# File: gpt_analyze.py
# -*- coding: utf-8 -*-
"""
Analyse & Rendering für den KI-Status-Report (Gold-Standard+)

Enthält:
- Robustes Briefing-Normalisieren + Pflichtfeld-Prüfung
- KPI-Berechnung (Mapping 1:1 zu Formbuilder-Optionen)
- Benchmarks: JSON tolerant (%, Komma), CSV-Fallback nur bei Bedarf
- Business Case mit 4-Monate-Payback-Baseline (konfigurierbar)
- GPT-Wrapper mit gpt-5 Temperature-Fix + Fallback-Modell
- Platzhalter-Postprocessing ({date}, {branche}, {business_case_json.*}) in allen GPT-Abschnitten
- Branchenkontext, Checklisten (inkl. Non-EU-Betriebsregeln)
- Live-Sektionen via websearch_utils (News/Tools/Förderungen) mit Fußnoten-Quellen
- Kompaktes, semantisches HTML via Jinja2-Templates (DE/EN)

Konfiguration über ENV (siehe railway-variablen.template.env)
"""

from __future__ import annotations

import csv
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

# OpenAI SDK (robuster Wrapper)
try:
    from openai import OpenAI  # type: ignore
    _openai_available = True
except Exception:
    _openai_available = False

log = logging.getLogger("gpt_analyze")
if not log.handlers:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

# ------------------------------ Pfade/ENV ------------------------------------

BASE_DIR = os.path.abspath(os.getenv("APP_BASE", os.getcwd()))
TEMPLATE_DIR = os.getenv("TEMPLATE_DIR", os.path.join(BASE_DIR, "templates"))
PROMPTS_DIR = os.getenv("PROMPTS_DIR", os.path.join(BASE_DIR, "prompts"))
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
BRANCHEN_DIR = os.path.join(DATA_DIR, "branchenkontext")
CONTENT_DIR = os.path.join(DATA_DIR, "content")

EXEC_SUMMARY_MODEL = os.getenv("EXEC_SUMMARY_MODEL", os.getenv("GPT_MODEL_NAME", "gpt-4o"))
EXEC_SUMMARY_MODEL_FALLBACK = os.getenv("EXEC_SUMMARY_MODEL_FALLBACK", os.getenv("OPENAI_FALLBACK_MODEL", "gpt-4o"))
DEFAULT_MODEL = os.getenv("GPT_MODEL_NAME", os.getenv("OPENAI_MODEL_DEFAULT", "gpt-4o"))

APPENDIX_CHECKLISTS = os.getenv("APPENDIX_CHECKLISTS", "true").strip().lower() in {"1", "true", "yes", "on"}
APPENDIX_MAX_DOCS = int(os.getenv("APPENDIX_MAX_DOCS", "6"))
ROI_BASELINE_MONTHS = float(os.getenv("ROI_BASELINE_MONTHS", "4"))

SEARCH_PROVIDER = os.getenv("SEARCH_PROVIDER", "hybrid").strip().lower()
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip()
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "").strip()

# ------------------------------ Hilfsfunktionen ------------------------------

def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _euro(n: float) -> str:
    try:
        s = f"{float(n):,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{s} €"
    except Exception:
        return f"{n} €"


def _md_to_html(md: str) -> str:
    """
    Schlanker Markdown->HTML Konverter (ohne externe Abhängigkeit).
    Unterstützt H1–H3, UL, Absätze, Links.
    """
    if not md:
        return ""
    html_lines: List[str] = []
    for line in md.splitlines():
        s = line.rstrip()
        if not s:
            html_lines.append("<p></p>")
            continue
        if s.startswith("### "):
            html_lines.append(f"<h3>{s[4:].strip()}</h3>")
        elif s.startswith("## "):
            html_lines.append(f"<h2>{s[3:].strip()}</h2>")
        elif s.startswith("# "):
            html_lines.append(f"<h1>{s[2:].strip()}</h1>")
        elif s.lstrip().startswith(("- ", "* ")):
            html_lines.append(f"<li>{s.lstrip()[2:].strip()}</li>")
        else:
            s = re.sub(r"\[(.*?)\]\((https?://[^\s)]+)\)", r"<a href='\2' target='_blank' rel='noopener noreferrer'>\1</a>", s)
            html_lines.append(f"<p>{s}</p>")
    out: List[str] = []
    in_list = False
    for l in html_lines:
        if l.startswith("<li>") and not in_list:
            out.append("<ul>")
            in_list = True
        if not l.startswith("<li>") and in_list:
            out.append("</ul>")
            in_list = False
        out.append(l)
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def _to_percent(value: Any, max_value: float) -> float:
    try:
        v = float(str(value).replace(",", "."))
        if max_value <= 0:
            return 0.0
        return max(0.0, min(100.0, round((v / max_value) * 100.0, 1)))
    except Exception:
        return 0.0


