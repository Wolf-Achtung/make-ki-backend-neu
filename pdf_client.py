# File: pdf_client.py
# -*- coding: utf-8 -*-
"""
Zentraler PDF-Client: postet HTML immer auf /generate-pdf (keine Alt-Route /render-pdf).
"""

from __future__ import annotations
import os
from typing import Optional
try:
    import httpx  # type: ignore
except Exception:  # pragma: no cover
    httpx = None  # type: ignore


def render_pdf(html: str, filename: str = "report.pdf", timeout_ms: Optional[int] = None) -> bytes:
    if not httpx:
        raise RuntimeError("httpx not available")
    base = os.getenv("PDF_SERVICE_URL", "").rstrip("/")
    if not base:
        raise RuntimeError("PDF_SERVICE_URL not configured")
    url = f"{base}/generate-pdf"
    tout = int(os.getenv("PDF_TIMEOUT", "90000")) if timeout_ms is None else int(timeout_ms)
    with httpx.Client(timeout=tout / 1000.0) as client:
        resp = client.post(url, json={"filename": filename, "html": html})
    resp.raise_for_status()
    return resp.content
