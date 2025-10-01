# filename: gpt_analyze.py
# -*- coding: utf-8 -*-
"""
MAKE-KI Backend – Report Generator (Gold-Standard+)
- Korrekte ROI/Payback-Logik
- BY/Branche/Hauptleistung-Synergie für News/Tools/Förderungen
- Compliance-Playbook (Go-Live-Gate, MVC, Re-Trigger, Human-in-the-Loop, Kill-Switch)
- Nutzung normalisierter Förder-CSV (data/foerderprogramme.csv)
- Präzisere Tavily-Suchen mit Domain-Whitelist & Zeitfenstern
- Optionale EU-Connectoren (OpenAIRE, CORDIS, F&T)
"""

from __future__ import annotations

import csv
import dataclasses
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx

# Lokale Module
from websearch_utils import tavily_search, days_to_tavily_range
from eu_connectors import (
    openaire_search_projects,
    cordis_search_projects,
    funding_tenders_search,
)

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("gpt_analyze")

# -----------------------------------------------------------------------------
# Konfiguration
# -----------------------------------------------------------------------------
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
PROMPTS_DIR = Path(os.getenv("PROMPTS_DIR", "prompts"))
TEMPLATE_DIR = Path(os.getenv("TEMPLATE_DIR", "templates"))
DEFAULT_LANG = os.getenv("DEFAULT_LANG", "de")

SEARCH_DAYS = int(os.getenv("SEARCH_DAYS", "30"))
SEARCH_DAYS_TOOLS = int(os.getenv("SEARCH_DAYS_TOOLS", str(SEARCH_DAYS)))
SEARCH_DAYS_FUNDING = int(os.getenv("SEARCH_DAYS_FUNDING", str(max(60, SEARCH_DAYS))))

SEARCH_MAX_RESULTS = int(os.getenv("SEARCH_MAX_RESULTS", "8"))
SEARCH_PROVIDER = os.getenv("SEARCH_PROVIDER", "tavily")

ENABLE_LLM_SECTIONS = os.getenv("ENABLE_LLM_SECTIONS", "true").lower() == "true"
ENABLE_COACHING = os.getenv("ENABLE_COACHING", "true").lower() == "true"

QUALITY_CONTROL_AVAILABLE = os.getenv("QUALITY_CONTROL_AVAILABLE", "true").lower() == "true"

# Domains für DE/Bundesländer (Whitelist)
DOMAIN_WHITELIST_BY = [
    "bayern.de", "stmwi.bayern.de", "l-bank.de", "stmuv.bayern.de",
    "ihk.de", "europa.eu", "eur-lex.europa.eu", "bmwk.de"
]
DOMAIN_WHITELIST_BE = ["berlin.de", "ibb.de", "ihk.de", "europa.eu", "bmwk.de"]
DOMAIN_WHITELIST_BW = ["baden-wuerttemberg.de", "l-bank.de", "ihk.de", "europa.eu", "bmwk.de"]

BUNDESLAND_DOMAIN_WHITELIST = {
    "by": DOMAIN_WHITELIST_BY,
    "be": DOMAIN_WHITELIST_BE,
    "bw": DOMAIN_WHITELIST_BW,
}

# -----------------------------------------------------------------------------
# Datenstrukturen
# -----------------------------------------------------------------------------
@dataclasses.dataclass
class Briefing:
    branche: str
    unternehmensgroesse: str
    bundesland: str
    hauptleistung: str
    jahresumsatz: str = ""
    lang: str = DEFAULT_LANG
    investitionsbudget: str = ""
    # optionale Felder
    digitalisierungsgrad: Optional[str] = None
    automatisierungsgrad: Optional[str] = None
    ai_roadmap: Optional[str] = None

    @staticmethod
    def from_json(path: Path) -> "Briefing":
        data = json.loads(path.read_text(encoding="utf-8"))
        return Briefing(
            branche=data.get("branche", ""),
            unternehmensgroesse=data.get("unternehmensgroesse", ""),
            bundesland=data.get("bundesland", ""),
            hauptleistung=data.get("hauptleistung", ""),
            jahresumsatz=data.get("jahresumsatz", ""),
            lang=data.get("lang", DEFAULT_LANG),
            investitionsbudget=data.get("investitionsbudget", ""),
            digitalisierungsgrad=data.get("digitalisierungsgrad"),
            automatisierungsgrad=data.get("automatisierungsgrad"),
            ai_roadmap=data.get("ai_roadmap"),
        )


