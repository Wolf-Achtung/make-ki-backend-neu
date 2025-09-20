# -*- coding: utf-8 -*-

from __future__ import annotations
from datetime import datetime
from typing import Dict, Any

__all__ = ["default_meta", "build_context"]

def _pick(src: Dict[str, Any], key: str, default: str = "-") -> str:
    """Return a trimmed string value from src[key] or a default dash placeholder."""
    val = src.get(key)
    if val is None:
        return default
    s = str(val).strip()
    return s if s else default

def default_meta(briefing: Dict[str, Any], lang: str = "de") -> Dict[str, str]:
    """Create safe meta information for the report cover and header."""
    return {
        "title": "KI-Statusbericht" if lang == "de" else "AI Status Report",
        "date": datetime.now().strftime("%d.%m.%Y"),
        "lang": lang,
        "branche": _pick(briefing, "branche"),
        "groesse": _pick(briefing, "unternehmensgroesse"),
        "standort": _pick(briefing, "bundesland"),
    }

def build_context(briefing: Dict[str, Any], rendered_sections: Dict[str, str], lang: str = "de") -> Dict[str, Any]:
    """Ensure meta/sections exist for Jinja templates even when data are thin."""
    return {
        "meta": default_meta(briefing or {}, lang),
        "sections": rendered_sections or {"placeholder": "n/a"},
    }
