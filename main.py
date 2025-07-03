from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pdf_export import create_pdf
import os

app = FastAPI()

# Jinja2 Template-Umgebung
env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape()
)

# Ordner für Downloads sicherstellen
os.makedirs("downloads", exist_ok=True)

# StaticFiles einbinden, damit /download/... funktioniert
app.mount("/download", StaticFiles(directory="downloads"), name="downloads")

# CORS
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
        
        # Template laden & rendern
        template = env.get_template("pdf_template.html")
        html_content = template.render(**data)
        
        # Jetzt den HTML-String an create_pdf geben
        filename = create_pdf(html_content)
        
        return {"filename": filename, "download_url": f"/download/{filename}"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
