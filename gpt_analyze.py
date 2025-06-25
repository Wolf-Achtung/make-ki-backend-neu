from openai import OpenAI
import os
import requests
import json
from flask import jsonify
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
def get_analysis(data: dict) -> dict:
    """Erstellt eine strukturierte Analyse mit GPT und generiert ein PDF mit PDFMonkey."""
    # Eingabe aggregieren
    input_string = "\n".join(
        f"{key.capitalize()}: {value}" for key, value in data.items() if value
    )
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
        gpt_analysis_result = json.loads(reply)  # Annahme: GPT antwortet mit JSON
    except Exception as e:
        print(f"Fehler bei der GPT-Analyse: {e}")
        return {"error": str(e)}  # Fehler zurückgeben
    # PDF mit PDFMonkey generieren
    pdf_url = generate_pdf(gpt_analysis_result)
    if pdf_url:
        return {"pdf_url": pdf_url}  # PDF-URL zurückgeben
    else:
        return {"error": "Fehler bei der PDF-Generierung"}  # Fehler zurückgeben
def generate_pdf(data: dict) -> str | None:
    """Generiert ein PDF mit PDFMonkey und gibt die PDF-URL zurück."""
    api_key = os.getenv("PDFMONKEY_API_KEY")
    template_id = os.getenv("PDFMONKEY_TEMPLATE_ID")
    api_url = "https://api.pdfmonkey.io/api/v1/documents"  # Korrekte API URL überprüfen!
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
        response.raise_for_status()  # Wirft eine Exception bei HTTP-Fehlern (4xx oder 5xx)
        response_json = response.json()
        pdf_url = response_json.get("document", {}).get("url")  # URL zum generierten PDF
        return pdf_url  # Gib die PDF-URL zurück
    except requests.exceptions.RequestException as e:
        print(f"Fehler bei der PDF-Generierung: {e}")
        return None  # Oder wirf eine Exception, je nachdem, wie du Fehler behandeln willst
    except json.JSONDecodeError as e:
        print(f"Fehler beim Decodieren des PDFMonkey-JSON: {e}")
        return None
# Beispiel, wie du diese Funktion in deiner Flask-Route nutzen könntest:
if __name__ != "__main__":  # Stelle sicher, dass dies nicht ausgeführt wird, wenn die Datei als Modul importiert wird
    def analyze_data(request_data): # request_data ist das Formular
        result = get_analysis(request_data)
        return jsonify(result)