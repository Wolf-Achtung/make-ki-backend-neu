# main.py — FULL (SMTP Admin Notice + Admin PDF copy)
# Version: 2025-09-24
import os, sys, time, uuid, json, logging, importlib, hashlib, re, asyncio, smtplib
from typing import Any, Dict, Optional
import httpx
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from jose import jwt
from jose.exceptions import JWTError
from pydantic import BaseModel
from email.message import EmailMessage
from email.utils import parseaddr, formataddr
import datetime as dt
from jinja2 import Environment, FileSystemLoader, select_autoescape
from urllib.parse import quote_plus

APP_NAME = "KI-Readiness Backend"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(levelname)s %(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("backend")

JWT_SECRET = os.getenv("JWT_SECRET", "change-me")
JWT_ALG = os.getenv("JWT_ALG", "HS256")
JWT_EXP_SECONDS = int(os.getenv("JWT_EXP_SECONDS", "86400"))

PDF_SERVICE_URL = os.getenv("PDF_SERVICE_URL", "").rstrip("/")
PDF_TIMEOUT = float(os.getenv("PDF_TIMEOUT", "90"))
PDF_POST_MODE = os.getenv("PDF_POST_MODE", "html").lower()

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")
ADMIN_NOTIFY = (os.getenv("ADMIN_NOTIFY", "1").strip().lower() in ("1","true","yes","on"))

TEMPLATE_DIR = os.getenv("TEMPLATE_DIR", "templates")
TEMPLATE_DE  = os.getenv("TEMPLATE_DE",  "pdf_template.html")
TEMPLATE_EN  = os.getenv("TEMPLATE_EN",  "pdf_template_en.html")

CORS_ALLOW = [o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS", "*").split(",")]
if CORS_ALLOW == ["*"]: CORS_ALLOW = ["*"]

SMTP_HOST = os.getenv("SMTP_HOST"); SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER"); SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "")
FEEDBACK_TO = os.getenv("FEEDBACK_TO")

IDEMP_DIR = os.getenv("IDEMP_DIR", "/tmp/ki_idempotency"); os.makedirs(IDEMP_DIR, exist_ok=True)
IDEMP_TTL_SECONDS = int(os.getenv("IDEMPOTENCY_TTL_SECONDS", "1800"))

def _idem_path(key: str) -> str: return os.path.join(IDEMP_DIR, f"{key}.json")
def _stable_json(obj: Dict[str, Any]) -> str:
    try: return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    except Exception: return str(obj)

def make_idempotency_key(user_email: str, payload: Dict[str, Any], html: Optional[str] = None) -> str:
    base = {"user": (user_email or "").strip().lower(), "payload": payload}
    if html is not None: base["html_sha256"] = hashlib.sha256((html or "").encode("utf-8")).hexdigest()
    return hashlib.sha256(_stable_json(base).encode("utf-8")).hexdigest()

def idempotency_get(key: str) -> Optional[Dict[str, Any]]:
    p = _idem_path(key)
    if not os.path.exists(p): return None
    try:
        with open(p, "r", encoding="utf-8") as f: data = json.load(f)
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
        with open(p, "w", encoding="utf-8") as f: json.dump({"ts": time.time(), "meta": meta}, f, ensure_ascii=False)
    except Exception: pass

def _build_jinja_env() -> Environment:
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR),
                      autoescape=select_autoescape(["html","xml"]), trim_blocks=True, lstrip_blocks=True)
    env.filters["urlencode"] = lambda s: quote_plus(str(s or ""))
    return env
_JINJA = _build_jinja_env()

def _render_template_file(lang: str, ctx: dict) -> str:
    name = TEMPLATE_DE if (lang or "de").lower().startswith("de") else TEMPLATE_EN
    return _JINJA.get_template(name).render(**ctx, now=dt.datetime.now)

def strip_code_fences(text: str) -> str:
    if not text: return text
    t = text.replace("\r","").replace("```html","```").replace("```HTML","```")
    while "```" in t: t = t.replace("```","")
    return t

