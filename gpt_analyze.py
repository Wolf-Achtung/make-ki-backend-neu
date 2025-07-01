import json
from openai import OpenAI

client = OpenAI()

# Lade Tools & Förderungen
with open("tools_und_foerderungen.json") as f:
    db = json.load(f)

def build_prompt(data):
    prompt = f"""
Sie sind ein TÜV-zertifizierter, strategischer KI- und Datenschutz-Manager mit besonderem Fokus auf zukunftsweisende Digitalisierung und Wachstumspotenziale. 
Ihre Aufgabe ist es, für das folgende Unternehmen ein sehr detailliertes, individuelles Executive-Briefing im Umfang von mindestens 3000 Wörtern zu erstellen.

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
- Vermutete Automatisierungspotenziale: {data.get('innovation_potentiale')}
- Moonshot-Idee: {data.get('moonshot')}

Bitte erstellen Sie ein valides JSON-Objekt mit folgendem Aufbau, wobei jede Textsektion mindestens 300-500 Wörter umfassen soll. 
Gehen Sie dabei besonders auf die individuellen Herausforderungen und Ziele des Unternehmens ein und formulieren Sie konkrete Gamechanger-Ansätze. 
Analysieren Sie auch, wie durch innovative KI-Use-Cases und Automatisierung nicht nur Effizienz, sondern auch völlig neue Erlösmodelle entstehen könnten. 
Zeigen Sie Mut zu provokativen Moonshots und DAN-Ansätzen („was wäre möglich, wenn Ressourcen keine Rolle spielen würden“).

{{
  "compliance_score": Zahl von 0 bis 10,
  "badge_level": "Bronze" | "Silber" | "Gold" | "Platin",
  "ds_gvo_level": Zahl von 0 bis 100,
  "ai_act_level": Zahl von 0 bis 100,
  "risk_traffic_light": "grün" | "gelb" | "rot",
  "executive_summary": "Kurzfassung (max. 300 Wörter) mit den wichtigsten Empfehlungen und ROI-Hebel",
  "readiness_analysis": "Sehr ausführliche branchenspezifische Analyse der KI-Readiness und Digitalstrategie inkl. SWOT-Elemente",
  "compliance_analysis": "Detaillierte Datenschutz- & Compliance-Bewertung inkl. individueller Schwachstellen, branchenspezifischer Best Practices und praxisnaher Next Steps",
  "use_case_analysis": "Konkrete, teils unkonventionelle Use Cases, die weit über Standardlösungen hinausgehen und das Unternehmen differenzieren können",
  "branche_trend": "Trends & Benchmarks der Branche inkl. Vergleich mit Marktdurchschnitt, Wettbewerbern und typischen Pain Points",
  "vision": "Ein inspirierendes, aber realistisch erreichbares Zukunftsbild für das Unternehmen in 2-3 Jahren bei optimaler Umsetzung inkl. Umsatz- und Marktpotenzial",
  "next_steps": ["Priorisierte, direkt umsetzbare Handlungsschritte inkl. Quick Wins und mittelfristigen Projekten"],
  "toolstipps": ["Branchenspezifische, teils Nischen-Tools inkl. konkretem Business-Mehrwert und ROI-Argument"],
  "foerdertipps": ["Passende deutsche oder EU-Förderprogramme, bevorzugt regional (passend zur PLZ {data.get('plz')})"],
  "risiko_und_haftung": "Sehr ausführliche Risikoanalyse inkl. Ampel, finanziellen Szenarien und Compliance-Vorteilen",
  "dan_inspiration": "Was wäre möglich, wenn das Unternehmen alle Grenzen sprengen und radikal digitalisieren würde? (DAN-Style, disruptive Ideen, provokant, aber realistisch umsetzbar)"
}}

Hinweise:
- Sprechen Sie das Unternehmen immer in der Sie-Form an, professionell und inspirierend.
- Verwenden Sie ausschließlich ein valides JSON-Objekt ohne Fließtext davor oder danach.
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

        # Robust: extrahiere JSON
        json_start = text_response.find('{')
        json_end = text_response.rfind('}') + 1
        json_str = text_response[json_start:json_end]

        return json.loads(json_str)

    except Exception as e:
        return {
            "error": f"Fehler beim GPT-Aufruf: {str(e)}",
            "raw": text_response
        }
