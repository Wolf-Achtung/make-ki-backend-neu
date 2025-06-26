
from flask import Flask, request, jsonify
import httpx

app = Flask(__name__)

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json(force=True)
    print("[DEBUG] Eingehende Daten:", data)

    payload = {
        "document": {
            "template": "your-template-id",
            "payload": {
                "name": data.get("name"),
                "unternehmen": data.get("unternehmen"),
                "email": data.get("email"),
                "branche": data.get("branche"),
                "selbststaendig": data.get("selbststaendig"),
                "bereich": data.get("bereich"),
                "tools": data.get("tools"),
                "ziel": data.get("ziel"),
                "strategie": data.get("strategie"),
                "prozesse": data.get("prozesse"),
                "infrastruktur": data.get("infrastruktur"),
                "knowhow": data.get("knowhow"),
                "massnahmen": data.get("massnahmen"),
                "verantwortung": data.get("verantwortung"),
                "foerderung": data.get("foerderung"),
                "datenschutz": data.get("datenschutz")
            }
        }
    }

    headers = {
        "Authorization": "Bearer your-api-key",
        "Content-Type": "application/json"
    }

    response = httpx.post("https://api.pdfmonkey.io/api/v1/documents", json=payload, headers=headers)
    print("[DEBUG] PDFMonkey Antwort:", response.status_code, response.text)

    return jsonify({"status": "ok", "pdfmonkey_response": response.json()}), 200

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8000)
