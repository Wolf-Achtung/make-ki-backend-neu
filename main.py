from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates

app = FastAPI()

# CORS offen für Tests, später auf Domain einschränken
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")

@app.post("/briefing", response_class=HTMLResponse)
async def create_briefing(request: Request):
    data = await request.json()
    print("📦 Empfangenes JSON:", data)  # Debug-Output

    # Direkte HTML-Response mit dem Template
    return templates.TemplateResponse("report_template.html", {
        "request": request,
        **data
    })
