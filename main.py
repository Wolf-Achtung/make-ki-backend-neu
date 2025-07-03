from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from jinja2 import Environment, FileSystemLoader, select_autoescape
import os

from pdf_export import create_pdf

app = FastAPI()

# Nur deine Domain erlauben
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://make.ki-sicherheit.jetzt"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Jinja2-Umgebung konfigurieren
templates_env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape()
)

@app.post("/briefing")
async def create_briefing(request: Request):
    try:
        data = await request.json()
        
        # Template laden und mit Daten rendern
        template = templates_env.get_template("pdf_template.html")
        html_content = template.render(**data)
        
        # PDF erstellen
        filename = create_pdf(html_content)
        
        return {"filename": filename}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/download/{filename}")
async def download_file(filename: str):
    file_path = os.path.join("downloads", filename)
    if os.path.exists(file_path):
        return FileResponse(path=file_path, filename=filename, media_type='application/pdf')
    return JSONResponse(status_code=404, content={"error": "File not found"})
