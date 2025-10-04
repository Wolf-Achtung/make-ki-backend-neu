# File: mail_utils.py
# -*- coding: utf-8 -*-
"""
SMTP Utility – send_email_with_attachments (async)

ENV:
- MAIL_HOST, MAIL_PORT (587), MAIL_USER, MAIL_PASSWORD, MAIL_FROM
"""

from __future__ import annotations

import asyncio
import logging
import os
import smtplib
from email.message import EmailMessage
from typing import Dict

logger = logging.getLogger("mail_utils")


def _smtp_config():
    host = os.getenv("MAIL_HOST")
    port = int(os.getenv("MAIL_PORT", "587"))
    user = os.getenv("MAIL_USER")
    pwd = os.getenv("MAIL_PASSWORD")
    sender = os.getenv("MAIL_FROM") or user
    if not all([host, port, user, pwd, sender]):
        raise RuntimeError("SMTP not configured (MAIL_HOST/PORT/USER/PASSWORD/FROM)")
    return host, port, user, pwd, sender


def _build_message(to_address: str, subject: str, html_body: str, attachments: Dict[str, bytes]) -> EmailMessage:
    msg = EmailMessage()
    msg["To"] = to_address
    msg["Subject"] = subject
    msg["From"] = os.getenv("MAIL_FROM") or os.getenv("MAIL_USER")
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
            server.starttls()
            server.login(user, pwd)
            server.send_message(msg)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _send)
    logger.info("Mail sent to %s (%d attachments)", to_address, len(attachments or {}))
