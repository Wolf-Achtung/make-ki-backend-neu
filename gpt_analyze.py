from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

def analyze_with_gpt(data):
    try:
        prompt = f"""
Sie sind ein zertifizierter KI-Manager und Fördermittelberater. 
Bitte analysieren Sie die folgenden Unternehmensangaben, die über ein Online-Formular übermittelt wurden.

Erstellen Sie ausschließlich ein JSON, ohne Einleitung oder Abschluss, mit exakt diesen Feldern:

- readiness_analysis: Einschätzung der allgemeinen KI-Readiness basierend auf Branche, Selbstständigkeit, Maßnahme und Ziel
- compliance_analysis: Einschätzung der DSGVO-/AI-Act-Konformität basierend auf den Antworten zu frage1 bis frage10
- use_case_analysis: Bewertung des geplanten Einsatzes und der Ziele inkl. Risiken & Potenziale
- executive_summary: Zusammenfassung der Lage & Handlungsempfehlungen
- fördertipps: Konkrete Förderprogramme oder allgemeine Förderstrategien
- toolkompass: Empfehlungen für Tools, Frameworks oder Plattformen
- branche_trend: Entwicklungen und Chancen speziell in dieser Branche
- compliance_score: Zahl von 0 bis 10 (0 = hohes Risiko, 10 = optimal abgesichert)
- badge_level: "Bronze", "Silber" oder "Gold" (basierend auf Score)
- vision: Inspirierende Perspektive, wie KI das Unternehmen transformieren kann

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
  "fördertipps": "...",
  "toolkompass": "...",
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
