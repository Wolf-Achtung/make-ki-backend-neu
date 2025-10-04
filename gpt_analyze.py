# File: gpt_analyze.py
# -*- coding: utf-8 -*-
"""
Analyse & Rendering für den KI-Status-Report (Gold-Standard+)

- Robust: OpenAI v1 Wrapper (max_completion_tokens / Fallback max_tokens)
- normalize_briefing(): Alias-Mapping (DE/EN) -> konsistente Felder
- Benchmarks: deterministische JSON-Auswahl mit Synonym-Fallbacks; CSV-Fallback
- ROI: nutzt data/config_roi.json (größenabhängig, plausibel)
- Live-Intro / optionale Prompt-Addons bleiben wie zuvor (prompts/)
- analyze_briefing(): rendert vollständiges HTML (DE/EN Templates)
- produce_admin_attachments(): raw/normalized/missing als JSON (für Admin-Mail)
"""

from __future__ import annotations

import csv
import json
import logging
import os
from typing import Any, Dict, List, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

# OpenAI v1 (robuster Wrapper)
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

BASE_DIR = os.path.abspath(os.getenv("APP_BASE", os.getcwd()))
TEMPLATE_DIR = os.getenv("TEMPLATE_DIR", os.path.join(BASE_DIR, "templates"))
PROMPTS_DIR = os.getenv("PROMPTS_DIR", os.path.join(BASE_DIR, "prompts"))
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))

EXEC_SUMMARY_MODEL = os.getenv("EXEC_SUMMARY_MODEL", os.getenv("GPT_MODEL_NAME", "gpt-4o"))
DEFAULT_MODEL = os.getenv("GPT_MODEL_NAME", "gpt-4o-mini")


# ------------------------------ Helpers -------------------------------------

def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _to_percent(value: Any, max_value: float) -> float:
    """Konvertiert einen Rohwert (0..max_value) in Prozent (0..100)."""
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


# --------------------------- Normalisierung ---------------------------------

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

# Slug-Synonyme zu Datei-Slugs im data/-Ordner
BR_SLUGS = {
    "beratung": ["beratung", "beratung_dienstleistungen"],
    "it": ["it", "it_software"],
    "marketing": ["marketing", "marketing_werbung"],
    "medien": ["medien", "medien_kreativwirtschaft"],
    "handel": ["handel_e_commerce"],
    "industrie": ["industrie_produktion"],
    "gesundheit": ["gesundheit_pflege"],
    "bau": ["bauwesen_architektur"],
    "logistik": ["transport_logistik"],
    "verwaltung": ["verwaltung"],
    "bildung": ["bildung"],
    "finanzen": ["finanzen", "finanzen_versicherungen"],
}
SIZE_ALIASES = {
    "solo": ["solo"],
    "small": ["small", "team", "team_2_10", "klein"],
    "kmu": ["kmu", "kmu_11_100", "mittel", "konzern"],  # wir fallen auf kmu zurück, wenn größer
}


def normalize_briefing(raw: Dict[str, Any]) -> Dict[str, Any]:
    # answers > raw
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
    # Label (menschlich)
    BR_LABEL = {
        "beratung": "Beratung & Dienstleistungen", "it": "IT & Software",
        "marketing": "Marketing & Werbung", "medien": "Medien & Kreativwirtschaft",
        "handel": "Handel & E‑Commerce", "industrie": "Industrie & Produktion",
        "gesundheit": "Gesundheit & Pflege", "bau": "Bauwesen & Architektur",
        "logistik": "Transport & Logistik", "verwaltung": "Verwaltung",
        "bildung": "Bildung", "finanzen": "Finanzen & Versicherungen",
    }
    SIZE_LABEL = {"solo": "1", "small": "2‑10", "kmu": "11‑100+"}

    # Heuristik: wenn size nicht solo/kmu ist, als small behandeln
    if size_key not in ("solo", "small", "kmu"):
        if size_key in ("konzern", "enterprise"):
            size_key = "kmu"
        else:
            size_key = "small"

    norm["branche_label"] = BR_LABEL.get(br_key, norm.get("branche"))
    norm["unternehmensgroesse_label"] = SIZE_LABEL.get(size_key, norm.get("unternehmensgroesse"))
    norm["branche"] = br_key
    norm["unternehmensgroesse"] = size_key
    return norm


def missing_fields(norm: Dict[str, Any]) -> List[str]:
    req = ["branche", "unternehmensgroesse", "bundesland", "hauptleistung", "investitionsbudget"]
    return [k for k in req if not (norm.get(k) and str(norm[k]).strip())]


# ------------------------------ Benchmarks -----------------------------------

