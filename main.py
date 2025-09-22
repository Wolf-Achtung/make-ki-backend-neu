
# main.py — Gold-Standard (Template-Only) with Sofort-Fix
# Changes in this revision:
#   • PDF sender: automatic fallback (HTML<->JSON), body snippet logging, optional script stripping, size cap
#   • Startup sanity: OPENAI_API_KEY missing -> LLM_MODE=off; TAVILY_API_KEY missing -> ALLOW_TAVILY=0
#   • Stable endpoints, Template-Only rendering (Jinja), idempotency, feedback (DB optional)
#   • Health/diag routes preserved
#
# ENV of interest:
#   LOG_LEVEL=info|debug
#   TEMPLATE_DIR=templates, TEMPLATE_DE=pdf_template.html, TEMPLATE_EN=pdf_template_en.html
#   PDF_SERVICE_URL=..., PDF_TIMEOUT=120, PDF_POST_MODE=html|json, PDF_STRIP_SCRIPTS=1, PDF_MAX_BYTES=800000
#   IDEMP_DIR=/tmp/..., IDEMP_TTL_SECONDS=1800
#   LLM_MODE=hybrid|off, OPENAI_API_KEY=...
#   ALLOW_TAVILY=0|1, TAVILY_API_KEY=...

import os, sys, time, uuid, json, logging, importlib, hashlib, re, asyncio, smtplib
from pathlib import Path
from typing import Any, Dict, Optional
from email.message import EmailMessage
from email.utils import parseaddr, formataddr

# --- Logging ----------------------------------------------------------------
APP_NAME = "KI-Readiness Backend"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(levelname)s %(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("backend")

# --- Startup sanity ---------------------------------------------------------
# If LLM is intended but no API key is present, turn it off to avoid 404/401 noise downstream.
if (os.getenv("LLM_MODE", "off").lower() != "off") and not os.getenv("OPENAI_API_KEY"):
    logger.warning("[LLM] OPENAI_API_KEY missing -> setting LLM_MODE=off for this process")
    os.environ["LLM_MODE"] = "off"

# If Tavily is allowed but no key provided, disable to avoid 401 spam.
if not os.getenv("TAVILY_API_KEY"):
    if os.getenv("ALLOW_TAVILY", "0") not in ("0","false","False"):
        logger.warning("[Tavily] TAVILY_API_KEY missing -> forcing ALLOW_TAVILY=0")
    os.environ["ALLOW_TAVILY"] = "0"

# --- JWT / Auth -------------------------------------------------------------
from jose import jwt
from jose.exceptions import JWTError

JWT_SECRET = os.getenv("JWT_SECRET", "change-me-now")
JWT_ALG = os.getenv("JWT_ALG", "HS256")
JWT_EXP_SECONDS = int(os.getenv("JWT_EXP_SECONDS", "86400"))

def create_access_token(data: Dict[str, Any], expires_in: int = JWT_EXP_SECONDS) -> str:
    payload = data.copy(); payload["exp"] = int(time.time()) + expires_in
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def decode_token(token: str) -> Dict[str, Any]:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])

# --- Optional DB (Feedback persistence) ------------------------------------
try:
    import psycopg2  # type: ignore
    from psycopg2.pool import SimpleConnectionPool  # type: ignore
except Exception:
    psycopg2 = None
    SimpleConnectionPool = None  # type: ignore

DB_POOL = None
def _init_db_pool():
    global DB_POOL
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        logger.info("[DB] DATABASE_URL not set — feedback will be logged only"); return
    if SimpleConnectionPool is None:
        logger.info("[DB] psycopg2 missing — feedback will be logged only"); return
    try:
        DB_POOL = SimpleConnectionPool(1, 5, dsn, connect_timeout=5, keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5)
        logger.info("[DB] Pool initialisiert")
    except Exception as e:
        logger.exception("[DB] Pool-Init fehlgeschlagen: %s", e); DB_POOL = None

# --- SMTP (Feedback mail) ---------------------------------------------------
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "")
FEEDBACK_TO = os.getenv("FEEDBACK_TO")

def _clean_header_value(v: Optional[str]) -> Optional[str]:
    if not v: return None
    v = v.replace("\\r", "").replace("\\n", "").strip()
    if not v: return None
    name, addr = parseaddr(v)
    if addr: return formataddr((name, addr)) if name else addr
    return v

