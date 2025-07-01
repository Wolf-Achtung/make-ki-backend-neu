import json
from openai import OpenAI

client = OpenAI()

# Lade Tools & Förderungen
with open("tools_und_foerderungen.json", encoding="utf-8") as f:
    db = json.load(f)

def build_prompt(data):
    tools_klein = ", ".join([t["name"] for t in db["tools"].get("kleinere", [])])
    tools_gross = ", ".join([t["name"] for t in db["tools"].get("groessere", [])])
    foerderungen_national = ", ".join([f["name"] for f in db["foerderungen"].get("national", [])])

    prompt = f"""
Du bist ein hochspezialisierter KI- und Datenschutzberater mit über 30 Jahren Erfahrung in digitaler Strategie, Compliance und Innovation.
Erstelle ein Executive Briefing mit folgender festen Struktur, aber gestaffelt:

- Block 1:
Executive Summary
Readiness & Strategie (inkl. SWOT, PESTEL oder BMC wo sinnvoll)
Compliance & Datenschutz (DSGVO, AI-Act, Risiken)
Risiko & Haftung (inkl. Eintrittswahrscheinlichkeit & Folgen als Ampelmatrix)

- Block 2:
Branchenvergleich & Benchmarks
Branchentrends & Tech-Benchmarks (tiefergehend)
Use Cases & Innovation (auch unkonventionell)
Use Case Analyse mit ROI (z. B. +15% Effizienz, -12% Kosten)

- Block 3:
Vision (konkret & mutig)
MoonShots & MarsShots
Top Tools (differenziert nach Unternehmensgröße)
Förderungen & Hidden Gems (national + regional, inkl. Nutzen)

- Block 4:
Prioritäten-Matrix (Impact vs Aufwand als Text-Tabelle)
Konkrete Next Steps (Quick Wins & langfristige Projekte)

Jeder Block soll ca. 1000-1300 Wörter haben, insgesamt ca. 4000-5000 Wörter. Gib alles in einem Fließtext zurück, strukturiert in Abschnitte, ohne JSON oder Code und professionell, seriös sowie teils visionär geschrieben.

Unternehmensprofil:
- Name: {data.get('unternehmen')}
- Branche: {data.get('branche')}
- Bereich: {data.get('bereich')}
- PLZ: {data.get('plz')}
- Mitarbeiterzahl: {data.get('mitarbeiterzahl')}
- Selbständig/Freiberuflich: {data.get('selbststaendig')}
- Geplante Maßnahme: {data.get('massnahme')}
- Produkt/Dienstleistung: {data.get('produkt_dienstleistung')}
- Aktuelle Herausforderungen: {data.get('herausforderungen')}
- 3-Jahres-Ziele: {data.get('ziele_3jahre')}
- IT-Systeme & Tools: {data.get('it_systeme')}
- Bereits genutzte KI-Tools: {data.get('ki_tools')}
- Zielgruppen: {data.get('zielgruppen')}
- Datenschutzmaßnahmen dokumentiert: {data.get('datenschutz')}
- Datenschutzvorfälle/Audits: {data.get('vorfaelle')}
- Automatisierungspotenziale: {data.get('innovation_potentiale')}
- Moonshot-Idee: {data.get('moonshot')}

Nutze als Tool- und Förderbasis:
- Für kleinere Unternehmen: {tools_klein}
- Für größere Unternehmen: {tools_gross}
- Nationale Förderungen: {foerderungen_national}

Achte besonders darauf:
- Tools und Förderungen passend zur Größe (KMU vs groß) und Freiberuflich-Status zu wählen.
- Regionale Hidden Gems anhand der PLZ zu erwähnen.
- ROI grob zu kalkulieren anhand typischer Digitalisierungsbenchmarks.
- SWOT, PESTEL oder Business Model Canvas Elemente nur wo sinnvoll.
- Eine klare Prioritäten-Matrix mit Impact vs Aufwand als Text-Tabelle zu liefern.
- Ca. 50% harte Analysen (Kennzahlen, Risiken, Compliance), 50% Vision & Moonshots.

Sprich das Unternehmen immer in der professionellen Sie-Form an. 
Gib nur den finalen Fließtext zurück, kein JSON, kein Code, keine zusätzliche Einleitung.
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
        return response.choices[0].message.content
    except Exception as e:
        return f"Fehler beim GPT-Aufruf: {str(e)}"
