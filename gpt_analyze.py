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

# ------------------------------- Fördermittel ---------------------------------
def build_dynamic_funding(data: dict, lang: str = "de", max_items: int = 5) -> str:
    """
    Generates an HTML fragment with funding programmes filtered according to
    company size and region. It reads the CSV file in data/foerdermittel.csv
    and picks a handful of relevant programmes. If no programmes match
    filters, it falls back to the first few entries. The output is a list
    with basic information and links. Language is either 'de' or 'en'.
    """
    import csv
    path_csv = os.path.join("data", "foerdermittel.csv")
    if not os.path.exists(path_csv):
        return ""
    programmes = []
    try:
        with open(path_csv, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                programmes.append(row)
    except Exception:
        return ""
    # Filter by company size (target group) where possible
    size = (data.get("unternehmensgroesse") or data.get("company_size") or "").lower()
    zielgruppe_map = {
        "solo": ["solo", "freelancer", "freiberuflich", "einzel"],
        "team": ["kmu", "team", "small"],
        "kmu":  ["kmu", "sme"],
    }
    targets = zielgruppe_map.get(size, [])
    # Filter by region: if Bundesland provided, prefer programmes marked with that region; else include 'Bund'
    region_code = (data.get("bundesland") or data.get("state") or "").lower()
    def matches(row):
        zg = row.get("Zielgruppe", "").lower()
        target_ok = True if not targets else any(t in zg for t in targets)
        reg = row.get("Region", "").lower()
        region_ok = True
        if region_code:
            region_ok = (reg == region_code) or (reg == "bund")
        return target_ok and region_ok
    filtered = [p for p in programmes if matches(p)]
    if not filtered:
        filtered = programmes[:max_items]
    selected = filtered[:max_items]
    if not selected:
        return ""
    title = "Dynamische Förderprogramme" if lang.startswith("de") else "Dynamic funding programmes"
    html_parts = [f"<h3>{title}</h3>", "<ul>"]
    for prog in selected:
        name = prog.get("Name", "")
        desc = (prog.get("Beschreibung", "") or "").strip()
        link = prog.get("Link", "")
        grant = prog.get("Fördersumme (€)", "")
        if lang.startswith("de"):
            line = f"<b>{name}</b>: {desc} – Förderhöhe: {grant}"
        else:
            line = f"<b>{name}</b>: {desc} – Funding amount: {grant}"
        if link:
            line += f" – <a href=\"{link}\" target=\"_blank\">Link</a>"
        html_parts.append(f"<li>{line}</li>")
    html_parts.append("</ul>")
    return "\n".join(html_parts)

# ---------------------------- Erweiterte Risiken -----------------------------
def build_extended_risks(data: dict, lang: str = "de") -> str:
    """
    Returns an HTML fragment with additional risk messages based on the
    questionnaire responses. If no additional risks are identified, returns
    an empty string. The returned fragment is a list (<ul>) of items.
    """
    risks = []
    dq = (data.get("datenqualitaet") or data.get("data_quality") or "").lower()
    if dq in {"niedrig", "low"}:
        if lang.startswith("de"):
            risks.append("Die Datenqualität ist niedrig; unstrukturierte und lückenhafte Daten erschweren KI-Projekte und können zu fehlerhaften Ergebnissen führen.")
        else:
            risks.append("Your data quality is low; unstructured or incomplete data make AI projects difficult and can lead to incorrect results.")
    ai_rm = (data.get("ai_roadmap") or "").lower()
    if ai_rm in {"nein", "no"}:
        if lang.startswith("de"):
            risks.append("Es fehlt eine klar definierte KI-Roadmap. Ohne strategische Planung besteht das Risiko von ineffizienten Insellösungen.")
        else:
            risks.append("There is no clearly defined AI roadmap. Without strategic planning there is a risk of inefficient point solutions.")
    gov = (data.get("governance") or "").lower()
    if gov in {"nein", "no"}:
        if lang.startswith("de"):
            risks.append("Es bestehen keine internen Richtlinien für Daten- oder KI-Governance; dies erhöht das Risiko von Rechtsverstößen und unsauberen Prozessen.")
        else:
            risks.append("There are no internal guidelines for data or AI governance; this increases the risk of legal violations and inconsistent processes.")
    inv = (data.get("innovationskultur") or data.get("innovation_culture") or "").lower()
    if inv in {"eher_zurueckhaltend", "sehr_zurueckhaltend", "rather_reluctant", "very_reluctant"}:
        if lang.startswith("de"):
            risks.append("Die Innovationskultur im Unternehmen ist zurückhaltend; eine ablehnende Haltung gegenüber neuen Technologien kann den Erfolg von KI-Projekten gefährden.")
        else:
            risks.append("Your company’s innovation culture is reluctant; a sceptical attitude towards new technologies can jeopardise AI project success.")
    if not risks:
        return ""
    parts = ["<ul>"]
    parts += [f"<li>{r}</li>" for r in risks]
    parts.append("</ul>")
    return "\n".join(parts)

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
    t = (text or "").strip()
    if "<" in t and ">" in t:
        return t
    lines = [ln.rstrip() for ln in t.splitlines() if ln.strip()]
    html = []; in_ul = False
    for ln in lines:
        if re.match(r"^[-•*]\s+", ln):
            if not in_ul:
                html.append("<ul>"); in_ul = True
            item = re.sub(r"^[-•*]\s+", "", ln).strip()
            html.append(f"<li>{item}</li>")
        elif re.match(r"^#{1,3}\s+", ln):
            level = len(ln) - len(ln.lstrip("#"))
            txt = ln[level:].strip()
            level = min(3, max(1, level))
            html.append(f"<h{level}>{txt}</h{level}>")
        else:
            if in_ul:
                html.append("</ul>"); in_ul = False
            html.append(f"<p>{ln}</p>")
    if in_ul:
        html.append("</ul>")
    return "\n".join(html)

# ------------------------------- Kontext -------------------------------------
def build_context(data: dict, branche: str, lang: str = "de") -> dict:
    context_path = f"branchenkontext/{branche}.{lang}.yaml"
    if not os.path.exists(context_path):
        context_path = f"branchenkontext/default.{lang}.yaml"
    context = load_yaml(context_path) if os.path.exists(context_path) else {}
    context.update(data or {})

    # Standardwerte
    context.setdefault("copyright_year", datetime.now().year)
    context.setdefault("copyright_owner", "Wolf Hohl")
    context.setdefault("company_size", _as_int(data.get("mitarbeiterzahl") or data.get("employees") or 1) or 1)

    # Solo-Flag
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
# ----------------------------- Prompt-Logik ----------------------------------
def render_prompt(template_text: str, context: dict) -> str:
    """
    Minimaler Renderer für {{ key }} und {{ key | join(', ') }}.
    Jinja nutzen wir unten nur für das PDF-HTML, nicht für Prompts.
    """
    def replace_join(m):
        key = m.group(1); sep = m.group(2)
        val = context.get(key.strip(), "")
        if isinstance(val, list):
            return sep.join(str(v) for v in val)
        return str(val)

    rendered = re.sub(
        r"\{\{\s*(\w+)\s*\|\s*join\(\s*['\"]([^'\"]*)['\"]\s*\)\s*\}\}",
        replace_join,
        template_text,
    )

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
        "Förderprogramme nur nennen, wenn explizit für Solo-Selbstständige geeignet."
    )
    solo_note_en = (
        "\n\nIMPORTANT: The user is SOLO self-employed. "
        "Avoid advice applicable only to organisations with multiple employees. "
        "Only list funding suitable for solo self-employed."
    )

    if str(lang).lower().startswith("de"):
        style = (
            "\n\n---\n"
            "Gib die Antwort AUSSCHLIESSLICH als gültiges HTML zurück (ohne <html>-Wrapper), "
            "nutze <h3>, <p>, <ul>, <ol>, <table> wo sinnvoll. "
            "Keine Meta-Kommentare, keine Vorrede.\n"
            "- Was tun? (3–5 präzise Maßnahmen, Imperativ)\n"
            "- Warum? (max. 2 Sätze)\n"
            "- Nächste 3 Schritte (Checkliste)\n"
        )
        if context.get("is_self_employed"):
            style += solo_note_de
    else:
        style = (
            "\n\n---\n"
            "Return VALID HTML ONLY (no <html> wrapper). "
            "Use <h3>, <p>, <ul>, <ol>, <table> when helpful. "
            "No meta talk, no preface.\n"
            "- What to do (3–5 precise actions)\n"
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

def gpt_generate_section(data, branche, chapter, lang="de"):
    lang = data.get("lang") or data.get("language") or data.get("sprache") or lang

    context = build_context(data, branche, lang)
    projektziel = data.get("projektziel", "")
    context = add_websearch_links(context, branche, projektziel)
    context = add_innovation_features(context, branche, data)

    # ggf. Checklisten aus data/
    if not context.get("checklisten"):
        md_path = "data/check_ki_readiness.md"
        if os.path.exists(md_path):
            with open(md_path, encoding="utf-8") as f:
                md = f.read()
            ctx_list = []
            for ln in md.splitlines():
                s = ln.strip()
                if s.startswith("- "):
                    ctx_list.append(f"<li>{s[2:].strip()}</li>")
            context["checklisten"] = "<ul>" + "\n".join(ctx_list) + "</ul>" if ctx_list else ""
        else:
            context["checklisten"] = ""

    prompt = build_masterprompt(chapter, context, lang)

    default_model = os.getenv("GPT_MODEL_NAME", "gpt-5")
    model_name = os.getenv("EXEC_SUMMARY_MODEL", default_model) if chapter == "executive_summary" else default_model

    section_text = _chat_complete(
        messages=[
            {"role": "system", "content": (
                "Du bist TÜV-zertifizierter KI-Manager, KI-Strategieberater, "
                "Datenschutz- und Fördermittel-Experte. "
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

    return ensure_html(fix_encoding(section_text), lang=lang)

# ------------------------------ Distillation ---------------------------------
def _distill_two_lists(html_src: str, lang: str, title_a: str, title_b: str):
    model = os.getenv("SUMMARY_MODEL_NAME", os.getenv("GPT_MODEL_NAME", "gpt-5"))
    if str(lang).lower().startswith("de"):
        sys = "Du extrahierst präzise Listen aus HTML."
        usr = (
            f"Extrahiere aus folgendem HTML zwei kompakte Listen als HTML:\n"
            f"<h3>{title_a}</h3><ul>…</ul>\n<h3>{title_b}</h3><ul>…</ul>\n"
            f"- 4–6 Punkte je Liste\n"
            f"- kurze Imperative\n"
            f"- gib nur VALIDES HTML zurück.\n\n"
            f"HTML:\n{html_src}"
        )
    else:
        sys = "You extract precise lists from HTML."
        usr = (
            f"From the HTML, extract two compact lists as HTML:\n"
            f"<h3>{title_a}</h3><ul>…</ul>\n<h3>{title_b}</h3><ul>…</ul>\n"
            f"- 4–6 bullets each\n"
            f"- short imperatives\n"
            f"- return VALID HTML ONLY.\n\n"
            f"HTML:\n{html_src}"
        )
    try:
        out = _chat_complete(
            messages=[{"role":"system", "content": sys}, {"role":"user","content": usr}],
            model_name=model,
            temperature=0.2,
        )
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
        usr = (
            "Extrahiere aus dem HTML 5–8 konkrete Maßnahmen als geordnete Liste <ol>. "
            "Imperativ, jeweils 1 Zeile. Gib nur HTML zurück.\n\n"
            f"HTML:\n{source_html}"
        )
    else:
        sys = "You distill actions from HTML."
        usr = (
            "Extract 5–8 actionable steps as an ordered list <ol>. "
            "Imperative, one line each. Return HTML only.\n\n"
            f"HTML:\n{source_html}"
        )
    try:
        out = _chat_complete(
            messages=[{"role":"system","content":sys},{"role":"user","content":usr}],
            model_name=model,
            temperature=0.2,
        )
        return ensure_html(out, lang)
    except Exception:
        return ""

# ------------------------------- Scoring -------------------------------------
def calc_score_percent(data: dict) -> int:
    """
    Calculate a readiness score on a 0–100 scale with extended dimensions.
    """
    score = 0
    max_score = 51  # siehe Breakdown in Kommentaren der ursprünglichen Version

    try:
        score += int(data.get("digitalisierungsgrad", 1))
    except Exception:
        score += 1

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

    try:
        score += int(data.get("risikofreude", data.get("risk_appetite", 1)))
    except Exception:
        score += 1

    dq_map = {"hoch": 5, "mittel": 3, "niedrig": 1, "high": 5, "medium": 3, "low": 1}
    dq_key = data.get("datenqualitaet") or data.get("data_quality") or ""
    score += dq_map.get(str(dq_key).lower(), 0)

    roadmap_map = {"ja": 5, "in_planung": 3, "nein": 1, "yes": 5, "planning": 3, "no": 1}
    score += roadmap_map.get(str(data.get("ai_roadmap") or "").lower(), 0)

    gov_map = {"ja": 5, "teilweise": 3, "nein": 1, "yes": 5, "partial": 3, "no": 1}
    score += gov_map.get(str(data.get("governance") or "").lower(), 0)

    inov_map = {"sehr_offen": 5, "eher_offen": 4, "neutral": 3, "eher_zurueckhaltend": 2, "sehr_zurueckhaltend": 1,
                "very_open": 5, "rather_open": 4, "neutral": 3, "rather_reluctant": 2, "very_reluctant": 1}
    inov_key = data.get("innovationskultur") or data.get("innovation_culture") or ""
    score += inov_map.get(str(inov_key).lower(), 0)

    if data.get("strategische_ziele") or data.get("strategic_goals"):
        score += 1

    try:
        percent = int((score / max_score) * 100)
    except Exception:
        percent = 0
    return max(0, min(100, percent))
# ---------------------------- Kapitel erzeugen -------------------------------
def gpt_generate_section_html(data, branche, chapter, lang="de") -> str:
    html = gpt_generate_section(data, branche, chapter, lang=lang)
    return ensure_html(html, lang)

def generate_full_report(data: dict, lang: str = "de") -> dict:
    """
    Liefert Kapitel-HTML & Template-Felder:
      exec_summary_html, quick_wins_html, risks_html, recommendations_html,
      roadmap_html, sections_html (+ optional foerderprogramme/tools/compliance/praxisbeispiel),
      preface, score_percent, chart_data.
    """
    branche = (data.get("branche") or "default").lower()
    data["score_percent"] = calc_score_percent(data)

    solo = is_self_employed(data)
    wants_funding = str(data.get("interesse_foerderung", "")).lower() in {"ja", "unklar"}

    # Vision als eigenes Kapitel ergänzen
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

    # Quick Wins & Risiken aus Executive + Roadmap
    src_for_qr = (out.get("executive_summary") or "") + "\n\n" + (out.get("roadmap") or "")
    q_r = distill_quickwins_risks(src_for_qr, lang=lang)
    out["quick_wins_html"] = q_r.get("quick_wins_html", "")
    out["risks_html"] = q_r.get("risks_html", "")

    # Empfehlungen aus Roadmap (+ Compliance Fallback)
    src_for_rec = (out.get("roadmap") or "") + "\n\n" + (out.get("compliance") or "")
    out["recommendations_html"] = distill_recommendations(src_for_rec, lang=lang) or (out.get("roadmap") or "")

    # Roadmap/Exec
    out["roadmap_html"] = out.get("roadmap", "")
    out["exec_summary_html"] = out.get("executive_summary", "")

    # Sammle übrige Kapitel
    parts = []
    label_tools = "Tools"
    label_foerd = "Förderprogramme" if str(lang).lower().startswith("de") else "Funding"
    label_comp = "Compliance"
    label_case = "Praxisbeispiel" if str(lang).lower().startswith("de") else "Case Study"

    # Vision ganz vorn
    if out.get("vision"):
        parts.append(f"<h2>{'Visionäre Empfehlung' if str(lang).startswith('de') else 'Visionary Recommendation'}</h2>\n{out['vision']}")

    if out.get("tools"):
        parts.append(f"<h2>{label_tools}</h2>\n{out['tools']}")
    if out.get("foerderprogramme"):
        note = "<p><em>Hinweis: Für Solo-Selbstständige gefiltert (sofern verfügbar).</em></p>" if solo else ""
        parts.append(f"<h2>{label_foerd}</h2>\n{note}\n{out['foerderprogramme']}")
    if out.get("compliance"):
        parts.append(f"<h2>{label_comp}</h2>\n{out['compliance']}")
    if out.get("praxisbeispiel"):
        parts.append(f"<h2>{label_case}</h2>\n{out['praxisbeispiel']}")

    out["sections_html"] = "\n\n".join(parts)

    # Dynamische Förderprogramme (CSV) optional davorsetzen
    try:
        wants_dynamic = str(data.get("interesse_foerderung", "")).lower() in {"ja", "unklar", "yes", "unsure"}
    except Exception:
        wants_dynamic = False
    if wants_dynamic:
        dynamic_html = build_dynamic_funding(data, lang=lang)
        if dynamic_html:
            out["sections_html"] = dynamic_html + ("\n\n" + out["sections_html"] if out["sections_html"] else "")

    # Risiken um zusätzliche Hinweise erweitern
    extra_risks = build_extended_risks(data, lang=lang)
    if extra_risks:
        existing = out.get("risks_html", "") or ""
        out["risks_html"] = (existing.strip() + "\n" + extra_risks) if existing.strip() else extra_risks

    out["score_percent"] = data["score_percent"]

    # Chart-Daten erzeugen
    out["chart_data"] = build_chart_payload(data, out["score_percent"], lang=lang)
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
            "<p>This document summarises your AI readiness results and provides "
            "tailored next steps. It is based on your input and considers legal "
            "requirements, funding options and current AI developments.</p>"
        )
        if score_percent is not None:
            preface += (
                f"<p><b>Your current AI readiness score is {score_percent:.0f}%.</b> "
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
            "footer_text": footer_text,
            # Assets (werden inlined, auch wenn Templates feste srcs haben)
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
  <small>
    TÜV-zertifiziertes KI-Management © {datetime.now().year}: Wolf Hohl ·
    E-Mail: kontakt@ki-sicherheit.jetzt
  </small>
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