def _today() -> str:
    import datetime as dt
    return dt.datetime.now().strftime("%Y-%m-%d")


def _is_true(val: Any) -> bool:
    return str(val).strip().lower() in {"1", "true", "yes", "ja", "y", "on"}


# --------------------------- Normalisierung ----------------------------------

CANON_KEYS = {
    "branche": ["branche", "industry", "sector"],
    "unternehmensgroesse": ["unternehmensgroesse", "company_size", "size", "mitarbeiterzahl"],
    "bundesland": ["bundesland", "state", "region"],
    "hauptleistung": ["hauptleistung", "main_service", "leistung"],
    "investitionsbudget": ["investitionsbudget", "budget", "capex", "investment"],
    "digitalisierungsgrad": ["digitalisierungsgrad", "digitization_level"],
    "prozesse_papierlos": ["prozesse_papierlos", "paperless"],
    "automatisierungsgrad": ["automatisierungsgrad", "automation_level"],
    "innovationskultur": ["innovationskultur", "innovation_culture"],
    "ki_knowhow": ["ki_knowhow", "ai_knowledge"],
    "governance": ["governance"],
    "datenschutz": ["datenschutz", "gdpr_ok"],
    "folgenabschaetzung": ["folgenabschaetzung", "dpia"],
    "meldewege": ["meldewege", "incident_process"],
    "loeschregeln": ["loeschregeln", "deletion_rules"],
}

BR_SLUGS = {
    "beratung": ["beratung", "beratung_dienstleistungen"],
    "it": ["it", "it_software"],
    "marketing": ["marketing", "marketing_werbung"],
    "medien": ["medien", "medien_kreativwirtschaft"],
    "handel": ["handel", "handel_e_commerce"],
    "industrie": ["industrie", "industrie_produktion"],
    "gesundheit": ["gesundheit", "gesundheit_pflege"],
    "bau": ["bau", "bauwesen_architektur"],
    "logistik": ["logistik", "transport_logistik"],
    "verwaltung": ["verwaltung"],
    "bildung": ["bildung"],
    "finanzen": ["finanzen", "finanzen_versicherungen"],
}
SIZE_ALIASES = {
    "solo": ["solo"],
    "small": ["small", "team", "team_2_10", "klein"],
    "kmu": ["kmu", "kmu_11_100", "mittel", "gross", "konzern"],
}
BR_LABEL = {
    "beratung": "Beratung & Dienstleistungen", "it": "IT & Software",
    "marketing": "Marketing & Werbung", "medien": "Medien & Kreativwirtschaft",
    "handel": "Handel & E‑Commerce", "industrie": "Industrie & Produktion",
    "gesundheit": "Gesundheit & Pflege", "bau": "Bauwesen & Architektur",
    "logistik": "Transport & Logistik", "verwaltung": "Verwaltung",
    "bildung": "Bildung", "finanzen": "Finanzen & Versicherungen",
}
SIZE_LABEL = {"solo": "1", "small": "2‑10", "kmu": "11‑100+"}

BL_MAP = {
    "berlin": "BE", "be": "BE",
    "bayern": "BY", "by": "BY",
    "baden-württemberg": "BW", "bw": "BW",
    "brandenburg": "BB", "bb": "BB",
    "bremen": "HB", "hb": "HB",
    "hamburg": "HH", "hh": "HH",
    "hessen": "HE", "he": "HE",
    "mecklenburg-vorpommern": "MV", "mv": "MV",
    "niedersachsen": "NI", "ni": "NI",
    "nordrhein-westfalen": "NW", "nrw": "NW", "nw": "NW",
    "rheinland-pfalz": "RP", "rp": "RP",
    "saarland": "SL", "sl": "SL",
    "sachsen": "SN", "sn": "SN",
    "sachsen-anhalt": "ST", "st": "ST",
    "schleswig-holstein": "SH", "sh": "SH",
    "thüringen": "TH", "thueringen": "TH", "th": "TH",
}

REQUIRED_FIELDS = ["branche", "unternehmensgroesse", "bundesland", "hauptleistung", "investitionsbudget"]


def normalize_briefing(raw: Dict[str, Any]) -> Dict[str, Any]:
    src = {**raw, **(raw.get("answers") or {})}
    norm: Dict[str, Any] = {}
    for key, aliases in CANON_KEYS.items():
        val = ""
        for a in aliases:
            if a in src and str(src[a]).strip():
                val = str(src[a]).strip()
                break
        norm[key] = val

    for keep in ("lang", "email", "to"):
        if keep in src and str(src[keep]).strip():
            norm[keep] = src[keep]

    br_key = (norm.get("branche") or "").lower()
    size_key = (norm.get("unternehmensgroesse") or "").lower()
    if size_key not in ("solo", "small", "kmu"):
        size_key = "small" if size_key not in ("konzern", "enterprise") else "kmu"

    norm["branche"] = br_key
    norm["unternehmensgroesse"] = size_key
    norm["branche_label"] = BR_LABEL.get(br_key, norm.get("branche"))
    norm["unternehmensgroesse_label"] = SIZE_LABEL.get(size_key, norm.get("unternehmensgroesse"))

    bl_raw = (norm.get("bundesland") or "").strip().lower()
    norm["bundesland_code"] = BL_MAP.get(bl_raw, BL_MAP.get(bl_raw.replace(" ", "-"), "")) or bl_raw.upper()
    return norm


