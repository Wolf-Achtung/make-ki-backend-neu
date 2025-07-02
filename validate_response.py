import json

EXPECTED_FIELDS = [
    "compliance_score", "badge_level", "ds_gvo_level", "ai_act_level",
    "risk_traffic_light", "executive_summary", "readiness_analysis",
    "compliance_analysis", "use_case_analysis", "branche_trend",
    "vision", "next_steps", "toolstipps", "foerdertipps",
    "risiko_und_haftung", "dan_inspiration"
]

def validate_gpt_response(response):
    print("🚀 Validierung des GPT-Outputs gestartet...")
    missing = []
    for field in EXPECTED_FIELDS:
        if field not in response:
            print(f"⚠️ Feld fehlt: {field}, wird mit Platzhalter gefüllt.")
            response[field] = "n/a" if not field.endswith("tipps") and field != "next_steps" else []
            missing.append(field)
    if missing:
        print("✅ Fehlende Felder auto-aufgefüllt:", missing)
    else:
        print("✅ Alle Felder vorhanden.")
    return response
