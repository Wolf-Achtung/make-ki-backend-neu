from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Template

from gpt_analyze import analyze_full_report
from pdf_export import create_pdf_from_template

import json
import os

app = FastAPI()

app.mount("/downloads", StaticFiles(directory="downloads"), name="downloads")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://make.ki-sicherheit.jetzt"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/briefing")
async def create_briefing(request: Request):
    data = await request.json()
    print("🚀 Empfangenes JSON:", data)

    if not data.get("datenschutz_ok"):
        return JSONResponse({"error": "Datenschutzerklärung nicht akzeptiert."}, status_code=400)

    # GPT + Markdown Analyse
    try:
        report_data = analyze_full_report(data)
        print("✅ GPT-Report-Data:", json.dumps(report_data, indent=2)[:600])
    except Exception as e:
        print(f"❌ Fehler bei GPT-Analyse: {e}")
        return JSONResponse({"error": f"GPT-Analyse fehlgeschlagen: {str(e)}"}, status_code=500)

    # HTML rendern
    try:
        with open("templates/pdf_template.html", encoding="utf-8") as f:
            template = Template(f.read())
        html_content = template.render(**report_data)
    except Exception as e:
        print(f"❌ Fehler beim Rendern des Templates: {e}")
        return JSONResponse({"error": f"Template-Rendering fehlgeschlagen: {str(e)}"}, status_code=500)

    # PDF erzeugen
    try:
        pdf_filename = create_pdf_from_template(
            html_content,
            report_data.get("summary", ""),
            report_data.get("check_readiness", ""),
            report_data.get("check_compliance", ""),
            report_data.get("check_ds", ""),
            report_data.get("innovation", ""),
            report_data.get("tools", ""),
            report_data.get("roadmap", ""),
            report_data.get("check_roadmap", ""),
            report_data.get("score_vis", ""),
            report_data.get("praxis", ""),
            report_data.get("check_foerder", ""),
            report_data.get("foerder_programme", ""),
            report_data.get("foerder", ""),
            report_data.get("compliance", ""),
            report_data.get("check_inno", ""),
            copyright_text="© KI-Sicherheit.jetzt | TÜV-zertifiziertes KI-Management: Wolf Hohl 2025"
        )
    except Exception as e:
        print(f"❌ Fehler beim PDF-Export: {e}")
        return JSONResponse({"error": f"PDF-Export fehlgeschlagen: {str(e)}"}, status_code=500)

    pdf_url = f"https://make-ki-backend-neu-production.up.railway.app/downloads/{pdf_filename}"
    return JSONResponse(content={"html": html_content, "pdf_url": pdf_url})

@app.get("/")
async def root():
    return {"message": "KI-Readiness Server läuft!"}
