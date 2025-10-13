# filename: backend/security.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import bcrypt

def hash_password(password: str) -> str:
    if not password:
        raise ValueError("empty password")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")

def verify_password(password: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False
