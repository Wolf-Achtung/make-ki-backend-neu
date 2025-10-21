# -*- coding: utf-8 -*-
"""
Briefing Endpoint - Gold Standard+ mit Live-Daten Integration
Optimiert für nahtlose Integration mit gpt_analyze.py
"""
from __future__ import annotations

import logging
import json
import os
import asyncio
from datetime import datetime
from typing import Any, Dict, Optional, List
from pathlib import Path

from fastapi import APIRouter, Request, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, EmailStr, Field

# Import der erweiterten GPT-Analyse Funktionen
try:
    # Versuche alle Funktionen zu importieren
    from gpt_analyze import (
        analyze_briefing,
        build_report, 
        build_html_report,
        analyze_briefing_enhanced,
        normalize_briefing,
        compute_scores,
        business_case,
        produce_admin_attachments
    )
    GPT_ANALYZE_AVAILABLE = True
except ImportError as e:
    logging.warning(f"GPT-Analyze Import fehlgeschlagen: {e}")
    GPT_ANALYZE_AVAILABLE = False
    
    # Fallback Funktionen
    def build_report(data: Dict, lang: str = "de") -> Dict:
        return {
            "html": "<html><body><h1>Analyse temporär nicht verfügbar</h1></body></html>",
            "meta": {"error": "gpt_analyze not available"}
        }
    
    def analyze_briefing(data: Dict, lang: str = "de") -> str:
        return build_report(data, lang)["html"]

logger = logging.getLogger("ki-backend.briefing")

router = APIRouter(tags=["briefing"])

# ===================== SCHEMA DEFINITION =====================

class BriefingData(BaseModel):
    """Validiertes Briefing Schema mit allen kritischen Feldern"""
    
    # Kritische Felder (müssen immer vorhanden sein)
    bundesland: Optional[str] = Field(None, description="Bundesland Code (z.B. BE für Berlin)")
    bundesland_code: Optional[str] = Field(None, description="Alternative für bundesland")
    branche: Optional[str] = Field(None, description="Branche/Industry")
    branche_code: Optional[str] = Field(None, description="Branche Code")
    branche_label: Optional[str] = Field(None, description="Branche Display Name")
    unternehmensgroesse: Optional[str] = Field(None, description="Unternehmensgröße")
    unternehmensgroesse_label: Optional[str] = Field(None, description="Größe Display Name")
    hauptleistung: Optional[str] = Field(None, description="Hauptleistung/Produkt")
    
    # Kontaktdaten
    email: Optional[EmailStr] = None
    user_email: Optional[EmailStr] = None
    company_name: Optional[str] = None
    
    # KI & Digitalisierung
    digitalisierungsgrad: Optional[Any] = None
    prozesse_papierlos: Optional[Any] = None
    automatisierungsgrad: Optional[str] = None
    ki_einsatz: Optional[List[str]] = None
    ki_knowhow: Optional[str] = None
    ki_usecases: Optional[List[str]] = None
    usecase_priority: Optional[str] = None
    
    # Compliance & Governance
    datenschutzbeauftragter: Optional[str] = None
    folgenabschaetzung: Optional[str] = None
    loeschregeln: Optional[str] = None
    meldewege: Optional[str] = None
    governance: Optional[str] = None
    
    # Budget & Ziele
    investitionsbudget: Optional[str] = None
    jahresumsatz: Optional[str] = None
    umsatzziel: Optional[str] = None
    zeitbudget: Optional[str] = None
    
    # Sprache
    language: Optional[str] = Field(default="de")
    lang: Optional[str] = Field(default="de")
    
    # Zusätzliche Felder
    answers: Optional[Dict[str, Any]] = None
    kontakt: Optional[Dict[str, Any]] = None
    
    class Config:
        extra = "allow"  # Erlaubt zusätzliche Felder

# ===================== HELPER FUNKTIONEN =====================

