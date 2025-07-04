from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from gpt_analyze import analyze_with_gpt
from validate_response import validate_gpt_response
from pdf_export import create_pdf  # <--- PDF-Export importieren

import os

app = FastAPI()

# PDF-Ordner als statische Route einbinden (für den Download)
app.mount("/downloads", StaticFiles(directory="downloads"), name="downloads")

origins = [
    "https://make.ki-sicherheit.jetzt",
    "http://localhost",
    "http://localhost:3000",
    "http://127.0.0.1:8000"
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://make.ki-sicherheit.jetzt"],  # <-- Deine echte Frontend-URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")

@app.post("/briefing")
async def create_briefing(request: Request):
    data = await request.json()
    print("🚀 Empfangenes JSON:", data)

    gpt_result = analyze_with_gpt(data)
    gpt_result = validate_gpt_response(gpt_result)

    # HTML generieren für PDF und Anzeige
    html_content = templates.get_template("pdf_template.html").render(**gpt_result)

    # PDF erzeugen und Dateinamen zurückbekommen
    pdf_filename = create_pdf(html_content)
    pdf_url = f"/downloads/{pdf_filename}"

    # JSON-Response enthält HTML **und** PDF-URL
    return JSONResponse(content={"html": html_content, "pdf_url": pdf_url})

@app.get("/")
async def root():
    return {"message": "KI-Readiness Server läuft!"}
