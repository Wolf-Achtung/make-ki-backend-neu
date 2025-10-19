"""
FastAPI application entrypoint for KI-Status-Report backend (Gold-Standard+ hotfix).
- Robust startup on Railway (python -m uvicorn main:app --app-dir <repo-root>).
- Strict security headers + CORS.
- Stable /healthz and /admin/status endpoints.
- Defensive router import (won't crash if optional route modules are absent).
- JWT verification for admin endpoints with optional X-Admin-Key bypass for tests.
"""
from __future__ import annotations

import os
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.datastructures import MutableHeaders

# JWT (python-jose)
try:
    from jose import jwt  # type: ignore
    # Import exceptions explicitly to avoid UnboundLocalError in except-blocks
    from jose.exceptions import JWTError, ExpiredSignatureError  # type: ignore
except Exception:  # pragma: no cover - keep server booting even if dependency missing during build
    jwt = None  # type: ignore
    JWTError = Exception  # type: ignore
    ExpiredSignatureError = Exception  # type: ignore

# ----------------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------------
LOG = logging.getLogger("ki-backend")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# ----------------------------------------------------------------------------
# Settings loader (compatible with both pydantic v1 and v2 projects)
# ----------------------------------------------------------------------------
class _FallbackSettings:
    ENV: str = os.getenv("ENV", "production")
    VERSION: str = os.getenv("APP_VERSION", "2025.10")
    ALLOWED_ORIGINS: Sequence[str] = tuple(
        filter(None, (os.getenv("ALLOWED_ORIGINS") or "").split(","))
    ) or ("*",)
    JWT_SECRET: str = os.getenv("JWT_SECRET", "dev-secret-change-me")
    JWT_ALG: str = os.getenv("JWT_ALG", "HS256")
    ADMIN_API_KEY: Optional[str] = os.getenv("ADMIN_API_KEY") or None
    QUEUE_ENABLED: bool = (os.getenv("QUEUE_ENABLED") or "").lower() in {"1","true","yes","on"}
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL") or None
    PDF_SERVICE_URL: Optional[str] = os.getenv("PDF_SERVICE_URL") or None

try:
    # Prefer project-native settings if present
    from settings import settings as _proj_settings  # type: ignore
    try:
        from settings import allowed_origins as _proj_allowed  # type: ignore
    except Exception:  # allowed_origins is optional
        _proj_allowed = None  # type: ignore

    class SettingsWrapper(_FallbackSettings):  # type: ignore
        def __init__(self) -> None:
            s = _proj_settings  # type: ignore
            self.ENV = getattr(s, "ENV", getattr(s, "env", "production"))
            self.VERSION = getattr(s, "VERSION", os.getenv("APP_VERSION", "2025.10"))
            self.ALLOWED_ORIGINS = tuple(
                getattr(s, "ALLOWED_ORIGINS", _proj_allowed or ("*",))
            )
            self.JWT_SECRET = getattr(s, "JWT_SECRET", os.getenv("JWT_SECRET", "dev-secret-change-me"))
            self.JWT_ALG = getattr(s, "JWT_ALG", "HS256")
            self.ADMIN_API_KEY = getattr(s, "ADMIN_API_KEY", os.getenv("ADMIN_API_KEY"))
            self.QUEUE_ENABLED = bool(getattr(s, "QUEUE_ENABLED", os.getenv("QUEUE_ENABLED", "false") in ("1","true","yes","on")))
            self.REDIS_URL = getattr(s, "REDIS_URL", os.getenv("REDIS_URL"))
            self.PDF_SERVICE_URL = getattr(s, "PDF_SERVICE_URL", os.getenv("PDF_SERVICE_URL"))

    settings = SettingsWrapper()
except Exception:
    LOG.warning("Falling back to internal settings (settings.py not found or invalid).")
    settings = _FallbackSettings()

allowed_origins: Sequence[str] = getattr(settings, "ALLOWED_ORIGINS", ("*",))

# ----------------------------------------------------------------------------
# App factory
# ----------------------------------------------------------------------------
app = FastAPI(
    title="KI-Status-Report Backend",
    version=getattr(settings, "VERSION", "2025.10"),
    docs_url=os.getenv("DOCS_URL", "/docs"),
    redoc_url=os.getenv("REDOC_URL", "/redoc"),
    openapi_url=os.getenv("OPENAPI_URL", "/openapi.json"),
)

# ---- CORS ------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(allowed_origins) or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=600,
)

# ---- Security Headers ------------------------------------------------------
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            response = await call_next(request)
        except Exception as exc:  # ensure we still set headers on errors
            LOG.error("Unhandled exception", exc_info=exc)
            response = JSONResponse({"detail": "internal server error"}, status_code=500)

        headers = MutableHeaders(response.headers)
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "no-referrer")
        headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        # Conservative CSP that is safe for APIs (adjust if you serve HTML)
        headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        # Only set HSTS on HTTPS deployments
        if (request.url.scheme or "").lower() == "https":
            headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload")
        return response

