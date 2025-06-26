import openai
import os
import json

def analyze_payload(payload: dict) -> dict:
    def fallback(key):
        return payload.get(key) or "nicht angegeben"

    prompt = f"""
    Du bist ein zertifizierter KI-Analyst. Analysiere die folgenden Angaben und liefere ein strukturiertes Briefing für ein PDF:

Nutzerdaten:
    Name: {fallback('name')}
    Unternehmen: {fallback('unternehmen')}
    Branche: {fallback('branche')}
    Ziel: {fallback('ziel')}
    Bereich: {fallback('bereich')}
    Tools: {fallback('tools')}
    Know-how: {fallback('knowhow')}
    Prozesse: {fallback('prozesse')}
    Infrastruktur: {fallback('infrastruktur')}
    Strategie: {fallback('strategie')}
    Maßnahmen: {fallback('massnahmen')}
    Verantwortung: {fallback('verantwortung')}
    Datenschutz: {fallback('datenschutz')}
    Förderung: {fallback('foerderung')}
    Herausforderung: {fallback('herausforderung')}

    Gib bitte als JSON mit genau diesen Feldern aus:

    {{
      "executive_summary": "...",
      "fördertipps": "...",
      "toolkompass": "...",
      "branche_trend": "...",
      "compliance": "...",
      "beratungsempfehlung": "...",
      "vision": "..."
    }}

    Vermeide jegliche Erklärtexte oder Zeilen außerhalb des JSON!
    """

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Du bist ein KI-Experte für förderfähige KI-Analysen und Beratung."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        raw = response.choices[0].message.content
        json_start = raw.find("{")
        json_data = raw[json_start:]
        parsed = json.loads(json_data)

        print("✅ GPT-Antwort erfolgreich geparst.")
        return parsed

    except Exception as e:
        print("❌ Fehler bei der GPT-Auswertung oder beim Parsen:", e)
        return {
            "executive_summary": "Fehler beim Analysieren.",
            "fördertipps": "",
            "toolkompass": "",
            "branche_trend": "",
            "compliance": "",
            "beratungsempfehlung": "",
            "vision": ""
        }
