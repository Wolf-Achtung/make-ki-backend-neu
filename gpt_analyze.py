import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

def analyze_with_gpt(data):
    prompt = f"""
Du bist ein KI-Strategie- und Förderexperte für kleine Unternehmen, Selbstständige und Freiberufler. 
Analysiere bitte die folgende Situation, beantworte alle Punkte ausführlich in professionellem Deutsch (Sie-Form). 
Formuliere so, dass auch KI-Neulinge es verstehen.

### Unternehmensdaten
- Name: {data['unternehmen']}
- Ansprechpartner: {data['name']}
- E-Mail: {data['email']}
- Branche: {data['branche']}
- Geplante Maßnahme: {data['massnahme']}
- Bereich: {data['bereich']}
- Ziel: {data['ziel']}

### Compliance-Check
- Frage1: {data['frage1']}
- Frage2: {data['frage2']}
- Frage3: {data['frage3']}
- Frage4: {data['frage4']}
- Frage5: {data['frage5']}
- Frage6: {data['frage6']}
- Frage7: {data['frage7']}
- Frage8: {data['frage8']}
- Frage9: {data['frage9']}
- Frage10: {data['frage10']}

### Deine Aufgabe
- Erstelle eine READINESS-ANALYSE: Wie bereit ist das Unternehmen für KI, mit Blick auf Branche, Maßnahme und Ziele?
- Erstelle eine COMPLIANCE-ANALYSE: Was läuft gut, was muss verbessert werden? Bewerte mit einem Score von 1-10.
- Erstelle einen USE CASE-ANALYSE-Block: Wo genau kann KI hier helfen, ganz konkret?
- Gib einen BRANCHENTREND: Was ist aktuell in dieser Branche in Bezug auf KI relevant?
- Gib eine inspirierende VISION.
- Erstelle einen EXECUTIVE SUMMARY: Kurz, prägnant, auf Management-Level.

### Fördertipps
- Suche 3 konkrete Förderprogramme (möglichst DE/EU), mit Link & 1 Satz Erklärung, die besonders gut zu diesem Vorhaben passen.

### Toolkompass
- Gib 3 konkrete Tools an (Name, Hersteller, Nutzen), die sofort ausprobiert werden können.

### Badge
- Vergib einen Badge-Level (Bronze/Silber/Gold) basierend auf dem Compliance-Score.
- Gib zusätzlich eine kurze badge_info: Warum dieser Level?
- Generiere optional einen HTML-Embed-Code für ein kleines Badge-Widget (div mit class="ki-badge bronze/silber/gold").

### JSON-Format
Bitte liefere ausschließlich folgendes JSON zurück (keine Prosa, keine Kommentare):

{{
"readiness_analysis": "...",
"compliance_analysis": "...",
"compliance_score": 7,
"badge_level": "Silber",
"badge_info": "...",
"badge_code": "<div class='ki-badge silber'>KI-Readiness: Silber</div>",
"use_case_analysis": "...",
"branche_trend": "...",
"vision": "...",
"executive_summary": "...",
"foerdertipps": [
{{"programm":"Digital Jetzt","link":"https://...","kurzbeschreibung":"..."}},
{{"programm":"go-digital","link":"https://...","kurzbeschreibung":"..."}},
{{"programm":"EU KI-Innovationsfonds","link":"https://...","kurzbeschreibung":"..."}}
],
"toolkompass": [
{{"name":"HubSpot AI","hersteller":"HubSpot","einsatz":"Kundenkommunikation automatisieren"}},
{{"name":"Dialogflow","hersteller":"Google","einsatz":"Chatbots erstellen"}},
{{"name":"Notion AI","hersteller":"Notion","einsatz":"Wissensdatenbanken & Content"}}
]
}}
"""
    response = client.chat.completions.create(
        model="gpt-4",
        temperature=0.5,
        messages=[{"role": "user", "content": prompt}]
    )
    output_text = response.choices[0].message.content

    try:
        # sicherer JSON-Parse, weil GPT validiert JSON liefert
        import json
        result = json.loads(output_text)
    except Exception as e:
        # Notfalls Dummy mit Hinweis
        result = {
            "error": f"Parsing error: {e}",
            "fallback_output": output_text
        }
    return result
