from flask import Flask, request, jsonify
from gpt_analyze import get_analysis
import os

app = Flask(__name__)

@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No input data provided"}), 400
        result = get_analysis(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
