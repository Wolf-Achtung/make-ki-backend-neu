import asyncio
from openai import OpenAI
import os
import json
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

async def call_gpt(prompt, model="gpt-4", temperature=0.3):
    response = await asyncio.to_thread(
        client.chat.completions.create,
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature
    )
    content = response.choices[0].message.content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"error": f"JSON Parse Fehler: {content}"}

async def analyze_compliance(data):
    prompt = f"""
Sie sind ein zertifizierter KI-Compliance-Experte.
Analysieren Sie die Antworten zu Datenschutz & Compliance für das Unternehmen:
{json.dumps(data, ensure_ascii=False, indent=2)}

Geben Sie folgendes JSON zurück:
{{
  "compliance_analysis": "...",
  "compliance_score": 0-10,
  "badge_level": "Bronze|Silber|Gold"
}}
Nur korrektes JSON ohne Einleitung.
"""
    result = await call_gpt(prompt, model="gpt-4", temperature=0.3)
    # Validation
    if "compliance_score" not in result:
        result["compliance_score"] = 0
        result["validation_hint"] = "compliance_score fehlte, Default 0 gesetzt."
    return result

async def analyze_use_cases_readiness(data):
    prompt = f"""
Sie sind KI-Strategieberater.
Analysieren Sie Branche "{data.get('branche')}", Maßnahme "{data.get('massnahme')}",
Bereich "{data.get('bereich')}", Ziel "{data.get('ziel')}". 

Geben Sie folgendes JSON zurück:
{{
  "readiness_analysis": "...",
  "use_case_analysis": "..."
}}
Nur korrektes JSON ohne Einleitung.
"""
    return await call_gpt(prompt, model="gpt-4", temperature=0.5)

async def analyze_vision_trends(data):
    prompt = f"""
Sie sind kreativer KI-Futurist & Förderberater.
Für Branche "{data.get('branche')}", Maßnahme "{data.get('massnahme')}", Bereich "{data.get('bereich')}", Ziel "{data.get('ziel')}":
Geben Sie folgendes JSON zurück:
{{
  "branche_trend": "...",
  "vision": "...",
  "toolkompass": ["Tool1", "Tool2"],
  "fördertipps": ["Tipp1", "Tipp2"],
  "executive_summary": "..."
}}
Nur korrektes JSON ohne Einleitung.
"""
    return await call_gpt(prompt, model="gpt-4-turbo", temperature=0.8)

async def analyze_with_gpt(data):
    results = await asyncio.gather(
        analyze_compliance(data),
        analyze_use_cases_readiness(data),
        analyze_vision_trends(data)
    )
    merged = {}
    for r in results:
        merged.update(r)
    return merged
