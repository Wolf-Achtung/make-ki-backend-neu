from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from gpt_analyze import analyze_briefing
from pdf_export import create_pdf

import os

app = FastAPI()

# Statische Route für PDF-Downloads
app.mount("/downloads", StaticFiles(directory="downloads"), name="downloads")

origins = [
    "https://make.ki-sicherheit.jetzt",
    "http://localhost",
    "http://localhost:3000",
    "http://127.0.0.1:8000"
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")

@app.post("/briefing")
async def create_briefing(request: Request):
    data = await request.json()
    print("🚀 Empfangenes JSON:", data)

    # GPT-Analyse (mehrstufig)
    gpt_result = analyze_briefing(data)
    print("✅ GPT-Ergebnis:", gpt_result)

    # HTML-Report generieren
    html_content = templates.get_template("pdf_template.html").render(**gpt_result)

    # PDF erzeugen
    pdf_filename = create_pdf(html_content)
    pdf_url = f"/downloads/{pdf_filename}"

    return JSONResponse(content={"html": html_content, "pdf_url": pdf_url})

@app.get("/")
async def root():
    return {"message": "KI-Readiness Server läuft!"}
