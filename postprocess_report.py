# postprocess_report.py
# -*- coding: utf-8 -*-
"""
Post-Processing: Aus Sections + Live-Addins werden HTML-Blöcke für den PDF-Service.
- Einheitliche Komponenten (Karten, Progress-Bars, Quellenliste, Deadlines-Tabelle).
- Benchmarks (data/benchmarks_<branche>_kmu.json) werden bei Verfügbarkeit eingespielt.
- Jede Kachel erhält "Stand: YYYY-MM-DD | Quelle(n): …" (Gold-Standard+ "Transparenz").

Export:
    render_pdf_payload(result: dict, briefing: dict) -> dict
        -> gibt {html_sections:{...}, assets:[], metadata:{...}} zurück
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

DATA_DIR = Path("data")


def _load_benchmarks(industry: str) -> Dict[str, Any]:
    path = DATA_DIR / f"benchmarks_{industry}_kmu.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _meta_line(stand_iso: str, sources: List[str]) -> str:
    src = ", ".join(sorted(set(sources))) if sources else "—"
    dt = stand_iso.split("T")[0] if "T" in stand_iso else stand_iso[:10]
    return f"<div class='meta'>Stand: {html.escape(dt)} &nbsp;·&nbsp; Quellen: {html.escape(src)}</div>"


def _render_sources(items: List[Dict[str, Any]]) -> List[str]:
    srcs = []
    for it in items:
        s = it.get("source") or ""
        if s:
            srcs.append(s)
    return srcs


def _progress(value: int) -> str:
    value = max(0, min(100, int(value)))
    return f"""
    <div class="progress"><div class="bar" style="width:{value}%"></div></div>
    """


def _table(rows: List[List[str]]) -> str:
    th = "".join(f"<th>{html.escape(c)}</th>" for c in rows[0])
    body = []
    for r in rows[1:]:
        body.append("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in r) + "</tr>")
    return f"<table class='compact'><thead><tr>{th}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _render_funding(items: List[Dict[str, Any]], generated_at: str) -> str:
    rows = [["Programm", "Frist", "Quelle"]]
    for it in items[:10]:
        rows.append([
            it.get("title", ""),
            it.get("deadline", "") or "—",
            it.get("url", ""),
        ])
    tbl = _table(rows)
    srcs = _render_sources(items)
    return f"<h3>Förderprogramme & Deadlines</h3>{tbl}{_meta_line(generated_at, srcs)}"


def _render_news(items: List[Dict[str, Any]], generated_at: str, title: str) -> str:
    cards = []
    for it in items[:10]:
        cards.append(
            f"<div class='card'><h4><a href='{html.escape(it.get('url',''))}'>{html.escape(it.get('title',''))}</a></h4>"
            f"<p>{html.escape(it.get('summary',''))}</p>"
            f"<div class='fine'>{html.escape((it.get('published_at') or '')[:10])} · {html.escape(it.get('source',''))}</div>"
            f"</div>"
        )
    srcs = _render_sources(items)
    return f"<h3>{html.escape(title)}</h3>{''.join(cards)}{_meta_line(generated_at, srcs)}"


def _render_benchmarks(industry: str, generated_at: str) -> str:
    data = _load_benchmarks(industry)
    if not data:
        return ""
    rows = [["KPI", "Branchen‑Richtwert", "Quelle"]]
    for kpi in data.get("kpis", []):
        rows.append([kpi["name"], str(kpi["value"]), kpi.get("source", "—")])
    return f"<h3>Benchmark‑Vergleich ({html.escape(industry)})</h3>{_table(rows)}{_meta_line(generated_at, [d.get('source_domain','') for d in data.get('kpis', [])])}"


def render_pdf_payload(result: Dict[str, Any], briefing: Dict[str, Any]) -> Dict[str, Any]:
    sections = result["sections"]
    live = result.get("live", {})
    meta = result.get("meta", {})
    generated_at = meta.get("generated_at", datetime.now(timezone.utc).isoformat())

    html_sections = {
        "executive_summary": sections.get("executive_summary", ""),
        "business": sections.get("business", ""),
        "persona": sections.get("persona", ""),
        "quick_wins": sections.get("quick_wins", ""),
        "risks": sections.get("risks", ""),
        "recommendations": sections.get("recommendations", ""),
        "roadmap": sections.get("roadmap", ""),
        "praxisbeispiel": sections.get("praxisbeispiel", ""),
        "coach": sections.get("coach", ""),
        "vision": sections.get("vision", ""),
        "gamechanger": sections.get("gamechanger", ""),
        "compliance": sections.get("compliance", ""),
        # Live‑Blöcke
        "benchmarks": _render_benchmarks(briefing.get("branche", ""), generated_at),
        "news_html": _render_news(live.get("news", []), generated_at, "Aktuelle Meldungen"),
        "tools_rich_html": _render_news(live.get("tools", []), generated_at, "Neue Tools & Releases"),
        "funding_rich_html": _render_news(live.get("publications", []), generated_at, "Relevante Studien/Projekte"),
        "funding_deadlines_html": _render_funding(live.get("funding", []), generated_at),
    }

    return {
        "html_sections": html_sections,
        "assets": [],
        "metadata": {
            "generated_at": generated_at,
            "benchmarks_loaded": meta.get("benchmarks_loaded", False),
            "sources_count": meta.get("sources_count", {}),
        },
    }
