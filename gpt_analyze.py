import os
import re
import json
import base64
import zipfile
import mimetypes
from datetime import datetime
from typing import Dict, Any, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

# OpenAI SDK (Environment: OPENAI_API_KEY)
from openai import OpenAI
client = OpenAI()

# ------------------------ optionale Domain-Bausteine -------------------------
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

# ----------------------------- ZIP Bootstrap ---------------------------------
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

# ------------------------------- Helpers -------------------------------------
def _as_int(x):
    try:
        return int(str(x).strip())
    except Exception:
        return None

def is_self_employed(data: dict) -> bool:
    """
    Sehr robuste Heuristik: Solo, Freelancer, self-employed, Mitarbeiterzahl <= 1 etc.
    """
    keys_text = [
        "beschaeftigungsform", "beschäftigungsform", "arbeitsform", "rolle",
        "role", "occupation", "unternehmensform", "company_type"
    ]
    txt = " ".join(str(data.get(k, "") or "") for k in keys_text).lower()
    if any(s in txt for s in ["selbst", "freelanc", "solo", "self-employ"]):
        return True
    for k in ["mitarbeiter", "mitarbeiterzahl", "anzahl_mitarbeiter", "employees", "employee_count", "team_size"]:
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

# ----------------------------- Encoding / HTML -------------------------------
def fix_encoding(text: str) -> str:
    return (
        (text or "")
        .replace("�", "-")
        .replace("–", "-")
        .replace("“", '"')
        .replace("”", '"')
        .replace("’", "'")
    )

def ensure_html(text: str, lang: str = "de") -> str:
    """
    Macht aus Plain-Text valides HTML (Absätze/Listen/Überschriften),
    lässt vorhandenes HTML unverändert durch.
    """
    t = (text or "").strip()
    if "<" in t and ">" in t:
        return t

    lines = [ln.rstrip() for ln in t.splitlines() if ln.strip()]
    html = []
    in_ul = False

    for ln in lines:
        # Bullet-Liste
        if re.match(r"^[-•*]\s+", ln):
            if not in_ul:
                html.append("<ul>")
                in_ul = True
            # WICHTIG: Kein backslash im f-string-Ausdruck → erst bereinigen, dann konkatenieren
            item_txt = re.sub(r"^[-•*]\s+", "", ln).strip()
            html.append("<li>" + item_txt + "</li>")
            continue

        # Überschriften mit #, ##, ###
        if re.match(r"^#{1,3}\s+", ln):
            level = len(ln) - len(ln.lstrip("#"))
            level = min(3, max(1, level))
            txt = ln[level:].strip()
            html.append("<h" + str(level) + ">" + txt + "</h" + str(level) + ">")
            continue

        # Absatz
        if in_ul:
            html.append("</ul>")
            in_ul = False
        html.append("<p>" + ln + "</p>")

    if in_ul:
        html.append("</ul>")

    return "\n".join(html)


# ---------------------------- Erweiterte Risiken -----------------------------
def build_extended_risks(data: dict, lang: str = "de") -> str:
    """Zusätzliche Risiko-Hinweise als <ul>-Liste auf Basis der Antworten."""
    risks = []
    dq = (data.get("datenqualitaet") or data.get("data_quality") or "").lower()
    if dq in {"niedrig", "low"}:
        risks.append("Die Datenqualität ist niedrig; unstrukturierte und lückenhafte Daten erschweren KI-Projekte."
                     if lang.startswith("de") else
                     "Your data quality is low; unstructured or incomplete data hinder AI projects.")
    ai_rm = (data.get("ai_roadmap") or "").lower()
    if ai_rm in {"nein", "no"}:
        risks.append("Es fehlt eine klar definierte KI-Roadmap; Risiko ineffizienter Insellösungen."
                     if lang.startswith("de") else
                     "No clearly defined AI roadmap; risk of inefficient point solutions.")
    gov = (data.get("governance") or "").lower()
    if gov in {"nein", "no"}:
        risks.append("Keine internen Richtlinien für Daten-/KI-Governance; erhöhtes Rechts-/Prozessrisiko."
                     if lang.startswith("de") else
                     "No data/AI governance; increased legal/process risk.")
    inv = (data.get("innovationskultur") or data.get("innovation_culture") or "").lower()
    if inv in {"eher_zurueckhaltend", "sehr_zurueckhaltend", "rather_reluctant", "very_reluctant"}:
        risks.append("Zurückhaltende Innovationskultur kann KI-Erfolg gefährden."
                     if lang.startswith("de") else
                     "Reluctant innovation culture can jeopardise AI project success.")
    if not risks:
        return ""
    return "<ul>" + "".join(f"<li>{r}</li>" for r in risks) + "</ul>"

