# main.py
# FastAPI-Backend für KI-Statusbericht
# - /api/login: liefert gültiges JWT (access_token / token)
# - /briefing_async: baut Report (async Analyze), ruft PDF-Service
# - Jinja-Render mit sicheren Defaults; robuste Fallbacks

from __future__ import annotations
import os, json, asyncio, datetime as dt, logging, inspect, hmac, hashlib, base64
from pathlib import Path
from typing import Dict, Any, Optional

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from jinja2 import Environment, FileSystemLoader, select_autoescape

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(asctime)s [backend] %(message)s")
log = logging.getLogger("backend")

# ---------- App ----------
app = FastAPI(title="KI-Statusbericht Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# ---------- Templates ----------
BASE_DIR = Path(__file__).parent
TPL_DIR = BASE_DIR / "templates"
env = Environment(
    loader=FileSystemLoader(str(TPL_DIR)),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True, lstrip_blocks=True,
)

# ---------- PDF Service ----------
PDF_BASE = os.getenv("PDF_SERVICE_BASE", "https://make-ki-pdfservice-production.up.railway.app")

async def warmup_pdf_service(rid: str):
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=5)) as client:
            r = await client.get(f"{PDF_BASE}/health")
            log.info("[PDF] rid=%s warmup %s", rid, r.status_code)
    except Exception:
        log.warning("[PDF] rid=%s warmup failed", rid)

async def send_html_to_pdf_service(html: str, rid: str) -> Optional[bytes]:
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10)) as client:
            r = await client.post(f"{PDF_BASE}/generate-pdf", json={"html": html})
            log.info("[PDF] rid=%s attempt status=%s", rid, r.status_code)
            if r.status_code == 200:
                return r.content
    except Exception:
        log.exception("[PDF] rid=%s call failed", rid)
    return None

# ---------- JWT Minimal (HS256) ----------
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_TTL_SECONDS = int(os.getenv("JWT_TTL_SECONDS", "7200"))  # 2h

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")

def create_jwt(payload: Dict[str, Any], secret: str = JWT_SECRET) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    h = _b64url(json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode())
    p = _b64url(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode())
    msg = f"{h}.{p}".encode()
    sig = _b64url(hmac.new(secret.encode(), msg, hashlib.sha256).digest())
    return f"{h}.{p}.{sig}"

# ---------- Analyze Loader ----------
def _load_analyze_module():
    try:
        import importlib.util, sys
        mod_path = BASE_DIR / "gpt_analyze.py"
        spec = importlib.util.spec_from_file_location("gpt_analyze", str(mod_path))
        mod = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(mod)  # type: ignore
        log.info("gpt_analyze loaded (direct): %s", mod_path)
        return mod
    except Exception:
        log.exception("failed to load gpt_analyze")
        return None

async def _call_analyze(mod, body: Dict[str,Any], lang: str) -> Dict[str, Any]:
    fn = getattr(mod, "analyze_briefing", None)
    if fn:
        try:
            if inspect.iscoroutinefunction(fn):
                return await fn(body, lang=lang)
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, lambda: fn(body, lang=lang))
        except Exception:
            log.exception("analyze_briefing failed")
            raise
    fn2 = getattr(mod, "analyze", None)
    if fn2:
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, lambda: fn2(body, lang=lang))
        except Exception:
            log.exception("legacy analyze failed")
            raise
    raise RuntimeError("No analyze_briefing/analyze in gpt_analyze.py found")

