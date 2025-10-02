# File: gpt_analyze.py
# -*- coding: utf-8 -*-
"""
MAKE-KI Backend – Report Generator (Gold‑Standard+)

Öffentliche API (vom Backend erwartet):
- analyze_briefing(form_data: dict = None, lang: str = None, **kwargs) -> str (HTML)
- analyze_briefing_enhanced(form_data: dict = None, lang: str = None, **kwargs) -> dict

Kern:
- build_context(form_data, lang)  -> dict  (Briefing + KPIs + Business Case + Live + LLM-Sektionen)
- render_html(context)            -> str   (Fallback-Renderer, wenn Jinja2/Template nicht genutzt werden)

Besondere Merkmale:
- LLM‑Sektionen: Executive Summary, Quick Wins, Roadmap, Risiken, Compliance, Doc‑Digest (robuste Fallbacks).
- Prompt‑Overlays nach Branche/Größe/Language mit definierten Fallbacks.
- Live‑Quellen (Tavily/EU‑APIs) – rückwärtskompatibel zu älteren util‑Signaturen.  (websearch_utils, eu_connectors)
- Quality‑Control‑Integration (ReportQualityController) inkl. Badge im Report.
- DOCX‑Digest (4‑Säulen / Stolpersteine / 10‑20‑70) als Executive‑Knowledge‑Box.

Verweise:
- Quality‑Control‑Logik siehe quality_control.py.  (wir mappen Kontext‑Keys, damit Checks greifen)  # filecite marker
- Live‑Suche siehe websearch_utils.py / eu_connectors.py.                                   # filecite marker
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
from typing import Any, Dict, Optional, Tuple, List

# Optionales Templating (für PDF-Service). Fällt andernfalls auf render_html zurück.
try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape  # type: ignore
except Exception:  # pragma: no cover
    Environment = None  # type: ignore

# -----------------------------------------------------------------------------
# Konfiguration / ENV
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
LLM_MODE = os.getenv("LLM_MODE", "hybrid").lower()  # hybrid | on | off
QUALITY_CONTROL_AVAILABLE = os.getenv("QUALITY_CONTROL_AVAILABLE", "true").lower() == "true"

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
    # optionale manuelle KPI-Eingaben 0–10
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
    s = s.replace("&", " und ").replace("ä","ae").replace("ö","oe").replace("ü","ue").replace("ß","ss")
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
# Benchmarks
# -----------------------------------------------------------------------------
def load_benchmarks(branch: str, size: str) -> Dict[str, float]:
    """Lädt Benchmarks aus data/benchmarks_<sanitized_branch>_<size>.json."""
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

# -----------------------------------------------------------------------------
# Business Case
# -----------------------------------------------------------------------------
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

def compute_business_case(briefing: Dict[str, Any], bm: Dict[str, float]) -> BusinessCase:
    invest = invest_from_bucket(_s(briefing.get("investitionsbudget")))
    auto = bm.get("automatisierung", 0.55)
    proc = bm.get("prozessreife", 0.60)
    scale = 40000.0  # obere Bandbreite jährliche Einsparung
    annual_saving = max(12000.0, (0.6 * auto + 0.4 * proc) * scale)
    return BusinessCase(invest_eur=invest, annual_saving_eur=annual_saving)

# -----------------------------------------------------------------------------
# Live‑Sektionen (robust / rückwärtskompatibel)
# -----------------------------------------------------------------------------
def _query_live_items(briefing: Dict[str, Any], lang: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Ruft Live‑Quellen ab und gibt kategorisierte Items zurück.
    Unterstützt neue und ältere Signaturen von websearch_utils.query_live_items.
    """
    try:
        # Neue API: benannte Parameter
        from websearch_utils import query_live_items as _ql  # type: ignore  # filecite marker
        return _ql(
            industry=_s(briefing.get("branche")),
            size=_s(briefing.get("unternehmensgroesse")),
            main_service=_s(briefing.get("hauptleistung")),
            region=_s(briefing.get("bundesland")),
        )
    except Exception:
        try:
            # Alte API: Tuple mit HTML‑Blöcken
            from websearch_utils import query_live_items as _ql_legacy  # type: ignore  # filecite marker
            news_html, tools_html, funding_html = _ql_legacy(briefing, lang)  # type: ignore
            return {
                "news": [{"kind": "news", "title": "", "url": "", "summary": news_html}],
                "tools": [{"kind": "tool", "title": "", "url": "", "summary": tools_html}],
                "funding": [{"kind": "funding", "title": "", "url": "", "summary": funding_html}],
            }
        except Exception as exc:
            logger.info("websearch_utils nicht verfügbar – Live-Sektionen leer. (%s)", exc)
            return {}

