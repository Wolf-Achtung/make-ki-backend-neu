# filename: ops/railway-cors.md
# Railway – CORS Hotfix (Backend)

**Ziel:** Fehlermeldung „No 'Access-Control-Allow-Origin' header“ beim Aufruf
`POST /api/login` aus `https://make.ki-sicherheit.jetzt` beseitigen.

## 1) Environment prüfen
Setze in Railway (Service: Backend) die Variablen:

```
CORS_ALLOW_ORIGINS=https://ki-sicherheit.jetzt,https://www.ki-sicherheit.jetzt,https://make.ki-sicherheit.jetzt,https://www.make.ki-sicherheit.jetzt,https://ki-foerderung.jetzt
CORS_ALLOW_REGEX=^https?://([a-z0-9-]+\.)?(ki-sicherheit\.jetzt|ki-foerderung\.jetzt)$
CORS_ALLOW_CREDENTIALS=0
```

> **Hinweis:** Falls du temporär alles erlauben willst, setze
> `CORS_ALLOW_ORIGINS=*` (dann sind Credentials automatisch deaktiviert).

## 2) Health / Debug
- `GET /healthz` zeigt die effektive CORS‑Konfiguration.
- `GET /health/cors-echo` spiegelt die **Origin**‑Header zurück (Browser‑Konsole: `fetch(<origin>/health/cors-echo)`).
- `OPTIONS /*` liefert 204 – Preflight wird immer korrekt beantwortet.

## 3) Frontend
- Nutze `credentials: "omit"` beim Login‑Fetch (siehe `frontend/login.js`).
- Hinterlege `<meta name="backend-origin" content="https://<railway-host>.up.railway.app">`.
