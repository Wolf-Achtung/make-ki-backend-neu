# filename: backend/gpt_analyze.py
# -*- coding: utf-8 -*-
"""
KI-Status-Report – Analyzer (Gold-Standard+)
- PEP8-konform, robuste Fehlerbehandlung, sauberes Logging
- Einheitliche Kontextinjektion (inkl. BUSINESS_JSON)
- Live-Layer via websearch_utils.hybrid_live_search (Tavily/Perplexity)
- Stabile KPI-/Benchmark-Berechnung, sauberes HTML-Filling
"""

from __future__ import annotations

import csv
import json
import logging
import math
import os
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional

import httpx

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
log = logging.getLogger("gpt_analyze")
if not log.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    handler.setFormatter(formatter)
    log.addHandler(handler)
log.setLevel(logging.INFO)

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
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

# Business/Live defaults
ROI_BASELINE_MONTHS = float(os.getenv("ROI_BASELINE_MONTHS", "4"))
SEARCH_DAYS_NEWS = int(os.getenv("SEARCH_DAYS_NEWS", "7"))
SEARCH_DAYS_NEWS_FALLBACK = int(os.getenv("SEARCH_DAYS_NEWS_FALLBACK", "30"))
SEARCH_DAYS_TOOLS = int(os.getenv("SEARCH_DAYS_TOOLS", "30"))
SEARCH_DAYS_FUNDING = int(os.getenv("SEARCH_DAYS_FUNDING", "60"))
LIVE_MAX_ITEMS = int(os.getenv("LIVE_MAX_ITEMS", "6"))

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _read_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        log.warning("Datei nicht gefunden: %s", path)
        return ""
    except Exception as exc:
        log.warning("Fehler beim Lesen %s: %s", path, exc)
        return ""


def _template_for_lang(lang: str) -> str:
    fname = TEMPLATE_DE if lang.startswith("de") else TEMPLATE_EN
    path = os.path.join(TEMPLATE_DIR, fname)
    if not os.path.exists(path):
        # Fallback
        path = os.path.join(TEMPLATE_DIR, "pdf_template.html")
    return _read_file(path)


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _strip_code_and_placeholders(text: str) -> str:
    """Entfernt Codefences und verwaiste {{token}}-Platzhalter."""
    if not text:
        return ""
    text = re.sub(r"```[a-zA-Z0-9]*\s*", "", text).replace("```", "")
    text = re.sub(r"\{\{.*?\}\}", "", text, flags=re.DOTALL)
    text = re.sub(r"\{[^{}]*\}", "", text)
    return text.strip()


def _load_prompt(lang: str, name: str) -> str:
    candidates = [
        os.path.join(PROMPTS_DIR, lang, f"{name}_{lang}.md"),
        os.path.join(PROMPTS_DIR, lang, f"{name}.md"),
        os.path.join(PROMPTS_DIR, f"{name}_{lang}.md"),
        os.path.join(PROMPTS_DIR, f"{name}.md"),
    ]
    for p in candidates:
        if os.path.exists(p):
            rel = os.path.relpath(p, PROMPTS_DIR)
            log.info("gpt_analyze: Loaded prompt: %s", rel)
            return _read_file(p)
    log.warning("Prompt nicht gefunden: %s (%s)", name, lang)
    return ""


# -----------------------------------------------------------------------------
# Briefing-Normalisierung & KPI-Ableitung
# -----------------------------------------------------------------------------
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


def _map(val: Any, mapping: Dict[str, int], default: int = 50) -> int:
    return mapping.get(str(val or "").lower(), default)