def _render_live_html(items: List[Dict[str, Any]]) -> str:
    if not items:
        return "<p>Keine Daten gefunden.</p>"
    lis = []
    for it in items[:10]:
        title = (it.get("title") or "").strip() or "Ohne Titel"
        url = (it.get("url") or "").strip()
        summary = (it.get("summary") or it.get("snippet") or "").strip()
        meta = []
        if it.get("published_at") or it.get("date"):
            meta.append((it.get("published_at") or it.get("date"))[:10])
        if it.get("deadline"):
            meta.append("Deadline: " + it["deadline"])
        meta_s = " · ".join(meta)
        if url:
            lis.append(f"<li><a href='{url}' rel='noopener' target='_blank'>{title}</a>"
                       f"{(' — ' + summary) if summary else ''}"
                       f"{(' <small>(' + meta_s + ')</small>') if meta_s else ''}</li>")
        else:
            lis.append(f"<li><b>{title}</b>{(' — ' + summary) if summary else ''}"
                       f"{(' <small>(' + meta_s + ')</small>') if meta_s else ''}</li>")
    return "<ul>" + "".join(lis) + "</ul>"

# -----------------------------------------------------------------------------
# KPI & Kontext
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
        "de": "Du bist Strategy‑Consultant. Erstelle eine prägnante Executive Summary (HTML <p>).",
        "en": "You are a strategy consultant. Create an executive summary (HTML <p>).",
    },
    "quick_wins": {
        "de": "Liste 5 Quick Wins als <ul> mit Aufwand (Tage), Nutzen und Owner‑Rolle.",
        "en": "List 5 quick wins as <ul> with effort (days), benefit and owner role.",
    },
    "roadmap": {
        "de": "Erstelle eine 90‑Tage‑Roadmap (1–2, 3–4, 5–8, 9–12) als <ol>.",
        "en": "Create a 90‑day roadmap (1–2, 3–4, 5–8, 9–12) as <ol>.",
    },
    "risks": {
        "de": "Top‑5‑Risikomatrix als <table> (Wahrsch., Auswirkung, Mitigation).",
        "en": "Top‑5 risk matrix as <table> (probability, impact, mitigation).",
    },
    "compliance": {
        "de": "MVC‑Checkliste (AI‑VO/DSA/CRA/Data Act) als <ul> mit klaren Aktionen.",
        "en": "MVC checklist (EU AI Act/DSA/CRA/Data Act) as <ul> with clear actions.",
    },
    "doc_digest": {
        "de": "Erstelle eine knappe Executive‑Kurzfassung der gelieferten Dokumente als <p> + <ul>. Text: {doc_text}",
        "en": "Provide a concise executive digest of the provided docs as <p> + <ul>. Text: {doc_text}",
    },
}

def _load_prompt(name: str, lang: str, *, branch: str = "", size: str = "") -> str:
    b = _sanitize_branch(branch)
    s = _sanitize_size(size)
    candidates = [
        PROMPTS_DIR / f"{name}__{b}_{s}_{lang}.md",
        PROMPTS_DIR / f"{name}__{b}_{lang}.md",
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
        def __missing__(self, key):
            return "{" + key + "}"
    return tpl.format_map(_D(ctx))

def _openai_chat(prompt: str) -> str:
    """Robuster OpenAI‑Aufruf (neu/alt SDK). Fällt auf Ausnahme zurück."""
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
                    temperature=OPENAI_TEMPERATURE,
                    max_tokens=OPENAI_MAX_TOKENS,
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
                    temperature=OPENAI_TEMPERATURE,
                    max_tokens=OPENAI_MAX_TOKENS,
                    messages=[
                        {"role": "system", "content": "You are a concise, senior AI and strategy consultant."},
                        {"role": "user", "content": prompt},
                    ],
                    timeout=OPENAI_TIMEOUT,
                )
                return (resp["choices"][0]["message"]["content"] or "").strip()
        except Exception as exc:  # pragma: no cover
            last_exc = exc
            logger.warning("OpenAI‑Call fehlgeschlagen (Versuch %s/2): %s", attempt + 1, exc)
            time.sleep(1.0 + attempt)
            if attempt == 0:
                os.environ["EXEC_SUMMARY_MODEL"] = OPENAI_FALLBACK_MODEL
    raise RuntimeError(f"OpenAI failed: {last_exc}")

