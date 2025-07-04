import json
from openai import OpenAI
client = OpenAI()

# 🔥 Tools & Förderungen laden
with open("tools_und_foerderungen.json") as f:
    tools_data = json.load(f)

def analyze_with_gpt(data):
    """
    Sendet die Felder an GPT und bekommt eine detaillierte, professionelle Standortanalyse zurück.
    """
    print("👉 Eingehende Daten für GPT:", json.dumps(data, indent=2))

    # Neuer, wirtschaftlich und rechtlich optimierter Prompt:
    prompt = f"""
    Sie sind ein erfahrener, TÜV-zertifizierter KI- und Digitalstrategie-Berater für deutsche Unternehmen.
    Analysieren Sie die folgende Unternehmens-Selbstauskunft maximal professionell, tiefgehend und wirtschaftlich orientiert.

    Ihr Ziel ist es, dem Unternehmen einen ausführlichen, verständlichen und motivierenden Executive-Briefing-Report (ca. 7-10 Seiten, 5000–6000 Wörter) zu erstellen, mit folgenden Schwerpunkten:
    1. Individuelle Standortbestimmung des Unternehmens in Sachen KI-Readiness, Digitalisierung und Innovation (inkl. Branchen- und Geschäftsmodell-Kontext)
    2. Identifikation von Risiken, Compliance-Lücken, Hemmnissen und Optimierungspotenzialen inkl. Bewertung nach DSGVO und EU AI Act, mit Ampel/Badge-Logik (Compliance-Score 0-100, Badge-Level LOW/MEDIUM/HIGH)
    3. Konkret auf das Unternehmen zugeschnittene Chancen, neue Geschäftsmodelle, Innovationspotenziale und Roadmap-Vorschläge
    4. Fördermöglichkeiten (Bund, Land, EU) und Zuschusschancen (inkl. Quick-Check und Next Steps)
    5. Handlungsorientierte Empfehlungen, konkrete Todos, Best Practices und Tool-Tipps für eine erfolgreiche und rechtssichere KI-Implementierung
    6. Abschluss mit Zusammenfassung, Badge/Score und Kontakt-/Weiterentwicklungsoptionen

    Verwenden Sie ausschließlich die professionelle Sie-Form, verzichten Sie auf Floskeln, und geben Sie jedem Abschnitt klare Überschriften. 
    Antworten Sie bitte so, dass ein Unternehmer direkt erkennt, welchen wirtschaftlichen Nutzen und welche Risiken KI für sein Unternehmen hat – und was die nächsten Schritte sind.

    Antworten Sie **ausschließlich** im folgenden JSON-Format:
    {{
      "compliance_score": ...,
      "badge_level": "...",
      "ds_gvo_level": ...,
      "ai_act_level": ...,
      "risk_traffic_light": "...",
      "executive_summary": "...",
      "branchen_und_unternehmensanalyse": "...",
      "readiness_analysis": "...",
      "compliance_analysis": "...",
      "use_case_analysis": "...",
      "branche_trend": "...",
      "foerdermittel_check": "...",
      "roadmap": "...",
      "next_steps": [...],
      "toolstipps": [...],
      "foerdertipps": [...],
      "risiko_und_haftung": "...",
      "abschluss": "...",
      "dan_inspiration": "..."
    }}

    Unternehmensdaten:
    {json.dumps(data, indent=2)}

    Zusätzlich findest du hier eine Liste bekannter Tools und Förderprogramme, die Sie in die Empfehlungen einfließen lassen können:
    {json.dumps(tools_data, indent=2)}
    """

    completion = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Du bist ein KI-Berater."},
            {"role": "user", "content": prompt}
        ]
    )

    content = completion.choices[0].message.content
    print("✅ GPT Antwort:", content)

    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        raise ValueError("GPT hat kein gültiges JSON geliefert.")

    return result
