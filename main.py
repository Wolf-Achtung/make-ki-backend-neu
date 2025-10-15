# filename: main.py
# -*- coding: utf-8 -*-
r"""
KI‑Status‑Report Backend – Gold‑Standard+
----------------------------------------

• Stabiler DB‑Login (pgcrypto, direkter SELECT … crypt()) + optionaler ORM‑Fallback
  ENV:
    - STRICT_DB_LOGIN=1                 → ohne DB/Passwort kein Login (Default)
    - DB_LOGIN_DIRECT_FIRST=1           → zuerst direkter pgcrypto‑Check (Default)
    - DB_CONNECT_TIMEOUT_S=4, DB_QUERY_TIMEOUT_S=3.5

• Analyzer/Report (/briefing_async) mit HTML→PDF (externer PDF‑Service), Admin‑Mail
  ENV (Auszug):
    - PDF_SERVICE_URL, PDF_TIMEOUT=45000 (ms), PDF_MAX_BYTES=33554432
    - PDF_STRIP_SCRIPTS=1, PDF_MINIFY_HTML=1
    - ADMIN_NOTIFY=1, ADMIN_EMAIL, SMTP_* (Host/Port/User/Pass/From)
    - TOOL_MATRIX_LIVE_ENRICH=1

• Health/Observability:
    - /healthz  (inkl. Version/Flags), /metrics (Prometheus), /api/ping
    - Request‑ID in Header (X‑Request‑ID, konfigurierbar), CORS, Rate‑Limit
"""

from __future__ import annotations

import asyncio
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
import psycopg
from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from jose import jwt
from jose.exceptions import JWTError
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# ---------------------------------------------------------------------
# App / Logging
# ---------------------------------------------------------------------

APP_NAME = os.getenv("APP_NAME", "make-ki-backend")
APP_VERSION = os.getenv("APP_VERSION", "")
SCHEMA_VERSION = os.getenv("SCHEMA_VERSION", "")
PROMPT_VERSION = os.getenv("PROMPT_VERSION", "")

REQUEST_ID_HEADER = os.getenv("REQUEST_ID_HEADER", "x-request-id")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("backend")

# ---------------------------------------------------------------------
# Auth / JWT
# ---------------------------------------------------------------------

JWT_SECRET = os.getenv("JWT_SECRET", os.getenv("SECRET_KEY", "dev-secret"))
JWT_ALGO = "HS256"

# ---------------------------------------------------------------------
# DB (direkter Zugriff + optional ORM)
# ---------------------------------------------------------------------

DATABASE_URL = (
    os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or os.getenv("POSTGRESQL_URL")
)
DB_CONNECT_TIMEOUT = float(os.getenv("DB_CONNECT_TIMEOUT_S", "4"))
DB_QUERY_TIMEOUT = float(os.getenv("DB_QUERY_TIMEOUT_S", "3.5"))

STRICT_DB_LOGIN = os.getenv("STRICT_DB_LOGIN", "1").strip().lower() in {
    "1",
    "true",
    "yes",
}
DB_LOGIN_DIRECT_FIRST = os.getenv("DB_LOGIN_DIRECT_FIRST", "1").strip().lower() in {
    "1",
    "true",
    "yes",
}


def _try_db_imports():
    """Optional ORM – nur falls vorhanden. Direkter PG‑Weg bleibt Quelle der Wahrheit."""
    try:
        from backend.db import (  # type: ignore
            get_session,
            engine_ok,
            ensure_schema,
            seed_from_env,
            db_url_effective,
        )
        from backend.models import User  # type: ignore
        from backend.security import verify_password  # type: ignore

        return (
            get_session,
            engine_ok,
            ensure_schema,
            seed_from_env,
            db_url_effective,
            User,
            verify_password,
        )
    except Exception:
        pass
    try:
        from db import (  # type: ignore
            get_session,
            engine_ok,
            ensure_schema,
            seed_from_env,
            db_url_effective,
        )
        from models import User  # type: ignore
        from security import verify_password  # type: ignore

        return (
            get_session,
            engine_ok,
            ensure_schema,
            seed_from_env,
            db_url_effective,
            User,
            verify_password,
        )
    except Exception:
        pass

    # Stubs (falls ORM nicht vorhanden)
    def engine_ok() -> bool:
        return False

    def db_url_effective(mask: bool = False) -> str:
        return DATABASE_URL or ""

    def ensure_schema() -> None:
        return None

    def seed_from_env() -> None:
        return None

    def get_session():  # pragma: no cover
        raise RuntimeError("ORM not configured")

    class _User:
        ...

    def verify_password(p: str, h: str) -> bool:
        return False

    return (
        get_session,
        engine_ok,
        ensure_schema,
        seed_from_env,
        db_url_effective,
        _User,
        verify_password,
    )


