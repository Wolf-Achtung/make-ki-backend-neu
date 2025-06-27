
from flask import Flask, request, jsonify
from flask_cors import CORS
from gpt_analyze import analyze_with_gpt
import logging

app = Flask(__name__)
CORS(app)

# Setup logging
logging.basicConfig(level=logging.INFO)

@app.route("/")
def home():
    return "KI-Briefing Backend ist aktiv"

@app.route("/briefing", methods=["POST"])
def generate_briefing():
    try:
        data = request.json
        logging.info("Eingehende Daten: %s", data)

        if not data:
            return jsonify({"error": "Keine Daten empfangen"}), 400

        result = analyze_with_gpt(data)
        logging.info("GPT-Ergebnis erfolgreich generiert.")
        return jsonify(result)

    except Exception as e:
        logging.exception("Fehler bei der GPT-Auswertung:")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8000)
