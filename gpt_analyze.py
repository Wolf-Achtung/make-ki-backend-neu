from openai import OpenAI

client = OpenAI()

import json

async def analyze_with_gpt(data):
    try:
        prompt = f"""
Du bist ein Premium-KI-Berater für Datenschutz, KI-Readiness und Förderung. 
Analysiere bitte die folgenden Unternehmensdaten und erstelle eine individuelle Auswertung. 
Das Ziel ist, Schwachstellen aufzudecken, Compliance & Datenschutz zu bewerten, Fördermöglichkeiten zu identifizieren und konkrete KI-Tools vorzuschlagen.

### Unternehmensdaten:
- Unternehmen: {data.get("unternehmen")}
- Name: {data.get("name")}
- Email: {data.get("email")}
- Branche: {data.get("branche")}
- Geplante Maßnahme: {data.get("massnahme")}
- Bereich: {data.get("bereich")}

### Datenschutz & KI-Management:
- Frage 1: {data.get("frage1")}
- Frage 2: {data.get("frage2")}
- Frage 3: {data.get("frage3")}
- Frage 4: {data.get("frage4")}
- Frage 5: {data.get("frage5")}
- Frage 6: {data.get("frage6")}
- Frage 7: {data.get("frage7")}
- Frage 8: {data.get("frage8")}
- Frage 9: {data.get("frage9")}
- Frage 10: {data.get("frage10")}

### Anforderungen an die Analyse:
1. **Compliance-Analyse:** Beschreibe die Datenschutz- und Compliance-Lage, inkl. Score von 0 bis 10.
2. **Badge-Level:** Gib eine Einstufung in Bronze, Silber oder Gold. Bronze = viele offene Punkte, Silber = mittel, Gold = sehr gut aufgestellt.
3. **Readiness-Analyse:** Wie bereit ist das Unternehmen für KI? Berücksichtige Branche, Maßnahme, Bereich & Antworten.
4. **Use-Case-Analyse:** Schlage konkrete KI-Use-Cases für dieses Unternehmen vor.
5. **Branche Trend:** Beschreibe kurz relevante Trends in dieser Branche.
6. **Vision:** Eine inspirierende kurze Vision für das Unternehmen.
7. **Toolstipps:** Liste 2-4 konkrete Tools, die dem Unternehmen helfen könnten.
8. **Foerdertipps:** Gib konkrete Förderideen oder Programme an.
9. **Executive Summary:** Eine knackige Zusammenfassung für die Geschäftsführung.

### Antwortformat:
Gib deine Antwort bitte in folgendem JSON zurück:
{{
"compliance_score": <int von 0-10>,
"badge_level": "<Bronze|Silber|Gold>",
"readiness_analysis": "...",
"compliance_analysis": "...",
"use_case_analysis": "...",
"branche_trend": "...",
"vision": "...",
"toolstipps": ["Tool1", "Tool2"],
"foerdertipps": ["Förder1", "Förder2"],
"executive_summary": "..."
}}
"""
        completion = await client.chat.completions.acreate(
            model="gpt-4o",
            temperature=0.2,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        text = completion.choices[0].message.content
        # JSON sauber laden
        try:
            result = json.loads(text)
        except Exception as parse_err:
            result = {
                "error": f"Fehler beim JSON parsen: {parse_err}",
                "raw_output": text
            }
        return result

    except Exception as e:
        return {"error": str(e)}
