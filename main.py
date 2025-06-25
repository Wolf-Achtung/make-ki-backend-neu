from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv
from gpt_analyze import analyze_payload

load_dotenv()

app = Flask(__name__)
CORS(app)

@app.route("/")
def index():
    return "KI-Briefing Backend läuft"

@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        data = request.get_json(force=True)

        required_fields = [
            "bereich", "branche", "datenschutz", "email", "foerderung",
            "herausforderung", "infrastruktur", "knowhow", "massnahmen", "name",
            "prozesse", "selbststaendig", "strategie", "tools", "unternehmen",
            "verantwortung", "ziel"
        ]

        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing field: {field}"}), 400

        print("📥 Eingehende Daten:", data)
        gpt_result = analyze_payload(data)
        print("✅ GPT-Ergebnis:", gpt_result)

        return jsonify(gpt_result)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
