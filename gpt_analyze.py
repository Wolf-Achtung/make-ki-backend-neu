import openai
import json
import logging

def get_analysis(data, openai_api_key):
    openai.api_key = openai_api_key

    # Prompt vorbereiten
    prompt = (
        "Du bist ein KI-Analyst für kleine Unternehmen. Bitte analysiere folgendes Unternehmen anhand dieser Daten:\n"
        f"Branche: {data.get('branche', 'nicht angegeben')}\n"
        f"Ziel: {data.get('ziel', 'nicht angegeben')}\n"
        f"Tools: {data.get('tools', 'nicht angegeben')}\n"
        f"Status: {data.get('status', 'nicht angegeben')}\n"
        f"Score: {data.get('score', 'nicht angegeben')}\n\n"
        "Gib eine strukturierte Analyse im JSON-Format zurück, mit Feldern wie:\n"
        "- executive_summary\n"
        "- analyse\n"
        "- empfehlung1_titel, empfehlung1_beschreibung, empfehlung1_next_step, empfehlung1_tool\n"
        "- empfehlung2_...\n"
        "- empfehlung3_...\n"
        "- roadmap_kurzfristig, roadmap_mittelfristig, roadmap_langfristig\n"
        "- ressourcen, zukunft, rueckfrage1–3\n"
        "- foerdertipp1/2: programm, zielgruppe, nutzen\n"
        "- risikoklasse, risikobegruendung, risikopflicht1/2\n"
        "- tool1/2: name, einsatz, warum\n"
        "- branchenvergleich, trendreport, vision"
    )

    # GPT-Call
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Du bist ein hilfreicher KI-Assistent."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7
    )

    reply = response.choices[0].message["content"]
    logging.info("GPT-Rohantwort:\n" + reply)

    try:
        json_data = json.loads(reply)
        return json_data
    except json.JSONDecodeError as e:
        logging.error("GPT-Antwort konnte nicht geparst werden.")
        logging.error(e)
        raise ValueError("Ungültige JSON-Antwort von GPT")
