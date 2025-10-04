# File: gpt_analyze.py
# -*- coding: utf-8 -*-
"""
MAKE-KI Backend - Report Generator (Gold-Standard+)

Neuerungen:
- Robustes Modell-Routing (v1-Client; Auto-Fallback auf gpt-4o bei model_not_found)
- Konsistentes Quality-Badge (Score-basiert)
- Progress-Bars & Benchmark-Vergleich (HTML)
- Admin-Payload-Helfer (raw + normalized + missing fields)
- Sicheres HTML, PEP8, Logging
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence
from urllib.parse import urlparse

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape  # type: ignore
except ImportError:
    Environment = None  # type: ignore

BASE_DIR: Path = Path(__file__).resolve().parent
DATA_DIR: Path = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
PROMPTS_DIR: Path = Path(os.getenv("PROMPTS_DIR", str(BASE_DIR / "prompts")))
TEMPLATE_DIR: Path = Path(os.getenv("TEMPLATE_DIR", str(BASE_DIR / "templates")))

DEFAULT_LANG: str = os.getenv("DEFAULT_LANG", "de")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

ENABLE_LLM_SECTIONS: bool = os.getenv("ENABLE_LLM_SECTIONS", "true").lower() == "true"
OFFICIAL_API_ENABLED: bool = os.getenv("OFFICIAL_API_ENABLED", "false").lower() == "true"
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

EXEC_SUMMARY_MODEL: str = os.getenv("EXEC_SUMMARY_MODEL", "gpt-4o")
OPENAI_TIMEOUT: int = int(os.getenv("OPENAI_TIMEOUT", "30"))
OPENAI_MAX_TOKENS: int = int(os.getenv("OPENAI_MAX_TOKENS", "1200"))
OPENAI_TEMPERATURE: float = float(os.getenv("GPT_TEMPERATURE", "0.2"))
LLM_MODE: str = os.getenv("LLM_MODE", "on").lower()

SEARCH_PROVIDER = os.getenv("SEARCH_PROVIDER", "hybrid").lower()
ENABLE_CASE_STUDIES = os.getenv("ENABLE_CASE_STUDIES", "true").lower() == "true"
ENABLE_REGULATORY = os.getenv("ENABLE_REGULATORY", "true").lower() == "true"
ENABLE_EU_HOST_CHECK = os.getenv("ENABLE_EU_HOST_CHECK", "true").lower() == "true"

if not logging.getLogger().handlers:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
logger = logging.getLogger("gpt_analyze")

# ------------------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def fix_encoding(text: Any) -> str:
    if text is None:
        return ""
    s = str(text)
    replacements = {
        "\u201a": ",", "\u201e": '"', "\u201c": '"', "\u201d": '"',
        "\u2013": "–", "\u2014": "—", "\u20ac": "€",
    }
    for old, new in replacements.items():
        s = s.replace(old, new)
    return s

def _s(x: Any) -> str:
    return fix_encoding(x).strip()

def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default

def _sanitize_name(name: str) -> str:
    s = fix_encoding(name or "").strip().lower()
    s = s.replace("&", "_und_").replace(" ", "_").replace("/", "_")
    s = re.sub(r"[^a-z0-9_]+", "", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "default"

def _escape_html(text: str) -> str:
    return html.escape(text, quote=True)

def _safe_href(url: str) -> str:
    try:
        parsed = urlparse(url)
        if parsed.scheme in ("http", "https"):
            return url
    except Exception:
        pass
    return "#"

class _SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:  # type: ignore[override]
        return "{" + key + "}"

def flatten_mapping(mapping: Mapping[str, Any]) -> Dict[str, Any]:
    flat: Dict[str, Any] = {}
    for k, v in mapping.items():
        if isinstance(v, dict):
            for sk, sv in v.items():
                flat[f"{k}.{sk}"] = sv
                flat[sk] = sv
        else:
            flat[k] = v
    return flat

def safe_format(template: str, mapping: Mapping[str, Any]) -> str:
    flat = flatten_mapping(mapping)
    return template.format_map(_SafeFormatDict(flat))

# ------------------------------------------------------------------------------
# Benchmarks (wie bisher, gekürzt)
# ------------------------------------------------------------------------------
BRANCH_MAPPINGS = {
    "beratung": ["beratung", "consulting", "dienstleistung", "dienstleistungen"],
    "medien": ["medien", "kreativwirtschaft", "media", "film", "video"],
    "handel": ["handel", "e_commerce", "retail", "verkauf"],
    "it": ["it", "software", "tech", "digital"],
    "industrie": ["industrie", "produktion", "manufacturing"],
    "finanzen": ["finanzen", "versicherungen", "banking", "insurance"],
    "gesundheit": ["gesundheit", "pflege", "health", "medical"],
    "bildung": ["bildung", "education", "training"],
    "verwaltung": ["verwaltung", "administration", "government"],
    "marketing": ["marketing", "werbung", "advertising", "pr"],
    "transport": ["transport", "logistik", "logistics"],
    "bau": ["bau", "bauwesen", "architektur", "construction"],
}
CATEGORY_TO_CANONICAL = {
    "bau": "bauwesen_architektur",
    "transport": "transport_logistik",
    "marketing": "marketing_werbung",
    "finanzen": "finanzen_versicherungen",
    "it": "it",
    "medien": "medien",
    "industrie": "industrie_produktion",
    "gesundheit": "gesundheit_pflege",
    "beratung": "beratung",
}

_BENCHMARK_INDEX_CACHE: Optional[set] = None

def _discover_benchmark_index():
    global _BENCHMARK_INDEX_CACHE
    if _BENCHMARK_INDEX_CACHE is not None:
        return _BENCHMARK_INDEX_CACHE
    combos = set()
    if DATA_DIR.exists():
        for p in DATA_DIR.glob("benchmarks_*_*.json"):
            name = p.stem[len("benchmarks_") :]
            if "_" not in name:
                continue
            *branch_parts, size = name.split("_")
            branch_key = "_".join(branch_parts)
            combos.add((_sanitize_name(branch_key), _sanitize_name(size)))
    _BENCHMARK_INDEX_CACHE = combos
    return combos

def _best_branch_key(user_branch: str, branch_category: str) -> str:
    b = _sanitize_name(user_branch)
    cat = _sanitize_name(branch_category)
    available = _discover_benchmark_index()
    keys = {bk for (bk, _) in available}
    if b in keys:
        return b
    canonical = CATEGORY_TO_CANONICAL.get(cat)
    if canonical in keys:
        return canonical
    # Fallback: erste Datei (stabil), kein Zufall
    return "verwaltung_kmu" if ("verwaltung_kmu" in {f"{a}_{s}" for a, s in available}) else next(iter(keys), "default")

def find_best_benchmark(branch: str, size: str) -> Dict[str, float]:
    b_in = _sanitize_name(branch)
    s_in = _sanitize_name(size)
    if any(x in s_in for x in ["solo", "einzel", "freelance", "freiberuf", "1"]):
        s = "solo"
    elif any(x in s_in for x in ["klein", "small", "2", "3", "4", "5", "bis_10", "team_2_10"]):
        s = "small"
    else:
        s = "kmu"
    branch_category = next((cat for cat, keys in BRANCH_MAPPINGS.items() if any(k in b_in for k in keys)), "beratung")
    best_key = _best_branch_key(b_in, branch_category)
    candidates = [
        DATA_DIR / f"benchmarks_{best_key}_{s}.json",
        DATA_DIR / f"benchmarks_{best_key}_kmu.json",
        DATA_DIR / "benchmarks_default.json",
    ]
    for path in candidates:
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                kpis = {it["name"]: float(it["value"]) for it in data.get("kpis", [])}
                if kpis:
                    logger.info("Loaded benchmark: %s", path.name)
                    return kpis
            except Exception as e:
                logger.warning("Failed to load %s: %s", path, e)
    logger.warning("Using default benchmarks")
    return {"digitalisierung": 0.60, "automatisierung": 0.35, "compliance": 0.50, "prozessreife": 0.45, "innovation": 0.55}

# ------------------------------------------------------------------------------
# Business Case
# ------------------------------------------------------------------------------
@dataclass
class BusinessCase:
    invest_eur: float
    annual_saving_eur: float
    @property
    def payback_months(self) -> float:
        if self.annual_saving_eur <= 0:
            return 999.0
        return min((self.invest_eur / self.annual_saving_eur) * 12, 999.0)
    @property
    def roi_year1_pct(self) -> float:
        if self.invest_eur <= 0:
            return 0.0
        roi = (self.annual_saving_eur - self.invest_eur) / self.invest_eur * 100
        return max(min(roi, 500.0), -50.0)

def invest_from_bucket(bucket: Optional[str]) -> float:
    if not bucket:
        return 6000.0
    b = bucket.lower()
    if "bis" in b and "2000" in b: return 1500.0
    if "2000" in b and "10000" in b: return 6000.0
    if "10000" in b and "50000" in b: return 30000.0
    if "50000" in b: return 75000.0
    numbers = re.findall(r"\d+", b.replace(".", ""))
    if numbers:
        avg = sum(int(n) for n in numbers) / len(numbers)
        return float(min(max(avg, 1000), 100000))
    return 6000.0

def compute_business_case(briefing: Mapping[str, Any], benchmarks: Mapping[str, float]) -> BusinessCase:
    invest = invest_from_bucket(briefing.get("investitionsbudget"))
    branch = (briefing.get("branche") or "").lower()
    size = (briefing.get("unternehmensgroesse") or "").lower()
    auto = float(benchmarks.get("automatisierung", 0.35))
    proc = float(benchmarks.get("prozessreife", 0.45))
    if "solo" in size:
        if "beratung" in branch or "consulting" in branch:
            hours_saved = 60 * (auto + proc) / 2
            hourly_rate = 100.0
            annual_saving = hours_saved * hourly_rate * 12 * 0.3
        else:
            annual_saving = invest * 2.0
    elif "beratung" in branch:
        annual_saving = invest * 2.5
    elif "medien" in branch:
        annual_saving = invest * 3.0
    elif "it" in branch or "software" in branch:
        annual_saving = invest * 3.5
    else:
        base_saving = 12000 + (invest * 0.5)
        annual_saving = base_saving * (1 + auto * 0.5) * (1 + proc * 0.3)
    return BusinessCase(invest_eur=float(invest), annual_saving_eur=float(annual_saving))

# ------------------------------------------------------------------------------
# OpenAI (v1 + sicheres Fallback, kein Legacy-Spam)
# ------------------------------------------------------------------------------
def _openai_call_v1(prompt: str, model: Optional[str] = None) -> str:
    from openai import OpenAI  # type: ignore
    client = OpenAI(api_key=OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model=model or EXEC_SUMMARY_MODEL,
        messages=[
            {"role": "system", "content": "You are an expert AI consultant. Generate concise, professional HTML."},
            {"role": "user", "content": prompt},
        ],
        temperature=OPENAI_TEMPERATURE,
        max_tokens=OPENAI_MAX_TOKENS,
        timeout=OPENAI_TIMEOUT,
    )
    return (resp.choices[0].message.content or "").strip()

def call_gpt(prompt: str, model: Optional[str] = None) -> str:
    """
    Verwendet v1-Client. Wenn das Modell nicht verfügbar ist, wird
    automatisch auf gpt-4o zurückgeschaltet. Kein Legacy-Fallback,
    damit keine ChatCompletion-Warnungen erscheinen.
    """
    if not OFFICIAL_API_ENABLED or not OPENAI_API_KEY:
        raise RuntimeError("GPT not configured (OFFICIAL_API_ENABLED / OPENAI_API_KEY)")
    try:
        return _openai_call_v1(prompt, model=model or EXEC_SUMMARY_MODEL)
    except Exception as e_v1:
        msg = str(e_v1).lower()
        if "model_not_found" in msg or "does not exist" in msg:
            return _openai_call_v1(prompt, model="gpt-4o")
        logger.warning("OpenAI call failed: %s", e_v1)
        raise

# ------------------------------------------------------------------------------
# Prompt Handling
# ------------------------------------------------------------------------------
CORE_SECTIONS: Sequence[str] = ("executive_summary", "quick_wins", "roadmap", "risks", "compliance")

def load_prompt(name: str, lang: str, branch: str = "", size: str = "") -> str:
    lang = (lang or "de")[:2].lower()
    b = _sanitize_name(branch); s = _sanitize_name(size)
    candidates = [
        PROMPTS_DIR / f"{name}_{b}_{s}_{lang}.md",
        PROMPTS_DIR / f"{name}_{b}_{lang}.md",
        PROMPTS_DIR / f"{name}_{lang}.md",
        PROMPTS_DIR / f"{name}_de.md",
    ]
    for path in candidates:
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8")
                logger.info("Loaded prompt: %s", path.name)
                return content
            except Exception as e:
                logger.warning("Failed to load prompt %s: %s", path, e)
    return f"Generate {name} section for {branch} company of size {size}"

def generate_section(section_name: str, context: Mapping[str, Any], lang: str) -> str:
    branch = context["briefing"]["branche"]; size = context["briefing"]["unternehmensgroesse"]
    if ENABLE_LLM_SECTIONS and OPENAI_API_KEY and LLM_MODE in ("on", "hybrid"):
        try:
            prompt_template = load_prompt(section_name, lang, branch, size)
            payload = {
                "branche": branch, "unternehmensgroesse": size,
                **context.get("briefing", {}), **context.get("business_case", {}),
                "score_percent": context.get("score_percent"),
            }
            prompt = safe_format(prompt_template, payload)
            return call_gpt(prompt)
        except Exception as e:
            logger.warning("GPT generation failed for %s: %s", section_name, e)
    return get_fallback_section(section_name, context, branch)

def get_fallback_section(section_name: str, context: Mapping[str, Any], branch: str) -> str:
    branch_lower = branch.lower()
    is_consulting = any(x in branch_lower for x in ["beratung", "consult", "dienst"])
    is_media = any(x in branch_lower for x in ["medien", "kreativ", "film", "video"])
    is_it = any(x in branch_lower for x in ["it", "software", "digital", "tech"])
    if section_name == "executive_summary":
        score = context["score_percent"]; roi = context["business_case"]["roi_year1_pct"]; payback = context["business_case"]["payback_months"]
        focus = ("Automatisierung von Beratungsprozessen" if is_consulting else
                 "Content-Automatisierung" if is_media else
                 "Code-Qualität & Dev-Automation" if is_it else
                 "Prozessautomatisierung & Daten")
        return (f"<p><b>Key Takeaways:</b> 1) Readiness {score:.1f} %, 2) ROI Jahr 1 {roi:.1f} %, "
                f"3) Amortisation ~{payback:.1f} Monate. Fokus: {html.escape(focus)}.</p>")
    if section_name == "quick_wins":
        return "<ul><li>Automatisierte Prozesse</li><li>KI‑Chatbot</li><li>Document AI</li><li>Predictive Analytics</li><li>RPA‑Pilot</li></ul>"
    if section_name == "roadmap":
        return "<ol><li>W1–2: Setup & Datenschutz</li><li>W3–4: Pilot</li><li>W5–8: Rollout</li><li>W9–12: Optimierung & Scale</li></ol>"
    if section_name == "risks":
        return ('<table style="width:100%;border-collapse:collapse"><thead><tr><th>Risiko</th><th>Wahrsch.</th><th>Impact</th><th>Mitigation</th></tr></thead>'
                '<tbody><tr><td>Datenschutz</td><td>Mittel</td><td>Hoch</td><td>DSGVO-Prozesse</td></tr>'
                '<tr><td>Compliance</td><td>Mittel</td><td>Hoch</td><td>AI-Act-Checklisten</td></tr>'
                '<tr><td>Vendor-Lock</td><td>Mittel</td><td>Mittel</td><td>Open-Source-First</td></tr>'
                '<tr><td>Change-Resistenz</td><td>Hoch</td><td>Mittel</td><td>Change Management</td></tr></tbody></table>')
    if section_name == "compliance":
        return "<ul><li>AI-Act-Klassifizierung</li><li>Transparenzpflichten</li><li>Datenschutz</li><li>Dokumentation</li><li>Monitoring</li></ul>"
    return "<p>Inhalt wird vorbereitet.</p>"

# ------------------------------------------------------------------------------
# Live-Daten – Rendering
# ------------------------------------------------------------------------------
def render_tags(badges: List[str]) -> str:
    return " ".join(f'<span class="tag">{_escape_html(b)}</span>' for b in (badges or []))

def render_cards_html(items: List[Mapping[str, Any]]) -> str:
    if not items: return "<p>Keine Einträge gefunden.</p>"
    out = ['<div class="grid">']
    for it in items[:8]:
        t = _escape_html(fix_encoding(it.get("title",""))); u = _safe_href(str(it.get("url") or ""))
        s = _escape_html(fix_encoding(it.get("summary",""))[:200]); date = str(it.get("published_at") or "")[:10]
        out.append('<div class="card">')
        out.append(f'<h3 style="margin:.2rem 0">{f"<a href=\"{u}\" target=\"_blank\" rel=\"noopener noreferrer\">{t}</a>" if u!="#" else t}</h3>')
        if s: out.append(f"<p>{s}</p>")
        meta = " · ".join([x for x in [date, _escape_html(str(it.get("source",""))[:40])] if x])
        if meta: out.append(f'<div class="meta">{meta}</div>')
        out.append("</div>")
    out.append("</div>"); return "".join(out)

def render_tools_html(items: List[Mapping[str, Any]]) -> str:
    if not items: return "<p>Keine Tools gefunden.</p>"
    out = ["<ul>"]
    for it in items[:10]:
        t = _escape_html(fix_encoding(it.get("title",""))); u = _safe_href(str(it.get("url") or ""))
        cat = _escape_html(str(it.get("category",""))); host = _escape_html(str(it.get("host_cc",""))); badges = render_tags(list(it.get("badges", [])))
        li = f'<li>{f"<a href=\"{u}\" target=\"_blank\" rel=\"noopener noreferrer\">{t}</a>" if u!="#" else f"<b>{t}</b>"}'
        if cat: li += f" <small>({cat})</small>"
        if host: li += f" <small>(Host: {host})</small>"
        if badges: li += f" {badges}"
        out.append(li + "</li>")
    out.append("</ul>"); return "".join(out)

def render_funding_html(items: List[Mapping[str, Any]]) -> str:
    if not items: return "<p>Keine Förderprogramme gefunden.</p>"
    out = ["<ul>"]
    for it in items[:10]:
        t = _escape_html(fix_encoding(it.get("title",""))); u = _safe_href(str(it.get("url") or ""))
        date = str(it.get("published_at") or "")[:10]; badges = render_tags(list(it.get("badges", [])))
        li = f'<li>{f"<a href=\"{u}\" target=\"_blank\" rel=\"noopener noreferrer\">{t}</a>" if u!="#" else f"<b>{t}</b>"}'
        if date: li += f" <small>({ _escape_html(date) })</small>"
        if badges: li += f" {badges}"
        out.append(li + "</li>")
    out.append("</ul>"); return "".join(out)

# ------------------------------------------------------------------------------
# Live-Hook
# ------------------------------------------------------------------------------
def query_live_items(briefing: Mapping[str, Any], lang: str) -> Dict[str, List[Mapping[str, Any]]]:
    try:
        from websearch_utils import query_live_items as _ql  # type: ignore
        return _ql(
            branche=briefing.get("branche"),
            unternehmensgroesse=briefing.get("unternehmensgroesse"),
            leistung=briefing.get("hauptleistung"),
            bundesland=briefing.get("bundesland"),
            lang=lang,
        )
    except Exception as e:
        logger.warning("Live data not available: %s", e)
        return {"news": [], "tools": [], "funding": []}

# ------------------------------------------------------------------------------
# Kontextaufbau & Admin-Payload
# ------------------------------------------------------------------------------
def normalize_briefing_for_context(form_data: Mapping[str, Any]) -> Mapping[str, Any]:
    """
    Lässt Felder unangetastet (keine hartkodierten Defaults),
    normalisiert nur Typen (z.B. 1→0.1 für KPI, falls 0..10).
    """
    def norm(v: Any) -> float:
        try:
            f = float(v)
            return f / 10.0 if f <= 10 else f / 100.0
        except Exception:
            return -1.0

    return {
        "branche": _s(form_data.get("branche")),
        "unternehmensgroesse": _s(form_data.get("unternehmensgroesse")),
        "bundesland": _s(form_data.get("bundesland")),
        "hauptleistung": _s(form_data.get("hauptleistung")),
        "investitionsbudget": _s(form_data.get("investitionsbudget")),
        "ziel": _s(form_data.get("strategische_ziele") or form_data.get("ziel") or ""),
        "digitalisierung": norm(form_data.get("digitalisierungsgrad", -1)),
        "automatisierung": norm(form_data.get("automatisierungsgrad", -1)),
        "compliance": norm(form_data.get("compliance", -1 if form_data.get("compliance") in (None, "") else form_data.get("compliance"))),
        "prozessreife": norm(form_data.get("prozessreife", -1)),
        "innovation": norm(form_data.get("innovation", -1)),
    }

def prepare_admin_payload(raw_form: Mapping[str, Any], normalized_for_context: Mapping[str, Any]) -> Dict[str, Any]:
    """Erzeugt saubere Mail-Anhänge (raw + normalized + missing)."""
    missing = [k for k, v in normalized_for_context.items() if isinstance(v, str) and not v]
    return {
        "attachments": {
            "briefing_raw.json": json.dumps(raw_form, ensure_ascii=False, indent=2),
            "briefing_normalized.json": json.dumps(normalized_for_context, ensure_ascii=False, indent=2),
            "briefing_missing_fields.json": json.dumps({"missing": missing}, ensure_ascii=False, indent=2),
        }
    }

def build_context(form_data: Optional[Mapping[str, Any]], lang: str) -> Dict[str, Any]:
    form_data = form_data or {}
    now = _now_iso()

    nrm = normalize_briefing_for_context(form_data)
    benchmarks = find_best_benchmark(nrm["branche"], nrm["unternehmensgroesse"])

    # KPIs: leere Felder → Benchmark-Wert
    kpis = {
        "digitalisierung": nrm["digitalisierung"] if nrm["digitalisierung"] >= 0 else float(benchmarks.get("digitalisierung", 0.6)),
        "automatisierung": nrm["automatisierung"] if nrm["automatisierung"] >= 0 else float(benchmarks.get("automatisierung", 0.35)),
        "compliance": nrm["compliance"] if nrm["compliance"] >= 0 else float(benchmarks.get("compliance", 0.5)),
        "prozessreife": nrm["prozessreife"] if nrm["prozessreife"] >= 0 else float(benchmarks.get("prozessreife", 0.45)),
        "innovation": nrm["innovation"] if nrm["innovation"] >= 0 else float(benchmarks.get("innovation", 0.55)),
    }
    score = sum(kpis.values()) / max(len(kpis), 1)

    bc = compute_business_case(
        {"investitionsbudget": nrm["investitionsbudget"], "branche": nrm["branche"], "unternehmensgroesse": nrm["unternehmensgroesse"]},
        benchmarks,
    )
    live = query_live_items(
        {"branche": nrm["branche"], "unternehmensgroesse": nrm["unternehmensgroesse"], "bundesland": nrm["bundesland"], "hauptleistung": nrm["hauptleistung"]},
        lang,
    )

    # Progress-HTML
    def bar(label: str, value: float) -> str:
        pct = max(0, min(int(round(value * 100)), 100))
        return f'<div class="bar"><div class="bar__label">{_escape_html(label)}</div><div class="bar__track"><div class="bar__fill" style="width:{pct}%"></div></div><div class="bar__pct">{pct}%</div></div>'

    progress_html = "".join([
        bar("Digitalisierung", kpis["digitalisierung"]),
        bar("Automatisierung", kpis["automatisierung"]),
        bar("Compliance", kpis["compliance"]),
        bar("Prozessreife", kpis["prozessreife"]),
        bar("Innovation", kpis["innovation"]),
    ])

    # Benchmark-Vergleichstabelle (einfach)
    def row(label: str, val: float, bm: float) -> str:
        v = int(round(val * 100)); b = int(round(bm * 100))
        return f"<tr><td>{_escape_html(label)}</td><td>{v}%</td><td>{b}%</td></tr>"

    benchmark_table_html = (
        "<table><thead><tr><th>KPI</th><th>Ihr Wert</th><th>Branchen‑Benchmark</th></tr></thead><tbody>"
        + row("Digitalisierung", kpis["digitalisierung"], float(benchmarks.get("digitalisierung", 0.6)))
        + row("Automatisierung", kpis["automatisierung"], float(benchmarks.get("automatisierung", 0.35)))
        + row("Compliance", kpis["compliance"], float(benchmarks.get("compliance", 0.5)))
        + row("Prozessreife", kpis["prozessreife"], float(benchmarks.get("prozessreife", 0.45)))
        + row("Innovation", kpis["innovation"], float(benchmarks.get("innovation", 0.55)))
        + "</tbody></table>"
    )

    # Quality Badge: konsistent (0–100)
    score_pct = round(score * 100, 1)
    grade = "EXCELLENT" if score_pct >= 80 else "GOOD" if score_pct >= 60 else "FAIR" if score_pct >= 40 else "POOR"

    context: Dict[str, Any] = {
        "meta": {"title": "KI-Status-Report", "date": now, "lang": lang},
        "briefing": {
            "branche": nrm["branche"], "unternehmensgroesse": nrm["unternehmensgroesse"],
            "bundesland": nrm["bundesland"], "hauptleistung": nrm["hauptleistung"],
            "investitionsbudget": nrm["investitionsbudget"], "ziel": nrm["ziel"],
        },
        "kpis": kpis,
        "kpis_progress_html": progress_html,
        "kpis_benchmark_table_html": benchmark_table_html,
        "kpis_benchmark": benchmarks,
        "score_percent": score_pct,
        "business_case": {
            "invest_eur": round(bc.invest_eur, 2),
            "annual_saving_eur": round(bc.annual_saving_eur, 2),
            "payback_months": round(bc.payback_months, 1),
            "roi_year1_pct": round(bc.roi_year1_pct, 1),
        },
        "flags": {
            "search_provider": SEARCH_PROVIDER,
            "case_studies": ENABLE_CASE_STUDIES,
            "regulatory": ENABLE_REGULATORY,
            "eu_host_check": ENABLE_EU_HOST_CHECK,
        },
        "live": {
            "news_html": render_cards_html(live.get("news", [])),
            "tools_html": render_cards_html(live.get("tools", [])),
            "funding_html": render_funding_html(live.get("funding", [])),
            "regulatory_html": render_cards_html(live.get("regulatory", [])),
            "case_studies_html": render_cards_html(live.get("case_studies", [])),
            "vendor_shortlist_html": render_cards_html(live.get("vendor_shortlist", [])),
            "tool_alternatives_html": render_cards_html(live.get("tool_alternatives", [])),
            "stand": now,
        },
        "sections": {},
        "quality_badge": {"grade": grade, "score": f"{score_pct:.1f}/100", "passed_checks": "n/a", "critical_issues": 0},
    }

    for section in CORE_SECTIONS:
        context["sections"][f"{section}_html"] = generate_section(section, context, lang)
    return context

# ------------------------------------------------------------------------------
# Rendering
# ------------------------------------------------------------------------------
def render_with_template(context: Mapping[str, Any], lang: str, template: Optional[str] = None) -> str:
    if Environment is None:
        raise RuntimeError("Jinja2 not available")
    template_name = template or ("pdf_template.html" if lang == "de" else "pdf_template_en.html")
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=select_autoescape(["html", "xml"]))
    tmpl = env.get_template(template_name)
    return tmpl.render(**context)

# ------------------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------------------
def analyze_briefing(form_data: Optional[Mapping[str, Any]] = None, lang: Optional[str] = None,
                     template: Optional[str] = None, **_: Any) -> str:
    form_data = form_data or {}
    language = (lang or form_data.get("lang") or DEFAULT_LANG)[:2]
    context = build_context(form_data, language)
    try:
        return render_with_template(context, language, template)
    except Exception as e:
        logger.error("Template rendering failed: %s", e)
        return f"""<!DOCTYPE html>
