
import json
from fastapi import FastAPI, Request
from pydantic import BaseModel
from fastapi.responses import JSONResponse

app = FastAPI()

class KIInput(BaseModel):
    unternehmen: str
    name: str
    email: str
    datum: str
    branche: str
    selbststaendig: str

@app.post("/analyze")
async def analyze(input: KIInput):
    # Simulierter GPT-Antwort-Block
    response = {
        "score": "7/10",
        "status": "Fortschrittlich",
        "bewertung": "Solide KI-Strategie mit kleinen Schwächen.",
        "executive_summary": "KI bietet hier hohes Potenzial.",
        "analyse": "Gute Basis, Fokus auf Integration ausbauen.",
        "empfehlungen": [
            {
                "titel": "Pilot starten",
                "beschreibung": "Start mit MVP in einem Bereich.",
                "next_step": "Use Case auswählen",
                "tool": "ChatGPT"
            }
        ],
        "roadmap": {
            "kurzfristig": "Start MVP",
            "mittelfristig": "Skalieren auf Abteilungen",
            "langfristig": "KI als Standard"
        },
        "ressourcen": "aiCampus, BMWK Förderkompass",
        "zukunft": "Steigerung der Effizienz und Qualität",
        "rueckfragen": ["Wer betreut die KI intern?"],
        "foerdertipps": [
            {
                "programm": "go-digital",
                "nutzen": "Fördert Implementierung",
                "zielgruppe": "KMU"
            }
        ],
        "risikoprofil": {
            "risikoklasse": "Moderat",
            "begruendung": "Datenschutz relevant",
            "pflichten": ["Transparenz", "Aufklärung"]
        },
        "tooltipps": [
            {
                "name": "Notion AI",
                "einsatz": "Textideen",
                "warum": "Einfache Nutzung"
            }
        ],
        "branchenvergleich": "Über dem Durchschnitt.",
        "trendreport": "KI in Content & Support.",
        "vision": "KI als Wettbewerbsvorteil."
    }
    return JSONResponse(content=response)

@app.get("/")
async def root():
    return {"status": "OK"}

