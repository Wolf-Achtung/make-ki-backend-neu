import json
from openai import OpenAI
client = OpenAI()

# 🔥 Tools & Förderungen laden
with open("tools_und_foerderungen.json") as f:
    tools_data = json.load(f)

def prompt_abschnitt_1(data):
    return f"""
Sie sind ein TÜV-zertifizierter KI-Consultant. Analysieren Sie die folgenden Angaben und liefern Sie ausschließlich ein valides JSON mit folgenden Feldern zurück:

- "executive_summary": 10-15 Zeilen Management-Zusammenfassung zur KI-Readiness, Digitalisierung, Hauptstärken/-schwächen.
- "unternehmensprofil": Branchen-Zuordnung, Mitarbeiterzahl, Selbstständigkeit, Region, Hauptleistung, Zielgruppen.
- "status_quo_ki": Stand bei Digitalisierung, Automatisierung, papierlosen Prozessen und aktuellem KI-Einsatz. Wo steht das Unternehmen im Vergleich zum Branchendurchschnitt?

Jeglicher erläuternder Text außerhalb des JSON ist untersagt.

Nutzerdaten:
{json.dumps(data, ensure_ascii=False)}
"""

def prompt_abschnitt_2(data):
    return f"""
Sie sind ein TÜV-zertifizierter KI-Consultant. Analysieren Sie die Angaben und liefern Sie ausschließlich ein valides JSON mit folgenden Feldern zurück:

- "compliance_analysis": Bewertung zu Datenschutzbeauftragtem, technischen Maßnahmen, DSGVO-Status, Meldewegen, Löschregeln, AI-Act-Kenntnis. Welche Risiken bestehen aktuell? Wo besteht akuter Handlungsbedarf?
- "risikoanalyse": Größte Hemmnisse für KI-Einsatz, rechtliche Stolpersteine, branchenspezifische Risiken.
- "foerdermittel": Übersicht: Welche Förderprogramme sind realistisch (regional, bundesweit, EU)? Welches Förderbudget ist erreichbar? Gibt es spezielle Chancen für die Unternehmensgröße/Region? Individuelle Tipps.

Jeglicher erläuternder Text außerhalb des JSON ist untersagt.

Nutzerdaten:
{json.dumps(data, ensure_ascii=False)}
"""

def prompt_abschnitt_3(data):
    return f"""
Sie sind ein TÜV-zertifizierter KI-Consultant. Analysieren Sie die folgenden Angaben und liefern Sie ausschließlich ein valides JSON mit folgenden Feldern zurück:

- "innovation_analysis": Bewertung der laufenden/geplanten KI-Projekte. Welche Use Cases sind für die Branche am relevantesten? Wo liegt das größte individuelle Potenzial? Welche Benchmarks/Best Practices aus der Branche sind relevant?
- "chancen": Welche kurzfristigen Quick-Wins und mittel-/langfristigen Chancen ergeben sich?
- "wettbewerbsanalyse": Wo steht das Unternehmen im Marktvergleich? Gibt es Besonderheiten (Nische, Innovationsgrad, Positionierung)?

Jeglicher erläuternder Text außerhalb des JSON ist untersagt.

Nutzerdaten:
{json.dumps(data, ensure_ascii=False)}
"""

def prompt_abschnitt_4(data):
    return f"""
Sie sind ein TÜV-zertifizierter KI-Consultant. Analysieren Sie die folgenden Angaben und liefern Sie ausschließlich ein valides JSON mit folgenden Feldern zurück:

- "vision": Zukunftsbild – Wie könnte das Unternehmen in 2 Jahren mit optimal genutzter KI aussehen? (Fokus: Gamechanger-Effekte, neue Geschäftsmodelle, „Moonshot“-Potenziale)
- "empfehlungen": Konkrete Next Steps und Roadmap für sofortige und mittelfristige Umsetzung. Welche Tools, Maßnahmen, Kooperationen sollten jetzt gestartet werden? (max. 10 bullet points, praxisnah, priorisiert)
- "call_to_action": Abschlussbotschaft, die motiviert und auf Umsetzung/Weiterberatung hinweist.

Jeglicher erläuternder Text außerhalb des JSON ist untersagt.

Nutzerdaten:
{json.dumps(data, ensure_ascii=False)}
"""

def gpt_call(prompt):
    response = client.chat.completions.create(
        model="gpt-4o",  # GPT-4o ist empfohlen
        messages=[
            {"role": "system", "content": "Sie sind ein deutschsprachiger, zertifizierter KI-Consultant."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        response_format={"type": "json_object"}
    )
    return response.choices[0].message.content

def analyze_briefing(data):
    results = {}

    # Abschnitt 1: Unternehmensprofil & Status Quo
    try:
        content1 = gpt_call(prompt_abschnitt_1(data))
        results.update(json.loads(content1))
    except Exception:
        # Retry mit expliziter JSON-Aufforderung
        content1 = gpt_call(prompt_abschnitt_1(data) + "\n\nAntwort ausschließlich als valides JSON-Objekt!")
        results.update(json.loads(content1))

    # Abschnitt 2: Compliance, Risiken, Fördermittel
    try:
        content2 = gpt_call(prompt_abschnitt_2(data))
        results.update(json.loads(content2))
    except Exception:
        content2 = gpt_call(prompt_abschnitt_2(data) + "\n\nAntwort ausschließlich als valides JSON-Objekt!")
        results.update(json.loads(content2))

    # Abschnitt 3: Innovation, Chancen, Benchmarking
    try:
        content3 = gpt_call(prompt_abschnitt_3(data))
        results.update(json.loads(content3))
    except Exception:
        content3 = gpt_call(prompt_abschnitt_3(data) + "\n\nAntwort ausschließlich als valides JSON-Objekt!")
        results.update(json.loads(content3))

    # Abschnitt 4: Vision, Moonshot, Roadmap
    try:
        content4 = gpt_call(prompt_abschnitt_4(data))
        results.update(json.loads(content4))
    except Exception:
        content4 = gpt_call(prompt_abschnitt_4(data) + "\n\nAntwort ausschließlich als valides JSON-Objekt!")
        results.update(json.loads(content4))

    return results
