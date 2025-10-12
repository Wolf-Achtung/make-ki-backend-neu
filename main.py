# filename: main.py
# -*- coding: utf-8 -*-
"""
Production API für KI‑Status‑Report (Gold‑Standard+)

- Korrekte CORS-Guards (kein "*" mit Credentials)
- /health mit effektivem PPLX-Modell
- /briefing_async robust (idempotent, PDF-Logging)
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import smtplib
import time
import uuid
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from typing import Any, Dict

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from jose import jwt
from jose.exceptions import JWTError
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# Optional schema router (keine harte Abhängigkeit)
try:
    from schema import get_router as get_schema_router, get_schema_info  # type: ignore
except Exception:  # pragma: no cover
    def get_schema_router():
        from fastapi import APIRouter
        r = APIRouter()
        @r.get("/schema")
        def _noop():
            return {"ok": False, "detail": "schema file not found"}
        return r
    def get_schema_info():
        return {"ok": False}

APP_NAME = os.getenv("APP_NAME", "make-ki-backend")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("backend")

JWT_SECRET = os.getenv("JWT_SECRET", os.getenv("SECRET_KEY", "dev-secret"))
JWT_ALGO = "HS256"

IDEMPOTENCY_TTL_SECONDS = int(os.getenv("IDEMPOTENCY_TTL_SECONDS", "3600"))
IDEMPOTENCY_DIR = os.getenv("IDEMPOTENCY_DIR", "/tmp/ki_idempotency")

BASE_DIR = os.path.abspath(os.getenv("APP_BASE", os.getcwd()))
TEMPLATE_DIR = os.getenv("TEMPLATE_DIR", os.path.join(BASE_DIR, "templates"))

# Live flags (für /health)
LIVE_TAVILY = bool(os.getenv("TAVILY_API_KEY"))
LIVE_PERPLEXITY = bool(os.getenv("PPLX_API_KEY") or os.getenv("PERPLEXITY_API_KEY"))

# PDF service
PDF_SERVICE_URL = (os.getenv("PDF_SERVICE_URL") or "").rstrip("/")
_pdf_timeout_raw = int(os.getenv("PDF_TIMEOUT", "45000"))
PDF_TIMEOUT = _pdf_timeout_raw / 1000 if _pdf_timeout_raw > 1000 else _pdf_timeout_raw
PDF_MAX_BYTES = int(os.getenv("PDF_MAX_BYTES", str(32 * 1024 * 1024)))
PDF_STRIP_SCRIPTS = os.getenv("PDF_STRIP_SCRIPTS", "1").strip().lower() in {"1", "true", "yes"}
PDF_EMAIL_FALLBACK_TO_USER = os.getenv("PDF_EMAIL_FALLBACK_TO_USER", "1").strip().lower() in {"1", "true", "yes"}
PDF_MINIFY_HTML = os.getenv("PDF_MINIFY_HTML", "1").strip().lower() in {"1", "true", "yes"}

# Email
SEND_TO_USER = os.getenv("SEND_TO_USER", "1").strip().lower() in {"1", "true", "yes"}
ADMIN_NOTIFY = os.getenv("ADMIN_NOTIFY", "1").strip().lower() in {"1", "true", "yes"}
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", os.getenv("SMTP_FROM", ""))

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "noreply@example.com")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "KI‑Sicherheit")

MAIL_SUBJECT_PREFIX = os.getenv("MAIL_SUBJECT_PREFIX", "KI‑Ready")

# -------- CORS Guards ---------
def _parse_csv(s: str) -> list[str]:
    return [p.strip() for p in (s or "").split(",") if p and p.strip()]

CORS_ALLOW = _parse_csv(os.getenv("CORS_ALLOW_ORIGINS", ""))
ALLOW_ALL = (not CORS_ALLOW) or CORS_ALLOW == ["*"]
CORS_CREDENTIALS_ENV = os.getenv("CORS_ALLOW_CREDENTIALS", "0").strip().lower() in {"1","true","yes"}
# Wenn "*" genutzt wird, dürfen laut Spec keine Credentials gesetzt werden
CORS_ALLOW_CREDENTIALS = (False if ALLOW_ALL else CORS_CREDENTIALS_ENV)
if ALLOW_ALL and CORS_CREDENTIALS_ENV:
    log.warning("CORS: '*' mit Credentials ist nicht erlaubt. Credentials wurden deaktiviert. "
                "Setze CORS_ALLOW_ORIGINS auf die konkrete Frontend‑Domain, z. B. "
                "'https://make.ki-sicherheit.jetzt'")

# Metrics
REQUESTS = Counter("app_requests_total", "HTTP requests total", ["method", "path", "status"])
LATENCY = Histogram("app_request_latency_seconds", "Request latency", ["path"])
PDF_RENDER = Histogram("app_pdf_render_seconds", "PDF render duration seconds")
POOL_AVAILABLE = Gauge("app_pdf_pool_available", "PDF contexts available (reported by service)")


def _now_str() -> str:
    import datetime as dt
    return dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _sanitize_email(value: str | None) -> str:
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
            import time as _t
            age = _t.time() - os.path.getmtime(path)
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
    cand = answers.get("to") or answers.get("email") or body.get("to") or body.get("email") or fallback
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


def _minify_html(s: str) -> str:
    if not s:
        return s
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = re.sub(r">\\s+<", "><", s)
    s = re.sub(r"\\s{2,}", " ", s)
    return s.strip()

def _pplx_model_effective(raw: str | None) -> str:
    name = (raw or "").strip()
    if not name:
        return "auto"
    low = name.lower()
    if low in {"auto", "best", "default", "none"}:
        return "auto"
    if "online" in low:
        return "auto"
    return name

# --------------------------- PDF service ------------------------------------

async def _render_pdf_bytes(html: str, filename: str):
    if not (PDF_SERVICE_URL and html):
        return None
    start = time.time()
    payload_html = _minify_html(html) if PDF_MINIFY_HTML else html
    headers_logged = {}
    async with httpx.AsyncClient(timeout=PDF_TIMEOUT) as cli:
        payload = {"html": payload_html, "fileName": filename, "stripScripts": PDF_STRIP_SCRIPTS, "maxBytes": PDF_MAX_BYTES}
        try:
            r = await cli.post(f"{PDF_SERVICE_URL}/render-pdf", json=payload)
            headers_logged = {"X-PDF-Bytes": r.headers.get("x-pdf-bytes"), "X-PDF-Limit": r.headers.get("x-pdf-limit")}
            ct = (r.headers.get("content-type") or "").lower()
            if r.status_code == 200 and "application/pdf" in ct:
                log.info("[pdf] bytes=%s limit=%s via /render-pdf", headers_logged.get("X-PDF-Bytes"), headers_logged.get("X-PDF-Limit"))
                return r.content
        except Exception as exc:
            log.warning("pdf /render-pdf failed: %s", exc)
        try:
            r = await cli.post(f"{PDF_SERVICE_URL}/generate-pdf", json={**payload, "return_pdf_bytes": True})
            headers_logged = {"X-PDF-Bytes": r.headers.get("x-pdf-bytes"), "X-PDF-Limit": r.headers.get("x-pdf-limit")}
            ct = (r.headers.get("content-type") or "").lower()
            if r.status_code == 200 and "application/pdf" in ct:
                log.info("[pdf] bytes=%s limit=%s via /generate-pdf", headers_logged.get("X-PDF-Bytes"), headers_logged.get("X-PDF-Limit"))
                return r.content
            if r.status_code == 200 and "application/json" in ct:
                data = r.json()
                b64 = data.get("pdf_base64") or data.get("pdf") or data.get("data")
                if b64:
                    return base64.b64decode(b64)
        except Exception as exc:
            log.warning("pdf /generate-pdf failed: %s", exc)
    return None

# --------------------------- SMTP -------------------------------------------

def _send_combined_email(
    to_address: str,
    subject: str,
    html_body: str,
    html_attachment: bytes,
    pdf_attachment: bytes | None,
    admin_json: Dict[str, bytes] | None = None,
    html_filename: str = "report.html",
    pdf_filename: str = "report.pdf",
) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((SMTP_FROM_NAME, SMTP_FROM))
    msg["To"] = to_address
    msg.set_content("Dies ist eine HTML-Mail. Bitte HTML-Ansicht verwenden.")
    msg.add_alternative(html_body or "<p></p>", subtype="html")
    msg.add_attachment(html_attachment, maintype="text", subtype="html", filename=html_filename)
    if pdf_attachment:
        msg.add_attachment(pdf_attachment, maintype="application", subtype="pdf", filename=pdf_filename)
    for name, data in (admin_json or {}).items():
        msg.add_attachment(data, maintype="application", subtype="json", filename=name)
    _smtp_send(msg)

# --------------------------- Auth / App -------------------------------------

def _issue_token(email: str) -> str:
    payload = {"sub": email, "iat": int(time.time()), "exp": int(time.time() + 14 * 24 * 3600)}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


async def current_user(req: Request):
    auth = req.headers.get("authorization") or ""
    parts = auth.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        try:
            payload = jwt.decode(parts[1], JWT_SECRET, algorithms=["HS256"])
            return {"sub": payload.get("sub"), "email": payload.get("sub")}
        except JWTError:
            pass
    return {"sub": "anon", "email": ""}


app = FastAPI(title=APP_NAME)
app.add_middleware(
    CORSMiddleware,
    allow_origins=(["*"] if ALLOW_ALL else CORS_ALLOW),
    allow_credentials=CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(get_schema_router())


@app.get("/health")
def health() -> dict:
    pplx_env = os.getenv("PPLX_MODEL", "")
    return {
        "ok": True,
        "ts": _now_str(),
        "app": APP_NAME,
        "pdf_service": PDF_SERVICE_URL or "-",
        "live": {
            "tavily": LIVE_TAVILY,
            "perplexity": LIVE_PERPLEXITY,
            "pplx_model_env": pplx_env or "unset",
            "pplx_model_effective": _pplx_model_effective(pplx_env),
        },
        "schema": get_schema_info(),
        "smtp": bool(SMTP_HOST),
        "cache": {
            "file": os.getenv("LIVE_CACHE_FILE", "/tmp/ki_live_cache.json"),
            "enabled": os.getenv("LIVE_CACHE_ENABLED", "1"),
            "ttl_sec": os.getenv("LIVE_CACHE_TTL_SECONDS", "1800"),
        }
    }


@app.get("/health/html")
def health_html() -> HTMLResponse:
    html = f"""<!doctype html>
