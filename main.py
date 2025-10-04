# File: main.py
# -*- coding: utf-8 -*-
"""
Production API für KI‑Status‑Report (Gold‑Standard+)

- /briefing_async: Report erzeugen, PDF via externem Service RENDERN,
  Versand per SMTP (1 Mail pro Empfänger) mit PDF+HTML im Anhang.
- Projekt‑Prefix im Betreff via MAIL_SUBJECT_PREFIX (z. B. "KI‑Ready/CustomerX").
- Kein doppeltes Admin‑Mailing mehr (PDF‑Service schickt keine Mails).
- Fallback: Wenn PDF‑Bytes nicht verfügbar sind, schicken wir HTML
  und können optional den PDF‑Service NUR für den USER als E‑Mail fallbacken.
"""

from __future__ import annotations

import base64
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

# PDF‑Service: nur Rendern (Bytes holen), kein Mailversand
PDF_SERVICE_URL = (os.getenv("PDF_SERVICE_URL") or "").rstrip("/")
_pdf_timeout_raw = int(os.getenv("PDF_TIMEOUT", "45"))
PDF_TIMEOUT = _pdf_timeout_raw / 1000 if _pdf_timeout_raw > 1000 else _pdf_timeout_raw
PDF_MAX_BYTES = int(os.getenv("PDF_MAX_BYTES", str(10 * 1024 * 1024)))
PDF_STRIP_SCRIPTS = os.getenv("PDF_STRIP_SCRIPTS", "1").strip().lower() in {"1", "true", "yes"}
PDF_EMAIL_FALLBACK_TO_USER = os.getenv("PDF_EMAIL_FALLBACK_TO_USER", "1").strip().lower() in {"1", "true", "yes"}

# Versand / Empfänger
SEND_TO_USER = os.getenv("SEND_TO_USER", "1").strip().lower() in {"1", "true", "yes"}
ADMIN_NOTIFY = os.getenv("ADMIN_NOTIFY", "1").strip().lower() in {"1", "true", "yes"}
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", os.getenv("SMTP_FROM", ""))

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "noreply@example.com")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "KI‑Sicherheit")

# Betreff‑Prefix (Projekt/Client)
MAIL_SUBJECT_PREFIX = os.getenv("MAIL_SUBJECT_PREFIX", "KI‑Ready")

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


def _idem_seen(key: str) -> bool:
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


def _smtp_send(msg: EmailMessage) -> None:
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


def _recipient_from(body: Dict[str, Any], fallback: str) -> str:
    answers = body.get("answers") or {}
    cand = (
        answers.get("to") or answers.get("email") or
        body.get("to") or body.get("email") or
        fallback
    )
    return _sanitize_email(cand)


def _display_name_from(body: Dict[str, Any]) -> str:
    for key in ("unternehmen", "firma", "company", "company_name", "organization"):
        val = (body.get("answers") or {}).get(key) or body.get(key)
        if val:
            return str(val)[:64]
    email = _recipient_from(body, ADMIN_EMAIL)
    return (email.split("@")[0] if email else "Customer").title()


def _build_subject(prefix: str, lang: str, display_name: str) -> str:
    core = "KI‑Status Report" if lang == "de" else "AI Status Report"
    return f"{prefix}/{display_name} – {core}"


def _safe_pdf_filename(display_name: str, lang: str) -> str:
    dn = re.sub(r"[^a-zA-Z0-9_.-]+", "_", display_name) or "user"
    return f"KI-Status-Report-{dn}-{lang}.pdf"


def _safe_html_filename(display_name: str, lang: str) -> str:
    dn = re.sub(r"[^a-zA-Z0-9_.-]+", "_", display_name) or "user"
    return f"KI-Status-Report-{dn}-{lang}.html"


# -----------------------------------------------------------------------------
# PDF-Service (Rendern – robust gegen verschiedene API-Varianten)
# -----------------------------------------------------------------------------

