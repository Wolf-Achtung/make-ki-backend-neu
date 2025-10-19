# main.py (v2)
# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

def _coerce_level(value: str, default: int = logging.INFO) -> int:
    mapping = {
        "CRITICAL": logging.CRITICAL,
        "ERROR": logging.ERROR,
        "WARNING": logging.WARNING,
        "INFO": logging.INFO,
        "DEBUG": logging.DEBUG,
    }
    if not value:
        return default
    return mapping.get(str(value).upper(), default)

logging.basicConfig(
    level=_coerce_level(os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("ki-backend")

try:
    from settings import settings, allowed_origins  # type: ignore
except Exception as exc:  # pragma: no cover
    logger.exception("Failed to import settings, using minimal fallbacks: %s", exc)
    class _Fallback:
        APP_NAME = "KI‑Status‑Report Backend"
        VERSION = os.getenv("APP_VERSION", "2025.10")
        ENV = os.getenv("ENV", "production")
        DEBUG = os.getenv("DEBUG", "false").lower() == "true"
        JWT_SECRET = os.getenv("JWT_SECRET")
        ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")
        QUEUE_ENABLED = os.getenv("QUEUE_ENABLED", "false").lower() == "true"
        REDIS_URL = os.getenv("REDIS_URL")
        PDF_SERVICE_URL = os.getenv("PDF_SERVICE_URL")
        PDF_SERVICE_ENABLED = os.getenv("PDF_SERVICE_ENABLED", "true").lower() == "true"
        PDF_TIMEOUT = int(os.getenv("PDF_TIMEOUT", "15000"))
    settings = _Fallback()  # type: ignore
    allowed_origins = ["*"]

app = FastAPI(title=getattr(settings, "APP_NAME", "KI‑Status‑Report Backend"),
              version=getattr(settings, "VERSION", "2025.10"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=PlainTextResponse)
async def root() -> str:
    return "KI–Status–Report backend is running."

@app.get("/healthz", response_class=JSONResponse)
async def healthz() -> Dict[str, Any]:
    features = {"eu_host_check": True, "idempotency": True, "quality": True}
    return {
        "ok": True,
        "time": datetime.now(timezone.utc).isoformat(),
        "env": getattr(settings, "ENV", "production"),
        "version": getattr(settings, "VERSION", "2025.10"),
        "features": features,
        "queue_enabled": bool(getattr(settings, "QUEUE_ENABLED", False)),
        "pdf_service": bool(getattr(settings, "PDF_SERVICE_URL", None)),
        "status": "ok",
    }

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

async def _is_admin(request: Request, x_admin_key: Optional[str] = Header(default=None)) -> None:
    if getattr(settings, "DEBUG", False):
        return
    configured = getattr(settings, "ADMIN_API_KEY", None)
    if configured and (x_admin_key == configured or request.query_params.get("key") == configured):
        return
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer ") and getattr(settings, "JWT_SECRET", None):
        token = auth.split(" ", 1)[1].strip()
        try:
            from jose import jwt  # type: ignore
            data = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])  # type: ignore
            if str(data.get("role", "")).lower() == "admin":
                return
        except Exception:
            pass
    raise HTTPException(status_code=401, detail="Unauthorized")

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

def _include(router_path: str) -> bool:
    try:
        module = importlib.import_module(router_path)
        router = getattr(module, "router", None)
        if router is None:
            logger.warning("%s found but has no 'router' attribute", router_path)
            return False
        app.include_router(router)
        logger.info("Included %s", router_path)
        return True
    except Exception as exc:
        logger.warning("Could not include %s: %s", router_path, exc)
        return False

included_feedback = False
for mod in ["routes.briefing", "routes.auth_login", "routes.feedback", "routes.admin_submissions"]:
    ok = _include(mod)
    if mod.endswith(".feedback"):
        included_feedback = ok

# --- Feedback Fallback, falls Modul fehlt ---
if not included_feedback:
    from fastapi import APIRouter
    fallback = APIRouter()
    @fallback.post("/feedback", response_class=JSONResponse, tags=["feedback"])
    async def submit_feedback(payload: dict[str, Any]) -> Dict[str, Any]:
        logger.info("Feedback (fallback) received: %s", str(payload)[:500])
        return {"ok": True, "status": "accepted"}
    app.include_router(fallback)
    logger.info("Installed feedback fallback router")

# --- API Aliases (preserve method + body via 307 redirect) ---
def _alias(path: str):
    async def _redir() -> RedirectResponse:
        return RedirectResponse(url=path, status_code=307)
    return _redir

for p in ["login", "analyze", "feedback"]:
    app.add_api_route(f"/api/{p}", endpoint=_alias(f"/{p}"), methods=["GET", "POST", "OPTIONS"])

# result with ID
async def _alias_result(job_id: str) -> RedirectResponse:
    return RedirectResponse(url=f"/result/{job_id}", status_code=307)
app.add_api_route("/api/result/{job_id}", endpoint=_alias_result, methods=["GET"])

# health & diag aliases
app.add_api_route("/api/health", endpoint=_alias("/healthz"), methods=["GET"])
app.add_api_route("/api/healthz", endpoint=_alias("/healthz"), methods=["GET"])
app.add_api_route("/api/diag", endpoint=_alias("/diag"), methods=["GET"])
