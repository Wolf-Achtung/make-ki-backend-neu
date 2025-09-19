import os
import sys
import time
import uuid
import json
import logging
import importlib
import hashlib
from typing import Any, Dict, Optional

# Optional DB (Feedback-Persistenz)
try:
    import psycopg2  # type: ignore
    from psycopg2.pool import SimpleConnectionPool  # type: ignore
except Exception:
    psycopg2 = None
    SimpleConnectionPool = None  # type: ignore

# Web & API
import httpx
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from jose import jwt
from jose.exceptions import JWTError
from pydantic import BaseModel
from contextlib import asynccontextmanager

# Jinja für HTML-Rendering
from jinja2 import Environment, FileSystemLoader, select_autoescape
from urllib.parse import quote_plus
import datetime as dt

# Async E-Mail
import asyncio
import smtplib
from email.message import EmailMessage
from email.utils import parseaddr, formataddr

# ----------------------------
# Basis-Config & Logger
# ----------------------------
APP_NAME = "KI-Readiness Backend"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(levelname)s %(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("backend")

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

# Templates
TEMPLATE_DIR = os.getenv("TEMPLATE_DIR", "templates")   # statt "."
TEMPLATE_DE  = os.getenv("TEMPLATE_DE",  "pdf_template.html")
TEMPLATE_EN  = os.getenv("TEMPLATE_EN",  "pdf_template_en.html")


# SMTP
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "")
FEEDBACK_TO = os.getenv("FEEDBACK_TO")

# Idempotency (Duplikate vermeiden)
IDEMP_DIR = os.getenv("IDEMP_DIR", "/tmp/ki_idempotency")
IDEMP_TTL_SECONDS = int(os.getenv("IDEMP_TTL_SECONDS", "1800"))  # 30 min
os.makedirs(IDEMP_DIR, exist_ok=True)

def _idem_path(key: str) -> str:
    return os.path.join(IDEMP_DIR, f"{key}.json")

def _stable_json(obj: Dict[str, Any]) -> str:
    try:
        return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return str(obj)

def make_idempotency_key(user_email: str, payload: Dict[str, Any], html: Optional[str] = None) -> str:
    base = {"user": (user_email or "").strip().lower(), "payload": payload}
    if html is not None:
        base["html_sha256"] = hashlib.sha256((html or "").encode("utf-8")).hexdigest()
    return hashlib.sha256(_stable_json(base).encode("utf-8")).hexdigest()

def idempotency_get(key: str) -> Optional[Dict[str, Any]]:
    p = _idem_path(key)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        ts = float(data.get("ts", 0))
        if (time.time() - ts) > IDEMP_TTL_SECONDS:
            try: os.remove(p)
            except Exception: pass
            return None
        return data
    except Exception:
        return None

def idempotency_set(key: str, meta: Dict[str, Any]) -> None:
    p = _idem_path(key)
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "meta": meta}, f, ensure_ascii=False)
    except Exception:
        pass

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

def _close_db_pool():
    global DB_POOL
    try:
        if DB_POOL:
            DB_POOL.closeall()
            DB_POOL = None
            logger.info("[DB] Pool geschlossen")
    except Exception as e:
        logger.exception("[DB] Pool-Close fehlgeschlagen: %s", e)

# ----------------------------
# Jinja-Environment
# ----------------------------
def _build_jinja_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True, lstrip_blocks=True,
    )
    env.filters["urlencode"] = lambda s: quote_plus(str(s or ""))
    return env

_JINJA = _build_jinja_env()

def _render_template_file(lang: str, ctx: dict) -> str:
    name = TEMPLATE_DE if (lang or "de").lower().startswith("de") else TEMPLATE_EN
    tpl = _JINJA.get_template(name)
    return tpl.render(**ctx, now=dt.datetime.now)

def _render_template_string(tpl_str: str, ctx: dict) -> str:
    tpl = _JINJA.from_string(tpl_str)
    return tpl.render(**ctx, now=dt.datetime.now)
def _clean_header_value(v: Optional[str]) -> Optional[str]:
    if not v: return None
    v = v.replace("\r", "").replace("\n", "").strip()
    if not v: return None
    name, addr = parseaddr(v)
    if addr:
        return formataddr((name, addr)) if name else addr
    return v

