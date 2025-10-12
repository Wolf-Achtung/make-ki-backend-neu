# filename: gpt_analyze.py
# -*- coding: utf-8 -*-
"""
KI-Status-Report Analyzer – Best of all worlds (Gold-Standard+)

Vereint:
- Deine aktuelle, robuste Pipeline (Normalisierung, KPI-Scoring + Δ, ROI/Payback,
  Prompt-Overlays, Hybrid-Live via websearch_utils, Quellen-Badges, Admin-JSONs).
- Sanitizer & Fallbacks aus der früheren "Gold"-Variante (Listen/Zahlen raus, Vision/Praxis-Fallback).
- Optionale CSV-Fallbacks für Tools/Förderungen, wenn Live-Layer leer bleibt.

Kompatibel mit:
- pdf_template.html / pdf_template_en.html (Token-Replace-Platzhalter)
- prompts/<lang>/*.md (Overlays liefern HTML-Fragmente)
- utils_sources.classify_source / filter_and_rank
- content_loader.load_content_sections (4 Säulen, Legal, 10-20-70)

Env (Auszug):
  LOG_LEVEL=INFO|DEBUG
  TEMPLATE_DE=pdf_template.html
  TEMPLATE_EN=pdf_template_en.html
  PROMPTS_DIR=prompts
  TEMPLATE_DIR=templates
  ROI_BASELINE_MONTHS=4
  HYBRID_LIVE=1
  SEARCH_DAYS_NEWS=30  SEARCH_DAYS_TOOLS=60  SEARCH_DAYS_FUNDING=60
  LIVE_MAX_ITEMS=8
  CONTENT_SECTIONS=pillars,legal,formula
  CONTENT_DIR=content
  OPENAI_API_KEY=...  OPENAI_MODEL_DEFAULT=gpt-4o  EXEC_SUMMARY_MODEL=gpt-4o
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import json
import logging
import os
import re

import httpx

# -------- optional imports (robust) -----------------------------------------

try:
    import websearch_utils  # Hybrid-Live (Perplexity+Tavily) + Backoff/Guards
except Exception:  # pragma: no cover
    websearch_utils = None  # type: ignore

try:
    from utils_sources import classify_source, filter_and_rank
except Exception:  # pragma: no cover
    def classify_source(url: str, domain: Optional[str] = None):
        return ("web", "Quelle", "badge--muted", 50)
    def filter_and_rank(items, **kw):
        return list(items)

try:
    from content_loader import load_content_sections
except Exception:  # pragma: no cover
    def load_content_sections(lang: str = "de") -> Dict[str, Dict[str, str]]:
        return {"pillars": {"html": "", "source": ""}, "legal": {"html": "", "source": ""}, "formula": {"html": "", "source": ""}}

try:
    from live_logger import log_event as _emit  # strukturierte Logs (optional)
except Exception:  # pragma: no cover
    def _emit(provider: str, model: Optional[str], status: str, latency_ms: int, count: int = 0, **kw: Any) -> None:
        pass

# -------- Logging/Paths/Env -------------------------------------------------

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("gpt_analyze")

BASE_DIR = Path(os.getenv("APP_BASE") or os.getcwd()).resolve()
DATA_DIR = Path(os.getenv("DATA_DIR") or BASE_DIR / "data").resolve()
PROMPTS_DIR = Path(os.getenv("PROMPTS_DIR") or BASE_DIR / "prompts").resolve()
TEMPLATES_DIR = Path(os.getenv("TEMPLATE_DIR") or BASE_DIR / "templates").resolve()

TEMPLATE_DE = os.getenv("TEMPLATE_DE", "pdf_template.html")
TEMPLATE_EN = os.getenv("TEMPLATE_EN", "pdf_template_en.html")
ASSETS_BASE_URL = os.getenv("ASSETS_BASE_URL", os.getenv("ASSETS_BASE", "/assets"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or ""
OPENAI_MODEL = os.getenv("OPENAI_MODEL_DEFAULT", "gpt-4o")
EXEC_SUMMARY_MODEL = os.getenv("EXEC_SUMMARY_MODEL", OPENAI_MODEL)
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "45"))
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "1200"))
GPT_TEMPERATURE = float(os.getenv("GPT_TEMPERATURE", "0.2"))

SEARCH_DAYS_NEWS = int(os.getenv("SEARCH_DAYS_NEWS", "30"))
SEARCH_DAYS_TOOLS = int(os.getenv("SEARCH_DAYS_TOOLS", "60"))
SEARCH_DAYS_FUNDING = int(os.getenv("SEARCH_DAYS_FUNDING", "60"))
LIVE_MAX_ITEMS = int(os.getenv("LIVE_MAX_ITEMS", "8"))
HYBRID_LIVE = os.getenv("HYBRID_LIVE", "1").strip().lower() in {"1", "true", "yes"}

ROI_BASELINE_MONTHS = float(os.getenv("ROI_BASELINE_MONTHS", "4"))
CONTENT_SECTIONS_ENABLED = os.getenv("CONTENT_SECTIONS", "pillars,legal,formula")

# -------- Utilities ----------------------------------------------------------

def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""

def _template(lang: str) -> str:
    p = TEMPLATES_DIR / (TEMPLATE_DE if lang.startswith("de") else TEMPLATE_EN)
    if not p.exists():
        p = TEMPLATES_DIR / "pdf_template.html"
    return _read_text(p)

def _strip_llm(text: str) -> str:
    if not text:
        return ""
    t = re.sub(r"```[a-zA-Z0-9]*\s*", "", text).replace("```", "")
    return t.strip()

def _as_fragment(html: str) -> str:
    """Entfernt <html>/<head>/<body>/<style> und Doctype."""
    if not html:
        return ""
    s = re.sub(r"(?is)<!doctype.*?>", "", html)
    s = re.sub(r"(?is)<\s*html[^>]*>|</\s*html\s*>", "", s)
    s = re.sub(r"(?is)<\s*head[^>]*>.*?</\s*head\s*>", "", s)
    s = re.sub(r"(?is)<\s*body[^>]*>|</\s*body\s*>", "", s)
    s = re.sub(r"(?is)<\s*style[^>]*>.*?</\s*style\s*>", "", s)
    return s.strip()

# --- Sanitizer aus „Gold“-Variante (angepasst) -------------------------------

_NUMBER_PAT = re.compile(r"(?:\b\d{1,3}(?:[\.,]\d{1,3})*(?:%|[kKmMbB])?\b)|(?:\b\d+ ?(?:%|EUR|€|USD)\b)")
_BULLET_PAT = re.compile(r"^\s*[-–—•\*]\s*", re.MULTILINE)

def _strip_lists_and_numbers(raw: str) -> str:
    """Entfernt Listen-Markierungen sowie nackte Zahlen/Einheiten aus generierten Texten."""
    if not raw:
        return raw
    t = str(raw).replace("\r", "")
    # Listen → Fließtext
    t = _BULLET_PAT.sub("", t)
    t = t.replace("</li>", " ").replace("<li>", "").replace("<ul>", "").replace("</ul>", "")
    t = t.replace("<ol>", "").replace("</ol>", "")
    # Zahlen/Einheiten entfernen (für narrative Sektionen)
    t = _NUMBER_PAT.sub("", t)
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r",\s*,", ", ", t)
    return t.strip()

# -------- Locale helpers -----------------------------------------------------

def _fmt_pct(v: float, lang: str) -> str:
    if lang.startswith("de"):
        s = f"{v:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return s.replace(",0", "") + " %"
    return f"{v:,.1f}%".replace(".0", "")

# -------- Normalisierung -----------------------------------------------------

def _parse_percent_bucket(val: Any) -> int:
    s = str(val or "").lower()
    if "81" in s: return 90
    if "61" in s: return 70
    if "41" in s: return 50
    if "21" in s: return 30
    if "0" in s:  return 10
    try:
        return int(max(0, min(100, float(s))))
    except Exception:
        return 50

@dataclass
class Normalized:
    branche: str = "beratung"
    branche_label: str = "Beratung"
    unternehmensgroesse: str = "solo"
    unternehmensgroesse_label: str = "Solo/Freiberuflich"
    bundesland_code: str = "DE"
    hauptleistung: str = "Beratung/Service"
    pull_kpis: Dict[str, Any] = field(default_factory=dict)

    kpi_digitalisierung: int = 60
    kpi_automatisierung: int = 55
    kpi_compliance: int = 60
    kpi_prozessreife: int = 55
    kpi_innovation: int = 60

    raw: Dict[str, Any] = field(default_factory=dict)

def normalize_briefing(raw: Dict[str, Any], lang: str = "de") -> Normalized:
    b: Dict[str, Any] = dict(raw or {})
    if isinstance(raw, dict) and isinstance(raw.get("answers"), dict):
        b = {**raw, **raw["answers"]}

    branche_code = str(b.get("branche") or b.get("branche_code") or "beratung").lower()
    branche_label = str(b.get("branche_label") or b.get("branche") or "Beratung")
    size_code = str(b.get("unternehmensgroesse") or b.get("size") or "solo").lower()
    size_label = str(b.get("unternehmensgroesse_label") or "Solo/Freiberuflich")
    bundesland_code = str(b.get("bundesland_code") or b.get("bundesland") or "DE").upper()
    hl = b.get("hauptleistung") or b.get("produkt") or "Beratung/Service"

    # KPIs aus Fragebogenfeldern ableiten (tolerant)
    digi = _parse_percent_bucket(b.get("digitalisierungsgrad"))
    papier = _parse_percent_bucket(b.get("prozesse_papierlos"))
    digitalisierung = int(round(0.6 * digi + 0.4 * papier))

    auto = 50
    if str(b.get("automatisierungsgrad", "")).lower() in ("eher_hoch", "sehr_hoch"): auto = 70
    if isinstance(b.get("ki_einsatz"), list) and b["ki_einsatz"]: auto = min(100, auto + 5)

    comp = 40
    if str(b.get("datenschutzbeauftragter", "")).lower() in ("ja", "true", "1"): comp += 15
    if str(b.get("folgenabschaetzung", "")).lower() == "ja": comp += 10
    if str(b.get("loeschregeln", "")).lower() == "ja": comp += 10
    if str(b.get("meldewege", "")).lower() in ("ja", "teilweise"): comp += 5
    if str(b.get("governance", "")).lower() == "ja": comp += 10
    comp = max(0, min(100, comp))

    proz = 30 + (10 if str(b.get("governance", "")).lower() == "ja" else 0) + int(0.2 * papier)
    proz = max(0, min(100, proz))

    know = 70 if str(b.get("ki_knowhow", "")).lower() == "fortgeschritten" else 55
    inn = int(0.6 * know + 0.4 * 65)

    pull = {
        "umsatzziel": b.get("umsatzziel") or b.get("jahresumsatz") or "",
        "top_use_case": b.get("usecase_priority") or (b.get("ki_usecases") or [""])[0] if b.get("ki_usecases") else "",
        "zeitbudget": b.get("zeitbudget") or "",
    }

    return Normalized(
        branche=branche_code, branche_label=branche_label,
        unternehmensgroesse=size_code, unternehmensgroesse_label=size_label,
        bundesland_code=bundesland_code, hauptleistung=hl,
        pull_kpis=pull,
        kpi_digitalisierung=digitalisierung,
        kpi_automatisierung=auto,
        kpi_compliance=comp,
        kpi_prozessreife=proz,
        kpi_innovation=inn,
        raw=b
    )

# -------- Benchmarks/Scoring -------------------------------------------------

def _kpi_key_norm(k: str) -> str:
    s = k.strip().lower()
    mapping = {
        "digitalisierung": "digitalisierung", "automatisierung": "automatisierung", "automation": "automatisierung",
        "compliance": "compliance", "prozessreife": "prozessreife", "prozesse": "prozessreife",
        "innovation": "innovation"
    }
    return mapping.get(s, s)

def _load_benchmarks(branche: str, groesse: str) -> Dict[str, float]:
    def patterns():
        yield f"benchmarks_{branche}_{groesse}"
        yield f"benchmarks_{branche}"
        yield f"benchmarks_{groesse}"
        yield "benchmarks_global"
        yield "benchmarks_default"
        yield "benchmarks"
    for base in patterns():
        for ext in (".json", ".csv"):
            p = DATA_DIR / f"{base}{ext}"
            if not p.exists(): 
                continue
            try:
                out: Dict[str, float] = {}
                if ext == ".json":
                    obj = json.loads(_read_text(p) or "{}")
                    for k, v in (obj or {}).items():
                        try:
                            out[_kpi_key_norm(k)] = float(str(v).replace("%", "").strip())
                        except Exception:
                            pass
                else:
                    import csv as _csv
                    with p.open("r", encoding="utf-8") as f:
                        for row in _csv.DictReader(f):
                            k = _kpi_key_norm((row.get("kpi") or row.get("name") or "").strip())
                            v = row.get("value") or row.get("pct") or row.get("percent") or ""
                            try:
                                out[k] = float(str(v).replace("%", "").strip())
                            except Exception:
                                pass
                if out:
                    return out
            except Exception as exc:  # pragma: no cover
                log.warning("Benchmark import failed (%s): %s", p, exc)
    # Default, wenn nichts gefunden
    return {k: 60.0 for k in ["digitalisierung", "automatisierung", "compliance", "prozessreife", "innovation"]}

@dataclass
class ScorePack:
    total: int
    badge: str
    kpis: Dict[str, Dict[str, float]]
    weights: Dict[str, float]
    benchmarks: Dict[str, float]

def _badge(total: float) -> str:
    if total >= 85: return "EXCELLENT"
    if total >= 70: return "GOOD"
    if total >= 55: return "FAIR"
    return "BASIC"

def compute_scores(n: Normalized) -> ScorePack:
    weights = {k: 0.2 for k in ("digitalisierung", "automatisierung", "compliance", "prozessreife", "innovation")}
    bm = _load_benchmarks(n.branche, n.unternehmensgroesse)
    vals = {
        "digitalisierung": n.kpi_digitalisierung, "automatisierung": n.kpi_automatisierung,
        "compliance": n.kpi_compliance, "prozessreife": n.kpi_prozessreife,
        "innovation": n.kpi_innovation
    }
    kpis: Dict[str, Dict[str, float]] = {}
    total = 0.0
    for k, v in vals.items():
        m = float(bm.get(k, 60.0))
        d = float(v) - m
        kpis[k] = {"value": float(v), "benchmark": m, "delta": d}
        total += weights[k] * float(v)
    t = int(round(total))
    return ScorePack(total=t, badge=_badge(t), kpis=kpis, weights=weights, benchmarks=bm)

# -------- Business Case (ROI) -----------------------------------------------

@dataclass
class BusinessCase:
    invest_eur: float
    save_year_eur: float
    payback_months: float
    roi_year1_pct: float

def _parse_invest(val: Any, default: float = 6000.0) -> float:
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val or "")
    parts = re.split(r"[^\d]", s)
    nums = [float(p) for p in parts if p.isdigit()]
    if len(nums) >= 2:
        return (nums[0] + nums[1]) / 2.0
    if len(nums) == 1:
        return nums[0]
    return default

def business_case(n: Normalized) -> BusinessCase:
    invest = _parse_invest(n.raw.get("investitionsbudget"), 6000.0)
    monthly = invest / max(1.0, ROI_BASELINE_MONTHS)
    save_year = monthly * 12.0
    payback_m = invest / max(1.0, monthly)
    roi_y1 = (save_year - invest) / invest * 100.0
    return BusinessCase(round(invest, 2), round(save_year, 2), round(payback_m, 1), round(roi_y1, 1))

# -------- OpenAI Overlay -----------------------------------------------------

def _openai_chat(messages: List[Dict[str, str]], model: Optional[str] = None, max_tokens: Optional[int] = None) -> str:
    if not OPENAI_API_KEY:
        return ""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": model or OPENAI_MODEL, "messages": messages,
               "max_tokens": int(max_tokens or OPENAI_MAX_TOKENS),
               "temperature": GPT_TEMPERATURE, "top_p": 0.95}
    try:
        with httpx.Client(timeout=OPENAI_TIMEOUT) as cli:
            r = cli.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            return _strip_llm(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
    except Exception as exc:  # pragma: no cover
        log.warning("LLM call failed: %s", exc)
        return ""

def _load_prompt(lang: str, name: str) -> str:
    cand = [
        PROMPTS_DIR / lang / f"{name}_{lang}.md",
        PROMPTS_DIR / lang / f"{name}.md",
        PROMPTS_DIR / f"{name}_{lang}.md",
        PROMPTS_DIR / f"{name}.md",
    ]
    for p in cand:
        if p.exists():
            log.info("Loaded prompt: %s", p.relative_to(PROMPTS_DIR))
            return _read_text(p)
    log.info("Prompt missing for '%s' (%s) – skipping section", name, lang)
    return ""

def render_overlay(name: str, lang: str, ctx: Dict[str, Any]) -> str:
    prompt = _load_prompt(lang, name)
    if not prompt:
        return ""
    system = "Antworte als sauberes HTML-Fragment (ohne <html>/<head>/<body>), präzise & risikobewusst." if lang.startswith("de") \
        else "Answer as clean HTML fragment (no <html>/<head>/<body>), precise & risk-aware."
    user = (prompt
            .replace("{{BRIEFING_JSON}}", json.dumps(ctx.get("briefing", {}), ensure_ascii=False))
            .replace("{{SCORING_JSON}}", json.dumps(ctx.get("scoring", {}), ensure_ascii=False))
            .replace("{{BENCHMARKS_JSON}}", json.dumps(ctx.get("benchmarks", {}), ensure_ascii=False))
            .replace("{{TOOLS_JSON}}", json.dumps(ctx.get("tools", []), ensure_ascii=False))
            .replace("{{FUNDING_JSON}}", json.dumps(ctx.get("funding", []), ensure_ascii=False))
            .replace("{{BUSINESS_JSON}}", json.dumps(ctx.get("business", {}), ensure_ascii=False)))
    out = _openai_chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
                       model=EXEC_SUMMARY_MODEL if name == "executive_summary" else OPENAI_MODEL)
    return _as_fragment(_strip_llm(out))

# -------- HTML‑Bausteine -----------------------------------------------------

def _badge_html(url: str, domain: str) -> str:
    cat, label, badge, _ = classify_source(url, domain)
    return f"<span class='badge {badge}'>{label}</span>"

def _list_html(items: List[Dict[str, Any]], empty_msg: str, berlin_badge: bool = False) -> str:
    if not items:
        return f"<div class='muted'>{empty_msg}</div>"
    lis = []
    for it in items:
        title = it.get("title") or it.get("name") or it.get("url")
        url = it.get("url") or "#"
        dom = it.get("domain") or (url.split('/')[2] if '://' in url else "")
        when = (it.get("date") or "")[:10]
        extra = " <span class='flag-berlin'>Land Berlin</span>" if (berlin_badge and any(d in (url or "") for d in ("berlin.de", "ibb.de"))) else ""
        lis.append(f"<li><a href='{url}'>{title}</a> – <span class='muted'>{dom} {when}</span> {_badge_html(url, dom)}{extra}</li>")
    return "<ul class='source-list'>" + "".join(lis) + "</ul>"

def _kpi_bars_html(score: ScorePack) -> str:
    order = ["digitalisierung", "automatisierung", "compliance", "prozessreife", "innovation"]
    labels = {"digitalisierung": "Digitalisierung", "automatisierung": "Automatisierung", "compliance": "Compliance",
              "prozessreife": "Prozessreife", "innovation": "Innovation"}
    rows = []
    for k in order:
        v = score.kpis[k]["value"]; m = score.kpis[k]["benchmark"]; d = score.kpis[k]["delta"]
        rows.append(
            "<div class='bar'>"
            f"<div class='label'>{labels[k]}</div>"
            "<div class='bar__track'>"
            f"<div class='bar__fill' style='width:{max(0, min(100, int(round(v))))}%;'></div>"
            f"<div class='bar__median' style='left:{max(0, min(100, int(round(m))))}%;'></div>"
            "</div>"
            f"<div class='bar__delta'>{'+' if d >= 0 else ''}{int(round(d))} pp</div>"
            "</div>"
        )
    return "<div class='kpi'>" + "".join(rows) + "</div>"

def _benchmark_table_html(score: ScorePack) -> str:
    labels = {"digitalisierung": "Digitalisierung", "automatisierung": "Automatisierung", "compliance": "Compliance",
              "prozessreife": "Prozessreife", "innovation": "Innovation"}
    head = "<table class='bm'><thead><tr><th>KPI</th><th>Ihr Wert</th><th>Branchen‑Benchmark</th><th>Δ (pp)</th></tr></thead><tbody>"
    rows = []
    for k, lab in labels.items():
        v = score.kpis[k]["value"]; m = score.kpis[k]["benchmark"]; d = score.kpis[k]["delta"]
        rows.append(f"<tr><td>{lab}</td><td>{int(round(v))}%</td><td>{int(round(m))}%</td><td>{'+' if d >= 0 else ''}{int(round(d))}</td></tr>")
    return head + "".join(rows) + "</tbody></table>"

def _sources_footer_html(news: List[Dict[str, Any]], tools: List[Dict[str, Any]], funding: List[Dict[str, Any]], lang: str) -> str:
    def _mk(items, title):
        if not items:
            return f"<div class='muted'>Keine {title}.</div>" if lang.startswith("de") else f"<div class='muted'>No {title}.</div>"
        lis = []; seen = set()
        for it in items:
            url = (it.get("url") or "").split("#")[0]
            if not url or url in seen:
                continue
            seen.add(url)
            title_ = it.get("title") or it.get("name") or it.get("url")
            dom = it.get("domain") or (url.split('/')[2] if '://' in url else "")
            when = (it.get("date") or "")[:10]
            lis.append(f"<li><a href='{url}'>{title_}</a> – <span class='muted'>{dom} {when}</span> {_badge_html(url, dom)}</li>")
        return "<ul class='source-list'>" + "".join(lis) + "</ul>"
    return "<div class='grid'>" \
           + "<div><h4>News</h4>" + _mk(news, "News") + "</div>" \
           + "<div><h4>Tools</h4>" + _mk(tools, "Tools") + "</div>" \
           + "<div><h4>" + ("Förderungen" if lang.startswith("de") else "Funding") + "</h4>" + _mk(funding, "Förderungen") + "</div>" \
           + "</div>"

# -------- Lokale CSV-Fallbacks (optional) -----------------------------------

def _read_csv_rows(path: Path) -> List[Dict[str, str]]:
    try:
        import csv
        with path.open("r", encoding="utf-8") as f:
            rd = csv.DictReader(f)
            return [{k.strip(): (v or "").strip() for k, v in r.items()} for r in rd]
    except Exception:
        return []

def _augment_from_csv(n: Normalized, tools: List[Dict[str, Any]], funding: List[Dict[str, Any]], max_items: int = 8) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Füllt Tools/Förderungen mit lokalen CSVs auf, falls Live-Layer nichts liefert."""
    try:
        if len(tools) < max_items:
            p = DATA_DIR / "tools.csv"
            rows = _read_csv_rows(p) if p.exists() else []
            for r in rows:
                nm = r.get("name") or r.get("Tool") or r.get("Tool-Name")
                url = r.get("link") or r.get("url")
                if not (nm and url):
                    continue
                tools.append({"title": nm, "url": url, "domain": (url.split("/")[2] if "://" in url else ""), "date": "", "provider": "local"})
                if len(tools) >= max_items:
                    break
        if len(funding) < max_items:
            p = DATA_DIR / "foerderprogramme.csv"
            rows = _read_csv_rows(p) if p.exists() else []
            for r in rows:
                nm = r.get("name") or r.get("programm") or r.get("Program")
                url = r.get("link") or r.get("url")
                if not (nm and url):
                    continue
                funding.append({"title": nm, "url": url, "domain": (url.split("/")[2] if "://" in url else ""), "date": "", "provider": "local"})
                if len(funding) >= max_items:
                    break
    except Exception:
        pass
    return tools, funding

