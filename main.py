import os
from flask import Flask, request, jsonify
from gpt_analyze import analyze_payload
from placid_generate import generate_placid_pdf

app = Flask(__name__)

@app.route("/", methods=["GET"])
def index():
    return "KI-Briefing Service läuft"

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.json

    # GPT-Auswertung
    gpt_result = analyze_payload(data)

    # Alle Daten zusammenführen
    full_data = {**data, **gpt_result}

    try:
        pdf_url = generate_placid_pdf(full_data)
        return jsonify({ "status": "success", "download_url": pdf_url })
    except Exception as e:
        return jsonify({ "status": "error", "details": str(e) }), 500

if __name__ == "__main__":
    app.run(debug=True)
