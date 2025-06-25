import os
from openai import OpenAI
from dotenv import load_dotenv
import json

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def analyze_payload(data):
    print("🟢 Eingehende Daten für Analyse:")
    print(data)

    prompt = f"""
Du bist ein KI-Berater für kleine Unternehmen, Selbstständige und Freiberufler.
Analysiere die folgenden Unternehmensdaten und gib klare, praxisnahe Empfehlungen zur KI-Nutzung, Förderung und Sicherheit – im JSON-Format.

## Unternehmensdaten
Name: {data.get('name')}
Unternehmen: {data.get('unternehmen')}
E-Mail: {data.get('email')}
Branche: {data.get('branche')}
Bereich: {data.get('bereich')}
Selbstständig: {data.get('selbststaendig')}
Ziel: {data.get('ziel')}
Strategie: {data.get('strategie')}
Tools: {data.get('tools')}
Prozesse: {data.get('prozesse')}
Infrastruktur: {data.get('infrastruktur')}
Know-how: {data.get('knowhow')}
Maßnahmen: {data.get('massnahmen')}
Verantwortung: {data.get('verantwortung')}
Herausforderung: {data.get('herausforderung')}
Förderung: {data.get('foerderung')}
Datenschutz: {data.get('datenschutz')}

Gib die Antwort **ausschließlich im gültigen JSON-Format** zurück, mit folgenden Feldern:
"analyse", "empfehlungen", "foerdertipps", "compliance", "trendreport", "beratungsempfehlung", "zukunft", "gamechanger"
"""

    try:
        print("📡 Sende Anfrage an OpenAI ...")
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Du bist ein professioneller KI-Analyst. Antworte ausschließlich mit JSON – ohne weitere Kommentare."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )

        reply = response.choices[0].message.content.strip()
        print("🤖 GPT-Antwort erhalten:")
        print(reply)

        # Versuch, das JSON zu parsen
        try:
            return json.loads(reply)
        except json.JSONDecodeError as e:
            print("⚠️ GPT-Antwort ist kein valides JSON!")
            return {"error": "Ungültige JSON-Antwort", "raw": reply}

    except Exception as e:
        print(f"❌ Fehler beim GPT-Aufruf: {e.__class__.__name__}: {str(e)}")
        return {"error": str(e)}
