# KI-Status-Report Backend – Optimierungsstand v1 (2025-10-19T10:52:36.244153Z)

**Highlights**
- Konsolidierte Settings (Pydantic v2), saubere CORS/Env-Auswertung
- Stabiler Start (Python 3.12 + Pydantic + email-validator in requirements)
- `/admin/status` jetzt mit JWT-Auth (Role=admin)
- Queue optional via Redis/RQ (fallback: lokaler BackgroundTask)
- PDF-Service-Client mit Timeout und Base64-Fallback
- Mailversand async (to_thread) + sync (für Worker), Attachments robust
- Health/Metrics unverändert erreichbar

**ENV Variablen (relevant)**
- `DATABASE_URL`, `JWT_SECRET`
- `FRONTEND_ORIGINS`
- `PDF_SERVICE_URL`, `PDF_TIMEOUT` (ms)
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`, `SMTP_FROM_NAME`
- `ADMIN_EMAIL`, `SEND_USER_MAIL=true|false`, `SEND_ADMIN_MAIL=true|false`, `ATTACH_HTML_FALLBACK=true|false`
- `REDIS_URL` (optional für Queue)

**Start**
- Web: `python -m uvicorn main:app --host 0.0.0.0 --port 8080`
- Worker (optional): `python worker.py`

**Sicherheit**
- Admin-Endpunkte nur mit `Authorization: Bearer <JWT>` und Claim `role=admin`.

**Rate Limiting**
- Redis-basiert wenn `REDIS_URL` gesetzt; sonst in-memory.
