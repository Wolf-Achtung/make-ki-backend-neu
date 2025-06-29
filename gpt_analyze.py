from openai import OpenAI
import os
import json
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

def generate_briefing(inputs):
    """
    Inputs ist ein Python-Objekt (dict), z.B.
    {
      "name": "Max Mustermann",
      "branche": "IT",
      ...
    }
    """
    # Simpler Prompt
    prompt = f"""
    Erstelle eine professionelle Bewertung für {inputs.get('name', 'ein Unternehmen')}
    in der Branche {inputs.get('branche', '-')}, basierend auf folgenden Daten:

    {json.dumps(inputs, indent=2)}

    Fokus: DSGVO, EU AI Act, Chancen, Risiken, Handlungsempfehlungen.
    """
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content
