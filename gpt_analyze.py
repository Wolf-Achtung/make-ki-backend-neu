# filename: gpt_analyze.py
# -*- coding: utf-8 -*-
"""
MAKE-KI Backend – Report Generator (Gold-Standard+)

Ziele
-----
- Promptaustausch (DE/EN) für alle Sektionen aus /prompts
- Synergie-Logik: Branche × Unternehmensgröße × Hauptleistung × Bundesland
- Live-Add-ins: Tavily (News/Tools), EU-Calls (optional), normalisierte CSV (data/foerderprogramme.csv)
- Compliance-Playbook (klarer Klartext, Go-Live-Gate, MVC, HiTL, Kill-Switch, Re-Trigger, Rechtslandkarte, Monitoring)
- Benchmarks: Katalog (data/benchmarks_catalog.json) + Fallback (data/benchmarks_beratung_kmu.json)
- Sauberes Logging, Fehlerrobustheit, PEP8, Typen, Timeouts
- Farbpalette (Blau + Orange) für Templates
- Keine Stillannahmen: alle Eingaben aus briefing.json; Variablen/Schalter via Env

Kompatibel mit bisherigen Logs & Aufrufen (siehe Railway-Logs).
"""

from __future__ import annotations

import csv
import dataclasses
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx

# Optionale lokale Module (robuste Fallbacks)
try:
    from websearch_utils import tavily_search, days_to_tavily_range  # type: ignore
except Exception:  # pragma: no cover
    def days_to_tavily_range(days: int) -> str:
        if days <= 7:
            return "day"
        if days <= 30:
            return "week"
        if days <= 90:
            return "month"
        return "year"

    def tavily_search(
        query: str,
        days: int = 30,
        include_domains: Optional[List[str]] = None,
        max_results: int = 8,
    ) -> List[Dict[str, str]]:
        return []

# EU-Connectoren sind optional und dürfen niemals das Rendering blockieren
try:
    from eu_connectors import (  # type: ignore
        openaire_search_projects,
        cordis_search_projects,
        funding_tenders_search,
    )
except Exception:  # pragma: no cover
    def openaire_search_projects(*args, **kwargs) -> List[Dict[str, str]]:  # type: ignore
        return []

    def cordis_search_projects(*args, **kwargs) -> List[Dict[str, str]]:  # type: ignore
        return []

    def funding_tenders_search(*args, **kwargs) -> List[Dict[str, str]]:  # type: ignore
        return []

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("gpt_analyze")

# -----------------------------------------------------------------------------
# Konfiguration
# -----------------------------------------------------------------------------
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
PROMPTS_DIR = Path(os.getenv("PROMPTS_DIR", "prompts"))
TEMPLATE_DIR = Path(os.getenv("TEMPLATE_DIR", "templates"))
DEFAULT_LANG = os.getenv("DEFAULT_LANG", "de")

SEARCH_DAYS = int(os.getenv("SEARCH_DAYS", "30"))
SEARCH_DAYS_TOOLS = int(os.getenv("SEARCH_DAYS_TOOLS", str(max(30, SEARCH_DAYS))))
SEARCH_DAYS_FUNDING = int(os.getenv("SEARCH_DAYS_FUNDING", str(max(60, SEARCH_DAYS))))
SEARCH_MAX_RESULTS = int(os.getenv("SEARCH_MAX_RESULTS", "8"))

ENABLE_LLM_SECTIONS = os.getenv("ENABLE_LLM_SECTIONS", "true").lower() == "true"
ENABLE_COACHING = os.getenv("ENABLE_COACHING", "true").lower() == "true"
QUALITY_CONTROL_AVAILABLE = os.getenv("QUALITY_CONTROL_AVAILABLE", "true").lower() == "true"

GPT_MODEL_NAME = os.getenv("GPT_MODEL_NAME", "gpt-4o-mini")
OPENAI_FALLBACK_MODEL = os.getenv("OPENAI_FALLBACK_MODEL", "gpt-4o")
GPT_TEMPERATURE = float(os.getenv("GPT_TEMPERATURE", "0.25"))

# Bundesland → Domain-Whitelist (reduziert SEO-Spam)
DOMAIN_WHITELIST_BY = ["bayern.de", "stmwi.bayern.de", "l-bank.de", "ihk.de", "europa.eu", "eur-lex.europa.eu", "bmwk.de"]
DOMAIN_WHITELIST_BE = ["berlin.de", "ibb.de", "ihk.de", "europa.eu", "bmwk.de"]
DOMAIN_WHITELIST_BW = ["baden-wuerttemberg.de", "l-bank.de", "ihk.de", "europa.eu", "bmwk.de"]
BUNDESLAND_DOMAIN_WHITELIST: Dict[str, List[str]] = {"by": DOMAIN_WHITELIST_BY, "be": DOMAIN_WHITELIST_BE, "bw": DOMAIN_WHITELIST_BW}

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
    # optional
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
    efficiency_gain_frac: float = 0.40  # 40 %
    base_hours_per_day: float = 8.0

    @property
    def roi_year1_pct(self) -> int:
        if self.invest_eur <= 0:
            return 0
        return round(((self.annual_saving_eur - self.invest_eur) / self.invest_eur) * 100)

    @property
    def payback_months(self) -> float:
        if self.annual_saving_eur <= 0:
            return 0.0
        monthly = self.annual_saving_eur / 12.0
        if monthly <= 0:
            return 0.0
        return round(self.invest_eur / monthly, 1)

    @property
    def three_year_profit(self) -> int:
        return int(round(self.annual_saving_eur * 3 - self.invest_eur))

    @property
    def time_saved_hours_per_month(self) -> int:
        # 40% * 8h * 20 AT ≈ gesparte Stunden/Monat pro FTE
        return int(round(self.efficiency_gain_frac * self.base_hours_per_day * 20))


# -----------------------------------------------------------------------------
# Fallback generators for section content
#
# Wenn kein API‑Key für OpenAI vorhanden ist, liefern die LLM‑Aufrufe oben leere
# Zeichenketten.  Um dennoch aussagekräftige Berichte zu erzeugen, werden hier
# einfache Heuristiken verwendet, die auf den Eingabedaten und dem Business
# Case basieren.  Diese Funktionen erzeugen kurze HTML‑Blöcke, die die
# wichtigsten Informationen zusammenfassen.  Sie ersetzen keine echte
# Generierung mit einem LLM, liefern aber nützliche Platzhalter für die
# wichtigsten Sektionen.