<meta charset="utf-8">
<title>{APP_NAME} /health</title>
<style>
body{{font:14px system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:880px;margin:2rem auto;line-height:1.4}}
.card{{border:1px solid #e5e7eb;border-radius:8px;padding:1rem;margin:.75rem 0;box-shadow:0 1px 2px rgba(0,0,0,.04)}}
.badge{{display:inline-block;padding:.15rem .5rem;border-radius:6px;background:#e6fffa;color:#065f46;font-weight:600}}
.kv{{display:grid;grid-template-columns:180px 1fr;gap:.25rem .75rem}}
</style>
<h1>{APP_NAME} <span class="badge">OK</span></h1>
<div class="card"><div class="kv">
  <div>Zeit</div><div>{_now_str()}</div>
  <div>PDF-Service</div><div>{PDF_SERVICE_URL or "–"}</div>
  <div>Live-Quellen</div><div>Tavily: {"ON" if LIVE_TAVILY else "off"} · Perplexity: {"ON" if LIVE_PERPLEXITY else "off"}</div>
  <div>Perplexity-Model</div><div>{_pplx_model_effective(os.getenv("PPLX_MODEL",""))} (env: {os.getenv("PPLX_MODEL","unset") or "unset"})</div>
  <div>SMTP</div><div>{"on" if SMTP_HOST else "off"} ({SMTP_FROM_NAME})</div>
  <div>Cache</div><div>{os.getenv("LIVE_CACHE_ENABLED","1")} · TTL {os.getenv("LIVE_CACHE_TTL_SECONDS","1800")}s</div>
</div></div>
<p><a href="/metrics">/metrics</a></p>"""
    return HTMLResponse(html)


@app.get("/metrics")
def metrics() -> PlainTextResponse:
    data = generate_latest()  # type: ignore
    return PlainTextResponse(data, media_type=CONTENT_TYPE_LATEST)


@app.post("/api/login")
def api_login(req: Dict[str, Any]) -> Dict[str, Any]:
    email = _sanitize_email(str(req.get("email") or ""))
    if not email:
        raise HTTPException(status_code=400, detail="email required")
    token = _issue_token(email)
    return {"token": token, "email": email}

# --------------------------- Core Endpoint ----------------------------------

@app.post("/briefing_async")
async def briefing_async(body: Dict[str, Any], request: Request, user=Depends(current_user)):
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
        return JSONResponse({"status": "duplicate", "job_id": uuid.uuid4().hex})

    # Merge answers up one level
    form_data = dict(body.get("answers") or {})
    for k, v in body.items():
        form_data.setdefault(k, v)

    # Import analyzer
    html_content: str
    admin_json: Dict[str, bytes] = {}
    try:
        try:
            from gpt_analyze import build_report, produce_admin_attachments  # type: ignore
            result = build_report(form_data, lang=lang)
            html_content = result["html"] if isinstance(result, dict) else str(result)
            if callable(produce_admin_attachments):
                tri = produce_admin_attachments(form_data, lang=lang)
                admin_json = {name: content.encode("utf-8") for name, content in tri.items()}
        except Exception:  # pragma: no cover
            from gpt_analyze import analyze_briefing  # type: ignore
            html_content = analyze_briefing(form_data, lang=lang)
    except Exception as exc:
        log.error("gpt_analyze import/exec failed: %s", exc)
        raise HTTPException(status_code=500, detail="analysis module not available")

    if not html_content or "<html" not in html_content.lower():
        raise HTTPException(status_code=500, detail="rendering failed (empty html)")

    pdf_bytes = None
    try:
        pdf_bytes = await _render_pdf_bytes(html_content, filename_pdf)
    except Exception as exc:
        log.warning("PDF render failed: %s", exc)

    # Mail an User
    try:
        _send_combined_email(
            to_address=recipient_user,
            subject=subject,
            html_body=("<p>Ihr KI‑Status‑Report liegt im Anhang (PDF &amp; HTML).</p>" if lang == "de"
                       else "<p>Your AI status report is attached (PDF &amp; HTML).</p>"),
            html_attachment=html_content.encode("utf-8"),
            pdf_attachment=pdf_bytes,
            html_filename=filename_html,
            pdf_filename=filename_pdf,
            admin_json=admin_json if os.getenv("ADMIN_ATTACH_USER", "0") in {"1", "true"} else None,
        )
        user_result = {"ok": True, "status": 200, "detail": "SMTP"}
    except Exception as exc:
        log.error("[mail] user SMTP failed: %s", exc)
        user_result = {"ok": False, "status": 0, "detail": "smtp failed"}

    # Admin-Mail
    admin_result = {"ok": False, "status": 0, "detail": "skipped"}
    if os.getenv("ADMIN_NOTIFY", "1").lower() in {"1", "true"} and os.getenv("ADMIN_EMAIL"):
        try:
            _send_combined_email(
                to_address=os.getenv("ADMIN_EMAIL"),
                subject=subject + (" (Admin‑Kopie)" if lang == "de" else " (Admin copy)"),
                html_body=("<p>Neuer Report erstellt. Anhänge: PDF, HTML sowie JSON‑Diagnosen.</p>" if lang == "de"
                           else "<p>New report created. Attachments: PDF, HTML and JSON diagnostics.</p>"),
                html_attachment=html_content.encode("utf-8"),
                pdf_attachment=pdf_bytes,
                admin_json=admin_json or None,
                html_filename=filename_html,
                pdf_filename=filename_pdf,
            )
            admin_result = {"ok": True, "status": 200, "detail": "SMTP"}
        except Exception as exc:
            log.error("[mail] admin SMTP failed: %s", exc)

    return JSONResponse({"status": "ok", "job_id": uuid.uuid4().hex, "user_mail": user_result, "admin_mail": admin_result})


@app.post("/pdf_test")
async def pdf_test(body: Dict[str, Any]) -> Dict[str, Any]:
    lang = _lang_from_body(body)
    html = body.get("html") or "<!doctype html><meta charset='utf-8'><h1>Ping</h1>"
    pdf = await _render_pdf_bytes(html, _safe_pdf_filename("test", lang))
    return {"ok": bool(pdf), "bytes": len(pdf or b'0')}


@app.get("/")
def root() -> HTMLResponse:
    return HTMLResponse(f"<!doctype html><meta charset='utf-8'><h1>{APP_NAME}</h1><p>OK – {_now_str()}</p>")
