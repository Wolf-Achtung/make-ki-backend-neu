import json
import openai
import os

# Optional: Lade API-Key aus Umgebungsvariable oder trage direkt ein
openai.api_key = os.getenv("OPENAI_API_KEY", "HIER_DEIN_API_KEY")

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
    summary = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt_exec_summary(data, score)}],
        max_tokens=4000
    )["choices"][0]["message"]["content"]
    results.append("## Executive Summary & KI-Readiness-Score\n\n" + summary)

    # Benchmark & Branchenvergleich
    benchmark = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt_benchmark(data)}],
        max_tokens=3000
    )["choices"][0]["message"]["content"]
    results.append("## Branchenvergleich & Benchmarks\n\n" + benchmark)

    # Compliance & Fördermittel
    compliance = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt_compliance_foerdermittel(data)}],
        max_tokens=3000
    )["choices"][0]["message"]["content"]
    results.append("## Compliance, Risiken & Fördermittel\n\n" + compliance)

    # Innovation & Tools
    innovation = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt_innovation_tools(data)}],
        max_tokens=3500
    )["choices"][0]["message"]["content"]
    results.append("## Innovation, Chancen & Tool-Tipps\n\n" + innovation)

    # Vision & Roadmap
    vision = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt_vision_roadmap(data)}],
        max_tokens=3500
    )["choices"][0]["message"]["content"]
    results.append("## Ihre Zukunft mit KI: Vision & Roadmap\n\n" + vision)

    # Glossar, Tool-Liste, FAQ
    glossary = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt_glossar_tools_faq(data)}],
        max_tokens=2000
    )["choices"][0]["message"]["content"]
    results.append("## Glossar, Tool-Liste & FAQ\n\n" + glossary)

    # Optional: Zusammenführen für HTML/PDF
    return "\n\n---\n\n".join(results)

# --- Beispiel für Aufruf (data ist das vom Formular erhaltene JSON) ---
if __name__ == "__main__":
    with open("sample_data.json", encoding="utf-8") as f:
        data = json.load(f)
    report = generate_report(data)
    with open("output_report.md", "w", encoding="utf-8") as f:
        f.write(report)
    print("Report erfolgreich generiert!")

