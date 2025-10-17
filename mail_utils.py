# filename: mail_utils.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import logging
import os
import smtplib
from email.message import EmailMessage
from typing import Dict

logger = logging.getLogger("mail_utils")

def _smtp_config():
    host = os.getenv("MAIL_HOST") or os.getenv("SMTP_HOST")
    port = int(os.getenv("MAIL_PORT") or os.getenv("SMTP_PORT") or 587)
    user = os.getenv("MAIL_USER") or os.getenv("SMTP_USER")
    pwd  = os.getenv("MAIL_PASSWORD") or os.getenv("SMTP_PASS")
    sender = os.getenv("MAIL_FROM") or os.getenv("SMTP_FROM") or user
    if not all([host, port, user, pwd, sender]):
        raise RuntimeError("SMTP not configured (host/port/user/password/from missing)")
    return host, port, user, pwd, sender

def _build_message(to_address: str, subject: str, html_body: str, attachments: Dict[str, bytes]) -> EmailMessage:
    msg = EmailMessage()
    msg["To"] = to_address
    msg["Subject"] = subject
    msg["From"] = os.getenv("MAIL_FROM") or os.getenv("SMTP_FROM") or os.getenv("MAIL_USER") or os.getenv("SMTP_USER")
    msg.set_content("HTML-only email. Please open with an HTML-capable client.")
    msg.add_alternative(html_body or "<p></p>", subtype="html")
    for name, data in (attachments or {}).items():
        maintype, subtype = ("application", "octet-stream")
        if name.endswith(".pdf"):
            maintype, subtype = ("application", "pdf")
        elif name.endswith(".html"):
            maintype, subtype = ("text", "html")
        elif name.endswith(".json"):
            maintype, subtype = ("application", "json")
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    return msg

async def send_email_with_attachments(to_address: str, subject: str, html_body: str, attachments: Dict[str, bytes]) -> None:
    host, port, user, pwd, _ = _smtp_config()
    msg = _build_message(to_address, subject, html_body, attachments)
    def _send():
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.ehlo()
            try:
                server.starttls()
            except Exception:
                pass
            if user and pwd:
                server.login(user, pwd)
            server.send_message(msg)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _send)
    logger.info("Mail sent to %s (%d attachments)", to_address, len(attachments or {}))
