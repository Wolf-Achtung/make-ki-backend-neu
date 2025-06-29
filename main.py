from flask import Flask, request, jsonify
from gpt_analyze import analyze_with_gpt
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

@app.route("/briefing", methods=["POST"])
def generate_briefing():
    try:
        data = request.json
        logging.info(f"📥 Eingehende Daten: {data}")
        if not data:
            return jsonify({"error": "Keine Daten erhalten"}), 400

        result = analyze_with_gpt(data)
        logging.info("✅ GPT-Analyse fertig.")

        # GPT Output loggen (nur ersten Teil, damit Logs nicht platzen)
        if isinstance(result, str):
            logging.info(f"📝 GPT-Output (erste 300 Zeichen): {result[:300]}...")
        elif isinstance(result, dict):
            logging.info(f"📝 GPT-Output Dict Keys: {list(result.keys())}")

        # Smarte Rückgabe: JSON oder Text
        if isinstance(result, dict):
            return jsonify(result), 200, {"Content-Type": "application/json"}
        else:
            return result, 200, {"Content-Type": "text/plain; charset=utf-8"}

    except Exception as e:
        logging.exception("❌ Fehler bei GPT:")
        return jsonify({"error": str(e)}), 500

@app.route("/healthz", methods=["GET"])
def healthcheck():
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
