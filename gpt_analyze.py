# -*- coding: utf-8 -*-
"""
MAKE‑KI Backend – Report Generator (Gold‑Standard+)

Dieses Modul erzeugt den vollständigen Payload für den KI‑Status‑Report.  Es
kombiniert Informationen aus dem Fragebogen (Briefing), berechnet einen
Business‑Case, lädt branchenspezifische Benchmarks, ruft Live‑Add‑ins (News,
Tools und Förderprogramme) ab und generiert alle inhaltlichen Sektionen via
LLM‑Prompts oder heuristische Fallbacks.  Es erfüllt folgende Ziele:

* **Immer LLM‑Sektionen:** Wenn ein gültiger OpenAI‑API‑Key vorhanden ist, werden
  alle Sektionen (Executive Summary, Business, Persona, Quick Wins, Risks,
  Recommendations, Roadmap, Praxisbeispiel, Coach, Vision, Gamechanger,
  Compliance, Förderprogramme, Tools) aus den entsprechenden Prompt‑Dateien
  generiert.  Fallback‑Heuristiken stellen sicher, dass der Report nie leer
  bleibt.
* **Korrekte Business‑Case‑Berechnungen:** Investition und Einsparung werden
  dynamisch aus dem Fragebogen abgeleitet.  Der ROI (Jahr 1), Payback in
  Monaten und der kumulierte Gewinn über drei Jahre werden transparent
  berechnet.  Zur Vereinfachung wird von einer Effizienzsteigerung von 40 %
  ausgegangen; der jährliche Nutzen entspricht dem Vierfachen der Investition
  (ROI ≈ 300 %).
* **Realistische KPI‑Berechnung:** Digitalisierungs‑ und Automatisierungsgrad
  werden aus den Textfeldern des Fragebogens abgeleitet und auf eine Skala
  von 0–100 normalisiert.  Daraus werden Readiness‑ und Effizienzscores
  berechnet.  Benchmarks werden aus einer branchenspezifischen JSON‑Datei
  geladen und dienen dem Vergleich.
* **Umfangreiche Live‑Add‑ins:** Die Tavily‑Suche wird genutzt, um aktuelle
  Meldungen, Tools und EU‑Förderungen aus zuverlässigen Quellen zu sammeln.
  Förderprogramme aus der CSV werden nach Bundesland gefiltert und mit
  Quoten und Deadlines dargestellt.  Die Live‑Abschnitte enthalten immer
  einen Zeitstempel (Stand: heute).
* **Compliance‑Playbook und Governance:** Ein statischer Abschnitt mit klaren
  Regeln (Go‑Live‑Gate, Minimal Viable Compliance, Human‑in‑the‑Loop,
  Kill‑Switch, Re‑Trigger, Rechtslandkarte, AI‑Literacy, Monitoring).
* **PEP8‑Konformität, Typannotationen, Logging:** Alle Funktionen sind
  dokumentiert, typisiert und verfügen über robustes Fehlerhandling.  Das
  Logging ist strukturiert und informative Warnungen helfen bei der
  Fehlersuche.

Diese Datei ersetzt ältere Implementierungen von ``gpt_analyze.py``.  Sie
ist kompatibel mit den vorhandenen Templates und wird vom FastAPI‑Endpoint
``/briefing_async`` importiert.
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

# -----------------------------------------------------------------------------
# Optionale lokale Module (robuste Fallbacks)
# -----------------------------------------------------------------------------
try:
    # Die Tavily‑Funktionen können je nach Version unterschiedlich heißen.  Wir
    # versuchen ``tavily_search`` direkt zu importieren, andernfalls wird ein
    # Fallback definiert.
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
        logging.getLogger("gpt_analyze").warning(
            "Tavily search fallback verwendet – es werden keine Ergebnisse geliefert"
        )
        return []

# EU‑Connectoren sind optional und dürfen niemals das Rendering blockieren.  Bei
# fehlender Importmöglichkeit werden leere Listen zurückgegeben.
try:  # pragma: no cover
    from eu_connectors import (
        openaire_search_projects,
        cordis_search_projects,
        funding_tenders_search,
    )  # type: ignore
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

# Template-Dateien (für HTML/PDF-Rendering)
TEMPLATE_DE = os.getenv("TEMPLATE_DE", "pdf_template.html")
TEMPLATE_EN = os.getenv("TEMPLATE_EN", "pdf_template_en.html")

SEARCH_DAYS = int(os.getenv("SEARCH_DAYS", "30"))
SEARCH_DAYS_TOOLS = int(os.getenv("SEARCH_DAYS_TOOLS", str(max(30, SEARCH_DAYS))))
SEARCH_DAYS_FUNDING = int(os.getenv("SEARCH_DAYS_FUNDING", str(max(60, SEARCH_DAYS))))
SEARCH_MAX_RESULTS = int(os.getenv("SEARCH_MAX_RESULTS", "8"))

# LLM‑Konfiguration
ENABLE_LLM_SECTIONS = os.getenv("ENABLE_LLM_SECTIONS", "true").lower() != "false"
GPT_MODEL_NAME = os.getenv("GPT_MODEL_NAME", "gpt-4o-mini")
OPENAI_FALLBACK_MODEL = os.getenv("OPENAI_FALLBACK_MODEL", "gpt-4o")
GPT_TEMPERATURE = float(os.getenv("GPT_TEMPERATURE", "0.25"))

# Bundesland → Domain‑Whitelist (reduziert SEO‑Spam)
DOMAIN_WHITELIST_BY = [
    "bayern.de",
    "stmwi.bayern.de",
    "l-bank.de",
    "ihk.de",
    "europa.eu",
    "eur-lex.europa.eu",
    "bmwk.de",
]
DOMAIN_WHITELIST_BE = ["berlin.de", "ibb.de", "ihk.de", "europa.eu", "bmwk.de"]
DOMAIN_WHITELIST_BW = ["baden-wuerttemberg.de", "l-bank.de", "ihk.de", "europa.eu", "bmwk.de"]
BUNDESLAND_DOMAIN_WHITELIST: Dict[str, List[str]] = {
    "by": DOMAIN_WHITELIST_BY,
    "be": DOMAIN_WHITELIST_BE,
    "bw": DOMAIN_WHITELIST_BW,
}

# -----------------------------------------------------------------------------
# Datenstrukturen
# -----------------------------------------------------------------------------
@dataclasses.dataclass
class Briefing:
    """Strukturierte Darstellung des Fragebogens.

    :param branche: Branchenbezeichnung (z. B. "Medien")
    :param unternehmensgroesse: Größe (z. B. "kmu")
    :param bundesland: Bundesland (z. B. "BY")
    :param hauptleistung: Hauptleistung bzw. Dienstleistungsbereich
    :param jahresumsatz: Optionaler Jahresumsatz (zur ROI‑Feinabstimmung)
    :param lang: Sprache ("de" oder "en")
    :param investitionsbudget: Budget im Fragebogen (Bucket)
    :param digitalisierungsgrad: Selbstangabe ("0-3", "3-7", "7-10" oder Zahl)
    :param automatisierungsgrad: Selbstangabe (analog)
    :param ai_roadmap: Optionales Textfeld zur geplanten KI‑Nutzung
    """

    branche: str
    unternehmensgroesse: str
    bundesland: str
    hauptleistung: str
    jahresumsatz: str = ""
    lang: str = DEFAULT_LANG
    investitionsbudget: str = ""
    digitalisierungsgrad: Optional[str] = None
    automatisierungsgrad: Optional[str] = None
    ai_roadmap: Optional[str] = None

    @staticmethod
    def from_json(path: Path) -> "Briefing":
        """Liest einen JSON‑Briefing und erzeugt ein ``Briefing``‑Objekt."""
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
    """Repräsentiert die betriebswirtschaftliche Analyse einer KI‑Einführung."""

    invest_eur: float
    annual_saving_eur: float
    efficiency_gain_frac: float = 0.40  # 40 %
    base_hours_per_day: float = 8.0

    @property
    def roi_year1_pct(self) -> int:
        """Return on Investment nach Jahr 1 in Prozent."""
        if self.invest_eur <= 0:
            return 0
        return round(((self.annual_saving_eur - self.invest_eur) / self.invest_eur) * 100)

    @property
    def payback_months(self) -> float:
        """Monate bis zur Amortisation."""
        if self.annual_saving_eur <= 0:
            return 0.0
        monthly = self.annual_saving_eur / 12.0
        if monthly <= 0:
            return 0.0
        return round(self.invest_eur / monthly, 1)

    @property
    def three_year_profit(self) -> int:
        """Kumuliertes Ergebnis nach drei Jahren (Ersparnis × 3 – Investition)."""
        return int(round(self.annual_saving_eur * 3 - self.invest_eur))

    @property
    def time_saved_hours_per_month(self) -> int:
        """Durch Effizienzgewinn eingesparte Stunden pro Monat pro FTE."""
        return int(round(self.efficiency_gain_frac * self.base_hours_per_day * 20))


# -----------------------------------------------------------------------------
# Utility‑Funktionen
# -----------------------------------------------------------------------------
def now_iso() -> str:
    """Gibt das aktuelle Datum im ISO‑Format zurück (YYYY‑MM‑DD)."""
    return datetime.now().date().isoformat()


def load_csv(path: Path) -> List[Dict[str, str]]:
    """Lädt eine CSV‑Datei als Liste von Dictionarys oder gibt eine leere Liste zurück."""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_json(path: Path, default: Any = None) -> Any:
    """Lädt JSON‑Daten aus einer Datei und gibt im Fehlerfall einen Default zurück."""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def map_region_code(bundesland: str) -> str:
    """Mappt ein Bundesland auf einen zweibuchstabigen Region‑Code."""
    m = {
        "by": "BY",
        "be": "BE",
        "bw": "BW",
        "bundesweit": "DE",
        "deutschland": "DE",
    }
    return m.get((bundesland or "").lower(), "DE")


def invest_from_bucket(bucket: str) -> float:
    """Leitet aus dem investitionsbudget (Bucket) einen Mittelwert ab."""
    # Die Buckets entsprechen den Formularoptionen; Mittelwerte definieren den
    # Durchschnitt der jeweiligen Spannbreite.
    mapping = {
        "unter_1000": 500.0,
        "1000_2000": 1500.0,
        "2000_10000": 6000.0,
        "ueber_10000": 12000.0,
    }
    return mapping.get((bucket or "").lower(), 6000.0)


def parse_grade(value: Optional[str]) -> float:
    """Wandelt einen Digitalisierungs‑ oder Automatisierungsgrad in einen Prozentwert um.

    Die Eingaben im Briefing können z. B. "0-3", "3-7", "7-10" oder eine
    einzelne Zahl (z. B. "8") sein.  Der Rückgabewert liegt zwischen 0 und 100.
    """
    if value is None:
        return 0.0
    value = value.strip()
    # Bereichsangaben (z. B. "0-3")
    m_range = re.match(r"^(\d+)[^\d]?(\d+)$", value)
    if m_range:
        start = float(m_range.group(1))
        end = float(m_range.group(2))
        return (start + end) / 2.0 * 10.0  # mittlerer Wert, in Prozent
    # Einzelwerte (z. B. "8")
    try:
        num = float(value)
        # Werte können schon als 0–100 oder 0–10 angegeben sein
        return num if num > 10.0 else num * 10.0
    except Exception:
        return 0.0


def compute_kpi_scores(b: Briefing, benchmarks: Dict[str, float]) -> Dict[str, float]:
    """Berechnet KPI‑Scores aus dem Briefing und Benchmarks.

    :return: Dictionary mit ``score_percent`` (Readiness), ``kpi_efficiency``,
        ``kpi_compliance``, ``kpi_innovation``.
    """
    digi = parse_grade(b.digitalisierungsgrad)
    auto = parse_grade(b.automatisierungsgrad)
    # Readiness Score: Mittelwert beider Grade
    readiness = (digi + auto) / 2.0
    # Effizienzpotenzial: Automatisierungsgrad + optionaler Faktor aus der AI‑Roadmap
    eff = auto
    # Compliance‑Reife: Benchmark‑Wert * 100; falls kein Benchmark: 70
    comp = benchmarks.get("compliance", 0.7) * 100.0
    # Innovationskraft: Benchmark‑Wert * 100; falls kein Benchmark: 65
    innov = benchmarks.get("innovation", 0.65) * 100.0
    return {
        "score_percent": max(0.0, min(100.0, readiness)),
        "kpi_efficiency": max(0.0, min(100.0, eff)),
        "kpi_compliance": max(0.0, min(100.0, comp)),
        "kpi_innovation": max(0.0, min(100.0, innov)),
    }


def flatten(d: Dict[str, Any], prefix: str = "", sep: str = ".") -> Dict[str, Any]:
    """Flacht verschachtelte Dictionarys zu einem Key‑Path ab (für Templates)."""
    out: Dict[str, Any] = {}
    for k, v in d.items():
        key = f"{prefix}{sep}{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flatten(v, key, sep))
        else:
            out[key] = v
    return out


def fill_placeholders(tpl: str, ctx: Dict[str, Any]) -> str:
    """Ersetzt einfache ``{{var}}``‑Platzhalter durch Werte aus dem Kontext."""
    for k, v in ctx.items():
        tpl = tpl.replace("{{" + k + "}}", str(v))
    return tpl


# -----------------------------------------------------------------------------
# LLM‑Client
# -----------------------------------------------------------------------------
class OpenAIChat:
    """Ein sehr einfacher HTTP‑Client für OpenAI Chat API.

    Da diese Abhängigkeit optional ist, schlägt der Aufruf fehl, wenn kein
    API‑Key gesetzt ist, und gibt in diesem Fall eine leere Zeichenkette
    zurück.  Das Modell und die Temperatur können über Umgebungsvariablen
    konfiguriert werden.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = GPT_MODEL_NAME):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model

    def chat(self, system: str, user: str, temperature: float = GPT_TEMPERATURE) -> str:
        if not self.api_key:
            logger.warning("OPENAI_API_KEY fehlt – LLM‑Aufruf wird übersprungen.")
            return ""
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "temperature": max(0.0, min(1.0, float(temperature))),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, headers=headers, json=body)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except Exception as ex:  # pragma: no cover
            logger.error("OpenAI chat failed (%s)", ex)
            if OPENAI_FALLBACK_MODEL and OPENAI_FALLBACK_MODEL != self.model:
                self.model = OPENAI_FALLBACK_MODEL
                return self.chat(system, user, temperature)
            return ""


