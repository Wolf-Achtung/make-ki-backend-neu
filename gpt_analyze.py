# gpt_analyze.py — Direct Renderer + Enhanced Innenleben (+ Live Updates + Readiness-Benchmark + Admin-Rohdaten)
# Stand: 2025-09-29

from __future__ import annotations

import glob
import io
import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from websearch_utils import collect_recent_items  # Live-Sektionen (Tavily etc.)

# -----------------------------------------------------------------------------
# Pfade & Konfiguration
# -----------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.getenv("APP_BASE", os.getcwd()))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
PROMPTS_DIR = os.getenv("PROMPTS_DIR", os.path.join(BASE_DIR, "prompts"))
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))

# Template-Namen über ENV, ansonsten sprachbasiert
TEMPLATE_DE = os.getenv("TEMPLATE_DE", "pdf_template.html")
TEMPLATE_EN = os.getenv("TEMPLATE_EN", "pdf_template_en.html")
PDF_TEMPLATE_NAME = os.getenv("PDF_TEMPLATE_NAME")  # optional override

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("gpt_analyze")

# -----------------------------------------------------------------------------
# OpenAI optional
# -----------------------------------------------------------------------------
_openai = None
try:
    from openai import OpenAI  # type: ignore

    if os.getenv("OPENAI_API_KEY"):
        _openai = OpenAI()
        log.info("OpenAI Client initialisiert")
except Exception as e:
    log.warning(f"OpenAI nicht verfügbar: {e}")
    _openai = None


# -----------------------------------------------------------------------------
# Jinja Environment
# -----------------------------------------------------------------------------
def make_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader([TEMPLATE_DIR, BASE_DIR]),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    def currency(v: Any, symbol: str = "€") -> str:
        try:
            n = int(float(str(v).replace(",", ".").replace(" ", "").replace("€", "")))
        except Exception:
            n = 0
        s = f"{n:,}"
        if symbol == "€":
            s = s.replace(",", ".")
        return f"{s} {symbol}"

    env.filters["currency"] = currency
    return env


# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------
def _safe_int(x: Any, default: int = 0) -> int:
    try:
        if isinstance(x, (int, float)):
            return int(x)
        s = re.sub(r"[^\d-]", "", str(x))
        return int(s) if s else default
    except Exception:
        return default


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).replace(",", ".")
        s = re.sub(r"[^\d\.-]", "", s)
        return float(s) if s and s not in {".", "-", ""} else default
    except Exception:
        return default


def _readiness_label(score: int, lang: str = "de") -> str:
    s = _safe_int(score, 50)
    if lang.startswith("de"):
        return (
            "Anfänger",
            "Grundlegend",
            "Fortgeschritten",
            "Reif",
            "Führend",
        )[0 if s < 30 else 1 if s < 50 else 2 if s < 70 else 3 if s < 85 else 4]
    return (
        "Beginner",
        "Basic",
        "Advanced",
        "Mature",
        "Leading",
    )[0 if s < 30 else 1 if s < 50 else 2 if s < 70 else 3 if s < 85 else 4]


def _debug_list_prompts() -> None:
    try:
        files = sorted(
            [os.path.basename(p) for p in glob.glob(os.path.join(PROMPTS_DIR, "*"))]
        )
        log.info("PROMPTS_DIR=%s, found=%s", PROMPTS_DIR, files)
    except Exception as e:
        log.warning("Prompt listing failed: %s", e)


