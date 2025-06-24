# GPT Backend für KI-Briefing

## Lokaler Start

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

## Endpoint

POST `/briefing`

Payload: Siehe `BriefingRequest` in `main.py`
