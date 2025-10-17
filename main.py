# filename: main.py
# -*- coding: utf-8 -*-
# FastAPI Main – resilient import (queue_stats optional), Admin-Status with graceful fallback

from __future__ import annotations

import base64
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request, Response, status, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, HTMLResponse
try:
    from fastapi.templating import Jinja2Templates
    TEMPLATES_AVAILABLE = True
except Exception:
    TEMPLATES_AVAILABLE = False
    Jinja2Templates = None  # type: ignore

from pydantic import BaseModel, EmailStr, Field

from settings import settings, allowed_origins
from analyzer import run_analysis
from db import init_db, get_session
from models import Task, Feedback as FeedbackModel
from rate_limiter import is_limited
from security import verify_password
from sqlalchemy import text
from jose import jwt, JWTError
from mail_utils import send_email_with_attachments
from gpt_analyze import produce_admin_attachments

# ---- queue_redis imports: get_stats optional to avoid import-time crash on older file versions
try:
    from queue_redis import enqueue_report, enabled as queue_enabled, get_stats as queue_stats
except Exception:
    try:
        from queue_redis import enqueue_report, enabled as queue_enabled  # type: ignore
    except Exception:
        # minimal shims if queue_redis module itself is absent; app still works in local background mode
        def queue_enabled() -> bool:
            return False
        def enqueue_report(report_id: str, payload: Dict[str, Any]) -> bool:
            return False
    def queue_stats() -> Dict[str, int]:
        return {"queued": 0, "started": 0, "finished": 0, "failed": 0, "deferred": 0, "scheduled": 0}

LOG_LEVEL = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("ki-backend")

app = FastAPI(title="KI-Status-Report Backend", version="2025.10")

if TEMPLATES_AVAILABLE:
    templates = Jinja2Templates(directory="templates")

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
    lang: str = Field(default=settings.DEFAULT_LANG)
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

from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["method","endpoint","http_status"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "Request latency", ["endpoint"])

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
    try:
        from routes import briefing as _briefing
        app.include_router(_briefing.router)
        logger.info("Included routes.briefing")
    except Exception as e1:
        try:
            from app.routes import briefing as _briefing
            app.include_router(_briefing.router)
            logger.info("Included app.routes.briefing")
        except Exception as e2:
            logger.warning("Briefing routes not included: %s / %s", e1, e2)

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
        "status": "ok"
    }

def _client_ip(request: Request) -> str:
    h = request.headers.get("X-Forwarded-For") or request.headers.get("X-Real-IP") or ""
    if "," in h:
        h = h.split(",", 1)[0].strip()
    return h or (request.client.host if request.client else "unknown")

def _effective_lang(code: Optional[str]) -> str:
    c = (code or settings.DEFAULT_LANG or "DE").upper()
    return c if c in {"DE","EN"} else "DE"

def _persist_and_schedule(ip: str, payload: AnalyzePayload, background: BackgroundTasks) -> str:
    import uuid
    report_id = str(uuid.uuid4())
    with get_session() as s:
        t = Task(
            id=report_id,
            status="queued",
            company=payload.company,
            email=(payload.email or None),
            lang=_effective_lang(payload.lang),
            answers_json=payload.answers,
            ip=ip
        )
        s.add(t)
    if queue_enabled():
        ok = enqueue_report(report_id, payload.model_dump())
        if not ok:
            # Fallback auf lokalen BackgroundTask, damit Requests nicht „hängen bleiben“
            background.add_task(_local_background_job, report_id, payload.model_dump())
    else:
        background.add_task(_local_background_job, report_id, payload.model_dump())
    return report_id

