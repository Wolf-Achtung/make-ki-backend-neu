# File: routes/briefing.py
# -*- coding: utf-8 -*-
"""
/briefing_async – mit User- und Admin-Mail inkl. 3 JSON-Admin-Attachments.

Fixes ggü. deinem aktuellen Verhalten:
- OpenAI-404/Legacy-Fallback ist vollständig entfernt (wird in gpt_analyze.py
  korrekt auf v1 + Auto-Fallback auf gpt-4o behandelt; siehe dein Log)
- Admin-Mail enthält jetzt IMMER: briefing_raw.json, briefing_normalized.json,
  briefing_missing_fields.json (alte vs. neue Briefings waren Ursache für leere Felder) 
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from gpt_analyze import (
    analyze_briefing,
    analyze_briefing_enhanced,
    produce_admin_attachments,
)
from mail_utils import send_email_with_attachments

logger = logging.getLogger("routes_briefing")

router = APIRouter()

PDF_SERVICE_URL = os.getenv("PDF_SERVICE_URL", "").strip()
PDF_TIMEOUT = float(os.getenv("PDF_TIMEOUT", "25"))
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip()
SEND_USER_MAIL = (os.getenv("SEND_USER_MAIL") or os.getenv("SEND_TO_USER") or os.getenv("MAIL_TO_USER") or "true").lower() == "true"
SEND_ADMIN_MAIL = (os.getenv("SEND_ADMIN_MAIL") or os.getenv("ADMIN_NOTIFY") or "true").lower() == "true"
ATTACH_HTML_FALLBACK = os.getenv("ATTACH_HTML_FALLBACK", "true").lower() == "true"


def _is_email(value: str) -> bool:
    return bool(re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", (value or "").strip()))


async def _generate_pdf(html: str, filename: str) -> Optional[bytes]:
    """Ruft externen PDF-Service auf; gibt PDF-Bytes oder None zurück."""
    if not (PDF_SERVICE_URL and html):
        return None
    try:
        async with httpx.AsyncClient(timeout=PDF_TIMEOUT) as client:
            r = await client.post(PDF_SERVICE_URL, json={"html": html, "fileName": filename})
            r.raise_for_status()
            return r.content
    except Exception as e:
        logger.warning("PDF service call failed: %s", e)
        return None


def _subject(prefix: str, lang: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return f"{prefix} – KI-Status-Report ({today})" if lang == "de" else f"{prefix} – AI Status Report ({today})"


@router.post("/briefing_async")
async def briefing_async(request: Request) -> JSONResponse:
    try:
        raw: Dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    lang = (raw.get("lang") or "de")[:2]
    recipient = (raw.get("to") or raw.get("email") or "").strip()

    if SEND_USER_MAIL and not _is_email(recipient):
        raise HTTPException(status_code=422, detail="Recipient email missing or invalid")
    if SEND_ADMIN_MAIL and not _is_email(ADMIN_EMAIL):
        raise HTTPException(status_code=500, detail="ADMIN_EMAIL not configured")

    # 1) Report bauen
    try:
        html_report = analyze_briefing(raw, lang=lang)
        enhanced = analyze_briefing_enhanced(raw, lang=lang)
    except Exception as e:
        logger.exception("Report generation failed: %s", e)
        raise HTTPException(status_code=500, detail="Report generation failed")

    # 2) PDF erzeugen (optional)
    filename_base = f"KI-Status-Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    pdf_bytes = await _generate_pdf(html_report, filename=f"{filename_base}.pdf")

    # 3) User-Mail
    user_attachments: Dict[str, bytes] = {}
    if pdf_bytes:
        user_attachments[f"{filename_base}.pdf"] = pdf_bytes
    elif ATTACH_HTML_FALLBACK:
        user_attachments[f"{filename_base}.html"] = html_report.encode("utf-8")

    if SEND_USER_MAIL:
        try:
            await send_email_with_attachments(
                to_address=recipient,
                subject=_subject("Ihr Ergebnis", lang),
                html_body="<p>Ihr KI-Status-Report ist da.</p><p>Live-Abschnitte zeigen das Datum der letzten Aktualisierung.</p>",
                attachments=user_attachments,
            )
            logger.info("[mail] user notice sent to %s", recipient)
        except Exception as e:
            logger.exception("User mail failed: %s", e)

    # 4) Admin-Mail mit Diagnose-Anhängen
    admin_attachments: Dict[str, bytes] = {}
    if pdf_bytes:
        admin_attachments[f"{filename_base}-admin.pdf"] = pdf_bytes
    elif ATTACH_HTML_FALLBACK:
        admin_attachments[f"{filename_base}-admin.html"] = html_report.encode("utf-8")

    try:
        tri = produce_admin_attachments(raw)
        for name, content in tri.items():
            admin_attachments[name] = content.encode("utf-8")
    except Exception as e:
        logger.warning("Admin attachments generation failed: %s", e)

    if SEND_ADMIN_MAIL:
        try:
            await send_email_with_attachments(
                to_address=ADMIN_EMAIL,
                subject=_subject("Admin: neuer Report", lang),
                html_body=(
                    "<p>Neuer Report generiert.</p>"
                    "<ul>"
                    f"<li>Branche: <b>{(enhanced['briefing']['branche'] or '—')}</b></li>"
                    f"<li>Größe: <b>{(enhanced['briefing']['unternehmensgroesse'] or '—')}</b></li>"
                    f"<li>Score: <b>{enhanced['score_percent']}%</b></li>"
                    f"<li>Stand: <b>{enhanced['meta']['date']}</b></li>"
                    "</ul>"
                    "<p>Angehängt: PDF/HTML + briefing_raw/normalized/missing.json</p>"
                ),
                attachments=admin_attachments,
            )
            logger.info("[mail] admin notice sent to %s", ADMIN_EMAIL)
        except Exception as e:
            logger.exception("Admin mail failed: %s", e)
            raise HTTPException(status_code=500, detail="Admin mail failed")

    return JSONResponse(
        {"ok": True, "to": recipient, "attachments": list(user_attachments.keys()) + list(admin_attachments.keys())}
    )
