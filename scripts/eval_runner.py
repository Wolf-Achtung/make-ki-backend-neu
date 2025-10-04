# File: scripts/eval_runner.py
# -*- coding: utf-8 -*-
"""
Mini-Eval:
- 5 Briefings → HTML (optional PDF via PDF_SERVICE_URL)
- Prüfungen: ≥5 Progress-Bars, Benchmark-Tabelle vorhanden, ≥5 http-Links
- Ergebnisse als CSV & Markdown

Ausführen:  python scripts/eval_runner.py
"""

from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import httpx

from gpt_analyze import analyze_briefing

OUT_DIR = Path(os.getenv("EVAL_OUT_DIR", "eval_reports"))
MAKE_PDFS = os.getenv("MAKE_PDFS", "false").lower() == "true"
PDF_SERVICE_URL = os.getenv("PDF_SERVICE_URL", "").strip()
PDF_TIMEOUT = float(os.getenv("PDF_TIMEOUT", "25"))


@dataclass
class EvalCase:
    name: str
    payload: Dict[str, object]


def _pdf_or_none(html: str, name: str) -> bytes | None:
    if not (MAKE_PDFS and PDF_SERVICE_URL and html):
        return None
    try:
        with httpx.Client(timeout=PDF_TIMEOUT) as client:
            r = client.post(PDF_SERVICE_URL, json={"html": html, "fileName": f"{name}.pdf"})
            r.raise_for_status()
            return r.content
    except Exception:
        return None


def _check_progress_bars(html: str) -> Tuple[bool, int]:
    hits = len(re.findall(r'class="bar__fill"', html, flags=re.I))
    return hits >= 5, hits


def _check_benchmark_table(html: str) -> bool:
    return bool(re.search(r"Benchmark", html, flags=re.I))


def _check_links(html: str) -> Tuple[bool, int]:
    cnt = len(re.findall(r'<a\s+[^>]*href="https?://', html, flags=re.I))
    return cnt >= 5, cnt


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "case"


def run_eval(cases: List[EvalCase]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows: List[Dict[str, object]] = []

    for case in cases:
        html = analyze_briefing(case.payload, lang=str(case.payload.get("lang", "de")))
        slug = _slug(case.name)
        (OUT_DIR / f"{slug}.html").write_text(html, encoding="utf-8")

        pdf = _pdf_or_none(html, slug)
        if pdf:
            (OUT_DIR / f"{slug}.pdf").write_bytes(pdf)

        ok_bars, n_bars = _check_progress_bars(html)
        ok_bm = _check_benchmark_table(html)
        ok_links, n_links = _check_links(html)

        score = round((sum([ok_bars, ok_bm, ok_links]) / 3) * 100, 1)
        rows.append(
            {
                "case": case.name,
                "progress_bars_ok": ok_bars,
                "progress_bars_count": n_bars,
                "benchmark_table_ok": ok_bm,
                "links_ok": ok_links,
                "links_count": n_links,
                "quality_score": score,
            }
        )

    with (OUT_DIR / "eval_results.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "case",
                "progress_bars_ok",
                "progress_bars_count",
                "benchmark_table_ok",
                "links_ok",
                "links_count",
                "quality_score",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    md = ["# Mini‑Evaluation", "", "| Case | Bars (ok/anz) | Benchmark | Links (ok/anz) | Score |", "|---|---:|:---:|---:|---:|"]
    for r in rows:
        md.append(
            f"| {r['case']} | {'✅' if r['progress_bars_ok'] else '❌'} {r['progress_bars_count']} | "
            f"{'✅' if r['benchmark_table_ok'] else '❌'} | "
            f"{'✅' if r['links_ok'] else '❌'} {r['links_count']} | {r['quality_score']} |"
        )
    (OUT_DIR / "eval_summary.md").write_text("\n".join(md), encoding="utf-8")


if __name__ == "__main__":
    cases = [
        EvalCase(
            "Beratung solo (DE/BE)",
            {
                "branche": "Beratung & Dienstleistungen",
                "unternehmensgroesse": "solo",
                "bundesland": "BE",
                "hauptleistung": "GPT‑Auswertung",
                "investitionsbudget": "2000_10000",
                "digitalisierungsgrad": 7,
                "automatisierungsgrad": 4,
                "lang": "de",
                "email": "demo@example.com",
                "to": "demo@example.com",
            },
        ),
        EvalCase(
            "IT & Software KMU",
            {"branche": "IT & Software", "unternehmensgroesse": "kmu", "bundesland": "BY", "investitionsbudget": "10000_50000", "digitalisierungsgrad": 8, "automatisierungsgrad": 6, "lang": "de", "email": "demo@example.com", "to": "demo@example.com"},
        ),
        EvalCase(
            "Handel & E‑Commerce",
            {"branche": "Handel & E‑Commerce", "unternehmensgroesse": "small", "bundesland": "NW", "investitionsbudget": "2000_10000", "digitalisierungsgrad": 6, "automatisierungsgrad": 5, "lang": "de", "email": "demo@example.com", "to": "demo@example.com"},
        ),
        EvalCase(
            "Gesundheit & Pflege",
            {"branche": "Gesundheit & Pflege", "unternehmensgroesse": "kmu", "bundesland": "SN", "investitionsbudget": "10000_50000", "digitalisierungsgrad": 5, "automatisierungsgrad": 3, "lang": "de", "email": "demo@example.com", "to": "demo@example.com"},
        ),
        EvalCase(
            "Verwaltung",
            {"branche": "Verwaltung", "unternehmensgroesse": "kmu", "bundesland": "HE", "investitionsbudget": "bis_2000", "digitalisierungsgrad": 6, "automatisierungsgrad": 3, "lang": "de", "email": "demo@example.com", "to": "demo@example.com"},
        ),
    ]
    run_eval(cases)
    print(f"Ergebnisse unter: {OUT_DIR.resolve()}")