# ----------------------------- Charts-Payload --------------------------------
def build_chart_payload(data: dict, score_percent: int, lang: str = "de") -> dict:
    """
    JSON-Payload für Charts (Score, Benchmarks, Risiken/Kultur) – für Chart.js.
    """
    def as_int(v, default=0):
        try:
            return int(v)
        except Exception:
            return default

    digitalisierung = as_int(data.get("digitalisierungsgrad", 1), 1)

    auto_map = {"sehr_niedrig": 1, "eher_niedrig": 2, "mittel": 3, "eher_hoch": 4, "sehr_hoch": 5,
                "very_low": 1, "rather_low": 2, "medium": 3, "rather_high": 4, "very_high": 5}
    autom = auto_map.get(str(data.get("automatisierungsgrad","")).lower(), 1)

    pap_map = {"0-20": 1, "21-50": 2, "51-80": 4, "81-100": 5}
    paperless = pap_map.get(str(data.get("prozesse_papierlos","0-20")).lower(), 1)

    know_map = {"keine": 1, "grundkenntnisse": 2, "mittel": 3, "fortgeschritten": 4, "expertenwissen": 5,
                "none": 1, "basic": 2, "medium": 3, "advanced": 4, "expert": 5}
    knowhow = know_map.get(str(data.get("ki_knowhow", data.get("ai_knowhow","keine"))).lower(), 1)

    risk = as_int(data.get("risikofreude", data.get("risk_appetite", 1)), 1)

    dq_map = {"hoch": 5, "mittel": 3, "niedrig": 1, "high": 5, "medium": 3, "low": 1}
    dq = dq_map.get(str(data.get("datenqualitaet", data.get("data_quality",""))).lower(), 0)

    roadmap_map = {"ja": 5, "in_planung": 3, "nein": 1, "yes": 5, "planning": 3, "no": 1}
    roadmap = roadmap_map.get(str(data.get("ai_roadmap","")).lower(), 0)

    gov_map = {"ja": 5, "teilweise": 3, "nein": 1, "yes": 5, "partial": 3, "no": 1}
    gov = gov_map.get(str(data.get("governance","")).lower(), 0)

    inov_map = {"sehr_offen": 5, "eher_offen": 4, "neutral": 3, "eher_zurueckhaltend": 2, "sehr_zurueckhaltend": 1,
                "very_open": 5, "rather_open": 4, "neutral": 3, "rather_reluctant": 2, "very_reluctant": 1}
    inov = inov_map.get(str(data.get("innovationskultur", data.get("innovation_culture",""))).lower(), 0)

    labels_de = ["Digitalisierung","Automatisierung","Papierlos","KI-Know-how",
                 "Risikofreude","Datenqualität","Roadmap","Governance","Innovationskultur"]
    labels_en = ["Digitalisation","Automation","Paperless","AI know-how",
                 "Risk appetite","Data quality","AI roadmap","Governance","Innovation culture"]
    labels = labels_de if str(lang).startswith("de") else labels_en

    dataset = [digitalisierung, autom, paperless, knowhow, risk, dq, roadmap, gov, inov]

    # grober Risikoindikator
    risk_level = 1
    if dq == 1 or gov == 1:
        risk_level = 3
    elif roadmap in {1, 3}:
        risk_level = 2

    return {
        "score": score_percent,
        "dimensions": {"labels": labels, "values": dataset},
        "risk_level": risk_level
    }

# ----------------------------- Tabellen-Payload ------------------------------
def build_funding_table(data: dict, lang: str = "de", max_items: int = 6):
    """CSV data/foerdermittel.csv → Liste für die Tabelle."""
    import csv
    path = os.path.join("data", "foerdermittel.csv")
    if not os.path.exists(path):
        return []
    size = (data.get("unternehmensgroesse") or "").lower()
    targets = {"solo": ["solo","freelancer","einzel"],
               "team": ["kmu","team","small"],
               "kmu":  ["kmu","sme"]}.get(size, [])
    region = (data.get("bundesland") or "").lower()
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            zg = (row.get("Zielgruppe","") or "").lower()
            reg = (row.get("Region","") or "").lower()
            target_ok = True if not targets else any(t in zg for t in targets)
            region_ok = (not region) or (reg == region) or (reg == "bund")
            if target_ok and region_ok:
                rows.append({
                    "name": row.get("Name",""),
                    "zielgruppe": row.get("Zielgruppe",""),
                    "foerderhoehe": row.get("Fördersumme (€)",""),
                    "link": row.get("Link",""),
                })
    return rows[:max_items]

