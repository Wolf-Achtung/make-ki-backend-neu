from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pdf_export import create_pdf
import os

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Statischer Ordner für Downloads
app.mount("/download", StaticFiles(directory="downloads"), name="download")

@app.post("/briefing")
async def generate_briefing(request: Request):
    data = await request.json()
    print("Empfangene Daten:", data)

    # Template rendern
    html_content = templates.get_template("briefing_dynamic.html").render(data=data)

    # PDF erstellen
    filename = create_pdf(html_content)

    # URL zurückgeben
    download_url = f"/download/{filename}"
    return {"download_url": download_url}

# Test-Route zum manuellen Aufruf
@app.get("/")
def root():
    return {"message": "KI-Readiness-Backend läuft!"}
