from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import logging
from gpt_analyze import generate_briefing

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.post("/briefing")
async def create_briefing(request: Request):
    data = await request.json()
    logging.info(f"Received data: {data}")
    result = generate_briefing(data)
    logging.info(f"GPT result: {result}")
    return {"briefing": result}