def build_tools_table(data: dict, branche: str, lang: str = "de", max_items: int = 8):
    """CSV data/tools.csv (optional) → Liste {name,usecase,cost,link}."""
    import csv
    path = os.path.join("data", "tools.csv")
    if not os.path.exists(path):
        return []
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            tags = (row.get("Tags") or row.get("Branche") or "").lower()
            if branche and tags and branche not in tags:
                continue
            out.append({
                "name": row.get("Name",""),
                "usecase": row.get("Usecase") or row.get("Einsatz") or "",
                "cost": row.get("Kosten") or row.get("Cost") or "",
                "link": row.get("Link",""),
            })
    return out[:max_items]
# ----------------------------- Prompt-Logik ----------------------------------
def render_prompt(template_text: str, context: dict) -> str:
    """Minimaler Renderer für {{ key }} und {{ key | join(', ') }} in Prompts."""
    def replace_join(m):
        key = m.group(1); sep = m.group(2)
        val = context.get(key.strip(), "")
        if isinstance(val, list):
            return sep.join(str(v) for v in val)
        return str(val)

    rendered = re.sub(r"\{\{\s*(\w+)\s*\|\s*join\(\s*['\"]([^'\"]*)['\"]\s*\)\s*\}\}", replace_join, template_text)

    def replace_simple(m):
        key = m.group(1)
        val = context.get(key.strip(), "")
        if isinstance(val, list):
            return ", ".join(str(v) for v in val)
        return str(val)

    rendered = re.sub(r"\{\{\s*(\w+)\s*\}\}", replace_simple, rendered)
    return rendered

def build_masterprompt(chapter: str, context: dict, lang: str = "de") -> str:
    search_paths = [
        f"prompts/{lang}/{chapter}.md",
        f"prompts_unzip/{lang}/{chapter}.md",
        f"{lang}/{chapter}.md",
        f"de_unzip/de/{chapter}.md",
        f"en_unzip/en/{chapter}.md",
    ]
    prompt_text = None
    for p in search_paths:
        if os.path.exists(p):
            try:
                prompt_text = load_text(p); break
            except Exception:
                continue
    if prompt_text is None:
        prompt_text = f"[NO PROMPT FOUND for {chapter}/{lang}]"

    prompt = render_prompt(prompt_text, context)

    # Stil + Solo-Hinweis
    solo_note_de = (
        "\n\nWICHTIG: Der/die Nutzer:in arbeitet SOLO-selbstständig. "
        "Vermeide Empfehlungen, die nur für Unternehmen mit mehreren Mitarbeitenden sinnvoll sind. "
        "Nur Förderungen listen, die für Solo-Selbstständige passen."
    )
    solo_note_en = (
        "\n\nIMPORTANT: The user is SOLO self-employed. "
        "Avoid advice only applicable to organisations with multiple employees. "
        "List only funding suitable for solo self-employed."
    )

    if str(lang).lower().startswith("de"):
        style = (
            "\n\n---\n"
            "Gib die Antwort AUSSCHLIESSLICH als gültiges HTML zurück (ohne <html>-Wrapper), "
            "nutze <h3>, <p>, <ul>, <ol>, <table> wo sinnvoll. Keine Meta-Kommentare.\n"
            "- Was tun? (3–5 präzise Maßnahmen, Imperativ)\n"
            "- Warum? (max. 2 Sätze)\n"
            "- Nächste 3 Schritte (Checkliste)\n"
        )
        if context.get("is_self_employed"):
            style += solo_note_de
    else:
        style = (
            "\n\n---\n"
            "Return VALID HTML ONLY (no <html> wrapper). Use <h3>, <p>, <ul>, <ol>, <table> when helpful. No meta talk.\n"
            "- What to do (3–5 actions)\n"
            "- Why (max 2 sentences)\n"
            "- Next 3 steps (checklist)\n"
        )
        if context.get("is_self_employed"):
            style += solo_note_en

    return prompt + style

