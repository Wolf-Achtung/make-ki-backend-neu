import json
from openai import OpenAI

client = OpenAI()

# Lade Tools & Förderungen
with open("tools_und_foerderungen.json", encoding="utf-8") as f:
    db = json.load(f)

def build_prompt(data):
    prompt = f"""
Du bist ein hochspezialisierter KI-Berater mit über 30 Jahren Erfahrung.
Bitte analysiere das folgende Unternehmensprofil und liefere ein JSON mit exakt diesen Feldern:

{{
  "compliance_score": "...",
  "dsgvo_score": "...",
  "ai_act_score": "...",
  "trust_badge": "...",
  "risiko_haftung": "...",
  "executive_summary": "...",
  "readiness_strategie": "...",
  "compliance_datenschutz": "...",
  "branchenvergleich": "...",
  "branchentrends": "...",
  "use_cases_innovation": "...",
  "use_cases_roi": "...",
  "vision": "...",
  "moonshots_marsshots": "...",
  "top_tools": "...",
  "foerderungen": "...",
  "prioritaeten_matrix": "...",
  "next_steps": "..."
}}

Die Inhalte sollen zusammen ca. 7-10 Seiten lang sein (3000-4000 Wörter).
Verteile die Inhalte ausgewogen: ca. 50% harte Analysen (Compliance, Risiken, Benchmarks), 50% visionäre Ansätze.

Unternehmensdaten:
- Name: {data.get('unternehmen')}
- Branche: {data.get('branche')}
- Bereich: {data.get('bereich')}
- PLZ: {data.get('plz')}
- Mitarbeiterzahl: {data.get('mitarbeiterzahl')}
- Selbständig/Freiberuflich: {data.get('selbststaendig')}
- Geplante Maßnahme: {data.get('massnahme')}
- Produkt/Dienstleistung: {data.get('produkt_dienstleistung')}
- Datenschutz dokumentiert: {data.get('datenschutz')}
- Aktuelle Herausforderungen: {data.get('herausforderungen')}
- 3-Jahres-Ziele: {data.get('ziele_3jahre')}
- IT-Systeme & Tools: {data.get('it_systeme')}
- Bereits genutzte KI-Tools: {data.get('ki_tools')}
- Zielgruppen: {data.get('zielgruppen')}
- Datenschutzvorfälle/Audits: {data.get('vorfaelle')}
- Automatisierungspotenziale: {data.get('innovation_potentiale')}
- Moonshot-Idee: {data.get('moonshot')}

Tools & Förderungen für kleinere Unternehmen:
- {", ".join([t["name"] for t in db["tools"].get("kleinere", [])])}

Für größere Unternehmen:
- {", ".join([t["name"] for t in db["tools"].get("groessere", [])])}

Nationale Förderungen:
- {", ".join([f["name"] for f in db["foerderungen"].get("national", [])])}

Achte darauf:
- SWOT, PESTEL oder BMC-Elemente einzubauen, wo sinnvoll.
- ROI grob in % anzugeben (z. B. +12% Umsatz).
- Prioritäten-Matrix als Texttabelle zu formulieren.
- MoonShots & MarsShots kreativ und mutig zu gestalten.

Gib ausschließlich das JSON-Objekt zurück, keine Einleitung, keine Fließtexte davor oder danach.
"""
    return prompt

def analyze_with_gpt(data):
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "user", "content": build_prompt(data)}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return json.dumps({"error": str(e)})
