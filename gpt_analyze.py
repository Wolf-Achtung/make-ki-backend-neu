import os
import json
import yaml
import pandas as pd
import re
from openai import OpenAI
from datetime import datetime

from gamechanger_blocks import build_gamechanger_blocks
from gamechanger_features import GAMECHANGER_FEATURES
from innovation_intro import INNOVATION_INTRO
from websearch_utils import serpapi_search

client = OpenAI()

def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_prompt(filename):
    with open(filename, "r", encoding="utf-8") as f:
        return f.read()

def build_context(data, branche, lang="de"):
    context_path = f"branchenkontext/{branche}.{lang}.yaml"
    if not os.path.exists(context_path):
        context_path = f"branchenkontext/default.{lang}.yaml"
    context = load_yaml(context_path)
    context.update(data)
    return context

def render_template(template: str, context: dict) -> str:
    """
    Einfacher Renderer für Templates mit doppelten geschweiften Klammern.
    Unterstützt Platzhalter wie {{ key }} und join-Filter wie {{ key | join(', ') }}.
    """
    # Filter für Join-Ausdrücke
    def replace_join(match: re.Match) -> str:
        key = match.group(1)
        sep = match.group(2)
        value = context.get(key.strip(), "")
        if isinstance(value, list):
            return sep.join([str(v) for v in value])
        return str(value)

    rendered = re.sub(r"\{\{\s*(\w+)\s*\|\s*join\(\s*['\"]([^'\"]*)['\"]\s*\)\s*\}\}", replace_join, template)

    # Einfache Platzhalter ersetzen
    def replace_simple(match: re.Match) -> str:
        key = match.group(1)
        value = context.get(key.strip(), "")
        if isinstance(value, list):
            return ", ".join([str(v) for v in value])
        return str(value)

    rendered = re.sub(r"\{\{\s*(\w+)\s*\}\}", replace_simple, rendered)
    return rendered


