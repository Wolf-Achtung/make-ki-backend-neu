from flask import Flask, request, jsonify
from gpt_analyze import get_analysis

app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "KI-Briefing läuft!"

@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Keine JSON-Daten empfangen."}), 400

        result = get_analysis(data)
        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
