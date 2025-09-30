# main.py — Production API (PDF via Puppeteer, Admin Notices, Benchmarks fix)
# Gold-Standard+: PEP8, strukturierte Logs, robuste Fehlerbehandlung
# - Benchmarks: Dateien liegen direkt in ./data (z.B. benchmark_beratung.csv)
# - Admin: JSON-Rohdaten + PDF-Kopie; User-PDF über PDF-Service
# - Endpunkte: /api/login, /briefing_async, /pdf_test, /feedback, /
# - Aliase: SEND_TO_USER oder MAIL_TO_USER; PDF_TIMEOUT versteht s/ms

from __future__ import annotations

import datetime as dt
import hashlib
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
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

APP_NAME = os.getenv("APP_NAME", "make-ki-backend-neu")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
JWT_SECRET = os.getenv("JWT_SECRET", os.getenv("SECRET_KEY", "dev-secret"))
JWT_ALGO = "HS256"
TOKEN_TTL_SECONDS = int(os.getenv("IDEMPOTENCY_TTL_SECONDS", "3600"))

BASE_DIR = os.path.abspath(os.getenv("APP_BASE", os.getcwd()))
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
TEMPLATE_DIR = os.getenv("TEMPLATE_DIR", os.path.join(BASE_DIR, "templates"))
PROMPTS_DIR = os.getenv("PROMPTS_DIR", os.path.join(BASE_DIR, "prompts"))

TEMPLATE_DE = os.getenv("TEMPLATE_DE", "pdf_template.html")
TEMPLATE_EN = os.getenv("TEMPLATE_EN", "pdf_template_en.html")

PDF_SERVICE_URL = (os.getenv("PDF_SERVICE_URL") or "").rstrip("/")
# PDF_TIMEOUT kann Sekunden (z.B. "90") ODER Millisekunden (z.B. "90000") sein:
_pdf_timeout_raw = int(os.getenv("PDF_TIMEOUT", "45"))
PDF_TIMEOUT = _pdf_timeout_raw / 1000 if _pdf_timeout_raw > 1000 else _pdf_timeout_raw
PDF_MAX_BYTES = int(os.getenv("PDF_MAX_BYTES", str(10 * 1024 * 1024)))
PDF_STRIP_SCRIPTS = (os.getenv("PDF_STRIP_SCRIPTS", "1").lower() in {"1", "true", "yes"})

# Alias-Unterstützung: SEND_TO_USER oder MAIL_TO_USER
SEND_TO_USER = (
    os.getenv("SEND_TO_USER", "").lower() in {"1", "true", "yes"}
    or os.getenv("MAIL_TO_USER", "1").lower() in {"1", "true", "yes"}
)

ADMIN_NOTIFY = (os.getenv("ADMIN_NOTIFY", "1").lower() in {"1", "true", "yes"})
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", os.getenv("SMTP_FROM", ""))

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "noreply@example.com")

# CORS
CORS_ALLOW = [o.strip() for o in (os.getenv("CORS_ALLOW_ORIGINS") or "*").split(",")]
if not CORS_ALLOW:
    CORS_ALLOW = ["*"]

# Logging
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
log = logging.getLogger("backend")

# ---------------------------------------------------------------------------
# Utils
# ---------------------------------------------------------------------------


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _sanitize_email(value: str) -> str:
    name, addr = parseaddr(value or "")
    return addr or ""


def _safe_recipient(body: Dict[str, Any], fallback: str) -> str:
    """
    Priorität: body['email'] > body['user_email'] > body['user']['email'] > fallback
    """
    cand = (
        body.get("email")
        or body.get("user_email")
        or (body.get("user") or {}).get("email")
        or fallback
    )
    return _sanitize_email(cand)


def _make_job_id() -> str:
    return uuid.uuid4().hex


def _idem_key(s: str) -> str:
    import hashlib as _hl

    return _hl.sha256(s.encode("utf-8")).hexdigest()