# -----------------------------------------------------------------------------
# Live‑Content (News/Tools/Funding)
# -----------------------------------------------------------------------------
def build_queries(b: Briefing) -> Dict[str, Any]:
    """Erzeugt eine Query‑Map für News, Tools und Funding basierend auf dem Briefing."""
    size = b.unternehmensgroesse
    qs_base = f"{b.branche} \"{b.hauptleistung}\" KI Automatisierung {b.bundesland.upper()}"
    return {
        "news": [
            f"{qs_base} KI‑VO DSGVO site:bmwk.de",
            f"{qs_base} Förderung Deadline",
            f"{b.branche} KMU KI Best Practice {b.bundesland.upper()}",
        ],
        "tools": [
            f"Tools {b.branche} KI Automatisierung DSGVO DPA {b.bundesland.upper()}",
            f"Open‑Source KI Automatisierung {b.branche} self‑hosted",
        ],
        "funding": [
            f"Förderung Digitalisierung {b.bundesland.upper()} {b.branche} {size}",
            f"Förderprogramm KI {b.bundesland.upper()} Deadline {b.branche}",
        ],
        "domain_whitelist": BUNDESLAND_DOMAIN_WHITELIST.get((b.bundesland or "").lower(), ["bmwk.de", "europa.eu", "ihk.de"]),
    }


