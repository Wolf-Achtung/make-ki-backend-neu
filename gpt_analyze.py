from openai import OpenAI
import os

client = OpenAI()

async def generate_briefing(data):
    prompt = f"""
    Erstelle ein strategisches KI-Briefing basierend auf:
    Branche: {data.get('branche')}, Ziel: {data.get('ziel')}, Maßnahme: {data.get('massnahme')}.
    Compliance: Richtlinien={data.get('richtlinien')}, DSGVO={data.get('personen')}, DSB={data.get('dsb')} usw.
    Füge ROI-Tipps, Förder-Hinweise und eine motivierende Vision hinzu.
    """
    
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return completion.choices[0].message.content
