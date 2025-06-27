
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from gpt_analyze import analyze_with_gpt
import uvicorn

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/briefing")
async def generate_briefing(request: Request):
    try:
        data = await request.json()
        result = analyze_with_gpt(data)
        return result
    except Exception as e:
        return {"error": str(e)}


@app.get("/briefing")
def dummy_briefing():
    return {
        "executive_summary": "Dies ist eine Beispiel-Auswertung.",
        "fördertipps": "Nutzen Sie Förderprogramme von Bund und Land.",
        "toolkompass": "Empfohlene Tools: ChatGPT, Notion, Zapier.",
        "branche_trend": "In Ihrer Branche sind Automatisierung und KI die wichtigsten Trends.",
        "compliance": "Beachten Sie DSGVO und EU-AI-Act.",
        "beratungsempfehlung": "Lassen Sie sich zu Datenschutz und Prozessautomatisierung beraten.",
        "vision": "Ein visionärer Ausblick: Ihre Prozesse laufen bald fast vollautomatisiert."
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