def _bench_json_path_candidates(br: str, sz: str) -> List[str]:
    # erst alle Slugs zur Branche abarbeiten, dann Size-Aliase
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
    candidates = _bench_json_path_candidates(branche_key, size_key)
    for name in candidates:
        path = os.path.join(DATA_DIR, name)
        if os.path.exists(path):
            log.info("Loaded benchmark: %s", name)
            return path
    return ""


def _load_benchmarks_from_csv(br: str, sz: str) -> Dict[str, float]:
    """
    Fallback: benchmark_{slug}.csv ODER benchmark_default.csv
    Erwartete Formen:
      - Spalten: Kategorie, Wert_Durchschnitt (0..10) -> *10
      - Alternativ: Kriterium + Spalten Solo/Klein/KMU (teils bereits in %)
    Mapping auf unsere KPIs:
      Digitalisierung, Automatisierung, Compliance, Prozessreife, Innovation
    """
    # 1) branchenspezifische CSV
    csv_name = f"benchmark_{br}.csv"
    path = os.path.join(DATA_DIR, csv_name)
    if not os.path.exists(path):
        path = os.path.join(DATA_DIR, "benchmark_default.csv")
        if not os.path.exists(path):
            return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except Exception:
        return {}

    result: Dict[str, float] = {}
    # Form 1: Kategorie/Wert_Durchschnitt
    if rows and "Kategorie" in rows[0] and "Wert_Durchschnitt" in rows[0]:
        mapping = {
            "digitalisierungsgrad": "digitalisierung",
            "automatisierungsgrad": "automatisierung",
            "datenschutz-compliance": "compliance",
            "datenschutzkonformität": "compliance",
            "innovationsgrad": "innovation",
            "innovationsindex": "innovation",
            "papierloser anteil (%)": "prozessreife",
        }
        for r in rows:
            k = (r["Kategorie"] or "").strip().lower()
            v = r.get("Wert_Durchschnitt")
            if v is None or str(v).strip() == "":
                continue
            key = mapping.get(k)
            if not key:
                continue
            vv = float(str(v).replace(",", "."))
            if vv <= 10.0:
                vv = vv * 10.0
            result[key] = round(vv, 1)
    # Form 2: Kriterium + Solo/Klein/KMU
    elif rows and "Kriterium" in rows[0]:
        col = "KMU"
        if sz == "solo":
            col = "Solo"
        elif sz in ("small",):
            col = "Klein"
        mapping = {
            "digitalisierungsgrad": "digitalisierung",
            "automatisierungsgrad": "automatisierung",
            "datenschutzkonformität": "compliance",
            "innovationsindex": "innovation",
            "papierloser anteil (%)": "prozessreife",
        }
        for r in rows:
            k = (r["Kriterium"] or "").strip().lower()
            v = r.get(col)
            if v is None or str(v).strip() == "":
                continue
            key = mapping.get(k)
            if not key:
                continue
            try:
                vv = float(str(v).replace(",", "."))
            except Exception:
                continue
            # Werte sind teils 0..10, teils schon %
            vv = vv * 10.0 if vv <= 10.0 else vv
            result[key] = round(vv, 1)

    # Mindestmenge absichern
    if result:
        for need in ("digitalisierung", "automatisierung", "compliance", "prozessreife", "innovation"):
            result.setdefault(need, 60.0)
    return result


def load_benchmarks(norm: Dict[str, Any]) -> Dict[str, float]:
    br = (norm.get("branche") or "").lower() or "beratung"
    sz = (norm.get("unternehmensgroesse") or "").lower() or "small"
    path = pick_benchmark_file(br, sz)
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {k.lower(): float(v) for k, v in data.items()}
        except Exception:
            pass
    # CSV-Fallback
    csv_bm = _load_benchmarks_from_csv(br, sz)
    if csv_bm:
        log.info("Loaded benchmark fallback from CSV for %s/%s", br, sz)
        return csv_bm
    # Letzte Rettung (konservativ)
    return {"digitalisierung": 72.0, "automatisierung": 64.0, "compliance": 70.0, "prozessreife": 68.0, "innovation": 69.0}


# --------------------------- KPIs / Business Case ----------------------------