async def send_feedback_mail_async(data: Dict[str, Any], user_email_hdr: Optional[str], ua: str, ip: str) -> None:
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS and (FEEDBACK_TO or SMTP_FROM)):
        logger.info("[MAIL] SMTP not configured – skip")
        return

    subject = f"[KI-Feedback] {data.get('email') or 'anonym'}".replace("\r", " ").replace("\n", " ").strip()
    from_addr = _clean_header_value(SMTP_FROM or SMTP_USER)
    to_addr   = _clean_header_value(FEEDBACK_TO or SMTP_FROM or SMTP_USER)
    reply_to  = _clean_header_value(user_email_hdr or data.get('email'))
    if not from_addr or not to_addr:
        logger.info("[MAIL] Missing from/to after sanitize – skip")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    if reply_to: msg["Reply-To"] = reply_to

    order = ["email","variant","report_version","hilfe","verstaendlich_analyse","verstaendlich_empfehlung","vertrauen","dauer",
             "serio","textstellen","unsicher","features","freitext","tipp_name","tipp_firma","tipp_email","timestamp"]
    seen = set(); fields = []
    for k in order:
        v = data.get(k)
        if v is not None and str(v).strip() != "":
            seen.add(k); fields.append(f"{k}: {v}")
    for k in sorted(data.keys()):
        if k in seen: continue
        v = data[k]
        if v is not None and str(v).strip() != "":
            fields.append(f"{k}: {v}")

    meta = [f"client_ip: {ip}", f"user_agent: {ua}", f"user_header_email: {user_email_hdr or ''}"]
    msg.set_content("Neues Feedback:\n\n" + "\n".join(fields + [""] + meta))

    def _send():
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            try: s.starttls()
            except Exception: pass
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _send)

# ---------- kleine Helpers ----------
def strip_code_fences(text: str) -> str:
    if not text: return text
    t = text.replace("\r", "")
    t = t.replace("```html","```").replace("```HTML","```")
    while "```" in t:
        t = t.replace("```","")
    return t

# ---------- JWT ----------
def create_access_token(data: Dict[str, Any], expires_in: int = JWT_EXP_SECONDS) -> str:
    payload = data.copy(); payload["exp"] = int(time.time()) + expires_in
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def decode_token(token: str) -> Dict[str, Any]:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])

def current_user(request: Request) -> Dict[str, Any]:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth.split(" ", 1)[1].strip()
    try:
        return decode_token(token)
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

# ---------- Diagnose ----------
def load_analyze_module():
    """
    Load gpt_analyze.analyze_briefing with preference for the file next to this main.py.
    Falls back to normal import if the direct load fails. Logs the path to spot shadow copies.
    """
    import os, sys, importlib, importlib.util, logging
    logger = logging.getLogger("backend")
    try:
        importlib.invalidate_caches()
        if "gpt_analyze" in sys.modules:
            del sys.modules["gpt_analyze"]
    except Exception:
        pass
    here = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.join(here, "gpt_analyze.py")
    if os.path.exists(candidate):
        try:
            spec = importlib.util.spec_from_file_location("gpt_analyze", candidate)
            if spec and spec.loader:
                ga = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(ga)
                fn = getattr(ga, "analyze_briefing", None)
                if callable(fn):
                    logger.info("gpt_analyze loaded (direct): %s", getattr(ga, "__file__", "n/a"))
                    return fn, ga
                else:
                    logger.error("gpt_analyze loaded direct but analyze_briefing missing")
        except SyntaxError as e:
            logger.error("gpt_analyze SyntaxError (direct at %s): %s", candidate, e)
        except Exception as e:
            logger.exception("gpt_analyze direct load failed: %s", e)
    try:
        ga = importlib.import_module("gpt_analyze")
        fn = getattr(ga, "analyze_briefing", None)
        if callable(fn):
            logger.info("gpt_analyze loaded (import): %s", getattr(ga, "__file__", "n/a"))
            return fn, ga
        logger.error("gpt_analyze loaded via import, but analyze_briefing not found.")
    except SyntaxError as e:
        logger.error("gpt_analyze SyntaxError (import): %s", e)
    except Exception as e:
        logger.exception("gpt_analyze Importfehler: %s", e)
    return None, None
