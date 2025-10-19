# -*- coding: utf-8 -*-
from __future__ import annotations
import re
from typing import Any, Dict, Optional
from datetime import datetime
import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from settings import settings
from mail_utils import send_email_with_attachments
from gpt_analyze import analyze_briefing, analyze_briefing_enhanced, produce_admin_attachments  # type: ignore

router = APIRouter()

def _is_email(value: str) -> bool:
    return bool(re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", (value or "").strip()))

async def _generate_pdf(html: str, filename: str) -> Optional[bytes]:
    if not (settings.PDF_SERVICE_URL and html):
        return None
    try:
        async with httpx.AsyncClient(timeout=settings.PDF_TIMEOUT/1000) as client:
            r = await client.post(settings.PDF_SERVICE_URL, json={"html": html, "filename": filename})
            r.raise_for_status()
            return r.content
    except Exception:
        return None

def _subject(prefix: str, lang: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return f"{prefix} – KI-Status-Report ({today})" if lang.lower().startswith("de") else f"{prefix} – AI Status Report ({today})"

@router.post("/briefing_async")
async def briefing_async(request: Request) -> JSONResponse:
    try:
        raw: Dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    lang = (raw.get("lang") or "de")[:2]
    recipient = (raw.get("to") or raw.get("email") or "").strip()

    if settings.SEND_USER_MAIL and not _is_email(recipient):
        raise HTTPException(status_code=422, detail="Recipient email missing or invalid")
    if settings.SEND_ADMIN_MAIL and not _is_email(settings.ADMIN_EMAIL or ""):
        raise HTTPException(status_code=500, detail="ADMIN_EMAIL not configured")

    # 1) Report bauen
    try:
        html_report = analyze_briefing(raw, lang=lang)
        enhanced = analyze_briefing_enhanced(raw, lang=lang)
    except Exception:
        raise HTTPException(status_code=500, detail="Report generation failed")

    # 2) PDF (optional)
    filename_base = f"KI-Status-Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    pdf_bytes = await _generate_pdf(html_report, filename=f"{filename_base}.pdf")

    # 3) User-Mail
    user_attachments = {}
    if pdf_bytes:
        user_attachments[f"{filename_base}.pdf"] = pdf_bytes
    elif settings.ATTACH_HTML_FALLBACK:
        user_attachments[f"{filename_base}.html"] = html_report.encode("utf-8")

    if settings.SEND_USER_MAIL:
        try:
            await send_email_with_attachments(
                to_address=recipient,
                subject=_subject("Ihr Ergebnis", lang),
                html_body="<p>Ihr KI-Status-Report ist da.</p><p>Live-Abschnitte zeigen das Datum der letzten Aktualisierung.</p>",
                attachments=user_attachments or None,
            )
        except Exception:
            # log happens inside mail_utils via exception propagation in to_thread
            pass

    # 4) Admin-Mail mit Diagnose-Anhängen
    admin_attachments = dict(user_attachments)
    try:
        tri = produce_admin_attachments(raw)
        for name, content in tri.items():
            admin_attachments[name] = content.encode("utf-8")
    except Exception:
        pass

    if settings.SEND_ADMIN_MAIL:
        try:
            await send_email_with_attachments(
                to_address=settings.ADMIN_EMAIL,
                subject=_subject("Admin: neuer Report", lang),
                html_body="<p>Neuer Report generiert (siehe Anhänge).</p>",
                attachments=admin_attachments or None,
            )
        except Exception:
            raise HTTPException(status_code=500, detail="Admin mail failed")

    return JSONResponse({"ok": True, "to": recipient, "attachments": list(user_attachments.keys()) + list(admin_attachments.keys())})
