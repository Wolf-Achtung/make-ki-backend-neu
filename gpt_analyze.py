# gpt_analyze.py — Direct Renderer + Enhanced Innenleben (+ Live Updates + Benchmarks)
# Stand: 2025-09-30 (Gold-Standard+)

from __future__ import annotations
import csv
import glob
import io
import os
import re
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from jinja2 import Environment, FileSystemLoader, select_autoescape

from websearch_utils import collect_recent_items  # Live-Sektionen (Tavily etc.)

# Optional YAML und HTML: Für branchenspezifische Daten und sichere HTML-Ausgabe
try:
    import yaml  # type: ignore
except Exception:
    yaml = None  # Wird geprüft, bevor YAML-Dateien geladen werden

import html  # Für Escape in Tool-/Förderlisten

# Versuche, die intelligente Förderprogramm-Matching-Funktion zu importieren
try:
    from ENHANCED_FUNDING_DATABASE import match_funding_programs_smart  # type: ignore
except Exception:
    match_funding_programs_smart = None

BASE_DIR = os.path.abspath(os.getenv("APP_BASE", os.getcwd()))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
PROMPTS_DIR = os.getenv("PROMPTS_DIR", os.path.join(BASE_DIR, "prompts"))
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
BRANCHEN_DIR = os.getenv("BRANCHEN_DIR", os.path.join(BASE_DIR, "branchenkontext"))

TEMPLATE_DE = os.getenv("TEMPLATE_DE", "pdf_template.html")
TEMPLATE_EN = os.getenv("TEMPLATE_EN", "pdf_template_en.html")
PDF_TEMPLATE_NAME = os.getenv("PDF_TEMPLATE_NAME")  # optional override
FEEDBACK_URL = os.getenv(
    "FEEDBACK_URL", "https://make.ki-sicherheit.jetzt/feedback/feedback.html"
)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("gpt_analyze")

# ----------------------------- OpenAI optional -----------------------------
_openai = None
try:
    from openai import OpenAI
    if os.getenv("OPENAI_API_KEY"):
        _openai = OpenAI()
        log.info("OpenAI Client initialisiert")
except Exception as e:
    log.warning(f"OpenAI nicht verfügbar: {e}")
    _openai = None


# ----------------------------- Jinja Environment ---------------------------
def make_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader([TEMPLATE_DIR, BASE_DIR]),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    def currency(v, symbol="€"):
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


# ----------------------------- Utils ---------------------------------------
def _safe_int(x, default=0) -> int:
    try:
        if isinstance(x, (int, float)):
            return int(x)
        s = re.sub(r"[^\d-]", "", str(x))
        return int(s) if s else default
    except Exception:
        return default


def _safe_float(x, default=0.0) -> float:
    try:
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).replace(",", ".")
        s = re.sub(r"[^\d\.-]", "", s)
        return float(s) if s and s not in {".", "-", ""} else default
    except Exception:
        return default


def _readiness_label(score: int, lang="de") -> str:
    s = _safe_int(score, 50)
    if lang.startswith("de"):
        return ("Anfänger", "Grundlegend", "Fortgeschritten", "Reif", "Führend")[
            0 if s < 30 else 1 if s < 50 else 2 if s < 70 else 3 if s < 85 else 4
        ]
    return ("Beginner", "Basic", "Advanced", "Mature", "Leading")[
        0 if s < 30 else 1 if s < 50 else 2 if s < 70 else 3 if s < 85 else 4
    ]


def _debug_list_prompts():
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


# ----------------------------- KPIs ----------------------------------------
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
        digital * 3.0
        + (auto / 10) * 2.5
        + (papier / 10) * 2.0
        + (risk * 2) * 2.0
        + (kw / 10) * 2.0
        + 15
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

    roi_months = max(4, min(18, int((budget / annual_saving) * 10))) if annual_saving > 0 else 12

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
    if k["kpi_roi_months"] < 4:
        k["kpi_roi_months"] = 4
    return k


# ----------------------------- Labels / Vars -------------------------------
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


