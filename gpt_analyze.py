import os
import json
import yaml
import pandas as pd
import re
import zipfile
from openai import OpenAI
from datetime import datetime

from gamechanger_blocks import build_gamechanger_blocks
from gamechanger_features import GAMECHANGER_FEATURES
from innovation_intro import INNOVATION_INTRO
from websearch_utils import serpapi_search

client = OpenAI()

# ---------- Files / Prompts / Kontext ----------

def ensure_unzipped(zip_name: str, dest_dir: str):
    """
    Falls eine ZIP vorliegt (prompts.zip, branchenkontext.zip, data.zip),
    entpacken wir sie 1x in dest_dir. Existiert dest_dir bereits, passiert nichts.
    """
    try:
        if os.path.exists(zip_name) and not os.path.exists(dest_dir):
            os.makedirs(dest_dir, exist_ok=True)
            with zipfile.ZipFile(zip_name, "r") as zf:
                zf.extractall(dest_dir)
    except Exception:
        # still silent; Log optional
        pass

# ZIPs optional automatisch zur Verfügung stellen
ensure_unzipped("prompts.zip", "prompts_unzip")
ensure_unzipped("branchenkontext.zip", "branchenkontext")
ensure_unzipped("data.zip", "data")


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_prompt(filename):
    with open(filename, "r", encoding="utf-8") as f:
        return f.read()


def build_context(data, branche, lang="de"):
    """
    Lädt Branchen-YAML (branchenkontext/<branche>.<lang>.yaml, Fallback default.<lang>.yaml)
    und merged Formulardaten hinein.
    """
    context_path = f"branchenkontext/{branche}.{lang}.yaml"
    if not os.path.exists(context_path):
        context_path = f"branchenkontext/default.{lang}.yaml"
    context = load_yaml(context_path) if os.path.exists(context_path) else {}
    context.update(data or {})
    return context


def render_template(template: str, context: dict) -> str:
    """
    Minimaler Renderer für {{ key }} und {{ key | join(', ') }}.
    """
    # join-Filter
    def replace_join(m: re.Match) -> str:
        key = m.group(1)
        sep = m.group(2)
        val = context.get(key.strip(), "")
        if isinstance(val, list):
            return sep.join(str(v) for v in val)
        return str(val)

    rendered = re.sub(
        r"\{\{\s*(\w+)\s*\|\s*join\(\s*['\"]([^'\"]*)['\"]\s*\)\s*\}\}",
        replace_join,
        template,
    )

    # einfache Platzhalter
    def replace_simple(m: re.Match) -> str:
        key = m.group(1)
        val = context.get(key.strip(), "")
        if isinstance(val, list):
            return ", ".join(str(v) for v in val)
        return str(val)

    rendered = re.sub(r"\{\{\s*(\w+)\s*\}\}", replace_simple, rendered)
    return rendered


def build_masterprompt(chapter, context, lang="de"):
    """
    Lädt den Prompt für Kapitel+Sprache aus robusten Suchpfaden
    (inkl. prompts_unzip/) und rendert Platzhalter mit Kontext.
    Ergänzt einen Stilblock, der eine scannbare Gold-Standard-Ausgabe erzwingt.
    """
    # Suchpfade in Priorität
    possible_paths = [
        f"prompts/{lang}/{chapter}.md",
        f"prompts_unzip/{lang}/{chapter}.md",
        f"{lang}/{chapter}.md",
        f"{lang}_unzip/{lang}/{chapter}.md",
        f"de_unzip/de/{chapter}.md",
        f"en_unzip/en/{chapter}.md",
        f"en_mod/en/{chapter}.md",
    ]
    prompt_text = None
    for path in possible_paths:
        if os.path.exists(path):
            try:
                prompt_text = load_prompt(path)
                break
            except Exception:
                continue
    if prompt_text is None:
        # letzte Eskalation (kann fehlschlagen)
        prompt_text = load_prompt(f"prompts/{lang}/{chapter}.md")

    # Platzhalter rendern
    try:
        prompt = render_template(prompt_text, context)
    except Exception as e:
        prompt = f"[Prompt-Rendering-Fehler: {e}]\n{prompt_text}"

    # Gold-Standard-Ausgabestil anhängen
    if str(lang).lower().startswith("de"):
        style = (
            "\n\n---\n"
            "Formatiere die Antwort kompakt und scannbar, ohne Meta-Text.\n"
            "- Was tun? (3–5 präzise Maßnahmen, Imperativ)\n"
            "- Warum? (max. 2 Sätze, Impact)\n"
            "- Nächste 3 Schritte (Checkliste, kurze Punkte)\n"
            "Vermeide Einleitungen wie 'In diesem Kapitel geht es ...'. "
            "Nutze klare, aktive Sprache und kurze Sätze."
        )
    else:
        style = (
            "\n\n---\n"
            "Return a compact, scannable answer with no meta text.\n"
            "- What to do (3–5 precise actions, imperative)\n"
            "- Why (max. 2 sentences, impact)\n"
            "- Next 3 steps (checklist, short bullets)\n"
            "Avoid introductions like 'This chapter covers ...'. Use clear, active voice."
        )
    return prompt + style


