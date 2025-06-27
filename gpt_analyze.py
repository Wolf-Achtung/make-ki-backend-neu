
import openai
import os
from dotenv import load_dotenv

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

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

        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )

        # Extrahiere das JSON aus der Antwort
        output_text = response.choices[0].message.content.strip()
        result = eval(output_text)  # Verwende hier eval bewusst – Alternativen wie `json.loads()` nur bei gültigem JSON
        return result

    except Exception as e:
        raise RuntimeError(f"Fehler bei der Analyse: {e}")
