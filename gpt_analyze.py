from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
import json

app = FastAPI()
client = OpenAI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/briefing")
async def analyze_with_gpt(request: Request):
    data = await request.json()

    prompt = f"""
    Sie sind ein professioneller KI- und Digital-Advisor. Erstellen Sie auf Basis dieser Angaben eine tiefgehende Analyse, inklusive Risiko & Haftung, DSGVO / AI-Act Einschätzung, Executive Summary, Readiness & Strategie, Compliance & Datenschutz, Branchenvergleich, Branchentrends & Benchmarks, Use Cases & Innovation, ROI-Analyse, Vision, Moonshots & Marsshots, Top Tools (unterscheidend nach Unternehmensgröße), Förderungen (inkl. Hidden Gems) und einer Prioritäten-Matrix (Impact vs. Aufwand), sowie konkrete Next Steps.

    Stellen Sie die Ergebnisse als reines JSON mit diesen Feldern dar:
    {{
      "compliance_score": "",
      "dsgvo_score": "",
      "ai_act_score": "",
      "trust_badge": "",
      "risiko_haftung": "",
      "executive_summary": "",
      "readiness_strategie": "",
      "compliance_datenschutz": "",
      "branchenvergleich": "",
      "branchentrends": "",
      "use_cases_innovation": "",
      "use_cases_roi": "",
      "vision": "",
      "moonshots_marsshots": "",
      "top_tools": "",
      "foerderungen": "",
      "prioritaeten_matrix": "",
      "next_steps": ""
    }}

    Keine zusätzlichen Erklärungen oder Texte, nur reines JSON.
    Input Daten: {data}
    """

    response = await client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )

    content = response.choices[0].message.content.strip()

    if content.startswith("```json"):
        content = content[7:-3].strip()
    elif content.startswith("```"):
        content = content[3:-3].strip()

    return json.loads(content)