def _render_final_html_from_result(result: Any, lang: str) -> str:
    """
    Akzeptiert dict oder str:
      - dict mit 'html': ggf. Jinja-String → rendern
      - dict ohne 'html': Datei-Template rendern (alle Keys im Kontext)
      - str: fertiges HTML; wenn noch Jinja-Tags enthalten → rendern
    """
    ctx = result if isinstance(result, dict) else {}
    html = ""
    if isinstance(result, dict):
        html = (result.get("html") or "").strip()
        if html:
            # enthält Jinja-Tags?
            if ("{{" in html) or ("{%" in html):
                return _render_template_string(html, ctx)
            return strip_code_fences(html)
        # kein 'html': Dateitemplate mit Kontext rendern
        return _render_template_file(lang, ctx)
    elif isinstance(result, str):
        s = strip_code_fences(result)
        if ("{{" in s) or ("{%" in s):
            return _render_template_string(s, ctx)
        return s
    # Fallback
    return _render_template_file(lang, ctx)

async def analyze_to_html(body: Dict[str, Any], lang: str) -> str:
    analyze_fn, _mod = load_analyze_module()
    if analyze_fn:
        try:
            result = analyze_fn(body, lang=lang)
            html = _render_final_html_from_result(result, lang)
            # Sicherheitsnetz: keine ungelösten Jinja-Marker in den ersten Bytes
            head = html[:400]
            if ("{{" in head) or ("{%" in head):
                raise RuntimeError("Template not fully rendered – unresolved Jinja tags found")
            return html
        except Exception as e:
            logger.exception("analyze_briefing failed: %s", e)
# Minimaler Fallback (meta/sections enthalten, damit Templates nie crashen)
fallback = {
    "meta": {
        "title": ("KI-Statusbericht" if lang.startswith("de") else "AI Status Report"),
        "report_title": ("KI-Statusbericht" if lang.startswith("de") else "AI Status Report"),
        "language": lang,
        "month_year": "",
        "company": ""
    },
    "sections": {
        "executive_summary": "Analysemodul nicht geladen – Fallback.",
        "quick_wins": "",
        "risks": "",
        "recommendations": "",
        "roadmap": "",
        "compliance": "",
        "funding_programs": "",
        "tools": "",
        "vision": "",
        "gamechanger": ""
    },
    "score_percent": 0,
    "live_box_html": ""
}
return _render_template_file(lang, fallback)


