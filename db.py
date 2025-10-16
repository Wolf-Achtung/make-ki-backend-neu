# filename: db.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from contextlib import contextmanager
from typing import Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from settings import settings

engine = None
SessionLocal: Optional[sessionmaker] = None

def _normalize_url(url: str) -> str:
    """Ensure SQLAlchemy uses psycopg v3 driver.
    Railway often provides URLs like 'postgresql://...'
    SQLAlchemy then imports psycopg2 unless we force '+psycopg'.
    """
    if not url:
        return url
    if url.startswith("postgres://"):
        # old Heroku-style scheme
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+" not in url.split("://", 1)[0]:
        # inject modern driver
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url

def init_db() -> None:
    global engine, SessionLocal
    if not settings.DATABASE_URL:
        raise RuntimeError("DATABASE_URL not configured")
    dsn = _normalize_url(settings.DATABASE_URL)
    engine = create_engine(dsn, pool_pre_ping=True, future=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    # create tables
    from models import Base  # noqa
    Base.metadata.create_all(engine)

@contextmanager
def get_session() -> Session:
    if SessionLocal is None:
        raise RuntimeError("DB not initialized - call init_db() first")
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
