# postprocess_report.py — Admin-Mail inkl. Rohdaten
from __future__ import annotations

import json
import logging
import os
import smtplib
from email.message import EmailMessage
from typing import Dict, Optional

log = logging.getLogger("postprocess")

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")

def _send_mail(to_addr: str, subject: str, html_body: str, attachments: Optional[Dict[str, bytes]] = None) -> None:
    if not (SMTP_HOST and SMTP_FROM and to_addr):
        log.warning("SMTP nicht vollständig konfiguriert – Mail übersprungen (to=%s)", to_addr)
        return
    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content("HTML-only mail. Please view in an HTML-capable client.")
    msg.add_alternative(html_body, subtype="html")
    for name, data in (attachments or {}).items():
        maintype, subtype = ("application", "octet-stream")
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.starttls()
        if SMTP_USER and SMTP_PASS:
            s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)

def send_user_copy(user_email: str, pdf_bytes: bytes, rid: str, lang: str = "de") -> None:
    title = "KI-Status-Report" if lang.startswith("de") else "AI Status Report"
    body = f"<p>{title} – Ihre Kopie (Job-ID: {rid}).</p>"
    _send_mail(user_email, title, body, attachments={f"{title}.pdf": pdf_bytes})

def send_admin_copy(ctx: Dict[str, str], pdf_bytes: bytes, rid: str, lang: str = "de") -> None:
    """Hängt briefing.json an die Admin-Mail an (falls ADMIN_EMAIL gesetzt)."""
    to = ADMIN_EMAIL
    if not to:
        log.info("ADMIN_EMAIL nicht gesetzt – Admin-Mail übersprungen.")
        return
    subject = ctx.get("admin_subject") or ("Neuer KI-Status-Report – Rohdaten" if lang.startswith("de") else "New AI Status Report – Raw data")
    note = ctx.get("admin_note") or "Automatisch generierte Rohdaten (JSON)."
    body = f"<p>{subject}<br/>Job-ID: {rid}</p><p>{note}</p>"
    raw_json = (ctx.get("admin_form_json") or "{}").encode("utf-8")
    _send_mail(to, subject, body, attachments={
        "KI-Status-Report.pdf": pdf_bytes,
        "briefing.json": raw_json,
    })
