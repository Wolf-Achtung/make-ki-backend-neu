# KI-Backend (Gold-Standard+ v3)

## Start (lokal)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload

## Start (Railway)
Start Command:
uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}

## Health
/healthz, /health, /metrics