app.add_middleware(SecurityHeadersMiddleware)

# ----------------------------------------------------------------------------
# Utilities
# ----------------------------------------------------------------------------
def _feature_flags() -> Dict[str, bool]:
    return {
        "eu_host_check": True,
        "idempotency": True,
        "quality": True,
    }

def _bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).lower() in {"1", "true", "yes", "on"}

# ----------------------------------------------------------------------------
# Health Check
# ----------------------------------------------------------------------------
@app.get("/healthz", tags=["system"])
async def healthz() -> Dict[str, Any]:
    return {
        "ok": True,
        "time": datetime.now(timezone.utc).isoformat(),
        "env": getattr(settings, "ENV", "production"),
        "version": getattr(settings, "VERSION", "2025.10"),
        "features": _feature_flags(),
        "queue_enabled": _bool(getattr(settings, "QUEUE_ENABLED", False)),
        "pdf_service": bool(getattr(settings, "PDF_SERVICE_URL", None)),
        "status": "ok",
    }

# ----------------------------------------------------------------------------
# Admin authentication helpers
# ----------------------------------------------------------------------------
def _extract_bearer_token(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization") or request.headers.get("authorization")
    if not auth:
        return None
    parts = auth.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None

def verify_admin(request: Request) -> None:
    # 1) Allow X-Admin-Key for operational checks during tests
    admin_key_env = getattr(settings, "ADMIN_API_KEY", None)
    if admin_key_env:
        key_hdr = request.headers.get("X-Admin-Key")
        if key_hdr and key_hdr == admin_key_env:
            return  # ok

    # 2) Fall back to JWT Bearer
    token = _extract_bearer_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing credentials")

    if jwt is None:
        raise HTTPException(status_code=500, detail="JWT subsystem not available")

    try:
        jwt.decode(
            token,
            getattr(settings, "JWT_SECRET", "dev-secret-change-me"),
            algorithms=[getattr(settings, "JWT_ALG", "HS256")],
            options={"verify_aud": False},
        )
    except ExpiredSignatureError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired") from e
    except JWTError as e:  # <- explicitly imported to avoid UnboundLocalError
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from e

# ----------------------------------------------------------------------------
# Admin status page (JSON)
# ----------------------------------------------------------------------------
@app.get("/admin/status", tags=["admin"])
async def admin_status(request: Request, _: None = Depends(verify_admin)) -> Dict[str, Any]:
    # Keep it simple and side-effect-free (suitable for Railway health checks)
    info = {
        "ok": True,
        "time": datetime.now(timezone.utc).isoformat(),
        "env": getattr(settings, "ENV", "production"),
        "version": getattr(settings, "VERSION", "2025.10"),
        "queue": {
            "enabled": _bool(getattr(settings, "QUEUE_ENABLED", False)),
            "redis_url": getattr(settings, "REDIS_URL", None) is not None,
        },
        "pdf_service": bool(getattr(settings, "PDF_SERVICE_URL", None)),
        "features": _feature_flags(),
    }
    return info

# ----------------------------------------------------------------------------
# Optional: diagnostic echo (no auth, safe to leave in test)
# ----------------------------------------------------------------------------
@app.get("/diag", tags=["system"])
async def diag(request: Request) -> Dict[str, Any]:
    return {
        "client": request.client.host if request.client else None,
        "headers_sample": {k: request.headers.get(k) for k in ["user-agent", "x-forwarded-for", "x-request-id"]},
    }

# ----------------------------------------------------------------------------
# Router auto-discovery (defensive)
# ----------------------------------------------------------------------------
def _include_optional_router(module_path: str, prefix: Optional[str] = None) -> None:
    try:
        mod = __import__(module_path, fromlist=["router"])
        router = getattr(mod, "router", None)
        if router is not None:
            app.include_router(router, prefix=prefix or "")
            LOG.info("Included %s", module_path)
        else:
            LOG.warning("Module %s has no 'router'", module_path)
    except Exception as exc:
        LOG.warning("Optional router %s could not be imported: %s", module_path, exc)

# Include known project routers if they exist
for mod in (
    "routes.briefing",
    "routes.feedback",
    "routes.reports",
    "routes.users",
    "routes.admin",
):
    _include_optional_router(mod)

# ----------------------------------------------------------------------------
# Root
# ----------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
async def root() -> Response:
    return PlainTextResponse("KI-Status-Report backend is running. See /healthz")

# ----------------------------------------------------------------------------
# Local dev entrypoint
# ----------------------------------------------------------------------------
if __name__ == "__main__":  # pragma: no cover
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8080")), reload=False)
