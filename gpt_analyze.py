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

        # Fragen 1-10 sammeln
        fragen = [data.get(f"frage{i}", "noch unklar") for i in range(1,11)]

        prompt = f"""
Sie sind ein deutscher Unternehmensberater und KI-Compliance-Experte.
Ihre Aufgabe ist es, auf Grundlage der folgenden Angaben eine individuelle, branchenspezifische, verständliche Analyse und Handlungsempfehlung für ein kleines Unternehmen zu erstellen.

Unternehmen: {unternehmen}
Branche: {branche}
Geplante Maßnahme: {massnahme}
Bereich: {bereich}

Datenschutz- & KI-Management Antworten:
Frage 1 (technische Maßnahmen): {fragen[0]}
Frage 2 (Mitarbeiterschulungen): {fragen[1]}
Frage 3 (Datenschutzbeauftragter): {fragen[2]}
Frage 4 (Risiken dokumentiert): {fragen[3]}
Frage 5 (Regeln Löschung/Anonymisierung): {fragen[4]}
Frage 6 (Mitarbeiter wissen was tun): {fragen[5]}
Frage 7 (Rechte Wahrnehmung): {fragen[6]}
Frage 8 (regelmäßige Löschung unnötiger Daten): {fragen[7]}
Frage 9 (Meldepflicht & Ablauf Datenschutzvorfälle): {fragen[8]}
Frage 10 (regelmäßige Überprüfungen/Audits): {fragen[9]}

Bitte antworten Sie ausschließlich mit einem validen JSON-Objekt ohne ```json oder ähnliche Formatierung. 
Struktur:

{
  "compliance_score": ganze Zahl von 0 bis 10 (10 bedeutet vollständige Datenschutz- und KI-Readiness),
  "badge_level": "Bronze" | "Silber" | "Gold" | "Platin",
  "readiness_analysis": "Kurze, branchenspezifische Einschätzung, was das Unternehmen aktuell behindert und was ihm nützen würde.",
  "compliance_analysis": "Detaillierte Datenschutz-Bewertung in Sie-Form.",
  "use_case_analysis": "Empfehlung, wie KI sinnvoll eingesetzt werden kann.",
  "branche_trend": "Kurzer Trendtext zu dieser Branche.",
  "vision": "Motivierendes Zukunftsbild.",
  "toolstipps": ["Tool 1", "Tool 2"],
  "foerdertipps": ["Förderprogramm 1", "Förderprogramm 2"],
  "executive_summary": "1-2 Sätze, was das Unternehmen als nächstes tun sollte."
}
"""

        # GPT call
        completion = client.chat.completions.create(
            model="gpt-4o",
            temperature=0.7,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        text = completion.choices[0].message.content.strip()

        # versuchen als JSON zu parsen
        try:
            response_json = json.loads(text)
            return response_json
        except json.JSONDecodeError:
            return {
                "error": "Konnte JSON nicht parsen",
                "raw": text
            }

    except Exception as e:
        return {"error": str(e)}
