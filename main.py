from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pdf_export import create_pdf
import os

app = FastAPI()

# CORS Middleware für ALLE Domains ("*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # später kannst du hier z.B. ["https://make.ki-sicherheit.jetzt"] eintragen
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/briefing")
async def create_briefing(request: Request):
    try:
        data = await request.json()
        filename = create_pdf(data)
        return JSONResponse(content={"filename": filename})
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/download/{filename}")
async def download_file(filename: str):
    file_path = os.path.join("downloads", filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type='application/pdf', filename=filename)
    else:
        return JSONResponse(content={"error": "File not found"}, status_code=404)

@app.get("/")
async def root():
    return {"message": "Backend läuft!"}
