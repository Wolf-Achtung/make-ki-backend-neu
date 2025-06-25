from openai import OpenAI
import os
import requests
import json
from flask import jsonify

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def format_value(val):
    if isinstance(val, list):
        return ", ".join(str(v) for v in val)
    if isinstance(val, dict):
        return json.dumps(val, ensure_ascii=False)
    return str(val)

def get_analysis(data: dict) -> dict:
    """Erstellt eine strukturierte Analyse mit GPT und generiert ein PDF mit PDFMonkey."""

    # 🔍 Nur relevante Nutzereingaben an GPT übergeben
    user_keys = [
        "name", "unternehmen", "email", "datum", "branche", "selbststaendig",
        "tool1_name", "tool1_einsatz", "tool1_warum",
        "tool2_name", "tool2_einsatz", "tool2_warum",
        "risikoklasse", "risikobegruendung"
    ]

    filtered_data = {k: v for k, v in data.items() if k in user_keys and v}

    try:
        input_string = "\n".join(
            f"{key.capitalize()}: {format_value(value)}"
            for key, value in filtered_data.items()
        )
        print("📥 Aggregierte Nutzerdaten für GPT:\n", input_string)
    except Exception as e:
        print("❌ Fehler bei der Eingabeverarbeitung:", str(e))
        return {"error": "Fehler bei der Eingabeverarbeitung"}

    # GPT-Prompt
    prompt = f"""
Erstelle eine strukturierte Analyse für folgende Nutzereingabe:
{input_string}
Strukturiere die Analyse ausschließlich in folgendem JSON-Format und gib nur JSON zurück (ohne Einleitung):

{{
  "executive_summary": "...",
  "score": "42",
  "status": "Gut vorbereitet",
  "bewertung": "Solide Ausgangslage",
  "branche": "Marketing & Werbung",
  "selbststaendig": "Ja",
  "analyse": "...",
  "empfehlung1_titel": "...",
  "empfehlung1_beschreibung": "...",
  "empfehlung1_next_step": "...",
  "empfehlung1_tool": "...",
  "empfehlung2_titel": "...",
  "empfehlung2_beschreibung": "...",
  "empfehlung2_next_step": "...",
  "empfehlung2_tool": "...",
  "empfehlung3_titel": "...",
  "empfehlung3_beschreibung": "...",
  "empfehlung3_next_step": "...",
  "empfehlung3_tool": "...",
  "roadmap_kurzfristig": "...",
  "roadmap_mittelfristig": "...",
  "roadmap_langfristig": "...",
  "ressourcen": "...",
  "zukunft": "...",
  "rueckfrage1": "...",
  "rueckfrage2": "...",
  "rueckfrage3": "...",
  "foerdertipp1_programm": "...",
  "foerdertipp1_zielgruppe": "...",
  "foerdertipp1_nutzen": "...",
  "foerdertipp2_programm": "...",
  "foerdertipp2_zielgruppe": "...",
  "foerdertipp2_nutzen": "...",
  "risikoklasse": "...",
  "risikobegruendung": "...",
  "risikopflicht1": "...",
  "risikopflicht2": "...",
  "tool1_name": "...",
  "tool1_einsatz": "...",
  "tool1_warum": "...",
  "tool2_name": "...",
  "tool2_einsatz": "...",
  "tool2_warum": "...",
  "branchenvergleich": "...",
  "trendreport": "...",
  "vision": "...",
  "compliance": "...",
  "beratungsempfehlung": "..."
}}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        raw_output = response.choices[0].message.content.strip()
        print("\n🧠 GPT-Rohantwort:\n", raw_output)
        return json.loads(raw_output)

    except Exception as e:
        print("❌ GPT-Verarbeitung oder JSON-Parsing fehlgeschlagen:", str(e))
        return {"error": f"Fehler bei der GPT-Antwort: {str(e)}"}