@app.post("/analyze", response_model=AnalyzeResult)
async def analyze(request: Request, payload: AnalyzePayload, background: BackgroundTasks):
    ip = _client_ip(request)
    rl_keys = []
    if payload.email:
        rl_keys.append(f"email:{payload.email.lower()}")
    rl_keys.append(f"ip:{ip}")
    for key in rl_keys:
        blocked, _ = is_limited(key, settings.API_RATE_LIMIT_PER_HOUR, settings.API_RATE_LIMIT_WINDOW_SECONDS)
        if blocked:
            headers = {"Retry-After": str(settings.API_RATE_LIMIT_WINDOW_SECONDS)}
            raise HTTPException(429, detail="Rate limit exceeded", headers=headers)

    report_id = _persist_and_schedule(ip, payload, background)
    return AnalyzeResult(report_id=report_id, status="queued", html=None, meta={"lang": _effective_lang(payload.lang)})

@app.post("/briefing_async")
async def briefing_async(request: Request, payload: Dict[str, Any] = Body(...), background: BackgroundTasks = None):
    ip = _client_ip(request)
    company = payload.get("company") or payload.get("unternehmen") or payload.get("firma") or "Unbekannt"
    email = payload.get("email") or payload.get("to")
    lang = _effective_lang(payload.get("lang"))
    answers = payload.get("answers")
    if not isinstance(answers, dict):
        known = {"company","unternehmen","firma","email","to","lang","answers","options"}
        answers = {k: v for k, v in payload.items() if k not in known}
    options = payload.get("options") or {}
    ap = AnalyzePayload(lang=lang, company=company, email=email, answers=answers, options=options)

    rl_keys = []
    if ap.email:
        rl_keys.append(f"email:{ap.email.lower()}")
    rl_keys.append(f"ip:{ip}")
    for key in rl_keys:
        blocked, _ = is_limited(key, settings.API_RATE_LIMIT_PER_HOUR, settings.API_RATE_LIMIT_WINDOW_SECONDS)
        if blocked:
            headers = {"Retry-After": str(settings.API_RATE_LIMIT_WINDOW_SECONDS)}
            raise HTTPException(429, detail="Rate limit exceeded", headers=headers)

    report_id = _persist_and_schedule(ip, ap, background)
    return {"ok": True, "status": "queued", "report_id": report_id, "lang": ap.lang}

async def _local_background_job(report_id: str, payload: dict):
    try:
        html = await run_analysis(payload) if hasattr(run_analysis, "__call__") else None  # async compat
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

async def _generate_pdf(html: str, filename: str = "report.pdf"):
    if not html:
        return None
    if settings.PDF_SERVICE_URL:
        try:
            async with httpx.AsyncClient(timeout=settings.PDF_TIMEOUT/1000) as client:
                resp = await client.post(str(settings.PDF_SERVICE_URL), json={"html": html, "filename": filename})
                ctype = (resp.headers.get("content-type") or "").lower()
                if "application/pdf" in ctype or "application/octet-stream" in ctype:
                    return resp.content
                try:
                    data = resp.json()
                    for key in ("pdf_base64", "data", "pdf"):
                        if isinstance(data.get(key), str):
                            b64s = data[key]
                            if ";base64," in b64s:
                                b64s = b64s.split(",", 1)[1]
                            import base64 as _b
                            return _b.b64decode(b64s)
                except Exception:
                    pass
        except Exception as e:
            logger.warning("PDF service failed: %s", e)
    return None

@app.post("/generate-pdf")
async def generate_pdf(payload: Dict[str, Any]):
    html = str(payload.get("html", ""))
    filename = str(payload.get("filename", "report.pdf"))
    if not html:
        raise HTTPException(400, "missing html")
    pdf_bytes = await _generate_pdf(html, filename)
    if pdf_bytes:
        import base64
        return {
            "mode": "service",
            "content_type": "application/pdf;base64",
            "data": base64.b64encode(pdf_bytes).decode("ascii"),
            "filename": filename
        }
    b64 = base64.b64encode(html.encode("utf-8")).decode("ascii")
    return {"mode": "fallback", "content_type": "text/html;base64", "data": b64, "filename": filename}