# ---- Fallback‑Sektionen ------------------------------------------------------
def _fallback_exec_summary(ctx: Dict[str, Any]) -> str:
    return (
        "<p>Ihre Organisation weist ein hohes KI‑Potenzial auf. "
        f"Der zusammengesetzte Score liegt bei <b>{ctx['score_percent']:.1f}%</b>. "
        f"Der Business‑Case zeigt einen <b>ROI im ersten Jahr von {ctx['business_case']['roi_year1_pct']:.1f}%</b> "
        f"bei einer <b>Amortisationszeit von {ctx['business_case']['payback_months']:.1f} Monaten</b>. "
        "Fokussieren Sie Automatisierung in Kernprozessen und ein Minimum‑Viable‑Compliance‑Set.</p>"
    )

def _fallback_quick_wins(ctx: Dict[str, Any]) -> str:
    return (
        "<ul>"
        "<li>E‑Mail‑ und Angebotsvorlagen automatisieren (2–3 Tage, Owner: Vertrieb/Marketing).</li>"
        "<li>Meeting‑Zusammenfassungen mit KI (1 Tag, Owner: PMO).</li>"
        "<li>FAQ‑/Wissensbot intern (3–5 Tage, Owner: IT).</li>"
        "<li>Lead‑Qualifizierung halbautomatisieren (3–5 Tage, Owner: Marketing).</li>"
        "<li>Compliance‑Checkliste & Go‑Live‑Gate (1–2 Tage, Owner: Legal/IT).</li>"
        "</ul>"
    )

def _fallback_roadmap(ctx: Dict[str, Any]) -> str:
    return (
        "<ol>"
        "<li>W1–2: KPI‑Baseline; Quick‑Wins priorisieren; MVC‑Checkliste.</li>"
        "<li>W3–4: Daten/Toolauswahl; Pilot automatisierter Prozess.</li>"
        "<li>W5–8: Rollout Kern‑Use‑Case; Schulung; Monitoring & Drift‑Checks.</li>"
        "<li>W9–12: Skalierung; Controlling; ROI‑Review; nächste Welle planen.</li>"
        "</ol>"
    )

def _fallback_risks(ctx: Dict[str, Any]) -> str:
    return (
        "<table role='table' style='width:100%;border-collapse:collapse'>"
        "<thead><tr><th>Risiko</th><th>Wahrsch.</th><th>Auswirkung</th><th>Mitigation</th></tr></thead>"
        "<tbody>"
        "<tr><td>Compliance‑Verstöße (AI‑VO/DSA/CRA)</td><td>mittel</td><td>hoch</td>"
        "<td>MVC, HiTL, Go‑Live‑Gate, Re‑Klassifizierung</td></tr>"
        "<tr><td>Modell‑Drift/Bias</td><td>mittel</td><td>mittel</td>"
        "<td>Monitoring, Re‑Tests, Data‑Governance</td></tr>"
        "<tr><td>Datenleck/DLP</td><td>niedrig</td><td>hoch</td>"
        "<td>Pseudonymisierung, Rollen, Protokollierung</td></tr>"
        "<tr><td>Abhängigkeit von Drittanbietern</td><td>mittel</td><td>mittel</td>"
        "<td>Exit‑Strategie, Multi‑Vendor, Offline‑Fallbacks</td></tr>"
        "<tr><td>Akzeptanz/Change</td><td>mittel</td><td>mittel</td>"
        "<td>Enablement, klare Leitplanken, Stakeholder‑Kommunikation</td></tr>"
        "</tbody></table>"
    )

