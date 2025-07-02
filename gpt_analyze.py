import json
from openai import OpenAI
client = OpenAI()

def analyze_with_gpt(data):
    """
    Sendet die Felder an GPT und bekommt eine detaillierte Bewertung zurück.
    """
    # Für Debug
    print("👉 Eingehende Daten für GPT:", json.dumps(data, indent=2))

    # GPT Prompt (du kannst das noch beliebig erweitern)
    prompt = f"""
    Du bist ein KI- und Datenschutz-Experte. Analysiere die folgenden Unternehmensangaben
    und erstelle eine umfassende Bewertung der KI-Readiness sowie Datenschutz-Compliance
    inklusive Compliance-Score (0-100), Badge-Level (LOW, MEDIUM, HIGH),
    Empfehlungen und nächsten Schritte. Antworte im JSON-Format mit:
    {{
      "compliance_score": ...,
      "badge_level": "...",
      "ds_gvo_level": ...,
      "ai_act_level": ...,
      "risk_traffic_light": "...",
      "executive_summary": "...",
      "readiness_analysis": "...",
      "compliance_analysis": "...",
      "use_case_analysis": "...",
      "branche_trend": "...",
      "vision": "...",
      "next_steps": [...],
      "toolstipps": [...],
      "foerdertipps": [...],
      "risiko_und_haftung": "...",
      "dan_inspiration": "..."
    }}

    Unternehmensdaten:
    {json.dumps(data, indent=2)}
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
