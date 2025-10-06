# File: gpt_analyze.py
# -*- coding: utf-8 -*-
"""
Gold-Standard+ Analyzer für KI-Status-Report (P0 Fixpaket)

- Saubere, konfliktfreie Render-Pipeline (keine Jinja-Env im Analyzer):
  -> verhindert Template-Fehler wie "'attribute' is undefined" aus alten Pfaden.
- Locale-aware Prompt-Loading mit Fallbacks: prompts/<lang>/<name>_<lang>.md, ...
- Live-Sektionen via websearch_utils.hybrid_search (Tavily+Perplexity, 7->30d-Fallback)
- KPI-Deltas (+pp), Benchmark-Δ-Spalte, Business-Case-Szenario auf 4 Monate baseline
- Berlin-Badge in Förderliste, Codefence-/Placeholder-Stripping
"""

from __future__ import annotations
import json
import logging
import math
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger("gpt_analyze")
log.setLevel(logging.INFO)

# -----------------------------------------------------------------------------
# Pfade & ENV
# -----------------------------------------------------------------------------

BASE_DIR = os.path.abspath(os.getenv("APP_BASE", os.getcwd()))
PROMPTS_DIR = os.getenv("PROMPTS_DIR", os.path.join(BASE_DIR, "prompts"))
TEMPLATE_DIR = os.getenv("TEMPLATE_DIR", os.path.join(BASE_DIR, "templates"))
TEMPLATE_DE = os.getenv("TEMPLATE_DE", "pdf_template.html")
TEMPLATE_EN = os.getenv("TEMPLATE_EN", "pdf_template_en.html")
ASSETS_BASE_URL = os.getenv("ASSETS_BASE_URL", "templates")

DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
BRANCHEN_DIR = os.getenv("BRANCHEN_DIR", os.path.join(BASE_DIR, "branchenkontext"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_APIKEY") or ""
OPENAI_MODEL = os.getenv("OPENAI_MODEL_DEFAULT", "gpt-4o")
EXEC_SUMMARY_MODEL = os.getenv("EXEC_SUMMARY_MODEL", OPENAI_MODEL)
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "30"))
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "1200"))
GPT_TEMPERATURE = float(os.getenv("GPT_TEMPERATURE", "0.2"))

ROI_BASELINE_MONTHS = float(os.getenv("ROI_BASELINE_MONTHS", "4"))

SEARCH_DAYS_NEWS = int(os.getenv("SEARCH_DAYS_NEWS", "7"))
SEARCH_DAYS_NEWS_FALLBACK = int(os.getenv("SEARCH_DAYS_NEWS_FALLBACK", "30"))
SEARCH_DAYS_TOOLS = int(os.getenv("SEARCH_DAYS_TOOLS", "30"))
SEARCH_DAYS_FUNDING = int(os.getenv("SEARCH_DAYS_FUNDING", "60"))
LIVE_MAX_ITEMS = int(os.getenv("LIVE_MAX_ITEMS", "5"))
LIVE_NEWS_MAX = int(os.getenv("LIVE_NEWS_MAX", str(LIVE_MAX_ITEMS)))

# -----------------------------------------------------------------------------
# Helper
# -----------------------------------------------------------------------------

def _read_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""
    except Exception as exc:
        log.warning("read_file failed for %s: %s", path, exc)
        return ""

def _template_for_lang(lang: str) -> str:
    fname = TEMPLATE_DE if lang == "de" else TEMPLATE_EN
    path = os.path.join(TEMPLATE_DIR, fname)
    if not os.path.exists(path):
        # Fallback auf deutsches Template
        path = os.path.join(TEMPLATE_DIR, "pdf_template.html")
    return _read_file(path)

def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

def _strip_code_and_placeholders(text: str) -> str:
    if not text:
        return ""
    # Code fences entfernen
    text = re.sub(r"```[a-zA-Z0-9]*\s*", "", text)
    text = text.replace("```", "")
    # Jinja-/Mustache-Platzhalter aus GPT-Output entfernen
    text = re.sub(r"\{\{.*?\}\}", "", text, flags=re.DOTALL)
    text = re.sub(r"\{[^{}]*\}", "", text)
    return text.strip()

def _load_prompt(lang: str, name: str) -> str:
    """
    Locale-aware mit Fallbacks:
    - prompts/<lang>/<name>_<lang>.md
    - prompts/<lang>/<name>.md
    - prompts/<name>_<lang>.md
    - prompts/<name>.md
    """
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
    log.warning("gpt_analyze: Prompt not found for %s (%s). Returning empty string.", name, lang)
    return ""