def _fallback_compliance(ctx: Dict[str, Any]) -> str:
    return (
        "<ul>"
        "<li>AI‑Policy & Registry; Rollen & Pflichten definieren.</li>"
        "<li>DPIA/DSFA durchführen; Freigaben dokumentieren.</li>"
        "<li>Verträge/TOMs/IP klären; DLP & Audit‑Trail.</li>"
        "<li>Re‑Klassifizierungs‑Trigger; HiTL & Kill‑Switch.</li>"
        "<li>Rollenbasierte Trainings & Refreshers.</li>"
        "</ul>"
    )

def _fallback_doc_digest(ctx: Dict[str, Any]) -> str:
    return "<p>Kurzfassung nicht verfügbar.</p><ul><li>Policies</li><li>Use‑Case‑Register</li><li>Go‑Live‑Gate</li><li>Trainings</li></ul>"

def _gen_llm(name: str, ctx_small: Dict[str, Any], *, branch: str, size: str, lang: str) -> str:
    tpl = _load_prompt(name, lang, branch=branch, size=size)
    prompt = _format_prompt(tpl, ctx_small)
    return _openai_chat(prompt)

def _generate_llm_sections(context: Dict[str, Any], lang: str) -> Dict[str, str]:
    """Erzeugt HTML‑Sektionen via LLM, mit robusten Fallbacks."""
    branch = context["briefing"]["branche"]
    size = context["briefing"]["unternehmensgroesse"]

    ctx_small = {
        "branche": branch,
        "unternehmensgroesse": size,
        "bundesland": context["briefing"]["bundesland"],
        "hauptleistung": context["briefing"]["hauptleistung"],
        "score_percent": context["score_percent"],
        "roi_year1_pct": context["business_case"]["roi_year1_pct"],
        "payback_months": context["business_case"]["payback_months"],
    }

    def try_gen(key: str, fb) -> str:
        try:
            return _gen_llm(key, ctx_small, branch=branch, size=size, lang=lang)
        except Exception as exc:
            logger.info("LLM‑Sektion %s – Fallback aktiv (%s)", key, exc)
            return fb(context)

    def try_doc_digest() -> str:
        doc_text = context.get("docs_text", "")
        if not doc_text:
            return _fallback_doc_digest(context)
        tpl = _load_prompt("doc_digest", lang, branch=branch, size=size)
        prompt = _format_prompt(tpl, {"doc_text": doc_text})
        try:
            return _openai_chat(prompt)
        except Exception as exc:
            logger.info("LLM‑Sektion doc_digest – Fallback aktiv (%s)", exc)
            return _fallback_doc_digest(context)

    return {
        "executive_summary_html": try_gen("executive_summary", _fallback_exec_summary),
        "quick_wins_html": try_gen("quick_wins", _fallback_quick_wins),
        "roadmap_html": try_gen("roadmap", _fallback_roadmap),
        "risks_html": try_gen("risks", _fallback_risks),
        "compliance_html": try_gen("compliance", _fallback_compliance),
        "doc_digest_html": try_doc_digest(),
    }

# -----------------------------------------------------------------------------
# Dokument‑Integration (DOCX)
# -----------------------------------------------------------------------------
def _load_docx_as_text_if_exists(filename: str) -> str:
    path = BASE_DIR / filename
    if not path.exists():
        return ""
    try:
        import zipfile
        from xml.etree import ElementTree as ET
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml")
        root = ET.fromstring(xml)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        texts = [node.text for node in root.findall(".//w:t", ns) if node.text]
        return "\n".join(texts)
    except Exception as exc:
        logger.warning("DOCX‑Lesen fehlgeschlagen (%s): %s", filename, exc)
        return ""

def _compose_docs_text() -> str:
    # Drei gelieferte Basis‑Dokumente, als inhaltliche Anker.
    # 4‑Säulen, rechtliche Stolpersteine, 10‑20‑70.                          # filecite markers
    files = [
        "4-Saeulen-KI-Readiness.docx",            # :contentReference[oaicite:2]{index=2}
        "rechtliche-Stolpersteine-KI-im Unternehmen.docx",  # :contentReference[oaicite:3]{index=3}
        "Formel-fuer Transformation.docx",        # :contentReference[oaicite:4]{index=4}
    ]
    parts: List[str] = []
    for fn in files:
        txt = _load_docx_as_text_if_exists(fn)
        if txt:
            parts.append(txt)
    return "\n\n".join(parts)

