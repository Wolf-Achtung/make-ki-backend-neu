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
    Analysiere das folgende Unternehmensprofil tiefgehend im Hinblick auf:

    1️⃣ DSGVO & Datenschutz (Art. 30, Art. 35) – z.B. ob ein Verzeichnis oder DPIA nötig ist.
    2️⃣ EU AI Act: Klassifiziere das Risiko (Hochrisiko? Minimal?) und was das bedeutet.
    3️⃣ Fördermöglichkeiten: Bundes-/EU-Programme, steuerliche Forschungsförderung.
    4️⃣ Konkrete Tools & Methoden, die sofort helfen (inkl. Begründung).
    5️⃣ Eine Roadmap (30 Tage / 90 Tage / 365 Tage), priorisiert.
    6️⃣ ROI & Wettbewerbsvorteile: Was spart / gewinnt das Unternehmen?
    7️⃣ Branchentrends und Benchmarks.
    8️⃣ Eine Vision (DAN-Style), was das Unternehmen erreichen kann.

    Nutze auch die Info, ob der Kunde selbstständig tätig ist: "{data.get('selbststaendig', '')}".

    Daten des Unternehmens:
    Name: {data.get('name', '')}
    Email: {data.get('email', '')}
    Branche: {data.get('branche', '')}
    Geplante Maßnahme: {data.get('massnahme', '')}
    Einsatzbereich: {data.get('bereich', '')}
    Ziel mit KI: {data.get('ziel', '')}
    Compliance-Antworten: {[data.get('frage'+str(i), '') for i in range(1,11)]}

    Antworte strukturiert mit folgenden Abschnitten:
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
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        return response.choices[0].message.content

    except Exception as e:
        logging.error(f"Fehler bei der Analyse: {e}")
        raise RuntimeError(f"Fehler bei der Analyse: {e}")
