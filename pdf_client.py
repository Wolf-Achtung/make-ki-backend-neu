# filename: pdf_client.py
# -*- coding: utf-8 -*-
"""
Zentraler PDF-Client
- Rendert HTML ausschließlich über /generate-pdf (keine Alt-Route /render-pdf).
- Enthält optionalen Health-Ping für den PDF-Service.

ENV:
  PDF_SERVICE_URL    Basis-URL des PDF-Dienstes (ohne Slash)
  PDF_TIMEOUT        Millisekunden (Default 90000)

Abhängigkeit: httpx
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

try:
    import httpx  # type: ignore
except Exception:  # pragma: no cover
    httpx = None  # type: ignore


def render_pdf(html: str, filename: str = "report.pdf", timeout_ms: Optional[int] = None) -> bytes:
    """Rendert HTML zu PDF über /generate-pdf und gibt Bytes zurück."""
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
    return resp.content


def ping_pdf_service(timeout_s: float = 4.0) -> Tuple[bool, str]:
    """
    Leichter Health-Ping für den PDF-Service:
      1) /health, sonst
      2) HEAD /generate-pdf (falls unterstützt), sonst
      3) Minimaler Dry-Run-POST (ohne PDF-Bytes zu verlangen)
    Gibt (ok, detail) zurück.
    """
    if not httpx:
        return False, "httpx not available"
    base = os.getenv("PDF_SERVICE_URL", "").rstrip("/")
    if not base:
        return False, "PDF_SERVICE_URL not configured"

    try:
        with httpx.Client(timeout=timeout_s) as cli:
            # 1) explicit health
            try:
                r = cli.get(f"{base}/health")
                if r.status_code == 200:
                    return True, "/health:200"
            except Exception:
                pass
            # 2) HEAD generate
            try:
                r = cli.request("HEAD", f"{base}/generate-pdf")
                if 200 <= r.status_code < 500:
                    return True, f"HEAD /generate-pdf:{r.status_code}"
            except Exception:
                pass
            # 3) minimal dry-run (no bytes)
            try:
                r = cli.post(f"{base}/generate-pdf", json={"html": "<b>ping</b>", "return_pdf_bytes": False})
                if 200 <= r.status_code < 300:
                    return True, "POST /generate-pdf:200"
                return False, f"POST /generate-pdf:{r.status_code}"
            except Exception as exc:
                return False, f"POST fail: {exc}"
    except Exception as exc:
        return False, str(exc)
