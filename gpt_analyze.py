# gpt_analyze.py — Gold-Standard (Teil 1/4)
import os
import re
import json
import base64
import zipfile
import mimetypes
from datetime import datetime
from typing import Dict, Any, Optional, List
# Optional post-processing: clamp lists, add missing fields (quick wins, roadmap, trade-offs).
# Attempt to import the helper.  If unavailable, default to None so that
# report generation still works without post-processing.
try:
    from postprocess_report import postprocess_report_dict  # type: ignore[attr-defined]
except Exception:
    postprocess_report_dict = None

from jinja2 import Environment, FileSystemLoader, select_autoescape
from openai import OpenAI
# Absolute path helpers for templates and assets
from pathlib import Path

# Base directory of this module
BASE_DIR = Path(__file__).resolve().parent
# Templates directory relative to this module
TEMPLATES_DIR = BASE_DIR / "templates"

client = OpenAI()

# VERSION_MARKER: v-test-2025-09-14

# ---------- optionale Domain-Bausteine ----------
try:
    from gamechanger_blocks import build_gamechanger_blocks
    from gamechanger_features import GAMECHANGER_FEATURES
    from innovation_intro import INNOVATION_INTRO
except Exception:
    build_gamechanger_blocks = lambda data, feats: []
    GAMECHANGER_FEATURES = {}
    INNOVATION_INTRO = {}

try:
    from websearch_utils import serpapi_search
except Exception:
    serpapi_search = lambda query, num_results=5: []

# ---------- ZIP-Autounpack (Prompts/Kontexte/Daten) ----------
def ensure_unzipped(zip_name: str, dest_dir: str):
    try:
        if os.path.exists(zip_name) and not os.path.exists(dest_dir):
            os.makedirs(dest_dir, exist_ok=True)
            with zipfile.ZipFile(zip_name, "r") as zf:
                zf.extractall(dest_dir)
    except Exception:
        pass

ensure_unzipped("prompts.zip", "prompts_unzip")
ensure_unzipped("branchenkontext.zip", "branchenkontext")
ensure_unzipped("data.zip", "data")
# Automatically unpack additional data archives such as aus-Data.zip.  This
# allows the report generator to find updated CSVs or Markdown tables
# packaged externally.  If aus-Data.zip is present it will be extracted
# into the ``data`` directory the first time this module is imported.
ensure_unzipped("aus-Data.zip", "data")

# ---------- kleine Helfer ----------
def _as_int(x):
    try:
        return int(str(x).strip())
    except Exception:
        return None

def _norm_lang(lang: Optional[str]) -> str:
    l = (lang or "de").lower().strip()
    return "de" if l.startswith("de") else "en"

def fix_encoding(text: str) -> str:
    """
    Normalize a text snippet by replacing common problematic unicode characters
    with ASCII equivalents.  This helper is used before any HTML is parsed to
    avoid character encoding issues in the generated report.  It leaves most
    content untouched but ensures dashes and quotes are consistent.
    """
    return (text or "").replace("�", "-").replace("–", "-").replace("“", '"').replace("”", '"').replace("’", "'")

# Remove hidden or zero-width unicode characters that sometimes leak from
# questionnaires or copy/paste operations.  Without sanitisation these
# characters show up as squares (e.g. "￾") in the rendered PDF.  Apply to
# every string output produced by the report generator.
def _sanitize_text(value: str) -> str:
    if not value:
        return value
    # Define a set of invisible or problematic code points to remove
    bad_chars = ["\uFFFE", "\uFEFF", "\u200B", "\u00AD"]
    text = str(value)
    for ch in bad_chars:
        text = text.replace(ch, "")
    # Replace legacy model or product names with technology-agnostic terms.
    replacements = {
        "GPT-3": "LLM-gestützte Auswertung",
        "GPT-3": "LLM-gestützte Auswertung",
        "GPT-Analyse": "LLM-gestützte Analyse",
        "GPT-Analyse": "LLM-gestützte Analyse",
        "GPT-Technologie": "LLM-gestützte Technologie",
        "GPT-Technologie": "LLM-gestützte Technologie",
        "GPT basierte": "LLM-gestützte",
        "GPT-basierte": "LLM-gestützte",
        "GPT-ausgewerteten": "LLM-gestützten",
        "GPT-ausgewerteten": "LLM-gestützten",
        "GPT-ausgewertete": "LLM-gestützte",
        "GPT-ausgewertete": "LLM-gestützte",
        "GPT-Prototyp": "KI-Prototyp",
        "GPT-Prototyp": "KI-Prototyp",
        "GPT-Prototypen": "KI-Prototypen",
        "GPT-Prototypen": "KI-Prototypen",
        "GPT-gestützt": "LLM-gestützte",
        "GPT-gestützt": "LLM-gestützte",
        "GPT-gestützte": "LLM-gestützte",
        "GPT-gestützte": "LLM-gestützte",
        "GPT-gestützten": "LLM-gestützten",
        "GPT-gestützten": "LLM-gestützten",
        "GPT-gestützte Auswertung": "LLM-gestützte Auswertung",
        "GPT-gestützte Auswertung": "LLM-gestützte Auswertung",
        "GPT-gestützte Technologie": "LLM-gestützte Technologie",
        "GPT-gestützte Technologie": "LLM-gestützte Technologie",
        "gpt-ausgewertete": "LLM-gestützte",
        "gpt-ausgewerteten": "LLM-gestützten",
        "gpt-gestützt": "LLM-gestützte"
    }
    for old, new in replacements.items():
        if old in text:
            text = text.replace(old, new)
    return text

