import json
import openai
import pandas as pd
import matplotlib.pyplot as plt

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
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Du bist ein TÜV-zertifizierter KI-Manager mit Expertise in Strategie, Compliance, Förderung, Benchmarking und Innovation."},
            {"role": "user", "content":
f"""
Erstelle einen ausführlichen Analyseabschnitt mit mindestens 1200 Wörtern zum Thema: {topic}.

Berücksichtige dabei die folgenden Felder:
- ki_potenzial, ki_hemmnisse, innovationsprozess, marktposition, moonshot, ai_act_kenntnis, interesse_foerderung, bisherige_foerdermittel

Nutze eine strukturierte Gliederung mit:
- SWOT-Analyse (Stärken, Schwächen, Chancen, Risiken)
- Handlungsempfehlungen
- ggf. Fördermöglichkeiten
- praxisnahe Beispiele

Hier sind die strukturierten Antworten:
{json.dumps(data, indent=2)}
"""
            }
        ]
    )
    return response.choices[0].message.content.strip()

def read_markdown_file(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except:
        return ""

def analyze_full_report(data):
    generate_chart(data)

    summary = gpt_block(data, "Executive Summary & Gesamtstrategie")
    compliance = gpt_block(data, "Compliance, Datenschutz & AI Act")
    innovation = gpt_block(data, "Innovation, Moonshot & Wettbewerb")
    roadmap = gpt_block(data, "Empfohlene Roadmap")
    foerder = gpt_block(data, "Förderprogramme & Finanzierung")

    # Aus externen Markdown-Dateien
    tools = read_markdown_file("tools.md")
    checklist = read_markdown_file("checklisten.md")
    praxis = read_markdown_file("praxisbeispiele.md")
    vis = read_markdown_file("score_visualisierung.md")

    return {
        "summary": summary,
        "compliance": compliance,
        "innovation": innovation,
        "roadmap": roadmap,
        "foerder": foerder,
        "tools": tools,
        "checklist": checklist,
        "praxis": praxis,
        "score_vis": vis
    }
