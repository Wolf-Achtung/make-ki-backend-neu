from __future__ import annotations

import time
from typing import Optional

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .settings import settings

bearer = HTTPBearer(auto_error=False)

def create_token(sub: str, role: str = "user", expires_in: int | None = None) -> str:
    exp = int(time.time()) + int(expires_in or settings.JWT_EXPIRE_SECONDS)
    payload = {"sub": sub, "role": role, "exp": exp, "iss": settings.APP_NAME}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)

def verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

def admin_required(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
) -> dict:
    # Accept either Bearer JWT or plain X-Admin-Token header for operational checks
    if x_admin_token and settings.ADMIN_TOKEN and x_admin_token == settings.ADMIN_TOKEN:
        return {"sub": "admin", "role": "admin", "method": "x-admin-token"}

    if creds and creds.scheme.lower() == "bearer":
        claims = verify_token(creds.credentials)
        if claims.get("role") in {"admin", "superuser"}:
            return claims

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
