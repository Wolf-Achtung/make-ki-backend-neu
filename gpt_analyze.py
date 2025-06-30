from openai import OpenAI
import json
import re
import logging

client = OpenAI()

async def analyze_with_gpt(data):
    try:
        prompt = f"""
Sie sind ein KI- und Förderberater für KMU in Deutschland. Analysieren Sie bitte folgende Unternehmensdaten und geben Sie Empfehlungen in einer für kleine Unternehmen verständlichen Sprache (Sie-Form).

Unternehmen: {data.get('unternehmen')}
Name: {data.get('name')}
E-Mail: {data.get('email')}
Branche: {data.get('branche')}
Geplante Maßnahme: {data.get('massnahme')}
Bereich: {data.get('bereich')}

Fragen zum Datenschutz & KI-Management:
1. Haben Sie technische Maßnahmen getroffen, z. B. Verschlüsselung, Firewalls oder Zugriffskontrollen? Antwort: {data.get('frage1')}
2. Gibt es Schulungen oder Informationen für Mitarbeiter zu Datenschutz, KI oder rechtlichen Anforderungen? Antwort: {data.get('frage2')}
3. Haben Sie einen Datenschutzbeauftragten oder eine verantwortliche Person benannt? Antwort: {data.get('frage3')}
4. Haben Sie Risiken für den Datenschutz dokumentiert (z. B. Datenschutz-Folgenabschätzung)? Antwort: {data.get('frage4')}
5. Gibt es feste Regeln zur Löschung oder Anonymisierung personenbezogener Daten? Antwort: {data.get('frage5')}
6. Wissen Ihre Mitarbeiter, was bei einer Datenschutzverletzung zu tun ist? Antwort: {data.get('frage6')}
7. Achten Sie darauf, dass Personen ihre Rechte (Auskunft, Löschung, Berichtigung) wahrnehmen können? Antwort: {data.get('frage7')}
8. Haben Sie Prozesse zur regelmäßigen Löschung oder Anonymisierung nicht mehr benötigter Daten? Antwort: {data.get('frage8')}
9. Gibt es eine Meldepflicht und klare Abläufe für Datenschutzvorfälle? Antwort: {data.get('frage9')}
10. Führen Sie regelmäßige Überprüfungen oder Audits durch, um sicherzustellen, dass Ihr Unternehmen datenschutzkonform bleibt? Antwort: {data.get('frage10')}

Bitte antworten Sie ausschließlich mit einem validen JSON-Objekt (ohne ```json oder ähnliches), das folgende Felder enthält:

{
  "compliance_score": <0-10>,
  "badge_level": "<Bronze|Silber|Gold|Platin>",
  "readiness_analysis": "<Einschätzung zur generellen KI-Readiness>",
  "compliance_analysis": "<Datenschutz- und Compliance-Analyse>",
  "use_case_analysis": "<Empfehlung für konkrete KI-Use-Cases>",
  "branche_trend": "<Branchentrends>",
  "vision": "<Vision für das Unternehmen>",
  "toolstipps": ["<Tool1>", "<Tool2>"],
  "foerdertipps": ["<Förderprogramm1>", "<Förderprogramm2>"],
  "executive_summary": "<Kurze Zusammenfassung für Entscheider>"
}
"""

        completion = client.chat.completions.create(
            model="gpt-4o",
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = completion.choices[0].message.content

        # Automatischer JSON-Extractor ohne Markdown
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            extracted_json = json_match.group(0)
            result = json.loads(extracted_json)
        else:
            result = {"error": "Kein gültiges JSON gefunden", "debug_text": response_text}

        return result

    except Exception as e:
        logging.exception("Fehler bei GPT-Analyse")
        return {"error": str(e)}
