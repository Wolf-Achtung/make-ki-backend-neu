import os
import json
import openai

openai.api_key = os.getenv("OPENAI_API_KEY")

def get_analysis(data):
    prompt = (
        "Du bist ein KI-Analyst für kleine Unternehmen. "
        "Bitte analysiere folgendes Unternehmen anhand dieser Daten:\n"
        f"Branche: {data.get('branche', 'nicht angegeben')}\n"
        f"Ziel: {data.get('ziel', 'nicht angegeben')}\n"
        f"Tools: {data.get('tools', 'nicht angegeben')}\n"
        f"Status: {data.get('status', 'nicht angegeben')}\n"
        f"Score: {data.get('score', 'nicht angegeben')}\n"
        "Gib eine strukturierte Analyse im JSON-Format zurück, "
        "mit Feldern wie executive_summary, analyse, empfehlung1_titel, "
        "empfehlung1_beschreibung, roadmap_kurzfristig usw."
    )

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Du bist ein hilfreicher KI-Assistent."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7
    )

    reply = response.choices[0].message["content"]
    return json.loads(reply)