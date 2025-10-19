# -*- coding: utf-8 -*-
"""RQ tasks for PDF rendering and email (optional)."""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Optional, Dict, Any

import httpx
from rq import get_current_job
from redis import Redis

from queue_utils import get_redis_connection

PDF_SERVICE_URL = os.getenv("PDF_SERVICE_URL", "").strip()
PDF_TIMEOUT = int(os.getenv("PDF_TIMEOUT", "45000")) / 1000.0  # ms → s
RESULT_TTL = int(os.getenv("RQ_RESULT_TTL", "3600"))  # seconds

def _store_bytes(redis: Redis, key: str, data: bytes, ttl: int) -> None:
    redis.set(key, data, ex=ttl)

def _fetch_pdf(html: Optional[str] = None, url: Optional[str] = None) -> bytes:
    if not PDF_SERVICE_URL:
        raise RuntimeError("PDF_SERVICE_URL is not configured")
    payload: Dict[str, Any] = {}
    if html:
        payload["html"] = html
    if url:
        payload["url"] = url
    headers = {"Accept": "application/pdf"}
    with httpx.Client(timeout=PDF_TIMEOUT) as client:
        r = client.post(PDF_SERVICE_URL, json=payload, headers=headers)
        ct = r.headers.get("content-type", "")
        if "application/pdf" in ct.lower():
            return r.content
        try:
            data = r.json()
            pdf_url = data.get("pdf_url") or data.get("url")
            if pdf_url:
                rr = client.get(pdf_url)
                rr.raise_for_status()
                return rr.content
        except Exception:
            pass
        r.raise_for_status()
        return r.content

def _send_email_with_attachment(to_email: str, subject: str, body_text: str, pdf_bytes: bytes, filename: str = "report.pdf") -> None:
    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USERNAME", "").strip()
    pwd = os.getenv("SMTP_PASSWORD", "").strip()
    use_tls = str(os.getenv("SMTP_USE_TLS", "true")).strip().lower() in {"1", "true", "yes", "on"}
    mail_from = os.getenv("MAIL_FROM", user or "no-reply@example.com")
    if not host or not user or not pwd:
        return
    msg = EmailMessage()
    msg["From"] = mail_from
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body_text)
    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=filename)
    with smtplib.SMTP(host, port) as smtp:
        if use_tls:
            smtp.starttls()
        smtp.login(user, pwd)
        smtp.send_message(msg)

def analyze_and_render(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Render PDF (html or url) and optionally email it.
    payload: html?: str, url?: str, email?: str, filename?: str
    returns dict with job_id, redis_key, filename
    """
    job = get_current_job()
    job_id = job.id if job else None
    html = payload.get("html")
    url = payload.get("url")
    email = payload.get("email")
    filename = payload.get("filename") or "ki-report.pdf"
    if not html and not url:
        raise ValueError("Provide 'html' or 'url' in payload")
    pdf_bytes = _fetch_pdf(html=html, url=url)
    redis = get_redis_connection()
    redis_key = f"pdf:{job_id}"
    _store_bytes(redis, redis_key, pdf_bytes, RESULT_TTL)
    if email:
        try:
            _send_email_with_attachment(
                to_email=email,
                subject="Ihr KI-Status-Report",
                body_text="Anbei Ihr KI-Status-Report als PDF.",
                pdf_bytes=pdf_bytes,
                filename=filename,
            )
        except Exception:
            pass
    return {"ok": True, "job_id": job_id, "redis_key": redis_key, "filename": filename}
