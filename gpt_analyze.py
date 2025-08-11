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
    # Wenn das Formular eine Sprache definiert (z. B. data.language oder data.sprache),  
    # verwenden wir diese, um die richtigen Prompts/YAMLs zu laden.  
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
        if os.path.exists("data/check_ki_readiness.md"):
            context["checklisten"] = checklist_markdown_to_html(open("data/check_ki_readiness.md", encoding="utf-8").read())
        else:
            context["checklisten"] = ""
    # Masterprompt bauen
    prompt = build_masterprompt(chapter, context, lang)
    # GPT-Call
    # Wähle das Modell abhängig vom Kapitel. Für das Executive‑Summary kann
    # per EXEC_SUMMARY_MODEL ein anderes Modell konfiguriert werden. Für
    # alle anderen Kapitel wird GPT_MODEL_NAME verwendet. Standard ist
    # "gpt-5". Diese Trennung ermöglicht schnellere Ausgaben (z. B. mit
    # gpt-4o) für die meisten Kapitel, während das Executive Summary auf
    # einem hochwertigeren Modell generiert wird.
    default_model = os.getenv("GPT_MODEL_NAME", "gpt-5")
    if chapter == "executive_summary":
        model_name = os.getenv("EXEC_SUMMARY_MODEL", default_model)
    else:
        model_name = default_model

    temperature_args: dict[str, float] = {}
    temp_env = os.getenv("GPT_TEMPERATURE")
    if temp_env:
        try:
            temperature_value = float(temp_env)
        except Exception:
            temperature_value = None
    else:
        temperature_value = 0.3
    # Nur setzen, wenn Modell nicht gpt-5 und ein Temperaturwert definiert ist.
    if not model_name.startswith("gpt-5") and temperature_value is not None:
        temperature_args = {"temperature": temperature_value}

    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": "Du bist ein TÜV-zertifizierter KI-Manager, KI-Strategieberater, Datenschutz- und Fördermittel-Experte. Berichte sind immer aktuell, innovativ, motivierend und branchenspezifisch."},
            {"role": "user", "content": prompt}
        ],
        **temperature_args,
    )
    section_text = response.choices[0].message.content.strip()
    # Für die Kapitel 'tools' und 'foerderprogramme' die Länge der HTML‑Tabelle
    # begrenzen, damit der Report kompakt bleibt. Wir behalten die Kopfzeile
    # und maximal fünf Datenzeilen (max_rows). Falls die Tabelle kürzer
    # ist, bleibt sie unverändert.
    max_rows = 5
    if chapter in {"tools", "foerderprogramme"}:
        try:
            parts = section_text.split("<tr>")
            if len(parts) > (max_rows + 1):
                header = parts[0]
                rows = parts[1:max_rows + 1]
                ending = ""
                if "</table>" in parts[-1]:
                    ending = "</table>"
                section_text = "<tr>".join([header] + rows) + ending
        except Exception:
            pass
    return section_text

# ---------------------------------------------------------------------------
# Neue Hilfsfunktionen für bessere Lesbarkeit und Glossar