(
    get_session,
    engine_ok,
    ensure_schema,
    seed_from_env,
    db_url_effective,
    User,
    verify_password,
) = _try_db_imports()


def _db_verify_user_direct(email: str, password: str) -> Optional[dict]:
    """Direkter, schneller pgcrypto‑Check – unabhängig von der ORM‑Schicht."""
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="db not configured")
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=DB_CONNECT_TIMEOUT) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, email, role FROM users "
                    "WHERE email=%s AND password_hash = crypt(%s, password_hash)",
                    (email, password),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return {"id": row[0], "email": row[1], "role": row[2] or "user"}
    except psycopg.Error as exc:
        # Verbindung/Query-Fehler → 503 statt 502
        log.warning("[db-direct] login query failed: %s", exc)
        raise HTTPException(status_code=503, detail="db unavailable")


# ---------------------------------------------------------------------
# Analyzer / Live / PDF / Mail – Konfiguration
# ---------------------------------------------------------------------

IDEMPOTENCY_TTL_SECONDS = int(os.getenv("IDEMPOTENCY_TTL_SECONDS", "3600"))
IDEMPOTENCY_DIR = os.getenv("IDEMPOTENCY_DIR", "/tmp/ki_idempotency")

LIVE_TAVILY = bool(os.getenv("TAVILY_API_KEY"))
LIVE_PERPLEXITY = bool(os.getenv("PERPLEXITY_API_KEY") or os.getenv("PPLX_API_KEY"))
SEARCH_PROVIDER = os.getenv("SEARCH_PROVIDER", "hybrid")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")
OPENAI_MODEL_DEFAULT = os.getenv("OPENAI_MODEL_DEFAULT", "gpt-4o")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
PPLX_USE_CHAT = os.getenv("PPLX_USE_CHAT", "0")
PPLX_MODEL = os.getenv("PPLX_MODEL", "")
TOOL_MATRIX_LIVE_ENRICH = (
    os.getenv("TOOL_MATRIX_LIVE_ENRICH", "1").strip().lower() in {"1", "true", "yes"}
)

PDF_SERVICE_URL = (os.getenv("PDF_SERVICE_URL") or "").rstrip("/")
_pdf_timeout_raw = int(os.getenv("PDF_TIMEOUT", "45000"))
PDF_TIMEOUT = _pdf_timeout_raw / 1000 if _pdf_timeout_raw > 1000 else _pdf_timeout_raw
PDF_MAX_BYTES = int(os.getenv("PDF_MAX_BYTES", str(32 * 1024 * 1024)))
PDF_STRIP_SCRIPTS = os.getenv("PDF_STRIP_SCRIPTS", "1").strip().lower() in {
    "1",
    "true",
    "yes",
}
PDF_EMAIL_FALLBACK_TO_USER = os.getenv("PDF_EMAIL_FALLBACK_TO_USER", "1").strip().lower() in {
    "1",
    "true",
    "yes",
}
PDF_MINIFY_HTML = os.getenv("PDF_MINIFY_HTML", "1").strip().lower() in {
    "1",
    "true",
    "yes",
}

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


def _parse_csv(s: str) -> list[str]:
    return [p.strip() for p in (s or "").split(",") if p and p.strip()]


CORS_ALLOW = _parse_csv(os.getenv("CORS_ALLOW_ORIGINS", ""))
ALLOW_ALL = (not CORS_ALLOW) or CORS_ALLOW == ["*"]
CORS_CREDENTIALS_ENV = os.getenv("CORS_ALLOW_CREDENTIALS", "0").strip().lower() in {
    "1",
    "true",
    "yes",
}
CORS_ALLOW_CREDENTIALS = False if ALLOW_ALL else CORS_CREDENTIALS_ENV
CORS_ALLOW_REGEX = os.getenv(
    "CORS_ALLOW_REGEX",
    r"^https?://([a-z0-9-]+\.)?(ki-sicherheit\.jetzt|ki-foerderung\.jetzt)$",
)

# ---------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------

