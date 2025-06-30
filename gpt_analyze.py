import json
from openai import OpenAI

client = OpenAI()

def load_tools_and_grants():
    with open("tools_und_foerderungen.json", "r", encoding="utf-8") as f:
        return json.load(f)

def build_prompt(data, context):
    return f"""
Sie sind ein TÜV-zertifizierter deutscher KI- und Datenschutzberater.
Ihre Aufgabe ist es, kleine Unternehmen, Selbstständige und Freiberufler professionell, rechtskonform und inspirierend zu beraten.

Unternehmensdaten:
- Unternehmen: {data.get('unternehmen')}
- Ansprechpartner: {data.get('name')}
- E-Mail: {data.get('email')}
- Branche: {data.get('branche')}
- Geplante Maßnahme: {data.get('massnahme')}
- Bereich: {data.get('bereich')}
- Standort (PLZ): {data.get('plz')}

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

Verfügbare interne Tools und Förderprogramme:
{json.dumps(context, ensure_ascii=False, indent=2)}

Bitte analysieren Sie diese Daten und liefern Sie ausschließlich ein gültiges JSON mit folgendem Aufbau, auf Deutsch in der Sie-Form, mit klaren priorisierten Handlungsanweisungen und Roadmap:

{{
  "frage_audit": {{
    "frage1": "...",
    "frage2": "...",
    "...": "..."
  }},
  "compliance_score": Zahl von 0 bis 10,
  "badge_level": "Bronze | Silber | Gold | Platin",
  "readiness_analysis": "Branchenspezifische Einschätzung",
  "compliance_analysis": "Detaillierte Datenschutz- und KI-Bewertung mit konkreten Handlungsempfehlungen",
  "use_case_analysis": "Empfehlung, wie Sie KI sinnvoll einsetzen können.",
  "branche_trend": "Trendtext für Ihre Branche",
  "vision": "Operative, inspirierende Vision inkl. Bulletpoints für nächste Schritte (1-3, 4-12, 12-24 Monate) und wichtige EU-Termine.",
  "quick_wins": ["Quick Win 1", "Quick Win 2"],
  "toolstipps": ["Tool inkl. Link", "..."],
  "foerdertipps": ["Förderprogramm inkl. Link", "..."],
  "executive_summary": "Was Ihr Unternehmen jetzt tun sollte, inkl. Hinweis auf TÜV-zertifiziertes KI-Management bei Wolf Hohl (foerderung@ki-sicherheit.jetzt)"
}}
"""

    return prompt

def analyze_with_gpt(data):
    text_response = ""
    try:
        context = load_tools_and_grants()

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "user", "content": build_prompt(data, context)}
            ]
        )
        text_response = response.choices[0].message.content

        # JSON extrahieren
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
