# filename: routes/auth_login.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import text
from jose import jwt
from typing import Optional, Dict, Any
import bcrypt

from settings import settings
from db import get_session

router = APIRouter(tags=["auth"])

class LoginPayload(BaseModel):
    email: EmailStr
    password: str

def _extract_password_and_role(row: Dict[str, Any]) -> tuple[Optional[str], str, Optional[str]]:
    # Try to find a password hash column dynamically
    pwd_keys = [k for k in row.keys() if "pass" in k.lower()]
    pwd_val: Optional[str] = None
    for k in pwd_keys:
        v = row.get(k)
        if v and isinstance(v, (str, bytes)):
            pwd_val = v.decode("utf-8") if isinstance(v, (bytes, bytearray)) else v
            break
    role = "admin" if bool(row.get("is_admin")) else (row.get("role") or "user")
    name = row.get("name") or row.get("fullname") or None
    return pwd_val, str(role), name

def _verify_password(plain: str, hashed: str) -> bool:
    try:
        hb = hashed.encode("utf-8") if isinstance(hashed, str) else hashed
        return bcrypt.checkpw(plain.encode("utf-8"), hb)
    except Exception:
        return False

@router.post("/api/login")
def login(payload: LoginPayload):
    email_norm = payload.email.lower()
    with get_session() as s:
        row = s.execute(text("SELECT * FROM users WHERE LOWER(email)=:email LIMIT 1"), {"email": email_norm}).mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    pwd_hash, role, name = _extract_password_and_role(row)
    if not pwd_hash or not _verify_password(payload.password, pwd_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    token = jwt.encode({"email": email_norm, "role": role, "name": name}, settings.JWT_SECRET, algorithm="HS256")
    return {"access_token": token, "token_type": "Bearer", "user": {"email": email_norm, "role": role, "name": name}}
