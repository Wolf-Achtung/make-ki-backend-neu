# main.py — KI-Readiness Backend (Gold-Standard + Login restored) — 2025-09-23
import os, re, json, time, hashlib, logging, datetime, asyncio, hmac
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import FastAPI, Depends, BackgroundTasks, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
import httpx

APP_NAME = "KI-Readiness Backend"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(levelname)s %(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("backend")

# --- Startup sanity (LLM/Tavily) ---
if (os.getenv("LLM_MODE", "off").lower() != "off") and not os.getenv("OPENAI_API_KEY"):
    logger.warning("[LLM] OPENAI_API_KEY missing -> forcing LLM_MODE=off"); os.environ["LLM_MODE"] = "off"
if not os.getenv("TAVILY_API_KEY"):
    if os.getenv("ALLOW_TAVILY", "0") not in ("0","false","False"):
        logger.warning("[Tavily] TAVILY_API_KEY missing -> forcing ALLOW_TAVILY=0"); os.environ["ALLOW_TAVILY"] = "0"

# --- JWT (Auth) ---
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

# --- App & CORS ---
app = FastAPI(title=APP_NAME)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS","*").split(",") if o.strip()],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# --- Idempotency store ---
IDEMP_DIR = os.getenv("IDEMP_DIR", "/tmp/ki_idempotency"); Path(IDEMP_DIR).mkdir(parents=True, exist_ok=True)
IDEMP_TTL_SECONDS = int(os.getenv("IDEMP_TTL_SECONDS", "1800"))
def _idem_path(key: str) -> str: return str(Path(IDEMP_DIR) / f"{key}.json")
def _stable_json(obj: Dict[str, Any]) -> str:
    try: return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",",":"))
    except Exception: return str(obj)
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

# --- Current user from Bearer ---
def current_user(request: Request) -> Dict[str, Any]:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            claims = decode_token(auth[7:])
            if isinstance(claims, dict): return claims
        except Exception: pass
    return {}

# --- Rate limiter (in-memory; IP+User) ---
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "1") in ("1","true","True")
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW_SEC", "60"))
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "5"))
_rate_buckets: Dict[str, list] = {}
def _rl_key(request: Request, user: Dict[str, Any]) -> str:
    ip = (request.client.host if request and request.client else "0.0.0.0")
    email = (user.get("email") or user.get("sub") or "").lower()
    return f"{ip}|{email}"
def _check_rate_limit(key: str) -> Dict[str,int]:
    now = int(time.time())
    bucket = _rate_buckets.get(key, [])
    bucket = [t for t in bucket if now - t < RATE_LIMIT_WINDOW]
    allowed = len(bucket) < RATE_LIMIT_MAX
    if allowed:
        bucket.append(now); _rate_buckets[key] = bucket
    remaining = max(0, RATE_LIMIT_MAX - len(bucket))
    return {"allowed": int(allowed), "remaining": remaining}

# --- Jinja template env ---
from jinja2 import Environment, FileSystemLoader, select_autoescape
TEMPLATE_DIR = Path(os.getenv("TEMPLATE_DIR", "templates"))
TEMPLATE_DE = os.getenv("TEMPLATE_DE", "pdf_template.html")
TEMPLATE_EN = os.getenv("TEMPLATE_EN", "pdf_template_en.html")
_jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=select_autoescape(["html","xml"]))
def _render_template_only(lang: str, context: Dict[str, Any]) -> str:
    tpl = _jinja_env.get_template(TEMPLATE_DE if lang.startswith("de") else TEMPLATE_EN)
    return tpl.render(**context)
def _has_unresolved_tokens(html: str) -> bool: return ("{{" in html) or ("{%" in html)
def strip_code_fences(s: str) -> str: return re.sub(r"^```(html|json)?|```$", "", s.strip(), flags=re.M)

# --- Analyzer bridge ---
async def analyze_to_html(body: Dict[str, Any], lang: str) -> str:
    def normalize_company(data: Dict[str, Any]) -> Dict[str, Any]:
        c = data.get("company") if isinstance(data.get("company"), dict) else {}
        merged = { **{k:v for k,v in data.items() if k not in ("company",)}, **c }
        cn = merged.get("unternehmen") or merged.get("company") or "—"
        br = merged.get("branche") or merged.get("industry") or "—"
        sz = merged.get("unternehmensgroesse") or merged.get("size") or "—"
        lc = merged.get("standort") or merged.get("location") or "—"
        if (not cn or cn == "—") and data.get("_user_email"):
            cn = data["_user_email"].split("@")[-1].split(".")[0].title()
        return {"unternehmen": cn, "branche": br, "unternehmensgroesse": sz, "location": lc}

    report: Dict[str, Any] = {}
    try:
        from gpt_analyze import analyze_briefing
        if body.get("_user_email"): body.setdefault("meta", {})["created_by"] = body["_user_email"]
        body["company"] = normalize_company(body)
        report = analyze_briefing(body, lang=lang)
    except Exception as e:
        logger.exception("analyze_briefing failed: %s", e)
        now = datetime.date.today().isoformat()
        report = {
          "meta": {"company_name":"—","branche":"—","groesse":"—","standort":"—","date":now,"as_of":now,"created_by":body.get("_user_email","")},
          "executive_summary":"Analysemodul nicht geladen — Fallback.",
          "quick_wins":"Inventur/Policy/Quick Wins.",
          "risks":"Datenqualität, Compliance, Schatten‑IT.",
          "recommendations":"Automatisieren, Governance, Rollen.",
          "roadmap":"0–3 M, 3–6 M, 6–12 M.", "tools_table":"", "funding_table":""
        }

    try:
        html = _render_template_only(lang, report)
        if _has_unresolved_tokens(html): raise RuntimeError("Unresolved template tokens in HTML")
        return strip_code_fences(html)
    except Exception as e:
        logger.error("Jinja render failed: %s", e)
        return f"<html><body><h1>Renderfehler</h1><pre>{str(e)}</pre></body></html>"