def calculate_kpis(norm: Dict[str, Any]) -> Dict[str, float]:
    # Digitalisierung (0..10 -> %)
    digi = _to_percent(norm.get("digitalisierungsgrad") or 0, 10.0)

    auto_map = {"sehr_hoch": 85, "hoch": 75, "eher_hoch": 65, "mittel": 50, "eher_niedrig": 35, "niedrig": 20}
    auto = float(auto_map.get(str(norm.get("automatisierungsgrad") or "").lower(), 40))

    comp = 0.0
    comp += 25.0 if str(norm.get("datenschutz")).lower() in {"1", "true", "ja"} else 0.0
    for flag in ("governance", "folgenabschaetzung", "meldewege", "loeschregeln"):
        if str(norm.get(flag) or "").strip():
            comp += 18.75
    comp = min(100.0, round(comp or 55.0, 1))

    paper = str(norm.get("prozesse_papierlos") or "").lower()
    paper_map = {"0-20": 10, "21-40": 30, "41-60": 50, "61-80": 65, "81-100": 80}
    proc = float(paper_map.get(paper, 60))
    if norm.get("governance"):
        proc = min(100.0, proc + 8.0)

    kult_map = {"sehr_offen": 80, "offen": 70, "neutral": 55, "skeptisch": 40}
    know_map = {"expertenwissen": 80, "fortgeschritten": 70, "solide": 60, "basis": 45}
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
    s = size_key.lower()
    if s in ("solo",):
        return "solo"
    if s in ("small", "team", "team_2_10", "klein"):
        return "team_2_10"
    return "kmu_11_100"  # kmu/konzern u.ä. -> kmu_11_100


def business_case(norm: Dict[str, Any], score: float) -> Dict[str, float]:
    """
    Nutzt config_roi.json (falls vorhanden) für realistischere Annual Savings.
    Investitionsbudget aus Survey-Kategorien bleibt als Investitionssumme.
    """
    # Invest aus Survey
    invest_map = {
        "unter_1000": 1000,
        "1000_2000": 1500,
        "2000_10000": 6000,
        "10000_50000": 20000,
        "ueber_50000": 60000,
    }
    invest = float(invest_map.get(str(norm.get("investitionsbudget") or "").lower(), 6000))

    # ROI-Konfig
    cfg = _load_roi_config()
    bucket = _size_to_roi_bucket(norm.get("unternehmensgroesse") or "small")
    roi = cfg.get(bucket, {})
    if roi:
        hrs = (float(roi["hours_saved_per_week_range"][0]) + float(roi["hours_saved_per_week_range"][1])) / 2.0
        rate = (float(roi["hourly_rate_range_eur"][0]) + float(roi["hourly_rate_range_eur"][1])) / 2.0
        tool_pm = float(roi.get("tool_cost_per_user_month_eur", 40))
        # Sitzanzahl heuristisch (Median des Buckets)
        seats = {"solo": 1, "team_2_10": 6, "kmu_11_100": 30}.get(bucket, 6)
        per_user_month = max(0.0, hrs * rate * 4.33 - tool_pm)
        annual_saving = max(0.0, per_user_month * 12 * seats)
    else:
        # Fallback: konservativ – an Score gekoppelt
        annual_saving = invest * 4.0

    payback_months = max(0.5, round(invest / (annual_saving / 12.0), 1)) if annual_saving > 0 else 12.0
    roi_y1_pct = round(((annual_saving - invest) / invest) * 100.0, 1) if invest > 0 else 0.0
    return {
        "invest_eur": round(invest, 0),
        "annual_saving_eur": round(annual_saving, 0),
        "payback_months": payback_months,
        "roi_year1_pct": roi_y1_pct,
    }


# ----------------------------- HTML‑Fragmente --------------------------------

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


def render_benchmark_table(kpis: Dict[str, float], bm: Dict[str, float]) -> str:
    rows = []
    for key, label in [("digitalisierung", "Digitalisierung"), ("automatisierung", "Automatisierung"),
                       ("compliance", "Compliance"), ("prozessreife", "Prozessreife"), ("innovation", "Innovation")]:
        rows.append(f"<tr><td>{label}</td><td>{int(round(kpis.get(key, 0)))}%</td><td>{int(round(bm.get(key, 0)))}%</td></tr>")
    return "<table><thead><tr><th>KPI</th><th>Ihr Wert</th><th>Branchen‑Benchmark</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"


# ------------------------------ OpenAI Wrapper -------------------------------

def _chat_once(model: str, messages: List[Dict[str, str]], temperature: float = 0.2, tokens: int = 800) -> str:
    """
    Robust gegenüber neuen/alten Parametern:
    - versucht 'max_completion_tokens' (neue Modelle, z. B. gpt‑4o/gpt‑5)
    - fällt auf 'max_tokens' zurück (ältere Pfade)
    """
    if not _openai_available:
        raise RuntimeError("OpenAI SDK not available")

    client = OpenAI()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_completion_tokens=tokens,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        msg = str(e)
        if "max_tokens" in msg or "unsupported_parameter" in msg.lower():
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=tokens,
            )
            return (resp.choices[0].message.content or "").strip()
        raise


