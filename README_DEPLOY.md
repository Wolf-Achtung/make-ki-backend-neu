# KI-Status-Report Backend — Deploy notes (Railway)

## Endpoints
- `GET /` – plain text uptime message
- `GET /api/healthz` – health probe
- `GET /api/diag` – diagnostics (no secrets)
- `POST /api/login` – email/password login
- `GET /api/admin/status` – requires header `X-Admin-Token: <ADMIN_API_TOKEN>` or `Authorization: Bearer <ADMIN_API_TOKEN>`
- `POST /api/feedback` – store feedback if table exists

## Required environment
Create these variables in Railway:

```
APP_NAME=KI-Status-Report Backend
ENV=production
VERSION=2025.10
LOG_LEVEL=INFO

# Comma-separated; list your domains explicitly (no trailing slashes)
CORS_ALLOW_ORIGINS=https://ki-sicherheit.jetzt,https://www.ki-sicherheit.jetzt,https://make.ki-sicherheit.jetzt,https://www.make.ki-sicherheit.jetzt

# Database
DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DBNAME   # Railway "Postgres" plugin exposes this; we normalize automatically.

# Optional queue
ENABLE_QUEUE=false
REDIS_URL=redis://:PASSWORD@HOST:PORT/0

# PDF service
PDF_SERVICE_URL=https://<your-pdf-service>/api/render
PDF_TIMEOUT=45000

# Security
SECRET_KEY=<generate 32+ chars>
ADMIN_API_TOKEN=<choose a strong token>
```

### Notes
- If Railway gives the DB URL as `postgres://...` we automatically convert to `postgresql+asyncpg://...` for SQLAlchemy async.
- If `REDIS_URL` is empty, queue stays disabled (no crash).
- GET `/api/login` returns a helpful message. Use `POST` from the frontend.

## Local run
```
python -m uvicorn main:app --reload
```