def _fallback_exec_summary(data: Dict[str, Any], bc: BusinessCase) -> str:
    """Erzeugt eine kurze Executive Summary ohne LLM.

    Die Zusammenfassung orientiert sich an den Vorgaben aus den Prompt‑MDs:
    Ausgangslage & Chancen, Werthebel, Kennzahlen und ein konkreter nächster
    Schritt.  Alle Werte werden aus den Eingabedaten und dem Business Case
    berechnet.

    :param data: questionaire answers (flattened) or briefing dict
    :param bc: vorberechneter BusinessCase
    :return: HTML‑String mit drei Absätzen, Bullet‑Liste und Abschlusszeile
    """
    branche = data.get("branche", "")
    bundesland = data.get("bundesland", "")
    size = data.get("unternehmensgroesse", "")
    leistung = data.get("hauptleistung", "")

    # Abschnitt 1: Ausgangslage & Chancen
    p1 = (
        f"Ihr Unternehmen in der Branche {branche.title()} in {bundesland.upper()} "
        f"({size}) erbringt {leistung}. Das hohe Digitalisierungsniveau und eine offene "
        f"Innovationskultur schaffen ideale Voraussetzungen für den Einsatz von KI." )

    # Abschnitt 2: Werthebel
    p2 = (
        "Durch den gezielten Einsatz von KI können Sie Effizienz steigern, Qualität "
        "sichern, das Kundenerlebnis verbessern und Risiken reduzieren."
    )

    # Abschnitt 3: Kennzahlen
    p3 = (
        f"Investition: {bc.invest_eur:,.0f} € · ROI im 1. Jahr: {bc.roi_year1_pct}% · "
        f"Payback: {bc.payback_months} Monate · 3‑Jahres‑Gewinn: {bc.three_year_profit:,.0f} € · "
        f"Zeitersparnis: {bc.time_saved_hours_per_month} Std./Monat."
    )

    # Nächster Schritt
    next_step = (
        "<ul><li>Starten Sie innerhalb von 14 Tagen ein Pilotprojekt für automatisierte "
        "Texterstellung und Übersetzung, um erste Erfahrungen zu sammeln und Prozesse zu optimieren.</li></ul>"
    )

    return (
        f"<p>{p1}</p><p>{p2}</p><p>{p3}</p>{next_step}<p class='stand'>Stand: {now_iso()}</p>"
    )


def _fallback_business_html(bc: BusinessCase) -> str:
    """Erstellt einen Business‑Case‑Abschnitt mit Kennzahlen als HTML.

    :param bc: berechneter BusinessCase
    :return: HTML‑String mit einer kompakten Tabelle
    """
    rows = [
        ["Investition", f"{bc.invest_eur:,.0f} €"],
        ["Jährliche Einsparung", f"{bc.annual_saving_eur:,.0f} €"],
        ["ROI (Jahr 1)", f"{bc.roi_year1_pct}%"],
        ["Payback", f"{bc.payback_months} Monate"],
        ["3‑Jahres‑Gewinn", f"{bc.three_year_profit:,.0f} €"],
        ["Zeitersparnis/Monat", f"{bc.time_saved_hours_per_month} Std."],
    ]
    table_html = "<table class='compact'><thead><tr><th>Kennzahl</th><th>Wert</th></tr></thead><tbody>"
    for r in rows:
        table_html += f"<tr><td>{r[0]}</td><td>{r[1]}</td></tr>"
    table_html += "</tbody></table>"
    return table_html + f"<p class='stand'>Stand: {now_iso()}</p>"


def _fallback_persona_html(data: Dict[str, Any]) -> str:
    """Erstellt eine einfache Persona‑Beschreibung.

    :param data: questionaire answers
    :return: HTML‑String
    """
    branche = data.get("branche", "")
    size = data.get("unternehmensgroesse", "")
    leistung = data.get("hauptleistung", "")
    bundesland = data.get("bundesland", "")
    persona = (
        f"<p><strong>Unternehmen:</strong> Ein {size.upper()}‑Unternehmen aus der Branche {branche.title()} in {bundesland.upper()}.</p>"
        f"<p><strong>Leistung:</strong> {leistung}.</p>"
        f"<p><strong>Vision:</strong> {data.get('ki_geschaeftsmodell_vision', '').strip() or '–'}</p>"
    )
    return persona + f"<p class='stand'>Stand: {now_iso()}</p>"


def _fallback_recommendations_html() -> str:
    """Erzeugt strategische Empfehlungspunkte als HTML.
    Diese Vorschläge sind generischer Natur und können als Ausgangspunkt dienen.
    """
    recs = [
        "Priorisieren Sie Automatisierungsprojekte, um Effizienz und Skalierbarkeit zu erhöhen.",
        "Investieren Sie in Datenqualität und Governance, um belastbare Ergebnisse zu erzielen.",
        "Bauen Sie interne KI‑Kompetenzen aus (Schulungen, AI‑Literacy).",
        "Integrieren Sie Compliance von Anfang an (DSGVO, AI Act, CRA, DSA, Data Act).",
        "Nutzen Sie Fördermittel und Netzwerke (BMWK, EU‑Programme) zur Unterstützung Ihrer Projekte.",
    ]
    html_list = "<ul>" + "".join(f"<li>{r}</li>" for r in recs) + "</ul>"
    return html_list + f"<p class='stand'>Stand: {now_iso()}</p>"


def _fallback_quick_wins_html() -> str:
    """Erzeugt eine Liste von Quick Wins als HTML.
    Diese Maßnahmen lassen sich kurzfristig realisieren und liefern schnelle Erfolge.
    """
    wins = [
        "Automatisieren Sie Übersetzungen mit Tools wie DeepL API.",
        "Nutzen Sie ChatGPT für Ideengenerierung und Inhaltserstellung.",
        "Implementieren Sie Spracherkennung für Transkripte und Untertitel.",
        "Setzen Sie Workflows zur Qualitätskontrolle (z. B. automatisch generierte Checklisten) um.",
        "Testen Sie Tools zur Bildgenerierung für Social‑Media Assets.",
    ]
    html_list = "<ul>" + "".join(f"<li>{w}</li>" for w in wins) + "</ul>"
    return html_list + f"<p class='stand'>Stand: {now_iso()}</p>"


