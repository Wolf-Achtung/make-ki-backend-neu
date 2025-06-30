import os
from openai import OpenAI

client = OpenAI()

async def analyze_with_gpt(data):
    try:
        # JSON-Eingang prüfen
        print("Eingehend:", data)

        # Prompt bauen
        prompt = f"""
Sie sind ein KI-Strategieberater. Bitte analysieren Sie folgendes Unternehmen:
- Unternehmen: {data.get('unternehmen')}
- Name: {data.get('name')}
- Email: {data.get('email')}
- Branche: {data.get('branche')}
- Geplante Maßnahme: {data.get('massnahme')}
- Bereich: {data.get('bereich')}
- Fragen zu Datenschutz & KI-Management:
  1: {data.get('frage1')}
  2: {data.get('frage2')}
  3: {data.get('frage3')}
  4: {data.get('frage4')}
  5: {data.get('frage5')}
  6: {data.get('frage6')}
  7: {data.get('frage7')}
  8: {data.get('frage8')}
  9: {data.get('frage9')}
 10: {data.get('frage10')}

Geben Sie folgendes JSON zurück:
{{
  "readiness_analysis": "...",
  "compliance_analysis": "...",
  "use_case_analysis": "...",
  "branche_trend": "...",
  "vision": "...",
  "toolstipps": ["Tool 1", "Tool 2"],
  "foerdertipps": ["Tipp 1", "Tipp 2"],
  "executive_summary": "...",
  "compliance_score": 6,
  "badge_level": "Silber"
}}
Keine weiteren Kommentare, nur gültiges JSON.
"""

        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )

        response_text = completion.choices[0].message.content
        print("Antwort von GPT:", response_text)

        import json
        parsed = json.loads(response_text)
        return parsed

    except Exception as e:
        print("Fehler:", e)
        return {"error": str(e)}
