from __future__ import annotations

import socket
from fastapi import APIRouter, Depends
from ..security import admin_required
from ..settings import settings

router = APIRouter()

@router.get("/admin/status", tags=["ops"])
def admin_status(_claims: dict = Depends(admin_required)) -> dict:
    # Return a concise operational snapshot usable by the frontend and humans
    return {
        "ok": True,
        "env": settings.ENV,
        "version": settings.VERSION,
        "host": socket.gethostname(),
        "queue": {
            "enabled": settings.QUEUE_ENABLED,
            "redis_url_set": bool(settings.REDIS_URL),
        },
        "pdf_service": {
            "configured": bool(settings.PDF_SERVICE_URL),
            "timeout_ms": settings.PDF_TIMEOUT,
        },
        "features": {
            "eu_host_check": True,
            "idempotency": True,
            "quality": True
        }
    }
