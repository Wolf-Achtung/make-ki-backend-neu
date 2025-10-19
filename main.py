# filename: updated_backend/main.py
# -*- coding: utf-8 -*-
"""
Main application entry point for the KI‑Status‑Report backend.

This version of ``main.py`` reflects the Gold‑Standard+ refinements:

* Logging is initialised based on the ``LOG_LEVEL`` environment variable
  (case‑insensitive) with a safe fallback to ``INFO``.  Unexpected values
  no longer cause the logger to crash at startup.
* CORS configuration is obtained from the central ``settings`` module.  If
  no origins are provided, the server defaults to accepting all origins in
  test mode.  Origins may be specified as a JSON array, a comma‑separated
  string or the wildcard ``*``.
* The application attempts to dynamically import and register all routers
  located in the ``routes`` package.  Import errors in individual routers
  are logged but do not prevent the server from starting.
* Basic health and diagnostic endpoints are provided.  ``/healthz`` returns
  a JSON payload suitable for Railway health checks.  ``/diag`` provides
  a minimal information dump useful during development.
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
    # attempt to import the project settings and computed allowed origins
    from settings import settings, allowed_origins  # type: ignore
except Exception as exc:
    # If the settings cannot be imported, fall back to safe defaults.  The
    # health check will still return useful information and the server
    # continues to boot instead of crashing with an obscure error.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("ki-backend").exception(
        "Failed to import settings at startup.  Using fallback defaults.  Error: %s", exc
    )

    class _FallbackSettings:
        APP_NAME: str = os.getenv("APP_NAME", "KI‑Status‑Report Backend")
        APP_VERSION: str = os.getenv("APP_VERSION", "0.0.0")
        ENV: str = os.getenv("ENV", "production")
        LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
        QUEUE_ENABLED: bool = False
        PDF_SERVICE_URL: Optional[str] = None
        PDF_SERVICE_ENABLED: bool = False

        @property
        def CORS_ALLOW_ORIGINS(self) -> list[str]:
            # fallback to wildcard
            return ["*"]

    settings = _FallbackSettings()  # type: ignore
    allowed_origins = settings.CORS_ALLOW_ORIGINS  # type: ignore

else:
    # initialise logging using the configured log level.  ``LOG_LEVEL`` may
    # be set in the environment (any case), in the settings file or in the
    # default fallback above.  Unknown values map to ``INFO``.
    level_name = (os.getenv("LOG_LEVEL", settings.LOG_LEVEL) or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

logger = logging.getLogger("ki-backend")

# ---------------------------------------------------------------------------
# FastAPI application configuration
# ---------------------------------------------------------------------------
app = FastAPI(
    title=getattr(settings, "APP_NAME", "KI‑Status‑Report Backend"),
    version=getattr(settings, "APP_VERSION", "2025.10"),
    description="Backend for KI‑Sicherheit / KI‑Status‑Report",
    contact={"name": "KI‑Sicherheit.jetzt", "url": "https://ki-sicherheit.jetzt"},
)

_origins = allowed_origins if isinstance(allowed_origins, (list, tuple)) and allowed_origins else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins if _origins != ["*"] else ["*"],
    allow_credentials=bool(getattr(settings, "CORS_ALLOW_CREDENTIALS", False)),
    allow_methods=list(getattr(settings, "CORS_ALLOW_METHODS", ["*"])) or ["*"],
    allow_headers=list(getattr(settings, "CORS_ALLOW_HEADERS", ["*"])) or ["*"],
    max_age=86400,
)

# ---------------------------------------------------------------------------
# Basic system endpoints
# ---------------------------------------------------------------------------
@app.get("/", response_class=PlainTextResponse, include_in_schema=False)
async def root() -> str:
    """Return a simple message indicating that the backend is running."""
    return "KI‑Status‑Report backend is running."


@app.get("/healthz", response_class=JSONResponse)
async def healthz():
    """
    Health check endpoint used by Railway.  Returns a minimal JSON payload
    containing version, environment and enabled features.  The ``status`` field
    indicates whether at least one router was successfully imported.
    """
    status = "ok" if getattr(app.state, "routes_loaded", 0) > 0 else "degraded"
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


@app.get("/diag", response_class=JSONResponse)
async def diag():
    """
    Diagnostic endpoint for development and testing.  This endpoint should
    not expose sensitive information in production.  Returns environment and
    settings keys useful for troubleshooting.
    """
    return {
        "env": getattr(settings, "ENV", "unknown"),
        "version": getattr(settings, "APP_VERSION", "unknown"),
        "queue_enabled": bool(getattr(settings, "QUEUE_ENABLED", False)),
        "pdf_service_url": getattr(settings, "PDF_SERVICE_URL", None),
        "allow_origins": _origins,
    }

# ---------------------------------------------------------------------------
# Dynamic router inclusion
# ---------------------------------------------------------------------------
def include_all_routers() -> int:
    """
    Import and include all APIRouter objects from Python modules located in
    the ``routes`` package.  Each module that defines a global ``router``
    attribute will be added to the application.  Errors during import of
    individual modules are logged but do not stop the server from loading.
    Returns the number of routers successfully included.
    """
    included = 0
    pkg_name = "routes"
    try:
        pkg = importlib.import_module(pkg_name)
        search_path = list(getattr(pkg, "__path__", []))
        if not search_path:
            logger.warning("Package '%s' has no __path__; router discovery skipped.", pkg_name)
            return 0
    except Exception as exc:
        logger.warning("Package '%s' could not be imported: %s", pkg_name, exc)
        return 0

    for finder, name, ispkg in pkgutil.iter_modules(search_path, f"{pkg_name}."):
        base = name.split(".")[-1]
        if base.startswith("_"):
            continue  # skip private modules
        try:
            module = importlib.import_module(name)
            router = getattr(module, "router", None)
            if router is not None:
                app.include_router(router)
                included += 1
                logger.info("Included router from %s", name)
            else:
                logger.debug("Module %s has no 'router' attribute", name)
        except Exception:
            logger.exception("Failed to include router from %s", name)
    if included == 0:
        logger.warning("No route modules were successfully included from '%s'.", pkg_name)
    return included


@app.on_event("startup")
async def on_startup() -> None:
    """Executed during application startup to load all routers."""
    count = include_all_routers()
    app.state.routes_loaded = count
    logger.info("Startup complete.  Included %d routers. ENV=%s", count, getattr(settings, "ENV", "n/a"))


# For running directly via ``python main.py``
if __name__ == "__main__":  # pragma: no cover
    import uvicorn
    uvicorn.run(
        "updated_backend.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        reload=True,
    )