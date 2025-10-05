# File: gpt_analyze.py
# -*- coding: utf-8 -*-
"""
Analyse & Rendering für den KI-Status-Report (Gold-Standard+)

Neu:
- Appendix "Checklisten" aus data/check_*.md / data/content/checklist_*.md (optional via ENV)
- Branchenkontext aus data/branchenkontext/<branche>_{de|en}.md
- Content-Intros (tools/foerderungen) aus data/content/*
- ROI mit config_roi.json
- Benchmarks JSON + CSV-Fallback; synonyme Branchen-Slugs
- Robuster OpenAI-Wrapper (max_completion_tokens / Fallback max_tokens)
"""

from __future__ import annotations

import csv
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

# OpenAI v1 (robuster Wrapper)
try:
    from openai import OpenAI  # type: ignore
    _openai_available = True
except Exception:
    _openai_available = False

log = logging.getLogger("gpt_analyze")
if not log.handlers:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

BASE_DIR = os.path.abspath(os.getenv("APP_BASE", os.getcwd()))
TEMPLATE_DIR = os.getenv("TEMPLATE_DIR", os.path.join(BASE_DIR, "templates"))
PROMPTS_DIR = os.getenv("PROMPTS_DIR", os.path.join(BASE_DIR, "prompts"))
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
BRANCHEN_DIR = os.path.join(DATA_DIR, "branchenkontext")
CONTENT_DIR = os.path.join(DATA_DIR, "content")

EXEC_SUMMARY_MODEL = os.getenv("EXEC_SUMMARY_MODEL", os.getenv("GPT_MODEL_NAME", "gpt-4o"))
DEFAULT_MODEL = os.getenv("GPT_MODEL_NAME", "gpt-4o-mini")

APPENDIX_CHECKLISTS = os.getenv("APPENDIX_CHECKLISTS", "true").strip().lower() in {"1", "true", "yes", "on"}
APPENDIX_MAX_DOCS = int(os.getenv("APPENDIX_MAX_DOCS", "6"))


# ------------------------------ Helfer ---------------------------------------

def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _md_to_html(md: str) -> str:
    """
    Sehr schlanker Markdown->HTML Konverter (ohne externe Abhängigkeit).
    Unterstützt Überschriften (#,##), Listen (-,*), einfache Absätze, Links.
    """
    if not md:
        return ""
    html_lines: List[str] = []
    for line in md.splitlines():
        s = line.rstrip()
        if not s:
            html_lines.append("<p></p>")
        elif s.startswith("### "):
            html_lines.append(f"<h3>{s[4:].strip()}</h3>")
        elif s.startswith("## "):
            html_lines.append(f"<h2>{s[3:].strip()}</h2>")
        elif s.startswith("# "):
            html_lines.append(f"<h1>{s[2:].strip()}</h1>")
        elif s.lstrip().startswith(("- ", "* ")):
            html_lines.append(f"<li>{s.lstrip()[2:].strip()}</li>")
        else:
            # rudimentäre Link-Ersetzung
            s = re.sub(r"\[(.*?)\]\((https?://[^\s)]+)\)", r"<a href='\2' target='_blank' rel='noopener noreferrer'>\1</a>", s)
            html_lines.append(f"<p>{s}</p>")
    # List-Items gruppieren
    out: List[str] = []
    in_list = False
    for l in html_lines:
        if l.startswith("<li>") and not in_list:
            out.append("<ul>")
            in_list = True
        if not l.startswith("<li>") and in_list:
            out.append("</ul>")
            in_list = False
        out.append(l)
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def _to_percent(value: Any, max_value: float) -> float:
    try:
        v = float(str(value).replace(",", "."))
        if max_value <= 0:
            return 0.0
        return max(0.0, min(100.0, round((v / max_value) * 100.0, 1)))
    except Exception:
        return 0.0


def _today() -> str:
    import datetime as dt
    return dt.datetime.now().strftime("%Y-%m-%d")


# --------------------------- Normalisierung ---------------------------------

