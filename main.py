# main.py — Hardened (SMTP header sanitize, migration wiring, async mail)
import os
import sys
import time
import uuid
import json
import logging
import importlib
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from jose import jwt
from jose.exceptions import JWTError
import httpx

# Optional DB imports for feedback persistence
try:
    import psycopg2  # type: ignore
    from psycopg2.pool import SimpleConnectionPool  # type: ignore
except Exception:
    psycopg2 = None
    SimpleConnectionPool = None  # type: ignore

# SMTP / Mail
import asyncio
import smtplib
from email.message import EmailMessage
from email.utils import parseaddr, formataddr

# ----------------------------
# SMTP & Migration Settings
# ----------------------------
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "")
FEEDBACK_TO = os.getenv("FEEDBACK_TO")  # e.g. bewertung@ki-sicherheit.jetzt

MIGRATION_ENABLED = os.getenv("MIGRATION_ENABLED", "false").lower() == "true"

# ----------------------------
# Basis-Config & Logger
# ----------------------------
APP_NAME = "KI-Readiness Backend"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(levelname)s %(asctime)s [%(name)s] %(message)s",
)
logger = logging.getLogger("main")

# ----------------------------
# ENV/Settings
# ----------------------------
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-now")
JWT_ALG = os.getenv("JWT_ALG", "HS256")
JWT_EXP_SECONDS = int(os.getenv("JWT_EXP_SECONDS", "86400"))

PDF_SERVICE_URL = os.getenv("PDF_SERVICE_URL", "").rstrip("/")
PDF_TIMEOUT = float(os.getenv("PDF_TIMEOUT", "120"))
PDF_POST_MODE = os.getenv("PDF_POST_MODE", "html").lower()  # "html" oder "json"
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")

CORS_ALLOW = [o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS", "*").split(",")]
if CORS_ALLOW == ["*"]:
    CORS_ALLOW = ["*"]

# ----------------------------
# App & CORS
# ----------------------------
app = FastAPI(title=APP_NAME)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Admin-migration route (optional)
if MIGRATION_ENABLED:
    try:
        from app.routes import admin_migration
        app.include_router(admin_migration.router)
        logger.info("[MIGRATION] Admin route /admin/migrate-feedback enabled")
    except Exception as e:
        logger.exception("[MIGRATION] Router include failed: %s", e)

# ----------------------------
# DB-Pool (optional)
# ----------------------------
DB_POOL = None

def _init_db_pool():
    global DB_POOL
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        logger.warning("[DB] DATABASE_URL fehlt – Feedback wird nur geloggt.")
        return
    if SimpleConnectionPool is None:
        logger.warning("[DB] psycopg2 nicht installiert – Feedback wird nur geloggt.")
        return
    try:
        DB_POOL = SimpleConnectionPool(
            1, 5, dsn,
            connect_timeout=5,
            keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5
        )
        logger.info("[DB] Pool initialisiert")
    except Exception as e:
        logger.exception("[DB] Pool-Init fehlgeschlagen: %s", e)
        DB_POOL = None

@app.on_event("startup")
async def _on_startup_db_pool():
    try:
        _init_db_pool()
    except Exception as e:
        logger.exception("[DB] Startup-Init fehlgeschlagen: %s", e)

@app.on_event("shutdown")
async def _on_shutdown_db_pool():
    global DB_POOL
    try:
        if DB_POOL:
            DB_POOL.closeall()
            DB_POOL = None
            logger.info("[DB] Pool geschlossen")
    except Exception as e:
        logger.exception("[DB] Shutdown-Close fehlgeschlagen: %s", e)

# ----------------------------
# JWT-Helpers
# ----------------------------
def create_access_token(data: Dict[str, Any], expires_in: int = JWT_EXP_SECONDS) -> str:
    payload = data.copy()
    payload["exp"] = int(time.time()) + expires_in
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def decode_token(token: str) -> Dict[str, Any]:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])

def current_user(request: Request) -> Dict[str, Any]:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth.split(" ", 1)[1].strip()
    try:
        claims = decode_token(token)
        return claims
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

