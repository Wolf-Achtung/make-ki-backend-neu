# -*- coding: utf-8 -*-
"""
Gold-Standard+ Analyzer for KI-Status-Report (P1/P2 refinements)

- Locale-aware prompt loading, strict guards
- KPI clamp [0..100] for visual stability
- Business-case scenario box & 4-month baseline delta
- Hybrid live search via websearch_utils with 7->30 day fallback
"""

from __future__ import annotations
import json, logging, os, re, math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger("gpt_analyze")

BASE_DIR = os.path.abspath(os.getenv("APP_BASE", os.getcwd()))
PROMPTS_DIR = os.getenv("PROMPTS_DIR", os.path.join(BASE_DIR, "prompts"))
TEMPLATE_DIR = os.getenv("TEMPLATE_DIR", os.path.join(BASE_DIR, "templates"))
TEMPLATE_DE = os.getenv("TEMPLATE_DE", "pdf_template.html")
TEMPLATE_EN = os.getenv("TEMPLATE_EN", "pdf_template_en.html")
ASSETS_BASE_URL = os.getenv("ASSETS_BASE_URL", "templates")

ROI_BASELINE_MONTHS = float(os.getenv("ROI_BASELINE_MONTHS", "4"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_APIKEY") or ""
OPENAI_MODEL = os.getenv("OPENAI_MODEL_DEFAULT", "gpt-4o")
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "30"))
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "1200"))

DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
BRANCHEN_DIR = os.getenv("BRANCHEN_DIR", os.path.join(BASE_DIR, "branchenkontext"))

def _read_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""

def _load_prompt(lang: str, name: str) -> str:
    cands = [
        os.path.join(PROMPTS_DIR, lang, f"{name}_{lang}.md"),
        os.path.join(PROMPTS_DIR, lang, f"{name}.md"),
        os.path.join(PROMPTS_DIR, f"{name}_{lang}.md"),
        os.path.join(PROMPTS_DIR, f"{name}.md"),
    ]
    for p in cands:
        if os.path.exists(p):
            log.info("gpt_analyze: Loaded prompt: %s", os.path.relpath(p, PROMPTS_DIR))
            return _read_file(p)
    log.warning("gpt_analyze: Prompt not found for %s (%s). Returning empty string.", name, lang)
    return ""

def _template_for_lang(lang: str) -> str:
    fname = TEMPLATE_DE if lang == "de" else TEMPLATE_EN
    path = os.path.join(TEMPLATE_DIR, fname)
    if not os.path.exists(path):
        # fallback auf deutsches Template
        path = os.path.join(TEMPLATE_DIR, "pdf_template.html")
    return _read_file(path)

def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

def _strip_placeholders(html: str) -> str:
    html = re.sub(r"\{\{.*?\}\}", "", html, flags=re.DOTALL)
    html = re.sub(r"\{[^{}]*\}", "", html)
    return html

# ---------------- Briefing normalization ----------------

