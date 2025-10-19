# -*- coding: utf-8 -*-
"""Login endpoint backed by PostgreSQL (async)."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session, fetch_user_by_email
from security import create_access_token, verify_password

logger = logging.getLogger("ki-backend.auth")

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    ok: bool
    token: str
    user: dict


@router.get("/login")
async def login_get_hint():
    # Helpful message when someone tries a GET
    raise HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, detail="Use POST /api/login")


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, session: AsyncSession = Depends(get_session)):
    """
    Authenticate a user:
    - Look up the row in `users` by email
    - Verify password (bcrypt/argon2 or plaintext fallback)
    - Return a signed token and a tiny user profile
    """
    user = await fetch_user_by_email(session, req.email)
    if not user:
        logger.info("Login failed for %s: user not found", req.email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Accept several possible column names for the password
    for candidate in ("password_hash", "hashed_password", "password", "pwd"):
        if candidate in user and user[candidate]:
            stored = str(user[candidate])
            break
    else:
        logger.warning("Login failed for %s: password column not found in users table", req.email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not verify_password(req.password, stored):
        logger.info("Login failed for %s: invalid password", req.email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token(user.get("email", ""))

    profile = {
        "id": user.get("id"),
        "email": user.get("email"),
        "role": user.get("role") or user.get("user_role"),
        "name": user.get("name") or user.get("full_name"),
        "active": bool(user.get("is_active", True)),
    }

    return LoginResponse(ok=True, token=token, user=profile)
