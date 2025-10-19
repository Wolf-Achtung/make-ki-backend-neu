# -*- coding: utf-8 -*-
"""Minimal feedback endpoint.

Tries to insert into a table named `feedback` if present; otherwise, logs and returns success.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session

logger = logging.getLogger("ki-backend.feedback")

router = APIRouter(tags=["feedback"])


class FeedbackIn(BaseModel):
    email: Optional[EmailStr] = None
    message: str
    rating: Optional[int] = None


@router.post("/feedback")
async def submit_feedback(data: FeedbackIn, session: AsyncSession = Depends(get_session)):
    # Try to insert if possible. If it fails (schema mismatch), just log and acknowledge.
    try:
        q = text("""
            INSERT INTO feedback (email, message, rating, created_at)
            VALUES (:email, :message, :rating, :created_at)
        """)
        await session.execute(q, {
            "email": data.email,
            "message": data.message,
            "rating": data.rating,
            "created_at": datetime.now(timezone.utc),
        })
        await session.commit()
        logger.info("Stored feedback from %s", data.email or "anonymous")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Feedback insert skipped (schema mismatch or table missing): %s", exc)
    return {"ok": True}
