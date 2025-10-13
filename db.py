# filename: backend/db.py
# -*- coding: utf-8 -*-
"""
SQLAlchemy Setup for Railway Postgres (psycopg3)
- Accepts DATABASE_URL / POSTGRES_URL / POSTGRESQL_URL / RAILWAY_DATABASE_URL
- Normalizes "postgres://" -> "postgresql+psycopg://"
- Provides get_session() dependency, engine_ok(), ensure_schema(), seed_from_env()
"""
from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .models import Base, User
from .security import hash_password

_engine = None
_SessionLocal = None
_effective_url = None

def _env_url() -> Optional[str]:
    for key in ("DATABASE_URL","POSTGRES_URL","POSTGRESQL_URL","RAILWAY_DATABASE_URL"):
        val = os.getenv(key)
        if val:
            return val
    return None

def _normalize(url: str) -> str:
    url = url.strip()
    # fix scheme
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url.split("postgres://",1)[1]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url.split("postgresql://",1)[1]
    # add query defaults for SSL if not present (Railway usually sets them)
    return url

def _ensure():
    global _engine, _SessionLocal, _effective_url
    if _engine is None:
        raw = _env_url()
        if not raw:
            return
        url = _normalize(raw)
        _engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10, future=True)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
        _effective_url = url

def engine_ok() -> bool:
    _ensure()
    return _engine is not None

def db_url_effective(mask: bool = False) -> str:
    _ensure()
    if not _effective_url:
        return ""
    if not mask:
        return _effective_url
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", _effective_url)

@contextmanager
def get_session() -> Iterator:
    _ensure()
    if _SessionLocal is None:
        raise RuntimeError("DATABASE_URL not configured")
    db = _SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def ensure_schema() -> None:
    _ensure()
    if _engine is None:
        return
    Base.metadata.create_all(bind=_engine)

def seed_from_env() -> None:
    """
    ADMIN_SEED_USERS='[{"email":"user@example.com","password":"secret"}]'
    """
    _ensure()
    if _engine is None:
        return
    raw = os.getenv("ADMIN_SEED_USERS","").strip()
    if not raw:
        return
    try:
        data = json.loads(raw)
    except Exception:
        return
    if not isinstance(data, list):
        return
    with get_session() as db:
        for item in data:
            try:
                email = str(item.get("email","")).strip().lower()
                pwd = str(item.get("password",""))
                if not email or not pwd:
                    continue
                if db.query(User).filter(User.email==email).first():
                    continue
                u = User(email=email, password_hash=hash_password(pwd))
                db.add(u)
            except Exception:
                continue
