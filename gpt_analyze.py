# gpt_analyze.py
# -*- coding: utf-8 -*-
"""
Analyzer für KI-Status-Report (Gold-Standard+)

Neuerungen in dieser Fassung:
- Live-Layer: Tavily **und** Perplexity als zweite Quelle; Dedup & Ranking.
- Benchmarks: flexible Suche in /data (branchenspezifisch + größenbasiert, CSV/JSON).
- Platzhalter-Killer: füllt/entfernt übrig gebliebene Tokens ([Branche], {{…}}) sicher.
- Listen/Links: Titel – Quelle, Datum (Domain) + Berlin-Badge.
- **NEU:** Prompt-Override für „tools“ & „foerderprogramme“ (falls Prompts vorhanden); Fallback bleibt HTML-Listendarstellung.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger("gpt_analyze")
if not log.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    log.addHandler(h)
log.setLevel(logging.INFO)

# ----------------------------- ENV / Defaults -------------------------------

BASE_DIR = os.path.abspath(os.getenv("APP_BASE", os.getcwd()))
PROMPTS_DIR = os.getenv("PROMPTS_DIR", os.path.join(BASE_DIR, "prompts"))
TEMPLATE_DIR = os.getenv("TEMPLATE_DIR", os.path.join(BASE_DIR, "templates"))
TEMPLATE_DE = os.getenv("TEMPLATE_DE", "pdf_template.html")
TEMPLATE_EN = os.getenv("TEMPLATE_EN", "pdf_template_en.html")
ASSETS_BASE_URL = os.getenv("ASSETS_BASE_URL", "templates")
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_APIKEY") or ""
OPENAI_MODEL = os.getenv("OPENAI_MODEL_DEFAULT", "gpt-4o")
EXEC_SUMMARY_MODEL = os.getenv("EXEC_SUMMARY_MODEL", OPENAI_MODEL)
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "45"))
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "1200"))
GPT_TEMPERATURE = float(os.getenv("GPT_TEMPERATURE", "0.2"))

# Live search
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")
PERPLEXITY_MODEL = os.getenv("PERPLEXITY_MODEL", "sonar-small-online")  # Zweitquelle

ROI_BASELINE_MONTHS = float(os.getenv("ROI_BASELINE_MONTHS", "4"))
SEARCH_DAYS_NEWS = int(os.getenv("SEARCH_DAYS_NEWS", "7"))
SEARCH_DAYS_NEWS_FALLBACK = int(os.getenv("SEARCH_DAYS_NEWS_FALLBACK", "30"))
SEARCH_DAYS_TOOLS = int(os.getenv("SEARCH_DAYS_TOOLS", "30"))
SEARCH_DAYS_FUNDING = int(os.getenv("SEARCH_DAYS_FUNDING", "60"))
LIVE_MAX_ITEMS = int(os.getenv("LIVE_MAX_ITEMS", "6"))

# ----------------------------- Helpers --------------------------------------

def _read_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as exc:
        log.warning("read failed %s: %s", path, exc)
        return ""

def _template_for_lang(lang: str) -> str:
    fname = TEMPLATE_DE if lang.startswith("de") else TEMPLATE_EN
    path = os.path.join(TEMPLATE_DIR, fname)
    if not os.path.exists(path):
        path = os.path.join(TEMPLATE_DIR, "pdf_template.html")
    return _read_file(path)

def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

def _strip_llm(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"```[a-zA-Z0-9]*\s*", "", text).replace("```", "")
    return text.strip()

def _as_fragment(html: str) -> str:
    """Entfernt Doctype/HTML/HEAD/BODY/STYLE, so dass ein valider Fragment-Block übrig bleibt."""
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

def _fill_placeholders(html: str, b: Dict[str, Any]) -> str:
    """Ersetzt übrig gebliebene Platzhalter höflich."""
    if not html:
        return html
    branche = b.get("branche_label") or b.get("branche") or "—"
    groesse = b.get("unternehmensgroesse_label") or b.get("unternehmensgroesse") or "—"
    hl = b.get("hauptleistung") or "—"

    # heuristisch Top-2 Hebel nach Delta zum Benchmark
    kpis = {
        "digitalisierung": b.get("kpi_digitalisierung"),
        "automatisierung": b.get("kpi_automatisierung"),
        "compliance": b.get("kpi_compliance"),
        "prozessreife": b.get("kpi_prozessreife"),
        "innovation": b.get("kpi_innovation"),
    }
    deltas = []
    for k, v in kpis.items():
        try:
            deltas.append((k, abs(float(v) - 60.0)))
        except Exception:
            pass
    deltas.sort(key=lambda x: x[1], reverse=True)
    map_de = {
        "digitalisierung": "Digitalisierung",
        "automatisierung": "Automatisierung",
        "compliance": "Compliance",
        "prozessreife": "Prozessreife",
        "innovation": "Innovation",
    }
    top2 = " & ".join([map_de.get(d[0], d[0].title()) for d in deltas[:2]]) or "Digitalisierung & Compliance"

    repl = {
        "[Branche]": str(branche),
        "[Größe]": str(groesse),
        "[Hauptleistung]": str(hl),
        "[wichtigste Δ‑Hebel]": top2,
        "{{ hauptleistung }}": str(hl),
    }
    for k, v in repl.items():
        html = html.replace(k, v)

    # Rest freundlich tilgen
    html = re.sub(r"\[[^\]]+\]", "", html)
    html = re.sub(r"\{\{[^}]+\}\}", "", html)
    return html

def _load_prompt(lang: str, name: str) -> str:
    cand = [
        os.path.join(PROMPTS_DIR, lang, f"{name}_{lang}.md"),
        os.path.join(PROMPTS_DIR, lang, f"{name}.md"),
        os.path.join(PROMPTS_DIR, f"{name}_{lang}.md"),
        os.path.join(PROMPTS_DIR, f"{name}.md"),
    ]
    for p in cand:
        if os.path.exists(p):
            log.info("gpt_analyze: Loaded prompt: %s", os.path.relpath(p, PROMPTS_DIR))
            return _read_file(p)
    log.info("gpt_analyze: Prompt missing for '%s' (%s) → empty section", name, lang)
    return ""

def _badge(total: float) -> str:
    if total >= 85:
        return "EXCELLENT"
    if total >= 70:
        return "GOOD"
    if total >= 55:
        return "FAIR"
    return "BASIC"

def _sanitize_pct(v: Any) -> float:
    try:
        return max(0.0, min(100.0, float(v)))
    except Exception:
        return 0.0

def _parse_percent_bucket(val: Any) -> int:
    s = str(val or "").lower()
    if "81" in s:
        return 90
    if "61" in s:
        return 70
    if "41" in s:
        return 50
    if "21" in s:
        return 30
    if "0" in s:
        return 10
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

def normalize_briefing(raw: Dict[str, Any], lang: str = "de") -> Dict[str, Any]:
    """Formulardaten vereinheitlichen und KPIs ableiten."""
    b: Dict[str, Any] = dict(raw or {})
    if isinstance(raw, dict) and isinstance(raw.get("answers"), dict):
        for k, v in raw["answers"].items():
            b.setdefault(k, v)

    # Labels & Codes
    branche_map = {
        "marketing": "Marketing & Werbung", "beratung": "Beratung", "it": "IT & Software",
        "finanzen": "Finanzen & Versicherungen", "handel": "Handel & E‑Commerce", "bildung": "Bildung",
        "verwaltung": "Verwaltung", "gesundheit": "Gesundheit & Pflege", "bau": "Bauwesen & Architektur",
        "medien": "Medien & Kreativwirtschaft", "industrie": "Industrie & Produktion", "logistik": "Transport & Logistik",
    }
    size_map = {"solo": "solo", "team": "2–10", "kmu": "11–100"}

    b["branche"] = str(b.get("branche") or "beratung").lower()
    b["branche_label"] = b.get("branche_label") or branche_map.get(b["branche"], b["branche"].title())
    b["unternehmensgroesse"] = str(b.get("unternehmensgroesse") or "solo").lower()
    b["unternehmensgroesse_label"] = b.get("unternehmensgroesse_label") or size_map.get(b["unternehmensgroesse"], b["unternehmensgroesse"])
    b["bundesland_code"] = (b.get("bundesland_code") or b.get("bundesland") or "DE").upper()
    b["hauptleistung"] = b.get("hauptleistung") or "Beratung/Service"

    # Pull-KPIs + Top-Level Korrektur
    top_use = str(b.get("usecase_priority") or "")
    if not top_use and isinstance(b.get("ki_usecases"), list) and b["ki_usecases"]:
        top_use = str(b["ki_usecases"][0])
    if not b.get("umsatzziel") and b.get("jahresumsatz"):
        b["umsatzziel"] = b["jahresumsatz"]
    b["pull_kpis"] = {
        "umsatzziel": b.get("umsatzziel") or b.get("jahresumsatz") or "",
        "top_use_case": top_use,
        "zeitbudget": b.get("zeitbudget") or "",
    }

    # KPIs ableiten
    k = _derive_kpis(b)
    for key, val in k.items():
        b[f"kpi_{key}"] = val
    return b

def _kpi_synonyms(k: str) -> str:
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

def _load_benchmarks(branche: str, groesse: str) -> Dict[str, float]:
    """
    Benchmarks aus /data laden (JSON oder CSV). Fallback-Reihenfolge:
    1) data/benchmarks_{branche}_{groesse}.{json,csv}
    2) data/benchmarks_{branche}.{json,csv}
    3) data/benchmarks_{groesse}.{json,csv}
    4) data/benchmarks_{global|default}.{json,csv}
    5) Default 60 % für alle KPIs
    """
    patterns = [
        f"benchmarks_{branche}_{groesse}",
        f"benchmarks_{branche}",
        f"benchmarks_{groesse}",
        "benchmarks_global",
        "benchmarks_default",
        "benchmarks",
    ]
    out: Dict[str, float] = {}
    for base in patterns:
        for ext in (".json", ".csv"):
            path = os.path.join(DATA_DIR, f"{base}{ext}")
            if not os.path.exists(path):
                continue
            try:
                if ext == ".json":
                    data = json.loads(_read_file(path) or "{}")
                    for k, v in (data or {}).items():
                        try:
                            out[_kpi_synonyms(k)] = float(v)
                        except Exception:
                            pass
                else:
                    with open(path, "r", encoding="utf-8") as f:
                        for row in csv.DictReader(f):
                            k = _kpi_synonyms((row.get("kpi") or row.get("name") or "").strip())
                            v = row.get("value") or row.get("pct") or row.get("percent") or ""
                            try:
                                out[k] = float(str(v).replace("%", "").strip())
                            except Exception:
                                pass
                if out:
                    return out
            except Exception as exc:
                log.warning("Benchmark-Import fehlgeschlagen (%s): %s", path, exc)
    # Fallback
    return {k: 60.0 for k in ["digitalisierung", "automatisierung", "compliance", "prozessreife", "innovation"]}

@dataclass
class ScorePack:
    total: int
    badge: str
    kpis: Dict[str, Dict[str, float]]
    weights: Dict[str, float]
    benchmarks: Dict[str, float]

def compute_scores(b: Dict[str, Any]) -> ScorePack:
    weights = {k: 0.2 for k in ("digitalisierung", "automatisierung", "compliance", "prozessreife", "innovation")}
    bm = _load_benchmarks(b.get("branche", "beratung"), b.get("unternehmensgroesse", "solo"))
    vals = {
        "digitalisierung": _sanitize_pct(b.get("kpi_digitalisierung")),
        "automatisierung": _sanitize_pct(b.get("kpi_automatisierung")),
        "compliance": _sanitize_pct(b.get("kpi_compliance")),
        "prozessreife": _sanitize_pct(b.get("kpi_prozessreife")),
        "innovation": _sanitize_pct(b.get("kpi_innovation")),
    }
    kpis: Dict[str, Dict[str, float]] = {}
    total = 0.0
    for k, v in vals.items():
        m = float(bm.get(k, 60.0))
        d = v - m
        kpis[k] = {"value": v, "benchmark": m, "delta": d}
        total += weights[k] * v
    t = int(round(total))
    return ScorePack(total=t, badge=_badge(t), kpis=kpis, weights=weights, benchmarks=bm)

# ----------------------------- Business Case --------------------------------

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

def business_case(b: Dict[str, Any], score: ScorePack) -> BusinessCase:
    invest = _parse_invest(b.get("investitionsbudget"), 6000.0)
    monthly = invest / max(1.0, ROI_BASELINE_MONTHS)
    save_year = monthly * 12.0
    payback_m = invest / max(1.0, monthly)
    roi_y1 = (save_year - invest) / invest * 100.0
    return BusinessCase(round(invest, 2), round(save_year, 2), round(payback_m, 1), round(roi_y1, 1))

# ----------------------------- LLM / Prompts --------------------------------

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
    except Exception as exc:
        log.warning("LLM call failed: %s", exc)
        return ""

def render_section(name: str, lang: str, ctx: Dict[str, Any]) -> str:
    prompt = _load_prompt(lang, name)
    if not prompt:
        return ""
    system = "Du bist ein präziser, risikobewusster Assistent. Antworte ausschließlich als sauberes HTML-Fragment ohne <html>/<head>/<body>."
    if not lang.startswith("de"):
        system = "You are a precise, risk-aware assistant. Respond as clean HTML fragment only (no <html>/<head>/<body>)."
    user = (
        prompt.replace("{{BRIEFING_JSON}}", _json(ctx.get("briefing", {})))
        .replace("{{SCORING_JSON}}", _json(ctx.get("scoring", {})))
        .replace("{{BENCHMARKS_JSON}}", _json(ctx.get("benchmarks", {})))
        .replace("{{TOOLS_JSON}}", _json(ctx.get("tools", [])))
        .replace("{{FUNDING_JSON}}", _json(ctx.get("funding", [])))
        .replace("{{BUSINESS_JSON}}", _json(ctx.get("business", {})))
    )
    out = _openai_chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        model=EXEC_SUMMARY_MODEL if name == "executive_summary" else OPENAI_MODEL,
    )
    out = _minify_html_soft(_as_fragment(out))
    return out

# ----------------------------- Live Layer -----------------------------------

def _dt_iso(days_back: int) -> str:
    return (datetime.utcnow() - timedelta(days=days_back)).date().isoformat()

def _tavily_query(q: str, max_results: int) -> List[Dict[str, Any]]:
    if not TAVILY_API_KEY:
        return []
    url = "https://api.tavily.com/search"
    payload = {"api_key": TAVILY_API_KEY, "query": q, "max_results": max_results, "include_answer": False}
    delays = (0.0, 0.6, 1.2)
    for i, d in enumerate(delays):
        try:
            if d:
                import time as _time
                _time.sleep(d)
            with httpx.Client(timeout=8.0) as cli:
                r = cli.post(url, json=payload)
                if r.status_code == 401:
                    log.warning("Tavily 401 (attempt %s)", i + 1)
                    continue
                r.raise_for_status()
                data = r.json() or {}
                results = []
                for it in data.get("results", [])[:max_results]:
                    results.append({
                        "title": it.get("title") or it.get("url"),
                        "url": it.get("url"),
                        "source": it.get("source") or "Tavily",
                        "domain": (it.get("url") or "").split("/")[2] if "://" in (it.get("url") or "") else "",
                        "date": it.get("published_date") or "",
                    })
                return results
        except Exception as exc:
            log.warning("Tavily attempt %s failed: %s", i + 1, exc)
    return []

def _perplexity_query(prompt: str, max_items: int = 6) -> List[Dict[str, Any]]:
    """Zweitquelle – wird zusätzlich genutzt (nicht nur Fallback)."""
    if not PERPLEXITY_API_KEY:
        return []
    url = "https://api.perplexity.ai/chat/completions"
    headers = {"Authorization": f"Bearer {PERPLEXITY_API_KEY}", "Content-Type": "application/json"}
    messages = [
        {"role": "system", "content": "Return concise bullet JSON with items: title, url, source, date."},
        {"role": "user", "content": f"Give top {max_items} up-to-date items with title, url, source, date. Query: {prompt}"},
    ]
    try:
        with httpx.Client(timeout=10.0) as cli:
            r = cli.post(url, headers=headers, json={"model": PERPLEXITY_MODEL, "messages": messages, "max_tokens": 500})
            r.raise_for_status()
            data = r.json()
            content = (((data.get("choices") or [{}])[0]).get("message") or {}).get("content") or ""
            m = re.search(r"\[.*\]", content, flags=re.S)
            if not m:
                return []
            arr = json.loads(m.group(0))
            out = []
            for it in arr[:max_items]:
                url_ = it.get("url")
                out.append({
                    "title": it.get("title") or url_,
                    "url": url_,
                    "source": it.get("source") or "Perplexity",
                    "domain": (url_ or "").split("/")[2] if "://" in (url_ or "") else "",
                    "date": it.get("date") or "",
                })
            return out
    except Exception as exc:
        log.warning("Perplexity call failed: %s", exc)
    return []

def _merge_rank(items1: List[Dict[str, Any]], items2: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    def key(it: Dict[str, Any]) -> str:
        u = (it.get("url") or "").split("?")[0].strip().lower()
        if u:
            return u
        return (it.get("title") or "").strip().lower()

    def parse_dt(s: str) -> datetime:
        try:
            s = s.replace("Z", "")
            return datetime.fromisoformat(s)
        except Exception:
            return datetime.min

    seen = set()
    out: List[Dict[str, Any]] = []
    for arr in (items1, items2):
        for it in arr:
            k = key(it)
            if not k or k in seen:
                continue
            seen.add(k)
            out.append(it)

    # sortiere neueste zuerst (falls Datum vorhanden)
    out.sort(key=lambda x: parse_dt(str(x.get("date") or "")), reverse=True)
    return out[:limit]

def _dedup_by_url(items: List[Dict[str, Any]], limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Einfache Deduplizierung nach URL (ohne Querystring) oder Titel."""
    seen = set()
    out: List[Dict[str, Any]] = []
    for it in items or []:
        url = (it.get("url") or "").split("?")[0].strip().lower()
        title = (it.get("title") or it.get("name") or "").strip().lower()
        key = url or title
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(it)
    if limit is not None:
        return out[:limit]
    return out

