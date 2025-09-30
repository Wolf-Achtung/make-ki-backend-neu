# main.py — Production API (FastAPI) für KI-Report-Generator
# Gold-Standard+: PEP8, strukturierte Logs, robuste Fehlerbehandlung
# Wichtige Features:
# - Idempotency pro Nutzer (User-Scope) + optionaler Client-Nonce
# - PDF-Service (Puppeteer) mit ms/sek-Autodetektion
# - Admin-Mail mit JSON-Rohdaten (Briefing) als Anhang
# - /feedback vorhanden (verhindert 404 in Logs)
# - CORS-/ENV-konfigurierbar, JWT-Minimal-Login

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

APP_NAME = os.getenv("APP_NAME", "make-ki-backend-neu")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("backend")

JWT_SECRET = os.getenv("JWT_SECRET", os.getenv("SECRET_KEY", "dev-secret"))
JWT_ALGO = "HS256"

IDEMPOTENCY_TTL_SECONDS = int(os.getenv("IDEMPOTENCY_TTL_SECONDS", "3600"))  # 1 h Default
IDEMPOTENCY_DIR = os.getenv("IDEMPOTENCY_DIR", "/tmp/ki_idempotency")

BASE_DIR = os.path.abspath(os.getenv("APP_BASE", os.getcwd()))
TEMPLATE_DIR = os.getenv("TEMPLATE_DIR", os.path.join(BASE_DIR, "templates"))
PROMPTS_DIR = os.getenv("PROMPTS_DIR", os.path.join(BASE_DIR, "prompts"))

TEMPLATE_DE = os.getenv("TEMPLATE_DE", "pdf_template.html")
TEMPLATE_EN = os.getenv("TEMPLATE_EN", "pdf_template_en.html")

PDF_SERVICE_URL = (os.getenv("PDF_SERVICE_URL") or "").rstrip("/")
_pdf_timeout_raw = int(os.getenv("PDF_TIMEOUT", "45"))
# akzeptiert Sekunden (z. B. "90") oder Millisekunden (z. B. "90000")
PDF_TIMEOUT = _pdf_timeout_raw / 1000 if _pdf_timeout_raw > 1000 else _pdf_timeout_raw
PDF_MAX_BYTES = int(os.getenv("PDF_MAX_BYTES", str(10 * 1024 * 1024)))
PDF_STRIP_SCRIPTS = os.getenv("PDF_STRIP_SCRIPTS", "1").strip().lower() in {"1", "true", "yes"}

# Versand / Empfänger
SEND_TO_USER = (
    os.getenv("SEND_TO_USER", "").strip().lower() in {"1", "true", "yes"}
    or os.getenv("MAIL_TO_USER", "1").strip().lower() in {"1", "true", "yes"}
)
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
    name, addr = parseaddr(value or "")
    return addr or ""


def _safe_recipient(body: Dict[str, Any], fallback: str) -> str:
    """
    Empfänger-Auflösung mit sicherem Fallback.
    Priorität: body['email'] > body['user_email'] > body['user']['email'] > fallback
    """
    cand = (
        body.get("email")
        or body.get("user_email")
        or (body.get("user") or {}).get("email")
        or fallback
    )
    return _sanitize_email(cand)


def _lang_from_body(body: Dict[str, Any]) -> str:
    lang = str(body.get("lang") or body.get("language") or "de").lower()
    return "de" if lang.startswith("de") else "en"


def _new_job_id() -> str:
    return uuid.uuid4().hex


def _sha256(s: str) -> str:
    import hashlib

    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _idem_seen(key: str) -> bool:
    """
    Primitive Idempotency-Sperre auf Dateibasis.
    Sperrt identische Schlüssel innerhalb von IDEMPOTENCY_TTL_SECONDS.
    """
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

    # Lege Spurdatei an
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(_now_str())
    except Exception:
        # Im Fehlerfall: lieber nicht blockieren
        return False
    return False


def _smtp_send(msg: EmailMessage) -> None:
    """Versendet E-Mail über SMTP, sofern konfiguriert."""
    if not SMTP_HOST or not SMTP_FROM:
        log.info("[mail] SMTP deaktiviert oder unkonfiguriert")
        return

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
        try:
            s.starttls()
        except Exception:
            # Einige Provider erfordern kein STARTTLS
            pass
        if SMTP_USER and SMTP_PASS:
            s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)


# -----------------------------------------------------------------------------
# Auth (Minimal)
# -----------------------------------------------------------------------------

class LoginReq(BaseModel):
    email: str