def _chat_complete(messages, model_name: Optional[str], temperature: Optional[float] = None) -> str:
    args = {"model": model_name or os.getenv("GPT_MODEL_NAME", "gpt-5"), "messages": messages}
    if temperature is None:
        temperature = float(os.getenv("GPT_TEMPERATURE", "0.3"))
    if not str(args["model"]).startswith("gpt-5"):
        args["temperature"] = temperature
    resp = client.chat.completions.create(**args)
    return resp.choices[0].message.content.strip()

# ------------------------------- Kontext -------------------------------------
def build_context(data: dict, branche: str, lang: str = "de") -> dict:
    """Kontext aus Branchen-YAML + Fragebogen-Daten zusammenführen."""
    context_path = f"branchenkontext/{branche}.{lang}.yaml"
    if not os.path.exists(context_path):
        context_path = f"branchenkontext/default.{lang}.yaml"
    context = load_yaml(context_path) if os.path.exists(context_path) else {}
    context.update(data or {})
    context.setdefault("copyright_year", datetime.now().year)
    context.setdefault("copyright_owner", "Wolf Hohl")
    context.setdefault("company_size", _as_int(data.get("mitarbeiterzahl") or data.get("employees") or 1) or 1)
    context["is_self_employed"] = is_self_employed(data)
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
        context["websearch_links_foerder"] = serpapi_search(f"aktuelle Förderprogramme {branche} {projektziel} Deutschland {year}", num_results=5)
        context["websearch_links_tools"]   = serpapi_search(f"aktuelle KI-Tools {branche} Deutschland {year}", num_results=5)
    except Exception:
        context["websearch_links_foerder"] = []
        context["websearch_links_tools"] = []
    return context

# ------------------------------ GPT-Kapitel ----------------------------------
def gpt_generate_section(data, branche, chapter, lang="de"):
    lang = data.get("lang") or data.get("language") or data.get("sprache") or lang
    context = build_context(data, branche, lang)
    projektziel = data.get("projektziel", "")
    context = add_websearch_links(context, branche, projektziel)
    context = add_innovation_features(context, branche, data)

    # optionale Checklisten aus data/
    if not context.get("checklisten"):
        md_path = "data/check_ki_readiness.md"
        if os.path.exists(md_path):
            with open(md_path, encoding="utf-8") as f:
                md = f.read()
            ctx_list = [f"<li>{ln[2:].strip()}</li>" for ln in md.splitlines() if ln.strip().startswith("- ")]
            context["checklisten"] = "<ul>" + "\n".join(ctx_list) + "</ul>" if ctx_list else ""
        else:
            context["checklisten"] = ""

    prompt = build_masterprompt(chapter, context, lang)

    default_model = os.getenv("GPT_MODEL_NAME", "gpt-5")
    model_name = os.getenv("EXEC_SUMMARY_MODEL", default_model) if chapter == "executive_summary" else default_model

    section_text = _chat_complete(
        messages=[
            {"role": "system", "content": (
                "Du bist TÜV-zertifizierter KI-Manager, KI-Strategieberater, Datenschutz- und Fördermittel-Experte. "
                "Liefere präzise, umsetzbare, aktuelle und branchenrelevante Inhalte als HTML."
            ) if str(lang).lower().startswith("de") else (
                "You are a TÜV-certified AI manager and strategy consultant. "
                "Deliver precise, actionable, up-to-date, sector-relevant content as HTML."
            )},
            {"role": "user", "content": prompt},
        ],
        model_name=model_name,
        temperature=None,
    )
    return section_text

def gpt_generate_section_html(data, branche, chapter, lang="de") -> str:
    html = gpt_generate_section(data, branche, chapter, lang=lang)
    return ensure_html(fix_encoding(html), lang)

