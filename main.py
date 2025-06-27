from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import os
import httpx
from gpt_analyze import analyze_payload
from html_generator import generate_html

app = FastAPI()
templates = Jinja2Templates(directory=".")

# === Upload-Seite anzeigen ===
@app.get("/upload-template", response_class=HTMLResponse)
async def get_upload_page(request: Request):
    return templates.TemplateResponse("placid-upload.html", {"request": request})

# === Template-Upload verarbeiten ===
@app.post("/upload-template")
async def upload_template(template: UploadFile = File(...)):
    content = await template.read()
    with open("template.html", "wb") as f:
        f.write(content)
    return {"status": "success", "filename": template.filename}

# === Analyse & PDF-Generierung ===
@app.post("/analyze")
async def analyze(request: Request):
    data = await request.json()
    gpt_result = analyze_payload(data)
    html_content = generate_html(data, gpt_result)

    headers = {
        "Authorization": f"Bearer {os.getenv('PDFMONKEY_API_KEY')}",
        "Content-Type": "application/json"
    }

    payload = {
        "document": {
            "document_type": "html",
            "content": html_content
        }
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.pdfmonkey.io/api/v1/documents",
            json=payload,
            headers=headers
        )

    if response.status_code == 201:
        url = response.json().get("data", {}).get("download_url", "")
        return JSONResponse({"status": "success", "download_url": url})
    else:
        return JSONResponse({"status": "error", "details": response.text}, status_code=500)

# === Root Route für Funktionsprüfung ===
@app.get("/")
async def root():
    return {"message": "KI-Briefing Backend läuft ✅"}
