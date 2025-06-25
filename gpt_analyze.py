
def format_value(value):
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if item)
    return str(value)

def get_analysis(data):
    # Eingehende Daten validieren
    required_fields = ["unternehmen", "email"]
    missing = [field for field in required_fields if not data.get(field)]
    if missing:
        raise ValueError(f"Pflichtfelder fehlen: {', '.join(missing)}")

    print("🔍 Validierte Eingabedaten:", data)

    filtered = {
        "unternehmen": format_value(data.get("unternehmen")),
        "email": format_value(data.get("email")),
        "branche": format_value(data.get("branche")),
        "bereich": format_value(data.get("bereich")),
        "ziel": format_value(data.get("ziel")),
        "tools": format_value(data.get("tools")),
    }

    # Platzhalter für GPT-Auswertung
    result = {
        "score": 73,
        "status": "Standard",
        "bewertung": "Ihr Unternehmen hat grundlegende Maßnahmen im Bereich KI ergriffen.",
        "analyse": "Sie nutzen bereits einige Tools, aber es bestehen noch Potenziale.",
        "vision": "Mit gezieltem Tool-Einsatz und Fördermitteln kann Ihr Unternehmen ein Vorreiter in Ihrer Branche werden.",
        "empfehlung": "Analysieren Sie Ihre Prozesse mit Blick auf Automatisierung und beginnen Sie mit kleinen KI-Projekten.",
        "tooltipp": "Nutzen Sie Tools wie ChatGPT, Make oder Notion AI für erste interne Automatisierungen.",
        "foerdertipp": "Informieren Sie sich über das Programm 'go-digital' oder regionale KI-Förderungen.",
        "branchenvergleich": "Im Vergleich zur Branche ist Ihr Unternehmen leicht über dem Durchschnitt.",
        "trendreport": "Derzeit liegt der Trend bei generativen KI-Tools und smarten Assistenten.",
        "zukunftsausblick": "Bis 2027 wird KI ein zentraler Wettbewerbsfaktor für Ihre Branche.",
        "compliance": "Ihr Unternehmen sollte DSGVO und EU-AI-Act im Blick behalten und ggf. externe Beratung einholen.",
        "beratungsempfehlung": "Lassen Sie sich von einem KI-Manager individuell beraten – z. B. unter ki-sicherheit.jetzt.",
    }

    print("✅ Ergebnisdaten:", result)
    return {**filtered, **result}
