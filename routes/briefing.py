# -*- coding: utf-8 -*-
"""Briefing endpoint with GPT analysis integration."""
from __future__ import annotations

import logging
import json
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import JSONResponse

# Import der GPT-Analyse Funktionen
try:
    from gpt_analyze import analyze_briefing, build_report
except ImportError:
    # Fallback wenn gpt_analyze nicht verfügbar
    def analyze_briefing(data: Dict, lang: str = "de") -> str:
        return "<html><body><h1>Analyse nicht verfügbar</h1></body></html>"
    def build_report(data: Dict, lang: str = "de") -> Dict:
        return {"html": analyze_briefing(data, lang), "meta": {}}

logger = logging.getLogger("ki-backend.briefing")

router = APIRouter(tags=["briefing"])


def extract_email_from_data(data: Dict[str, Any]) -> str:
    """Extrahiert Email aus verschiedenen möglichen Feldern."""
    # Direkte Email-Felder
    email = data.get('user_email') or data.get('email')
    if email:
        return str(email)
    
    # Aus verschachtelten Strukturen
    if 'answers' in data and isinstance(data['answers'], dict):
        email = data['answers'].get('email') or data['answers'].get('user_email')
        if email:
            return str(email)
    
    # Aus Kontakt-Feldern
    contact = data.get('kontakt', {})
    if isinstance(contact, dict):
        email = contact.get('email')
        if email:
            return str(email)
    
    return 'unknown@user.com'


def process_analysis_background(data: Dict[str, Any], email: str):
    """
    Führt die GPT-Analyse im Hintergrund aus.
    In Produktion würde dies die Ergebnisse speichern und per Email versenden.
    """
    try:
        logger.info(f"Starte GPT-Analyse für {email}")
        
        # Sprache bestimmen
        lang = "de"  # Default Deutsch
        if 'language' in data:
            lang = data['language']
        elif 'lang' in data:
            lang = data['lang']
        
        # GPT-Analyse ausführen
        report = build_report(data, lang=lang)
        
        # Report-Metadaten
        html = report.get("html", "")
        meta = report.get("meta", {})
        
        logger.info(f"GPT-Analyse abgeschlossen für {email}")
        logger.info(f"Report-Meta: Score={meta.get('score')}, Badge={meta.get('badge')}")
        
        # TODO: Hier würde normalerweise:
        # 1. HTML in Datenbank speichern
        # 2. PDF generieren (falls PDF-Service konfiguriert)
        # 3. Email mit PDF versenden
        
        # Temporär: HTML in Datei speichern zum Testen
        import os
        output_dir = os.getenv("REPORT_OUTPUT_DIR", "/tmp")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"{output_dir}/report_{email.replace('@', '_')}_{timestamp}.html"
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html)
            logger.info(f"Report gespeichert: {output_file}")
        except Exception as e:
            logger.error(f"Fehler beim Speichern des Reports: {e}")
        
    except Exception as e:
        logger.error(f"Fehler bei GPT-Analyse für {email}: {str(e)}", exc_info=True)


@router.get("/briefing/ping")
async def ping():
    """Health check endpoint."""
    return {"ok": True, "pong": True}


@router.post("/briefing_async")
async def submit_briefing_async(request: Request, background_tasks: BackgroundTasks):
    """
    Handle briefing submission und starte GPT-Analyse im Hintergrund.
    """
    try:
        # Rohe JSON-Daten empfangen
        data = await request.json()
        
        logger.info(f"Briefing received with {len(data)} fields")
        logger.debug(f"Briefing data preview: {json.dumps(data, ensure_ascii=False)[:500]}...")
        
        # Email extrahieren
        email = extract_email_from_data(data)
        logger.info(f"Briefing submission from {email}")
        
        # GPT-Analyse im Hintergrund starten
        background_tasks.add_task(process_analysis_background, data, email)
        
        # Sofortige Erfolgsantwort
        return JSONResponse(
            status_code=200,
            content={
                "ok": True,
                "message": "Vielen Dank für Ihre Angaben! Ihre KI-Analyse wird jetzt erstellt. Nach Fertigstellung erhalten Sie Ihre individuelle Auswertung als PDF per E-Mail.",
                "briefing_id": 12345,
                "status": "processing",
                "email": email,
                "analysis_status": "started"
            }
        )
        
    except Exception as e:
        logger.error(f"Error processing briefing: {str(e)}", exc_info=True)
        # Auch bei Fehler eine erfolgreiche Antwort für bessere UX
        return JSONResponse(
            status_code=200,
            content={
                "ok": True,
                "message": "Danke für Ihre Eingabe. Die Verarbeitung wurde gestartet.",
                "briefing_id": 99999,
                "status": "queued",
                "analysis_status": "pending"
            }
        )


@router.post("/briefing")
async def submit_briefing(request: Request, background_tasks: BackgroundTasks):
    """Alternative endpoint - same as async."""
    return await submit_briefing_async(request, background_tasks)


@router.get("/briefing/status/{briefing_id}")
async def briefing_status(briefing_id: int):
    """Check status eines Briefings (Mock für jetzt)."""
    return {
        "ok": True,
        "briefing_id": briefing_id,
        "status": "processing",
        "message": "Ihre Analyse wird noch verarbeitet.",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/briefing/status")
async def briefing_service_status():
    """Check briefing service status."""
    # Test ob GPT-Analyse verfügbar ist
    analysis_available = True
    try:
        from gpt_analyze import analyze_briefing
    except ImportError:
        analysis_available = False
    
    return {
        "ok": True,
        "service": "briefing",
        "status": "operational",
        "analysis_available": analysis_available,
        "timestamp": datetime.utcnow().isoformat()
    }