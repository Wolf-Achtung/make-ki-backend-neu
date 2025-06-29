from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging
from gpt_analyze import generate_briefing

# Logging schöner formatieren
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # für Tests
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/healthz")
async def health():
    logging.info("Health check OK")
    return {"status": "ok"}

@app.post("/briefing")
async def briefing(request: Request):
    data = await request.json()
    logging.info(f"Received data: {data}")

    # GPT-Analyse
    result = generate_briefing(data)
    logging.info(f"GPT result: {result}")

    return {"result": result}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
