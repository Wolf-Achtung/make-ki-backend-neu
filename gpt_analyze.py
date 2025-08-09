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
def gpt_generate_section(data, branche, chapter, lang: str = "de") -> str:
    """
    Generiert einen Abschnitt des KI-Readiness-Reports.

    Die Sprache wird aus dem Formular (`language` oder `sprache`) ermittelt.
    Das zu verwendende Modell wird über die Umgebungsvariable
    `GPT_MODEL_NAME` gesteuert (Standard: "gpt-4o"). Für GPT-5 wird
    automatisch keine Temperatur übergeben, für andere Modelle kann
    die Temperatur über `GPT_TEMPERATURE` festgelegt werden (Standard: 0.3).
    """
    # Sprache aus dem Formular bevorzugen
    lang = data.get("language", data.get("sprache", lang))
    # Kontextdaten (Formulardaten + Branchen-YAML)
    context = build_context(data, branche, lang)
    projektziel = data.get("projektziel", "")
    context = add_websearch_links(context, branche, projektziel)
    context = add_innovation_features(context, branche, data)
    # Checklisten laden
    if "checklisten" not in context or not context["checklisten"]:
        md_path = "data/check_ki_readiness.md"
        if os.path.exists(md_path):
            with open(md_path, encoding="utf-8") as f:
                context["checklisten"] = checklist_markdown_to_html(f.read())
        else:
            context["checklisten"] = ""
    # Prompt zusammensetzen
    prompt = build_masterprompt(chapter, context, lang)
    # Modellwahl aus ENV
    model_name = os.getenv("GPT_MODEL_NAME", "gpt-4o")
    temperature_str = os.getenv("GPT_TEMPERATURE", "0.3")
    temperature_args = {}
    # Für GPT-5 keine Temperatur setzen
    if not model_name.startswith("gpt-5"):
        try:
            temperature_args = {"temperature": float(temperature_str)}
        except Exception:
            temperature_args = {"temperature": 0.3}
    # OpenAI-Call
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

# ==== Report-Assembly (alle Kapitel durchlaufen) ====

def generate_full_report(data, lang="de"):
    branche = data.get("branche", "default").lower()
    # Automatisch Score berechnen und Kontext hinzufügen
    data["score_percent"] = calc_score_percent(data)
    # Reihenfolge und Kapitelnamen der Prompts (anpassbar!)
    chapters = [
        "executive_summary",
        "tools",
        "foerderprogramme",
        "roadmap",
        "compliance",
        "praxisbeispiel"
    ]
    report = {}
    for chapter in chapters:
        try:
            section = gpt_generate_section(data, branche, chapter, lang=lang)
            report[chapter] = fix_encoding(section)
        except Exception as e:
            report[chapter] = f"[Fehler in Kapitel {chapter}: {e}]"
    return report

# ---------------------------------------------------------------------------
# Erweiterte Generierungsfunktionen (asynchron und Dual-Modus)

import asyncio  # für asynchrone Generierung

