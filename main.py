# filename: main.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, HTMLResponse
from pydantic import BaseModel, EmailStr, Field

from settings import settings, allowed_origins
from analyzer import run_analysis
from db import init_db, get_session
from models import Task, Feedback as FeedbackModel
from rate_limiter import is_limited
from queue_redis import enqueue_report, enabled as queue_enabled

LOG_LEVEL = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("ki-backend")

app = FastAPI(title="KI-Status-Report Backend", version="2025.10")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def security_headers(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    start = time.perf_counter()
    try:
        response: Response = await call_next(request)
    except Exception:
        logger.exception("Unhandled exception")
        return JSONResponse({"error": "internal_error", "request_id": request_id}, status_code=500)
    dur_ms = int((time.perf_counter() - start) * 1000)
    response.headers.update({
        "X-Request-ID": request_id,
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "geolocation=(), microphone=()"
    })
    response.headers.setdefault("Content-Security-Policy", "default-src 'self' data: https:; frame-ancestors 'none';")
    response.headers["Server-Timing"] = f"app;dur={dur_ms}"
    return response

class AnalyzePayload(BaseModel):
    lang: str = Field(default=settings.DEFAULT_LANG, pattern="^(DE|EN)$")
    company: str
    answers: Dict[str, Any] = Field(default_factory=dict)
    email: Optional[EmailStr] = None
    options: Dict[str, Any] = Field(default_factory=dict)

class AnalyzeResult(BaseModel):
    report_id: str
    status: str
    html: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)

class Feedback(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    message: str
    context: Dict[str, Any] = Field(default_factory=dict)

# Prometheus
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["method","endpoint","http_status"])  # noqa
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "Request latency", ["endpoint"])  # noqa

@app.middleware("http")
async def prometheus_mw(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    try:
        endpoint = request.url.path
        REQUEST_LATENCY.labels(endpoint=endpoint).observe(time.perf_counter() - start)
        REQUEST_COUNT.labels(method=request.method, endpoint=endpoint, http_status=response.status_code).inc()
    except Exception:
        pass
    return response

@app.on_event("startup")
def on_startup():
    init_db()

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/healthz")
async def healthz():
    return {
        "ok": True,
        "time": datetime.utcnow().isoformat() + "Z",
        "env": settings.ENVIRONMENT,
        "version": app.version,
        "features": {
            "eu_host_check": settings.ENABLE_EU_HOST_CHECK,
            "idempotency": settings.ENABLE_IDEMPOTENCY,
            "quality": settings.QUALITY_CONTROL_AVAILABLE,
        },
        "queue_enabled": queue_enabled(),
        "pdf_service": bool(settings.PDF_SERVICE_URL),
    }

def _client_ip(request: Request) -> str:
    h = request.headers.get("X-Forwarded-For") or request.headers.get("X-Real-IP") or ""
    if "," in h:
        h = h.split(",",1)[0].strip()
    return h or (request.client.host if request.client else "unknown")  # type: ignore

@app.post("/analyze", response_model=AnalyzeResult)
async def analyze(request: Request, payload: AnalyzePayload, background: BackgroundTasks):
    # Rate limit: per email & per IP
    ip = _client_ip(request)
    rl_keys = []
    if payload.email:
        rl_keys.append(f"email:{payload.email.lower()}")
    rl_keys.append(f"ip:{ip}")
    for key in rl_keys:
        blocked, remaining = is_limited(key, settings.API_RATE_LIMIT_PER_HOUR, settings.API_RATE_LIMIT_WINDOW_SECONDS)
        if blocked:
            headers = {"Retry-After": str(settings.API_RATE_LIMIT_WINDOW_SECONDS)}
            raise HTTPException(429, detail="Rate limit exceeded", headers=headers)

    report_id = str(uuid.uuid4())
    # Persist task
    with get_session() as s:
        t = Task(
            id=report_id, status="queued", company=payload.company, email=(payload.email or None),
            lang=payload.lang, answers_json=payload.answers, ip=ip
        )
        s.add(t)

    # Enqueue in Redis if configured, otherwise local background task
    if queue_enabled():
        enqueue_report(report_id, payload.model_dump())
    else:
        background.add_task(_local_background_job, report_id, payload.model_dump())

    return AnalyzeResult(report_id=report_id, status="queued", html=None, meta={"lang": payload.lang})

async def _local_background_job(report_id: str, payload: dict):
    try:
        html = await run_analysis(payload)
        with get_session() as s:
            t = s.get(Task, report_id)
            if t:
                t.status = "done"
                t.html = html
                t.finished_at = datetime.utcnow()
    except Exception as e:
        with get_session() as s:
            t = s.get(Task, report_id)
            if t:
                t.status = "failed"
                t.error = str(e)
                t.finished_at = datetime.utcnow()

@app.get("/result/{report_id}", response_model=AnalyzeResult)
async def result(report_id: str):
    with get_session() as s:
        t = s.get(Task, report_id)
        if not t:
            raise HTTPException(404, "unknown report_id")
        return AnalyzeResult(report_id=t.id, status=t.status, html=t.html, meta={
            "created_at": str(t.created_at), "finished_at": str(t.finished_at)
        })

@app.post("/generate-pdf")
async def generate_pdf(payload: Dict[str, Any]):
    html = str(payload.get("html", ""))
    filename = str(payload.get("filename", "report.pdf"))
    if not html:
        raise HTTPException(400, "missing html")
    if settings.PDF_SERVICE_URL:
        try:
            async with httpx.AsyncClient(timeout=settings.PDF_TIMEOUT/1000) as client:
                resp = await client.post(str(settings.PDF_SERVICE_URL), json={"html": html, "filename": filename})
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.warning("PDF service failed: %s", e)
    b64 = base64.b64encode(html.encode("utf-8")).decode("ascii")
    return {"mode": "fallback", "content_type": "text/html;base64", "data": b64, "filename": filename}

@app.post("/feedback")
async def feedback(request: Request, item: Feedback, background: BackgroundTasks):
    ip = _client_ip(request)
    # Save to DB
    with get_session() as s:
        fb = FeedbackModel(email=item.email, name=item.name, message=item.message, meta=item.context, ip=ip)
        s.add(fb)

    # Send asynchronously (best-effort)
    background.add_task(_send_email, settings.FEEDBACK_TO, f"{settings.MAIL_SUBJECT_PREFIX} Feedback",
                        f"From: {item.name or '-'} <{item.email}>\n\n{item.message}")

    return {"ok": True}

async def _send_email(to: str, subject: str, text: str):
    import smtplib
    from email.message import EmailMessage
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM}>"
        msg["To"] = to
        msg.set_content(text)
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as s:
            if settings.SMTP_USER and settings.SMTP_PASS:
                s.starttls(); s.login(settings.SMTP_USER, settings.SMTP_PASS)
            s.send_message(msg)
    except Exception as e:
        logger.warning("send email failed: %s", e)

