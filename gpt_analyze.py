import json
from openai import OpenAI

client = OpenAI()

# Lade Tools & Förderungen
with open("tools_und_foerderungen.json") as f:
    db = json.load(f)

def build_prompt(data):
    prompt = f"""
Sie sind ein TÜV-zertifizierter KI- und Datenschutz-Manager für kleine Unternehmen, Selbstständige und Freiberufler in Deutschland. 
Das analysierte Unternehmen heißt {data.get('unternehmen')} und ist in der Branche {data.get('branche')} im Bereich {data.get('bereich')} tätig. 
Es befindet sich an der Postleitzahl {data.get('plz')} und hat {data.get('mitarbeiter')} Mitarbeiter. 
Es handelt sich um ein reales, wachstumsorientiertes Unternehmen, das an nachhaltiger, zukunftsweisender Digitalisierung interessiert ist.

Antworten auf Fragen zur Datenschutz- und KI-Readiness:
1. Haben Sie technische Maßnahmen (Firewall, Verschlüsselung etc.) umgesetzt? {data.get('frage1')}
2. Gibt es regelmäßige Schulungen zu Datenschutz, KI und rechtlichen Vorgaben? {data.get('frage2')}
3. Haben Sie einen Datenschutzbeauftragten benannt? {data.get('frage3')}
4. Führen Sie Risikoanalysen oder Datenschutz-Folgenabschätzungen durch? {data.get('frage4')}
5. Gibt es Prozesse zur Datenlöschung oder Anonymisierung? {data.get('frage5')}
6. Wissen Mitarbeiter, wie bei Datenschutzverletzungen zu handeln ist? {data.get('frage6')}
7. Werden Betroffenenrechte (Auskunft, Löschung) aktiv umgesetzt? {data.get('frage7')}
8. Gibt es eine Dokumentation der Datenverarbeitungsprozesse? {data.get('frage8')}
9. Existieren Meldepflichten und klar geregelte Abläufe bei Datenschutzvorfällen? {data.get('frage9')}
10. Führen Sie regelmäßige interne Audits zu Datenschutz und KI durch? {data.get('frage10')}

Bitte erstellen Sie eine professionelle, deutschsprachige und in der Sie-Form formulierte Auswertung. 
Die Auswertung soll folgende Rubriken enthalten:

{{
  "compliance_score": Zahl von 0 bis 10,
  "badge_level": "Bronze" | "Silber" | "Gold" | "Platin",
  "readiness_analysis": "Kurze branchenspezifische Einschätzung",
  "compliance_analysis": "Detaillierte, praxisnahe Datenschutzbewertung mit klaren Empfehlungen",
  "use_case_analysis": "Konkrete, branchengerechte Vorschläge für KI-Use-Cases",
  "branche_trend": "Aktuelle KI- und Digitaltrends in dieser Branche",
  "vision": "Motivierendes Zukunftsbild, individuell auf das Unternehmen zugeschnitten",
  "next_steps": ["Konkret priorisierte Handlungsschritte (bulletpoints)"],
  "toolstipps": ["Branchenspezifische Tools inkl. Nischenlösungen"],
  "foerdertipps": ["Relevante deutsche oder EU-Förderprogramme"],
  "risiko_und_haftung": "Risiko- und Haftungsanalyse für das Unternehmen",
  "executive_summary": "Zusammenfassung, was das Unternehmen als Nächstes tun sollte"
}}

Vermeiden Sie bitte Formulierungen wie „nicht existentes Unternehmen“, „unternehmenslos“ oder Ähnliches. 
Gehen Sie immer davon aus, dass es sich um ein echtes, ambitioniertes Unternehmen handelt, das Ihr Fachgutachten wünscht. 
Liefern Sie ausschließlich ein gültiges JSON-Objekt im beschriebenen Format.
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
