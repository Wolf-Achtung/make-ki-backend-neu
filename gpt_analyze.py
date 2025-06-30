import json
import os
from openai import OpenAI

client = OpenAI()

# robustes Directory ermitteln
dir_path = os.path.dirname(os.path.realpath(__file__))

# JSON sicher laden
with open(os.path.join(dir_path, "tools_und_foerderungen.json"), "r", encoding="utf-8") as f:
    db = json.load(f)

def build_prompt(data):
    tools = [tool['name'] for tool in db.get('tools', [])]
    foerderungen = [f['name'] for f in db.get('foerderungen', [])]

    prompt = f"""
Sie sind ein TÜV-zertifizierter deutscher KI- und Datenschutzberater für kleine Unternehmen, Selbstständige und Freiberufler.
Bitte sprechen Sie die Nutzer in der Sie-Form an, in professionellem, klar verständlichem Deutsch.

Unternehmensdaten:
- Unternehmen: {data.get('unternehmen')}
- Ansprechpartner: {data.get('name')}
- E-Mail: {data.get('email')}
- Branche: {data.get('branche')}
- Geplante Maßnahme: {data.get('massnahme')}
- Bereich: {data.get('bereich')}
- Mitarbeiterzahl: {data.get('mitarbeiterzahl')}
- Postleitzahl: {data.get('plz')}

Antworten auf Fragen zur Datenschutz- und KI-Readiness:
1. Haben Sie technische Maßnahmen (Firewall, Verschlüsselung etc.) umgesetzt? {data.get('frage1')}
2. Gibt es regelmäßige Schulungen zu Datenschutz, KI und rechtlichen Vorgaben? {data.get('frage2')}
3. Haben Sie einen Datenschutzbeauftragten benannt? {data.get('frage3')}
4. Führen Sie Risikoanalysen oder Datenschutz-Folgenabschätzungen durch? {data.get('frage4')}
5. Gibt es Prozesse zur Datenlöschung oder Anonymisierung? {data.get('frage5')}
6. Wissen Mitarbeiter, wie bei Datenschutzverletzungen zu handeln ist? {data.get('frage6')}
7. Werden Betroffenenrechte (Auskunft, Löschung) aktiv umgesetzt? {data.get('frage7')}
8. Gibt es eine Dokumentation der Datenverarbeitungsprozesse? {data.get('frage8')}
9. Existieren Meldepflichten und klar geregelte Abläufe bei Datenschutzvorfällen? {data.get('frage9')}
10. Führen Sie regelmäßige interne Audits zu Datenschutz und KI durch? {data.get('frage10')}

Bitte erstellen Sie nun ein Audit mit folgendem JSON-Aufbau und nutzen Sie dafür Ihre Fachkenntnis:

{{
  "compliance_score": ganze Zahl von 0 bis 10 (10 = optimal),
  "badge_level": "Bronze" | "Silber" | "Gold" | "Platin",
  "readiness_analysis": "Branchenspezifische Einschätzung, was derzeit behindert und was nützen würde.",
  "compliance_analysis": "Detaillierte Datenschutz- und KI-Bewertung in Sie-Form, inkl. konkreter Risiken und Hinweise auf Haftung.",
  "use_case_analysis": "Konkret, wie KI hier sinnvoll eingesetzt werden könnte.",
  "branche_trend": "Kurzer branchenspezifischer Trend.",
  "vision": "Motivierendes, operatives Zukunftsbild für das Unternehmen.",
  "toolstipps": ["maximal 3 spezifische Tools aus folgender Liste, bitte ausgewählt passend: {', '.join(tools)}"],
  "foerdertipps": ["maximal 3 spezifische Programme aus folgender Liste, bitte ausgewählt passend: {', '.join(foerderungen)}"],
  "executive_summary": "1-2 Sätze, was das Unternehmen als Nächstes tun sollte.",
  "risiko_und_haftung": "Klare Einschätzung zu Risiken & Haftungspflichten mit Priorität."
}}

Antwort bitte **ausschließlich als JSON liefern**, keine Einleitung, keine Kommentare.
"""
    return prompt

def analyze_with_gpt(data):
    text_response = ""
    try:
        # GPT-Request
        response = client.chat.completions.create(
            model="gpt-4o",
            temperature=0.2,
            messages=[
                {"role": "user", "content": build_prompt(data)}
            ]
        )
        text_response = response.choices[0].message.content

        # JSON-Teil extrahieren
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
