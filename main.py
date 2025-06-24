from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json
import httpx

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/analyze")
async def analyze(request: Request):
    try:
        raw_body = await request.body()
        json_data = json.loads(raw_body.decode("utf-8"))
    except Exception as e:
        print("Fehler beim JSON-Parsing:", e)
        raise HTTPException(status_code=400, detail=str(e))

    # Debug-Ausgabe mit Feldinhalten
    print("--- ANALYZE-EINGANG ---")
    for key, value in json_data.items():
        print(f"{key}: {value}")

    # Beispiel: Score-basiertes Rating
    score = int(json_data.get("score", 0))
    if score >= 80:
        status = "Fortgeschritten"
    elif score >= 50:
        status = "Solide Basis"
    else:
        status = "Einsteiger"

    # Beispiel-Auswertung (hier noch simpel, kann ersetzt werden)
    result = {
        "name": json_data.get("name"),
        "unternehmen": json_data.get("unternehmen"),
        "email": json_data.get("email"),
        "datum": json_data.get("datum"),
        "score": score,
        "status": status,
        "bewertung": "Individuelle Bewertung folgt...",
        "executive_summary": "Zusammenfassung wird generiert...",
        "analyse": "Auswertung in Arbeit...",
        "empfehlung1": {
            "titel": "KI starten",
            "beschreibung": "Pilotprojekt beginnen",
            "next_step": "Use Case definieren",
            "tool": "ChatGPT"
        },
        "empfehlung2": {
            "titel": "Prozesse automatisieren",
            "beschreibung": "Kleine repetitive Aufgaben automatisieren",
            "next_step": "Toolauswahl",
            "tool": "Make"
        },
        "empfehlung3": {
            "titel": "Team stärken",
            "beschreibung": "Mitarbeiter schulen",
            "next_step": "Workshop planen",
            "tool": "aiCampus"
        },
        "roadmap": {
            "kurzfristig": "Start",
            "mittelfristig": "Standardisierung",
            "langfristig": "Transformation"
        },
        "ressourcen": "aiCampus, BMWK Förderkompass",
        "zukunft": "Große Chancen durch KI",
        "rueckfrage1": "Wer betreut die KI intern?",
        "rueckfrage2": "Welche KPIs sind relevant?",
        "rueckfrage3": "Wie messen wir Erfolg?",
        "foerdertipp1": {
            "programm": "go-digital",
            "zielgruppe": "KMU",
            "nutzen": "50% Förderung"
        },
        "foerdertipp2": {
            "programm": "digital jetzt",
            "zielgruppe": "Mittelstand",
            "nutzen": "bis zu 100.000€ Förderung"
        },
        "risikoprofil": {
            "risikoklasse": "Moderat",
            "begruendung": "KI mit Nutzerdaten",
            "pflicht1": "Transparenz",
            "pflicht2": "Aufklärung"
        },
        "tooltipps": {
            "tool1_name": "Notion AI",
            "tool1_einsatz": "Text-Ideen",
            "tool1_warum": "Einfach nutzbar",
            "tool2_name": "Runway",
            "tool2_einsatz": "Video-KI",
            "tool2_warum": "Visuelle Qualität"
        },
        "branchenvergleich": "Sie liegen im Mittelfeld",
        "trendreport": "Große Nachfrage nach KI-Basics",
        "vision": "Verdopplung der Effizienz"
    }

    # Webhook an Make senden
    make_webhook_url = "https://hook.eu2.make.com/gxydz1j89buq91wl1o26noto0eciax5h"
    try:
        webhook_response = httpx.post(make_webhook_url, json=result)
        print("Webhook an Make gesendet. Status:", webhook_response.status_code)
    except Exception as e:
        print("Fehler beim Senden an Make:", e)

    return {"message": "Analyse abgeschlossen", "data": result}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