# ------------------------------- Destillation --------------------------------
def _distill_two_lists(html_src: str, lang: str, title_a: str, title_b: str):
    model = os.getenv("SUMMARY_MODEL_NAME", os.getenv("GPT_MODEL_NAME", "gpt-5"))
    if str(lang).lower().startswith("de"):
        sys = "Du extrahierst präzise Listen aus HTML."
        usr = (f"Extrahiere aus folgendem HTML zwei kompakte Listen als HTML:\n"
               f"<h3>{title_a}</h3><ul>…</ul>\n<h3>{title_b}</h3><ul>…</ul>\n"
               f"- 4–6 Punkte je Liste, kurze Imperative, nur valides HTML.\n\nHTML:\n{html_src}")
    else:
        sys = "You extract precise lists from HTML."
        usr = (f"From the HTML, extract two compact lists as HTML:\n"
               f"<h3>{title_a}</h3><ul>…</ul>\n<h3>{title_b}</h3><ul>…</ul>\n"
               f"- 4–6 bullets each, short imperatives, return VALID HTML only.\n\nHTML:\n{html_src}")
    try:
        out = _chat_complete([{"role":"system","content":sys},{"role":"user","content":usr}],
                             model_name=model, temperature=0.2)
        return ensure_html(out, lang)
    except Exception:
        return ""

def distill_quickwins_risks(source_html: str, lang: str = "de") -> Dict[str, str]:
    html = _distill_two_lists(source_html, lang, "Quick Wins", "Hauptrisiken" if str(lang).lower().startswith("de") else "Key Risks")
    if not html:
        return {"quick_wins_html": "", "risks_html": ""}
    m = re.split(r"(?i)<h3[^>]*>", html)
    if len(m) >= 3:
        a = "<h3>" + m[1]; b = "<h3>" + m[2]
        if "Quick Wins" in a or "Quick" in a:
            return {"quick_wins_html": a, "risks_html": b}
        else:
            return {"quick_wins_html": b, "risks_html": a}
    return {"quick_wins_html": html, "risks_html": ""}

def distill_recommendations(source_html: str, lang: str = "de") -> str:
    model = os.getenv("SUMMARY_MODEL_NAME", os.getenv("GPT_MODEL_NAME", "gpt-5"))
    if str(lang).lower().startswith("de"):
        sys = "Du destillierst Maßnahmen aus HTML."
        usr = ("Extrahiere aus dem HTML 5–8 konkrete Maßnahmen als geordnete Liste <ol>. "
               "Imperativ, jeweils 1 Zeile. Gib nur HTML zurück.\n\n" + f"HTML:\n{source_html}")
    else:
        sys = "You distill actions from HTML."
        usr = ("Extract 5–8 actionable steps as an ordered list <ol>. "
               "Imperative, one line each. Return HTML only.\n\n" + f"HTML:\n{source_html}")
    try:
        out = _chat_complete([{"role":"system","content":sys},{"role":"user","content":usr}],
                             model_name=model, temperature=0.2)
        return ensure_html(out, lang)
    except Exception:
        return ""

# ------------------------------- Scoring -------------------------------------
def calc_score_percent(data: dict) -> int:
    """
    Readiness-Score 0–100 mit erweiterten Dimensionen (inkl. Datenqualität,
    Roadmap, Governance, Innovationskultur, Bonus für klare Ziele).
    Robust gegen fehlende Werte; bounded 0..100.
    """
    def as_int_val(v, default=0):
        try:
            return int(v)
        except Exception:
            return default

    score = 0
    max_score = 51  # Summe der Einzelskalen

    score += as_int_val(data.get("digitalisierungsgrad", 1), 1)

    auto_map = {
        "sehr_niedrig": 0, "eher_niedrig": 1, "mittel": 3, "eher_hoch": 4, "sehr_hoch": 5,
        "very_low": 0, "rather_low": 1, "medium": 3, "rather_high": 4, "very_high": 5,
    }
    score += auto_map.get(str(data.get("automatisierungsgrad", "")).lower(), 0)

    pap_map = {"0-20": 1, "21-50": 2, "51-80": 4, "81-100": 5, "0-20%": 1, "21-50%": 2, "51-80%": 4, "81-100%": 5}
    score += pap_map.get(str(data.get("prozesse_papierlos", "0-20")).lower(), 0)

    know_map = {
        "keine": 0, "grundkenntnisse": 1, "mittel": 3, "fortgeschritten": 4, "expertenwissen": 5,
        "none": 0, "basic": 1, "medium": 3, "advanced": 4, "expert": 5,
    }
    score += know_map.get(str(data.get("ki_knowhow", data.get("ai_knowhow", "keine"))).lower(), 0)

    score += as_int_val(data.get("risikofreude", data.get("risk_appetite", 1)), 1)

    dq_map = {"hoch": 5, "mittel": 3, "niedrig": 1, "high": 5, "medium": 3, "low": 1}
    score += dq_map.get(str(data.get("datenqualitaet") or data.get("data_quality") or "").lower(), 0)

    roadmap_map = {"ja": 5, "in_planung": 3, "nein": 1, "yes": 5, "planning": 3, "no": 1}
    score += roadmap_map.get(str(data.get("ai_roadmap") or "").lower(), 0)

    gov_map = {"ja": 5, "teilweise": 3, "nein": 1, "yes": 5, "partial": 3, "no": 1}
    score += gov_map.get(str(data.get("governance") or "").lower(), 0)

    inov_map = {"sehr_offen": 5, "eher_offen": 4, "neutral": 3, "eher_zurueckhaltend": 2, "sehr_zurueckhaltend": 1,
                "very_open": 5, "rather_open": 4, "neutral": 3, "rather_reluctant": 2, "very_reluctant": 1}
    score += inov_map.get(str(data.get("innovationskultur") or data.get("innovation_culture") or "").lower(), 0)

    if data.get("strategische_ziele") or data.get("strategic_goals"):
        score += 1

    try:
        percent = int((score / max_score) * 100)
    except Exception:
        percent = 0
    return max(0, min(100, percent))