# ----------------------------
# Helpers: Templates (minimal Fallbacks)
# ----------------------------
def strip_code_fences(text: str) -> str:
    if not text:
        return text
    t = text.replace("\r", "")
    t = t.replace("```html", "```").replace("```HTML", "```")
    while "```" in t:
        t = t.replace("```", "")
    return t

def load_template(lang: str) -> str:
    base = os.path.join(os.getcwd(), "templates")
    candidates = ["pdf_template_en.html", "pdf_template-en.html"] if lang.startswith("en") else ["pdf_template.html", "pdf_template_de.html"]
    for name in candidates:
        path = os.path.join(base, name)
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                logger.warning("Template read failed (%s): %s", path, repr(e))
    title = "KI-Readiness Report" if lang.startswith("de") else "AI Readiness Report"
    return f"""<!doctype html>
<html lang="{lang}">
<head><meta charset="utf-8"><title>{title}</title>
<style>body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;margin:24px;}}</style></head>
<body>
  <h1>{title}</h1>
  <p>Fallback-Ansicht: Kein Template gefunden. Bitte Templates unter /templates bereitstellen.</p>
  <pre id="raw"></pre>
  <script>try {{
    const raw = JSON.parse(document.body.dataset.raw || "{{}}");
    document.getElementById('raw').textContent = JSON.stringify(raw, null, 2);
  }} catch(e) {{}}</script>
</body>
</html>"""

def render_html_from_report(report: Dict[str, Any], lang: str) -> str:
    html = load_template(lang)
    if not report:
        return html
    out = html
    for k, v in report.items():
        token = "{{ " + str(k) + " }}"
        out = out.replace(token, str(v) if v is not None else "")
    return strip_code_fences(out)

# ----------------------------
# Analyze Loader
# ----------------------------
def load_analyze_module():
    try:
        if "" not in sys.path:
            sys.path.insert(0, "")
        ga = importlib.import_module("gpt_analyze")
        fn = getattr(ga, "analyze_briefing", None)
        if fn is None:
            logger.error("gpt_analyze geladen, aber analyze_briefing nicht gefunden.")
            return None, ga
        logger.info("gpt_analyze geladen: %s", getattr(ga, "__file__", "n/a"))
        return fn, ga
    except Exception as e:
        logger.exception("gpt_analyze Importfehler: %s", e)
        return None, None

# ----------------------------
# PDF-Service
# ----------------------------
async def warmup_pdf_service(request_id: str, base_url: str, timeout: float = 10.0):
    if not base_url:
        return
    try:
        to = httpx.Timeout(connect=timeout, read=timeout, write=timeout, pool=timeout)
        async with httpx.AsyncClient(http2=True, timeout=to) as c:
            r = await c.get(f"{base_url}/health")
            logger.info("[PDF] rid=%s warmup %s", request_id, r.status_code)
    except Exception as e:
        logger.warning("[PDF] rid=%s warmup failed: %s", request_id, repr(e))

