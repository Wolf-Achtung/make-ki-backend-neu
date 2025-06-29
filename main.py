from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from gpt_analyze import analyze_with_gpt
import logging

# Logging Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ki-check")

# FastAPI App
app = FastAPI()

# CORS aktivieren
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # oder ["https://make-ki-sicherheit.jetzt"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Healthcheck Endpoint
@app.get("/healthz")
def health_check():
    logger.info("Healthcheck aufgerufen.")
    return {"status": "ok"}

# Briefing Endpoint
@app.post("/briefing")
async def generate_briefing(request: Request):
    data = await request.json()
    logger.info(f"Empfangene Daten: {data}")

    try:
        result = analyze_with_gpt(data)
        logger.info(f"GPT-Antwort: {result}")
        return {"success": True, "briefing": result}
    except Exception as e:
        logger.error(f"Fehler bei GPT-Analyse: {e}")
        return {"success": False, "error": str(e)}