def _live_search(topic: str, b: Dict[str, Any], max_results: int, short_days: int, long_days: int) -> List[Dict[str, Any]]:
    """Sucht live Inhalte; kombiniert Tavily + Perplexity; dann Dedup/Ranking."""
    branche = b.get("branche_label") or b.get("branche") or ""
    region = b.get("bundesland_code") or ""
    if topic == "news":
        q1 = f"KI {branche} aktuelle Nachrichten {region}".strip()
        tv = _tavily_query(q1, max_results)
        px = _perplexity_query(q1, max_results)
        if not (tv or px):
            q2 = f"KI {branche} News"
            tv = _tavily_query(q2, max_results)
            px = _perplexity_query(q2, max_results)
        return _merge_rank(tv, px, max_results)
    if topic == "tools":
        q = f"KI Tools {branche} Unternehmen"
        tv = _tavily_query(q, max_results)
        px = _perplexity_query(q, max_results)
        return _merge_rank(tv, px, max_results)
    if topic == "funding":
        q = f"Förderung Digitalisierung {region} KMU"
        tv = _tavily_query(q, max_results)
        px = _perplexity_query(q, max_results)
        return _merge_rank(tv, px, max_results)
    return []

# ----------------------------- HTML blocks ----------------------------------

def _kpi_bars_html(score: ScorePack) -> str:
    order = ["digitalisierung", "automatisierung", "compliance", "prozessreife", "innovation"]
    labels = {
        "digitalisierung": "Digitalisierung",
        "automatisierung": "Automatisierung",
        "compliance": "Compliance",
        "prozessreife": "Prozessreife",
        "innovation": "Innovation",
    }
    rows = []
    for k in order:
        v = score.kpis[k]["value"]
        m = score.kpis[k]["benchmark"]
        d = score.kpis[k]["delta"]
        rows.append(
            f"<div class='bar'><div class='label'>{labels[k]}</div>"
            f"<div class='bar__track'><div class='bar__fill' style='width:{max(0,min(100,v))}%;'></div>"
            f"<div class='bar__median' style='left:{max(0,min(100,m))}%;'></div></div>"
            f"<div class='bar__delta'>{'+' if d>=0 else ''}{int(round(d))} pp</div></div>"
        )
    return "<div class='kpi'>" + "".join(rows) + "</div>"

