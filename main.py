from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import logging
from gpt_analyze import generate_briefing

app = FastAPI()

# CORS erlauben
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Templates
templates = Jinja2Templates(directory="templates")

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

# Index-Seite
@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# POST /briefing
@app.post("/briefing")
async def briefing(request: Request):
    data = await request.json()
    logger.info(f"Empfangene Daten: {data}")
    result = await generate_briefing(data)
    logger.info(f"GPT-Antwort: {result}")
    return JSONResponse(content={"briefing": result})
