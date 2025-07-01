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
Erstelle ein Executive Briefing mit folgender festen Struktur:

1. Executive Summary
2. Readiness & Strategie (inkl. SWOT, PESTEL oder BMC wo sinnvoll)
3. Compliance & Datenschutz (DSGVO, AI-Act, Risiken)
4. Risiko & Haftung (inkl. Eintrittswahrscheinlichkeit & Folgen als Ampelmatrix)
5. Branchenvergleich & Benchmarks
6. Branchentrends & Tech-Benchmarks (tiefergehend)
7. Use Cases & Innovation (auch unkonventionell)
8. Use Case Analyse mit ROI (z. B. +15% Effizienz, -12% Kosten)
9. Vision (konkret & mutig)
10. MoonShots & MarsShots
11. Top Tools (differenziert nach Unternehmensgröße)
12. Förderungen & Hidden Gems (national + regional, inkl. Nutzen)
13. Prioritäten-Matrix (Impact vs Aufwand als Text-Tabelle)
14. Konkrete Next Steps (Quick Wins & langfristige Projekte)

Das Executive Briefing soll ca. 7-10 Seiten (3000-4000 Wörter) umfassen und professionell, seriös sowie teils visionär geschrieben sein.

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