def _get_bool(name: str, default: bool = False) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if v in {"1", "true", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _load_json_if_exists(path: str) -> Optional[Dict[str, Any]]:
    try:
        if os.path.exists(path):
            with io.open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log.warning("Konnte JSON nicht laden (%s): %s", path, e)
    return None


# -----------------------------------------------------------------------------
# KPI-Berechnung
# -----------------------------------------------------------------------------
def _budget_amount(budget_str: Any) -> int:
    if not budget_str:
        return 6000
    s = str(budget_str).lower().replace("€", "").replace(" ", "").replace(".", "")
    mapping = {
        "unter_2000": 1500,
        "unter2000": 1500,
        "2000-10000": 6000,
        "2.000-10.000": 6000,
        "10000-50000": 25000,
        "10.000-50.000": 25000,
        "ueber_50000": 75000,
        "ueber50000": 75000,
        "über50000": 75000,
    }
    for k, v in mapping.items():
        if k in s or s in k:
            return v
    m = re.findall(r"\d+", s)
    if m:
        val = int(m[0])
        return val * 1000 if val < 100 else val
    return 6000


def calculate_kpis_from_answers(answers: Dict[str, Any]) -> Dict[str, Any]:
    digital = min(10, max(1, _safe_int(answers.get("digitalisierungsgrad", 5), 5)))
    auto_map = {
        "sehr_niedrig": 10,
        "eher_niedrig": 30,
        "mittel": 50,
        "eher_hoch": 70,
        "sehr_hoch": 85,
    }
    auto = auto_map.get(
        str(answers.get("automatisierungsgrad", "mittel")).lower().replace(" ", "_"),
        50,
    )
    papier_map = {"0-20": 20, "21-50": 40, "51-80": 65, "81-100": 85}
    papier = papier_map.get(
        str(answers.get("prozesse_papierlos", "51-80")).replace("_", "-"), 65
    )
    risk = min(5, max(1, _safe_int(answers.get("risikofreude", 3), 3)))
    kw_map = {
        "anfaenger": 20,
        "anfänger": 20,
        "grundkenntnisse": 40,
        "fortgeschritten": 70,
        "experte": 90,
    }
    kw = kw_map.get(str(answers.get("ki_knowhow", "grundkenntnisse")).lower(), 40)

    readiness = int(
        digital * 3.0 + (auto / 10) * 2.5 + (papier / 10) * 2.0 + (risk * 2) * 2.0 + (kw / 10) * 2.0 + 15
    )
    readiness = max(35, min(95, readiness))

    budget = _budget_amount(answers.get("budget", "2000-10000"))
    efficiency_gap = 100 - auto
    kpi_eff = max(25, int(efficiency_gap * 0.75))
    kpi_cost = int(kpi_eff * 0.8)

    branche = str(answers.get("branche", "beratung")).lower()
    branche_mult = {
        "beratung": 1.3,
        "it": 1.4,
        "marketing": 1.25,
        "handel": 1.15,
        "industrie": 1.2,
        "produktion": 1.2,
        "finanzen": 1.35,
        "gesundheit": 1.1,
        "logistik": 1.15,
        "bildung": 1.05,
    }.get(branche, 1.1)

    size = str(answers.get("unternehmensgroesse", "2-10")).lower()
    size_cost_base = {
        "1": 60000,
        "solo": 60000,
        "2-10": 300000,
        "11-100": 3000000,
        "101-500": 15000000,
    }.get(size, 300000)
    base_saving = int(size_cost_base * (kpi_cost / 100))
    annual_saving = max(int(base_saving * branche_mult), int(budget * 2.5))

    roi_months = max(3, min(18, int((budget / annual_saving) * 10))) if annual_saving > 0 else 12

    compliance = 40
    if answers.get("datenschutzbeauftragter") in {"ja", "extern", "yes"}:
        compliance += 30
    if answers.get("dsgvo_folgenabschaetzung") in {"ja", "teilweise"}:
        compliance += 25
    if answers.get("eu_ai_act_kenntnis") in {"gut", "sehr_gut"}:
        compliance += 25
    elif answers.get("eu_ai_act_kenntnis") in {"grundkenntnisse"}:
        compliance += 15
    compliance = max(45, min(100, compliance))

    has_inno_team = answers.get("innovationsteam") in {"ja", "internes_team"}
    innovation = int(risk * 18 + (kw / 100) * 35 + (25 if has_inno_team else 10) + (digital / 10) * 40)
    innovation = max(40, min(95, innovation))

    return {
        "readiness_score": readiness,
        "kpi_efficiency": kpi_eff,
        "kpi_cost_saving": kpi_cost,
        "kpi_roi_months": roi_months,
        "kpi_compliance": compliance,
        "kpi_innovation": innovation,
        "roi_investment": budget,
        "roi_annual_saving": annual_saving,
        "roi_three_year": annual_saving * 3 - budget,
        "digitalisierungsgrad": digital,
        "automatisierungsgrad": auto,
        "papierlos": papier,
        "risikofreude": risk,
    }


def calculate_optimistic_kpis(raw: Dict[str, Any]) -> Dict[str, Any]:
    k = dict(raw)
    s = k["readiness_score"]
    k["readiness_score"] = min(92, (s + 10 if s < 40 else s + 8 if s < 60 else s + 5))
    e = k["kpi_efficiency"]
    k["kpi_efficiency"] = min(85, (e + 15 if e < 40 else e + 10))
    if k["kpi_roi_months"] > 12:
        k["kpi_roi_months"] = max(8, k["kpi_roi_months"] - 4)
    elif k["kpi_roi_months"] > 6:
        k["kpi_roi_months"] = max(4, k["kpi_roi_months"] - 2)
    if k["roi_annual_saving"] < k["roi_investment"] * 2:
        k["roi_annual_saving"] = int(k["roi_investment"] * 2.5)
    else:
        k["roi_annual_saving"] = int(k["roi_annual_saving"] * 1.2)
    k["roi_three_year"] = int(k["roi_annual_saving"] * 3 - k["roi_investment"])
    k["kpi_innovation"] = min(90, k["kpi_innovation"] + 15)
    k["kpi_compliance"] = min(85, k["kpi_compliance"])
    k["kpi_cost_saving"] = min(75, int(k["kpi_efficiency"] * 0.85))
    return k


def validate_kpis(k: Dict[str, Any]) -> Dict[str, Any]:
    if k["roi_annual_saving"] > k["roi_investment"] * 4:
        k["roi_annual_saving"] = int(k["roi_investment"] * 4)
        k["roi_three_year"] = int(k["roi_annual_saving"] * 3 - k["roi_investment"])
    if k["readiness_score"] > 85:
        k["readiness_score"] = 85
    # Mindest-Payback: 4 Monate
    if k["kpi_roi_months"] < 4:
        k["kpi_roi_months"] = 4
    return k


# -----------------------------------------------------------------------------
# Labels / Vars
# -----------------------------------------------------------------------------
def get_company_size_label(size: str, lang: str) -> str:
    labels = {
        "de": {
            "1": "1 (Solo-Selbstständig)",
            "solo": "1 (Solo-Selbstständig)",
            "2-10": "2-10 (Kleines Team)",
            "11-100": "11-100 (KMU)",
            "101-500": "101-500 (Mittelstand)",
            "ueber_500": "Über 500 (Großunternehmen)",
        },
        "en": {
            "1": "1 (Freelancer)",
            "solo": "1 (Freelancer)",
            "2-10": "2-10 (Small Team)",
            "11-100": "11-100 (SME)",
            "101-500": "101-500 (Mid-size)",
            "ueber_500": "Over 500 (Enterprise)",
        },
    }
    return labels.get(lang, labels["de"]).get(str(size).lower(), str(size))


def get_knowledge_label(knowledge: str, lang: str) -> str:
    labels = {
        "de": {
            "anfaenger": "Anfänger",
            "grundkenntnisse": "Grundkenntnisse",
            "fortgeschritten": "Fortgeschritten",
            "experte": "Experte",
        },
        "en": {
            "anfaenger": "Beginner",
            "grundkenntnisse": "Basic Knowledge",
            "fortgeschritten": "Advanced",
            "experte": "Expert",
        },
    }
    return labels.get(lang, labels["de"]).get(str(knowledge).lower(), str(knowledge))


def _readiness_level(score: int, lang: str) -> str:
    return _readiness_label(score, lang)


def get_primary_quick_win(form_data: Dict[str, Any], lang: str) -> str:
    ucs = form_data.get("ki_usecases") or []
    if isinstance(ucs, str):
        ucs = [ucs]
    if not ucs:
        return "Prozessautomatisierung" if lang.startswith("de") else "Process Automation"
    mapping = {
        "de": {
            "texterstellung": "Automatisierte Texterstellung",
            "spracherkennung": "Meeting-Transkription",
            "prozessautomatisierung": "Workflow-Automatisierung",
            "datenanalyse": "Automatisierte Reports",
            "kundensupport": "KI-Chatbot",
            "wissensmanagement": "Wissensdatenbank",
            "marketing": "Content-Automation",
        },
        "en": {
            "texterstellung": "Automated Writing",
            "spracherkennung": "Meeting Transcription",
            "prozessautomatisierung": "Workflow Automation",
            "datenanalyse": "Automated Reports",
            "kundensupport": "AI Chatbot",
            "wissensmanagement": "Knowledge Base",
            "marketing": "Content Automation",
        },
    }
    d = mapping.get(lang, mapping["de"])
    key = re.sub(r"[\s\-]", "", str(ucs[0]).lower())
    for k, v in d.items():
        if k in key or key in k:
            return v
    return d["prozessautomatisierung"]


# -----------------------------------------------------------------------------
# Branchendaten / Benchmark
# -----------------------------------------------------------------------------
def _load_branch_benchmark(branche: str) -> Dict[str, Any]:
    """
    Lädt optionale Benchmarks aus data/benchmarks/<branche>.json;
    Fallback auf konservative Standardwerte.
    """
    safe = re.sub(r"[^a-z0-9_\-]", "", str(branche).lower())
    candidates = [
        os.path.join(DATA_DIR, "benchmarks", f"{safe}.json"),
        os.path.join(DATA_DIR, "benchmarks", "default.json"),
    ]
    for p in candidates:
        data = _load_json_if_exists(p)
        if data:
            return data

    # Fallback konservativ (geeignet für Beratung)
    return {
        "name": "beratung",
        "digitalization": 80,
        "automation": 75,
        "paperless": 65,
        "compliance": 80,
        "innovation": 85,
        "efficiency": 60,  # Branchenschnitt
    }


def _build_benchmark_rows(k: Dict[str, Any], bench: Dict[str, Any], lang: str) -> List[Dict[str, str]]:
    def _row(label_de: str, label_en: str, our: float, bm: float, is_percent: bool = True) -> Dict[str, str]:
        delta = our - bm
        interp = (
            ("besser" if delta >= 0 else "schlechter")
            if lang.startswith("de")
            else ("better" if delta >= 0 else "worse")
        )
        fmt = lambda v: f"{int(round(v))}%" if is_percent else f"{int(round(v))}"
        return {
            "kpi": label_de if lang.startswith("de") else label_en,
            "our": fmt(our),
            "bench": fmt(bm),
            "delta": f"{int(round(delta))}",
            "interp": interp,
        }

    rows = [
        _row("Digitalisierung", "Digitalization", k.get("digitalisierungsgrad", 50) * 10, bench.get("digitalization", 70)),
        _row("Automatisierung", "Automation", k.get("automatisierungsgrad", 50), bench.get("automation", 60)),
        _row("Papierlosigkeit", "Paperless", k.get("papierlos", 65), bench.get("paperless", 60)),
        _row("Compliance", "Compliance", k.get("kpi_compliance", 70), bench.get("compliance", 75)),
        _row("Innovation", "Innovation", k.get("kpi_innovation", 80), bench.get("innovation", 75)),
        _row("Effizienz (Punktscore)", "Efficiency (score)", k.get("kpi_efficiency", 40), bench.get("efficiency", 50), is_percent=False),
    ]
    return rows


def _make_benchmark_html(rows: List[Dict[str, str]], lang: str) -> str:
    head = (
        "<thead><tr>"
        + ("<th>KPI</th><th>Unser Wert</th><th>Benchmark</th><th>Δ (pp)</th><th>Interpretation</th>"
           if lang.startswith("de")
           else "<th>KPI</th><th>Our value</th><th>Benchmark</th><th>Δ (pp)</th><th>Interpretation</th>")
        + "</tr></thead>"
    )
    body = ["<tbody>"]
    for r in rows:
        body.append(
            f"<tr><td>{r['kpi']}</td><td>{r['our']}</td><td>{r['bench']}</td><td>{r['delta']}</td><td>{r['interp']}</td></tr>"
        )
    body.append("</tbody>")
    return "<table>" + head + "".join(body) + "</table>"


# -----------------------------------------------------------------------------
# Template-Variablen
# -----------------------------------------------------------------------------
def get_template_variables(form_data: Dict[str, Any], lang: str = "de") -> Dict[str, Any]:
    raw = calculate_kpis_from_answers(form_data)
    k = validate_kpis(calculate_optimistic_kpis(raw))

    size = str(form_data.get("unternehmensgroesse", "2-10"))
    branche = form_data.get("branche", "beratung")

    # Readiness-Benchmark zusammenbauen
    bench = _load_branch_benchmark(branche)
    bench_rows = _build_benchmark_rows(
        {
            **k,
            "digitalisierungsgrad": raw.get("digitalisierungsgrad", 5),
            "automatisierungsgrad": raw.get("automatisierungsgrad", 50),
            "papierlos": raw.get("papierlos", 65),
        },
        bench,
        lang,
    )
    benchmark_html = _make_benchmark_html(bench_rows, lang)

    # Variablen
    vars = {
        # Zeit/Meta
        "datum": datetime.now().strftime("%d.%m.%Y"),
        "today": datetime.now().strftime("%Y-%m-%d"),
        "generation_date": datetime.now().strftime("%d.%m.%Y"),
        "copyright_year": datetime.now().year,
        "meta": {
            "title": "KI-Statusbericht & Handlungsempfehlungen"
            if lang.startswith("de")
            else "AI Status Report & Recommendations",
            "subtitle": f"AI Readiness: {k['readiness_score']}%",
            "date": datetime.now().strftime("%d.%m.%Y"),
            "lang": lang,
            "version": "3.2",
        },
        "lang": lang,
        "is_german": lang.startswith("de"),

        # Firma
        "branche": branche,
        "bundesland": form_data.get("bundesland", "BE"),
        "hauptleistung": form_data.get("hauptleistung", ""),
        "unternehmensgroesse": size,
        "company_size_label": get_company_size_label(size, lang),

        # KPIs
        "score_percent": k["readiness_score"],
        "readiness_level": _readiness_level(k["readiness_score"], lang),
        "kpi_efficiency": k["kpi_efficiency"],
        "kpi_cost_saving": k["kpi_cost_saving"],
        "kpi_roi_months": k["kpi_roi_months"],
        "kpi_compliance": k["kpi_compliance"],
        "kpi_innovation": k["kpi_innovation"],

        # Budget/ROI
        "budget": form_data.get("budget", "2000-10000"),
        "budget_amount": k["roi_investment"],
        "roi_investment": k["roi_investment"],
        "roi_annual_saving": k["roi_annual_saving"],
        "roi_three_year": k["roi_three_year"],

        # KI-Daten
        "ki_usecases": form_data.get("ki_usecases", []),
        "ki_hemmnisse": form_data.get("ki_hemmnisse", []),
        "ki_knowhow": form_data.get("ki_knowhow", "grundkenntnisse"),
        "ki_knowhow_label": get_knowledge_label(form_data.get("ki_knowhow", "grundkenntnisse"), lang),
        "automatisierungsgrad": form_data.get("automatisierungsgrad", "mittel"),
        "automatisierungsgrad_percent": raw.get("automatisierungsgrad", 50),
        "prozesse_papierlos": form_data.get("prozesse_papierlos", "51-80"),
        "quick_win_primary": get_primary_quick_win(form_data, lang),

        # Tabellen (optional vom Template genutzt)
        "funding_programs": form_data.get("funding_programs", []),
        "tools": form_data.get("tools", []),
        "foerderprogramme_table": form_data.get("funding_programs", []),
        "tools_table": form_data.get("tools", []),

        # Readiness-Benchmark (neu)
        "readiness_benchmark_rows": bench_rows,
        "readiness_benchmark_html": benchmark_html,
        "readiness_benchmark_label": bench.get("name", branche),

        # Admin-Rohdaten (JSON als String; wird von postprocess_report.py angehängt)
        "admin_form_json": json.dumps(form_data, ensure_ascii=False, indent=2),
        "admin_subject": (
            f"Neuer AI Status Report – Rohdaten ({branche}, {size})"
            if not lang.startswith("de")
            else f"Neuer KI-Status-Report – Rohdaten ({branche}, {size})"
        ),
        "admin_note": "Automatisch generierte Rohdaten des Fragebogens (JSON).",
        # Links
        "feedback_link": "https://make.ki-sicherheit.jetzt/feedback/feedback.html",
    }
    if vars["kpi_efficiency"] == 0:
        vars["kpi_efficiency"] = 1
    return vars


# -----------------------------------------------------------------------------
# Prompt-Engine
# -----------------------------------------------------------------------------
class PromptLoader:
    def __init__(self, directory: str = PROMPTS_DIR):
        self.dir = directory
        self.env = Environment(
            loader=FileSystemLoader([self.dir]),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def _render_md_plain(self, text: str, ctx: Dict[str, Any]) -> str:
        # 1) Jinja-Blöcke in .md ignorieren
        text = re.sub(r"\{%.*?%\}", "", text, flags=re.S)

        # 2) Platzhalter {{ var }} ersetzen
        def repl(m: re.Match) -> str:
            key = m.group(1).strip()
            val = ctx.get(key, "")
            return str(val) if val is not None else ""

        out = re.sub(r"\{\{\s*([a-zA-Z0-9_\.]+)\s*\}\}", repl, text)
        return out

    def render(self, name: str, ctx: Dict[str, Any], lang: str) -> str:
        candidates = [
            f"{name}_{lang}.md",
            f"{name}.md",
            f"{name}_{lang}.jinja",
            f"{name}.jinja",
        ]
        last_err = None
        for fn in candidates:
            path = os.path.join(self.dir, fn)
            try:
                if fn.endswith(".md"):
                    with io.open(path, "r", encoding="utf-8") as f:
                        html = self._render_md_plain(f.read(), ctx)
                        log.info("Prompt resolved: %s -> %s (mode=md-plain)", name, fn)
                        return html
                else:
                    tpl = self.env.get_template(fn)
                    log.info("Prompt resolved: %s -> %s (mode=jinja)", name, fn)
                    return tpl.render(**ctx)
            except Exception as e:
                last_err = e
                continue
        raise FileNotFoundError(f"Prompt nicht renderbar: {name} ({last_err})")


# -----------------------------------------------------------------------------
# GPT optional
# -----------------------------------------------------------------------------
def _gpt(prompt: str, section: str, lang: str = "de") -> Optional[str]:
    if not _openai:
        return None
    try:
        system_msg = (
            "Du bist ein KI-Strategieberater. Schreibe prägnante, narrative Abschnitte "
            "in reinem HTML (<p>…</p>, optional <strong>), ohne Listen/Tabellen. "
            "Kein Payback < 4 Monaten nennen. Werte nicht über 100% ausgeben."
            if lang.startswith("de")
            else "You are an AI strategy consultant. Write concise, narrative sections "
            "in plain HTML (<p>…</p>, optional <strong>), no lists/tables. "
            "Do not claim payback under 4 months. Do not output values > 100%."
        )
        resp = _openai.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            temperature=_safe_float(os.getenv("LLM_TEMPERATURE", 0.6), 0.6),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", 1200)),
        )
        return resp.choices[0].message.content
    except Exception as e:
        log.warning(f"GPT API Fehler ({section}): {e}")
        return None


# -----------------------------------------------------------------------------
# Fallback-Generatoren (narrativ)
# -----------------------------------------------------------------------------
def _p(s: str) -> str:
    return f"<p>{s}</p>"


def fallback_executive_summary(v: Dict[str, Any], lang: str = "de") -> str:
    if lang.startswith("de"):
        return _p(
            f"<strong>Ausgangslage:</strong> Mit {v.get('score_percent',50)}% KI-Reifegrad besteht eine solide Basis. "
            f"Starten Sie mit {v.get('quick_win_primary','Quick Wins')} und professionalisieren Sie Schritt für Schritt."
        ) + _p(
            f"<strong>Wirtschaftlichkeit:</strong> Investition {v.get('roi_investment',10000)} €, "
            f"Break-even in {v.get('kpi_roi_months',12)} Monaten, jährliche Einsparungen {v.get('roi_annual_saving',20000)} €."
        )
    return _p("With a solid starting point, begin with pragmatic quick wins and scale responsibly.")


def fallback_business(v: Dict[str, Any], lang: str = "de") -> str:
    if lang.startswith("de"):
        return _p(
            f"Konservativer Business Case: Investition {v.get('roi_investment',10000)} €, "
            f"jährlicher Nutzen {v.get('roi_annual_saving',20000)} €, "
            f"3-Jahres-Nettonutzen {v.get('roi_three_year',50000)} €."
        )
    return _p("Conservative business case with positive year-one cash-flow.")


def fallback_generic(section: str, lang: str = "de") -> str:
    return (
        _p("Die Inhalte dieser Sektion wurden generiert und stehen bereit.")
        if lang.startswith("de")
        else _p("This section has been generated and is ready.")
    )


def generate_quick_wins(answers: Dict[str, Any], kpis: Dict[str, Any], lang: str = "de") -> str:
    primary = get_primary_quick_win(answers, lang)
    if lang.startswith("de"):
        return _p(f"Sofort starten mit <strong>{primary}</strong>; sichtbare Ergebnisse in 2–4 Wochen.")
    return _p("Start with your primary quick win; visible results in 2–4 weeks.")


def generate_risk_analysis(answers: Dict[str, Any], kpis: Dict[str, Any], lang: str = "de") -> str:
    if lang.startswith("de"):
        return _p("Risikomanagement: Zuständigkeiten klären (DPO/DSFA), schrittweise Einführung, Shadow-IT vermeiden.")
    return _p("Risk management: clarify GDPR/DPIA, phased rollout, avoid shadow IT.")


def generate_roadmap(answers: Dict[str, Any], kpis: Dict[str, Any], lang: str = "de") -> str:
    b = kpis.get("roi_investment", 10000)
    m = kpis.get("kpi_roi_months", 12)
    if lang.startswith("de"):
        return _p(f"Roadmap: 0–30 Tage Quick-Win (ca. {int(b*0.2)} €); 31–90 Tage Scale-Up; 91–180 Tage Optimierung; Break-even nach ~{m} Monaten.")
    return _p("Roadmap: quick win, scale up, optimize; break-even in the first year.")


# -----------------------------------------------------------------------------
# Tool-/Funding-Kataloge (kurz, statisch)
# -----------------------------------------------------------------------------
TOOL_DATABASE = {
    "texterstellung": [
        {"name": "DeepL Write", "desc": "DSGVO-freundliches Schreibtool", "use_case": "E-Mails, Berichte", "cost": "Free/Pro", "fit_score": 95},
        {"name": "Jasper AI", "desc": "Content-Automation", "use_case": "Blog/Social", "cost": "ab 39€", "fit_score": 80},
    ],
    "prozessautomatisierung": [
        {"name": "n8n", "desc": "Open-Source Workflows", "use_case": "APIs/Automation", "cost": "Free", "fit_score": 92},
        {"name": "Make", "desc": "Low-Code Automatisierung", "use_case": "Workflows", "cost": "ab 9€", "fit_score": 88},
    ],
    "datenanalyse": [
        {"name": "Metabase", "desc": "Open-Source BI", "use_case": "Dashboards", "cost": "Free/Cloud", "fit_score": 85},
    ],
    "kundensupport": [
        {"name": "Typebot", "desc": "Open-Source Chatbot", "use_case": "FAQ/Leads", "cost": "Free", "fit_score": 90},
    ],
}


def match_tools_to_company(answers: Dict[str, Any], lang: str = "de") -> str:
    ucs = answers.get("ki_usecases") or []
    if isinstance(ucs, str):
        ucs = [ucs]
    if not ucs:
        ucs = ["prozessautomatisierung"]
    picks, used = [], set()
    for uc in ucs:
        key = re.sub(r"[\s\-]", "", str(uc).lower())
        for dbk, tools in TOOL_DATABASE.items():
            if dbk in key or key in dbk:
                best = sorted(tools, key=lambda t: -t.get("fit_score", 0))
                for t in best:
                    if t["name"] not in used:
                        picks.append(t)
                        used.add(t["name"])
                        break
                break
    if not picks:
        return (
            _p("Individuelle Tool-Empfehlungen folgen nach Detailklärung.")
            if lang.startswith("de")
            else _p("Individual tool recommendations will follow.")
        )
    out = []
    for t in picks[:6]:
        if lang.startswith("de"):
            out.append(f"{t['name']} – {t['desc']} ({t['use_case']}, {t['cost']}). Hinweis: Prüfen Sie stets AVV/DPA & Region.")
        else:
            out.append(f"{t['name']} – {t['desc']} ({t['use_case']}, {t['cost']}). Note: Always verify DPA & region.")
    return _p(" ".join(out))


FUNDING_PROGRAMS = {
    "bundesweit": [
        {"name": "go-digital", "amount": "bis 16.500€ (50%)", "deadline": "laufend", "fit": 90},
        {"name": "Digital Jetzt", "amount": "bis 50.000€ (40%)", "deadline": "bis 31.12.2025", "fit": 85},
        {"name": "KfW-Digitalisierungskredit", "amount": "Kredit, günstiger Zins", "deadline": "laufend", "fit": 80},
    ],
    "berlin": [
        {"name": "Digitalprämie Berlin", "amount": "bis 17.000€", "deadline": "31.12.2025", "fit": 88},
        {"name": "Mittelstand 4.0", "amount": "Beratung", "deadline": "laufend", "fit": 100},
    ],
}


def match_funding_programs(answers: Dict[str, Any], lang: str = "de") -> str:
    state = str(answers.get("bundesland", "BE")).upper()
    region_map = {"BE": "berlin"}
    region = region_map.get(state)
    programs = list(FUNDING_PROGRAMS.get("bundesweit", []))
    if region and region in FUNDING_PROGRAMS:
        programs += FUNDING_PROGRAMS[region]
    programs = sorted(programs, key=lambda p: -p.get("fit", 0))[:6]
    if not programs:
        return _p("Aktuell keine passenden Programme.") if lang.startswith("de") else _p("No suitable programs found.")
    rows = "; ".join([f"{p['name']} ({p['amount']})" for p in programs])
    return _p(("Förderoptionen: " + rows) if lang.startswith("de") else ("Funding options: " + rows))


# -----------------------------------------------------------------------------
# Sektionen-Renderer
# -----------------------------------------------------------------------------
def _render_section(name: str, ctx: Dict[str, Any], lang: str = "de") -> str:
    # 1) Prompt laden
    prompt = None
    try:
        prompt = PromptLoader().render(name, ctx, lang)
    except Exception as e:
        log.warning(f"Prompt-Rendering fehlgeschlagen [{name}]: {e}")
    # 2) GPT (optional)
    if prompt:
        html = _gpt(prompt, name, lang)
        if html and len(html.strip()) > 80:
            return html
    # 3) Fallback/Generator
    if name == "executive_summary":
        return fallback_executive_summary(ctx, lang)
    if name == "business":
        return fallback_business(ctx, lang)
    if name == "quick_wins":
        return generate_quick_wins(ctx, ctx, lang)
    if name == "risks":
        return generate_risk_analysis(ctx, ctx, lang)
    if name == "roadmap":
        return generate_roadmap(ctx, ctx, lang)
    if name == "tools":
        return match_tools_to_company(ctx, lang)
    if name == "foerderprogramme":
        return match_funding_programs(ctx, lang)
    return fallback_generic(name, lang)


# -----------------------------------------------------------------------------
# Narrative Sanitizer
# -----------------------------------------------------------------------------
def _sanitize_html_block(html: str) -> str:
    if not isinstance(html, str):
        return ""
    s = html
    items = re.findall(r"<li[^>]*>(.*?)</li>", s, flags=re.I | re.S)
    if items:
        cleaned = []
        for it in items:
            txt = re.sub(r"<[^>]+>", "", it)
            txt = re.sub(r"^\s*(?:\d+[\.\)]|[-\*•])\s*", "", txt)
            if txt.strip():
                cleaned.append(txt.strip())
        if cleaned:
            s = re.sub(r"</?ul[^>]*>|</?ol[^>]*>|<li[^>]*>.*?</li>", "", s, flags=re.I | re.S)
            s += "".join([f"<p>{c}</p>" for c in cleaned])
    s = re.sub(r"</?(ul|ol)[^>]*>", "", s, flags=re.I)
    s = re.sub(r"(<p[^>]*>)\s*\d+[\.\)]\s*", r"\1", s)
    if "<p" not in s.strip().lower():
        s = f"<p>{re.sub(r'<[^>]+>', '', s).strip()}</p>"
    return s


def sanitize_narrative(context: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(context)
    for k, v in list(out.items()):
        if isinstance(v, str) and k.endswith("_html"):
            out[k] = _sanitize_html_block(v)
    return out


def _clamp_percents_in_html(ctx: Dict[str, Any]) -> Dict[str, Any]:
    pct = re.compile(r"(\d{1,3})%")
    for k, v in list(ctx.items()):
        if isinstance(v, str) and k.endswith("_html"):
            ctx[k] = pct.sub(lambda m: f"{min(int(m.group(1)),100)}%", v)
    return ctx


# -----------------------------------------------------------------------------
# Live Updates (Tavily)
# -----------------------------------------------------------------------------
def inject_live_updates(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fügt news_html / tools_rich_html / funding_rich_html hinzu (wenn erlaubt & Key vorhanden).
    """
    if not _get_bool("ALLOW_TAVILY", True) or not os.getenv("TAVILY_API_KEY"):
        return ctx
    try:
        adds = collect_recent_items(ctx, lang=ctx.get("lang", "de"))
        ctx.update(adds)
        ctx["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    except Exception as e:
        log.warning("inject_live_updates failed: %s", e)
    return ctx


# -----------------------------------------------------------------------------
# Innenleben-API
# -----------------------------------------------------------------------------
def analyze_briefing_enhanced(body: Dict[str, Any], lang: str = "de") -> Dict[str, Any]:
    lang = "de" if str(lang).lower().startswith("de") else "en"
    vars = get_template_variables(body, lang)

    sections: List[str] = [
        "executive_summary",
        "business",
        "persona",
        "quick_wins",
        "risks",
        "recommendations",
        "roadmap",
        "praxisbeispiel",
        "coach",
        "vision",
        "gamechanger",
        "compliance",
        "foerderprogramme",
        "tools",
    ]

    ctx: Dict[str, Any] = dict(vars)
    for sec in sections:
        key = "exec_summary_html" if sec == "executive_summary" else f"{sec}_html"
        ctx[key] = _render_section(sec, vars, lang)

    # Sektionen ohne Inhalt auffüllen
    for aux in [
        "persona_html",
        "recommendations_html",
        "praxisbeispiel_html",
        "vision_html",
        "gamechanger_html",
        "coach_html",
        "compliance_html",
    ]:
        if not (ctx.get(aux) and len(ctx.get(aux, "").strip()) > 40):
            ctx[aux] = fallback_generic(aux[:-5] if aux.endswith("_html") else aux, lang)

    # Live-Updates (News/Tools/Förderungen) einmischen
    ctx = inject_live_updates(ctx)

    return ctx


# -----------------------------------------------------------------------------
# Außenhaut: Renderer
# -----------------------------------------------------------------------------
def analyze_briefing(form_data: Dict[str, Any], lang: str = "de") -> str:
    log.info("gpt_analyze loaded (direct): %s", os.path.join(BASE_DIR, "gpt_analyze.py"))
    _debug_list_prompts()

    env = make_env()
    try:
        # Template anhand Sprache / ENV wählen
        chosen = PDF_TEMPLATE_NAME
        if not chosen:
            chosen = TEMPLATE_DE if str(lang).lower().startswith("de") else TEMPLATE_EN

        try:
            template = env.get_template(chosen)
        except Exception:
            html_files = [f for f in os.listdir(TEMPLATE_DIR) if f.endswith(".html")]
            template = env.get_template(html_files[0]) if html_files else None
        if not template:
            raise RuntimeError("Kein HTML-Template gefunden")

        ctx = analyze_briefing_enhanced(form_data, lang)
        ctx = sanitize_narrative(ctx)
        ctx = _clamp_percents_in_html(ctx)

        # Guard: wichtige Kapitel nie leer
        def _ensure_narrative(c: Dict[str, Any], key: str, title: str) -> None:
            if not isinstance(c.get(key), str) or len(c[key].strip()) < 80:
                c[key] = (
                    f"<p><strong>{title}:</strong> Dieser Abschnitt wurde vorläufig automatisch erzeugt. "
                    f"Er enthält eine narrative, verständliche Beschreibung der nächsten "
                    f"Schritte – ohne Aufzählungszeichen und ohne Zahlenkolonnen. "
                    f"Die kuratierte Fassung wird im nächsten Lauf ergänzt.</p>"
                )

        for k, t in [
            ("exec_summary_html", "Executive Summary"),
            ("business_html", "Business Case"),
            ("quick_wins_html", "Quick Wins"),
            ("risks_html", "Risikomanagement"),
            ("roadmap_html", "Roadmap"),
        ]:
            _ensure_narrative(ctx, k, t)

        # Legacy-Key
        if not ctx.get("quick_wins_html") and ctx.get("quickwins_html"):
            ctx["quick_wins_html"] = ctx["quickwins_html"]

        return template.render(**ctx)

    except Exception as e:
        log.error(f"Template-Rendering fehlgeschlagen: {e}")
        return (
            "<html><body><h1>KI-Statusbericht</h1>"
            "<p>Der Report wird generiert. Bitte versuchen Sie es in wenigen Minuten erneut.</p>"
            "<p>Bei anhaltenden Problemen kontaktieren Sie: kontakt@ki-sicherheit.jetzt</p>"
            "</body></html>"
        )


__all__ = ["analyze_briefing", "analyze_briefing_enhanced"]
