from flask import Flask, request, jsonify
from gpt_analyze import get_analysis
import json

app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "✅ KI-Briefing-API läuft (Flask + GPT + PDFMonkey)"

@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        data = request.get_json(force=True)

        if not data:
            print("\n🚫 Keine JSON-Daten empfangen.")
            return jsonify({"error": "Keine JSON-Daten empfangen."}), 400

        required_fields = ["name", "unternehmen", "email", "branche"]
        for field in required_fields:
            if not data.get(field):
                print(f"\n❗️ Pflichtfeld fehlt oder leer: {field}")
                return jsonify({"error": f"Pflichtfeld fehlt oder leer: {field}"}), 400

        print("\n📥 [EINGANG] Daten von Make:")
        print(json.dumps(data, indent=2, ensure_ascii=False))

        result = get_analysis(data)

        print("\n📤 [AUSGANG] Ergebnis zurück an Make:")
        print(json.dumps(result, indent=2, ensure_ascii=False))

        return jsonify(result)

    except Exception as e:
        print("\n❌ [FEHLER] in /analyze:", str(e))
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
