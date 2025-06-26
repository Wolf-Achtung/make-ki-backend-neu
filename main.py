
import os
from flask import Flask, request, jsonify
from gpt_analyze import analyze_payload
import httpx
from datetime import datetime

app = Flask(__name__)

@app.route("/", methods=["GET"])
def index():
    return "KI-Briefing Service läuft"

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.json

    # Logging in Datei
    log_path = "analyze_log.txt"
    with open(log_path, "a") as logfile:
        logfile.write(f"[{datetime.now()}] Eingehende Daten:\n")
        for key, value in data.items():
            logfile.write(f"{key}: {value}\n")
        logfile.write("\n" + "="*40 + "\n")

    print("📥 Eingehende Daten:", data)

    # GPT-Auswertung durchführen
    gpt_result = analyze_payload(data)
    print("📤 GPT-Auswertung:", gpt_result)

    # HTML-Generierung aus GPT-Auswertung
    html_content = f"""
    <html><head><meta charset='UTF-8'><title>KI-Briefing</title></head><body>
    <h1>KI-Briefing</h1>
    <h2>Executive Summary</h2><p>{gpt_result['executive_summary']}</p>
    <h2>Fördertipps</h2><p>{gpt_result['fördertipps']}</p>
    <h2>Toolkompass</h2><p>{gpt_result['toolkompass']}</p>
    <h2>Branchenvergleich & Trends</h2><p>{gpt_result['branche_trend']}</p>
    <h2>Compliance</h2><p>{gpt_result['compliance']}</p>
    <h2>Beratungsempfehlung</h2><p>{gpt_result['beratungsempfehlung']}</p>
    <h2>Visionärer Ausblick</h2><p>{gpt_result['vision']}</p>
    </body></html>
    """

    # PDFMonkey HTML-Dokument anlegen
    pdfmonkey_api_key = os.getenv("PDFMONKEY_API_KEY")
    pdfmonkey_url = "https://api.pdfmonkey.io/api/v1/documents"
    headers = {
        "Authorization": f"Bearer {pdfmonkey_api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "document": {
            "document_template": {
                "content_html": html_content
            }
        }
    }

    response = httpx.post(pdfmonkey_url, json=payload, headers=headers)
    result = response.json()
    print("📄 PDFMonkey Response:", result)

    # Vorschau-Link zurückgeben
    download_url = result.get("data", {}).get("attributes", {}).get("download_url")
    return jsonify({"status": "success", "download_url": download_url})

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8000)