async def send_feedback_mail_async(data: Dict[str, Any], user_email_hdr: Optional[str], ua: str, ip: str) -> None:
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS and (FEEDBACK_TO or SMTP_FROM)):
        logger.info("[MAIL] SMTP not configured — skip"); return
    subject = f"[KI-Feedback] {data.get('email') or 'anonym'}".replace("\\r"," ").replace("\\n"," ").strip()
    from_addr = _clean_header_value(SMTP_FROM or SMTP_USER)
    to_addr = _clean_header_value(FEEDBACK_TO or SMTP_FROM or SMTP_USER)
    reply_to = _clean_header_value(user_email_hdr or data.get('email'))
    if not from_addr or not to_addr:
        logger.info("[MAIL] Missing from/to after sanitize — skip"); return
    msg = EmailMessage()
    msg["Subject"] = subject; msg["From"] = from_addr; msg["To"] = to_addr
    if reply_to: msg["Reply-To"] = reply_to
    order = ["email","variant","report_version","hilfe","verstaendlich_analyse","verstaendlich_empfehlung","vertrauen","dauer","serio","textstellen","unsicher","features","freitext","tipp_name","tipp_firma","tipp_email","timestamp"]
    seen=set(); fields=[]
    for k in order:
        v = data.get(k)
        if v is not None and str(v).strip() != "": seen.add(k); fields.append(f"{k}: {v}")
    for k in sorted(data.keys()):
        if k in seen: continue
        v = data[k]
        if v is not None and str(v).strip() != "": fields.append(f"{k}: {v}")
    meta = [f"client_ip: {ip}", f"user_agent: {ua}", f"user_header_email: {user_email_hdr or ''}"]
    msg.set_content("Neues Feedback:\\n\\n" + "\\n".join(fields + [""] + meta))
    def _send():
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            try: s.starttls()
            except Exception: pass
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _send)

# --- FastAPI / CORS ---------------------------------------------------------
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel
import httpx

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")
CORS_ALLOW = [o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS", "*").split(",")]
if CORS_ALLOW == ["*"]:
    CORS_ALLOW = ["*"]

app = FastAPI(title=APP_NAME)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ALLOW, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
async def _on_startup():
    try: _init_db_pool()
    except Exception as e: logger.exception("[DB] Startup-Init fehlgeschlagen: %s", e)

@app.on_event("shutdown")
async def _on_shutdown():
    global DB_POOL
    try:
        if DB_POOL: DB_POOL.closeall(); DB_POOL = None; logger.info("[DB] Pool geschlossen")
    except Exception as e:
        logger.exception("[DB] Shutdown-Close fehlgeschlagen: %s", e)

# --- Templates (Jinja) — Template-Only Rendering ----------------------------
from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATE_DIR = Path(os.getenv("TEMPLATE_DIR", "templates"))
TEMPLATE_DE = os.getenv("TEMPLATE_DE", "pdf_template.html")
TEMPLATE_EN = os.getenv("TEMPLATE_EN", "pdf_template_en.html")
_jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=select_autoescape(["html","xml"]))

def _render_template_only(lang: str, context: Dict[str, Any]) -> str:
    tpl_name = TEMPLATE_DE if str(lang).lower().startswith("de") else TEMPLATE_EN
    tpl = _jinja_env.get_template(tpl_name)
    return tpl.render(**context)

# --- Idempotency ------------------------------------------------------------
IDEMP_DIR = os.getenv("IDEMP_DIR", "/tmp/ki_idempotency")
IDEMP_TTL_SECONDS = int(os.getenv("IDEMP_TTL_SECONDS", "1800"))
os.makedirs(IDEMP_DIR, exist_ok=True)

def _idem_path(key: str) -> str:
    return os.path.join(IDEMP_DIR, f"{key}.json")

def _stable_json(obj: Dict[str, Any]) -> str:
    try: return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",",":"))
    except Exception: return str(obj)

def make_idempotency_key(user_email: str, payload: Dict[str, Any], html: Optional[str] = None) -> str:
    base = {"user": (user_email or "").strip().lower(), "payload": payload}
    if html is not None:
        base["html_sha256"] = hashlib.sha256((html or "").encode("utf-8")).hexdigest()
    raw = _stable_json(base)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def idempotency_get(key: str) -> Optional[Dict[str, Any]]:
    p = _idem_path(key)
    if not os.path.exists(p): return None
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

