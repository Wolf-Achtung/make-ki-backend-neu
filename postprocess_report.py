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

# Zusätzliche SMTP-Konfigurationen für SSL/TLS
SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "0").lower() in {"1", "true", "yes"}
SMTP_REQUIRE_TLS = os.getenv("SMTP_REQUIRE_TLS", "1").lower() in {"1", "true", "yes"}

def _send_mail(
    to_addr: str,
    subject: str,
    html_body: str,
    attachments: Optional[Dict[str, bytes]] = None,
) -> None:
    """
    Sendet eine E‑Mail über SMTP. Nutzt wahlweise SSL (SMPT_SSL) oder STARTTLS
    entsprechend der Umgebungsvariablen ``SMTP_USE_SSL`` und ``SMTP_REQUIRE_TLS``.
    Bei fehlender oder unvollständiger SMTP‑Konfiguration wird der Versand
    übersprungen und eine Warnung ausgegeben.
    """
    if not (SMTP_HOST and SMTP_FROM and to_addr):
        log.warning("SMTP nicht vollständig konfiguriert – Mail übersprungen (to=%s)", to_addr)
        return

    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = to_addr
    msg["Subject"] = subject or "Notification"
    # Plaintext-Platzhalter
    msg.set_content("HTML-only mail. Please view in an HTML-capable client.")
    msg.add_alternative(html_body or "<p>(empty)</p>", subtype="html")
    for name, data in (attachments or {}).items():
        if not isinstance(data, (bytes, bytearray)):
            log.warning("Attachment %s hat keine Bytes – übersprungen.", name)
            continue
        msg.add_attachment(data, maintype="application", subtype="octet-stream", filename=name)

    try:
        if SMTP_USE_SSL:
            # Direkte SSL-Verbindung
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as s:
                if SMTP_USER and SMTP_PASS:
                    s.login(SMTP_USER, SMTP_PASS)
                s.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
                s.ehlo()
                if SMTP_REQUIRE_TLS:
                    try:
                        s.starttls()
                        s.ehlo()
                    except smtplib.SMTPException as e:
                        log.error("STARTTLS fehlgeschlagen: %s", e)
                        if SMTP_REQUIRE_TLS:
                            raise
                if SMTP_USER and SMTP_PASS:
                    s.login(SMTP_USER, SMTP_PASS)
                s.send_message(msg)
    except Exception as e:
        log.error("Mailversand fehlgeschlagen (to=%s): %s", to_addr, e)

def send_user_copy(user_email: str, pdf_bytes: bytes, rid: str, lang: str = "de") -> None:
    """
    Versendet den generierten Report an den Nutzer. Als Betreff wird der
    Report‑Titel inklusive Job‑ID genutzt, sodass die Mail eindeutig zuordenbar
    ist. Der HTML‑Body enthält ebenfalls einen kurzen Hinweis mit der Job‑ID.
    """
    title = "KI-Status-Report" if lang.startswith("de") else "AI Status Report"
    subject = f"{title} – Ihre Kopie (Job-ID: {rid})" if lang.startswith("de") else f"{title} – Your copy (Job-ID: {rid})"
    body = f"<p>{subject}</p>"
    _send_mail(user_email, subject, body, attachments={f"{title}.pdf": pdf_bytes})

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
