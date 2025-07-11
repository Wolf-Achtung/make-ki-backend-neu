import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from dotenv import load_dotenv

from gpt_analyze import analyze_full_report
from pdf_export import export_pdf

import tempfile
import uuid

load_dotenv()

# Konfiguration
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://make.ki-sicherheit.jetzt, http://localhost:8888").split(",")

app = FastAPI()

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

@app.get("/health")
def healthcheck():
    return {"status": "ok"}

@app.post("/briefing")
async def create_briefing(request: Request):
    try:
        data = await request.json()
        print("[INFO] Neue Anfrage erhalten")
        print("[INFO] Daten:", data)

        # NEU: Wir gehen immer von Value-Keys aus (siehe Formbuilder!)
        # Analyse starten (returns dict mit Texten etc.)
        report_data = analyze_full_report(data)
        print("[INFO] Analyse abgeschlossen")

        # --- Ergänze alle Platzhalter für das PDF-Template ---
        placeholder_keys = [
            "ScoreVisualisierung",
            "tools_tabelle",
            "benchmark_diagramm",
            "benchmark_tabelle",
            "checklisten",
            "score_percent"   # <-- Nur diese Zeile ist NEU!
        ]
        for key in placeholder_keys:
            report_data.setdefault(key, "")

        # ScoreVisualisierung notfalls dynamisch aus score_percent füllen
        if not report_data["ScoreVisualisierung"]:
            report_data["ScoreVisualisierung"] = f"<b>Score: {report_data['score_percent']}%</b>"
        if report_data["score_percent"] == "":
            report_data["score_percent"] = 0

        # PDF generieren (gibt Pfad zurück)
        pdf_path = export_pdf(report_data)
        print("[INFO] PDF erstellt:", pdf_path)

        # Download-Link erzeugen
        return JSONResponse({"pdf_url": f"/download/{os.path.basename(pdf_path)}"})

    except Exception as e:
        print("[ERROR] Fehler beim Erstellen des Reports:", str(e))
        return JSONResponse({"error": str(e)}, status_code=500)

# Download-Endpoint für PDFs
@app.get("/download/{pdf_file}")
def download(pdf_file: str):
    file_path = os.path.join(tempfile.gettempdir(), pdf_file)
    if os.path.exists(file_path):
        return FileResponse(path=file_path, media_type='application/pdf', filename=pdf_file)
    return JSONResponse({"error": "Datei nicht gefunden"}, status_code=404)
