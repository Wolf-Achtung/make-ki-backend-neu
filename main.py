from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Template
import json
import os

from gpt_analyze import analyze_full_report
from pdf_export import create_pdf_from_template

app = FastAPI()

app.mount("/downloads", StaticFiles(directory="downloads"), name="downloads")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://make.ki-sicherheit.jetzt",
        "http://localhost",
        "http://127.0.0.1"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/briefing")
async def create_briefing(request: Request):
    try:
        data = await request.json()
    except Exception as e:
        return JSONResponse({"error": f"Ungültiges JSON: {str(e)}"}, status_code=400)

    print("🚀 Empfangenes JSON:", json.dumps(data, ensure_ascii=False, indent=2))

    if not data.get("datenschutz_ok"):
        return JSONResponse({"error": "Datenschutzerklärung nicht akzeptiert."}, status_code=400)

    # GPT Analyse
    try:
        report_data = analyze_full_report(data)
        print("✅ GPT-Report-Data:", json.dumps(report_data, indent=2)[:800])
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
        pdf_filename = create_pdf_from_template(html_content)
    except Exception as e:
        print(f"❌ Fehler beim PDF-Export: {e}")
        return JSONResponse({"error": f"PDF-Export fehlgeschlagen: {str(e)}"}, status_code=500)

    pdf_url = f"https://make-ki-backend-neu-production.up.railway.app/downloads/{pdf_filename}"
    return JSONResponse(content={"html": html_content, "pdf_url": pdf_url})

@app.get("/")
async def root():
    return {"message": "KI-Readiness Backend läuft!"}
