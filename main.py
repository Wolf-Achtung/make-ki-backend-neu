
from flask import Flask, request, jsonify
from gpt_analyze import get_analysis
import traceback

app = Flask(__name__)

@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        data = request.get_json(force=True)
        print("📥 Eingehende Daten:", data)
        result = get_analysis(data)
        print("📤 Analyseergebnis:", result)
        return jsonify(result)
    except Exception as e:
        print("❌ Fehler in /analyze:", str(e))
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