# --- Helpers ----------------------------------------------------------------
def strip_code_fences(text: str) -> str:
    if not text: return text
    t = text.replace("\\r", "")
    t = t.replace("```html","```").replace("```HTML","```")
    while "```" in t: t = t.replace("```","")
    return t

def load_template(lang: str) -> str:
    base = os.path.join(os.getcwd(), "templates")
    candidates = ["pdf_template_en.html","pdf_template-en.html"] if lang.startswith("en") else ["pdf_template.html","pdf_template_de.html"]
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
<body><h1>{title}</h1><p>Fallback-Ansicht: Kein Template gefunden. Bitte Templates unter /templates bereitstellen.</p></body></html>"""

def render_html_from_report(report: Dict[str, Any], lang: str) -> str:
    html = load_template(lang)
    if not report: return html
    out = html
    for k, v in report.items():
        token = "{{ " + str(k) + " }}"
        out = out.replace(token, str(v) if v is not None else "")
    return strip_code_fences(out)

def _has_unresolved_tokens(html: str) -> bool:
    return bool(re.search(r"({{[^}{]+}}|{%-?|-%}|{%|%})", html))

# --- Analyze Flow (Template-Only Guard) -------------------------------------
async def analyze_to_html(body: Dict[str, Any], lang: str) -> str:
    """
    Calls gpt_analyze.analyze_briefing(body, lang) and *always* renders file templates.
    Analyzer-provided HTML is ignored to prevent narrative output.
    """
    try:
        if "" not in sys.path: sys.path.insert(0, "")
        ga = importlib.import_module("gpt_analyze")
        analyze_fn = getattr(ga, "analyze_briefing", None)
    except Exception as e:
        logger.exception("gpt_analyze import failed: %s", e); analyze_fn = None

    report: Dict[str, Any] = {}
    if analyze_fn:
        try:
            result = analyze_fn(body, lang=lang)
            if isinstance(result, dict): report = result
            elif isinstance(result, str):
                logger.warning("Analyzer returned raw HTML — ignored (Template-Only enforced).")
                report = {}
        except Exception as e:
            logger.exception("analyze_briefing failed: %s", e)

    if not report:
        report = {"title": "KI-Readiness Report" if lang.startswith("de") else "AI Readiness Report",
                  "executive_summary": "Analysemodul nicht geladen — Fallback.", "score_percent": 0}

    try:
        html = _render_template_only(lang, report)
        if _has_unresolved_tokens(html):
            raise RuntimeError("Unresolved template tokens detected in final HTML")
        return strip_code_fences(html)
    except Exception as e:
        logger.error("Jinja render failed (%s) — falling back to simple replacer", repr(e))
        return render_html_from_report(report, lang)

# --- Auth dependency ---------------------------------------------------------
def current_user(request: Request) -> Dict[str, Any]:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth.split(" ", 1)[1].strip()
    try:
        claims = decode_token(token); return claims
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

# --- Feedback model & handlers ----------------------------------------------
class Feedback(BaseModel):
    email: Optional[str] = None; variant: Optional[str] = None; report_version: Optional[str] = None
    hilfe: Optional[str] = None; verstaendlich_analyse: Optional[str] = None; verstaendlich_empfehlung: Optional[str] = None; vertrauen: Optional[str] = None; dauer: Optional[str] = None
    serio: Optional[str] = None; textstellen: Optional[str] = None; unsicher: Optional[str] = None; features: Optional[str] = None; freitext: Optional[str] = None
    tipp_name: Optional[str] = None; tipp_firma: Optional[str] = None; tipp_email: Optional[str] = None
    timestamp: Optional[str] = None; best: Optional[str] = None; next: Optional[str] = None
    class Config: extra = "allow"

async def _handle_feedback(payload: Feedback, request: Request, authorization: Optional[str] = None):
    try:
        if authorization is None: authorization = request.headers.get("authorization")
        user_email = None
        if authorization and authorization.strip().lower().startswith("bearer "):
            token = authorization.split(" ", 1)[1].strip()
            try:
                claims = decode_token(token); user_email = claims.get("email") or claims.get("sub")
            except Exception as e:
                logger.info("[FEEDBACK] Token nicht validiert: %s", repr(e))
        try:
            raw_json = await request.json()
            if not isinstance(raw_json, dict): raw_json = {}
        except Exception: raw_json = {}
        data = {**payload.dict(exclude_none=True), **{k:v for k,v in raw_json.items() if v is not None}}
        if not data.get("timestamp"):
            from datetime import datetime; data["timestamp"] = datetime.utcnow().isoformat()
        ua = request.headers.get("user-agent", ""); ip = request.client.host if request.client else ""
        inserted = False
        if 'DB_POOL' in globals() and DB_POOL:
            try:
                conn = DB_POOL.getconn()
                try:
                    with conn:
                        with conn.cursor() as cur:
                            cur.execute("""CREATE TABLE IF NOT EXISTS feedback (id SERIAL PRIMARY KEY, email TEXT, variant TEXT, report_version TEXT, details JSONB, user_agent TEXT, ip TEXT, created_at TIMESTAMPTZ DEFAULT now());""")
                            cur.execute("INSERT INTO feedback (email, variant, report_version, details, user_agent, ip) VALUES (%s,%s,%s,%s::jsonb,%s,%s)",
                                        (user_email or data.get('email'), data.get('variant'), data.get('report_version'), json.dumps(data, ensure_ascii=False), ua, ip))
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
        logger.exception("[FEEDBACK] Fehler: %s", e); raise HTTPException(status_code=500, detail="feedback failed")

# --- Routes -----------------------------------------------------------------
from fastapi import Body

@app.post("/feedback")
async def feedback_root(payload: Feedback, request: Request, authorization: Optional[str] = None):
    return await _handle_feedback(payload, request, authorization)

@app.post("/api/feedback")
async def feedback_api(payload: Feedback, request: Request, authorization: Optional[str] = None):
    return await _handle_feedback(payload, request, authorization)

@app.post("/v1/feedback")
async def feedback_v1(payload: Feedback, request: Request, authorization: Optional[str] = None):
    return await _handle_feedback(payload, request, authorization)

@app.post("/api/login")
def api_login(body: Dict[str, Any] = Body(...)):
    email = (body.get("email") or "").strip().lower()
    password = (body.get("password") or "").strip()
    if not email or not password:
        raise HTTPException(status_code=400, detail="email/password required")
    token = create_access_token({"sub": email, "email": email, "role": "user"})
    return {"access_token": token, "token_type": "bearer"}

@app.get("/health")
async def health():
    return JSONResponse({
        "ok": True,
        "time": int(time.time()),
        "pdf_service_url": os.getenv("PDF_SERVICE_URL", None),
        "pdf_post_mode": os.getenv("PDF_POST_MODE", "html"),
        "timeout": float(os.getenv("PDF_TIMEOUT", "120")),
        "llm_mode": os.getenv("LLM_MODE", "off"),
        "allow_tavily": os.getenv("ALLOW_TAVILY", "0"),
        "version": "2025-09-22-fix1"
    })

@app.get("/diag/analyze")
def diag_analyze():
    info = {"loaded": False, "has_analyze_briefing": False, "error": None}
    try:
        if "" not in sys.path: sys.path.insert(0, "")
        ga = importlib.import_module("gpt_analyze")
        info["loaded"] = True
        info["module"] = getattr(ga, "__file__", "n/a")
        info["has_analyze_briefing"] = hasattr(ga, "analyze_briefing")
        if info["has_analyze_briefing"]:
            info["analyze_briefing_doc"] = getattr(getattr(ga, "analyze_briefing"), "__doc__", "")
    except Exception as e:
        info["error"] = repr(e)
    return JSONResponse(info)

# --- Render endpoints --------------------------------------------------------
@app.post("/render_html")
async def render_html_endpoint(body: Dict[str, Any], user=Depends(current_user)):
    lang = (body.get("lang") or "de").lower()
    html = await analyze_to_html(body, lang)
    return {"ok": True, "lang": lang, "html": html}

TASKS: Dict[str, Dict[str, Any]] = {}
def new_job() -> str: return uuid.uuid4().hex
def set_job(job_id: str, **kwargs): TASKS.setdefault(job_id, {}); TASKS[job_id].update(kwargs)

def resolve_recipient(user_claims: Dict[str, Any], body: Dict[str, Any]) -> str:
    return body.get("to") or user_claims.get("email") or user_claims.get("sub") or os.getenv("ADMIN_EMAIL","")

@app.post("/briefing_async")
async def briefing_async(body: Dict[str, Any], bg: BackgroundTasks, user=Depends(current_user)):
    lang = (body.get("lang") or "de").lower()
    job_id = new_job(); rid = job_id
    set_job(job_id, status="running", created=int(time.time()), lang=lang, email_admin=os.getenv("ADMIN_EMAIL",""))

    async def run():
        try:
            await warmup_pdf_service(rid, os.getenv("PDF_SERVICE_URL","").rstrip("/"))
            html = await analyze_to_html(body, lang)
            set_job(job_id, html_len=len(html))
            user_email = resolve_recipient(user, body)
            if not user_email: raise RuntimeError("No recipient (user email) available")
            head = html[:400]
            if ("{{" in head) or ("{%" in head):
                logger.error("[PDF] unresolved template markers detected — aborting PDF send")
                set_job(job_id, status="error", error="Template not fully rendered — unresolved Jinja tags in HTML")
                return
            try:
                pre_key = make_idempotency_key(user_email, body, html)
                prev = idempotency_get(pre_key)
                if prev:
                    logger.info("[IDEMP] hit for user=%s, skipping PDF send", user_email)
                    set_job(job_id, pdf_sent=True, pdf_status=prev.get("meta", {}).get("status"), pdf_meta=prev.get("meta"), status="done", error=None)
                    return
            except Exception as _e:
                logger.warning("[IDEMP] check failed: %s", _e)

            res = await send_html_to_pdf_service(html, user_email, subject="KI-Readiness Report", lang=lang, request_id=rid)
            set_job(job_id, pdf_sent=bool(res.get("ok")), pdf_status=res.get("status"), pdf_meta=res.get("data"),
                    status="done" if res.get("ok") else "error", error=None if res.get("ok") else res.get("error"))
            try:
                if res.get('ok'): idempotency_set(pre_key, res)
            except Exception as _e:
                logger.warning('[IDEMP] save failed: %s', _e)
        except Exception as e:
            logger.exception("briefing_async job failed: %s", e); set_job(job_id, status="error", error=str(e))

    bg.add_task(run)
    return {"job_id": job_id, "status": "queued"}

@app.get("/briefing_status/{job_id}")
async def briefing_status(job_id: str, user=Depends(current_user)):
    st = TASKS.get(job_id)
    if not st: raise HTTPException(status_code=404, detail="unknown job_id")
    return JSONResponse(st)

@app.post("/pdf_test")
async def pdf_test(body: Dict[str, Any], user=Depends(current_user)):
    lang = (body.get("lang") or "de").lower()
    html = (body.get("html") or "<!doctype html><h1>Ping</h1>")
    to = resolve_recipient(user, body)
    await warmup_pdf_service("pdf_test", os.getenv("PDF_SERVICE_URL","").rstrip("/"))
    res = await send_html_to_pdf_service(html, to, subject="KI-Readiness Report (Test)", lang=lang, request_id="pdf_test")
    return res

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
    <li><code>POST /render_html</code> (Bearer) – synchrone HTML-Vorschau</li>
    <li><code>POST /briefing_async</code> (Bearer)</li>
    <li><code>GET /briefing_status/&lt;job_id&gt;</code> (Bearer)</li>
    <li><code>POST /pdf_test</code> (Bearer)</li>
    <li><code>POST /feedback</code>, <code>/api/feedback</code>, <code>/v1/feedback</code></li>
  </ul>
</body></html>""")