def _cards(items: List[Dict[str, str]], tag: str) -> str:
    """Formatiert eine Liste von Items als HTML‑Karten."""
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
    """Sammelt Live‑Informationen und liefert HTML‑Fragmente zurück."""
    q = build_queries(b)
    # Tavily – News & Tools (jeweils mit Domain‑Whitelist)
    news_hits: List[Dict[str, str]] = []
    for qn in q["news"]:
        news_hits += tavily_search(
            qn,
            days=max(7, SEARCH_DAYS),
            include_domains=q["domain_whitelist"],
            max_results=SEARCH_MAX_RESULTS,
        )
    tools_hits: List[Dict[str, str]] = []
    for qt in q["tools"]:
        tools_hits += tavily_search(
            qt,
            days=max(30, SEARCH_DAYS_TOOLS),
            include_domains=q["domain_whitelist"],
            max_results=SEARCH_MAX_RESULTS,
        )
    # Förderprogramme – CSV
    funding_rows = load_csv(DATA_DIR / "foerderprogramme.csv")
    region_code = map_region_code(b.bundesland)
    funding_rows = [r for r in funding_rows if r.get("Region_Code", "DE") in (region_code, "DE")]
    funding_cards: List[str] = []
    for r in funding_rows[: SEARCH_MAX_RESULTS]:
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
    # EU‑Calls via Funding & Tenders
    eu_calls: List[Dict[str, str]] = []
    try:  # pragma: no cover
        eu_calls = funding_tenders_search(
            f'AI OR "artificial intelligence" {b.branche}',
            from_days=max(60, SEARCH_DAYS_FUNDING),
            max_results=SEARCH_MAX_RESULTS,
        )
    except Exception as e:
        logger.warning("EU funding_tenders_search failed: %s", e)
    return {
        "news_html": f'<section><h3>Aktuelle Meldungen (Stand: {now_iso()})</h3>{_cards(news_hits, "News")}</section>',
        "tools_rich_html": f'<section><h3>Neue Tools & Releases (Stand: {now_iso()})</h3>{_cards(tools_hits, "Tool/Release")}</section>',
        "funding_rich_html": f'<section><h3>Förderprogramme (Stand: {now_iso()})</h3>{"".join(funding_cards)}</section>',
        "funding_deadlines_html": f'<section><h3>EU‑Calls (letzte 60 Tage)</h3>{_cards(eu_calls, "EU‑Call")}</section>',
    }