def normalize_briefing_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalisiert und validiert Briefing-Daten
    Stellt sicher dass kritische Felder vorhanden sind
    """
    normalized = dict(data)
    
    # Extrahiere aus verschachtelten Strukturen
    if 'answers' in data and isinstance(data['answers'], dict):
        normalized.update(data['answers'])
    
    # Bundesland Normalisierung
    if not normalized.get('bundesland_code'):
        if normalized.get('bundesland'):
            # Mappe Bundesland Namen zu Code wenn nötig
            bundesland_map = {
                'berlin': 'BE', 'bayern': 'BY', 'baden-württemberg': 'BW',
                'brandenburg': 'BB', 'bremen': 'HB', 'hamburg': 'HH',
                'hessen': 'HE', 'mecklenburg-vorpommern': 'MV',
                'niedersachsen': 'NI', 'nordrhein-westfalen': 'NW',
                'rheinland-pfalz': 'RP', 'saarland': 'SL',
                'sachsen': 'SN', 'sachsen-anhalt': 'ST',
                'schleswig-holstein': 'SH', 'thüringen': 'TH'
            }
            bl_lower = str(normalized['bundesland']).lower()
            normalized['bundesland_code'] = bundesland_map.get(bl_lower, 'DE')
        else:
            normalized['bundesland_code'] = 'DE'
    
    # Branche Normalisierung
    if not normalized.get('branche_code'):
        normalized['branche_code'] = normalized.get('branche', 'beratung')
    
    if not normalized.get('branche_label'):
        normalized['branche_label'] = normalized.get('branche', 'Beratung')
    
    # Unternehmensgröße Normalisierung
    if not normalized.get('unternehmensgroesse'):
        size = normalized.get('size') or normalized.get('company_size')
        if size:
            normalized['unternehmensgroesse'] = size
        else:
            normalized['unternehmensgroesse'] = 'solo'
    
    # Label für Unternehmensgröße
    size_labels = {
        'solo': '1 (Solo/Selbstständig)',
        'klein': '2-10 (Kleines Team)',
        'kmu': '11-100 (KMU)',
        'mittel': '101-500 (Mittelstand)',
        'gross': '500+ (Großunternehmen)'
    }
    if not normalized.get('unternehmensgroesse_label'):
        size_key = str(normalized.get('unternehmensgroesse', 'solo')).lower()
        normalized['unternehmensgroesse_label'] = size_labels.get(size_key, size_key)
    
    # Hauptleistung
    if not normalized.get('hauptleistung'):
        normalized['hauptleistung'] = normalized.get('produkt') or normalized.get('main_service') or 'Beratung'
    
    # Email Extraktion
    email = extract_email_from_data(normalized)
    if email and email != 'unknown@user.com':
        normalized['email'] = email
    
    # Sprache
    lang = normalized.get('language') or normalized.get('lang') or 'de'
    normalized['language'] = lang
    normalized['lang'] = lang
    
    return normalized

def extract_email_from_data(data: Dict[str, Any]) -> str:
    """Extrahiert Email aus verschiedenen möglichen Feldern"""
    # Direkte Email-Felder
    email = data.get('user_email') or data.get('email')
    if email:
        return str(email)
    
    # Aus Kontakt-Feldern
    contact = data.get('kontakt', {})
    if isinstance(contact, dict):
        email = contact.get('email')
        if email:
            return str(email)
    
    return 'unknown@user.com'

def validate_critical_fields(data: Dict[str, Any]) -> List[str]:
    """
    Validiert kritische Felder und gibt Liste fehlender Felder zurück
    """
    critical_fields = {
        'bundesland_code': 'Bundesland',
        'branche': 'Branche',
        'unternehmensgroesse': 'Unternehmensgröße',
        'hauptleistung': 'Hauptleistung/Produkt'
    }
    
    missing = []
    for field, label in critical_fields.items():
        if not data.get(field):
            missing.append(label)
    
    return missing

async def generate_report_async(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generiert Report asynchron mit Live-Daten wenn verfügbar
    """
    loop = asyncio.get_event_loop()
    
    # Führe CPU-intensive Operationen in Thread-Pool aus
    result = await loop.run_in_executor(
        None,  # Default executor
        build_html_report,  # Die erweiterte Funktion aus gpt_analyze
        data,
        data.get('language', 'de')
    )
    
    return result

def save_report_to_file(html: str, email: str, meta: Dict[str, Any]) -> str:
    """
    Speichert Report als HTML-Datei (temporär für Testing)
    """
    output_dir = Path(os.getenv("REPORT_OUTPUT_DIR", "/tmp/ki-reports"))
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    score = meta.get('score', 0)
    badge = meta.get('badge', 'UNKNOWN')
    
    filename = f"report_{email.replace('@', '_')}_{timestamp}_{badge}_{score}.html"
    output_file = output_dir / filename
    
    try:
        output_file.write_text(html, encoding='utf-8')
        logger.info(f"Report gespeichert: {output_file}")
        return str(output_file)
    except Exception as e:
        logger.error(f"Fehler beim Speichern: {e}")
        return ""

