from openai import OpenAI
import os
import logging

# Logging
logging.basicConfig(level=logging.INFO)

# Initialisiere den OpenAI-Client mit explizitem base_url und API-Key
client = OpenAI(
    base_url="https://api.openai.com/v1",
    api_key=os.getenv("OPENAI_API_KEY")
)

def get_analysis(payload: dict) -> dict:
    """
    Führt eine GPT-Auswertung basierend auf den übergebenen Nutzerdaten durch.
    """
    try:
        user_input = payload.get("antworten", "")
        unternehmen = payload.get("unternehmen", "Ein Unternehmen")
        email = payload.get("email", "keine@email.de")

        system_prompt = (
            f"Du bist ein KI-Compliance-Berater. Analysiere die folgenden Antworten eines Unternehmens "
            f"auf Fragen zur KI-Nutzung. Gib eine kompakte Bewertung, eine Empfehlung sowie einen visionären Ausblick."
        )

        # Logging zur Kontrolle
        logging.info(f"Empfange Nutzerdaten für Analyse von: {unternehmen} ({email})")

        # OpenAI-Call
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ],
            temperature=0.7
        )

        # Extrahiere Antwort
        content = response.choices[0].message.content.strip()
        logging.info("GPT-Antwort erhalten.")

        # Beispielhafte Struktur für PDFMonkey oder Folgeprozesse
        return {
            "score": "✅ Empfehlung",
            "analyse": content,
            "beratungsempfehlung": "Vereinbaren Sie eine individuelle Beratung auf ki-sicherheit.jetzt.",
            "zukunft": "KI wird Ihre Branche fundamental verändern – bleiben Sie vorne dabei.",
            "compliance": "Die EU AI Act-Vorgaben sind relevant – holen Sie sich rechtliche Unterstützung.",
            "branche": payload.get("branche", "unbekannt"),
            "unternehmen": unternehmen,
            "email": email
        }

    except Exception as e:
        logging.error(f"Fehler bei der GPT-Analyse: {e}")
        return {
            "score": "❌ Fehler",
            "analyse": "Die Analyse konnte nicht durchgeführt werden.",
            "error": str(e)
        }
