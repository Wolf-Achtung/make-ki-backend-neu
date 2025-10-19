from __future__ import annotations

from fastapi import APIRouter
from ..settings import settings
from ..models import HealthResponse

router = APIRouter()

@router.get("/healthz", response_model=HealthResponse, tags=["ops"])
def healthz() -> HealthResponse:
    return HealthResponse(
        env=settings.ENV,
        version=settings.VERSION,
        queue_enabled=bool(settings.QUEUE_ENABLED),
        pdf_service=bool(settings.PDF_SERVICE_URL),
    )