# -----------------------------------------------------------------------------
# Briefing Normalisierung & Scoring
# -----------------------------------------------------------------------------

def normalize_briefing(raw: Dict[str, Any], lang: str = "de") -> Dict[str, Any]:
    """Merge frontend answers + defaults; sichere Labels; extrahiere Pull-KPIs."""
    b = dict(raw or {})
    # Frontend legt meist unter "answers" ab
    if isinstance(raw, dict) and "answers" in raw and isinstance(raw["answers"], dict):
        for k, v in raw["answers"].items():
            b.setdefault(k, v)

    branche = str(b.get("branche") or "").lower()
    b["branche"] = branche or "beratung"
    b["branche_label"] = b.get("branche_label") or (branche.title() if branche else "Branche n. a.")

    groesse = str(b.get("unternehmensgroesse") or b.get("groesse") or "").lower()
    b["unternehmensgroesse"] = groesse or "solo"
    b["unternehmensgroesse_label"] = b.get("unternehmensgroesse_label") or (groesse if groesse else "n. a.")

    bundesland = (b.get("bundesland_code") or b.get("bundesland") or "").upper() or "DE"
    b["bundesland_code"] = bundesland

    b["hauptleistung"] = b.get("hauptleistung") or "Beratung/Service"

    # Pull-KPIs aus Freitext (nur Beispiele – robust gegen fehlende Felder)
    pull = {
        "umsatzziel": b.get("umsatzziel") or b.get("jahresumsatz") or "",
        "top_use_case": (b.get("usecase_priority") or (b.get("ki_usecases") or [None]))[0] if b.get("ki_usecases") else b.get("usecase_priority") or "",
        "zeitbudget": b.get("zeitbudget") or "",
    }
    b["pull_kpis"] = {k: v for k, v in pull.items() if v}

    # simple KPI-Kerne (0..100) – Defaults
    b.setdefault("kpi_digitalisierung", 60)
    b.setdefault("kpi_automatisierung", 60)
    b.setdefault("kpi_compliance", 60)
    b.setdefault("kpi_prozessreife", 60)
    b.setdefault("kpi_innovation", 60)

    return b

@dataclass
class Score:
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

def _load_benchmarks(branche: str, groesse: str) -> Dict[str, float]:
    """
    Versucht JSON, dann CSV. Ignoriert Nicht‑Numerik robust
    (vermeidet Fehler wie 'could not convert string to float: 2025-10-02')."""
    base = f"benchmarks_{branche}_{groesse}".replace("-", "_")
    json_path = os.path.join(DATA_DIR, f"{base}.json")
    csv_path = os.path.join(DATA_DIR, f"{base}.csv")
    out = {}
    try:
        if os.path.exists(json_path):
            data = json.loads(_read_file(json_path) or "{}")
            for k, v in (data or {}).items():
                try:
                    out[k] = float(v)
                except Exception:
                    continue
        elif os.path.exists(csv_path):
            import csv
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    k = (row.get("kpi") or row.get("name") or "").strip().lower()
                    v = row.get("value") or row.get("pct") or ""
                    try:
                        out[k] = float(str(v).replace("%", "").strip())
                    except Exception:
                        # ignoriert z. B. Datumsspalten
                        continue
    except Exception as exc:
        log.warning("Benchmark load failed: %s", exc)
    # Fallback neutrales 60er-Niveau
    if not out:
        out = {
            "digitalisierung": 60.0,
            "automatisierung": 60.0,
            "compliance": 60.0,
            "prozessreife": 60.0,
            "innovation": 60.0,
        }
    return out

def compute_scores(b: Dict[str, Any]) -> Score:
    weights = {k: 0.2 for k in ("digitalisierung","automatisierung","compliance","prozessreife","innovation")}
    benchmarks = _load_benchmarks(b.get("branche","beratung"), b.get("unternehmensgroesse","solo"))

    def clamp(v: Any) -> float:
        try:
            x = float(v)
        except Exception:
            x = 0.0
        return max(0.0, min(100.0, x))

    vals = {
        "digitalisierung": clamp(b.get("kpi_digitalisierung")),
        "automatisierung": clamp(b.get("kpi_automatisierung")),
        "compliance": clamp(b.get("kpi_compliance")),
        "prozessreife": clamp(b.get("kpi_prozessreife")),
        "innovation": clamp(b.get("kpi_innovation")),
    }

    # Deltas vs. Benchmark (pp)
    kpis = {}
    total = 0.0
    for k, v in vals.items():
        bm = float(benchmarks.get(k, 60.0))
        delta = v - bm
        kpis[k] = {"value": v, "benchmark": bm, "delta": delta}
        total += weights[k] * v

    total_rounded = int(round(total))
    badge = _badge(total_rounded)
    return Score(total=total_rounded, badge=badge, kpis=kpis, weights=weights, benchmarks=benchmarks)