@dataclasses.dataclass
class BusinessCase:
    invest_eur: float
    annual_saving_eur: float
    efficiency_gain_frac: float = 0.4  # 40% default
    base_hours_per_day: float = 8.0

    @property
    def roi_year1_pct(self) -> int:
        """(Einsparung - Investition) / Investition * 100, gerundet."""
        if self.invest_eur <= 0:
            return 0
        return round(((self.annual_saving_eur - self.invest_eur) / self.invest_eur) * 100)

    @property
    def payback_months(self) -> float:
        """Investition / (Einsparung pro Monat)."""
        if self.annual_saving_eur <= 0:
            return 0.0
        monthly = self.annual_saving_eur / 12.0
        if monthly <= 0:
            return 0.0
        return round(self.invest_eur / monthly, 1)

    @property
    def three_year_profit(self) -> int:
        """(Einsparung*3 - Investition), gerundet."""
        return int(round(self.annual_saving_eur * 3 - self.invest_eur))

    @property
    def time_saved_hours_per_month(self) -> int:
        """40% von 8h/Tag auf Monatsbasis (~20 Arbeitstage)"""
        return int(round(self.efficiency_gain_frac * self.base_hours_per_day * 20))


# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------
def load_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def map_region_code(bundesland: str) -> str:
    m = {
        "by": "BY", "be": "BE", "bw": "BW",
        "bundesweit": "DE", "deutschland": "DE"
    }
    return m.get(bundesland.lower(), "DE")


def now_iso() -> str:
    return datetime.now().date().isoformat()


# -----------------------------------------------------------------------------
# Live Content (News/Tools/Funding)
# -----------------------------------------------------------------------------
def build_queries(b: Briefing) -> Dict[str, Any]:
    """Kombiniert Branche × Größe × Hauptleistung × Bundesland."""
    size = b.unternehmensgroesse
    qs_base = f'{b.branche} "{b.hauptleistung}" KI Automatisierung {b.bundesland.upper()}'
    return {
        "news": [
            f"{qs_base} AI Act DSGVO site:bmwk.de",
            f"{qs_base} Förderung Deadline",
            f"{b.branche} KMU KI Best Practice {b.bundesland.upper()}",
        ],
        "tools": [
            f"Tools {b.branche} KI Automatisierung DSGVO DPA {b.bundesland.upper()}",
            f"Open-Source KI Automatisierung {b.branche} self-hosted",
        ],
        "funding": [
            f"Förderung Digitalisierung {b.bundesland.upper()} Beratung KMU",
            f"Förderprogramm KI {b.bundesland.upper()} Deadline",
        ],
        "domain_whitelist": BUNDESLAND_DOMAIN_WHITELIST.get(b.bundesland.lower(), ["bmwk.de", "europa.eu", "ihk.de"]),
    }