def summarize_intro(text: str, lang: str = "de") -> str:
    """
    Erstelle eine kurze, laienverständliche Einführung für ein Kapitel.

    Diese Funktion nutzt ein kleineres Modell (standardmäßig GPT‑4o), um aus
    einem längeren Abschnitt eine verständliche Einleitung von 4–5 Sätzen
    abzuleiten. Die Einleitung erklärt, worum es im folgenden Kapitel geht,
    und weckt Interesse. Für englische Berichte wird automatisch ins
    Englische übersetzt.

    Falls der Abschnitt leer ist oder ein Fehler auftritt, wird ein leerer
    String zurückgegeben.
    """
    if not text:
        return ""
    # Eingabetext begrenzen, um sehr lange Abschnitte zu kürzen. Dies
    # verhindert ein Überschreiten des Tokenlimits und beschleunigt
    # die Zusammenfassung. Wir nehmen die ersten 6000 Zeichen.
    max_chars = 6000
    if len(text) > max_chars:
        text = text[:max_chars] + "…"
    # Wähle ein Modell für die Zusammenfassung. Wir nutzen standardmäßig
    # GPT‑4o, da dieses Modell stabilere und besser formatierte Ausgaben liefert.
    summary_model = os.getenv("SUMMARY_MODEL_NAME", "gpt-4o")
    try:
        if lang.startswith("de"):
            # Die Einleitung soll für Laien verständlich sein und am Ende die wichtigsten Punkte in einer Liste aufführen.
            prompt_intro = (
                "Fasse den folgenden Abschnitt in 4-5 kurzen Sätzen zusammen."
                " Schreibe eine laienverständliche Einleitung, die erläutert, worum es in diesem Kapitel geht und die Neugier weckt."
                " Verwende einfache, klare Sprache. Danach liste die zwei bis drei wichtigsten Empfehlungen oder Erkenntnisse stichpunktartig auf."
                " Nutze dafür echte Aufzählungszeichen (•) und setze jeden Punkt in eine eigene Zeile.\n\n"
                f"Abschnitt:\n{text.strip()}"
            )
            system_msg = "Du bist ein professioneller Redakteur, der komplexe Inhalte verständlich zusammenfasst."
        else:
            prompt_intro = (
                "Summarize the following section in 4-5 concise sentences."
                " Provide an easy-to-understand introduction that explains what this chapter is about and sparks curiosity."
                " Use simple, clear language. Afterwards list the two to three most important recommendations or insights as bullet points."
                " Use real bullet points (•) and put each item on its own line.\n\n"
                f"Section:\n{text.strip()}"
            )
            system_msg = "You are a professional editor who summarises complex content clearly and concisely."
        response = client.chat.completions.create(
            model=summary_model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt_intro},
            ],
        )
        return response.choices[0].message.content.strip()
    except Exception:
        # Bei Fehlern wird einfach ein leerer String zurückgegeben
        return ""


def generate_glossary(full_text: str, lang: str = "de") -> str:
    """
    Generiert ein Glossar der im Bericht verwendeten Fachbegriffe.

    Der GPT‑Call erstellt eine alphabetisch sortierte Liste von Begriffen mit
    kurzen Erklärungen (1–2 Sätze) in der jeweiligen Sprache. Für deutsche
    Berichte wird die Anweisung auf Deutsch formuliert, für englische Berichte
    auf Englisch. Falls der Bericht leer ist, wird ein leerer String
    zurückgegeben.
    """
    if not full_text:
        return ""
    # Begrenze den Text für das Glossar auf max. 8000 Zeichen, um eine
    # Überlastung des Modells zu vermeiden. Ein gekürzter Text reicht
    # in der Regel aus, um die wichtigsten Begriffe zu extrahieren.
    max_chars = 8000
    if len(full_text) > max_chars:
        full_text = full_text[:max_chars] + "…"
    glossary_model = os.getenv("SUMMARY_MODEL_NAME", "gpt-4o")
    try:
        if lang.startswith("de"):
            prompt_glossary = (
                "Erstelle ein Glossar der wichtigsten Fachbegriffe aus dem folgenden Bericht."
                " Liste die Begriffe alphabetisch und erkläre jeden in ein bis zwei Sätzen"
                " für Laien verständlich. Verwende das Format 'Begriff: Erklärung' und"
                " vermeide Tabellen.\n\n"
                f"Bericht:\n{full_text.strip()}"
            )
            system_msg = "Du bist ein Fachautor, der technische Begriffe für Laien erklärt."
        else:
            prompt_glossary = (
                "Create a glossary of the key technical terms from the following report."
                " List the terms alphabetically and explain each in one to two sentences"
                " in plain language. Use the format 'Term: Explanation' and avoid tables.\n\n"
                f"Report:\n{full_text.strip()}"
            )
            system_msg = "You are a technical writer who explains technical terms for laypeople."
        response = client.chat.completions.create(
            model=glossary_model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt_glossary},
            ],
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return ""

