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
Sie sind ein zertifizierter KI-Manager und beraten kleine Unternehmen im deutschsprachigen Raum.
Analysieren Sie die folgenden Angaben eines Unternehmens und geben Sie Empfehlungen in folgenden Rubriken ab:
1. executive_summary
2. fördertipps
3. toolkompass
4. branche_trend
5. compliance
6. beratungsempfehlung
7. vision

Unternehmensangaben:
- Name: {unternehmen}
- Branche: {branche}
- Bereich: {bereich}
- Ziel: {ziel}
- Eingesetzte Tools: {tools}

Bitte antworten Sie im folgenden JSON-Format:

{{
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
            temperature=0.7
        )

        output_text = response.choices[0].message.content.strip()
        result = eval(output_text)  # Alternativ json.loads() wenn GPT sauber JSON liefert
        return result

    except Exception as e:
        raise RuntimeError(f"Fehler bei der Analyse: {e}")