<html lang="{html.escape(language)}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>KI-Status-Report</title><style>body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:920px;margin:2rem auto;padding:1rem}}</style></head>
<body><h1>KI-Status-Report</h1><p>Report generation failed. Please check configuration.</p><pre>{html.escape(str(e))}</pre></body></html>"""

def analyze_briefing_enhanced(form_data: Optional[Mapping[str, Any]] = None, lang: Optional[str] = None, **_: Any) -> Dict[str, Any]:
    form_data = form_data or {}
    language = (lang or form_data.get("lang") or DEFAULT_LANG)[:2]
    return build_context(form_data, language)

# Convenience für Admin-Mailer (Backend-Route):
def produce_admin_attachments(form_data: Mapping[str, Any]) -> Dict[str, str]:
    nrm = normalize_briefing_for_context(form_data)
    pkg = prepare_admin_payload(form_data, {"branche": nrm["branche"], "unternehmensgroesse": nrm["unternehmensgroesse"],
                                            "bundesland": nrm["bundesland"], "hauptleistung": nrm["hauptleistung"],
                                            "investitionsbudget": nrm["investitionsbudget"]})
    return pkg["attachments"]

if __name__ == "__main__":
    demo = {"branche": "Beratung", "unternehmensgroesse": "solo", "hauptleistung": "GPT-Auswertung", "bundesland": "BE",
            "investitionsbudget": "bis 10.000 EUR", "digitalisierungsgrad": 7, "automatisierungsgrad": 4}
    html_report = analyze_briefing(demo, lang="de")
    (BASE_DIR / "demo_report.html").write_text(html_report, encoding="utf-8")
    print("Demo-Report geschrieben.")