def missing_fields(norm: Dict[str, Any]) -> List[str]:
    return [k for k in REQUIRED_FIELDS if not (norm.get(k) and str(norm[k]).strip())]


# ------------------------------ Benchmarks -----------------------------------

def _bench_json_path_candidates(br: str, sz: str) -> List[str]:
    br_variants = [br] + BR_SLUGS.get(br, [])
    size_variants = []
    for key, aliases in SIZE_ALIASES.items():
        if sz in aliases or sz == key:
            size_variants.append(key)
    if not size_variants:
        size_variants = ["small", "kmu", "solo"]
    names = []
    for b in br_variants:
        for s in size_variants:
            names.append(f"benchmarks_{b}_{s}.json")
    return names


def pick_benchmark_file(branche_key: str, size_key: str) -> str:
    for name in _bench_json_path_candidates(branche_key, size_key):
        path = os.path.join(DATA_DIR, name)
        if os.path.exists(path):
            log.info("Loaded benchmark: %s", name)
            return path
    return ""


def _parse_percentish(val: Any) -> float:
    """
    Akzeptiert 65, '65', '65%', '65,0', '0.65' (interpretiert als 65), etc.
    """
    s = str(val).strip()
    if not s:
        return 0.0
    s = s.replace(" ", "")
    if s.endswith("%"):
        s = s[:-1]
    s = s.replace(",", ".")
    try:
        f = float(s)
        if 0.0 <= f <= 1.0:
            f *= 100.0
        return max(0.0, min(100.0, round(f, 1)))
    except Exception:
        return 0.0


def _load_benchmarks_from_csv(br: str, sz: str) -> Dict[str, float]:
    csv_name = f"benchmark_{br}.csv"
    path = os.path.join(DATA_DIR, csv_name)
    if not os.path.exists(path):
        path = os.path.join(DATA_DIR, "benchmark_default.csv")
        if not os.path.exists(path):
            return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except Exception:
        return {}

    result: Dict[str, float] = {}
    # Variante A: Kategorie/Wert_Durchschnitt
    if rows and "Kategorie" in rows[0] and "Wert_Durchschnitt" in rows[0]:
        mapping = {
            "digitalisierung": "digitalisierung",
            "automatisierung": "automatisierung",
            "datenschutzkonformität": "compliance",
            "datenschutz-compliance": "compliance",
            "innovationsindex": "innovation",
            "papierloser anteil (%)": "prozessreife",
            "prozessreife": "prozessreife",
        }
        for r in rows:
            k = (r.get("Kategorie") or "").strip().lower()
            key = mapping.get(k)
            if not key:
                continue
            vv = _parse_percentish(r.get("Wert_Durchschnitt"))
            if vv:
                result[key] = vv
    # Variante B: Kriterium + Spalten pro Größe
    elif rows and "Kriterium" in rows[0]:
        col = "KMU" if sz == "kmu" else ("Klein" if sz == "small" else "Solo")
        mapping = {
            "digitalisierung": "digitalisierung",
            "automatisierung": "automatisierung",
            "datenschutzkonformität": "compliance",
            "innovationsindex": "innovation",
            "papierloser anteil (%)": "prozessreife",
            "prozessreife": "prozessreife",
        }
        for r in rows:
            k = (r.get("Kriterium") or "").strip().lower()
            key = mapping.get(k)
            if not key:
                continue
            vv = _parse_percentish(r.get(col))
            if vv:
                result[key] = vv

    if result:
        for need in ("digitalisierung", "automatisierung", "compliance", "prozessreife", "innovation"):
            result.setdefault(need, 60.0)
    return result


def load_benchmarks(norm: Dict[str, Any]) -> Dict[str, float]:
    br = (norm.get("branche") or "beratung").lower()
    sz = (norm.get("unternehmensgroesse") or "small").lower()
    path = pick_benchmark_file(br, sz)
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            out: Dict[str, float] = {}
            for k, v in data.items():
                out[k.lower()] = _parse_percentish(v)
            if out:
                return out
        except Exception as e:
            log.warning("Benchmark JSON parsing failed (%s), trying CSV fallback", e)
    csv_bm = _load_benchmarks_from_csv(br, sz)
    if csv_bm:
        log.info("Loaded benchmark fallback from CSV for %s/%s", br, sz)
        return csv_bm
    return {"digitalisierung": 72.0, "automatisierung": 64.0, "compliance": 70.0, "prozessreife": 68.0, "innovation": 69.0}


