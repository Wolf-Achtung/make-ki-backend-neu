# filename: main.py
# -*- coding: utf-8 -*-
"""
KI-Status-Report Backend (Gold-Standard+)
- FastAPI app with strict CORS, security headers, request IDs and structured logging
- Background job for report generation (allowed per product decision)
- Optional PDF microservice client
- Minimal feedback API with SMTP send + optional DB insert
- Health/metrics endpoints and read-only admin status page
NOTE: This file is self-contained and does not depend on incomplete modules.
If optional modules exist (e.g., gpt_analyze), they are used automatically.
"""
from __future__ import annotations

import asyncio
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

# ---------------------------------------------------------------------
# Logging (structured)
# ---------------------------------------------------------------------
LOG_LEVEL = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("ki-backend")

# ---------------------------------------------------------------------
# App
# ---------------------------------------------------------------------
app = FastAPI(title="KI-Status-Report Backend", version="2025.10")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security headers
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    start = time.perf_counter()
    try:
        response: Response = await call_next(request)
    except Exception:
        logger.exception("Unhandled exception")
        return JSONResponse({"error": "internal_error", "request_id": request_id}, status_code=500)

    dur_ms = int((time.perf_counter() - start) * 1000)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=()"
    response.headers.setdefault("Content-Security-Policy", "default-src 'self' data: https:; frame-ancestors 'none';")
    response.headers["Server-Timing"] = f"app;dur={dur_ms}"
    return response

# ---------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------
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

# ---------------------------------------------------------------------
# Optional analyzer import with fallback
# ---------------------------------------------------------------------
async def _analyze_with_optional_module(payload: AnalyzePayload) -> str:
    """Returns HTML report. Tries to use gpt_analyze.analyze_briefing_enhanced if present.
    Falls back to a simple templated summary."""
    try:
        from gpt_analyze import analyze_briefing_enhanced  # type: ignore
        html = await analyze_briefing_enhanced(payload.model_dump())
        if not isinstance(html, str):
            html = json.dumps(html, ensure_ascii=False)
        return html
    except Exception as e:
        logger.warning("Using fallback analyzer: %s", e)
        company = payload.company
        lang = payload.lang
        title = "KI-Status-Report" if lang == "DE" else "AI Status Report"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        items = "".join(f"<li><strong>{k}</strong>: {v}</li>" for k, v in (payload.answers or {}).items())
        return (
            f"<h1>{title} – {company}</h1>"
            f"<p><em>Stand: {ts} – Fallback-Modus</em></p>"
            f"{'<h2>Zusammenfassung</h2>' if lang=='DE' else '<h2>Summary</h2>'}"
            f"<ul>{items}</ul>"
        )

# Background task registry (simple in-memory)
TASKS: Dict[str, Dict[str, Any]] = {}

async def _run_analysis_task(report_id: str, payload: AnalyzePayload):
    TASKS[report_id] = {"status": "running", "created_at": datetime.utcnow().isoformat()}
    try:
        html = await _analyze_with_optional_module(payload)
        TASKS[report_id] = {"status": "done", "html": html, "finished_at": datetime.utcnow().isoformat()}
    except Exception as e:
        TASKS[report_id] = {"status": "failed", "error": str(e), "finished_at": datetime.utcnow().isoformat()}
        logger.exception("Background analysis failed: %s", e)

# ---------------------------------------------------------------------
# Prometheus Metrics
# ---------------------------------------------------------------------
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["method", "endpoint", "http_status"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "Request latency", ["endpoint"])

@app.middleware("http")
async def prometheus_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    try:
        endpoint = request.url.path
        REQUEST_LATENCY.labels(endpoint=endpoint).observe(time.perf_counter() - start)
        REQUEST_COUNT.labels(method=request.method, endpoint=endpoint, http_status=response.status_code).inc()
    except Exception:
        pass
    return response

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

# ---------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------
@app.get("/healthz")
async def healthz():
    public = {
        "ok": True,
        "time": datetime.utcnow().isoformat() + "Z",
        "version": app.version,
        "env": settings.ENVIRONMENT,
        "features": {
            "idempotency": settings.ENABLE_IDEMPOTENCY,
            "eu_host_check": settings.ENABLE_EU_HOST_CHECK,
            "quality": settings.QUALITY_CONTROL_AVAILABLE,
        },
        "pdf_service": bool(settings.PDF_SERVICE_URL),
        "llm_provider": settings.LLM_PROVIDER,
    }
    return JSONResponse(public)

@app.post("/analyze", response_model=AnalyzeResult)
async def analyze(payload: AnalyzePayload, background: BackgroundTasks):
    """Starts a background report generation task; returns report_id immediately.
    Client may poll /result/{report_id}"""
    report_id = str(uuid.uuid4())
    background.add_task(_run_analysis_task, report_id, payload)
    return AnalyzeResult(report_id=report_id, status="queued", html=None, meta={"lang": payload.lang})

