from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from gpt_analyze import generate_briefing
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ki-cert")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.post("/briefing")
async def briefing(request: Request):
    data = await request.json()
    logger.info("Empfangene Daten: %s", data)
    result = generate_briefing(data)
    logger.info("GPT-Antwort: %s", result)
    return {"result": result}