# ---------- Jinja Render ----------
def _render_template_file(lang: str, ctx: Dict[str,Any]) -> str:
    tpl_name = "pdf_template_en.html" if lang.lower().startswith("en") else "pdf_template.html"
    tpl = env.get_template(tpl_name)
    import datetime as _dt
    meta_defaults = {
        "title": "KI‑Statusbericht" if lang.startswith("de") else "AI Status Report",
        "date": _dt.date.today().isoformat(),
        "lang": lang,
    }
    ctx = dict(ctx or {})
    ctx["meta"] = {**meta_defaults, **(ctx.get("meta") or {})}
    if not ctx.get("sections"):
        ctx["sections"] = [{"id":"empty","title":"Executive Summary","html":"<p>Report konnte nicht generiert werden. Fallback aktiviert.</p>"}]
    ctx["tables"] = ctx.get("tables") or {}
    return tpl.render(**ctx, now=_dt.datetime.now)

async def analyze_to_html(body: Dict[str, Any], lang: str) -> str:
    mod = _load_analyze_module()
    if not mod:
        log.error("gpt_analyze not loaded; using bare template fallback")
        return _render_template_file(lang, {"sections":[]})

    try:
        result = await _call_analyze(mod, body, lang)
        if not isinstance(result, dict) or "sections" not in result:
            log.error("analyze result invalid; using fallback")
            return _render_template_file(lang, {"sections":[]})
        html = _render_template_file(lang, result)
        if not html or len(html) < 1000:
            log.warning("HTML too short; injecting narrative fallback")
            fb = {"meta": result.get("meta", {}), "sections":[{"id":"fb","title":"Executive Summary","html":"<p>Kurzfassung: Die Analyse lieferte zu wenige Inhalte. Fallback aktiviert.</p>"}]}
            return _render_template_file(lang, fb)
        return html
    except Exception as e:
        log.exception("analyze_to_html failed: %s", e)
        return _render_template_file(lang, {"sections":[]})

# ---------- API ----------

@app.get("/health")
async def health():
    return JSONResponse({"ok": True, "ts": dt.datetime.utcnow().isoformat()+"Z"})

@app.post("/api/login")
async def login(request: Request):
    """
    Liefert bei Erfolg ein gültiges JWT unter access_token UND token (beide Keys).
    Auth-Modus:
      - AUTH_MODE=open  → akzeptiert jede E-Mail/Passwort-Kombination (Testbetrieb)
      - AUTH_MODE=strict → vergleicht mit ADMIN_EMAIL / ADMIN_PASSWORD
    """
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    email = (body.get("email") or "").strip().lower()
    password = (body.get("password") or "").strip()

    auth_mode = os.getenv("AUTH_MODE", "open").lower()  # default: open
    admin_email = (os.getenv("ADMIN_EMAIL") or "").strip().lower()
    admin_pwd = os.getenv("ADMIN_PASSWORD") or ""

    if auth_mode == "strict":
        if not (email and password and email == admin_email and password == admin_pwd):
            raise HTTPException(status_code=401, detail="invalid credentials")
    else:
        # open mode: nur minimal prüfen, dass Felder da sind
        if not email or not password:
            raise HTTPException(status_code=400, detail="missing email or password")

    now = dt.datetime.utcnow()
    exp = now + dt.timedelta(seconds=JWT_TTL_SECONDS)
    role = "admin" if email == admin_email and admin_email else "user"
    payload = {"sub": email, "email": email, "role": role, "iat": int(now.timestamp()), "exp": int(exp.timestamp())}
    token = create_jwt(payload)

    return JSONResponse({
        "ok": True,
        "access_token": token,   # <- Frontend sucht zuerst hier
        "token": token,          # <- Fallback für ältere Frontends
        "token_type": "bearer",
        "expires_in": JWT_TTL_SECONDS,
        "email": email
    })

@app.post("/briefing_async")
async def briefing_async(request: Request):
    body = await request.json()
    lang = (body.get("lang") or "de").lower()
    rid = os.urandom(16).hex()

    # Warmup PDF
    await warmup_pdf_service(rid)

    # Analyse → HTML
    html = await analyze_to_html(body, lang)

    # PDF erzeugen (optional)
    pdf = await send_html_to_pdf_service(html, rid)
    return JSONResponse({"ok": True, "rid": rid, "pdf": bool(pdf)})
