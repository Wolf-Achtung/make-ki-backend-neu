from openai import OpenAI
import os
from dotenv import load_dotenv
import logging

load_dotenv()
client = OpenAI()

logging.basicConfig(level=logging.INFO)

def analyze_with_gpt(data):
    prompt = f"""
    Du bist ein hochqualifizierter Compliance- & Digitalberater für KI-Projekte.
    Analysiere das folgende Unternehmensprofil tiefgehend im Hinblick auf DSGVO, EU AI Act, ROI, Roadmap und Vision.

    Name: {data.get('name', '')}
    Email: {data.get('email', '')}
    Branche: {data.get('branche', '')}
    Selbstständig: {data.get('selbststaendig', '')}
    Geplante Maßnahme: {data.get('massnahme', '')}
    Einsatzbereich: {data.get('bereich', '')}
    Ziel: {data.get('ziel', '')}
    Compliance-Antworten: {[data.get('frage'+str(i), '') for i in range(1,11)]}

    Gib mir eine klare Struktur:
    - Executive Summary
    - DSGVO & EU AI Act Risiken
    - Fördertipps
    - Tool-Kompass
    - Compliance-Ampel
    - Roadmap
    - ROI & Wettbewerb
    - Branchentrends
    - Vision (DAN-Style)
    """

    try:
        logging.info("🚀 Starte GPT-Analyse...")
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Du bist ein KI- und Compliance-Experte."},
                {"role": "user", "content": prompt}
            ]
        )

        text = response.choices[0].message.content
        logging.info(f"📝 GPT-Antwort:\n{text[:300]}...")  # nur die ersten 300 Zeichen anzeigen
        return text

    except Exception as e:
        logging.error(f"❌ Fehler bei der Analyse: {e}")
        raise RuntimeError(f"Fehler bei der Analyse: {e}")
