import os
import json
import time
import uuid
import logging
import inspect
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, HTMLResponse
from jose import jwt
from jose.exceptions import JWTError

import httpx

# Optional DB (wenn DATABASE_URL gesetzt ist)
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except Exception:  # pragma: no cover
    psycopg2 = None

# Optional: Analyse-Modul
try:
    from gpt_analyze import analyze_briefing  # deine Datei
from gpt_analyze import calc_score_percent
except Exception:
    analyze_briefing = None  # Fallback unten


# -----------------------------------------------------------------------------
# Konfiguration / Umgebungsvariablen
# -----------------------------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
ALGORITHM = "HS256"

DATABASE_URL = os.getenv("DATABASE_URL", "")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "bewertung@ki-sicherheit.jetzt")

ADMIN_LOGIN_EMAIL = os.getenv("ADMIN_LOGIN_EMAIL")  # optionaler Fallback
ADMIN_LOGIN_PASSWORD = os.getenv("ADMIN_LOGIN_PASSWORD")  # optionaler Fallback

PDF_SERVICE_URL = os.getenv("PDF_SERVICE_URL", "").rstrip("/")
PDF_TIMEOUT = int(os.getenv("PDF_TIMEOUT", "120"))

APP_VERSION = os.getenv("APP_VERSION", "2025-08-19")

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(levelname)s:%(name)s:%(message)s",
)
logger = logging.getLogger("backend")

