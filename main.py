from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()

# CORS offen für deine Website
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

    # Render das HTML mit den Daten
    html_content = templates.get_template("pdf_template.html").render(**data)

    return JSONResponse(content={"html": html_content})

@app.get("/")
async def root():
    return {"message": "KI-Readiness Server läuft!"}
