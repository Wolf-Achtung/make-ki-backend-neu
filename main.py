import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from dotenv import load_dotenv

from gpt_analyze import analyze_full_report
from pdf_export import export_pdf

load_dotenv()

# --- CORS-Konfiguration ---
ALLOWED_ORIGINS = [
    "https://make.ki-sicherheit.jetzt",
    "http://localhost",
    "http://127.0.0.1"
]

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
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

        # Analyse starten (liefert dict mit allen Report-Abschnitten)
        print("### DEBUG: Starte analyze_full_report()")
        report_data = analyze_full_report(data)
        print("[DEBUG] report_data nach analyze_full_report:", report_data)
        print("[INFO] Analyse abgeschlossen")

        # --- Platzhalter für PDF-Template sicherstellen ---
        placeholder_keys = [
            "ScoreVisualisierung",
            "tools_tabelle",
            "benchmark_diagramm",
            "benchmark_tabelle",
            "checklisten",
            "score_percent"
        ]
        for key in placeholder_keys:
            report_data.setdefault(key, "")

        if not report_data["ScoreVisualisierung"]:
            report_data["ScoreVisualisierung"] = f"<b>Score: {report_data['score_percent']}%</b>"
        if report_data["score_percent"] == "":
            report_data["score_percent"] = 0

        print("### DEBUG: report_data für PDF-Export bereit:", report_data.keys())

        # --- PDF erstellen: Speichert IMMER im "downloads"-Ordner ---
        pdf_path = export_pdf(report_data)
        print("[INFO] PDF erstellt:", pdf_path)
        print("### DEBUG: pdf_path returned by export_pdf:", pdf_path)
        print("### DEBUG: Existiert Datei wirklich?", os.path.exists(pdf_path))

        # --- Download-Link zurückgeben ---
        return JSONResponse({"pdf_url": f"/download/{os.path.basename(pdf_path)}"})

    except Exception as e:
        print("[ERROR] Fehler beim Erstellen des Reports:", str(e))
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)

# --- Download-Endpoint für PDFs ---
@app.get("/download/{pdf_file}")
def download(pdf_file: str):
    downloads_dir = os.path.join(os.path.dirname(__file__), "downloads")
    file_path = os.path.join(downloads_dir, pdf_file)
    print("### DEBUG: Download-Request für", file_path)
    if os.path.exists(file_path):
        print("### DEBUG: Datei gefunden und wird ausgeliefert")
        return FileResponse(path=file_path, media_type='application/pdf', filename=pdf_file)
    print("### DEBUG: Datei nicht gefunden!")
    return JSONResponse({"error": "Datei nicht gefunden"}, status_code=404)
