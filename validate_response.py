# validate_response.py

def validate_gpt_response(response: dict, autofix: bool = True):
    """
    Prüft, ob alle erwarteten Felder vorhanden sind.
    Wenn autofix=True, füllt fehlende Felder mit Defaults.
    """
    required_keys = {
        "compliance_score": "n/a",
        "badge_level": "n/a",
        "ds_gvo_level": "0%",
        "ai_act_level": "0%",
        "risk_traffic_light": "grau",
        "executive_summary": "n/a",
        "readiness_analysis": "n/a",
        "compliance_analysis": "n/a",
        "use_case_analysis": "n/a",
        "branche_trend": "n/a",
        "vision": "n/a",
        "next_steps": [],
        "toolstipps": [],
        "foerdertipps": [],
        "risiko_und_haftung": "n/a",
        "dan_inspiration": "n/a"
    }

    missing = [key for key in required_keys if key not in response]
    
    if missing:
        if autofix:
            for key in missing:
                response[key] = required_keys[key]
        else:
            raise ValueError(f"Fehlende Felder im GPT-Output: {missing}")

    return response
