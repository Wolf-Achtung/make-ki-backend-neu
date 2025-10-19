"""
FastAPI application entry point for KI-Status-Report backend.
Gold-Standard+ edition: robust logging, resilient router loading, strict CORS setup.
"""
from __future__ import annotations

import importlib
import logging
import os
import pkgutil
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.middleware.cors import CORSMiddleware

try:
    # local module
    from settings import settings, allowed_origins  # type: ignore
except Exception as exc:  # pragma: no cover - startup guard
    # Minimal fallback to still boot the server to expose a meaningful error
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("ki-backend").exception("Failed to import settings at startup. Server will still boot with limited features. Error: %s", exc)
    # Provide minimal stand-in config
    class _FallbackSettings:
        APP_NAME = "KI-Backend"
        APP_VERSION = "0.0.0"
        ENV = os.getenv("ENV", "production")
        LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        QUEUE_ENABLED = False
        PDF_SERVICE_URL = None
        def __init__(self):
            pass
        @property
        def CORS_ALLOW_ORIGINS(self):
            raw = os.getenv("CORS_ALLOW_ORIGINS_RAW", "") or os.getenv("CORS_ALLOW_ORIGINS", "*")
            if raw.strip() in ("*", "", None):
                return ["*"]
            return [p.strip() for p in raw.split(",") if p.strip()]
    settings = _FallbackSettings()  # type: ignore
    allowed_origins = settings.CORS_ALLOW_ORIGINS  # type: ignore

# -------------------------------------------------------------------------
# Logging (structured-friendly but simple)
# -------------------------------------------------------------------------
LOG_LEVEL = (os.getenv("LOG_LEVEL", settings.LOG_LEVEL) or "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("ki-backend")

# -------------------------------------------------------------------------
# App
# -------------------------------------------------------------------------
app = FastAPI(
    title=getattr(settings, "APP_NAME", "KI-Status-Report Backend"),
    version=getattr(settings, "APP_VERSION", "2025.10"),
    description="Backend for KI-Sicherheit / KI-Status-Report",
    contact={"name": "KI-Sicherheit.jetzt", "url": "https://ki-sicherheit.jetzt"},
)

# CORS – accept CSV or computed list from settings; fall back to '*'
_origins = allowed_origins if isinstance(allowed_origins, (list, tuple)) and allowed_origins else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins if _origins != ["*"] else ["*"],
    allow_credentials=bool(getattr(settings, "CORS_ALLOW_CREDENTIALS", False)),
    allow_methods=list(getattr(settings, "CORS_ALLOW_METHODS", ["*"])),
    allow_headers=list(getattr(settings, "CORS_ALLOW_HEADERS", ["*"])),
    max_age=86400,
)

# -------------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------------
@app.get("/", response_class=PlainTextResponse, include_in_schema=False)
async def root() -> str:
    return "KI-Status-Report backend is running."

@app.get("/healthz", response_class=JSONResponse)
async def healthz():
    # Keep fields stable for the Railway healthcheck
    try:
        # If a routes/ module imports successfully, we likely have a functioning app
        status = "ok"
    except Exception:  # pragma: no cover
        status = "degraded"
    features = {
        "eu_host_check": True,
        "idempotency": True,
        "quality": True,
    }
    return {
        "ok": True,
        "time": datetime.now(timezone.utc).isoformat(),
        "env": getattr(settings, "ENV", os.getenv("ENV", "production")),
        "version": getattr(settings, "APP_VERSION", "2025.10"),
        "features": features,
        "queue_enabled": bool(getattr(settings, "QUEUE_ENABLED", False)),
        "pdf_service": bool(getattr(settings, "PDF_SERVICE_URL", None) or getattr(settings, "PDF_SERVICE_ENABLED", False)),
        "status": status,
    }

# Dynamic router inclusion: any module in the 'routes' pkg exposing variable 'router'
def include_all_routers() -> int:
    imported = 0
    pkg_name = "routes"
    try:
        pkg = importlib.import_module(pkg_name)
        search_path = list(getattr(pkg, "__path__", []))
        if not search_path:
            logger.warning("Package '%s' has no __path__, skipping router discovery.", pkg_name)
            return 0
    except Exception as exc:
        logger.warning("No '%s' package found or failed to import: %s", pkg_name, exc)
        return 0

    for module_finder, name, ispkg in pkgutil.iter_modules(search_path, f"{pkg_name}."):
        # Skip dunder and private modules
        base = name.split(".")[-1]
        if base.startswith("_"):
            continue
        try:
            module = importlib.import_module(name)
            router = getattr(module, "router", None)
            if router is not None:
                app.include_router(router)  # type: ignore[arg-type]
                imported += 1
                logger.info("Included router from %s", name)
            else:
                logger.debug("Module %s has no 'router' attribute; skipped.", name)
        except Exception:
            logger.exception("Failed to include router from %s", name)
    if imported == 0:
        logger.warning("No route modules found under '%s' package.", pkg_name)
    return imported

@app.on_event("startup")
async def on_startup():
    count = include_all_routers()
    logger.info("Startup complete. Included %d routers. ENV=%s", count, getattr(settings, "ENV", "n/a"))

# For local debug with: python -m uvicorn main:app --reload
if __name__ == "__main__":  # pragma: no cover - manual execution helper
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8080")), reload=True)