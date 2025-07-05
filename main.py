from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from jinja2 import Template

from gpt_analyze import generate_report
from pdf_export import create_pdf

import os
import markdown
import re

app = FastAPI()

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

def extract_sections(markdown_text):
    """
    Extrahiert die wichtigsten Abschnitte aus dem Markdown-Report.
    Gibt ein Dict für die Template-Platzhalter zurück.
    """
    sections = {
        "EXEC_SUMMARY": "",
        "BENCHMARK": "",
        "COMPLIANCE": "",
        "INNOVATION": "",
        "VISION": "",
        "GLOSSAR": "",
        "FAQ": "",
        "TOOLS": "",
        "TOOLS_COMPACT": "",
        "KI_SCORE": "",
        "DATUM": "",
        "UNTERNEHMEN": "",
        "BRANCHE": ""
    }
    # Einfache Regex für Abschnitte
    patterns = {
        "EXEC_SUMMARY": r"## Executive Summary[^\n]*\n+(.*?)(?=\n##|\Z)",
        "BENCHMARK": r"## Branchenvergleich[^\n]*\n+(.*?)(?=\n##|\Z)",
        "COMPLIANCE": r"## Compliance[^\n]*\n+(.*?)(?=\n##|\Z)",
        "INNOVATION": r"## Innovation[^\n]*\n+(.*?)(?=\n##|\Z)",
        "VISION": r"## Ihre Zukunft mit KI[^\n]*\n+(.*?)(?=\n##|\Z)",
        "GLOSSAR": r"## Glossar[^\n]*\n+(.*?)(?=(##|\Z))",
        # Optional weitere: FAQ, Tools, etc.
    }
    for key, pat in patterns.items():
        match = re.search(pat, markdown_text, re.DOTALL)
        if match:
            sections[key] = markdown.markdown(match.group(1), extensions=['tables', 'fenced_code', 'smarty'])
    return sections

@app.post("/briefing")
async def create_briefing(request: Request):
    data = await request.json()
    print("🚀 Empfangenes JSON:", data)

    # GPT-Analyse
    report_markdown = generate_report(data)
    print("✅ GPT-Report (Markdown):", report_markdown[:600])  # Preview

    # Extrahiere Abschnitte für Template
    sections = extract_sections(report_markdown)

    # Werte für KI-Score etc. (berechne ggf. in gpt_analyze.py, oder ziehe aus Report)
    sections["KI_SCORE"] = data.get("ki_score", "—")
    sections["DATUM"] = data.get("datum", "")
    sections["UNTERNEHMEN"] = data.get("unternehmen", "")
    sections["BRANCHE"] = data.get("branche", "")

    # Lade dein HTML-Template
    with open("pdf_template.html", encoding="utf-8") as f:
        template = Template(f.read())
    html_content = template.render(**sections)

    # PDF erzeugen
    pdf_filename = create_pdf(html_content)
    pdf_url = f"/downloads/{pdf_filename}"

    return JSONResponse(content={"html": html_content, "pdf_url": pdf_url})

@app.get("/")
async def root():
    return {"message": "KI-Readiness Server läuft!"}
