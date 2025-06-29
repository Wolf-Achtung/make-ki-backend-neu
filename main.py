from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import logging
from gpt_analyze import generate_briefing

logging.basicConfig(level=logging.INFO)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/healthz")
def health_check():
    return {"status": "ok"}

@app.post("/briefing")
async def create_briefing(request: Request):
    data = await request.json()
    logging.info(f"Received input data: {data}")
    result = generate_briefing(data)
    logging.info(f"Generated briefing: {result}")
    return {"briefing": result}