# -------- Report-Bau ---------------------------------------------------------

def build_report(raw: Dict[str, Any], lang: str = "de") -> Dict[str, Any]:
    # Boot-Snapshot (hilfreich im Log)
    _emit("analyzer", None, "boot", 0, 0, extra={
        "hybrid_live": os.getenv("HYBRID_LIVE", "1"),
        "pplx_model_effective": (os.getenv("PPLX_MODEL") or "").strip() or "auto",
        "search_windows": {"news": SEARCH_DAYS_NEWS, "tools": SEARCH_DAYS_TOOLS, "funding": SEARCH_DAYS_FUNDING},
    })

    n = normalize_briefing(raw, lang=lang)
    score = compute_scores(n)
    case = business_case(n)

    # Live-Layer (Best Practices: kurze, spezifische Queries; mehrteilig)
    news: List[Dict[str, Any]] = []
    tools: List[Dict[str, Any]] = []
    funding: List[Dict[str, Any]] = []

    if websearch_utils:
        try:
            q_news = f"Aktuelle KI-News {n.branche_label} {n.bundesland_code} letzte {SEARCH_DAYS_NEWS} Tage"
            q_tools = f"KI-Tools/Anbieter für {n.branche_label} {n.unternehmensgroesse_label} DSGVO"
            q_fund = f"Förderprogramme Digitalisierung/KI {n.bundesland_code} Fristen {SEARCH_DAYS_FUNDING} Tage (ZIM, BMBF)"
            news = websearch_utils.perplexity_search_multi(q_news, max_results=LIVE_MAX_ITEMS)
            tools = websearch_utils.perplexity_search_multi(q_tools, max_results=LIVE_MAX_ITEMS)
            funding = websearch_utils.perplexity_search_multi(q_fund, max_results=max(LIVE_MAX_ITEMS, 10))
        except Exception as exc:  # pragma: no cover
            log.warning("hybrid_live failed: %s", exc)

    # Fallback mit lokalen CSVs, falls Live leer
    tools, funding = _augment_from_csv(n, tools, funding, max_items=max(LIVE_MAX_ITEMS, 8))

    news = filter_and_rank(news)[:LIVE_MAX_ITEMS]
    tools = filter_and_rank(tools)[:LIVE_MAX_ITEMS]
    funding = filter_and_rank(funding)[:max(LIVE_MAX_ITEMS, 10)]

    ctx = {
        "briefing": {
            "branche": n.branche, "branche_label": n.branche_label,
            "unternehmensgroesse": n.unternehmensgroesse, "unternehmensgroesse_label": n.unternehmensgroesse_label,
            "bundesland_code": n.bundesland_code, "hauptleistung": n.hauptleistung, "pull_kpis": n.pull_kpis
        },
        "scoring": {"score_total": score.total, "badge": score.badge, "kpis": score.kpis, "weights": score.weights},
        "benchmarks": score.benchmarks,
        "tools": tools, "funding": funding,
        "business": {"invest_eur": case.invest_eur, "save_year_eur": case.save_year_eur,
                     "payback_months": case.payback_months, "roi_year1_pct": case.roi_year1_pct},
    }

    # Overlays (DE/EN) – strikt HTML-Fragmente
    def sec(name: str) -> str:
        return _as_fragment(render_overlay(name, lang, ctx) or "")

    exec_llm = sec("executive_summary")
    quick = sec("quick_wins")
    roadmap = sec("roadmap")
    risks = sec("risks")
    compliance = sec("compliance")
    business_block = sec("business")
    recs = sec("recommendations")
    game = sec("gamechanger")
    vision = sec("vision") or ("<p><b>Vision:</b> Ein schlankes KI‑Serviceportal …</p>" if lang.startswith("de")
                               else "<p><b>Vision:</b> A lean AI service portal …</p>")
    praxis = sec("praxisbeispiel") or ""
    persona = sec("persona")
    coach = sec("coach")
    digest = sec("doc_digest")

    # Content‑Guides (4 Säulen, Legal, 10‑20‑70)
    content = load_content_sections(lang)
    want = [s.strip() for s in (CONTENT_SECTIONS_ENABLED or "").split(",") if s.strip()]
    pillars_html = content["pillars"]["html"] if "pillars" in want else ""
    legal_html = content["legal"]["html"] if "legal" in want else ""
    formula_html = content["formula"]["html"] if "formula" in want else ""

    tpl = _template(lang)
    report_date = os.getenv("REPORT_DATE_OVERRIDE") or date.today().isoformat()

    html = (tpl.replace("{{LANG}}", "de" if lang.startswith("de") else "en")
            .replace("{{ASSETS_BASE}}", ASSETS_BASE_URL)
            .replace("{{REPORT_DATE}}", report_date)
            .replace("{{EXEC_SUMMARY_HTML}}", exec_llm)
            .replace("{{KPI_BARS_HTML}}", _kpi_bars_html(score))
            .replace("{{BENCHMARK_TABLE_HTML}}", _benchmark_table_html(score))
            .replace("{{BUSINESS_CASE_HTML}}", business_block or "")
            .replace("{{NEWS_HTML}}", _list_html(news, "Keine aktuellen News (30–60 Tage überprüft)." if lang.startswith("de") else "No recent news (30–60 days)."))
            .replace("{{TOOLS_HTML}}", _list_html(tools, "Keine passenden Tools gefunden." if lang.startswith("de") else "No matching tools."))
            .replace("{{FUNDING_HTML}}", _list_html(funding, "Keine aktuellen Einträge." if lang.startswith("de") else "No current items.", berlin_badge=True))
            .replace("{{SOURCES_FOOTER_HTML}}", _sources_footer_html(news, tools, funding, lang))
            .replace("{{CONTENT_PILLARS_HTML}}", pillars_html)
            .replace("{{CONTENT_LEGAL_HTML}}", legal_html)
            .replace("{{CONTENT_FORMULA_HTML}}", formula_html)
            .replace("{{PROFILE_HTML}}", "")  # optionaler Block – dein Template nutzt eigene Kopfzeile
            .replace("{{QUICK_WINS_HTML}}", quick)
            .replace("{{ROADMAP_HTML}}", roadmap)
            .replace("{{RISKS_HTML}}", risks)
            .replace("{{COMPLIANCE_HTML}}", compliance)
            .replace("{{RECOMMENDATIONS_HTML}}", recs)
            .replace("{{GAMECHANGER_HTML}}", game)
            .replace("{{VISION_HTML}}", vision)
            .replace("{{PRAXISBEISPIEL_HTML}}", praxis)
            .replace("{{PERSONA_HTML}}", persona)
            .replace("{{COACH_HTML}}", coach)
            .replace("{{DOC_DIGEST_HTML}}", digest)
            )

    return {
        "html": html,
        "meta": {
            "score": score.total, "badge": score.badge, "date": report_date,
            "branche": n.branche, "size": n.unternehmensgroesse, "bundesland": n.bundesland_code,
            "kpis": score.kpis, "benchmarks": score.benchmarks,
            "live_counts": {"news": len(news), "tools": len(tools), "funding": len(funding)}
        },
        "normalized": n.__dict__,
        "raw": n.raw
    }