# ---------- Feedback-Model & Handler ----------
class Feedback(BaseModel):
    email: Optional[str] = None
    variant: Optional[str] = None
    report_version: Optional[str] = None
    hilfe: Optional[str] = None
    verstaendlich_analyse: Optional[str] = None
    verstaendlich_empfehlung: Optional[str] = None
    vertrauen: Optional[str] = None
    dauer: Optional[str] = None
    serio: Optional[str] = None
    textstellen: Optional[str] = None
    unsicher: Optional[str] = None
    features: Optional[str] = None
    freitext: Optional[str] = None
    tipp_name: Optional[str] = None
    tipp_firma: Optional[str] = None
    tipp_email: Optional[str] = None
    timestamp: Optional[str] = None
    best: Optional[str] = None
    next: Optional[str] = None
    class Config:
        extra = "allow"

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
        try:
            raw_json = await request.json()
            if not isinstance(raw_json, dict):
                raw_json = {}
        except Exception:
            raw_json = {}
        data = {**payload.dict(exclude_none=True), **{k: v for k, v in raw_json.items() if v is not None}}
        if not data.get("timestamp"):
            data["timestamp"] = dt.datetime.utcnow().isoformat()

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
                                    email TEXT, variant TEXT, report_version TEXT,
                                    details JSONB, user_agent TEXT, ip TEXT,
                                    created_at TIMESTAMPTZ DEFAULT now()
                                );
                            """)
                            cur.execute(
                                "INSERT INTO feedback (email,variant,report_version,details,user_agent,ip) "
                                "VALUES (%s,%s,%s,%s::jsonb,%s,%s)",
                                (user_email or data.get('email'), data.get('variant'),
                                 data.get('report_version'), json.dumps(data, ensure_ascii=False), ua, ip)
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
# ---------- Lifespan statt on_event (keine Deprecation-Warnungen) ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        _init_db_pool()
    except Exception as e:
        logger.exception("[DB] Startup-Init fehlgeschlagen: %s", e)
    yield
    try:
        _close_db_pool()
    except Exception as e:
        logger.exception("[DB] Shutdown-Close fehlgeschlagen: %s", e)

# ---------- App ----------
app = FastAPI(title=APP_NAME, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Endpunkte ----------
@app.get("/health")
async def health():
    return JSONResponse(await health_info())

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

@app.post("/api/login")
def api_login(body: Dict[str, Any]):
    email = (body.get("email") or "").strip().lower()
    password = (body.get("password") or "").strip()
    if not email or not password:
        raise HTTPException(status_code=400, detail="email/password required")
    token = create_access_token({"sub": email, "email": email, "role": "user"})
    return {"access_token": token, "token_type": "bearer"}

# In-Memory Job Store
TASKS: Dict[str, Dict[str, Any]] = {}
def new_job() -> str: return uuid.uuid4().hex
def set_job(job_id: str, **kwargs):
    TASKS.setdefault(job_id, {}); TASKS[job_id].update(kwargs)

# --- PDF Warmup Helper -------------------------------------------------------
# (httpx ist in deiner Datei bereits importiert)
async def warmup_pdf_service(rid: str, base_url: str, timeout: float = 8.0) -> None:
    """
    Ping the PDF service's /health endpoint so the first /generate-pdf call
    avoids cold-start latency. Never raises; only logs.
    """
    if not base_url:
        return
    url = base_url.rstrip("/") + "/health"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            status = getattr(resp, "status_code", "n/a")
        logger.info("[PDF] rid=%s warmup %s", rid, status)
    except Exception as e:
        # bewusst nur warnen – den Report-Flow nicht abbrechen
        logger.warning("[PDF] rid=%s warmup failed: %s", rid, e)


@app.post("/briefing_async")
async def briefing_async(body: Dict[str, Any], bg: BackgroundTasks, user=Depends(current_user)):
    lang = (body.get("lang") or "de").lower()
    job_id = new_job(); rid = job_id
    set_job(job_id, status="running", created=int(time.time()), lang=lang, email_admin=ADMIN_EMAIL)

    async def run():
        try:
            await warmup_pdf_service(rid, PDF_SERVICE_URL)
            html = await analyze_to_html(body, lang)
            set_job(job_id, html_len=len(html))

            user_email = body.get("to") or user.get("email") or user.get("sub") or ADMIN_EMAIL
            if not user_email:
                raise RuntimeError("No recipient (user email) available")

            head = html[:400]
            if ("{{" in head) or ("{%" in head):
                logger.error("[PDF] unresolved template markers detected – aborting PDF send")
                set_job(job_id, status="error", error="Template not fully rendered – unresolved Jinja tags in HTML")
                return

            try:
                pre_key = make_idempotency_key(user_email, body, html)
                prev = idempotency_get(pre_key)
                if prev:
                    logger.info("[IDEMP] hit for user=%s, skipping PDF send", user_email)
                    set_job(job_id, pdf_sent=True, pdf_status=prev.get("meta", {}).get("status"),
                            pdf_meta=prev.get("meta"), status="done", error=None)
                    return
            except Exception as _e:
                logger.warning("[IDEMP] check failed: %s", _e)

            res = await send_html_to_pdf_service(html, user_email, subject="KI-Readiness Report", lang=lang, request_id=rid)
            set_job(job_id, pdf_sent=bool(res.get("ok")), pdf_status=res.get("status"), pdf_meta=res.get("data"),
                    status="done" if res.get("ok") else "error", error=None if res.get("ok") else res.get("error"))

            try:
                if res.get('ok'):
                    idempotency_set(pre_key, res)
            except Exception as _e:
                logger.warning('[IDEMP] save failed: %s', _e)

        except Exception as e:
            logger.exception("briefing_async job failed: %s", e)
            set_job(job_id, status="error", error=str(e))

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
    to = body.get("to") or user.get("email") or user.get("sub") or ADMIN_EMAIL
    await warmup_pdf_service("pdf_test", PDF_SERVICE_URL)
    res = await send_html_to_pdf_service(html, to, subject="KI-Readiness Report (Test)", lang=lang, request_id="pdf_test")
    return res

@app.post("/feedback")
async def feedback_root(payload: Feedback, request: Request, authorization: Optional[str] = None):
    return await _handle_feedback(payload, request, authorization)

@app.post("/api/feedback")
async def feedback_api(payload: Feedback, request: Request, authorization: Optional[str] = None):
    return await _handle_feedback(payload, request, authorization)

@app.post("/v1/feedback")
async def feedback_v1(payload: Feedback, request: Request, authorization: Optional[str] = None):
    return await _handle_feedback(payload, request, authorization)

@app.get("/")
def root():
    return HTMLResponse(f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><title>{APP_NAME}</title>
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
    <li><code>POST /feedback</code> · <code>/api/feedback</code> · <code>/v1/feedback</code></li>
  </ul>
</body></html>""")
