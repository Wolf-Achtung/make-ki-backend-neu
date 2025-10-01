# filename: postprocess_report.py
# -*- coding: utf-8 -*-
"""
MAKE-KI Backend – Post-Processor (Gold-Standard+)
- Erzwingt korrekte ROI-/Payback-Berechnungen
- Repariert unplausible Zeitangaben (z. B. "32 Stunden/Tag")
- Fügt "Stand: YYYY-MM-DD" in Live-Sektionen ein (News/Tools/Förderungen)
- Füllt Benchmark-Tabelle aus Fallback/Datei
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("postprocess_report")

def iso_today() -> str:
    return datetime.now().date().isoformat()

def compute_business_case(invest: float, annual_saving: float) -> Dict[str, Any]:
    if invest <= 0 or annual_saving <= 0:
        return {"roi_year1_pct": 0, "payback_months": 0.0, "three_year_profit": 0}
    roi = round(((annual_saving - invest) / invest) * 100)
    payback = round(invest / (annual_saving / 12.0), 1)
    profit3y = int(round(annual_saving * 3 - invest))
    return {"roi_year1_pct": roi, "payback_months": payback, "three_year_profit": profit3y}

def fix_time_claims(text: str) -> str:
    # Ersetzt "40% = 32 Stunden/Tag" durch Monatsdarstellung (8h/Tag, 20 Tage)
    text = re.sub(r"40%\s*=\s*32\s*Stunden/Tag", "40% ≈ 64 Stunden/Monat (Basis: 8 h × 20 Tage)", text)
    return text

def inject_stand_date(html: str) -> str:
    return re.sub(r"(Aktuelle Meldungen.*?</h3>)", r"\1 <span class='stand'>(Stand: %s)</span>" % iso_today(), html, flags=re.I)

def fill_benchmarks(html: str, benchmarks: Dict[str, float]) -> str:
    # Sucht leere Benchmark-Tabelle und trägt Werte ein
    # (einfaches Platzhalter-Verfahren; die PDF-Engine rendert <table> sauber)
    for key, val in {
        "Digitalisierungsgrad": f"{benchmarks.get('digitalisierung', 7.5):.1f}/10",
        "Automatisierungsgrad": f"{int(benchmarks.get('automatisierung', 0.65) * 100)}%",
        "Datenschutz-Compliance": f"{int(benchmarks.get('compliance', 0.73) * 100)}%",
        "Prozessreife": f"{int(benchmarks.get('prozessreife', 0.68) * 100)}%",
        "Innovationsgrad": f"{int(benchmarks.get('innovation', 0.60) * 100)}%",
    }.items():
        html = re.sub(rf"({re.escape(key)}.*?<td>)\s*-\s*(</td>)", rf"\1{val}\2", html, flags=re.S)
    return html

def run(payload_path: Path, html_path: Path) -> None:
    data = json.loads(payload_path.read_text(encoding="utf-8"))
    # Business Case
    bc = data.get("business_case", {})
    fixed = compute_business_case(float(bc.get("invest_eur", 0)), float(bc.get("annual_saving_eur", 0)))
    bc.update(fixed)
    data["business_case"] = bc

    # HTML laden & korrigieren
    html = html_path.read_text(encoding="utf-8")
    html = fix_time_claims(html)
    html = inject_stand_date(html)
    html = fill_benchmarks(html, data.get("benchmarks", {}))

    # Compliance-Playbook anhängen, falls noch nicht enthalten
    compl_html = data.get("compliance_playbook_html")
    if compl_html and "Compliance‑Playbook" not in html:
        html += "\n" + compl_html

    # Speichern
    payload_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    logger.info("Post-Processing abgeschlossen: ROI/Payback korrigiert, Benchmarks/Stand eingefügt.")

if __name__ == "__main__":
    # Erwartet Pfade als ENV (oder Standard)
    payload = Path(os.getenv("REPORT_PAYLOAD", "build/payload.json"))
    html = Path(os.getenv("REPORT_HTML", "build/report.html"))
    if payload.exists() and html.exists():
        run(payload, html)
    else:
        logger.warning("payload/html nicht gefunden – nichts zu tun.")