CANON_KEYS = {
    "branche": ["branche", "industry", "sector"],
    "unternehmensgroesse": ["unternehmensgroesse", "company_size", "size", "mitarbeiterzahl"],
    "bundesland": ["bundesland", "state", "region"],
    "hauptleistung": ["hauptleistung", "main_service", "leistung"],
    "investitionsbudget": ["investitionsbudget", "budget", "capex", "investment"],
    "digitalisierungsgrad": ["digitalisierungsgrad", "digitization_level"],
    "prozesse_papierlos": ["prozesse_papierlos", "paperless"],
    "automatisierungsgrad": ["automatisierungsgrad", "automation_level"],
    "innovationskultur": ["innovationskultur", "innovation_culture"],
    "ki_knowhow": ["ki_knowhow", "ai_knowledge"],
    "governance": ["governance"],
    "datenschutz": ["datenschutz", "gdpr_ok"],
    "folgenabschaetzung": ["folgenabschaetzung", "dpia"],
    "meldewege": ["meldewege", "incident_process"],
    "loeschregeln": ["loeschregeln", "deletion_rules"],
}

BR_SLUGS = {
    "beratung": ["beratung_dienstleistungen", "dienstleistungen", "professional_services"],
    "it": ["it_software", "software", "it_und_software"],
    "marketing": ["marketing_werbung"],
    "medien": ["medien_kreativ"],
    "handel": ["handel_ecommerce", "ecommerce"],
    "industrie": ["industrie_produktion"],
    "gesundheit": ["gesundheit_pflege"],
    "bau": ["bauwesen_architektur"],
    "logistik": ["transport_logistik"],
    "verwaltung": ["verwaltung"],
    "bildung": ["bildung"],
    "finanzen": ["finanzen", "finanzen_versicherungen"],
}
SIZE_ALIASES = {
    "solo": ["solo"],
    "small": ["small", "team", "team_2_10", "klein"],
    "kmu": ["kmu", "kmu_11_100", "mittel", "konzern"],  # große fallen auf kmu zurück
}
BR_LABEL = {
    "beratung": "Beratung & Dienstleistungen", "it": "IT & Software",
    "marketing": "Marketing & Werbung", "medien": "Medien & Kreativwirtschaft",
    "handel": "Handel & E‑Commerce", "industrie": "Industrie & Produktion",
    "gesundheit": "Gesundheit & Pflege", "bau": "Bauwesen & Architektur",
    "logistik": "Transport & Logistik", "verwaltung": "Verwaltung",
    "bildung": "Bildung", "finanzen": "Finanzen & Versicherungen",
}
SIZE_LABEL = {"solo": "1", "small": "2‑10", "kmu": "11‑100+"}

BL_MAP = {
    # Name/Abkürzung -> Code
    "berlin": "BE", "be": "BE",
    "bayern": "BY", "by": "BY",
    "baden-württemberg": "BW", "bw": "BW",
    "brandenburg": "BB", "bb": "BB",
    "bremen": "HB", "hb": "HB",
    "hamburg": "HH", "hh": "HH",
    "hessen": "HE", "he": "HE",
    "mecklenburg-vorpommern": "MV", "mv": "MV",
    "niedersachsen": "NI", "ni": "NI",
    "nordrhein-westfalen": "NW", "nw": "NW",
    "rheinland-pfalz": "RP", "rp": "RP",
    "saarland": "SL", "sl": "SL",
    "sachsen": "SN", "sn": "SN",
    "sachsen-anhalt": "ST", "st": "ST",
    "schleswig-holstein": "SH", "sh": "SH",
    "thüringen": "TH", "thueringen": "TH", "th": "TH",
}

def normalize_briefing(raw: Dict[str, Any]) -> Dict[str, Any]:
    norm: Dict[str, Any] = {}
    for canon, aliases in CANON_KEYS.items():
        for a in [canon] + aliases:
            if a in raw:
                norm[canon] = raw[a]
                break
    # Labels/Slugs
    br = (norm.get("branche") or "").strip().lower()
    br_key = None
    for k, aliases in BR_SLUGS.items():
        if br in ([k] + aliases):
            br_key = k
            break
    if not br_key:
        br_key = "beratung"
    size = (norm.get("unternehmensgroesse") or "").strip().lower()
    size_key = None
    for k, aliases in SIZE_ALIASES.items():
        if size in ([k] + aliases):
            size_key = k
            break
    if size_key is None:
        size_key = "small"
    if size_key not in ("solo", "small", "kmu"):
        size_key = "small" if size_key not in ("konzern", "enterprise") else "kmu"

    norm["branche"] = br_key
    norm["unternehmensgroesse"] = size_key
    norm["branche_label"] = BR_LABEL.get(br_key, norm.get("branche"))
    norm["unternehmensgroesse_label"] = SIZE_LABEL.get(size_key, norm.get("unternehmensgroesse"))

    # Bundesland-Code
    bl_raw = (norm.get("bundesland") or "").strip().lower()
    norm["bundesland_code"] = BL_MAP.get(bl_raw, BL_MAP.get(bl_raw.replace(" ", "-"), "")) or bl_raw.upper()
    return norm


