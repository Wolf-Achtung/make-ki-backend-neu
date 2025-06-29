from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from gpt_analyze import analyze
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()

# 🚀 CORS vollständig freischalten (für deine Tests)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/briefing")
async def create_briefing(request: Request):
    data = await request.json()
    logger.info(f"Empfangenes JSON: {data}")

    result = analyze(data)
    logger.info(f"GPT-Auswertung:\n{result}")

    return {"briefing": result}


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