# -----------------------------------------------------------------------------
# Quality‑Control Integration (optional)
# -----------------------------------------------------------------------------
def _map_for_qc(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Flacht Kontext auf erwartete Keys der quality_control‑Checks ab."""
    out = dict(ctx)  # flacher Start
    sec = ctx.get("sections", {})
    bc = ctx.get("business_case", {})
    kpi = ctx.get("kpis", {})

    # Sektionen (Top‑Level, damit bestehende QC‑Checks greifen)
    out["exec_summary_html"] = sec.get("executive_summary_html", "")
    out["quick_wins_html"] = sec.get("quick_wins_html", "")
    out["roadmap_html"] = sec.get("roadmap_html", "")
    out["risks_html"] = sec.get("risks_html", "")
    # einfache „Empfehlungen“-Sektion aus QuickWins/Compliance gemischt
    rec = (sec.get("quick_wins_html", "") or "") + (sec.get("compliance_html", "") or "")
    out["recommendations_html"] = rec[:8000]

    # ROI & KPI‑Mapping
    out["roi_investment"] = bc.get("invest_eur", 0)
    out["roi_annual_saving"] = bc.get("annual_saving_eur", 0)
    out["kpi_roi_months"] = bc.get("payback_months", 0)
    out["kpi_compliance"] = round(kpi.get("compliance", 0.0) * 100, 1)
    out["automatisierungsgrad"] = round(kpi.get("automatisierung", 0.0) * 100, 1)
    # konservativer Effizienz‑Wert (<= 0.6 * (100 - Automatisierung)) → QC‑Check „plausibel“
    out["kpi_efficiency"] = round((1.0 - kpi.get("automatisierung", 0.0)) * 60, 1)

    # Readiness‑Level‑Label passend zur QC‑Heuristik
    score = ctx.get("score_percent", 0)
    if score >= 85:
        level = "Führend"
    elif score >= 70:
        level = "Reif"
    elif score >= 50:
        level = "Fortgeschritten"
    elif score >= 30:
        level = "Grundlegend"
    else:
        level = "Anfänger"
    out["readiness_level"] = level

    # Datenschutzbeauftragter – defensiver Default
    out["datenschutzbeauftragter"] = "extern"

    return out

def _run_quality_control(ctx: Dict[str, Any], lang: str) -> Dict[str, Any]:
    if not QUALITY_CONTROL_AVAILABLE:
        return {"enabled": False}
    try:
        from quality_control import ReportQualityController  # type: ignore  # filecite marker
    except Exception as exc:
        logger.info("Quality‑Control nicht verfügbar: %s", exc)
        return {"enabled": False, "error": str(exc)}

    qc = ReportQualityController()
    qc_input = _map_for_qc(ctx)
    result = qc.validate_complete_report(qc_input, lang)  # :contentReference[oaicite:5]{index=5}

    # Checks serialisieren (robust)
    def _ser(check):
        return {
            "name": getattr(check, "name", ""),
            "passed": bool(getattr(check, "passed", False)),
            "score": float(getattr(check, "score", 0)),
            "message": getattr(check, "message", ""),
            "severity": getattr(check, "severity", "minor"),
        }

    payload = {
        "enabled": True,
        "passed": bool(result.get("passed", False)),
        "quality_level": result.get("quality_level", "FAILED"),
        "overall_score": float(result.get("overall_score", 0)),
        "checks": [_ser(c) for c in result.get("checks", [])],
        "critical_issues": [_ser(c) for c in result.get("critical_issues", [])],
        "improvements": result.get("improvements", [])[:5],
        "report_card": result.get("report_card", {}),
    }
    return payload

# -----------------------------------------------------------------------------
# Kontextaufbau
# -----------------------------------------------------------------------------
def build_context(form_data: Dict[str, Any], lang: str) -> Dict[str, Any]:
    now = _now_iso()
    branch = _s(form_data.get("branche"))
    size = _s(form_data.get("unternehmensgroesse"))
    bm = load_benchmarks(branch, size)
    kpi_raw = _kpi_from_briefing(form_data)
    kpi = _merge_kpis(kpi_raw, bm)

    score = (kpi["digitalisierung"] + kpi["automatisierung"] +
             kpi["compliance"] + kpi["prozessreife"] + kpi["innovation"]) / 5.0

    bc = compute_business_case(form_data, bm)

    # Live
    live_items = _query_live_items(form_data, lang)  # :contentReference[oaicite:6]{index=6}
    news_html = _render_live_html(live_items.get("news", [])) if live_items else ""
    tools_html = _render_live_html(live_items.get("tools", [])) if live_items else ""
    funding_html = _render_live_html(live_items.get("funding", [])) if live_items else ""

    # Docs (für Doc‑Digest)
    docs_text = _compose_docs_text()

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
        "docs_text": docs_text,
        "sections": {
            "executive_summary_html": "",
            "quick_wins_html": "",
            "roadmap_html": "",
            "risks_html": "",
            "compliance_html": "",
            "doc_digest_html": "",
        },
    }

    # LLM‑Sektionen
    if ENABLE_LLM_SECTIONS and LLM_MODE in ("on", "hybrid"):
        try:
            secs = _generate_llm_sections(ctx, lang)
            ctx["sections"].update(secs)
        except Exception as exc:
            logger.info("LLM‑Sektionen globaler Fallback: %s", exc)
            ctx["sections"]["executive_summary_html"] = _fallback_exec_summary(ctx)
            ctx["sections"]["quick_wins_html"] = _fallback_quick_wins(ctx)
            ctx["sections"]["roadmap_html"] = _fallback_roadmap(ctx)
            ctx["sections"]["risks_html"] = _fallback_risks(ctx)
            ctx["sections"]["compliance_html"] = _fallback_compliance(ctx)
            ctx["sections"]["doc_digest_html"] = _fallback_doc_digest(ctx)
    else:
        ctx["sections"]["executive_summary_html"] = _fallback_exec_summary(ctx)
        ctx["sections"]["quick_wins_html"] = _fallback_quick_wins(ctx)
        ctx["sections"]["roadmap_html"] = _fallback_roadmap(ctx)
        ctx["sections"]["risks_html"] = _fallback_risks(ctx)
        ctx["sections"]["compliance_html"] = _fallback_compliance(ctx)
        ctx["sections"]["doc_digest_html"] = _fallback_doc_digest(ctx)

    # Quality‑Control (optional, robust)
    qc_payload = _run_quality_control(ctx, lang)  # :contentReference[oaicite:7]{index=7}
    if qc_payload.get("enabled"):
        ctx["quality"] = qc_payload
        ctx["quality_badge"] = qc_payload.get("report_card", {})

    return ctx

# -----------------------------------------------------------------------------
# Rendering
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
        f"<div style='display:flex;justify-content:space-between;"
        f"font:14px/1.4 system-ui,Arial'><span>{label}</span><span>{pct}%</span></div>"
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
    k = ctx["kpis"]
    bc = ctx["business_case"]
    live = ctx["live"]
    s = ctx["sections"]
    qb = ctx.get("quality_badge", {})

    quality_html = ""
    if qb:
        quality_html = (
            "<ul style='margin:0 0 0 18px;padding:0;font:14px/1.5 system-ui,Arial'>"
            f"<li>Grade: <b>{qb.get('grade','')}</b></li>"
            f"<li>Score: <b>{qb.get('score','')}</b></li>"
            f"<li>Checks: <b>{qb.get('passed_checks','')}</b></li>"
            f"<li>Kritische Themen: <b>{qb.get('critical_issues',0)}</b></li>"
            "</ul>"
        )

    kpi_html = "".join([
        _progress_bar("Digitalisierung", k["digitalisierung"]),
        _progress_bar("Automatisierung", k["automatisierung"]),
        _progress_bar("Compliance", k["compliance"]),
        _progress_bar("Prozessreife", k["prozessreife"]),
        _progress_bar("Innovation", k["innovation"]),
    ])

    bench = ctx["kpis_benchmark"]
    rows = []
    for key, label in [
        ("digitalisierung", "Digitalisierung"),
        ("automatisierung", "Automatisierung"),
        ("compliance", "Compliance"),
        ("prozessreife", "Prozessreife"),
        ("innovation", "Innovation"),
    ]:
        v = k[key] * 100.0
        b = bench.get(key, 0) * 100.0
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

    news_block = live.get("news_html") or "<p>Keine aktuellen Meldungen gefunden.</p>"
    tools_block = live.get("tools_html") or "<p>Keine neuen Tools/Versionen gefunden.</p>"
    fund_block = live.get("funding_html") or "<p>Keine passenden Förderprogramme gefunden.</p>"

    html = (
        "<!doctype html><html lang='de'><head><meta charset='utf-8'/>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'/>"
        "<title>KI‑Status‑Report</title></head>"
        "<body style='background:#f7fbff;margin:0'>"
        f"<header style='background:{COLOR_PRIMARY};color:#fff;padding:16px 20px'>"
        "<h1 style='margin:0;font:600 22px/1.3 system-ui,Arial'>KI‑Status‑Report</h1>"
        f"<p style='margin:6px 0 0;font:14px/1.5 system-ui,Arial'>Stand: {ctx['meta']['date']}</p>"
        "</header>"
        "<main style='max-width:980px;margin:0 auto;padding:16px 20px'>"
        f"{_card('Executive Summary', s['executive_summary_html'])}"
        f"{_card('Quality Check', quality_html) if quality_html else ''}"
        f"{_card('KPI‑Übersicht', kpi_html)}"
        f"{_card('Business Case', bc_html)}"
        f"{_card('Benchmark‑Vergleich', bench_html)}"
        f"{_card('Quick Wins', s['quick_wins_html'])}"
        f"{_card('90‑Tage‑Roadmap', s['roadmap_html'])}"
        f"{_card('Risikomatrix & Mitigation', s['risks_html'])}"
        f"{_card('Compliance (MVC) – Go‑Live‑Gate', s['compliance_html'])}"
        f"{_card('Executive Knowledge Digest', s['doc_digest_html'])}"
        f"{_card('Aktuelle Meldungen (Stand: ' + live['stand'] + ')', news_block)}"
        f"{_card('Neue Tools & Releases (Stand: ' + live['stand'] + ')', tools_block)}"
        f"{_card('Förderprogramme (Stand: ' + live['stand'] + ')', fund_block)}"
        "<footer style='margin:24px 0 12px;color:#6b7280;font:12px/1.4 system-ui,Arial'>"
        "Quelle/Owner: TÜV‑zertifiziertes KI‑Management – Wolf Hohl – ki‑sicherheit.jetzt"
        "</footer>"
        "</main>"
        "</body></html>"
    )
    return html

# -----------------------------------------------------------------------------
# Öffentliche API
# -----------------------------------------------------------------------------
def analyze_briefing(form_data: Optional[Dict[str, Any]] = None,
                     lang: Optional[str] = None,
                     template: Optional[str] = None,
                     **kwargs: Any) -> str:
    """Kompatible Signatur (akzeptiert 'lang'; ignoriert zusätzliche kwargs)."""
    if not form_data:
        form_data = {}
    language = (lang or form_data.get("lang") or DEFAULT_LANG)[:5]
    ctx = build_context(form_data, language)

    if template or Environment is not None:
        try:
            return _render_jinja(ctx, language, template)
        except Exception as exc:
            logger.warning("Template‑Rendering fehlgeschlagen, nutze Fallback‑Renderer: %s", exc)
    return render_html(ctx)

def analyze_briefing_enhanced(form_data: Optional[Dict[str, Any]] = None,
                              lang: Optional[str] = None,
                              **kwargs: Any) -> Dict[str, Any]:
    """Gibt Payload/Context als Dict zurück (Debug/QC)."""
    if not form_data:
        form_data = {}
    language = (lang or form_data.get("lang") or DEFAULT_LANG)[:5]
    return build_context(form_data, language)

# CLI optional
if __name__ == "__main__":  # pragma: no cover
    sample = {
        "branche": "Medien & Kreativwirtschaft",
        "unternehmensgroesse": "KMU",
        "bundesland": "BY",
        "hauptleistung": "Beratung",
        "investitionsbudget": "2.000–10.000 €",
        "ziel": "Automatisierung & Innovation",
        "digitalisierung": 8,  # optional 0–10
        "automatisierung": 6,
        "compliance": 7,
        "prozessreife": 6,
        "innovation": 7,
    }
    print(analyze_briefing(sample, lang="de")[:600])
