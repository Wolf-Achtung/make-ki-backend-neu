# main.py — Gold-Standard Backend (Template-Only) — 2025-09-23
# Änderungen ggü. Ihrer Version:
# - normalize_company(): robustes Mapping, Fallbacks
# - analyze_to_html(): Template-Only + Prompt-Appendix wie gehabt
# - send_html_to_pdf_service(): JSON-minimal bevorzugt, korrekte Header
# - resolve_recipient(): Body.to > JWT.email > ADMIN_EMAIL
# - Startup-Sanity: Tavily-Gate bleibt; Logging gestrafft

import os, re, json, time, hashlib, logging, datetime, asyncio, base64
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import FastAPI, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
from email.message import EmailMessage
from email.utils import parseaddr, formataddr

APP_NAME = "KI-Readiness Backend"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(levelname)s %(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("backend")

# Startup sanity
if (os.getenv("LLM_MODE", "off").lower() != "off") and not os.getenv("OPENAI_API_KEY"):
    logger.warning("[LLM] OPENAI_API_KEY missing -> forcing LLM_MODE=off"); os.environ["LLM_MODE"] = "off"
if not os.getenv("TAVILY_API_KEY"):
    if os.getenv("ALLOW_TAVILY", "0") not in ("0","false","False"):
        logger.warning("[Tavily] TAVILY_API_KEY missing -> forcing ALLOW_TAVILY=0"); os.environ["ALLOW_TAVILY"] = "0"

# JWT / Auth
from jose import jwt
from jose.exceptions import JWTError
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-now")
JWT_ALG = os.getenv("JWT_ALG", "HS256")
JWT_EXP_SECONDS = int(os.getenv("JWT_EXP_SECONDS", "86400"))

def create_access_token(data: Dict[str, Any], expires_in: int = JWT_EXP_SECONDS) -> str:
    payload = data.copy(); payload["exp"] = int(time.time()) + expires_in
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def decode_token(token: str) -> Dict[str, Any]:
    try: return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except JWTError: return {}

# App
app = FastAPI(title=APP_NAME)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS","*").split(",") if o.strip()],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# SMTP feedback (unverändert)
SMTP_HOST = os.getenv("SMTP_HOST"); SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER"); SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or ""); FEEDBACK_TO = os.getenv("FEEDBACK_TO")

def _clean_header_value(v: Optional[str]) -> Optional[str]:
    if not v: return None
    v = v.replace("\\r","").replace("\\n","").strip()
    name, addr = parseaddr(v)
    if addr: return formataddr((name, addr)) if name else addr
    return v

# PG optional (unverändert stark gekürzt)
DB_POOL = None
try:
    import psycopg2
    from psycopg2.pool import SimpleConnectionPool
    if os.getenv("DATABASE_URL"):
      DB_POOL = SimpleConnectionPool(1, 5, os.getenv("DATABASE_URL"))
      logger.info("[DB] Pool initialisiert")
except Exception as e:
    logger.info("[DB] optional: %s", e)

# Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape
TEMPLATE_DIR = Path(os.getenv("TEMPLATE_DIR", "templates"))
TEMPLATE_DE = os.getenv("TEMPLATE_DE", "pdf_template.html")
TEMPLATE_EN = os.getenv("TEMPLATE_EN", "pdf_template_en.html")
_jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=select_autoescape(["html","xml"]))

def _render_template_only(lang: str, context: Dict[str, Any]) -> str:
    tpl_name = TEMPLATE_DE if str(lang).lower().startswith("de") else TEMPLATE_EN
    tpl = _jinja_env.get_template(tpl_name)
    return tpl.render(**context)

def strip_code_fences(s: str) -> str:
    return re.sub(r"^```(html|json)?|```$", "", s.strip(), flags=re.M)

def _has_unresolved_tokens(html: str) -> bool:
    return ("{{" in html) or ("{%" in html)

def _stable_json(obj: Dict[str, Any]) -> str:
    try: return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",",":"))
    except Exception: return str(obj)

# Idempotenz
IDEMP_DIR = os.getenv("IDEMP_DIR", "/tmp/ki_idempotency")
IDEMP_TTL_SECONDS = int(os.getenv("IDEMP_TTL_SECONDS", "1800"))
Path(IDEMP_DIR).mkdir(parents=True, exist_ok=True)
def _idem_path(key: str) -> str: return str(Path(IDEMP_DIR) / f"{key}.json")
def make_idempotency_key(user_email: str, payload: Dict[str, Any], html: Optional[str] = None) -> str:
    base = {"user": (user_email or "").strip().lower(), "payload": payload}
    if html is not None: base["html_sha256"] = hashlib.sha256((html or "").encode("utf-8")).hexdigest()
    return hashlib.sha256(_stable_json(base).encode("utf-8")).hexdigest()
def idempotency_get(key: str) -> Optional[Dict[str, Any]]:
    p = Path(_idem_path(key))
    if not p.is_file(): return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if int(time.time()) - int(data.get("ts", 0)) > IDEMP_TTL_SECONDS: return None
        return data.get("result")
    except Exception: return None
def idempotency_set(key: str, result: Dict[str, Any]) -> None:
    Path(_idem_path(key)).write_text(json.dumps({"ts": int(time.time()), "result": result}, ensure_ascii=False), encoding="utf-8")