def normalize_briefing(raw: Dict[str, Any], lang: str = "de") -> Dict[str, Any]:
    b = dict(raw or {})
    passthrough = [
        "strategische_ziele","ki_projekte","ki_usecases","datenquellen",
        "zeitbudget","jahresumsatz","usecase_priority","zielgruppen",
        "ki_potenzial","ki_geschaeftsmodell_vision","moonshot",
    ]
    if "answers" in raw:
        for k in passthrough:
            if b.get(k) is None and raw["answers"].get(k) is not None:
                b[k] = raw["answers"][k]

    branche = str(b.get("branche") or "").lower()
    groesse = str(b.get("unternehmensgroesse") or "").lower()
    bundesland = (b.get("bundesland_code") or b.get("bundesland") or "").upper() or "DE"
    b["bundesland_code"] = bundesland

    b["branche_label"] = b.get("branche_label") or branche.title() or "Branche n. a."
    b["unternehmensgroesse_label"] = b.get("unternehmensgroesse_label") or f"{b.get('unternehmensgroesse','n. a.')}"

    b["hauptleistung"] = b.get("hauptleistung") or "Beratung/Service"

    def _first_usecase():
        u = b.get("usecase_priority") or (b.get("ki_usecases") or [None])
        if isinstance(u, list) and u: return u[0]
        return u if isinstance(u, str) else "Prozessautomatisierung"

    def _zeitbudget_label():
        z = str(b.get("zeitbudget") or "").lower()
        return {"unter_2":"< 2 Std/Woche","2_5":"2–5 Std/Woche","5_10":"5–10 Std/Woche","ueber_10":"> 10 Std/Woche"}.get(z,"k. A.")

    def _umsatz_klasse():
        u = str(b.get("jahresumsatz") or "").lower()
        mapping = {"unter_100k":"Umsatzklasse: < 100 Tsd €","100k_500k":"Umsatzklasse: 100–500 Tsd €","500k_2m":"Umsatzklasse: 0,5–2 Mio €","2m_10m":"Umsatzklasse: 2–10 Mio €","ueber_10m":"> 10 Mio €"}
        return mapping.get(u, "Umsatzklasse: n. a.")

    b["_pull_kpi"] = {"usecase": _first_usecase(), "zeitbudget": _zeitbudget_label(), "umsatzklasse": _umsatz_klasse()}
    return b

@dataclass
class ScorePack:
    kpis: Dict[str, float]
    weights: Dict[str, float]
    total: float
    badge: str
    benchmarks: Dict[str, float]
    deltas: Dict[str, float]

def _badge_for(score: float) -> str:
    return "EXCELLENT" if score>=85 else "GOOD" if score>=70 else "FAIR" if score>=55 else "BASIC"

def _load_benchmarks(branche: str, size: str) -> Dict[str, float]:
    cands = [
        os.path.join(DATA_DIR, f"benchmarks_{branche}_{size}.json"),
        os.path.join(DATA_DIR, f"benchmarks_{branche}.json"),
        os.path.join(DATA_DIR, "benchmarks_default.json"),
    ]
    for p in cands:
        if os.path.exists(p):
            try:
                data = json.loads(_read_file(p))
                if isinstance(data, dict):
                    return {k: float(v) for k, v in data.items()}
                if isinstance(data, list):
                    out = {}
                    for row in data:
                        k = str(row.get("kpi") or row.get("name")).lower()
                        v = float(row.get("median") or row.get("value") or 60)
                        out[k] = v
                    return out
            except Exception as exc:
                log.warning("Benchmark JSON read failed: %s", exc)
    return {"digitalisierung":60,"automatisierung":60,"compliance":60,"prozessreife":60,"innovation":60}

def compute_scores(b: Dict[str, Any]) -> ScorePack:
    clamp = lambda x: max(0, min(100, int(round(x))))
    dig = clamp((int(b.get("digitalisierungsgrad") or 6) * 10))
    aut = {"sehr_hoch":85,"hoch":75,"mittel":60,"niedrig":40}.get(str(b.get("automatisierungsgrad") or "mittel").lower(),60)
    comp = 100 if (b.get("datenschutz") and b.get("governance") and b.get("folgenabschaetzung")=="ja") else 70
    proc = 95 if str(b.get("ai_roadmap") or b.get("roadmap") or "nein").lower() in {"ja","true","1"} else 60
    inno = {"sehr_offen":75,"offen":65,"neutral":55,"zurueckhaltend":45}.get(str(b.get("innovationskultur") or "neutral").lower(),55)

    kpis = {"Digitalisierung":dig,"Automatisierung":aut,"Compliance":comp,"Prozessreife":proc,"Innovation":inno}
    kpis = {k: clamp(v) for k, v in kpis.items()}
    weights = {k:0.2 for k in kpis}
    total = round(sum(kpis[k]*weights[k] for k in kpis),1)
    badge = _badge_for(total)

    braw = _load_benchmarks(str(b.get("branche") or "default"), str(b.get("unternehmensgroesse") or "kmu"))
    map_key = {"Digitalisierung":"digitalisierung","Automatisierung":"automatisierung","Compliance":"compliance","Prozessreife":"prozessreife","Innovation":"innovation"}
    benchmarks = {k: float(braw.get(map_key[k], 60.0)) for k in kpis}
    deltas = {k: round(kpis[k] - benchmarks[k]) for k in kpis}
    return ScorePack(kpis=kpis, weights=weights, total=total, badge=badge, benchmarks=benchmarks, deltas=deltas)