def _derive_kpis(b: Dict[str, Any]) -> Dict[str, int]:
    digi = _parse_percent_bucket(b.get("digitalisierungsgrad"))
    papier = _parse_percent_bucket(b.get("prozesse_papierlos"))
    digitalisierung = int(round(0.6 * digi + 0.4 * papier))

    auto_map = {"sehr_hoch": 85, "hoch": 70, "mittel": 50, "niedrig": 30}
    auto = _map(b.get("automatisierungsgrad"), auto_map, 50)
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

    proz = 30 + (10 if str(b.get("governance", "")).lower() == "ja" else 0)
    proz += (10 if str(b.get("ai_roadmap", "")).lower() == "ja" else 0)
    proz += int(0.2 * papier)
    proz = max(0, min(100, proz))

    know_map = {"anfaenger": 40, "mittel": 55, "fortgeschritten": 70, "expert": 85}
    innov_map = {"sehr_offen": 80, "offen": 65, "neutral": 50, "vorsichtig": 40}
    inn = int(
        0.6 * know_map.get(str(b.get("ki_knowhow", "")).lower(), 55)
        + 0.4 * innov_map.get(str(b.get("innovationskultur", "")).lower(), 50)
    )
    if b.get("moonshot"):
        inn = min(100, inn + 5)

    return {
        "digitalisierung": digitalisierung,
        "automatisierung": auto,
        "compliance": comp,
        "prozessreife": proz,
        "innovation": inn,
    }


def normalize_briefing(raw: Dict[str, Any], lang: str = "de") -> Dict[str, Any]:
    b: Dict[str, Any] = dict(raw or {})
    if isinstance(raw, dict) and isinstance(raw.get("answers"), dict):
        for k, v in raw["answers"].items():
            b.setdefault(k, v)

    b["branche"] = str(b.get("branche") or "beratung").lower()
    b["branche_label"] = b.get("branche_label") or b["branche"].title()
    b["unternehmensgroesse"] = str(b.get("unternehmensgroesse") or "solo").lower()
    b["unternehmensgroesse_label"] = b.get("unternehmensgroesse_label") or b["unternehmensgroesse"]
    b["bundesland_code"] = (b.get("bundesland_code") or b.get("bundesland") or "DE").upper()
    b["hauptleistung"] = b.get("hauptleistung") or "Beratung/Service"

    # Pull KPIs
    top_use = str(b.get("usecase_priority") or "")
    if not top_use and isinstance(b.get("ki_usecases"), list) and b["ki_usecases"]:
        top_use = str(b["ki_usecases"][0])
    b["pull_kpis"] = {
        "umsatzziel": b.get("umsatzziel") or b.get("jahresumsatz") or "",
        "top_use_case": top_use,
        "zeitbudget": b.get("zeitbudget") or "",
    }

    # KPIs
    k = _derive_kpis(b)
    b["kpi_digitalisierung"] = k["digitalisierung"]
    b["kpi_automatisierung"] = k["automatisierung"]
    b["kpi_compliance"] = k["compliance"]
    b["kpi_prozessreife"] = k["prozessreife"]
    b["kpi_innovation"] = k["innovation"]
    return b


# -----------------------------------------------------------------------------
# Scoring & Benchmarks
# -----------------------------------------------------------------------------
@dataclass
class Score:
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


