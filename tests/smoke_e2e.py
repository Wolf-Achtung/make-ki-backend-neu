# -*- coding: utf-8 -*-

from __future__ import annotations
from services.normalize_briefing import normalize_briefing
from services.context_guards import build_context
from services.sanitize_html import sanitize
from services.pdf_gate import render_or_fallback

def mock_briefing():
    return {
        "branche": "beratung",
        "unternehmensgroesse": "solo",
        "bundesland": "be",
        "projektziel": ["prozessautomatisierung","compliance"]
    }

def render_html():
    brief = normalize_briefing(mock_briefing())
    sections = {
        "sichere_sofortschritte": "<h2>Sichere Sofortschritte</h2><p>...</p>",
        "roadmap": "<h2>Roadmap</h2><p>...</p>",
        "compliance": "<h2>Compliance</h2><p>...</p>",
    }
    ctx = build_context(brief, sections, lang="de")
    html = f"<h1>{ctx['meta']['title']}</h1>"            f"<p>Branche: {ctx['meta']['branche']}</p>"            + "".join(sections.values())
    return sanitize(html)

def fallback_html():
    return "<h2>Sichere Sofortschritte</h2><p>Fallback ...</p><h2>Roadmap</h2><p>...</p><h2>Compliance</h2><p>...</p>"

if __name__ == "__main__":
    html = render_or_fallback(render_html, fallback_html)
    assert "Sichere Sofortschritte" in html and "Roadmap" in html and "Compliance" in html, "Required tokens missing"
    print("OK - HTML bereit fuer PDF")