@dataclass
class BusinessCase:
    invest_eur: float
    save_year_eur: float
    payback_months: float
    roi_year1_pct: float
    target_months: float
    delta_months: float
    req_monthly_save_eur: float
    scenarios: List[Dict[str, Any]]

def _mid_of_range(rng: str) -> float:
    try:
        a, b = rng.split("_"); return (float(a) + float(b)) / 2.0
    except Exception:
        try: return float(rng)
        except Exception: return 6000.0

def business_case(b: Dict[str, Any], score: ScorePack) -> BusinessCase:
    invest = _mid_of_range(str(b.get("investitionsbudget") or "2000_10000"))
    base_monthly = (score.total/100.0) * 300.0
    save_year = base_monthly * 12
    payback = float("inf") if base_monthly<=0 else round(invest/base_monthly,1)
    roi1 = round((save_year - invest)/max(invest,1)*100.0,1)
    target = ROI_BASELINE_MONTHS
    delta = float("inf") if payback==float("inf") else round(payback - target,1)
    req_monthly = round(invest/max(target,0.001),2)
    def scen(mult: float, name: str) -> Dict[str, Any]:
        msave = base_monthly*mult
        pb = float("inf") if msave<=0 else round(invest/msave,1)
        roi = round(((msave*12)-invest)/max(invest,1)*100.0,1)
        return {"name":name,"monthly_saving_eur":round(msave,2),"payback_months":pb,"roi_year1_pct":roi}
    scenarios = [scen(0.5,"Conservative"),scen(1.0,"Realistic"),scen(1.5,"Ambitious")]
    return BusinessCase(invest, round(save_year,2), payback, roi1, target, delta, req_monthly, scenarios)

def business_case_html(case: BusinessCase, lang: str="de") -> str:
    if lang=="de":
        lines = [
            f'<div class="label">Ziel‑Payback: <b>{int(case.target_months)}&nbsp;Monate</b></div>',
            "<ul style='margin:.3rem 0 0 1rem;padding:0'>",
            f"<li>Investition: <span class='num'>{case.invest_eur:,.0f} €</span></li>",
            f"<li>Einsparung/Jahr: <span class='num'>{case.save_year_eur:,.0f} €</span></li>",
            f"<li>Payback (modelliert): <span class='num'>{case.payback_months}</span> Monate · ROI Jahr 1: <span class='num'>{case.roi_year1_pct}%</span></li>",
            f"<li>Δ zum Ziel: <span class='num'>{case.delta_months}</span> Monate · Erforderliche Einsparung/Monat: <span class='num'>{case.req_monthly_save_eur:,.0f} €</span></li>",
            "</ul>",
        ]
        head = "<h3 style='margin-top:8px'>Szenarien</h3>"
    else:
        lines = [
            f'<div class="label">Target payback: <b>{int(case.target_months)}&nbsp;months</b></div>',
            "<ul style='margin:.3rem 0 0 1rem;padding:0'>",
            f"<li>Investment: <span class='num'>€ {case.invest_eur:,.0f}</span></li>",
            f"<li>Savings / year: <span class='num'>€ {case.save_year_eur:,.0f}</span></li>",
            f"<li>Payback (modeled): <span class='num'>{case.payback_months}</span> months · ROI Y1: <span class='num'>{case.roi_year1_pct}%</span></li>",
            f"<li>Δ to target: <span class='num'>{case.delta_months}</span> months · Required monthly saving: <span class='num'>€ {case.req_monthly_save_eur:,.0f}</span></li>",
            "</ul>",
        ]
        head = "<h3 style='margin-top:8px'>Scenarios</h3>"
    lines.append(f'<div class="scen">{head}<table><thead><tr><th>Mode</th><th>Monthly saving</th><th>Payback</th><th>ROI Y1</th></tr></thead><tbody>')
    for s in case.scenarios:
        lines.append(f"<tr><td>{s['name']}</td><td class='num'>€ {s['monthly_saving_eur']:,.0f}</td><td class='num'>{s['payback_months']}</td><td class='num'>{s['roi_year1_pct']}%</td></tr>")
    lines.append("</tbody></table></div>")
    return "\n".join(lines)