def _fallback_risks_html() -> str:
    """Erzeugt eine kurze Risikomatrix als HTML.
    """
    risks = [
        ("Datenschutzverletzungen", "Durch unzureichende Anonymisierung oder Nutzung sensibler Daten."),
        ("Bias & Diskriminierung", "Modelle könnten unbeabsichtigte Vorurteile verstärken."),
        ("Abhängigkeit von Drittanbietern", "Externe Dienste könnten ausfallen oder Kosten erhöhen."),
        ("Komplexität & Wartung", "Modelle müssen überwacht und regelmäßig angepasst werden."),
    ]
    rows = "<table class='compact'><thead><tr><th>Risiko</th><th>Beschreibung</th></tr></thead><tbody>"
    for name, desc in risks:
        rows += f"<tr><td>{name}</td><td>{desc}</td></tr>"
    rows += "</tbody></table>"
    return rows + f"<p class='stand'>Stand: {now_iso()}</p>"


def _fallback_roadmap_html() -> str:
    """Erzeugt eine einfache 90‑Tage‑Roadmap als HTML.
    """
    phases = [
        ("0–30 Tage", "Use‑Cases identifizieren, Datenquelle evaluieren, Pilotprojekt auswählen."),
        ("31–60 Tage", "Pilot implementieren, Ergebnisse messen, Feedback einholen."),
        ("61–90 Tage", "Pilot skalieren, Prozesse optimieren, weitere Use‑Cases planen."),
    ]
    rows = "<table class='compact'><thead><tr><th>Zeitraum</th><th>Aktionen</th></tr></thead><tbody>"
    for period, action in phases:
        rows += f"<tr><td>{period}</td><td>{action}</td></tr>"
    rows += "</tbody></table>"
    return rows + f"<p class='stand'>Stand: {now_iso()}</p>"


def _fallback_compliance_html() -> str:
    """Verwendet das Compliance‑Playbook als Fallback für die Compliance‑Sektion."""
    return render_compliance_playbook()


def _fallback_tools_html() -> str:
    """Erzeugt eine Liste empfohlener KI‑Tools als HTML.
    Diese Liste ist generisch und sollte bei Bedarf auf das Unternehmen abgestimmt werden.
    """
    tools = [
        ("ChatGPT", "Textgenerierung & kreativer Schreibassistent", "https://openai.com"),
        ("DeepL", "Übersetzung & Lokalisierung", "https://deepl.com"),
        ("Canva", "Design & Social‑Media Content", "https://canva.com"),
        ("Otter.ai", "Spracherkennung & Transkription", "https://otter.ai"),
        ("Notion", "Wissensmanagement & Dokumentation", "https://www.notion.so"),
    ]
    cards = []
    for name, desc, url in tools:
        cards.append(
            f"<div class='card'><h4><a href='{url}' target='_blank' rel='noopener'>{name}</a></h4><p>{desc}</p></div>"
        )
    return "".join(cards) + f"<p class='stand'>Stand: {now_iso()}</p>"


def _fallback_foerderprogramme_html() -> str:
    """Generiert eine kurze Auflistung von Förderprogrammen.
    Diese Fallback‑Liste basiert auf öffentlich verfügbaren Programmen und dient der Illustration.
    """
    programmes = [
        ("Digital Jetzt", "Investitionszuschuss für KMU zur Digitalisierung", "https://www.bmwi.de", "laufend"),
        ("go-inno", "Beratungsförderung für Innovationsmanagement", "https://www.bmwi.de", "laufend"),
        ("KMU-innovativ", "Förderung von Forschungs‑ und Entwicklungsprojekten", "https://www.bmbf.de", "laufend"),
    ]
    rows = "<table class='compact'><thead><tr><th>Programm</th><th>Frist</th><th>Link</th></tr></thead><tbody>"
    for name, desc, url, deadline in programmes:
        rows += f"<tr><td>{name}</td><td>{deadline}</td><td><a href='{url}'>{url}</a></td></tr>"
    rows += "</tbody></table>"
    return rows + f"<p class='stand'>Stand: {now_iso()}</p>"


# -----------------------------------------------------------------------------
# Helper to generate report payload directly from a dictionary (not JSON file)
#
# In FastAPI, the questionnaire answers are passed as a dict.  The existing
# generate_report_payload() expects a path to briefing.json.  This helper
# constructs a Briefing instance from the provided dict and produces an
# equivalent payload.  The logic for business case, live add‑ins, compliance
# and benchmarks is reused from generate_report_payload().