def missing_fields(norm: Dict[str, Any]) -> List[str]:
    req = ["branche", "unternehmensgroesse", "bundesland", "hauptleistung", "investitionsbudget"]
    return [k for k in req if not (norm.get(k) and str(norm[k]).strip())]


# ------------------------------ Benchmarks -----------------------------------

def _bench_json_path_candidates(br: str, sz: str) -> List[str]:
    br_variants = [br] + BR_SLUGS.get(br, [])
    size_variants = []
    for key, aliases in SIZE_ALIASES.items():
        if sz in aliases or sz == key:
            size_variants.append(key)
    if not size_variants:
        size_variants = ["small", "kmu", "solo"]
    names = []
    for b in br_variants:
        for s in size_variants:
            names.append(f"benchmarks_{b}_{s}.json")
        names.append(f"benchmarks_{b}.json")
    names.append("benchmarks_default.json")
    paths = [os.path.join(DATA_DIR, n) for n in names]
    return paths


def _load_benchmarks_from_csv(br: str, sz: str) -> Dict[str, float]:
    # CSV-Fallback: data/benchmarks.csv mit Spalten: branche, size, dig, auto, comp, proc, inno
    csv_path = os.path.join(DATA_DIR, "benchmarks.csv")
    if not os.path.exists(csv_path):
        return {}
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if (row.get("branche") or "").strip().lower() == br and (row.get("size") or "").strip().lower() == sz:
                    return {
                        "digitalisierung": float(row.get("dig") or 0.0),
                        "automatisierung": float(row.get("auto") or 0.0),
                        "compliance": float(row.get("comp") or 0.0),
                        "prozessreife": float(row.get("proc") or 0.0),
                        "innovation": float(row.get("inno") or 0.0),
                    }
    except Exception:
        return {}
    return {}


def pick_benchmark_file(br: str, sz: str) -> str:
    for p in _bench_json_path_candidates(br, sz):
        if os.path.exists(p):
            return p
    return ""


def load_benchmarks(norm: Dict[str, Any]) -> Dict[str, float]:
    br = (norm.get("branche") or "beratung").lower()
    sz = (norm.get("unternehmensgroesse") or "small").lower()
    path = pick_benchmark_file(br, sz)
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {k.lower(): float(v) for k, v in data.items()}
        except Exception:
            pass
    csv_bm = _load_benchmarks_from_csv(br, sz)
    if csv_bm:
        log.info("Loaded benchmark fallback from CSV for %s/%s", br, sz)
        return csv_bm
    return {"digitalisierung": 72.0, "automatisierung": 64.0, "compliance": 70.0, "prozessreife": 68.0, "innovation": 69.0}


# --------------------------- KPIs / Business Case ----------------------------

def calculate_kpis(norm: Dict[str, Any]) -> Dict[str, float]:
    digi = _to_percent(norm.get("digitalisierungsgrad") or 0, 10.0)
    auto_map = {"sehr_hoch": 85, "hoch": 75, "eher_hoch": 65, "mittel": 50, "eher_niedrig": 35, "niedrig": 20}
    auto = float(auto_map.get(str(norm.get("automatisierungsgrad") or "").lower(), 40))

    comp = 0.0
    comp += 25.0 if str(norm.get("datenschutz")).lower() in {"1", "true", "ja"} else 0.0
    for flag in ("governance", "folgenabschaetzung", "meldewege", "loeschregeln"):
        if str(norm.get(flag) or "").strip():
            comp += 18.75
    comp = min(100.0, round(comp or 55.0, 1))

    proc = 40.0
    try:
        paperless = str(norm.get("prozesse_papierlos") or "").split("%")[0]
        if "-" in paperless:
            paperless = paperless.split("-")[-1]
        proc = max(30.0, min(95.0, float(paperless)))
    except Exception:
        pass

    inno_map = {"sehr_offen": 75, "offen": 65, "neutral": 50, "eher_skeptisch": 35, "skeptisch": 25}
    inno = float(inno_map.get(str(norm.get("innovationskultur") or "").lower(), 55))

    return {"digitalisierung": digi, "automatisierung": auto, "compliance": comp, "prozessreife": proc, "innovation": inno}