REQUESTS = Counter("app_requests_total", "HTTP requests total", ["method", "path", "status"])
LATENCY = Histogram("app_request_latency_seconds", "Request latency", ["path"])
PDF_RENDER = Histogram("app_pdf_render_seconds", "PDF render duration seconds")
POOL_AVAILABLE = Gauge("app_pdf_pool_available", "PDF contexts available (reported by service)")
LOGIN_REJECTS = Counter("app_login_rejects_total", "Rejected login attempts", ["reason"])
LOGIN_SUCCESS = Counter("app_login_success_total", "Successful logins")


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


# ---------------------------------------------------------------------
# PDF‑Renderer
# ---------------------------------------------------------------------

async def _render_pdf_bytes(html: str, filename: str):
    if not (PDF_SERVICE_URL and html):
        return None
    start = time.time()
    payload_html = re.sub(r"<!--.*?-->", "", html, flags=re.S) if PDF_MINIFY_HTML else html
    async with httpx.AsyncClient(timeout=PDF_TIMEOUT) as cli:
        payload = {
            "html": payload_html,
            "fileName": filename,
            "stripScripts": PDF_STRIP_SCRIPTS,
            "maxBytes": PDF_MAX_BYTES,
        }
        try:
            r = await cli.post(f"{PDF_SERVICE_URL}/render-pdf", json=payload)
            if r.status_code == 200 and "application/pdf" in (r.headers.get("content-type", "").lower()):
                PDF_RENDER.observe(time.time() - start)
                POOL_AVAILABLE.set(float(r.headers.get("x-pdf-pool-available", "0") or 0))
                return r.content
        except Exception as exc:
            log.warning("pdf /render-pdf failed: %s", exc)
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


# ---------------------------------------------------------------------
# Auth‑Utils
# ---------------------------------------------------------------------

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


# ---------------------------------------------------------------------
# Startup / App
# ---------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ORM‑Schema/Seed (falls vorhanden); direkter Weg funktioniert davon unabhängig.
    try:
        await run_in_threadpool(ensure_schema)
        await run_in_threadpool(seed_from_env)
        log.info(
            "[db] connected: %s",
            (db_url_effective(mask=True) if callable(db_url_effective) else "configured"),
        )
    except Exception as exc:
        log.warning("[db] init (optional) failed: %s", exc)

    log.info(
        "%s started | version=%s schema=%s prompt=%s strict_login=%s direct_first=%s",
        APP_NAME,
        APP_VERSION or "-",
        SCHEMA_VERSION or "-",
        PROMPT_VERSION or "-",
        STRICT_DB_LOGIN,
        DB_LOGIN_DIRECT_FIRST,
    )
    yield