def generate_report_payload_from_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Wie generate_report_payload(), aber Eingang ist ein dict statt JSON-Pfad."""
    # Instantiate Briefing from dict values
    b = Briefing(
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

    # Business Case
    invest = invest_from_bucket(b.investitionsbudget)
    annual_saving = 24000.0
    bc = BusinessCase(invest_eur=invest, annual_saving_eur=annual_saving, efficiency_gain_frac=0.40)

    # Live‑Add‑ins
    live = get_live_news_tools_funding(b)

    # Compliance Playbook
    playbook_html = render_compliance_playbook()

    # Benchmarks
    bm = load_benchmarks(b.branche)

    # Prompt sections: generiere via LLM (falls verfügbar) oder fallback
    ctx: Dict[str, Any] = {
        "heute": now_iso(),
        "branche": b.branche,
        "unternehmensgroesse": b.unternehmensgroesse,
        "bundesland": b.bundesland,
        "hauptleistung": b.hauptleistung,
        "jahresumsatz": b.jahresumsatz,
        "investitionsbudget": b.investitionsbudget,
        "ai_roadmap": b.ai_roadmap or "",
        "invest_eur": f"{bc.invest_eur:.0f}",
        "annual_saving_eur": f"{bc.annual_saving_eur:.0f}",
        "payback_months": f"{bc.payback_months:.1f}",
        "roi_year1_pct": f"{bc.roi_year1_pct}",
        "three_year_profit": f"{bc.three_year_profit}",
        "time_saved_hours_per_month": f"{bc.time_saved_hours_per_month}",
        "bench_digitalisierung": f"{bm.get('digitalisierung', 0):.2f}",
        "bench_automatisierung": f"{bm.get('automatisierung', 0):.2f}",
        "bench_compliance": f"{bm.get('compliance', 0):.2f}",
        "bench_prozessreife": f"{bm.get('prozessreife', 0):.2f}",
        "bench_innovation": f"{bm.get('innovation', 0):.2f}",
    }

    llm = OpenAIChat()
    sections: Dict[str, str] = {}
    if ENABLE_LLM_SECTIONS and llm.api_key:
        for sec in SECTION_FILES:
            sections[sec] = render_section_text(sec, b.lang, ctx, llm)
    else:
        # Fallback: generiere zentrale Sektionen manuell
        sections["executive_summary"] = _fallback_exec_summary(data, bc)
        sections["business"] = _fallback_business_html(bc)
        sections["persona"] = _fallback_persona_html(data)
        sections["quick_wins"] = _fallback_quick_wins_html()
        sections["recommendations"] = _fallback_recommendations_html()
        sections["roadmap"] = _fallback_roadmap_html()
        sections["risks"] = _fallback_risks_html()
        sections["compliance"] = _fallback_compliance_html()
        sections["praxisbeispiel"] = ""
        sections["coach"] = ""
        sections["vision"] = ""
        sections["gamechanger"] = ""
        sections["foerderprogramme"] = _fallback_foerderprogramme_html()
        sections["tools"] = _fallback_tools_html()

    # Farbpalette
    palette = {
        "primary_700": "#0B5FFF",
        "primary_500": "#1F7BFF",
        "primary_100": "#E8F0FF",
        "accent_700": "#D9480F",
        "accent_500": "#FB8C00",
        "accent_100": "#FFE8D6",
        "ok": "#12B886",
        "warn": "#F59F00",
        "err": "#E03131",
        "text": "#0F172A",
    }

    payload: Dict[str, Any] = {
        "meta": {
            "title": "Mehrwert im Wettbewerb durch KI",
            "created_at": now_iso(),
            "last_updated": now_iso(),
            "lang": b.lang,
            "branche": b.branche,
            "unternehmensgroesse": b.unternehmensgroesse,
            "bundesland": b.bundesland,
            "hauptleistung": b.hauptleistung,
        },
        "business_case": dataclasses.asdict(bc),
        "benchmarks": bm,
        "sections": sections,
        "live_addins": live,
        "compliance_playbook_html": playbook_html,
        "palette": palette,
    }
    return payload


# -----------------------------------------------------------------------------
# Templating / Context building
#
def _compute_scores(data: Dict[str, Any]) -> Tuple[int, int, int, int]:
    """Berechnet Balkenwerte für Readiness‑Profil.

    Aus den Eingabedaten werden vier Skalen zwischen 0 und 100 abgeleitet: 
    - gesamt (score_percent)
    - Effizienzpotenzial (kpi_efficiency)
    - Compliance-Reife (kpi_compliance)
    - Innovationskraft (kpi_innovation)

    :param data: Fragebogendaten
    :return: Tuple(score_percent, kpi_efficiency, kpi_compliance, kpi_innovation)
    """
    # Digitalisierung (0-10) → 0-100
    try:
        dig = float(data.get("digitalisierungsgrad", 0))
    except Exception:
        dig = 0.0
    score_percent = int(max(0, min(100, dig * 10)))

    # Automatisierungsgrad (string) auf Prozent mappen
    auto_map = {
        "sehr_hoch": 90,
        "eher_hoch": 75,
        "hoch": 80,
        "mittel": 50,
        "eher_gering": 30,
        "niedrig": 20,
        "gering": 30,
    }
    auto_str = str(data.get("automatisierungsgrad", "")).lower()
    kpi_efficiency = auto_map.get(auto_str, 60)

    # Compliance: aus Datenschutzstatus und datenschutzbeauftragter
    has_dpo = str(data.get("datenschutzbeauftragter", "")).lower() in {"ja", "extern"}
    has_gov = str(data.get("governance", "")).lower() in {"ja", "true", "1"}
    kpi_compliance = 80 if has_dpo and has_gov else 60

    # Innovation: aus Innovationskultur
    innov_map = {
        "sehr_offen": 90,
        "offen": 75,
        "neutral": 50,
        "begrenzt": 40,
        "verschlossen": 20,
    }
    innov_str = str(data.get("innovationskultur", "")).lower()
    kpi_innovation = innov_map.get(innov_str, 50)

    return score_percent, kpi_efficiency, kpi_compliance, kpi_innovation


def build_context_for_template(payload: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    """Baut den Kontext für das HTML‑Template auf.

    Kombiniert die generierten Sektionen, Live‑Add‑ins und KPIs mit zusätzlichen
    Feldern (Generation Timestamp, Labels).  Der zurückgegebene Kontext kann
    direkt mit jinja2 und pdf_template.html gerendert werden.

    :param payload: Ergebnis von generate_report_payload_from_dict
    :param data: Rohdaten des Formulars (für KPIs)
    :return: Kontext‑Dictionary
    """
    meta = payload.get("meta", {})
    sections = payload.get("sections", {})
    live = payload.get("live_addins", {})

    score_percent, kpi_efficiency, kpi_compliance, kpi_innovation = _compute_scores(data)

    context: Dict[str, Any] = {
        "meta": {
            "title": meta.get("title", "KI‑Status Report"),
            "subtitle": "KI‑Readiness & Business Case",  # generische Unterzeile
        },
        "generation_date": meta.get("created_at", now_iso()),
        "last_updated": meta.get("last_updated", now_iso()),
        "branche": meta.get("branche", ""),
        "company_size_label": meta.get("unternehmensgroesse", ""),
        "score_percent": score_percent,
        "kpi_efficiency": kpi_efficiency,
        "kpi_compliance": kpi_compliance,
        "kpi_innovation": kpi_innovation,
        # Sektionen (HTML)
        "exec_summary_html": sections.get("executive_summary", ""),
        "business_html": sections.get("business", ""),
        "persona_html": sections.get("persona", ""),
        "quick_wins_html": sections.get("quick_wins", ""),
        "recommendations_html": sections.get("recommendations", ""),
        "roadmap_html": sections.get("roadmap", ""),
        "risks_html": sections.get("risks", ""),
        "compliance_html": sections.get("compliance", payload.get("compliance_playbook_html", "")),
        "praxisbeispiel_html": sections.get("praxisbeispiel", ""),
        "coach_html": sections.get("coach", ""),
        "vision_html": sections.get("vision", ""),
        "gamechanger_html": sections.get("gamechanger", ""),
        # Live und Funding
        "news_html": live.get("news_html", ""),
        "tools_rich_html": live.get("tools_rich_html", ""),
        "funding_rich_html": live.get("funding_rich_html", ""),
        "funding_deadlines_html": live.get("funding_deadlines_html", ""),
        "foerderprogramme_html": sections.get("foerderprogramme", ""),
        "tools_html": sections.get("tools", ""),
        # Benchmarks (kompakte Darstellung): hier generieren wir einfache Tabelle
        "benchmarks_compact_html": "",
        # Palette (für spätere Verwendung)
        "palette": payload.get("palette", {}),
        # Footer
        "copyright_year": datetime.now().year,
        "feedback_link": "https://ki‑sicherheit.jetzt/feedback",
    }
    # optional: generiere eine kompakte Benchmark‑Tabelle wenn Benchmarks vorhanden sind
    bm = payload.get("benchmarks", {})
    if isinstance(bm, dict) and bm:
        rows = [["KPI", "Unser Wert", "Benchmark", "Δ"]]
        # unser Werte aus KPIs
        our = {
            "digitalisierung": score_percent / 10.0,
            "automatisierung": kpi_efficiency / 100.0,
            "compliance": kpi_compliance / 100.0,
            "innovation": kpi_innovation / 100.0,
        }
        for key, bench_val in bm.items():
            our_val = our.get(key, None)
            if our_val is not None:
                delta = (our_val - float(bench_val)) * 100.0 if bench_val else 0.0
                rows.append([
                    key.capitalize(),
                    f"{our_val*100:.1f}%", 
                    f"{float(bench_val)*100:.1f}%", 
                    f"{delta:+.1f}%"
                ])
        # Build table HTML
        table_html = "<table class='compact'><thead><tr>" + "".join(f"<th>{c}</th>" for c in rows[0]) + "</tr></thead><tbody>"
        for r in rows[1:]:
            table_html += "<tr>" + "".join(f"<td>{v}</td>" for v in r) + "</tr>"
        table_html += "</tbody></table>"
        context["benchmarks_compact_html"] = table_html + f"<p class='stand'>Stand: {now_iso()}</p>"

    return context


# -----------------------------------------------------------------------------
# analyze_briefing / analyze_briefing_enhanced
#
def analyze_briefing(form_data: Dict[str, Any], lang: str = "de") -> str:
    """Generiert das HTML für den KI‑Status‑Report.

    Diese Funktion wird vom FastAPI‑Endpoint /briefing_async aufgerufen.  Sie
    kombiniert die Fragebogendaten mit Benchmarks, Business Case, Live‑Add‑ins
    und Compliance‑Playbook, berechnet einfache Heuristiken für KPIs und
    rendert die HTML‑Vorlage mit jinja2.  Das Ergebnis kann direkt an einen
    PDF‑Service gesendet werden.

    :param form_data: Formularinhalte aus dem Frontend
    :param lang: Sprachcode ("de" oder "en")
    :return: vollständiges HTML
    """
    # Erzeuge payload aus den rohen Daten
    payload = generate_report_payload_from_dict(form_data)
    # Baue Kontext für das Template
    context = build_context_for_template(payload, form_data)
    # Template auswählen (Deutsch oder Englisch)
    template_dir = Path(os.getenv("TEMPLATE_DIR", "project/make-ki-backend-neu-main/templates")).resolve()
    template_name = os.getenv("TEMPLATE_DE", "pdf_template.html") if (lang or "de").lower().startswith("de") else os.getenv("TEMPLATE_EN", "pdf_template_en.html")
    template_path = template_dir / template_name
    # Fallback falls Vorlagendatei nicht existiert
    if not template_path.exists():
        logger.warning("Template %s nicht gefunden – fallback auf inline", template_path)
        # Einfaches Fallback mit minimaler Struktur
        html = ["<html><head><meta charset='utf-8'><title>KI‑Status Report</title></head><body>"]
        html.append(f"<h1>{context['meta']['title']}</h1>")
        html.append(f"<h2>Executive Summary</h2>{context['exec_summary_html']}")
        html.append(f"<h2>Business Case</h2>{context['business_html']}")
        html.append(f"<h2>Compliance</h2>{context['compliance_html']}")
        html.append("</body></html>")
        return "".join(html)
    # Verwende jinja2 zum Rendern
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
        env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(["html", "xml"]),
        )
        tmpl = env.get_template(template_name)
        rendered: str = tmpl.render(**context)
        return rendered
    except Exception as exc:
        logger.error("Template rendering failed: %s", exc)
        # Fallback auf einfache Ausgabe
        html = ["<html><head><meta charset='utf-8'><title>KI‑Status Report</title></head><body>"]
        html.append(f"<h1>{context['meta']['title']}</h1>")
        for key, val in context.items():
            if key.endswith('_html'):
                html.append(f"<h2>{key.replace('_html','').replace('_',' ').title()}</h2>{val}")
        html.append("</body></html>")
        return "".join(html)


def analyze_briefing_enhanced(form_data: Dict[str, Any], lang: str = "de") -> Dict[str, Any]:
    """Erzeugt einen Kontext für Qualitätskontrolle und Post‑Processing.

    Anders als analyze_briefing liefert diese Funktion ein Dictionary mit allen
    relevanten Inhalten (HTML‑Sektionen, KPI‑Werten, Live‑Blöcken).  Dieses
    Format wird von quality_control.py und enhanced_main_integration.py
    erwartet.  Es enthält die gleichen Felder wie das Template‑Kontext, aber
    strukturiert, damit Tests und Verbesserungen darauf zugreifen können.

    :param form_data: Formularinhalte
    :param lang: Sprachcode
    :return: Kontext‑Dictionary
    """
    payload = generate_report_payload_from_dict(form_data)
    context = build_context_for_template(payload, form_data)
    # Richte Felder ein, die Quality Control erwartet
    qc_context: Dict[str, Any] = {
        "exec_summary_html": context.get("exec_summary_html", ""),
        "business_html": context.get("business_html", ""),
        "persona_html": context.get("persona_html", ""),
        "quick_wins_html": context.get("quick_wins_html", ""),
        "recommendations_html": context.get("recommendations_html", ""),
        "roadmap_html": context.get("roadmap_html", ""),
        "risks_html": context.get("risks_html", ""),
        "compliance_html": context.get("compliance_html", ""),
        "praxisbeispiel_html": context.get("praxisbeispiel_html", ""),
        "coach_html": context.get("coach_html", ""),
        "vision_html": context.get("vision_html", ""),
        "gamechanger_html": context.get("gamechanger_html", ""),
        "benchmarks_compact_html": context.get("benchmarks_compact_html", ""),
        "news_html": context.get("news_html", ""),
        "tools_rich_html": context.get("tools_rich_html", ""),
        "funding_rich_html": context.get("funding_rich_html", ""),
        "funding_deadlines_html": context.get("funding_deadlines_html", ""),
        "foerderprogramme_html": context.get("foerderprogramme_html", ""),
        "tools_html": context.get("tools_html", ""),
        # KPIs
        "score_percent": context.get("score_percent", 0),
        "kpi_efficiency": context.get("kpi_efficiency", 0),
        "kpi_compliance": context.get("kpi_compliance", 0),
        "kpi_innovation": context.get("kpi_innovation", 0),
        # Compliance relevance
        "datenschutzbeauftragter": form_data.get("datenschutzbeauftragter"),
        "datenschutz": bool(form_data.get("datenschutz")),
        # Business numbers for QC
        "roi_investment": payload["business_case"].get("invest_eur", 0),
        "roi_annual_saving": payload["business_case"].get("annual_saving_eur", 0),
        "benchmarks": payload.get("benchmarks", {}),
    }
    # Füge meta hinzu
    qc_context["meta"] = {
        "generated_at": payload["meta"].get("created_at", now_iso()),
        "last_updated": payload["meta"].get("last_updated", now_iso()),
        "lang": payload["meta"].get("lang", "de"),
        "branche": payload["meta"].get("branche", ""),
        "unternehmensgroesse": payload["meta"].get("unternehmensgroesse", ""),
        "bundesland": payload["meta"].get("bundesland", ""),
        "hauptleistung": payload["meta"].get("hauptleistung", ""),
    }
    return qc_context


# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------
def now_iso() -> str:
    return datetime.now().date().isoformat()


def load_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def map_region_code(bundesland: str) -> str:
    m = {"by": "BY", "be": "BE", "bw": "BW", "bundesweit": "DE", "deutschland": "DE"}
    return m.get((bundesland or "").lower(), "DE")


def invest_from_bucket(bucket: str) -> float:
    m = {
        "unter_1000": 500.0,
        "1000_2000": 1500.0,
        "2000_10000": 6000.0,
        "ueber_10000": 12000.0,
    }
    return m.get((bucket or "").lower(), 6000.0)


def flatten(d: Dict[str, Any], prefix: str = "", sep: str = ".") -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in d.items():
        key = f"{prefix}{sep}{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flatten(v, key, sep))
        else:
            out[key] = v
    return out


def fill_placeholders(tpl: str, ctx: Dict[str, Any]) -> str:
    for k, v in ctx.items():
        tpl = tpl.replace("{{" + k + "}}", str(v))
    return tpl


# -----------------------------------------------------------------------------
# LLM Client (OpenAI via httpx; robustes Fallback auf anderes Modell)
# -----------------------------------------------------------------------------
class OpenAIChat:
    def __init__(self, api_key: Optional[str] = None, model: str = GPT_MODEL_NAME):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model

    def chat(self, system: str, user: str, temperature: float = GPT_TEMPERATURE) -> str:
        if not self.api_key:
            logger.warning("OPENAI_API_KEY fehlt – LLM-Aufruf wird übersprungen.")
            return ""
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        body = {
            "model": self.model,
            "temperature": max(0.0, min(1.0, float(temperature))),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        try:
            with httpx.Client(timeout=30.0) as client:
                r = client.post(url, headers=headers, json=body)
                r.raise_for_status()
                data = r.json()
                return data["choices"][0]["message"]["content"]
        except Exception as ex:  # pragma: no cover
            logger.error("OpenAI chat failed (%s) – versuche Fallback: %s", ex, OPENAI_FALLBACK_MODEL)
            if OPENAI_FALLBACK_MODEL and OPENAI_FALLBACK_MODEL != self.model:
                self.model = OPENAI_FALLBACK_MODEL
                return self.chat(system, user, temperature)
            return ""


# -----------------------------------------------------------------------------
# Live Content (News/Tools/Funding)
# -----------------------------------------------------------------------------
def build_queries(b: Briefing) -> Dict[str, Any]:
    """Kombiniert Branche × Unternehmensgröße × Hauptleistung × Bundesland."""
    size_token = {
        "solo": "Solo",
        "freiberuflich": "Solo",
        "2–10": "Kleines Team",
        "2-10": "Kleines Team",
        "11–100": "KMU",
        "11-100": "KMU",
        "kmu": "KMU",
    }
    size = size_token.get((b.unternehmensgroesse or "").lower(), b.unternehmensgroesse)
    qs_base = f'{b.branche} "{b.hauptleistung}" {size} KI Automatisierung {b.bundesland.upper()}'
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
            f"Förderung Digitalisierung {b.bundesland.upper()} {b.branche} {size}",
            f"Förderprogramm KI {b.bundesland.upper()} Deadline {b.branche}",
        ],
        "domain_whitelist": BUNDESLAND_DOMAIN_WHITELIST.get((b.bundesland or "").lower(), ["bmwk.de", "europa.eu", "ihk.de"]),
    }


def _cards(items: List[Dict[str, str]], tag: str) -> str:
    html: List[str] = []
    for it in items[:SEARCH_MAX_RESULTS]:
        title = it.get("title") or it.get("name") or "Unbenannter Eintrag"
        url = it.get("url") or it.get("link") or "#"
        date = it.get("published") or it.get("date") or ""
        snippet = (it.get("snippet") or it.get("summary") or it.get("description") or "").strip()
        html.append(
            f'<div class="card"><div class="card-tag">{tag}</div>'
            f'<div class="card-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></div>'
            f'<div class="card-meta">{date}</div><div class="card-body">{snippet}</div></div>'
        )
    return "\n".join(html)


def get_live_news_tools_funding(b: Briefing) -> Dict[str, str]:
    """Rendert HTML-Karten für News/Tools/Förderungen/EU-Calls."""
    q = build_queries(b)

    # Tavily – News & Tools (jeweils mit Domain-Whitelist)
    news_hits: List[Dict[str, str]] = []
    for qn in q["news"]:
        news_hits += tavily_search(qn, days=max(7, SEARCH_DAYS), include_domains=q["domain_whitelist"], max_results=SEARCH_MAX_RESULTS)

    tools_hits: List[Dict[str, str]] = []
    for qt in q["tools"]:
        tools_hits += tavily_search(qt, days=max(30, SEARCH_DAYS_TOOLS), include_domains=q["domain_whitelist"], max_results=SEARCH_MAX_RESULTS)

    # Förderprogramme – CSV (normalisiert) + optionale EU-Calls (Funding & Tenders)
    funding_rows = load_csv(DATA_DIR / "foerderprogramme.csv")
    region_code = map_region_code(b.bundesland)
    funding_rows = [r for r in funding_rows if (r.get("Region_Code", "DE") in (region_code, "DE"))]
    funding_cards = []
    for r in funding_rows[:SEARCH_MAX_RESULTS]:
        title = r.get("Programmname", "Programm")
        url = r.get("Website", "#")
        quote = r.get("Foerderquote_prozent", "")
        if isinstance(quote, str) and quote.endswith("%"):
            quote = quote[:-1]
        deadline = r.get("Deadline", "rolling")
        status = r.get("Status", "offen")
        funding_cards.append(
            f'<div class="card"><div class="card-tag">Förderung</div>'
            f'<div class="card-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></div>'
            f'<div class="card-meta">Quote: {quote}% · Deadline: {deadline} · Status: {status}</div></div>'
        )

    eu_calls: List[Dict[str, str]] = []
    try:
        eu_calls = funding_tenders_search(f'AI OR "artificial intelligence" {b.branche}', from_days=max(60, SEARCH_DAYS_FUNDING))
    except Exception as e:  # pragma: no cover
        logger.warning("EU funding_tenders_search failed: %s", e)

    return {
        "news_html": f'<section><h3>Aktuelle Meldungen (Stand: {now_iso()})</h3>{_cards(news_hits, "News")}</section>',
        "tools_rich_html": f'<section><h3>Neue Tools & Releases (Stand: {now_iso()})</h3>{_cards(tools_hits, "Tool/Release")}</section>',
        "funding_rich_html": f'<section><h3>Förderprogramme (Stand: {now_iso()})</h3>{"".join(funding_cards)}</section>',
        "funding_deadlines_html": f'<section><h3>EU‑Calls (letzte 60 Tage)</h3>{_cards(eu_calls, "EU‑Call")}</section>',
    }


# -----------------------------------------------------------------------------
# Compliance-Playbook – Klartext (aus Governance-Notiz integriert)
# -----------------------------------------------------------------------------
def render_compliance_playbook() -> str:
    return f"""