# ========================
# Static Preface Generator
def generate_preface(lang: str = "de", score_percent: float | None = None) -> str:
    """
    Generate a static preface explaining the purpose of the report. This
    function does not call the OpenAI API, ensuring that the preface can be
    created instantly. It optionally includes the score percentage if
    provided. The returned string is HTML and can be inserted directly
    into templates.

    Args:
        lang: Language code ("de" or "en") to select the text.
        score_percent: Optional readiness score to embed into the preface.

    Returns:
        An HTML snippet containing one or two paragraphs.
    """
    if lang.startswith("de"):
        preface = (
            "<p>Dieses Dokument fasst die Ergebnisse Ihres KI‑Readiness‑Checks "
            "zusammen und bietet individuelle Empfehlungen für die nächsten "
            "Schritte. Es basiert auf Ihren Angaben im Fragebogen und "
            "berücksichtigt aktuelle gesetzliche Vorgaben, Fördermöglichkeiten "
            "sowie technologische Entwicklungen im Bereich der Künstlichen "
            "Intelligenz. Nutzen Sie diesen Bericht als Ausgangspunkt für "
            "Ihre weitere KI‑Strategie.</p>"
        )
        if score_percent is not None:
            preface += (
                f"<p><b>Ihr aktueller KI‑Readiness‑Score liegt bei {score_percent:.0f}%.</b> "
                "Dieser Wert zeigt, wie gut Ihr Unternehmen bereits auf den "
                "Einsatz von KI vorbereitet ist.</p>"
            )
        return preface
    else:
        preface = (
            "<p>This document summarises the results of your AI readiness check "
            "and provides tailored recommendations for your next steps. It is "
            "based on the information you provided in the questionnaire and "
            "takes into account current legal requirements, funding "
            "opportunities and technological developments in artificial "
            "intelligence. Use this report as a starting point for your AI "
            "strategy.</p>"
        )
        if score_percent is not None:
            preface += (
                f"<p><b>Your current AI readiness score is {score_percent:.0f}%.</b> "
                "This figure indicates how well your organisation is prepared to "
                "adopt AI.</p>"
            )
        return preface

# ==== Report-Assembly (alle Kapitel durchlaufen) ====

def generate_full_report(data, lang="de"):
    """
    Generiert den kompletten Bericht mit allen Kapiteln sowie Einleitungen und Glossar.

    Für jedes Kapitel wird zunächst der spezifische Prompt via `gpt_generate_section`
    ausgeführt. Anschließend wird eine laienverständliche Einleitung (4–5 Sätze)
    mithilfe von `summarize_intro` erstellt und dem Kapitelinhalt vorangestellt.
    Nachdem alle Kapitel verarbeitet wurden, erstellt `generate_glossary` ein
    Glossar der wichtigsten Fachbegriffe aus dem Gesamttext.

    Die fertigen Kapitel sowie das Glossar werden in einem Dictionary
    zurückgegeben. Die Schlüsselnamen entsprechen den Kapitelnamen. Der
    Glossar‑Eintrag verwendet den Schlüssel 'glossar' für deutsche Berichte
    beziehungsweise 'glossary' für englische Berichte.
    """
    branche = data.get("branche", "default").lower()
    # Automatisch Score berechnen und Kontext hinzufügen
    data["score_percent"] = calc_score_percent(data)
    # Reihenfolge und Kapitelnamen der Prompts
    chapters = [
        "executive_summary",
        "tools",
        "foerderprogramme",
        "roadmap",
        "compliance",
        "praxisbeispiel",
    ]
    report: dict[str, str] = {}
    full_text_segments: list[str] = []
    for chapter in chapters:
        try:
            # Abschnitt generieren
            section_raw = gpt_generate_section(data, branche, chapter, lang=lang)
            section = fix_encoding(section_raw)
            # Einleitung generieren und hinzufügen
            intro = summarize_intro(section, lang=lang)
            if intro:
                section_with_intro = f"<p>{intro}</p>\n\n{section}"
            else:
                section_with_intro = section
            report[chapter] = section_with_intro
            full_text_segments.append(section)
        except Exception as e:
            report[chapter] = f"[Fehler in Kapitel {chapter}: {e}]"
    # Glossar generieren aus dem vollständigen Text
    full_report_text = "\n\n".join(full_text_segments)
    glossary_text = generate_glossary(full_report_text, lang=lang)
    if lang.startswith("de"):
        report["glossar"] = glossary_text
    else:
        report["glossary"] = glossary_text
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