# ---- JWT --------------------------------------------------------------------
def create_access_token(data: Dict[str, Any], expires_in: int = JWT_EXP_SECONDS) -> str:
    payload = data.copy(); payload["exp"] = int(time.time()) + expires_in
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def decode_token(token: str) -> Dict[str, Any]:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])

def current_user(request: Request) -> Dict[str, Any]:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "): raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth.split(" ", 1)[1].strip()
    try: return decode_token(token)
    except JWTError as e: raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

# ---- Analyze-Lader ----------------------------------------------------------
def load_analyze_module():
    try:
        import importlib.util
        if "gpt_analyze" in sys.modules: 
            del sys.modules["gpt_analyze"]
        here = os.path.dirname(os.path.abspath(__file__))
        candidate = os.path.join(here, "gpt_analyze.py")
        if os.path.exists(candidate):
            spec = importlib.util.spec_from_file_location("gpt_analyze", candidate)
            if spec and spec.loader:
                ga = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(ga)
                
                # Versuche erst die Live-Version, dann Fallback
                fn = getattr(ga, "analyze_briefing_with_live_data", None)
                if not fn:
                    fn = getattr(ga, "analyze_briefing", None)
                    
                if callable(fn):
                    logger.info("gpt_analyze loaded (direct): %s", getattr(ga, "__file__", "n/a"))
                    return fn, ga
    except Exception as e:
        logger.exception("gpt_analyze direct load failed: %s", e)
    
    try:
        ga = importlib.import_module("gpt_analyze")
        
        # Versuche erst die Live-Version, dann Fallback
        fn = getattr(ga, "analyze_briefing_with_live_data", None)
        if not fn:
            fn = getattr(ga, "analyze_briefing", None)
            
        if callable(fn):
            logger.info("gpt_analyze loaded (import): %s", getattr(ga, "__file__", "n/a"))
            return fn, ga
    except Exception as e:
        logger.exception("gpt_analyze import failed: %s", e)
    
    return None, None

# ---- Health -----------------------------------------------------------------
async def health_info() -> Dict[str, Any]:
    info = {"app": APP_NAME, "time": dt.datetime.utcnow().isoformat()+"Z",
            "pdf_service_url_configured": bool(PDF_SERVICE_URL),
            "templates": {"dir": TEMPLATE_DIR, "de": TEMPLATE_DE, "en": TEMPLATE_EN},
            "admin_email": ADMIN_EMAIL, "status_pdf_service": None}
    if PDF_SERVICE_URL:
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                r = await client.get(PDF_SERVICE_URL.rstrip("/") + "/health")
                info["status_pdf_service"] = getattr(r, "status_code", None)
        except Exception as e:
            info["status_pdf_service"] = f"unreachable: {e.__class__.__name__}"
    return info

# ---- Admin Copy Helpers -----------------------------------------------------
def _clean_header_value(v: Optional[str]) -> Optional[str]:
    if not v: return None
    v = v.replace("\r","").replace("\n","").strip()
    name, addr = parseaddr(v)
    return formataddr((name, addr)) if name and addr else (addr or v)

def _safe_mail_file_name(user_email: str, rid: str, lang: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_.-]+", "_", (user_email or "user"))
    return (f"KI-Statusbericht-{base}-{rid}.pdf" if lang.startswith("de")
            else f"AI-Status-Report-{base}-{rid}.pdf")

async def send_admin_pdf_copy(html: str, user_email: str, lang: str, rid: str) -> dict:
    if not ADMIN_EMAIL:
        logger.info("[ADMIN-PDF] ADMIN_EMAIL not set – skip admin copy")
        return {"ok": False, "error": "ADMIN_EMAIL not set"}
    subject = (f"KI-Readiness Report (Admin-Kopie) – erzeugt von {user_email or 'Unbekannt'}"
               if lang.startswith("de") else
               f"AI Readiness Report (admin copy) – generated by {user_email or 'Unknown'}")
    fname = _safe_mail_file_name(user_email or "user", f"{rid}-admin", lang)
    return await send_html_to_pdf_service(html, ADMIN_EMAIL, subject=subject, lang=lang,
                                          request_id=f"{rid}-admin", file_name=fname)

