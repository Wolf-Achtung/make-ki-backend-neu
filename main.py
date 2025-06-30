from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from gpt_analyze import analyze_with_gpt
from check_sync import check_sync  # <--- NEU

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
        result = await analyze_with_gpt(data)
        return result
    except Exception as e:
        return {"error": str(e)}

@app.get("/sync-check")  # <--- NEU
async def run_sync_check():
    return check_sync()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
