from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

def analyze_with_gpt(data):
    try:
        unternehmen = data.get("unternehmen", "Ihr Unternehmen")
        branche = data.get("branche", "Allgemein")
        ziel = data.get("ziel", "nicht angegeben")
        tools = data.get("tools", "nicht angegeben")
        bereich = data.get("bereich", "nicht angegeben")

        prompt = f"""
Sie sind ein zertifizierter KI-Manager und Fördermittelberater. 
Bitte analysieren Sie die folgenden Unternehmensdaten und geben Sie 
ausschließlich ein JSON zurück, ohne Einleitung oder Abschluss.

Das JSON MUSS exakt folgende Felder enthalten:

- readiness_analysis: Eine kurze Analyse zur allgemeinen KI-Readiness des Unternehmens
- compliance_analysis: Einschätzung zum DSGVO- & AI-Act-konformen Einsatz, inkl. möglicher Risiken
- use_case_analysis: Einschätzung der geplanten KI-Use-Cases inkl. Optimierungstipps
- executive_summary: Eine Gesamtzusammenfassung
- fördertipps: Konkrete Förderprogramme oder allgemeine Förderstrategien
- toolkompass: Empfehlungen für Tools, Frameworks oder Plattformen
- branche_trend: Entwicklungen und Chancen speziell in dieser Branche
- compliance_score: Eine Zahl von 0 bis 10, die das Datenschutz- & Compliance-Level bewertet
- badge_level: Entweder "Bronze", "Silber" oder "Gold", basierend auf dem Score
- vision: Inspirierende Perspektive, wie KI das Unternehmen transformieren kann

Unternehmensdaten:
- Name: {unternehmen}
- Branche: {branche}
- Bereich: {bereich}
- Ziel: {ziel}
- Eingesetzte Tools: {tools}

Beispielausgabe:
{{
  "readiness_analysis": "...",
  "compliance_analysis": "...",
  "use_case_analysis": "...",
  "executive_summary": "...",
  "fördertipps": "...",
  "toolkompass": "...",
  "branche_trend": "...",
  "compliance_score": 7,
  "badge_level": "Silber",
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
