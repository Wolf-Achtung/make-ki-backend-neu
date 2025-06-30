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

Datenschutz- und KI-Management-Fragen:
- Frage 1: {data.get('frage1')}
- Frage 2: {data.get('frage2')}
- Frage 3: {data.get('frage3')}
- Frage 4: {data.get('frage4')}
- Frage 5: {data.get('frage5')}
- Frage 6: {data.get('frage6')}
- Frage 7: {data.get('frage7')}
- Frage 8: {data.get('frage8')}
- Frage 9: {data.get('frage9')}
- Frage 10: {data.get('frage10')}

Bitte analysieren Sie diese Daten und geben Sie ausschließlich ein gültiges JSON-Objekt zurück
mit folgendem Aufbau:

{{
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

async def analyze_with_gpt(data):
    try:
        response = await client.chat.completions.acreate(
            model="gpt-4o",
            messages=[
                {"role": "user", "content": build_prompt(data)}
            ]
        )
        text_response = response.choices[0].message.content

        json_start = text_response.find('{')
        json_end = text_response.rfind('}') + 1
        json_str = text_response[json_start:json_end]
        return json.loads(json_str)
    except Exception as e:
        return {"error": str(e), "raw": text_response}