def _idem_seen(key: str) -> bool:
    """
    Einfache Idempotenz: legt eine Spurdatei in /tmp an.
    """
    path = os.path.join("/tmp/ki_idempotency", key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        try:
            age = time.time() - os.path.getmtime(path)
            if age < TOKEN_TTL_SECONDS:
                return True
        except Exception:
            return True
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(_now())
    except Exception:
        pass
    return False


def _lang_from_body(body: Dict[str, Any]) -> str:
    lang = (body.get("lang") or body.get("language") or "de").lower()
    return "de" if lang.startswith("de") else "en"


def _safe_mail_file_name(user_email: str, prefix: str, lang: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9_.-]+", "_", (user_email or "user").split("@")[0]) or "user"
    return f"{prefix}-{base}-{lang}.pdf"


# ---------------------------------------------------------------------------
# Auth (minimal)
# ---------------------------------------------------------------------------


class LoginReq(BaseModel):
    email: str


def _issue_token(email: str) -> str:
    payload = {
        "sub": email,
        "iat": int(time.time()),
        "exp": int(time.time() + 86400 * 14),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


async def current_user(req: Request) -> Dict[str, Any]:
    auth = req.headers.get("authorization") or ""
    parts = auth.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        token = parts[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
            return {"sub": payload.get("sub"), "email": payload.get("sub")}
        except JWTError:
            pass
    return {"sub": "anon", "email": ""}


# ---------------------------------------------------------------------------
# PDF-Service Client (Puppeteer)
# ---------------------------------------------------------------------------


async def warmup_pdf_service(rid: str, base_url: str) -> None:
    if not base_url:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as cli:
            r = await cli.get(f"{base_url}/health")
            log.info("[PDF] rid=%s warmup %s", rid, r.status_code)
    except Exception as e:
        log.warning("[PDF] warmup failed: %s", e)


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
            return {"status": resp.status_code, "ok": resp.status_code == 200, "detail": resp.text[:300]}
    except Exception as e:
        log.error("[PDF] send failed: %s", e)
        return {"status": 0, "ok": False, "detail": str(e)}


# ---------------------------------------------------------------------------
# Mail (Admin Notice + Rohdaten)
# ---------------------------------------------------------------------------


def _smtp_send(msg: EmailMessage) -> None:
    if not SMTP_HOST or not SMTP_FROM:
        log.info("[mail] SMTP disabled or not configured")
        return
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
        s.starttls()
        if SMTP_USER and SMTP_PASS:
            s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)


def send_admin_notice(
    job_id: str,
    admin_to: str,
    lang: str,
    user_email: str,
    pdf_service_url: str,
    raw_payload: Optional[Dict[str, Any]] = None,
) -> None:
    if not admin_to:
        return
    subject = (
        f"Neuer KI-Status Report – {user_email or 'unbekannt'}"
        if lang == "de"
        else f"New AI Status Report – {user_email or 'unknown'}"
    )
    body_lines = [
        f"Job-ID: {job_id}",
        f"Sprache: {lang}",
        f"Empfänger (User): {user_email or '-'}",
        f"PDF-Service: {pdf_service_url or '-'}",
        "Hinweis: Diese Mail ist die Admin-Notiz. Die PDF-Kopie kommt separat vom PDF-Service.",
    ]
    if raw_payload:
        body_lines.append("")
        body_lines.append("=== Raw questionnaire data (JSON) ===")
        body_lines.append(json.dumps(raw_payload, ensure_ascii=False, indent=2))

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr(("KI‑Sicherheit", SMTP_FROM))
    msg["To"] = admin_to
    msg.set_content("\n".join(body_lines))

    # Rohdaten auch als Anhang
    if raw_payload:
        raw_bytes = json.dumps(raw_payload, ensure_ascii=False, indent=2).encode("utf-8")
        msg.add_attachment(raw_bytes, maintype="application", subtype="json", filename="briefing.json")

    try:
        _smtp_send(msg)
        log.info("[mail] admin notice sent to %s", admin_to)
    except Exception as e:
        log.warning("[mail] admin notice failed: %s", e)


# ---------------------------------------------------------------------------
# Templating (nur für Test-Endpunkt)
# ---------------------------------------------------------------------------


def _make_env() -> Environment:
    return Environment(
        loader=FileSystemLoader([TEMPLATE_DIR, BASE_DIR]),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


# ---------------------------------------------------------------------------
# FastAPI
# ---------------------------------------------------------------------------

app = FastAPI(title=APP_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW if CORS_ALLOW else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/login")
def api_login(req: LoginReq) -> Dict[str, Any]:
    email = _sanitize_email(req.email)
    if not email:
        raise HTTPException(status_code=400, detail="email required")
    token = _issue_token(email)
    return {"token": token, "email": email}


# ------------------------------ Haupt-Endpunkt -----------------------------


class BriefingReq(BaseModel):
    lang: Optional[str] = "de"
    html: Optional[str] = None
    answers: Optional[Dict[str, Any]] = None
    # legacy/compat: payload evtl. flach, daher Dict[str, Any] zulassen


@app.post("/briefing_async")
async def briefing_async(
    body: Dict[str, Any],
    tasks: BackgroundTasks,
    user=Depends(current_user),
):
    """
    Erzeugt den Report sofort und übergibt ihn dem PDF‑Service.
    Rückgabe = Status beider PDF‑Versände (User + Admin).
    """
    lang = _lang_from_body(body)
    job_id = _make_job_id()

    # Idempotency (einfach)
    idem_source = json.dumps(body, sort_keys=True, ensure_ascii=False)
    idem_key = _idem_key(idem_source)
    if _idem_seen(idem_key):
        log.info("[idem] skip duplicate request")
        return JSONResponse({"status": "duplicate", "job_id": job_id})

    # HTML generieren
    try:
        from gpt_analyze import analyze_briefing
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"gpt_analyze import failed: {e}")

    # Empfänger ableiten
    recipient_user = _safe_recipient(body, fallback=ADMIN_EMAIL)
    if not recipient_user:
        raise HTTPException(status_code=400, detail="recipient could not be resolved")

    # answers + flache Keys zusammenführen
    form_data = dict(body.get("answers") or {})
    for k, v in body.items():
        if k not in form_data:
            form_data[k] = v

    # PDF-Service Warmlauf
    await warmup_pdf_service("briefing_async", PDF_SERVICE_URL)

    # HTML bauen
    try:
        html = analyze_briefing(form_data, lang=lang)
    except Exception as e:
        log.error("analyze_briefing failed: %s", e)
        raise HTTPException(status_code=500, detail="rendering failed")

    # Versand
    subject = "KI‑Status Report" if lang == "de" else "AI Status Report"
    filename_user = _safe_mail_file_name(recipient_user or "user", "KI-Status-Report", lang)

    log.info("[PDF] recipient resolved to: %s", recipient_user)

    user_result = {"ok": False, "status": 0, "detail": "skipped"}
    if SEND_TO_USER:
        user_result = await send_html_to_pdf_service(
            html=html,
            recipient=recipient_user,
            subject=subject,
            lang=lang,
            rid=job_id,
            filename=filename_user,
            admin_copy=False,
        )
        log.info("[PDF] rid=%s attempt status=%s", job_id, user_result.get("status"))

    admin_result = {"ok": False, "status": 0, "detail": "skipped"}
    if ADMIN_EMAIL:
        filename_admin = _safe_mail_file_name(ADMIN_EMAIL, "KI-Status-Report", lang)[:-4] + "-admin.pdf"
        admin_result = await send_html_to_pdf_service(
            html=html,
            recipient=ADMIN_EMAIL,
            subject=subject + " (Admin-Kopie)",
            lang=lang,
            rid=f"{job_id}-admin",
            filename=filename_admin,
            admin_copy=True,
        )
        log.info("[PDF] rid=%s-admin attempt status=%s", job_id, admin_result.get("status"))

    # Admin‑Notiz + Rohdaten (separat via SMTP, ohne PDF)
    if ADMIN_NOTIFY and ADMIN_EMAIL:
        try:
            send_admin_notice(
                job_id=job_id,
                admin_to=ADMIN_EMAIL,
                lang=lang,
                user_email=recipient_user,
                pdf_service_url=PDF_SERVICE_URL,
                raw_payload=form_data,
            )
        except Exception as e:
            log.warning("admin notice failed: %s", e)

    return JSONResponse({"status": "ok", "job_id": job_id, "user_pdf": user_result, "admin_pdf": admin_result})


# ------------------------------- Hilfsrouten -------------------------------


@app.post("/pdf_test")
async def pdf_test(body: Dict[str, Any], user=Depends(current_user)):
    """
    Schickt beliebiges HTML an den PDF‑Service (Debug).
    """
    lang = _lang_from_body(body)
    html = body.get("html") or "<!doctype html><h1>Ping</h1>"
    to = body.get("to") or user.get("email") or ADMIN_EMAIL
    await warmup_pdf_service("pdf_test", PDF_SERVICE_URL)
    subject = "KI‑Readiness Report (Test)" if lang == "de" else "AI Readiness Report (Test)"
    fname = _safe_mail_file_name(to or "user", "pdf_test", lang)
    return await send_html_to_pdf_service(html, to, subject, lang, "pdf_test", fname)


@app.post("/feedback")
async def feedback(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Nimmt Feedback-POSTs entgegen (verhindert 404 in Logs).
    """
    log.info("[feedback] received: keys=%s", list(body.keys()))
    return {"status": "ok", "received": True, "ts": _now()}


@app.get("/")
def root() -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><meta charset='utf-8'>"
        f"<h1>{APP_NAME}</h1><p>OK – {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>"
    )
