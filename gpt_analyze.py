from openai import OpenAI
import os
from dotenv import load_dotenv
import json

load_dotenv()
client = OpenAI()

def generate_briefing(inputs: dict) -> str:
    """
    Erzeugt das Executive Briefing basierend auf den Eingaben
    """
    prompt = f"""
    Erstelle ein Executive Briefing für:
    {json.dumps(inputs, indent=2)}

    Fokus: DSGVO, EU AI Act Risiken & Chancen, Empfehlungen für KMU & Selbstständige,
    ROI-Potenzial, Vision: Wie kann das Unternehmen KI-Vorreiter werden?
    """
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    return completion.choices[0].message.content
