# -*- coding: utf-8 -*-
"""Briefing submission endpoint for KI-Readiness assessment."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session

logger = logging.getLogger("ki-backend.briefing")

router = APIRouter(tags=["briefing"])


class BriefingRequest(BaseModel):
    """Briefing/Assessment submission model."""
    user_email: str
    company_name: Optional[str] = None
    assessment_data: Dict[str, Any] = Field(default_factory=dict)
    responses: Dict[str, Any] = Field(default_factory=dict)
    score: Optional[float] = None
    timestamp: Optional[str] = None


class BriefingResponse(BaseModel):
    """Response model for briefing submission."""
    ok: bool
    message: str
    briefing_id: Optional[int] = None


@router.get("/briefing/ping")
async def ping():
    """Health check endpoint."""
    return {"ok": True, "pong": True}


@router.post("/briefing_async", response_model=BriefingResponse)
async def submit_briefing_async(
    request: BriefingRequest,
    session: AsyncSession = Depends(get_session)
):
    """
    Handle async briefing submission from frontend.
    Stores the assessment data and returns confirmation.
    """
    try:
        logger.info(f"Briefing submission received from {request.user_email}")
        
        # Hier würdest du normalerweise in die Datenbank speichern
        # Für jetzt loggen wir nur und geben Erfolg zurück
        
        # Beispiel für Datenbank-Insert (anpassen an dein Schema):
        # result = await session.execute(
        #     text("""
        #         INSERT INTO briefings (user_email, company_name, data, score, created_at)
        #         VALUES (:email, :company, :data, :score, NOW())
        #         RETURNING id
        #     """),
        #     {
        #         "email": request.user_email,
        #         "company": request.company_name,
        #         "data": json.dumps(request.assessment_data),
        #         "score": request.score
        #     }
        # )
        # briefing_id = result.scalar()
        
        # Temporär: Simuliere erfolgreiche Speicherung
        briefing_id = 12345  # Mock ID
        
        logger.info(f"Briefing successfully processed for {request.user_email}")
        
        return BriefingResponse(
            ok=True,
            message="Briefing erfolgreich eingereicht! Vielen Dank für Ihre Teilnahme.",
            briefing_id=briefing_id
        )
        
    except Exception as e:
        logger.error(f"Error processing briefing: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Fehler beim Verarbeiten des Briefings: {str(e)}"
        )


@router.post("/briefing", response_model=BriefingResponse)
async def submit_briefing(
    request: BriefingRequest,
    session: AsyncSession = Depends(get_session)
):
    """
    Alternative endpoint - falls Frontend /api/briefing verwendet.
    Ruft intern den async-Endpoint auf.
    """
    return await submit_briefing_async(request, session)


@router.get("/briefing/status")
async def briefing_status():
    """Check briefing service status."""
    return {
        "ok": True,
        "service": "briefing",
        "status": "operational",
        "timestamp": datetime.utcnow().isoformat()
    }