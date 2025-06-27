
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import httpx
from gpt_analyze import analyze_payload
from html_generator import generate_html

app = Flask(__name__)
CORS(app)

@app.route("/", methods=["GET"])
def index():
    return "KI-Briefing Service läuft"

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.json

    # GPT-Auswertung
    gpt_result = analyze_payload(data)

    # HTML generieren
    html_content = generate_html(data, gpt_result)

    # PDFMonkey-Upload vorbereiten
    headers = {
        "Authorization": f"Bearer {os.getenv('PDFMONKEY_API_KEY')}",
        "Content-Type": "application/json"
    }

    payload = {
        "document": {
            "document_type": "html",
            "content": html_content
        }
    }

    response = httpx.post("https://api.pdfmonkey.io/api/v1/documents", json=payload, headers=headers)

    if response.status_code == 201:
        url = response.json().get("data", {}).get("download_url", "")
        return jsonify({ "status": "success", "download_url": url })
    else:
        return jsonify({ "status": "error", "details": response.text }), 500

if __name__ == "__main__":
    app.run(debug=True)