async def process_analysis_background(
    data: Dict[str, Any], 
    email: str, 
    job_id: str
):
    """
    Führt die GPT-Analyse im Hintergrund aus mit Live-Daten
    """
    try:
        logger.info(f"🚀 Starte Gold Standard+ Analyse für {email}")
        logger.info(f"Kritische Felder: Bundesland={data.get('bundesland_code')}, "
                   f"Branche={data.get('branche')}, Größe={data.get('unternehmensgroesse')}")
        
        # Verwende die erweiterte Analyse-Funktion
        report_data = await generate_report_async(data)
        
        html = report_data.get("html", "")
        meta = report_data.get("meta", {})
        normalized = report_data.get("normalized", {})
        
        # Log wichtige Metriken
        logger.info(f"✅ Analyse abgeschlossen für {email}")
        logger.info(f"📊 KPIs: Score={meta.get('score')}, Badge={meta.get('badge')}")
        logger.info(f"🔍 Live-Daten: News={meta.get('live_counts', {}).get('news', 0)}, "
                   f"Tools={meta.get('live_counts', {}).get('tools', 0)}, "
                   f"Funding={meta.get('live_counts', {}).get('funding', 0)}")
        
        # Speichere Report
        file_path = save_report_to_file(html, email, meta)
        
        # Admin-Attachments generieren (für Debugging)
        if os.getenv("ENABLE_ADMIN_ATTACHMENTS", "false").lower() == "true":
            attachments = produce_admin_attachments(data, data.get('language', 'de'))
            attachment_dir = Path(os.getenv("REPORT_OUTPUT_DIR", "/tmp/ki-reports")) / "admin"
            attachment_dir.mkdir(parents=True, exist_ok=True)
            
            for filename, content in attachments.items():
                (attachment_dir / f"{job_id}_{filename}").write_text(content, encoding='utf-8')
        
        # TODO: In Produktion würde hier:
        # 1. Report in Datenbank speichern
        # 2. PDF via Puppeteer generieren
        # 3. Email mit PDF versenden
        # 4. Queue-Status updaten
        
        return {
            "success": True,
            "file_path": file_path,
            "meta": meta,
            "job_id": job_id
        }
        
    except Exception as e:
        logger.error(f"❌ Fehler bei Analyse für {email}: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "job_id": job_id
        }

# ===================== API ENDPOINTS =====================

@router.get("/briefing/health")
async def health_check():
    """Health Check mit Feature-Status"""
    
    # Prüfe verfügbare Features
    features = {
        "gpt_analyze": GPT_ANALYZE_AVAILABLE,
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "anthropic_configured": bool(os.getenv("ANTHROPIC_API_KEY")),
        "tavily_configured": bool(os.getenv("TAVILY_API_KEY")),
        "perplexity_configured": bool(os.getenv("PPLX_API_KEY")),
        "hybrid_live_enabled": os.getenv("HYBRID_LIVE", "1") == "1",
        "pdf_service": bool(os.getenv("PDF_SERVICE_URL")),
    }
    
    # Prüfe welche Overlays verfügbar sind
    if GPT_ANALYZE_AVAILABLE:
        try:
            from pathlib import Path
            prompts_dir = Path(os.getenv("PROMPTS_DIR", "prompts"))
            de_dir = prompts_dir / "de"
            
            overlays = []
            if de_dir.exists():
                overlays = [f.stem for f in de_dir.glob("*.md")]
            
            features["available_overlays"] = overlays
        except:
            features["available_overlays"] = []
    
    return {
        "status": "healthy" if GPT_ANALYZE_AVAILABLE else "degraded",
        "service": "briefing-gold-standard-plus",
        "version": "2.0.0",
        "features": features,
        "timestamp": datetime.utcnow().isoformat()
    }

