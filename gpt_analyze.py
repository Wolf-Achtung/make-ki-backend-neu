from openai import OpenAI
import json

client = OpenAI()

async def analyze_with_gpt(data):
    try:
        prompt = f"""
Sie sind ein KI-Strategieberater für kleine Unternehmen. Analysieren Sie die Angaben des Unternehmens {data['unternehmen']} (Branche: {data['branche']}, Bereich: {data['bereich']}, geplante Maßnahme: {data['massnahme']}) und berücksichtigen Sie dabei:

- Frage 1: Haben Sie technische Maßnahmen getroffen, z. B. Verschlüsselung, Firewalls oder Zugriffskontrollen, um Daten zu schützen? Antwort: {data['frage1']}
- Frage 2: Gibt es in Ihrem Unternehmen schon Schulungen oder Informationen für Mitarbeiter zum Thema Datenschutz, Künstliche Intelligenz oder rechtliche Anforderungen? Antwort: {data['frage2']}
- Frage 3: Haben Sie einen Datenschutzbeauftragten oder eine verantwortliche Person dafür benannt? Antwort: {data['frage3']}
- Frage 4: Haben Sie schon einmal geprüft oder dokumentiert, welche Risiken für den Datenschutz entstehen könnten (z. B. durch eine Datenschutz-Folgenabschätzung)? Antwort: {data['frage4']}
- Frage 5: Gibt es feste Regeln, wann und wie personenbezogene Daten gelöscht oder anonymisiert werden? Antwort: {data['frage5']}
- Frage 6: Wissen Ihre Mitarbeiter, was zu tun ist, wenn eine Datenschutzverletzung passiert (z. B. durch Hackerangriff)? Antwort: {data['frage6']}
- Frage 7: Achten Sie darauf, dass Personen, deren Daten Sie speichern, ihre Rechte wahrnehmen können (z. B. Auskunft, Löschung, Berichtigung)? Antwort: {data['frage7']}
- Frage 8: Haben Sie Prozesse, um die regelmäßige Löschung oder Anonymisierung von Daten sicherzustellen, die nicht mehr benötigt werden? Antwort: {data['frage8']}
- Frage 9: Gibt es eine Meldepflicht und einen klaren Ablauf für Datenschutzvorfälle in Ihrem Unternehmen? Antwort: {data['frage9']}
- Frage 10: Führen Sie regelmäßige Überprüfungen oder Audits durch, um sicherzustellen, dass Ihr Unternehmen datenschutzkonform bleibt? Antwort: {data['frage10']}

Erstellen Sie daraus ein detailliertes JSON mit:
{{
  "compliance_score": <0-10>,
  "badge_level": "<Bronze|Silber|Gold>",
  "readiness_analysis": "<Ihre Einschätzung zur generellen KI-Readiness>",
  "compliance_analysis": "<Datenschutzanalyse>",
  "use_case_analysis": "<Empfehlung für konkrete Anwendungsfälle>",
  "branche_trend": "<Branchentrend>",
  "vision": "<Zukunftsperspektive für das Unternehmen>",
  "toolstipps": ["<Tool 1>", "<Tool 2>"],
  "foerdertipps": ["<Förderung 1>", "<Förderung 2>"],
  "executive_summary": "<Kurze Zusammenfassung für Entscheider>"
}}

Antwort nur als JSON, ohne weiteren Text.
"""
        
        completion = client.chat.completions.create(
            model="gpt-4o",
            temperature=0.5,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = completion.choices[0].message.content

        try:
            result = json.loads(response_text)
        except json.JSONDecodeError:
            result = {"error": "Konnte JSON nicht parsen", "raw": response_text}

        return result
    
    except Exception as e:
        return {"error": str(e)}