def _benchmark_table_html(score: ScorePack) -> str:
    head = "<table class='bm'><thead><tr><th>KPI</th><th>Ihr Wert</th><th>Branchen‑Benchmark</th><th>Δ (pp)</th></tr></thead><tbody>"
    labels = {
        "digitalisierung": "Digitalisierung",
        "automatisierung": "Automatisierung",
        "compliance": "Compliance",
        "prozessreife": "Prozessreife",
        "innovation": "Innovation",
    }
    rows = []
    for k, lab in labels.items():
        v = score.kpis[k]["value"]
        m = score.kpis[k]["benchmark"]
        d = score.kpis[k]["delta"]
        rows.append(f"<tr><td>{lab}</td><td>{int(round(v))}%</td><td>{int(round(m))}%</td><td>{'+' if d>=0 else ''}{int(round(d))}</td></tr>")
    return head + "".join(rows) + "</tbody></table>"

def business_case_html(case: BusinessCase, lang: str) -> str:
    t_inv = "Investition" if lang.startswith("de") else "Investment"
    t_sav = "Einsparung/Jahr" if lang.startswith("de") else "Saving/year"
    t_pay = "Payback"
    t_roi = "ROI Jahr 1" if lang.startswith("de") else "ROI Year 1"
    return (
        "<div class='card'><h2>Business Case</h2>"
        f"<div class='pill'>⏱️ Baseline Payback ≈ {int(ROI_BASELINE_MONTHS)} Monate</div>"
        "<div class='columns'><div><ul>"
        f"<li>{t_inv}: {case.invest_eur:,.2f} €</li>"
        f"<li>{t_sav}: {case.save_year_eur:,.2f} €</li>"
        f"<li>{t_pay}: {case.payback_months:.1f} Monate</li>"
        f"<li>{t_roi}: {case.roi_year1_pct:.1f}%</li>"
        "</ul></div><div class='footnotes'>Annahme: Zeitersparnis aus 1–2 priorisierten Automatisierungen entlang der Hauptleistung.</div></div></div>"
    )

