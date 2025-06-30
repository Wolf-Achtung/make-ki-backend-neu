import os
import json
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def analyze_with_gpt(data):
    prompt = f"""
Sie sind ein zertifizierter KI-Experte für Datenschutz, Compliance und Förderberatung.
Analysieren Sie die Angaben dieses Unternehmens und erstellen Sie ein professionelles Executive Briefing auf Deutsch in der Sie-Form.
Unternehmensdaten:
- Unternehmen: {data['unternehmen']}
- Name: {data['name']}
- Email: {data['email']}
- Branche: {data['branche']}
- Geplante Maßnahme: {data['massnahme']}
- Bereich: {data['bereich']}

Fragen zum Datenschutz & KI-Management:
1. {data['frage1']}
2. {data['frage2']}
3. {data['frage3']}
4. {data['frage4']}
5. {data['frage5']}
6. {data['frage6']}
7. {data['frage7']}
8. {data['frage8']}
9. {data['frage9']}
10. {data['frage10']}

Geben Sie folgendes JSON zurück:
{{
"readiness_analysis": "...",
"compliance_analysis": "...",
"use_case_analysis": "...",
"branche_trend": "...",
"vision": "...",
"toolstipps": ["...", "..."],
"foerdertipps": ["...", "..."],
"executive_summary": "...",
"compliance_score": 0,
"badge_level": "Bronze"
}}
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.4,
        messages=[{"role": "user", "content": prompt}]
    )
    output_text = response.choices[0].message.content
    try:
        result = json.loads(output_text)
    except json.JSONDecodeError:
        result = {
            "readiness_analysis": "Keine Daten verfügbar",
            "compliance_analysis": "Keine Daten verfügbar",
            "use_case_analysis": "Keine Daten verfügbar",
            "branche_trend": "Keine Daten verfügbar",
            "vision": "Keine Daten verfügbar",
            "toolstipps": [],
            "foerdertipps": [],
            "executive_summary": "Keine Daten verfügbar",
            "compliance_score": 0,
            "badge_level": "Bronze"
        }
    return result