async def send_admin_notice_async(user_email: str, lang: str, rid: str):
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS and ADMIN_EMAIL):
        logger.info("[ADMIN-NOTICE] SMTP not configured or ADMIN_EMAIL missing – skip")
        return
    subj = (f"Neu: KI-Status Report – ausgelöst von {user_email or 'Unbekannt'}"
            if lang.startswith("de") else
            f"New: AI Status Report – triggered by {user_email or 'Unknown'}")
    body = (f"Job-ID: {rid}\nSprache: {lang}\nEmpfänger (User): {user_email or 'Unbekannt'}\n"
            f"PDF-Service: {PDF_SERVICE_URL}\n"
            "Hinweis: Diese Mail ist die Admin-Notiz. Die PDF-Kopie kommt separat vom PDF-Service.")
    msg = EmailMessage()
    msg["Subject"] = subj
    msg["From"] = _clean_header_value(SMTP_FROM or SMTP_USER)
    msg["To"] = _clean_header_value(ADMIN_EMAIL)
    msg.set_content(body)
    def _send():
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            try: s.starttls()
            except Exception: pass
            s.login(SMTP_USER, SMTP_PASS); s.send_message(msg)
    loop = asyncio.get_event_loop(); await loop.run_in_executor(None, _send)

# ---- PDF Service ------------------------------------------------------------
async def send_html_to_pdf_service(html: str, user_email: str, subject: str, lang: str, request_id: str, file_name: str|None=None) -> dict:
    if not PDF_SERVICE_URL:
        logger.warning("[PDF] rid=%s no PDF_SERVICE_URL configured", request_id)
        return {"ok": False, "error": "PDF_SERVICE_URL not set"}
    url = PDF_SERVICE_URL.rstrip("/") + "/generate-pdf"
    payload = {"html": html, "email": user_email or "", "subject": subject or ("KI-Statusbericht" if lang.startswith("de") else "AI Status Report"),
               "lang": lang, "request_id": request_id,
               "file_name": file_name or (f"KI-Statusbericht-{request_id}.pdf" if lang.startswith("de") else f"AI-Status-Report-{request_id}.pdf")}
    try:
        async with httpx.AsyncClient(timeout=PDF_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
            status = resp.status_code
            try: data = resp.json()
            except Exception: data = {"text": resp.text}
        logger.info("[PDF] rid=%s attempt status=%s", request_id, status)
        ok = 200 <= status < 300
        return {"ok": ok, "status": status, "data": data}
    except Exception as e:
        logger.warning("[PDF] rid=%s send failed: %s", request_id, e)
        return {"ok": False, "error": str(e)}

# ---- Analyze → HTML ---------------------------------------------------------
async def analyze_to_html(body: Dict[str, Any], lang: str) -> str:
    analyze_fn, _mod = load_analyze_module()
    if analyze_fn:
        try:
            result = analyze_fn(body, lang=lang)
            if isinstance(result, dict):
                html = _render_template_file(lang, result) if not (result.get("html") or "").strip() else result.get("html")
            else:
                html = str(result)
            html = strip_code_fences(html or "")
            head = html[:400]
            if ("{{" in head) or ("{%" in head):
                raise RuntimeError("Template not fully rendered – unresolved Jinja tags found")
            return html
        except Exception as e:
            logger.exception("analyze_briefing failed: %s", e)
    return "<!doctype html><meta charset='utf-8'><h1>Report</h1><p>Fallback.</p>"

# ---- FastAPI ----------------------------------------------------------------
app = FastAPI(title=APP_NAME)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ALLOW, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
async def health(): return JSONResponse(await health_info())

@app.post("/api/login")
def api_login(body: Dict[str, Any]):
    email = (body.get("email") or "").strip().lower()
    password = (body.get("password") or "").strip()
    if not email or not password: raise HTTPException(status_code=400, detail="email/password required")
    token = create_access_token({"sub": email, "email": email, "role": "user"})
    return {"access_token": token, "token_type": "bearer"}

TASKS: Dict[str, Dict[str, Any]] = {}
def new_job() -> str: return uuid.uuid4().hex
def set_job(job_id: str, **kwargs): TASKS.setdefault(job_id, {}); TASKS[job_id].update(kwargs)

async def warmup_pdf_service(rid: str, base_url: str, timeout: float = 8.0) -> None:
    if not base_url: return
    url = base_url.rstrip("/") + "/health"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            status = getattr(resp, "status_code", "n/a")
        logger.info("[PDF] rid=%s warmup %s", rid, status)
    except Exception as e:
        logger.warning("[PDF] rid=%s warmup failed: %s", rid, e)

@app.post("/briefing_async")
async def briefing_async(body: Dict[str, Any], bg: BackgroundTasks, user=Depends(current_user)):
    lang = (body.get("lang") or "de").lower()
    job_id = new_job(); rid = job_id
    set_job(job_id, status="running", created=int(time.time()), lang=lang, email_admin=ADMIN_EMAIL)

    async def run():
        try:
            await warmup_pdf_service(rid, PDF_SERVICE_URL)
            html = await analyze_to_html(body, lang); set_job(job_id, html_len=len(html))

            # Empfänger robust ermitteln
            candidate_emails = [
                body.get("to"), body.get("email"), body.get("kontakt_email"),
                body.get("contact_email"), body.get("user_email"),
                user.get("email"), user.get("sub")
            ]
            user_email = next((e for e in candidate_emails if e), None) or ADMIN_EMAIL
            logger.info("[PDF] recipient resolved to: %s", user_email)

            # Idempotency
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

            subject_user = "KI-Readiness Report" if lang.startswith("de") else "AI Readiness Report"
            file_name_user = _safe_mail_file_name(user_email or "user", rid, lang)

            # Versand an User
            res = await send_html_to_pdf_service(html, user_email, subject_user, lang, rid, file_name_user)
            set_job(job_id, pdf_sent=bool(res.get("ok")), pdf_status=res.get("status"),
                    pdf_meta=res.get("data"), status="done" if res.get("ok") else "error",
                    error=None if res.get("ok") else res.get("error"))

            try:
                if res.get('ok'): idempotency_set(pre_key, res)
            except Exception as _e:
                logger.warning('[IDEMP] save failed: %s', _e)

            # Admin-PDF-Kopie + SMTP-Notice
            if res.get("ok") and ADMIN_NOTIFY and ADMIN_EMAIL:
                try:
                    admin_res = await send_admin_pdf_copy(html, user_email, lang, rid)
                    set_job(job_id, admin_sent=bool(admin_res.get("ok")), admin_status=admin_res.get("status"))
                except Exception as e:
                    logger.warning("[ADMIN-PDF] failed: %s", e)
                try:
                    await send_admin_notice_async(user_email, lang, rid)
                except Exception as e:
                    logger.warning("[ADMIN-NOTICE] failed: %s", e)
        except Exception as e:
            logger.exception("briefing_async job failed: %s", e)
            set_job(job_id, status="error", error=str(e))

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
    to = body.get("to") or user.get("email") or user.get("sub") or ADMIN_EMAIL
    await warmup_pdf_service("pdf_test", PDF_SERVICE_URL)
    subject = "KI-Readiness Report (Test)" if lang.startswith("de") else "AI Readiness Report (Test)"
    fname = _safe_mail_file_name(to or 'user', "pdf_test", lang)
    res = await send_html_to_pdf_service(html, to, subject, lang, "pdf_test", fname)
    return res

@app.get("/")
def root():
    return HTMLResponse(f"<!doctype html><meta charset='utf-8'><h1>{APP_NAME}</h1><p>OK</p>")