# --- Helpers for PDF service ---
async def warmup_pdf_service(rid: str, base_url: str) -> None:
    if not base_url: return
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"{base_url}/health")
            logger.info("[PDF] rid=%s warmup %s", rid, r.status_code)
    except Exception: pass

async def send_html_to_pdf_service(html: str, user_email: str, *, subject: str, lang: str, request_id: str) -> Dict[str, Any]:
    PDF_SERVICE_URL = os.getenv("PDF_SERVICE_URL","").rstrip("/")
    if not PDF_SERVICE_URL: return {"ok": False, "error": "PDF_SERVICE_URL missing"}
    mode = os.getenv("PDF_POST_MODE","json").lower()  # "json" | "html"
    PDF_JSON_MINIMAL = os.getenv("PDF_JSON_MINIMAL","1") in ("1","true","True")
    timeout_sec = int(os.getenv("PDF_TIMEOUT","120"))

    headers = {"X-Request-ID": request_id, "X-User-Email": user_email or "", "X-Subject": subject, "X-Lang": lang}
    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            if mode == "json":
                payload = {"html": html} if PDF_JSON_MINIMAL else {"html": html, "to": user_email or "", "subject": subject, "lang": lang, "rid": request_id}
                resp = await client.post(f"{PDF_SERVICE_URL}/generate-pdf", json=payload, headers=headers)
            else:
                headers.update({"Accept":"application/pdf","Content-Type":"text/html; charset=utf-8"})
                resp = await client.post(f"{PDF_SERVICE_URL}/generate-pdf", headers=headers, content=html.encode("utf-8"))

        ct = resp.headers.get("content-type","")
        status = resp.status_code
        logger.info("[PDF] rid=%s attempt=1 mode=%s status=%s ct=%s", request_id, mode, status, ct)
        if "application/pdf" in ct:
            return {"ok": True, "status": status, "data": {"pdf_stream": True}}
        js = resp.json() if "application/json" in ct else {"text": (resp.text or "")[:1024]}
        return {"ok": (status//100)==2, "status": status, "data": js, "error": js.get("error")}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# -------------------------
#      LOGIN  (RESTORED)
# -------------------------
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

def _load_users() -> Dict[str, str]:
    # Preferred: JSON dict {email: password}
    raw = os.getenv("LOGIN_USERS_JSON","").strip()
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return {k.lower(): str(v) for k,v in data.items()}
            if isinstance(data, list):
                # list of {"email": "...", "password": "..."}
                d = {}
                for it in data:
                    if isinstance(it, dict) and it.get("email"):
                        d[str(it["email"]).lower()] = str(it.get("password",""))
                return d
        except Exception as e:
            logger.error("LOGIN_USERS_JSON parse error: %s", e)
    # Fallback: single test user
    u = os.getenv("TEST_LOGIN_USER","").lower()
    p = os.getenv("TEST_LOGIN_PASS","")
    return {u: p} if u else {}

def _verify_user(email: str, password: str) -> bool:
    users = _load_users()
    allow_any = os.getenv("LOGIN_ALLOW_ANY_PASSWORD","0").lower() in ("1","true","yes")
    if email.lower() in users:
        stored = users[email.lower()] or ""
        return True if allow_any else hmac.compare_digest(password, stored)
    # Optional: allow login if no users configured but allow_any=1
    if allow_any and users == {}:
        return True
    return False

@app.post("/api/login")
async def login_endpoint(req: LoginRequest):
    if not _verify_user(req.email, req.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": req.email, "email": req.email})
    return {"access_token": token, "token_type": "bearer"}

@app.get("/api/me")
async def me_endpoint(user=Depends(current_user)):
    if not user or not (user.get("email") or user.get("sub")):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"ok": True, "email": user.get("email") or user.get("sub")}

@app.post("/api/logout")
async def logout_endpoint():
    # stateless JWT; nothing to invalidate serverside
    return {"ok": True}

# --- Routes for report ---
@app.get("/health")
def health(): return {"ok": True, "ts": int(time.time()), "app": APP_NAME}

@app.post("/render_html")
async def render_html_endpoint(body: Dict[str, Any], request: Request, user=Depends(current_user)):
    lang = (body.get("lang") or "de").lower()
    if user and user.get("email"): body["_user_email"] = user["email"]
    html = await analyze_to_html(body, lang)
    return {"ok": True, "lang": lang, "html": html}

@app.post("/briefing_async")
async def briefing_async(body: Dict[str, Any], request: Request, bg: BackgroundTasks, user=Depends(current_user)):
    if RATE_LIMIT_ENABLED:
        rl = _check_rate_limit(_rl_key(request, user))
        if not rl["allowed"]:
            raise HTTPException(status_code=429, detail=f"Rate limit exceeded. Retry later. Remaining=0")
    lang = (body.get("lang") or "de").lower()
    job_id = hashlib.sha256(os.urandom(16)).hexdigest()[:16]
    async def run():
        try:
            if user and user.get("email"): body["_user_email"] = user["email"]
            await warmup_pdf_service(job_id, os.getenv("PDF_SERVICE_URL","").rstrip("/"))
            html = await analyze_to_html(body, lang)
            user_email = body.get("to") or user.get("email") or user.get("sub") or os.getenv("ADMIN_EMAIL","")
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
