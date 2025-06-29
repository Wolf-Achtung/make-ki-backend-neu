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

        prompt = f"""
Du bist ein zertifizierter KI-Manager und Fördermittelberater.
Bitte analysiere die Unternehmensdaten und gib ausschließlich ein JSON zurück, ohne zusätzliche Erläuterungen.

Das JSON muss exakt diese Felder enthalten:
executive_summary, fördertipps, toolkompass, branche_trend, compliance, beratungsempfehlung, vision.

Unternehmensdaten:
- Name: {unternehmen}
- Branche: {branche}
- Bereich: {bereich}
- Ziel: {ziel}
- Eingesetzte Tools: {tools}

Beispiel:
{{
  "executive_summary": "Kurze Zusammenfassung.",
  "fördertipps": "Tipps zu möglichen Förderprogrammen.",
  "toolkompass": "Empfohlene Tools und Technologien.",
  "branche_trend": "Trends in der Branche.",
  "compliance": "Risiken & DSGVO-Status.",
  "beratungsempfehlung": "Nächste Schritte.",
  "vision": "Zukunftsausblick."
}}
"""

        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )

        output_text = response.choices[0].message.content.strip()
        # Nutze eval hier vorsichtig, GPT liefert durch den Prompt aber genau JSON
        result = eval(output_text)
        return result

    except Exception as e:
        raise RuntimeError(f"Fehler bei der Analyse: {e}")
