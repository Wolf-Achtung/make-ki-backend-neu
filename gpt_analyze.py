# filename: gpt_analyze.py
# -*- coding: utf-8 -*-
"""
KI-Status-Report Analyzer – Gold-Standard+ (hardened)
- Normalisierung & Scoring (Benchmarks + Δ)
- ROI/Payback (≤ 4 Monate baseline)
- Prompt-Overlays (DE/EN) – saubere HTML-Fragmente (OpenAI/Anthropic, Auto-Fallback)
- Live-Layer (Tavily + Perplexity) mit Dedupe, Ranking, Badges
- Funding/Tools Baseline (CSV) + Live-Erweiterung, Filter by bundesland_code
- Branchen-Snippets (data/industry_snippets.json)
- Tool-Kompatibilitätsmatrix (Self-Hosting, EU-Residency, Audit-Logs)
- Content-Blocks aus /content (wenn vorhanden)
- Templates (einspaltig) – Sparklines/Badges; „Stand: Datum“
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional
from pathlib import Path
from functools import lru_cache
import json, re, os, logging, httpx

# Optional hybrid search
try:
    import websearch_utils  # type: ignore
except Exception:
    websearch_utils = None  # type: ignore

# Source helpers
try:
    from .utils_sources import classify_source, filter_and_rank  # type: ignore
except Exception:
    from utils_sources import classify_source, filter_and_rank  # type: ignore

# Optional event emitter
try:
    from .live_logger import log_event as _emit  # type: ignore
except Exception:
    def _emit(provider: str, model: Optional[str], status: str, latency_ms: int, count: int = 0, **kw: Any) -> None:
        pass

LOG_LEVEL = os.getenv("LOG_LEVEL","INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("gpt_analyze")

BASE_DIR = Path(os.getenv("APP_BASE") or os.getcwd()).resolve()
DATA_DIR = Path(os.getenv("DATA_DIR") or BASE_DIR / "data").resolve()
PROMPTS_DIR = Path(os.getenv("PROMPTS_DIR") or BASE_DIR / "prompts").resolve()
TEMPLATES_DIR = Path(os.getenv("TEMPLATE_DIR") or BASE_DIR / "templates").resolve()
CONTENT_DIR = Path(os.getenv("CONTENT_DIR") or BASE_DIR / "content").resolve()

TEMPLATE_DE = os.getenv("TEMPLATE_DE", "pdf_template.html")
TEMPLATE_EN = os.getenv("TEMPLATE_EN", "pdf_template_en.html")
ASSETS_BASE_URL = os.getenv("ASSETS_BASE_URL", "/assets")

# Models / Providers
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY","")
OPENAI_MODEL = os.getenv("OPENAI_MODEL_DEFAULT","gpt-4o")
EXEC_SUMMARY_MODEL = os.getenv("EXEC_SUMMARY_MODEL", OPENAI_MODEL)
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT","45"))
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS","1000"))

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY","")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL","claude-3-5-sonnet-20241022")
ANTHROPIC_TIMEOUT = float(os.getenv("ANTHROPIC_TIMEOUT","45"))
OVERLAY_PROVIDER = os.getenv("OVERLAY_PROVIDER","auto").lower()  # auto|anthropic|openai

GPT_TEMPERATURE = float(os.getenv("GPT_TEMPERATURE","0.2"))

# Live windows
SEARCH_DAYS_NEWS = int(os.getenv("SEARCH_DAYS_NEWS","30"))
SEARCH_DAYS_TOOLS = int(os.getenv("SEARCH_DAYS_TOOLS","60"))
SEARCH_DAYS_FUNDING = int(os.getenv("SEARCH_DAYS_FUNDING","60"))
LIVE_MAX_ITEMS = int(os.getenv("LIVE_MAX_ITEMS","8"))
HYBRID_LIVE = os.getenv("HYBRID_LIVE","1").strip().lower() in {"1","true","yes"}

ROI_BASELINE_MONTHS = float(os.getenv("ROI_BASELINE_MONTHS","4"))

__all__ = [
    # public API used by the backend
    "analyze_briefing", "analyze_briefing_enhanced",
    "build_report", "build_html_report",
    "produce_admin_attachments",
    # helpers (kept for compatibility)
    "normalize_briefing", "compute_scores", "business_case"
]

# ---------------- Basic helpers ----------------
def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception as exc:
        log.warning("read failed %s: %s", path, exc)
        return ""

@lru_cache(maxsize=32)
def _template_cached(lang_key: str) -> str:
    if lang_key == "de":
        p = TEMPLATES_DIR / TEMPLATE_DE
    else:
        p = TEMPLATES_DIR / TEMPLATE_EN
    if not p.exists():
        p = TEMPLATES_DIR / "pdf_template.html"
    return _read_text(p)

def _template(lang: str) -> str:
    return _template_cached("de" if lang.lower().startswith("de") else "en")

@lru_cache(maxsize=128)
def _load_prompt_cached(lang: str, name: str) -> str:
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
    text = re.sub(r"```[a-zA-Z0-9]*\s*", "", text).replace("```","")
    return text.strip()

def _fmt_pct(v: float, lang: str) -> str:
    if lang.startswith("de"):
        return (f"{v:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".").replace(",0", "")) + " %"
    return f"{v:,.1f}%".replace(".0","")

# ---------------- Schema / Normalization ----------------
def _parse_percent_bucket(val: Any) -> int:
    s = str(val or "").lower()
    if "81" in s: return 90
    if "61" in s: return 70
    if "41" in s: return 50
    if "21" in s: return 30
    if "0"  in s: return 10
    try:
        return int(max(0,min(100,float(s))))
    except Exception:
        return 50

@dataclass
class Normalized:
    branche: str = "beratung"
    branche_label: str = "Beratung"
    unternehmensgroesse: str = "solo"
    unternehmensgroesse_label: str = "solo"
    bundesland_code: str = "DE"
    hauptleistung: str = "Beratung"
    pull_kpis: Dict[str, Any] = field(default_factory=dict)
    kpi_digitalisierung: int = 60
    kpi_automatisierung: int = 55
    kpi_compliance: int = 60
    kpi_prozessreife: int = 55
    kpi_innovation: int = 60
    raw: Dict[str,Any] = field(default_factory=dict)

def normalize_briefing(raw: Dict[str,Any], lang: str = "de") -> Normalized:
    b: Dict[str,Any] = dict(raw or {})
    if isinstance(raw, dict) and isinstance(raw.get("answers"), dict):
        b = {**raw, **raw["answers"]}

    branche_code = str(b.get("branche") or b.get("branche_code") or "beratung").lower()
    branche_label = str(b.get("branche_label") or b.get("branche") or "Beratung")
    size_code = str(b.get("unternehmensgroesse") or b.get("size") or "solo").lower()
    size_label = str(b.get("unternehmensgroesse_label") or "solo")
    bundesland_code = str(b.get("bundesland_code") or b.get("bundesland") or "DE").upper()
    hl = b.get("hauptleistung") or b.get("produkt") or "Beratung"

    def _derive_kpis(bb: Dict[str,Any]) -> Dict[str,int]:
        digi = _parse_percent_bucket(bb.get("digitalisierungsgrad"))
        papier = _parse_percent_bucket(bb.get("prozesse_papierlos"))
        digitalisierung = int(round(0.6*digi + 0.4*papier))
        auto = 70 if str(bb.get("automatisierungsgrad","")).lower() in ("eher_hoch","sehr_hoch") else 50
        if isinstance(bb.get("ki_einsatz"), list) and bb["ki_einsatz"]:
            auto = min(100, auto + 5)
        comp = 40
        if str(bb.get("datenschutzbeauftragter","")).lower() in ("ja","true","1"): comp += 15
        if str(bb.get("folgenabschaetzung","")).lower() == "ja": comp += 10
        if str(bb.get("loeschregeln","")).lower() == "ja": comp += 10
        if str(bb.get("meldewege","")).lower() in ("ja","teilweise"): comp += 5
        if str(bb.get("governance","")).lower() == "ja": comp += 10
        comp = max(0,min(100,comp))
        proz = 30 + (10 if str(bb.get("governance","")).lower()=="ja" else 0) + int(0.2*papier)
        proz = max(0,min(100,proz))
        know = 70 if str(bb.get("ki_knowhow","")).lower()=="fortgeschritten" else 55
        inn = int(0.6*know + 0.4*65)
        return {"digitalisierung": digitalisierung,"automatisierung": auto,"compliance": comp,"prozessreife": proz,"innovation": inn}

    k = _derive_kpis(b)
    pull = {
        "umsatzziel": b.get("umsatzziel") or b.get("jahresumsatz") or "",
        "top_use_case": b.get("usecase_priority") or (b.get("ki_usecases") or [""])[0] if b.get("ki_usecases") else "",
        "zeitbudget": b.get("zeitbudget") or "",
    }

    return Normalized(
        branche=branche_code, branche_label=branche_label,
        unternehmensgroesse=size_code, unternehmensgroesse_label=size_label,
        bundesland_code=bundesland_code, hauptleistung=hl, pull_kpis=pull,
        kpi_digitalisierung=k["digitalisierung"], kpi_automatisierung=k["automatisierung"],
        kpi_compliance=k["compliance"], kpi_prozessreife=k["prozessreife"], kpi_innovation=k["innovation"],
        raw=b
    )

# ---------------- Benchmarks & Scoring ----------------
def _kpi_key_norm(k: str) -> str:
    s = k.strip().lower()
    mapping = {"digitalisierung":"digitalisierung","automatisierung":"automatisierung","automation":"automatisierung",
               "compliance":"compliance","prozessreife":"prozessreife","prozesse":"prozessreife","innovation":"innovation"}
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
        for ext in (".json",".csv"):
            p = DATA_DIR / f"{base}{ext}"
            if not p.exists(): continue
            try:
                out: Dict[str,float] = {}
                if ext == ".json":
                    obj = json.loads(_read_text(p) or "{}")
                    for k,v in (obj or {}).items():
                        try: out[_kpi_key_norm(k)] = float(str(v).replace("%","").strip())
                        except Exception: pass
                else:
                    import csv as _csv
                    with p.open("r", encoding="utf-8") as f:
                        for row in _csv.DictReader(f):
                            k = _kpi_key_norm((row.get("kpi") or row.get("name") or "").strip())
                            v = row.get("value") or row.get("pct") or row.get("percent") or ""
                            try: out[k] = float(str(v).replace("%","").strip())
                            except Exception: pass
                if out: return out
            except Exception as exc:
                log.warning("Benchmark import failed (%s): %s", p, exc)
    return {k: 60.0 for k in ["digitalisierung","automatisierung","compliance","prozessreife","innovation"]}

@dataclass
class ScorePack:
    total: int
    badge: str
    kpis: Dict[str, Dict[str,float]]
    weights: Dict[str, float]
    benchmarks: Dict[str, float]

def _badge(total: float) -> str:
    if total >= 85: return "EXCELLENT"
    if total >= 70: return "GOOD"
    if total >= 55: return "FAIR"
    return "BASIC"

def compute_scores(n: Normalized) -> ScorePack:
    weights = {k:0.2 for k in ("digitalisierung","automatisierung","compliance","prozessreife","innovation")}
    bm = _load_benchmarks(n.branche, n.unternehmensgroesse)
    vals = {"digitalisierung": n.kpi_digitalisierung,"automatisierung": n.kpi_automatisierung,"compliance": n.kpi_compliance,"prozessreife": n.kpi_prozessreife,"innovation": n.kpi_innovation}
    kpis: Dict[str, Dict[str,float]] = {}
    total = 0.0
    for k, v in vals.items():
        m = float(bm.get(k, 60.0)); d = float(v) - m
        kpis[k] = {"value": float(v), "benchmark": m, "delta": d}
        total += weights[k] * float(v)
    t = int(round(total))
    return ScorePack(total=t, badge=_badge(t), kpis=kpis, weights=weights, benchmarks=bm)

# ---------------- Business Case ----------------
@dataclass
class BusinessCase:
    invest_eur: float
    save_year_eur: float
    payback_months: float
    roi_year1_pct: float

def _parse_invest(val: Any, default: float = 6000.0) -> float:
    if isinstance(val,(int,float)): return float(val)
    s = str(val or "")
    import re as _re
    parts = _re.split(r"[^\d]", s)
    nums = [float(p) for p in parts if p.isdigit()]
    if len(nums) >= 2: return (nums[0] + nums[1]) / 2.0
    if len(nums) == 1: return nums[0]
    return default

def business_case(n: Normalized) -> BusinessCase:
    invest = _parse_invest(n.raw.get("investitionsbudget"), 6000.0)
    monthly = invest / max(1.0, ROI_BASELINE_MONTHS)
    save_year = monthly * 12.0
    payback_m = invest / max(1.0, monthly)
    roi_y1 = (save_year - invest) / invest * 100.0
    return BusinessCase(round(invest,2), round(save_year,2), round(payback_m,1), round(roi_y1,1))

# ---------------- LLM Overlays ----------------
def _openai_chat(messages: List[Dict[str,str]], model: Optional[str] = None, max_tokens: Optional[int] = None) -> str:
    if not OPENAI_API_KEY: return ""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": model or OPENAI_MODEL, "messages": messages, "max_tokens": int(max_tokens or OPENAI_MAX_TOKENS),
               "temperature": GPT_TEMPERATURE, "top_p": 0.95}
    try:
        with httpx.Client(timeout=OPENAI_TIMEOUT) as cli:
            r = cli.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            return _strip_llm(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
    except Exception as exc:
        log.warning("OpenAI call failed: %s", exc); return ""

def _anthropic_chat(messages: List[Dict[str,str]], model: Optional[str] = None, max_tokens: int = 1200) -> str:
    if not ANTHROPIC_API_KEY: return ""
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    # Convert OpenAI-style messages to Anthropic
    sys = ""
    user_content = ""
    for m in messages:
        role = m.get("role","")
        if role == "system":
            sys = m.get("content","")
        elif role == "user":
            user_content += m.get("content","") + "\n"
    payload = {"model": model or CLAUDE_MODEL, "max_tokens": max_tokens, "system": sys, "messages": [{"role":"user","content": user_content}]}
    try:
        with httpx.Client(timeout=ANTHROPIC_TIMEOUT) as cli:
            r = cli.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json() or {}
            content = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    content += block.get("text","")
            return _strip_llm(content)
    except Exception as exc:
        log.warning("Anthropic call failed: %s", exc); return ""

def _overlay_chat(messages: List[Dict[str,str]], model_exec: Optional[str], name: str) -> str:
    provider = OVERLAY_PROVIDER
    # prefer anthropic if set to auto and api key present
    if provider == "auto":
        provider = "anthropic" if ANTHROPIC_API_KEY else "openai"
    if provider == "anthropic":
        out = _anthropic_chat(messages, model_exec if name=="executive_summary" else CLAUDE_MODEL)
        if not out and OPENAI_API_KEY:
            out = _openai_chat(messages, model_exec, OPENAI_MAX_TOKENS)
        return _minify_html_soft(_as_fragment(out))
    else:
        out = _openai_chat(messages, model_exec, OPENAI_MAX_TOKENS)
        if not out and ANTHROPIC_API_KEY:
            out = _anthropic_chat(messages, CLAUDE_MODEL)
        return _minify_html_soft(_as_fragment(out))

def _load_prompt(lang: str, name: str) -> str:
    return _load_prompt_cached(lang, name)

def render_overlay(name: str, lang: str, ctx: Dict[str,Any]) -> str:
    """Render a named overlay section using the selected LLM provider.
    Returns a **clean HTML fragment** (no <html>/<head>/<body>).
    """
    prompt = _load_prompt(lang, name)
    if not prompt: return ""
    system = "Du bist präzise und risikobewusst. Antworte als sauberes HTML-Fragment (ohne <html>/<head>/<body>)." if lang.startswith("de")                  else "You are precise and risk-aware. Answer as clean HTML fragment (no <html>/<head>/<body>)."
    user = (prompt
        .replace("{{BRIEFING_JSON}}", json.dumps(ctx.get("briefing", {}), ensure_ascii=False))
        .replace("{{SCORING_JSON}}", json.dumps(ctx.get("scoring", {}), ensure_ascii=False))
        .replace("{{BENCHMARKS_JSON}}", json.dumps(ctx.get("benchmarks", {}), ensure_ascii=False))
        .replace("{{TOOLS_JSON}}", json.dumps(ctx.get("tools", []), ensure_ascii=False))
        .replace("{{FUNDING_JSON}}", json.dumps(ctx.get("funding", []), ensure_ascii=False))
        .replace("{{BUSINESS_JSON}}", json.dumps(ctx.get("business", {}), ensure_ascii=False))
        .replace("{{INDUSTRY_SNIPPET}}", ctx.get("industry_snippet",""))
    )
    return _overlay_chat([{"role":"system","content": system},{"role":"user","content": user}], EXEC_SUMMARY_MODEL if name=="executive_summary" else OPENAI_MODEL, name)

# ---------------- HTML building blocks ----------------
def _kpi_bars_html(score: 'ScorePack') -> str:
    order = ["digitalisierung","automatisierung","compliance","prozessreife","innovation"]
    labels = {"digitalisierung":"Digitalisierung","automatisierung":"Automatisierung","compliance":"Compliance","prozessreife":"Prozessreife","innovation":"Innovation"}
    rows = []
    for k in order:
        v = score.kpis[k]["value"]; m = score.kpis[k]["benchmark"]; d = score.kpis[k]["delta"]
        spark_class = "spark-pos" if d >= 0 else "spark-neg"
        rows.append(f"<div class='bar'><div class='label'>{labels[k]}</div><div class='bar__track'><div class='bar__fill' style='width:{max(0,min(100,int(round(v))))}%;'></div><div class='bar__median' style='left:{max(0,min(100,int(round(m))))}%;'></div></div><div class='bar__delta'><span class='spark {spark_class}' data-delta='{int(round(d))}'></span> {'+' if d>=0 else ''}{int(round(d))} pp</div></div>")
    return "<div class='kpi'>" + "".join(rows) + "</div>"

def _benchmark_table_html(score: 'ScorePack') -> str:
    labels = {"digitalisierung":"Digitalisierung","automatisierung":"Automatisierung","compliance":"Compliance","prozessreife":"Prozessreife","innovation":"Innovation"}
    head = "<table class='bm'><thead><tr><th>KPI</th><th>Ihr Wert</th><th>Branchen‑Benchmark</th><th>Δ (pp)</th></tr></thead><tbody>"
    rows = []
    for k, lab in labels.items():
        v = score.kpis[k]["value"]; m = score.kpis[k]["benchmark"]; d = score.kpis[k]["delta"]
        rows.append(f"<tr><td>{lab}</td><td>{int(round(v))}%</td><td>{int(round(m))}%</td><td>{'+' if d>=0 else ''}{int(round(d))}</td></tr>")
    return head + "".join(rows) + "</tbody></table>"

def _profile_html(n: 'Normalized') -> str:
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

def _list_html(items: List[Dict[str,Any]], empty_msg: str, berlin_badge: bool = False) -> str:
    if not items: return f"<div class='muted'>{empty_msg}</div>"
    lis = []
    for it in items:
        title = it.get("title") or it.get("name") or it.get("url")
        url = it.get("url") or "#"
        dom = it.get("domain") or (url.split('/')[2] if '://' in url else "")
        when = (it.get("date") or "")[:10]
        extra = " <span class='flag-berlin'>Land Berlin</span>" if (berlin_badge and any(d in (url or "") for d in ("berlin.de","ibb.de"))) else ""
        lis.append(f"<li><a href='{url}'>{title}</a> – <span class='muted'>{dom} {when}</span> {_badge_html(url, dom)}{extra}</li>")
    return "<ul class='source-list'>" + "".join(lis) + "</ul>"

def _sources_footer_html(news: List[Dict[str,Any]], tools: List[Dict[str,Any]], funding: List[Dict[str,Any]], lang: str) -> str:
    def _mk(items, title):
        if not items:
            return f"<div class='muted'>Keine {title}.</div>" if lang.startswith("de") else f"<div class='muted'>No {title}.</div>"
        lis = []; seen = set()
        for it in items:
            url = (it.get("url") or "").split("#")[0]
            if not url or url in seen: continue
            seen.add(url)
            title_ = it.get("title") or it.get("name") or it.get("url")
            dom = it.get("domain") or (url.split('/')[2] if '://' in url else "")
            when = (it.get("date") or "")[:10]
            lis.append(f"<li><a href='{url}'>{title_}</a> – <span class='muted'>{dom} {when}</span> {_badge_html(url, dom)}</li>")
        return "<ul class='source-list'>" + "".join(lis) + "</ul>"
    return "<div class='grid'>" + "<div><h4>News</h4>" + _mk(news,"News") + "</div>" + "<div><h4>Tools</h4>" + _mk(tools,"Tools") + "</div>" + "<div><h4>" + ("Förderungen" if lang.startswith("de") else "Funding") + "</h4>" + _mk(funding,"Förderungen") + "</div>" + "</div>"

# ---------------- Baselines & matrices ----------------
def _read_csv_rows(path: Path) -> List[Dict[str,str]]:
    try:
        import csv as _csv
        with path.open("r", encoding="utf-8") as f:
            rd = _csv.DictReader(f)
            return [{k.strip(): (v or "").strip() for k,v in r.items()} for r in rd]
    except Exception:
        return []

def _industry_snippet(branche: str, lang: str) -> str:
    p = DATA_DIR / "industry_snippets.json"
    try:
        obj = json.loads(_read_text(p) or "{}")
        if lang.startswith("de"):
            return obj.get("de", {}).get(branche) or obj.get("de", {}).get("default","")
        return obj.get("en", {}).get(branche) or obj.get("en", {}).get("default","")
    except Exception:
        return ""

def _funding_baseline(n: 'Normalized', max_items: int = 5) -> List[Dict[str,Any]]:
    p = DATA_DIR / "funding_baseline.csv"
    rows = _read_csv_rows(p)
    out: List[Dict[str,Any]] = []
    for r in rows:
        region = (r.get("region") or "").upper()
        if region not in {"DE", n.bundesland_code.upper()}:
            continue
        out.append({
            "name": r.get("name"), "title": r.get("name"),
            "url": r.get("url"), "date": r.get("date") or "",
            "domain": (r.get("url","").split("/")[2] if "://" in r.get("url","") else ""),
            "score": 0
        })
    return out[:max_items]

def _tools_baseline(n: 'Normalized', max_items: int = 8) -> List[Dict[str,Any]]:
    p = DATA_DIR / "tools_baseline.csv"
    rows = _read_csv_rows(p)
    out: List[Dict[str,Any]] = []
    wanted = n.branche
    for r in rows:
        tags = (r.get("tags") or "").lower()
        if wanted and tags and wanted not in tags and "all" not in tags:
            continue
        out.append({
            "name": r.get("name"), "title": r.get("name"),
            "url": r.get("url"), "date": r.get("date") or "",
            "domain": (r.get("url","").split("/")[2] if "://" in r.get("url","") else ""),
            "score": 0
        })
    return out[:max_items]

def _tool_matrix_table(lang: str = "de") -> str:
    p = DATA_DIR / "tool_matrix.csv"
    rows = _read_csv_rows(p)
    if not rows:
        return ""
    th = ("<table class='tool-matrix'><thead><tr>"
          "<th>Tool</th><th>Kategorie</th><th>Self‑Hosting</th><th>EU‑Residency</th><th>Audit‑Logs</th><th>Link</th>"
          "</tr></thead><tbody>") if lang.startswith("de") else              ("<table class='tool-matrix'><thead><tr>"
          "<th>Tool</th><th>Category</th><th>Self‑hosting</th><th>EU residency</th><th>Audit logs</th><th>Link</th>"
          "</tr></thead><tbody>")
    rows_html = []
    for r in rows:
        link = f"<a href='{r.get('link','')}'>{r.get('name','')}</a>" if r.get("link") else (r.get("name",""))
        rows_html.append("<tr>"
                         f"<td>{link}</td>"
                         f"<td>{r.get('category','')}</td>"
                         f"<td>{r.get('self_hosting','')}</td>"
                         f"<td>{r.get('eu_residency','')}</td>"
                         f"<td>{r.get('audit_logs','')}</td>"
                         f"<td>{'<a href="'+r.get('link','')+'">Website</a>' if r.get('link') else ''}</td>"
                         "</tr>")
    return th + "".join(rows_html) + "</tbody></table>"

# ---------------- Static content blocks (from /content) ----------------
def _content_block(name: str, lang: str) -> str:
    # try HTML first
    cand: List[Path] = []
    if lang.startswith("de"):
        cand = [CONTENT_DIR / f"{name}.de.html", CONTENT_DIR / f"{name}.de.htm"]
    else:
        cand = [CONTENT_DIR / f"{name}.en.html", CONTENT_DIR / f"{name}.en.htm"]
    for p in cand:
        if p.exists():
            return _as_fragment(_read_text(p))

    # Optional: very tolerant DOCX reader
    try:
        import docx  # type: ignore
        # map names to provided docx files
        name_map_de = {
            "pillars": "4-Saeulen-KI-Readiness.docx",
            "legal": "rechtliche-Stolpersteine-KI-im-Unternehmen.docx",
            "formula": "Formel-fuer-Transformation.docx"
        }
        if lang.startswith("de") and (CONTENT_DIR / name_map_de.get(name,"")).exists():
            d = docx.Document(str(CONTENT_DIR / name_map_de[name]))
            txt = "\n".join(p.text for p in d.paragraphs if p.text.strip())
            return "<div>" + "".join(f"<p>{re.escape(t)}</p>" for t in txt.split("\n")) + "</div>"
    except Exception:
        pass

    # English fallback to known files (shipped as HTML commonly)
    en_map = {"pillars": "4-pillars-ai-readiness.en.html", "legal": "legal-pitfalls-ai.en.html", "formula": "transformation-formula-10-20-70.en.html"}
    if not lang.startswith("de") and (CONTENT_DIR / en_map.get(name,"")).exists():
        return _as_fragment(_read_text(CONTENT_DIR / en_map[name]))

    return ""

# ---------------- Glue ----------------
def build_html_report(raw: Dict[str,Any], lang: str = "de") -> Dict[str,Any]:
    _emit("analyzer", None, "boot", 0, 0, extra={
        "hybrid_live": os.getenv("HYBRID_LIVE","1"),
        "pplx_model_effective": (os.getenv("PPLX_MODEL") or "").strip() or "auto",
        "search_windows": {"news": SEARCH_DAYS_NEWS, "tools": SEARCH_DAYS_TOOLS, "funding": SEARCH_DAYS_FUNDING}
    })

    n = normalize_briefing(raw, lang=lang)
    score = compute_scores(n)
    case = business_case(n)

    # Live queries (hybrid)
    news = tools = funding = []
    if websearch_utils:
        q_news = f"Aktuelle KI-News in der Branche {n.branche_label} (letzte {SEARCH_DAYS_NEWS} Tage). Titel, Domain, URL, Datum." if lang.startswith("de")                      else f"Recent AI news in {n.branche_label} (last {SEARCH_DAYS_NEWS} days). Title, domain, URL, date."
        q_tools = f"Relevante KI-Tools/Anbieter für {n.branche_label}, Größe {n.unternehmensgroesse_label}. Titel, Domain, URL, Datum." if lang.startswith("de")                       else f"Relevant AI tools/vendors for {n.branche_label}, size {n.unternehmensgroesse_label}. Title, domain, URL, date."
        q_fund = f"Förderprogramme in {n.bundesland_code} (Digitalisierung/KI) – offen/laufend, Fristen innerhalb {SEARCH_DAYS_FUNDING} Tagen." if lang.startswith("de")                      else f"Funding programs in {n.bundesland_code} (digital/AI) – open/ongoing, deadlines within {SEARCH_DAYS_FUNDING} days."

        try:
            news = websearch_utils.perplexity_search(q_news, max_results=LIVE_MAX_ITEMS) +                        websearch_utils.tavily_search(q_news, max_results=LIVE_MAX_ITEMS, days=SEARCH_DAYS_NEWS)
            tools = websearch_utils.perplexity_search(q_tools, max_results=LIVE_MAX_ITEMS) +                         websearch_utils.tavily_search(q_tools, max_results=LIVE_MAX_ITEMS, days=SEARCH_DAYS_TOOLS)
            funding = websearch_utils.perplexity_search(q_fund, max_results=max(LIVE_MAX_ITEMS, 10)) +                           websearch_utils.tavily_search(q_fund, max_results=max(LIVE_MAX_ITEMS, 10), days=SEARCH_DAYS_FUNDING)
        except Exception as exc:
            log.warning("hybrid_live failed: %s", exc)

    # Baseline (always ensure some rows)
    funding = filter_and_rank((funding or []) + _funding_baseline(n, max_items=6))[:max(LIVE_MAX_ITEMS, 10)]
    tools = filter_and_rank((tools or []) + _tools_baseline(n, max_items=8))[:LIVE_MAX_ITEMS]
    news = filter_and_rank(news)[:LIVE_MAX_ITEMS]

    ctx = {
        "briefing": {"branche": n.branche, "branche_label": n.branche_label, "unternehmensgroesse": n.unternehmensgroesse, "unternehmensgroesse_label": n.unternehmensgroesse_label, "bundesland_code": n.bundesland_code, "hauptleistung": n.hauptleistung, "pull_kpis": n.pull_kpis},
        "scoring": {"score_total": score.total, "badge": score.badge, "kpis": score.kpis, "weights": score.weights},
        "benchmarks": score.benchmarks,
        "tools": tools,
        "funding": funding,
        "business": {"invest_eur": case.invest_eur, "save_year_eur": case.save_year_eur, "payback_months": case.payback_months, "roi_year1_pct": case.roi_year1_pct},
        "industry_snippet": _industry_snippet(n.branche, lang)
    }

    # Overlays
    sec = lambda name: render_overlay(name, lang, ctx) or ""
    exec_llm = sec("executive_summary")
    quick     = sec("quick_wins")
    roadmap   = sec("roadmap")
    risks     = sec("risks")
    compliance= sec("compliance")
    business_block = sec("business")
    recs      = sec("recommendations")
    game      = sec("gamechanger")
    vision    = sec("vision")
    persona   = sec("persona")
    praxis    = sec("praxisbeispiel")
    coach     = sec("coach")
    digest    = sec("doc_digest")

    tpl = _template(lang)
    report_date = os.getenv("REPORT_DATE_OVERRIDE") or date.today().isoformat()

    html = (tpl.replace("{{LANG}}", "de" if lang.startswith("de") else "en")
           .replace("{{ASSETS_BASE}}", ASSETS_BASE_URL)
           .replace("{{REPORT_DATE}}", report_date)
           .replace("{{PROFILE_HTML}}", _profile_html(n))
           .replace("{{KPI_BARS_HTML}}", _kpi_bars_html(score))
           .replace("{{BENCHMARK_TABLE_HTML}}", _benchmark_table_html(score))
           .replace("{{BUSINESS_CASE_HTML}}", business_block or "")
           .replace("{{EXEC_SUMMARY_HTML}}", exec_llm)
           .replace("{{QUICK_WINS_HTML}}", quick)
           .replace("{{ROADMAP_HTML}}", roadmap)
           .replace("{{RISKS_HTML}}", risks)
           .replace("{{COMPLIANCE_HTML}}", compliance)
           .replace("{{NEWS_HTML}}", _list_html(news, "Keine aktuellen News (30–60 Tage überprüft)." if lang.startswith("de") else "No recent news (30–60 days)."))
           .replace("{{TOOLS_HTML}}", _list_html(tools, "Keine passenden Tools gefunden." if lang.startswith("de") else "No matching tools."))
           .replace("{{FUNDING_HTML}}", _list_html(funding, "Keine aktuellen Einträge." if lang.startswith("de") else "No current items.", berlin_badge=True))
           .replace("{{SOURCES_FOOTER_HTML}}", _sources_footer_html(news, tools, funding, lang))
           .replace("{{TOOL_MATRIX_HTML}}", _tool_matrix_table(lang))
           .replace("{{CONTENT_PILLARS_HTML}}", _content_block("pillars", lang))
           .replace("{{CONTENT_LEGAL_HTML}}", _content_block("legal", lang))
           .replace("{{CONTENT_FORMULA_HTML}}", _content_block("formula", lang))
    )
    return {"html": html, "meta": {"score": score.total, "badge": score.badge, "date": report_date,
                                   "branche": n.branche, "size": n.unternehmensgroesse, "bundesland": n.bundesland_code,
                                   "kpis": score.kpis, "benchmarks": score.benchmarks,
                                   "live_counts": {"news": len(news), "tools": len(tools), "funding": len(funding)}},
            "normalized": n.__dict__, "raw": n.raw}

def analyze_briefing(raw: Dict[str,Any], lang: str = "de") -> str:
    return build_html_report(raw, lang)["html"]

def build_report(raw: Dict[str,Any], lang: str = "de") -> Dict[str,Any]:
    return build_html_report(raw, lang)

def analyze_briefing_enhanced(raw: Dict[str,Any], lang: str = "de", *, as_dict: bool = False):
    """
    Legacy‑kompatibler Wrapper – **Option A**:
    - Beseitigt Importfehler im alten Router, der `analyze_briefing_enhanced` erwartet.
    - Standardmäßig wird **HTML (str)** zurückgegeben, damit bestehender Code nicht bricht.
    - Wer zusätzliche Metadaten benötigt, kann `as_dict=True` setzen und erhält den vollen Payload.
    """
    try:
        out = build_html_report(raw, lang)
    except Exception as exc:
        log.exception("analyze_briefing_enhanced failed, falling back to analyze_briefing: %s", exc)
        # Graceful degradation – liefere wenigstens HTML
        return analyze_briefing(raw, lang)
    return out if as_dict else out.get("html","")

def produce_admin_attachments(raw: Dict[str,Any], lang: str = "de") -> Dict[str,str]:
    try:
        norm = normalize_briefing(raw, lang=lang)
    except Exception as exc:
        norm = Normalized(raw={"_error": f"normalize failed: {exc}", "_raw_keys": list((raw or {}).keys())})
    required = ["branche","branche_label","unternehmensgroesse","unternehmensgroesse_label","bundesland_code","hauptleistung",
                "kpi_digitalisierung","kpi_automatisierung","kpi_compliance","kpi_prozessreife","kpi_innovation"]
    def _is_missing(v) -> bool:
        if v is None: return True
        if isinstance(v, str): return v.strip() == ""
        if isinstance(v, (list, dict, tuple, set)): return len(v) == 0
        return False
    missing = sorted([k for k in required if _is_missing(getattr(norm, k, None))])
    payload_raw = raw if isinstance(raw, dict) else {"_note": "raw not dict"}
    return {"briefing_raw.json": json.dumps(payload_raw, ensure_ascii=False, indent=2),
            "briefing_normalized.json": json.dumps(norm.__dict__, ensure_ascii=False, indent=2),
            "briefing_missing_fields.json": json.dumps({"missing": missing}, ensure_ascii=False, indent=2)}