def _load_benchmarks(branche: str, groesse: str) -> Dict[str, float]:
    base = f"benchmarks_{branche}_{groesse}".replace("-", "_")
    out: Dict[str, float] = {}
    for ext in (".json", ".csv"):
        path = os.path.join(DATA_DIR, f"{base}{ext}")
        if not os.path.exists(path):
            continue
        try:
            if ext == ".json":
                data = json.loads(_read_file(path) or "{}")
                for k, v in (data or {}).items():
                    try:
                        out[k] = float(v)
                    except Exception:
                        pass
            else:
                with open(path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        k = (row.get("kpi") or row.get("name") or "").strip().lower()
                        v = row.get("value") or row.get("pct") or ""
                        try:
                            out[k] = float(str(v).replace("%", "").strip())
                        except Exception:
                            pass
        except Exception as exc:
            log.warning("Benchmark-Import fehlgeschlagen (%s): %s", path, exc)
    if not out:
        out = {k: 60.0 for k in ["digitalisierung", "automatisierung", "compliance", "prozessreife", "innovation"]}
    return out


def compute_scores(b: Dict[str, Any]) -> Score:
    weights = {k: 0.2 for k in ("digitalisierung", "automatisierung", "compliance", "prozessreife", "innovation")}
    bm = _load_benchmarks(b.get("branche", "beratung"), b.get("unternehmensgroesse", "solo"))

    def clamp(x: Any) -> float:
        try:
            return max(0.0, min(100.0, float(x)))
        except Exception:
            return 0.0

    vals = {
        "digitalisierung": clamp(b.get("kpi_digitalisierung")),
        "automatisierung": clamp(b.get("kpi_automatisierung")),
        "compliance": clamp(b.get("kpi_compliance")),
        "prozessreife": clamp(b.get("kpi_prozessreife")),
        "innovation": clamp(b.get("kpi_innovation")),
    }

    kpis: Dict[str, Dict[str, float]] = {}
    total = 0.0
    for k, v in vals.items():
        m = float(bm.get(k, 60.0))
        d = v - m
        kpis[k] = {"value": v, "benchmark": m, "delta": d}
        total += weights[k] * v

    total_rounded = int(round(total))
    return Score(total=total_rounded, badge=_badge(total_rounded), kpis=kpis, weights=weights, benchmarks=bm)


# -----------------------------------------------------------------------------
# Business Case
# -----------------------------------------------------------------------------
@dataclass
class BusinessCase:
    invest_eur: float
    save_year_eur: float
    payback_months: float
    roi_year1_pct: float


def _parse_invest(val: Any, default: float = 6000.0) -> float:
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val or "").strip()
    if not s:
        return default
    parts = re.split(r"[^\d]", s)
    nums = [float(p) for p in parts if p.isdigit()]
    if len(nums) >= 2:
        return (nums[0] + nums[1]) / 2.0
    if len(nums) == 1:
        return nums[0]
    return default


def business_case(b: Dict[str, Any], score: Score) -> BusinessCase:
    invest = _parse_invest(b.get("investitionsbudget"), 6000.0)
    monthly = invest / max(1.0, ROI_BASELINE_MONTHS)
    save_year = monthly * 12.0
    payback_m = invest / max(1.0, monthly)
    roi_y1 = (save_year - invest) / invest * 100.0
    return BusinessCase(round(invest, 2), round(save_year, 2), round(payback_m, 1), round(roi_y1, 1))


# -----------------------------------------------------------------------------
# Live Layer
# -----------------------------------------------------------------------------
def _hybrid_live(topic: str, b: Dict[str, Any], days: int, max_items: int) -> List[Dict[str, Any]]:
    try:
        from websearch_utils import hybrid_live_search
    except Exception as exc:
        log.warning("websearch_utils import fehlgeschlagen: %s", exc)
        return []
    try:
        result = hybrid_live_search(topic=topic, briefing=b, short_days=days, long_days=SEARCH_DAYS_NEWS_FALLBACK, max_results=max_items)
        return (result or {}).get("items") or []
    except Exception as exc:
        log.warning("hybrid_live_search failed: %s", exc)
        return []


# -----------------------------------------------------------------------------
# Local loaders (Tools/Funding)
# -----------------------------------------------------------------------------
def _tools_local(b: Dict[str, Any], limit: int = 8) -> List[Dict[str, Any]]:
    try:
        from tools_loader import filter_tools
    except Exception as exc:
        log.info("tools_loader nicht verfügbar: %s", exc)
        return []
    try:
        industry = b.get("branche") or "*"
        if isinstance(industry, list):
            industry = industry[0] if industry else "*"
        size = b.get("unternehmensgroesse")
        if isinstance(size, list):
            size = size[0]
        return filter_tools(industry=str(industry), company_size=str(size or ""), limit=limit) or []
    except Exception as exc:
        log.warning("filter_tools fehlgeschlagen: %s", exc)
        return []


def _funding_local(b: Dict[str, Any], limit: int = 10) -> List[Dict[str, Any]]:
    try:
        from funding_loader import filter_funding
    except Exception as exc:
        log.info("funding_loader nicht verfügbar: %s", exc)
        return []
    try:
        region = b.get("bundesland_code") or "DE"
        return filter_funding(region=str(region), limit=limit) or []
    except Exception as exc:
        log.warning("filter_funding fehlgeschlagen: %s", exc)
        return []