@app.post("/feedback")
async def feedback(request: Request, item: Feedback, background: BackgroundTasks):
    ip = _client_ip(request)
    with get_session() as s:
        fb = FeedbackModel(email=item.email, name=item.name, message=item.message, meta=item.context, ip=ip)
        s.add(fb)
    background.add_task(
        _send_email,
        settings.FEEDBACK_TO,
        f"{settings.MAIL_SUBJECT_PREFIX} Feedback",
        f"From: {item.name or '-'} <{item.email}>\n\n{item.message}"
    )
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
                s.starttls()
                s.login(settings.SMTP_USER, settings.SMTP_PASS)
            s.send_message(msg)
    except Exception as e:
        logger.warning("send email failed: %s", e)

class LoginPayload(BaseModel):
    email: EmailStr
    password: str

def _get_user_credentials(email: str):
    with get_session() as s:
        res = s.execute(text("SELECT password_hash, role FROM users WHERE LOWER(email)=:email"), {"email": email.lower()})
        return res.fetchone()

def get_current_user(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token = auth_header.split(" ", 1)[1]
    try:
        data = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return data

@app.post("/api/login")
async def login(payload: LoginPayload):
    row = _get_user_credentials(payload.email)
    if not row or not verify_password(payload.password, row[0]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    token = jwt.encode({"email": payload.email, "role": row[1]}, settings.JWT_SECRET, algorithm="HS256")
    return {"access_token": token}

@app.get("/admin/submissions")
async def admin_submissions(request: Request):
    current = get_current_user(request)
    if current.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    with get_session() as s:
        tasks = s.query(Task).order_by(Task.created_at.desc()).all()
        items = []
        for t in tasks:
            try:
                created_ts = int(t.created_at.timestamp())
            except Exception:
                created_ts = None
            items.append({
                "job_id": t.id,
                "user_email": t.email or "",
                "created": created_ts,
                "score_percent": getattr(t, "score_percent", None) or None
            })
    return items

@app.post("/admin/submissions/{report_id}/regenerate")
async def admin_regenerate(report_id: str, request: Request):
    current = get_current_user(request)
    if current.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    with get_session() as s:
        t = s.get(Task, report_id)
        if not t:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report ID not found")
        if not t.html:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No report content to regenerate")
        html_content = t.html
        recipient_email = t.email
        raw_answers = t.answers_json or {}
        lang = (t.lang or "DE").lower()
    filename_base = f"KI-Status-Report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    pdf_bytes = await _generate_pdf(html_content, filename=f"{filename_base}.pdf")
    user_attach = {}
    if pdf_bytes:
        user_attach[f"{filename_base}.pdf"] = pdf_bytes
    else:
        user_attach[f"{filename_base}.html"] = html_content.encode("utf-8")
    admin_attach = {}
    if pdf_bytes:
        admin_attach[f"{filename_base}-admin.pdf"] = pdf_bytes
    else:
        admin_attach[f"{filename_base}-admin.html"] = html_content.encode("utf-8")
    try:
        tri = produce_admin_attachments(raw_answers, lang=lang)
        for name, content in tri.items():
            admin_attach[name] = content.encode("utf-8")
    except Exception as e:
        logger.warning("Admin attachments generation failed: %s", e)
    if recipient_email:
        try:
            await send_email_with_attachments(
                to_address=recipient_email,
                subject=f"{settings.MAIL_SUBJECT_PREFIX} – KI-Status-Report (Neuversand)",
                html_body="<p>Ihr KI-Status-Report wurde erneut erstellt. Der Report ist als PDF angehängt.</p>",
                attachments=user_attach
            )
            logger.info("[mail] Resent report to user %s", recipient_email)
        except Exception as e:
            logger.exception("Resend user mail failed: %s", e)
            raise HTTPException(status_code=500, detail="User email failed")
    try:
        await send_email_with_attachments(
            to_address=settings.ADMIN_EMAIL,
            subject=f"{settings.MAIL_SUBJECT_PREFIX} – Admin: Report neu generiert",
            html_body=f"<p>Report {report_id} wurde neu generiert und gesendet.</p>",
            attachments=admin_attach
        )
        logger.info("[mail] Resent report %s to admin", report_id)
    except Exception as e:
        logger.exception("Resend admin mail failed: %s", e)
        raise HTTPException(status_code=500, detail="Admin email failed")
    return {"ok": True, "job_id": report_id}

@app.get("/admin/status")
async def admin_status(request: Request):
    # DB-Zahlen
    with get_session() as s:
        total = s.query(Task).count()
        done = s.query(Task).filter(Task.status == "done").count()
        running = s.query(Task).filter(Task.status == "running").count() if hasattr(Task, "status") else 0
        queued = s.query(Task).filter(Task.status == "queued").count()
        failed = s.query(Task).filter(Task.status == "failed").count()
        last = s.query(Task).order_by(Task.created_at.desc()).limit(20).all()

    # Queue-Zahlen (falls Redis aktiv)
    qstats = queue_stats() if queue_enabled() else {"queued": 0, "started": 0, "finished": 0, "failed": 0, "deferred": 0, "scheduled": 0}
    flags = {
        "eu_host_check": settings.ENABLE_EU_HOST_CHECK,
        "idempotency": settings.ENABLE_IDEMPOTENCY,
        "quality": settings.QUALITY_CONTROL_AVAILABLE,
        "pdf_service": bool(settings.PDF_SERVICE_URL),
    }

    # Template bevorzugen
    if TEMPLATES_AVAILABLE:
        try:
            return templates.TemplateResponse("admin_status.html", {
                "request": request,
                "queue_mode": "Redis" if queue_enabled() else "Local",
                "flags": flags,
                "db": {"total": total, "done": done, "running": running, "queued": queued, "failed": failed, "last": last},
                "q": qstats
            })
        except Exception:
            pass

    # Fallback: Inline HTML
    rows = []
    for t in last:
        rows.append(
            f"<tr><td>{t.id}</td><td>{t.status}</td>"
            f"<td>{(t.company or '')}</td><td>{(t.email or '')}</td>"
            f"<td>{getattr(t,'created_at', '')}</td><td>{getattr(t,'finished_at','')}</td></tr>"
        )
    html = (
        "<!doctype html><meta charset='utf-8'>"
        "<title>Admin Status</title>"
        "<style>body{font:14px/1.45 system-ui,Segoe UI,Roboto,Helvetica,Arial}table{border-collapse:collapse}"
        "th,td{border:1px solid #ddd;padding:6px 8px}th{text-align:left;background:#f6f8fa}"
        ".muted{color:#666}</style>"
        f"<h1>Admin Status</h1>"
        f"<p><b>Queue:</b> {'Redis' if queue_enabled() else 'Local'}</p>"
        f"<ul><li>Gesamt: {total}</li><li>Fertig: {done}</li><li>Laufend: {running}</li><li>Queued: {queued}</li><li>Fehlgeschlagen: {failed}</li></ul>"
        "<h2>Feature‑Flags</h2>"
        f"<pre class='muted'>{json.dumps(flags, ensure_ascii=False, indent=2)}</pre>"
        "<h2>Redis Queue</h2>"
        f"<pre class='muted'>{json.dumps(qstats, ensure_ascii=False, indent=2)}</pre>"
        "<h2>Letzte 20 Tasks</h2>"
        "<table><thead><tr><th>ID</th><th>Status</th><th>Firma</th><th>E‑Mail</th><th>Erstellt</th><th>Fertig</th></tr></thead>"
        f"<tbody>{''.join(rows) if rows else '<tr><td colspan=6 class=muted>Keine Tasks</td></tr>'}</tbody></table>"
    )
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})

@app.get("/")
def root():
    return PlainTextResponse("KI-Status-Report Backend OK")