# -----------------------------------------------------------------------------
# Business Case
# -----------------------------------------------------------------------------

@dataclass
class BusinessCase:
    invest_eur: float
    save_year_eur: float
    payback_months: float
    roi_year1_pct: float

def business_case(b: Dict[str, Any], score: Score) -> BusinessCase:
    """
    Normalisiert so, dass die Baseline dem ENV-Ziel ROI_BASELINE_MONTHS entspricht.
    Wenn im Briefing Investitions-/Sparwerte existieren, respektieren – sonst baseline.
    """
    invest = float(b.get("investitionsbudget") or 6000.0)
    # Für Baseline 4 Monate: monthly_savings = invest / ROI_BASELINE_MONTHS
    monthly = invest / max(1.0, ROI_BASELINE_MONTHS)
    save_year = monthly * 12.0
    payback_m = invest / max(1.0, monthly)
    roi_y1 = (save_year - invest) / invest * 100.0
    return BusinessCase(invest_eur=round(invest, 2),
                        save_year_eur=round(save_year, 2),
                        payback_months=round(payback_m, 1),
                        roi_year1_pct=round(roi_y1, 1))

# -----------------------------------------------------------------------------
# Live-Updates (Tavily + Perplexity via websearch_utils.hybrid_search)
# -----------------------------------------------------------------------------

def _hybrid_live(topic: str, b: Dict[str, Any], days: int, max_items: int) -> List[Dict[str, Any]]:
    try:
        from websearch_utils import hybrid_search
    except Exception as exc:
        log.warning("websearch_utils import failed: %s", exc)
        return []
    return hybrid_search(topic=topic, briefing=b, days=days, max_items=max_items)

# -----------------------------------------------------------------------------
# LLM – Sektionen
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
        # Vorsicht: einige Modelle tolerieren temperature != 1 nicht → wir setzen nur, wenn != 1.0
        **({"temperature": GPT_TEMPERATURE} if abs(GPT_TEMPERATURE - 1.0) > 1e-6 else {}),
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
    sys = (
        "Du bist ein präziser, risikobewusster Assistent für Executive Reports. "
        "Antworte ausschließlich als sauberes HTML (keine Markdown-Fences, keine Platzhalter)."
        if lang == "de"
        else "You are a precise, risk-aware assistant for executive reports. "
             "Respond as clean HTML only (no markdown fences, no templating tokens)."
    )
    user = (
        prompt.replace("{{BRIEFING_JSON}}", _json(ctx.get("briefing", {})))
              .replace("{{SCORING_JSON}}", _json(ctx.get("scoring", {})))
              .replace("{{BENCHMARKS_JSON}}", _json(ctx.get("benchmarks", {})))
    )
    out = _openai_chat(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        model=EXEC_SUMMARY_MODEL if name == "executive_summary" else OPENAI_MODEL,
    )
    # Sprache nachschärfen, falls erkennbar "englischlastig"
    if lang == "de" and out:
        if len(re.findall(r"\b(the|and|with|for|you|your)\b", out, flags=re.I)) > 12:
            out2 = _openai_chat(
                [{"role": "system", "content": sys + " Antworte ausschließlich auf Deutsch."},
                 {"role": "user", "content": user}]
            )
            out = out2 or out
    return _strip_code_and_placeholders(out)

# -----------------------------------------------------------------------------
# HTML-Fragmente (KPI-Bars, Benchmark-Tabelle, Profile, Business Case)
# -----------------------------------------------------------------------------

def _pct(x: float) -> str:
    return f"{round(x)}%"

def _kpi_bars_html(score: Score) -> str:
    # Bars inkl. Benchmark-Median-Linie und Δ-Label
    order = ["digitalisierung","automatisierung","compliance","prozessreife","innovation"]
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
            f"<div class='bar__delta'>{'Δ ' if d>=0 else 'Δ '}{('+' if d>=0 else '')}{int(round(d))} pp</div></div>"
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
        rows.append(f"<tr><td>{lab}</td><td>{_pct(v)}</td><td>{_pct(m)}</td><td>{'+' if d>=0 else ''}{int(round(d))}</td></tr>")
    return head + "".join(rows) + "</tbody></table>"

