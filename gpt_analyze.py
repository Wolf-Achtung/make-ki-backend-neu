from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

def analyze_with_gpt(data):
    try:
        prompt = f"""
Sie sind ein zertifizierter KI-Manager und Fördermittelberater 
und beraten Geschäftsführer von kleinen Unternehmen oder Selbstständige, 
die wenig technisches Vorwissen haben und sich für den professionellen KI-Einsatz interessieren.

Bitte analysieren Sie die folgenden Unternehmensangaben. 
Erstellen Sie ausschließlich ein JSON ohne Einleitung oder Abschluss, mit exakt diesen Feldern:

- readiness_analysis: Einschätzung der allgemeinen KI-Readiness des Unternehmens in maximal 3 Sätzen. Danach bitte eine kurze 3-Punkte-Checkliste mit den nächsten konkreten Schritten.
- compliance_analysis: Eine klare Compliance-Checkliste, die auf den Antworten zu frage1 bis frage10 basiert. Bitte spezifisch auf Defizite eingehen und ToDos geben.
- use_case_analysis: Eine kompakte Bewertung der geplanten Maßnahme und Ziele, inklusive konkreter Chancen & Risiken für dieses Unternehmen.
- executive_summary: Seriöse Gesamtzusammenfassung in der Sie-Form, maximal 5 Sätze.
- fördertipps: Konkrete Förderprogramme oder Strategien, die speziell für die Branche "{data.get("branche")}" und die Maßnahme "{data.get("massnahme")}" geeignet sind. Bitte als Bulletpoints.
- toolkompass: 3 konkrete Tools, Frameworks oder Plattformen, die exakt zu Ziel und Bereich passen, mit je einem Satz Begründung.
- branche_trend: Kurzbeschreibung der wichtigsten Trends und Chancen in der Branche "{data.get("branche")}".
- compliance_score: Zahl von 0 bis 10 (0 = sehr hohes Risiko, 10 = optimal abgesichert).
- badge_level: "Bronze", "Silber" oder "Gold", basierend auf dem compliance_score (bis 4 Bronze, bis 7 Silber, ab 8 Gold).
- vision: Eine inspirierende Perspektive, wie KI dieses Unternehmen in den nächsten 3 Jahren transformieren könnte, formuliert als kurzer Absatz.

Unternehmensdaten:
- Name: {data.get("name")}
- E-Mail: {data.get("email")}
- Branche: {data.get("branche")}
- Selbstständig: {data.get("selbststaendig")}
- Maßnahme: {data.get("massnahme")}
- Bereich: {data.get("bereich")}
- Ziel: {data.get("ziel")}
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

Beispielausgabe:
{{
  "readiness_analysis": "...",
  "compliance_analysis": "...",
  "use_case_analysis": "...",
  "executive_summary": "...",
  "fördertipps": ["..."],
  "toolkompass": ["..."],
  "branche_trend": "...",
  "compliance_score": 8,
  "badge_level": "Gold",
  "vision": "..."
}}
"""

        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )

        output_text = response.choices[0].message.content.strip()
        result = eval(output_text)
        return result

    except Exception as e:
        raise RuntimeError(f"Fehler bei der Analyse: {e}")
