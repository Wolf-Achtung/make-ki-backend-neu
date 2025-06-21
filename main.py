import json
import os
import requests
from fastapi import FastAPI, Request
from pydantic import BaseModel
from typing import Literal
from dotenv import load_dotenv
import openai
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

app = FastAPI()

# CORS für alle Ursprünge aktivieren (für Netlify-Frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # für Produktion z. B. ["https://make.ki-sicherheit.jetzt"]
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ENV Variablen für GPT und PDFMonkey
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PDFMONKEY_TEMPLATE_ID = os.getenv("PDFMONKEY_TEMPLATE_ID")
PDFMONKEY_API_KEY = os.getenv("PDFMONKEY_API_KEY")
openai.api_key = OPENAI_API_KEY

class PDFRequest(BaseModel):
    payload: dict
    version: Literal["preview", "full"]

@app.get("/")
async def root():
    return {"message": "KI-Check Pro Backend läuft"}

def analyze_payload(user_data):
    prompt = f"""
    Du bist ein KI-Berater. Analysiere folgende Nutzerdaten für ein Executive Briefing:

    {user_data}

    Gib zurück:
    - executive_summary
    - analyse
    - empfehlung1–3 (jeweils mit titel, beschreibung, next_step, tool)
    - roadmap (kurzfristig, mittelfristig, langfristig)
    - ressourcen, zukunft, risikoprofil (risikoklasse, begruendung, pflichten[])
    - tooltipps, foerdertipps, branchenvergleich, trendreport, vision
    Gib die Antwort als JSON zurück.
    """

    response = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Du bist ein präziser KI-Berater."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.6
    )

    result_text = response.choices[0].message.content

    try:
        result_json = json.loads(result_text)
        return result_json
    except Exception as e:
        return {"error": f"Fehler beim Parsen der GPT-Ausgabe: {e}", "raw": result_text}

@app.post("/generate-pdf")
async def generate_pdf(req: PDFRequest):
    payload = req.payload
    version = req.version

    # GPT-Auswertung nur bei Vollversion
    if version == "full":
        gpt_output = analyze_payload(payload)
        if "error" not in gpt_output:
            payload.update(gpt_output)
        else:
            return {"status": "error", "details": gpt_output["error"], "raw": gpt_output.get("raw")}

    # PDFMonkey-Aufruf vorbereiten
    headers = {
        "Authorization": f"Bearer {PDFMONKEY_API_KEY}",
        "Content-Type": "application/json"
    }

    document_data = {
        "document": {
            "template_id": PDFMONKEY_TEMPLATE_ID,
            "payload": payload,
            "meta": {
                "version": version
            }
        }
    }

    response = requests.post(
        "https://api.pdfmonkey.io/api/v1/documents",
        headers=headers,
        data=json.dumps(document_data)
    )

    if response.status_code == 201:
        return {"status": "ok", "pdf": response.json()}
    else:
        return {"status": "error", "details": response.text}