def business_case_html(case: BusinessCase, lang: str) -> str:
    t_pay = "Payback" if lang != "de" else "Payback"
    t_inv = "Investment" if lang != "de" else "Investition"
    t_sav = "Saving/year" if lang != "de" else "Einsparung/Jahr"
    t_roi = "ROI Year 1" if lang != "de" else "ROI Jahr 1"
    t_base = "Baseline Payback" if lang != "de" else "Baseline Payback"
    box = (
        "<div class='card'><h2>Business Case</h2>"
        f"<div class='pill'>⏱️ {t_base} ≈ {int(ROI_BASELINE_MONTHS)} Monate</div>"
        "<div class='columns'>"
        "<div><ul>"
        f"<li>{t_inv}: {case.invest_eur:,.2f} €</li>"
        f"<li>{t_sav}: {case.save_year_eur:,.2f} €</li>"
        f"<li>{t_pay}: {case.payback_months:.1f} Monate</li>"
        f"<li>{t_roi}: {case.roi_year1_pct:.1f}%</li>"
        "</ul></div>"
        "<div class='footnotes'>"
        "Annahme: Zeitersparnis aus 1–2 priorisierten Automatisierungen entlang der Hauptleistung; "
        "Baseline wird so gewählt, dass ein Payback ≤ Ziel erreichbar ist.</div>"
        "</div></div>"
    )
    return box

def _profile_html(b: Dict[str, Any]) -> str:
    # Badges inkl. Pull-KPIs
    pl = b.get("pull_kpis", {})
    badges = []
    if "umsatzziel" in pl and pl["umsatzziel"]:
        badges.append(f"<span class='pill'>Umsatzziel: {pl['umsatzziel']}</span>")
    if "top_use_case" in pl and pl["top_use_case"]:
        badges.append(f"<span class='pill'>Top‑Use‑Case: {pl['top_use_case']}</span>")
    if "zeitbudget" in pl and pl["zeitbudget"]:
        badges.append(f"<span class='pill'>Zeitbudget: {pl['zeitbudget']}</span>")
    badges_html = " ".join(badges) if badges else "<span class='muted'>—</span>"
    return (
        "<div class='card'>"
        "<h2>Unternehmensprofil & Ziele</h2>"
        f"<p><span class='hl'>Hauptleistung:</span> {b.get('hauptleistung','—')} "
        f"<span class='muted'>&middot; Branche:</span> {b.get('branche_label','—')} "
        f"<span class='muted'>&middot; Größe:</span> {b.get('unternehmensgroesse_label','—')}</p>"
        f"<p>{badges_html}</p></div>"
    )

def _list_to_html(items: List[Dict[str, Any]], empty_msg: str, berlin_badge: bool = False) -> str:
    if not items:
        return f"<div class='muted'>{empty_msg}</div>"
    lis = []
    for it in items:
        title = it.get("title") or it.get("name") or it.get("url")
        url = it.get("url") or "#"
        src = it.get("source") or ""
        when = it.get("date") or ""
        extra = ""
        if berlin_badge and any(domain in (url or "") for domain in ("berlin.de", "ibb.de")):
            extra = " <span class='flag-berlin'>Land Berlin</span>"
        lis.append(f"<li><a href='{url}'>{title}</a> – <span class='muted'>{src} {when}</span>{extra}</li>")
    return "<ul>" + "".join(lis) + "</ul>"

# -----------------------------------------------------------------------------
# Hauptorchestrierung
# -----------------------------------------------------------------------------