# ---------------------------- Kapitel erzeugen -------------------------------
def generate_full_report(data: dict, lang: str = "de") -> dict:
    """
    Liefert Kapitel-HTML & Felder:
      exec_summary_html, quick_wins_html, risks_html, recommendations_html,
      roadmap_html, sections_html, preface, score_percent,
      chart_data, foerderprogramme_table, tools_table, vision.
    """
    branche = (data.get("branche") or "default").lower()
    data["score_percent"] = calc_score_percent(data)

    solo = is_self_employed(data)
    wants_funding = str(data.get("interesse_foerderung", "")).lower() in {"ja", "unklar", "yes", "unsure"}

    chapters = ["executive_summary", "vision", "tools"] \
               + (["foerderprogramme"] if wants_funding else []) \
               + ["roadmap", "compliance", "praxisbeispiel"]

    out: Dict[str, str] = {}
    for chap in chapters:
        try:
            out[chap] = gpt_generate_section_html(data, branche, chap, lang=lang)
        except Exception as e:
            out[chap] = f"<p>[Fehler in Kapitel {chap}: {e}]</p>"

    # Preface
    out["preface"] = generate_preface(lang=lang, score_percent=data.get("score_percent"))

    # Quick Wins & Risiken aus Executive + Roadmap destillieren
    src_for_qr = (out.get("executive_summary") or "") + "\n\n" + (out.get("roadmap") or "")
    q_r = distill_quickwins_risks(src_for_qr, lang=lang)
    out["quick_wins_html"] = q_r.get("quick_wins_html", "")
    out["risks_html"] = q_r.get("risks_html", "")

    # Empfehlungen aus Roadmap (+ Compliance)
    src_for_rec = (out.get("roadmap") or "") + "\n\n" + (out.get("compliance") or "")
    out["recommendations_html"] = distill_recommendations(src_for_rec, lang=lang) or (out.get("roadmap") or "")

    # Roadmap & Exec
    out["roadmap_html"] = out.get("roadmap", "")
    out["exec_summary_html"] = out.get("executive_summary", "")

    # Sammle übrige Kapitel (Vision zuerst)
    parts = []
    if out.get("vision"):
        parts.append(f"<h2>{'Visionäre Empfehlung' if str(lang).startswith('de') else 'Visionary Recommendation'}</h2>\n{out['vision']}")
    if out.get("tools"):
        parts.append(f"<h2>Tools</h2>\n{out['tools']}")
    if out.get("foerderprogramme"):
        label_foerd = "Förderprogramme" if str(lang).startswith("de") else "Funding"
        note = "<p><em>Hinweis: Für Solo-Selbstständige gefiltert (sofern verfügbar).</em></p>" if solo and str(lang).startswith("de") else ""
        parts.append(f"<h2>{label_foerd}</h2>\n{note}\n{out['foerderprogramme']}")
    if out.get("compliance"):
        parts.append(f"<h2>Compliance</h2>\n{out['compliance']}")
    if out.get("praxisbeispiel"):
        parts.append(f"<h2>{'Praxisbeispiel' if str(lang).startswith('de') else 'Case Study'}</h2>\n{out['praxisbeispiel']}")

    out["sections_html"] = "\n\n".join(parts)

    # Dynamischer Förder-Teaser
    if wants_funding:
        dynamic_html = build_dynamic_funding(data, lang=lang)
        if dynamic_html:
            out["sections_html"] = dynamic_html + ("\n\n" + out["sections_html"] if out["sections_html"] else "")

    # Risiken erweitern
    extra_risks = build_extended_risks(data, lang=lang)
    if extra_risks:
        existing = out.get("risks_html", "") or ""
        out["risks_html"] = (existing.strip() + "\n" + extra_risks) if existing.strip() else extra_risks

    # Charts & Tabellen
    out["score_percent"] = data["score_percent"]
    out["chart_data"] = build_chart_payload(data, out["score_percent"], lang=lang)

    try:
        out["foerderprogramme_table"] = build_funding_table(data, lang=lang)
    except Exception:
        out["foerderprogramme_table"] = []
    try:
        out["tools_table"] = build_tools_table(data, branche=branche, lang=lang)
    except Exception:
        out["tools_table"] = []

    # Fallbacks, wenn CSVs fehlen → rudimentär aus HTML-Listen extrahieren
    if wants_funding and not out.get("foerderprogramme_table"):
        teaser = out.get("foerderprogramme") or out.get("sections_html","")
        rows = []
        for m in re.finditer(r"<b>([^<]+)</b>.*?(?:Förderhöhe|Funding amount):\s*([^<]+).*?<a[^>]*href=\"([^\"]+)\"", teaser, re.I|re.S):
            name, amount, link = m.groups()
            rows.append({"name": name.strip(), "zielgruppe": "", "foerderhoehe": amount.strip(), "link": link})
        out["foerderprogramme_table"] = rows[:6]

    if not out.get("tools_table"):
        html_tools = out.get("tools") or out.get("sections_html","")
        rows = []
        for m in re.finditer(r'<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', html_tools, re.I):
            link, name = m.group(1), m.group(2)
            if name and link:
                rows.append({"name": name.strip(), "usecase": "", "cost": "", "link": link})
        out["tools_table"] = rows[:8]

    return out