async def generate_full_report_async(data: dict, lang: str = "de") -> dict:
    """
    Erzeugt alle Kapitel parallel in asynchronen Threads.

    Für jedes Kapitel wird `gpt_generate_section` in einem Thread
    ausgeführt. Dies reduziert die Gesamtwartezeit, sofern die
    zugrundeliegende OpenAI-API mehrere Anfragen parallel verarbeiten
    kann.

    Parameters:
        data (dict): Formulardaten
        lang (str): Sprache
    Returns:
        dict: Bericht mit allen Kapiteln
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

    async def process(ch: str) -> tuple[str, str]:
        try:
            section = await asyncio.to_thread(gpt_generate_section, data, branche, ch, lang)
            return ch, fix_encoding(section)
        except Exception as e:
            return ch, f"[Fehler in Kapitel {ch}: {e}]"

    tasks = [process(ch) for ch in chapters]
    results = await asyncio.gather(*tasks)
    return {ch: text for ch, text in results}

def _call_openai(prompt: str, model_name: str, temperature: float | None = None) -> str:
    """
    Hilfsfunktion, um den OpenAI-Chatendpunkt mit dem angegebenen
    Modell aufzurufen. Falls eine Temperatur übergeben wird und das
    Modell nicht GPT-5 ist, wird sie gesetzt.
    """
    temperature_args = {}
    if temperature is not None and not model_name.startswith("gpt-5"):
        temperature_args = {"temperature": temperature}
    resp = client.chat.completions.create(
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
    return resp.choices[0].message.content.strip()

def gpt_generate_section_model(data: dict, branche: str, chapter: str, model_name: str, lang: str = "de", temperature: float | None = None) -> str:
    """
    Variante von `gpt_generate_section`, die ein explizit angegebenes Modell
    verwendet. Sie erzeugt den Kontext, baut den Prompt und ruft
    anschließend das Modell über `_call_openai` auf.
    """
    # Sprache aus dem Formular bevorzugen
    lang = data.get("language", data.get("sprache", lang))
    context = build_context(data, branche, lang)
    projektziel = data.get("projektziel", "")
    context = add_websearch_links(context, branche, projektziel)
    context = add_innovation_features(context, branche, data)
    if "checklisten" not in context or not context["checklisten"]:
        md_path = "data/check_ki_readiness.md"
        if os.path.exists(md_path):
            with open(md_path, encoding="utf-8") as f:
                context["checklisten"] = checklist_markdown_to_html(f.read())
        else:
            context["checklisten"] = ""
    prompt = build_masterprompt(chapter, context, lang)
    return _call_openai(prompt, model_name, temperature)

def summarise_with_model(text: str, chapter: str, model_name: str = "gpt-4o", lang: str = "de") -> str:
    """
    Verdichtet und strukturiert einen Text mithilfe eines GPT-Modells.

    Das Modell formatiert den Text mit Überschriften und Listen und
    entfernt eckige Klammern oder Tags.
    """
    if lang.startswith("de"):
        instruction = (
            f"Fasse den folgenden Abschnitt des KI-Readiness-Reports zum Thema '{chapter}' "
            "prägnant zusammen, strukturiere ihn mit Zwischenüberschriften und Aufzählungen in Markdown. "
            "Entferne eckige Klammern oder Tags wie [Prozessautomatisierung/Kostensenkung]. Behalte alle wichtigen Punkte bei."
        )
    else:
        instruction = (
            f"Summarize the following section of the AI Readiness report on '{chapter}' in a concise way. "
            "Use clear headings and bullet lists in Markdown, and remove square brackets or tags such as [Process Automation/Cost Reduction]. "
            "Retain all key points."
        )
    prompt = instruction + "\n\n" + text
    # Für die Zusammenfassung nutzen wir keine benutzerdefinierte Temperatur
    return _call_openai(prompt, model_name, None)

def gpt_generate_section_dual(data: dict, branche: str, chapter: str, lang: str = "de") -> str:
    """
    Kombiniert GPT-5 und GPT-4o für einen Abschnitt.

    Zuerst wird der Abschnitt mit GPT-5 generiert, anschließend mit
    GPT-4o verdichtet und strukturiert.
    """
    raw_text = gpt_generate_section_model(data, branche, chapter, model_name="gpt-5", lang=lang, temperature=None)
    return summarise_with_model(raw_text, chapter, model_name="gpt-4o", lang=lang)

def generate_full_report_dual(data: dict, lang: str = "de") -> dict:
    """
    Erzeugt einen vollständigen Report im Dual-Modus (GPT-5 + GPT-4o).

    Jeder Abschnitt wird zunächst von GPT-5 erstellt und dann von GPT-4o
    formatiert. Der Score wird weiterhin berechnet.
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
            text = gpt_generate_section_dual(data, branche, chapter, lang=lang)
            report[chapter] = fix_encoding(text)
        except Exception as e:
            report[chapter] = f"[Fehler in Kapitel {chapter}: {e}]"
    return report

async def generate_full_report_dual_async(data: dict, lang: str = "de") -> dict:
    """
    Asynchrone Variante des Dual-Modus.

    Für jedes Kapitel wird die Dual-Funktion in einem Thread ausgeführt,
    sodass die gesamte Berichtserstellung parallelisiert wird.
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
    async def process(ch: str) -> tuple[str, str]:
        try:
            text = await asyncio.to_thread(gpt_generate_section_dual, data, branche, ch, lang)
            return ch, fix_encoding(text)
        except Exception as e:
            return ch, f"[Fehler in Kapitel {ch}: {e}]"
    tasks = [process(ch) for ch in chapters]
    results = await asyncio.gather(*tasks)
    return {ch: text for ch, text in results}

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