# --------------------------- KPIs / Business Case ----------------------------

def calculate_kpis(norm: Dict[str, Any]) -> Dict[str, float]:
    # Digitalisierung 1–10 → %
    digi = _to_percent(norm.get("digitalisierungsgrad") or 0, 10.0)

    # Automatisierungsgrad – Mapping exakt wie im Formbuilder
    auto_map = {
        "sehr_hoch": 85, "eher_hoch": 65, "mittel": 50, "eher_niedrig": 35, "sehr_niedrig": 20
    }
    auto = float(auto_map.get(str(norm.get("automatisierungsgrad") or "").lower(), 40))

    # Compliance – prüfbare Flags
    comp = 0.0
    comp += 25.0 if _is_true(norm.get("datenschutz")) else 0.0
    for flag in ("governance", "folgenabschaetzung", "meldewege", "loeschregeln"):
        val = str(norm.get(flag) or "").strip().lower()
        if val in {"ja", "yes", "true", "1", "teilweise", "partial"}:
            comp += 18.75
    comp = min(100.0, round(comp or 55.0, 1))

    # Prozessreife – papierlos
    paper = str(norm.get("prozesse_papierlos") or "").lower()
    paper_map = {"0-20": 10, "21-50": 40, "51-80": 65, "81-100": 80}
    proc = float(paper_map.get(paper, 60))
    if str(norm.get("governance") or "").strip():
        proc = min(100.0, proc + 8.0)

    # Innovation – Kultur + Knowhow
    kult_map = {
        "sehr_offen": 80, "eher_offen": 70, "neutral": 55, "eher_zurueckhaltend": 45, "sehr_zurueckhaltend": 35
    }
    know_map = {
        "expertenwissen": 80, "fortgeschritten": 70, "mittel": 60, "grundkenntnisse": 50, "keine": 40
    }
    inv = (float(kult_map.get(str(norm.get("innovationskultur") or "").lower(), 65))
           + float(know_map.get(str(norm.get("ki_knowhow") or "").lower(), 60))) / 2.0

    return {
        "digitalisierung": round(digi, 1),
        "automatisierung": round(auto, 1),
        "compliance": round(comp, 1),
        "prozessreife": round(proc, 1),
        "innovation": round(inv, 1),
    }


def overall_score(kpis: Dict[str, float]) -> float:
    vals = list(kpis.values()) or [0, 0, 0, 0, 0]
    return round(sum(vals) / len(vals), 1)


def quality_badge(score_pct: float) -> Dict[str, Any]:
    s = round(float(score_pct), 1)
    if s >= 85:
        grade = "EXCELLENT"
    elif s >= 70:
        grade = "GOOD"
    elif s >= 55:
        grade = "FAIR"
    else:
        grade = "BASIC"
    return {"grade": grade, "score": s}


