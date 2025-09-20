# -*- coding: utf-8 -*-

from __future__ import annotations
import re
from typing import Final

__all__ = ["sanitize", "strip_lists_tables"]
ALLOWED_BLOCKS: Final = ("p","h2","h3","small","br","em","strong","b","i","u","sup","sub","a")

def strip_lists_tables(html: str) -> str:
    """Flatten UL/OL/TABLE to plain text paragraphs and remove bullet prefix markers."""
    html = re.sub(r"</?(ul|ol|li|table|thead|tbody|tr|td|th)[^>]*>", " ", html, flags=re.I)
    html = re.sub(r"(^|\n)\s*[-*•]\s+", r"\1", html)
    return html

def sanitize(html: str) -> str:
    """Basic sanitizer enforcing narrative blocks only (no lists/tables/code fences)."""
    if not html:
        return ""
    html = re.sub(r"```.*?```", "", html, flags=re.S)   # remove code fences
    html = strip_lists_tables(html)

    # Primitive allow-list filter for tags
    def _filter(m):
        tag = m.group(2).lower()
        return f"<{m.group(1)}{tag}>" if tag in ALLOWED_BLOCKS else ""
    html = re.sub(r"<(/?)(\w+)([^>]*)>", _filter, html)
    return html.strip()
