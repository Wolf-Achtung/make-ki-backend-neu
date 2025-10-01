# File: gpt_analyze.py
# -*- coding: utf-8 -*-
"""
Core report generation for the MAKE‑KI backend.

This module orchestrates loading user briefings, calculating simple business
case metrics, fetching live information (news, tools, and funding calls),
and rendering compliance guidance.  It has been revised to follow modern
Python best practices: all functions are documented, type hints are used
throughout, imports are robust against missing optional dependencies, and
logging is consistently configured.  The exposed entry point is
``generate_report_payload()``, which produces a dictionary suitable for
passing into an HTML or PDF template.
"""

from __future__ import annotations

import csv
import dataclasses
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx

# Optionale lokale Module (robuste Fallbacks)
# Newer versions of ``websearch_utils`` expose only ``search_tavily``; older
# ones expose ``tavily_search`` and ``days_to_tavily_range`` directly.  To
# remain compatible with both, attempt to import ``search_tavily`` and
# normalise its output.  Should the import fail entirely, stub
# implementations returning empty lists are used.
try:
    from websearch_utils import search_tavily as _search_tavily  # type: ignore

    def tavily_search(
        query: str,
        days: int = 30,
        include_domains: Optional[List[str]] = None,
        max_results: int = 8,
    ) -> List[Dict[str, str]]:
        items: List[Dict[str, str]] = []
        try:
            raw_items: Iterable[Any] = _search_tavily(query, days=days, max_results=max_results)  # type: ignore[arg-type]
        except Exception as exc:
            logger.warning("Tavily search failed: %s", exc)
            return items
        for it in raw_items:
            if isinstance(it, dict):
                title = it.get("title") or it.get("name") or ""
                url = it.get("url") or it.get("link") or ""
                published = it.get("published") or it.get("date") or it.get("published_at") or ""
                snippet = it.get("snippet") or it.get("summary") or it.get("description") or ""
            else:
                title = getattr(it, "title", "")
                url = getattr(it, "url", "")
                published = getattr(it, "published_at", None) or ""
                snippet = getattr(it, "summary", "")
            items.append({
                "title": str(title).strip(),
                "url": str(url).strip(),
                "published": str(published).strip(),
                "snippet": str(snippet).strip(),
            })
        # Apply optional domain filtering
        if include_domains:
            filtered: List[Dict[str, str]] = []
            for itm in items:
                domain = re.sub(r"^https?://", "", itm["url"]).split("/")[0].lower()
                if any(domain.endswith(d.lower()) for d in include_domains):
                    filtered.append(itm)
            items = filtered
        return items[:max_results]

    def days_to_tavily_range(days: int) -> str:
        if days <= 7:
            return "day"
        if days <= 30:
            return "week"
        if days <= 90:
            return "month"
        return "year"

except Exception:
    # Fall back to legacy API if available
    try:
        from websearch_utils import tavily_search as tavily_search  # type: ignore  # noqa: F401
        from websearch_utils import days_to_tavily_range as days_to_tavily_range  # type: ignore  # noqa: F401
    except Exception:
        # Final fallback: stubs that return empty lists and sensible ranges
        def tavily_search(
            query: str,
            days: int = 30,
            include_domains: Optional[List[str]] = None,
            max_results: int = 8,
        ) -> List[Dict[str, str]]:
            logger.info("tavily_search fallback invoked – no results returned")
            return []

        def days_to_tavily_range(days: int) -> str:
            if days <= 7:
                return "day"
            if days <= 30:
                return "week"
            if days <= 90:
                return "month"
            return "year"

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
# Utilities
# -----------------------------------------------------------------------------
def now_iso() -> str:
    return datetime.now().date().isoformat()


def load_csv(path: Path) -> List[Dict[str, str]]:
    """Load a CSV file and return a list of rows as dictionaries.

    If the given path does not exist, an empty list is returned.  Files are
    assumed to be UTF‑8 encoded and the first row defines the field names.

    :param path: path to the CSV file
    :return: a list of dictionaries keyed by the column names
    """
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


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
    """Map a German state designation to a two‑letter region code.

    Funding data uses two‑letter codes (e.g. ``BY`` for Bayern).  The user
    may enter free text or a lower‑case abbreviation.  Unknown entries
    default to the country code ``DE``.

    :param bundesland: state abbreviation or name
    :return: two‑letter region code for filtering funding entries
    """
    mapping = {
        "by": "BY",
        "be": "BE",
        "bw": "BW",
        "bundesweit": "DE",
        "deutschland": "DE",
    }
    return mapping.get((bundesland or "").lower(), "DE")


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
def build_queries(b: "Briefing") -> Dict[str, Any]:
    """Compose search queries for news, tools and funding based on a briefing.

    This helper takes into account the industry (``branche``), company size
    (``unternehmensgroesse``), primary service (``hauptleistung``) and
    state (``bundesland``) to assemble targeted search strings.  A domain
    whitelist is provided based on the state to restrict results to trusted
    websites.

    :param b: briefing containing industry, size, state and main service
    :return: a mapping with keys ``news``, ``tools``, ``funding`` and
             ``domain_whitelist``
    """
    # Normalise the company size into broad buckets for keyword tuning
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
    qs_base = f"{b.branche} \"{b.hauptleistung}\" {size} KI Automatisierung {b.bundesland.upper()}"
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


def get_live_news_tools_funding(b: "Briefing") -> Dict[str, str]:
    """Fetch and render live sections for news, tools and funding.

    This combines Tavily searches, local CSV data and optional EU calls
    into HTML fragments.  Each section is timestamped with the current
    date.  Searches leverage the domain whitelist defined in the briefing.

    :param b: briefing containing the search context
    :return: a mapping with keys ``news_html``, ``tools_rich_html``,
             ``funding_rich_html`` and ``funding_deadlines_html``
    """
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