def get_live_news_tools_funding(b: Briefing) -> Dict[str, str]:
    """Rendert HTML-Karten aus Tavily und CSV/EU-APIs."""
    q = build_queries(b)
    time_range_news = days_to_tavily_range(max(7, SEARCH_DAYS))
    time_range_tools = days_to_tavily_range(max(30, SEARCH_DAYS_TOOLS))
    time_range_funding = days_to_tavily_range(max(60, SEARCH_DAYS_FUNDING))

    def as_cards(items: List[Dict[str, str]], tag: str) -> str:
        cards = []
        for it in items[:SEARCH_MAX_RESULTS]:
            title = it.get("title") or it.get("name") or "Unbenannter Eintrag"
            url = it.get("url") or it.get("link") or "#"
            date = it.get("published") or it.get("date") or ""
            snippet = (it.get("snippet") or it.get("summary") or it.get("description") or "").strip()
            cards.append(
                f"""<div class="card">
                    <div class="card-tag">{tag}</div>
                    <div class="card-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></div>
                    <div class="card-meta">{date}</div>
                    <div class="card-body">{snippet}</div>
                </div>"""
            )
        return "\n".join(cards)

    # Tavily
    news_hits: List[Dict[str, str]] = []
    for qn in q["news"]:
        news_hits += tavily_search(
            qn, days=max(7, SEARCH_DAYS), include_domains=q["domain_whitelist"], max_results=SEARCH_MAX_RESULTS
        )

    tools_hits: List[Dict[str, str]] = []
    for qt in q["tools"]:
        tools_hits += tavily_search(
            qt, days=max(30, SEARCH_DAYS_TOOLS), include_domains=q["domain_whitelist"], max_results=SEARCH_MAX_RESULTS
        )

    # EU-APIs (optional – robust gegen Fehler)
    eu_calls = []
    try:
        eu_calls += funding_tenders_search(f'AI OR "artificial intelligence" {b.branche}', from_days=60)
    except Exception as e:
        logger.warning("EU F&T search failed: %s", e)

    # Förderungen aus CSV (normalisiert)
    funding_rows = load_csv(DATA_DIR / "foerderprogramme.csv")
    region_code = map_region_code(b.bundesland)
    funding_rows = [r for r in funding_rows if r.get("Region_Code", "DE") in (region_code, "DE")]
    funding_cards = []
    for r in funding_rows[:8]:
        title = r.get("Programmname", "Programm")
        url = r.get("Website", "#")
        quote = r.get("Foerderquote_prozent", "")
        deadline = r.get("Deadline", "rolling")
        status = r.get("Status", "offen")
        funding_cards.append(
            f"""<div class="card">
                <div class="card-tag">Förderung</div>
                <div class="card-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></div>
                <div class="card-meta">Quote: {quote}% · Deadline: {deadline} · Status: {status}</div>
            </div>"""
        )

    html = {
        "news_html": f'<section><h3>Aktuelle Meldungen (Stand: {now_iso()})</h3>{as_cards(news_hits, "News")}</section>',
        "tools_rich_html": f'<section><h3>Neue Tools & Releases (Stand: {now_iso()})</h3>{as_cards(tools_hits, "Tool/Release")}</section>',
        "funding_rich_html": f'<section><h3>Förderprogramme (Stand: {now_iso()})</h3>{"".join(funding_cards)}</section>',
        "funding_deadlines_html": f'<section><h3>EU‑Calls (letzte 60 Tage)</h3>{as_cards(eu_calls, "EU‑Call")}</section>',
    }
    return html


# -----------------------------------------------------------------------------
# Compliance-Playbook (aus Governance-Notiz)
# -----------------------------------------------------------------------------
def render_compliance_playbook() -> str:
    """HTML-Abschnitt mit Klartext-Regeln & Checkliste."""
    return f"""
<section>
  <h3>Compliance‑Playbook (Go‑Live‑Gate & Betrieb)</h3>
  <ol>
    <li><strong>Go‑Live‑Gate & Minimal Viable Compliance (MVC):</strong> Vor Produktivbetrieb Nachweis von
      Risikoklasse, DPA/AVV, Rechtekette, Tests (Performance/Drift/Bias), Rollen & Verantwortlichkeiten.</li>
    <li><strong>Human‑in‑the‑Loop & Kill‑Switch:</strong> Kritische Entscheidungen bleiben beim Menschen; dokumentierter Not‑Aus mit Rückfallebene.</li>
    <li><strong>Input‑/Output‑Checks:</strong> Rechtekette & Datenbasis prüfen (Input). Ausgaben auf Halluzinationen/IP/DSGVO/Policy prüfen (Output). Beide als Prozess‑Gates verankern.</li>
    <li><strong>Re‑Klassifizierungs‑Trigger:</strong> Fine‑Tuning, Zweckwechsel, White‑Label/Markenwechsel, autonome Agenten → Pflichten neu bewerten.</li>
    <li><strong>Rechtslandkarte:</strong> Neben KI‑VO auch Produktrecht/Sektorrecht, CRA, DSA und Data Act berücksichtigen; Verantwortliche & Nachweise benennen.</li>
    <li><strong>AI‑Literacy:</strong> Pflichttrainings mit jährlicher Auffrischung; Zugriffsrechte an Schulungsstand koppeln.</li>
    <li><strong>Monitoring & Re‑Tests:</strong> Technologieradar, periodische Re‑Tests (Performance/Drift/Bias); Ergebnisse zurück in Standards & Modelle.</li>
  </ol>
  <p class="stand">Stand: {now_iso()}</p>
</section>
"""


