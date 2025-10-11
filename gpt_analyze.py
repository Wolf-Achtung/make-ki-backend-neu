# filename: gpt_analyze.py
# -*- coding: utf-8 -*-
"""
KI-Status-Report Analyzer – Gold-Standard+ (hardened)
- Schema-tolerante Normalisierung
- KPI-Scoring + Benchmarks + Δ
- ROI/Payback (≤ 4 Monate baseline via ROI_BASELINE_MONTHS)
- Prompt-Overlays (DE/EN), strikt HTML-Fragmente
- Live-Layer: Tavily + Perplexity (Guards, Retry), optional Hybrid websearch_utils
- Quellen-Badges (Gov/EU/Forschung/Fachpresse/Vendor/NGO/Blog/Web)
- PDF-Template-Füllung inkl. Quellen-Footer (Stand: Datum)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import logging
import os
import re
import time

import httpx

# Optional schema module (tolerant if missing)
try:
    import schema as schema_mod  # type: ignore
except Exception:  # pragma: no cover
    schema_mod = None

# Hybrid search optional
try:
    import websearch_utils  # type: ignore
except Exception:  # pragma: no cover
    websearch_utils = None  # type: ignore

# Source classification
try:
    from .utils_sources import classify_source, filter_and_rank, dedupe_items  # type: ignore
except Exception:  # pragma: no cover
    from utils_sources import classify_source, filter_and_rank, dedupe_items  # type: ignore

# Optional Perplexity adapter
try:
    from perplexity_client import PerplexityClient  # type: ignore
except Exception:  # pragma: no cover
    PerplexityClient = None  # type: ignore

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("gpt_analyze")

def _live_log(provider: str, status: str, latency_ms: float, count: int = 0, **extra: Any) -> None:
    payload: Dict[str, Any] = {
        "evt": "live_search",
        "provider": provider,
        "status": status,
        "latency_ms": int(round(latency_ms)),
        "count": int(count),
    }
    payload.update(extra or {})
    try:
        log.info(json.dumps(payload, ensure_ascii=False))
    except Exception:
        log.info("live_search %s %s %sms %s %s", provider, status, int(round(latency_ms)), count, extra)

# ---------------------------------------------------------------------------
# ENV / Pfade
# ---------------------------------------------------------------------------

BASE_DIR = Path(os.getenv("APP_BASE") or os.getcwd()).resolve()
DATA_DIR = Path(os.getenv("DATA_DIR") or BASE_DIR / "data").resolve()
PROMPTS_DIR = Path(os.getenv("PROMPTS_DIR") or BASE_DIR / "prompts").resolve()
TEMPLATES_DIR = Path(os.getenv("TEMPLATE_DIR") or BASE_DIR / "templates").resolve()

TEMPLATE_DE = os.getenv("TEMPLATE_DE", "pdf_template.html")
TEMPLATE_EN = os.getenv("TEMPLATE_EN", "pdf_template_en.html")
ASSETS_BASE_URL = os.getenv("ASSETS_BASE_URL", "/assets")

# OpenAI for overlays
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_APIKEY") or ""
OPENAI_MODEL = os.getenv("OPENAI_MODEL_DEFAULT", "gpt-4o")
EXEC_SUMMARY_MODEL = os.getenv("EXEC_SUMMARY_MODEL", OPENAI_MODEL)
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "45"))
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "1200"))
GPT_TEMPERATURE = float(os.getenv("GPT_TEMPERATURE", "0.2"))

# Live providers
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
PPLX_API_KEY = os.getenv("PPLX_API_KEY") or os.getenv("PERPLEXITY_API_KEY") or ""
PPLX_MODEL_RAW = (os.getenv("PPLX_MODEL") or "").strip()
PPLX_TIMEOUT = float(os.getenv("PPLX_TIMEOUT", "30.0"))

# ROI baseline
ROI_BASELINE_MONTHS = float(os.getenv("ROI_BASELINE_MONTHS", "4"))

# Live windows
SEARCH_DAYS_NEWS = int(os.getenv("SEARCH_DAYS_NEWS", "30"))
SEARCH_DAYS_TOOLS = int(os.getenv("SEARCH_DAYS_TOOLS", "60"))
SEARCH_DAYS_FUNDING = int(os.getenv("SEARCH_DAYS_FUNDING", "60"))
LIVE_MAX_ITEMS = int(os.getenv("LIVE_MAX_ITEMS", "8"))
HYBRID_LIVE = os.getenv("HYBRID_LIVE", "1").strip().lower() in {"1", "true", "yes"}

# ---------------------------------------------------------------------------
# Template / IO helpers
# ---------------------------------------------------------------------------

def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover
        log.warning("read failed %s: %s", path, exc)
        return ""

def _template(lang: str) -> str:
    fname = TEMPLATE_DE if lang.startswith("de") else TEMPLATE_EN
    p = TEMPLATES_DIR / fname
    if not p.exists():
        p = TEMPLATES_DIR / "pdf_template.html"
    return _read_text(p)

def _minify_html_soft(s: str) -> str:
    if not s:
        return s
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = re.sub(r">\s+<", "><", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()

def _strip_llm(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"```[a-zA-Z0-9]*\s*", "", text).replace("```", "")
    return text.strip()

def _as_fragment(html: str) -> str:
    if not html:
        return ""
    s = html
    s = re.sub(r"(?is)<!doctype.*?>", "", s)
    s = re.sub(r"(?is)<\s*html[^>]*>|</\s*html\s*>", "", s)
    s = re.sub(r"(?is)<\s*head[^>]*>.*?</\s*head\s*>", "", s)
    s = re.sub(r"(?is)<\s*body[^>]*>|</\s*body\s*>", "", s)
    s = re.sub(r"(?is)<\s*style[^>]*>.*?</\s*style\s*>", "", s)
    return s.strip()

# ---------------------------------------------------------------------------
# Locale
# ---------------------------------------------------------------------------

def _fmt_pct(v: float, lang: str) -> str:
    if lang.startswith("de"):
        return f"{v:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".").replace(".0", "") + " %"
    return f"{v:,.1f}%".replace(".0", "")

def _fmt_money_eur(v: float, lang: str) -> str:
    if lang.startswith("de"):
        s = f"{v:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return s + " €"
    return "€" + f"{v:,.0f}"

def _nbsp(s: str) -> str:
    return s.replace(" ", " ")

# ---------------------------------------------------------------------------
# Schema / Normalization
# ---------------------------------------------------------------------------

def _schema_label(field_key: str, value: str, lang: str) -> Optional[str]:
    try:
        if schema_mod:
            return schema_mod.resolve_label(field_key, value, lang)
    except Exception:
        pass
    return None

def _schema_valid(field_key: str, value: str) -> bool:
    try:
        if schema_mod:
            return schema_mod.validate_enum(field_key, value)
    except Exception:
        pass
    return True

BRANCHE_FALLBACK = {
    "marketing": "Marketing & Werbung",
    "beratung": "Beratung",
    "it": "IT & Software",
    "finanzen": "Finanzen & Versicherungen",
    "handel": "Handel & E‑Commerce",
    "bildung": "Bildung",
    "verwaltung": "Verwaltung",
    "gesundheit": "Gesundheit & Pflege",
    "bau": "Bauwesen & Architektur",
    "medien": "Medien & Kreativwirtschaft",
    "industrie": "Industrie & Produktion",
    "logistik": "Transport & Logistik",
}
GROESSE_FALLBACK = {
    "solo": "1 (Solo/Freiberuflich)",
    "team": "2–10 (Kleines Team)",
    "kmu": "11–100 (KMU)",
}

@dataclass
class Normalized:
    branche: str = "beratung"
    branche_label: str = "Beratung"
    unternehmensgroesse: str = "solo"
    unternehmensgroesse_label: str = "1 (Solo/Freiberuflich)"
    bundesland_code: str = "DE"
    hauptleistung: str = "Beratung/Service"
    pull_kpis: Dict[str, Any] = field(default_factory=dict)
    kpi_digitalisierung: int = 60
    kpi_automatisierung: int = 55
    kpi_compliance: int = 60
    kpi_prozessreife: int = 55
    kpi_innovation: int = 60
    raw: Dict[str, Any] = field(default_factory=dict)

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

def _derive_kpis(b: Dict[str, Any]) -> Dict[str, int]:
    digi = _parse_percent_bucket(b.get("digitalisierungsgrad"))
    papier = _parse_percent_bucket(b.get("prozesse_papierlos"))
    digitalisierung = int(round(0.6 * digi + 0.4 * papier))
    auto = 70 if str(b.get("automatisierungsgrad", "")).lower() in ("eher_hoch", "sehr_hoch") else 50
    if isinstance(b.get("ki_einsatz"), list) and b["ki_einsatz"]:
        auto = min(100, auto + 5)
    comp = 40
    if str(b.get("datenschutzbeauftragter", "")).lower() in ("ja", "true", "1"):
        comp += 15
    if str(b.get("folgenabschaetzung", "")).lower() == "ja":
        comp += 10
    if str(b.get("loeschregeln", "")).lower() == "ja":
        comp += 10
    if str(b.get("meldewege", "")).lower() in ("ja", "teilweise"):
        comp += 5
    if str(b.get("governance", "")).lower() == "ja":
        comp += 10
    comp = max(0, min(100, comp))
    proz = 30 + (10 if str(b.get("governance", "")).lower() == "ja" else 0) + int(0.2 * papier)
    proz = max(0, min(100, proz))
    know = 70 if str(b.get("ki_knowhow", "")).lower() == "fortgeschritten" else 55
    inn = int(0.6 * know + 0.4 * 65)
    return {
        "digitalisierung": digitalisierung,
        "automatisierung": auto,
        "compliance": comp,
        "prozessreife": proz,
        "innovation": inn,
    }

def normalize_briefing(raw: Dict[str, Any], lang: str = "de") -> Normalized:
    b: Dict[str, Any] = dict(raw or {})
    if isinstance(raw, dict) and isinstance(raw.get("answers"), dict):
        b = {**raw, **raw["answers"]}

    branche_code = str(b.get("branche") or "beratung").lower()
    if not _schema_valid("branche", branche_code):
        branche_code = "beratung"
    branche_label = _schema_label("branche", branche_code, lang) or BRANCHE_FALLBACK.get(branche_code, branche_code.title())

    size_code = str(b.get("unternehmensgroesse") or "solo").lower()
    if not _schema_valid("unternehmensgroesse", size_code):
        size_code = "solo"
    size_label = _schema_label("unternehmensgroesse", size_code, lang) or GROESSE_FALLBACK.get(size_code, size_code)

    bundesland_code = str(b.get("bundesland") or b.get("bundesland_code") or "DE").upper()
    hl = b.get("hauptleistung") or b.get("produkt") or "Beratung/Service"

    top_use = str(b.get("usecase_priority") or "")
    if not top_use and isinstance(b.get("ki_usecases"), list) and b["ki_usecases"]:
        top_use = str(b["ki_usecases"][0])

    pull = {
        "umsatzziel": b.get("umsatzziel") or b.get("jahresumsatz") or "",
        "top_use_case": top_use,
        "zeitbudget": b.get("zeitbudget") or "",
    }

    k = _derive_kpis(b)

    return Normalized(
        branche=branche_code,
        branche_label=branche_label,
        unternehmensgroesse=size_code,
        unternehmensgroesse_label=size_label,
        bundesland_code=bundesland_code,
        hauptleistung=hl,
        pull_kpis=pull,
        kpi_digitalisierung=k["digitalisierung"],
        kpi_automatisierung=k["automatisierung"],
        kpi_compliance=k["compliance"],
        kpi_prozessreife=k["prozessreife"],
        kpi_innovation=k["innovation"],
        raw=b,
    )

# ---------------------------------------------------------------------------
# Benchmarks & Scoring
# ---------------------------------------------------------------------------

def _kpi_key_norm(k: str) -> str:
    s = k.strip().lower()
    mapping = {
        "digitalisierung": "digitalisierung",
        "automatisierung": "automatisierung",
        "automation": "automatisierung",
        "compliance": "compliance",
        "prozessreife": "prozessreife",
        "prozesse": "prozessreife",
        "innovation": "innovation",
    }
    return mapping.get(s, s)

def _bench_file_patterns(branche: str, groesse: str) -> List[str]:
    return [
        f"benchmarks_{branche}_{groesse}",
        f"benchmarks_{branche}",
        f"benchmarks_{groesse}",
        "benchmarks_global",
        "benchmarks_default",
        "benchmarks",
    ]

def _load_benchmarks(branche: str, groesse: str) -> Dict[str, float]:
    for base in _bench_file_patterns(branche, groesse):
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
    return {k: 60.0 for k in ["digitalisierung", "automatisierung", "compliance", "prozessreife", "innovation"]}

@dataclass
class ScorePack:
    total: int
    badge: str
    kpis: Dict[str, Dict[str, float]]
    weights: Dict[str, float]
    benchmarks: Dict[str, float]

def _badge(total: float) -> str:
    if total >= 85:
        return "EXCELLENT"
    if total >= 70:
        return "GOOD"
    if total >= 55:
        return "FAIR"
    return "BASIC"

def compute_scores(n: Normalized) -> ScorePack:
    weights = {k: 0.2 for k in ("digitalisierung", "automatisierung", "compliance", "prozessreife", "innovation")}
    bm = _load_benchmarks(n.branche, n.unternehmensgroesse)
    vals = {
        "digitalisierung": n.kpi_digitalisierung,
        "automatisierung": n.kpi_automatisierung,
        "compliance": n.kpi_compliance,
        "prozessreife": n.kpi_prozessreife,
        "innovation": n.kpi_innovation,
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

# ---------------------------------------------------------------------------
# Business Case (ROI)
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# LLM Overlays (OpenAI)
# ---------------------------------------------------------------------------

def _openai_chat(messages: List[Dict[str, str]], model: Optional[str] = None, max_tokens: Optional[int] = None) -> str:
    if not OPENAI_API_KEY:
        return ""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": model or OPENAI_MODEL,
        "messages": messages,
        "max_tokens": int(max_tokens or OPENAI_MAX_TOKENS),
        "temperature": GPT_TEMPERATURE,
        "top_p": 0.95,
    }
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
    system = "Du bist präzise und risikobewusst. Antworte als sauberes HTML-Fragment (ohne <html>/<head>/<body>)."
    if not lang.startswith("de"):
        system = "You are precise and risk-aware. Answer as clean HTML fragment (no <html>/<head>/<body>)."
    user = (
        prompt
        .replace("{{BRIEFING_JSON}}", json.dumps(ctx.get("briefing", {}), ensure_ascii=False))
        .replace("{{SCORING_JSON}}", json.dumps(ctx.get("scoring", {}), ensure_ascii=False))
        .replace("{{BENCHMARKS_JSON}}", json.dumps(ctx.get("benchmarks", {}), ensure_ascii=False))
        .replace("{{TOOLS_JSON}}", json.dumps(ctx.get("tools", []), ensure_ascii=False))
        .replace("{{FUNDING_JSON}}", json.dumps(ctx.get("funding", []), ensure_ascii=False))
        .replace("{{BUSINESS_JSON}}", json.dumps(ctx.get("business", {}), ensure_ascii=False))
    )
    out = _openai_chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        model=EXEC_SUMMARY_MODEL if name == "executive_summary" else OPENAI_MODEL,
    )
    return _minify_html_soft(_as_fragment(out))

# ---------------------------------------------------------------------------
# Live Layer (Tavily + Perplexity)
# ---------------------------------------------------------------------------

def _pplx_model_effective() -> Optional[str]:
    name = (PPLX_MODEL_RAW or "").strip()
    if not name or name.lower() in {"auto", "best", "default", "none"}:
        return None
    if "online" in name.lower():
        log.warning("PPLX_MODEL '%s' legacy – switching to Best-Mode (no model).", name)
        return None
    return name

def _tavily(query: str, max_results: int, days: int) -> List[Dict[str, Any]]:
    if not TAVILY_API_KEY:
        return []
    headers = {"Authorization": f"Bearer {TAVILY_API_KEY}", "Content-Type": "application/json", "Accept": "application/json"}
    payload = {"query": query, "search_depth": "advanced", "max_results": max_results, "include_answer": False, "time_range": f"{days}d"}
    t0 = time.monotonic()
    try:
        with httpx.Client(timeout=30) as cli:
            r = cli.post("https://api.tavily.com/search", headers=headers, json=payload)
            if r.status_code == 400:
                _live_log("tavily", "400_bad_request_retry_minimal", (time.monotonic()-t0)*1000, 0)
                r = cli.post("https://api.tavily.com/search", headers=headers, json={"query": query})
            r.raise_for_status()
            data = r.json() or {}
            items = []
            for it in (data.get("results") or [])[:max_results]:
                url = it.get("url")
                items.append({"title": it.get("title") or url, "url": url, "domain": (url or "").split("/")[2] if "://" in (url or "") else "", "date": (it.get("published_date") or "")[:10]})
            _live_log("tavily", "ok", (time.monotonic()-t0)*1000, len(items))
            return items
    except httpx.HTTPStatusError as exc:
        _live_log("tavily", f"http_{exc.response.status_code}", (time.monotonic()-t0)*1000, 0, body=str(exc.response.text)[:300])
        return []
    except Exception as exc:  # pragma: no cover
        _live_log("tavily", f"error_{type(exc).__name__}", (time.monotonic()-t0)*1000, 0, error=str(exc))
        return []

def _perplexity_http(query: str, max_items: int, category_hint: Optional[str] = None) -> List[Dict[str, Any]]:
    if not PPLX_API_KEY:
        return []
    headers = {"Authorization": f"Bearer {PPLX_API_KEY}", "Content-Type": "application/json", "Accept": "application/json"}
    system = "Be precise and return ONLY valid JSON matching the provided schema."
    user = f"Find recent, reliable web sources (title, url, date). Return strictly as JSON. Category hint: {category_hint or 'mixed'}. Query: {query}"
    schema = {"type": "object", "properties": {"items": {"type": "array","items": {"type": "object","properties": {"title": {"type": "string"},"url": {"type": "string"},"date": {"type": "string"}},"required": ["title", "url"],"additionalProperties": True}}}, "required": ["items"], "additionalProperties": False}

    base_body = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "temperature": 0.1, "max_tokens": 900, "response_format": {"type": "json_schema", "json_schema": {"schema": schema}}}
    model = _pplx_model_effective()
    body = dict(base_body, **({"model": model} if model else {}))

    url = "https://api.perplexity.ai/chat/completions"
    t0 = time.monotonic()
    try:
        with httpx.Client(timeout=PPLX_TIMEOUT) as cli:
            r = cli.post(url, headers=headers, json=body)
            if r.status_code == 400 and "invalid_model" in (r.text or "").lower():
                _live_log("perplexity", "400_invalid_model_retry_auto", (time.monotonic()-t0)*1000, 0, model_sent=model)
                body.pop("model", None)
                r = cli.post(url, headers=headers, json=body)
            r.raise_for_status()
            data = r.json() or {}
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "{}")
            parsed = json.loads(content) if isinstance(content, str) else content
            items = []
            for it in (parsed.get("items") or [])[:max_items]:
                url_i = it.get("url")
                items.append({"title": it.get("title") or url_i, "url": url_i, "domain": (url_i or "").split("/")[2] if "://" in (url_i or "") else "", "date": (it.get("date") or "")[:10]})
            _live_log("perplexity", "ok", (time.monotonic()-t0)*1000, len(items), model_used=model or "auto")
            return items
    except httpx.HTTPStatusError as exc:
        _live_log("perplexity", f"http_{exc.response.status_code}", (time.monotonic()-t0)*1000, 0, body=str(exc.response.text)[:300])
        return []
    except Exception as exc:  # pragma: no cover
        _live_log("perplexity", f"error_{type(exc).__name__}", (time.monotonic()-t0)*1000, 0, error=str(exc))
        return []

def _perplexity(query: str, max_items: int) -> List[Dict[str, Any]]:
    if PerplexityClient:
        t0 = time.monotonic()
        try:
            client = PerplexityClient()
            schema = {"title": "string", "url": "string", "date": "string"}
            items = client.search_json(query, schema=schema, max_items=max_items) or []
            out = []
            for it in items[:max_items]:
                url_i = it.get("url")
                out.append({"title": it.get("title") or url_i, "url": url_i, "domain": (url_i or "").split("/")[2] if "://" in (url_i or "") else "", "date": (it.get("date") or "")[:10]})
            _live_log("perplexity_adapter", "ok", (time.monotonic()-t0)*1000, len(out))
            return out
        except Exception as exc:  # pragma: no cover
            _live_log("perplexity_adapter", f"error_{type(exc).__name__}", (time.monotonic()-t0)*1000, 0, error=str(exc))
    return _perplexity_http(query, max_items, category_hint="mixed")

def _merge_rank(*arrays: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    def key(it: Dict[str, Any]) -> str:
        u = (it.get("url") or "").split("?")[0].strip().lower()
        return u or (it.get("title") or "").strip().lower()
    def parse_dt(s: str) -> datetime:
        try:
            return datetime.fromisoformat(s.replace("Z", "")[:19])
        except Exception:
            return datetime.min
    seen, out = set(), []
    for arr in arrays:
        for it in arr:
            k = key(it)
            if not k or k in seen:
                continue
            seen.add(k)
            out.append(it)
    out.sort(key=lambda x: parse_dt(str(x.get("date") or "")), reverse=True)
    return out[:limit]

def _live_topic(topic: str, n: Normalized, max_results: int) -> List[Dict[str, Any]]:
    branche = n.branche_label
    region = n.bundesland_code
    if topic == "news":
        q = f"Aktuelle KI-News in der Branche {branche} (letzte {SEARCH_DAYS_NEWS} Tage). Titel, Domain, URL, Datum."
        internal = _merge_rank(_perplexity(q, max_results), _tavily(q, max_results, days=SEARCH_DAYS_NEWS), limit=max_results)
    elif topic == "tools":
        q = f"Relevante KI-Tools/Anbieter für {branche}, Größe {n.unternehmensgroesse_label}. Titel, Domain, URL, Datum."
        internal = _merge_rank(_perplexity(q, max_results), _tavily(q, max_results, days=SEARCH_DAYS_TOOLS), limit=max_results)
    elif topic == "funding":
        q = f"Förderprogramme in {region} (Digitalisierung/KI) – offen oder laufend, Fristen innerhalb {SEARCH_DAYS_FUNDING} Tagen. Titel, Domain, URL, Datum."
        internal = _merge_rank(_perplexity(q, max_results), _tavily(q, max_results, days=SEARCH_DAYS_FUNDING), limit=max_results)
    else:
        return []

    if HYBRID_LIVE and websearch_utils:
        try:  # pragma: no cover
            res = websearch_utils.hybrid_live_search(q, short_days=SEARCH_DAYS_NEWS, long_days=SEARCH_DAYS_TOOLS, max_results=max_results)
            items = (res.get("items") or []) + internal
        except Exception as exc:
            log.warning("hybrid_live_search failed: %s", exc)
            items = internal
    else:
        items = internal

    return filter_and_rank(items)[:max_results]

# ---------------------------------------------------------------------------
# HTML rendering & glue
# ---------------------------------------------------------------------------

def _kpi_bars_html(score: ScorePack) -> str:
    order = ["digitalisierung", "automatisierung", "compliance", "prozessreife", "innovation"]
    labels = {"digitalisierung": "Digitalisierung", "automatisierung": "Automatisierung", "compliance": "Compliance", "prozessreife": "Prozessreife", "innovation": "Innovation"}
    rows = []
    for k in order:
        v = score.kpis[k]["value"]
        m = score.kpis[k]["benchmark"]
        d = score.kpis[k]["delta"]
        rows.append(
            f"<div class='bar'><div class='label'>{labels[k]}</div>"
            f"<div class='bar__track'><div class='bar__fill' style='width:{max(0,min(100,int(round(v))))}%;'></div>"
            f"<div class='bar__median' style='left:{max(0,min(100,int(round(m))))}%;'></div></div>"
            f"<div class='bar__delta'>{'+' if d>=0 else ''}{int(round(d))} pp</div></div>"
        )
    return "<div class='kpi'>" + "".join(rows) + "</div>"

def _benchmark_table_html(score: ScorePack) -> str:
    head = "<table class='bm'><thead><tr><th>KPI</th><th>Ihr Wert</th><th>Branchen‑Benchmark</th><th>Δ (pp)</th></tr></thead><tbody>"
    labels = {"digitalisierung": "Digitalisierung", "automatisierung": "Automatisierung", "compliance": "Compliance", "prozessreife": "Prozessreife", "innovation": "Innovation"}
    rows = []
    for k, lab in labels.items():
        v = score.kpis[k]["value"]
        m = score.kpis[k]["benchmark"]
        d = score.kpis[k]["delta"]
        rows.append(f"<tr><td>{lab}</td><td>{int(round(v))}%</td><td>{int(round(m))}%</td><td>{'+' if d>=0 else ''}{int(round(d))}</td></tr>")
    return head + "".join(rows) + "</tbody></table>"

def _profile_html(n: Normalized) -> str:
    pl = n.pull_kpis or {}
    pills = []
    if pl.get("umsatzziel"): pills.append(f"<span class='pill'>Umsatzziel: {pl['umsatzziel']}</span>")
    if pl.get("top_use_case"): pills.append(f"<span class='pill'>Top‑Use‑Case: {pl['top_use_case']}</span>")
    if pl.get("zeitbudget"): pills.append(f"<span class='pill'>Zeitbudget: {pl['zeitbudget']}</span>")
    pills_html = " ".join(pills) if pills else "<span class='muted'>—</span>"
    return ("<div class='card'><h2>Unternehmensprofil & Ziele</h2>"
            f"<p><span class='hl'>Hauptleistung:</span> {n.hauptleistung} "
            f"<span class='muted'>&middot; Branche:</span> {n.branche_label} "
            f"<span class='muted'>&middot; Größe:</span> {n.unternehmensgroesse_label}</p>"
            f"<p>{pills_html}</p></div>")

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
        extra = ""
        if berlin_badge and any(d in (url or "") for d in ("berlin.de", "ibb.de")):
            extra = " <span class='flag-berlin'>Land Berlin</span>"
        lis.append(f"<li><a href='{url}'>{title}</a> – <span class='muted'>{dom} {when}</span> {_badge_html(url, dom)}{extra}</li>")
    return "<ul class='source-list'>" + "".join(lis) + "</ul>"

def _sources_footer_html(news: List[Dict[str, Any]], tools: List[Dict[str, Any]], funding: List[Dict[str, Any]], lang: str) -> str:
    def _mk(items, title):
        if not items:
            return f"<div class='muted'>Keine {title}.</div>" if lang.startswith("de") else f"<div class='muted'>No {title}.</div>"
        lis = []
        seen = set()
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
    return ("<div class='grid'>"
            + "<div><h4>News</h4>" + _mk(news, "News") + "</div>"
            + "<div><h4>Tools</h4>" + _mk(tools, "Tools") + "</div>"
            + "<div><h4>" + ("Förderungen" if lang.startswith("de") else "Funding") + "</h4>" + _mk(funding, "Förderungen") + "</div>"
            + "</div>")

def _business_case_block(case: BusinessCase, lang: str) -> str:
    payback = f"{case.payback_months:.1f}"
    roi = _fmt_pct(case.roi_year1_pct, lang)
    invest = _fmt_money_eur(case.invest_eur, lang)
    save = _fmt_money_eur(case.save_year_eur, lang)
    label_invest = "Invest" if lang.startswith("de") else "Invest"
    label_save = "Ersparnis/Jahr" if lang.startswith("de") else "Savings/year"
    label_payback = "Payback" if not lang.startswith("de") else "Payback"
    label_roi = "ROI Jahr 1" if lang.startswith("de") else "ROI year 1"
    return ("<div class='card'><h2>ROI & Payback</h2>"
            f"<p><b>{label_invest}:</b> ~{_nbsp(invest)} | <b>{label_save}:</b> ~{_nbsp(save)} | "
            f"<b>{label_payback}:</b> ~{payback} Monate | <b>{label_roi}:</b> ~{roi}</p>"
            "<div class='footnotes'>Formel: Invest/Monate × 12; konservative Annahmen.</div></div>")

def _fill_placeholders(html: str, n: Normalized) -> str:
    if not html:
        return html
    kpis = {"digitalisierung": n.kpi_digitalisierung,"automatisierung": n.kpi_automatisierung,"compliance": n.kpi_compliance,"prozessreife": n.kpi_prozessreife,"innovation": n.kpi_innovation}
    deltas = sorted(((k, abs(v - 60.0)) for k, v in kpis.items()), key=lambda x: x[1], reverse=True)
    map_de = {"digitalisierung": "Digitalisierung","automatisierung": "Automatisierung","compliance": "Compliance","prozessreife": "Prozessreife","innovation": "Innovation"}
    top2 = " & ".join([map_de.get(d[0], d[0].title()) for d in deltas[:2]]) or "Digitalisierung & Compliance"
    repl = {"[Branche]": n.branche_label,"[Größe]": n.unternehmensgroesse_label,"[Hauptleistung]": n.hauptleistung,"[wichtigste Δ‑Hebel]": top2,"{{ hauptleistung }}": n.hauptleistung,"{branche_label}": n.branche_label,"{unternehmensgroesse_label}": n.unternehmensgroesse_label,"{hauptleistung}": n.hauptleistung}
    for k, v in repl.items():
        html = html.replace(k, v)
    html = re.sub(r"\[[^\]]+\]", "", html)
    html = re.sub(r"\{\{[^}]+\}\}", "", html)
    return html

def build_html_report(raw: Dict[str, Any], lang: str = "de") -> Dict[str, Any]:
    n = normalize_briefing(raw, lang=lang)
    score = compute_scores(n)
    case = business_case(n)

    # Live
    live_news = _live_topic("news", n, LIVE_MAX_ITEMS)
    live_tools = _live_topic("tools", n, LIVE_MAX_ITEMS)
    live_funding = _live_topic("funding", n, max(LIVE_MAX_ITEMS, 10))

    tools_items = filter_and_rank(live_tools)[:LIVE_MAX_ITEMS]
    funding_items = filter_and_rank(live_funding)[:max(LIVE_MAX_ITEMS, 10)]

    ctx = {
        "briefing": {"branche": n.branche, "branche_label": n.branche_label,"unternehmensgroesse": n.unternehmensgroesse, "unternehmensgroesse_label": n.unternehmensgroesse_label,"bundesland_code": n.bundesland_code, "hauptleistung": n.hauptleistung, "pull_kpis": n.pull_kpis},
        "scoring": {"score_total": score.total, "badge": score.badge, "kpis": score.kpis, "weights": score.weights},
        "benchmarks": score.benchmarks,
        "tools": tools_items,
        "funding": funding_items,
        "business": case.__dict__,
    }

    # LLM sections
    sec = lambda n_: render_overlay(n_, lang, ctx) or ""
    exec_llm = sec("executive_summary")
    quick = sec("quick_wins")
    roadmap = sec("roadmap")
    risks = sec("risks")
    compliance = sec("compliance")
    business_block = sec("business")
    recs = sec("recommendations")
    game = sec("gamechanger")
    vision = sec("vision")
    persona = sec("persona")
    praxis = sec("praxisbeispiel")
    coach = sec("coach")
    digest = sec("doc_digest")

    tools_block = sec("tools") or _list_html(tools_items, "Keine passenden Tools gefunden." if lang.startswith("de") else "No matching tools.")
    funding_block = sec("foerderprogramme") or _list_html(funding_items, "Keine aktuellen Einträge." if lang.startswith("de") else "No current items.", berlin_badge=True)

    tpl = _template(lang)
    report_date = os.getenv("REPORT_DATE_OVERRIDE") or date.today().isoformat()

    html = (tpl.replace("{{LANG}}", "de" if lang.startswith("de") else "en")
           .replace("{{ASSETS_BASE}}", ASSETS_BASE_URL)
           .replace("{{REPORT_DATE}}", report_date)
           .replace("{{STAND_DATUM}}", report_date)
           .replace("{{SCORE_PERCENT}}", f"{score.total}%")
           .replace("{{SCORE_BADGE}}", score.badge)
           .replace("{{KPI_BARS_HTML}}", _kpi_bars_html(score))
           .replace("{{BENCHMARK_TABLE_HTML}}", _benchmark_table_html(score))
           .replace("{{BUSINESS_CASE_HTML}}", _business_case_block(case, lang))
           .replace("{{PROFILE_HTML}}", _profile_html(n))
           .replace("{{EXEC_SUMMARY_HTML}}", exec_llm)
           .replace("{{QUICK_WINS_HTML}}", quick)
           .replace("{{ROADMAP_HTML}}", roadmap)
           .replace("{{RISKS_HTML}}", risks)
           .replace("{{COMPLIANCE_HTML}}", compliance)
           .replace("{{NEWS_HTML}}", _list_html(live_news, "Keine aktuellen News (30–60 Tage geprüft)." if lang.startswith("de") else "No recent news (30–60 days)."))
           .replace("{{TOOLS_HTML}}", tools_block)
           .replace("{{FUNDING_HTML}}", funding_block)
           .replace("{{RECOMMENDATIONS_BLOCK}}", f"<section class='card'><h2>Recommendations</h2>{recs}<div class='meta'>{'Stand' if lang.startswith('de') else 'As of'}: {report_date}</div></section>")
           .replace("{{GAMECHANGER_BLOCK}}", f"<section class='card'><h2>Gamechanger</h2>{game}<div class='meta'>{'Stand' if lang.startswith('de') else 'As of'}: {report_date}</div></section>")
           .replace("{{VISION_BLOCK}}", f"<section class='card'><h2>Vision</h2>{vision}<div class='meta'>{'Stand' if lang.startswith('de') else 'As of'}: {report_date}</div></section>")
           .replace("{{PERSONA_BLOCK}}", f"<section class='card'><h2>Persona</h2>{persona}<div class='meta'>{'Stand' if lang.startswith('de') else 'As of'}: {report_date}</div></section>")
           .replace("{{PRAXIS_BLOCK}}", f"<section class='card'><h2>Praxisbeispiel</h2>{praxis}<div class='meta'>{'Stand' if lang.startswith('de') else 'As of'}: {report_date}</div></section>")
           .replace("{{COACH_BLOCK}}", f"<section class='card'><h2>Coach</h2>{coach}<div class='meta'>{'Stand' if lang.startswith('de') else 'As of'}: {report_date}</div></section>")
           .replace("{{DOC_DIGEST_BLOCK}}", digest or "")
           .replace("{{SOURCES_FOOTER_HTML}}", _sources_footer_html(live_news, tools_items, funding_items, lang))
    )
    html = _fill_placeholders(html, n)
    return {"html": html, "meta": {"score": score.total, "badge": score.badge, "date": report_date,"branche": n.branche,"size": n.unternehmensgroesse,"bundesland": n.bundesland_code,"kpis": score.kpis,"benchmarks": score.benchmarks,"live_counts": {"news": len(live_news), "tools": len(tools_items), "funding": len(funding_items)}}, "normalized": n.__dict__, "raw": n.raw}

# Public API
def analyze_briefing(raw: Dict[str, Any], lang: str = "de") -> str:
    return build_html_report(raw, lang)["html"]

def build_report(raw: Dict[str, Any], lang: str = "de") -> Dict[str, Any]:
    return build_html_report(raw, lang)

def produce_admin_attachments(raw: Dict[str, Any], lang: str = "de") -> Dict[str, str]:
    try:
        norm = normalize_briefing(raw, lang=lang)
    except Exception as exc:  # pragma: no cover
        norm = Normalized(raw={"_error": f"normalize failed: {exc}", "_raw_keys": list((raw or {}).keys())})
    required = ["branche","branche_label","unternehmensgroesse","unternehmensgroesse_label","bundesland_code","hauptleistung","kpi_digitalisierung","kpi_automatisierung","kpi_compliance","kpi_prozessreife","kpi_innovation"]
    def _is_missing(v) -> bool:
        if v is None: return True
        if isinstance(v, str): return v.strip() == ""
        if isinstance(v, (list, dict, tuple, set)): return len(v) == 0
        return False
    missing = sorted([k for k in required if _is_missing(getattr(norm, k, None))])
    payload_raw = raw if isinstance(raw, dict) else {"_note": "raw not dict"}
    return {"briefing_raw.json": json.dumps(payload_raw, ensure_ascii=False, indent=2),"briefing_normalized.json": json.dumps(norm.__dict__, ensure_ascii=False, indent=2),"briefing_missing_fields.json": json.dumps({"missing": missing}, ensure_ascii=False, indent=2)}