def _issue_token(email: str) -> str:
    payload = {
        "sub": email,
        "iat": int(time.time()),
        "exp": int(time.time() + 14 * 24 * 3600),  # 14 Tage
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


async def current_user(req: Request) -> Dict[str, Any]:
    """
    Extrahiert ein optionales JWT aus Authorization: Bearer <token>.
    Fällt zurück auf anon.
    """
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
            ok = resp.status_code == 200
            detail = resp.text[:500]
            return {"ok": ok, "status": resp.status_code, "detail": detail}
    except Exception as exc:
        log.error("[PDF] send failed: %s", exc)
        return {"ok": False, "status": 0, "detail": str(exc)}


# -----------------------------------------------------------------------------
# Admin-Notiz (inkl. JSON-Anhang)
# -----------------------------------------------------------------------------

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

    if raw_payload:
        raw_bytes = json.dumps(raw_payload, ensure_ascii=False, indent=2).encode("utf-8")
        msg.add_attachment(raw_bytes, maintype="application", subtype="json", filename="briefing.json")

    try:
        _smtp_send(msg)
        log.info("[mail] admin notice sent to %s", admin_to)
    except Exception as exc:
        log.warning("[mail] admin notice failed: %s", exc)


# -----------------------------------------------------------------------------
# FastAPI App
# -----------------------------------------------------------------------------

app = FastAPI(title=APP_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW if CORS_ALLOW else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------- Endpunkte --------------------------------

@app.post("/api/login")
def api_login(req: LoginReq) -> Dict[str, Any]:
    email = _sanitize_email(req.email)
    if not email:
        raise HTTPException(status_code=400, detail="email required")
    token = _issue_token(email)
    return {"token": token, "email": email}


class BriefingReq(BaseModel):
    lang: Optional[str] = "de"
    html: Optional[str] = None
    answers: Optional[Dict[str, Any]] = None


@app.post("/briefing_async")
async def briefing_async(
    body: Dict[str, Any],
    request: Request,
    tasks: BackgroundTasks,
    user=Depends(current_user),
):
    """
    Erzeugt den Report und übergibt ihn dem PDF‑Service.
    Rückgabe = Status beider PDF‑Versände (User + Admin).
    Idempotency-Scope: pro Nutzer + Sprache (+ optionaler Client-Nonce).
    """
    # --- 1) Empfänger & Sprache bestimmen (früh, da für Idempotency relevant)
    lang = _lang_from_body(body)
    recipient_user = _safe_recipient(body, fallback=ADMIN_EMAIL)
    if not recipient_user:
        raise HTTPException(status_code=400, detail="recipient could not be resolved")

    # optionaler Client-Nonce (aus Body oder Header)
    nonce = str(
        body.get("nonce")
        or request.headers.get("x-request-id")
        or request.headers.get("x-idempotency-key")
        or ""
    )

    # --- 2) Idempotency: SCOPE pro Nutzer + Sprache (+ NONCE)
    # Der Key hängt vom gesamten Payload, aber zusätzlich von Empfänger/Language ab.
    idem_payload = {
        "body": body,  # identischer Payload => identischer Hash
        "scope_user": recipient_user or "",
        "scope_lang": lang,
        "nonce": nonce,  # erlaubt dem Client, bewusst neue Läufe zu forcen
    }
    idem_source = json.dumps(idem_payload, sort_keys=True, ensure_ascii=False)
    idem_key = _sha256(idem_source)

    if _idem_seen(idem_key):
        log.info("[idem] duplicate (user=%s, lang=%s) – skipping", recipient_user, lang)
        # bewusst neue Job-ID erzeugen, um Frontend nicht zu verwirren
        return JSONResponse({"status": "duplicate", "job_id": _new_job_id()})

    # --- 3) HTML erzeugen
    try:
        # gpt_analyze.py muss im selben App-Image liegen
        from gpt_analyze import analyze_briefing  # type: ignore
    except Exception as exc:
        log.error("gpt_analyze import failed: %s", exc)
        raise HTTPException(status_code=500, detail="analysis module not available")

    # Antworten zusammenführen (flach + answers{})
    form_data = dict(body.get("answers") or {})
    for k, v in body.items():
        if k not in form_data:
            form_data[k] = v

    job_id = _new_job_id()

    await warmup_pdf_service("briefing_async")

    try:
        html = analyze_briefing(form_data, lang=lang)
    except Exception as exc:
        log.error("analyze_briefing failed: %s", exc)
        raise HTTPException(status_code=500, detail="rendering failed")

    # --- 4) Versand (User + Admin)
    subject = "KI‑Status Report" if lang == "de" else "AI Status Report"
    filename_user = _safe_mail_file_name(recipient_user or "user", "KI-Status-Report", lang)

    log.info("[PDF] recipient resolved to: %s", recipient_user)

    user_result: Dict[str, Any] = {"ok": False, "status": 0, "detail": "skipped"}
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
        log.info("[PDF] rid=%s user status=%s", job_id, user_result.get("status"))

    admin_result: Dict[str, Any] = {"ok": False, "status": 0, "detail": "skipped"}
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
        log.info("[PDF] rid=%s-admin status=%s", job_id, admin_result.get("status"))

    # --- 5) Separate Admin-Benachrichtigung inkl. Rohdaten
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
        except Exception as exc:
            log.warning("admin notice failed: %s", exc)

    return JSONResponse(
        {"status": "ok", "job_id": job_id, "user_pdf": user_result, "admin_pdf": admin_result}
    )


def _safe_mail_file_name(user_email: str, prefix: str, lang: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9_.-]+", "_", (user_email or "user").split("@")[0]) or "user"
    return f"{prefix}-{base}-{lang}.pdf"


@app.post("/pdf_test")
async def pdf_test(body: Dict[str, Any], request: Request, user=Depends(current_user)):
    """
    Debug-Endpoint: Beliebiges HTML an den PDF‑Service schicken.
    """
    lang = _lang_from_body(body)
    html = body.get("html") or "<!doctype html><meta charset='utf-8'><h1>Ping</h1>"
    to = _sanitize_email(body.get("to") or user.get("email") or ADMIN_EMAIL)
    await warmup_pdf_service("pdf_test")
    subject = "KI‑Readiness Report (Test)" if lang == "de" else "AI Readiness Report (Test)"
    fname = _safe_mail_file_name(to or "user", "pdf_test", lang)
    return await send_html_to_pdf_service(html, to, subject, lang, "pdf_test", fname)


@app.post("/feedback")
async def feedback(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Nimmt Feedback-POSTs entgegen (verhindert 404).
    """
    log.info("[feedback] received: keys=%s", list(body.keys()))
    return {"status": "ok", "received": True, "ts": _now_str()}


@app.get("/")
def root() -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><meta charset='utf-8'><h1>{APP_NAME}</h1>"
        f"<p>OK – {_now_str()}</p>"
    )
