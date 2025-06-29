from flask import Flask, request, jsonify
from flask_cors import CORS
from gpt_analyze import analyze_with_gpt
import logging

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

@app.route("/")
def home():
    return "KI-Briefing Backend läuft."

@app.route("/briefing", methods=["POST"])
def generate_briefing():
    try:
        data = request.json
        logging.info(f"Eingehend: {data}")
        if not data:
            return jsonify({"error": "Keine Daten erhalten"}), 400

        result = analyze_with_gpt(data)
        logging.info("GPT-Analyse fertig.")
        return jsonify(result)
    except Exception as e:
        logging.exception("Fehler bei GPT:")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
