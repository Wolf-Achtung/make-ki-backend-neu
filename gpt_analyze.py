from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

def analyze_with_gpt(data):
    try:
        unternehmen = data.get("unternehmen", "Ihr Unternehmen")
        branche = data.get("branche", "Allgemein")
        ziel = data.get("ziel", "nicht angegeben")
        tools = data.get("tools", "nicht angegeben")
        bereich = data.get("bereich", "nicht angegeben")

        compliance = []
        for i in range(1,11):
            compliance.append(data.get(f"frage{i}", "Nicht beantwortet"))

        prompt = f"""
Du bist ein zertifizierter KI-Manager für DSGVO & EU-AI-Act. 
Analysiere folgende Angaben eines Unternehmens und erstelle:

1. Compliance-Score (Anzahl 'Ja' bei den Fragen)
2. Badge-Level: 
   - Gold bei 8-10 'Ja'
   - Silber bei 5-7 'Ja'
   - Starter unter 5 'Ja'
3. Danach die Rubriken:
- executive_summary
- fördertipps
- toolkompass
- branche_trend
- compliance
- beratungsempfehlung
- vision

Daten:
- Unternehmen: {unternehmen}
- Branche: {branche}
- Bereich: {bereich}
- Ziel: {ziel}
- Tools: {tools}
- Compliance-Fragen: {compliance}

Antworte strikt als JSON:
{{
"score": ...,
"badge": "...",
"executive_summary": "...",
"fördertipps": "...",
"toolkompass": "...",
"branche_trend": "...",
"compliance": "...",
"beratungsempfehlung": "...",
"vision": "..."
}}
"""

        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )

        output_text = response.choices[0].message.content.strip()
        result = eval(output_text)
        return result

    except Exception as e:
        raise RuntimeError(f"Fehler bei der Analyse: {e}")
