import json
from openai import OpenAI

client = OpenAI()

def build_prompt(data):
    prompt = f"""
Sie sind ein deutscher KI- und Datenschutzberater für kleine Unternehmen.

Unternehmensdaten:
- Unternehmen: {data.get('unternehmen')}
- Name: {data.get('name')}
- E-Mail: {data.get('email')}
- Branche: {data.get('branche')}
- Maßnahme: {data.get('massnahme')}
- Bereich: {data.get('bereich')}

Antworten auf konkrete Fragen:
- Haben Sie technische Maßnahmen getroffen (z. B. Verschlüsselung, Firewalls, Zugriffskontrollen)? -> {data.get('frage1')}
- Gibt es Schulungen oder Infos für Mitarbeiter zu Datenschutz, KI oder rechtlichen Anforderungen? -> {data.get('frage2')}
- Haben Sie einen Datenschutzbeauftragten oder Verantwortlichen benannt? -> {data.get('frage3')}
- Haben Sie Risiken für den Datenschutz dokumentiert (z. B. Datenschutz-Folgenabschätzung)? -> {data.get('frage4')}
- Gibt es Regeln zur Löschung oder Anonymisierung von personenbezogenen Daten? -> {data.get('frage5')}
- Wissen Ihre Mitarbeiter, was bei einer Datenschutzverletzung zu tun ist? -> {data.get('frage6')}
- Achten Sie darauf, dass Personen ihre Rechte (Auskunft, Löschung, Berichtigung) wahrnehmen können? -> {data.get('frage7')}
- Haben Sie Prozesse zur regelmäßigen Löschung oder Anonymisierung unnötiger Daten? -> {data.get('frage8')}
- Gibt es eine Meldepflicht und klare Abläufe für Datenschutzvorfälle? -> {data.get('frage9')}
- Führen Sie regelmäßige Überprüfungen oder Audits zur Datenschutzkonformität durch? -> {data.get('frage10')}

Bitte erstellen Sie nun ein Audit pro Frage und zusätzlich eine Gesamtbewertung.
Liefern Sie **ausschließlich ein gültiges JSON** mit folgendem Aufbau:

{{
  "frage_audit": {{
    "frage1": "Ihre kurze Analyse dieser Antwort",
    "frage2": "...",
    "frage3": "...",
    "frage4": "...",
    "frage5": "...",
    "frage6": "...",
    "frage7": "...",
    "frage8": "...",
    "frage9": "...",
    "frage10": "..."
  }},
  "compliance_score": ganze Zahl von 0 bis 10,
  "badge_level": "Bronze" | "Silber" | "Gold" | "Platin",
  "readiness_analysis": "kurze branchenspezifische Einschätzung",
  "compliance_analysis": "detaillierte Datenschutz-Bewertung in Sie-Form",
  "use_case_analysis": "Empfehlung für sinnvolle KI-Anwendung",
  "branche_trend": "kurzer Trendtext für diese Branche",
  "vision": "motivierendes Zukunftsbild",
  "toolstipps": ["Tool 1", "Tool 2"],
  "foerdertipps": ["Förderprogramm 1", "Förderprogramm 2"],
  "executive_summary": "1-2 Sätze, was das Unternehmen als Nächstes tun sollte"
}}
"""
    return prompt


def analyze_with_gpt(data):
    text_response = ""
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "user", "content": build_prompt(data)}
            ]
        )
        text_response = response.choices[0].message.content

        # JSON-Teil aus GPT-Antwort herausfiltern
        json_start = text_response.find('{')
        json_end = text_response.rfind('}') + 1
        json_str = text_response[json_start:json_end]

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return {
                "error": "Konnte JSON nicht parsen",
                "raw": text_response
            }

    except Exception as e:
        return {
            "error": f"Fehler beim GPT-Aufruf: {str(e)}",
            "raw": text_response
        }

