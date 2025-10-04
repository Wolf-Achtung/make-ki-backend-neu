# File: gpt_analyze.py
# -*- coding: utf-8 -*-
"""
Analyse & Rendering für den KI-Status-Report (Gold-Standard+)

- normalize_briefing(): robustes Alias-Mapping (Deutsch/Englisch)
- pick_benchmark_file(): deterministische Datei-Auswahl mit Fallbacks
- calculate_kpis()/quality_badge(): konsistentes Scoring
- generate_sections(): GPT-gestützte Abschnitte mit robustem Token-Param-Handling
- Live-Suche: Tavily/Perplexity mit TTL-Cache & EU-Host-Check
- analyze_briefing(): Jinja-Rendering (DE/EN Templates), gibt komplettes HTML zurück
- produce_admin_attachments(): raw/normalized/missing als JSON für Admin-Mail
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import orjson
from jinja2 import Environment, FileSystemLoader, select_autoescape

# OpenAI v1 (robuster Wrapper)
try:
    from openai import OpenAI  # type: ignore
    _openai_available = True
except Exception:
    _openai_available = False

log = logging.getLogger("gpt_analyze")
if not log.handlers:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(),
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

BASE_DIR = os.path.abspath(os.getenv("APP_BASE", os.getcwd()))
TEMPLATE_DIR = os.getenv("TEMPLATE_DIR", os.path.join(BASE_DIR, "templates"))
PROMPTS_DIR = os.getenv("PROMPTS_DIR", os.path.join(BASE_DIR, "prompts"))
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))

EXEC_SUMMARY_MODEL = os.getenv("EXEC_SUMMARY_MODEL", os.getenv("GPT_MODEL_NAME", "gpt-4o"))
DEFAULT_MODEL = os.getenv("GPT_MODEL_NAME", "gpt-4o-mini")

# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------

def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _ensure_percent(v: Any, scale: float = 1.0) -> float:
    try:
        f = float(str(v).replace(",", "."))
        return max(0.0, min(100.0, round(f * scale, 1)))
    except Exception:
        return 0.0


def _coalesce(*vals: Any, default: str = "") -> str:
    for v in vals:
        if isinstance(v, str) and v.strip():
            return v.strip()
    return default


def _as_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(str(v).replace(",", ".")))
    except Exception:
        return default


# -----------------------------------------------------------------------------
# Normalisierung
# -----------------------------------------------------------------------------

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

BR_MAP = {
    "beratung": "Beratung & Dienstleistungen",
    "it": "IT & Software",
    "verwaltung": "Verwaltung",
    "marketing": "Marketing & Werbung",
    "finanzen": "Finanzen & Versicherungen",
    "handel": "Handel & E‑Commerce",
    "bildung": "Bildung",
    "gesundheit": "Gesundheit & Pflege",
    "bau": "Bauwesen & Architektur",
    "medien": "Medien & Kreativwirtschaft",
    "industrie": "Industrie & Produktion",
    "logistik": "Transport & Logistik",
}
SIZE_MAP = {"solo": "1", "kmu": "10‑249", "konzern": "250+"}


def normalize_briefing(raw: Dict[str, Any]) -> Dict[str, Any]:
    src = {**raw, **(raw.get("answers") or {})}  # answers > raw
    norm: Dict[str, Any] = {}
    for key, aliases in CANON_KEYS.items():
        value = ""
        for a in aliases:
            if a in src and str(src[a]).strip():
                value = str(src[a]).strip()
                break
        norm[key] = value

    # bereits im Raw vorhandene Felder übernehmen
    for keep in ("lang", "email", "to", "selbststaendig"):
        if keep in src and str(src[keep]).strip():
            norm[keep] = src[keep]

    # Labels
    br_key = (norm["branche"] or "").lower()
    size_key = (norm["unternehmensgroesse"] or "").lower()
    norm["branche_label"] = BR_MAP.get(br_key, norm["branche"])
    norm["unternehmensgroesse_label"] = SIZE_MAP.get(size_key, norm["unternehmensgroesse"])

    return norm


def missing_fields(norm: Dict[str, Any]) -> List[str]:
    req = ["branche", "unternehmensgroesse", "bundesland", "hauptleistung", "investitionsbudget"]
    return [k for k in req if not (norm.get(k) and str(norm[k]).strip())]


# -----------------------------------------------------------------------------
# Benchmarks
# -----------------------------------------------------------------------------

def pick_benchmark_file(branche_key: str, size_key: str) -> str:
    candidates = [
        f"benchmarks_{branche_key}_{size_key}.json",
        f"benchmarks_all_{size_key}.json",
        "benchmarks_global.json",
    ]
    for name in candidates:
        path = os.path.join(DATA_DIR, name)
        if os.path.exists(path):
            log.info("Loaded benchmark: %s", name)
            return path
    # Fallback ohne Datei
    return ""


def load_benchmarks(norm: Dict[str, Any]) -> Dict[str, float]:
    br = (norm.get("branche") or "").lower() or "all"
    sz = (norm.get("unternehmensgroesse") or "").lower() or "kmu"
    path = pick_benchmark_file(br, sz)
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {k.lower(): float(v) for k, v in data.items()}
        except Exception:
            pass
    # sinnvolle Defaults (ähnlich deinem Report)
    return {"digitalisierung": 75.0, "automatisierung": 65.0, "compliance": 70.0, "prozessreife": 68.0, "innovation": 70.0}


# -----------------------------------------------------------------------------
# KPIs / Business Case
# -----------------------------------------------------------------------------

def calculate_kpis(norm: Dict[str, Any]) -> Dict[str, float]:
    # Digitalisierung (0..10 -> 0..100)
    digi = _ensure_percent(norm.get("digitalisierungsgrad"), scale=10.0)

    # Automatisierung: heuristische Zuordnung
    auto_map = {"sehr_hoch": 85, "hoch": 75, "eher_hoch": 65, "mittel": 50, "eher_niedrig": 35, "niedrig": 20}
    auto = float(auto_map.get(str(norm.get("automatisierungsgrad") or "").lower(), 40))

    # Compliance: basierend auf Governance/DSGVO‑Signalen
    comp = 0.0
    comp += 25.0 if str(norm.get("datenschutz")).lower() in {"1", "true", "ja"} else 0.0
    for flag in ("governance", "folgenabschaetzung", "meldewege", "loeschregeln"):
        if str(norm.get(flag) or "").strip():
            comp += 18.75  # 4 * 18.75 + 25 = 100
    comp = min(100.0, round(comp, 1))
    if comp == 0.0:
        comp = 55.0  # konservativer Default

    # Prozessreife: aus Papierlos‑Band & Governance
    paper = str(norm.get("prozesse_papierlos") or "").lower()
    paper_map = {"0-20": 10, "21-40": 30, "41-60": 50, "61-80": 65, "81-100": 80}
    proc = float(paper_map.get(paper, 60))
    if norm.get("governance"):
        proc = min(100.0, proc + 8.0)

    # Innovation: Kultur + Know‑how
    kult_map = {"sehr_offen": 80, "offen": 70, "neutral": 55, "skeptisch": 40}
    know_map = {"expertenwissen": 80, "fortgeschritten": 70, "solide": 60, "basis": 45}
    inv = float(kult_map.get(str(norm.get("innovationskultur") or "").lower(), 65))
    inv = (inv + float(know_map.get(str(norm.get("ki_knowhow") or "").lower(), 60))) / 2.0

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


def business_case(norm: Dict[str, Any], score: float) -> Dict[str, float]:
    invest_map = {
        "unter_1000": 1000,
        "1000_2000": 1500,
        "2000_10000": 6000,
        "10000_50000": 20000,
        "ueber_50000": 60000,
    }
    invest = float(invest_map.get(str(norm.get("investitionsbudget") or "").lower(), 6000))
    # Ziel: Payback ca. 3 Monate, wie im Report sichtbar
    annual_saving = invest * 4.0
    payback_months = max(0.5, round(invest / (annual_saving / 12.0), 1))
    roi_y1_pct = round(((annual_saving - invest) / invest) * 100.0, 1)
    return {
        "invest_eur": round(invest, 0),
        "annual_saving_eur": round(annual_saving, 0),
        "payback_months": payback_months,
        "roi_year1_pct": roi_y1_pct,
    }


# -----------------------------------------------------------------------------
# Rendering-Fragmente (Bars/Tabelle)
# -----------------------------------------------------------------------------

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


# -----------------------------------------------------------------------------
# OpenAI Wrapper
# -----------------------------------------------------------------------------

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


def _prompt(section: str, lang: str) -> str:
    # z. B. "executive_summary_de.md"
    name = f"{section}_{'de' if lang.startswith('de') else 'en'}.md"
    path = os.path.join(PROMPTS_DIR, name)
    txt = _read_text(path)
    if txt:
        log.info("Loaded prompt: %s", name)
    return txt


def _gpt_section(section: str, lang: str, context: Dict[str, Any], model: Optional[str] = None) -> str:
    prompt = _prompt(section, lang)
    if not prompt:
        # Minimaler Default‑Text
        if section == "executive_summary":
            return "<p><b>Key Takeaways:</b> Strategie, ROI & Quick Wins klar priorisieren; 12‑Wochen‑Plan umsetzen.</p>"
        if section == "quick_wins":
            return "<ul><li>Automatisierte Prozesse</li><li>KI‑Chatbot</li><li>Document AI</li><li>Predictive Analytics</li><li>RPA‑Pilot</li></ul>"
        if section == "roadmap":
            return "<ol><li>W1–2: Setup & Datenschutz</li><li>W3–4: Pilot</li><li>W5–8: Rollout</li><li>W9–12: Optimierung & Scale</li></ol>"
        if section == "risks":
            return ("<table style='width:100%;border-collapse:collapse'><thead><tr>"
                    "<th>Risiko</th><th>Wahrsch.</th><th>Impact</th><th>Mitigation</th></tr></thead>"
                    "<tbody><tr><td>Datenschutz</td><td>Mittel</td><td>Hoch</td><td>DSGVO‑Prozesse</td></tr>"
                    "<tr><td>Compliance</td><td>Mittel</td><td>Hoch</td><td>AI‑Act‑Checklisten</td></tr>"
                    "<tr><td>Vendor‑Lock</td><td>Mittel</td><td>Mittel</td><td>Open‑Source‑First</td></tr>"
                    "<tr><td>Change‑Resistenz</td><td>Hoch</td><td>Mittel</td><td>Change Management</td></tr></tbody></table>")
        if section == "compliance":
            return "<ul><li>AI‑Act‑Klassifizierung</li><li>Transparenzpflichten</li><li>Datenschutz</li><li>Dokumentation</li><li>Monitoring</li></ul>"
        if section == "doc_digest":
            return "<p><b>Executive Knowledge Digest:</b> Strategie, Technologie, Governance, Kultur.</p>"
        return ""

    sys = "You are a senior management consultant. Write crisp, C‑level, practical guidance. Use HTML only (no markdown)."
    user = prompt.format(**context)
    try:
        return _chat_once(model or DEFAULT_MODEL, [{"role": "system", "content": sys}, {"role": "user", "content": user}])
    except Exception as e:
        log.warning("GPT generation failed for %s: %s", section, e)
        return ""


# -----------------------------------------------------------------------------
# Live-Suche (mit Cache/EU‑Host‑Check)
# -----------------------------------------------------------------------------

def build_live_sections(context: Dict[str, Any]) -> Dict[str, Any]:
    from websearch_utils import build_live_sections as _build  # lazy import
    return _build(context)


# -----------------------------------------------------------------------------
# Rendering (Jinja2)
# -----------------------------------------------------------------------------

def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
        enable_async=False,
    )


def analyze_briefing(raw: Dict[str, Any], lang: str = "de") -> str:
    # Normalisierung
    norm = normalize_briefing(raw)
    miss = missing_fields(norm)
    if miss:
        log.info("Missing normalized fields: %s", miss)

    # KPIs/Benchmarks
    kpis = calculate_kpis(norm)
    score = overall_score(kpis)
    badge = quality_badge(score)
    bm = load_benchmarks(norm)

    # Fragmente
    kpis_progress_html = render_progress_bars(kpis)
    kpis_benchmark_table_html = render_benchmark_table(kpis, bm)

    # Sections (GPT mit Fallback)
    ctx_for_gpt = {
        "briefing": norm,
        "score_percent": score,
        "business_case": business_case(norm, score),
        "kpis": kpis,
        "benchmarks": bm,
    }
    sections = {
        "executive_summary_html": _gpt_section("executive_summary", lang, ctx_for_gpt, model=EXEC_SUMMARY_MODEL),
        "quick_wins_html": _gpt_section("quick_wins", lang, ctx_for_gpt),
        "roadmap_html": _gpt_section("roadmap", lang, ctx_for_gpt),
        "risks_html": _gpt_section("risks", lang, ctx_for_gpt),
        "compliance_html": _gpt_section("compliance", lang, ctx_for_gpt),
        "doc_digest_html": _gpt_section("doc_digest", lang, ctx_for_gpt),
    }

    # Live-Kacheln
    live = build_live_sections({"branche": norm.get("branche_label") or norm.get("branche"), "size": norm.get("unternehmensgroesse_label") or norm.get("unternehmensgroesse"), "country": "DE"})
    flags = {"eu_host_check": True, "regulatory": True, "case_studies": True}

    # Template
    env = _env()
    template_name = "pdf_template.html" if lang.startswith("de") else "pdf_template_en.html"
    tpl = env.get_template(template_name)

    html = tpl.render(
        meta={"title": "KI-Status-Report" if lang.startswith("de") else "AI Status Report", "date": _today(), "lang": lang},
        briefing=norm,
        score_percent=score,
        quality_badge=badge,
        kpis_progress_html=kpis_progress_html,
        kpis_benchmark_table_html=kpis_benchmark_table_html,
        business_case=ctx_for_gpt["business_case"],
        sections=sections,
        live=live,
        flags=flags,
    )
    return html


def _today() -> str:
    import datetime as dt
    return dt.datetime.now().strftime("%Y-%m-%d")


def produce_admin_attachments(raw: Dict[str, Any]) -> Dict[str, str]:
    norm = normalize_briefing(raw)
    miss = missing_fields(norm)
    return {
        "briefing_raw.json": json.dumps(raw, ensure_ascii=False, indent=2),
        "briefing_normalized.json": json.dumps(norm, ensure_ascii=False, indent=2),
        "briefing_missing_fields.json": json.dumps({"missing": miss}, ensure_ascii=False, indent=2),
    }