def _prompt(name: str, lang: str) -> str:
    # lädt z. B. "executive_summary_de.md"
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
            "risks": ("<table style='width:100%;border-collapse:collapse'><thead><tr>"
                      "<th>Risiko</th><th>Wahrsch.</th><th>Impact</th><th>Mitigation</th></tr></thead>"
                      "<tbody><tr><td>Datenschutz</td><td>Mittel</td><td>Hoch</td><td>DSGVO‑Prozesse</td></tr>"
                      "<tr><td>Regulatorik</td><td>Mittel</td><td>Hoch</td><td>AI‑Act‑Check</td></tr>"
                      "<tr><td>Vendor‑Lock</td><td>Mittel</td><td>Mittel</td><td>Offene Standards</td></tr>"
                      "<tr><td>Change</td><td>Hoch</td><td>Mittel</td><td>Enablement</td></tr></tbody></table>"),
            "compliance": "<ul><li>AI‑Act‑Klassifizierung</li><li>Transparenz & Logging</li><li>DPIA/DSGVO</li><li>Dokumentation</li><li>Monitoring</li></ul>",
            "doc_digest": "<p><b>Executive Knowledge Digest:</b> Strategie, Technologie, Governance, Kultur.</p>",
            "tools": "<p>Die folgende Auswahl führt geeignete Tools mit EU‑Host‑Hinweis auf.</p>",
            "foerderprogramme": "<p>Relevante Förderprogramme mit Fristen und Links – bitte Deadlines beachten.</p>",
            "business": "<p>Der Business‑Case profitiert von frühen Automatisierungsgewinnen; Payback &lt; 4 Monate erreichbar.</p>",
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
    user = prompt.format(**context)
    try:
        return _chat_once(model or DEFAULT_MODEL, [{"role": "system", "content": system}, {"role": "user", "content": user}])
    except Exception as e:
        log.warning("GPT generation failed for %s: %s", section, e)
        return ""


# -------------------------- Live-Sektionen (extern) --------------------------

def build_live_sections(context: Dict[str, Any]) -> Dict[str, Any]:
    from websearch_utils import build_live_sections as _build  # lazy import
    return _build(context)


# ------------------------------- Rendering -----------------------------------

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
        log.info("Missing normalized fields: %s", miss)

    # KPIs & Benchmarks
    kpis = calculate_kpis(norm)
    score = overall_score(kpis)
    badge = quality_badge(score)
    bm = load_benchmarks(norm)

    # Fragmente
    kpis_progress_html = render_progress_bars(kpis)
    kpis_benchmark_table_html = render_benchmark_table(kpis, bm)
    bc = business_case(norm, score)

    # Kontext für GPT
    gpt_ctx = {
        "briefing": norm,
        "score_percent": score,
        "kpis": kpis,
        "benchmarks": bm,
        "business_case": bc,
        "today": _today(),
    }

    # Kernsektionen
    sections = {
        "executive_summary_html": _gpt_section("executive_summary", lang, gpt_ctx, model=EXEC_SUMMARY_MODEL),
        "quick_wins_html": _gpt_section("quick_wins", lang, gpt_ctx),
        "roadmap_html": _gpt_section("roadmap", lang, gpt_ctx),
        "risks_html": _gpt_section("risks", lang, gpt_ctx),
        "compliance_html": _gpt_section("compliance", lang, gpt_ctx),
        "doc_digest_html": _gpt_section("doc_digest", lang, gpt_ctx),
    }

    # Optionale Add‑ons (nur wenn Prompts vorhanden sind)
    for extra in ["business", "recommendations", "gamechanger", "vision", "persona", "praxisbeispiel", "coach", "tools", "foerderprogramme"]:
        html = _gpt_section(extra, lang, gpt_ctx)
        if html.strip():
            sections[f"{extra}_html"] = html

    # Live-Kacheln (unabhängig)
    live = build_live_sections({
        "branche": norm.get("branche_label") or norm.get("branche"),
        "size": norm.get("unternehmensgroesse_label") or norm.get("unternehmensgroesse"),
        "country": "DE",
    })
    flags = {"eu_host_check": True, "regulatory": True, "case_studies": True}

    # Rendering
    env = _env()
    tpl_name = "pdf_template.html" if lang.startswith("de") else "pdf_template_en.html"
    tpl = env.get_template(tpl_name)
    html = tpl.render(
        meta={"title": "KI-Status-Report" if lang.startswith("de") else "AI Status Report", "date": _today(), "lang": lang},
        briefing=norm,
        score_percent=score,
        quality_badge=badge,
        kpis_progress_html=kpis_progress_html,
        kpis_benchmark_table_html=kpis_benchmark_table_html,
        business_case=bc,
        sections=sections,
        live=live,
        flags=flags,
    )
    return html


def produce_admin_attachments(raw: Dict[str, Any]) -> Dict[str, str]:
    norm = normalize_briefing(raw)
    miss = missing_fields(norm)
    return {
        "briefing_raw.json": json.dumps(raw, ensure_ascii=False, indent=2),
        "briefing_normalized.json": json.dumps(norm, ensure_ascii=False, indent=2),
        "briefing_missing_fields.json": json.dumps({"missing": miss}, ensure_ascii=False, indent=2),
    }
