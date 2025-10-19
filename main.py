#!/usr/bin/env python3
"""
KI-Status-Report Backend – Gold-Standard+ main.py
-------------------------------------------------
- Saubere App-Initialisierung
- Sichere CORS- und Security-Header-Middleware
- Robuste Router-Auto-Discovery (routes.* mit APIRouter)
- /healthz, /diag, /admin/status mit optionalem JWT-Schutz
- Fallbacks, wenn settings, Templates oder Redis fehlen
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
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Settings (robust mit Fallback)
# ---------------------------------------------------------------------------
try:
    from settings import settings, allowed_origins  # type: ignore
except Exception:  # pragma: no cover - Fallback für Deploy-Umgebungen
    class _FallbackSettings:
        PROJECT_NAME: str = os.getenv("PROJECT_NAME", "ki-backend")
        ENV: str = os.getenv("ENV", "prod")
        DEBUG: bool = os.getenv("DEBUG", "0") in {"1", "true", "True", "yes"}
        JWT_SECRET: str = os.getenv("JWT_SECRET", "change-me")
        JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
        ALLOWED_ORIGINS: List[str] = (
            os.getenv("ALLOWED_ORIGINS", "*").split(",")
        )
        REDIS_URL: Optional[str] = os.getenv("REDIS_URL")

    settings = _FallbackSettings()  # type: ignore
    allowed_origins = getattr(settings, "ALLOWED_ORIGINS", ["*"])  # type: ignore

# ---------------------------------------------------------------------------
# JWT (robust import, sauberer Fehlerfall)
# ---------------------------------------------------------------------------
try:
    from jose import JWTError, jwt  # type: ignore
except Exception:  # pragma: no cover - falls jose fehlt
    class JWTError(Exception):
        pass

    jwt = None  # type: ignore

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("ki-backend")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="KI-Status-Report Backend",
    version=os.getenv("APP_VERSION", "2025.10.19"),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if allowed_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Security-Header Middleware – robust gegen Stream-Abbrüche (anyio.EndOfStream)
# ---------------------------------------------------------------------------
@app.middleware("http")
async def security_headers(request: Request, call_next):
    try:
        response: Response = await call_next(request)
    except Exception:  # keine Unbound-Exceptions nach außen
        logger.exception("Unhandled exception")
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

    # Sichere Defaults (können via CSP env überschrieben werden)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-XSS-Protection", "1; mode=block")
    default_csp = (
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline';"
    )
    response.headers.setdefault("Content-Security-Policy", os.getenv("CSP", default_csp))
    return response

# ---------------------------------------------------------------------------
# Templates (optional)
# ---------------------------------------------------------------------------
templates: Optional[Any] = None
TEMPLATES_DIR = os.getenv("TEMPLATES_DIR", "templates")
if os.path.isdir(TEMPLATES_DIR):
    try:
        from fastapi.templating import Jinja2Templates  # noqa
        templates = Jinja2Templates(directory=TEMPLATES_DIR)  # type: ignore
    except Exception:
        templates = None

# ---------------------------------------------------------------------------
# Router Auto-Discovery (routes.* -> APIRouter mit Namen "router")
# ---------------------------------------------------------------------------
def include_all_routers(app: FastAPI) -> List[str]:
    included: List[str] = []
    with contextlib.suppress(Exception):
        import routes  # type: ignore
        package = routes
        for module in pkgutil.iter_modules(package.__path__, package.__name__ + "."):
            try:
                mod = importlib.import_module(module.name)
                router = getattr(mod, "router", None)
                if router:
                    app.include_router(router)
                    included.append(module.name)
            except Exception:
                logger.exception("Failed to include router %s", module.name)
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
# Utility: Token aus Request holen + dekodieren
# ---------------------------------------------------------------------------
def _get_bearer_token(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth.split(" ", 1)[1].strip()
    token = request.query_params.get("token")
    return token

def _decode_token_or_401(token: Optional[str]) -> Dict[str, Any]:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    if jwt is None:
        raise HTTPException(status_code=500, detail="JWT library not installed")
    secret = getattr(settings, "JWT_SECRET", None) or os.getenv("JWT_SECRET")
    algo = getattr(settings, "JWT_ALGORITHM", None) or os.getenv("JWT_ALGORITHM", "HS256")
    try:
        return jwt.decode(token, secret, algorithms=[algo])  # type: ignore[arg-type]
    except JWTError as exc:  # noqa: F405 - aus jose import
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
        k: ("***" if any(x in k for x in ("KEY", "SECRET", "TOKEN", "PASSWORD")) else v)
        for k, v in os.environ.items()
    }
    return {"version": app.version, "env": getattr(settings, "ENV", "prod"), "env_vars": safe_env}

@app.get("/admin/status", response_class=HTMLResponse, tags=["ops"])
async def admin_status(request: Request):
    # Auth: In DEBUG optional, sonst Pflicht
    debug = bool(getattr(settings, "DEBUG", False))
    if not debug:
        _decode_token_or_401(_get_bearer_token(request))

    data: Dict[str, Any] = {
        "version": app.version,
        "environment": getattr(settings, "ENV", "prod"),
        "routers": included_modules,
        "features": {"templates": bool(templates)},
        "redis": None,
    }

    # Redis-Verbindung prüfen, wenn konfiguriert
    redis_url = getattr(settings, "REDIS_URL", None) or os.getenv("REDIS_URL")
    if redis_url:
        try:
            import redis  # noqa
            r = redis.Redis.from_url(redis_url, decode_responses=True)  # type: ignore
            pong = r.ping()
            data["redis"] = {"url": redis_url.split("@")[-1], "ok": bool(pong)}
        except Exception as exc:  # pragma: no cover
            data["redis"] = {"url": redis_url.split("@")[-1], "ok": False, "error": str(exc)}

    if templates and os.path.exists(os.path.join(TEMPLATES_DIR, "admin_status.html")):
        # HTML-Template vorhanden
        from fastapi.templating import Jinja2Templates  # noqa
        return templates.TemplateResponse("admin_status.html", {"request": request, "data": data})

    # JSON-Fallback
    return JSONResponse(data)

# Root-Fallback (hilfreich in Testphase)
@app.get("/", include_in_schema=False)
async def root() -> Dict[str, str]:
    return {"status": "ok", "service": "ki-backend", "version": app.version}