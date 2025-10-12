# gpt_analyze.py
# -*- coding: utf-8 -*-
"""
KI-Status-Report Analyzer – Gold-Standard+ (2025-10-12)
- Schema-Normalisierung, Benchmarks, Δ, Business-Case
- Live-Layer (Perplexity Search + Tavily) mit 429-Backoff
- Quellen-Badges (utils_sources.classify_source) + Footer
- Content-Blocks aus /content (DE/EN) einbindbar
- Branchen-Snippets aus /data/industry_snippets.json
- Tool-Kompatibilitätsmatrix aus /data/tool_matrix.csv
- PDF-Templates: pdf_template.html / pdf_template_en.html
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional
import json, os, re, csv, httpx, logging

# Optional live search helpers
try:
    import websearch_utils
except Exception:
    websearch_utils = None  # type: ignore

# Badges/helpers
try:
    from utils_sources import classify_source, filter_and_rank
except Exception:
    # fallback for local execution
    from .utils_sources import classify_source, filter_and_rank  # type: ignore

LOG_LEVEL = os.getenv("LOG_LEVEL","INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("gpt_analyze")

BASE_DIR = Path(os.getenv("APP_BASE") or os.getcwd()).resolve()
DATA_DIR = Path(os.getenv("DATA_DIR") or BASE_DIR / "data").resolve()
PROMPTS_DIR = Path(os.getenv("PROMPTS_DIR") or BASE_DIR / "prompts").resolve()
CONTENT_DIR = Path(os.getenv("CONTENT_DIR") or BASE_DIR / "content").resolve()
TEMPLATES_DIR = Path(os.getenv("TEMPLATE_DIR") or BASE_DIR / "templates").resolve()

TEMPLATE_DE = os.getenv("TEMPLATE_DE","pdf_template.html")
TEMPLATE_EN = os.getenv("TEMPLATE_EN","pdf_template_en.html")
ASSETS_BASE_URL = os.getenv("ASSETS_BASE_URL","/assets")

# OpenAI overlays (optional)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or ""
OPENAI_MODEL = os.getenv("OPENAI_MODEL_DEFAULT","gpt-4o")
EXEC_SUMMARY_MODEL = os.getenv("EXEC_SUMMARY_MODEL", OPENAI_MODEL)
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT","45"))
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS","1200"))
GPT_TEMPERATURE = float(os.getenv("GPT_TEMPERATURE","0.2"))

# Live windows / switches
SEARCH_DAYS_NEWS = int(os.getenv("SEARCH_DAYS_NEWS","30"))
SEARCH_DAYS_TOOLS = int(os.getenv("SEARCH_DAYS_TOOLS","60"))
SEARCH_DAYS_FUNDING = int(os.getenv("SEARCH_DAYS_FUNDING","60"))
LIVE_MAX_ITEMS = int(os.getenv("LIVE_MAX_ITEMS","8"))
HYBRID_LIVE = os.getenv("HYBRID_LIVE","1").strip().lower() in {"1","true","yes"}

ROI_BASELINE_MONTHS = float(os.getenv("ROI_BASELINE_MONTHS","4"))

# ------------ small IO helpers -------------
def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception as exc:
        log.warning("read failed %s: %s", path, exc)
        return ""

def _template(lang: str) -> str:
    p = TEMPLATES_DIR / (TEMPLATE_DE if lang.startswith("de") else TEMPLATE_EN)
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

# --------------- locale helpers ----------------
def _fmt_pct(v: float, lang: str) -> str:
    if lang.startswith("de"):
        return f"{v:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".").replace(",0", "") + " %"
    return f"{v:,.1f}%".replace(".0","")

# --------- schema + normalization ---------
from dataclasses import dataclass, field
@dataclass
class Normalized:
    branche: str = "beratung"
    branche_label: str = "Beratung"
    unternehmensgroesse: str = "solo"
    unternehmensgroesse_label: str = "Solo"
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

def normalize_briefing(raw: Dict[str, Any], lang: str = "de") -> Normalized:
    b: Dict[str, Any] = dict(raw or {})
    if isinstance(raw, dict) and isinstance(raw.get("answers"), dict):
        b = {**raw, **raw["answers"]}

    branche_code = str(b.get("branche") or b.get("branche_code") or "beratung").lower()
    branche_label = str(b.get("branche_label") or b.get("branche") or "Beratung")
    size_code = str(b.get("unternehmensgroesse") or b.get("size") or "solo").lower()
    size_label = str(b.get("unternehmensgroesse_label") or "Solo")
    bundesland_code = str(b.get("bundesland") or b.get("bundesland_code") or "DE").upper()
    hl = b.get("hauptleistung") or b.get("produkt") or "Beratung/Service"

    def _derive_kpis(bb: Dict[str, Any]) -> Dict[str, int]:
        digi = _parse_percent_bucket(bb.get("digitalisierungsgrad"))
        papier = _parse_percent_bucket(bb.get("prozesse_papierlos"))
        digitalisierung = int(round(0.6 * digi + 0.4 * papier))
        auto = 70 if str(bb.get("automatisierungsgrad","")).lower() in ("eher_hoch","sehr_hoch") else 50
        if isinstance(bb.get("ki_einsatz"), list) and bb["ki_einsatz"]:
            auto = min(100, auto + 5)
        comp = 40
        if str(bb.get("datenschutzbeauftragter","")).lower() in ("ja","true","1"): comp += 15
        if str(bb.get("folgenabschaetzung","")).lower() == "ja": comp += 10
        if str(bb.get("loeschregeln","")).lower() == "ja": comp += 10
        if str(bb.get("meldewege","")).lower() in ("ja","teilweise"): comp += 5
        if str(bb.get("governance","")).lower() == "ja": comp += 10
        comp = max(0, min(100, comp))
        proz = 30 + (10 if str(bb.get("governance","")).lower() == "ja" else 0) + int(0.2 * papier)
        proz = max(0, min(100, proz))
        know = 70 if str(bb.get("ki_knowhow","")).lower() == "fortgeschritten" else 55
        inn = int(0.6 * know + 0.4 * 65)
        return {"digitalisierung": digitalisierung, "automatisierung": auto, "compliance": comp, "prozessreife": proz, "innovation": inn}

    k = _derive_kpis(b)
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
        kpi_digitalisierung=k["digitalisierung"],
        kpi_automatisierung=k["automatisierung"],
        kpi_compliance=k["compliance"],
        kpi_prozessreife=k["prozessreife"],
        kpi_innovation=k["innovation"],
        raw=b
    )

# ---------------- Benchmarks/Scoring ----------------
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
            if not p.exists(): 
                continue
            try:
                out: Dict[str, float] = {}
                if ext == ".json":
                    obj = json.loads(_read_text(p) or "{}") or {}
                    for k,v in obj.items():
                        try: out[_kpi_key_norm(k)] = float(str(v).replace("%","").strip())
                        except Exception: pass
                else:
                    with p.open("r", encoding="utf-8", newline="") as f:
                        rd = csv.DictReader(f)
                        for row in rd:
                            k = _kpi_key_norm((row.get("kpi") or row.get("name") or "").strip())
                            v = row.get("value") or row.get("pct") or row.get("percent") or ""
                            try: out[k] = float(str(v).replace("%","").strip())
                            except Exception: pass
                if out: return out
            except Exception as exc:
                log.warning("Benchmark import failed (%s): %s", p, exc)
    return {k: 60.0 for k in ["digitalisierung","automatisierung","compliance","prozessreife","innovation"]}

from dataclasses import dataclass
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
    weights = {k: 0.2 for k in ("digitalisierung","automatisierung","compliance","prozessreife","innovation")}
    bm = _load_benchmarks(n.branche, n.unternehmensgroesse)
    vals = {"digitalisierung": n.kpi_digitalisierung,"automatisierung": n.kpi_automatisierung,
            "compliance": n.kpi_compliance,"prozessreife": n.kpi_prozessreife,"innovation": n.kpi_innovation}
    kpis: Dict[str, Dict[str, float]] = {}
    total = 0.0
    for k, v in vals.items():
        m = float(bm.get(k, 60.0)); d = float(v) - m
        kpis[k] = {"value": float(v), "benchmark": m, "delta": d}
        total += weights[k] * float(v)
    t = int(round(total))
    return ScorePack(total=t, badge=_badge(t), kpis=kpis, weights=weights, benchmarks=bm)

# --------------- ROI --------------
from dataclasses import dataclass
@dataclass
class BusinessCase:
    invest_eur: float
    save_year_eur: float
    payback_months: float
    roi_year1_pct: float

def _parse_invest(val: Any, default: float = 6000.0) -> float:
    if isinstance(val, (int,float)): return float(val)
    s = str(val or "")
    parts = re.split(r"[^\d]", s)
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

# ---------- Overlays (OpenAI) ----------
def _openai_chat(messages: List[Dict[str,str]], model: Optional[str]=None, max_tokens: Optional[int]=None) -> str:
    if not OPENAI_API_KEY:
        return ""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": model or OPENAI_MODEL, "messages": messages, "max_tokens": int(max_tokens or OPENAI_MAX_TOKENS),
               "temperature": GPT_TEMPERATURE, "top_p": 0.95}
    try:
        with httpx.Client(timeout=OPENAI_TIMEOUT) as cli:
            r = cli.post(url, headers=headers, json=payload); r.raise_for_status()
            data = r.json()
            return _strip_llm(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
    except Exception as exc:
        log.warning("LLM call failed: %s", exc)
        return ""

def _load_prompt(lang: str, name: str) -> str:
    # lookups: prompts/{lang}/{name}_{lang}.md or prompts/{lang}/{name}.md
    for p in [
        PROMPTS_DIR / lang / f"{name}_{lang}.md",
        PROMPTS_DIR / lang / f"{name}.md",
        PROMPTS_DIR / f"{name}_{lang}.md",
        PROMPTS_DIR / f"{name}.md",
    ]:
        if p.exists():
            return _read_text(p)
    return ""

def render_overlay(name: str, lang: str, ctx: Dict[str, Any]) -> str:
    prompt = _load_prompt(lang, name)
    if not prompt:
        return ""
    system = "Du bist präzise und risikobewusst. Antworte als sauberes HTML‑Fragment (ohne <html>/<head>/<body>)." if lang.startswith("de") \
             else "You are precise and risk‑aware. Answer as clean HTML fragment (no <html>/<head>/<body>)."
    user = (prompt
        .replace("{{BRIEFING_JSON}}", json.dumps(ctx.get("briefing", {}), ensure_ascii=False))
        .replace("{{SCORING_JSON}}", json.dumps(ctx.get("scoring", {}), ensure_ascii=False))
        .replace("{{BENCHMARKS_JSON}}", json.dumps(ctx.get("benchmarks", {}), ensure_ascii=False))
        .replace("{{TOOLS_JSON}}", json.dumps(ctx.get("tools", []), ensure_ascii=False))
        .replace("{{FUNDING_JSON}}", json.dumps(ctx.get("funding", []), ensure_ascii=False))
        .replace("{{BUSINESS_JSON}}", json.dumps(ctx.get("business", {}), ensure_ascii=False))
    )
    out = _openai_chat([{"role":"system","content": system}, {"role":"user","content": user}], 
                       model=(EXEC_SUMMARY_MODEL if name == "executive_summary" else OPENAI_MODEL),
                       max_tokens=OPENAI_MAX_TOKENS)
    return _minify_html_soft(_as_fragment(out))

# ---------- HTML helpers ----------
def _kpi_bars_html(score: ScorePack) -> str:
    order = ["digitalisierung","automatisierung","compliance","prozessreife","innovation"]
    labels = {"digitalisierung":"Digitalisierung","automatisierung":"Automatisierung","compliance":"Compliance","prozessreife":"Prozessreife","innovation":"Innovation"}
    rows = []
    for k in order:
        v = score.kpis[k]["value"]; m = score.kpis[k]["benchmark"]; d = score.kpis[k]["delta"]
        rows.append(f"<div class='bar'><div class='label'>{labels[k]}</div><div class='bar__track'><div class='bar__fill' style='width:{max(0,min(100,int(round(v))))}%;'></div><div class='bar__median' style='left:{max(0,min(100,int(round(m))))}%;'></div></div><div class='bar__delta'>{'+' if d>=0 else ''}{int(round(d))} pp</div></div>")
    return "<div class='kpi'>" + "".join(rows) + "</div>"

def _benchmark_table_html(score: ScorePack) -> str:
    labels = {"digitalisierung":"Digitalisierung","automatisierung":"Automatisierung","compliance":"Compliance","prozessreife":"Prozessreife","innovation":"Innovation"}
    head = "<table class='bm'><thead><tr><th>KPI</th><th>Ihr Wert</th><th>Branchen‑Benchmark</th><th>Δ (pp)</th></tr></thead><tbody>"
    rows = []
    for k, lab in labels.items():
        v = score.kpis[k]["value"]; m = score.kpis[k]["benchmark"]; d = score.kpis[k]["delta"]
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

def _list_html(items: List[Dict[str, Any]], empty_msg: str) -> str:
    if not items: return f"<div class='muted'>{empty_msg}</div>"
    lis = []
    for it in items:
        title = it.get("title") or it.get("name") or it.get("url")
        url = it.get("url") or "#"
        dom = it.get("domain") or (url.split('/')[2] if '://' in url else "")
        when = (it.get("date") or "")[:10]
        lis.append(f"<li><a href='{url}'>{title}</a> – <span class='muted'>{dom} {when}</span> {_badge_html(url, dom)}</li>")
    return "<ul class='source-list'>" + "".join(lis) + "</ul>"

def _sources_footer_html(news: List[Dict[str, Any]], tools: List[Dict[str, Any]], funding: List[Dict[str, Any]], lang: str) -> str:
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

# ---------- content blocks & industry snippets ----------
def _load_content_blocks(lang: str) -> str:
    """Load static content HTML files from /content and concatenate."""
    files = [
        ("de", ["4-saeulen-ki-readiness.de.html", "rechtliche-stolpersteine-ki.de.html", "transformationsformel-10-20-70.de.html"]),
        ("en", ["4-pillars-ai-readiness.en.html", "legal-pitfalls-ai.en.html", "transformation-formula-10-20-70.en.html"])
    ]
    want = files[0][1] if lang.startswith("de") else files[1][1]
    frags = []
    for name in want:
        p = CONTENT_DIR / name
        if p.exists():
            frags.append(_as_fragment(_read_text(p)))
    return "\n".join(frags)

def _industry_snippet_html(branche: str, lang: str) -> str:
    p = DATA_DIR / "industry_snippets.json"
    if not p.exists():
        return ""
    try:
        obj = json.loads(_read_text(p) or "{}")
    except Exception:
        return ""
    node = obj.get(branche) or obj.get(branche.lower()) or {}
    txt = node.get("de" if lang.startswith("de") else "en") or ""
    return f"<div class='card'><h2>{'Branchen‑Einblick' if lang.startswith('de') else 'Industry Insight'}</h2><p>{txt}</p></div>" if txt else ""

def _tool_matrix_html(branche: str, lang: str) -> str:
    csv_path = DATA_DIR / "tool_matrix.csv"
    if not csv_path.exists():
        return ""
    try:
        rows = []
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            rd = csv.DictReader(f)
            for r in rd:
                tags = (r.get("tags") or "").lower()
                if branche and tags and branche not in tags:
                    continue
                rows.append(r)
        if not rows:
            return ""
    except Exception:
        return ""

    def h(s: str) -> str:
        return (s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    th = ["Tool","Self‑Hosting","EU‑Residency","Audit‑Logs","Notes","Link"]
    thead = "<thead><tr>" + "".join(f"<th>{c}</th>" for c in th) + "</tr></thead>"
    trs = []
    for r in rows[:12]:
        link = r.get("link") or ""
        anchor = f"<a href='{h(link)}'>{h(r.get('tool') or 'Link')}</a>" if link else h(r.get("tool") or "")
        trs.append("<tr>" +
                   f"<td>{anchor}</td>" +
                   f"<td>{h(r.get('self_hosting') or '')}</td>" +
                   f"<td>{h(r.get('eu_residency') or '')}</td>" +
                   f"<td>{h(r.get('audit_logs') or '')}</td>" +
                   f"<td>{h(r.get('notes') or '')}</td>" +
                   f"<td>{(f'<a href=\"{h(link)}\">open</a>' if link else '')}</td>" +
                   "</tr>")
    title = "KI‑Tool‑Kompatibilität (Auswahl)" if lang.startswith("de") else "AI Tool Compatibility (selection)"
    return f"<div class='card'><h2>{title}</h2><table class='compat'>{thead}<tbody>{''.join(trs)}</tbody></table></div>"

# ---------- glue ----------
def build_html_report(raw: Dict[str, Any], lang: str = "de") -> Dict[str, Any]:
    n = normalize_briefing(raw, lang=lang)
    score = compute_scores(n); case = business_case(n)

    # Live search
    news = tools = funding = []
    if websearch_utils and HYBRID_LIVE:
        try:
            country = "DE" if lang.startswith("de") else None
            q_news = f"Aktuelle KI-News in der Branche {n.branche_label} (letzte {SEARCH_DAYS_NEWS} Tage)." if lang.startswith("de") else f"Latest AI news for industry {n.branche_label} (last {SEARCH_DAYS_NEWS} days)."
            q_tools = f"Relevante KI-Tools für {n.branche_label}, Größe {n.unternehmensgroesse_label}." if lang.startswith("de") else f"Relevant AI tools for {n.branche_label}, size {n.unternehmensgroesse_label}."
            q_fund = f"Förderprogramme in {n.bundesland_code} (Digitalisierung/KI), Frist in {SEARCH_DAYS_FUNDING} Tagen." if lang.startswith("de") else f"Funding in {n.bundesland_code} (digital/AI), deadline within {SEARCH_DAYS_FUNDING} days."

            news = (websearch_utils.perplexity_search(q_news, max_results=LIVE_MAX_ITEMS, country=country) +
                    websearch_utils.tavily_search(q_news, max_results=LIVE_MAX_ITEMS, days=SEARCH_DAYS_NEWS))
            tools = (websearch_utils.perplexity_search(q_tools, max_results=LIVE_MAX_ITEMS, country=country) +
                     websearch_utils.tavily_search(q_tools, max_results=LIVE_MAX_ITEMS, days=SEARCH_DAYS_TOOLS))
            funding = (websearch_utils.perplexity_search(q_fund, max_results=max(LIVE_MAX_ITEMS,10), country=country) +
                       websearch_utils.tavily_search(q_fund, max_results=max(LIVE_MAX_ITEMS,10), days=SEARCH_DAYS_FUNDING))
        except Exception as exc:
            log.warning("live layer failed: %s", exc)

    news = filter_and_rank(news)[:LIVE_MAX_ITEMS]
    tools = filter_and_rank(tools)[:LIVE_MAX_ITEMS]
    funding = filter_and_rank(funding)[:max(LIVE_MAX_ITEMS,10)]

    ctx = {
        "briefing": {"branche": n.branche, "branche_label": n.branche_label, "unternehmensgroesse": n.unternehmensgroesse, "unternehmensgroesse_label": n.unternehmensgroesse_label, "bundesland_code": n.bundesland_code, "hauptleistung": n.hauptleistung, "pull_kpis": n.pull_kpis},
        "scoring": {"score_total": score.total, "badge": score.badge, "kpis": score.kpis, "weights": score.weights},
        "benchmarks": score.benchmarks,
        "tools": tools, "funding": funding,
        "business": {"invest_eur": case.invest_eur, "save_year_eur": case.save_year_eur, "payback_months": case.payback_months, "roi_year1_pct": case.roi_year1_pct},
    }

    # Overlays via LLM
    sec = lambda name: render_overlay(name, lang, ctx) or ""
    blocks = {
        "exec": sec("executive_summary"),
        "quick": sec("quick_wins"),
        "roadmap": sec("roadmap"),
        "risks": sec("risks"),
        "compliance": sec("compliance"),
        "business": sec("business"),
        "recs": sec("recommendations"),
        "game": sec("gamechanger"),
        "vision": sec("vision"),
        "persona": sec("persona"),
        "praxis": sec("praxisbeispiel"),
        "coach": sec("coach"),
        "digest": sec("doc_digest"),
    }

    tpl = _template(lang)
    report_date = os.getenv("REPORT_DATE_OVERRIDE") or date.today().isoformat()

    html = (tpl.replace("{{LANG}}", "de" if lang.startswith("de") else "en")
             .replace("{{ASSETS_BASE}}", ASSETS_BASE_URL)
             .replace("{{REPORT_DATE}}", report_date)
             .replace("{{PROFILE_HTML}}", _profile_html(n))
             .replace("{{KPI_BARS_HTML}}", _kpi_bars_html(score))
             .replace("{{BENCHMARK_TABLE_HTML}}", _benchmark_table_html(score))
             .replace("{{BUSINESS_CASE_HTML}}", blocks["business"] or "")
             .replace("{{EXEC_SUMMARY_HTML}}", blocks["exec"])
             .replace("{{QUICK_WINS_HTML}}", blocks["quick"])
             .replace("{{ROADMAP_HTML}}", blocks["roadmap"])
             .replace("{{RISKS_HTML}}", blocks["risks"])
             .replace("{{COMPLIANCE_HTML}}", blocks["compliance"])
             .replace("{{NEWS_HTML}}", _list_html(news, "Keine aktuellen News (30–60 Tage überprüft)." if lang.startswith("de") else "No recent news (30–60 days)."))
             .replace("{{TOOLS_HTML}}", _list_html(tools, "Keine passenden Tools gefunden." if lang.startswith("de") else "No matching tools."))
             .replace("{{FUNDING_HTML}}", _list_html(funding, "Keine aktuellen Einträge." if lang.startswith("de") else "No current items."))
             .replace("{{SOURCES_FOOTER_HTML}}", _sources_footer_html(news, tools, funding, lang))
             .replace("{{GUIDES_HTML}}", _load_content_blocks(lang))
             .replace("{{INDUSTRY_SNIPPET_HTML}}", _industry_snippet_html(n.branche, lang))
             .replace("{{TOOL_MATRIX_HTML}}", _tool_matrix_html(n.branche, lang))
           )
    return {"html": html, "meta": {"score": score.total, "badge": score.badge, "date": report_date,
                                   "branche": n.branche, "size": n.unternehmensgroesse, "bundesland": n.bundesland_code,
                                   "kpis": score.kpis, "benchmarks": score.benchmarks,
                                   "live_counts": {"news": len(news), "tools": len(tools), "funding": len(funding)}},
            "normalized": n.__dict__, "raw": n.raw}

def analyze_briefing(raw: Dict[str, Any], lang: str = "de") -> str:
    return build_html_report(raw, lang)["html"]

def build_report(raw: Dict[str, Any], lang: str = "de") -> Dict[str, Any]:
    return build_html_report(raw, lang)
