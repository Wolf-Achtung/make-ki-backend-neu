# filename: db.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from settings import settings

engine = None
SessionLocal = None

def init_db() -> None:
    global engine, SessionLocal
    if not settings.DATABASE_URL:
        raise RuntimeError("DATABASE_URL not configured")
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, future=True)
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