async def send_html_to_pdf_service(
    html: str,
    user_email: str,
    subject: str = "KI-Readiness Report",
    lang: str = "de",
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    if not PDF_SERVICE_URL:
        raise RuntimeError("PDF_SERVICE_URL is not configured")
    rid = request_id or uuid.uuid4().hex
    html = strip_code_fences(html or "")
    timeouts = httpx.Timeout(connect=15.0, read=PDF_TIMEOUT, write=30.0, pool=60.0)
    limits = httpx.Limits(max_keepalive_connections=10, max_connections=20, keepalive_expiry=60.0)
    async with httpx.AsyncClient(http2=True, timeout=timeouts, limits=limits) as client:
        last_exc = None
        for attempt in range(1, 4):
            try:
                if PDF_POST_MODE == "json":
                    payload = {
                        "html": html, "to": user_email or "", "adminEmail": ADMIN_EMAIL or "",
                        "subject": subject, "lang": lang, "rid": rid,
                    }
                    resp = await client.post(f"{PDF_SERVICE_URL}/generate-pdf", json=payload)
                else:
                    headers = {
                        "X-Request-ID": rid, "X-User-Email": user_email or "",
                        "X-Subject": subject, "X-Lang": lang,
                        "Accept": "application/pdf", "Content-Type": "text/html; charset=utf-8",
                    }
                    resp = await client.post(f"{PDF_SERVICE_URL}/generate-pdf", headers=headers, content=html.encode("utf-8"))
                ok = 200 <= resp.status_code < 300
                data = {}
                try:
                    data = resp.json()
                except Exception:
                    pass
                logger.info("[PDF] rid=%s attempt=%s status=%s", rid, attempt, resp.status_code)
                return {
                    "ok": ok, "status": resp.status_code, "data": data if data else {"headers": dict(resp.headers)},
                    "error": None if ok else f"HTTP {resp.status_code}", "user": user_email, "admin": ADMIN_EMAIL,
                }
            except (httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                last_exc = e
                wait = 1.8 ** attempt
                logger.warning("[PDF] rid=%s timeout attempt %s/3 → retry in %.2fs", rid, attempt, wait)
                await asyncio.sleep(wait)
            except Exception as e:
                last_exc = e
                logger.warning("[PDF] rid=%s unexpected on attempt %s: %s", rid, attempt, repr(e))
                await asyncio.sleep(1.0)
    raise httpx.ReadTimeout(f"PDF service timed out after retries ({PDF_TIMEOUT}s read timeout).") from last_exc

# ----------------------------
# Auth
# ----------------------------
@app.post("/api/login")
def api_login(body: Dict[str, Any]):
    email = (body.get("email") or "").strip().lower()
    password = (body.get("password") or "").strip()
    if not email or not password:
        raise HTTPException(status_code=400, detail="email/password required")
    token = create_access_token({"sub": email, "email": email, "role": "user"})
    return {"access_token": token, "token_type": "bearer"}

# ----------------------------
# Analyze → HTML
# ----------------------------
async def analyze_to_html(body: Dict[str, Any], lang: str) -> str:
    analyze_fn, _mod = load_analyze_module()
    report: Dict[str, Any] = {}
    if analyze_fn:
        try:
            result = analyze_fn(body, lang=lang)
            if isinstance(result, dict):
                html_ready = result.get("html")
                if isinstance(html_ready, str) and html_ready.strip():
                    return strip_code_fences(html_ready)
                report = result
            elif isinstance(result, str):
                return strip_code_fences(result)
        except Exception as e:
            logger.exception("analyze_briefing failed: %s", e)
    if not report:
        report = {"title": "KI-Readiness Report" if lang.startswith("de") else "AI Readiness Report",
                  "executive_summary": "Analysemodul nicht geladen – Fallback.", "score_percent": 0}
    return render_html_from_report(report, lang)

def resolve_recipient(user_claims: Dict[str, Any], body: Dict[str, Any]) -> str:
    return body.get("to") or user_claims.get("email") or user_claims.get("sub") or ADMIN_EMAIL

# ----------------------------
# Feedback
# ----------------------------
from pydantic import BaseModel

class Feedback(BaseModel):
    email: Optional[str] = None
    variant: Optional[str] = None
    report_version: Optional[str] = None
    hilfe: Optional[str] = None
    verstaendlich_analyse: Optional[str] = None
    verstaendlich_empfehlung: Optional[str] = None
    vertrauen: Optional[str] = None
    dauer: Optional[str] = None
    best: Optional[str] = None
    next: Optional[str] = None
    timestamp: Optional[str] = None

def _clean_header_value(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    v = v.replace("\r", "").replace("\n", "").strip()
    name, addr = parseaddr(v)
    if addr:
        return formataddr((name, addr)) if name else addr
    return v

async def send_feedback_mail_async(payload: Dict[str, Any], user_email_header: Optional[str], ua: str, ip: str):
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS and (FEEDBACK_TO or SMTP_FROM)):
        logger.info("[MAIL] SMTP not configured – skip")
        return
    subject = f"[KI-Feedback] {payload.get('email') or 'anonym'}"
    subject = subject.replace("\r", " ").replace("\n", " ").strip()
    from_addr = _clean_header_value(SMTP_FROM or SMTP_USER)
    to_addr   = _clean_header_value(FEEDBACK_TO or SMTP_FROM or SMTP_USER)
    reply_to  = _clean_header_value(payload.get("email"))

    if not from_addr or not to_addr:
        logger.info("[MAIL] Missing from/to after sanitize – skip")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    if reply_to:
        msg["Reply-To"] = reply_to

    lines = [f"{k}: {v}" for k, v in payload.items()]
    extra = [f"client_ip: {ip}", f"user_agent: {ua}", f"user_header_email: {user_email_header or ''}"]
    msg.set_content("Neues Feedback:\n\n" + "\n".join(lines + [""] + extra))

    def _send():
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            try:
                s.starttls()
            except Exception:
                pass
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _send)

async def _handle_feedback(payload: Feedback, request: Request, authorization: Optional[str] = None):
    try:
        if authorization is None:
            authorization = request.headers.get("authorization")
        user_email = None
        if authorization and authorization.strip().lower().startswith("bearer "):
            token = authorization.split(" ", 1)[1].strip()
            try:
                claims = decode_token(token)
                user_email = claims.get("email") or claims.get("sub")
            except Exception as e:
                logger.info("[FEEDBACK] Token nicht validiert: %s", repr(e))

        data = payload.dict()
        if not data.get("timestamp"):
            from datetime import datetime
            data["timestamp"] = datetime.utcnow().isoformat()

        ua = request.headers.get("user-agent", "")
        ip = request.client.host if request.client else ""

        inserted = False
        if 'DB_POOL' in globals() and DB_POOL:
            try:
                conn = DB_POOL.getconn()
                try:
                    with conn:
                        with conn.cursor() as cur:
                            cur.execute("""
                                CREATE TABLE IF NOT EXISTS feedback (
                                    id SERIAL PRIMARY KEY,
                                    email TEXT,
                                    variant TEXT,
                                    report_version TEXT,
                                    details JSONB,
                                    user_agent TEXT,
                                    ip TEXT,
                                    created_at TIMESTAMPTZ DEFAULT now()
                                );
                            """)
                            cur.execute(
                                "INSERT INTO feedback (email, variant, report_version, details, user_agent, ip) VALUES (%s,%s,%s,%s::jsonb,%s,%s)",
                                (user_email or data.get('email'),
                                 data.get('variant'),
                                 data.get('report_version'),
                                 json.dumps(data, ensure_ascii=False),
                                 ua, ip)
                            )
                    inserted = True
                finally:
                    DB_POOL.putconn(conn)
            except Exception as e:
                logger.exception("[FEEDBACK] DB insert failed: %s", e)

        if not inserted:
            logger.info("[FEEDBACK] (log-only) ip=%s ua=%s data=%s", ip, ua, json.dumps(data, ensure_ascii=False))

        try:
            asyncio.create_task(send_feedback_mail_async(data, user_email, ua, ip))
        except Exception as e:
            logger.warning("[MAIL] dispatch failed: %s", e)

        return {"ok": True, "stored": bool(inserted)}
    except Exception as e:
        logger.exception("[FEEDBACK] Fehler: %s", e)
        raise HTTPException(status_code=500, detail="feedback failed")

@app.post("/feedback")
async def feedback_root(payload: Feedback, request: Request, authorization: Optional[str] = None):
    return await _handle_feedback(payload, request, authorization)

@app.post("/api/feedback")
async def feedback_api(payload: Feedback, request: Request, authorization: Optional[str] = None):
    return await _handle_feedback(payload, request, authorization)

@app.post("/v1/feedback")
async def feedback_v1(payload: Feedback, request: Request, authorization: Optional[str] = None):
    return await _handle_feedback(payload, request, authorization)

# ----------------------------
# Analyze-flow
# ----------------------------
TASKS: Dict[str, Dict[str, Any]] = {}

@app.post("/briefing_async")
async def briefing_async(body: Dict[str, Any], bg: BackgroundTasks, user=Depends(current_user)):
    lang = (body.get("lang") or "de").lower()
    job_id = uuid.uuid4().hex
    rid = job_id

    TASKS[job_id] = {"status": "running", "created": int(time.time()), "lang": lang, "email_admin": ADMIN_EMAIL}

    async def run():
        try:
            await warmup_pdf_service(rid, PDF_SERVICE_URL)
            html = await analyze_to_html(body, lang)
            TASKS[job_id]["html_len"] = len(html)
            user_email = resolve_recipient(user, body)
            if not user_email:
                raise RuntimeError("No recipient (user email) available")
            head = html[:400]
            if ("{{" in head) or ("{%" in head):
                logger.error("[PDF] unresolved template markers detected in head — check call path")
            res = await send_html_to_pdf_service(html, user_email, subject="KI-Readiness Report", lang=lang, request_id=rid)
            TASKS[job_id].update(
                pdf_sent=bool(res["ok"]),
                pdf_status=res["status"],
                pdf_meta=res.get("data"),
                status="done" if res["ok"] else "error",
                error=None if res["ok"] else res.get("error"),
            )
        except Exception as e:
            logger.exception("briefing_async job failed: %s", e)
            TASKS[job_id].update(status="error", error=str(e))

    bg.add_task(run)
    return {"job_id": job_id, "status": "queued"}

@app.get("/briefing_status/{job_id}")
async def briefing_status(job_id: str, user=Depends(current_user)):
    st = TASKS.get(job_id)
    if not st:
        raise HTTPException(status_code=404, detail="unknown job_id")
    return JSONResponse(st)

@app.post("/pdf_test")
async def pdf_test(body: Dict[str, Any], user=Depends(current_user)):
    lang = (body.get("lang") or "de").lower()
    html = (body.get("html") or "<!doctype html><h1>Ping</h1>")
    to = resolve_recipient(user, body)
    await warmup_pdf_service("pdf_test", PDF_SERVICE_URL)
    res = await send_html_to_pdf_service(html, to, subject="KI-Readiness Report (Test)", lang=lang, request_id="pdf_test")
    return res

# ----------------------------
# Health & Diagnose
# ----------------------------
@app.get("/health")
async def health():
    ok = True
    detail = {"ok": ok, "time": int(time.time()), "pdf_service_url": PDF_SERVICE_URL or None,
              "pdf_post_mode": PDF_POST_MODE, "timeout": PDF_TIMEOUT, "version": "2025-09-10"}
    return JSONResponse(detail)

@app.get("/diag/analyze")
def diag_analyze():
    info = {"loaded": False, "has_analyze_briefing": False, "error": None}
    try:
        if "" not in sys.path:
            sys.path.insert(0, "")
        ga = importlib.import_module("gpt_analyze")
        info["loaded"] = True
        info["module"] = getattr(ga, "__file__", "n/a")
        info["has_analyze_briefing"] = hasattr(ga, "analyze_briefing")
        if info["has_analyze_briefing"]:
            ab = getattr(ga, "analyze_briefing")
            info["analyze_briefing_doc"] = getattr(ab, "__doc__", "")
    except Exception as e:
        info["error"] = repr(e)
    return JSONResponse(info)

# ----------------------------
# Root page
# ----------------------------
@app.get("/")
def root():
    return HTMLResponse(f"""<!doctype html>
<html lang="de">
<head><meta charset="utf-8"><title>{APP_NAME}</title>
<style>body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;margin:40px;}}</style></head>
<body>
  <h1>{APP_NAME}</h1>
  <p>Alles läuft. Endpunkte:</p>
  <ul>
    <li><code>GET /health</code></li>
    <li><code>GET /diag/analyze</code></li>
    <li><code>POST /api/login</code> → Token</li>
    <li><code>POST /briefing_async</code> (Bearer)</li>
    <li><code>GET /briefing_status/&lt;job_id&gt;</code> (Bearer)</li>
    <li><code>POST /pdf_test</code> (Bearer)</li>
    <li><code>POST /feedback</code></li>
    <li><code>POST /api/feedback</code></li>
    <li><code>POST /v1/feedback</code></li>
  </ul>
</body></html>""")