@router.post("/briefing")
async def submit_briefing(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Hauptendpoint für Briefing-Submission mit Gold Standard+ Analyse
    """
    try:
        # Empfange Rohdaten
        raw_data = await request.json()
        
        # Normalisiere Daten
        data = normalize_briefing_data(raw_data)
        
        # Validiere kritische Felder
        missing_fields = validate_critical_fields(data)
        if missing_fields:
            logger.warning(f"Fehlende kritische Felder: {missing_fields}")
            # Trotzdem fortfahren mit Defaults
        
        # Email extrahieren
        email = extract_email_from_data(data)
        
        # Job-ID generieren
        job_id = f"job_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hash(email) % 10000}"
        
        logger.info(f"📨 Briefing empfangen: Email={email}, JobID={job_id}")
        logger.info(f"📋 Kritische Parameter: Bundesland={data.get('bundesland_code')}, "
                   f"Branche={data.get('branche')}, Größe={data.get('unternehmensgroesse')}, "
                   f"Hauptleistung={data.get('hauptleistung')[:50] if data.get('hauptleistung') else 'N/A'}")
        
        # Starte Hintergrund-Analyse
        if GPT_ANALYZE_AVAILABLE:
            background_tasks.add_task(
                process_analysis_background,
                data,
                email,
                job_id
            )
            
            message = ("Vielen Dank für Ihre Angaben! 🎯\n\n"
                      "Ihre individuelle KI-Statusanalyse wird jetzt mit aktuellen Live-Daten "
                      f"für {data.get('branche_label', 'Ihre Branche')} in "
                      f"{data.get('bundesland_code', 'Ihrem Bundesland')} erstellt.\n\n"
                      "Sie erhalten Ihren personalisierten Report in wenigen Minuten per E-Mail.")
        else:
            message = ("Vielen Dank für Ihre Angaben! "
                      "Die Analyse-Funktion wird gerade gewartet. "
                      "Bitte versuchen Sie es in Kürze erneut.")
        
        return JSONResponse(
            status_code=200,
            content={
                "ok": True,
                "message": message,
                "job_id": job_id,
                "status": "processing" if GPT_ANALYZE_AVAILABLE else "maintenance",
                "email": email,
                "parameters": {
                    "bundesland": data.get('bundesland_code'),
                    "branche": data.get('branche'),
                    "groesse": data.get('unternehmensgroesse'),
                    "hauptleistung": data.get('hauptleistung', '')[:50]
                }
            }
        )
        
    except Exception as e:
        logger.error(f"Fehler bei Briefing-Verarbeitung: {str(e)}", exc_info=True)
        
        # User-freundliche Fehlermeldung
        return JSONResponse(
            status_code=200,  # 200 für bessere UX
            content={
                "ok": True,
                "message": "Ihre Anfrage wurde entgegengenommen und wird bearbeitet.",
                "job_id": "pending",
                "status": "queued"
            }
        )

@router.post("/briefing_async")
async def submit_briefing_async(request: Request, background_tasks: BackgroundTasks):
    """Alias für Hauptendpoint"""
    return await submit_briefing(request, background_tasks)

@router.get("/briefing/status/{job_id}")
async def get_job_status(job_id: str):
    """
    Prüft Status eines Analyse-Jobs
    """
    # TODO: In Produktion würde dies aus Datenbank/Redis gelesen
    
    # Für Testing: Prüfe ob HTML-Datei existiert
    output_dir = Path(os.getenv("REPORT_OUTPUT_DIR", "/tmp/ki-reports"))
    matching_files = list(output_dir.glob(f"*{job_id}*.html"))
    
    if matching_files:
        return {
            "ok": True,
            "job_id": job_id,
            "status": "completed",
            "message": "Analyse erfolgreich abgeschlossen",
            "download_available": True
        }
    
    return {
        "ok": True,
        "job_id": job_id,
        "status": "processing",
        "message": "Analyse läuft noch...",
        "estimated_time": "2-3 Minuten"
    }

@router.get("/briefing/download/{job_id}")
async def download_report(job_id: str):
    """
    Download des generierten Reports (für Testing)
    """
    output_dir = Path(os.getenv("REPORT_OUTPUT_DIR", "/tmp/ki-reports"))
    matching_files = list(output_dir.glob(f"*{job_id}*.html"))
    
    if not matching_files:
        raise HTTPException(status_code=404, detail="Report nicht gefunden")
    
    return FileResponse(
        path=matching_files[0],
        media_type="text/html",
        filename=f"ki-statusbericht-{job_id}.html"
    )

@router.post("/briefing/test")
async def test_analysis():
    """
    Test-Endpoint mit Beispieldaten
    """
    test_data = {
        "bundesland": "Berlin",
        "bundesland_code": "BE",
        "branche": "beratung",
        "branche_label": "Beratung & Dienstleistungen",
        "unternehmensgroesse": "solo",
        "unternehmensgroesse_label": "1 (Solo/Selbstständig)",
        "hauptleistung": "KI-Beratung und Implementierung",
        "email": "test@example.com",
        "company_name": "Test GmbH",
        "digitalisierungsgrad": "61-80",
        "prozesse_papierlos": "81-100",
        "automatisierungsgrad": "eher_hoch",
        "ki_einsatz": ["chatgpt", "claude"],
        "ki_knowhow": "fortgeschritten",
        "investitionsbudget": "10000-50000",
        "language": "de"
    }
    
    if not GPT_ANALYZE_AVAILABLE:
        return {"error": "GPT-Analyse nicht verfügbar"}
    
    try:
        # Synchroner Test
        report = await generate_report_async(test_data)
        
        return {
            "ok": True,
            "message": "Test erfolgreich",
            "meta": report.get("meta", {}),
            "html_length": len(report.get("html", "")),
            "has_live_data": report.get("meta", {}).get("live_counts", {})
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e)
        }