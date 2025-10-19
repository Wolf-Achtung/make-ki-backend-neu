# main.py (v3 – preferences applied)
# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

# ---------- Logging ----------
def _coerce_level(value: str, default: int = logging.INFO) -> int:
    mapping = {"CRITICAL":50,"ERROR":40,"WARNING":30,"INFO":20,"DEBUG":10}
    if not value:
        return default
    return mapping.get(str(value).upper(), default)

logging.basicConfig(
    level=_coerce_level(os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("ki-backend")

# ---------- Settings ----------
try:
    from settings import settings, allowed_origins  # type: ignore
except Exception as exc:  # pragma: no cover
    logger.exception("Failed to import settings: %s", exc)
    class _FB:
        APP_NAME="KI‑Status‑Report Backend"; VERSION=os.getenv("APP_VERSION","2025.10")
        ENV=os.getenv("ENV","production"); DEBUG=False; JWT_SECRET=os.getenv("JWT_SECRET")
        QUEUE_ENABLED=False; REDIS_URL=None; PDF_SERVICE_URL=None; PDF_SERVICE_ENABLED=True; PDF_TIMEOUT=15000
    settings=_FB()  # type: ignore
    allowed_origins=["*"]

app = FastAPI(title=getattr(settings, "APP_NAME", "KI‑Status‑Report Backend"),
              version=getattr(settings, "VERSION", "2025.10"))

# ---------- CORS ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Templates ----------
templates = Jinja2Templates(directory="templates")

# ---------- Health (both flat and /api for ops) ----------
@app.get("/healthz", response_class=JSONResponse)
async def healthz() -> Dict[str, Any]:
    return {
        "ok": True,
        "time": datetime.now(timezone.utc).isoformat(),
        "env": getattr(settings, "ENV", "production"),
        "version": getattr(settings, "VERSION", "2025.10"),
        "queue_enabled": bool(getattr(settings, "QUEUE_ENABLED", False)),
        "pdf_service": bool(getattr(settings, "PDF_SERVICE_URL", None)) and bool(getattr(settings, "PDF_SERVICE_ENABLED", True)),
        "status": "ok",
    }

@app.get("/api/healthz", response_class=JSONResponse)
async def api_healthz() -> Dict[str, Any]:
    return await healthz()  # same payload

@app.get("/api/health", response_class=JSONResponse)
async def api_health() -> Dict[str, Any]:
    return await healthz()

# ---------- Diag (flat + /api) ----------
@app.get("/diag", response_class=JSONResponse)
async def diag() -> Dict[str, Any]:
    safe_settings = {
        "APP_NAME": getattr(settings, "APP_NAME", None),
        "ENV": getattr(settings, "ENV", None),
        "VERSION": getattr(settings, "VERSION", None),
        "QUEUE_ENABLED": getattr(settings, "QUEUE_ENABLED", False),
        "REDIS_URL_SET": bool(getattr(settings, "REDIS_URL", None)),
        "PDF_SERVICE_URL_SET": bool(getattr(settings, "PDF_SERVICE_URL", None)),
        "PDF_TIMEOUT": getattr(settings, "PDF_TIMEOUT", None),
        "DEBUG": getattr(settings, "DEBUG", False),
    }
    return {"ok": True, "settings": safe_settings, "time": datetime.now(timezone.utc).isoformat()}

@app.get("/api/diag", response_class=JSONResponse)
async def api_diag() -> Dict[str, Any]:
    return await diag()

# ---------- Root ----------
@app.get("/", response_class=PlainTextResponse)
async def root() -> str:
    return "KI–Status–Report backend is running."

# ---------- Admin Guard (2B: JWT only, no API key, no DEBUG bypass) ----------
async def _is_admin(request: Request) -> None:
    auth = request.headers.get("Authorization", "")
    secret = getattr(settings, "JWT_SECRET", None)
    if not (auth.lower().startswith("bearer ") and secret):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = auth.split(" ", 1)[1].strip()
    try:
        from jose import jwt  # type: ignore
        data = jwt.decode(token, secret, algorithms=["HS256"])  # type: ignore
        if str(data.get("role", "")).lower() != "admin":
            raise HTTPException(status_code=403, detail="Forbidden")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Unauthorized")

# ---------- Admin Status (HTML) ----------
@app.get("/admin/status", response_class=HTMLResponse, dependencies=[Depends(_is_admin)])
async def admin_status(request: Request) -> HTMLResponse:
    queue_mode = "Local"
    queue_stats: dict[str, Any] = {}
    if getattr(settings, "QUEUE_ENABLED", False) and getattr(settings, "REDIS_URL", None):
        try:
            import redis  # type: ignore
            from rq import Queue  # type: ignore
            r = redis.from_url(settings.REDIS_URL)  # type: ignore
            q = Queue("reports", connection=r)  # type: ignore
            queue_mode = "Redis"
            queue_stats = {
                "count": len(q.jobs),  # type: ignore
                "deferred": len(q.deferred_job_registry),  # type: ignore
                "failed": len(q.failed_job_registry),  # type: ignore
            }
        except Exception as exc:
            logger.warning("Queue stats not available: %s", exc)

    pdf_enabled = bool(getattr(settings, "PDF_SERVICE_URL", None)) and bool(getattr(settings, "PDF_SERVICE_ENABLED", True))

    ctx = {
        "request": request,
        "app_name": getattr(settings, "APP_NAME", "KI‑Status‑Report Backend"),
        "env": getattr(settings, "ENV", "production"),
        "version": getattr(settings, "VERSION", "2025.10"),
        "queue_mode": queue_mode,
        "queue_stats": queue_stats,
        "pdf_enabled": pdf_enabled,
        "time": datetime.now(timezone.utc).isoformat(),
    }
    return templates.TemplateResponse("admin_status.html", ctx)

# API path for admin status for consistency with 1B+6A
@app.get("/api/admin/status", response_class=HTMLResponse, dependencies=[Depends(_is_admin)])
async def api_admin_status(request: Request) -> HTMLResponse:
    return await admin_status(request)

# ---------- Dynamic router include under real /api prefix (1B) ----------
def _include(router_path: str, *, prefix: str = "/api") -> bool:
    try:
        module = importlib.import_module(router_path)
        router = getattr(module, "router", None)
        if router is None:
            logger.warning("%s found but has no 'router' attribute", router_path)
            return False
        app.include_router(router, prefix=prefix)
        logger.info("Included %s as %s/*", router_path, prefix)
        return True
    except Exception as exc:
        logger.warning("Could not include %s: %s", router_path, exc)
        return False

included_feedback = False
for mod in ["routes.briefing", "routes.auth_login", "routes.feedback", "routes.admin_submissions"]:
    ok = _include(mod, prefix="/api")
    if mod.endswith(".feedback"):
        included_feedback = ok

# Fallback feedback (mounted under /api) if module missing
if not included_feedback:
    from fastapi import APIRouter
    fb = APIRouter()
    @fb.post("/feedback", response_class=JSONResponse, tags=["feedback"])
    async def submit_feedback(payload: dict[str, Any]) -> Dict[str, Any]:
        logger.info("Feedback (fallback) received: %s", str(payload)[:500])
        return {"ok": True, "status": "accepted"}
    app.include_router(fb, prefix="/api")
    logger.info("Installed /api/feedback fallback router")