def overall_score(kpis: Dict[str, float]) -> float:
    weights = {"digitalisierung": 0.2, "automatisierung": 0.2, "compliance": 0.2, "prozessreife": 0.2, "innovation": 0.2}
    s = sum(kpis.get(k, 0.0) * w for k, w in weights.items())
    return round(s, 1)


def quality_badge(score: float) -> str:
    if score >= 85:
        return "EXCELLENT"
    if score >= 70:
        return "GOOD"
    if score >= 55:
        return "FAIR"
    return "BASIC"


def business_case(norm: Dict[str, Any], score: float) -> Dict[str, float]:
    budget_map = {"unter_2000": 1500.0, "2000_10000": 6000.0, "10000_50000": 20000.0, "ueber_50000": 60000.0}
    invest = float(budget_map.get(str(norm.get("investitionsbudget") or "").lower(), 6000.0))
    # Baseline auf 4 Monate trimmen
    seats = 1 if (str(norm.get("unternehmensgroesse")) == "solo") else 5
    per_user_month = 300.0 if score >= 70 else 200.0
    annual_saving = max(0.0, per_user_month * 12 * seats)
    if annual_saving <= 0:
        annual_saving = invest * 4.0

    payback_months = max(0.5, round(invest / (annual_saving / 12.0), 1)) if annual_saving > 0 else 12.0
    roi_y1_pct = round(((annual_saving - invest) / invest) * 100.0, 1) if invest > 0 else 0.0
    return {
        "invest_eur": round(invest, 0),
        "annual_saving_eur": round(annual_saving, 0),
        "payback_months": payback_months,
        "roi_year1_pct": roi_y1_pct,
    }


# ------------------------- Branchenkontext / Appendix ------------------------

def _industry_context_html(branche_key: str, lang: str) -> str:
    """Lädt data/branchenkontext/<branche>_{de|en}.md"""
    fn = f"{branche_key}_{'de' if lang.startswith('de') else 'en'}.md"
    path = os.path.join(BRANCHEN_DIR, fn)
    md = _read_text(path)
    return _md_to_html(md) if md else ""


def _appendix_checklists_html(lang: str) -> str:
    """Sammelt check_*.md aus data/ und data/content/ (max APPENDIX_MAX_DOCS)."""
    if not APPENDIX_CHECKLISTS:
        return ""
    paths: List[str] = []
    for base in (DATA_DIR, CONTENT_DIR):
        try:
            for fn in os.listdir(base):
                if fn.startswith(("check_", "checklist_")) and fn.endswith(".md"):
                    paths.append(os.path.join(base, fn))
        except Exception:
            continue
    paths = sorted(paths)[:APPENDIX_MAX_DOCS]
    html_parts = [_md_to_html(_read_text(p)) for p in paths]
    return "\n".join([h for h in html_parts if h.strip()])


# ------------------------------ OpenAI Wrapper -------------------------------

def _chat_once(model: str, messages: List[Dict[str, str]], temperature: float = 0.2, tokens: int = 800) -> str:
    """Robust gegenüber neuen/alten Parametern."""
    if not _openai_available:
        raise RuntimeError("OpenAI SDK not available")

    client = OpenAI()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_completion_tokens=tokens,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        msg = str(e)
        if "max_tokens" in msg or "unsupported_parameter" in msg.lower():
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=tokens,
            )
            return (resp.choices[0].message.content or "").strip()
        raise


# ------------------------------ Prompt Loader --------------------------------

