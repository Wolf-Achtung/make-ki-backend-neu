from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "KI-Check API läuft"}

@app.post("/analyze")
async def analyze(request: Request):
    data = await request.json()
    print("Empfangene Daten:", data)

    return {
        "name": "Max Mustermann",
        "unternehmen": "Beispiel GmbH",
        "branche": "Marketing",
        "email": "max@example.de",
        "datum": "2025-06-23",
        "score": "82",
        "status": "Fortgeschritten",
        "bewertung": "Gute Grundlagen, punktuell optimierbar",
        "executive_summary": "Kurzfassung der Bewertung...",
        "analyse": "Ausführliche Analyse...",

        "empfehlung1": {
            "titel": "KI starten",
            "beschreibung": "Pilotprojekt beginnen",
            "next_step": "Use Case definieren",
            "tool": "ChatGPT"
        },
        "empfehlung2": {
            "titel": "Kleine Prozesse automatisieren",
            "beschreibung": "Identifizieren Sie einfache Automatisierungen",
            "next_step": "Tool auswählen",
            "tool": "Make.com"
        },
        "empfehlung3": {
            "titel": "Team befähigen",
            "beschreibung": "Kompetenzzentren aufbauen",
            "next_step": "Schulung starten",
            "tool": "aiCampus"
        },

        "roadmap": {
            "kurzfristig": "Start",
            "mittelfristig": "Standards etablieren",
            "langfristig": "Transformation"
        },

        "ressourcen": "Plattformen wie aiCampus",
        "zukunft": "Sie sind auf gutem Kurs",

        "rueckfrage1": "Wie beginnen?",
        "rueckfrage2": "Welche Tools zuerst?",
        "rueckfrage3": "Wie integrieren wir das Team?",

        "foerdertipp1": {
            "programm": "go-digital",
            "zielgruppe": "KMU",
            "nutzen": "50% Förderung"
        },
        "foerdertipp2": {
            "programm": "Digital Jetzt",
            "zielgruppe": "Mittelstand",
            "nutzen": "Investitionsförderung"
        },

        "risikoprofil": {
            "risikoklasse": "Moderat",
            "begruendung": "KI mit Nutzerdaten"
        },
        "risikopflicht1": "Schulung",
        "risikopflicht2": "Transparenz",

        "tooltipp1": {
            "name": "Zapier",
            "einsatz": "Automatisierung",
            "warum": "Einfache Anbindung"
        },
        "tooltipp2": {
            "name": "Notion AI",
            "einsatz": "Texterstellung",
            "warum": "Intuitive Nutzung"
        },

        "branchenvergleich": "Sie liegen im Mittelfeld",
        "trendreport": "Große Nachfrage nach KI-Basics",
        "vision": "Verdopplung der Effizienz"
    }