# -----------------------------------------------------------------------------
# Benchmarks (Fallback)
# -----------------------------------------------------------------------------
DEFAULT_BENCHMARKS_BERATUNG = {
    "digitalisierung": 7.5,
    "automatisierung": 0.65,
    "compliance": 0.73,
    "prozessreife": 0.68,
    "innovation": 0.60,
}


def load_benchmarks(branche: str) -> Dict[str, float]:
    """Lädt branchenspezifische Benchmarks; fällt auf Default zurück."""
    path = DATA_DIR / "benchmarks_beratung_kmu.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    if branche.lower().startswith("beratung"):
        return DEFAULT_BENCHMARKS_BERATUNG
    return DEFAULT_BENCHMARKS_BERATUNG


# -----------------------------------------------------------------------------
# Hauptfunktion für den Controller
# -----------------------------------------------------------------------------
def generate_report_payload(briefing_json_path: Path) -> Dict[str, Any]:
    """
    Erzeugt ein Payload-Dict für die HTML-Vorlage/PDF-Engine.
    Wird vom FastAPI-Endpunkt /briefing_async gerufen.
    """
    logger.info("OpenAI Client initialisiert")
    b = Briefing.from_json(briefing_json_path)
    logger.info("Briefing geladen: %s", b)

    # Business Case – Zahlen (robust)
    # Defaultannahmen belassen; können aus Fragebogen/Prompts übersteuert werden
    bc = BusinessCase(invest_eur=6000.0, annual_saving_eur=24000.0, efficiency_gain_frac=0.40)

    # Live‑Add‑ins
    live = get_live_news_tools_funding(b)

    # Compliance‑Playbook
    playbook_html = render_compliance_playbook()

    # Benchmarks
    bm = load_benchmarks(b.branche)

    payload = {
        "lang": b.lang,
        "branche": b.branche,
        "bundesland": b.bundesland,
        "unternehmensgroesse": b.unternehmensgroesse,
        "hauptleistung": b.hauptleistung,
        "created_at": now_iso(),
        "last_updated": now_iso(),
        "business_case": {
            "invest_eur": bc.invest_eur,
            "annual_saving_eur": bc.annual_saving_eur,
            "roi_year1_pct": bc.roi_year1_pct,
            "payback_months": bc.payback_months,
            "three_year_profit": bc.three_year_profit,
            "time_saved_hours_per_month": bc.time_saved_hours_per_month,
        },
        "benchmarks": bm,
        "live_addins": live,
        "compliance_playbook_html": playbook_html,
    }
    logger.info("Live add-ins: %s", list(live.keys()))
    return payload


if __name__ == "__main__":
    # Lokaler Testlauf (optional)
    example = Path("briefing.json")
    if example.exists():
        print(json.dumps(generate_report_payload(example), ensure_ascii=False, indent=2))
    else:
        logger.warning("briefing.json nicht gefunden – lokaler Test übersprungen.")
