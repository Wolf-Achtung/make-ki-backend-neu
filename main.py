from flask import Flask, request, jsonify
from gpt_analyze import get_analysis
import json  # für sauberes Logging

app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "KI-Briefing läuft!"

@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        data = request.get_json(force=True)
        if not data:
            print("❗ Warnung: Keine JSON-Daten empfangen.")
            return jsonify({"error": "Keine JSON-Daten empfangen."}), 400

        print("📥 Eingangsdaten von Make:\n", json.dumps(data, indent=2, ensure_ascii=False))
        result = get_analysis(data)
        print("📤 Ergebnis an Client:\n", json.dumps(result, indent=2, ensure_ascii=False))
        return jsonify(result)

    except Exception as e:
        print("❌ Fehler in /analyze:", str(e))
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
