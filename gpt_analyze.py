import json
import os
import pandas as pd
from openai import OpenAI

client = OpenAI()  # API-Key wird aus Umgebungsvariable gelesen

# --- Hilfsfunktion: KI-Readiness-Score berechnen ---
def calc_readiness_score(data):
    score = 0
    try:
        score += int(data.get("digitalisierungsgrad", 0)) * 2
        score += int(data.get("risikofreude", 0)) * 2
        ki_knowhow_list = ["Keine Erfahrung", "Grundkenntnisse", "Mittel", "Fortgeschritten", "Expertenwissen"]
        score += ki_knowhow_list.index(data.get("ki_knowhow", "Keine Erfahrung")) * 4
        autom_list = ["Sehr niedrig", "Eher niedrig", "Mittel", "Eher hoch", "Sehr hoch"]
        score += autom_list.index(data.get("automatisierungsgrad", "Sehr niedrig")) * 4
        if data.get("ki_projekte", "").strip():
            score += 8
        if data.get("folgenabschaetzung") == "Ja":
            score += 8
        if data.get("technische_massnahmen") == "Alle relevanten Maßnahmen vorhanden":
            score += 8
        score += 12  # Grundwert für Teilnahme/Motivation
    except Exception:
        score = 42  # Fallback
    return min(100, max(0, score))


# --- Hilfsfunktionen für Datenintegration ---
def read_csv_html(path, filter_dict=None, columns=None):
    try:
        df = pd.read_csv(path)
        if filter_dict:
            for key, value in filter_dict.items():
                if key in df.columns and value:
                    df = df[df[key].astype(str).str.contains(value, case=False, na=False)]
        if columns:
            df = df[columns]
        if df.empty:
            return "<i>Keine passenden Einträge gefunden.</i>"
        return df.to_html(index=False, justify='left', escape=False)
    except Exception as e:
        return f"<i>Fehler beim Lesen der CSV {path}: {e}</i>"

