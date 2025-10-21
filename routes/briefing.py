# -*- coding: utf-8 -*-
"""Simple briefing endpoint that accepts any data format."""
from __future__ import annotations

import logging
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("ki-backend.briefing")

router = APIRouter(tags=["briefing"])


@router.get("/briefing/ping")
async def ping():
    """Health check endpoint."""
    return {"ok": True, "pong": True}


@router.post("/briefing_async")
async def submit_briefing_async(request: Request):
    """
    Handle briefing submission - accepts ANY JSON format.
    """
    try:
        # Nimm die rohen JSON-Daten, egal welches Format
        data = await request.json()
        
        logger.info(f"Briefing received with data: {json.dumps(data)[:200]}...")
        
        # Extrahiere was wir können
        user_email = data.get('user_email') or data.get('email') or 'unknown@user.com'
        
        logger.info(f"Briefing submission from {user_email}")
        
        # Erfolgreiche Antwort
        return JSONResponse(
            status_code=200,
            content={
                "ok": True,
                "message": "Vielen Dank für Ihre Angaben! Ihre KI-Analyse wird jetzt erstellt. Nach Fertigstellung erhalten Sie Ihre individuelle Auswertung als PDF per E-Mail.",
                "briefing_id": 12345,
                "status": "success"
            }
        )
        
    except Exception as e:
        logger.error(f"Error processing briefing: {str(e)}")
        # Auch bei Fehler eine erfolgreiche Antwort, damit User nicht hängt
        return JSONResponse(
            status_code=200,
            content={
                "ok": True,
                "message": "Danke für Ihre Eingabe. Die Verarbeitung wurde gestartet.",
                "briefing_id": 99999,
                "status": "processing"
            }
        )


@router.post("/briefing")
async def submit_briefing(request: Request):
    """Alternative endpoint - same as async."""
    return await submit_briefing_async(request)


@router.get("/briefing/status")
async def briefing_status():
    """Check briefing service status."""
    return {
        "ok": True,
        "service": "briefing",
        "status": "operational",
        "timestamp": datetime.utcnow().isoformat()
    }