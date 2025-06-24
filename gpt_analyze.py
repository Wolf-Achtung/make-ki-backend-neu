from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_analysis(data: dict) -> dict:
    # Eingabe aggregieren
    input_string = "\n".join(
        f"{key.capitalize()}: {value}" for key, value in data.items() if value
    )

    # Prompt
    prompt = f"""
Erstelle eine strukturierte Analyse für folgende Nutzereingabe:

{input_string}

Strukturiere die Analyse in folgenden Feldern (im JSON-Format):

- executive_summary
- score
- empfehlungen
- risiken
- branche_vergleich
- visionaerer_blick
- trendreport
- compliance
- beratungsempfehlung
- foerdertipps
- toolkompass

Antworte ausschließlich im JSON-Format ohne Kommentare oder weitere Einleitung.
"""

    # GPT-Request
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )

    # Rückgabe
    reply = response.choices[0].message.content
    return {"gpt_analysis": reply}
