# filename: worker_tasks.py
# -*- coding: utf-8 -*-
# RQ-Worker-Job zum Verarbeiten von Reports.
# - Läuft im separaten Prozess (rq worker)
# - Ruft die Analyse-Engine auf
# - Persistiert Ergebnis, erzeugt PDF (optional) und versendet E-Mails (User + Admin)

from __future__ import annotations
import asyncio
import base64
import logging
from typing import Any, Dict, Optional

import httpx

from settings import settings
from db import get_session
from models import Task
from analyzer import run_analysis
from gpt_analyze import produce_admin_attachments
from mail_utils import send_email_with_attachments

log = logging.getLogger("worker_tasks")

async def _generate_pdf_async(html: str, filename: str = "report.pdf") -> Optional[bytes]:
    if not html:
        return None
    if settings.PDF_SERVICE_URL:
        try:
            async with httpx.AsyncClient(timeout=settings.PDF_TIMEOUT/1000) as client:
                resp = await client.post(str(settings.PDF_SERVICE_URL), json={"html": html, "filename": filename})
                ctype = (resp.headers.get("content-type") or "").lower()
                if "application/pdf" in ctype or "application/octet-stream" in ctype:
                    return resp.content
                # try JSON base64 format
                try:
                    data = resp.json()
                    for key in ("pdf_base64", "data", "pdf"):
                        if isinstance(data.get(key), str):
                            b64s = data[key]
                            if ";base64," in b64s:
                                b64s = b64s.split(",", 1)[1]
                            return base64.b64decode(b64s)
                except Exception:
                    pass
        except Exception as e:
            log.warning("[worker] PDF service failed: %s", e)
    return None

def _update_task(report_id: str, **fields: Any) -> None:
    with get_session() as s:
        t = s.get(Task, report_id)
        if not t:
            return
        for k, v in fields.items():
            setattr(t, k, v)

def process_report(report_id: str, payload: Dict[str, Any]) -> bool:
    """
    Entry point für RQ.
    """
    log.info("[worker] start report_id=%s", report_id)

    # mark running
    _update_task(report_id, status="running")

    # 1) Analyse ausführen (run_analysis kann async sein)
    try:
        if asyncio.iscoroutinefunction(run_analysis):
            html = asyncio.run(run_analysis(payload))
        else:
            html = run_analysis(payload)
    except Exception as e:
        log.exception("[worker] analysis failed: %s", e)
        _update_task(report_id, status="failed", error=str(e))
        return False

    # 2) Ergebnis persistieren
    _update_task(report_id, html=html)

    # 3) PDF erzeugen (wenn Service aktiv)
    try:
        pdf_bytes = asyncio.run(_generate_pdf_async(html, filename=f"KI-Status-Report_{report_id}.pdf"))
    except Exception as e:
        log.warning("[worker] pdf generation failed: %s", e)
        pdf_bytes = None

    # 4) Attachments zusammenstellen
    answers = (payload or {}).get("answers") or {}
    lang = ((payload or {}).get("lang") or settings.DEFAULT_LANG or "DE").lower()
    filename_base = f"KI-Status-Report_{report_id}"
    user_attach = {}
    if pdf_bytes:
        user_attach[f"{filename_base}.pdf"] = pdf_bytes
    else:
        user_attach[f"{filename_base}.html"] = (html or "").encode("utf-8")

    admin_attach = dict(user_attach)  # gleiches PDF/HTML
    try:
        tri = produce_admin_attachments(answers, lang=lang)
        for name, content in tri.items():
            admin_attach[name] = content.encode("utf-8")
    except Exception as e:
        log.warning("[worker] admin attachments failed: %s", e)

    # 5) E-Mails versenden (best-effort)
    to_user = (payload or {}).get("email")
    try:
        if to_user:
            asyncio.run(send_email_with_attachments(
                to_address=to_user,
                subject=f"{settings.MAIL_SUBJECT_PREFIX} – Ihr KI-Status-Report",
                html_body="<p>Ihr KI-Status-Report ist fertiggestellt. Der Report liegt im Anhang.</p>",
                attachments=user_attach
            ))
            log.info("[worker] sent user mail to %s", to_user)
    except Exception as e:
        log.exception("[worker] send user mail failed: %s", e)

    try:
        asyncio.run(send_email_with_attachments(
            to_address=settings.ADMIN_EMAIL,
            subject=f"{settings.MAIL_SUBJECT_PREFIX} – Admin: Report erstellt",
            html_body=f"<p>Report {report_id} wurde erstellt und versendet.</p>",
            attachments=admin_attach
        ))
        log.info("[worker] sent admin mail")
    except Exception as e:
        log.exception("[worker] send admin mail failed: %s", e)

    # 6) Abschlussstatus
    _update_task(report_id, status="done")
    log.info("[worker] done report_id=%s", report_id)
    return True
