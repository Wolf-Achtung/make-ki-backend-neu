
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from placid_upload_server import handle_template_upload

app = FastAPI()

@app.get("/upload-template", response_class=HTMLResponse)
async def get_template_form():
    with open("placid-upload.html", "r") as f:
        return f.read()

@app.post("/upload-template")
async def upload_template(template: UploadFile = File(...)):
    return await handle_template_upload(template)



import os
from flask import Flask, request, jsonify
import httpx
from gpt_analyze import analyze_payload
from html_generator import generate_html

app = Flask(__name__)

@app.route("/", methods=["GET"])
def index():
    return "KI-Briefing Service läuft"

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.json

    # GPT-Auswertung
    gpt_result = analyze_payload(data)

    # HTML generieren
    html_content = generate_html(data, gpt_result)

    # PDFMonkey-Upload vorbereiten
    headers = {
        "Authorization": f"Bearer {os.getenv('PDFMONKEY_API_KEY')}",
        "Content-Type": "application/json"
    }

    payload = {
        "document": {
            "document_type": "html",
            "content": html_content
        }
    }

    response = httpx.post("https://api.pdfmonkey.io/api/v1/documents", json=payload, headers=headers)

    if response.status_code == 201:
        url = response.json().get("data", {}).get("download_url", "")
        return jsonify({ "status": "success", "download_url": url })
    else:
        return jsonify({ "status": "error", "details": response.text }), 500

if __name__ == "__main__":
    app.run(debug=True)
