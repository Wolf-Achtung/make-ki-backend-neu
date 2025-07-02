def validate_gpt_response(response: dict):
    """
    Prüft, ob alle erwarteten Felder vorhanden sind.
    Gibt True zurück, wenn vollständig, sonst Exception.
    """
    required_keys = [
        "compliance_score", "badge_level", "ds_gvo_level", "ai_act_level",
        "risk_traffic_light", "executive_summary", "readiness_analysis",
        "compliance_analysis", "use_case_analysis", "branche_trend",
        "vision", "next_steps", "toolstipps", "foerdertipps",
        "risiko_und_haftung", "dan_inspiration"
    ]
    missing = [key for key in required_keys if key not in response]
    if missing:
        raise ValueError(f"Fehlende Felder im GPT-Output: {missing}")
    return True
