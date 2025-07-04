from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

# ➔ NEU: Importiere die GPT-Logik & Validierung
from gpt_analyze import analyze_with_gpt
from validate_response import validate_gpt_response

app = FastAPI()

origins = [
    "https://make.ki-sicherheit.jetzt",
    "http://localhost",
    "http://localhost:3000",
    "http://127.0.0.1:8000"
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")

@app.post("/briefing")
async def create_briefing(request: Request):
    data = await request.json()
    print("🚀 Empfangenes JSON:", data)

    # ➔ NEU: GPT-Analyse aufrufen und Ergebnis validieren
    gpt_result = analyze_with_gpt(data)
    gpt_result = validate_gpt_response(gpt_result)

    # Render das HTML mit den GPT-Resultaten
    html_content = templates.get_template("pdf_template.html").render(**gpt_result)

    return JSONResponse(content={"html": html_content})

@app.get("/")
async def root():
    return {"message": "KI-Readiness Server läuft!"}
