# filename: gpt_analyze.py
# -*- coding: utf-8 -*-
"""
Analyzer (Gold-Standard+) – embeds /content sections, Hybrid-Live, KPI/Δ & ROI.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json, os, re, httpx, logging, zipfile

import websearch_utils
from utils_sources import classify_source, filter_and_rank

# Structured logging (optional)
try:
    from live_logger import log_event as _emit  # type: ignore
except Exception:
    def _emit(provider: str, model: Optional[str], status: str, latency_ms: int, count: int = 0, **kw: Any) -> None:
        pass

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("gpt_analyze")

BASE_DIR = Path(os.getenv("APP_BASE") or os.getcwd()).resolve()
DATA_DIR = Path(os.getenv("DATA_DIR") or BASE_DIR / "data").resolve()
PROMPTS_DIR = Path(os.getenv("PROMPTS_DIR") or BASE_DIR / "prompts").resolve()
TEMPLATES_DIR = Path(os.getenv("TEMPLATE_DIR") or BASE_DIR / "templates").resolve()
CONTENT_DIR = Path(os.getenv("CONTENT_DIR") or BASE_DIR / "content").resolve()

TEMPLATE_DE = os.getenv("TEMPLATE_DE", "pdf_template.html")
TEMPLATE_EN = os.getenv("TEMPLATE_EN", "pdf_template_en.html")
ASSETS_BASE_URL = os.getenv("ASSETS_BASE_URL", "/assets")

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
HYBRID_LIVE = os.getenv("HYBRID_LIVE", "1").strip().lower() in {"1","true","yes"}

ROI_BASELINE_MONTHS = float(os.getenv("ROI_BASELINE_MONTHS", "4"))
CONTENT_SECTIONS = os.getenv("CONTENT_SECTIONS", "pillars,legal,formula")

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
    if not text: return ""
    return re.sub(r"```[a-zA-Z0-9]*\s*", "", text).replace("```","").strip()

def _as_fragment(html: str) -> str:
    if not html: return ""
    s = re.sub(r"(?is)<!doctype.*?>", "", html)
    s = re.sub(r"(?is)<\s*html[^>]*>|</\s*html\s*>", "", s)
    s = re.sub(r"(?is)<\s*head[^>]*>.*?</\s*head\s*>", "", s)
    s = re.sub(r"(?is)<\s*body[^>]*>|</\s*body\s*>", "", s)
    s = re.sub(r"(?is)<\s*style[^>]*>.*?</\s*style\s*>", "", s)
    return s.strip()

# --- DOCX (no external lib) --------------------------------------------------
def _docx_to_html(path: Path) -> str:
    """Crude DOCX -> HTML paragraphs by parsing document.xml for <w:t> text nodes."""
    try:
        with zipfile.ZipFile(str(path), "r") as zf:
            xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
        # Split by paragraphs
        parts = re.split(r"</w:p>", xml)
        paras: List[str] = []
        for part in parts:
            texts = re.findall(r"<w:t[^>]*>(.*?)</w:t>", part, flags=re.S)
            txt = "".join(texts)
            txt = re.sub(r"&amp;","&", txt)
            txt = re.sub(r"&lt;","<", txt)
            txt = re.sub(r"&gt;",">", txt)
            if txt.strip():
                paras.append(f"<p>{txt.strip()}</p>")
        return "\n".join(paras)
    except Exception:
        return ""

def load_content_sections(lang: str = "de") -> Dict[str, Dict[str, str]]:
    """Load pillars/legal/formula as HTML fragments from /content.
       DE prefers *.docx if no *.de.html exists; EN uses *.en.html.
    """
    out: Dict[str, Dict[str,str]] = {"pillars": {"html":"", "source": ""},
                                     "legal": {"html":"", "source": ""},
                                     "formula": {"html":"", "source": ""}}
    if lang.startswith("de"):
        # try .de.html first; else .docx variants provided by user
        pillars_html = ""
        legal_html = ""
        formula_html = ""
        p_de = CONTENT_DIR / "4-Saeulen-KI-Readiness.de.html"
        l_de = CONTENT_DIR / "rechtliche-Stolpersteine-KI-im-Unternehmen.de.html"
        f_de = CONTENT_DIR / "Formel-fuer-Transformation.de.html"
        if p_de.exists(): pillars_html = _as_fragment(_read_text(p_de))
        else:
            p_docx = CONTENT_DIR / "4-Saeulen-KI-Readiness.docx"
            pillars_html = _docx_to_html(p_docx) if p_docx.exists() else ""
        if l_de.exists(): legal_html = _as_fragment(_read_text(l_de))
        else:
            l_docx = CONTENT_DIR / "rechtliche-Stolpersteine-KI-im-Unternehmen.docx"
            legal_html = _docx_to_html(l_docx) if l_docx.exists() else ""
        if f_de.exists(): formula_html = _as_fragment(_read_text(f_de))
        else:
            f_docx = CONTENT_DIR / "Formel-fuer-Transformation.docx"
            formula_html = _docx_to_html(f_docx) if f_docx.exists() else ""

        out["pillars"]["html"] = pillars_html
        out["legal"]["html"] = legal_html
        out["formula"]["html"] = formula_html
    else:
        # english HTML files as provided
        p_en = CONTENT_DIR / "4-pillars-ai-readiness.en.html"
        l_en = CONTENT_DIR / "legal-pitfalls-ai.en.html"
        f_en = CONTENT_DIR / "transformation-formula-10-20-70.en.html"
        out["pillars"]["html"] = _as_fragment(_read_text(p_en)) if p_en.exists() else ""
        out["legal"]["html"] = _as_fragment(_read_text(l_en)) if l_en.exists() else ""
        out["formula"]["html"] = _as_fragment(_read_text(f_en)) if f_en.exists() else ""
    return out

# --- KPI & Score -------------------------------------------------------------
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
    digi = _parse_percent_bucket(b.get("digitalisierungsgrad"))
    papier = _parse_percent_bucket(b.get("prozesse_papierlos"))
    digitalisierung = int(round(0.6*digi + 0.4*papier))
    auto = 70 if str(b.get("automatisierungsgrad","")).lower() in ("eher_hoch","sehr_hoch") else 50
    if isinstance(b.get("ki_einsatz"), list) and b["ki_einsatz"]:
        auto = min(100, auto+5)
    comp = 40
    if str(b.get("datenschutzbeauftragter","")).lower() in ("ja","true","1"): comp += 15
    if str(b.get("folgenabschaetzung","")).lower()=="ja": comp += 10
    if str(b.get("loeschregeln","")).lower()=="ja": comp += 10
    if str(b.get("meldewege","")).lower() in ("ja","teilweise"): comp += 5
    if str(b.get("governance","")).lower()=="ja": comp += 10
    comp = max(0, min(100, comp))
    proz = 30 + (10 if str(b.get("governance","")).lower()=="ja" else 0) + int(0.2*papier)
    proz = max(0, min(100, proz))
    know = 70 if str(b.get("ki_knowhow","")).lower()=="fortgeschritten" else 55
    inn = int(0.6*know + 0.4*65)
    pull = {
        "umsatzziel": b.get("umsatzziel") or b.get("jahresumsatz") or "",
        "top_use_case": b.get("usecase_priority") or (b.get("ki_usecases") or [""])[0] if b.get("ki_usecases") else "",
        "zeitbudget": b.get("zeitbudget") or "",
    }
    return Normalized(
        branche=branche_code, branche_label=branche_label,
        unternehmensgroesse=size_code, unternehmensgroesse_label=size_label,
        bundesland_code=bundesland_code, hauptleistung=hl, pull_kpis=pull,
        kpi_digitalisierung=digitalisierung, kpi_automatisierung=auto,
        kpi_compliance=comp, kpi_prozessreife=proz, kpi_innovation=inn, raw=b
    )

def _kpi_key_norm(k: str) -> str:
    s = k.strip().lower()
    m = {"digitalisierung":"digitalisierung","automatisierung":"automatisierung","automation":"automatisierung",
         "compliance":"compliance","prozessreife":"prozessreife","prozesse":"prozessreife","innovation":"innovation"}
    return m.get(s, s)

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
                if ext==".json":
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
            except Exception:
                pass
    return {k:60.0 for k in ["digitalisierung","automatisierung","compliance","prozessreife","innovation"]}

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
    weights = {k:0.2 for k in ("digitalisierung","automatisierung","compliance","prozessreife","innovation")}
    bm = _load_benchmarks(n.branche, n.unternehmensgroesse)
    vals = {"digitalisierung": n.kpi_digitalisierung, "automatisierung": n.kpi_automatisierung,
            "compliance": n.kpi_compliance, "prozessreife": n.kpi_prozessreife, "innovation": n.kpi_innovation}
    kpis: Dict[str, Dict[str,float]] = {}
    total = 0.0
    for k, v in vals.items():
        m = float(bm.get(k, 60.0))
        d = float(v) - m
        kpis[k] = {"value": float(v), "benchmark": m, "delta": d}
        total += weights[k]*float(v)
    t = int(round(total))
    return ScorePack(total=t, badge=_badge(t), kpis=kpis, weights=weights, benchmarks=bm)

@dataclass
class BusinessCase:
    invest_eur: float
    save_year_eur: float
    payback_months: float
    roi_year1_pct: float

def _parse_invest(val: Any, default: float = 6000.0) -> float:
    if isinstance(val,(int,float)): return float(val)
    s = str(val or "")
    parts = re.split(r"[^\d]", s)
    nums = [float(p) for p in parts if p.isdigit()]
    if len(nums) >= 2: return (nums[0]+nums[1])/2.0
    if len(nums) == 1: return nums[0]
    return default

def business_case(n: Normalized) -> BusinessCase:
    invest = _parse_invest(n.raw.get("investitionsbudget"), 6000.0)
    monthly = invest / max(1.0, ROI_BASELINE_MONTHS)
    save_year = monthly * 12.0
    payback_m = invest / max(1.0, monthly)
    roi_y1 = (save_year - invest) / invest * 100.0
    return BusinessCase(round(invest,2), round(save_year,2), round(payback_m,1), round(roi_y1,1))

# --- OpenAI overlay ----------------------------------------------------------
def _openai_chat(messages: List[Dict[str,str]], model: Optional[str]=None, max_tokens: Optional[int]=None) -> str:
    if not OPENAI_API_KEY: return ""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type":"application/json"}
    payload = {"model": model or OPENAI_MODEL, "messages": messages, "max_tokens": int(max_tokens or OPENAI_MAX_TOKENS),
               "temperature": GPT_TEMPERATURE, "top_p": 0.95}
    try:
        with httpx.Client(timeout=OPENAI_TIMEOUT) as cli:
            r = cli.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            return _strip_llm(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
    except Exception as exc:
        log.warning("LLM call failed: %s", exc)
        return ""

def _load_prompt(lang: str, name: str) -> str:
    cand = [PROMPTS_DIR / lang / f"{name}_{lang}.md", PROMPTS_DIR / lang / f"{name}.md",
            PROMPTS_DIR / f"{name}_{lang}.md", PROMPTS_DIR / f"{name}.md"]
    for p in cand:
        if p.exists():
            log.info("Loaded prompt: %s", p.relative_to(PROMPTS_DIR))
            return _read_text(p)
    log.info("Prompt missing for '%s' (%s) – skipping section", name, lang)
    return ""

def render_overlay(name: str, lang: str, ctx: Dict[str,Any]) -> str:
    prompt = _load_prompt(lang, name)
    if not prompt: return ""
    system = "Antworte als sauberes HTML-Fragment (ohne <html>/<head>/<body>), präzise & risikobewusst." if lang.startswith("de") \
        else "Answer as clean HTML fragment (no <html>/<head>/<body>), precise & risk-aware."
    user = (prompt
        .replace("{{BRIEFING_JSON}}", json.dumps(ctx.get("briefing", {}), ensure_ascii=False))
        .replace("{{SCORING_JSON}}", json.dumps(ctx.get("scoring", {}), ensure_ascii=False))
        .replace("{{BENCHMARKS_JSON}}", json.dumps(ctx.get("benchmarks", {}), ensure_ascii=False))
        .replace("{{TOOLS_JSON}}", json.dumps(ctx.get("tools", []), ensure_ascii=False))
        .replace("{{FUNDING_JSON}}", json.dumps(ctx.get("funding", []), ensure_ascii=False))
        .replace("{{BUSINESS_JSON}}", json.dumps(ctx.get("business", {}), ensure_ascii=False))
    )
    out = _openai_chat([{"role":"system","content": system}, {"role":"user","content": user}],
                       model=EXEC_SUMMARY_MODEL if name=="executive_summary" else OPENAI_MODEL)
    return _as_fragment(_strip_llm(out))

# --- HTML building -----------------------------------------------------------
def _badge_html(url: str, domain: str) -> str:
    cat, label, badge, _ = classify_source(url, domain)
    return f"<span class='badge {badge}'>{label}</span>"

def _list_html(items: List[Dict[str,Any]], empty_msg: str, berlin_badge: bool=False) -> str:
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

def _kpi_bars_html(score) -> str:
    order = ["digitalisierung","automatisierung","compliance","prozessreife","innovation"]
    labels = {"digitalisierung":"Digitalisierung","automatisierung":"Automatisierung","compliance":"Compliance",
              "prozessreife":"Prozessreife","innovation":"Innovation"}
    rows = []
    for k in order:
        v = score.kpis[k]["value"]; m = score.kpis[k]["benchmark"]; d = score.kpis[k]["delta"]
        rows.append(
            "<div class='bar'>"
            f"<div class='label'>{labels[k]}</div>"
            "<div class='bar__track'>"
            f"<div class='bar__fill' style='width:{max(0,min(100,int(round(v))))}%;'></div>"
            f"<div class='bar__median' style='left:{max(0,min(100,int(round(m))))}%;'></div>"
            "</div>"
            f"<div class='bar__delta'>{'+' if d>=0 else ''}{int(round(d))} pp</div>"
            "</div>"
        )
    return "<div class='kpi'>" + "".join(rows) + "</div>"

def _benchmark_table_html(score) -> str:
    labels = {"digitalisierung":"Digitalisierung","automatisierung":"Automatisierung","compliance":"Compliance",
              "prozessreife":"Prozessreife","innovation":"Innovation"}
    head = "<table class='bm'><thead><tr><th>KPI</th><th>Ihr Wert</th><th>Branchen‑Benchmark</th><th>Δ (pp)</th></tr></thead><tbody>"
    rows = []
    for k, lab in labels.items():
        v = score.kpis[k]["value"]; m = score.kpis[k]["benchmark"]; d = score.kpis[k]["delta"]
        rows.append(f"<tr><td>{lab}</td><td>{int(round(v))}%</td><td>{int(round(m))}%</td><td>{'+' if d>=0 else ''}{int(round(d))}</td></tr>")
    return head + "".join(rows) + "</tbody></table>"

def build_report(raw: Dict[str,Any], lang: str="de") -> Dict[str,Any]:
    # boot log
    _emit("live_layer", None, "boot", 0, 0, extra={
        "hybrid_live": os.getenv("HYBRID_LIVE","1"),
        "pplx_model_effective": os.getenv("PPLX_MODEL","").strip() or "none",
        "search_windows": {"news": SEARCH_DAYS_NEWS, "tools": SEARCH_DAYS_TOOLS, "funding": SEARCH_DAYS_FUNDING},
    })

    n = normalize_briefing(raw, lang=lang)
    score = compute_scores(n)
    case = business_case(n)

    # live layer (short, specific queries; domains filter)
    news: List[Dict[str,Any]] = []
    tools: List[Dict[str,Any]] = []
    funding: List[Dict[str,Any]] = []

    if HYBRID_LIVE:
        try:
            inc = os.getenv("SEARCH_INCLUDE_DOMAINS","")
            q_news = f"Aktuelle KI-News {n.branche_label} {n.bundesland_code} letzte {SEARCH_DAYS_NEWS} Tage {inc}"
            q_tools = f"KI-Tools/Anbieter {n.branche_label} {n.unternehmensgroesse_label} DSGVO {inc}"
            q_fund = f"Förderprogramme Digitalisierung/KI {n.bundesland_code} Fristen {SEARCH_DAYS_FUNDING} Tage ZIM BMBF BMWK DLR {inc}"
            news = websearch_utils.perplexity_search_multi(q_news, max_results=LIVE_MAX_ITEMS, days=SEARCH_DAYS_NEWS)
            tools = websearch_utils.perplexity_search_multi(q_tools, max_results=LIVE_MAX_ITEMS, days=SEARCH_DAYS_TOOLS)
            funding = websearch_utils.perplexity_search_multi(q_fund, max_results=max(LIVE_MAX_ITEMS,10), days=SEARCH_DAYS_FUNDING)
        except Exception as exc:
            log.warning("hybrid_live failed: %s", exc)

    # rank + trim again
    news = filter_and_rank(news)[:LIVE_MAX_ITEMS]
    tools = filter_and_rank(tools)[:LIVE_MAX_ITEMS]
    funding = filter_and_rank(funding)[:max(LIVE_MAX_ITEMS,10)]

    # content sections
    content = load_content_sections(lang)
    pillars_html = content["pillars"]["html"]
    legal_html = content["legal"]["html"]
    formula_html = content["formula"]["html"]

    tpl = _template(lang)
    report_date = os.getenv("REPORT_DATE_OVERRIDE") or date.today().isoformat()

    html = (tpl.replace("{{LANG}}", "de" if lang.startswith("de") else "en")
            .replace("{{ASSETS_BASE}}", ASSETS_BASE_URL)
            .replace("{{REPORT_DATE}}", report_date)
            .replace("{{EXEC_SUMMARY_HTML}}", render_overlay("executive_summary", lang, {
                "briefing": n.__dict__, "scoring": {"score_total": score.total, "badge": score.badge, "kpis": score.kpis},
                "benchmarks": score.benchmarks, "tools": tools, "funding": funding,
                "business": {"invest_eur": case.invest_eur, "save_year_eur": case.save_year_eur,
                             "payback_months": case.payback_months, "roi_year1_pct": case.roi_year1_pct}
            }))
            .replace("{{PROFILE_HTML}}", f"<div class='card'><h2>{'Unternehmensprofil & Ziele' if lang.startswith('de') else 'Company Profile & Goals'}</h2>"
                                         f"<p><span class='hl'>Hauptleistung:</span> {n.hauptleistung} "
                                         f"<span class='muted'>&middot; Branche:</span> {n.branche_label} "
                                         f"<span class='muted'>&middot; Größe:</span> {n.unternehmensgroesse_label}</p></div>")
            .replace("{{KPI_BARS_HTML}}", _kpi_bars_html(score))
            .replace("{{BENCHMARK_TABLE_HTML}}", _benchmark_table_html(score))
            .replace("{{BUSINESS_CASE_HTML}}", render_overlay("business", lang, {
                "briefing": n.__dict__, "scoring": {"score_total": score.total}, "benchmarks": score.benchmarks,
                "business": {"invest_eur": case.invest_eur, "save_year_eur": case.save_year_eur,
                             "payback_months": case.payback_months, "roi_year1_pct": case.roi_year1_pct}
            }))
            .replace("{{NEWS_HTML}}", _list_html(news, "Keine aktuellen News (30–60 Tage überprüft)." if lang.startswith("de") else "No recent news (30–60 days)."))
            .replace("{{TOOLS_HTML}}", _list_html(tools, "Keine passenden Tools gefunden." if lang.startswith("de") else "No matching tools."))
            .replace("{{FUNDING_HTML}}", _list_html(funding, "Keine aktuellen Einträge." if lang.startswith("de") else "No current items.", berlin_badge=True))
            .replace("{{SOURCES_FOOTER_HTML}}", (
                "<div class='muted'>—</div>" if not (news or tools or funding) else
                "<div class='grid'>"
                + "<div><h4>News</h4>"+_list_html(news,"")+"</div>"
                + "<div><h4>Tools</h4>"+_list_html(tools,"")+"</div>"
                + "<div><h4>"+("Förderungen" if lang.startswith("de") else "Funding")+"</h4>"+_list_html(funding,"")+"</div>"
                + "</div>"
            ))
            .replace("{{CONTENT_PILLARS_HTML}}", pillars_html)
            .replace("{{CONTENT_LEGAL_HTML}}", legal_html)
            .replace("{{CONTENT_FORMULA_HTML}}", formula_html)
           )
    return {
        "html": html,
        "meta": {"score": score.total, "badge": score.badge, "date": report_date,
                 "branche": n.branche, "size": n.unternehmensgroesse, "bundesland": n.bundesland_code,
                 "kpis": score.kpis, "benchmarks": score.benchmarks,
                 "live_counts": {"news": len(news), "tools": len(tools), "funding": len(funding)}},
        "normalized": n.__dict__,
        "raw": n.raw
    }

def analyze_briefing(raw: Dict[str,Any], lang: str = "de") -> str:
    return build_report(raw, lang)["html"]

def produce_admin_attachments(raw: Dict[str,Any], lang: str = "de") -> Dict[str,str]:
    norm = normalize_briefing(raw, lang=lang)
    required = ["branche","branche_label","unternehmensgroesse","unternehmensgroesse_label","bundesland_code","hauptleistung",
                "kpi_digitalisierung","kpi_automatisierung","kpi_compliance","kpi_prozessreife","kpi_innovation"]
    def _is_missing(v) -> bool:
        if v is None: return True
        if isinstance(v, str): return v.strip()==""
        if isinstance(v, (list,dict,tuple,set)): return len(v)==0
        return False
    missing = sorted([k for k in required if _is_missing(getattr(norm, k, None))])
    return {
        "briefing_raw.json": json.dumps(raw if isinstance(raw, dict) else {"_note":"raw not dict"}, ensure_ascii=False, indent=2),
        "briefing_normalized.json": json.dumps(norm.__dict__, ensure_ascii=False, indent=2),
        "briefing_missing_fields.json": json.dumps({"missing": missing}, ensure_ascii=False, indent=2)
    }