def _load_roi_config() -> Dict[str, Any]:
    path = os.path.join(DATA_DIR, "config_roi.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _size_to_roi_bucket(size_key: str) -> str:
    s = (size_key or "").lower()
    if s in ("solo",):
        return "solo"
    if s in ("small", "team", "team_2_10", "klein"):
        return "team_2_10"
    return "kmu_11_100"


def business_case(norm: Dict[str, Any], score: float) -> Dict[str, float]:
    # Budget aus Auswahl; konservative Defaults
    invest_map = {
        "unter_2000": 1500,
        "2000_10000": 6000,
        "10000_50000": 20000,
        "ueber_50000": 60000,
        "unter_1000": 1000,  # Altkompat.
    }
    invest = float(invest_map.get(str(norm.get("investitionsbudget") or "").lower(), 6000))

    cfg = _load_roi_config()
    bucket = _size_to_roi_bucket(norm.get("unternehmensgroesse") or "small")
    roi = cfg.get(bucket, {})
    if roi:
        hrs = (float(roi["hours_saved_per_week_range"][0]) + float(roi["hours_saved_per_week_range"][1])) / 2.0
        rate = (float(roi["hourly_rate_range_eur"][0]) + float(roi["hourly_rate_range_eur"][1])) / 2.0
        tool_pm = float(roi.get("tool_cost_per_user_month_eur", 40))
        seats = {"solo": 1, "team_2_10": 6, "kmu_11_100": 30}.get(bucket, 6)
        per_user_month = max(0.0, hrs * rate * 4.33 - tool_pm)
        annual_saving = max(0.0, per_user_month * 12 * seats)
    else:
        # fallback: 4x Invest p.a.
        annual_saving = invest * 4.0

    # 4‑Monate‑Baseline, falls länger → Saving anheben
    payback_months = max(0.5, round(invest / (annual_saving / 12.0), 1)) if annual_saving > 0 else 12.0
    if ROI_BASELINE_MONTHS > 0 and payback_months > ROI_BASELINE_MONTHS:
        annual_saving = max(1.0, invest * 12.0 / ROI_BASELINE_MONTHS)
        payback_months = round(invest / (annual_saving / 12.0), 1)

    roi_y1_pct = round(((annual_saving - invest) / invest) * 100.0, 1) if invest > 0 else 0.0

    # Zusätzliche, oft gewünschte Kennzahl
    three_year_gain = max(0.0, annual_saving * 3.0 - invest)

    return {
        "invest_eur": round(invest, 0),
        "annual_saving_eur": round(annual_saving, 0),
        "payback_months": payback_months,
        "roi_year1_pct": roi_y1_pct,
        "three_year_gain_eur": round(three_year_gain, 0),
    }


# ------------------------- Branchenkontext / Appendix ------------------------

def _industry_context_html(branche_key: str, lang: str) -> str:
    fn = f"{branche_key}_{'de' if lang.startswith('de') else 'en'}.md"
    path = os.path.join(BRANCHEN_DIR, fn)
    md = _read_text(path)
    return _md_to_html(md) if md else ""


def _appendix_checklists_html(lang: str) -> str:
    """
    Sammelt check_*.md aus data/ und data/content/ (max APPENDIX_MAX_DOCS).
    Fügt immer eine Non‑EU‑Betriebsregeln‑Checkliste an (fixer Teil deiner Anforderungen).
    """
    parts: List[str] = []
    if APPENDIX_CHECKLISTS:
        for base in (DATA_DIR, CONTENT_DIR):
            try:
                names = sorted(os.listdir(base))
            except Exception:
                continue
            for name in names:
                if name.lower().startswith("check_") and name.lower().endswith(".md"):
                    parts.append(f"<h3>{os.path.splitext(name)[0].replace('_',' ').title()}</h3>")
                    parts.append(_md_to_html(_read_text(os.path.join(base, name))))
                    if len(parts) // 2 >= APPENDIX_MAX_DOCS:
                        break

    # Non‑EU Betriebsregeln (immer anhängen)
    non_eu = """
<h3>Non‑EU‑Betriebsregeln (verbindliche Checkliste)</h3>
<ul>
  <li>Kein Upload personenbezogener Daten/Geheimnisse ohne <b>AVV/SCC</b> &amp; DPIA.</li>
  <li><b>Pseudonymisierung</b>/Anonymisierung vor jeder Verarbeitung; Logging prüfen.</li>
  <li><b>Role‑Based Access</b>, 2FA, Key‑Rotation; Modell‑/Chat‑Logs deaktivieren oder minimieren.</li>
  <li>Inhalte &amp; Metadaten nur <b>auftragsbezogen</b> speichern; Export-/Löschpfade definieren.</li>
  <li><b>Fallback‑EU‑Alternative</b> (On‑Prem/SaaS) für kritische Workloads bereithalten.</li>
  <li><b>Data Residency</b> &amp; Sub‑Processor‑Liste prüfen; US‑Übermittlungen dokumentieren.</li>
  <li><b>Red‑Team‑Tests</b> (Prompt‑Leakage, Training‑Data‑Extraction, Halluzination) vor Go‑Live.</li>
  <li>Vertragliche <b>Nutzungsgrenzen</b> (keine Trainingsnutzung), SLA/Verfügbarkeit fixieren.</li>
  <li><b>Incident‑Meldewege</b>, Löschregeln und Re‑Klassifizierungs‑Trigger definieren.</li>
  <li>Regelmäßige <b>Re‑Auditierung</b> (mind. halbjährlich) &amp; Schulungen.</li>
</ul>
"""
    parts.append(non_eu)
    return "\n".join(parts)


def _content_intro(name: str, lang: str) -> str:
    fn = f"{name}_intro_{'de' if lang.startswith('de') else 'en'}.md"
    path = os.path.join(CONTENT_DIR, fn)
    md = _read_text(path)
    return _md_to_html(md) if md else ""


# ------------------------------ HTML-Fragmente -------------------------------

def render_progress_bars(kpis: Dict[str, float]) -> str:
    order = [("Digitalisierung", "digitalisierung"), ("Automatisierung", "automatisierung"),
             ("Compliance", "compliance"), ("Prozessreife", "prozessreife"), ("Innovation", "innovation")]
    parts = []
    for label, key in order:
        pct = int(round(kpis.get(key, 0.0)))
        parts.append(
            f"<div class='bar'><div class='bar__label'>{label}</div>"
            f"<div class='bar__track'><div class='bar__fill' style='width:{pct}%'></div></div>"
            f"<div class='bar__pct'>{pct}%</div></div>"
        )
    return "".join(parts)


def render_benchmark_table(kpis: Dict[str, float], bm: Dict[str, float], lang: str = "de") -> str:
    rows = []
    pairs = [("digitalisierung", "Digitalisierung"), ("automatisierung", "Automatisierung"),
             ("compliance", "Compliance"), ("prozessreife", "Prozessreife"), ("innovation", "Innovation")]
    if not lang.startswith("de"):
        pairs = [("digitalisierung", "Digitisation"), ("automatisierung", "Automation"),
                 ("compliance", "Compliance"), ("prozessreife", "Process maturity"), ("innovation", "Innovation")]
    for key, label in pairs:
        rows.append(f"<tr><td>{label}</td><td>{int(round(kpis.get(key, 0)))}%</td><td>{int(round(bm.get(key, 0)))}%</td></tr>")
    head = "<tr><th>KPI</th><th>Ihr Wert</th><th>Branchen‑Benchmark</th></tr>" if lang.startswith("de") \
           else "<tr><th>KPI</th><th>Your value</th><th>Industry benchmark</th></tr>"
    return "<table class='bm'><thead>" + head + "</thead><tbody>" + "".join(rows) + "</tbody></table>"


# ------------------------------ OpenAI Wrapper -------------------------------

def _chat_once(model: str, messages: List[Dict[str, str]], temperature: Optional[float] = 0.2, tokens: int = 800) -> str:
    """
    Robust gegenüber Parametern der Chat API (max_completion_tokens/max_tokens).
    Erzwingt für gpt-5 die Default-Temperature (=1).
    """
    if not _openai_available:
        raise RuntimeError("OpenAI SDK not available")

    client = OpenAI()
    try:
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_completion_tokens": tokens,
        }
        if model.startswith("gpt-5"):
            kwargs["temperature"] = 1
        elif temperature is not None:
            kwargs["temperature"] = temperature
        resp = client.chat.completions.create(**kwargs)
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        # Retry mit alternativen Parametern
        msg = str(e)
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=tokens,
                temperature=(1 if model.startswith("gpt-5") else (temperature if temperature is not None else 0.2)),
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception:
            raise RuntimeError(f"OpenAI request failed: {msg}") from e


