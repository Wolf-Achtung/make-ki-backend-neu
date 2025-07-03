from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from gpt_analyze import analyze_with_gpt
from validate_response import validate_gpt_response
from pdf_export import create_pdf_and_upload
from check_sync import check_sync

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        pdf_url = create_pdf_and_upload(result)

        return {
            "pdf_url": pdf_url,
            "score": result["compliance_score"],
            "badge": result["badge_level"]
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
