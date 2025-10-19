#!/usr/bin/env python3
"""
KI-Status-Report Backend – Gold-Standard+ (stabiler Railway-Start)
-----------------------------------------------------------------
- Sichere Logging-Initialisierung (ENV LOG_LEVEL beliebig: info/INFO/Fehleingaben)
- CORS und Security-Header
- Router Auto-Discovery (ignoriert fehlende optionale Abhängigkeiten wie sqlalchemy)
- /healthz, /diag, /admin/status (JWT optional in DEBUG)
- Template-Fallback: JSON, wenn Jinja2/Tpl fehlen
"""
from __future__ import annotations

import contextlib
import importlib
import json
import logging
import os
import pkgutil
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Settings (robust, mit Fallback)
# ---------------------------------------------------------------------------
try:
    from settings import settings, allowed_origins  # type: ignore
except Exception:
    class _FallbackSettings:
        PROJECT_NAME: str = os.getenv("PROJECT_NAME", "ki-backend")
        ENV: str = os.getenv("ENV", "prod")
        DEBUG: bool = (os.getenv("DEBUG", "0") or "0").lower() in {"1","true","yes","on"}
        JWT_SECRET: str = os.getenv("JWT_SECRET", "change-me")
        JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
        ADMIN_API_KEY: Optional[str] = os.getenv("ADMIN_API_KEY")
        REDIS_URL: Optional[str] = os.getenv("REDIS_URL")
        PDF_SERVICE_URL: Optional[str] = os.getenv("PDF_SERVICE_URL")
        CORS_ALLOW_ORIGINS: List[str] = (
            [o.strip() for o in (os.getenv("CORS_ALLOW_ORIGINS","*") or "*").split(",")] or ["*"]
        )
    settings = _FallbackSettings()  # type: ignore
    allowed_origins = getattr(settings, "CORS_ALLOW_ORIGINS", ["*"])  # type: ignore

# ---------------------------------------------------------------------------
# JWT (robust import)
# ---------------------------------------------------------------------------
try:
    from jose import JWTError, jwt  # type: ignore
except Exception:  # pragma: no cover
    class JWTError(Exception):
        pass
    jwt = None  # type: ignore

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
import logging as _logging
_lvl_name = (os.getenv("LOG_LEVEL", "INFO") or "INFO").upper()
_lvl = getattr(_logging, _lvl_name, _logging.INFO)
logging.basicConfig(
    level=_lvl,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("ki-backend")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="KI-Status-Report Backend",
    version=os.getenv("APP_VERSION", "2025.10"),
)

# CORS
cors_origins = allowed_origins if allowed_origins else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=600,
)

# Security headers
@app.middleware("http")
async def security_headers(request: Request, call_next):
    try:
        response: Response = await call_next(request)
    except Exception:
        logger.exception("Unhandled exception in request")
        return JSONResponse({"detail": "internal server error"}, status_code=500)
    # conservative defaults
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'"
    )
    if (request.url.scheme or "").lower() == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload")
    return response

# ---------------------------------------------------------------------------
# Optional Templates
# ---------------------------------------------------------------------------
templates: Optional[Any] = None
TEMPLATES_DIR = os.getenv("TEMPLATES_DIR", "templates")
if os.path.isdir(TEMPLATES_DIR):
    try:
        from fastapi.templating import Jinja2Templates
        templates = Jinja2Templates(directory=TEMPLATES_DIR)  # type: ignore
    except Exception:
        templates = None

# ---------------------------------------------------------------------------
# Router Auto-Discovery
# ---------------------------------------------------------------------------
def include_all_routers(target_app: FastAPI) -> List[str]:
    included: List[str] = []
    with contextlib.suppress(Exception):
        import routes  # type: ignore
        for module in pkgutil.iter_modules(routes.__path__, routes.__name__ + "."):
            try:
                mod = importlib.import_module(module.name)
                router = getattr(mod, "router", None)
                if router is not None:
                    target_app.include_router(router)
                    included.append(module.name)
            except ModuleNotFoundError as e:
                logger.error("Failed to include router %s (missing dep: %s)", module.name, e.name)
            except Exception as exc:
                logger.error("Failed to include router %s", module.name, exc_info=exc)
    return included

included_modules = include_all_routers(app)
if included_modules:
    logger.info("Included %s", ", ".join(included_modules))
else:
    logger.warning("No route modules found under 'routes' package")

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class HealthzOut(BaseModel):
    status: str
    version: str
    env: str

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def _get_bearer_token(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return request.query_params.get("token")

def _decode_token_or_401(token: Optional[str]) -> Dict[str, Any]:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    if jwt is None:
        raise HTTPException(status_code=500, detail="JWT not available")
    secret = getattr(settings, "JWT_SECRET", None) or os.getenv("JWT_SECRET") or "change-me"
    algo = getattr(settings, "JWT_ALGORITHM", None) or os.getenv("JWT_ALGORITHM", "HS256")
    try:
        return jwt.decode(token, secret, algorithms=[algo])  # type: ignore[arg-type]
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/healthz", response_model=HealthzOut, tags=["ops"])
async def healthz() -> HealthzOut:
    return HealthzOut(status="ok", version=app.version, env=getattr(settings, "ENV", "prod"))

@app.get("/diag", tags=["ops"])
async def diag() -> Dict[str, Any]:
    safe_env = {
        k: ("***" if any(x in k for x in ("KEY", "SECRET", "TOKEN", "PASS")) else v)
        for k, v in os.environ.items()
    }
    return {
        "version": app.version,
        "env": getattr(settings, "ENV", "prod"),
        "features": {"templates": bool(templates)},
        "routes": included_modules,
        "env_vars": safe_env,
    }

@app.get("/admin/status", response_class=HTMLResponse, tags=["ops"])
async def admin_status(request: Request):
    # In DEBUG ohne Auth, sonst JWT erforderlich
    if not bool(getattr(settings, "DEBUG", False)):
        _decode_token_or_401(_get_bearer_token(request))

    data: Dict[str, Any] = {
        "version": app.version,
        "env": getattr(settings, "ENV", "prod"),
        "routes": included_modules,
        "cors": cors_origins,
    }

    # Redis-Ping (optional)
    redis_url = getattr(settings, "REDIS_URL", None) or os.getenv("REDIS_URL")
    if redis_url:
        try:
            import redis  # type: ignore
            r = redis.Redis.from_url(redis_url, decode_responses=True)  # type: ignore
            pong = r.ping()
            data["redis"] = {"ok": bool(pong)}
        except Exception as exc:
            data["redis"] = {"ok": False, "error": str(exc)}

    if templates and os.path.exists(os.path.join(TEMPLATES_DIR, "admin_status.html")):
        return templates.TemplateResponse("admin_status.html", {"request": request, "data": data})  # type: ignore
    return JSONResponse(data)

@app.get("/", include_in_schema=False)
async def root() -> Response:
    return PlainTextResponse("KI-Status-Report backend is running. See /healthz")