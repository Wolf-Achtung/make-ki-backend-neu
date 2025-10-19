# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Dict, Optional
import asyncio
import smtplib
from email.message import EmailMessage
from settings import settings

def _smtp_send(msg: EmailMessage) -> None:
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as s:
        if settings.SMTP_USER and settings.SMTP_PASS:
            s.starttls()
            s.login(settings.SMTP_USER, settings.SMTP_PASS)
        s.send_message(msg)

def _build_message(to_address: str, subject: str, html_body: str, attachments: Optional[Dict[str, bytes]] = None) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM}>"
    msg["To"] = to_address
    msg.set_content("HTML-only message; please use an HTML-capable client.")
    msg.add_alternative(html_body or "<p>—</p>", subtype="html")
    if attachments:
        for name, content in attachments.items():
            maintype, subtype = ("application", "octet-stream")
            if name.lower().endswith(".pdf"):
                maintype, subtype = ("application", "pdf")
            elif name.lower().endswith(".json"):
                maintype, subtype = ("application", "json")
            elif name.lower().endswith(".html"):
                maintype, subtype = ("text", "html")
            msg.add_attachment(content, maintype=maintype, subtype=subtype, filename=name)
    return msg

async def send_email_with_attachments(to_address: str, subject: str, html_body: str, attachments: Optional[Dict[str, bytes]] = None) -> None:
    """Async wrapper that offloads blocking SMTP to a thread."""
    msg = _build_message(to_address, subject, html_body, attachments)
    await asyncio.to_thread(_smtp_send, msg)

def send_email_with_attachments_sync(to_address: str, subject: str, html_body: str, attachments: Optional[Dict[str, bytes]] = None) -> None:
    msg = _build_message(to_address, subject, html_body, attachments)
    _smtp_send(msg)
