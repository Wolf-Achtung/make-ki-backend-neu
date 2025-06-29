from flask import Flask, request, jsonify
from gpt_analyze import analyze_with_gpt
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

@app.route("/briefing", methods=["POST"])
def generate_briefing():
    try:
        data = request.json
        logging.info(f"Eingehend: {data}")
        if not data:
            return jsonify({"error": "Keine Daten erhalten"}), 400

        result = analyze_with_gpt(data)
        logging.info("GPT-Analyse fertig.")

        # Smarte Ausgabe: wenn result ein dict, jsonify, sonst plain text
        if isinstance(result, dict):
            return jsonify(result)
        else:
            return result, 200, {"Content-Type": "text/plain; charset=utf-8"}

    except Exception as e:
        logging.exception("Fehler bei GPT:")
        return jsonify({"error": str(e)}), 500

@app.route("/", methods=["GET"])
def home():
    return "KI-Backend läuft."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