# -----------------------------------------------------------------------------
# LLM Call (OpenAI)
# -----------------------------------------------------------------------------
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
            out = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            return _strip_code_and_placeholders(out)
    except Exception as exc:
        log.warning("LLM call failed: %s", exc)
        return ""


def render_section(name: str, lang: str, ctx: Dict[str, Any]) -> str:
    prompt = _load_prompt(lang, name)
    if not prompt:
        return ""
    system = ("Du bist ein präziser, risikobewusster Assistent für Executive Reports. "
              "Antworte ausschließlich als sauberes HTML.") if lang.startswith("de") else \
             ("You are a precise, risk-aware assistant for executive reports. Respond as clean HTML only.")
    user = (
        prompt
        .replace("{{BRIEFING_JSON}}", _json(ctx.get("briefing", {})))
        .replace("{{SCORING_JSON}}", _json(ctx.get("scoring", {})))
        .replace("{{BENCHMARKS_JSON}}", _json(ctx.get("benchmarks", {})))
        .replace("{{TOOLS_JSON}}", _json(ctx.get("tools", [])))
        .replace("{{FUNDING_JSON}}", _json(ctx.get("funding", [])))
        .replace("{{BUSINESS_JSON}}", _json(ctx.get("business", {})))  # <-- NEW
    )
    out = _openai_chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        model=EXEC_SUMMARY_MODEL if name == "executive_summary" else OPENAI_MODEL,
    )
    # Notbremse: Falsche Sprache korrigieren
    if lang.startswith("de") and out and len(re.findall(r"\b(the|and|with|for|you|your)\b", out, flags=re.I)) > 12:
        out2 = _openai_chat(
            [{"role": "system", "content": system + " Antworte ausschließlich auf Deutsch."},
             {"role": "user", "content": user}]
        )
        out = out2 or out
    return _strip_code_and_placeholders(out)


# -----------------------------------------------------------------------------
# HTML Helpers
# -----------------------------------------------------------------------------
def _pct(x: float) -> str:
    return f"{round(x)}%"


def _kpi_bars_html(score: Score) -> str:
    order = ["digitalisierung", "automatisierung", "compliance", "prozessreife", "innovation"]
    labels = {
        "digitalisierung": "Digitalisierung",
        "automatisierung": "Automatisierung",
        "compliance": "Compliance",
        "prozessreife": "Prozessreife",
        "innovation": "Innovation",
    }
    rows: List[str] = []
    for k in order:
        v = score.kpis[k]["value"]
        m = score.kpis[k]["benchmark"]
        d = score.kpis[k]["delta"]
        rows.append(
            f"<div class='bar'><div class='label'>{labels[k]}</div>"
            f"<div class='bar__track'><div class='bar__fill' style='width:{max(0,min(100,v))}%;'></div>"
            f"<div class='bar__median' style='left:{max(0,min(100,m))}%;'></div></div>"
            f"<div class='bar__delta'>{'+' if d >= 0 else ''}{int(round(d))} pp</div></div>"
        )
    return "<div class='kpi'>" + "".join(rows) + "</div>"


def _benchmark_table_html(score: Score) -> str:
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
        rows.append(
            f"<tr><td>{lab}</td><td>{_pct(v)}</td><td>{_pct(m)}</td><td>{'+' if d >= 0 else ''}{int(round(d))}</td></tr>"
        )
    return head + "".join(rows) + "</tbody></table>"


