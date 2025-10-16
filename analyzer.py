# filename: analyzer.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import json
from datetime import datetime

async def run_analysis(payload: dict) -> str:
    """Unified analyzer used by web and worker.
    Tries optional gpt_analyze module; falls back to lightweight HTML summary.
    """
    try:
        from gpt_analyze import analyze_briefing_enhanced  # type: ignore
        html = await analyze_briefing_enhanced(payload)
        if not isinstance(html, str):
            html = json.dumps(html, ensure_ascii=False)
        return html
    except Exception:
        # Fallback: Render simple HTML
        company = payload.get("company", "-")
        lang = payload.get("lang", "DE")
        title = "KI-Status-Report" if lang == "DE" else "AI Status Report"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        items = ''.join(f"<li><strong>{k}</strong>: {v}</li>" for k, v in (payload.get("answers") or {}).items())
        return (
            f"<h1>{title} – {company}</h1>"
            f"<p><em>Stand: {ts} – Fallback-Modus</em></p>"
            f"{'<h2>Zusammenfassung</h2>' if lang=='DE' else '<h2>Summary</h2>'}"
            f"<ul>{items}</ul>"
        )
