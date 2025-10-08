# File: pdf_client.py
# -*- coding: utf-8 -*-
"""
Zentraler PDF-Client: bevorzugt /generate-pdf; akzeptiert Bytes ODER JSON {pdf_base64}.
"""

from __future__ import annotations
import os, base64
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
        resp = client.post(url, json={"filename": filename, "html": html, "return_pdf_bytes": True})
    resp.raise_for_status()
    ctype = (resp.headers.get("content-type") or "").lower()
    if "application/pdf" in ctype:
        return resp.content
    if "application/json" in ctype:
        data = resp.json()
        b64 = data.get("pdf_base64") or data.get("pdf") or data.get("data")
        if b64:
            return base64.b64decode(b64)
    raise RuntimeError(f"unexpected PDF response: {ctype}")