def strip_code_fences(text: str) -> str:
    if not text:
        return text
    t = text.replace("\r", "")
    t = t.replace("```html", "```").replace("```HTML", "```")
    while "```" in t:
        t = t.replace("```", "")
    return t.replace("`", "")

def ensure_html(text: str, lang: str = "de") -> str:
    t = (text or "").strip()
    if "<" in t and ">" in t:
        return t
    lines = [ln.rstrip() for ln in t.splitlines() if ln.strip()]
    html = []
    in_ul = False
    for ln in lines:
        if re.match(r"^[-•*]\s+", ln):
            if not in_ul:
                html.append("<ul>"); in_ul = True
            html.append("<li>" + re.sub(r"^[-•*]\s+", "", ln).strip() + "</li>")
            continue
        if re.match(r"^#{1,3}\s+", ln):
            level = min(3, max(1, len(ln) - len(ln.lstrip("#"))))
            txt = ln[level:].strip()
            html.append(f"<h{level}>{txt}</h{level}>")
            continue
        if in_ul:
            html.append("</ul>"); in_ul = False
        html.append("<p>" + ln + "</p>")
    if in_ul: html.append("</ul>")
    return "\n".join(html)

def _read_md_table(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    try:
        lines = [ln.rstrip("\n") for ln in open(path, encoding="utf-8").read().splitlines() if ln.strip()]
    except Exception:
        return []
    if len(lines) < 2 or "|" not in lines[0] or "|" not in lines[1]:
        return []
    headers = [h.strip().strip("|").strip() for h in lines[0].split("|") if h.strip()]
    rows: List[dict] = []
    for ln in lines[2:]:
        if "|" not in ln:
            continue
        cells = [c.strip().strip("|").strip() for c in ln.split("|")]
        if not any(cells):
            continue
        row = {headers[i]: (cells[i] if i < len(cells) else "") for i in range(len(headers))}
        rows.append(row)
    return rows

# -----------------------------------------------------------------------------
# Fallback Vision Generator
def fallback_vision(data: dict, lang: str = "de") -> str:
    lang = _norm_lang(lang)
    if lang == "de":
        paragraphs = [
            ("<p><b>Innovative Idee:</b> KI-Serviceportal für KMU – ein digitales Ökosystem, das "
             "kleinen und mittleren Unternehmen den Zugang zu KI-gestützten Fragebögen, Tools "
             "und praxisnahen Benchmarks eröffnet. Durch intuitive Workflows und kuratierte "
             "Best-Practice-Beispiele entsteht ein Raum, in dem Innovationsimpulse wachsen können.</p>"),
            ("<p>Als erster Schritt könnten Sie einen schlanken Prototypen aufsetzen, der ein "
             "Fragebogen-Tool mit unmittelbarem Feedback und einer unkomplizierten Terminvereinbarung "
             "kombiniert. Dieses Portal dient als Drehscheibe für Ihr KI-Programm und erleichtert "
             "Ihren Kundinnen und Kunden den Einstieg.</p>"),
            ("<p>Langfristig entwickelt sich das Portal zu einem lebendigen Wissenswerk, das "
             "Erfahrungen aus unterschiedlichen Projekten zusammenführt und Ihnen hilft, neue "
             "Dienstleistungen zu entwickeln. Es geht nicht um nackte Zahlen, sondern um eine "
             "gemeinsame Lernreise, bei der Sie sich als Vorreiter im Mittelstand positionieren.</p>")
        ]
    else:
        paragraphs = [
            ("<p><b>Bold idea:</b> AI service portal for SMEs – a digital ecosystem that opens up "
             "AI-powered questionnaires, tools and practical benchmarks to small and midsized "
             "businesses. By providing intuitive workflows and curated best-practice examples, "
             "it creates a space where innovation impulses can flourish.</p>"),
            ("<p>As an initial step you might build a lean prototype combining a questionnaire "
             "tool, immediate feedback and an easy appointment system. This portal will be the hub "
             "for your AI programme, guiding your clients gently into the world of AI.</p>"),
            ("<p>Over time, the portal evolves into a living knowledge platform that brings together "
             "experience from diverse projects and helps you develop new services. The focus is not "
             "on numbers but on a shared learning journey where you position yourself as an "
             "innovator in your industry.</p>")
        ]
    return "".join(paragraphs)
# -----------------------------------------------------------------------------
# Fallback practice example loader
def _fallback_praxisbeispiel(branche: str, lang: str = "de") -> str:
    try:
        br = (branche or "").strip().lower()
        branch_map = {
            "beratung": "Beratung & Dienstleistungen",
            "dienstleistungen": "Beratung & Dienstleistungen",
            "it": "IT & Software",
            "it & software": "IT & Software",
            "marketing": "Marketing & Werbung",
            "werbung": "Marketing & Werbung",
            "bau": "Bauwesen",
            "bausektor": "Bauwesen",
            "industrie": "Industrie/Produktion",
            "produktion": "Industrie/Produktion",
            "finanzen": "Finanzen & Versicherungen",
            "versicherung": "Finanzen & Versicherungen",
            "gesundheit": "Gesundheitswesen",
            "gesundheitswesen": "Gesundheitswesen",
            "handel": "Handel & E-Commerce",
            "e-commerce": "Handel & E-Commerce",
            "bildung": "Bildung",
            "handwerk": "Handwerk",
            "sonstige": "Sonstige",
        }
        header = branch_map.get(br, None)
        md_path = Path(__file__).resolve().parent / "data" / "praxisbeispiele.md"
        if not md_path.exists():
            return ""
        content = md_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        start = None
        header_pattern = f"## {header}" if header else None
        if header_pattern:
            for idx, ln in enumerate(lines):
                if ln.strip().lower() == header_pattern.lower():
                    start = idx; break
        if start is None:
            for idx, ln in enumerate(lines):
                if ln.strip().lower() == "## sonstige":
                    start = idx; break
        if start is None:
            return ""
        section_lines: List[str] = []
        for ln in lines[start + 1:]:
            if ln.startswith("## "):
                break
            section_lines.append(ln)
        case_lines: List[str] = []; in_case = False
        for ln in section_lines:
            if ln.strip().startswith("**Case"):
                if in_case: break
                in_case = True; continue
            if in_case:
                if not ln.strip(): break
                case_lines.append(ln)
        text_parts: List[str] = []
        for ln in case_lines:
            stripped = ln.strip().lstrip("- •*").strip()
            if not stripped: continue
            lowered = stripped.lower()
            if lowered.startswith("pain point"):
                stripped = "Problem: " + stripped.split(":", 1)[-1].strip()
            elif lowered.startswith("ki-lösung") or lowered.startswith("ki-lösung"):
                stripped = "Lösung: " + stripped.split(":", 1)[-1].strip()
            elif lowered.startswith("outcome"):
                stripped = "Ergebnis: " + stripped.split(":", 1)[-1].strip()
            text_parts.append(stripped)
        description = " ".join(text_parts).replace("**","").replace("__","")
        description = _strip_lists_and_numbers(description)
        return f"<p>{description}</p>"
    except Exception:
        return ""

# gpt_analyze.py — Gold-Standard (Teil 2/4)
def is_self_employed(data: dict) -> bool:
    keys_text = ["beschaeftigungsform","beschäftigungsform","arbeitsform","rolle","role","occupation","unternehmensform","company_type"]
    txt = " ".join(str(data.get(k, "") or "") for k in keys_text).lower()
    if any(s in txt for s in ["selbst","freelanc","solo","self-employ"]):
        return True
    for k in ["mitarbeiter","mitarbeiterzahl","anzahl_mitarbeiter","employees","employee_count","team_size"]:
        n = _as_int(data.get(k))
        if n is not None and n <= 1:
            return True
    return False

def load_yaml(path: str):
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def build_context(data: dict, branche: str, lang: str = "de") -> dict:
    context_path = f"branchenkontext/{branche}.{lang}.yaml"
    if not os.path.exists(context_path):
        context_path = f"branchenkontext/default.{lang}.yaml"
    context = load_yaml(context_path) if os.path.exists(context_path) else {}
    context.update(data or {}); context["lang"] = lang

    def _get_employee_count(d: dict) -> Optional[int]:
        for key in ["mitarbeiter","mitarbeiterzahl","anzahl_mitarbeiter","employees","employee_count","team_size","anzahl_mitarbeiterinnen"]:
            v = d.get(key); n = _as_int(v)
            if n is not None: return n
        sz = (d.get("unternehmensgroesse") or d.get("company_size") or "").strip().lower()
        if sz:
            if any(s in sz for s in ["solo","einzel","self"]): return 1
            m = re.match(r"(\d+)", sz)
            if m:
                try: return int(m.group(1))
                except Exception: pass
        return None

    emp_count = _get_employee_count(context)
    self_emp = is_self_employed(context)
    category = "solo" if self_emp else None
    if category is None:
        if emp_count is None: category = "team"
        elif emp_count <= 1: category = "solo"
        elif emp_count <= 10: category = "team"
        else: category = "kmu"

    if lang == "de":
        label = "Solo-Unternehmer:in" if category=="solo" else ("Team (2–10 Mitarbeitende)" if category=="team" else "KMU (11+ Mitarbeitende)")
    else:
        label = "Solo entrepreneur" if category=="solo" else ("Small team (2–10 people)" if category=="team" else "SME (11+ people)")

    context["company_size_category"] = category
    context["company_size_label"] = label
    context["unternehmensgroesse"] = label
    context["self_employed"] = "Yes" if self_emp else "No"
    context["selbststaendig"] = "Ja" if self_emp and lang=="de" else ("Nein" if lang=="de" else context["self_employed"])
    cf = context.get("rechtsform") or context.get("company_form") or context.get("legal_form")
    context["company_form"] = cf or ""
    if lang != "de":
        _branch_translations = {
            "beratung":"consulting","bau":"construction","bildung":"education","finanzen":"finance",
            "gesundheit":"healthcare","handel":"trade","industrie":"industry","it":"IT",
            "logistik":"logistics","marketing":"marketing","medien":"media","verwaltung":"public administration"
        }
        context["branche"] = _branch_translations.get(branche.lower(), branche)
    else:
        context["branche"] = branche
    context.setdefault("copyright_year", datetime.now().year)
    context.setdefault("copyright_owner", "Wolf Hohl")
    context.setdefault("company_size", _as_int(data.get("mitarbeiterzahl") or data.get("employees") or 1) or 1)
    context["is_self_employed"] = is_self_employed(data)
    context["hauptleistung"] = context.get("hauptleistung") or context.get("main_service") or context.get("hauptprodukt") or ""
    context["projektziel"] = context.get("projektziel") or context.get("ziel") or ""
    return context

def add_innovation_features(context, branche, data):
    context["branchen_innovations_intro"] = INNOVATION_INTRO.get(branche, "")
    try:
        context["gamechanger_blocks"] = build_gamechanger_blocks(data, GAMECHANGER_FEATURES)
    except Exception:
        context["gamechanger_blocks"] = []
    return context

def add_websearch_links(context, branche, projektziel):
    year = datetime.now().year
    try:
        context["websearch_links_foerder"] = serpapi_search(
            f"aktuelle Förderprogramme {branche} {projektziel} Deutschland {year}", num_results=5
        )
        context["websearch_links_tools"] = serpapi_search(
            f"aktuelle KI-Tools {branche} Deutschland {year}", num_results=5
        )
    except Exception:
        context["websearch_links_foerder"] = []
        context["websearch_links_tools"] = []
    return context

def render_prompt(template_text: str, context: dict) -> str:
    def replace_join(m):
        key = m.group(1); sep = m.group(2)
        val = context.get(key.strip(), "")
        return sep.join(str(v) for v in val) if isinstance(val, list) else str(val)
    rendered = re.sub(r"\{\{\s*(\w+)\s*\|\s*join\(\s*['\"]([^'\"]*)['\"]\s*\)\s*\}\}", replace_join, template_text)
    def replace_simple(m):
        key = m.group(1); val = context.get(key.strip(), "")
        return ", ".join(str(v) for v in val) if isinstance(val, list) else str(val)
    return re.sub(r"\{\{\s*(\w+)\}\}", replace_simple, template_text)

def build_masterprompt(chapter: str, context: dict, lang: str = "de") -> str:
    primary_path = f"prompts/{lang}/{chapter}.md"
    if os.path.exists(primary_path):
        try:
            prompt_text = load_text(primary_path)
        except Exception:
            prompt_text = None
    else:
        prompt_text = None
    if not prompt_text:
        prompt_text = f"[NO PROMPT FOUND for {chapter}/{lang}]"
    prompt = render_prompt(prompt_text, context)
    is_de = (lang == "de")
    base_rules = (
        "Gib die Antwort ausschließlich als gültiges HTML ohne <html>-Wrapper zurück. "
        "Verwende nur <h3> und <p>. Keine Listen, keine Tabellen, keine Aufzählungen. "
        "Formuliere 2–3 zusammenhängende Absätze mit freundlicher, motivierender Sprache. "
        "Integriere Best-Practice-Beispiele als kurze Geschichten. Keine Zahlen oder Prozentwerte."
        if is_de else
        "Return VALID HTML only (no <html> wrapper). Use only <h3> and <p>. "
        "Avoid lists and tables. Write 2–3 connected paragraphs in a warm, motivating tone. "
        "Integrate best-practice examples as short stories. Do not include numbers or percentages."
    )
    style = "\n\n---\n" + base_rules
    return prompt + style

def _chat_complete(messages, model_name: Optional[str], temperature: Optional[float] = None) -> str:
    args = {"model": model_name or os.getenv("GPT_MODEL_NAME", "gpt-5"), "messages": messages}
    if temperature is None:
        temperature = float(os.getenv("GPT_TEMPERATURE", "0.3"))
    if not str(args["model"]).startswith("gpt-5"):
        args["temperature"] = temperature
    resp = client.chat.completions.create(**args)
    return resp.choices[0].message.content.strip()

def gpt_generate_section(data, branche, chapter, lang="de"):
    lang = _norm_lang(data.get("lang") or data.get("language") or data.get("sprache") or lang)
    context = build_context(data, branche, lang)
    context = add_innovation_features(context, branche, data)
    context = add_websearch_links(context, branche, context.get("projektziel", ""))
    if not context.get("checklisten"):
        md_path = "data/check_ki_readiness.md"
        if os.path.exists(md_path):
            with open(md_path, encoding="utf-8") as f: md = f.read()
            ctx_list = [f"<li>{ln[2:].strip()}</li>" for ln in md.splitlines() if ln.strip().startswith("- ")]
            context["checklisten"] = "<ul>" + "\n".join(ctx_list) + "</ul>" if ctx_list else ""
        else:
            context["checklisten"] = ""
    prompt = build_masterprompt(chapter, context, lang)
    default_model = os.getenv("GPT_MODEL_NAME", "gpt-5")
    model_name = os.getenv("EXEC_SUMMARY_MODEL", default_model) if chapter == "executive_summary" else default_model
    section_text = _chat_complete(
        messages=[
            {
                "role": "system",
                "content": ("Sie sind TÜV-zertifizierte:r KI-Manager:in, KI-Strategieberater:in sowie Datenschutz- und Fördermittel-Expert:in. "
                            "Liefern Sie präzise, umsetzbare, aktuelle und branchenrelevante Inhalte als HTML.")
                if lang == "de" else
                           ("You are a TÜV-certified AI manager and strategy consultant. "
                            "Deliver precise, actionable, up-to-date, sector-relevant content as HTML.")
            },
            {"role": "user", "content": prompt},
        ],
        model_name=model_name,
        temperature=None,
    )
    return section_text

def gpt_generate_section_html(data, branche, chapter, lang="de") -> str:
    html = gpt_generate_section(data, branche, chapter, lang=lang)
    return ensure_html(strip_code_fences(fix_encoding(html)), lang)

# gpt_analyze.py — Gold-Standard (Teil 3/4)
def build_chart_payload(data: dict, score_percent: int, lang: str = "de") -> dict:
    def as_int(v, d=0):
        try: return int(v)
        except Exception: return d
    auto_map = {"sehr_niedrig":1,"eher_niedrig":2,"mittel":3,"eher_hoch":4,"sehr_hoch":5,
                "very_low":1,"rather_low":2,"medium":3,"rather_high":4,"very_high":5}
    pap_map  = {"0-20":1,"21-50":2,"51-80":4,"81-100":5}
    know_map = {"keine":1,"grundkenntnisse":2,"mittel":3,"fortgeschritten":4,"expertenwissen":5,
                "none":1,"basic":2,"medium":3,"advanced":4,"expert":5}
    dq_map   = {"hoch":5,"mittel":3,"niedrig":1,"high":5,"medium":3,"low":1}
    roadmap_map = {"ja":5,"in_planung":3,"nein":1,"yes":5,"planning":3,"no":1}
    gov_map  = {"ja":5,"teilweise":3,"nein":1,"yes":5,"partial":3,"no":1}
    inov_map = {"sehr_offen":5,"eher_offen":4,"neutral":3,"eher_zurueckhaltend":2,"sehr_zurückhaltend":1,
                "very_open":5,"rather_open":4,"neutral":3,"rather_reluctant":2,"very_reluctant":1}

    dataset = [
        as_int(data.get("digitalisierungsgrad", 1), 1),
        auto_map.get(str(data.get("automatisierungsgrad", "")).lower(), 1),
        pap_map.get(str(data.get("prozesse_papierlos", "0-20")).lower(), 1),
        know_map.get(str(data.get("ki_knowhow", data.get("ai_knowhow", "keine"))).lower(), 1),
        as_int(data.get("risikofreude", data.get("risk_appetite", 1)), 1),
        dq_map.get(str(data.get("datenqualitaet", data.get("data_quality", ""))).lower(), 0),
        roadmap_map.get(str(data.get("ai_roadmap", "")).lower(), 0),
        gov_map.get(str(data.get("governance", "")).lower(), 0),
        inov_map.get(str(data.get("innovationskultur", data.get("innovation_culture", ""))).lower(), 0),
    ]
    labels_de = ["Digitalisierung","Automatisierung","Papierlos","KI-Know-how","Risikofreude","Datenqualität","Roadmap","Governance","Innovationskultur"]
    labels_en = ["Digitalisation","Automation","Paperless","AI know-how","Risk appetite","Data quality","AI roadmap","Governance","Innovation culture"]
    labels = labels_de if lang == "de" else labels_en

    risk_level = 1
    dq, gov, roadmap = dataset[5], dataset[7], dataset[6]
    if dq == 1 or gov == 1: risk_level = 3
    elif roadmap in {1,3}:  risk_level = 2
    return {"score": score_percent, "dimensions": {"labels": labels, "values": dataset}, "risk_level": risk_level}

def _weights_from_env() -> Dict[str, int]:
    raw = os.getenv("SCORE_WEIGHTS")
    if not raw: return {}
    try: return {k:int(v) for k,v in json.loads(raw).items()}
    except Exception: return {}

def calc_score_percent(data: dict) -> int:
    return 0

# … (unverändert) build_funding_table(...)
# … (unverändert) build_tools_table(...)

def build_dynamic_funding(data: dict, lang: str = "de", max_items: int = 5) -> str:
    import csv, os
    path = os.path.join("data", "foerdermittel.csv")
    if not os.path.exists(path):
        alt1 = os.path.join("data", "data", "foerdermittel.csv")
        alt2 = "foerdermittel.csv"
        if os.path.exists(alt1):
            path = alt1
        elif os.path.exists(alt2):
            path = alt2
        else:
            return ""
    try:
        with open(path, newline="", encoding="utf-8") as csvfile:
            programmes = list(csv.DictReader(csvfile))
            programmes = [p for p in programmes if p and any(v for v in p.values())]
    except Exception:
        return ""
    size = (data.get("unternehmensgroesse") or data.get("company_size") or "").lower()
    targets = {
        "solo": ["solo","freelancer","freiberuflich","einzel","kmu","startup","start-up","gründung","gründungs","unternehmer"],
        "team": ["kmu","team","small"],
        "kmu":  ["kmu","sme"]
    }.get(size, [])
    region = (data.get("bundesland") or data.get("state") or "").strip()
    region_lower = region.lower()
    alias_map = {
        "nrw":"nordrhein-westfalen","by":"bayern","bw":"baden-württemberg","be":"berlin","bb":"brandenburg",
        "he":"hessen","hh":"hamburg","sl":"saarland","sn":"sachsen","st":"sachsen-anhalt","sh":"schleswig-holstein",
        "th":"thüringen","mv":"mecklenburg-vorpommern","rp":"rheinland-pfalz","ni":"niedersachsen","hb":"bremen","nds":"niedersachsen",
    }
    region = alias_map.get(region_lower, region_lower)

    def matches(row: dict) -> bool:
        if not isinstance(row, dict): return False
        zg = (row.get("Zielgruppe","") or "").lower()
        reg = (row.get("Region","") or "").lower()
        t_ok = True if not targets else any(t in zg for t in targets)
        if not region: return t_ok
        return t_ok and (reg == region or region in reg or reg == "bund")

    region_matches = []
    if region:
        for p in programmes:
            reg_val = p.get("Region") if isinstance(p, dict) else None
            reg = ((reg_val or "").lower()) if isinstance(reg_val, str) else ""
            name = (p.get("Name","") or "").strip()
            if name and reg == region:
                region_matches.append(p)

    filtered = [p for p in programmes if matches(p)]
    if region:
        filtered = sorted(filtered, key=lambda p: 0 if ((p.get("Region") or "").lower())==region
                                         else (1 if ((p.get("Region") or "").lower())=="bund" else 2))

    selected: List[dict] = []; used_names = set()
    if region_matches:
        for p in region_matches:
            name = (p.get("Name","") or "").strip()
            if name and name not in used_names:
                selected.append(p); used_names.add(name)
            if len(selected) >= max_items: break

    for p in filtered:
        if len(selected) >= max_items: break
        name = (p.get("Name","") or "").strip()
        if not name or name in used_names: continue
        selected.append(p); used_names.add(name)

    if len(selected) < max_items:
        for p in programmes:
            if len(selected) >= max_items: break
            name = (p.get("Name","") or "").strip()
            if not name or name in used_names: continue
            if region:
                reg_val = p.get("Region") if isinstance(p, dict) else None
                reg = ((reg_val or "").lower()) if isinstance(reg_val, str) else ""
                if not (reg == region or reg == "bund"): continue
            selected.append(p); used_names.add(name)

    has_non_federal = any(((p.get("Region") or "").lower() != "bund") for p in selected)
    if not has_non_federal:
        for p in programmes:
            name = (p.get("Name","") or "").strip()
            reg_val = p.get("Region") if isinstance(p, dict) else None
            reg = ((reg_val or "").lower()) if isinstance(reg_val, str) else ""
            if not name or name in used_names: continue
            if reg and reg != "bund":
                selected.append(p); used_names.add(name); break

    if not selected: return ""
    try:
        now = datetime.now()
        stand = now.strftime("%m/%Y") if lang=="de" else now.strftime("%B %Y")
    except Exception:
        stand = ""
    title = "Dynamische Förderprogramme" if lang == "de" else "Dynamic funding programmes"
    note_html = ""
    if not region:
        example = None
        for p in programmes:
            reg = (p.get("Region","") or "").strip()
            if reg and reg.lower() != "bund":
                example = p; break
        if example:
            ex_name = (example.get("Name","") or "").strip()
            ex_reg = (example.get("Region","") or "").strip()
            note_html = (f"<p><em>Kein Bundesland ausgewählt – Beispiel Landesprogramm: <b>{ex_name}</b> ({ex_reg}).</em></p>"
                         if lang=="de" else
                         f"<p><em>No state selected – example regional programme: <b>{ex_name}</b> ({ex_reg}).</em></p>")
    out = [f"<h3>{title}</h3>"]
    if note_html: out.append(note_html)
    out.append("<ul>")
    for p in selected:
        name = p.get("Name",""); desc = (p.get("Beschreibung","") or "").strip()
        link = p.get("Link",""); grant = p.get("Fördersumme (€)","")
        line = f"<b>{name}</b>: {desc}"
        if grant:
            line += (" – Förderhöhe: " + grant) if lang=="de" else (" – Funding amount: " + grant)
        if link:
            line += f' – <a href="{link}" target="_blank">Link</a>'
        out.append(f"<li>{line}</li>")
    out.append("</ul>")
    if stand:
        out.append(f"<p style=\"font-size:10px;color:var(--muted);margin-top:.2rem\">{'Stand' if lang=='de' else 'Updated'}: {stand}</p>")
    return "\n".join(out)
# gpt_analyze.py — Gold-Standard (Teil 3/3)

def generate_full_report(data: dict, lang: str = "de") -> dict:
    branche = (data.get("branche") or "default").lower()
    lang = _norm_lang(lang)
    data["score_percent"] = None

    chapters = [
        "executive_summary","vision","gamechanger","quick_wins",
        "risks","tools","foerderprogramme","roadmap",
        "compliance","praxisbeispiel","recommendations",
    ]

    out: Dict[str, Any] = {}
    for chap in chapters:
        try:
            sect_html = gpt_generate_section_html(data, branche, chap, lang=lang)
            out[chap] = ensure_html(strip_code_fences(fix_encoding(sect_html)), lang)
        except Exception as e:
            out[chap] = f"<p>[Fehler in Kapitel {chap}: {e}]</p>"

    # Executive summary etc.
    for key_from, key_to in [
        ("executive_summary","exec_summary_html"),
        ("quick_wins","quick_wins_html"),
        ("risks","risks_html"),
        ("recommendations","recommendations_html"),
        ("roadmap","roadmap_html"),
    ]:
        out[key_to] = ensure_html(strip_code_fences(fix_encoding(out.get(key_from,""))), lang)

    # Vision normalisieren
    try:
        if isinstance(out.get("vision"), str):
            vtxt = out["vision"]
            for legacy in ("Innovative Idee:", "Innovative Idee", "Bold idea:", "Bold idea"):
                vtxt = vtxt.replace(legacy, "Vision")
            out["vision"] = vtxt
        out["vision_html"] = f"<div class='vision-card'>{out['vision']}</div>" if out.get("vision") else ""
    except Exception:
        out["vision_html"] = ensure_html(strip_code_fences(fix_encoding(out.get("vision",""))), lang)

    # Gamechanger
    gc_raw = out.get("gamechanger") or ""
    out["gamechanger_html"] = ensure_html(strip_code_fences(fix_encoding(gc_raw)), lang) if gc_raw else ""

    # Narrative Felder für Förder/Tools
    try:
        fp_raw = out.get("foerderprogramme") or ""
        if fp_raw:
            out["foerderprogramme_html"] = ensure_html(strip_code_fences(fix_encoding(fp_raw)), lang)
    except Exception:
        out["foerderprogramme_html"] = out.get("foerderprogramme_html","")

    try:
        tl_raw = out.get("tools") or ""
        if tl_raw:
            out["tools_html"] = ensure_html(strip_code_fences(fix_encoding(tl_raw)), lang)
    except Exception:
        out["tools_html"] = out.get("tools_html","")

    # Compliance-Fallback
    def _fallback_compliance_narr(_lang: str) -> str:
        if (_lang or "de").startswith("de"):
            return (
                "<p>Für den rechtssicheren KI-Einsatz sind DSGVO, ePrivacy, der Digital Services Act "
                "und der EU AI Act zentral. Empfohlen sind Privacy-by-Design, Datenminimierung, "
                "klare Rollen-/Rechtekonzepte, eine kompakte DSFA bei erhöhtem Risiko sowie "
                "nachvollziehbare Freigaben (Human-in-the-Loop) und Audit-Trails.</p>"
                "<p>In der Praxis heißt das: Datenflüsse dokumentieren, Auftragsverarbeiter prüfen, "
                "Modelle und Prompts versionieren, Logging & Monitoring etablieren und "
                "Betroffenenrechte effizient bedienen – für eine belastbare, auditierbare Basis.</p>"
            )
        else:
            return (
                "<p>For compliant AI, pay attention to GDPR, ePrivacy, the Digital Services Act and the EU AI Act. "
                "Apply privacy-by-design, data minimisation, role-based access, a light DPIA for higher risks, "
                "and human-in-the-loop approvals with audit trails.</p>"
                "<p>In practice: document data flows, verify processors, version models and prompts, "
                "enable logging & monitoring, and handle data-subject rights efficiently to stay auditable.</p>"
            )

    try:
        comp_plain = re.sub(r"<[^>]+>", "", out.get("compliance") or "").strip()
        if not comp_plain:
            out["compliance"] = _fallback_compliance_narr(lang)
        out["compliance_html"] = ensure_html(strip_code_fences(fix_encoding(out.get("compliance") or "")), lang)
    except Exception:
        out["compliance_html"] = ensure_html(_fallback_compliance_narr(lang), lang)

    # Sections (nur Praxisbeispiel ergänzen, Compliance separat gerendert)
    parts = []
    if out.get("praxisbeispiel"):
        parts.append(f"<h2>{'Praxisbeispiel' if lang=='de' else 'Case study'}</h2>\n{out['praxisbeispiel']}")
    out["sections_html"] = "\n\n".join(parts)

    # Defensiv Tabellen-Fallbacks initialisieren
    out.setdefault("foerderprogramme_table", [])
    out.setdefault("tools_table", [])

    return out
