import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def analyze_payload(data):
    print("🟢 Eingehende Daten für Analyse:")
    print(data)

    prompt = f"""
    Du bist ein KI-Berater für kleine Unternehmen, Selbstständige und Freiberufler.
    Analysiere das folgende Unternehmensprofil und gib konkrete, praxisnahe Empfehlungen zur KI-Nutzung, Förderung und Sicherheit.

    ## Basisdaten
    Name: {data.get("name")}
    E-Mail: {data.get("email")}
    Unternehmen: {data.get("unternehmen")}

    ## Geschäftsbereich
    Branche: {data.get("branche")}
    Bereich: {data.get("bereich")}
    Selbstständig: {data.get("selbststaendig")}

    ## Ziele & Strategie
    Ziel: {data.get("ziel")}
    Strategie: {data.get("strategie")}

    ## Infrastruktur & Knowhow
    Infrastruktur: {data.get("infrastruktur")}
    Know-how: {data.get("knowhow")}
    Prozesse: {data.get("prozesse")}

    ## Verantwortung & Datenschutz
    Verantwortung: {data.get("verantwortung")}
    Datenschutz: {data.get("datenschutz")}

    ## Herausforderung & Maßnahmen
    Herausforderung: {data.get("herausforderung")}
    Geplante Maßnahmen: {data.get("massnahmen")}

    ## Förderung & Tools
    Förderinteresse: {data.get("foerderung")}
    Tools im Einsatz: {data.get("tools")}

    Gib bitte zurück im JSON-Format mit den Feldern:
    "analyse", "empfehlungen", "foerdertipps", "compliance", "trendreport", "beratungsempfehlung", "zukunft", "gamechanger".
    """

    try:
        print("📡 Sende Anfrage an OpenAI ...")
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Du bist ein professioneller KI-Analyst ..."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
        )
        reply = response.choices[0].message.content.strip()
        print("✅ GPT-Antwort:", reply)
        return {"gpt_output": reply}

    except Exception as e:
        print("❌ Fehler beim GPT-Aufruf:", type(e).__name__, "-", str(e))
        return {"gpt_output": f"Fehler: {type(e).__name__} – {str(e)}"}