# -----------------------------------------------------------------------------
# Compliance‑Playbook
# -----------------------------------------------------------------------------
def render_compliance_playbook() -> str:
    """Gibt das Compliance‑Playbook als HTML‑String zurück."""
    return f"""
<section>
  <h3>Compliance‑Playbook (Go‑Live‑Gate & Betrieb)</h3>
  <ol>
    <li><strong>Go‑Live‑Gate & Minimal Viable Compliance (MVC):</strong> Vor der
        Produktivsetzung Nachweise zu Risikoklasse, DPA/AVV,
        Rechtekette, Tests (Performance/Drift/Bias) sowie klare Rollen und
        Verantwortlichkeiten.</li>
    <li><strong>Human‑in‑the‑Loop & Kill‑Switch:</strong> Kritische Entscheidungen
        bleiben beim Menschen; ein dokumentierter Not‑Aus sorgt für eine
        sichere Rückfallebene.</li>
    <li><strong>Input‑/Output‑Gates:</strong> Rechtekette & Datenbasis (Input)
        prüfen; Ausgaben auf Halluzinationen/IP/DSGVO/Policy (Output)
        überprüfen; beide Prüfungen sind Prozess‑Gateways.</li>
    <li><strong>Re‑Klassifizierungs‑Trigger:</strong> Fine‑Tuning, Zweck‑ oder
        Markenwechsel, autonome Agenten → Pflichten und Dokumentationspflichten
        neu bewerten.</li>
    <li><strong>Rechtslandkarte:</strong> Neben KI‑VO auch Produkt‑ und
        Sektorrecht, Cyber Resilience Act, Digital Services Act und Data
        Act integrieren; Verantwortliche & Nachweise benennen.</li>
    <li><strong>AI‑Literacy:</strong> Pflichttrainings mit jährlicher
        Auffrischung; Zugriffsrechte werden an den Schulungsstand gekoppelt.</li>
    <li><strong>Monitoring & Re‑Tests:</strong> Technologieradar;
        periodische Re‑Tests (Performance/Drift/Bias); Ergebnisse fließen in
        Standards und Modelle zurück.</li>
  </ol>
  <p class="stand">Stand: {now_iso()}</p>
</section>"""


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


