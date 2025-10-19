# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Optional
import base64
import httpx
from settings import settings

async def render_pdf(html: str, filename: str = "report.pdf") -> Optional[bytes]:
    if not settings.PDF_SERVICE_URL:
        return None
    try:
        async with httpx.AsyncClient(timeout=settings.PDF_TIMEOUT/1000) as client:
            r = await client.post(settings.PDF_SERVICE_URL, json={"html": html, "filename": filename})
            r.raise_for_status()
            ct = (r.headers.get("content-type") or "").lower()
            if "application/pdf" in ct or "application/octet-stream" in ct:
                return r.content
            data = r.json()
            for key in ("pdf_base64", "data", "pdf"):
                if isinstance(data.get(key), str):
                    s = data[key]
                    if ";base64," in s:
                        s = s.split(",", 1)[1]
                    return base64.b64decode(s)
    except Exception:
        return None
    return None
