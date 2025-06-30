from openai import OpenAI
import json
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def analyze_with_gpt(data):
    try:
        unternehmen = data.get("unternehmen", "Ihr Unternehmen")
        name = data.get("name", "")
        email = data.get("email", "")
        branche = data.get("branche", "keine Angabe")
        massnahme = data.get("massnahme", "keine Angabe")
        bereich = data.get("bereich", "keine Angabe")

        fragen = [data.get(f"frage{i}", "noch unklar") for i in range(1,11)]

        prompt = f"""
Sie sind ein deutscher KI-Readiness- und Datenschutzberater. Analysieren Sie bitte folgende Angaben und erstellen Sie eine klare, branchenspezifische Auswertung:

Unternehmen: {unternehmen}
Branche: {branche}
Geplante Maßnahme: {massnahme}
Bereich: {bereich}

Antworten:
1: {fragen[0]}, 2: {fragen[1]}, 3: {fragen[2]}, 4: {fragen[3]}, 5: {fragen[4]},
6: {fragen[5]}, 7: {fragen[6]}, 8: {fragen[7]}, 9: {fragen[8]}, 10: {fragen[9]}

Bitte geben Sie ausschließlich ein validiertes JSON zurück, ohne ``` oder ähnliches, in dieser Struktur:

{{
  "compliance_score": ganze Zahl von 0 bis 10,
  "badge_level": "Bronze" | "Silber" | "Gold" | "Platin",
  "readiness_analysis": "Kurze branchenspezifische Einschätzung",
  "compliance_analysis": "Detailanalyse des Datenschutz-Standes",
  "use_case_analysis": "Konkrete Empfehlung, wie KI hier helfen kann",
  "branche_trend": "Branchentrend",
  "vision": "Motivierendes Zukunftsbild",
  "toolstipps": ["Tool 1", "Tool 2"],
  "foerdertipps": ["Förderprogramm 1", "Förderprogramm 2"],
  "executive_summary": "Zusammenfassung für Entscheider"
}}
"""

        completion = client.chat.completions.create(
            model="gpt-4o",
            temperature=0.4,
            messages=[{"role": "user", "content": prompt}]
        )

        text = completion.choices[0].message.content.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"error": "Konnte JSON nicht parsen", "debug_text": text}

    except Exception as e:
        return {"error": str(e)}
