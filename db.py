# -*- coding: utf-8 -*-
"""Database utilities (async SQLAlchemy)."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

logger = logging.getLogger("ki-backend.db")

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

_engine: Optional[AsyncEngine] = None
_sessionmaker: Optional[async_sessionmaker] = None


def _normalize_url(url: str) -> str:
    if not url:
        return url
    # Railway often provides postgres:// scheme; SQLAlchemy requires postgresql+asyncpg:// for async.
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _build_engine() -> AsyncEngine:
    url = _normalize_url(DATABASE_URL)
    if not url:
        raise RuntimeError("DATABASE_URL is not set.")
    engine = create_async_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    return engine


def _ensure_engine() -> None:
    global _engine, _sessionmaker
    if _engine is None:
        _engine = _build_engine()
        _sessionmaker = async_sessionmaker(bind=_engine, expire_on_commit=False)
        logger.info("Async DB engine created.")


async def get_session() -> AsyncSession:
    """FastAPI dependency to provide a session and close it afterwards."""
    _ensure_engine()
    assert _sessionmaker is not None
    async with _sessionmaker() as session:
        yield session


async def fetch_user_by_email(session: AsyncSession, email: str) -> Optional[Dict[str, Any]]:
    """
    Fetch a user row by email (case-insensitive). Works with arbitrary user schemas.
    Assumes a table named `users` with at least a column `email` and some password column.
    """
    q = text("""
        SELECT * FROM users
        WHERE lower(email) = lower(:email)
        ORDER BY 1
        LIMIT 1
    """)
    res = await session.execute(q, {"email": email})
    mapping = res.mappings().first()
    return dict(mapping) if mapping else None