# Analyzer
async def analyze_to_html(body: Dict[str, Any], lang: str) -> str:
    def normalize_company(data: Dict[str, Any]) -> Dict[str, Any]:
        c = data.get("company") if isinstance(data.get("company"), dict) else {}
        merged = { **data, **c }
        # Normalize keys
        cn = merged.get("unternehmen") or merged.get("company") or "—"
        br = merged.get("branche") or merged.get("industry") or "—"
        sz = merged.get("unternehmensgroesse") or merged.get("size") or "—"
        lc = merged.get("standort") or merged.get("location") or "—"
        # fallback aus E-Mail Domain
        if (cn == "—") and data.get("_user_email"):
            cn = data["_user_email"].split("@")[-1].split(".")[0].title()
        return {"unternehmen": cn, "branche": br, "unternehmensgroesse": sz, "location": lc}
    # try import analyzer
    report: Dict[str, Any] = {}
    try:
        from gpt_analyze import analyze_briefing
        body["company"] = normalize_company(body)
        report = analyze_briefing(body, lang=lang)
    except Exception as e:
        logger.exception("analyze_briefing failed: %s", e)
        report = {"title": "KI-Readiness Report", "executive_summary": "Analysemodul nicht geladen — Fallback.", "score_percent": 0}

    try:
        html = _render_template_only(lang, report)
        if _has_unresolved_tokens(html): raise RuntimeError("Unresolved template tokens")
        return strip_code_fences(html)
    except Exception as e:
        logger.error("Jinja render failed (%s)", repr(e))
        return "<html><body><h1>Renderfehler</h1><pre>{}</pre></body></html>".format(str(e))

# Auth helper
from fastapi import Request
def current_user(request: Request) -> Dict[str, Any]:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        claims = decode_token(auth[7:])
        if isinstance(claims, dict): return claims
    return {}

def resolve_recipient(user_claims: Dict[str, Any], body: Dict[str, Any]) -> str:
    return body.get("to") or user_claims.get("email") or user_claims.get("sub") or os.getenv("ADMIN_EMAIL","")

# HTTP helpers
async def warmup_pdf_service(rid: str, base_url: str) -> None:
    if not base_url: return
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            await c.get(f"{base_url}/health")
    except Exception:
        pass

async def send_html_to_pdf_service(html: str, user_email: str, *, subject: str, lang: str, request_id: str) -> Dict[str, Any]:
    PDF_SERVICE_URL = os.getenv("PDF_SERVICE_URL","").rstrip("/")
    if not PDF_SERVICE_URL: return {"ok": False, "error": "PDF_SERVICE_URL missing"}
    mode = os.getenv("PDF_POST_MODE","json").lower()
    PDF_JSON_MINIMAL = os.getenv("PDF_JSON_MINIMAL","1") in ("1","true","True")
    timeout_sec = int(os.getenv("PDF_TIMEOUT","120"))
    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            if mode == "json":
                payload = {"html": html} if PDF_JSON_MINIMAL else {"html": html, "to": user_email or "", "adminEmail": os.getenv("ADMIN_EMAIL",""), "subject": subject, "lang": lang, "rid": request_id}
                resp = await client.post(f"{PDF_SERVICE_URL}/generate-pdf", json=payload)
            else:
                headers = {"X-Request-ID": request_id, "X-User-Email": user_email or "", "X-Subject": subject, "X-Lang": lang,
                           "Accept": "application/pdf", "Content-Type": "text/html; charset=utf-8"}
                resp = await client.post(f"{PDF_SERVICE_URL}/generate-pdf", headers=headers, content=html.encode("utf-8"))

        ct = resp.headers.get("content-type","")
        if "application/pdf" in ct:
            return {"ok": True, "status": resp.status_code, "data": {"pdf_stream": True}}
        js = resp.json() if "application/json" in ct else {"text": (resp.text or "")[:1024]}
        return {"ok": (resp.status_code//100)==2, "status": resp.status_code, "data": js, "error": js.get("error")}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# Routes
@app.get("/health")
def health(): return {"ok": True, "ts": int(time.time())}

@app.post("/render_html")
async def render_html_endpoint(body: Dict[str, Any], user=Depends(current_user)):
    lang = (body.get("lang") or "de").lower()
    if user and user.get("email"): body["_user_email"] = user["email"]
    html = await analyze_to_html(body, lang)
    return {"ok": True, "lang": lang, "html": html}

@app.post("/briefing_async")
async def briefing_async(body: Dict[str, Any], bg: BackgroundTasks, user=Depends(current_user)):
    lang = (body.get("lang") or "de").lower()
    job_id = hashlib.sha256(os.urandom(16)).hexdigest()[:16]
    async def run():
        try:
            if user and user.get("email"): body["_user_email"] = user["email"]
            await warmup_pdf_service(job_id, os.getenv("PDF_SERVICE_URL","").rstrip("/"))
            html = await analyze_to_html(body, lang)
            user_email = resolve_recipient(user, body)
            if not user_email: raise RuntimeError("No recipient email")
            res = await send_html_to_pdf_service(html, user_email, subject="KI-Readiness Report", lang=lang, request_id=job_id)
            logger.info("[PDF] send result: %s", res)
        except Exception as e:
            logger.exception("briefing_async failed: %s", e)
    bg.add_task(run)
    return {"ok": True, "job_id": job_id}

@app.post("/pdf_test")
async def pdf_test():
    html = "<html><body><h1>PDF Smoke</h1><p>OK</p></body></html>"
    res = await send_html_to_pdf_service(html, os.getenv("ADMIN_EMAIL",""), subject="Smoke", lang="de", request_id="smoke")
    return res

@app.get("/")
def root(): return {"ok": True, "app": APP_NAME}