# --- PDF Service with fallback ----------------------------------------------
PDF_SERVICE_URL = os.getenv("PDF_SERVICE_URL","").rstrip("/")
PDF_TIMEOUT = float(os.getenv("PDF_TIMEOUT","120"))
PDF_POST_MODE = os.getenv("PDF_POST_MODE","html").lower()    # preferred mode
PDF_STRIP_SCRIPTS = os.getenv("PDF_STRIP_SCRIPTS","1") in ("1","true","True")
PDF_MAX_BYTES = int(os.getenv("PDF_MAX_BYTES","800000"))

async def warmup_pdf_service(request_id: str, base_url: str, timeout: float = 10.0):
    if not base_url: return
    try:
        to = httpx.Timeout(connect=timeout, read=timeout, write=timeout, pool=timeout)
        async with httpx.AsyncClient(http2=True, timeout=to) as c:
            r = await c.get(f"{base_url}/health")
            logger.info("[PDF] rid=%s warmup %s", request_id, r.status_code)
    except Exception as e:
        logger.warning("[PDF] rid=%s warmup failed: %s", request_id, repr(e))

def _sanitize_html_for_pdf(html: str) -> str:
    t = html or ""
    if PDF_STRIP_SCRIPTS:
        t = re.sub(r"<script\\b[^>]*>.*?</script>", "", t, flags=re.I|re.S)
    if PDF_MAX_BYTES and len(t.encode("utf-8")) > PDF_MAX_BYTES:
        # try to cut at closing tag boundary
        cut = t.encode("utf-8")[:PDF_MAX_BYTES].decode("utf-8", "ignore")
        t = cut + "\\n<!-- truncated for PDF size cap -->"
    return t