def _prompt(name: str, lang: str) -> str:
    file_name = f"{name}_{'de' if lang.startswith('de') else 'en'}.md"
    path = os.path.join(PROMPTS_DIR, file_name)
    txt = _read_text(path)
    if txt:
        log.info("Loaded prompt: %s", file_name)
    return txt


def _gpt_section(section: str, lang: str, context: Dict[str, Any], model: Optional[str] = None) -> str:
    prompt = _prompt(section, lang)
    if not prompt:
        defaults = {
            "executive_summary": "<p><b>Key Takeaways:</b> Status, Potenzial & Quick Wins priorisieren; 12‑Wochen‑Plan; ROI früh sichtbar machen.</p>",
            "quick_wins": "<ul><li>3–5 Routineprozesse automatisieren</li><li>Dokumenten‑KI</li><li>CRM‑Assistent</li><li>FAQ‑Bot</li><li>Reporting automatisieren</li></ul>",
            "roadmap": "<ol><li>W1–2: Setup & Governance</li><li>W3–4: Pilot</li><li>W5–8: Rollout</li><li>W9–12: Skalieren</li></ol>",
            "risks": ("<table class='table'><thead><tr><th>Risiko</th><th>P</th><th>I</th><th>Score</th><th>Mitigation</th></tr></thead>"
                      "<tbody><tr><td>Datenschutz</td><td>M</td><td>H</td><td>20</td><td>DSGVO‑Prozesse</td></tr>"
                      "<tr><td>Regulatorik</td><td>M</td><td>H</td><td>18</td><td>AI‑Act‑Check</td></tr></tbody></table>"),
            "compliance": "<ul><li>AI‑Act‑Klassifizierung</li><li>Transparenz & Logging</li><li>DPIA/DSGVO</li><li>Dokumentation</li><li>Monitoring</li></ul>",
            "doc_digest": "<p><b>Executive Knowledge Digest:</b> Strategie, Technologie, Governance, Kultur.</p>",
            "tools": "<p>Die folgende Auswahl führt geeignete Tools mit EU‑Host‑Hinweis auf.</p>",
            "foerderprogramme": "<p>Relevante Förderprogramme mit Fristen und Links – bitte Deadlines beachten.</p>",
            "business": "<p>Der Business‑Case profitiert von frühen Automatisierungsgewinnen; Payback ~4 Monate als Baseline.</p>",
            "recommendations": "<ul><li>Strategische Leitlinien als Ergänzung zu den Quick Wins</li></ul>",
            "gamechanger": "<p>Ein bis zwei Hebel mit hoher Wirkung (z. B. Document‑AI at Scale, Agenten im Backoffice).</p>",
            "vision": "<p>Nordstern‑Formulierung für 12–18 Monate.</p>",
            "persona": "<p>Haupt‑Stakeholder (Buyer Persona) mit Pain Points und Zielen.</p>",
            "praxisbeispiel": "<p>Kurzes Praxisbeispiel (Case) mit Ergebniszahlen.</p>",
            "coach": "<p>Enablement‑Plan: Schulungen, Guidelines, Hands‑on Sessions.</p>",
        }
        return defaults.get(section, "")

    system = (
        "You are a senior management consultant. "
        "Write crisp, C-level, practical guidance. Use HTML only (no markdown)."
    )

    # Kontext + Aliase für Prompts (zur Beseitigung von {branche}/{date}/business_case_json.* im Output)
    ctx = dict(context)
    bc = ctx.get("business_case") or {}
    roi_cfg = _load_roi_config()
    bucket = _size_to_roi_bucket((ctx.get("briefing") or {}).get("unternehmensgroesse") or "small")
    hours_range = (roi_cfg.get(bucket, {}).get("hours_saved_per_week_range") or [0, 0])
    avg_hours_week = (float(hours_range[0]) + float(hours_range[1])) / 2.0 if hours_range else 0.0
    ctx.update({
        "branche": (ctx.get("briefing") or {}).get("branche_label") or (ctx.get("briefing") or {}).get("branche") or "",
        "hauptleistung": (ctx.get("briefing") or {}).get("hauptleistung") or "",
        "date": ctx.get("today"),
        "business_case_json": {
            "ROI_Jahr_1": f"{bc.get('roi_year1_pct', 0)}%",
            "Payback_Monate": bc.get("payback_months", 0),
            "Drei_Jahres_Gewinn": _euro(bc.get("three_year_gain_eur", 0)),
            "eingesparte_Stunden_Monat": round(avg_hours_week * 4.33, 1) if avg_hours_week else "n/a",
        },
    })

    user = prompt.format(**ctx)
    try:
        model_to_use = model or (EXEC_SUMMARY_MODEL if section == "executive_summary" else DEFAULT_MODEL)
        return _chat_once(model_to_use, [{"role": "system", "content": system}, {"role": "user", "content": user}], temperature=0.2, tokens=900)
    except Exception as e:
        # Fallback auf DEFAULT/FALLBACK-Modell
        log.warning("GPT generation failed for %s: %s", section, e)
        try:
            fb_model = EXEC_SUMMARY_MODEL_FALLBACK if section == "executive_summary" else DEFAULT_MODEL
            return _chat_once(fb_model, [{"role": "system", "content": system}, {"role": "user", "content": user}], temperature=0.2, tokens=900)
        except Exception as e2:
            log.error("Fallback generation failed for %s: %s", section, e2)
            return ""