# ----------------------------- Branchenkontext -----------------------------
def _load_branchen_context(branche: str, lang: str) -> Optional[str]:
    """
    Lädt optionalen Kurztext aus ./branchenkontext/<branche>_{de|en}.md und gibt HTML (<p>…</p>) zurück.
    """
    if not os.path.isdir(BRANCHEN_DIR):
        return None
    stem = re.sub(r"[^a-z0-9]+", "_", str(branche or "").lower())
    cand = [
        os.path.join(BRANCHEN_DIR, f"{stem}_{'de' if lang.startswith('de') else 'en'}.md"),
        os.path.join(BRANCHEN_DIR, f"{stem}.md"),
    ]
    for path in cand:
        if os.path.exists(path):
            try:
                txt = io.open(path, "r", encoding="utf-8").read().strip()
                if txt:
                    txt = re.sub(r"\r\n|\r|\n", " ", txt)
                    return f"<p>{txt}</p>"
            except Exception:
                pass
    return None

# Neu: Laden von branchenspezifischen YAML-Definitionen
def _load_branch_yaml(branch: str) -> Optional[Dict[str, Any]]:
    """
    Lädt Daten aus branchenkontext/<branch>.yaml oder <branch>.de.yaml.
    Gibt ein Dictionary mit den Feldern ``tools_list`` und ``foerderprogramme_list`` zurück.
    Wenn keine Datei existiert oder PyYAML nicht verfügbar ist, wird ``None`` zurückgegeben.
    """
    if not yaml or not BRANCHEN_DIR:
        return None
    if not os.path.isdir(BRANCHEN_DIR):
        return None
    slug = re.sub(r"[^a-z0-9]+", "_", (branch or "").lower())
    candidates = [
        os.path.join(BRANCHEN_DIR, f"{slug}.yaml"),
        os.path.join(BRANCHEN_DIR, f"{slug}.de.yaml"),
        os.path.join(BRANCHEN_DIR, f"{slug}.en.yaml"),
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if isinstance(data, dict):
                        return data  # type: ignore
            except Exception:
                continue
    return None

# Neu: Filtert Tools aus tools.csv basierend auf Branche, Unternehmensgröße und Schlagworten
def _filter_csv_tools(
    branch: str,
    company_size: str,
    main_service: str,
    use_cases: List[str],
    max_results: int = 6,
) -> List[Dict[str, str]]:
    """
    Liest die Datei ``data/tools.csv`` ein und filtert Tools anhand des Bereichs (industry),
    der Unternehmensgröße und optionaler Keywords aus ``main_service`` oder den angegebenen KI-Use-Cases.
    Gibt eine Liste von Tool-Dictionaries mit den Feldern ``name``, ``description``, ``cost``, ``link`` zurück.
    """
    results: List[Dict[str, str]] = []
    csv_path = os.path.join(DATA_DIR, "tools.csv")
    if not os.path.exists(csv_path):
        return results
    branch_key = (branch or "").lower().split("&")[0].strip()
    size_key = str(company_size).lower()
    keywords: List[str] = []
    if main_service:
        keywords += re.findall(r"[a-zA-Z0-9äöüÄÖÜß]+", main_service.lower())
    for uc in use_cases:
        keywords += re.findall(r"[a-zA-Z0-9äöüÄÖÜß]+", str(uc).lower())
    seen: set[str] = set()
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                industry = (row.get("industry", "").lower()).strip()
                if branch_key and industry and branch_key not in industry and industry not in branch_key:
                    continue
                size_field = (row.get("company_size", "").lower()).strip()
                if size_field and size_key not in size_field and size_field not in size_key:
                    continue
                text_fields = " ".join([
                    row.get("use_case", ""),
                    row.get("description", ""),
                    row.get("one_liner", ""),
                ]).lower()
                if keywords:
                    if not any(k in text_fields for k in keywords):
                        continue
                name = row.get("name") or row.get("tool") or ""
                name = name.strip()
                if not name or name in seen:
                    continue
                seen.add(name)
                results.append({
                    "name": name,
                    "description": row.get("one_liner", row.get("description", "")).strip(),
                    "cost": row.get("cost_tier", row.get("cost", "")).strip(),
                    "link": row.get("url", "").strip(),
                })
                if len(results) >= max_results:
                    break
    except Exception as e:
        log.warning(f"tools.csv parse failed: {e}")
    return results


# ----------------------------- Benchmarks (CSV in ./data) ------------------
def _find_benchmark_csv(branche: str) -> Optional[str]:
    """
    Sucht data/benchmark_<branche>.csv, fallback: data/benchmark_default.csv
    """
    if not os.path.isdir(DATA_DIR):
        return None
    stem = re.sub(r"[^a-z0-9]+", "_", (branche or "").lower())
    cand = [
        os.path.join(DATA_DIR, f"benchmark_{stem}.csv"),
        os.path.join(DATA_DIR, "benchmark_default.csv"),
    ]
    for p in cand:
        if os.path.exists(p):
            return p
    return None


def _parse_csv(path: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with io.open(path, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append({k.strip(): (v or "").strip() for k, v in row.items()})
    return rows


def _canonical_kpi(name: str) -> str:
    n = (name or "").strip().lower()
    mapping = {
        "digitalisierung": "digitalization",
        "digitalization": "digitalization",
        "automatisierung": "automation",
        "automation": "automation",
        "papierlos": "paperless",
        "paperless": "paperless",
        "ki-know-how": "ai_knowledge",
        "ai know-how": "ai_knowledge",
        "ai knowledge": "ai_knowledge",
        "effizienz": "efficiency",
        "efficiency": "efficiency",
        "compliance": "compliance",
        "innovation": "innovation",
    }
    return mapping.get(n, n)


def _our_value_for_kpi(canon: str, ctx: Dict[str, Any]) -> Optional[str]:
    if canon == "digitalization":
        return f"{ctx.get('digitalisierungsgrad', 0) * 10}%"
    if canon == "automation":
        return f"{ctx.get('automatisierungsgrad_percent', 0)}%"
    if canon == "paperless":
        rng = str(ctx.get("prozesse_papierlos", "51-80"))
        m = re.findall(r"\d+", rng)
        if m:
            nums = list(map(int, m))
            mid = int((nums[0] + (nums[1] if len(nums) > 1 else nums[0])) / 2)
            return f"{mid}%"
        return None
    if canon == "ai_knowledge":
        return str(ctx.get("ki_knowhow_label") or ctx.get("ki_knowhow") or "")
    if canon == "efficiency":
        return f"{ctx.get('kpi_efficiency', 0)}%"
    if canon == "compliance":
        return f"{ctx.get('kpi_compliance', 0)}%"
    if canon == "innovation":
        return f"{ctx.get('kpi_innovation', 0)}%"
    return None


def _pp_delta(a: str, b: str) -> Optional[int]:
    try:
        def num(s: str) -> Optional[int]:
            if not s:
                return None
            m = re.findall(r"-?\d+", str(s))
            return int(m[0]) if m else None

        av = num(a)
        bv = num(b)
        if av is None or bv is None:
            return None
        return av - bv
    except Exception:
        return None


def build_benchmarks_table(ctx: Dict[str, Any], lang: str) -> Optional[str]:
    path = _find_benchmark_csv(ctx.get("branche"))
    if not path:
        return None
    try:
        rows = _parse_csv(path)
    except Exception as e:
        log.warning("benchmark parse failed: %s", e)
        return None

    cols = {k.lower(): k for k in (rows[0].keys() if rows else [])}
    kpi_col = cols.get("kpi") or cols.get("metric") or list(cols.values())[0]
    bench_col = (
        cols.get("benchmark")
        or cols.get("branchenwert")
        or cols.get("branch")
        or list(cols.values())[-1]
    )

    if lang.startswith("de"):
        th = "<thead><tr><th>KPI</th><th>Unser Wert</th><th>Benchmark</th><th>Δ (pp)</th><th>Hinweis</th></tr></thead>"
    else:
        th = "<thead><tr><th>KPI</th><th>Our value</th><th>Benchmark</th><th>Δ (pp)</th><th>Note</th></tr></thead>"

    tr_html = []
    for r in rows:
        kpi = r.get(kpi_col, "").strip()
        canon = _canonical_kpi(kpi)
        our = _our_value_for_kpi(canon, ctx) or "-"
        bench = (r.get(bench_col, "") or "-").strip()
        delta = _pp_delta(our, bench)
        note = r.get("note") or r.get("hinweis") or ""
        d_str = f"{delta:+d}" if delta is not None else "-"
        tr_html.append(
            f"<tr><td>{kpi}</td><td>{our}</td><td>{bench}</td><td>{d_str}</td><td>{note}</td></tr>"
        )

    table = f"<table>{th}<tbody>{''.join(tr_html)}</tbody></table>"
    box_title = "Benchmark‑Vergleich (Branche)" if lang.startswith("de") else "Benchmark comparison (industry)"
    return f'<div class="info-box"><div class="info-box-title">{box_title}</div>{table}</div>'


# ----------------------------- Template-Variablen --------------------------
def get_template_variables(form_data: Dict[str, Any], lang: str = "de") -> Dict[str, Any]:
    k = validate_kpis(calculate_optimistic_kpis(calculate_kpis_from_answers(form_data)))
    size = str(form_data.get("unternehmensgroesse", "2-10"))
    vars = {
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
            "version": "3.3",
        },
        "lang": lang,
        "is_german": lang.startswith("de"),
        "branche": form_data.get("branche", "beratung"),
        "bundesland": form_data.get("bundesland", "BE"),
        "hauptleistung": form_data.get("hauptleistung", ""),
        "unternehmensgroesse": size,
        "company_size_label": get_company_size_label(size, lang),
        "score_percent": k["readiness_score"],
        "readiness_level": _readiness_level(k["readiness_score"], lang),
        "kpi_efficiency": k["kpi_efficiency"],
        "kpi_cost_saving": k["kpi_cost_saving"],
        "kpi_roi_months": k["kpi_roi_months"],
        "kpi_compliance": k["kpi_compliance"],
        "kpi_innovation": k["kpi_innovation"],
        "budget": form_data.get("budget", "2000-10000"),
        "budget_amount": k["roi_investment"],
        "roi_investment": k["roi_investment"],
        "roi_annual_saving": k["roi_annual_saving"],
        "roi_three_year": k["roi_three_year"],
        "ki_usecases": form_data.get("ki_usecases", []),
        "ki_hemmnisse": form_data.get("ki_hemmnisse", []),
        "ki_knowhow": form_data.get("ki_knowhow", "grundkenntnisse"),
        "ki_knowhow_label": get_knowledge_label(
            form_data.get("ki_knowhow", "grundkenntnisse"), lang
        ),
        "automatisierungsgrad": form_data.get("automatisierungsgrad", "mittel"),
        "automatisierungsgrad_percent": k["automatisierungsgrad"],
        "prozesse_papierlos": form_data.get("prozesse_papierlos", "51-80"),
        "quick_win_primary": get_primary_quick_win(form_data, lang),
        "funding_programs": form_data.get("funding_programs", []),
        "tools": form_data.get("tools", []),
        "foerderprogramme_table": form_data.get("funding_programs", []),
        "tools_table": form_data.get("tools", []),
        "feedback_link": FEEDBACK_URL,
    }
    if vars["kpi_efficiency"] == 0:
        vars["kpi_efficiency"] = 1
    return vars


# ----------------------------- Prompt-Engine -------------------------------
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
        text = re.sub(r"\{%.*?%\}", "", text, flags=re.S)

        def repl(m):
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
                        log.info("Prompt resolved: %s -> %s (md-plain)", name, fn)
                        return html
                else:
                    tpl = self.env.get_template(fn)
                    log.info("Prompt resolved: %s -> %s (jinja)", name, fn)
                    return tpl.render(**ctx)
            except Exception as e:
                last_err = e
                continue
        raise FileNotFoundError(f"Prompt nicht renderbar: {name} ({last_err})")


# ----------------------------- GPT optional --------------------------------
def _gpt(prompt: str, section: str, lang="de") -> Optional[str]:
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


# ----------------------------- Fallback-Generatoren ------------------------
def _p(s: str) -> str:
    return f"<p>{s}</p>"


def fallback_executive_summary(v: Dict[str, Any], lang="de") -> str:
    if lang.startswith("de"):
        return (
            _p(
                f"<strong>Ausgangslage:</strong> Mit {v.get('score_percent', 50)}% KI‑Reifegrad besteht eine solide Basis."
            )
            + _p(
                f"<strong>Wirtschaftlichkeit:</strong> Investition {v.get('roi_investment', 10000)} €, "
                f"Break‑even in {v.get('kpi_roi_months', 12)} Monaten, jährliche Einsparungen "
                f"{v.get('roi_annual_saving', 20000)} €."
            )
        )
    return _p(
        "Solid starting point. Conservative business case with break‑even in the first year and tangible savings."
    )


def fallback_business(v: Dict[str, Any], lang="de") -> str:
    if lang.startswith("de"):
        return _p(
            f"Konservativer Business Case: Investition {v.get('roi_investment', 10000)} €, "
            f"jährlicher Nutzen {v.get('roi_annual_saving', 20000)} €, "
            f"3‑Jahres‑Nettonutzen {v.get('roi_three_year', 50000)} €."
        )
    return _p("Conservative business case with positive year‑one cash‑flow.")


def fallback_generic(section: str, lang="de") -> str:
    return (
        _p("Dieser Abschnitt wurde generiert und steht bereit.")
        if lang.startswith("de")
        else _p("This section has been generated and is ready.")
    )


def generate_quick_wins(answers: Dict[str, Any], kpis: Dict[str, Any], lang: str = "de") -> str:
    primary = get_primary_quick_win(answers, lang)
    if lang.startswith("de"):
        return _p(
            f"Sofort starten mit <strong>{primary}</strong>; sichtbare Ergebnisse in 2–4 Wochen."
        )
    return _p("Start with your primary quick win; visible results in 2–4 weeks.")


def generate_risk_analysis(answers: Dict[str, Any], kpis: Dict[str, Any], lang: str = "de") -> str:
    if lang.startswith("de"):
        return _p(
            "Risikomanagement: Zuständigkeiten klären (DPO/DSFA), schrittweise Einführung, Shadow‑IT vermeiden."
        )
    return _p("Risk management: clarify GDPR/DPIA, phased rollout, avoid shadow IT.")


def generate_roadmap(answers: Dict[str, Any], kpis: Dict[str, Any], lang: str = "de") -> str:
    b = kpis.get("roi_investment", 10000)
    m = kpis.get("kpi_roi_months", 12)
    if lang.startswith("de"):
        return _p(
            f"Roadmap: 0–30 Tage Quick‑Win (≈ {int(b * 0.2)} €); 31–90 Tage Scale‑up; "
            f"91–180 Tage Optimierung; Break‑even nach ~{m} Monaten."
        )
    return _p("Roadmap: quick win, scale up, optimize; break‑even in the first year.")


# ----------------------------- Tool/Funding-Kataloge (statisch) -----------
TOOL_DATABASE = {
    "texterstellung": [
        {
            "name": "DeepL Write",
            "desc": "DSGVO‑freundliches Schreibtool",
            "use_case": "E‑Mails, Berichte",
            "cost": "Free/Pro",
            "fit_score": 95,
        },
        {
            "name": "Jasper AI",
            "desc": "Content‑Automation",
            "use_case": "Blog/Social",
            "cost": "ab 39€",
            "fit_score": 80,
        },
    ],
    "prozessautomatisierung": [
        {"name": "n8n", "desc": "Open‑Source Workflows", "use_case": "APIs/Automation", "cost": "Free", "fit_score": 92},
        {"name": "Make", "desc": "Low‑Code Automatisierung", "use_case": "Workflows", "cost": "ab 9€", "fit_score": 88},
    ],
    "datenanalyse": [
        {"name": "Metabase", "desc": "Open‑Source BI", "use_case": "Dashboards", "cost": "Free/Cloud", "fit_score": 85}
    ],
    "kundensupport": [
        {"name": "Typebot", "desc": "Open‑Source Chatbot", "use_case": "FAQ/Leads", "cost": "Free", "fit_score": 90}
    ],
}


def match_tools_to_company(answers: Dict[str, Any], lang: str = "de") -> str:
    """
    Erstellt eine auf das Unternehmen zugeschnittene Liste von Tool‑Empfehlungen.

    Diese Funktion kombiniert mehrere Datenquellen:
    - Branchenkontexte (YAML): Enthalten manuell kuratierte Tools pro Branche.
    - CSV‑Datenbank (data/tools.csv): Enthält eine breite Palette an Tools mit
      Branchen‑, Größen‑ und Use‑Case‑Tags.
    - Fallback‑Datenbank (TOOL_DATABASE): Wird nur genutzt, wenn weder YAML noch
      CSV passende Ergebnisse liefern.

    Dabei werden Branche, Unternehmensgröße, Hauptdienstleistung sowie die
    ausgewählten KI‑Use‑Cases zur Filterung verwendet. Duplikate werden
    entfernt. Das Ergebnis wird als HTML in einem Absatz ausgegeben.
    """
    # Sammle Eingaben
    branch = str(answers.get("branche", "")).strip()
    company_size = str(answers.get("unternehmensgroesse", "")).strip()
    main_service = str(answers.get("hauptleistung", "")).strip()
    use_cases = answers.get("ki_usecases") or []
    if isinstance(use_cases, str):
        use_cases = [use_cases]

    suggestions: List[Dict[str, str]] = []
    seen_names: set[str] = set()

    # 1) Branchen-YAML laden
    branch_data = _load_branch_yaml(branch)
    if branch_data and isinstance(branch_data, dict):
        for t in branch_data.get("tools_list", []):
            name = str(t.get("name", "")).strip()
            if not name or name in seen_names:
                continue
            desc = str(t.get("desc", t.get("description", ""))).strip()
            cost = str(t.get("cost", "")).strip()
            url = str(t.get("link", "")).strip()
            dpa = str(t.get("datenschutz", "")).strip()
            suggestions.append({
                "name": name,
                "description": desc,
                "cost": cost,
                "link": url,
                "dpa": dpa,
            })
            seen_names.add(name)
            if len(suggestions) >= 6:
                break

    # 2) CSV‑Tools filtern, wenn noch Platz ist
    if len(suggestions) < 6:
        csv_tools = _filter_csv_tools(branch, company_size, main_service, use_cases, max_results=6)
        for t in csv_tools:
            name = t.get("name", "").strip()
            if not name or name in seen_names:
                continue
            suggestions.append({
                "name": name,
                "description": t.get("description", "").strip(),
                "cost": t.get("cost", "").strip(),
                "link": t.get("link", "").strip(),
                "dpa": "",
            })
            seen_names.add(name)
            if len(suggestions) >= 6:
                break

    # 3) Fallback: Statische Datenbank
    if not suggestions:
        ucs = use_cases or ["prozessautomatisierung"]
        for uc in ucs:
            key = re.sub(r"[\s\-]", "", str(uc).lower())
            for dbk, tools in TOOL_DATABASE.items():
                if dbk in key or key in dbk:
                    best = sorted(tools, key=lambda t: -t.get("fit_score", 0))
                    for t in best:
                        name = t.get("name")
                        if name and name not in seen_names:
                            suggestions.append({
                                "name": t["name"],
                                "description": t.get("desc", ""),
                                "cost": t.get("cost", ""),
                                "link": t.get("use_case", ""),  # Fallback: Use-Case im Link-Feld
                                "dpa": "",
                            })
                            seen_names.add(name)
                            break
                    break
            if len(suggestions) >= 6:
                break

    # Formatierung
    if not suggestions:
        return _p("Individuelle Tool‑Empfehlungen folgen nach Detailklärung." if lang.startswith("de") else "Individual tool recommendations will follow.")

    lines = []
    for t in suggestions[:6]:
        name = html.escape(t["name"])
        desc = html.escape(t.get("description", ""))
        cost = html.escape(t.get("cost", ""))
        link = t.get("link", "").strip()
        dpa = t.get("dpa", "").strip()
        if lang.startswith("de"):
            parts = [name]
            if desc:
                parts.append(f"– {desc}")
            if cost:
                parts.append(f"({cost})")
            if dpa:
                parts.append(f"AVV: {dpa}")
            if link:
                parts.append(f"{link}")
            lines.append(" ".join(parts))
        else:
            parts = [name]
            if desc:
                parts.append(f"– {desc}")
            if cost:
                parts.append(f"({cost})")
            if dpa:
                parts.append(f"DPA: {dpa}")
            if link:
                parts.append(f"{link}")
            lines.append(" ".join(parts))
    return _p("; ".join(lines))


# Statische Fallback-Datenbank für Förderprogramme (wird selten genutzt)
FUNDING_PROGRAMS = {
    "bundesweit": [
        {"name": "go‑digital", "amount": "bis 16.500€ (50%)", "deadline": "laufend", "fit": 90},
        {"name": "Digital Jetzt", "amount": "bis 50.000€ (40%)", "deadline": "bis 31.12.2025", "fit": 85},
        {"name": "KfW‑Digitalisierungskredit", "amount": "Kredit, günstiger Zins", "deadline": "laufend", "fit": 80},
    ],
    "berlin": [
        {"name": "Digitalprämie Berlin", "amount": "bis 17.000€", "deadline": "31.12.2025", "fit": 88},
        {"name": "Mittelstand 4.0", "amount": "Beratung", "deadline": "laufend", "fit": 100},
    ],
}

def match_funding_programs(answers: Dict[str, Any], lang: str = "de") -> str:
    """
    Liefert eine Liste passender Förderprogramme als HTML. Die Auswahl basiert auf
    Bundesland, Unternehmensgröße, Branche und Hauptleistung. Es wird zunächst
    versucht, die intelligente Matching-Funktion aus ENHANCED_FUNDING_DATABASE
    zu verwenden. Schlägt dies fehl oder stehen keine Programme zur Verfügung,
    werden branchenspezifische YAML-Definitionen genutzt. Als letzter Fallback
    greift eine statische Liste.
    """
    # Versuche intelligente Förderprogramme
    progs: List[Dict[str, Any]] = []
    try:
        if match_funding_programs_smart:
            progs = match_funding_programs_smart(answers)  # type: ignore
    except Exception as e:
        log.warning(f"smart funding match failed: {e}")
        progs = []

    # Falls vorhanden: nutze nur die Top 8
    if progs:
        # Optional: Filtere anhand von Keywords aus Hauptleistung/Branche
        main_service = str(answers.get("hauptleistung", "")).lower()
        branche = str(answers.get("branche", "")).lower()
        keywords: List[str] = []
        if main_service:
            keywords += re.findall(r"[a-zA-Z0-9äöüÄÖÜß]+", main_service)
        if branche:
            keywords += re.findall(r"[a-zA-Z0-9äöüÄÖÜß]+", branche)
        filtered: List[Dict[str, Any]] = []
        if keywords:
            for p in progs:
                text = (p.get("use_case", "") + " " + p.get("name", "")).lower()
                if any(k in text for k in keywords):
                    filtered.append(p)
        # Wenn zu wenige Treffer, nimm dennoch die besten
        if not filtered:
            filtered = progs
        progs = filtered[:6]
        # Formatieren
        lines: List[str] = []
        for p in progs:
            name = html.escape(p.get("name", ""))
            amount = html.escape(p.get("amount", ""))
            deadline = html.escape(p.get("deadline", ""))
            url = p.get("url", "")
            if lang.startswith("de"):
                parts = [name]
                if amount:
                    parts.append(f"– {amount}")
                if deadline:
                    parts.append(f"(Frist: {deadline})")
                if url:
                    parts.append(url)
                lines.append(" ".join(parts))
            else:
                parts = [name]
                if amount:
                    parts.append(f"– {amount}")
                if deadline:
                    parts.append(f"(Deadline: {deadline})")
                if url:
                    parts.append(url)
                lines.append(" ".join(parts))
        return _p("; ".join(lines))

    # Zweiter Fallback: Branchen-YAML
    branch = str(answers.get("branche", "")).strip()
    branch_data = _load_branch_yaml(branch)
    if branch_data and isinstance(branch_data, dict):
        fp_list = branch_data.get("foerderprogramme_list", [])
        formatted: List[str] = []
        for p in fp_list:
            name = html.escape(str(p.get("name", "")))
            amount = html.escape(str(p.get("amount", "")))
            deadline = html.escape(str(p.get("deadline", "")))
            link = p.get("link", "")
            if lang.startswith("de"):
                parts = [name]
                if amount:
                    parts.append(f"– {amount}")
                if deadline:
                    parts.append(f"(Frist: {deadline})")
                if link:
                    parts.append(link)
                formatted.append(" ".join(parts))
            else:
                parts = [name]
                if amount:
                    parts.append(f"– {amount}")
                if deadline:
                    parts.append(f"(Deadline: {deadline})")
                if link:
                    parts.append(link)
                formatted.append(" ".join(parts))
        if formatted:
            return _p("; ".join(formatted[:6]))

    # Letzter Fallback: Statische Datenbank
    state = str(answers.get("bundesland", "BE")).upper()
    region_map = {"BE": "berlin"}
    region = region_map.get(state)
    programs = list(FUNDING_PROGRAMS.get("bundesweit", []))
    if region and region in FUNDING_PROGRAMS:
        programs += FUNDING_PROGRAMS[region]
    programs = sorted(programs, key=lambda p: -p.get("fit", 0))[:6]
    if not programs:
        return _p("Aktuell keine passenden Programme." if lang.startswith("de") else "No suitable programs found.")
    rows = "; ".join([f"{p['name']} ({p['amount']})" for p in programs])
    return _p(("Förderoptionen: " + rows) if lang.startswith("de") else ("Funding options: " + rows))


# ----------------------------- Sektionen-Renderer --------------------------
def _render_section(name: str, ctx: Dict[str, Any], lang="de") -> str:
    prompt = None
    try:
        prompt = PromptLoader().render(name, ctx, lang)
    except Exception as e:
        log.warning(f"Prompt-Rendering fehlgeschlagen [{name}]: {e}")
    if prompt:
        html = _gpt(prompt, name, lang)
        if html and len(html.strip()) > 80:
            return html
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


# ----------------------------- Narrative Sanitizer -------------------------
def _sanitize_html_block(html: str) -> str:
    if not isinstance(html, str):
        return ""
    # Entferne Code-Fences wie ```html ... ``` oder ```
    s = re.sub(r"```(?:html|md|markdown)?\s*|```", "", html, flags=re.I)
    # Listen in narrative Absätze umwandeln
    items = re.findall(r"<li[^>]*>(.*?)</li>", s, flags=re.I | re.S)
    if items:
        cleaned: List[str] = []
        for it in items:
            txt = re.sub(r"<[^>]+>", "", it)
            txt = re.sub(r"^\s*(?:\d+[\.\)]|[-\*•])\s*", "", txt)
            if txt.strip():
                cleaned.append(txt.strip())
        if cleaned:
            s = re.sub(r"</?ul[^>]*>|</?ol[^>]*>|<li[^>]*>.*?</li>", "", s, flags=re.I | re.S)
            s += "".join([f"<p>{c}</p>" for c in cleaned])
    s = re.sub(r"</?(ul|ol)[^>]*>", "", s, flags=re.I)
    # Zahlen am Absatzanfang UND nach <br> oder Punkt entfernen
    s = re.sub(r"(<p[^>]*>)\s*\d+[\.\)]\s*", r"\1", s)
    s = re.sub(r"(<br\s*/?>|\.)\s*\d+[\.\)]\s+", r"\1 ", s)
    # Fallback: reinen Text in <p> einschließen
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
            ctx[k] = pct.sub(lambda m: f"{min(int(m.group(1)), 100)}%", v)
    return ctx


# ----------------------------- Live Updates (Tavily) -----------------------
def inject_live_updates(ctx: Dict[str, Any]) -> Dict[str, Any]:
    if not _get_bool("ALLOW_TAVILY", True) or not os.getenv("TAVILY_API_KEY"):
        return ctx
    try:
        adds = collect_recent_items(ctx, lang=ctx.get("lang", "de"))
        # Sichtbarkeits-Logging (siehe Railway-Logs)
        log.info("Live add-ins: %s", [k for k, v in adds.items() if isinstance(v, str) and len(v.strip()) > 0])
        ctx.update(adds)
        ctx["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    except Exception as e:
        log.warning("inject_live_updates failed: %s", e)
    return ctx


# ----------------------------- Innenleben-API -------------------------------
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

    # Optional: Branchenkontext unterhalb des Readiness‑Profils
    br_ctx = _load_branchen_context(ctx.get("branche"), lang)
    if br_ctx:
        ctx["persona_html"] = (ctx.get("persona_html") or "") + br_ctx

    # Kompakte Benchmark‑Tabelle
    bm_html = build_benchmarks_table(ctx, lang)
    if bm_html:
        ctx["benchmarks_compact_html"] = bm_html

    # Fallbacks auffüllen
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

    ctx = inject_live_updates(ctx)
    return ctx


# ----------------------------- Außenhaut: Renderer -------------------------
def analyze_briefing(form_data: Dict[str, Any], lang: str = "de") -> str:
    log.info("gpt_analyze loaded (direct): %s", os.path.join(BASE_DIR, "gpt_analyze.py"))
    _debug_list_prompts()

    env = make_env()
    try:
        chosen = PDF_TEMPLATE_NAME or (TEMPLATE_DE if str(lang).lower().startswith("de") else TEMPLATE_EN)

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

        # Guards: zentrale Kapitel nie leer
        def _ensure_narrative(c: Dict[str, Any], key: str, title: str) -> None:
            if not isinstance(c.get(key), str) or len(c[key].strip()) < 80:
                c[key] = (
                    f"<p><strong>{title}:</strong> Dieser Abschnitt wurde vorläufig automatisch erzeugt. "
                    f"Er enthält eine narrative, verständliche Beschreibung der nächsten Schritte – ohne Aufzählungszeichen "
                    f"und ohne Zahlenkolonnen. Die kuratierte Fassung wird im nächsten Lauf ergänzt.</p>"
                )

        for k, t in [
            ("exec_summary_html", "Executive Summary"),
            ("business_html", "Business Case"),
            ("quick_wins_html", "Quick Wins"),
            ("risks_html", "Risikomanagement"),
            ("roadmap_html", "Roadmap"),
        ]:
            _ensure_narrative(ctx, k, t)

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