def build_masterprompt(chapter, context, lang="de"):
    """
    Load the prompt for the given chapter and language. If the default path
    "prompts/{lang}/{chapter}.md" is not found, fall back to other known
    directories (e.g., unpacked zip folders) to improve robustness.

    This function also renders the template with the provided context.
    """
    # try a list of possible locations for the prompt file
    possible_paths = [
        f"prompts/{lang}/{chapter}.md",
        f"{lang}/{chapter}.md",
        f"{lang}_unzip/{lang}/{chapter}.md",
        f"en_mod/en/{chapter}.md",
        f"de_unzip/de/{chapter}.md",
        f"en_unzip/en/{chapter}.md",
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
        # as a last resort, try to read the filename directly (may raise)
        prompt_text = load_prompt(f"prompts/{lang}/{chapter}.md")

    # Replace placeholders in the template with context values
    try:
        prompt = render_template(prompt_text, context)
    except Exception as e:
        prompt = f"[Prompt-Rendering-Fehler: {e}]\n{prompt_text}"
    return prompt

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
    html_lines: list[str] = []
    ul_open = False
    for line in md_text.splitlines():
        striped = line.strip()
        if not striped:
            continue
        if striped.startswith('#'):
            if ul_open:
                html_lines.append('</ul>')
                ul_open = False
            heading = striped.lstrip('#').strip()
            html_lines.append(f'<h3>{heading}</h3>')
            continue
        if striped.startswith('- [ ]') or striped.startswith('- [x]'):
            item = striped[5:].strip()
        elif striped.startswith('- '):
            item = striped[2:].strip()
        else:
            continue
        if not ul_open:
            html_lines.append('<ul>')
            ul_open = True
        html_lines.append(f'<li>{item}</li>')
    if ul_open:
        html_lines.append('</ul>')
    return '\n'.join(html_lines)

# Score-Berechnung bleibt bestehen (wie gehabt)
def calc_score_percent(data: dict) -> int:
    score = 0
    max_score = 35
    try:
        score += int(data.get("digitalisierungsgrad", 1))
    except Exception:
        score += 1
    auto_map = {
        "sehr_niedrig": 0, "eher_niedrig": 1, "mittel": 3, "eher_hoch": 4, "sehr_hoch": 5,
    }
    score += auto_map.get(data.get("automatisierungsgrad", ""), 0)
    pap_map = {
        "0-20": 1, "21-50": 2, "51-80": 4, "81-100": 5,
    }
    score += pap_map.get(data.get("prozesse_papierlos", "0-20"), 0)
    know_map = {
        "keine": 0, "grundkenntnisse": 1, "mittel": 3, "fortgeschritten": 4, "expertenwissen": 5,
    }
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
def gpt_generate_section(data, branche, chapter, lang="de"):
    """
    Generiert einen einzelnen Abschnitt des Reports für das angegebene Kapitel.

    Es wird automatisch die Sprache aus dem übermittelten `data` verwendet
    (Felder `language` oder `sprache`). Anschließend wird der Kontext aus
    Brancheninformationen, Websuche und Innovationseigenschaften erzeugt,
    bevor das passende Prompt geladen und mit OpenAI abgefragt wird.

    Das zu verwendende Modell kann über die Umgebungsvariable
    `GPT_MODEL_NAME` konfiguriert werden. Standardmäßig wird `gpt-4o`
    verwendet, da dieses Modell ein gutes Verhältnis aus Geschwindigkeit
    und Qualität bietet. Für `gpt-5` darf keine Temperatur übergeben
    werden, sonst führt die API zu einem Fehler. Für alle anderen Modelle
    kann die Temperatur über `GPT_TEMPERATURE` eingestellt werden
    (Standard: 0.3).

    Parameter:
        data (dict): Formularinhalte des Benutzers
        branche (str): Branche, für die der Report generiert werden soll
        chapter (str): Name des Kapitels/Prompts
        lang (str): Sprache ("de" oder "en")

    Rückgabe:
        str: Vom Modell generierter Abschnittstext
    """
    # Sprache aus dem Formular bevorzugen
    lang = data.get("language", data.get("sprache", lang))

    # Kontextdaten (Formulardaten + Branchen-YAML)
    context = build_context(data, branche, lang)
    # Websearch einbauen
    projektziel = data.get("projektziel", "")
    context = add_websearch_links(context, branche, projektziel)
    # Innovationsfeatures immer ergänzen
    context = add_innovation_features(context, branche, data)
    # Checklisten (z. B. als HTML aus Markdown) einbauen
    if "checklisten" not in context or not context["checklisten"]:
        md_path = "data/check_ki_readiness.md"
        if os.path.exists(md_path):
            with open(md_path, encoding="utf-8") as f:
                context["checklisten"] = checklist_markdown_to_html(f.read())
        else:
            context["checklisten"] = ""
    # Masterprompt bauen
    prompt = build_masterprompt(chapter, context, lang)

    # Modell und Temperatur bestimmen
    model_name = os.getenv("GPT_MODEL_NAME", "gpt-4o")
    temperature_str = os.getenv("GPT_TEMPERATURE", "0.3")
    temperature_args = {}
    try:
        # GPT-5 unterstützt keine Temperatur; andere Modelle schon
        if not model_name.startswith("gpt-5"):
            temperature_args = {"temperature": float(temperature_str)}
    except Exception:
        # Fallback, falls die Temperatur-Variable kein Float ist
        temperature_args = {"temperature": 0.3}

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
    return response.choices[0].message.content.strip()


import asyncio

async def gpt_generate_section_async(data, branche, chapter, lang="de") -> str:
    """
    Asynchrone Variante von `gpt_generate_section`.

    Diese Funktion führt den synchronen GPT-Aufruf in einem Thread aus,
    sodass mehrere Kapitel parallel generiert werden können. Die
    eigentliche Logik bleibt unverändert.
    """
    return await asyncio.to_thread(gpt_generate_section, data, branche, chapter, lang)


# ==== Report-Assembly (alle Kapitel durchlaufen) ====

def generate_full_report(data, lang: str = "de") -> dict:
    """
    Synchronously generates a full report by processing all chapters one after another.

    This function is kept for backward compatibility and testing. It still
    calculates the readiness score and iterates over all report chapters,
    but each GPT call is executed sequentially. For improved performance,
    use the asynchronous counterpart `generate_full_report_async`.

    Parameters:
        data (dict): The user-submitted form data
        lang (str): Report language

    Returns:
        dict: A mapping from chapter names to generated report sections
    """
    branche = data.get("branche", "default").lower()
    data["score_percent"] = calc_score_percent(data)
    chapters = [
        "executive_summary",
        "tools",
        "foerderprogramme",
        "roadmap",
        "compliance",
        "praxisbeispiel",
    ]
    report: dict[str, str] = {}
    for chapter in chapters:
        try:
            section = gpt_generate_section(data, branche, chapter, lang=lang)
            report[chapter] = fix_encoding(section)
        except Exception as e:
            report[chapter] = f"[Fehler in Kapitel {chapter}: {e}]"
    return report

async def generate_full_report_async(data: dict, lang: str = "de") -> dict:
    """
    Generates all report chapters concurrently using asynchronous tasks.

    Each chapter is generated in a separate thread via `gpt_generate_section_async`.
    This can significantly reduce the overall processing time when the
    underlying OpenAI API supports concurrent calls.

    Parameters:
        data (dict): The user-submitted form data
        lang (str): Report language

    Returns:
        dict: A mapping from chapter names to generated report sections
    """
    branche = data.get("branche", "default").lower()
    data["score_percent"] = calc_score_percent(data)
    chapters = [
        "executive_summary",
        "tools",
        "foerderprogramme",
        "roadmap",
        "compliance",
        "praxisbeispiel",
    ]
    tasks = [gpt_generate_section_async(data, branche, ch, lang=lang) for ch in chapters]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    report: dict[str, str] = {}
    for ch, res in zip(chapters, results):
        if isinstance(res, Exception):
            report[ch] = f"[Fehler in Kapitel {ch}: {res}]"
        else:
            report[ch] = fix_encoding(res)
    return report

# ==== Optional: PDF-Export, HTML-Export, API-Endpunkte etc. ergänzen ====

# Beispiel für die Ausgabe im Flask/FastAPI-Route:
"""
from fastapi import FastAPI, Request
app = FastAPI()

@app.post("/report")
async def generate_report(request: Request):
    data = await request.json()
    report = generate_full_report(data)
    return {"report": report}
"""

# ==== Hinweise für Integration ====
# - Die Funktionen build_context, build_masterprompt, add_websearch_links, add_innovation_features etc. sind jetzt Gold-Standard
# - Du musst NUR noch Masterprompts und Kontextdaten (YAML) pflegen!
# - Innovations- und Gamechanger-Features werden immer sinnvoll integriert
# - Keine Wiederholungen mehr, alles wird pro Kapitel sauber getrennt

analyze_full_report = generate_full_report