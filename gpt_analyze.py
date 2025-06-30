import json
import os
from openai import OpenAI

client = OpenAI()

# robustes Directory ermitteln
dir_path = os.path.dirname(os.path.realpath(__file__))

# JSON sicher laden
with open(os.path.join(dir_path, "tools_und_foerderungen.json"), "r", encoding="utf-8") as f:
    db = json.load(f)

def build_prompt(data, db):
    prompt = f"""
Sie sind ein TÜV-zertifizierter KI-Manager & Datenschutz-Experte in Deutschland.
Analysieren Sie folgendes Unternehmen basierend auf diesen Angaben:

Unternehmen: {data.get('unternehmen')}
Name: {data.get('name')}
Email: {data.get('email')}
PLZ: {data.get('plz')}
Branche: {data.get('branche')}
Bereich: {data.get('bereich')}
Mitarbeiterzahl: {data.get('mitarbeiter')}

Antworten auf Fragen zur Datenschutz- und KI-Readiness:
1. Technische Maßnahmen umgesetzt? {data.get('frage1')}
2. Schulungen zu Datenschutz, KI & rechtlichen Vorgaben? {data.get('frage2')}
3. Datenschutzbeauftragten benannt? {data.get('frage3')}
4. Risikoanalysen / Folgenabschätzungen? {data.get('frage4')}
5. Prozesse zur Datenlöschung / Anonymisierung? {data.get('frage5')}
6. Wissen Mitarbeiter, wie sie bei Datenschutzverletzungen handeln? {data.get('frage6')}
7. Werden Betroffenenrechte aktiv umgesetzt? {data.get('frage7')}
8. Dokumentation der Datenverarbeitung? {data.get('frage8')}
9. Meldepflichten & Abläufe bei Datenschutzvorfällen? {data.get('frage9')}
10. Regelmäßige Audits zu Datenschutz & KI? {data.get('frage10')}

Bitte geben Sie eine extrem präzise, praxisnahe Auswertung nur als JSON zurück:

{{
"compliance_score": ganze Zahl von 0 bis 10,
"badge_level": "Bronze", "Silber", "Gold", "Platin",
"readiness_analysis": "Branchenspezifische Chancen & Schwächen",
"compliance_analysis": "Klare Bewertung mit Handlungsempfehlungen",
"use_case_analysis": "Innovative KI-Use-Cases für diese Branche & Größe",
"branche_trend": "Trends & Entwicklungen speziell für diese Branche",
"vision": "Inspirierende, unternehmensindividuelle Zukunftsvision",
"next_steps": ["Sofort:...", "3 Monate:...", "12 Monate:..."],
"toolstipps": ["{db['tools'][0]}", "{db['tools'][1]}", "{db['tools'][2]}"],
"foerdertipps": ["{db['foerderungen'][0]}", "{db['foerderungen'][1]}"],
"risiko_und_haftung": "Klare Risikobewertung & Haftungsgefahr",
"executive_summary": "Kurz & knackig, was das Unternehmen jetzt tun sollte"
}}

Nutzen Sie bitte die Sie-Form, schreiben Sie professionell und vermeiden Sie Wiederholungen.
"""
    return prompt


def analyze_with_gpt(data):
    text_response = ""
    try:
        # GPT-Request
        response = client.chat.completions.create(
            model="gpt-4o",
            temperature=0.2,
            messages=[
                {"role": "user", "content": build_prompt(data)}
            ]
        )
        text_response = response.choices[0].message.content

        # JSON-Teil extrahieren
        json_start = text_response.find('{')
        json_end = text_response.rfind('}') + 1
        json_str = text_response[json_start:json_end]

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return {
                "error": "Konnte JSON nicht parsen",
                "raw": text_response
            }

    except Exception as e:
        return {
            "error": f"Fehler beim GPT-Aufruf: {str(e)}",
            "raw": text_response
        }
