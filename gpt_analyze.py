import json
from openai import OpenAI

client = OpenAI()

# Lade Tools & Förderungen
with open("tools_und_foerderungen.json") as f:
    db = json.load(f)

def build_prompt(data):
    prompt = f"""
Sie sind ein TÜV-zertifizierter KI-Manager & Datenschutz-Experte in Deutschland.

Analysieren Sie das folgende Unternehmen sehr detailliert und individuell.
Generieren Sie ein inspirierendes, praxisnahes Executive-Briefing inkl. klarer Risiken.

Unternehmensdaten:
- Unternehmen: {data.get('unternehmen')}
- Name: {data.get('name')}
- Email: {data.get('email')}
- PLZ: {data.get('plz')}
- Branche: {data.get('branche')}
- Bereich: {data.get('bereich')}
- Mitarbeiter: {data.get('mitarbeiter')}

Antworten auf Fragen zur Datenschutz- & KI-Readiness:
1. Technische Maßnahmen? {data.get('frage1')}
2. Schulungen zu Datenschutz, KI & rechtlichen Vorgaben? {data.get('frage2')}
3. Datenschutzbeauftragter benannt? {data.get('frage3')}
4. Risikoanalysen / Folgenabschätzungen? {data.get('frage4')}
5. Prozesse zur Datenlöschung oder Anonymisierung? {data.get('frage5')}
6. Wissen Mitarbeiter, wie bei Datenschutzverletzungen zu handeln ist? {data.get('frage6')}
7. Betroffenenrechte aktiv umgesetzt? {data.get('frage7')}
8. Dokumentation der Datenverarbeitungsprozesse? {data.get('frage8')}
9. Meldepflichten & Abläufe bei Datenschutzvorfällen? {data.get('frage9')}
10. Regelmäßige interne Audits? {data.get('frage10')}

Berücksichtigen Sie außerdem folgende Förderprogramme & Tools aus einer aktuellen Marktrecherche:

TOOLS: {db['tools']}
FÖRDERUNGEN: {db['foerderungen']}

Erstellen Sie ein reines JSON-Objekt (ohne Kommentartext, ohne Einleitung) mit diesem Aufbau:

{{
"compliance_score": ganze Zahl von 0 bis 10,
"badge_level": "Bronze", "Silber", "Gold" oder "Platin",
"readiness_analysis": "Branchenspezifische Chancen & Schwächen",
"compliance_analysis": "Klare Bewertung mit Handlungsempfehlungen",
"use_case_analysis": "Innovative KI-Use-Cases speziell für diese Branche & Größe",
"branche_trend": "Trends & Entwicklungen dieser Branche",
"vision": "Inspirierende, unternehmensindividuelle Zukunftsvision",
"next_steps": ["Sofort: ...", "3 Monate: ...", "12 Monate: ..."],
"toolstipps": ["konkretes Tool 1", "konkretes Tool 2", "konkretes Tool 3"],
"foerdertipps": ["konkretes Förderprogramm 1", "konkretes Förderprogramm 2"],
"risiko_und_haftung": "Klare Risikobewertung & Haftungsgefahr",
"executive_summary": "Kurz, was das Unternehmen jetzt tun sollte"
}}

Sprechen Sie das Unternehmen konsequent in der **Sie-Form** an, verwenden Sie professionelles, seriöses Deutsch. 
Machen Sie keine Links klickbar. 
Seien Sie kreativ, praxisorientiert, liefern Sie einen Wow-Effekt.
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
