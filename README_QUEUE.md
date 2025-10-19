# Queue/Worker Setup (Railway)

## 1) Variables (Backend & Worker services)
- ENABLE_QUEUE=true
- REDIS_URL=redis://default:<PASS>@<redis-private-host>:6379
- RQ_QUEUES=reports,emails
- RQ_JOB_TIMEOUT=600
- RQ_RESULT_TTL=3600

## 2) Services
Railway startet pro Service genau einen Prozess. Lege daher im gleichen Projekt **zwei Services** an (gleiche Repo-Quelle):

- Service 1 (Web): Start Command → `uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers`
- Service 2 (Worker): Start Command → `python worker.py`

Beide Services benötigen identische Env-Variablen (REDIS_URL, ENABLE_QUEUE, etc.).

## 3) Endpunkte / Tests
- `GET  /api/queue/ping` → `{"ok": true, "redis": "ok", "queues": [...]}`
- `POST /api/analyze` Body: `{ "url": "https://example.com", "email": "you@domain.tld" }` → `202 {status:"queued", job_id:"..."}`
- `GET  /api/result/<job_id>?download=1` → PDF-Download (zuvor 202, bis fertig).

## 4) PDF-Service
- Erwartet POST JSON mit `html` oder `url` an `PDF_SERVICE_URL`. Liefert entweder PDF direkt (**Content-Type: application/pdf**) oder JSON mit `pdf_url`.

## 5) E-Mail (optional)
- Setze SMTP_* Variablen und MAIL_FROM. Wenn nicht gesetzt, wird kein E-Mail-Versand versucht; das Job-Ergebnis (PDF) liegt dennoch in Redis.