# -----------------------------------------------------------------------------
# App & CORS
# -----------------------------------------------------------------------------
app = FastAPI(title="KI-Readiness Backend", version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # falls enger gewünscht → Domain-Liste
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def db_conn():
    """Postgres-Verbindung (nur wenn DATABASE_URL gesetzt & psycopg2 verfügbar)."""
    if not DATABASE_URL or psycopg2 is None:
        return None
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def create_access_token(payload: Dict[str, Any], expires_seconds: int = 3600 * 12) -> str:
    """
    Erzeugt einen JWT-Token für das gegebene Payload. Standardmäßig läuft der Token
    nach 12 Stunden ab (statt 1 Stunde). Die längere Laufzeit stellt sicher, dass
    Nutzer bei längeren Fragebogensitzungen nicht ausgeloggt werden und 401-Fehler
    vermieden werden. Optional kann bei Bedarf ein anderer Wert übergeben werden.
    """
    payload = dict(payload)
    payload["exp"] = int(time.time()) + expires_seconds
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


def get_bearer_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return auth.split(" ", 1)[1].strip()


def current_user(request: Request) -> Dict[str, Any]:
    token = get_bearer_token(request)
    try:
        return decode_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def resolve_recipient(data: Dict[str, Any], default_email: str) -> str:
    """
    Sucht robust nach einer Nutzer-E-Mail im Payload. Fällt auf default_email zurück.
    """
    candidates = []

    # flache Keys
    for k in ("email", "kontakt_email", "contact_email", "user_email", "recipient", "to"):
        v = (data.get(k) or "").strip()
        if v and "@" in v:
            candidates.append(v)

    # verschachtelte Strukturen
    paths = [
        ("user", "email"),
        ("auth", "email"),
        ("account", "email"),
        ("profile", "email"),
        ("antworten", "email"),
        ("answers", "email"),
        ("meta", "email"),
    ]
    for path in paths:
        cur = data
        for p in path:
            if isinstance(cur, dict):
                cur = cur.get(p, {})
            else:
                cur = {}
        if isinstance(cur, str) and "@" in cur:
            candidates.append(cur.strip())

    # Meta gespiegelt vom Frontend
    meta = data.get("_meta") or {}
    if isinstance(meta, dict):
        for k in ("x_user_email", "x-user-email"):
            v = (meta.get(k) or "").strip()
            if v and "@" in v:
                candidates.append(v)

    for v in candidates:
        if v and "@" in v:
            return v

    return default_email


def html_fallback(lang: str = "de") -> str:
    title = "KI-Readiness Report" if lang == "de" else "AI Readiness Report"
    return f"""<!doctype html>
<html lang="{lang}">
<head><meta charset="utf-8"><title>{title}</title>
<style>body{{font-family:Arial,Helvetica,sans-serif;padding:24px;}}</style></head>
<body>
  <h1>{title}</h1>
  <p>Dies ist eine Fallback-Ansicht (Analyse-Modul nicht geladen).</p>
</body>
</html>"""


async def send_html_to_pdf_service(
    html: str,
    user_email: str,
    subject: str = "KI-Readiness Report",
    lang: str = "de",
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Schickt HTML an den PDF-Service, der PDF rendert & Mails an user+admin sendet.
    Minimaler Payload → kompatibel zu deiner Node-App (index.js).
    """
    if not PDF_SERVICE_URL:
        raise RuntimeError("PDF_SERVICE_URL is not configured")

    payload = {
        "mode": "auto",
        "timeout": PDF_TIMEOUT,
        "html": html,
        # explizit für dein Logging im PDF-Service:
        "userEmail": user_email,
        "adminEmail": ADMIN_EMAIL,
        "subject": subject,
        "lang": lang,
    }
    if request_id:
        payload["rid"] = request_id

    async with httpx.AsyncClient(timeout=PDF_TIMEOUT + 10) as client:
        r = await client.post(f"{PDF_SERVICE_URL}/generate-pdf", json=payload)
        ok = (200 <= r.status_code < 300)
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}
        return {
            "ok": ok,
            "status": r.status_code,
            "data": data,
            "error": None if ok else (data.get("error") if isinstance(data, dict) else r.text),
            "user": user_email,
            "admin": ADMIN_EMAIL,
        }


# -----------------------------------------------------------------------------
# In-Memory Task-Store für Async-Flow
# -----------------------------------------------------------------------------
TASKS: Dict[str, Dict[str, Any]] = {}

# In‑memory store for submissions; persisted to a JSON file in data/submissions.json.
SUBMISSIONS_FILE = os.path.join("data", "submissions.json")
try:
    # ensure directory exists
    os.makedirs(os.path.dirname(SUBMISSIONS_FILE), exist_ok=True)
except Exception:
    pass
def load_submissions() -> list:
    """Load previously stored submissions from disk."""
    try:
        with open(SUBMISSIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_submissions(subs: list) -> None:
    try:
        with open(SUBMISSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(subs, f, ensure_ascii=False, indent=2)
    except Exception as ex:
        logger.warning("Could not save submissions: %s", ex)
def new_job() -> str:
    return uuid.uuid4().hex


# -----------------------------------------------------------------------------
# Health
# -----------------------------------------------------------------------------
@app.get("/health", response_class=JSONResponse)
def health():
    return {
        "ok": True,
        "version": APP_VERSION,
        "pdf_service": bool(PDF_SERVICE_URL),
        "db": bool(DATABASE_URL),
    }
# -----------------------------------------------------------------------------
# Login
# -----------------------------------------------------------------------------
@app.post("/api/login")
def api_login(body: Dict[str, Any]):
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""

    # 1) DB-Login (pgcrypto)
    if DATABASE_URL and psycopg2 is not None:
        try:
            conn = db_conn()
            cur = conn.cursor()
            # Passwortcheck via pgcrypto: crypt(<pw>, users.password)
            cur.execute(
                "SELECT id, email, role FROM users "
                "WHERE lower(email) = lower(%s) AND password_hash = crypt(%s, password_hash)",
                (email, password),
            )
            row = cur.fetchone()
            cur.close()
            conn.close()
            if row:
                token = create_access_token({"uid": str(row["id"]), "email": row["email"], "role": row["role"]})
                return {"token": token, "email": row["email"], "role": row["role"]}
        except Exception as ex:  # pragma: no cover
            logger.exception("DB login failed: %s", ex)
            # Fallback unten

    # 2) Fallback-Login per ENV (optional)
    if ADMIN_LOGIN_EMAIL and ADMIN_LOGIN_PASSWORD:
        if email == ADMIN_LOGIN_EMAIL.strip().lower() and password == ADMIN_LOGIN_PASSWORD:
            token = create_access_token({"uid": "admin", "email": ADMIN_LOGIN_EMAIL, "role": "admin"})
            return {"token": token, "email": ADMIN_LOGIN_EMAIL, "role": "admin"}

    raise HTTPException(status_code=401, detail="Unauthorized")


# -----------------------------------------------------------------------------
# PDF Smoke-Test (manuell)
# -----------------------------------------------------------------------------
@app.post("/pdf_test")
async def pdf_test(body: Dict[str, Any], user=Depends(current_user)):
    html = body.get("html") or html_fallback()
    lang = (body.get("lang") or "de").lower()
    recipient = resolve_recipient(body, default_email=user["email"])

    rid = uuid.uuid4().hex
    res = await send_html_to_pdf_service(html, recipient, subject="KI-Readiness Report (Test)", lang=lang, request_id=rid)
    logger.info("PDF_SERVICE result | ok=%s status=%s user=%s admin=%s err=%s",
                res["ok"], res["status"], res.get("user"), res.get("admin"), res.get("error"))
    return res


# -----------------------------------------------------------------------------
# Briefing Async → Status
# -----------------------------------------------------------------------------
@app.post("/briefing_async")
async def briefing_async(body: Dict[str, Any], bg: BackgroundTasks, user=Depends(current_user)):
    """
    Startet den End-to-End-Flow (GPT-Analyse → HTML → PDF-Service → Mail).
    Antwortet sofort mit job_id; Ergebnis via /briefing_status/<job_id>.
    """
    lang = (body.get("lang") or "de").lower()
    job_id = new_job()
    rid = job_id  # fürs PDF-Service-Log durchreichen

    TASKS[job_id] = {
        "status": "running",
        "created": int(time.time()),
        "lang": lang,
        "email_admin": ADMIN_EMAIL,
        "email_user": None,
        "html_len": None,
        "pdf_sent": False,
        "pdf_status": None,
        "pdf_error": None,
        "error": None,
    }

    async def run():
        try:
            # 1) Empfänger bestimmen
            user_email = resolve_recipient(body, default_email=user["email"])
            TASKS[job_id]["email_user"] = user_email

            html: str
            if analyze_briefing:
                try:
                    # analyze_briefing kann sync ODER async sein
                    if inspect.iscoroutinefunction(analyze_briefing):
                        result = await analyze_briefing(body)
                    else:
                        result = analyze_briefing(body)

                    if isinstance(result, dict) and "html" in result:
                        html = result["html"]
                    elif isinstance(result, str) and "<html" in result.lower():
                        html = result
                    else:
                        logger.warning("analyze_briefing returned unexpected type: %s", type(result))
                        html = html_fallback(lang)
                except Exception as ex:
                    logger.exception("analyze_briefing failed: %s", ex)
                    html = html_fallback(lang)
            else:
                logger.warning("Analyze module not loaded; using fallback.")
                html = html_fallback(lang)
                html = html_fallback(lang)

            TASKS[job_id]["html_len"] = len(html)

            # Persist submission for admin dashboard
            try:
                # compute a quick readiness score for listing
                score = calc_score_percent(body)
                subs = load_submissions()
                subs.append({
                    "job_id": job_id,
                    "created": int(time.time()),
                    "user_email": user_email,
                    "score_percent": score,
                    "payload": body,
                })
                save_submissions(subs)
            except Exception as ex:
                logger.warning("Could not persist submission: %s", ex)

            # 3) An PDF-Service senden
            res = await send_html_to_pdf_service(html, user_email, subject="KI-Readiness Report", lang=lang, request_id=rid)
            TASKS[job_id]["pdf_sent"] = bool(res["ok"])
            TASKS[job_id]["pdf_status"] = res["status"]
            TASKS[job_id]["pdf_error"] = res["error"]

            logger.info("PDF_SERVICE result | ok=%s status=%s user=%s admin=%s err=%s",
                        res["ok"], res["status"], res.get("user"), res.get("admin"), res.get("error"))

            TASKS[job_id]["status"] = "completed" if res["ok"] else "failed"
        except Exception as ex:
            logger.exception("briefing_async job failed: %s", ex)
            TASKS[job_id]["status"] = "failed"
            TASKS[job_id]["error"] = str(ex)

    # Hintergrund starten
    bg.add_task(run)
    return {"ok": True, "job_id": job_id}


@app.get("/briefing_status/{job_id}")
def briefing_status(job_id: str, user=Depends(current_user)):
    info = TASKS.get(job_id)
    if not info:
        raise HTTPException(status_code=404, detail="unknown job_id")
    return info

# -----------------------------------------------------------------------------
# Admin endpoints for submissions
# -----------------------------------------------------------------------------

@app.get("/admin/submissions", response_class=JSONResponse)
def admin_submissions(user=Depends(current_user)):
    """
    Returns a list of all stored submissions. Only accessible for users with
    the role 'admin'. Each record contains job_id, created timestamp,
    user_email, score_percent and the original payload.
    """
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return load_submissions()

@app.get("/admin/submissions/{job_id}", response_class=JSONResponse)
def admin_get_submission(job_id: str, user=Depends(current_user)):
    """
    Returns the submission details for a specific job_id.
    """
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    subs = load_submissions()
    for s in subs:
        if s.get("job_id") == job_id:
            return s
    raise HTTPException(status_code=404, detail="Submission not found")

@app.post("/admin/submissions/{job_id}/regenerate", response_class=JSONResponse)
async def admin_regenerate(job_id: str, bg: BackgroundTasks, user=Depends(current_user)):
    """
    Regenerates and resends the PDF for a given submission. Only for admin.
    It looks up the original payload and triggers analyze_briefing and PDF
    delivery again. Returns a status JSON similar to briefing_async.
    """
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    subs = load_submissions()
    sub = None
    for s in subs:
        if s.get("job_id") == job_id:
            sub = s
            break
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    payload = sub.get("payload") or {}
    lang = (payload.get("lang") or payload.get("language") or payload.get("sprache") or "de").lower()
    rid = new_job()
    TASKS[rid] = {
        "status": "running",
        "created": int(time.time()),
        "lang": lang,
        "email_admin": ADMIN_EMAIL,
        "email_user": sub.get("user_email"),
        "html_len": None,
        "pdf_sent": False,
        "pdf_status": None,
        "pdf_error": None,
        "error": None,
    }
    async def run_regeneration():
        try:
            # reuse analyze_briefing to generate new HTML and send to PDF service
            html = ""
            if analyze_briefing:
                try:
                    if inspect.iscoroutinefunction(analyze_briefing):
                        result = await analyze_briefing(payload)
                    else:
                        result = analyze_briefing(payload)
                    html = result.get("html") if isinstance(result, dict) else result
                except Exception as ex:
                    logger.exception("analyze_briefing failed in regeneration: %s", ex)
                    html = html_fallback(lang)
            else:
                html = html_fallback(lang)
            TASKS[rid]["html_len"] = len(html)
            res = await send_html_to_pdf_service(html, sub.get("user_email"), subject="KI-Readiness Report (Regeneration)", lang=lang, request_id=rid)
            TASKS[rid]["pdf_sent"] = bool(res.get("ok"))
            TASKS[rid]["pdf_status"] = res.get("status")
            TASKS[rid]["pdf_error"] = res.get("error")
            TASKS[rid]["status"] = "completed" if res.get("ok") else "failed"
        except Exception as ex:
            logger.exception("regenerate job failed: %s", ex)
            TASKS[rid]["status"] = "failed"
            TASKS[rid]["error"] = str(ex)
    bg.add_task(run_regeneration)
    return {"ok": True, "job_id": rid}


# -----------------------------------------------------------------------------
# Startseite (Mini-Hinweis)
# -----------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def root():
    return """
<!doctype html>
<html lang="de"><head><meta charset="utf-8"><title>KI-Readiness Backend</title>
<style>body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;margin:40px;}</style></head>
<body>
  <h1>KI-Readiness Backend</h1>
  <p>Alles läuft. Endpunkte:</p>
  <ul>
    <li><code>GET /health</code></li>
    <li><code>POST /api/login</code> → Token</li>
    <li><code>POST /briefing_async</code> (Bearer)</li>
    <li><code>GET /briefing_status/&lt;job_id&gt;</code> (Bearer)</li>
    <li><code>POST /pdf_test</code> (Bearer)</li>
  </ul>
</body></html>
"""