async def _render_pdf_bytes(html: str, filename: str) -> Optional[bytes]:
    if not (PDF_SERVICE_URL and html):
        return None
    async with httpx.AsyncClient(timeout=PDF_TIMEOUT) as cli:
        payload = {"html": html, "fileName": filename, "stripScripts": PDF_STRIP_SCRIPTS, "maxBytes": PDF_MAX_BYTES}
        # 1) /render-pdf → application/pdf
        try:
            r = await cli.post(f"{PDF_SERVICE_URL}/render-pdf", json=payload)
            ct = (r.headers.get("content-type") or "").lower()
            if r.status_code == 200 and "application/pdf" in ct:
                return r.content
        except Exception:
            pass
        # 2) /generate-pdf → application/pdf ODER JSON {pdf_base64}
        try:
            r = await cli.post(f"{PDF_SERVICE_URL}/generate-pdf", json={**payload, "return_pdf_bytes": True})
            ct = (r.headers.get("content-type") or "").lower()
            if r.status_code == 200 and "application/pdf" in ct:
                return r.content
            if r.status_code == 200 and "application/json" in ct:
                data = r.json()
                b64 = data.get("pdf_base64") or data.get("pdf") or data.get("data")
                if b64:
                    try:
                        return base64.b64decode(b64)
                    except Exception:
                        pass
        except Exception:
            pass
    return None


async def _pdf_service_email(recipient: str, subject: str, html: str, lang: str, filename: str) -> Dict[str, Any]:
    if not PDF_SERVICE_URL:
        return {"ok": False, "status": 0, "detail": "PDF service not configured"}
    try:
        async with httpx.AsyncClient(timeout=PDF_TIMEOUT) as cli:
            payload = {
                "html": html,
                "lang": lang,
                "subject": subject,
                "recipient": recipient,
                "filename": filename,
                "stripScripts": PDF_STRIP_SCRIPTS,
                "maxBytes": PDF_MAX_BYTES,
                "meta": {"app": APP_NAME, "mode": "fallback-email"},
            }
            r = await cli.post(f"{PDF_SERVICE_URL}/generate-pdf", json=payload)
            return {"ok": r.status_code == 200, "status": r.status_code, "detail": r.text[:500]}
    except Exception as exc:
        return {"ok": False, "status": 0, "detail": str(exc)}


# -----------------------------------------------------------------------------
# SMTP‑Versand (PDF+HTML, optional Admin‑JSON)
# -----------------------------------------------------------------------------

def _send_combined_email(
    to_address: str,
    subject: str,
    html_body: str,
    html_attachment: bytes,
    pdf_attachment: Optional[bytes],
    admin_json: Optional[Dict[str, bytes]] = None,
) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((SMTP_FROM_NAME, SMTP_FROM))
    msg["To"] = to_address
    msg.set_content("This is an HTML email. Please enable HTML view.")
    msg.add_alternative(html_body or "<p></p>", subtype="html")
    msg.add_attachment(html_attachment, maintype="text", subtype="html", filename="report.html")
    if pdf_attachment:
        msg.add_attachment(pdf_attachment, maintype="application", subtype="pdf", filename="report.pdf")
    for name, data in (admin_json or {}).items():
        msg.add_attachment(data, maintype="application", subtype="json", filename=name)
    _smtp_send(msg)


# -----------------------------------------------------------------------------
# Auth / FastAPI
# -----------------------------------------------------------------------------

class LoginReq(BaseModel):
    email: str


