from fastapi import FastAPI, Request
from validate_response import validate_gpt_response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from gpt_analyze import analyze_with_gpt
from check_sync import check_sync  # <--- NEU
from pdf_export import create_pdf
from fastapi.responses import FileResponse, JSONResponse
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/briefing")
async def generate_briefing(request: Request):
    data = await request.json()
    try:
        result = analyze_with_gpt(data)
        validate_gpt_response(result)
        
        # PDF erstellen
        pdf_path = create_pdf(result)
        
        # URL zurückgeben (z. B. für deine Thankyou-Page)
        return {
            "pdf_url": f"/{pdf_path}",
            "score": result["compliance_score"],
            "badge": result["badge_level"]
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/sync-check")  # <--- NEU
async def run_sync_check():
    return check_sync()

@app.get("/download/{filename}")
async def download_pdf(filename: str):
    if not filename.lower().endswith(".pdf"):
        return JSONResponse(status_code=400, content={"error": "Nur PDF-Downloads erlaubt."})
    
    file_path = os.path.join("downloads", filename)
    
    if not os.path.isfile(file_path):
        return JSONResponse(status_code=404, content={"error": f"Datei '{filename}' nicht gefunden."})
    
    return FileResponse(path=file_path, filename=filename, media_type='application/pdf')

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