def _openai_chat(messages: List[Dict[str, str]], model: Optional[str]=None, max_tokens: Optional[int]=None) -> str:
    if not OPENAI_API_KEY: return ""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": model or OPENAI_MODEL,"messages": messages,"temperature": float(os.getenv("GPT_TEMPERATURE","0.2")),"top_p":0.95,"max_tokens": max_tokens or OPENAI_MAX_TOKENS}
    try:
        with httpx.Client(timeout=float(OPENAI_TIMEOUT)) as cli:
            r = cli.post(url, headers=headers, json=payload); r.raise_for_status()
            data = r.json()
            return (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    except Exception as exc:
        log.warning("LLM call failed: %s", exc); return ""

def render_section(prompt_name: str, lang: str, ctx: Dict[str, Any]) -> str:
    prompt = _load_prompt(lang, prompt_name)
    if not prompt: return ""
    sys = "Du bist ein präziser, risikobewusster Assistent für Executive Reports." if lang=="de" else "You are a precise, risk-aware assistant for executive reports."
    filled = prompt.replace("{{BRIEFING_JSON}}", _json(ctx.get("briefing", {}))) \
                   .replace("{{SCORING_JSON}}", _json(ctx.get("scoring", {}))) \
                   .replace("{{BENCHMARKS_JSON}}", _json(ctx.get("benchmarks", {})))
    out = _openai_chat([{"role":"system","content":sys},{"role":"user","content":filled}],
                       model=os.getenv("EXEC_SUMMARY_MODEL", OPENAI_MODEL) if prompt_name=="executive_summary" else OPENAI_MODEL)
    out = _strip_placeholders(out or "")
    if lang=="de":
        import re as _re
        if len(_re.findall(r"\b(the|and|with|for|you|your)\b", out, flags=_re.I)) > 12:
            out2 = _openai_chat([{"role":"system","content":sys + " Antworte ausschließlich auf Deutsch."},{"role":"user","content":filled}])
            out = _strip_placeholders(out2 or out)
    return out

def _hybrid_live(topic: str, b: Dict[str, Any], days: int, max_items: int) -> List[Dict[str, Any]]:
    try:
        from websearch_utils import hybrid_search
    except Exception as exc:
        log.warning("websearch_utils import failed: %s", exc); return []
    return hybrid_search(topic=topic, briefing=b, days=days, max_items=max_items)

def _kpi_bars_html(score: ScorePack) -> str:
    def clamp(v: float) -> int: return max(0, min(100, int(round(v))))
    lines = []
    for k, v in score.kpis.items():
        v = clamp(v); median = clamp(score.benchmarks[k]); delta = v - median
        lines.append(
            "<div class='bar'>"
            f"<div class='bar__label'>{k}</div>"
            "<div class='bar__track'>"
            f"<div class='bar__fill' style='width:{v}%'></div>"
            f"<div class='bar__median' style='left:{median}%'></div>"
            "</div>"
            f"<div class='bar__pct'>{v}% <span class='bar__delta'>(Δ {'+' if delta>=0 else ''}{delta} pp)</span></div>"
            "</div>"
        )
    return "".join(lines)

def _benchmark_table_html(score: ScorePack) -> str:
    rows = ["<table class='bm'><thead><tr><th>KPI</th><th>Ihr Wert</th><th>Branchen‑Benchmark</th><th>Δ (pp)</th></tr></thead><tbody>"]
    for k in score.kpis:
        v = int(round(score.kpis[k])); m = int(round(score.benchmarks[k])); d = v - m
        rows.append(f"<tr><td>{k}</td><td>{v}%</td><td>{m}%</td><td>{'+' if d>=0 else ''}{d} pp</td></tr>")
    rows.append("</tbody></table>")
    return "".join(rows)

def _profile_html(b: Dict[str, Any]) -> str:
    badges = [
        f"<span class='pill'>TOP‑Use‑Case: {b['_pull_kpi']['usecase']}</span>",
        f"<span class='pill'>Zeitbudget: {b['_pull_kpi']['zeitbudget']}</span>",
        f"<span class='pill'>{b['_pull_kpi']['umsatzklasse']}</span>",
    ]
    items = [f"<li><b>Hauptleistung</b>: {b.get('hauptleistung')}</li>", "<li> " + " ".join(badges) + " </li>"]
    return "<ul>" + "".join(items) + "</ul>"

def _list_to_html(items: List[Dict[str, Any]], empty_msg: str, berlin_badge: bool=False) -> str:
    if not items: return f"<div class='muted'>{empty_msg}</div>"
    lis = []
    for it in items:
        title = it.get("title") or it.get("name") or it.get("url"); url = it.get("url") or "#"
        src = it.get("source") or ""; when = it.get("date") or ""
        extra = ""
        if berlin_badge and any(d in (url or "") for d in ("berlin.de","ibb.de")):
            extra = " <span class='flag-berlin'>Land Berlin</span>"
        lis.append(f"<li><a href='{url}'>{title}</a> – <span class='muted'>{src} {when}</span>{extra}</li>")
    return "<ul>" + "".join(lis) + "</ul>"

def analyze_briefing(raw: Dict[str, Any], lang: str="de") -> str:
    b = normalize_briefing(raw, lang=lang)
    score = compute_scores(b)
    case = business_case(b, score)

    news = _hybrid_live("news", b, days=int(os.getenv("SEARCH_DAYS_NEWS_FALLBACK","30")), max_items=int(os.getenv("LIVE_NEWS_MAX","5")))
    tools = _hybrid_live("tools", b, days=int(os.getenv("SEARCH_DAYS_TOOLS","30")), max_items=int(os.getenv("LIVE_MAX_ITEMS","5")))
    funding = _hybrid_live("funding", b, days=int(os.getenv("SEARCH_DAYS_FUNDING","60")), max_items=int(os.getenv("LIVE_MAX_ITEMS","5")))

    ctx = {
        "briefing": b,
        "scoring": {"score_total": score.total,"score_badge": score.badge,"kpis": score.kpis,"weights": score.weights},
        "benchmarks": score.benchmarks,
    }

    def sec(name: str) -> str: return render_section(name, lang, ctx) or ""
    exec_sum, quick, rdmp = sec("executive_summary"), sec("quick_wins"), sec("roadmap")
    risks, comp, business = sec("risks"), sec("compliance"), sec("business")
    recs, game, vision = sec("recommendations"), sec("gamechanger"), sec("vision")
    persona, praxis, coach = sec("persona"), sec("praxisbeispiel"), sec("coach")
    tools_static, funding_static, doc_digest = sec("tools"), sec("foerderprogramme"), sec("doc_digest")

    tpl = _template_for_lang(lang)
    filled = (
        tpl.replace("{{LANG}}", lang)
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
           .replace("{{NEWS_HTML}}", _list_to_html(news, "No recent items (checked up to 30 days)." if lang!="de" else "Keine aktuellen News gefunden (Suche bis 30 Tage geprüft)."))
           .replace("{{TOOLS_HTML}}", _list_to_html(tools, "No current items in the 30‑day window." if lang!="de" else "Keine aktuellen Einträge im Fenster (30 Tage)."))
           .replace("{{FUNDING_HTML}}", _list_to_html(funding, "No current items in the 30‑day window." if lang!="de" else "Keine aktuellen Einträge im Fenster (30 Tage).", berlin_badge=True))
           .replace("{{RECOMMENDATIONS_BLOCK}}", f"<section class='card' style='margin-top:12px'><h2>{'Recommendations' if lang!='de' else 'Recommendations'}</h2>{recs}<div class='meta'>{'As of' if lang!='de' else 'Stand'}: {{STAND_DATUM}}</div></section>")
           .replace("{{GAMECHANGER_BLOCK}}", f"<section class='card' style='margin-top:12px'><h2>{'Gamechanger' if lang!='de' else 'Gamechanger'}</h2>{game}<div class='meta'>{'As of' if lang!='de' else 'Stand'}: {{STAND_DATUM}}</div></section>")
           .replace("{{VISION_BLOCK}}", f"<section class='card' style='margin-top:12px'><h2>{'Vision' if lang!='de' else 'Vision'}</h2>{vision}<div class='meta'>{'As of' if lang!='de' else 'Stand'}: {{STAND_DATUM}}</div></section>")
           .replace("{{PERSONA_BLOCK}}", f"<section class='card' style='margin-top:12px'><h2>{'Persona' if lang!='de' else 'Persona'}</h2>{persona}<div class='meta'>{'As of' if lang!='de' else 'Stand'}: {{STAND_DATUM}}</div></section>")
           .replace("{{PRAXIS_BLOCK}}", f"<section class='card' style='margin-top:12px'><h2>{'Case study' if lang!='de' else 'Praxisbeispiel'}</h2>{praxis}<div class='meta'>{'As of' if lang!='de' else 'Stand'}: {{STAND_DATUM}}</div></section>")
           .replace("{{COACH_BLOCK}}", f"<section class='card' style='margin-top:12px'><h2>{'Coach' if lang!='de' else 'Coach'}</h2>{coach}<div class='meta'>{'As of' if lang!='de' else 'Stand'}: {{STAND_DATUM}}</div></section>")
           .replace("{{TOOLS_STATIC_BLOCK}}", f"<section class='card' style='margin-top:12px'><h2>Tools</h2>{tools_static}<div class='meta'>{'As of' if lang!='de' else 'Stand'}: {{STAND_DATUM}}</div></section>")
           .replace("{{FUNDING_STATIC_BLOCK}}", f"<section class='card' style='margin-top:12px'><h2>{'Funding' if lang!='de' else 'Foerderprogramme'}</h2>{funding_static}<div class='meta'>{'As of' if lang!='de' else 'Stand'}: {{STAND_DATUM}}</div></section>")
           .replace("{{BUSINESS_BLOCK}}", f"<section class='card' style='margin-top:12px'><h2>Business</h2>{business}<div class='meta'>{'As of' if lang!='de' else 'Stand'}: {{STAND_DATUM}}</div></section>")
           .replace("{{APPENDIX_BLOCK}}", f"<section class='card' style='margin-top:12px'><h2>Appendix – Checklists</h2><div class='columns'>{doc_digest or ''}</div></section>")
    )
    filled = filled.replace("{{STAND_DATUM}}", os.getenv("REPORT_DATE_OVERRIDE") or __import__("datetime").date.today().isoformat())
    return _strip_placeholders(filled)

def produce_admin_attachments(raw: Dict[str, Any]) -> Dict[str, str]:
    b = normalize_briefing(raw, lang=str(raw.get("lang") or "de"))
    score = compute_scores(b); case = business_case(b, score)
    pay = {"invest_eur":case.invest_eur,"save_year_eur":case.save_year_eur,"payback_modeled_months":case.payback_months,"payback_target_months":case.target_months,"delta_months":case.delta_months,"required_monthly_saving_eur":case.req_monthly_save_eur,"scenarios":case.scenarios}
    return {
        "briefing_raw.json": json.dumps(raw, ensure_ascii=False, indent=2),
        "briefing_normalized.json": json.dumps(b, ensure_ascii=False, indent=2),
        "kpi_score.json": json.dumps({"total":score.total,"badge":score.badge,"kpis":score.kpis,"benchmarks":score.benchmarks,"deltas":score.deltas}, ensure_ascii=False, indent=2),
        "business_case.json": json.dumps(pay, ensure_ascii=False, indent=2),
    }
