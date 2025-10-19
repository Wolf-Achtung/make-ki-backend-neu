from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, status, Request
from passlib.context import CryptContext

from ..models import LoginRequest, LoginResponse
from ..security import create_token
from ..settings import settings

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
log = logging.getLogger("ki-backend")

router = APIRouter()

@router.get("/login", tags=["auth"])
def login_get_info():
    # Give a helpful hint when someone hits the login route in a browser
    return {"detail": "Use POST /api/login"}

def _env_login(email: str, password: str) -> bool:
    if settings.BASIC_AUTH_USER and settings.BASIC_AUTH_PASSWORD:
        if email.lower() == settings.BASIC_AUTH_USER.lower() and password == settings.BASIC_AUTH_PASSWORD:
            return True
    # Optional demo logins
    if settings.DEMO_LOGIN_EMAILS and email.lower() in [e.lower() for e in settings.DEMO_LOGIN_EMAILS]:
        return True
    return False

@router.post("/login", response_model=LoginResponse, tags=["auth"])
def login(req: LoginRequest, request: Request) -> LoginResponse:
    """
    Flexible login supporting three modes:
    - AUTH_MODE=env (default): check BASIC_AUTH_USER/BASIC_AUTH_PASSWORD or DEMO_LOGIN_EMAILS
    - AUTH_MODE=db: try a very generic lookup against a 'users' table (email column, password or password_hash)
    - AUTH_MODE=demo: any email in DEMO_LOGIN_EMAILS passes
    """
    email = req.email.lower().strip()
    password = req.password

    if settings.AUTH_MODE in {"env", "demo"}:
        if _env_login(email, password):
            token = create_token(email, role="admin")  # invited testers act as admin for now
            return LoginResponse(access_token=token, expires_in=settings.JWT_EXPIRE_SECONDS)
        if settings.AUTH_MODE == "env":
            # fall through to db if configured
            pass
        elif settings.AUTH_MODE == "demo":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    # Optional DB-based auth (best-effort, schema-agnostic)
    if settings.DATABASE_URL:
        try:
            # lazy import to keep startup fast
            import psycopg
            with psycopg.connect(settings.DATABASE_URL, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT password, password_hash FROM users WHERE lower(email)=lower(%s) LIMIT 1", (email,))
                    row = cur.fetchone()
                    if not row:
                        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
                    pw_plain, pw_hash = row
                    ok = False
                    if pw_hash:
                        ok = pwd.verify(password, pw_hash)
                    if not ok and pw_plain:
                        ok = (password == pw_plain)
                    if not ok:
                        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        except HTTPException:
            raise
        except Exception as ex:  # pragma: no cover - operational visibility
            log.exception("DB login check failed: %s", ex)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth backend unavailable")

        token = create_token(email, role="admin")
        return LoginResponse(access_token=token, expires_in=settings.JWT_EXPIRE_SECONDS)

    # If we reach here, no method succeeded
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
