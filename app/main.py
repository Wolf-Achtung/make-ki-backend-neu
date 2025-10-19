from __future__ import annotations

import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import PlainTextResponse

from .settings import settings, allowed_origins
from .routes import health, diag, auth_login, admin_status

# ----------------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------------
LOG_LEVEL = settings.LOG_LEVEL
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("ki-backend")
logger.info("Starting %s v%s (env=%s)", settings.APP_NAME, settings.VERSION, settings.ENV)

# ----------------------------------------------------------------------------
# App
# ----------------------------------------------------------------------------
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    docs_url=None if settings.ENV == "production" else "/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

# CORS
if allowed_origins():
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins(),
        allow_methods=settings.CORS_ALLOW_METHODS or ["*"],
        allow_headers=settings.CORS_ALLOW_HEADERS or ["*"],
        allow_credentials=True,
        max_age=86400,
    )

# Root is a simple liveness text (as in your screenshot)
@app.get("/", response_class=PlainTextResponse, include_in_schema=False)
def root():
    return "KI–Status–Report backend is running."

# Mount API routers under /api
from fastapi import APIRouter
api = APIRouter(prefix="/api")
api.include_router(health.router)
api.include_router(diag.router)
api.include_router(auth_login.router)
api.include_router(admin_status.router)
app.include_router(api)

# 404 safety: helpful hint when someone hits /api without route
@app.get("/api", include_in_schema=False)
def api_index():
    return {"ok": True, "message": "See /api/healthz, /api/diag, POST /api/login, /api/admin/status"}
