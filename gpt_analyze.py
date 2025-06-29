from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

def generate_briefing(data):
    prompt = f"""
    Erstelle eine Executive-Analyse basierend auf folgenden Angaben:
    Branche: {data.get('branche')}
    Selbstständig: {data.get('selbststaendig')}
    Maßnahme: {data.get('massnahme')}
    Bereich: {data.get('bereich')}
    Ziel: {data.get('ziel')}
    DSGVO-Check: {data.get('ds_gvo')}
    ...

    Bitte antworte detailliert mit ROI-Hinweisen, Förderchancen und Visionen.
    """
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content