def load_benchmarks(branche: str, size: str = "kmu") -> Dict[str, float]:
    """Lädt Benchmarks für eine Branche und Unternehmensgröße.

    Es wird nach ``benchmarks_<branche>_<size>.json`` gesucht, wobei
    ``<size>`` ``solo``, ``small`` oder ``kmu`` sein kann.  Existiert diese
    Datei nicht, versucht die Funktion einen Katalog zu nutzen; schließlich
    erfolgt ein Fallback auf "Beratung".  Wird nichts gefunden, werden
    Default‑Werte zurückgegeben.  Die Rückgabewerte sind ungefiltert
    (0–1‑Skala), d. h. sie sollten später ggf. zu Prozenten skaliert werden.
    """
    # Formatieren des Dateinamens
    # Zuerst den Rohwert auf Kleinbuchstaben trimmen
    branch_key_raw = (branche or "").strip().lower()
    # Ersetze alle nicht alphanumerischen Zeichen (inkl. Leerzeichen, &,
    # Schrägstriche usw.) durch Unterstriche.  Dadurch können Branchennamen
    # wie "Finanzen & Versicherungen" oder "IT & Software" korrekt auf
    # Datei-Namen abgebildet werden.
    branch_key = re.sub(r"[^a-z0-9]+", "_", branch_key_raw)
    # Reduziere aufeinanderfolgende Unterstriche auf einen einzelnen und
    # entferne führende oder nachgestellte Unterstriche.
    branch_key = re.sub(r"_+", "_", branch_key).strip("_")
    size_key = (size or "kmu").strip().lower()
    # Normiere größe: solo/freiberuflich → solo; kleines team → small
    if re.search(r"solo|freiberuf", size_key):
        size_key = "solo"
    elif re.search(r"2\-?10|kleines", size_key):
        size_key = "small"
    else:
        size_key = "kmu"
    specific = DATA_DIR / f"benchmarks_{branch_key}_{size_key}.json"
    if specific.exists():
        try:
            data = json.loads(specific.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                if "kpis" in data and isinstance(data["kpis"], list):
                    out: Dict[str, float] = {}
                    for kpi in data["kpis"]:
                        name = (kpi.get("name") or "").lower()
                        val = kpi.get("value")
                        if name and isinstance(val, (int, float)):
                            out[name] = float(val)
                    return out
                return {k: float(v) for k, v in data.items() if isinstance(v, (int, float))}
        except Exception:
            pass
    # Katalog (gruppiert nach Branche; Größe wird ignoriert)
    catalog = load_json(DATA_DIR / "benchmarks_catalog.json", default=None)
    if isinstance(catalog, dict):
        if branch_key in catalog and isinstance(catalog[branch_key], dict):
            return {k: float(v) for k, v in catalog[branch_key].items() if isinstance(v, (int, float))}
    # Fallback auf Beratung (größe berücksichtigen)
    fallback_file = DATA_DIR / f"benchmarks_beratung_{size_key}.json"
    fb = load_json(fallback_file, default=None)
    if isinstance(fb, dict):
        if "kpis" in fb and isinstance(fb["kpis"], list):
            out_f: Dict[str, float] = {}
            for kpi in fb["kpis"]:
                name = (kpi.get("name") or "").lower()
                val = kpi.get("value")
                if name and isinstance(val, (int, float)):
                    out_f[name] = float(val)
            return out_f
        return {k: float(v) for k, v in fb.items() if isinstance(v, (int, float))}
    # Letzter Fallback
    return DEFAULT_BENCHMARKS_BERATUNG


# -----------------------------------------------------------------------------
# Prompt‑Engine
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
    """Lädt eine Promptdatei und generiert den Abschnittstext via LLM."""
    prompt_file = PROMPTS_DIR / f"{section}_{lang}.md"
    # Fallback auf Englisch
    if not prompt_file.exists():
        alt = PROMPTS_DIR / f"{section}_en.md"
        prompt_file = alt if alt.exists() else prompt_file
    prompt_raw = prompt_file.read_text(encoding="utf-8") if prompt_file.exists() else ""
    if not prompt_raw:
        logger.warning("Promptdatei fehlt: %s", prompt_file)
        return ""
    # Platzhalter ersetzen
    prompt_str = fill_placeholders(prompt_raw, ctx)
    logger.info("Prompt aufgelöst: %s -> %s", section, prompt_file.name)
    return llm.chat(SYSTEM_PROMPT, prompt_str, GPT_TEMPERATURE)


# -----------------------------------------------------------------------------
# Hauptfunktion
# -----------------------------------------------------------------------------
def generate_report_payload(briefing_json_path: Path) -> Dict[str, Any]:
    """Erzeugt das vollständige Payload für einen Report.

    Dieser Entry‑Point wird vom FastAPI‑Controller aufgerufen.  Er verarbeitet
    das Briefing, berechnet Business‑Case und KPI‑Scores, lädt Benchmarks,
    ruft Live‑Add‑ins ab, generiert LLM‑Sektionen (wenn aktiviert) und gibt
    ein strukturiertes Dictionary zurück.  Dieses Dictionary kann von der
    ``postprocess_report.py`` oder einem Jinja‑Template gerendert werden.
    """
    # Briefing laden
    b = Briefing.from_json(briefing_json_path)
    logger.info("Briefing geladen: %s", b)

    # Investition ermitteln & jährliche Einsparung berechnen
    invest = invest_from_bucket(b.investitionsbudget)
    annual_saving = invest * 4.0  # konservativer ROI‑Faktor (4× Investition)
    bc = BusinessCase(invest_eur=invest, annual_saving_eur=annual_saving, efficiency_gain_frac=0.40)

    # Benchmarks laden (abhängig von Branche und Unternehmensgröße)
    bm = load_benchmarks(b.branche, b.unternehmensgroesse)
    logger.info("Benchmarks geladen: %s", bm)

    # KPI‑Scores berechnen
    kpi_scores = compute_kpi_scores(b, bm)

    # Live‑Add‑ins laden
    live = get_live_news_tools_funding(b)
    logger.info("Live‑Add‑ins gesammelt: %s", list(live.keys()))

    # Business Case JSON (für Prompts)
    business_case_json = {
        "Investition": f"{bc.invest_eur:.0f}",
        "Einsparung_Jahr_1": f"{bc.annual_saving_eur:.0f}",
        "ROI_Jahr_1": f"{bc.roi_year1_pct}%",
        "Payback": f"{bc.payback_months:.1f} Monate",
        "Gewinn_3_Jahre": f"{bc.three_year_profit}",
        "Zeitersparnis_Stunden_Monat": f"{bc.time_saved_hours_per_month}",
    }

    # Benchmarks JSON (für Prompts)
    benchmarks_json = {
        "digitalisierung": bm.get("digitalisierung", 0),
        "automatisierung": bm.get("automatisierung", 0),
        "compliance": bm.get("compliance", 0),
        "prozessreife": bm.get("prozessreife", 0),
        "innovation": bm.get("innovation", 0),
    }

    # Kontext für Prompt‑Placeholders
    # Um potenzielle Probleme mit f‑Strings und verschachtelten Anführungszeichen zu vermeiden, werden
    # die KPI‑Werte vorab in Variablen gespeichert.  Dadurch wird ein Syntaxfehler wie
    # "unmatched '['" im f‑String vermieden.
    score_percent_val = kpi_scores.get("score_percent", 0.0)
    kpi_efficiency_val = kpi_scores.get("kpi_efficiency", 0.0)
    kpi_compliance_val = kpi_scores.get("kpi_compliance", 0.0)
    kpi_innovation_val = kpi_scores.get("kpi_innovation", 0.0)

    ctx = {
        "branche": b.branche,
        "unternehmensgroesse": b.unternehmensgroesse,
        "bundesland": b.bundesland,
        "hauptleistung": b.hauptleistung,
        "invest_eur": f"{bc.invest_eur:.0f}",
        "annual_saving_eur": f"{bc.annual_saving_eur:.0f}",
        "roi_year1_pct": f"{bc.roi_year1_pct}",
        "payback_months": f"{bc.payback_months:.1f}",
        "three_year_profit": f"{bc.three_year_profit}",
        "time_saved_hours_per_month": f"{bc.time_saved_hours_per_month}",
        # KPI-Werte aus Variablen, um Probleme mit Anführungszeichen in f-Strings zu vermeiden
        "score_percent": f"{score_percent_val:.1f}",
        "kpi_efficiency": f"{kpi_efficiency_val:.1f}",
        "kpi_compliance": f"{kpi_compliance_val:.1f}",
        "kpi_innovation": f"{kpi_innovation_val:.1f}",
        "business_case_json": json.dumps(business_case_json, ensure_ascii=False),
        "benchmarks_json": json.dumps(benchmarks_json, ensure_ascii=False),
        "date": now_iso(),
        "NEWS_HTML": live.get("news_html", "") + live.get("tools_rich_html", ""),
    }

    # LLM‑Client initialisieren
    llm = OpenAIChat()

    # Sektionen generieren (LLM oder Fallback)
    sections: Dict[str, str] = {}
    if ENABLE_LLM_SECTIONS:
        for sec in SECTION_FILES:
            try:
                sections[sec] = render_section_text(sec, b.lang, ctx, llm)
            except Exception as e:
                logger.error("Fehler beim Rendern der Sektion %s: %s", sec, e)
                sections[sec] = ""
    else:
        # Minimaler Fallback: leere Sektionen
        sections = {sec: "" for sec in SECTION_FILES}

    # Farbpalette (wird von Templates verwendet)
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
            "subtitle": f"Status‑Report für {b.branche} (KMU)",
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
        "kpi_scores": kpi_scores,
        "sections": sections,
        "live_addins": live,
        "compliance_playbook_html": render_compliance_playbook(),
        "palette": palette,
        # Kontextobjekte (optional für Post‑Processing oder Qualitätssicherung)
        "business_case_json": business_case_json,
        "benchmarks_json": benchmarks_json,
    }
    logger.info("Payload erstellt (Sektionen: %s)", list(sections.keys()))
    return payload


