# filename: backend/gpt_analyze.py
# -*- coding: utf-8 -*-
"""
Analyzer für KI-Status-Report (Gold-Standard+):
- saubere Prompt-Injektion inkl. BUSINESS_JSON
- Executive-Kernaussagen (2 Zeilen) werden SERVERSEITIG mit echten Zahlen gerendert
- robustes Live-Layer (websearch_utils.hybrid_live_search)
- PEP8, defensives Logging
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

log = logging.getLogger("gpt_analyze")
if not log.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    log.addHandler(h)
log.setLevel(logging.INFO)

BASE_DIR = os.path.abspath(os.getenv("APP_BASE", os.getcwd()))
PROMPTS_DIR = os.getenv("PROMPTS_DIR", os.path.join(BASE_DIR, "prompts"))
TEMPLATE_DIR = os.getenv("TEMPLATE_DIR", os.path.join(BASE_DIR, "templates"))
TEMPLATE_DE = os.getenv("TEMPLATE_DE", "pdf_template.html")
TEMPLATE_EN = os.getenv("TEMPLATE_EN", "pdf_template_en.html")
ASSETS_BASE_URL = os.getenv("ASSETS_BASE_URL", "templates")
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_APIKEY") or ""
OPENAI_MODEL = os.getenv("OPENAI_MODEL_DEFAULT", "gpt-4o")
EXEC_SUMMARY_MODEL = os.getenv("EXEC_SUMMARY_MODEL", OPENAI_MODEL)
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "45"))
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "1200"))
GPT_TEMPERATURE = float(os.getenv("GPT_TEMPERATURE", "0.2"))

ROI_BASELINE_MONTHS = float(os.getenv("ROI_BASELINE_MONTHS", "4"))
SEARCH_DAYS_NEWS = int(os.getenv("SEARCH_DAYS_NEWS", "7"))
SEARCH_DAYS_NEWS_FALLBACK = int(os.getenv("SEARCH_DAYS_NEWS_FALLBACK", "30"))
SEARCH_DAYS_TOOLS = int(os.getenv("SEARCH_DAYS_TOOLS", "30"))
SEARCH_DAYS_FUNDING = int(os.getenv("SEARCH_DAYS_FUNDING", "60"))
LIVE_MAX_ITEMS = int(os.getenv("LIVE_MAX_ITEMS", "6"))


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


@dataclass
class Score:
    total: int
    badge: str
    kpis: Dict[str, Dict[str, float]]
    weights: Dict[str, float]
    benchmarks: Dict[str, float]


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
    auto = 70 if str(b.get("automatisierungsgrad","")).lower() in ("hoch","sehr_hoch") else 50
    if isinstance(b.get("ki_einsatz"), list) and b["ki_einsatz"]:
        auto = min(100, auto + 5)
    comp = 40
    if str(b.get("datenschutzbeauftragter","")).lower() in ("ja","true","1"):
        comp += 15
    if str(b.get("folgenabschaetzung","")).lower() == "ja":
        comp += 10
    if str(b.get("loeschregeln","")).lower() == "ja":
        comp += 10
    if str(b.get("meldewege","")).lower() in ("ja","teilweise"):
        comp += 5
    if str(b.get("governance","")).lower() == "ja":
        comp += 10
    comp = max(0, min(100, comp))
    proz = 30 + (10 if str(b.get("governance","")).lower()=="ja" else 0) + int(0.2*papier)
    proz = max(0, min(100, proz))
    know = 70 if str(b.get("ki_knowhow","")).lower()=="fortgeschritten" else 55
    inn = int(0.6*know + 0.4*65)
    return {"digitalisierung": digitalisierung, "automatisierung": auto,
            "compliance": comp, "prozessreife": proz, "innovation": inn}


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
    # Pull-KPIs
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
    for key, val in k.items():
        b[f"kpi_{key}"] = val
    return b


def _load_benchmarks(branche: str, groesse: str) -> Dict[str, float]:
    base = f"benchmarks_{branche}_{groesse}".replace("-", "_")
    out: Dict[str, float] = {}
    for ext in (".json", ".csv"):
        path = os.path.join(DATA_DIR, f"{base}{ext}")
        if not os.path.exists(path):
            continue
        try:
            if ext == ".json":
                d = json.loads(_read_file(path) or "{}")
                for k, v in (d or {}).items():
                    try:
                        out[k] = float(v)
                    except Exception:
                        pass
            else:
                with open(path, "r", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        k = (row.get("kpi") or row.get("name") or "").strip().lower()
                        v = row.get("value") or row.get("pct") or ""
                        try:
                            out[k] = float(str(v).replace("%","").strip())
                        except Exception:
                            pass
        except Exception as exc:
            log.warning("Benchmark-Import fehlgeschlagen (%s): %s", path, exc)
    if not out:
        out = {k: 60.0 for k in ["digitalisierung","automatisierung","compliance","prozessreife","innovation"]}
    return out


@dataclass
class ScorePack:
    total: int
    badge: str
    kpis: Dict[str, Dict[str, float]]
    weights: Dict[str, float]
    benchmarks: Dict[str, float]


def compute_scores(b: Dict[str, Any]) -> ScorePack:
    weights = {k: 0.2 for k in ("digitalisierung","automatisierung","compliance","prozessreife","innovation")}
    bm = _load_benchmarks(b.get("branche","beratung"), b.get("unternehmensgroesse","solo"))
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


def _lede_html(score: ScorePack, case: BusinessCase, lang: str) -> str:
    # Top-2 Hebel nach Δ
    labels = {"digitalisierung":"Digitalisierung","automatisierung":"Automatisierung",
              "compliance":"Compliance","prozessreife":"Prozessreife","innovation":"Innovation"}
    deltas = sorted(((k, abs(v["delta"])) for k, v in score.kpis.items()), key=lambda x: x[1], reverse=True)
    top = [labels[deltas[0][0]], labels[deltas[1][0]]] if len(deltas) >= 2 else ["Automatisierung","Compliance"]
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


def _openai_chat(messages: List[Dict[str, str]], model: Optional[str] = None, max_tokens: Optional[int] = None) -> str:
    if not OPENAI_API_KEY:
        return ""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": model or OPENAI_MODEL, "messages": messages,
               "max_tokens": int(max_tokens or 1200), "temperature": 0.2, "top_p": 0.95}
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
    system = ("Du bist ein präziser, risikobewusster Assistent. Antworte ausschließlich als sauberes HTML.")
    if not lang.startswith("de"):
        system = ("You are a precise, risk-aware assistant. Respond as clean HTML only.")
    user = (
        prompt
        .replace("{{BRIEFING_JSON}}", _json(ctx.get("briefing", {})))
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
    return out


def _kpi_bars_html(score: ScorePack) -> str:
    order = ["digitalisierung","automatisierung","compliance","prozessreife","innovation"]
    labels = {"digitalisierung":"Digitalisierung","automatisierung":"Automatisierung",
              "compliance":"Compliance","prozessreife":"Prozessreife","innovation":"Innovation"}
    rows = []
    for k in order:
        v = score.kpis[k]["value"]; m = score.kpis[k]["benchmark"]; d = score.kpis[k]["delta"]
        rows.append(
            f"<div class='bar'><div class='label'>{labels[k]}</div>"
            f"<div class='bar__track'><div class='bar__fill' style='width:{max(0,min(100,v))}%;'></div>"
            f"<div class='bar__median' style='left:{max(0,min(100,m))}%;'></div></div>"
            f"<div class='bar__delta'>{'+' if d>=0 else ''}{int(round(d))} pp</div></div>"
        )
    return "<div class='kpi'>" + "".join(rows) + "</div>"


def _benchmark_table_html(score: ScorePack) -> str:
    head = "<table class='bm'><thead><tr><th>KPI</th><th>Ihr Wert</th><th>Branchen‑Benchmark</th><th>Δ (pp)</th></tr></thead><tbody>"
    labels = {"digitalisierung":"Digitalisierung","automatisierung":"Automatisierung",
              "compliance":"Compliance","prozessreife":"Prozessreife","innovation":"Innovation"}
    rows = []
    for k, lab in labels.items():
        v = score.kpis[k]["value"]; m = score.kpis[k]["benchmark"]; d = score.kpis[k]["delta"]
        rows.append(f"<tr><td>{lab}</td><td>{int(round(v))}%</td><td>{int(round(m))}%</td><td>{'+' if d>=0 else ''}{int(round(d))}</td></tr>")
    return head + "".join(rows) + "</tbody></table>"


def business_case_html(case: BusinessCase, lang: str) -> str:
    t_pay = "Payback" if not lang.startswith("de") else "Payback"
    t_inv = "Investment" if not lang.startswith("de") else "Investition"
    t_sav = "Saving/year" if not lang.startswith("de") else "Einsparung/Jahr"
    t_roi = "ROI Year 1" if not lang.startswith("de") else "ROI Jahr 1"
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
    if pl.get("umsatzziel"): pills.append(f"<span class='pill'>Umsatzziel: {pl['umsatzziel']}</span>")
    if pl.get("top_use_case"): pills.append(f"<span class='pill'>Top‑Use‑Case: {pl['top_use_case']}</span>")
    if pl.get("zeitbudget"): pills.append(f"<span class='pill'>Zeitbudget: {pl['zeitbudget']}</span>")
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
        src = it.get("source") or ""
        when = it.get("date") or ""
        extra = " <span class='flag-berlin'>Land Berlin</span>" if (berlin_badge and any(d in (url or "") for d in ("berlin.de","ibb.de"))) else ""
        lis.append(f"<li><a href='{url}'>{title}</a> – <span class='muted'>{src} {when}</span>{extra}</li>")
    return "<ul>" + "".join(lis) + "</ul>"


def analyze_briefing(raw: Dict[str, Any], lang: str = "de") -> str:
    b = normalize_briefing(raw, lang=lang)
    score = compute_scores(b)
    case = business_case(b, score)

    # Live
    try:
        from websearch_utils import hybrid_live_search
    except Exception as exc:
        log.warning("websearch import failed: %s", exc)
        hybrid_live_search = lambda **_: {"items": []}  # type: ignore

    news_live = (hybrid_live_search(topic="news", briefing=b, short_days=SEARCH_DAYS_NEWS,
                                    long_days=SEARCH_DAYS_NEWS_FALLBACK, max_results=LIVE_MAX_ITEMS) or {}).get("items") or []
    tools_live = (hybrid_live_search(topic="tools", briefing=b, short_days=SEARCH_DAYS_TOOLS,
                                     long_days=SEARCH_DAYS_NEWS_FALLBACK, max_results=LIVE_MAX_ITEMS) or {}).get("items") or []
    funding_live = (hybrid_live_search(topic="funding", briefing=b, short_days=SEARCH_DAYS_FUNDING,
                                       long_days=SEARCH_DAYS_NEWS_FALLBACK, max_results=LIVE_MAX_ITEMS) or {}).get("items") or []

    # Local
    try:
        from tools_loader import filter_tools
        tools_local = filter_tools(industry=b.get("branche"), company_size=b.get("unternehmensgroesse"), limit=8)
    except Exception as exc:
        log.info("tools_loader not available: %s", exc)
        tools_local = []

    try:
        from funding_loader import filter_funding
        funding_local = filter_funding(region=b.get("bundesland_code","DE"), limit=10)
    except Exception as exc:
        log.info("funding_loader not available: %s", exc)
        funding_local = []

    ctx = {
        "briefing": b,
        "scoring": {"score_total": score.total, "badge": score.badge, "kpis": score.kpis, "weights": score.weights},
        "benchmarks": score.benchmarks,
        "tools": tools_local,
        "funding": funding_local,
        "business": case.__dict__,
    }

    # Sections
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

    # Template filling
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
        .replace("{{TOOLS_HTML}}", _list_html(tools_live, "Keine passenden Tools gefunden." if lang.startswith("de") else "No matching tools.") if tools_live else _list_html(tools_local, "Keine passenden Tools (lokal)." if lang.startswith("de") else "No matching tools (local)."))
        .replace("{{FUNDING_HTML}}", _list_html(funding_live or funding_local, "Keine aktuellen Einträge." if lang.startswith("de") else "No current items.", berlin_badge=True))
        .replace("{{RECOMMENDATIONS_BLOCK}}", f"<section class='card'><h2>Recommendations</h2>{recs}<div class='meta'>{'Stand' if lang.startswith('de') else 'As of'}: {report_date}</div></section>")
        .replace("{{GAMECHANGER_BLOCK}}", f"<section class='card'><h2>Gamechanger</h2>{game}<div class='meta'>{'Stand' if lang.startswith('de') else 'As of'}: {report_date}</div></section>")
        .replace("{{VISION_BLOCK}}", f"<section class='card'><h2>Vision</h2>{vision}<div class='meta'>{'Stand' if lang.startswith('de') else 'As of'}: {report_date}</div></section>")
        .replace("{{PERSONA_BLOCK}}", f"<section class='card'><h2>Persona</h2>{persona}<div class='meta'>{'Stand' if lang.startswith('de') else 'As of'}: {report_date}</div></section>")
        .replace("{{PRAXIS_BLOCK}}", f"<section class='card'><h2>Praxisbeispiel</h2>{praxis}<div class='meta'>{'Stand' if lang.startswith('de') else 'As of'}: {report_date}</div></section>")
        .replace("{{COACH_BLOCK}}", f"<section class='card'><h2>Coach</h2>{coach}<div class='meta'>{'Stand' if lang.startswith('de') else 'As of'}: {report_date}</div></section>")
        .replace("{{DOC_DIGEST_BLOCK}}", digest or "")
    )
    return filled