def _prompt_candidates(name: str, lang: str) -> List[str]:
    """Return ordered candidate paths for a prompt file (locale-aware with graceful fallbacks).
    Search order (examples for name="executive_summary", lang="de"):
      1) <PROMPTS_DIR>/de/executive_summary_de.md
      2) <PROMPTS_DIR>/de/executive_summary.md
      3) <PROMPTS_DIR>/executive_summary_de.md
      4) <PROMPTS_DIR>/executive_summary.md
    """
    lang = (lang or "").lower()
    loc = "de" if lang.startswith("de") else "en"
    suffix = "de" if loc == "de" else "en"
    return [
        os.path.join(PROMPTS_DIR, loc, f"{name}_{suffix}.md"),
        os.path.join(PROMPTS_DIR, loc, f"{name}.md"),
        os.path.join(PROMPTS_DIR, f"{name}_{suffix}.md"),
        os.path.join(PROMPTS_DIR, f"{name}.md"),
    ]


def _prompt(name: str, lang: str) -> str:
    """Load a prompt by name with locale-aware lookup and robust fallback."""
    for cand in _prompt_candidates(name, lang):
        txt = _read_text(cand)
        if txt:
            rel = os.path.relpath(cand, PROMPTS_DIR)
            log.info("Loaded prompt: %s", rel)
            return txt
    log.warning("Prompt not found for %s (%s). Returning empty string.", name, lang)
    return ""


def _gpt_section(section: str, lang: str, context: Dict[str, Any], model: Optional[str] = None) -> str:
    prompt = _prompt(section, lang)
    if not prompt:
        defaults = {
            "executive_summary": "<p><b>Key Takeaways:</b> Status ≥ {score_percent:.1f}%; priorisierte Use‑Cases; 12‑Wochen‑Plan; ROI früh sichtbar machen.</p>",
            "quick_wins": "<ul><li>3–5 Routineprozesse automatisieren</li><li>Standard‑Reports</li><li>FAQ‑Bot</li><li>Reporting automatisieren</li></ul>",
            "roadmap": "<ol><li>W1–2: Setup & Governance</li><li>W3–4: Pilot</li><li>W5–8: Rollout</li><li>W9–12: Skalieren</li></ol>",
            "risks": (
                "<table style='width:100%;border-collapse:collapse'><thead><tr>"
                "<th>#</th><th>Risiko</th><th>Bereich</th><th>P</th><th>I</th><th>Score</th><th>Mitigation</th>"
                "</tr></thead><tbody>"
                "<tr><td>1</td><td>Nichteinhaltung der EU-AI-VO</td><td>Compliance</td><td>4</td><td>5</td><td>20</td>"
                "<td>Regelwerk & Audits einführen</td></tr></tbody></table>"
            ),
            "compliance": "<ul><li>DSFA</li><li>AVV/SCC</li><li>RACI</li><li>Testprotokolle</li></ul>",
        }
        return defaults.get(section, "")
    system = (
        "You are a senior AI strategy analyst. Write concise, actionable, de-buzzworded guidance."
        " Use the provided JSON context. Output HTML only (no markdown fences), valid tags, no <meta>,"
        " no <!DOCTYPE>, no extraneous headers."
    )
    user = prompt.format(**context)
    try:
        return _chat_once(model or DEFAULT_MODEL, [{"role": "system", "content": system}, {"role": "user", "content": user}])
    except Exception as e:
        log.warning("GPT generation failed for %s: %s", section, e)
        return ""


# -------------------------- Live-Sektionen (extern) --------------------------

def build_live_sections(context: Dict[str, Any]) -> Dict[str, Any]:
    from websearch_utils import build_live_sections as _build  # lazy import
    return _build(context)


# -------------------------------- Rendering ----------------------------------

def render_progress_bars(kpis: Dict[str, float]) -> str:
    order = [("Digitalisierung", "digitalisierung"), ("Automatisierung", "automatisierung"),
             ("Compliance", "compliance"), ("Prozessreife", "prozessreife"), ("Innovation", "innovation")]
    parts = []
    for label, key in order:
        pct = int(round(kpis.get(key, 0.0)))
        parts.append(
            f"<div class='bar'><div class='bar__label'>{label}</div>"
            f"<div class='bar__track'><div class='bar__fill' style='width:{pct}%'></div></div>"
            f"<div class='bar__pct'>{pct}%</div></div>"
        )
    return "".join(parts)


