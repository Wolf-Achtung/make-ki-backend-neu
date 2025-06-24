
from fastapi import FastAPI, Request, HTTPException
import json
import httpx

app = FastAPI()

MAKE_WEBHOOK_URL = "https://hook.eu2.make.com/gxydz1j89buq91wl1o26noto0eciax5h"

@app.post("/analyze")
async def analyze(request: Request):
    try:
        raw_body = await request.body()
        json_data = json.loads(raw_body.decode("utf-8"))
    except Exception as e:
        print("Fehler beim JSON-Parsing:", e)
        raise HTTPException(status_code=400, detail=f"Fehler beim JSON-Parsing: {str(e)}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(MAKE_WEBHOOK_URL, json=json_data)
            response.raise_for_status()
    except Exception as e:
        print("Fehler beim Senden an Make:", e)
        raise HTTPException(status_code=500, detail=f"Fehler beim Senden an Make: {str(e)}")

    return {"status": "ok", "message": "Payload erfolgreich verarbeitet"}
