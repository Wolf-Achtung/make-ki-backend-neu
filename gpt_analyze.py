import os
import json
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def analyze_with_gpt(data):
    try:
        print("==== Eingehende Form-Daten ====")
        print(json.dumps(data, indent=2, ensure_ascii=False))

        # GPT Prompt zusammenbauen
prompt = f"""
Du bist ein deutschsprachiger, hochpräziser KI-Readiness- und Förder-Analyst. 
Analysiere die Lage des Unternehmens auf Basis folgender Daten und liefere NUR ein gültiges JSON ohne Fließtext oder Erklärungen.

Unternehmen: {data.get("unternehmen")}
Name: {data.get("name")}
Email: {data.get("email")}
Branche: {data.get("branche")}
Geplante Maßnahme: {data.get("massnahme")}
Bereich: {data.get("bereich")}
Fragen:
1: {data.get("frage1")}
2: {data.get("frage2")}
3: {data.get("frage3")}
4: {data.get("frage4")}
5: {data.get("frage5")}
6: {data.get("frage6")}
7: {data.get("frage7")}
8: {data.get("frage8")}
9: {data.get("frage9")}
10: {data.get("frage10")}

Gib die Antwort ausschließlich in diesem JSON-Format zurück:

{{
    "compliance_score": int,
    "badge_level": "Bronze|Silber|Gold|Platin",
    "readiness_analysis": "...",
    "compliance_analysis": "...",
    "use_case_analysis": "...",
    "branche_trend": "...",
    "vision": "...",
    "toolstipps": ["...", "..."],
    "foerdertipps": ["...", "..."],
    "executive_summary": "..."
}}
"""


        print("==== Sende Anfrage an GPT ====")
        completion = client.chat.completions.create(
            model="gpt-4o",
            temperature=0.4,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        gpt_content = completion.choices[0].message.content
        print("==== GPT Roh-Antwort ====")
        print(gpt_content)

        try:
            response_data = json.loads(gpt_content)
        except json.JSONDecodeError as e:
            print("==== JSON-Parsing Fehler ====")
            print(str(e))
            # Fallback JSON
            response_data = {
                "compliance_score": 0,
                "badge_level": "Bronze",
                "readiness_analysis": "Keine Daten verfügbar",
                "compliance_analysis": "Keine Daten verfügbar",
                "use_case_analysis": "Keine Daten verfügbar",
                "branche_trend": "Keine Daten verfügbar",
                "vision": "Keine Daten verfügbar",
                "toolstipps": [],
                "foerdertipps": [],
                "executive_summary": "Keine Daten verfügbar"
            }

        print("==== Finale Antwort an Frontend ====")
        print(json.dumps(response_data, indent=2, ensure_ascii=False))

        return response_data

    except Exception as e:
        print("==== Globaler Fehler ====")
        print(str(e))
        return {
            "error": str(e),
            "compliance_score": 0,
            "badge_level": "Bronze",
            "readiness_analysis": "Keine Daten verfügbar",
            "compliance_analysis": "Keine Daten verfügbar",
            "use_case_analysis": "Keine Daten verfügbar",
            "branche_trend": "Keine Daten verfügbar",
            "vision": "Keine Daten verfügbar",
            "toolstipps": [],
            "foerdertipps": [],
            "executive_summary": "Keine Daten verfügbar"
        }
