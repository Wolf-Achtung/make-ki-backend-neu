import json
from openai import OpenAI

client = OpenAI()

with open("tools_und_foerderungen.json") as f:
    db = json.load(f)

def build_prompt(data):
    prompt = f"""
Sie sind ein TÜV-zertifizierter, strategischer KI- und Datenschutz-Manager mit über 30 Jahren Erfahrung. 
Ihre Aufgabe ist es, für das untenstehende Unternehmen ein äußerst detailliertes Executive-Briefing zu erstellen, das alle Felder vollständig ausfüllt.

Das Unternehmen:
- Name: {data.get('unternehmen')}
- Branche: {data.get('branche')}
- Bereich: {data.get('bereich')}
- PLZ: {data.get('plz')}
- Mitarbeiterzahl: {data.get('mitarbeiterzahl')}
- Geplante Maßnahme: {data.get('massnahme')}
- Aktuelle Herausforderungen: {data.get('herausforderungen')}
- 3-Jahres-Ziele: {data.get('ziele_3jahre')}
- IT-Systeme & Tools: {data.get('it_systeme')}
- Bereits genutzte KI-Tools: {data.get('ki_tools')}
- Zielgruppen: {data.get('zielgruppen')}
- Datenschutzvorfälle/Audits: {data.get('vorfaelle')}
- Automatisierungspotenziale: {data.get('innovation_potentiale')}
- Was bieten sie konkret an: {data.get('produkt_dienstleistung')}
- Moonshot-Idee: {data.get('moonshot')}

Falls einzelne Angaben unvollständig oder nicht vorhanden sind, ergänzen Sie diese bitte durch branchenübliche Annahmen, damit das Briefing in jedem Fall vollständig ist.

Bitte liefern Sie ein valides JSON-Objekt ohne Fließtext davor oder danach, exakt in folgendem Format:

{{
  "compliance_score": Zahl von 0 bis 10,
  "badge_level": "Bronze" | "Silber" | "Gold" | "Platin",
  "ds_gvo_level": Zahl von 0 bis 100,
  "ai_act_level": Zahl von 0 bis 100,
  "risk_traffic_light": "grün" | "gelb" | "rot",
  "executive_summary": "Max. 400 Wörter mit klaren ROI-Hebeln und Top-3-Prioritäten.",
  "readiness_analysis": "Sehr ausführliche Analyse inkl. SWOT-ähnlicher Stärken/Schwächen.",
  "compliance_analysis": "Detaillierte Bewertung inkl. Datenschutz, KI-Governance & Haftung.",
  "use_case_analysis": "Konkrete, kreative Use-Cases, die über Standardlösungen hinausgehen.",
  "branche_trend": "Trends & Benchmarks mit einem Vergleich zum Wettbewerb.",
  "vision": "Inspirierendes, aber realistisch erreichbares Zukunftsbild in 2-3 Jahren.",
  "next_steps": ["Max. 7 direkt umsetzbare Handlungsschritte inkl. Quick Wins."],
  "toolstipps": ["Max. 5 branchenspezifische Tools inkl. kurzer ROI-Begründung."],
  "foerdertipps": ["Max. 5 passende deutsche oder EU-Förderprogramme (ggf. regional zu PLZ {data.get('plz')})"],
  "risiko_und_haftung": "Sehr ausführliche Risikoanalyse inkl. finanzieller Szenarien und Compliance-Vorteilen.",
  "dan_inspiration": "Radikal-disruptive Moonshot-Ideen, provokant aber umsetzbar (DAN-Style)."
}}

Zusätzliche Regeln:
- Füllen Sie **alle Felder zwingend aus**, auch wenn Annahmen erforderlich sind.
- Keine Listen länger als 7 Punkte.
- Verwenden Sie ausschließlich die Sie-Form, professionell und inspirierend.
"""
    return prompt

def analyze_with_gpt(data):
    text_response = ""
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "user", "content": build_prompt(data)}
            ]
        )
        text_response = response.choices[0].message.content

        json_start = text_response.find('{')
        json_end = text_response.rfind('}') + 1
        json_str = text_response[json_start:json_end]

        return json.loads(json_str)

    except Exception as e:
        return {
            "error": f"Fehler beim GPT-Aufruf: {str(e)}",
            "raw": text_response
        }
