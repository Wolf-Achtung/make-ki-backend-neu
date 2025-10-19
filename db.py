# -*- coding: utf-8 -*-
from __future__ import annotations
import contextlib
from typing import Iterator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from settings import settings
from models import Base

_engine = None
_SessionLocal = None

def _build_engine():
    global _engine, _SessionLocal
    if not settings.DATABASE_URL:
        # Allow to start without DB during tests; use in-memory SQLite
        _engine = create_engine("sqlite+pysqlite:///:memory:", echo=False, future=True)
    else:
        _engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, future=True)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)

def init_db() -> None:
    if not _engine:
        _build_engine()
    Base.metadata.create_all(bind=_engine)

@contextlib.contextmanager
def get_session() -> Iterator:
    if not _SessionLocal:
        _build_engine()
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