def add_innovation_features(context, branche, data):
    context["branchen_innovations_intro"] = INNOVATION_INTRO.get(branche, "")
    context["gamechanger_blocks"] = build_gamechanger_blocks(data, GAMECHANGER_FEATURES)
    return context


def add_websearch_links(context, branche, projektziel):
    year = datetime.now().year
    query_foerder = f"aktuelle Förderprogramme {branche} {projektziel} Deutschland {year}"
    context["websearch_links_foerder"] = serpapi_search(query_foerder, num_results=5)
    query_tools = f"aktuelle KI-Tools {branche} Deutschland {year}"
    context["websearch_links_tools"] = serpapi_search(query_tools, num_results=5)
    return context


def checklist_markdown_to_html(md_text: str) -> str:
    """
    Sehr simpler MD→HTML-Konverter für Checklisten-Abschnitte.
    """
    html_lines: list[str] = []
    ul_open = False
    for line in md_text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            if ul_open:
                html_lines.append("</ul>")
                ul_open = False
            heading = s.lstrip("#").strip()
            html_lines.append(f"<h3>{heading}</h3>")
            continue
        if s.startswith("- [ ]") or s.startswith("- [x]"):
            item = s[5:].strip()
        elif s.startswith("- "):
            item = s[2:].strip()
        else:
            continue
        if not ul_open:
            html_lines.append("<ul>")
            ul_open = True
        html_lines.append(f"<li>{item}</li>")
    if ul_open:
        html_lines.append("</ul>")
    return "\n".join(html_lines)
# ---------- Scoring / Utilities ----------

def calc_score_percent(data: dict) -> int:
    score = 0
    max_score = 35
    try:
        score += int(data.get("digitalisierungsgrad", 1))
    except Exception:
        score += 1
    auto_map = {"sehr_niedrig": 0, "eher_niedrig": 1, "mittel": 3, "eher_hoch": 4, "sehr_hoch": 5}
    score += auto_map.get(data.get("automatisierungsgrad", ""), 0)
    pap_map = {"0-20": 1, "21-50": 2, "51-80": 4, "81-100": 5}
    score += pap_map.get(data.get("prozesse_papierlos", "0-20"), 0)
    know_map = {"keine": 0, "grundkenntnisse": 1, "mittel": 3, "fortgeschritten": 4, "expertenwissen": 5}
    score += know_map.get(data.get("ki_knowhow", "keine"), 0)
    try:
        score += int(data.get("risikofreude", 1))
    except Exception:
        score += 1
    percent = int((score / max_score) * 100)
    return percent


def fix_encoding(text: str) -> str:
    return (
        text.replace("�", "-")
        .replace("–", "-")
        .replace("“", '"')
        .replace("”", '"')
        .replace("’", "'")
    )


def extract_swot(full_text: str) -> dict:
    def find(pattern: str) -> str:
        m = re.search(pattern, full_text, re.DOTALL | re.IGNORECASE)
        return m.group(1).strip() if m else ""
    return {
        "swot_strengths": find(r"Stärken:(.*?)(?:Schwächen:|Chancen:|Risiken:|$)"),
        "swot_weaknesses": find(r"Schwächen:(.*?)(?:Chancen:|Risiken:|$)"),
        "swot_opportunities": find(r"Chancen:(.*?)(?:Risiken:|$)"),
        "swot_threats": find(r"Risiken:(.*?)(?:$)"),
    }


# ---------- GPT-Kapitel ----------

def gpt_generate_section(data, branche, chapter, lang="de"):
    """
    Baut den Masterprompt (inkl. Branchenkontext, Websuche, Gamechanger-Blöcke)
    und ruft das passende Modell auf. Tabellen in 'tools' und 'foerderprogramme'
    werden auf max. 5 Datenzeilen begrenzt.
    """
    # Sprache konsistent bestimmen
    lang = data.get("lang") or data.get("language") or data.get("sprache") or lang

    # Kontextdaten
    context = build_context(data, branche, lang)
    projektziel = data.get("projektziel", "")
    context = add_websearch_links(context, branche, projektziel)
    context = add_innovation_features(context, branche, data)

    # Checkliste laden (falls nicht bereits im Kontext)
    if not context.get("checklisten"):
        md_path = "data/check_ki_readiness.md"
        if os.path.exists(md_path):
            with open(md_path, encoding="utf-8") as f:
                context["checklisten"] = checklist_markdown_to_html(f.read())
        else:
            context["checklisten"] = ""

    # Prompt bauen
    prompt = build_masterprompt(chapter, context, lang)

    # Modellwahl
    default_model = os.getenv("GPT_MODEL_NAME", "gpt-5")
    model_name = os.getenv("EXEC_SUMMARY_MODEL", default_model) if chapter == "executive_summary" else default_model

    # Temperatur optional
    temperature_args: dict[str, float] = {}
    temp_env = os.getenv("GPT_TEMPERATURE")
    if temp_env:
        try:
            temperature_value = float(temp_env)
        except Exception:
            temperature_value = None
    else:
        temperature_value = 0.3
    if not model_name.startswith("gpt-5") and temperature_value is not None:
        temperature_args = {"temperature": temperature_value}

    # API Call
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "system",
                "content": (
                    "Du bist ein TÜV-zertifizierter KI-Manager, KI-Strategieberater, "
                    "Datenschutz- und Fördermittel-Experte. Berichte sind immer aktuell, "
                    "innovativ, motivierend und branchenspezifisch."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        **temperature_args,
    )
    section_text = response.choices[0].message.content.strip()

    # Tabelle begrenzen
    max_rows = 5
    if chapter in {"tools", "foerderprogramme"}:
        try:
            parts = section_text.split("<tr>")
            if len(parts) > (max_rows + 1):
                header = parts[0]
                rows = parts[1 : max_rows + 1]
                ending = "</table>" if "</table>" in parts[-1] else ""
                section_text = "<tr>".join([header] + rows) + ending
        except Exception:
            pass

    return section_text


