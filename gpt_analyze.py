import json
from openai import OpenAI

client = OpenAI()

# Lade Tools & Förderungen
with open("tools_und_foerderungen.json", encoding="utf-8") as f:
    db = json.load(f)

def build_prompt(data):
    prompt = f"""
Du bist ein hochspezialisierter KI- und Digitalisierungsberater mit über 30 Jahren Erfahrung.
Analysiere das folgende Unternehmensprofil ausführlich und liefere ein umfassendes Executive-Briefing 
zu folgenden Themenblöcken (bitte in dieser Reihenfolge, jeweils als Abschnitt mit Überschrift):

- Risiko & Haftung
- DSGVO / AI-Act / Risiko
- Executive Summary
- Readiness & Strategie
- Compliance & Datenschutz
- Use Cases & Innovation
- Use Case Analyse mit ROI
- Branchenvergleich
- Branchentrends & Benchmarks
- Vision
- MoonShots
- MarsShots
- Top Tools (unterscheide KMU/große Unternehmen)
- Förderungen (national & regionale Hidden Gems inkl. Nutzen)
- Prioritäten-Matrix Impact vs Aufwand (als Texttabelle)
- konkrete Next Steps (mindestens 7 konkrete Handlungsempfehlungen)

Die Inhalte sollen insgesamt 7-10 Seiten lang sein (~3000-4000 Wörter), dabei ca. 50% seriöse Management-Analyse
und 50% visionäre, mutige Impulse.

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
- SWOT, PESTEL oder BMC-Elemente gelegentlich einbauen.
- ROI grob in % angeben (z. B. +12% Umsatz).
- Prioritäten-Matrix als Texttabelle darstellen.
- MoonShots & MarsShots kreativ und mutig formulieren.

Gib ausschließlich folgendes zurück:
ein reines JSON-Objekt mit einem einzigen Schlüssel:
{{
  "executive_report": "...hier der gesamte Text des Executive Reports..."
}}
ohne ```json, ohne ```-Block, ohne jeglichen Text davor oder danach, keine Erklärungen, keine Kommentare.
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
