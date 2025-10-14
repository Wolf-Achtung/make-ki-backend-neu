# filename: main.py
# -*- coding: utf-8 -*-
"""
KI‑Status‑Report Backend – Gold‑Standard+ (Merged & Complete)

Diese Version vereint die Stärken beider zuvor gelieferten Fassungen:
- Robustes CORS‑Setup, OPTIONS‑Preflight, Metriken (/metrics), Health (/health, /healthz, /health/html)
- **Login-Fix**: korrekte Param‑Reihenfolge, kein Optional[Request], optionaler DB‑Check (sofern Module/ENV vorhanden)
- **Auth‑Guard Support**: /api/auth/verify
- **PDF‑Pipeline**: Fallback /render-pdf → /generate-pdf, Base64‑Decode, sauberes Timeout, Limit‑Header‑Logging
- **Analyzer‑Kompatibilität**: build_report() bevorzugt, analyze_briefing() Fallback, Tool‑Matrix‑Flag durchgereicht
- **Idempotency**: Duplicate‑Erkennungsdatei mit TTL
- **Mailversand**: kombinierte HTML+PDF Mail an User und optional Admin (inkl. JSON‑Anhänge)
- **Misc**: /pdf_test, / Root, Prometheus Counter/Histogram/Gauge, Login‑Rate‑Limit
- **Lifespan** statt @on_event("startup")

HINWEIS: DB‑Module (SQLAlchemy etc.) sind optional – die Imports werden sicher umgangen, wenn nicht vorhanden.
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
from contextlib import asynccontextmanager
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from typing import Any, Dict, Optional

import httpx
from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from jose import jwt
from jose.exceptions import JWTError
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

# --------------------------- Optional Integrationen ---------------------------
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
try:
    from feedback_api import attach_to as attach_feedback  # type: ignore
except Exception:
    attach_feedback = None

# --------------------------- App / Logging -----------------------------------
APP_NAME = os.getenv("APP_NAME", "make-ki-backend")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("backend")

# --------------------------- Security / Tokens --------------------------------
JWT_SECRET = os.getenv("JWT_SECRET", os.getenv("SECRET_KEY", "dev-secret"))
JWT_ALGO = "HS256"

# --------------------------- Idempotency -------------------------------------
IDEMPOTENCY_TTL_SECONDS = int(os.getenv("IDEMPOTENCY_TTL_SECONDS", "3600"))
IDEMPOTENCY_DIR = os.getenv("IDEMPOTENCY_DIR", "/tmp/ki_idempotency")

# --------------------------- Live / LLM Flags --------------------------------
LIVE_TAVILY = bool(os.getenv("TAVILY_API_KEY"))
LIVE_PERPLEXITY = bool(os.getenv("PERPLEXITY_API_KEY") or os.getenv("PPLX_API_KEY"))
SEARCH_PROVIDER = os.getenv("SEARCH_PROVIDER", "hybrid")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")
OPENAI_MODEL_DEFAULT = os.getenv("OPENAI_MODEL_DEFAULT", "gpt-4o")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
PPLX_USE_CHAT = os.getenv("PPLX_USE_CHAT", "0")
PPLX_MODEL = os.getenv("PPLX_MODEL", "")
TOOL_MATRIX_LIVE_ENRICH = os.getenv("TOOL_MATRIX_LIVE_ENRICH", "1").strip().lower() in {"1", "true", "yes"}

# --------------------------- PDF Service -------------------------------------
PDF_SERVICE_URL = (os.getenv("PDF_SERVICE_URL") or "").rstrip("/")
_pdf_timeout_raw = int(os.getenv("PDF_TIMEOUT", "45000"))
PDF_TIMEOUT = _pdf_timeout_raw / 1000 if _pdf_timeout_raw > 1000 else _pdf_timeout_raw
PDF_MAX_BYTES = int(os.getenv("PDF_MAX_BYTES", str(32 * 1024 * 1024)))
PDF_STRIP_SCRIPTS = os.getenv("PDF_STRIP_SCRIPTS", "1").strip().lower() in {"1", "true", "yes"}
PDF_EMAIL_FALLBACK_TO_USER = os.getenv("PDF_EMAIL_FALLBACK_TO_USER", "1").strip().lower() in {"1", "true", "yes"}
PDF_MINIFY_HTML = os.getenv("PDF_MINIFY_HTML", "1").strip().lower() in {"1", "true", "yes"}

# --------------------------- E-Mail ------------------------------------------
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

# --------------------------- CORS --------------------------------------------
def _parse_csv(s: str) -> list[str]:
    return [p.strip() for p in (s or "").split(",") if p and p.strip()]

CORS_ALLOW = _parse_csv(os.getenv("CORS_ALLOW_ORIGINS", ""))
ALLOW_ALL = (not CORS_ALLOW) or CORS_ALLOW == ["*"]
CORS_CREDENTIALS_ENV = os.getenv("CORS_ALLOW_CREDENTIALS", "0").strip().lower() in {"1","true","yes"}
# Bei "*" sind Credentials laut Spezifikation aus – nur bei konkreten Origins sinnvoll.
CORS_ALLOW_CREDENTIALS = (False if ALLOW_ALL else CORS_CREDENTIALS_ENV)
CORS_ALLOW_REGEX = os.getenv(
    "CORS_ALLOW_REGEX",
    r"^https?://([a-z0-9-]+\.)?(ki-sicherheit\.jetzt|ki-foerderung\.jetzt)$",
)

# --------------------------- Metrics -----------------------------------------
REQUESTS = Counter("app_requests_total", "HTTP requests total", ["method", "path", "status"])
LATENCY = Histogram("app_request_latency_seconds", "Request latency", ["path"])
PDF_RENDER = Histogram("app_pdf_render_seconds", "PDF render duration seconds")
POOL_AVAILABLE = Gauge("app_pdf_pool_available", "PDF contexts available (reported by service)")
LOGIN_REJECTS = Counter("app_login_rejects_total", "Rejected login attempts", ["reason"])

def _normalize_path(path: str) -> str:
    p = re.sub(r"/[0-9a-fA-F]{8,}", "/:id", path)
    p = re.sub(r"/\d+", "/:n", p)
    return p if len(p) <= 64 else p[:64]

def _now_str() -> str:
    import datetime as dt
    return dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

def _sanitize_email(value: str | None) -> str:
    _, addr = parseaddr(value or "")
    return addr or ""

def _lang_from_body(body: Dict[str, Any]) -> str:
    lang = str(body.get("lang") or body.get("language") or "de").lower()
    return "de" if lang.startswith("de") else "en"

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
    cand = answers.get("to") or answers.get("email") or body.get("to") or body.get("email") or fallback
    return _sanitize_email(cand)

def _display_name_from(body: Dict[str, Any]) -> str:
    for key in ("unternehmen", "firma", "company", "company_name", "organization"):
        val = (body.get("answers") or {}).get(key) or body.get(key)
        if val:
            return str(val)[:64]
    email = _recipient_from(body, ADMIN_EMAIL)
    return (email.split("@")[0] if email else "Customer").title()

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
    s = re.sub(r">\s+<", "><", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()

def _pplx_model_effective(raw: Optional[str]) -> str:
    name = (raw or "").strip()
    if not name:
        return "auto"
    low = name.lower()
    if low in {"auto", "best", "default", "none"} or "online" in low:
        return "auto"
    return name

# --------------------------- Optional: DB & Rate Limiting --------------------
def _try_db_imports():
    # 1) backend.*
    try:
        from backend.db import get_session, engine_ok, ensure_schema, seed_from_env, db_url_effective  # type: ignore
        from backend.models import User  # type: ignore
        from backend.security import verify_password  # type: ignore
        return get_session, engine_ok, ensure_schema, seed_from_env, db_url_effective, User, verify_password
    except Exception:
        pass
    # 2) flat layout
    try:
        from db import get_session, engine_ok, ensure_schema, seed_from_env, db_url_effective  # type: ignore
        from models import User  # type: ignore
        from security import verify_password  # type: ignore
        return get_session, engine_ok, ensure_schema, seed_from_env, db_url_effective, User, verify_password
    except Exception:
        pass
    # 3) none available
    def engine_ok() -> bool: return False
    def db_url_effective(mask: bool = False) -> str: return ""
    def ensure_schema() -> None: return None
    def seed_from_env() -> None: return None
    def get_session():  # pragma: no cover
        raise RuntimeError("DATABASE is not configured")
    class _User: pass
    def verify_password(p: str, h: str) -> bool: return False
    return get_session, engine_ok, ensure_schema, seed_from_env, db_url_effective, _User, verify_password

(get_session, engine_ok, ensure_schema, seed_from_env, db_url_effective, User, verify_password) = _try_db_imports()

class _TokenBucket:
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = max(1, int(capacity))
        self.tokens = float(capacity)
        self.refill = float(refill_rate)
        self.last = time.time()
    def allow(self) -> bool:
        now = time.time()
        delta = now - self.last
        self.last = now
        self.tokens = min(self.capacity, self.tokens + delta * self.refill)
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False

class _RateLimiter:
    def __init__(self, capacity: int = 10, refill_rate: float = 0.2):
        self.capacity = capacity
        self.refill = refill_rate
        self.buckets: dict[str, _TokenBucket] = {}
    def allow(self, key: str) -> bool:
        b = self.buckets.get(key)
        if b is None:
            b = self.buckets[key] = _TokenBucket(self.capacity, self.refill)
        return b.allow()

# --------------------------- PDF Rendering -----------------------------------
async def _render_pdf_bytes(html: str, filename: str):
    if not (PDF_SERVICE_URL and html):
        return None
    start = time.time()
    payload_html = _minify_html(html) if PDF_MINIFY_HTML else html
    async with httpx.AsyncClient(timeout=PDF_TIMEOUT) as cli:
        payload = {"html": payload_html, "fileName": filename, "stripScripts": PDF_STRIP_SCRIPTS, "maxBytes": PDF_MAX_BYTES}
        # 1) /render-pdf (schnellster Pfad)
        try:
            r = await cli.post(f"{PDF_SERVICE_URL}/render-pdf", json=payload)
            ct = (r.headers.get("content-type") or "").lower()
            if r.status_code == 200 and "application/pdf" in ct:
                PDF_RENDER.observe(time.time() - start)
                POOL_AVAILABLE.set(float(r.headers.get("x-pdf-pool-available", "0") or 0))
                return r.content
        except Exception as exc:
            log.warning("pdf /render-pdf failed: %s", exc)
        # 2) /generate-pdf (Rückfall, auch base64)
        try:
            r = await cli.post(f"{PDF_SERVICE_URL}/generate-pdf", json={**payload, "return_pdf_bytes": True})
            ct = (r.headers.get("content-type") or "").lower()
            if r.status_code == 200 and "application/pdf" in ct:
                PDF_RENDER.observe(time.time() - start)
                POOL_AVAILABLE.set(float(r.headers.get("x-pdf-pool-available", "0") or 0))
                return r.content
            if r.status_code == 200 and "application/json" in ct:
                data = r.json()
                b64 = data.get("pdf_base64") or data.get("pdf") or data.get("data")
                if b64:
                    PDF_RENDER.observe(time.time() - start)
                    return base64.b64decode(b64)
        except Exception as exc:
            log.warning("pdf /generate-pdf failed: %s", exc)
    return None

# --------------------------- Auth / App --------------------------------------
def _issue_token(email: str) -> str:
    payload = {"sub": email, "iat": int(time.time()), "exp": int(time.time() + 14 * 24 * 3600)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)

async def current_user(req: Request):
    auth = req.headers.get("authorization") or ""
    parts = auth.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        try:
            payload = jwt.decode(parts[1], JWT_SECRET, algorithms=[JWT_ALGO])
            return {"sub": payload.get("sub"), "email": payload.get("sub")}
        except JWTError:
            pass
    return {"sub": "anon", "email": ""}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: DB vorbereiten, wenn verfügbar
    if engine_ok():
        try:
            await run_in_threadpool(ensure_schema)
            await run_in_threadpool(seed_from_env)
            log.info("[db] connected: %s", db_url_effective(mask=True))
        except Exception as exc:
            log.warning("[db] init failed: %s", exc)
    yield
    # Shutdown: nothing special
    return

app = FastAPI(title=APP_NAME, lifespan=lifespan)

# CORS‑Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=(["*"] if ALLOW_ALL else CORS_ALLOW),
    allow_origin_regex=(None if ALLOW_ALL else CORS_ALLOW_REGEX),
    allow_credentials=CORS_ALLOW_CREDENTIALS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=600,
)

# Request‑Metriken
@app.middleware("http")
async def _metrics_mw(request: Request, call_next):
    path_label = _normalize_path(request.url.path)
    start = time.time()
    try:
        resp = await call_next(request)
    except Exception:
        REQUESTS.labels(request.method, path_label, "500").inc()
        LATENCY.labels(path_label).observe(time.time() - start)
        raise
    status = getattr(resp, "status_code", 200) or 200
    REQUESTS.labels(request.method, path_label, str(status)).inc()
    LATENCY.labels(path_label).observe(time.time() - start)
    return resp

# Preflight Catch‑All
@app.options("/{rest_of_path:path}")
def cors_preflight_ok(rest_of_path: str) -> PlainTextResponse:
    return PlainTextResponse("", status_code=204)

# Schema/Feedback einbinden
app.include_router(get_schema_router())
if attach_feedback:
    try:
        attach_feedback(app)
    except Exception as exc:
        log.warning("feedback_api attach failed: %s", exc)

# --------------------------- Health / Metrics --------------------------------
@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "ts": _now_str(),
        "app": APP_NAME,
        "pdf_service": PDF_SERVICE_URL or "-",
        "live": {
            "tavily": LIVE_TAVILY,
            "perplexity": LIVE_PERPLEXITY,
            "provider": SEARCH_PROVIDER,
            "llm_provider": LLM_PROVIDER,
            "pplx_model_env": PPLX_MODEL or "unset",
            "pplx_model_effective": _pplx_model_effective(PPLX_MODEL),
            "tools_live_enrich": TOOL_MATRIX_LIVE_ENRICH,
        },
        "smtp": bool(SMTP_HOST),
        "db": {"connected": bool(engine_ok()), "url": db_url_effective(mask=True) if engine_ok() else ""},
        "schema": get_schema_info(),
        "metrics": {"endpoint": "/metrics"}
    }

@app.get("/healthz")
def healthz() -> dict:
    return {
        "status": "ok",
        "ts": _now_str(),
        "env": {
            "cors_allow_origins": CORS_ALLOW,
            "cors_allow_regex": CORS_ALLOW_REGEX,
            "cors_allow_credentials": CORS_ALLOW_CREDENTIALS,
            "llm_provider": LLM_PROVIDER,
            "openai_default": OPENAI_MODEL_DEFAULT,
            "claude_model": CLAUDE_MODEL,
            "pplx_use_chat": PPLX_USE_CHAT,
            "search_provider": SEARCH_PROVIDER,
            "db": db_url_effective(mask=True) if engine_ok() else "",
        },
        "metrics": {"exposed": True, "endpoint": "/metrics"}
    }

@app.get("/health/html")
def health_html() -> HTMLResponse:
    now = _now_str()
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
  <div>Zeit (UTC)</div><div>{now}</div>
  <div>PDF-Service</div><div>{PDF_SERVICE_URL or "–"}</div>
  <div>Live-Quellen</div><div>Tavily: {"ON" if LIVE_TAVILY else "off"} · Perplexity: {"ON" if LIVE_PERPLEXITY else "off"}</div>
  <div>Perplexity-Model</div><div>{_pplx_model_effective(PPLX_MODEL)} (env: {PPLX_MODEL or "unset"})</div>
  <div>SMTP</div><div>{"on" if SMTP_HOST else "off"} ({SMTP_FROM_NAME})</div>
  <div>DB</div><div>{"on" if engine_ok() else "off"}</div>
</div></div>
<p><a href="/healthz">/healthz</a> · <a href="/metrics">/metrics</a></p>"""
    return HTMLResponse(html)