def _profile_html(b: Dict[str, Any]) -> str:
    pl = b.get("pull_kpis", {}) or {}
    pills = []
    if pl.get("umsatzziel"):
        pills.append(f"<span class='pill'>Umsatzziel: {pl['umsatzziel']}</span>")
    if pl.get("top_use_case"):
        pills.append(f"<span class='pill'>Top‑Use‑Case: {pl['top_use_case']}</span>")
    if pl.get("zeitbudget"):
        pills.append(f"<span class='pill'>Zeitbudget: {pl['zeitbudget']}</span>")
    pills_html = " ".join(pills) if pills else "<span class='muted'>—</span>"
    return (
        "<div class='card'><h2>Unternehmensprofil & Ziele</h2>"
        f"<p><span class='hl'>Hauptleistung:</span> {b.get('hauptleistung','—')} "
        f"<span class='muted'>&middot; Branche:</span> {b.get('branche_label','—')} "
        f"<span class='muted'>&middot; Größe:</span> {b.get('unternehmensgroesse_label','—')}</p>"
        f"<p>{pills_html}</p></div>"
    )

def _list_html(items: List[Dict[str, Any]], empty_msg: str, berlin_badge: bool = False) -> str:
    if not items:
        return f"<div class='muted'>{empty_msg}</div>"
    lis = []
    for it in items:
        title = it.get("title") or it.get("name") or it.get("url")
        url = it.get("url") or "#"
        src = it.get("source") or (it.get("domain") or "")
        when = it.get("date") or ""
        dom = it.get("domain") or (url.split('/')[2] if '://' in url else "")
        extra = " <span class='flag-berlin'>Land Berlin</span>" if (berlin_badge and any(d in (url or "") for d in ("berlin.de", "ibb.de"))) else ""
        lis.append(f"<li><a href='{url}'>{title}</a> – <span class='muted'>{src or dom} {when}</span>{extra}</li>")
    return "<ul>" + "".join(lis) + "</ul>"

