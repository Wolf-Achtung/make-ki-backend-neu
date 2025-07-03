from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pdf_export import create_pdf
import os

app = FastAPI()

# Ordner für Downloads sicherstellen
os.makedirs("downloads", exist_ok=True)

# StaticFiles einbinden, damit /download/... funktioniert
app.mount("/download", StaticFiles(directory="downloads"), name="downloads")

# CORS für dein Frontend oder global öffnen
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # oder ["https://make.ki-sicherheit.jetzt"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/briefing")
async def generate_briefing(request: Request):
    try:
        data = await request.json()
        filename = create_pdf(data)  # pdf_export.py erstellt und speichert PDF
        return {"filename": filename, "download_url": f"/download/{filename}"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