# -------------------------- Live-Sektionen (extern) --------------------------

def build_live_sections(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Kapselt Live-Suche; wenn Keys fehlen oder SEARCH_PROVIDER='off', wird eine
    saubere, deaktivierte Sektion zurückgegeben (kein 'Quellen: 1' Widerspruch).
    """
    if SEARCH_PROVIDER in {"off", "none"} or (not TAVILY_API_KEY and not PERPLEXITY_API_KEY):
        return {
            "enabled": False,
            "note": "Live‑Updates deaktiviert (API‑Keys nicht gesetzt).",
            "news": [], "tools": [], "funding": [], "sources": [],
        }
    # Lazy import, damit lokale Builds ohne httpx-Dependencies laufen
    from websearch_utils import build_live_sections as _build  # type: ignore
    return _build(context)


# ------------------------------ Postprocessing --------------------------------

def _replace_placeholders(html: str, ctx: Dict[str, Any]) -> str:
    """
    Ersetzt in GPT-HTML verbleibende Platzhalter wie {date}, {branche}, {business_case_json.*}
    """
    if not html:
        return html
    rep = {
        "{date}": ctx.get("date") or _today(),
        "{branche}": ctx.get("branche") or "",
        "{hauptleistung}": ctx.get("hauptleistung") or "",
        "{business_case_json.ROI_Jahr_1}": f"{ctx.get('roi_year1_pct', 0)}%",
        "{business_case_json.Payback_Monate}": str(ctx.get("payback_months", "")),
        "{business_case_json.Drei_Jahres_Gewinn}": _euro(ctx.get("three_year_gain_eur", 0)),
        "{business_case_json.eingesparte_Stunden_Monat}": str(ctx.get("hours_saved_pm", "n/a")),
    }
    for k, v in rep.items():
        html = html.replace(k, str(v))
    return html


# -------------------------------- Rendering ----------------------------------

def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
        enable_async=False,
    )


def analyze_briefing(raw: Dict[str, Any], lang: str = "de") -> str:
    norm = normalize_briefing(raw)
    miss = missing_fields(norm)
    if miss:
        # Logging der fehlenden Pflichtfelder (Server sollte 422 senden, hier nur Hinweis)
        log.info("Missing normalized fields: %s", miss)

    # KPIs & Benchmarks
    kpis = calculate_kpis(norm)
    score = overall_score(kpis)
    badge = quality_badge(score)
    bm = load_benchmarks(norm)

    # Fragmente
    kpis_progress_html = render_progress_bars(kpis)
    kpis_benchmark_table_html = render_benchmark_table(kpis, bm, lang=lang)
    bc = business_case(norm, score)

    # Kontext für GPT/Platzhalter
    today = _today()
    gpt_ctx = {
        "briefing": norm,
        "score_percent": score,
        "kpis": kpis,
        "benchmarks": bm,
        "business_case": bc,
        "today": today,
        # Aliase:
        "branche": norm.get("branche_label") or norm.get("branche"),
        "hauptleistung": norm.get("hauptleistung") or "",
        "date": today,
    }

    # Kernsektionen (GPT)
    sections = {
        "executive_summary_html": _gpt_section("executive_summary", lang, gpt_ctx, model=EXEC_SUMMARY_MODEL),
        "quick_wins_html": _gpt_section("quick_wins", lang, gpt_ctx),
        "roadmap_html": _gpt_section("roadmap", lang, gpt_ctx),
        "risks_html": _gpt_section("risks", lang, gpt_ctx),
        "compliance_html": _gpt_section("compliance", lang, gpt_ctx),
        "doc_digest_html": _gpt_section("doc_digest", lang, gpt_ctx),
        "business_html": _gpt_section("business", lang, gpt_ctx),
        "recommendations_html": _gpt_section("recommendations", lang, gpt_ctx),
        "gamechanger_html": _gpt_section("gamechanger", lang, gpt_ctx),
        "vision_html": _gpt_section("vision", lang, gpt_ctx),
        "persona_html": _gpt_section("persona", lang, gpt_ctx),
        "praxisbeispiel_html": _gpt_section("praxisbeispiel", lang, gpt_ctx),
        "coach_html": _gpt_section("coach", lang, gpt_ctx),
        "tools_html": _gpt_section("tools", lang, gpt_ctx),
        "foerderprogramme_html": _gpt_section("foerderprogramme", lang, gpt_ctx),
    }

    # Platzhalter-Postprocessing für alle GPT-Abschnitte
    roi_cfg = _load_roi_config()
    bucket = _size_to_roi_bucket(norm.get("unternehmensgroesse") or "small")
    hours_range = (roi_cfg.get(bucket, {}).get("hours_saved_per_week_range") or [0, 0])
    avg_hours_week = (float(hours_range[0]) + float(hours_range[1])) / 2.0 if hours_range else 0.0
    post_ctx = {
        "date": today,
        "branche": gpt_ctx["branche"],
        "hauptleistung": gpt_ctx["hauptleistung"],
        "roi_year1_pct": bc.get("roi_year1_pct", 0.0),
        "payback_months": bc.get("payback_months", 0.0),
        "three_year_gain_eur": bc.get("three_year_gain_eur", 0.0),
        "hours_saved_pm": round(avg_hours_week * 4.33, 1) if avg_hours_week else "n/a",
    }
    for k, v in list(sections.items()):
        sections[k] = _replace_placeholders(v, post_ctx)

    # Branchenkontext & Appendix
    sections["industry_context_html"] = _industry_context_html(norm.get("branche") or "", lang)
    sections["appendix_checklists_html"] = _appendix_checklists_html(lang)

    # Live-Kacheln (Bundesland-Filter & Fußnoten)
    live = build_live_sections({
        "branche": norm.get("branche_label") or norm.get("branche"),
        "size": norm.get("unternehmensgroesse_label") or norm.get("unternehmensgroesse"),
        "country": "DE",
        "region_code": norm.get("bundesland_code") or "",
    })
    flags = {"eu_host_check": True, "regulatory": True, "case_studies": True}

    # Score-Legende
    score_legend = ("Score 0–54 = Basic · 55–69 = Fair · 70–84 = Good · ≥ 85 = Excellent. "
                    "Gewichtung: Digitalisierung/Automatisierung/Compliance/Prozessreife/Innovation je 20 %.")

    # Rendering
    env = _env()
    tpl_name = "pdf_template.html" if lang.startswith("de") else "pdf_template_en.html"
    tpl = env.get_template(tpl_name)
    html = tpl.render(
        meta={"title": "KI-Status-Report" if lang.startswith("de") else "AI Status Report", "date": today, "lang": lang},
        briefing=norm,
        score_percent=score,
        quality_badge=badge,
        kpis_progress_html=kpis_progress_html,
        kpis_benchmark_table_html=kpis_benchmark_table_html,
        business_case=bc,
        sections=sections,
        live=live,
        flags=flags,
        score_legend=score_legend,
    )
    return html


def produce_admin_attachments(raw: Dict[str, Any]) -> Dict[str, str]:
    norm = normalize_briefing(raw)
    miss = missing_fields(norm)
    payload = {
        "briefing_raw.json": json.dumps(raw, ensure_ascii=False, indent=2),
        "briefing_normalized.json": json.dumps(norm, ensure_ascii=False, indent=2),
        "briefing_missing_fields.json": json.dumps({"missing": miss, "count": len(miss)}, ensure_ascii=False, indent=2),
    }
    return payload