def render_benchmark_table(kpis: Dict[str, float], bm: Dict[str, float]) -> str:
    rows = []
    for key, label in [("digitalisierung", "Digitalisierung"), ("automatisierung", "Automatisierung"),
                       ("compliance", "Compliance"), ("prozessreife", "Prozessreife"), ("innovation", "Innovation")]:
        rows.append(f"<tr><td>{label}</td><td>{int(round(kpis.get(key, 0)))}%</td><td>{int(round(bm.get(key, 0)))}%</td></tr>")
    return "<table><thead><tr><th>KPI</th><th>Ihr Wert</th><th>Branchen‑Benchmark</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
        enable_async=False,
    )


def analyze_briefing(raw: Dict[str, Any], lang: str = "de") -> str:
    norm = normalize_briefing(raw)
    miss = missing_fields(norm)
    if miss:
        log.info("Missing normalized fields: %s", miss)

    # KPIs & Benchmarks
    kpis = calculate_kpis(norm)
    score = overall_score(kpis)
    badge = quality_badge(score)
    bm = load_benchmarks(norm)

    # Fragmente
    kpis_progress_html = render_progress_bars(kpis)
    kpis_benchmark_table_html = render_benchmark_table(kpis, bm)
    bc = business_case(norm, score)

    # Kontext für GPT
    gpt_ctx = {
        "briefing": norm,
        "score_percent": score,
        "kpis": kpis,
        "benchmarks": bm,
        "business_case": bc,
        "today": _today(),
    }

    # Kernsektionen
    sections = {
        "executive_summary_html": _gpt_section("executive_summary", lang, gpt_ctx, model=EXEC_SUMMARY_MODEL),
        "quick_wins_html": _gpt_section("quick_wins", lang, gpt_ctx),
        "roadmap_html": _gpt_section("roadmap", lang, gpt_ctx),
        "risks_html": _gpt_section("risks", lang, gpt_ctx),
        "compliance_html": _gpt_section("compliance", lang, gpt_ctx),
        "doc_digest_html": _gpt_section("doc_digest", lang, gpt_ctx),
    }

    # Optionale Add‑ons
    for extra in ["business", "recommendations", "gamechanger", "vision", "persona", "praxisbeispiel", "coach", "tools", "foerderprogramme"]:
        html = _gpt_section(extra, lang, gpt_ctx)
        if html.strip():
            sections[f"{extra}_html"] = html

    # Branchenkontext & Appendix
    sections["industry_context_html"] = _industry_context_html(norm.get("branche") or "", lang)
    sections["appendix_checklists_html"] = _appendix_checklists_html(lang)

    # Live-Kacheln mit Bundesland-Filter
    live = build_live_sections({
        "branche": norm.get("branche_label") or norm.get("branche"),
        "size": norm.get("unternehmensgroesse_label") or norm.get("unternehmensgroesse"),
        "country": "DE",
        "region_code": norm.get("bundesland_code") or "",
    })
    flags = {"eu_host_check": True, "regulatory": True, "case_studies": True}

    # Rendering
    env = _env()
    tpl_name = "pdf_template.html" if lang.startswith("de") else "pdf_template_en.html"
    tpl = env.get_template(tpl_name)
    html = tpl.render(
        meta={"title": "KI-Status-Report" if lang.startswith("de") else "AI Status Report", "date": _today(), "lang": lang},
        briefing=norm,
        score_percent=score,
        quality_badge=badge,
        kpis_progress_html=kpis_progress_html,
        kpis_benchmark_table_html=kpis_benchmark_table_html,
        business_case=bc,
        sections=sections,
        live=live,
        flags=flags,
    )
    return html


def produce_admin_attachments(raw: Dict[str, Any]) -> Dict[str, str]:
    norm = normalize_briefing(raw)
    miss = missing_fields(norm)
    return {
        "briefing_raw.json": json.dumps(raw, ensure_ascii=False, indent=2),
        "briefing_normalized.json": json.dumps(norm, ensure_ascii=False, indent=2),
        "briefing_missing_fields.json": json.dumps({"missing": miss}, ensure_ascii=False, indent=2),
    }