def business_case_html(case: BusinessCase, lang: str) -> str:
    t_pay = "Payback" if not lang.startswith("de") else "Payback"
    t_inv = "Investment" if not lang.startswith("de") else "Investition"
    t_sav = "Saving/year" if not lang.startswith("de") else "Einsparung/Jahr"
    t_roi = "ROI Year 1" if not lang.startswith("de") else "ROI Jahr 1"
    t_base = "Baseline Payback" if not lang.startswith("de") else "Baseline Payback"
    return (
        "<div class='card'><h2>Business Case</h2>"
        f"<div class='pill'>⏱️ {t_base} ≈ {int(ROI_BASELINE_MONTHS)} Monate</div>"
        "<div class='columns'><div><ul>"
        f"<li>{t_inv}: {case.invest_eur:,.2f} €</li>"
        f"<li>{t_sav}: {case.save_year_eur:,.2f} €</li>"
        f"<li>{t_pay}: {case.payback_months:.1f} Monate</li>"
        f"<li>{t_roi}: {case.roi_year1_pct:.1f}%</li>"
        "</ul></div><div class='footnotes'>Annahme: Zeitersparnis aus 1–2 priorisierten Automatisierungen entlang der Hauptleistung; "
        "Baseline so gewählt, dass ein Payback ≤ Ziel erreichbar ist.</div></div></div>"
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
    pill_html = " ".join(pills) if pills else "<span class='muted'>—</span>"
    return (
        "<div class='card'><h2>Unternehmensprofil & Ziele</h2>"
        f"<p><span class='hl'>Hauptleistung:</span> {b.get('hauptleistung','—')} "
        f"<span class='muted'>&middot; Branche:</span> {b.get('branche_label','—')} "
        f"<span class='muted'>&middot; Größe:</span> {b.get('unternehmensgroesse_label','—')}</p>"
        f"<p>{pill_html}</p></div>"
    )


def _list_to_html(items: List[Dict[str, Any]], empty_msg: str, berlin_badge: bool = False) -> str:
    if not items:
        return f"<div class='muted'>{empty_msg}</div>"
    lis: List[str] = []
    for it in items:
        title = it.get("title") or it.get("name") or it.get("url")
        url = it.get("url") or "#"
        src = it.get("source") or ""
        when = it.get("date") or ""
        extra = ""
        if berlin_badge and any(d in (url or "") for d in ("berlin.de", "ibb.de")):
            extra = " <span class='flag-berlin'>Land Berlin</span>"
        lis.append(f"<li><a href='{url}'>{title}</a> – <span class='muted'>{src} {when}</span>{extra}</li>")
    return "<ul>" + "".join(lis) + "</ul>"


def _tools_html_from_local(items: List[Dict[str, Any]], lang: str) -> str:
    if not items:
        return "<div class='muted'>Keine passenden Tools gefunden.</div>" if lang.startswith("de") else "<div class='muted'>No matching tools.</div>"
    lis = []
    for t in items:
        name = t.get("name") or "Tool"
        url = t.get("homepage_url") or "#"
        one = t.get("one_liner") or ""
        eff = str(t.get("integration_effort_1to5") or "—")
        price = t.get("pricing_tier") or "€"
        gdpr = (t.get("gdpr_ai_act") or "").upper() or "UNKNOWN"
        region = t.get("vendor_region") or ""
        resid = t.get("data_residency") or ""
        lis.append(
            f"<li><a href='{url}'>{name}</a> – {one} "
            f"<span class='pill'>{'Aufwand' if lang.startswith('de') else 'Effort'} {eff}/5</span> "
            f"<span class='pill'>{'Preis' if lang.startswith('de') else 'Price'} {price}</span> "
            f"<span class='pill'>GDPR/AI‑Act: {gdpr}</span> "
            f"<span class='pill'>{region}; Residency {resid}</span></li>"
        )
    return "<ul class='tool-list'>" + "".join(lis) + "</ul>"


def _render_tools(local_tools: List[Dict[str, Any]], lang: str, base_ctx: Dict[str, Any]) -> str:
    if not local_tools:
        return ""
    ctx2 = dict(base_ctx or {})
    ctx2["tools"] = local_tools
    html = render_section("tools", lang, ctx2)
    return html or _tools_html_from_local(local_tools, lang)


# -----------------------------------------------------------------------------
# Orchestrierung
# -----------------------------------------------------------------------------
def analyze_briefing(raw: Dict[str, Any], lang: str = "de") -> str:
    b = normalize_briefing(raw, lang=lang)
    score = compute_scores(b)
    case = business_case(b, score)

    # Live (News/Tools/Funding)
    news_live = _hybrid_live("news", b, days=SEARCH_DAYS_NEWS, max_items=LIVE_MAX_ITEMS)
    tools_live = _hybrid_live("tools", b, days=SEARCH_DAYS_TOOLS, max_items=LIVE_MAX_ITEMS)
    funding_live = _hybrid_live("funding", b, days=SEARCH_DAYS_FUNDING, max_items=LIVE_MAX_ITEMS)

    # Local (Tools/Funding)
    tools_local = _tools_local(b, limit=8)
    funding_local = _funding_local(b, limit=10)

    ctx = {
        "briefing": b,
        "scoring": {"score_total": score.total, "score_badge": score.badge, "kpis": score.kpis, "weights": score.weights},
        "benchmarks": score.benchmarks,
        "tools": tools_local,
        "funding": funding_local,
        "business": case.__dict__,
    }

    # Prompts
    sec = lambda n: render_section(n, lang, ctx) or ""
    exec_sum = sec("executive_summary")
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
        .replace("{{EXEC_SUMMARY_HTML}}", exec_sum)
        .replace("{{QUICK_WINS_HTML}}", quick)
        .replace("{{ROADMAP_HTML}}", roadmap)
        .replace("{{RISKS_HTML}}", risks)
        .replace("{{COMPLIANCE_HTML}}", compliance)
        .replace("{{NEWS_HTML}}", _list_to_html(news_live, "Keine aktuellen News (30 Tage geprüft)." if lang.startswith("de") else "No recent news (30 days)."))
        .replace("{{TOOLS_HTML}}", _render_tools(tools_local, lang, ctx) or _tools_html_from_local([], lang))
        .replace("{{FUNDING_HTML}}", _list_to_html(funding_live or funding_local, "Keine aktuellen Einträge." if lang.startswith("de") else "No current items.", berlin_badge=True))
        .replace("{{RECOMMENDATIONS_BLOCK}}", f"<section class='card'><h2>Recommendations</h2>{recs}<div class='meta'>{'Stand' if lang.startswith('de') else 'As of'}: {report_date}</div></section>")
        .replace("{{GAMECHANGER_BLOCK}}", f"<section class='card'><h2>Gamechanger</h2>{game}<div class='meta'>{'Stand' if lang.startswith('de') else 'As of'}: {report_date}</div></section>")
        .replace("{{VISION_BLOCK}}", f"<section class='card'><h2>Vision</h2>{vision}<div class='meta'>{'Stand' if lang.startswith('de') else 'As of'}: {report_date}</div></section>")
        .replace("{{PERSONA_BLOCK}}", f"<section class='card'><h2>Persona</h2>{persona}<div class='meta'>{'Stand' if lang.startswith('de') else 'As of'}: {report_date}</div></section>")
        .replace("{{PRAXIS_BLOCK}}", f"<section class='card'><h2>Praxisbeispiel</h2>{praxis}<div class='meta'>{'Stand' if lang.startswith('de') else 'As of'}: {report_date}</div></section>")
        .replace("{{COACH_BLOCK}}", f"<section class='card'><h2>Coach</h2>{coach}<div class='meta'>{'Stand' if lang.startswith('de') else 'As of'}: {report_date}</div></section>")
        .replace("{{DOC_DIGEST_BLOCK}}", digest or "")
    )
    return filled


# -----------------------------------------------------------------------------
# Admin-Attachments (für E-Mail)
# -----------------------------------------------------------------------------
def produce_admin_attachments(form_data: Dict[str, Any]) -> Dict[str, str]:
    b = normalize_briefing(form_data)
    score = compute_scores(b)
    case = business_case(b, score)
    try:
        tools = _tools_local(b, limit=8)
    except Exception:
        tools = []
    try:
        funding = _funding_local(b, limit=10)
    except Exception:
        funding = []

    return {
        "briefing_raw.json": json.dumps(form_data, ensure_ascii=False, indent=2),
        "briefing_normalized.json": json.dumps(b, ensure_ascii=False, indent=2),
        "kpi_score.json": json.dumps({"score": score.total, "badge": score.badge, "kpis": score.kpis}, ensure_ascii=False, indent=2),
        "business_case.json": json.dumps(case.__dict__, ensure_ascii=False, indent=2),
        "tools_selected.json": json.dumps(tools, ensure_ascii=False, indent=2),
        "funding_selected.json": json.dumps(funding, ensure_ascii=False, indent=2),
    }