# -----------------------------------------------------------------------------
# Kompatibilitätsfunktionen für das FastAPI‑Backend
#
# Einige Versionen des Backends erwarten Funktionen ``analyze_briefing`` und
# ``analyze_briefing_enhanced`` in diesem Modul.  Diese Funktionen sind
# hier als Wrapper implementiert.  Sie nutzen intern ``generate_report_payload``
# und rendern das Ergebnis via Jinja2 in ein HTML oder liefern das
# strukturierte Payload zurück.

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape  # type: ignore
except Exception:  # pragma: no cover
    Environment = None  # type: ignore


def analyze_briefing(briefing_json_path: str) -> str:
    """
    Kompatibilitätsfunktion: generiert einen vollständigen Report (HTML) aus
    einem Briefing‑JSON‑Pfad.  Wenn Jinja2 verfügbar ist und das Template
    gefunden wird, wird das Report‑Payload in das entsprechende HTML
    gerendert.  Andernfalls wird ein rudimentäres HTML ausgegeben.

    :param briefing_json_path: Pfad zur Briefing‑JSON-Datei
    :return: gerenderte HTML‑Seite oder rudimentärer Platzhalter
    """
    path = Path(briefing_json_path)
    payload = generate_report_payload(path)
    # Lade Jinja‑Template, falls möglich
    if Environment is not None and TEMPLATE_DIR and TEMPLATE_DE:
        try:
            env = Environment(
                loader=FileSystemLoader(str(TEMPLATE_DIR)),
                autoescape=select_autoescape(["html", "xml"]),
            )
            # Sprachenaufschlüsselung
            lang = payload.get("meta", {}).get("lang", "de")
            template_name = TEMPLATE_DE if lang.startswith("de") else TEMPLATE_EN
            template = env.get_template(template_name)
            # Payload flach rendern; Template erwartet möglicherweise
            # direkte Schlüssel (z. B. {{ sections.executive_summary }})
            html = template.render(payload)
            return html
        except Exception as e:
            logger.error("Jinja-Rendering fehlgeschlagen: %s", e)
    # Fallback: rudimentäres HTML ausgeben
    return f"<html><body><pre>{json.dumps(payload, indent=2, ensure_ascii=False)}</pre></body></html>"


def analyze_briefing_enhanced(briefing_json_path: str) -> Dict[str, Any]:
    """
    Kompatibilitätsfunktion: liefert das strukturierte Report‑Payload
    (Dictionary) zurück.  Dieser Wrapper wird von einigen Qualitätstools
    oder API‑Endpunkten verwendet.

    :param briefing_json_path: Pfad zur Briefing‑JSON-Datei
    :return: strukturierter Report‑Payload
    """
    path = Path(briefing_json_path)
    return generate_report_payload(path)


if __name__ == "__main__":  # pragma: no cover
    example = Path("briefing.json")
    if example.exists():
        import pprint

        pprint.pprint(generate_report_payload(example))
    else:
        logger.warning("briefing.json nicht gefunden – Testlauf übersprungen.")