#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KI-Status-Report Backend - FastAPI entrypoint (Queue-enabled).

- Robust logging & settings
- CORS via env
- Health/diag endpoints
- Routers: login, admin, feedback, briefing, tasks_api (queue)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import List

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

def _get_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return str(val).strip().lower() in {"1", "true", "yes", "y", "on"}

APP_NAME = os.getenv("APP_NAME", "KI-Status-Report Backend")
ENV = os.getenv("ENV", "production")
VERSION = os.getenv("VERSION", "2025.10")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

PDF_SERVICE_URL = os.getenv("PDF_SERVICE_URL", "").strip()
PDF_TIMEOUT = int(os.getenv("PDF_TIMEOUT", "45000"))

REDIS_URL = os.getenv("REDIS_URL", "").strip()
ENABLE_QUEUE = _get_bool("ENABLE_QUEUE", False)

# CORS
raw_origins = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
if raw_origins:
    CORS_ALLOW_ORIGINS: List[str] = [o.strip() for o in raw_origins.split(",") if o.strip()]
else:
    CORS_ALLOW_ORIGINS = []

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("ki-backend")

app = FastAPI(title=APP_NAME, version=VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS or (["*"] if ENV != "production" else []),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        "queue_enabled": bool(ENABLE_QUEUE and REDIS_URL),
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
            "ENABLE_QUEUE": bool(ENABLE_QUEUE),
            "REDIS_URL_SET": bool(REDIS_URL),
            "PDF_SERVICE_URL_SET": bool(PDF_SERVICE_URL),
            "PDF_TIMEOUT": PDF_TIMEOUT,
            "DEBUG": LOG_LEVEL in {"DEBUG", "TRACE"},
        },
        "time": datetime.now(timezone.utc).isoformat(),
    }

def _include_router(module_name: str, prefix: str = "/api") -> None:
    try:
        module = __import__(module_name, fromlist=["router"])
        router = getattr(module, "router", None)
        if router is None:
            logger.warning("Module %s found but no 'router' attribute.", module_name)
            return
        app.include_router(router, prefix=prefix)
        logger.info("Included %s as %s/*", module_name, prefix)
    except Exception as exc:
        logger.warning("Could not include %s: %s", module_name, exc)

# Core routers
_include_router("routes.auth_login", prefix="/api")
_include_router("routes.admin_status", prefix="/api")
_include_router("routes.feedback", prefix="/api")
_include_router("routes.briefing", prefix="/api")
# NEW: tasks/queue API
_include_router("routes.tasks_api", prefix="/api")

@app.get("/api/login")
async def login_get_hint():
    raise HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, detail="Use POST /api/login")
