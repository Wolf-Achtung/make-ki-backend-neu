from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from jinja2 import Environment, FileSystemLoader
from datetime import datetime
import os

from gpt_analyze import analyze_with_gpt
from validate_response import validate_gpt_response
from pdf_export import create_pdf
from check_sync import check_sync

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

env = Environment(loader=FileSystemLoader("templates"))

@app.get("/health")
async def health():
    return {"status": "ok", "message": "Backend läuft stabil."}

@app.get("/sync-check")
async def sync_check():
    return check_sync()

@app.post("/briefing")
async def generate_briefing(request: Request):
    data = await request.json()
    print("📥 Formulardaten empfangen:", data)
    try:
        result = analyze_with_gpt(data)
        result = validate_gpt_response(result)

        # PDF erzeugen
        html_content = env.get_template("pdf_template.html").render(**result)
        filename = f"KI-Readiness-{datetime.now().strftime('%Y%m%d-%H%M%S')}.pdf"
        filepath = create_pdf(html_content, filename)

        return {
            "pdf_url": f"/download/{filename}",
            "score": result["compliance_score"],
            "badge": result["badge_level"]
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/download/{filename}")
async def download_file(filename: str):
    file_path = os.path.join("downloads", filename)
    if os.path.exists(file_path):
        return FileResponse(path=file_path, filename=filename, media_type='application/pdf')
    return JSONResponse(status_code=404, content={"error": "File not found"})
