from openai import OpenAI
import os
from dotenv import load_dotenv
import logging

load_dotenv()
client = OpenAI()
logger = logging.getLogger(__name__)

def analyze(data):
    # Prompt bauen
    prompt = f"""
    Bitte analysiere folgende Angaben zu KI-Readiness und Compliance. Gib fundierte, praxisnahe Empfehlungen.
    Daten: {data}
    
    ➡ Bitte berücksichtige:
    - DSGVO- und EU AI Act-Konformität
    - ROI-Potenzial und Fördermöglichkeiten
    - Hinweise speziell für Selbstständige
    - Motivation / Vision (z.B. 'Ihr Unternehmen kann Vorreiter werden...')

    Ergebnis als strukturiertes Briefing auf Deutsch.
    """

    logger.info(f"GPT Prompt:\n{prompt}")

    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )

    result = completion.choices[0].message.content
    logger.info(f"GPT Ergebnis:\n{result}")
    return result
