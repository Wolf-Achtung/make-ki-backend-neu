import json
from openai import OpenAI

client = OpenAI()

# Lade Tools & Förderungen
with open("tools_und_foerderungen.json") as f:
    db = json.load(f)

def build_prompt(data):
    prompt = f"""
Sie sind ein TÜV-zertifizierter KI- und Datenschutz-Manager für kleine Unternehmen, Selbstständige und Freiberufler in Deutschland. 
Sie erstellen auf Basis des folgenden Fragebogens eine hochprofessionelle, deutschsprachige Auswertung in der Sie-Form.

Das Unternehmen:
- Name: {data.get('unternehmen')}
- Branche: {data.get('branche')}
- Bereich: {data.get('bereich')}
- PLZ: {data.get('plz')}
- Mitarbeiterzahl: {data.get('mitarbeiterzahl')}
- Geplante Maßnahme: {data.get('massnahme')}

Antworten zur Datenschutz- und KI-Readiness:
1. Technische Maßnahmen: {data.get('frage1')}
2. Schulungen: {data.get('frage2')}
3. Datenschutzbeauftragter: {data.get('frage3')}
4. Risikoanalysen/DSFA: {data.get('frage4')}
5. Datenlöschung/Anonymisierung: {data.get('frage5')}
6. Awareness Datenschutzverletzungen: {data.get('frage6')}
7. Betroffenenrechte: {data.get('frage7')}
8. Dokumentation: {data.get('frage8')}
9. Meldepflichten: {data.get('frage9')}
10. Interne Audits: {data.get('frage10')}

Bitte erstellen Sie ein JSON-Objekt mit folgendem Aufbau:

{{
  "compliance_score": Zahl von 0 bis 10,
  "badge_level": "Bronze" | "Silber" | "Gold" | "Platin",
  "ds_gvo_level": Zahl von 0 bis 100,
  "ai_act_level": Zahl von 0 bis 100,
  "risk_traffic_light": "grün" | "gelb" | "rot",
  "readiness_analysis": "Kurze branchenspezifische Einschätzung",
  "compliance_analysis": "Detaillierte, praxisnahe Datenschutzbewertung mit klaren Empfehlungen",
  "use_case_analysis": "Konkrete, branchengerechte Vorschläge für KI-Use-Cases",
  "branche_trend": "Aktuelle KI- und Digitaltrends in dieser Branche",
  "vision": "Motivierendes Zukunftsbild, das konkrete Chancen illustriert",
  "next_steps": ["Priorisierte Handlungsschritte inkl. Quick Wins"],
  "toolstipps": ["Branchenspezifische Tools inkl. Nischenlösungen"],
  "foerdertipps": ["Relevante deutsche oder EU-Förderprogramme"],
  "risiko_und_haftung": "Risiko- und Haftungsanalyse inkl. Ampel-Beurteilung",
  "executive_summary": "Management-Zusammenfassung, was als Nächstes zu tun ist"
}}

Hinweise:
- Beziehen Sie bitte typische Datenschutz- und KI-Risiken in der Branche ein.
- Geben Sie immer konkrete Tools und Programme aus Deutschland oder der EU an.
- Vergleichen Sie wo möglich mit dem Branchendurchschnitt (z. B. „12 % unter Standard“).
- Verwenden Sie Defaultwerte, falls Informationen fehlen.
- Verwenden Sie ausschließlich ein valides JSON-Objekt im gewünschten Format – ohne zusätzliche Texte oder Erklärungen davor oder danach.
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