@app.post("/admin/migrate")
async def admin_migrate():
    if not settings.MIGRATION_ENABLED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="migration disabled")
    return {"ok": True, "message": "no-op"}

@app.get("/admin/status", response_class=HTMLResponse)
async def admin_status():
    # Minimal read-only status page
    with get_session() as s:
        total = s.query(Task).count()
        done = s.query(Task).filter(Task.status=="done").count()
        running = s.query(Task).filter(Task.status=="running").count()
        failed = s.query(Task).filter(Task.status=="failed").count()
        latest = s.query(Task).order_by(Task.created_at.desc()).limit(20).all()

    rows = "".join(f"<tr><td>{t.id}</td><td>{t.status}</td><td>{t.company}</td><td>{t.email or ''}</td><td>{t.created_at}</td><td>{t.finished_at or ''}</td></tr>" for t in latest) or "<tr><td colspan='6'><em>Keine Tasks</em></td></tr>"
    html = f"""<!DOCTYPE html><html lang='de'><head><meta charset='utf-8'/>
    <meta name='robots' content='noindex, nofollow'/>
    <title>Admin Status</title>
    <style>body{{font-family:system-ui,Segoe UI,Roboto,Arial,sans-serif;margin:1rem 2rem}}table{{border-collapse:collapse}}td,th{{border:1px solid #cbd5e1;padding:.4rem .6rem}}</style>
    </head><body>
    <h1>Admin Status</h1>
    <p>Queue: {"Redis" if queue_enabled() else "Local"}</p>
    <ul>
      <li>Gesamt: {total}</li>
      <li>Fertig: {done}</li>
      <li>Laufend: {running}</li>
      <li>Fehlgeschlagen: {failed}</li>
    </ul>
    <h2>Letzte 20 Tasks</h2>
    <table><thead><tr><th>ID</th><th>Status</th><th>Firma</th><th>E-Mail</th><th>Erstellt</th><th>Fertig</th></tr></thead>
    <tbody>{rows}</tbody></table>
    </body></html>"""
    return HTMLResponse(content=html, headers={"X-Robots-Tag": "noindex, nofollow"})

@app.get("/admin/status.json")
async def admin_status_json():
    with get_session() as s:
        latest = s.query(Task).order_by(Task.created_at.desc()).limit(50).all()
        data = [{"id": t.id, "status": t.status, "company": t.company, "email": t.email, "created_at": str(t.created_at), "finished_at": str(t.finished_at)} for t in latest]
    return {"queue": ("redis" if queue_enabled() else "local"), "items": data}

@app.get("/")
def root():
    return PlainTextResponse("KI-Status-Report Backend OK")
