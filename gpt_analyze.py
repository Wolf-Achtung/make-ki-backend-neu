import asyncio
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

async def analyze_compliance(data):
    prompt = f"""
Sie sind ein zertifizierter KI-Compliance-Experte.
Analysieren Sie die folgenden Antworten des Unternehmens zu Datenschutz & Compliance (besonders "noch unklar").
Antwort bitte als JSON mit:
- compliance_analysis
- compliance_score (0-10)
- badge_level ("Bronze", "Silber", "Gold")
Fragen: {data}
Nur JSON ohne Einleitung.
"""
    response = await asyncio.to_thread(
        client.chat.completions.create,
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    return eval(response.choices[0].message.content.strip())

async def analyze_use_cases_readiness(data):
    prompt = f"""
Sie sind KI-Strategieberater.
Analysieren Sie Branche "{data.get('branche')}", Maßnahme "{data.get('massnahme')}", Bereich "{data.get('bereich')}", Ziel "{data.get('ziel')}".
Geben Sie bitte:
- readiness_analysis
- use_case_analysis
als JSON ohne Einleitung zurück.
"""
    response = await asyncio.to_thread(
        client.chat.completions.create,
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5
    )
    return eval(response.choices[0].message.content.strip())

async def analyze_vision_trends(data):
    prompt = f"""
Sie sind ein kreativer KI-Futurist & Förderberater.
Analysieren Sie die Branche "{data.get('branche')}" und geben Sie:
- branche_trend
- vision
- toolkompass (Liste)
- fördertipps (Liste)
- executive_summary
als JSON zurück.
"""
    response = await asyncio.to_thread(
        client.chat.completions.create,
        model="gpt-4-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8
    )
    return eval(response.choices[0].message.content.strip())

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
