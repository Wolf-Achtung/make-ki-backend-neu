from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from jinja2 import Template

from gpt_analyze import generate_report
from pdf_export import create_pdf_from_template

import os
import markdown
import re

app = FastAPI()

app.mount("/downloads", StaticFiles(directory="downloads"), name="downloads")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://make.ki-sicherheit.jetzt"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")

def extract_sections(markdown_text):
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
        "BRANCHE": "",
        "CHECKLISTEN": "",
        "SCORE_VISUALISIERUNG": "",
        "PRAXISBEISPIELE": "",
        "FOERDERMITTEL_TAB": "",
        "FOERDERMITTEL_MD": ""
    }
    patterns = {
        "EXEC_SUMMARY": r"## Executive Summary[^\n]*\n+(.*?)(?=\n##|\Z)",
        "BENCHMARK": r"## Branchenvergleich[^\n]*\n+(.*?)(?=\n##|\Z)",
        "COMPLIANCE": r"## Compliance[^\n]*\n+(.*?)(?=\n##|\Z)",
        "INNOVATION": r"## Innovation[^\n]*\n+(.*?)(?=\n##|\Z)",
        "VISION": r"## Ihre Zukunft mit KI[^\n]*\n+(.*?)(?=\n##|\Z)",
        "GLOSSAR": r"## Glossar[^\n]*\n+(.*?)(?=(##|\Z))",
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

    if not data.get("datenschutz_ok"):
        return JSONResponse({"error": "Datenschutzerklärung nicht akzeptiert."}, status_code=400)

    # GPT-Analyse
    try:
        report_markdown = generate_report(data)
        print("✅ GPT-Report (Markdown):", report_markdown[:600])
    except Exception as e:
        print(f"❌ Fehler bei GPT-Analyse: {e}")
        return JSONResponse({"error": f"GPT-Analyse fehlgeschlagen: {str(e)}"}, status_code=500)

    sections = extract_sections(report_markdown)
    sections["KI_SCORE"] = data.get("ki_score", "—")
    sections["DATUM"] = data.get("datum", "")
    sections["UNTERNEHMEN"] = data.get("unternehmen", "")
    sections["BRANCHE"] = data.get("branche", "")

    # HTML-Template laden
    try:
        with open("templates/pdf_template.html", encoding="utf-8") as f:
            template = Template(f.read())
        html_content = template.render(**sections)
    except Exception as e:
        print(f"❌ Fehler beim Rendern des Templates: {e}")
        return JSONResponse({"error": f"Template-Rendering fehlgeschlagen: {str(e)}"}, status_code=500)

    # PDF erzeugen
    try:
        pdf_filename = create_pdf_from_template(
            html_content,
            sections.get("EXEC_SUMMARY", ""),
            sections.get("KI_SCORE", ""),
            sections.get("BENCHMARK", ""),
            sections.get("COMPLIANCE", ""),
            sections.get("INNOVATION", ""),
            sections.get("TOOLS", ""),
            sections.get("VISION", ""),
            sections.get("CHECKLISTEN", ""),
            sections.get("SCORE_VISUALISIERUNG", ""),
            sections.get("PRAXISBEISPIELE", ""),
            sections.get("FOERDERMITTEL_TAB", ""),
            sections.get("FOERDERMITTEL_MD", ""),
            sections.get("GLOSSAR", ""),
            sections.get("FAQ", ""),
            sections.get("TOOLS_COMPACT", ""),
            copyright_text="© KI-Sicherheit.jetzt | TÜV-zertifiziertes KI-Management: Wolf Hohl 2025"
        )
    except Exception as e:
        print(f"❌ Fehler beim PDF-Export: {e}")
        return JSONResponse({"error": f"PDF-Export fehlgeschlagen: {str(e)}"}, status_code=500)

    # Hier absolute URL zurückgeben
    pdf_url = f"https://make-ki-backend-neu-production.up.railway.app/downloads/{pdf_filename}"
    return JSONResponse(content={"html": html_content, "pdf_url": pdf_url})

@app.get("/")
async def root():
    return {"message": "KI-Readiness Server läuft!"}