# ---------- Einleitung / Glossar / Preface ----------

def summarize_intro(text: str, lang: str = "de") -> str:
    if not text:
        return ""
    max_chars = 6000
    if len(text) > max_chars:
        text = text[:max_chars] + "…"
    summary_model = os.getenv("SUMMARY_MODEL_NAME", "gpt-4o")
    try:
        if str(lang).lower().startswith("de"):
            prompt_intro = (
                "Fasse den folgenden Abschnitt in 4–5 kurzen Sätzen zusammen. "
                "Schreibe eine laienverständliche Einleitung, dann 2–3 wichtigste Punkte als Bullets (•). "
                "Kein Meta-Text.\n\n"
                f"Abschnitt:\n{text.strip()}"
            )
            system_msg = "Du bist ein professioneller Redakteur, der komplexe Inhalte verständlich zusammenfasst."
        else:
            prompt_intro = (
                "Summarize the following section in 4–5 concise sentences. "
                "Provide an easy intro and then 2–3 key bullets (•). No meta text.\n\n"
                f"Section:\n{text.strip()}"
            )
            system_msg = "You are a professional editor who summarises complex content clearly and concisely."
        response = client.chat.completions.create(
            model=summary_model,
            messages=[{"role": "system", "content": system_msg}, {"role": "user", "content": prompt_intro}],
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return ""


def generate_glossary(full_text: str, lang: str = "de") -> str:
    if not full_text:
        return ""
    max_chars = 8000
    if len(full_text) > max_chars:
        full_text = full_text[:max_chars] + "…"
    glossary_model = os.getenv("SUMMARY_MODEL_NAME", "gpt-4o")
    try:
        if str(lang).lower().startswith("de"):
            prompt_glossary = (
                "Erstelle ein Glossar der wichtigsten Fachbegriffe aus dem folgenden Bericht. "
                "Alphabetisch, Format 'Begriff: Erklärung', 1–2 Sätze, laienverständlich, keine Tabelle.\n\n"
                f"Bericht:\n{full_text.strip()}"
            )
            system_msg = "Du bist ein Fachautor, der technische Begriffe für Laien erklärt."
        else:
            prompt_glossary = (
                "Create a glossary of key technical terms from the report. "
                "Alphabetical, format 'Term: Explanation', 1–2 sentences, plain language, no tables.\n\n"
                f"Report:\n{full_text.strip()}"
            )
            system_msg = "You are a technical writer who explains technical terms for laypeople."
        response = client.chat.completions.create(
            model=glossary_model,
            messages=[{"role": "system", "content": system_msg}, {"role": "user", "content": prompt_glossary}],
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return ""


def generate_preface(lang: str = "de", score_percent: float | None = None) -> str:
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


# ---------- Vollbericht ----------

def generate_full_report(data, lang="de"):
    """
    Erzeugt den kompletten Bericht (Kapitel → Intro → Glossar).
    'foerderprogramme' wird nur erzeugt, wenn interesse_foerderung ∈ {ja, unklar}.
    """
    branche = (data.get("branche") or "default").lower()
    data["score_percent"] = calc_score_percent(data)

    wants_funding = str(data.get("interesse_foerderung", "")).lower() in {"ja", "unklar"}
    chapters = ["executive_summary", "tools"] + (["foerderprogramme"] if wants_funding else []) + ["roadmap", "compliance", "praxisbeispiel"]

    report: dict[str, str] = {}
    full_text_segments: list[str] = []

    for chapter in chapters:
        try:
            section_raw = gpt_generate_section(data, branche, chapter, lang=lang)
            section = fix_encoding(section_raw)
            intro = summarize_intro(section, lang=lang)
            section_with_intro = (f"<p>{intro}</p>\n\n{section}") if intro else section
            report[chapter] = section_with_intro
            full_text_segments.append(section)
        except Exception as e:
            report[chapter] = f"[Fehler in Kapitel {chapter}: {e}]"

    full_report_text = "\n\n".join(full_text_segments)
    glossary_text = generate_glossary(full_report_text, lang=lang)
    if str(lang).lower().startswith("de"):
        report["glossar"] = glossary_text
    else:
        report["glossary"] = glossary_text

    return report


# Bequemer Alias für Integrationen
analyze_full_report = generate_full_report