# ----------------------------- Assemble -------------------------------------

def analyze_briefing(raw: Dict[str, Any], lang: str = "de") -> str:
    """Zentrale Render-Funktion: erzeugt vollständiges HTML für den Report."""
    b = normalize_briefing(raw, lang=lang)
    score = compute_scores(b)
    case = business_case(b, score)

    # Live-Daten (Kombination: Tavily + Perplexity)
    news_live = _live_search("news", b, LIVE_MAX_ITEMS, SEARCH_DAYS_NEWS, SEARCH_DAYS_NEWS_FALLBACK)
    tools_live = _live_search("tools", b, LIVE_MAX_ITEMS, SEARCH_DAYS_TOOLS, SEARCH_DAYS_NEWS_FALLBACK)
    funding_live = _live_search("funding", b, LIVE_MAX_ITEMS, SEARCH_DAYS_FUNDING, SEARCH_DAYS_NEWS_FALLBACK)

    # Lokale Tools/Förderungen (Whitelist etc.)
    try:
        from tools_loader import filter_tools  # type: ignore
        tools_local = filter_tools(industry=b.get("branche"), company_size=b.get("unternehmensgroesse"), limit=8)
    except Exception as exc:
        log.info("tools_loader not available: %s", exc)
        tools_local = []

    try:
        from funding_loader import filter_funding  # type: ignore
        funding_local = filter_funding(region=b.get("bundesland_code", "DE"), limit=10)
    except Exception as exc:
        log.info("funding_loader not available: %s", exc)
        funding_local = []

    # Kombinierte Listen (live + lokal) deduplizieren
    tools_items = _dedup_by_url((tools_live or []) + (tools_local or []), limit=LIVE_MAX_ITEMS)
    funding_items = _dedup_by_url((funding_live or []) + (funding_local or []), limit=max(LIVE_MAX_ITEMS, 10))

    ctx = {
        "briefing": b,
        "scoring": {"score_total": score.total, "badge": score.badge, "kpis": score.kpis, "weights": score.weights},
        "benchmarks": score.benchmarks,
        "tools": tools_items,      # wichtig: an Prompts durchreichen
        "funding": funding_items,  # wichtig: an Prompts durchreichen
        "business": case.__dict__,
    }

    # LLM-Sections
    sec = lambda n: render_section(n, lang, ctx) or ""
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

    # **Prompt-Override für Tools/Förderungen** (wenn Prompt-Dateien vorhanden)
    tools_block = render_section("tools", lang, ctx) or (
        _list_html(tools_items, "Keine passenden Tools gefunden." if lang.startswith("de") else "No matching tools.")
    )
    funding_block = render_section("foerderprogramme", lang, ctx) or (
        _list_html(funding_items, "Keine aktuellen Einträge." if lang.startswith("de") else "No current items.", berlin_badge=True)
    )

    # Template
    tpl = _template_for_lang(lang)
    report_date = os.getenv("REPORT_DATE_OVERRIDE") or date.today().isoformat()

    filled = (
        tpl.replace("{{LANG}}", "de" if lang.startswith("de") else "en")
        .replace("{{ASSETS_BASE}}", ASSETS_BASE_URL)
        .replace("{{BRANCHE_LABEL}}", b["branche_label"])
        .replace("{{GROESSE_LABEL}}", b["unternehmensgroesse_label"])
        .replace("{{STAND_DATUM}}", report_date)
        .replace("{{SCORE_PERCENT}}", f"{score.total}%")
        .replace("{{SCORE_BADGE}}", score.badge)
        .replace("{{KPI_BARS_HTML}}", _kpi_bars_html(score))
        .replace("{{BUSINESS_CASE_HTML}}", business_case_html(case, lang))
        .replace("{{PROFILE_HTML}}", _profile_html(b))
        .replace("{{BENCHMARK_TABLE_HTML}}", _benchmark_table_html(score))
        .replace("{{EXEC_SUMMARY_HTML}}", _lede_html(score, case, lang) + exec_llm)
        .replace("{{QUICK_WINS_HTML}}", quick)
        .replace("{{ROADMAP_HTML}}", roadmap)
        .replace("{{RISKS_HTML}}", risks)
        .replace("{{COMPLIANCE_HTML}}", compliance)
        .replace("{{NEWS_HTML}}", _list_html(news_live, "Keine aktuellen News (30 Tage geprüft)." if lang.startswith("de") else "No recent news (30 days)."))
        .replace("{{TOOLS_HTML}}", tools_block)          # ← Override wired in
        .replace("{{FUNDING_HTML}}", funding_block)      # ← Override wired in
        .replace("{{RECOMMENDATIONS_BLOCK}}", f"<section class='card'><h2>Recommendations</h2>{recs}<div class='meta'>{'Stand' if lang.startswith('de') else 'As of'}: {report_date}</div></section>")
        .replace("{{GAMECHANGER_BLOCK}}", f"<section class='card'><h2>Gamechanger</h2>{game}<div class='meta'>{'Stand' if lang.startswith('de') else 'As of'}: {report_date}</div></section>")
        .replace("{{VISION_BLOCK}}", f"<section class='card'><h2>Vision</h2>{vision}<div class='meta'>{'Stand' if lang.startswith('de') else 'As of'}: {report_date}</div></section>")
        .replace("{{PERSONA_BLOCK}}", f"<section class='card'><h2>Persona</h2>{persona}<div class='meta'>{'Stand' if lang.startswith('de') else 'As of'}: {report_date}</div></section>")
        .replace("{{PRAXIS_BLOCK}}", f"<section class='card'><h2>Praxisbeispiel</h2>{praxis}<div class='meta'>{'Stand' if lang.startswith('de') else 'As of'}: {report_date}</div></section>")
        .replace("{{COACH_BLOCK}}", f"<section class='card'><h2>Coach</h2>{coach}<div class='meta'>{'Stand' if lang.startswith('de') else 'As of'}: {report_date}</div></section>")
        .replace("{{DOC_DIGEST_BLOCK}}", digest or "")
    )

    # >>> Platzhalter freundlich schließen
    filled = _fill_placeholders(filled, b)
    return filled

