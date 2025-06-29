from openai import OpenAI
import os
from dotenv import load_dotenv
import logging

# ENV Variablen laden
load_dotenv()
client = OpenAI()

# Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ki-check-gpt")

def analyze_with_gpt(data):
    # Dynamischen Prompt bauen
    prompt = f"""
    Du bist ein hochqualifizierter Compliance- und Digitalberater.
    Analysiere dieses Unternehmensprofil umfassend in Bezug auf DSGVO, EU AI Act, ROI und KI-Readiness.

    Unternehmensdaten:
    - Name: {data.get('name')}
    - Email: {data.get('email')}
    - Branche: {data.get('branche')}
    - Selbstständig: {data.get('selbststaendig')}
    - Maßnahme: {data.get('massnahme')}
    - Einsatzbereich: {data.get('bereich')}
    - Ziel: {data.get('ziel')}
    - Compliance-Antworten: {[data.get('frage'+str(i), '') for i in range(1,11)]}

    Erstelle ein strukturiertes Executive Briefing auf Deutsch mit:
    - Executive Summary
    - DSGVO & EU AI Act Risiken
    - Fördermöglichkeiten & ROI
    - Empfehlungen speziell für Selbstständige
    - Motivierende Vision (z.B. 'Ihr Unternehmen kann Vorreiter werden...')
    """

    logger.info("\n--- GPT Prompt ---\n%s\n-------------------", prompt)

    try:
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        result = completion.choices[0].message.content
        logger.info("\n--- GPT Ergebnis ---\n%s\n---------------------", result)
        return result

    except Exception as e:
        logger.error(f"❌ Fehler beim GPT-Aufruf: {e}")
        return "Es gab ein Problem bei der KI-Analyse. Bitte später erneut versuchen."
