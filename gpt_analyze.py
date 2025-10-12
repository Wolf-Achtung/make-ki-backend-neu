# filename: gpt_analyze.py
# -*- coding: utf-8 -*-
"""
KI-Status-Report Analyzer – Gold-Standard+
- Normalisierung + Scoring + Benchmarks + Δ
- ROI (≤ 4 Monate baseline via ROI_BASELINE_MONTHS)
- Prompt-Overlays (DE/EN) – strikt HTML-Fragmente
- Live-Layer: Tavily + Perplexity (Guards, Backoff)
- Guides-Einbindung aus content/ (DE: .docx -> HTML Fallback)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json, logging, os, re, httpx, zipfile, xml.etree.ElementTree as ET

# Hybrid search optional
try:
    import websearch_utils  # type: ignore
except Exception:  # pragma: no cover
    websearch_utils = None  # type: ignore

# Source helpers
try:
    from utils_sources import classify_source, filter_and_rank  # type: ignore
except Exception:  # pragma: no cover
    def classify_source(url: str, domain: str): return ("web","Web","badge-web",0.5)
    def filter_and_rank(x): return x

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
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

# OpenAI overlays (optional)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or ""
OPENAI_MODEL = os.getenv("OPENAI_MODEL_DEFAULT", "gpt-4o")
EXEC_SUMMARY_MODEL = os.getenv("EXEC_SUMMARY_MODEL", OPENAI_MODEL)
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "45"))
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "1100"))
GPT_TEMPERATURE = float(os.getenv("GPT_TEMPERATURE", "0.2"))

SEARCH_DAYS_NEWS = int(os.getenv("SEARCH_DAYS_NEWS", "30"))
SEARCH_DAYS_TOOLS = int(os.getenv("SEARCH_DAYS_TOOLS", "60"))
SEARCH_DAYS_FUNDING = int(os.getenv("SEARCH_DAYS_FUNDING", "60"))
LIVE_MAX_ITEMS = int(os.getenv("LIVE_MAX_ITEMS", "8"))
HYBRID_LIVE = os.getenv("HYBRID_LIVE", "1").strip().lower() in {"1","true","yes"}

ROI_BASELINE_MONTHS = float(os.getenv("ROI_BASELINE_MONTHS", "4"))

# ---------------- IO helpers ----------------
def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover
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
    s = re.sub(r">\\s+<", "><", s)
    s = re.sub(r"\\s{2,}", " ", s)
    return s.strip()

def _strip_llm(text: str) -> str:
    if not text: return ""
    text = re.sub(r"```[a-zA-Z0-9]*\\s*", "", text).replace("```", "")
    return text.strip()

def _as_fragment(html: str) -> str:
    if not html: return ""
    s = html
    s = re.sub(r"(?is)<!doctype.*?>", "", s)
    s = re.sub(r"(?is)<\\s*html[^>]*>|</\\s*html\\s*>", "", s)
    s = re.sub(r"(?is)<\\s*head[^>]*>.*?</\\s*head\\s*>", "", s)
    s = re.sub(r"(?is)<\\s*body[^>]*>|</\\s*body\\s*>", "", s)
    s = re.sub(r"(?is)<\\s*style[^>]*>.*?</\\s*style\\s*>", "", s)
    return s.strip()

# ---------------- Locale helpers ----------------
def _fmt_pct(v: float, lang: str) -> str:
    if lang.startswith("de"):
        return f"{v:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".").replace(".0", "") + " %"
    return f"{v:,.1f}%".replace(".0", "")

def _fmt_money_eur(v: float, lang: str) -> str:
    if lang.startswith("de"):
        s = f"{v:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return s + " €"
    return "€" + f"{v:,.0f}"

# ---------------- Schema / Normalization ----------------
def _parse_percent_bucket(val: Any) -> int:
    s = str(val or "").lower()
    if "81" in s: return 90
    if "61" in s: return 70
    if "41" in s: return 50
    if "21" in s: return 30
    if "0" in s:  return 10
    try: return int(max(0, min(100, float(s))))
    except Exception: return 50

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

def normalize_briefing(raw: Dict[str, Any], lang: str = "de") -> Normalized:
    b: Dict[str, Any] = dict(raw or {})
    if isinstance(raw, dict) and isinstance(raw.get("answers"), dict):
        b = {**raw, **raw["answers"]}

    branche_code = str(b.get("branche") or b.get("branche_code") or "beratung").lower()
    branche_label = str(b.get("branche_label") or b.get("branche") or "Beratung")
    size_code = str(b.get("unternehmensgroesse") or b.get("size") or "solo").lower()
    size_label = str(b.get("unternehmensgroesse_label") or "1 (Solo/Freiberuflich)")
    bundesland_code = str(b.get("bundesland") or b.get("bundesland_code") or "DE").upper()
    hl = b.get("hauptleistung") or b.get("produkt") or "Beratung/Service"

    def _derive_kpis(bb: Dict[str, Any]) -> Dict[str, int]:
        digi = _parse_percent_bucket(bb.get("digitalisierungsgrad"))
        papier = _parse_percent_bucket(bb.get("prozesse_papierlos"))
        digitalisierung = int(round(0.6 * digi + 0.4 * papier))
        auto = 70 if str(bb.get("automatisierungsgrad", "")).lower() in ("eher_hoch", "sehr_hoch") else 50
        if isinstance(bb.get("ki_einsatz"), list) and bb["ki_einsatz"]:
            auto = min(100, auto + 5)
        comp = 40
        if str(bb.get("datenschutzbeauftragter", "")).lower() in ("ja", "true", "1"): comp += 15
        if str(bb.get("folgenabschaetzung", "")).lower() == "ja": comp += 10
        if str(bb.get("loeschregeln", "")).lower() == "ja": comp += 10
        if str(bb.get("meldewege", "")).lower() in ("ja", "teilweise"): comp += 5
        if str(bb.get("governance", "")).lower() == "ja": comp += 10
        comp = max(0, min(100, comp))
        proz = 30 + (10 if str(bb.get("governance", "")).lower() == "ja" else 0) + int(0.2 * papier)
        proz = max(0, min(100, proz))
        know = 70 if str(bb.get("ki_knowhow", "")).lower() == "fortgeschritten" else 55
        inn = int(0.6 * know + 0.4 * 65)
        return {
            "digitalisierung": digitalisierung,
            "automatisierung": auto,
            "compliance": comp,
            "prozessreife": proz,
            "innovation": inn,
        }

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
        for ext in (".json", ".csv"):
            p = DATA_DIR / f"{base}{ext}"
            if not p.exists(): continue
            try:
                out: Dict[str, float] = {}
                if ext == ".json":
                    obj = json.loads(_read_text(p) or "{}")
                    for k, v in (obj or {}).items():
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

# ---------------- Business Case (ROI) ----------------
@dataclass
class BusinessCase:
    invest_eur: float
    save_year_eur: float
    payback_months: float
    roi_year1_pct: float

def _parse_invest(val: Any, default: float = 6000.0) -> float:
    if isinstance(val, (int, float)): return float(val)
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

# ---------------- LLM Overlays (OpenAI) ----------------
def _openai_chat(messages: List[Dict[str, str]], model: Optional[str] = None, max_tokens: Optional[int] = None) -> str:
    if not OPENAI_API_KEY:
        return ""
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
    except Exception as exc:  # pragma: no cover
        log.warning("LLM call failed: %s", exc)
        return ""

def _load_prompt(lang: str, name: str) -> str:
    cand = [PROMPTS_DIR / lang / f"{name}_{lang}.md", PROMPTS_DIR / lang / f"{name}.md", PROMPTS_DIR / f"{name}_{lang}.md", PROMPTS_DIR / f"{name}.md"]
    for p in cand:
        if p.exists():
            log.info("Loaded prompt: %s", p.relative_to(PROMPTS_DIR))
            return _read_text(p)
    log.info("Prompt missing for '%s' (%s) – skipping section", name, lang)
    return ""

def render_overlay(name: str, lang: str, ctx: Dict[str, Any]) -> str:
    prompt = _load_prompt(lang, name)
    if not prompt: return ""
    system = "Du bist präzise und risikobewusst. Antworte als sauberes HTML-Fragment (ohne <html>/<head>/<body>)." if lang.startswith("de") else \
             "You are precise and risk-aware. Answer as clean HTML fragment (no <html>/<head>/<body>)."
    user = (prompt
        .replace("{{BRIEFING_JSON}}", json.dumps(ctx.get("briefing", {}), ensure_ascii=False))
        .replace("{{SCORING_JSON}}", json.dumps(ctx.get("scoring", {}), ensure_ascii=False))
        .replace("{{BENCHMARKS_JSON}}", json.dumps(ctx.get("benchmarks", {}), ensure_ascii=False))
        .replace("{{TOOLS_JSON}}", json.dumps(ctx.get("tools", []), ensure_ascii=False))
        .replace("{{FUNDING_JSON}}", json.dumps(ctx.get("funding", []), ensure_ascii=False))
        .replace("{{BUSINESS_JSON}}", json.dumps(ctx.get("business", {}), ensure_ascii=False))
    )
    out = _openai_chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
                       model=EXEC_SUMMARY_MODEL if name == "executive_summary" else OPENAI_MODEL)
    return _minify_html_soft(_as_fragment(out))

# ---------------- HTML helper blocks ----------------
def _spark_delta(delta: float) -> str:
    # Inline-SVG: -30..+30 pp
    try:
        d = max(-30.0, min(30.0, float(delta)))
    except Exception:
        d = 0.0
    x = int(round((d + 30.0) / 60.0 * 58))  # 0..58
    color = "#059669" if d >= 0 else "#b91c1c"
    return f"<svg width='60' height='12' viewBox='0 0 60 12' xmlns='http://www.w3.org/2000/svg'><line x1='30' y1='1' x2='30' y2='11' stroke='#9CA3AF' stroke-width='1'/><rect x='30' y='3' width='{abs(x-30)}' height='6' fill='{color}' transform='scale({1 if d>=0 else -1},1) translate({0 if d>=0 else -60},0)'></rect></svg>"

def _kpi_bars_html(score) -> str:
    order = ["digitalisierung","automatisierung","compliance","prozessreife","innovation"]
    labels = {"digitalisierung":"Digitalisierung","automatisierung":"Automatisierung","compliance":"Compliance","prozessreife":"Prozessreife","innovation":"Innovation"}
    rows = []
    for k in order:
        v = score.kpis[k]["value"]; m = score.kpis[k]["benchmark"]; d = score.kpis[k]["delta"]
        rows.append(f"<div class='bar'><div class='label'>{labels[k]}</div><div class='bar__track'><div class='bar__fill' style='width:{max(0,min(100,int(round(v))))}%;'></div><div class='bar__median' style='left:{max(0,min(100,int(round(m))))}%;'></div></div><div class='bar__delta'>{'+' if d>=0 else ''}{int(round(d))} pp {_spark_delta(d)}</div></div>")
    return "<div class='kpi'>" + "".join(rows) + "</div>"

def _benchmark_table_html(score) -> str:
    labels = {"digitalisierung":"Digitalisierung","automatisierung":"Automatisierung","compliance":"Compliance","prozessreife":"Prozessreife","innovation":"Innovation"}
    head = "<table class='bm'><thead><tr><th>KPI</th><th>Ihr Wert</th><th>Branchen‑Benchmark</th><th>Δ (pp)</th><th>Trend</th></tr></thead><tbody>"
    rows = []
    for k, lab in labels.items():
        v = score.kpis[k]["value"]; m = score.kpis[k]["benchmark"]; d = score.kpis[k]["delta"]
        rows.append(f"<tr><td>{lab}</td><td>{int(round(v))}%</td><td>{int(round(m))}%</td><td>{'+' if d>=0 else ''}{int(round(d))}</td><td>{_spark_delta(d)}</td></tr>")
    return head + "".join(rows) + "</tbody></table>"

def _profile_html(n) -> str:
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

def _read_docx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(str(path), "r") as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
        root = ET.fromstring(xml)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        parts: List[str] = []
        for p in root.findall(".//w:body/w:p", ns):
            text = "".join(t.text or "" for t in p.findall(".//w:t", ns)).strip()
            if text:
                parts.append(f"<p>{text}</p>")
        return "\n".join(parts)
    except Exception:
        return ""

def _guides_html(lang: str) -> str:
    blocks: List[str] = []
    if lang.startswith("de"):
        # Bevorzugt .html, Fallback .docx
        for name in ["4-Saeulen-KI-Readiness.html", "rechtliche-Stolpersteine-KI-im-Unternehmen.html", "Formel-fuer-Transformation.html"]:
            p = CONTENT_DIR / name
            if p.exists():
                blocks.append(_read_text(p))
        # Fallback: .docx -> simple HTML
        if not blocks:
            for docx in ["4-Saeulen-KI-Readiness.docx","rechtliche-Stolpersteine-KI-im-Unternehmen.docx","Formel-fuer-Transformation.docx"]:
                p = CONTENT_DIR / docx
                if p.exists():
                    blocks.append(_read_docx_text(p))
    else:
        for name in ["4-pillars-ai-readiness.en.html","legal-pitfalls-ai.en.html","transformation-formula-10-20-70.en.html"]:
            p = CONTENT_DIR / name
            if p.exists():
                blocks.append(_read_text(p))
    if not blocks:
        return ""
    hdr = "<h2>Guides & Checklisten</h2>"
    return "<section class='guides'>" + hdr + "".join(blocks) + "</section>"

def _sources_footer_html(news, tools, funding, lang: str) -> str:
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
            lis.append(f"<li><a href='{url}'>{title_}</a> – <span class='muted'>{dom} {when}</span></li>")
        return "<ul class='source-list'>" + "".join(lis) + "</ul>"
    return "<div class='grid'>" + "<div><h4>News</h4>" + _mk(news,"News") + "</div>" + "<div><h4>Tools</h4>" + _mk(tools,"Tools") + "</div>" + "<div><h4>" + ("Förderungen" if lang.startswith("de") else "Funding") + "</h4>" + _mk(funding,"Förderungen") + "</div>" + "</div>"

# ---------------- Glue ----------------
def build_html_report(raw: Dict[str, Any], lang: str = "de") -> Dict[str, Any]:
    n = normalize_briefing(raw, lang=lang)
    score = compute_scores(n)
    case = business_case(n)

    # Live
    q_news = f"Aktuelle KI-News in der Branche {n.branche_label} (letzte {SEARCH_DAYS_NEWS} Tage). Titel, Domain, URL, Datum."
    q_tools = f"Relevante KI-Tools/Anbieter für {n.branche_label}, Größe {n.unternehmensgroesse_label}. Titel, Domain, URL, Datum."
    q_fund = f"Förderprogramme in {n.bundesland_code} (Digitalisierung/KI) – offen/laufend, Fristen innerhalb {SEARCH_DAYS_FUNDING} Tagen."

    news = tools = funding = []
    if websearch_utils:
        try:
            news = websearch_utils.perplexity_search(q_news, max_results=LIVE_MAX_ITEMS) + websearch_utils.tavily_search(q_news, max_results=LIVE_MAX_ITEMS, days=SEARCH_DAYS_NEWS)
            tools = websearch_utils.perplexity_search(q_tools, max_results=LIVE_MAX_ITEMS) + websearch_utils.tavily_search(q_tools, max_results=LIVE_MAX_ITEMS, days=SEARCH_DAYS_TOOLS)
            funding = websearch_utils.perplexity_search(q_fund, max_results=max(LIVE_MAX_ITEMS, 10)) + websearch_utils.tavily_search(q_fund, max_results=max(LIVE_MAX_ITEMS, 10), days=SEARCH_DAYS_FUNDING)
        except Exception as exc:
            log.warning("hybrid_live failed: %s", exc)

    news = filter_and_rank(news)[:LIVE_MAX_ITEMS]
    tools = filter_and_rank(tools)[:LIVE_MAX_ITEMS]
    funding = filter_and_rank(funding)[:max(LIVE_MAX_ITEMS, 10)]

    ctx = {
        "briefing": {"branche": n.branche, "branche_label": n.branche_label, "unternehmensgroesse": n.unternehmensgroesse, "unternehmensgroesse_label": n.unternehmensgroesse_label, "bundesland_code": n.bundesland_code, "hauptleistung": n.hauptleistung, "pull_kpis": n.pull_kpis},
        "scoring": {"score_total": score.total, "badge": score.badge, "kpis": score.kpis, "weights": score.weights},
        "benchmarks": score.benchmarks,
        "tools": tools,
        "funding": funding,
        "business": {"invest_eur": case.invest_eur, "save_year_eur": case.save_year_eur, "payback_months": case.payback_months, "roi_year1_pct": case.roi_year1_pct},
    }

    # Overlays
    sec = lambda name: render_overlay(name, lang, ctx) or ""
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

    tpl = _template(lang)
    report_date = os.getenv("REPORT_DATE_OVERRIDE") or date.today().isoformat()

    guides = _guides_html(lang)

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
           .replace("{{GUIDES_HTML}}", guides)
           .replace("{{SOURCES_FOOTER_HTML}}", _sources_footer_html(news, tools, funding, lang))
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

def produce_admin_attachments(raw: Dict[str, Any], lang: str = "de") -> Dict[str, str]:
    try:
        norm = normalize_briefing(raw, lang=lang)
    except Exception as exc:  # pragma: no cover
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