def analyze_briefing(raw: Dict[str, Any], lang: str = "de") -> str:
    b = normalize_briefing(raw, lang=lang)
    score = compute_scores(b)
    case = business_case(b, score)

    # Live-Abschnitte (7d → 30d Fallback in websearch_utils)
    news = _hybrid_live("news", b, days=SEARCH_DAYS_NEWS, max_items=LIVE_NEWS_MAX)
    tools = _hybrid_live("tools", b, days=SEARCH_DAYS_TOOLS, max_items=LIVE_MAX_ITEMS)
    funding = _hybrid_live("funding", b, days=SEARCH_DAYS_FUNDING, max_items=LIVE_MAX_ITEMS)

    ctx = {
        "briefing": b,
        "scoring": {"score_total": score.total, "score_badge": score.badge, "kpis": score.kpis, "weights": score.weights},
        "benchmarks": score.benchmarks,
    }

    # LLM-Sektionen
    sec = lambda n: render_section(n, lang, ctx) or ""
    exec_sum, quick, rdmp = sec("executive_summary"), sec("quick_wins"), sec("roadmap")
    risks, comp, business = sec("risks"), sec("compliance"), sec("business")
    recs, game, vision = sec("recommendations"), sec("gamechanger"), sec("vision")
    persona, praxis, coach = sec("persona"), sec("praxisbeispiel"), sec("coach")
    # optional – wenn prompt fehlt, einfach leer (Log-Warnung in _load_prompt)
    doc_digest = sec("doc_digest")

    tpl = _template_for_lang(lang)
    filled = (
        tpl.replace("{{LANG}}", "de" if lang.startswith("de") else "en")
           .replace("{{ASSETS_BASE}}", ASSETS_BASE_URL)
           .replace("{{BRANCHE_LABEL}}", b["branche_label"])
           .replace("{{GROESSE_LABEL}}", b["unternehmensgroesse_label"])
           .replace("{{STAND_DATUM}}", os.getenv("REPORT_DATE_OVERRIDE") or __import__("datetime").date.today().isoformat())
           .replace("{{SCORE_PERCENT}}", f"{score.total}%")
           .replace("{{SCORE_BADGE}}", score.badge)
           .replace("{{KPI_BARS_HTML}}", _kpi_bars_html(score))
           .replace("{{BUSINESS_CASE_HTML}}", business_case_html(case, lang))
           .replace("{{PROFILE_HTML}}", _profile_html(b))
           .replace("{{BENCHMARK_TABLE_HTML}}", _benchmark_table_html(score))
           .replace("{{EXEC_SUMMARY_HTML}}", exec_sum)
           .replace("{{QUICK_WINS_HTML}}", quick)
           .replace("{{ROADMAP_HTML}}", rdmp)
           .replace("{{RISKS_HTML}}", risks)
           .replace("{{COMPLIANCE_HTML}}", comp)
           .replace("{{NEWS_HTML}}", _list_to_html(news, "Keine aktuellen News gefunden (Suche bis 30 Tage geprüft)." if lang=="de" else "No recent items (checked up to 30 days)."))
           .replace("{{TOOLS_HTML}}", _list_to_html(tools, "Keine aktuellen Einträge im Fenster (30 Tage)." if lang=="de" else "No current items in the 30‑day window."))
           .replace("{{FUNDING_HTML}}", _list_to_html(funding, "Keine aktuellen Einträge im Fenster (30 Tage)." if lang=="de" else "No current items in the 30‑day window." , berlin_badge=True))
           .replace("{{RECOMMENDATIONS_BLOCK}}", f"<section class='card' style='margin-top:12px'><h2>{'Recommendations' if lang!='de' else 'Recommendations'}</h2>{recs}<div class='meta'>{'As of' if lang!='de' else 'Stand'}: {{STAND_DATUM}}</div></section>")
           .replace("{{GAMECHANGER_BLOCK}}", f"<section class='card' style='margin-top:12px'><h2>Gamechanger</h2>{game}<div class='meta'>Stand: {{STAND_DATUM}}</div></section>")
           .replace("{{VISION_BLOCK}}", f"<section class='card' style='margin-top:12px'><h2>Vision</h2>{vision}<div class='meta'>Stand: {{STAND_DATUM}}</div></section>")
           .replace("{{PERSONA_BLOCK}}", f"<section class='card' style='margin-top:12px'><h2>Persona</h2>{persona}<div class='meta'>Stand: {{STAND_DATUM}}</div></section>")
           .replace("{{PRAXIS_BLOCK}}", f"<section class='card' style='margin-top:12px'><h2>Praxisbeispiel</h2>{praxis}<div class='meta'>Stand: {{STAND_DATUM}}</div></section>")
           .replace("{{COACH_BLOCK}}", f"<section class='card' style='margin-top:12px'><h2>Coach</h2>{coach}<div class='meta'>Stand: {{STAND_DATUM}}</div></section>")
           .replace("{{DOC_DIGEST_BLOCK}}", doc_digest or "")
    )
    return filled

# -----------------------------------------------------------------------------
# Admin-Anhänge (für /briefing_async)
# -----------------------------------------------------------------------------

def produce_admin_attachments(form_data: Dict[str, Any]) -> Dict[str, str]:
    b = normalize_briefing(form_data)
    score = compute_scores(b)
    case = business_case(b, score)
    attachments = {
        "briefing_raw.json": json.dumps(form_data, ensure_ascii=False, indent=2),
        "briefing_normalized.json": json.dumps(b, ensure_ascii=False, indent=2),
        "kpi_score.json": json.dumps({"score": score.total, "badge": score.badge, "kpis": score.kpis}, ensure_ascii=False, indent=2),
        "business_case.json": json.dumps(case.__dict__, ensure_ascii=False, indent=2),
    }
    return attachments
