from __future__ import annotations

from fastapi import APIRouter
from ..settings import settings

router = APIRouter()

@router.get("/diag", tags=["ops"])
def diag() -> dict:
    return {
        "ok": True,
        "settings": {
            "APP_NAME": settings.APP_NAME,
            "ENV": settings.ENV,
            "VERSION": settings.VERSION,
            "QUEUE_ENABLED": settings.QUEUE_ENABLED,
            "REDIS_URL_SET": bool(settings.REDIS_URL),
            "PDF_SERVICE_URL_SET": bool(settings.PDF_SERVICE_URL),
            "PDF_TIMEOUT": settings.PDF_TIMEOUT,
            "DEBUG": settings.DEBUG,
        },
    }
