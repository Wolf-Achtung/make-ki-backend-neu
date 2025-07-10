import json
import pandas as pd
import os
import matplotlib.pyplot as plt
from openai import OpenAI

client = OpenAI()

def calc_readiness_score(data):
    score = 0
    if data.get("digitalisierungsgrad") in ["Sehr hoch", "Eher hoch"]:
        score += 2
    elif data.get("digitalisierungsgrad") == "Mittel":
        score += 1

    if data.get("risikofreude") in ["Sehr risikobereit", "Eher risikobereit"]:
        score += 2
    elif data.get("risikofreude") == "Durchschnittlich":
        score += 1

    if data.get("ki_knowhow") in ["Sehr hoch", "Eher hoch"]:
        score += 2
    elif data.get("ki_knowhow") == "Mittel":
        score += 1

    if data.get("automatisierungsgrad") in ["Sehr hoch", "Eher hoch"]:
        score += 2
    elif data.get("automatisierungsgrad") == "Mittel":
        score += 1

    if data.get("ki_projekte"):
        score += 2

    return min(10, score)

def generate_chart(data):
    label_map = {
        "digitalisierungsgrad": "Digitalisierung",
        "automatisierungsgrad": "Automatisierung",
        "risikofreude": "Risikofreude"
    }

    score_map = {
        "Sehr hoch": 10, "Eher hoch": 8, "Mittel": 5,
        "Eher niedrig": 3, "Sehr niedrig": 1,
        "Sehr risikobereit": 10, "Eher risikobereit": 8,
        "Durchschnittlich": 5, "Eher vorsichtig": 3, "Sehr zurückhaltend": 1
    }

    values = []
    labels = []

    for key, label in label_map.items():
        value = score_map.get(data.get(key), 5)
        values.append(value)
        labels.append(label)

    plt.figure(figsize=(6,4))
    plt.bar(labels, values, color="#4a90e2")
    plt.ylim(0, 10)
    plt.title("KI-Readiness Indikatoren")
    plt.ylabel("Score")
    plt.savefig("static/chart.png", bbox_inches='tight')

def gpt_block(data, topic):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Du bist ein TÜV-zertifizierter KI-Manager und Experte."},
            {"role": "user", "content":
f"""
Erstelle einen ausführlichen Analyseabschnitt (mindestens 1200 Wörter) zum Thema: {topic}.

Berücksichtige Felder wie ki_potenzial, ki_hemmnisse, innovationsprozess, marktposition, moonshot, ai_act_kenntnis, interesse_foerderung, bisherige_foerdermittel.

Gib auch eine SWOT-Analyse zurück, formatiert so:
- SWOT Stärken: ...
- SWOT Schwächen: ...
- SWOT Chancen: ...
- SWOT Risiken: ...

Und schließe klare Handlungsempfehlungen und Praxisbeispiele ein.

Hier die strukturierten Antworten:
{json.dumps(data, indent=2)}
"""
            }
        ]
    )
    return response.choices[0].message.content.strip()

def extract_swot(full_text):
    import re
    def find(pattern):
        m = re.search(pattern, full_text, re.DOTALL | re.IGNORECASE)
        return m.group(1).strip() if m else ""
    return {
        "swot_strengths": find(r"SWOT Stärken:(.*?)(?:SWOT|$)"),
        "swot_weaknesses": find(r"SWOT Schwächen:(.*?)(?:SWOT|$)"),
        "swot_opportunities": find(r"SWOT Chancen:(.*?)(?:SWOT|$)"),
        "swot_threats": find(r"SWOT Risiken:(.*?)(?:SWOT|$)")
    }

def read_markdown_file(filename):
    path = os.path.join("data", filename)
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"Fehler beim Lesen von {path}: {e}")
        return ""

def analyze_full_report(data):
    generate_chart(data)

    summary = gpt_block(data, "Executive Summary")
    strategie = gpt_block(data, "Gesamtstrategie")
    compliance = gpt_block(data, "Compliance")
    datenschutz = gpt_block(data, "Datenschutz")
    ai_act = gpt_block(data, "EU AI Act")
    innovation = gpt_block(data, "Innovation")
    moonshot = gpt_block(data, "Moonshot & Vision")
    roadmap = gpt_block(data, "Empfohlene Roadmap")
    foerder = gpt_block(data, "Förderprogramme & Finanzierung")

    # SWOT extrahieren (einmal aus Innovation ziehen)
    swot_parts = extract_swot(innovation)

    # Score berechnen
    score = calc_readiness_score(data)
    score_percent = score * 10

    # Checks & Praxis
    check_readiness = read_markdown_file("check_ki_readiness.md")
    score_vis = read_markdown_file("score_visualisierung.md")
    check_compliance = read_markdown_file("check_compliance_eu_ai_act.md")
    check_ds = read_markdown_file("check_datenschutz.md")
    check_inno = read_markdown_file("check_innovationspotenzial.md")
    praxis = read_markdown_file("praxisbeispiele.md")
    check_roadmap = read_markdown_file("check_umsetzungsplan_ki.md")
    check_foerder = read_markdown_file("check_foerdermittel.md")
    foerder_programme = read_markdown_file("foerdermittel.md")
    tools = read_markdown_file("tools.md")

    return {
        "summary": summary,
        "strategie": strategie,
        "compliance": compliance,
        "datenschutz": datenschutz,
        "ai_act": ai_act,
        "innovation": innovation,
        "moonshot": moonshot,
        "roadmap": roadmap,
        "foerder": foerder,
        "score_percent": score_percent,
        **swot_parts,
        "check_readiness": check_readiness,
        "score_vis": score_vis,
        "check_compliance": check_compliance,
        "check_ds": check_ds,
        "check_inno": check_inno,
        "praxis": praxis,
        "check_roadmap": check_roadmap,
        "check_foerder": check_foerder,
        "foerder_programme": foerder_programme,
        "tools": tools
    }