app = FastAPI(title=APP_NAME, lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=(["*"] if ALLOW_ALL else CORS_ALLOW),
    allow_origin_regex=(None if ALLOW_ALL else CORS_ALLOW_REGEX),
    allow_credentials=CORS_ALLOW_CREDENTIALS,
    allow_methods=["GET", "POST", "OPTIONS", "HEAD"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=600,
)


# Request‑ID & Metrics
@app.middleware("http")
async def _metrics_mw(request: Request, call_next):
    def _norm(p: str) -> str:
        p = re.sub(r"/[0-9a-fA-F]{8,}", "/:id", p)
        p = re.sub(r"/\d+", "/:n", p)
        return p if len(p) <= 64 else p[:64]

    path_label = _norm(request.url.path)
    req_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
    start = time.time()
    try:
        resp = await call_next(request)
    except Exception:
        REQUESTS.labels(request.method, path_label, "500").inc()
        LATENCY.labels(path_label).observe(time.time() - start)
        resp = Response(status_code=500)
        resp.headers[REQUEST_ID_HEADER] = req_id
        raise
    status = getattr(resp, "status_code", 200) or 200
    REQUESTS.labels(request.method, path_label, str(status)).inc()
    LATENCY.labels(path_label).observe(time.time() - start)
    resp.headers[REQUEST_ID_HEADER] = req_id
    return resp


@app.options("/{rest_of_path:path}")
def cors_preflight_ok(rest_of_path: str) -> PlainTextResponse:
    return PlainTextResponse("", status_code=204)


# ---------------------------------------------------------------------
# Health & Metrics
# ---------------------------------------------------------------------

@app.get("/healthz")
@app.head("/healthz")
def healthz() -> dict:
    return {
        "status": "ok",
        "ts": _now_str(),
        "version": APP_VERSION or "",
        "schema": SCHEMA_VERSION or "",
        "prompt": PROMPT_VERSION or "",
        "strict_login": STRICT_DB_LOGIN,
        "direct_first": DB_LOGIN_DIRECT_FIRST,
        "metrics": {"exposed": True, "endpoint": "/metrics"},
    }


@app.get("/api/ping")
def api_ping() -> Dict[str, Any]:
    return {"ok": True, "ts": _now_str()}


@app.get("/metrics")
def metrics() -> Response:
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


# ---------------------------------------------------------------------
# Login (direkt → optional ORM)
# ---------------------------------------------------------------------

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


LOGIN_RATE = _RateLimiter(
    capacity=int(os.getenv("LOGIN_RATE_CAPACITY", "10")),
    refill_rate=float(os.getenv("LOGIN_RATE_REFILL_PER_SEC", "0.2")),
)

DB_LOGIN_TIMEOUT_S = float(os.getenv("DB_LOGIN_TIMEOUT_S", "2.0"))


@app.post("/api/login", response_model=None)
async def api_login(request: Request, body: Any = Body(...)) -> Dict[str, Any]:
    ip = request.client.host if request and request.client else "unknown"
    if not LOGIN_RATE.allow(ip):
        LOGIN_REJECTS.labels("rate").inc()
        raise HTTPException(status_code=429, detail="too many requests")

    # Body → dict
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except Exception:
            body = {"email": body}
    if not isinstance(body, dict):
        body = body or {}
    email = _sanitize_email(str(body.get("email") or ""))
    password = str(body.get("password") or "")

    if not email or (STRICT_DB_LOGIN and not password):
        LOGIN_REJECTS.labels("bad_input").inc()
        raise HTTPException(status_code=400, detail="email & password required")

    if not STRICT_DB_LOGIN:
        # Token-only (nur wenn ausdrücklich gewünscht)
        token = _issue_token(email)
        LOGIN_SUCCESS.inc()
        return {"token": token, "email": email}

    # --- STRICT: direkter pgcrypto‑Check (Default) ---
    async def _check_direct() -> Optional[dict]:
        return await run_in_threadpool(_db_verify_user_direct, email, password)

    # --- OPTIONAL: ORM‑Check (nur falls vorhanden/funktionsfähig) ---
    async def _check_orm() -> Optional[dict]:
        try:
            def _inner():
                with get_session() as db:  # type: ignore[misc]
                    user = db.query(User).filter(User.email == email).first()  # type: ignore[attr-defined]
                    if not user:
                        return None
                    ph = getattr(user, "password_hash", None)
                    if ph and not verify_password(password, ph):  # type: ignore[misc]
                        return None
                    return {
                        "id": getattr(user, "id", None),
                        "email": email,
                        "role": getattr(user, "role", "user"),
                    }

            return await run_in_threadpool(_inner)
        except Exception as exc:
            log.warning("[db-orm] login check failed: %s", exc)
            return None

    try:
        if DB_LOGIN_DIRECT_FIRST:
            user = await asyncio.wait_for(_check_direct(), timeout=DB_LOGIN_TIMEOUT_S)
            if user is None:
                user = await asyncio.wait_for(_check_orm(), timeout=DB_LOGIN_TIMEOUT_S)
        else:
            user = await asyncio.wait_for(_check_orm(), timeout=DB_LOGIN_TIMEOUT_S)
            if user is None:
                user = await asyncio.wait_for(_check_direct(), timeout=DB_LOGIN_TIMEOUT_S)
    except asyncio.TimeoutError:
        LOGIN_REJECTS.labels("timeout").inc()
        raise HTTPException(status_code=504, detail="login backend timeout")

    if not user:
        LOGIN_REJECTS.labels("invalid").inc()
        raise HTTPException(status_code=401, detail="invalid credentials")

    token = _issue_token(email)
    LOGIN_SUCCESS.inc()
    return {"token": token, "email": email, "role": user.get("role", "user")}


# ---------------------------------------------------------------------
# Analyzer / Report
# ---------------------------------------------------------------------

@app.post("/briefing_async")
async def briefing_async(
    body: Dict[str, Any], request: Request, user=Depends(current_user)
):
    lang = (str(body.get("lang") or body.get("language") or "de").lower())
    recipient_user = _sanitize_email((body.get("email") or ADMIN_EMAIL or ""))
    if not recipient_user:
        raise HTTPException(status_code=400, detail="recipient could not be resolved")

    display_name = (
        body.get("company")
        or body.get("unternehmen")
        or (recipient_user.split("@")[0].title())
    )
    fname_pdf = re.sub(
        r"[^a-zA-Z0-9_.-]+", "_", f"KI-Status-Report-{display_name}-{lang}.pdf"
    )
    fname_html = re.sub(
        r"[^a-zA-Z0-9_.-]+", "_", f"KI-Status-Report-{display_name}-{lang}.html"
    )
    subject = f"{MAIL_SUBJECT_PREFIX}/{display_name} – " + (
        "KI‑Status Report" if lang == "de" else "AI Status Report"
    )

    nonce = str(
        body.get("nonce")
        or request.headers.get("x-request-id")
        or request.headers.get("x-idempotency-key")
        or ""
    )
    idem_key = _sha256(
        json.dumps(
            {"body": body, "user": recipient_user, "lang": lang, "nonce": nonce},
            sort_keys=True,
            ensure_ascii=False,
        )
    )
    if _idem_seen(idem_key):
        return JSONResponse({"status": "duplicate", "job_id": uuid.uuid4().hex})

    form_data = dict(body.get("answers") or {})
    for k, v in body.items():
        form_data.setdefault(k, v)

    # Analyzer
    html_content: str
    admin_json: Dict[str, bytes] = {}
    try:
        try:
            from gpt_analyze import build_report, produce_admin_attachments  # type: ignore

            try:
                result = build_report(
                    form_data, lang=lang, live_enrich=TOOL_MATRIX_LIVE_ENRICH  # type: ignore
                )
            except TypeError:
                result = build_report(form_data, lang=lang)  # type: ignore
            html_content = result["html"] if isinstance(result, dict) else str(result)

            if callable(produce_admin_attachments):
                tri = produce_admin_attachments(form_data, lang=lang)  # type: ignore
                admin_json = {
                    name: content.encode("utf-8") for name, content in tri.items()
                }
        except Exception:
            from gpt_analyze import analyze_briefing, produce_admin_attachments  # type: ignore

            html_content = analyze_briefing(form_data, lang=lang)
            try:
                tri = produce_admin_attachments(form_data, lang=lang)
                admin_json = {
                    name: content.encode("utf-8") for name, content in tri.items()
                }
            except Exception:
                pass
    except Exception:
        raise HTTPException(status_code=500, detail="analysis module not available")

    if not html_content or "<html" not in html_content.lower():
        raise HTTPException(status_code=500, detail="rendering failed (empty html)")

    pdf_bytes = None
    try:
        pdf_bytes = await _render_pdf_bytes(html_content, fname_pdf)
    except Exception as exc:
        log.warning("PDF render failed: %s", exc)

    if ADMIN_NOTIFY and ADMIN_EMAIL:
        try:
            msg = EmailMessage()
            msg["Subject"] = subject + " (Admin)"
            msg["From"] = formataddr((SMTP_FROM_NAME, SMTP_FROM))
            msg["To"] = ADMIN_EMAIL
            msg.set_content("Admin‑Diagnose.")
            msg.add_alternative("<p>Admin‑Kopie des Reports.</p>", subtype="html")
            msg.add_attachment(
                html_content.encode("utf-8"),
                maintype="text",
                subtype="html",
                filename=fname_html,
            )
            if pdf_bytes:
                msg.add_attachment(
                    pdf_bytes,
                    maintype="application",
                    subtype="pdf",
                    filename=fname_pdf,
                )
            for name, data in (admin_json or {}).items():
                msg.add_attachment(
                    data, maintype="application", subtype="json", filename=name
                )
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
                try:
                    s.starttls()
                except Exception:
                    pass
                if SMTP_USER and SMTP_PASS:
                    s.login(SMTP_USER, SMTP_PASS)
                s.send_message(msg)
        except Exception:
            pass

    return JSONResponse({"status": "ok", "job_id": uuid.uuid4().hex})


# ---------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------

@app.get("/")
def root() -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><meta charset='utf-8'>"
        f"<h1>{APP_NAME}</h1>"
        f"<p>OK – {_now_str()}</p>"
        f"<small>v:{APP_VERSION or '-'} • schema:{SCHEMA_VERSION or '-'} • prompt:{PROMPT_VERSION or '-'}</small>"
    )
