# File: main.py
# -*- coding: utf-8 -*-
"""
Production API für KI‑Status‑Report (Gold‑Standard+)
- /briefing_async: Report bauen, an externen PDF‑Service senden (User + Admin)
- Admin‑Benachrichtigung per SMTP inkl. 3 JSON‑Anhängen:
    briefing_raw.json, briefing_normalized.json, briefing_missing_fields.json
- Idempotency pro Nutzer+Sprache (+ optionale Client‑Nonce)
- CORS, strukturierte Logs, Health‑Endpoints
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import smtplib
import time
import uuid
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from typing import Any, Dict, Optional

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from jose import jwt
from jose.exceptions import JWTError
from pydantic import BaseModel

# -----------------------------------------------------------------------------
# Konfiguration (ENV)
# -----------------------------------------------------------------------------

APP_NAME = os.getenv("APP_NAME", "make-ki-backend")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("backend")

JWT_SECRET = os.getenv("JWT_SECRET", os.getenv("SECRET_KEY", "dev-secret"))
JWT_ALGO = "HS256"

IDEMPOTENCY_TTL_SECONDS = int(os.getenv("IDEMPOTENCY_TTL_SECONDS", "3600"))  # 1 h
IDEMPOTENCY_DIR = os.getenv("IDEMPOTENCY_DIR", "/tmp/ki_idempotency")

BASE_DIR = os.path.abspath(os.getenv("APP_BASE", os.getcwd()))
TEMPLATE_DIR = os.getenv("TEMPLATE_DIR", os.path.join(BASE_DIR, "templates"))

PDF_SERVICE_URL = (os.getenv("PDF_SERVICE_URL") or "").rstrip("/")
_pdf_timeout_raw = int(os.getenv("PDF_TIMEOUT", "45"))
PDF_TIMEOUT = _pdf_timeout_raw / 1000 if _pdf_timeout_raw > 1000 else _pdf_timeout_raw
PDF_MAX_BYTES = int(os.getenv("PDF_MAX_BYTES", str(10 * 1024 * 1024)))
PDF_STRIP_SCRIPTS = os.getenv("PDF_STRIP_SCRIPTS", "1").strip().lower() in {"1", "true", "yes"}

# Versand / Empfänger
SEND_TO_USER = os.getenv("SEND_TO_USER", "1").strip().lower() in {"1", "true", "yes"}
ADMIN_NOTIFY = os.getenv("ADMIN_NOTIFY", "1").strip().lower() in {"1", "true", "yes"}
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", os.getenv("SMTP_FROM", ""))

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "noreply@example.com")

# CORS
CORS_ALLOW = [o.strip() for o in (os.getenv("CORS_ALLOW_ORIGINS") or "*").split(",") if o.strip()]
if not CORS_ALLOW:
    CORS_ALLOW = ["*"]

# -----------------------------------------------------------------------------
# Utils
# -----------------------------------------------------------------------------

def _now_str() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _sanitize_email(value: Optional[str]) -> str:
    _, addr = parseaddr(value or "")
    return addr or ""


def _lang_from_body(body: Dict[str, Any]) -> str:
    lang = str(body.get("lang") or body.get("language") or "de").lower()
    return "de" if lang.startswith("de") else "en"


def _new_job_id() -> str:
    return uuid.uuid4().hex


def _sha256(s: str) -> str:
    import hashlib
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _smtp_send(msg: EmailMessage) -> None:
    """Versendet E-Mail über SMTP, sofern konfiguriert."""
    if not SMTP_HOST or not SMTP_FROM:
        log.info("[mail] SMTP deaktiviert oder unkonfiguriert")
        return
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
        try:
            s.starttls()
        except Exception:
            pass
        if SMTP_USER and SMTP_PASS:
            s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)


def _idem_seen(key: str) -> bool:
    """Einfache Idempotenz-Sperre via Dateisystem."""
    path = os.path.join(IDEMPOTENCY_DIR, key)
    try:
        os.makedirs(IDEMPOTENCY_DIR, exist_ok=True)
    except Exception:
        pass
    if os.path.exists(path):
        try:
            age = time.time() - os.path.getmtime(path)
            if age < IDEMPOTENCY_TTL_SECONDS:
                return True
        except Exception:
            return True
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(_now_str())
    except Exception:
        return False
    return False


# -----------------------------------------------------------------------------
# Auth (Minimal)
# -----------------------------------------------------------------------------

class LoginReq(BaseModel):
    email: str


def _issue_token(email: str) -> str:
    payload = {"sub": email, "iat": int(time.time()), "exp": int(time.time() + 14 * 24 * 3600)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


async def current_user(req: Request) -> Dict[str, Any]:
    """Optionales JWT aus Authorization: Bearer <token> lesen, sonst anon."""
    auth = req.headers.get("authorization") or ""
    parts = auth.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        try:
            payload = jwt.decode(parts[1], JWT_SECRET, algorithms=[JWT_ALGO])
            return {"sub": payload.get("sub"), "email": payload.get("sub")}
        except JWTError:
            pass
    return {"sub": "anon", "email": ""}


# -----------------------------------------------------------------------------
# PDF-Service (Puppeteer)
# -----------------------------------------------------------------------------

async def warmup_pdf_service(rid: str) -> None:
    if not PDF_SERVICE_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as cli:
            r = await cli.get(f"{PDF_SERVICE_URL}/health")
            log.info("[PDF] rid=%s warmup %s", rid, r.status_code)
    except Exception as exc:
        log.warning("[PDF] warmup failed: %s", exc)


async def send_html_to_pdf_service(
    html: str,
    recipient: str,
    subject: str,
    lang: str,
    rid: str,
    filename: str,
    admin_copy: bool = False,
) -> Dict[str, Any]:
    if not PDF_SERVICE_URL:
        raise RuntimeError("PDF_SERVICE_URL not configured")

    payload = {
        "html": html,
        "lang": lang,
        "subject": subject,
        "recipient": recipient,
        "filename": filename,
        "stripScripts": PDF_STRIP_SCRIPTS,
        "maxBytes": PDF_MAX_BYTES,
        "meta": {"rid": rid, "admin": admin_copy, "app": APP_NAME},
    }

    try:
        async with httpx.AsyncClient(timeout=PDF_TIMEOUT) as cli:
            resp = await cli.post(f"{PDF_SERVICE_URL}/generate-pdf", json=payload)
            return {"ok": resp.status_code == 200, "status": resp.status_code, "detail": resp.text[:500]}
    except Exception as exc:
        log.error("[PDF] send failed: %s", exc)
        return {"ok": False, "status": 0, "detail": str(exc)}


# -----------------------------------------------------------------------------
# Admin-Notice (mit 3 JSON‑Anhängen aus gpt_analyze.produce_admin_attachments)
# -----------------------------------------------------------------------------

def send_admin_notice(
    job_id: str,
    admin_to: str,
    lang: str,
    user_email: str,
    pdf_service_url: str,
    raw_payload: Optional[Dict[str, Any]] = None,
    attachments: Optional[Dict[str, bytes]] = None,
) -> None:
    if not admin_to:
        return

    subject = (
        f"Neuer KI‑Status Report – {user_email or 'unbekannt'}"
        if lang == "de"
        else f"New AI Status Report – {user_email or 'unknown'}"
    )
    lines = [
        f"Job-ID: {job_id}",
        f"Lang: {lang}",
        f"User: {user_email or '-'}",
        f"PDF-Service: {pdf_service_url or '-'}",
        "Hinweis: Diese Mail ist die Admin-Benachrichtigung (PDF kommt separat).",
    ]
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr(("KI‑Sicherheit", SMTP_FROM))
    msg["To"] = admin_to
    msg.set_content("\n".join(lines))

    # JSON-Anhänge
    if raw_payload:
        raw_bytes = json.dumps(raw_payload, ensure_ascii=False, indent=2).encode("utf-8")
        msg.add_attachment(raw_bytes, maintype="application", subtype="json", filename="briefing_raw.json")
    for name, data in (attachments or {}).items():
        msg.add_attachment(data, maintype="application", subtype="json", filename=name)

    try:
        _smtp_send(msg)
        log.info("[mail] admin notice sent to %s", admin_to)
    except Exception as exc:
        log.warning("[mail] admin notice failed: %s", exc)


# -----------------------------------------------------------------------------
# FastAPI App & Endpunkte
# -----------------------------------------------------------------------------

app = FastAPI(title=APP_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW if CORS_ALLOW else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/ready")
def ready() -> dict:
    return {"ok": True, "ts": _now_str()}


@app.post("/api/login")
def api_login(req: LoginReq) -> Dict[str, Any]:
    email = _sanitize_email(req.email)
    if not email:
        raise HTTPException(status_code=400, detail="email required")
    token = _issue_token(email)
    return {"token": token, "email": email}


@app.post("/briefing_async")
async def briefing_async(
    body: Dict[str, Any],
    request: Request,
    tasks: BackgroundTasks,
    user=Depends(current_user),
):
    """
    Report generieren und via PDF‑Service als E-Mail versenden (User + Admin).
    Idempotenz: Hash aus Body + user/lang (+ optionaler Client‑Nonce).
    """
    lang = _lang_from_body(body)
    recipient_user = _sanitize_email(
        body.get("to") or body.get("email") or (user or {}).get("email") or ADMIN_EMAIL
    )
    if not recipient_user:
        raise HTTPException(status_code=400, detail="recipient could not be resolved")

    # optionale Client‑Nonce
    nonce = str(body.get("nonce") or request.headers.get("x-request-id") or request.headers.get("x-idempotency-key") or "")
    idem_key = _sha256(json.dumps({"body": body, "user": recipient_user, "lang": lang, "nonce": nonce}, sort_keys=True, ensure_ascii=False))
    if _idem_seen(idem_key):
        log.info("[idem] duplicate (user=%s, lang=%s) – skipping", recipient_user, lang)
        return JSONResponse({"status": "duplicate", "job_id": _new_job_id()})

    # gpt_analyze import (Report + Admin-Anhänge)
    try:
        from gpt_analyze import analyze_briefing, produce_admin_attachments  # type: ignore
    except Exception as exc:
        log.error("gpt_analyze import failed: %s", exc)
        raise HTTPException(status_code=500, detail="analysis module not available")

    # Formdaten flachziehen
    form_data = dict(body.get("answers") or {})
    for k, v in body.items():
        form_data.setdefault(k, v)

    job_id = _new_job_id()
    await warmup_pdf_service("briefing_async")

    # HTML-Report
    try:
        html = analyze_briefing(form_data, lang=lang)
    except Exception as exc:
        log.error("analyze_briefing failed: %s", exc)
        raise HTTPException(status_code=500, detail="rendering failed")

    # Versand (User + Admin via PDF‑Service)
    subject = "KI‑Status Report" if lang == "de" else "AI Status Report"
    fname_user = _safe_pdf_filename(recipient_user or "user", "KI-Status-Report", lang)

    user_result = {"ok": False, "status": 0, "detail": "skipped"}
    if SEND_TO_USER:
        user_result = await send_html_to_pdf_service(html, recipient_user, subject, lang, job_id, fname_user, admin_copy=False)

    admin_result = {"ok": False, "status": 0, "detail": "skipped"}
    if ADMIN_EMAIL:
        fname_admin = _safe_pdf_filename(ADMIN_EMAIL, "KI-Status-Report", lang)[:-4] + "-admin.pdf"
        admin_result = await send_html_to_pdf_service(html, ADMIN_EMAIL, subject + " (Admin copy)", lang, f"{job_id}-admin", fname_admin, admin_copy=True)

    # Admin-Mail mit Rohdaten + 3 JSON‑Anhängen
    attachments: Dict[str, bytes] = {}
    try:
        tri = produce_admin_attachments(form_data)  # -> dict[str,str]
        attachments = {name: content.encode("utf-8") for name, content in tri.items()}
    except Exception as exc:
        log.warning("produce_admin_attachments failed: %s (fallback: raw only)", exc)

    if ADMIN_NOTIFY and ADMIN_EMAIL:
        try:
            send_admin_notice(job_id, ADMIN_EMAIL, lang, recipient_user, PDF_SERVICE_URL, raw_payload=form_data, attachments=attachments)
        except Exception as exc:
            log.warning("admin notice failed: %s", exc)

    return JSONResponse({"status": "ok", "job_id": _new_job_id(), "user_pdf": user_result, "admin_pdf": admin_result})


def _safe_pdf_filename(user_email: str, prefix: str, lang: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9_.-]+", "_", (user_email or "user").split("@")[0]) or "user"
    return f"{prefix}-{base}-{lang}.pdf"


@app.post("/pdf_test")
async def pdf_test(body: Dict[str, Any], request: Request, user=Depends(current_user)):
    """Debug-Endpoint: beliebiges HTML an den PDF‑Service schicken."""
    lang = _lang_from_body(body)
    html = body.get("html") or "<!doctype html><meta charset='utf-8'><h1>Ping</h1>"
    to = _sanitize_email(body.get("to") or user.get("email") or ADMIN_EMAIL)
    await warmup_pdf_service("pdf_test")
    subject = "KI‑Readiness Report (Test)" if lang == "de" else "AI Readiness Report (Test)"
    fname = _safe_pdf_filename(to or "user", "pdf_test", lang)
    return await send_html_to_pdf_service(html, to, subject, lang, "pdf_test", fname)


@app.post("/feedback")
async def feedback(body: Dict[str, Any]) -> Dict[str, Any]:
    log.info("[feedback] received: keys=%s", list(body.keys()))
    return {"status": "ok", "received": True, "ts": _now_str()}


@app.get("/")
def root() -> HTMLResponse:
    return HTMLResponse(f"<!doctype html><meta charset='utf-8'><h1>{APP_NAME}</h1><p>OK – {_now_str()}</p>")
