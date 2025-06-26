from fastapi.middleware.cors import CORSMiddleware


import os
from flask import Flask, request, jsonify
from gpt_analyze import analyze_payload
import httpx

app = Flask(__name__)

@app.route("/", methods=["GET"])
def index():
    return "KI-Briefing Service läuft"

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.json

    # Logging: Eingehende Daten mit Zeitstempel in Datei schreiben
    from datetime import datetime
    log_path = "analyze_log.txt"
    with open(log_path, "a") as logfile:
        logfile.write(f"[{datetime.now()}] Eingehende Daten:\n")
        for key, value in data.items():
            logfile.write(f"{key}: {value}\n")
        logfile.write("\n" + "="*40 + "\n")

    print("📥 Eingehende Daten:", data)

    # GPT-Auswertung
    gpt_result = analyze_payload(data)
    print("📤 GPT-Auswertung:", gpt_result)

    # PDFMonkey-Call vorbereiten
    pdfmonkey_api_key = os.getenv("PDFMONKEY_API_KEY")
    pdfmonkey_template_id = os.getenv("PDFMONKEY_TEMPLATE_ID")

    payload = {
        "document": {
            "document_template_id": pdfmonkey_template_id,
            "payload": {
                "name": data.get("name"),
                "unternehmen": data.get("unternehmen"),
                "email": data.get("email"),
                "branche": data.get("branche"),
                "selbststaendig": data.get("selbststaendig"),
                "ziel": data.get("ziel"),
                "bereich": data.get("bereich"),
                "strategie": data.get("strategie"),
                "tools": data.get("tools"),
                "prozesse": data.get("prozesse"),
                "infrastruktur": data.get("infrastruktur"),
                "knowhow": data.get("knowhow"),
                "massnahmen": data.get("massnahmen"),
                "verantwortung": data.get("verantwortung"),
                "herausforderung": data.get("herausforderung"),
                "foerderung": data.get("foerderung"),
                "datenschutz": data.get("datenschutz"),
                # GPT-Ergebnisse
                "executive_summary": gpt_result.get("executive_summary", ""),
                "fördertipps": gpt_result.get("fördertipps", ""),
                "toolkompass": gpt_result.get("toolkompass", ""),
                "branche_trend": gpt_result.get("branche_trend", ""),
                "compliance": gpt_result.get("compliance", ""),
                "beratungsempfehlung": gpt_result.get("beratungsempfehlung", ""),
                "vision": gpt_result.get("vision", "")
            }
        }
    }

    headers = {
        "Authorization": f"Bearer {pdfmonkey_api_key}",
        "Content-Type": "application/json"
    }

    response = httpx.post("https://api.pdfmonkey.io/api/v1/documents", json=payload, headers=headers)

    if response.status_code == 201:
        print("✅ PDFMonkey-Dokument erfolgreich erstellt.")
        return jsonify({"status": "success", "pdf_url": response.json()})
    else:
        print("❌ Fehler bei PDFMonkey:", response.text)
        return jsonify({"status": "error", "details": response.text}), 500

if __name__ == "__main__":
    app.run(debug=True)