# Öffentliche API für main.py / PDF-Service
def analyze_briefing(raw: Dict[str, Any], lang: str = "de") -> str:
    return build_report(raw, lang)["html"]

def produce_admin_attachments(raw: Dict[str, Any], lang: str = "de") -> Dict[str, str]:
    """Erzeugt Admin-Anhänge: raw / normalized / missing."""
    try:
        norm = normalize_briefing(raw, lang=lang)
    except Exception as exc:  # pragma: no cover
        norm = Normalized(raw={"_error": f"normalize failed: {exc}", "_raw_keys": list((raw or {}).keys())})
    required = ["branche", "branche_label", "unternehmensgroesse", "unternehmensgroesse_label",
                "bundesland_code", "hauptleistung", "kpi_digitalisierung", "kpi_automatisierung",
                "kpi_compliance", "kpi_prozessreife", "kpi_innovation"]

    def _is_missing(v) -> bool:
        if v is None: return True
        if isinstance(v, str): return v.strip() == ""
        if isinstance(v, (list, dict, tuple, set)): return len(v) == 0
        return False

    missing = sorted([k for k in required if _is_missing(getattr(norm, k, None))])
    payload_raw = raw if isinstance(raw, dict) else {"_note": "raw not dict"}

    return {
        "briefing_raw.json": json.dumps(payload_raw, ensure_ascii=False, indent=2),
        "briefing_normalized.json": json.dumps(norm.__dict__, ensure_ascii=False, indent=2),
        "briefing_missing_fields.json": json.dumps({"missing": missing}, ensure_ascii=False, indent=2)
    }
# end of file