async def send_html_to_pdf_service(html: str, user_email: str, subject: str = "KI-Readiness Report", lang: str = "de", request_id: Optional[str] = None) -> Dict[str, Any]:
    if not PDF_SERVICE_URL:
        raise RuntimeError("PDF_SERVICE_URL is not configured")
    rid = request_id or uuid.uuid4().hex
    html = _sanitize_html_for_pdf(strip_code_fences(html or ""))

    timeouts = httpx.Timeout(connect=15.0, read=PDF_TIMEOUT, write=30.0, pool=60.0)
    limits = httpx.Limits(max_keepalive_connections=10, max_connections=20, keepalive_expiry=60.0)

    preferred = PDF_POST_MODE
    alternate = "json" if preferred == "html" else "html"
    modes_try = [preferred, alternate, preferred]  # third try: preferred again (after trunc/strip applied)

    last_exc = None
    last_status = None
    last_body_snip = None

    async with httpx.AsyncClient(http2=True, timeout=timeouts, limits=limits) as client:
        for attempt, mode in enumerate(modes_try, start=1):
            try:
                if mode == "json":
                    payload = {"html": html, "to": user_email or "", "adminEmail": os.getenv("ADMIN_EMAIL",""), "subject": subject, "lang": lang, "rid": rid}
                    resp = await client.post(f"{PDF_SERVICE_URL}/generate-pdf", json=payload)
                else:
                    headers = {"X-Request-ID": rid, "X-User-Email": user_email or "", "X-Subject": subject, "X-Lang": lang, "Accept": "application/pdf", "Content-Type": "text/html; charset=utf-8"}
                    resp = await client.post(f"{PDF_SERVICE_URL}/generate-pdf", headers=headers, content=html.encode("utf-8"))

                ok = 200 <= resp.status_code < 300
                # capture a small snippet for diagnostics
                body_snip = None
                try:
                    ct = resp.headers.get("content-type","")
                    if "application/json" in ct:
                        body_snip = json.dumps(resp.json(), ensure_ascii=False)[:1024]
                    else:
                        body_snip = (resp.text or "")[:1024]
                except Exception:
                    body_snip = None

                logger.info("[PDF] rid=%s attempt=%s mode=%s status=%s", rid, attempt, mode, resp.status_code)
                if ok:
                    data = {}
                    try: data = resp.json()
                    except Exception: data = {"headers": dict(resp.headers)}
                    return {"ok": True, "status": resp.status_code, "data": data, "error": None, "user": user_email, "admin": os.getenv("ADMIN_EMAIL","")}
                else:
                    last_status = resp.status_code
                    last_body_snip = body_snip
                    # On second failure, try to further sanitize (strip scripts already done; shorten aggressively)
                    if attempt == 2:
                        html = _sanitize_html_for_pdf(html[: int(len(html)*0.8) ])
            except (httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                last_exc = e
                wait = 1.8 ** attempt
                logger.warning("[PDF] rid=%s timeout attempt %s/3 → retry in %.2fs", rid, attempt, wait)
                await asyncio.sleep(wait)
            except Exception as e:
                last_exc = e
                logger.warning("[PDF] rid=%s unexpected on attempt %s: %s", rid, attempt, repr(e))
                await asyncio.sleep(1.0)

    # return structured error (with last status/snippet if available)
    err = f"HTTP {last_status}" if last_status else (f"{type(last_exc).__name__}" if last_exc else "unknown error")
    data = {"last_status": last_status, "body_snip": last_body_snip}
    return {"ok": False, "status": last_status or 0, "data": data, "error": err, "user": user_email, "admin": os.getenv("ADMIN_EMAIL","")}
