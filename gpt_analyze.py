# File: gpt_analyze.py
# -*- coding: utf-8 -*-
"""
Analyse & Rendering für den KI-Status-Report (Gold-Standard+)

Änderungen (2025-10-05):
- P0: Platzhalter-Fix (unternehmensgroesse, bundesland, score/roi/payback inkl. .1f-Formatter)
- P0: Benchmarks-Synonyme + Validierung; kein 0%-Tisch mehr (Fallback Median)
- P1: Sanitizer für GPT-HTML (<!DOCTYPE>, <html>, <head>, <body>, <title> entfernt)
- P1: Datums-Normalisierung ("Stand: <alt>" -> heute)
- P1: Live-Quellen pro Karte (news/tools/funding), kein Widerspruch bei leeren News
- P1: Branchenkontext mit Fallback-Pfaden
- P2: KPI-Balken mit Median-Haarlinie + Δ(pp)
- NEU: "Unternehmensprofil & Ziele" aus Freitextfeldern sichtbar im Report
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
BRANCHEN_DIR_DEFAULT = os.path.join(DATA_DIR, "branchenkontext")
BRANCHEN_DIR_ALT = os.path.join(BASE_DIR, "branchenkontext")
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
    """Schlanker Markdown->HTML Konverter (H1–H3, UL, Absätze, Links)."""
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
SIZE_LABEL = {"solo": "1", "small": "2‑10", "kmu": "11‑100+"}
BR_LABEL = {
    "beratung": "Beratung & Dienstleistungen", "it": "IT & Software",
    "marketing": "Marketing & Werbung", "medien": "Medien & Kreativwirtschaft",
    "handel": "Handel & E‑Commerce", "industrie": "Industrie & Produktion",
    "gesundheit": "Gesundheit & Pflege", "bau": "Bauwesen & Architektur",
    "logistik": "Transport & Logistik", "verwaltung": "Verwaltung",
    "bildung": "Bildung", "finanzen": "Finanzen & Versicherungen",
}
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
    if size_key not in SIZE_LABEL:
        size_key = "small" if size_key not in ("kmu", "konzern", "enterprise") else "kmu"

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
    size_variants = [sz] if sz in SIZE_LABEL else ["solo", "small", "kmu"]
    names = []
    for b in br_variants:
        for s in size_variants:
            names.append(f"benchmarks_{b}_{s}.json")
    return names


def pick_benchmark_file(branche_key: str, size_key: str) -> str:
    candidates = _bench_json_path_candidates(branche_key, size_key)
    for name in candidates:
        path = os.path.join(DATA_DIR, name)
        if os.path.exists(path):
            log.info("Loaded benchmark: %s", name)
            return path
    # Fallback
    return ""


def _parse_percentish(val: Any) -> float:
    """Akzeptiert 65, '65', '65%', '65,0', '0.65' (→ 65)."""
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


_BENCH_SYNONYMS = {
    "digitisation": "digitalisierung",
    "digitization": "digitalisierung",
    "digital": "digitalisierung",
    "automation": "automatisierung",
    "automatisierung": "automatisierung",
    "compliance": "compliance",
    "datenschutz": "compliance",
    "privacy": "compliance",
    "process": "prozessreife",
    "prozessreife": "prozessreife",
    "maturity": "prozessreife",
    "innovation": "innovation",
}

_BENCH_KEYS = ("digitalisierung", "automatisierung", "compliance", "prozessreife", "innovation")


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
    if rows and "Kriterium" in rows[0]:
        col = "KMU" if sz == "kmu" else ("Klein" if sz == "small" else "Solo")
        for r in rows:
            k = (r.get("Kriterium") or "").strip().lower()
            key = _BENCH_SYNONYMS.get(k, k)
            if key not in _BENCH_KEYS:
                continue
            vv = _parse_percentish(r.get(col))
            if vv:
                result[key] = vv
    else:
        # Generisches Mapping
        for r in rows:
            k = (r.get("Kategorie") or "").strip().lower()
            key = _BENCH_SYNONYMS.get(k, k)
            if key not in _BENCH_KEYS:
                continue
            vv = _parse_percentish(r.get("Wert_Durchschnitt"))
            if vv:
                result[key] = vv

    # Lücken auffüllen mit Median 60
    if result:
        for need in _BENCH_KEYS:
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
            for k, v in (data.items() if isinstance(data, dict) else []):
                kk = _BENCH_SYNONYMS.get(str(k).strip().lower(), str(k).strip().lower())
                if kk in _BENCH_KEYS:
                    out[kk] = _parse_percentish(v)
            # Vollständigkeit erzwingen, sonst Median
            for need in _BENCH_KEYS:
                out.setdefault(need, 60.0)
            # Log: Anzahl der gefundenen Keys
            log.info("Bench keys present: %s/5", sum(1 for k in _BENCH_KEYS if k in out))
            return out
        except Exception as e:
            log.warning("Benchmark JSON parsing failed (%s), trying CSV fallback", e)
    csv_bm = _load_benchmarks_from_csv(br, sz)
    if csv_bm:
        log.info("Loaded benchmark fallback from CSV for %s/%s", br, sz)
        return csv_bm
    # Ultimativer Fallback (Median)
    return {k: 60.0 for k in _BENCH_KEYS}


# --------------------------- KPIs / Business Case ----------------------------

def calculate_kpis(norm: Dict[str, Any]) -> Dict[str, float]:
    digi = _to_percent(norm.get("digitalisierungsgrad") or 0, 10.0)
    auto_map = {"sehr_hoch": 85, "eher_hoch": 65, "mittel": 50, "eher_niedrig": 35, "sehr_niedrig": 20}
    auto = float(auto_map.get(str(norm.get("automatisierungsgrad") or "").lower(), 40))

    comp = 0.0
    comp += 25.0 if _is_true(norm.get("datenschutz")) else 0.0
    for flag in ("governance", "folgenabschaetzung", "meldewege", "loeschregeln"):
        val = str(norm.get(flag) or "").strip().lower()
        if val in {"ja", "yes", "true", "1", "teilweise", "partial"}:
            comp += 18.75
    comp = min(100.0, round(comp or 55.0, 1))

    paper = str(norm.get("prozesse_papierlos") or "").lower()
    paper_map = {"0-20": 10, "21-50": 40, "51-80": 65, "81-100": 80}
    proc = float(paper_map.get(paper, 60))
    if str(norm.get("governance") or "").strip():
        proc = min(100.0, proc + 8.0)

    kult_map = {"sehr_offen": 80, "eher_offen": 70, "neutral": 55, "eher_zurueckhaltend": 45, "sehr_zurueckhaltend": 35}
    know_map = {"expertenwissen": 80, "fortgeschritten": 70, "mittel": 60, "grundkenntnisse": 50, "keine": 40}
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
    invest_map = {"unter_2000": 1500, "2000_10000": 6000, "10000_50000": 20000, "ueber_50000": 60000, "unter_1000": 1000}
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
        annual_saving = invest * 4.0

    payback_months = max(0.5, round(invest / (annual_saving / 12.0), 1)) if annual_saving > 0 else 12.0
    if ROI_BASELINE_MONTHS > 0 and payback_months > ROI_BASELINE_MONTHS:
        annual_saving = max(1.0, invest * 12.0 / ROI_BASELINE_MONTHS)
        payback_months = round(invest / (annual_saving / 12.0), 1)

    roi_y1_pct = round(((annual_saving - invest) / invest) * 100.0, 1) if invest > 0 else 0.0
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
    # Fallback-Pfade prüfen
    for base in (BRANCHEN_DIR_DEFAULT, BRANCHEN_DIR_ALT):
        path = os.path.join(base, fn)
        if os.path.exists(path):
            return _md_to_html(_read_text(path))
    return ""


def _appendix_checklists_html(lang: str) -> str:
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

def render_progress_bars(kpis: Dict[str, float], bm: Dict[str, float]) -> str:
    order = [("Digitalisierung", "digitalisierung"), ("Automatisierung", "automatisierung"),
             ("Compliance", "compliance"), ("Prozessreife", "prozessreife"), ("Innovation", "innovation")]
    parts = []
    for label, key in order:
        pct = int(round(kpis.get(key, 0.0)))
        med = int(round(bm.get(key, 60.0)))
        delta = pct - med
        sign = "+" if delta >= 0 else ""
        parts.append(
            f"<div class='bar'>"
            f"<div class='bar__label'>{label}</div>"
            f"<div class='bar__track'>"
            f"<div class='bar__fill' style='width:{pct}%'></div>"
            f"<div class='bar__median' style='left:{med}%'></div>"
            f"</div>"
            f"<div class='bar__pct'>{pct}% <span class='bar__delta'>(Δ {sign}{delta} pp)</span></div>"
            f"</div>"
        )
    return "".join(parts)


# ------------------------------ OpenAI Wrapper -------------------------------

def _chat_once(model: str, messages: List[Dict[str, str]], temperature: Optional[float] = 0.2, tokens: int = 900) -> str:
    if not _openai_available:
        raise RuntimeError("OpenAI SDK not available")
    client = OpenAI()
    try:
        kwargs: Dict[str, Any] = {"model": model, "messages": messages, "max_completion_tokens": tokens}
        if model.startswith("gpt-5"):
            kwargs["temperature"] = 1
        elif temperature is not None:
            kwargs["temperature"] = temperature
        resp = client.chat.completions.create(**kwargs)
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
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


def _sanitize_gpt_html(html: str) -> str:
    if not html:
        return ""
    # Entferne DOCTYPE & HTML-Wrapper
    html = re.sub(r"(?is)<!DOCTYPE.*?>", "", html)
    html = re.sub(r"(?is)</?(html|head|body|title)[^>]*>", "", html)
    # Entferne Script/Style
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", html)
    return html.strip()


def _normalize_dates_in_html(html: str, today: str) -> str:
    if not html:
        return html
    # "Stand: YYYY-MM-DD" oder "Stand: Monat YYYY" -> heute
    html = re.sub(r"Stand:\s*(\d{4}-\d{2}-\d{2}|[A-Za-zÄÖÜäöü]+ \d{4})", f"Stand: {today}", html)
    return html


def _gpt_section(section: str, lang: str, context: Dict[str, Any], model: Optional[str] = None) -> str:
    prompt = _prompt(section, lang)
    if not prompt:
        defaults = {
            "executive_summary": "<p><b>Key Takeaways:</b> Status, Potenzial & Quick Wins priorisieren; 12‑Wochen‑Plan; ROI früh sichtbar machen.</p>",
            "quick_wins": "<ul><li>3–5 Routineprozesse automatisieren</li><li>Dokumenten‑KI</li><li>CRM‑Assistent</li><li>FAQ‑Bot</li><li>Reporting automatisieren</li></ul>",
            "roadmap": "<ol><li>W1–2: Setup & Governance</li><li>W3–4: Pilot</li><li>W5–8: Rollout</li><li>W9–12: Skalieren</li></ol>",
            "risks": ("<table class='table'><thead><tr><th>Risiko</th><th>P</th><th>I</th><th>Score</th><th>Mitigation</th></tr></thead>"
                      "<tbody><tr><td>Datenschutz</td><td>M</td><td>H</td><td>20</td><td>DSGVO‑Prozesse</td></tr></tbody></table>"),
            "compliance": "<ul><li>AI‑Act‑Klassifizierung</li><li>Transparenz & Logging</li><li>DPIA/DSGVO</li><li>Dokumentation</li><li>Monitoring</li></ul>",
            "doc_digest": "<p><b>Executive Knowledge Digest:</b> Strategie, Technologie, Governance, Kultur.</p>",
            "tools": "<p>Die folgende Auswahl führt geeignete Tools mit EU‑Host‑Hinweis auf.</p>",
            "foerderprogramme": "<p>Relevante Förderprogramme mit Fristen und Links – bitte Deadlines beachten.</p>",
            "business": "<p>Der Business‑Case profitiert von frühen Automatisierungsgewinnen; Payback ~4 Monate als Baseline.</p>",
            "recommendations": "<ul><li>Strategische Leitlinien als Ergänzung zu den Quick Wins</li></ul>",
            "gamechanger": "<p>Ein bis zwei Hebel mit hoher Wirkung.</p>",
            "vision": "<p>Nordstern‑Formulierung für 12–18 Monate.</p>",
            "persona": "<p>Haupt‑Stakeholder (Buyer Persona) mit Pain Points und Zielen.</p>",
            "praxisbeispiel": "<p>Kurzes Praxisbeispiel (Case) mit Ergebniszahlen.</p>",
            "coach": "<p>Enablement‑Plan: Schulungen, Guidelines, Hands‑on Sessions.</p>",
        }
        return defaults.get(section, "")

    system = (
        "You are a senior management consultant. "
        "Write crisp, C-level, practical guidance. Use HTML only (no markdown). "
        "Tailor to the provided industry, size, region and the free-text briefing profile (priorities, use cases, goals). "
        "Avoid generic examples from unrelated industries."
    )

    # Prompt-Kontext
    ctx = dict(context)
    user = prompt.format(**ctx)
    try:
        model_to_use = model or (EXEC_SUMMARY_MODEL if section == "executive_summary" else DEFAULT_MODEL)
        html = _chat_once(model_to_use, [{"role": "system", "content": system}, {"role": "user", "content": user}], temperature=0.2, tokens=900)
        return _sanitize_gpt_html(html)
    except Exception as e:
        log.warning("GPT generation failed for %s: %s", section, e)
        try:
            fb_model = EXEC_SUMMARY_MODEL_FALLBACK if section == "executive_summary" else DEFAULT_MODEL
            html = _chat_once(fb_model, [{"role": "system", "content": system}, {"role": "user", "content": user}], temperature=0.2, tokens=900)
            return _sanitize_gpt_html(html)
        except Exception as e2:
            log.error("Fallback generation failed for %s: %s", section, e2)
            return ""


# -------------------------- Live-Sektionen (extern) --------------------------

def build_live_sections(context: Dict[str, Any]) -> Dict[str, Any]:
    if SEARCH_PROVIDER in {"off", "none"} or (not TAVILY_API_KEY and not PERPLEXITY_API_KEY):
        return {
            "enabled": False,
            "note": "Live‑Updates deaktiviert (API‑Keys nicht gesetzt).",
            "news": [], "tools": [], "funding": [],
            "news_sources": [], "tools_sources": [], "funding_sources": [],
        }
    from websearch_utils import build_live_sections as _build  # type: ignore
    return _build(context)


# ------------------------------ Postprocessing --------------------------------

def _replace_placeholders(html: str, ctx: Dict[str, Any]) -> str:
    """
    Ersetzt verbleibende Platzhalter inkl. Formatspz. {var:.1f}
    """
    if not html:
        return html

    # Direkte Mappings
    direct = {
        "date": ctx.get("date") or _today(),
        "branche": ctx.get("branche") or "",
        "hauptleistung": ctx.get("hauptleistung") or "",
        "unternehmensgroesse": ctx.get("unternehmensgroesse_label") or ctx.get("unternehmensgroesse") or "",
        "bundesland": ctx.get("bundesland_code") or "",
        "score_percent": ctx.get("score_percent", 0.0),
        "roi_year1_pct": ctx.get("roi_year1_pct", 0.0),
        "payback_months": ctx.get("payback_months", 0.0),
        "three_year_gain": _euro(ctx.get("three_year_gain_eur", 0.0)),
        "hours_saved_pm": ctx.get("hours_saved_pm", "n/a"),
    }

    # {var} & {var:.1f}
    def repl(m: re.Match) -> str:
        var = m.group("var")
        fmt = m.group("fmt")
        val = direct.get(var, "")
        if isinstance(val, (int, float)) and fmt:
            try:
                return f"{val:{fmt}}"
            except Exception:
                return str(val)
        return str(val)

    html = re.sub(r"\{(?P<var>[a-zA-Z0-9_]+)(?::(?P<fmt>[^}]+))?\}", repl, html)

    return html


# -------------------------------- Rendering ----------------------------------

def _env() -> Environment:
    return Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=select_autoescape(["html"]), enable_async=False)


def _extract_profile_html(raw: Dict[str, Any], norm: Dict[str, Any]) -> str:
    """Baut das 'Unternehmensprofil & Ziele' aus Freitextfeldern."""
    if not raw:
        return ""
    bullets: List[str] = []
    # Harte Priorität
    if norm.get("hauptleistung"):
        bullets.append(f"<b>Hauptleistung</b>: {norm['hauptleistung']}")
    for key, label in [
        ("ki_projekte", "Aktuelle/Geplante KI‑Projekte"),
        ("ki_potenzial", "KI‑Potenzial (Vision)"),
        ("strategische_ziele", "Strategische Ziele"),
    ]:
        val = raw.get(key) or (raw.get("answers", {}) if isinstance(raw.get("answers"), dict) else {}).get(key)
        if val and str(val).strip():
            bullets.append(f"<b>{label}</b>: {str(val).strip()}")
    # Listen
    for key, label in [
        ("projektziel", "Projektziele"),
        ("ki_usecases", "Fokus‑Use‑Cases"),
        ("zielgruppen", "Zielgruppen"),
    ]:
        arr = raw.get(key) or (raw.get("answers", {}) if isinstance(raw.get("answers"), dict) else {}).get(key)
        if isinstance(arr, list) and arr:
            bullets.append(f"<b>{label}</b>: " + ", ".join(str(x) for x in arr))

    if not bullets:
        return ""
    return "<ul>" + "".join(f"<li>{b}</li>" for b in bullets) + "</ul>"


def analyze_briefing(raw: Dict[str, Any], lang: str = "de") -> str:
    norm = normalize_briefing(raw)
    miss = missing_fields(norm)
    if miss:
        log.info("Missing normalized fields: %s", miss)

    kpis = calculate_kpis(norm)
    score = overall_score(kpis)
    badge = quality_badge(score)
    bm = load_benchmarks(norm)

    kpis_progress_html = render_progress_bars(kpis, bm)
    kpis_benchmark_table_html = render_benchmark_table(kpis, bm, lang=lang)
    bc = business_case(norm, score)

    today = _today()
    profile_html = _extract_profile_html(raw, norm)

    # ROI-Stunden (aus config) für Platzhalter
    roi_cfg = _load_roi_config()
    bucket = _size_to_roi_bucket(norm.get("unternehmensgroesse") or "small")
    hours_range = (roi_cfg.get(bucket, {}).get("hours_saved_per_week_range") or [0, 0])
    avg_hours_week = (float(hours_range[0]) + float(hours_range[1])) / 2.0 if hours_range else 0.0

    # Kontext für GPT/Platzhalter
    gpt_ctx = {
        "briefing": norm,
        "briefing_raw": raw,
        "score_percent": score,
        "kpis": kpis,
        "benchmarks": bm,
        "business_case": bc,
        "today": today,
        "branche": norm.get("branche_label") or norm.get("branche"),
        "unternehmensgroesse_label": norm.get("unternehmensgroesse_label"),
        "bundesland_code": norm.get("bundesland_code"),
        "hauptleistung": norm.get("hauptleistung") or "",
        "profile_text": re.sub(r"<.*?>", "", profile_html).strip(),
    }

    # GPT-Abschnitte
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
        "profile_html": profile_html,
    }

    # Platzhalter-Replacement & Datumsnormalisierung
    post_ctx = {
        "date": today,
        "branche": gpt_ctx["branche"],
        "hauptleistung": gpt_ctx["hauptleistung"],
        "unternehmensgroesse_label": norm.get("unternehmensgroesse_label"),
        "unternehmensgroesse": norm.get("unternehmensgroesse_label"),
        "bundesland_code": norm.get("bundesland_code"),
        "score_percent": score,
        "roi_year1_pct": bc.get("roi_year1_pct", 0.0),
        "payback_months": bc.get("payback_months", 0.0),
        "three_year_gain_eur": bc.get("three_year_gain_eur", 0.0),
        "hours_saved_pm": round(avg_hours_week * 4.33, 1) if avg_hours_week else "n/a",
    }
    for k, v in list(sections.items()):
        v = _replace_placeholders(v, post_ctx)
        v = _normalize_dates_in_html(v, today)
        sections[k] = v

    # Branchenkontext & Appendix
    sections["industry_context_html"] = _industry_context_html(norm.get("branche") or "", lang)
    sections["appendix_checklists_html"] = _appendix_checklists_html(lang)

    # Live-Sektionen
    live = build_live_sections({
        "branche": gpt_ctx["branche"],
        "size": norm.get("unternehmensgroesse_label") or norm.get("unternehmensgroesse"),
        "country": "DE",
        "region_code": norm.get("bundesland_code") or "",
    })
    flags = {"eu_host_check": True, "regulatory": True, "case_studies": True}

    score_legend = ("Score 0–54 = Basic · 55–69 = Fair · 70–84 = Good · ≥ 85 = Excellent. "
                    "Gewichtung: Digitalisierung/Automatisierung/Compliance/Prozessreife/Innovation je 20 %.")

    env = _env()
    tpl_name = "pdf_template.html" if lang.startswith("de") else "pdf_template_en.html"
    tpl = env.get_template(tpl_name)
    html = tpl.render(
        meta={"title": "KI-Status-Report" if lang.startswith("de") else "AI Status Report", "date": today, "lang": lang},
        briefing=norm,
        briefing_raw=raw,
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


def produce_admin_attachments(raw: Dict[str, Any]) -> Dict[str, str]:
    norm = normalize_briefing(raw)
    miss = missing_fields(norm)
    payload = {
        "briefing_raw.json": json.dumps(raw, ensure_ascii=False, indent=2),
        "briefing_normalized.json": json.dumps(norm, ensure_ascii=False, indent=2),
        "briefing_missing_fields.json": json.dumps({"missing": miss, "count": len(miss)}, ensure_ascii=False, indent=2),
    }
    return payload
