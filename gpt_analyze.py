import json
from openai import OpenAI
client = OpenAI()

# 🔥 Tools & Förderungen laden
with open("tools_und_foerderungen.json") as f:
    tools_data = json.load(f)

def prompt_abschnitt_1(data):
    return f"""
Sie sind ein TÜV-zertifizierter, deutschsprachiger KI-Consultant. Analysieren Sie die folgenden Angaben und liefern Sie ausschließlich ein valides JSON mit diesen Feldern:

- "executive_summary": Prägnante, verständliche Management-Zusammenfassung (10-15 Zeilen), die die wichtigsten Chancen und Herausforderungen der KI-Readiness sowie die Digitalisierungs- und Automatisierungsstärke im Vergleich zum Branchendurchschnitt beschreibt – **ohne Aufzählungszeichen**, sondern als Fließtext!
- "unternehmensprofil": Menschlich lesbare Beschreibung von Branche, Größe, Selbstständigkeit, Region, Hauptleistung, Zielgruppen – **keine Listen, sondern 2-3 Sätze**.
- "status_quo_ki": Stand bei Digitalisierung, Automatisierung, papierlosen Prozessen und aktuellem KI-Einsatz – **vergleichend, komprimiert, verständlich**.

Jeglicher erläuternder Text außerhalb des JSON ist untersagt.

Nutzerdaten:
{json.dumps(data, ensure_ascii=False)}
"""

def prompt_abschnitt_2(data):
    return f"""
Sie sind ein TÜV-zertifizierter KI-Consultant. Analysieren Sie die Angaben und liefern Sie ausschließlich ein valides JSON mit diesen Feldern:

- "compliance_analysis": Kompakte Bewertung zu Datenschutzbeauftragtem, technischen Maßnahmen, DSGVO-Status, Meldewegen, Löschregeln, AI-Act-Kenntnis. Welche Risiken und akuten Handlungsfelder bestehen? **Konkrete Praxis-Hinweise einbauen!**
- "risikoanalyse": Die größten Hemmnisse für den KI-Einsatz im Unternehmen, mit mindestens einem branchenspezifischen Beispiel.
- "foerdermittel": **Klartext!** Welche Förderprogramme (regional/bundesweit/EU) sind realistisch? Förderhöhe? Spezielle Chancen für die Unternehmensgröße/Region? Individuelle Tipps. Praxislink, falls möglich.

Jeglicher erläuternder Text außerhalb des JSON ist untersagt.

Nutzerdaten:
{json.dumps(data, ensure_ascii=False)}
"""

def prompt_abschnitt_3(data):
    return f"""
Sie sind ein TÜV-zertifizierter KI-Consultant. Analysieren Sie die Angaben und liefern Sie ausschließlich ein valides JSON mit diesen Feldern:

- "innovation_analysis": Welche laufenden/geplanten KI-Projekte sind für die Branche und Unternehmensgröße sinnvoll? 2-3 Beispiele als Satz.
- "chancen": **Quick-Wins und Chancen** in kurzen, prägnanten Bullet-Points (max. 5).
- "wettbewerbsanalyse": Kurztext zur Marktposition im Vergleich zum Wettbewerb (Innovationsgrad, Positionierung, evtl. Nachholbedarf).

Jeglicher erläuternder Text außerhalb des JSON ist untersagt.

Nutzerdaten:
{json.dumps(data, ensure_ascii=False)}
"""

def prompt_abschnitt_4(data):
    return f"""
Sie sind ein TÜV-zertifizierter KI-Consultant. Analysieren Sie die folgenden Angaben und liefern Sie ausschließlich ein valides JSON mit diesen Feldern:

- "vision": Ein motivierendes Zukunftsbild, wie das Unternehmen in 2 Jahren mit optimal genutzter KI dastehen könnte (Gamechanger-Effekte, neue Geschäftsmodelle, „Moonshot“-Potenziale), **als inspirierender Absatz**.
- "empfehlungen": Maximal 10 Next Steps/Bulletpoints, klar priorisiert, mit Tool- und Praxisempfehlungen, sofort umsetzbar.
- "call_to_action": Abschlussbotschaft, die zur Umsetzung und weiteren Beratung motiviert.

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
    except Exception as e:
        # Retry mit expliziter JSON-Aufforderung
        content1 = gpt_call(prompt_abschnitt_1(data) + "\n\nAntwort ausschließlich als valides JSON-Objekt!")
        results.update(json.loads(content1))

    # Abschnitt 2: Compliance, Risiken, Fördermittel
    try:
        content2 = gpt_call(prompt_abschnitt_2(data))
        results.update(json.loads(content2))
    except Exception as e:
        content2 = gpt_call(prompt_abschnitt_2(data) + "\n\nAntwort ausschließlich als valides JSON-Objekt!")
        results.update(json.loads(content2))

    # Abschnitt 3: Innovation, Chancen, Benchmarking
    try:
        content3 = gpt_call(prompt_abschnitt_3(data))
        results.update(json.loads(content3))
    except Exception as e:
        content3 = gpt_call(prompt_abschnitt_3(data) + "\n\nAntwort ausschließlich als valides JSON-Objekt!")
        results.update(json.loads(content3))

    # Abschnitt 4: Vision, Moonshot, Roadmap
    try:
        content4 = gpt_call(prompt_abschnitt_4(data))
        results.update(json.loads(content4))
    except Exception as e:
        content4 = gpt_call(prompt_abschnitt_4(data) + "\n\nAntwort ausschließlich als valides JSON-Objekt!")
        results.update(json.loads(content4))

    return results