def _issue_token(email: str) -> str:
    payload = {"sub": email, "iat": int(time.time()), "exp": int(time.time() + 14 * 24 * 3600)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


async def current_user(req: Request) -> Dict[str, Any]:
    auth = req.headers.get("authorization") or ""
    parts = auth.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        try:
            payload = jwt.decode(parts[1], JWT_SECRET, algorithms=[JWT_ALGO])
            return {"sub": payload.get("sub"), "email": payload.get("sub")}
        except JWTError:
            pass
    return {"sub": "anon", "email": ""}


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


# ------------------------------- Kern‑Endpoint -------------------------------

@app.post("/briefing_async")
async def briefing_async(
    body: Dict[str, Any],
    request: Request,
    tasks: BackgroundTasks,
    user=Depends(current_user),
):
    """
    Erzeugt den Report und verschickt E‑Mails (User + Admin) mit PDF+HTML im Anhang.
    Keine doppelten Admin‑Mails mehr; PDF‑Service wird nur für Rendering/Bytes genutzt.
    """
    lang = _lang_from_body(body)
    recipient_user = _recipient_from(body, fallback=ADMIN_EMAIL)
    if not recipient_user:
        raise HTTPException(status_code=400, detail="recipient could not be resolved")

    display_name = _display_name_from(body)
    subject = _build_subject(MAIL_SUBJECT_PREFIX, lang, display_name)
    filename_pdf = _safe_pdf_filename(display_name, lang)
    filename_html = _safe_html_filename(display_name, lang)

    nonce = str(body.get("nonce") or request.headers.get("x-request-id") or request.headers.get("x-idempotency-key") or "")
    idem_key = _sha256(json.dumps({"body": body, "user": recipient_user, "lang": lang, "nonce": nonce}, sort_keys=True, ensure_ascii=False))
    if _idem_seen(idem_key):
        log.info("[idem] duplicate (user=%s, lang=%s) – skipping", recipient_user, lang)
        return JSONResponse({"status": "duplicate", "job_id": _new_job_id()})

    try:
        from gpt_analyze import analyze_briefing, produce_admin_attachments  # type: ignore
    except Exception as exc:
        log.error("gpt_analyze import failed: %s", exc)
        raise HTTPException(status_code=500, detail="analysis module not available")

    form_data = dict(body.get("answers") or {})
    for k, v in body.items():
        form_data.setdefault(k, v)

    job_id = _new_job_id()

    try:
        html = analyze_briefing(form_data, lang=lang)
    except Exception as exc:
        log.error("analyze_briefing failed: %s", exc)
        raise HTTPException(status_code=500, detail="rendering failed")

    pdf_bytes = await _render_pdf_bytes(html, filename_pdf)

    admin_json: Dict[str, bytes] = {}
    try:
        tri = produce_admin_attachments(form_data)  # -> dict[str,str]
        admin_json = {name: content.encode("utf-8") for name, content in tri.items()}
    except Exception:
        pass

    user_result = {"ok": False, "status": 0, "detail": "skipped"}
    if SEND_TO_USER:
        try:
            _send_combined_email(
                to_address=recipient_user,
                subject=subject,
                html_body="<p>Ihr KI‑Status‑Report liegt im Anhang (PDF &amp; HTML).</p>" if lang == "de" else "<p>Your AI status report is attached (PDF &amp; HTML).</p>",
                html_attachment=html.encode("utf-8"),
                pdf_attachment=pdf_bytes,
            )
            user_result = {"ok": True, "status": 200, "detail": "SMTP"}
        except Exception as exc:
            log.error("[mail] user SMTP failed: %s", exc)
            if PDF_EMAIL_FALLBACK_TO_USER:
                fb = await _pdf_service_email(recipient_user, subject, html, lang, filename_pdf)
                user_result = fb

    admin_result = {"ok": False, "status": 0, "detail": "skipped"}
    if ADMIN_NOTIFY and ADMIN_EMAIL:
        try:
            _send_combined_email(
                to_address=ADMIN_EMAIL,
                subject=subject + (" (Admin‑Kopie)" if lang == "de" else " (Admin copy)"),
                html_body="<p>Neuer Report erstellt. Anhänge: PDF, HTML sowie JSON‑Diagnosen.</p>" if lang == "de" else "<p>New report created. Attachments: PDF, HTML and JSON diagnostics.</p>",
                html_attachment=html.encode("utf-8"),
                pdf_attachment=pdf_bytes,
                admin_json=admin_json,
            )
            admin_result = {"ok": True, "status": 200, "detail": "SMTP"}
        except Exception as exc:
            log.error("[mail] admin SMTP failed: %s", exc)

    return JSONResponse(
        {"status": "ok", "job_id": _new_job_id(), "user_mail": user_result, "admin_mail": admin_result}
    )


@app.post("/pdf_test")
async def pdf_test(body: Dict[str, Any]) -> Dict[str, Any]:
    lang = _lang_from_body(body)
    html = body.get("html") or "<!doctype html><meta charset='utf-8'><h1>Ping</h1>"
    pdf = await _render_pdf_bytes(html, _safe_pdf_filename("test", lang))
    return {"ok": bool(pdf), "bytes": len(pdf or b"0")}


@app.post("/feedback")
async def feedback(body: Dict[str, Any]) -> Dict[str, Any]:
    log.info("[feedback] received: keys=%s", list(body.keys()))
    return {"status": "ok", "received": True, "ts": _now_str()}


@app.get("/")
def root() -> HTMLResponse:
    return HTMLResponse(f"<!doctype html><meta charset='utf-8'><h1>{APP_NAME}</h1><p>OK – {_now_str()}</p>")
