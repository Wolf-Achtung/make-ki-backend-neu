# -*- coding: utf-8 -*-
"""Tiny compatibility router; extend as needed."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["briefing"])

@router.get("/briefing/ping")
async def ping():
    return {"ok": True, "pong": True}
