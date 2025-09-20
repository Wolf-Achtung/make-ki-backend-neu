# -*- coding: utf-8 -*-

"""Gold-Standard services package (drop-in).

Modules:
- context_guards: safe defaults for Jinja context (meta/sections)
- live_layer: graceful degrade wrapper for live updates (no stray %)
- sanitize_html: narrative-only sanitizer (lists/tables -> paragraphs)
- pdf_gate: PDF readiness guard (min length + must-have tokens)
- main_startup: robust analyzer loader with fallback
- normalize_briefing: DE<->EN canonical key normalisation
"""
__all__ = [
    "context_guards",
    "live_layer",
    "sanitize_html",
    "pdf_gate",
    "main_startup",
    "normalize_briefing",
]
__version__ = "2025.09.20"