def generate_preface(lang: str = "de", score_percent: Optional[float] = None) -> str:
    if str(lang).lower().startswith("de"):
        preface = (
            "<p>Dieses Dokument fasst die Ergebnisse Ihres KI-Readiness-Checks zusammen "
            "und bietet individuelle Empfehlungen für die nächsten Schritte. "
            "Es basiert auf Ihren Angaben und berücksichtigt aktuelle gesetzliche Vorgaben, "
            "Fördermöglichkeiten und technologische Entwicklungen.</p>"
        )
        if score_percent is not None:
            preface += (
                f"<p><b>Ihr aktueller KI-Readiness-Score liegt bei {score_percent:.0f}%.</b> "
                "Dieser Wert zeigt, wie gut Sie auf den Einsatz von KI vorbereitet sind.</p>"
            )
        return preface
    else:
        preface = (
            "<p>This document summarises your AI-readiness results and provides "
            "tailored next steps. It is based on your input and considers legal "
            "requirements, funding options and current AI developments.</p>"
        )
        if score_percent is not None:
            preface += (
                f"<p><b>Your current AI-readiness score is {score_percent:.0f}%.</b> "
                "It indicates how prepared you are to adopt AI.</p>"
            )
        return preface

# ------------------------------ Jinja + Assets -------------------------------
def _jinja_env():
    return Environment(
        loader=FileSystemLoader("templates"),
        autoescape=select_autoescape(["html", "htm"]),
        enable_async=False,
    )

def _pick_template(lang: str) -> str:
    if str(lang).lower().startswith("de") and os.path.exists("templates/pdf_template.html"):
        return "pdf_template.html"
    if os.path.exists("templates/pdf_template_en.html"):
        return "pdf_template_en.html"
    return None

