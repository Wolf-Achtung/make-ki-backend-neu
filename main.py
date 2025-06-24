
from fastapi import FastAPI, Request, HTTPException
import json
import httpx

app = FastAPI()

MAKE_WEBHOOK_URL = "https://hook.eu2.make.com/gxydz1j89buq91wl1o26noto0eciax5h"

REQUIRED_FIELDS = ["name", "unternehmen", "email"]
MAX_FIELD_LENGTH = 500  # beliebiger Grenzwert

@app.post("/analyze")
async def analyze(request: Request):
    try:
        raw_body = await request.body()
        json_data = json.loads(raw_body.decode("utf-8"))
        print("[INFO] JSON empfangen:", json.dumps(json_data, indent=2))
    except Exception as e:
        print("[ERROR] Fehler beim JSON-Parsing:", e)
        raise HTTPException(status_code=400, detail=f"Fehler beim JSON-Parsing: {str(e)}")

    # Pflichtfeldprüfung
    missing_fields = [field for field in REQUIRED_FIELDS if not json_data.get(field)]
    if missing_fields:
        raise HTTPException(status_code=422, detail=f"Fehlende Pflichtfelder: {', '.join(missing_fields)}")

    # Feldprüfung, Kürzen & Fallbacks
    validated_data = {}
    for key, value in json_data.items():
        if isinstance(value, str):
            value = value.strip()
            if len(value) > MAX_FIELD_LENGTH:
                print(f"[WARN] Feld '{key}' war zu lang – wurde gekürzt.")
                value = value[:MAX_FIELD_LENGTH]
        validated_data[key] = value or "N/A"

    # Logging: Eingabedaten ausgeben
    print("[INFO] Validierte Daten:", json.dumps(validated_data, indent=2))

    # Weitergabe an Make
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(MAKE_WEBHOOK_URL, json=validated_data)
            response.raise_for_status()
            print("[INFO] Erfolgreich an Make gesendet.")
    except Exception as e:
        print("[ERROR] Fehler beim Senden an Make:", e)
        raise HTTPException(status_code=500, detail=f"Fehler beim Senden an Make: {str(e)}")

    return {
        "status": "ok",
        "message": "Payload erfolgreich validiert und weitergeleitet",
        "fields_checked": len(validated_data),
        "missing_fields": missing_fields
    }
