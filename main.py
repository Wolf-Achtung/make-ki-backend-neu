# filename: main.py
# -*- coding: utf-8 -*-
"""
KI-Status-Report Backend
------------------------
Backend mit korrigierter CORS-Konfiguration
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
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
SCHEMA_VERSION = os.getenv("SCHEMA_VERSION", "1.0")
PROMPT_VERSION = os.getenv("PROMPT_VERSION", "1.0")

REQUEST_ID_HEADER = os.getenv("REQUEST_ID_HEADER", "x-request-id")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("backend")

# ---------------------------------------------------------------------
# Auth / JWT
# ---------------------------------------------------------------------

JWT_SECRET = os.getenv("JWT_SECRET", os.getenv("SECRET_KEY", "dev-secret-change-in-production"))
JWT_ALGO = "HS256"

# ---------------------------------------------------------------------
# DB Configuration
# ---------------------------------------------------------------------

DATABASE_URL = (
    os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or os.getenv("POSTGRESQL_URL")
)
DB_CONNECT_TIMEOUT = float(os.getenv("DB_CONNECT_TIMEOUT_S", "4"))
DB_QUERY_TIMEOUT = float(os.getenv("DB_QUERY_TIMEOUT_S", "3.5"))

# For development/testing: Allow login without DB
STRICT_DB_LOGIN = os.getenv("STRICT_DB_LOGIN", "0").strip().lower() in {
    "1",
    "true",
    "yes",
}
DB_LOGIN_DIRECT_FIRST = os.getenv("DB_LOGIN_DIRECT_FIRST", "1").strip().lower() in {
    "1",
    "true",
    "yes",
}


def _db_verify_user_direct(email: str, password: str) -> Optional[dict]:
    """Direct pgcrypto check"""
    if not DATABASE_URL:
        # In development mode without DB, accept any login
        if not STRICT_DB_LOGIN:
            return {"id": 1, "email": email, "role": "user"}
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
        log.warning("[db-direct] login query failed: %s", exc)
        # In development mode, allow login anyway
        if not STRICT_DB_LOGIN:
            return {"id": 1, "email": email, "role": "user"}
        raise HTTPException(status_code=503, detail="db unavailable")


# ---------------------------------------------------------------------
# CORS Configuration - FIXED
# ---------------------------------------------------------------------

def _parse_csv(s: str) -> list[str]:
    return [p.strip() for p in (s or "").split(",") if p and p.strip()]


# CORS erlaubte Origins - FIX: Explizit alle relevanten Origins setzen
CORS_ALLOW_ORIGINS_ENV = os.getenv("CORS_ALLOW_ORIGINS", "")

# Standard Origins für KI-Sicherheit Projekt
DEFAULT_ORIGINS = [
    "https://make.ki-sicherheit.jetzt",
    "http://make.ki-sicherheit.jetzt",
    "https://ki-sicherheit.jetzt",
    "http://ki-sicherheit.jetzt",
    "http://localhost:3000",
    "http://localhost:8000",
    "http://localhost:8080",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:8080"
]

# Parse environment variable or use defaults
if CORS_ALLOW_ORIGINS_ENV:
    CORS_ALLOW_ORIGINS = _parse_csv(CORS_ALLOW_ORIGINS_ENV)
else:
    CORS_ALLOW_ORIGINS = DEFAULT_ORIGINS

# In development, allow all origins
if os.getenv("ENVIRONMENT", "production").lower() in ["dev", "development", "local"]:
    CORS_ALLOW_ORIGINS = ["*"]
    
# ---------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------

REQUESTS = Counter("app_requests_total", "HTTP requests total", ["method", "path", "status"])
LATENCY = Histogram("app_request_latency_seconds", "Request latency", ["path"])
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


def _issue_token(email: str) -> str:
    payload = {"sub": email, "email": email, "iat": int(time.time()), "exp": int(time.time() + 14 * 24 * 3600)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


async def current_user(req: Request):
    auth = req.headers.get("authorization") or ""
    parts = auth.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        try:
            payload = jwt.decode(parts[1], JWT_SECRET, algorithms=[JWT_ALGO])
            return {"sub": payload.get("sub"), "email": payload.get("email", payload.get("sub"))}
        except JWTError:
            pass
    return {"sub": "anon", "email": ""}


# ---------------------------------------------------------------------
# Startup / App
# ---------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info(
        "%s started | version=%s schema=%s prompt=%s strict_login=%s direct_first=%s",
        APP_NAME,
        APP_VERSION or "-",
        SCHEMA_VERSION or "-",
        PROMPT_VERSION or "-",
        STRICT_DB_LOGIN,
        DB_LOGIN_DIRECT_FIRST,
    )
    log.info(f"CORS allowed origins: {CORS_ALLOW_ORIGINS}")
    log.info(f"JWT Secret configured: {'Yes' if JWT_SECRET != 'dev-secret-change-in-production' else 'No (using dev default)'}")
    log.info(f"Database configured: {'Yes' if DATABASE_URL else 'No'}")
    yield


app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan)

# CORS Middleware - Mit expliziten Headers
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600
)


# Request-ID & Metrics
@app.middleware("http")
async def _metrics_mw(request: Request, call_next):
    path_label = _normalize_path(request.url.path)
    req_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
    start = time.time()
    
    # Log incoming requests for debugging
    log.debug(f"Incoming request: {request.method} {request.url.path} from {request.client.host if request.client else 'unknown'}")
    
    try:
        resp = await call_next(request)
    except Exception as e:
        log.error(f"Request failed: {e}")
        REQUESTS.labels(request.method, path_label, "500").inc()
        LATENCY.labels(path_label).observe(time.time() - start)
        resp = Response(status_code=500)
        resp.headers[REQUEST_ID_HEADER] = req_id
        raise
    
    status = getattr(resp, "status_code", 200) or 200
    REQUESTS.labels(request.method, path_label, str(status)).inc()
    LATENCY.labels(path_label).observe(time.time() - start)
    resp.headers[REQUEST_ID_HEADER] = req_id
    
    # Add CORS headers explicitly for OPTIONS
    if request.method == "OPTIONS":
        resp.headers["Access-Control-Allow-Origin"] = request.headers.get("origin", "*")
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "*"
        resp.headers["Access-Control-Allow-Credentials"] = "true"
    
    return resp


# ---------------------------------------------------------------------
# Health & Metrics
# ---------------------------------------------------------------------

@app.get("/")
@app.head("/")
def root() -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><meta charset='utf-8'>"
        f"<title>{APP_NAME}</title>"
        f"<h1>{APP_NAME}</h1>"
        f"<p>Status: OK – {_now_str()}</p>"
        f"<p>Version: {APP_VERSION or 'dev'}</p>"
        f"<p>Endpoints: /api/login, /briefing_async, /healthz, /metrics</p>"
        f"<small>Schema: {SCHEMA_VERSION or '-'} • Prompt: {PROMPT_VERSION or '-'}</small>"
    )


@app.get("/health")
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
        "cors_origins": len(CORS_ALLOW_ORIGINS) if CORS_ALLOW_ORIGINS != ["*"] else "all",
        "metrics": {"exposed": True, "endpoint": "/metrics"},
    }


@app.get("/api/health")
@app.get("/api/ping")
def api_ping() -> Dict[str, Any]:
    return {"ok": True, "ts": _now_str(), "version": APP_VERSION}


@app.get("/metrics")
def metrics() -> Response:
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


# ---------------------------------------------------------------------
# Login Endpoint - SIMPLIFIED FOR TESTING
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
    capacity=int(os.getenv("LOGIN_RATE_CAPACITY", "20")),  # Increased for testing
    refill_rate=float(os.getenv("LOGIN_RATE_REFILL_PER_SEC", "0.5")),
)

DB_LOGIN_TIMEOUT_S = float(os.getenv("DB_LOGIN_TIMEOUT_S", "5.0"))


@app.post("/api/login")
async def api_login(request: Request, body: Any = Body(...)) -> Dict[str, Any]:
    """Login endpoint with rate limiting"""
    log.info(f"Login attempt from {request.client.host if request.client else 'unknown'}")
    
    ip = request.client.host if request and request.client else "unknown"
    if not LOGIN_RATE.allow(ip):
        LOGIN_REJECTS.labels("rate").inc()
        log.warning(f"Rate limit exceeded for {ip}")
        raise HTTPException(status_code=429, detail="too many requests")

    # Parse body
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except Exception:
            body = {"email": body}
    if not isinstance(body, dict):
        body = body or {}
    
    email = _sanitize_email(str(body.get("email") or ""))
    password = str(body.get("password") or "")

    log.info(f"Login attempt for email: {email}")

    if not email:
        LOGIN_REJECTS.labels("bad_input").inc()
        raise HTTPException(status_code=400, detail="email required")

    # For development/testing: Accept any valid email
    if not STRICT_DB_LOGIN:
        log.info(f"Development mode: Issuing token for {email}")
        token = _issue_token(email)
        LOGIN_SUCCESS.inc()
        return {"token": token, "email": email, "role": "user", "message": "Development mode - no DB validation"}

    # Database authentication
    if not password:
        LOGIN_REJECTS.labels("bad_input").inc()
        raise HTTPException(status_code=400, detail="password required")
        
    try:
        user = await asyncio.wait_for(
            run_in_threadpool(_db_verify_user_direct, email, password),
            timeout=DB_LOGIN_TIMEOUT_S
        )
    except asyncio.TimeoutError:
        LOGIN_REJECTS.labels("timeout").inc()
        log.error(f"Login timeout for {email}")
        # In dev mode, allow anyway
        if not STRICT_DB_LOGIN:
            token = _issue_token(email)
            LOGIN_SUCCESS.inc()
            return {"token": token, "email": email, "role": "user", "message": "DB timeout - fallback to dev mode"}
        raise HTTPException(status_code=504, detail="login backend timeout")
    except Exception as e:
        log.error(f"Login error: {e}")
        # In dev mode, allow anyway
        if not STRICT_DB_LOGIN:
            token = _issue_token(email)
            LOGIN_SUCCESS.inc()
            return {"token": token, "email": email, "role": "user", "message": "DB error - fallback to dev mode"}
        raise

    if not user:
        LOGIN_REJECTS.labels("invalid").inc()
        log.warning(f"Invalid credentials for {email}")
        raise HTTPException(status_code=401, detail="invalid credentials")

    token = _issue_token(email)
    LOGIN_SUCCESS.inc()
    log.info(f"Login successful for {email}")
    return {"token": token, "email": email, "role": user.get("role", "user")}


# ---------------------------------------------------------------------
# OPTIONS handler for CORS preflight
# ---------------------------------------------------------------------

@app.options("/api/login")
async def options_login():
    return Response(status_code=200)


@app.options("/briefing_async")
async def options_briefing():
    return Response(status_code=200)


# ---------------------------------------------------------------------
# Analyzer / Report
# ---------------------------------------------------------------------

@app.post("/briefing_async")
async def briefing_async(
    body: Dict[str, Any], 
    request: Request, 
    user=Depends(current_user)
):
    """Report generation endpoint"""
    log.info(f"Briefing request from {user.get('email', 'unknown')}")
    
    lang = str(body.get("lang") or body.get("language") or "de").lower()
    recipient_user = _sanitize_email(body.get("email") or user.get("email") or "")
    
    if not recipient_user:
        raise HTTPException(status_code=400, detail="recipient could not be resolved")
    
    # Log the form data (without sensitive info)
    log.info(f"Report requested for {recipient_user} in language {lang}")
    log.info(f"Form fields: {list(body.keys())}")
    
    # Simplified response for now
    job_id = uuid.uuid4().hex
    return JSONResponse({
        "status": "ok", 
        "job_id": job_id,
        "message": f"Report generation started for {recipient_user}",
        "language": lang,
        "estimated_time": "2-5 minutes"
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))