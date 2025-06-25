import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def analyze_payload(data):
    print("⏳ Eingehende Daten für Analyse:")
    print(data)

    prompt = f"""
Du bist ein KI-Berater für kleine Unternehmen, Selbstständige und Freiberufler.
Analysiere das folgende Unternehmensprofil und gib konkrete, praxisnahe Empfehlungen zur KI-Nutzung, Förderung und Sicherheit.

## Basisdaten
Name: {data.get('name')}
E-Mail: {data.get('email')}
Unternehmen: {data.get('unternehmen')}

## Geschäftliches Umfeld
Branche: {data.get('branche')}
Bereich: {data.get('bereich')}
Selbstständig: {data.get('selbstständig')}

## Ziele & Strategie
Ziel: {data.get('ziel')}
Strategie: {data.get('strategie')}

## Infrastruktur & Know-how
Infrastruktur: {data.get('infrastruktur')}
Know-how: {data.get('knowhow')}
Prozesse: {data.get('prozesse')}

## Datenschutz & Verantwortung
Datenschutz: {data.get('datenschutz')}
Verantwortung: {data.get('verantwortung')}

## Herausforderung & Maßnahmen
Herausforderung: {data.get('herausforderung')}
Geplante Maßnahmen: {data.get('maßnahmen')}

## Fördermöglichkeiten
#Förderinteresse: {data.get('förderung')}

## Tools
Eingesetzte Tools: {data.get('tools')}

Gib bitte zurück:
– Analyse der Ausgangssituation
– KI-Empfehlungen (kurz-, mittel-, langfristig)
– Risiken & rechtliche Hinweise
– DSGVO- & EU-AI-Act-Konformität
– Fördertipps (DE/EU)
– Tool-Kompass mit konkreten Empfehlungen
– Branchenvergleich & Benchmarks
– Visionärer Zukunftsausblick (Gamechanger-Idee)
– Persönliche Beratungsempfehlung

Antwort im JSON-Format mit klaren Feldern wie "analyse", "empfehlungen", "fördertipps", "compliance", "trendreport", "beratungsempfehlung", "zukunft", etc.
"""

    try:
        print("📡 Sende Anfrage an OpenAI ...")
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        reply = response.choices[0].message.content
        print("✅ Antwort von GPT erhalten")
        return {"gpt_output": reply}
    
    except Exception as e:
        print("❌ Fehler beim GPT-Aufruf:")
        print(e.__class__.__name__, ":", str(e))
        return {"gpt_output": f"Fehler beim GPT-Aufruf: {e.__class__.__name__} - {str(e)}"}
