# File: gpt_analyze.py
# -*- coding: utf-8 -*-
"""
MAKE-KI Backend – Report Generator (Gold‑Standard+)

- LLM‑Sektionen (Executive Summary, Quick Wins, Roadmap, Risiken) + Fallback
- EU‑Live‑Quellen über websearch_utils (CORDIS/OpenAIRE/F&T) mit Cache/Throttle
- QC‑Hook (quality_control.py) – optional, fehlertolerant
- Kompatible Public API: analyze_briefing(..., lang=...), analyze_briefing_enhanced(...)
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape  # type: ignore
except Exception:  # pragma: no cover
    Environment = None  # type: ignore

# -----------------------------------------------------------------------------
# ENV & Logging
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
PROMPTS_DIR = Path(os.getenv("PROMPTS_DIR", str(BASE_DIR / "prompts")))
TEMPLATE_DIR = Path(os.getenv("TEMPLATE_DIR", str(BASE_DIR / "templates")))
TEMPLATE_DE = os.getenv("TEMPLATE_DE", "pdf_template.html")
TEMPLATE_EN = os.getenv("TEMPLATE_EN", "pdf_template_en.html")

DEFAULT_LANG = os.getenv("DEFAULT_LANG", "de")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
ENABLE_LLM_SECTIONS = os.getenv("ENABLE_LLM_SECTIONS", "true").lower() == "true"
OFFICIAL_API_ENABLED = os.getenv("OFFICIAL_API_ENABLED", "false").lower() == "true"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
EXEC_SUMMARY_MODEL = os.getenv("EXEC_SUMMARY_MODEL", "gpt-4o")
OPENAI_FALLBACK_MODEL = os.getenv("OPENAI_FALLBACK_MODEL", "gpt-4o-mini")
OPENAI_TIMEOUT = int(os.getenv("OPENAI_TIMEOUT", "30"))
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "900"))
OPENAI_TEMPERATURE = float(os.getenv("GPT_TEMPERATURE", "0.2"))
LLM_MODE = os.getenv("LLM_MODE", "hybrid").lower()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gpt_analyze")

COLOR_PRIMARY = "#0B5FFF"
COLOR_ACCENT = "#FB8C00"

# -----------------------------------------------------------------------------
# Modelle
# -----------------------------------------------------------------------------
@dataclass
class Briefing:
    branche: str
    unternehmensgroesse: str
    bundesland: str
    hauptleistung: str
    investitionsbudget: Optional[str] = None
    ziel: Optional[str] = None
    digitalisierung: Optional[float] = None
    automatisierung: Optional[float] = None
    compliance: Optional[float] = None
    prozessreife: Optional[float] = None
    innovation: Optional[float] = None

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def _s(x: Any) -> str:
    return str(x) if x is not None else ""

def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default

def _sanitize_branch(name: str) -> str:
    s = (name or "").strip().lower()
    s = s.replace("&", " und ")
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "allgemein"

def _sanitize_size(size: str) -> str:
    s = (size or "").strip().lower()
    if any(k in s for k in ["solo", "einzel", "freelance", "freiberuf"]):
        return "solo"
    if any(k in s for k in ["klein", "2", "3", "4", "5", "6", "7", "8", "9", "10"]):
        return "small"
    return "kmu"

def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

# -----------------------------------------------------------------------------
# Benchmarks & Business Case
# -----------------------------------------------------------------------------
def load_benchmarks(branch: str, size: str) -> Dict[str, float]:
    b = _sanitize_branch(branch)
    s = _sanitize_size(size)
    candidates = [
        DATA_DIR / f"benchmarks_{b}_{s}.json",
        DATA_DIR / f"benchmarks_{b}_kmu.json",
        DATA_DIR / f"benchmarks_medien_kreativwirtschaft_{s}.json",
        DATA_DIR / f"benchmarks_medien_kmu.json",
    ]
    for p in candidates:
        if p.exists():
            try:
                raw = _read_json(p)
                kpis = {it["name"]: float(it["value"]) for it in raw.get("kpis", []) if "name" in it}
                if kpis:
                    logger.info("Benchmarks geladen: %s", p.name)
                    return kpis
            except Exception as exc:
                logger.warning("Benchmarks‑Laden fehlgeschlagen (%s): %s", p, exc)
    logger.warning("Benchmarks: Fallback‑Defaults aktiv.")
    return {
        "digitalisierung": 0.70,
        "automatisierung": 0.55,
        "compliance": 0.65,
        "prozessreife": 0.60,
        "innovation": 0.60,
    }

@dataclass
class BusinessCase:
    invest_eur: float
    annual_saving_eur: float

    @property
    def payback_months(self) -> float:
        if self.annual_saving_eur <= 0:
            return 0.0
        return (self.invest_eur / self.annual_saving_eur) * 12.0

    @property
    def roi_year1_pct(self) -> float:
        if self.invest_eur <= 0:
            return 0.0
        return (self.annual_saving_eur - self.invest_eur) / self.invest_eur * 100.0

def invest_from_bucket(bucket: Optional[str]) -> float:
    if not bucket:
        return 6000.0
    b = bucket.lower()
    if "bis" in b and "2000" in b:
        return 1500.0
    if "2000" in b and ("10000" in b or "10.000" in b):
        return 6000.0
    if "10000" in b and ("50000" in b or "50.000" in b):
        return 30000.0
    if "50000" in b or "50.000" in b:
        return 75000.0
    return 6000.0

def compute_business_case(briefing: Dict[str, Any], bm: Dict[str, float]) -> BusinessCase:
    invest = invest_from_bucket(_s(briefing.get("investitionsbudget")))
    auto = bm.get("automatisierung", 0.55)
    proc = bm.get("prozessreife", 0.60)
    scale = 40000.0
    annual_saving = max(12000.0, (0.6 * auto + 0.4 * proc) * scale)
    return BusinessCase(invest_eur=invest, annual_saving_eur=annual_saving)

# -----------------------------------------------------------------------------
# Live‑Suche (Adapter → HTML)
# -----------------------------------------------------------------------------
def _items_to_cards(items: list[dict], show_deadline: bool = False) -> str:
    if not items:
        return "<p>Keine Einträge gefunden.</p>"
    out = ["<ul>"]
    for it in items[:8]:
        t = (it.get("title") or "").strip()
        u = (it.get("url") or "").strip()
        snip = (it.get("summary") or it.get("snippet") or "").strip()
        date = (it.get("published_at") or it.get("date") or "").strip()
        tail = f" – <small>{date}</small>" if date else ""
        out.append(f"<li><a href=\"{u}\">{t}</a>{tail}<br><small>{snip}</small></li>")
    out.append("</ul>")
    return "".join(out)

def _funding_to_cards(items: list[dict]) -> str:
    if not items:
        return "<p>Keine passenden Förderprogramme gefunden.</p>"
    head = "<div>"
    body = []
    for it in items[:8]:
        t = (it.get("title") or "").strip()
        u = (it.get("url") or "").strip()
        dl = (it.get("deadline") or it.get("date") or "").strip()
        prog = (it.get("extra", {}) or {}).get("programme") or it.get("program") or ""
        meta = " · ".join(x for x in [prog, ("Deadline: " + dl) if dl else None] if x)
        body.append(
            "<section style='border:1px solid #e5e7eb;border-radius:8px;padding:10px;margin:8px 0;background:#fff'>"
            f"<div><a href=\"{u}\"><strong>{t}</strong></a></div>"
            f"<div style='color:#334155;font-size:12px'>{meta}</div>"
            "</section>"
        )
    tail = "</div>"
    return head + "".join(body) + tail

def query_live_items(briefing: Dict[str, Any], lang: str) -> Tuple[str, str, str]:
    """Wrapper: ruft websearch_utils.query_live_items auf und rendert HTML."""
    try:
        from websearch_utils import query_live_items as _ql  # type: ignore
    except Exception:
        logger.info("websearch_utils nicht verfügbar – Live‑Sektionen leer.")
        return ("", "", "")

    # Robust gegen beide Signaturen
    try:
        res = _ql(
            industry=_s(briefing.get("branche")),
            size=_s(briefing.get("unternehmensgroesse")),
            main_service=_s(briefing.get("hauptleistung")),
            region=_s(briefing.get("bundesland")),
            days_news=int(os.getenv("SEARCH_DAYS_NEWS", "7")),
            days_tools=int(os.getenv("SEARCH_DAYS_TOOLS", "30")),
            days_funding=int(os.getenv("SEARCH_DAYS_FUNDING", "60")),
            max_results=int(os.getenv("SEARCH_MAX_RESULTS", "8")),
        )
    except TypeError:
        # ältere Form
        res = _ql(
            branche=_s(briefing.get("branche")),
            size=_s(briefing.get("unternehmensgroesse")),
            leistung=_s(briefing.get("hauptleistung")),
            bundesland=_s(briefing.get("bundesland")),
            lang=lang,
            days_news=int(os.getenv("SEARCH_DAYS_NEWS", "7")),
            days_tools=int(os.getenv("SEARCH_DAYS_TOOLS", "30")),
            days_funding=int(os.getenv("SEARCH_DAYS_FUNDING", "60")),
            max_results=int(os.getenv("SEARCH_MAX_RESULTS", "8")),
        )

    if isinstance(res, dict):
        news_html = _items_to_cards(res.get("news", []))
        tools_html = _items_to_cards(res.get("tools", []))
        funding_html = _funding_to_cards(res.get("funding", []))
        return news_html, tools_html, funding_html

    # Fallback: tuple oder unbekannte Form
    try:
        a, b, c = res  # type: ignore
        return str(a), str(b), str(c)
    except Exception:
        return ("", "", "")

# -----------------------------------------------------------------------------
# KPI
# -----------------------------------------------------------------------------
def _kpi_from_briefing(briefing: Dict[str, Any]) -> Dict[str, float]:
    def norm(v: Any) -> float:
        f = _safe_float(v, -1.0)
        return f / 10.0 if f >= 0 else -1.0
    return {
        "digitalisierung": norm(briefing.get("digitalisierung")),
        "automatisierung": norm(briefing.get("automatisierung")),
        "compliance": norm(briefing.get("compliance")),
        "prozessreife": norm(briefing.get("prozessreife")),
        "innovation": norm(briefing.get("innovation")),
    }

def _merge_kpis(raw_kpi: Dict[str, float], bm: Dict[str, float]) -> Dict[str, float]:
    return {k: (v if v >= 0 else bm.get(k, 0.6)) for k, v in raw_kpi.items()}

# -----------------------------------------------------------------------------
# Prompts & LLM
# -----------------------------------------------------------------------------
DEFAULT_PROMPTS: Dict[str, Dict[str, str]] = {
    "executive_summary": {
        "de": (
            "Du bist Strategy‑Consultant. Erstelle eine prägnante Executive Summary für einen KI‑Status‑Report.\n"
            "Branche={branche}, Größe={unternehmensgroesse}, Region={bundesland}, Leistung={hauptleistung}.\n"
            "Kennzahlen: Score={score_percent:.1f}%, ROI Jahr1={roi_year1_pct:.1f}%, Payback={payback_months:.1f} Monate.\n"
            "3–5 Sätze, aktiv, ohne Floskeln. HTML‑Ausgabe mit <p>…</p>."
        ),
        "en": (
            "You are a strategy consultant. Write a crisp executive summary for an AI status report.\n"
            "industry={branche}, size={unternehmensgroesse}, region={bundesland}, service={hauptleistung}.\n"
            "KPIs: score={score_percent:.1f}%, ROI year1={roi_year1_pct:.1f}%, payback={payback_months:.1f} months.\n"
            "3–5 sentences, active voice. Output HTML with <p>…</p>."
        ),
    },
    "quick_wins": {
        "de": (
            "Liste 5 sofort umsetzbare Quick Wins (konkret; Aufwand in Tagen; Nutzen; Owner‑Rolle).\n"
            "Kontext: Branche={branche}, Größe={unternehmensgroesse}, Leistung={hauptleistung}.\n"
            "HTML als <ul><li>…</li></ul>."
        ),
        "en": (
            "List 5 actionable quick wins (concrete; effort in days; benefit; owner role).\n"
            "Context: industry={branche}, size={unternehmensgroesse}, service={hauptleistung}.\n"
            "HTML as <ul><li>…</li></ul>."
        ),
    },
    "roadmap": {
        "de": (
            "Erstelle eine 90‑Tage‑Roadmap (Wochen 1–2, 3–4, 5–8, 9–12) mit Meilensteinen & Deliverables.\n"
            "HTML als <ol><li>…</li></ol>."
        ),
        "en": (
            "Create a 90‑day roadmap (weeks 1–2, 3–4, 5–8, 9–12) with milestones & deliverables.\n"
            "HTML as <ol><li>…</li></ol>."
        ),
    },
    "risks": {
        "de": (
            "Erstelle eine Top‑5‑Risikomatrix mit Wahrscheinlichkeit, Auswirkung, Mitigation.\n"
            "Beziehe AI‑VO/DSA/CRA/Data Act, Bias/Drift, Betrieb ein. HTML‑Tabelle."
        ),
        "en": (
            "Create a Top‑5 risk matrix including probability, impact, mitigation.\n"
            "Include EU AI Act/DSA/CRA/Data Act, bias/drift, ops. HTML table."
        ),
    },
}

def _load_prompt(name: str, lang: str) -> str:
    candidates = [
        PROMPTS_DIR / f"{name}_{lang}.md",
        PROMPTS_DIR / f"{name}_{lang}.txt",
    ]
    for p in candidates:
        if p.exists():
            try:
                return p.read_text(encoding="utf-8")
            except Exception as exc:
                logger.warning("Prompt‑Datei %s konnte nicht gelesen werden: %s", p, exc)
    return DEFAULT_PROMPTS.get(name, {}).get(lang, DEFAULT_PROMPTS[name]["de"])

def _format_prompt(tpl: str, ctx: Dict[str, Any]) -> str:
    class _D(dict):
        def __missing__(self, key):  # toleriert fehlende Keys
            return "{" + key + "}"
    return tpl.format_map(_D(ctx))

def _openai_chat(prompt: str, lang: str) -> str:
    if not (OFFICIAL_API_ENABLED and OPENAI_API_KEY and LLM_MODE in ("on", "hybrid") and ENABLE_LLM_SECTIONS):
        raise RuntimeError("LLM disabled by configuration")
    last_exc: Optional[Exception] = None
    for attempt in range(2):
        try:
            try:
                from openai import OpenAI  # type: ignore
                client = OpenAI(api_key=OPENAI_API_KEY, timeout=OPENAI_TIMEOUT)
                resp = client.chat.completions.create(
                    model=EXEC_SUMMARY_MODEL,
                    temperature=float(os.getenv("GPT_TEMPERATURE", "0.2")),
                    max_tokens=int(os.getenv("OPENAI_MAX_TOKENS", "900")),
                    messages=[
                        {"role": "system", "content": "You are a concise, senior AI and strategy consultant."},
                        {"role": "user", "content": prompt},
                    ],
                )
                return (resp.choices[0].message.content or "").strip()
            except ImportError:
                import openai  # type: ignore
                openai.api_key = OPENAI_API_KEY
                resp = openai.ChatCompletion.create(
                    model=EXEC_SUMMARY_MODEL,
                    temperature=float(os.getenv("GPT_TEMPERATURE", "0.2")),
                    max_tokens=int(os.getenv("OPENAI_MAX_TOKENS", "900")),
                    messages=[
                        {"role": "system", "content": "You are a concise, senior AI and strategy consultant."},
                        {"role": "user", "content": prompt},
                    ],
                    timeout=int(os.getenv("OPENAI_TIMEOUT", "30")),
                )
                return (resp["choices"][0]["message"]["content"] or "").strip()
        except Exception as exc:
            last_exc = exc
            logger.warning("OpenAI‑Call fehlgeschlagen (Versuch %s/2): %s", attempt + 1, exc)
            time.sleep(1.0 + attempt)
            if attempt == 0:
                os.environ["EXEC_SUMMARY_MODEL"] = OPENAI_FALLBACK_MODEL
    raise RuntimeError(f"OpenAI failed: {last_exc}")

def _fallback_exec_summary(ctx: Dict[str, Any]) -> str:
    return (
        "<p>Ihre Organisation weist ein hohes KI‑Potenzial auf. "
        f"Score: <b>{ctx['score_percent']:.1f}%</b>, "
        f"ROI Jahr 1: <b>{ctx['business_case']['roi_year1_pct']:.1f}%</b>, "
        f"Payback: <b>{ctx['business_case']['payback_months']:.1f} Monate</b>. "
        "Priorisieren Sie Automatisierung in Kernprozessen und ein Minimum‑Viable‑Compliance‑Set.</p>"
    )

def _fallback_quick_wins(ctx: Dict[str, Any]) -> str:
    return (
        "<ul>"
        "<li>E‑Mail‑/Angebotsvorlagen automatisieren (2–3 Tage, Owner: Vertrieb/Marketing).</li>"
        "<li>Meeting‑Zusammenfassungen mit KI (1 Tag, Owner: PMO).</li>"
        "<li>Interner FAQ‑/Wissensbot (3–5 Tage, Owner: IT).</li>"
        "<li>Lead‑Qualifizierung halbautomatisieren (3–5 Tage, Owner: Marketing).</li>"
        "<li>Compliance‑Go‑Live‑Gate & Checkliste (1–2 Tage, Owner: Legal/IT).</li>"
        "</ul>"
    )

def _fallback_roadmap(ctx: Dict[str, Any]) -> str:
    return (
        "<ol>"
        "<li>W1–2: Zielbild/KPI‑Baseline, Quick‑Wins priorisieren, MVC‑Checkliste.</li>"
        "<li>W3–4: Daten/Tools auswählen, Pilot automatisierter Prozess.</li>"
        "<li>W5–8: Rollout Kern‑Use‑Case, Schulung, Monitoring & Drift‑Checks.</li>"
        "<li>W9–12: Skalierung, Controlling, ROI‑Review, nächste Welle planen.</li>"
        "</ol>"
    )

def _fallback_risks(ctx: Dict[str, Any]) -> str:
    return (
        "<table role='table' style='width:100%;border-collapse:collapse'>"
        "<thead><tr><th>Risiko</th><th>Wahrsch.</th><th>Auswirkung</th><th>Mitigation</th></tr></thead>"
        "<tbody>"
        "<tr><td>Compliance (AI‑VO/DSA/CRA)</td><td>mittel</td><td>hoch</td><td>MVC, HiTL, Go‑Live‑Gate</td></tr>"
        "<tr><td>Bias/Drift</td><td>mittel</td><td>mittel</td><td>Monitoring, Re‑Tests</td></tr>"
        "<tr><td>Datenleck/DLP</td><td>niedrig</td><td>hoch</td><td>Pseudonymisierung, Rollen</td></tr>"
        "<tr><td>Vendor‑Lock‑in</td><td>mittel</td><td>mittel</td><td>Multi‑Vendor, Exit‑Pfad</td></tr>"
        "<tr><td>Change/Adoption</td><td>mittel</td><td>mittel</td><td>Enablement, Leitplanken</td></tr>"
        "</tbody></table>"
    )

def _load_prompt(name: str, lang: str) -> str:
    candidates = [PROMPTS_DIR / f"{name}_{lang}.md", PROMPTS_DIR / f"{name}_{lang}.txt"]
    for p in candidates:
        if p.exists():
            try:
                return p.read_text(encoding="utf-8")
            except Exception as exc:
                logger.warning("Prompt‑Datei %s konnte nicht gelesen werden: %s", p, exc)
    return {
        "executive_summary": {"de": _fallback_exec_summary, "en": _fallback_exec_summary},
        "quick_wins": {"de": _fallback_quick_wins, "en": _fallback_quick_wins},
        "roadmap": {"de": _fallback_roadmap, "en": _fallback_roadmap},
        "risks": {"de": _fallback_risks, "en": _fallback_risks},
    }.get(name, {}).get(lang, "")

def _format_prompt(tpl: str, ctx: Dict[str, Any]) -> str:
    class _D(dict):
        def __missing__(self, key):  # toleriert fehlende Keys
            return "{" + key + "}"
    return tpl.format_map(_D(ctx))

def _gen_llm_sections(context: Dict[str, Any], lang: str) -> Dict[str, str]:
    small = {
        "branche": context["briefing"]["branche"],
        "unternehmensgroesse": context["briefing"]["unternehmensgroesse"],
        "bundesland": context["briefing"]["bundesland"],
        "hauptleistung": context["briefing"]["hauptleistung"],
        "score_percent": context["score_percent"],
        "roi_year1_pct": context["business_case"]["roi_year1_pct"],
        "payback_months": context["business_case"]["payback_months"],
    }
    sections: Dict[str, str] = {}
    for key, fb in [
        ("executive_summary", _fallback_exec_summary),
        ("quick_wins", _fallback_quick_wins),
        ("roadmap", _fallback_roadmap),
        ("risks", _fallback_risks),
    ]:
        try:
            tpl = _load_prompt(key, lang)
            if callable(tpl):
                sections[key] = tpl(context)  # eingebauter Fallback
                continue
            prompt = _format_prompt(tpl, small)
            sections[key] = _openai_chat(prompt, lang=lang)
        except Exception as exc:
            logger.info("LLM‑Sektion %s – Fallback (%s)", key, exc)
            sections[key] = fb(context)
    return sections

# -----------------------------------------------------------------------------
# Kontext & QC
# -----------------------------------------------------------------------------
def _kpi_from_briefing(briefing: Dict[str, Any]) -> Dict[str, float]:
    def norm(v: Any) -> float:
        f = _safe_float(v, -1.0)
        return f / 10.0 if f >= 0 else -1.0
    return {
        "digitalisierung": norm(briefing.get("digitalisierung")),
        "automatisierung": norm(briefing.get("automatisierung")),
        "compliance": norm(briefing.get("compliance")),
        "prozessreife": norm(briefing.get("prozessreife")),
        "innovation": norm(briefing.get("innovation")),
    }

def _merge_kpis(raw_kpi: Dict[str, float], bm: Dict[str, float]) -> Dict[str, float]:
    return {k: (v if v >= 0 else bm.get(k, 0.6)) for k, v in raw_kpi.items()}

def build_context(form_data: Dict[str, Any], lang: str) -> Dict[str, Any]:
    now = _now_iso()
    branch = _s(form_data.get("branche"))
    size = _s(form_data.get("unternehmensgroesse"))
    bm = load_benchmarks(branch, size)
    kpi = _merge_kpis(_kpi_from_briefing(form_data), bm)
    score = (kpi["digitalisierung"] + kpi["automatisierung"] + kpi["compliance"] +
             kpi["prozessreife"] + kpi["innovation"]) / 5.0
    bc = compute_business_case(form_data, bm)
    news_html, tools_html, funding_html = query_live_items(form_data, lang)

    ctx: Dict[str, Any] = {
        "meta": {"title": "KI‑Status‑Report", "date": now, "lang": lang},
        "briefing": {
            "branche": branch,
            "unternehmensgroesse": size,
            "bundesland": _s(form_data.get("bundesland")),
            "hauptleistung": _s(form_data.get("hauptleistung")),
            "investitionsbudget": _s(form_data.get("investitionsbudget")),
            "ziel": _s(form_data.get("ziel")),
        },
        "kpis": kpi,
        "kpis_benchmark": bm,
        "score_percent": round(score * 100.0, 1),
        "business_case": {
            "invest_eur": round(bc.invest_eur, 2),
            "annual_saving_eur": round(bc.annual_saving_eur, 2),
            "payback_months": round(bc.payback_months, 1),
            "roi_year1_pct": round(bc.roi_year1_pct, 1),
        },
        "live": {
            "news_html": news_html,
            "tools_html": tools_html,
            "funding_html": funding_html,
            "stand": now,
        },
        "sections": {
            "executive_summary_html": "",
            "quick_wins_html": "",
            "roadmap_html": "",
            "risks_html": "",
        },
        "quality": None,
        "quality_badge": "",
    }

    # LLM‑Sektionen
    if ENABLE_LLM_SECTIONS and LLM_MODE in ("on", "hybrid"):
        try:
            sec = _gen_llm_sections(ctx, lang)
            ctx["sections"]["executive_summary_html"] = sec["executive_summary"]
            ctx["sections"]["quick_wins_html"] = sec["quick_wins"]
            ctx["sections"]["roadmap_html"] = sec["roadmap"]
            ctx["sections"]["risks_html"] = sec["risks"]
        except Exception as exc:
            logger.info("LLM‑Sektionen globaler Fallback: %s", exc)
            ctx["sections"]["executive_summary_html"] = _fallback_exec_summary(ctx)
            ctx["sections"]["quick_wins_html"] = _fallback_quick_wins(ctx)
            ctx["sections"]["roadmap_html"] = _fallback_roadmap(ctx)
            ctx["sections"]["risks_html"] = _fallback_risks(ctx)
    else:
        ctx["sections"]["executive_summary_html"] = _fallback_exec_summary(ctx)
        ctx["sections"]["quick_wins_html"] = _fallback_quick_wins(ctx)
        ctx["sections"]["roadmap_html"] = _fallback_roadmap(ctx)
        ctx["sections"]["risks_html"] = _fallback_risks(ctx)

    # QC‑Hook (optional)
    try:
        from quality_control import ReportQualityController  # type: ignore
        qc_payload = {
            "exec_summary_html": ctx["sections"]["executive_summary_html"],
            "quick_wins_html": ctx["sections"]["quick_wins_html"],
            "roadmap_html": ctx["sections"]["roadmap_html"],
            "risks_html": ctx["sections"]["risks_html"],
            "score_percent": ctx["score_percent"],
            "roi_investment": ctx["business_case"]["invest_eur"],
            "roi_annual_saving": ctx["business_case"]["annual_saving_eur"],
            "kpi_roi_months": ctx["business_case"]["payback_months"],
            "kpi_efficiency": round(ctx["kpis"]["automatisierung"] * 100),
            "kpi_compliance": round(ctx["kpis"]["compliance"] * 100),
        }
        qc = ReportQualityController()
        qc_result = qc.validate_complete_report(qc_payload, lang=lang)  # type: ignore[attr-defined]
        ctx["quality"] = {k: v for k, v in qc_result.items() if k != "report_card"}
        ctx["quality_badge"] = qc_result.get("report_card", "")
    except Exception as exc:
        logger.info("QC‑Hook nicht aktiv/übersprungen: %s", exc)

    return ctx

# -----------------------------------------------------------------------------
# Rendering (Jinja oder Fallback)
# -----------------------------------------------------------------------------
def _render_jinja(ctx: Dict[str, Any], lang: str, template: Optional[str]) -> str:
    if Environment is None:
        raise RuntimeError("Jinja2 nicht installiert")
    tpl_name = template or (TEMPLATE_DE if lang.startswith("de") else TEMPLATE_EN)
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        enable_async=False,
    )
    tpl = env.get_template(tpl_name)
    return tpl.render(**ctx)

def _progress_bar(label: str, value: float) -> str:
    pct = max(0, min(100, int(round(value * 100))))
    return (
        f"<div style='margin:6px 0'>"
        f"<div style='display:flex;justify-content:space-between;font:14px/1.4 system-ui,Arial'>"
        f"<span>{label}</span><span>{pct}%</span></div>"
        f"<div style='width:100%;height:8px;background:#eee;border-radius:4px'>"
        f"<div style='width:{pct}%;height:8px;background:{COLOR_PRIMARY};border-radius:4px'></div>"
        f"</div></div>"
    )

def _card(title: str, body: str) -> str:
    return (
        f"<section style='border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin:14px 0;background:#fff'>"
        f"<h2 style='margin:0 0 8px;color:{COLOR_ACCENT};font:600 18px/1.3 system-ui,Arial'>{title}</h2>"
        f"{body}</section>"
    )

def render_html(ctx: Dict[str, Any]) -> str:
    k = ctx["kpis"]; bc = ctx["business_case"]; live = ctx["live"]; s = ctx["sections"]

    kpi_html = "".join([
        _progress_bar("Digitalisierung", k["digitalisierung"]),
        _progress_bar("Automatisierung", k["automatisierung"]),
        _progress_bar("Compliance", k["compliance"]),
        _progress_bar("Prozessreife", k["prozessreife"]),
        _progress_bar("Innovation", k["innovation"]),
    ])

    bench = ctx["kpis_benchmark"]
    rows = []
    for key, label in [("digitalisierung","Digitalisierung"),("automatisierung","Automatisierung"),
                       ("compliance","Compliance"),("prozessreife","Prozessreife"),("innovation","Innovation")]:
        v = k[key] * 100.0; b = bench.get(key, 0) * 100.0
        rows.append(
            f"<tr><td>{label}</td><td style='text-align:right'>{v:.1f}%</td>"
            f"<td style='text-align:right'>{b:.1f}%</td><td style='text-align:right'>{(v-b):+.1f} pp</td></tr>"
        )
    bench_html = (
        "<table role='table' style='width:100%;border-collapse:collapse;font:14px/1.5 system-ui,Arial'>"
        "<thead><tr><th>Kennzahl</th><th style='text-align:right'>Unser Wert</th>"
        "<th style='text-align:right'>Benchmark</th><th style='text-align:right'>Δ</th></tr></thead>"
        "<tbody>" + "".join(rows) + "</tbody></table>"
    )

    bc_html = (
        "<ul style='margin:0 0 0 18px;padding:0;font:14px/1.5 system-ui,Arial'>"
        f"<li>Investition: <b>{bc['invest_eur']:.0f} €</b></li>"
        f"<li>Jährliche Einsparung: <b>{bc['annual_saving_eur']:.0f} €</b></li>"
        f"<li>Payback: <b>{bc['payback_months']:.1f} Monate</b></li>"
        f"<li>ROI Jahr 1: <b>{bc['roi_year1_pct']:.1f}%</b></li>"
        "</ul>"
    )

    qc_card = ""
    if ctx.get("quality_badge"):
        qc_card = _card("Quality‑Check", ctx["quality_badge"])

    news_block = live.get("news_html") or "<p>Keine aktuellen Meldungen gefunden.</p>"
    tools_block = live.get("tools_html") or "<p>Keine neuen Tools/Versionen gefunden.</p>"
    fund_block = live.get("funding_html") or "<p>Keine passenden Förderprogramme gefunden.</p>"

    html = (
        "<!doctype html><html lang='de'><head><meta charset='utf-8'/>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'/>"
        "<title>KI‑Status‑Report</title></head><body style='background:#f7fbff;margin:0'>"
        f"<header style='background:{COLOR_PRIMARY};color:#fff;padding:16px 20px'>"
        "<h1 style='margin:0;font:600 22px/1.3 system-ui,Arial'>KI‑Status‑Report</h1>"
        f"<p style='margin:6px 0 0;font:14px/1.5 system-ui,Arial'>Stand: {ctx['meta']['date']}</p>"
        "</header>"
        "<main style='max-width:980px;margin:0 auto;padding:16px 20px'>"
        f"{_card('Executive Summary', s['executive_summary_html'])}"
        f"{_card('KPI‑Übersicht', kpi_html)}"
        f"{_card('Business Case', bc_html)}"
        f"{_card('Benchmark‑Vergleich', bench_html)}"
        f"{_card('Quick Wins', s['quick_wins_html'])}"
        f"{_card('90‑Tage‑Roadmap', s['roadmap_html'])}"
        f"{_card('Risikomatrix & Mitigation', s['risks_html'])}"
        f"{qc_card}"
        f"{_card('Aktuelle Meldungen (Stand: ' + live['stand'] + ')', news_block)}"
        f"{_card('Neue Tools & Releases (Stand: ' + live['stand'] + ')', tools_block)}"
        f"{_card('Förderprogramme (Stand: ' + live['stand'] + ')', fund_block)}"
        "</main></body></html>"
    )
    return html

# -----------------------------------------------------------------------------
# Öffentliche API
# -----------------------------------------------------------------------------
def analyze_briefing(form_data: Optional[Dict[str, Any]] = None,
                     lang: Optional[str] = None,
                     template: Optional[str] = None,
                     **kwargs: Any) -> str:
    if not form_data:
        form_data = {}
    language = (lang or form_data.get("lang") or DEFAULT_LANG)[:5]
    ctx = build_context(form_data, language)
    if template or Environment is not None:
        try:
            return _render_jinja(ctx, language, template)
        except Exception as exc:
            logger.warning("Template‑Rendering fehlgeschlagen, Fallback‑Renderer: %s", exc)
    return render_html(ctx)

def analyze_briefing_enhanced(form_data: Optional[Dict[str, Any]] = None,
                              lang: Optional[str] = None,
                              **kwargs: Any) -> Dict[str, Any]:
    if not form_data:
        form_data = {}
    language = (lang or form_data.get("lang") or DEFAULT_LANG)[:5]
    return build_context(form_data, language)

if __name__ == "__main__":  # pragma: no cover
    sample = {
        "branche": "Medien & Kreativwirtschaft",
        "unternehmensgroesse": "KMU",
        "bundesland": "BY",
        "hauptleistung": "Beratung",
        "investitionsbudget": "2.000–10.000 €",
        "ziel": "Automatisierung & Innovation",
        "digitalisierung": 8, "automatisierung": 6, "compliance": 7, "prozessreife": 6, "innovation": 7,
    }
    print(analyze_briefing(sample, lang="de")[:600])