<section>
  <h3>Compliance‑Playbook (Go‑Live‑Gate & Betrieb)</h3>
  <ol>
    <li><strong>Go‑Live‑Gate & Minimal Viable Compliance (MVC):</strong> Vor der Produktivsetzung Nachweise zu Risikoklasse, DPA/AVV, Rechtekette, Tests (Performance/Drift/Bias) sowie klaren Rollen/Verantwortlichkeiten.</li>
    <li><strong>Human‑in‑the‑Loop & Kill‑Switch:</strong> Kritische Entscheidungen bleiben beim Menschen; dokumentierter Not‑Aus mit Rückfallebene.</li>
    <li><strong>Input‑/Output‑Gates:</strong> Rechtekette & Datenbasis (Input) prüfen; Ausgaben auf Halluzinationen/IP/DSGVO/Policy (Output) prüfen; beide Prüfungen als verpflichtende Prozess‑Gates.</li>
    <li><strong>Re‑Klassifizierungs‑Trigger:</strong> Fine‑Tuning, Zweck‑/Brandenwechsel (White‑Label), autonome Agenten → Pflichten neu bewerten.</li>
    <li><strong>Rechtslandkarte:</strong> Neben KI‑VO auch Produkt‑ & Sektorrecht, Cyber Resilience Act, Digital Services Act und Data Act integrieren; Verantwortliche & Nachweise benennen.</li>
    <li><strong>AI‑Literacy:</strong> Pflichttrainings mit jährlicher Auffrischung; Zugriffsrechte an Schulungsstand koppeln.</li>
    <li><strong>Monitoring & Re‑Tests:</strong> Technologieradar; periodische Re‑Tests (Performance/Drift/Bias); Ergebnisse in Standards/Modelle zurückspielen.</li>
  </ol>
  <p class="stand">Stand: {now_iso()}</p>
