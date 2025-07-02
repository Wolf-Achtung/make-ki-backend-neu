import json
from openai import OpenAI

client = OpenAI()

with open("tools_und_foerderungen.json") as f:
    db = json.load(f)

# gpt_analyze.py (verbesserter Prompt)

def build_prompt(data):
    prompt = f"""
Sie sind ein zertifizierter KI- und Datenschutz-Consultant. Ihre Aufgabe:
Generieren Sie ausschließlich ein JSON mit exakt den folgenden Feldern:
{{
  "compliance_score": "...",
  "badge_level": "...",
  "ds_gvo_level": "...",
  "ai_act_level": "...",
  "risk_traffic_light": "...",
  "executive_summary": "...",
  "readiness_analysis": "...",
  "compliance_analysis": "...",
  "use_case_analysis": "...",
  "branche_trend": "...",
  "vision": "...",
  "next_steps": ["..."],
  "toolstipps": ["..."],
  "foerdertipps": ["..."],
  "risiko_und_haftung": "...",
  "dan_inspiration": "..."
}}
WICHTIG: Beantworten Sie ausschließlich in JSON ohne Vor- oder Nachtext.
Falls Sie eines der Felder nicht füllen können, setzen Sie es auf "n/a" bzw. [] bei Listen.
Alle Felder müssen IMMER enthalten sein, sonst wiederholen Sie die gesamte Antwort vollständig.

Eingabedaten:
{data}
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

        json_start = text_response.find('{')
        json_end = text_response.rfind('}') + 1
        json_str = text_response[json_start:json_end]

        return json.loads(json_str)

    except Exception as e:
        return {
            "error": f"Fehler beim GPT-Aufruf: {str(e)}",
            "raw": text_response
        }
