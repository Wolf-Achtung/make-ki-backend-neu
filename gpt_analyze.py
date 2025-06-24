
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def build_prompt(user_input: str, prompt_type: str = "standard") -> str:
    if prompt_type == "standard":
        return f"""Erstelle eine strukturierte, professionelle Analyse für folgende Nutzereingabe:

"""{user_input}"""

Die Analyse soll folgende Felder enthalten:
- Executive Summary
- Konkrete Handlungsempfehlungen
- DSGVO- & EU-AI-Act-Konformität
- Branchenvergleich & Risiken
- Förderprogramme & Tools
- Visionärer Zukunftsblick

Format: Klar gegliedert, stichpunktartig wo sinnvoll. Zielgruppe: Selbstständige, KMU, Berater:innen. Sprache: Deutsch.
"""
    elif prompt_type == "kurz":
        return f"Kurzfazit auf Deutsch für folgendes Anliegen:

{user_input}

Bitte mit maximal 5 Bulletpoints."
    elif prompt_type == "humorvoll":
        return f"Erstelle eine humorvolle, aber dennoch fundierte Analyse für dieses Thema:

{user_input}"
    else:
        return f"Bitte analysiere folgenden Nutzerinput:

{user_input}"

def get_analysis(user_input: str):
    prompt = build_prompt(user_input)

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Du bist ein KI-Experte für Business-Analysen und Strategien."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7
    )

    return response.choices[0].message.content.strip()
