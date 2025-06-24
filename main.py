import os
import json
import logging
from flask import Flask, request, jsonify
from gpt_analyze import get_analysis

app = Flask(__name__)

# Logging
logging.basicConfig(level=logging.INFO)

# Get environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")

if not OPENAI_API_KEY:
    raise EnvironmentError("❌ Fehlender OPENAI_API_KEY in Umgebungsvariablen")

@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        data = request.get_json(force=True)
        logging.info("📩 Empfangene Daten: %s", json.dumps(data, indent=2))

        required_fields = ["email", "unternehmen"]
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({"error": f"Pflichtfeld fehlt: {field}"}), 400

        result = get_analysis(data, OPENAI_API_KEY)

        logging.info("✅ GPT-Antwort erfolgreich erhalten")
        return jsonify(result), 200

    except json.JSONDecodeError as e:
        logging.exception("❌ JSON konnte nicht geparst werden")
        return jsonify({"error": "Ungültige JSON-Antwort von GPT"}), 500

    except Exception as e:
        logging.exception("❌ Allgemeiner Fehler im Analyseprozess")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=(ENVIRONMENT == "debug"))