def _lede_html(score: ScorePack, case: BusinessCase, lang: str) -> str:
    labels = {
        "digitalisierung": "Digitalisierung",
        "automatisierung": "Automatisierung",
        "compliance": "Compliance",
        "prozessreife": "Prozessreife",
        "innovation": "Innovation",
    }
    deltas = sorted(((k, abs(v["delta"])) for k, v in score.kpis.items()), key=lambda x: x[1], reverse=True)
    top = [labels[deltas[0][0]], labels[deltas[1][0]]] if len(deltas) >= 2 else ["Automatisierung", "Compliance"]
    if lang.startswith("de"):
        return (
            "<div class='lede'>"
            f"<p class='keyline'><strong>Kernaussage 1:</strong> Der KI‑Readiness‑Score beträgt "
            f"<strong>{score.total}%</strong> (Badge: <strong>{score.badge}</strong>); größte Hebel: "
            f"<em>{top[0]}</em> und <em>{top[1]}</em>.</p>"
            f"<p class='keyline'><strong>Kernaussage 2:</strong> Mit 1–2 priorisierten Automatisierungen ist ein "
            f"<strong>Payback ≤ {int(round(case.payback_months))} Monate</strong> realistisch.</p>"
            "</div>"
        )
    return (
        "<div class='lede'>"
        f"<p class='keyline'><strong>Keyline 1:</strong> KI‑readiness is <strong>{score.total}%</strong> "
        f"(badge <strong>{score.badge}</strong>); main levers: <em>{top[0]}</em> &amp; <em>{top[1]}</em>.</p>"
        f"<p class='keyline'><strong>Keyline 2:</strong> With 1–2 prioritized automations a "
        f"<strong>payback ≤ {int(round(case.payback_months))} months</strong> is realistic.</p>"
        "</div>"
    )