def read_markdown(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"_Datei nicht gefunden: {path}_"

def get_tools_table(data):
    filter_dict = {
        'Branche': data.get("branche", ""),
        'Unternehmensgröße': data.get("unternehmensgroesse", "")
    }
    return read_csv_html('data/tools.csv', filter_dict=filter_dict, columns=['Tool', 'Zweck', 'Link', 'Aufwand'])

def get_foerdermittel_table(data):
    filter_dict = {
        'Region': data.get("bundesland", ""),
        'Zielgruppe': data.get("unternehmensgroesse", "")
    }
    return read_csv_html('data/foerdermittel.csv', filter_dict=filter_dict, columns=['Programm', 'Region', 'Fördersumme', 'Link', 'Aufwand'])

def get_praxisbeispiele(data):
    inhalt = read_markdown('data/praxisbeispiele.md')
    branche = data.get("branche", "").lower()
    matches = [block.strip() for block in inhalt.split('---') if branche in block.lower()]
    return "<br><br>".join(matches[:2]) if matches else "<i>Keine Praxisbeispiele für Ihre Branche gefunden.</i>"

def get_checkliste(name):
    return read_markdown(f'data/{name}.md')

# --- Prompt-Vorlagen für alle Abschnitte (wie gehabt, keine Änderung nötig) ---
# --- Prompt-Vorlagen für alle Abschnitte ---
def prompt_exec_summary(data, score):
    return f"""
Sie sind ein deutschsprachiger, TÜV-zertifizierter KI-Consultant für Unternehmen der Branche {data.get("branche", "unbekannt")}.
Nutzen Sie die folgenden Unternehmensdaten, um eine Executive Summary mit **mindestens 1.200 Wörtern** zu verfassen:

- Heben Sie Stärken, Schwächen, Chancen und Risiken in ausführlichen Absätzen hervor.
- Berücksichtigen Sie alle Antworten des Fragebogens (siehe unten).
- Ergänzen Sie Infokästen wie „Praxisbeispiel“, „Expertentipp“, „Checkliste“ und „Fördermittel-Special“.
- Bauen Sie aktuelle deutsche Branchendaten & Benchmarks ein (z.B. KI-Nutzung, Digitalisierungsgrad laut Statista, Bitkom, IW Consult, etc.).
- Fügen Sie einen Abschnitt „KI-Readiness-Score: {score}/100“ mit einer kurzen Interpretation hinzu.

UNTERNEHMENSDATEN:
{json.dumps(data, ensure_ascii=False)}
"""

def prompt_benchmark(data):
    branche = data.get("branche", "unbekannt")
    return f"""
Sie sind ein datenbasierter KI-Branchen-Analyst.
Analysieren Sie die aktuelle Position des Unternehmens in der Branche {branche} anhand aktueller Studien (Bitkom, Statista, IW Consult, BMWK etc.).
Geben Sie mindestens 800 Wörter aus, nutzen Sie vergleichbare Statistiken (z.B. KI-Nutzungsquote in KMU, Automatisierungsgrad).
Erstellen Sie eine Tabelle mit mindestens 5 Benchmarks und erläutern Sie, wie das Unternehmen im Vergleich dasteht.
Fügen Sie 2–3 passende Praxisbeispiele/Stories echter Unternehmen der Branche ein.
"""

def prompt_compliance_foerdermittel(data):
    bundesland = data.get("bundesland", "unbekannt")
    groesse = data.get("unternehmensgroesse", "unbekannt")
    return f"""
Sie sind Datenschutz- & Fördermittel-Experte.
Analysieren Sie die Compliance-Situation und identifizieren Sie Risiken, offene Aufgaben und Potenziale (mindestens 800 Wörter).
Listen Sie alle passenden bundesweiten und landesspezifischen Förderprogramme für {bundesland} und {groesse} auf (bitte mit Namen, Fördersummen, typischem Ablauf, Link).
Schreiben Sie zu jedem Programm eine Schritt-für-Schritt-Box „So beantragen Sie diese Förderung“ (50–80 Wörter).
Fügen Sie pro Bereich 2–3 Best-Practice-Praxisbeispiele (je 100–150 Wörter) ein (Datenschutz, Fördermittel).
"""

def prompt_innovation_tools(data):
    branche = data.get("branche", "unbekannt")
    groesse = data.get("unternehmensgroesse", "unbekannt")
    projektziel = ", ".join(data.get("projektziel", [])) if isinstance(data.get("projektziel"), list) else data.get("projektziel", "")
    return f"""
Sie sind ein KI- und Digitalisierungsstratege.
Analysieren Sie Innovationspotenzial und Wachstumschancen für das Unternehmen (mindestens 900 Wörter).
Fügen Sie für alle genannten Ziele (z.B. {projektziel}) pro Bereich 2–3 inspirierende Praxisbeispiele aus der deutschen Wirtschaft ein.
Stellen Sie eine Tool-Liste mit Links zusammen (mindestens 6 KI- und Digitaltools), die zu Branche, Größe und Zielen passen. Jede Tool-Empfehlung soll eine Kurzbeschreibung und einen Link enthalten.
"""

def prompt_vision_roadmap(data):
    return f"""
Entwickeln Sie eine ausführliche, motivierende KI-Vision & Roadmap für das Unternehmen (mindestens 1.200 Wörter).
Strukturieren Sie als Zeitstrahl: Monate 1–6, 7–18, 19–24+. Geben Sie zu jeder Phase:
- konkrete Maßnahmen,
- Tool-Tipps (mit Links),
- Praxisbeispiel („So kann es aussehen“),
- einen „Moonshot“-Abschnitt (Wie sieht echter Durchbruch aus?).

Schließen Sie mit einem motivierenden Call-to-Action.
"""

def prompt_glossar_tools_faq(data):
    return f"""
Erstellen Sie:
- Ein Glossar mit 15 zentralen Begriffen zu KI, Digitalisierung, Förderung, Compliance (je Begriff: 1 Satz Erklärung)
- Eine separate Tabelle mit empfohlenen Tools (Toolname, Zweck, Link)
- 10 häufige Fragen (FAQ) zum Thema KI in der Branche des Unternehmens, mit prägnanten Antworten.
"""

# --- Hauptfunktion: Analyse & Report-Generierung ---
def generate_report(data):
    score = calc_readiness_score(data)
    results = []

    # Executive Summary & Score
    summary = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt_exec_summary(data, score)}],
        max_tokens=4000
    ).choices[0].message.content
    results.append("## Executive Summary & KI-Readiness-Score\n\n" + summary)

    # Benchmark & Branchenvergleich
    benchmark = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt_benchmark(data)}],
        max_tokens=3000
    ).choices[0].message.content
    results.append("## Branchenvergleich & Benchmarks\n\n" + benchmark)

    # Compliance & Fördermittel
    compliance = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt_compliance_foerdermittel(data)}],
        max_tokens=3000
    ).choices[0].message.content
    results.append("## Compliance, Risiken & Fördermittel\n\n" + compliance)

    # Innovation & Tools
    innovation = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt_innovation_tools(data)}],
        max_tokens=3500
    ).choices[0].message.content
    results.append("## Innovation, Chancen & Tool-Tipps\n\n" + innovation)

    # Vision & Roadmap
    vision = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt_vision_roadmap(data)}],
        max_tokens=3500
    ).choices[0].message.content
    results.append("## Ihre Zukunft mit KI: Vision & Roadmap\n\n" + vision)

    # Glossar, Tool-Liste, FAQ
    glossary = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt_glossar_tools_faq(data)}],
        max_tokens=2000
    ).choices[0].message.content
    results.append("## Glossar, Tool-Liste & FAQ\n\n" + glossary)

    # --- Eigene Datenintegration nach KI-Ausgabe ---

    # Score-Visualisierung (Markdown)
    score_vis = read_markdown('data/score_visualisierung.md')
    results.append("## Score-Visualisierung & Interpretation\n\n" + score_vis)

    # Alle Checklisten integrieren
    checklisten_namen = [
        "check_ki_readiness",
        "check_datenschutz",
        "check_compliance_eu_ai_act",
        "check_foerdermittel",
        "check_umsetzungsplan_ki",
        "check_innovationspotenzial"
    ]
    for name in checklisten_namen:
        content = get_checkliste(name)
        if content.strip():
            results.append(f"## Checkliste: {name.replace('check_', '').replace('_', ' ').title()}\n\n{content}")

    # Tool-Tabelle, nach Branche/Größe
    results.append("## Empfohlene Tools (gefiltert nach Branche & Größe)\n\n" + get_tools_table(data))

    # Fördermittel-Tabelle, nach Bundesland/Größe
    results.append("## Förderprogramme (regional & national)\n\n" + get_foerdermittel_table(data))

    # Praxisbeispiele (nach Branche gefiltert)
    results.append("## Branchennahe Praxisbeispiele\n\n" + get_praxisbeispiele(data))

    return "\n\n---\n\n".join(results)