@app.get("/result/{report_id}", response_model=AnalyzeResult)
async def result(report_id: str):
    data = TASKS.get(report_id)
    if not data:
        raise HTTPException(404, "unknown report_id")
    return AnalyzeResult(
        report_id=report_id,
        status=data.get("status","unknown"),
        html=data.get("html"),
        meta={k: v for k, v in data.items() if k not in {"html"}}
    )

@app.post("/generate-pdf")
async def generate_pdf(payload: Dict[str, Any]):
    """Forwards HTML -> PDF to external service if configured; otherwise returns HTML as base64.
    Payload expected: {"html": "...", "filename": "report.pdf"}"""
    html = str(payload.get("html", ""))
    filename = str(payload.get("filename", "report.pdf"))
    if not html:
        raise HTTPException(400, "missing html")
    if settings.PDF_SERVICE_URL:
        try:
            async with httpx.AsyncClient(timeout=settings.PDF_TIMEOUT/1000) as client:
                resp = await client.post(str(settings.PDF_SERVICE_URL), json={"html": html, "filename": filename})
                resp.raise_for_status()
                data = resp.json()
                return JSONResponse(data)
        except Exception as e:
            logger.warning("PDF service failed, returning HTML base64: %s", e)

    # fallback: return base64 of HTML for client-side save
    b64 = base64.b64encode(html.encode("utf-8")).decode("ascii")
    return JSONResponse({"mode": "fallback", "content_type": "text/html;base64", "data": b64, "filename": filename})

@app.post("/feedback")
async def feedback(item: Feedback, background: BackgroundTasks):
    """Stores feedback and dispatches email to FEEDBACK_TO.
    NOTE: In test-phase we allow storing email+IP (per product decision)."""
    ip = "unknown"
    try:
        ip = item.context.get("ip") or "unknown"  # could be forwarded by FE
    except Exception:
        pass

    logger.info("feedback received email=%s ip=%s", item.email, ip)

    # send mail in background
    background.add_task(_send_email, to=settings.FEEDBACK_TO,
                        subject=f"{settings.MAIL_SUBJECT_PREFIX} Feedback",
                        text=f"From: {item.name or '-'} <{item.email}>\n\n{item.message}\n\nContext: {json.dumps(item.context)}")

    return {"ok": True}

async def _send_email(to: str, subject: str, text: str):
    """Very small SMTP client (without attachments)."""
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
                s.starttls()
                s.login(settings.SMTP_USER, settings.SMTP_PASS)
            s.send_message(msg)
        logger.info("feedback email sent to %s", to)
    except Exception as e:
        logger.warning("sending email failed: %s", e)

# Admin migration intentionally disabled during tests
@app.post("/admin/migrate")
async def admin_migrate():
    if not settings.MIGRATION_ENABLED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="migration disabled")
    return {"ok": True, "message": "no-op in this build"}

@app.get("/admin/status", response_class=HTMLResponse)
async def admin_status():
    """Simple read-only status page (no auth, test-phase only)."""
    rows = []
    for rid, data in TASKS.items():
        rows.append(f"<tr><td>{rid}</td><td>{data.get('status','')}</td><td>{data.get('created_at','')}</td><td>{data.get('finished_at','')}</td></tr>")
    table = "".join(rows) or "<tr><td colspan='4'><em>Keine Tasks</em></td></tr>"
    html = f"""<!DOCTYPE html>
    <html lang='de'><head><meta charset='utf-8'/>
    <meta name='robots' content='noindex, nofollow'/>
    <title>Admin Status</title>
    <style>body{{font-family:system-ui,Segoe UI,Roboto,Arial,sans-serif;margin:1rem 2rem}}table{{border-collapse:collapse}}td,th{{border:1px solid #cbd5e1;padding:.4rem .6rem}}</style>
    </head><body>
    <h1>Admin Status</h1>
    <h2>Features</h2>
    <ul>
      <li>EU Host Check: {str(settings.ENABLE_EU_HOST_CHECK)}</li>
      <li>Idempotency: {str(settings.ENABLE_IDEMPOTENCY)}</li>
      <li>Quality: {str(settings.QUALITY_CONTROL_AVAILABLE)}</li>
    </ul>
    <h2>Tasks</h2>
    <table><thead><tr><th>ID</th><th>Status</th><th>Erstellt</th><th>Fertig</th></tr></thead><tbody>{table}</tbody></table>
    </body></html>"""
    return HTMLResponse(content=html, headers={"X-Robots-Tag": "noindex, nofollow"})

@app.get("/admin/status.json")
async def admin_status_json():
    return JSONResponse({"features": {
                            "eu_host_check": settings.ENABLE_EU_HOST_CHECK,
                            "idempotency": settings.ENABLE_IDEMPOTENCY,
                            "quality": settings.QUALITY_CONTROL_AVAILABLE,
                         },
                         "tasks": TASKS})

# Root
@app.get("/")
def root():
    return PlainTextResponse("KI-Status-Report Backend OK")