</section>
"""


# -----------------------------------------------------------------------------
# Benchmarks
# -----------------------------------------------------------------------------
DEFAULT_BENCHMARKS_BERATUNG = {
    "digitalisierung": 7.5,
    "automatisierung": 0.65,
    "compliance": 0.73,
    "prozessreife": 0.68,
    "innovation": 0.60,
}


def load_benchmarks(branche: str) -> Dict[str, float]:
    """
    Lädt branchenspezifische Benchmarks:
    - data/benchmarks_catalog.json (falls vorhanden, nach Branche auflösen)
    - Fallback: data/benchmarks_beratung_kmu.json (bestehende Datei)
    - Not‑Fallback: DEFAULT_BENCHMARKS_BERATUNG
    """
    # Katalog (mehrere Branchen)
    catalog = load_json(DATA_DIR / "benchmarks_catalog.json", default=None)
    if isinstance(catalog, dict):
        key = (branche or "").strip().lower()
        if key in catalog and isinstance(catalog[key], dict):
            return catalog[key]

    # Bestehende Datei (Beratung)
    fallback_file = DATA_DIR / "benchmarks_beratung_kmu.json"
    fb = load_json(fallback_file, default=None)
    if isinstance(fb, dict):
        # akzeptiere beide Formate (reiner KPI-Block oder komplettes Objekt)
        if "kpis" in fb and isinstance(fb["kpis"], list):
            # in einfachem Dict zusammenfassen
            out: Dict[str, float] = {}
            for kpi in fb["kpis"]:
                n = (kpi.get("name") or "").lower()
                v = kpi.get("value")
                if n and isinstance(v, (int, float)):
                    # grobe Zuordnung
                    if "digital" in n:
                        out["digitalisierung"] = float(v) if v <= 10 else float(v) / 10.0
                    elif "automatis" in n:
                        out["automatisierung"] = float(v)
                    elif "fehler" in n or "compl" in n:
                        out["compliance"] = float(v) if v <= 1 else float(v) / 100.0
            return {**DEFAULT_BENCHMARKS_BERATUNG, **out}
        if all(isinstance(v, (int, float)) for v in fb.values()):
            return fb  # bereits im gewünschten Format

    # Not-Fallback
    return DEFAULT_BENCHMARKS_BERATUNG


# -----------------------------------------------------------------------------
# Prompt-Engine
# -----------------------------------------------------------------------------
SECTION_FILES = [
    "executive_summary",
    "business",
    "persona",
    "quick_wins",
    "risks",
    "recommendations",
    "roadmap",
    "praxisbeispiel",
    "coach",
    "vision",
    "gamechanger",
    "compliance",
    "foerderprogramme",
    "tools",
]

SYSTEM_PROMPT = (
    "You are a senior management consultant & AI governance expert. "
    "Write concise, evidence-based, implementation-ready content. "
    "Be motivating but never salesy. Use clear German if lang=de, otherwise clear English. "
    "Use only the given context; if unsure, say so. Keep tables narrow; include explicit source links. "
    "Always include an 'Letzte Aktualisierung' line with ISO date."
)


def render_section_text(section: str, lang: str, ctx: Dict[str, Any], llm: OpenAIChat) -> str:
    prompt_file = PROMPTS_DIR / f"{section}_{lang}.md"
    # Fallback auf Englisch, falls DE fehlt
    if not prompt_file.exists():
        alt = PROMPTS_DIR / f"{section}_en.md"
        prompt_file = alt if alt.exists() else prompt_file
    prompt_raw = load_text(prompt_file)
    if not prompt_raw:
        logger.warning("Promptdatei fehlt: %s", prompt_file)
        return ""
    user_prompt = fill_placeholders(prompt_raw, ctx)
    logger.info("Prompt resolved: %s -> %s (md-plain)", section, prompt_file.name)
    return llm.chat(SYSTEM_PROMPT, user_prompt, GPT_TEMPERATURE)


# -----------------------------------------------------------------------------
# Hauptfunktion
# -----------------------------------------------------------------------------
def generate_report_payload(briefing_json_path: Path) -> Dict[str, Any]:
    logger.info("OpenAI Client initialisiert")
    b = Briefing.from_json(briefing_json_path)
    logger.info("Briefing geladen: %s", b)

    # Business Case – Grundannahmen (Budget aus Bucket ableiten)
    invest = invest_from_bucket(b.investitionsbudget)
    annual_saving = 24000.0  # kann via Prompt überschrieben/verfeinert werden
    bc = BusinessCase(invest_eur=invest, annual_saving_eur=annual_saving, efficiency_gain_frac=0.40)

    # Live‑Add‑ins (News/Tools/Förderungen)
    live = get_live_news_tools_funding(b)

    # Compliance‑Playbook (HTML)
    playbook_html = render_compliance_playbook()

    # Benchmarks (Branche)
    bm = load_benchmarks(b.branche)

    # Kontext für Prompts
    ctx: Dict[str, Any] = {
        "heute": now_iso(),
        "branche": b.branche,
        "unternehmensgroesse": b.unternehmensgroesse,
        "bundesland": b.bundesland,
        "hauptleistung": b.hauptleistung,
        "jahresumsatz": b.jahresumsatz,
        "investitionsbudget": b.investitionsbudget,
        "ai_roadmap": b.ai_roadmap or "",
        # Business Case
        "invest_eur": f"{bc.invest_eur:.0f}",
        "annual_saving_eur": f"{bc.annual_saving_eur:.0f}",
        "payback_months": f"{bc.payback_months:.1f}",
        "roi_year1_pct": f"{bc.roi_year1_pct}",
        "three_year_profit": f"{bc.three_year_profit}",
        "time_saved_hours_per_month": f"{bc.time_saved_hours_per_month}",
        # Benchmarks
        "bench_digitalisierung": f"{bm.get('digitalisierung', 0):.2f}",
        "bench_automatisierung": f"{bm.get('automatisierung', 0):.2f}",
        "bench_compliance": f"{bm.get('compliance', 0):.2f}",
        "bench_prozessreife": f"{bm.get('prozessreife', 0):.2f}",
        "bench_innovation": f"{bm.get('innovation', 0):.2f}",
    }

    # LLM – Sektionen generieren
    llm = OpenAIChat()
    sections: Dict[str, str] = {}
    if ENABLE_LLM_SECTIONS:
        for sec in SECTION_FILES:
            sections[sec] = render_section_text(sec, b.lang, ctx, llm)
    else:
        sections = {sec: "" for sec in SECTION_FILES}

    # Farbpalette (Blau + Orange) – von Templates konsumiert
    palette = {
        "primary_700": "#0B5FFF",
        "primary_500": "#1F7BFF",
        "primary_100": "#E8F0FF",
        "accent_700": "#D9480F",
        "accent_500": "#FB8C00",
        "accent_100": "#FFE8D6",
        "ok": "#12B886",
        "warn": "#F59F00",
        "err": "#E03131",
        "text": "#0F172A",
    }

    payload: Dict[str, Any] = {
        "meta": {
            "title": "Mehrwert im Wettbewerb durch KI",
            "created_at": now_iso(),
            "last_updated": now_iso(),
            "lang": b.lang,
            "branche": b.branche,
            "unternehmensgroesse": b.unternehmensgroesse,
            "bundesland": b.bundesland,
            "hauptleistung": b.hauptleistung,
        },
        "business_case": dataclasses.asdict(bc),
        "benchmarks": bm,
        "sections": sections,
        "live_addins": live,
        "compliance_playbook_html": playbook_html,
        "palette": palette,
    }
    logger.info("Payload fertig (Sektionen: %s)", list(sections.keys()))
    return payload


# Optional: manuelles Testen lokal
if __name__ == "__main__":  # pragma: no cover
    example = Path("briefing.json")
    if example.exists():
        pld = generate_report_payload(example)
        print(json.dumps(pld.keys(), indent=2, ensure_ascii=False))
    else:
        print("briefing.json nicht gefunden.")
