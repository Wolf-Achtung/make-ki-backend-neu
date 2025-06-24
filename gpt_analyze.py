import os
import openai
import logging
from dotenv import load_dotenv

load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")

logging.basicConfig(level=logging.INFO)

def gpt_analyze(payload: dict) -> dict:
    """
    Führt eine strukturierte GPT-Auswertung durch basierend auf dem Payload.
    Gibt ein valides JSON-Objekt für PDFMonkey zurück.
    """

    # Schritt 1: Validierung / Vorbereitung
    name = payload.get("name", "Unbekannt")
    unternehmen = payload.get("unternehmen", "Nicht angegeben")
    branche = payload.get("branche", "Allgemein")
    ziel = payload.get("ziel", "Wettbewerbsfähigkeit erhöhen")
    tools = payload.get("tools", "Keine Angabe")

    # Schritt 2: Prompt zusammenstellen
    prompt = f"""
    Du bist ein zertifizierter KI-Berater. Analysiere folgende Nutzerdaten und gib eine strukturierte Bewertung im JSON-Format zurück.

    Name: {name}
    Unternehmen: {unternehmen}
    Branche: {branche}
    Ziel mit KI: {ziel}
    Bereits genutzte Tools: {tools}

    Ausgabeformat:
    {{
      "executive_summary": "...",
      "analyse": "...",
      "empfehlung1_titel": "...",
      "empfehlung1_beschreibung": "...",
      "empfehlung1_next_step": "...",
      "empfehlung1_tool": "...",
      "empfehlung2_titel": "...",
      "empfehlung2_beschreibung": "...",
      "empfehlung2_next_step": "...",
      "empfehlung2_tool": "...",
      "empfehlung3_titel": "...",
      "empfehlung3_beschreibung": "...",
      "empfehlung3_next_step": "...",
      "empfehlung3_tool": "...",
      "roadmap_kurzfristig": "...",
      "roadmap_mittelfristig": "...",
      "roadmap_langfristig": "...",
      "ressourcen": "...",
      "zukunft": "...",
      "rueckfrage1": "...",
      "rueckfrage2": "...",
      "rueckfrage3": "...",
      "foerdertipp1_programm": "...",
      "foerdertipp1_zielgruppe": "...",
      "foerdertipp1_nutzen": "...",
      "foerdertipp2_programm": "...",
      "foerdertipp2_zielgruppe": "...",
      "foerdertipp2_nutzen": "...",
      "risikoklasse": "...",
      "risikobegruendung": "...",
      "risikopflicht1": "...",
      "risikopflicht2": "...",
      "tool1_name": "...",
      "tool1_einsatz": "...",
      "tool1_warum": "...",
      "tool2_name": "...",
      "tool2_einsatz": "...",
      "tool2_warum": "...",
      "branchenvergleich": "...",
      "trendreport": "...",
      "vision": "..."
    }}
    """

    try:
        logging.info("GPT-Analyse wird ausgeführt...")

        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Du bist ein KI-Experte mit Fokus auf Beratung von Unternehmen."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5
        )

        text = response.choices[0].message.content.strip()
        logging.info("Antwort erhalten")

        # Versuche, GPT-Antwort als JSON zu interpretieren
        import json
        parsed = json.loads(text)
        return parsed

    except Exception as e:
        logging.error(f"Fehler bei der GPT-Analyse: {e}")
        # Minimal-Fallback
        return {
            "executive_summary": "Die Analyse konnte nicht automatisch erstellt werden.",
            "analyse": "Fehler bei der automatisierten Bewertung.",
            "empfehlung1_titel": "Manuelle Prüfung empfohlen",
            "empfehlung1_beschreibung": "Bitte prüfen Sie Ihre Eingaben.",
            "empfehlung1_next_step": "Individuelle Beratung buchen",
            "empfehlung1_tool": "KI-Sicherheit.jetzt"
        }
