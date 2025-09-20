# -*- coding: utf-8 -*-

from __future__ import annotations
import logging, re
from typing import Dict, List, Any

__all__ = ["fetch_live_updates"]
log = logging.getLogger("live")

FALLBACK_HEADLINE = "Aktuelle Hinweise"

def _clean_text(s: str) -> str:
    if not s:
        return ""
    # Remove code fences, bullets and trim
    s = re.sub(r"```.*?```", "", s, flags=re.S)
    s = re.sub(r"^(\s*[-*•]\s+)", "", s, flags=re.M)
    return s.strip()

def _sanitize_percents(text: str) -> str:
    # Replace stray '%' with word if no preceding number is present
    if "%" in text and not re.search(r"\d+\s*%", text):
        text = text.replace("%", " Prozent")
    return text

def fetch_live_updates(query: str, days: int | None = None, depth: int | None = None) -> Dict[str, Any]:
    """Wrap your Tavily/SerpAPI lookup here.

    The function MUST NEVER raise; it returns a small, print-ready dict:
      { "headline": str, "bullets": [str, ...] }
    When the live call fails or yields nothing reliable, it degrades to
    a neutral headline and an empty bullet list.
    """
    try:
        # >>> Integrate your actual live search here <<<
        # result = tavily_search(query, days=days, depth=depth)
        # bullets = parse_result_to_sentences(result)
        bullets: List[str] = []  # keep empty on mock
        headline: str = "Neu seit September 2025"
    except Exception as e:
        log.warning("Live layer failed: %s", e)
        bullets, headline = [], FALLBACK_HEADLINE

    headline = _clean_text(headline or FALLBACK_HEADLINE)
    bullets = [_sanitize_percents(_clean_text(b)) for b in bullets]
    bullets = [b for b in bullets if b][:5]
    return {"headline": headline, "bullets": bullets}