@app.get("/metrics")
def metrics() -> PlainTextResponse:
    data = generate_latest()  # type: ignore
    return PlainTextResponse(data, media_type=CONTENT_TYPE_LATEST)

# --------------------------- Auth Endpoints ----------------------------------
_LOGIN_LIMITER = _RateLimiter(capacity=int(os.getenv("LOGIN_RATE_CAPACITY", "10")),
                              refill_rate=float(os.getenv("LOGIN_RATE_REFILL_PER_SEC", "0.2")))

@app.post("/api/login", response_model=None)
async def api_login(request: Request, body: Any = Body(...)) -> Dict[str, Any]:
    # Param‑Reihenfolge: non‑default (request) vor default (body)
    ip = request.client.host if request and request.client else "unknown"
    if not _LOGIN_LIMITER.allow(ip):
        LOGIN_REJECTS.labels("rate").inc()
        raise HTTPException(status_code=429, detail="too many requests")
    # JSON‑only – kein multipart erforderlich
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except Exception:
            body = {"email": body}
    if not isinstance(body, dict):
        body = body or {}
    email = _sanitize_email(str(body.get("email") or ""))
    password = str(body.get("password") or "")
    if not email:
        LOGIN_REJECTS.labels("no_email").inc()
        raise HTTPException(status_code=400, detail="email required")
    # Optional: DB‑Prüfung, wenn verfügbar
    if engine_ok():
        try:
            with get_session() as db:
                user = db.query(User).filter(User.email == email).first()
                if not user or (getattr(user, "password_hash", None) and not verify_password(password, user.password_hash)):  # type: ignore[attr-defined]
                    LOGIN_REJECTS.labels("invalid").inc()
                    raise HTTPException(status_code=401, detail="invalid credentials")
        except HTTPException:
            raise
        except Exception:
            # DB‑Fehler sollen den Login nicht crashen
            pass
    token = _issue_token(email)
    return {"token": token, "email": email}

