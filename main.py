#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KI-Status-Report Backend - production-grade FastAPI entrypoint.

- Robust logging & settings
- Strict CORS (configurable)
- Health & diagnostics endpoints
- Safe router inclusion (auth login, admin status, feedback, briefing)
- Friendly root message for uptime checks

Author: Gold-Standard+ refactor
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def _get_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return str(val).strip().lower() in {"1", "true", "yes", "y", "on"}

APP_NAME = os.getenv("APP_NAME", "KI-Status-Report Backend")
ENV = os.getenv("ENV", "production")
VERSION = os.getenv("VERSION", "2025.10")
PDF_SERVICE_URL = os.getenv("PDF_SERVICE_URL", "").strip()
PDF_TIMEOUT = int(os.getenv("PDF_TIMEOUT", "45000"))
REDIS_URL = os.getenv("REDIS_URL", "").strip()
QUEUE_ENABLED = _get_bool("ENABLE_QUEUE", False)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# CORS
_raw_origins = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
if _raw_origins:
    CORS_ALLOW_ORIGINS: List[str] = [o.strip() for o in _raw_origins.split(",") if o.strip()]
else:
    # In production you should explicitly list your domains here.
    # Leaving it empty defaults to a conservative "*only for dev*".
    CORS_ALLOW_ORIGINS = []

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("ki-backend")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title=APP_NAME, version=VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS or ["*"] if ENV != "production" else CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Root / Health / Diagnostics
# ---------------------------------------------------------------------------
@app.get("/", response_class=PlainTextResponse)
async def root() -> str:
    return "KI–Status–Report backend is running.\n"

@app.get("/api/healthz", response_class=JSONResponse)
async def healthz():
    return {
        "ok": True,
        "time": datetime.now(timezone.utc).isoformat(),
        "env": ENV,
        "version": VERSION,
        "queue_enabled": bool(QUEUE_ENABLED and REDIS_URL),
        "pdf_service": bool(PDF_SERVICE_URL),
        "status": "ok",
    }

@app.get("/api/diag", response_class=JSONResponse)
async def diag():
    return {
        "ok": True,
        "settings": {
            "APP_NAME": APP_NAME,
            "ENV": ENV,
            "VERSION": VERSION,
            "QUEUE_ENABLED": bool(QUEUE_ENABLED),
            "REDIS_URL_SET": bool(bool(REDIS_URL)),
            "PDF_SERVICE_URL_SET": bool(PDF_SERVICE_URL),
            "PDF_TIMEOUT": PDF_TIMEOUT,
            "DEBUG": LOG_LEVEL in {"DEBUG", "TRACE"},
        },
        "time": datetime.now(timezone.utc).isoformat(),
    }

# ---------------------------------------------------------------------------
# Router inclusion helpers
# ---------------------------------------------------------------------------
def _include_router(module_name: str, prefix: str = "/api") -> None:
    """
    Try to import a router module and include it. Log a clear message otherwise.
    """
    try:
        module = __import__(module_name, fromlist=["router"])
        router = getattr(module, "router", None)
        if router is None:
            logger.warning("Module %s found but no 'router' attribute.", module_name)
            return
        app.include_router(router, prefix=prefix)
        logger.info("Included %s as %s/*", module_name, prefix)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not include %s: %s", module_name, exc)

# Register core routes
_include_router("routes.auth_login", prefix="/api")
_include_router("routes.admin_status", prefix="/api")
_include_router("routes.feedback", prefix="/api")
_include_router("routes.briefing", prefix="/api")

# Optional: a small guidance for GET /api/login
from fastapi import HTTPException, status

@app.get("/api/login")
async def login_get_hint():
    raise HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, detail="Use POST /api/login")
