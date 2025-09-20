# -*- coding: utf-8 -*-

from __future__ import annotations
import re
from typing import Callable

__all__ = ["pdf_ready", "render_or_fallback"]

MUST_HAVE_TOKENS = ("Sichere Sofortschritte", "Roadmap", "Compliance")
MIN_TEXT_LEN = 1200  # characters without tags

def _text_length(html: str) -> int:
    return len(re.sub(r"<[^>]+>", "", html or ""))

def pdf_ready(html: str) -> bool:
    """Check minimal content & must-have tokens before any PDF service call."""
    return _text_length(html) >= MIN_TEXT_LEN and all(t in (html or "") for t in MUST_HAVE_TOKENS)

def render_or_fallback(render_html: Callable[[], str], fallback_html: Callable[[], str]) -> str:
    """Return render_html() if pdf_ready, else fallback_html()."""
    html = (render_html or (lambda: ""))()
    return html if pdf_ready(html) else (fallback_html or (lambda: ""))()
