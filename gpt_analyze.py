from openai import OpenAI
import os
import requests
import json
from flask import jsonify

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def format_value(val):
    if isinstance(val, list):
        return ", ".join(str(v) for v in val)
    if isinstance(val, dict):
        return json.dumps(val, ensure_ascii=False)
    return str(val)

def get_analysis(data: dict) -> dict:
    """Erstellt eine strukturierte Analyse mit GPT und generiert ein PDF mit PDFMonkey."""
    # Eingabe aggregieren & loggen
    try:
        input_string = "\n".join(
            f"{key.capitalize()}: {format_value(value)}"
            for key, value in data.items() if value
        )
        print("🧾 Eingabedaten für GPT:\n", input_string)
    except Exception as e:
        print("❌ Fehler bei der Eingabeverarbeitung:", str(e))
        return {"error": "Fehler bei der Eingabeverarbeitung"}

    # Prompt
    prompt = f"""
Erstelle eine strukturierte Analyse für folgende Nutzereingabe:
{input_string}
Strukturiere die Analyse in folgenden Feldern (im JSON-Format):
- executive_summary
- score
- empfehlungen
- risiken
- branche_vergleich
- visionaerer_blick
- trendreport
- compliance
- beratungsempfehlung
- foerdertipps
- toolkompass
Antworte ausschließlich im JSON-Format ohne Kommentare oder weitere Einleitung.
"""

    # GPT-Request
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        reply = response.choices[0].message.content
        gpt_analysis_result = json.loads(reply)
    except Exception as e:
        print(f"❌ Fehler bei der GPT-Analyse: {e}")
        return {"error": str(e)}

    # PDF mit PDFMonkey generieren
    pdf_url = generate_pdf(gpt_analysis_result)
    if pdf_url:
        return {"pdf_url": pdf_url}
    else:
        return {"error": "Fehler bei der PDF-Generierung"}

def generate_pdf(data: dict) -> str | None:
    """Generiert ein PDF mit PDFMonkey und gibt die PDF-URL zurück."""
    api_key = os.getenv("PDFMONKEY_API_KEY")
    template_id = os.getenv("PDFMONKEY_TEMPLATE_ID")
    api_url = "https://api.pdfmonkey.io/api/v1/documents"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "document": {
            "template_id": template_id,
            "payload": data,
        }
    }
    try:
        response = requests.post(api_url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        response_json = response.json()
        pdf_url = response_json.get("document", {}).get("url")
        print("✅ PDF erfolgreich erstellt:", pdf_url)
        return pdf_url
    except requests.exceptions.RequestException as e:
        print(f"❌ Fehler bei der PDF-Generierung: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ JSON-Fehler bei der PDF-Antwort: {e}")
        return None

# Optionales Beispiel für Integration
if __name__ != "__main__":
    def analyze_data(request_data):
        result = get_analysis(request_data)
        return jsonify(result)