# Backward compat
def analyze_briefing_enhanced(raw: Dict[str, Any], lang: str = "de") -> str:
    return analyze_briefing(raw, lang=lang)

def produce_admin_attachments(raw: Dict[str, Any]) -> Dict[str, str]:
    """Diagnose-Anhänge (JSON) für Admin-Mails."""
    import json as _jsonlib
    try:
        b = dict(raw or {})
    except Exception:
        b = {"_note": "non-dict raw payload"}
    try:
        lang = str(b.get("lang") or b.get("language") or "de")
        norm = normalize_briefing(b, lang=lang)
    except Exception as exc:
        norm = {"_error": f"normalize_briefing failed: {exc}", "_raw_keys": list(b.keys())}

    required = [
        "branche","branche_label","unternehmensgroesse","unternehmensgroesse_label","bundesland_code",
        "hauptleistung","usecase_priority","ki_usecases","umsatzziel","jahresumsatz","zeitbudget",
        "investitionsbudget","kpi_digitalisierung","kpi_automatisierung","kpi_compliance","kpi_prozessreife","kpi_innovation",
    ]
    def _is_missing(v) -> bool:
        if v is None: return True
        if isinstance(v, str): return v.strip() == ""
        if isinstance(v, (list, dict, tuple, set)): return len(v) == 0
        return False

    missing = sorted([k for k in required if _is_missing(norm.get(k))])

    return {
        "briefing_raw.json": _jsonlib.dumps(b, ensure_ascii=False, indent=2),
        "briefing_normalized.json": _jsonlib.dumps(norm, ensure_ascii=False, indent=2),
        "briefing_missing_fields.json": _jsonlib.dumps({"missing": missing}, ensure_ascii=False, indent=2),
    }