@app.get("/api/auth/verify", response_model=None)
async def api_auth_verify(user=Depends(current_user)) -> Dict[str, Any]:
    if user.get("email"):
        return {"ok": True, "email": user["email"]}
    raise HTTPException(status_code=401, detail="invalid token")

# --------------------------- Core Endpoint -----------------------------------
@app.post("/briefing_async")
async def briefing_async(body: Dict[str, Any], request: Request, user=Depends(current_user)):
    lang = _lang_from_body(body)
    recipient_user = _recipient_from(body, fallback=ADMIN_EMAIL)
    if not recipient_user:
        raise HTTPException(status_code=400, detail="recipient could not be resolved")

    display_name = (body.get("company") or body.get("unternehmen") or (recipient_user.split("@")[0].title()))
    subject = f"{MAIL_SUBJECT_PREFIX}/{display_name} – " + ("KI‑Status Report" if lang == "de" else "AI Status Report")
    filename_pdf = _safe_pdf_filename(display_name, lang)
    filename_html = _safe_html_filename(display_name, lang)

    nonce = str(body.get("nonce") or request.headers.get("x-request-id") or request.headers.get("x-idempotency-key") or "")
    idem_key = _sha256(json.dumps({"body": body, "user": recipient_user, "lang": lang, "nonce": nonce}, sort_keys=True, ensure_ascii=False))
    if _idem_seen(idem_key):
        return JSONResponse({"status": "duplicate", "job_id": uuid.uuid4().hex})

    # Antworten zusammenführen
    form_data = dict(body.get("answers") or {})
    for k, v in body.items():
        form_data.setdefault(k, v)

    # Analyzer import & Fallback
    html_content: str
    admin_json: Dict[str, bytes] = {}
    try:
        try:
            from gpt_analyze import build_report, produce_admin_attachments  # type: ignore
            try:
                result = build_report(form_data, lang=lang, live_enrich=TOOL_MATRIX_LIVE_ENRICH)  # type: ignore
            except TypeError:
                result = build_report(form_data, lang=lang)  # type: ignore
            html_content = result["html"] if isinstance(result, dict) else str(result)
            if callable(produce_admin_attachments):
                tri = produce_admin_attachments(form_data, lang=lang)  # type: ignore
                admin_json = {name: content.encode("utf-8") for name, content in tri.items()}
        except Exception:
            from gpt_analyze import analyze_briefing, produce_admin_attachments  # type: ignore
            html_content = analyze_briefing(form_data, lang=lang)
            try:
                tri = produce_admin_attachments(form_data, lang=lang)
                admin_json = {name: content.encode("utf-8") for name, content in tri.items()}
            except Exception:
                pass
    except Exception:
        raise HTTPException(status_code=500, detail="analysis module not available")

    if not html_content or "<html" not in html_content.lower():
        raise HTTPException(status_code=500, detail="rendering failed (empty html)")

    pdf_bytes = None
    try:
        pdf_bytes = await _render_pdf_bytes(html_content, filename_pdf)
    except Exception as exc:
        log.warning("PDF render failed: %s", exc)

    # Mail an User (optional) & Admin (optional)
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = formataddr((SMTP_FROM_NAME, SMTP_FROM))
        msg["To"] = recipient_user
        msg.set_content("Bitte HTML‑Ansicht verwenden.")
        msg.add_alternative(html_content or "<p></p>", subtype="html")
        msg.add_attachment(html_content.encode("utf-8"), maintype="text", subtype="html", filename=filename_html)
        if pdf_bytes:
            msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=filename_pdf)
        _smtp_send(msg)
    except Exception:
        pass

    if ADMIN_NOTIFY and ADMIN_EMAIL:
        try:
            admin_msg = EmailMessage()
            admin_msg["Subject"] = subject + (" (Admin‑Kopie)" if lang == "de" else " (Admin copy)")
            admin_msg["From"] = formataddr((SMTP_FROM_NAME, SMTP_FROM))
            admin_msg["To"] = ADMIN_EMAIL
            admin_msg.set_content("Admin‑Diagnose.")
            admin_msg.add_alternative("<p>Admin‑Kopie des Reports.</p>", subtype="html")
            admin_msg.add_attachment(html_content.encode("utf-8"), maintype="text", subtype="html", filename=filename_html)
            if pdf_bytes:
                admin_msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=filename_pdf)
            for name, data in (admin_json or {}).items():
                admin_msg.add_attachment(data, maintype="application", subtype="json", filename=name)
            _smtp_send(admin_msg)
        except Exception:
            pass

    return JSONResponse({"status": "ok", "job_id": uuid.uuid4().hex})

# --------------------------- Extras ------------------------------------------
@app.post("/pdf_test")
async def pdf_test(body: Dict[str, Any]) -> Dict[str, Any]:
    lang = _lang_from_body(body)
    html = body.get("html") or "<!doctype html><meta charset='utf-8'><h1>Ping</h1>"
    pdf = await _render_pdf_bytes(html, _safe_pdf_filename("test", lang))
    return {"ok": bool(pdf), "bytes": len(pdf or b'0')}

@app.get("/")
def root() -> HTMLResponse:
    return HTMLResponse(f"<!doctype html><meta charset='utf-8'><h1>{APP_NAME}</h1><p>OK – {_now_str()}</p>")
