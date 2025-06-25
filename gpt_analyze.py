import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def analyze_payload(data):
    prompt = f"""
Du bist ein KI-Berater für kleine Unternehmen, Selbstständige und Freiberufler. 
Analysiere das folgende Unternehmensprofil und gib konkrete, praxisnahe Empfehlungen zur KI-Nutzung, Förderung und Sicherheit.

## Basisdaten
Name: {data['name']}
E-Mail: {data['email']}
Unternehmen: {data['unternehmen']}

## Geschäftliches Umfeld
Branche: {data['branche']}
Bereich: {data['bereich']}
Selbstständig: {data['selbststaendig']}

## Ziele & Strategie
Ziel: {data['ziel']}
Strategie: {data['strategie']}

## Infrastruktur & Know-how
Infrastruktur: {data['infrastruktur']}
Know-how: {data['knowhow']}
Prozesse: {data['prozesse']}

## Datenschutz & Verantwortung
Datenschutz: {data['datenschutz']}
Verantwortung: {data['verantwortung']}

## Herausforderung & Maßnahmen
Herausforderung: {data['herausforderung']}
Geplante Maßnahmen: {data['massnahmen']}

## Fördermöglichkeiten
Förderinteresse: {data['foerderung']}

## Tools
Eingesetzte Tools: {data['tools']}

Gib bitte zurück:
- Analyse der Ausgangssituation
- KI-Empfehlungen (kurz-, mittel-, langfristig)
- Risiken & rechtliche Hinweise
- DSGVO- & EU-AI-Act-Konformität
- Fördertipps (DE/EU)
- Tool-Kompass mit konkreten Empfehlungen
- Branchenvergleich & Benchmarks
- Visionärer Zukunftsausblick (Gamechanger-Idee)
- Persönliche Beratungsempfehlung

Antwort im JSON-Format mit klaren Feldern wie "analyse", "empfehlungen", "foerdertipps", "compliance", "trendreport", "beratungsempfehlung", "zukunft", etc.
"""

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )

    reply = response.choices[0].message.content

    return {"gpt_output": reply}
