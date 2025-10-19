# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Dict, Any, Optional
from datetime import datetime
import httpx

from db import get_session
from models import Task
from mail_utils import send_email_with_attachments_sync
from settings import settings
from pdf_client import render_pdf

# Analyzer is expected to be available in project
from analyzer import run_analysis  # type: ignore
from gpt_analyze import produce_admin_attachments  # type: ignore

def _subject(prefix: str, lang: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return f"{prefix} – KI-Status-Report ({today})" if lang.upper().startswith("DE") else f"{prefix} – AI Status Report ({today})"

def process_report(report_id: str, payload: Dict[str, Any]) -> None:
    """RQ worker entry point: generates report, pdf, sends mails, and updates DB."""
    lang = (payload.get("lang") or settings.DEFAULT_LANG or "DE").upper()
    company = payload.get("company") or payload.get("unternehmen") or payload.get("firma") or "Unbekannt"
    email = payload.get("email") or payload.get("to")
    # 1) Generate HTML report
    try:
        html = run_analysis(payload)  # sync variant expected
        pdf_bytes = None
        try:
            # Call async pdf via sync client (httpx can be used sync as well if needed)
            # We'll do a direct httpx call here to avoid running event loop in worker.
            if settings.PDF_SERVICE_URL and html:
                with httpx.Client(timeout=settings.PDF_TIMEOUT/1000) as client:
                    r = client.post(settings.PDF_SERVICE_URL, json={"html": html, "filename": "report.pdf"})
                    if r.status_code == 200:
                        pdf_bytes = r.content
        except Exception:
            pdf_bytes = None

        # 2) Store result
        with get_session() as s:
            t = s.get(Task, report_id)
            if t:
                t.status = "done"
                t.company = company
                t.email = email
                t.lang = lang
                t.html = html
                t.finished_at = datetime.utcnow()

        # 3) Send mails
        attachments_user = {}
        if pdf_bytes:
            attachments_user["KI-Status-Report.pdf"] = pdf_bytes
        elif settings.ATTACH_HTML_FALLBACK and html:
            attachments_user["KI-Status-Report.html"] = html.encode("utf-8")

        attachments_admin = dict(attachments_user)

        try:
            tri = produce_admin_attachments(payload)  # returns dict of {name: json_str}
            for name, content in (tri or {}).items():
                attachments_admin[name] = content.encode("utf-8")
        except Exception:
            pass

        if settings.SEND_USER_MAIL and isinstance(email, str) and "@" in email:
            send_email_with_attachments_sync(
                to_address=email,
                subject=_subject("Ihr Ergebnis", "DE" if lang.startswith("DE") else "EN"),
                html_body="<p>Ihr KI-Status-Report ist da.</p>",
                attachments=attachments_user or None,
            )

        if settings.SEND_ADMIN_MAIL and settings.ADMIN_EMAIL:
            send_email_with_attachments_sync(
                to_address=settings.ADMIN_EMAIL,
                subject=_subject("Admin: neuer Report", "DE" if lang.startswith("DE") else "EN"),
                html_body=f"<p>Neuer Report: <b>{company}</b> ({email or '—'})</p>",
                attachments=attachments_admin or None,
            )

    except Exception as e:
        with get_session() as s:
            t = s.get(Task, report_id)
            if t:
                t.status = "failed"
                t.error = str(e)
                t.finished_at = datetime.utcnow()
        raise
