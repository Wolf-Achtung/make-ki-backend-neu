# -*- coding: utf-8 -*-
"""Admin status endpoint with simple token protection."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_API_TOKEN = os.getenv("ADMIN_API_TOKEN", "").strip()

def _require_admin(
    x_admin_token: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
) -> None:
    token = None
    if x_admin_token:
        token = x_admin_token.strip()
    elif authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()

    if not ADMIN_API_TOKEN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin token not configured")
    if token != ADMIN_API_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


@router.get("/status", dependencies=[Depends(_require_admin)])
async def admin_status():
    return {
        "ok": True,
        "env": os.getenv("ENV", "production"),
        "version": os.getenv("VERSION", "2025.10"),
        "queue_enabled": bool(os.getenv("ENABLE_QUEUE") and os.getenv("REDIS_URL")),
        "pdf_service": bool(os.getenv("PDF_SERVICE_URL", "")),
        "time": datetime.now(timezone.utc).isoformat(),
    }