def _data_uri_for(path: str) -> Optional[str]:
    if not path or path.startswith(("http://", "https://", "data:")):
        return path
    if os.path.exists(path):
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return f"data:{mime};base64,{b64}"
    tp = os.path.join("templates", path)
    if os.path.exists(tp):
        mime = mimetypes.guess_type(tp)[0] or "application/octet-stream"
        with open(tp, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return f"data:{mime};base64,{b64}"
    return None

def _inline_local_images(html: str) -> str:
    def repl(m):
        src = m.group(1)
        if src.startswith(("http://", "https://", "data:")):
            return m.group(0)
        data = _data_uri_for(src)
        return m.group(0).replace(src, data) if data else m.group(0)
    return re.sub(r'src="([^"]+)"', repl, html)

# ----------------------------- PUBLIC ENTRYPOINT -----------------------------
async def analyze_briefing(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Hauptschnittstelle für main.py:
      - nimmt das Fragebogen-Payload entgegen
      - erzeugt GPT-Kapitel
      - rendert Jinja-Template (de/en)
      - bettet lokale Assets als data-URI ein
      - liefert {"html": "...", "lang": "...", "score_percent": int, "meta": {...}}
    """
    lang = (payload.get("lang") or payload.get("language") or payload.get("sprache") or "de").lower()
    report = generate_full_report(payload, lang=lang)

    template_name = _pick_template(lang)
    if template_name:
        env = _jinja_env()
        tmpl = env.get_template(template_name)

        footer_de = (
            "TÜV-zertifiziertes KI-Management © {year}: Wolf Hohl · "
            "E-Mail: kontakt@ki-sicherheit.jetzt · Alle Inhalte ohne Gewähr; "
            "dieses Dokument ersetzt keine Rechtsberatung."
        )
        footer_en = (
            "TÜV-certified AI Management © {year}: Wolf Hohl · "
            "Email: kontakt@ki-sicherheit.jetzt · No legal advice; "
            "use at your own discretion."
        )
        footer_text = (footer_de if lang.startswith("de") else footer_en).format(year=datetime.now().year)

        ctx = {
            "lang": lang,
            "today": datetime.now().strftime("%Y-%m-%d"),
            "datum": datetime.now().strftime("%Y-%m-%d"),  # für Live-Abschnitte im Template
            "score_percent": report.get("score_percent", 0),
            "preface": report.get("preface", ""),
            "exec_summary_html": report.get("exec_summary_html", ""),
            "quick_wins_html": report.get("quick_wins_html", ""),
            "risks_html": report.get("risks_html", ""),
            "recommendations_html": report.get("recommendations_html", ""),
            "roadmap_html": report.get("roadmap_html", ""),
            "sections_html": report.get("sections_html", ""),
            "vision_html": report.get("vision", ""),
            "chart_data_json": json.dumps(report.get("chart_data", {}), ensure_ascii=False),
            "foerderprogramme_table": report.get("foerderprogramme_table", []),
            "tools_table": report.get("tools_table", []),
            "footer_text": footer_text,
            # Assets (Data-URIs)
            "logo_main": _data_uri_for("ki-sicherheit-logo.webp") or _data_uri_for("ki-sicherheit-logo.png"),
            "logo_tuev": _data_uri_for("tuev-logo-transparent.webp") or _data_uri_for("tuev-logo.webp"),
            "logo_euai": _data_uri_for("eu-ai.svg"),
            "logo_dsgvo": _data_uri_for("dsgvo.svg"),
            "badge_ready": _data_uri_for("ki-ready-2025.webp"),
        }
        html = tmpl.render(**ctx)
    else:
        title = "KI-Readiness Report" if lang.startswith("de") else "AI Readiness Report"
        html = f"""<!doctype html><html><head><meta charset="utf-8">
<style>body{{font-family:Arial,Helvetica,sans-serif;padding:24px;}}</style></head>
<body>
  <h1>{title} · {datetime.now().strftime("%Y-%m-%d")}</h1>
  <div>{report.get("preface","")}</div>
  <h2>Executive Summary</h2>{report.get("exec_summary_html","")}
  <div style="display:flex;gap:24px;">
    <div style="flex:1">{report.get("quick_wins_html","")}</div>
    <div style="flex:1">{report.get("risks_html","")}</div>
  </div>
  <h2>Nächste Schritte</h2>{report.get("recommendations_html","") or report.get("roadmap_html","")}
  {report.get("sections_html","")}
  <hr>
  <small>TÜV-zertifiziertes KI-Management © {datetime.now().year}: Wolf Hohl · E-Mail: kontakt@ki-sicherheit.jetzt</small>
</body></html>"""

    html = _inline_local_images(html)

    return {
        "html": html,
        "lang": lang,
        "score_percent": report.get("score_percent", 0),
        "meta": {
            "chapters": [k for k in ("executive_summary","vision","tools","foerderprogramme","roadmap","compliance","praxisbeispiel") if report.get(k)],
        },
    }

# Backwards-Compat alias
analyze_full_report = generate_full_report
