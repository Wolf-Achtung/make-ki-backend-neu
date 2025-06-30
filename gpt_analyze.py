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
- Erstelle eine READINESS-ANALYSE...
- Erstelle eine COMPLIANCE-ANALYSE...
- Erstelle einen USE CASE-ANALYSE-Block...
- Gib einen BRANCHENTREND...
- Gib eine inspirierende VISION...
- Erstelle einen EXECUTIVE SUMMARY...

### Foerdertipps
- Suche 3 konkrete Förderprogramme...

### Toolstipps
- Gib 3 konkrete Tools an...

### Badge
- Vergib einen Badge-Level (Bronze/Silber/Gold)...

### JSON-Format
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
"foerdertipps": ["..."],
"toolstipps": ["..."]
}}
"""
    response = client.chat.completions.create(
        model="gpt-4",
        temperature=0.5,
        messages=[{"role": "user", "content": prompt}]
    )
    output_text = response.choices[0].message.content
    try:
        import json
        result = json.loads(output_text)
    except Exception as e:
        result = {"error": f"Parsing error: {e}", "fallback_output": output_text}
    return result
