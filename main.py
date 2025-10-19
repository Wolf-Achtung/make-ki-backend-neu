#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KI–Status–Report Backend — stable entrypoint (hotfix)
----------------------------------------------------
This file configures FastAPI, logging, CORS, health/diagnostics,
and includes all routers. It also adds a compatibility alias for
/api/login (see routes/login_compat.py).
"""
from __future__ import annotations

import importlib
import logging
import os
from datetime import datetime, timezone
from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import PlainTextResponse, JSONResponse

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL_NAME = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_NAME, logging.INFO)
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("ki-backend")

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
APP_NAME = os.getenv("APP_NAME", "KI-Status-Report Backend")
ENV = os.getenv("ENV", "production").lower()
VERSION = os.getenv("VERSION", "2025.10")
API_PREFIX = os.getenv("API_PREFIX", "/api").rstrip("/")

# CORS
def _parse_csv(value: str) -> List[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]

ALLOW_ORIGINS = _parse_csv(os.getenv("CORS_ALLOW_ORIGINS", ""))
if not ALLOW_ORIGINS and ENV != "production":
    # in dev, allow localhost by default
    ALLOW_ORIGINS = [
        "http://localhost",
        "http://127.0.0.1",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title=APP_NAME,
    version=VERSION,
    docs_url=None if ENV == "production" else f"{API_PREFIX}/docs",
    redoc_url=None,
    openapi_url=None if ENV == "production" else f"{API_PREFIX}/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOW_ORIGINS or ["*"] if ENV != "production" else ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# ---------------------------------------------------------------------------
# Utility: safe include of routers
# ---------------------------------------------------------------------------
def include_router_safe(module_name: str, router_name: str = "router") -> None:
    try:
        module = importlib.import_module(module_name)
        router = getattr(module, router_name, None)
        if router is None:
            raise AttributeError(f"Module '{module_name}' has no '{router_name}'")
        app.include_router(router, prefix=API_PREFIX)
        logger.info("Included %s as %s/*", module_name, API_PREFIX)
    except Exception as exc:
        logger.warning("Could not include %s: %s", module_name, exc)

# Include project routers (only those that actually exist will be mounted)
for module in [
    "routes.auth_login",       # canonical login (/api/auth/login)
    "routes.briefing",         # domain routes, if present
    "routes.admin_status",     # /api/admin/status (protected)
    "routes.feedback",         # optional; may not exist
    "routes.login_compat",     # NEW: provides /api/login -> /api/auth/login
]:
    include_router_safe(module)

# ---------------------------------------------------------------------------
# Basic system routes
# ---------------------------------------------------------------------------
@app.get("/", response_class=PlainTextResponse)
async def root() -> str:
    return "KI–Status–Report backend is running."

@app.get(f"{API_PREFIX}/healthz")
async def healthz() -> dict:
    return {
        "ok": True,
        "time": datetime.now(timezone.utc).isoformat(),
        "env": ENV,
        "version": VERSION,
        "queue_enabled": bool(os.getenv("QUEUE_ENABLED", "")),
        "pdf_service": bool(os.getenv("PDF_SERVICE_URL", "")),
        "status": "ok",
    }

@app.get(f"{API_PREFIX}/diag")
async def diag() -> dict:
    return {
        "ok": True,
        "settings": {
            "APP_NAME": APP_NAME,
            "ENV": ENV,
            "VERSION": VERSION,
            "QUEUE_ENABLED": bool(os.getenv("QUEUE_ENABLED", "")),
            "REDIS_URL_SET": bool(os.getenv("REDIS_URL", "")),
            "PDF_SERVICE_URL_SET": bool(os.getenv("PDF_SERVICE_URL", "")),
            "PDF_TIMEOUT": int(os.getenv("PDF_TIMEOUT", "45000")),
            "DEBUG": ENV != "production",
        },
        "time": datetime.now(timezone.utc).isoformat(),
    }
