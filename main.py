# main.py
# FastAPI-Backend für KI-Statusbericht – Gold-Standard
# - /api/login: liefert gültiges JWT (access_token / token)
# - /briefing_async: analysiert Briefing, rendert HTML -> PDF, versendet E-Mails (Admin & User)
# - Robuste Analyze-Aufrufe (sync/async), Jinja-Defaults/Guards, HTML-Sanitizing
# - Live-Layer (optional): Tavily für Tools/Förderungen als Fallback-Tabellen

from __future__ import annotations
import os, json, re, asyncio, datetime as dt, logging, inspect, hmac, hashlib, base64, smtplib
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from email.message import EmailMessage

import httpx
from fastapi import FastAPI, Request, HTTPException, Header
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

# ---------- JWT (HS256) ----------
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_TTL_SECONDS = int(os.getenv("JWT_TTL_SECONDS", "7200"))  # 2h

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")

def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)

def create_jwt(payload: Dict[str, Any], secret: str = JWT_SECRET) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    h = _b64url(json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode())
    p = _b64url(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode())
    msg = f"{h}.{p}".encode()
    sig = _b64url(hmac.new(secret.encode(), msg, hashlib.sha256).digest())
    return f"{h}.{p}.{sig}"

def decode_and_verify_jwt(token: str, secret: str = JWT_SECRET) -> Dict[str, Any]:
    try:
        h_b64, p_b64, s_b64 = token.split(".")
        msg = f"{h_b64}.{p_b64}".encode()
        expected = hmac.new(secret.encode(), msg, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64url_decode(s_b64)):
            raise ValueError("invalid signature")
        payload = json.loads(_b64url_decode(p_b64))
        if "exp" in payload and int(payload["exp"]) < int(dt.datetime.utcnow().timestamp()):
            raise ValueError("token expired")
        return payload
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"invalid token: {e}")

# ---------- Analyze Loader ----------
def _load_analyze_module():
    try:
        import importlib.util
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

# ---------- Sanitizing ----------
def sanitize_html(html: str) -> str:
    if not html:
        return ""
    # Entferne Code-Fences/Backticks und Scripts
    html = re.sub(r"```.*?```", "", html, flags=re.S)
    html = re.sub(r"<script\b[^<]*(?:(?!</script>)<[^<]*)*</script>", "", html, flags=re.I)
    return html

# ---------- Live-Layer (Tavily) ----------
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip()
SEARCH_DAYS = int(os.getenv("SEARCH_DAYS", "365"))
SEARCH_DEPTH = os.getenv("SEARCH_DEPTH", "basic")  # basic / advanced

async def _tavily_search(q: str) -> List[Dict[str, str]]:
    if not TAVILY_API_KEY:
        return []
    try:
        payload = {
            "api_key": TAVILY_API_KEY,
            "query": q,
            "search_depth": SEARCH_DEPTH,
            "include_answer": False,
            "max_results": 5,
            "days": SEARCH_DAYS,
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=8)) as client:
            r = await client.post("https://api.tavily.com/search", json=payload)
            if r.status_code != 200:
                log.warning("[Tavily] status=%s for query=%s", r.status_code, q)
                return []
            data = r.json()
        return data.get("results", []) or []
    except Exception:
        log.exception("[Tavily] query failed: %s", q)
        return []

async def _augment_tables_with_live_layer(context: Dict[str, Any]) -> None:
    """
    Füllt context['tables']['tools'] / ['funding'], wenn leer.
    Baut Queries aus Branche/Region/Größe/Hauptleistung.
    """
    tables = context.setdefault("tables", {})
    # Tools
    if not tables.get("tools"):
        branche = (context.get("meta", {}).get("industry") or "").strip() or (context.get("inputs", {}).get("branche") or "")
        q_tools = f"EU-hosted tools stack for {branche or 'SME consulting'} CRM automation research EU data protection"
        res = await _tavily_search(q_tools)
        tools = []
        for it in res:
            tools.append({
                "name": it.get("title") or "Tool",
                "what": (it.get("content") or it.get("snippet") or "").strip()[:240],
                "eu_note": "EU-Hosting/Export prüfen",
                "link": it.get("url") or ""
            })
        # Minimal-kuratierte Default-Stacks, falls Tavily nichts bringt
        if not tools:
            tools = [
                {"name":"CentralStationCRM (DE)", "what":"Leichtgewichtiges CRM für KMU", "eu_note":"DE-Hosting, Export, Rollen/Logs", "link":"https://centralstationcrm.de/"},
                {"name":"n8n (EU/Self-Host)", "what":"Automationsplattform & Integrationen", "eu_note":"Self-Host (EU) oder Cloud EU-Region", "link":"https://n8n.io/"},
                {"name":"DeepL Write (EU)", "what":"Schreib-/Stillektor, Qualitätssteigerung", "eu_note":"EU-Anbieter; Datenmodus prüfen", "link":"https://www.deepl.com/write"}
            ]
        tables["tools"] = tools

    # Funding
    if not tables.get("funding"):
        region = (context.get("meta", {}).get("region") or context.get("inputs", {}).get("bundesland") or "DE")
        size = (context.get("meta", {}).get("size") or context.get("inputs", {}).get("unternehmensgroesse") or "KMU")
        q_funding = f"deutschland {region} foerderung digitalisierung KI KMU programme offizielle stelle antrag link"
        res = await _tavily_search(q_funding)
        programs = []
        for it in res:
            programs.append({
                "program": it.get("title") or "Förderprogramm",
                "who": f"{size} in {region}",
                "note": (it.get("content") or it.get("snippet") or "").strip()[:240],
                "link": it.get("url") or ""
            })
        if not programs:
            programs = [
                {"program":"go-digital / go-inno (BMWK)", "who":"KMU deutschlandweit", "note":"Beratung/Förderung Digitalisierung/KI", "link":"https://www.bmwi.de/"},
                {"program":"IBB / Investitionsbank Berlin", "who":"KMU Berlin", "note":"Landesprogramme (Digitalisierung/Innovation)", "link":"https://www.ibb.de/"},
                {"program":"EU Funding & Tenders", "who":"KMU / Konsortien", "note":"EU-weite Innovations-/Digitalprogramme", "link":"https://ec.europa.eu/info/funding-tenders/"},
            ]
        tables["funding"] = programs

# ---------- Jinja Render ----------
def _compose_meta(lang: str, inputs: Dict[str, Any], email: Optional[str]) -> Dict[str, Any]:
    # Freitext & Schlüsselangaben prominent bereitstellen
    return {
        "title": "KI‑Statusbericht" if lang.startswith("de") else "AI Status Report",
        "date": dt.date.today().isoformat(),
        "lang": lang,
        "contact_email": email or "—",
        "industry": inputs.get("branche") or "—",
        "size": inputs.get("unternehmensgroesse") or "—",
        "region": inputs.get("bundesland") or "—",
        "main_product": (inputs.get("hauptleistung") or "").strip() or "—",
    }

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
        ctx["sections"] = [{
            "id":"empty","title":"Executive Summary" if lang.startswith("en") else "Executive Summary",
            "html":"<p>Report konnte nicht generiert werden. Fallback aktiviert.</p>" if not lang.startswith("en") else
                    "<p>Report could not be generated. Fallback activated.</p>"
        }]
    ctx["tables"] = ctx.get("tables") or {}
    return tpl.render(**ctx, now=_dt.datetime.now)

async def analyze_to_html(body: Dict[str, Any], lang: str, user_email: Optional[str]) -> Tuple[str, Dict[str,Any]]:
    inputs = dict(body or {})
    mod = _load_analyze_module()
    result: Dict[str, Any] = {}
    if mod:
        try:
            result = await _call_analyze(mod, inputs, lang)
        except Exception as e:
            log.exception("analyze_to_html: analyze failed: %s", e)

    # Guard result
    if not isinstance(result, dict):
        result = {}
    # Inject meta + inputs for template use
    result["inputs"] = inputs
    meta = result.get("meta") or {}
    result["meta"] = {**_compose_meta(lang, inputs, user_email), **meta}

    # Live-Layer Fallback-Tabellen (optional)
    try:
        await _augment_tables_with_live_layer(result)
    except Exception:
        log.exception("live-layer augment failed")

    html = _render_template_file(lang, result)
    html = sanitize_html(html)
    if not html or len(html) < 1000:
        log.warning("HTML too short; injecting narrative fallback")
        fb = {
            "meta": result["meta"],
            "sections":[{"id":"fb","title":"Executive Summary","html":"<p>Kurzfassung: zu wenig Inhalte aus der Analyse. Fallback aktiviert.</p>"}],
            "tables": result.get("tables") or {}
        }
        html = _render_template_file(lang, fb)
        html = sanitize_html(html)
    return html, result

# ---------- E-Mail ----------
SMTP_HOST = os.getenv("SMTP_HOST","")
SMTP_PORT = int(os.getenv("SMTP_PORT","587"))
SMTP_USER = os.getenv("SMTP_USER","")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD","")
SMTP_FROM = os.getenv("SMTP_FROM","KI‑Sicherheit <kontakt@ki-sicherheit.jetzt>")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL","")

def _smtp_enabled() -> bool:
    return all([SMTP_HOST, SMTP_PORT, SMTP_FROM])

def _send_mail(to_addr: str, subject: str, text: str, html: Optional[str]=None,
               attachment: Optional[Tuple[bytes,str]]=None, reply_to: Optional[str]=None) -> bool:
    if not _smtp_enabled():
        log.warning("[MAIL] SMTP disabled/misconfigured: host=%s from=%s", SMTP_HOST, SMTP_FROM)
        return False
    try:
        msg = EmailMessage()
        msg["From"] = SMTP_FROM
        msg["To"] = to_addr
        msg["Subject"] = subject
        if reply_to:
            msg["Reply-To"] = reply_to
        if html:
            msg.set_content(text)
            msg.add_alternative(html, subtype="html")
        else:
            msg.set_content(text)
        if attachment:
            data, filename = attachment
            msg.add_attachment(data, maintype="application", subtype="pdf", filename=filename)
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
            s.starttls()
            if SMTP_USER and SMTP_PASSWORD:
                s.login(SMTP_USER, SMTP_PASSWORD)
            s.send_message(msg)
        return True
    except Exception:
        log.exception("[MAIL] send failed to %s", to_addr)
        return False

def _compose_subject_admin(meta: Dict[str,Any]) -> str:
    who = meta.get("industry") or "Unbekannt"
    return f"KI‑Status Report für {who}"

def _compose_subject_user(lang: str) -> str:
    return "Ihr KI‑Statusbericht ist fertig" if lang.startswith("de") else "Your AI Status Report is ready"

# ---------- API ----------

@app.get("/health")
async def health():
    return JSONResponse({"ok": True, "ts": dt.datetime.utcnow().isoformat()+"Z"})

@app.post("/api/login")
async def login(request: Request):
    """
    Liefert bei Erfolg ein gültiges JWT unter access_token UND token (beide Keys).
    AUTH_MODE:
      - open   → akzeptiert jede E-Mail/Passwort-Kombination (Testbetrieb)
      - strict → vergleicht mit ADMIN_EMAIL / ADMIN_PASSWORD
    """
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    email = (body.get("email") or "").strip().lower()
    password = (body.get("password") or "").strip()

    auth_mode = os.getenv("AUTH_MODE", "open").lower()
    admin_email = (os.getenv("ADMIN_EMAIL") or "").strip().lower()
    admin_pwd = os.getenv("ADMIN_PASSWORD") or ""

    if auth_mode == "strict":
        if not (email and password and email == admin_email and password == admin_pwd):
            raise HTTPException(status_code=401, detail="invalid credentials")
    else:
        if not email or not password:
            raise HTTPException(status_code=400, detail="missing email or password")

    now = dt.datetime.utcnow()
    exp = now + dt.timedelta(seconds=JWT_TTL_SECONDS)
    role = "admin" if email == admin_email and admin_email else "user"
    payload = {"sub": email, "email": email, "role": role, "iat": int(now.timestamp()), "exp": int(exp.timestamp())}
    token = create_jwt(payload)

    return JSONResponse({
        "ok": True,
        "access_token": token,   # Frontend sucht zuerst hier
        "token": token,          # Fallback für ältere Frontends
        "token_type": "bearer",
        "expires_in": JWT_TTL_SECONDS,
        "email": email
    })

@app.post("/briefing_async")
async def briefing_async(request: Request, authorization: Optional[str] = Header(None)):
    """
    Nimmt das Formular entgegen, ruft Analyse/Template/PDF und versendet Mails.
    Erwartet Bearer-JWT im Authorization-Header (für user_email/Reply-To).
    """
    body = await request.json()
    lang = (body.get("lang") or "de").lower()
    rid = os.urandom(16).hex()

    # JWT dekodieren
    user_email = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ",1)[1].strip()
        try:
            payload = decode_and_verify_jwt(token)
            user_email = payload.get("email") or payload.get("sub")
        except HTTPException:
            user_email = None

    # Warmup PDF
    await warmup_pdf_service(rid)

    # Analyse → HTML
    html, context = await analyze_to_html(body, lang, user_email)

    # PDF erzeugen
    pdf_bytes = await send_html_to_pdf_service(html, rid)
    has_pdf = bool(pdf_bytes)

    # E-Mail Versand
    # Admin
    meta = context.get("meta", {})
    subj_admin = _compose_subject_admin(meta)
    admin_text = (
        f"Neuer Report wurde erstellt.\n\n"
        f"Branche: {meta.get('industry')}\nGröße: {meta.get('size')}\nRegion: {meta.get('region')}\n"
        f"Kontakt (Formular): {user_email or '—'}\nRID: {rid}\n"
        f"Zeit: {meta.get('date')}\n"
        f"—\nDieser Hinweis wurde automatisiert erzeugt."
    )
    admin_html = admin_text.replace("\n","<br>")

    if ADMIN_EMAIL:
        _send_mail(
            to_addr=ADMIN_EMAIL,
            subject=subj_admin,
            text=admin_text,
            html=admin_html,
            attachment=(pdf_bytes, f"KI-Status-Report.pdf") if has_pdf else None,
            reply_to=user_email
        )
    else:
        log.warning("[MAIL] ADMIN_EMAIL not set; skip admin mail")

    # User
    if user_email and has_pdf:
        subj_user = _compose_subject_user(lang)
        user_text = (
            "Ihr KI‑Statusbericht ist fertig. Vielen Dank für Ihr Vertrauen!\n\n"
            "Hinweis: Dieser Report wurde mit kuratierten Prompts und optionalem Live‑Layer erstellt.\n"
            "Feedback willkommen: https://make.ki-sicherheit.jetzt/feedback/feedback.html"
        ) if lang.startswith("de") else (
            "Your AI Status Report is ready. Thank you!\n\n"
            "This report was created with curated prompts and an optional live layer.\n"
            "We welcome your feedback: https://make.ki-sicherheit.jetzt/feedback/feedback.html"
        )
        user_html = user_text.replace("\n","<br>")
        ok = _send_mail(
            to_addr=user_email,
            subject=subj_user,
            text=user_text,
            html=user_html,
            attachment=(pdf_bytes, f"KI-Status-Report.pdf"),
            reply_to=ADMIN_EMAIL or SMTP_FROM
        )
        if not ok:
            log.warning("[MAIL] user mail failed for %s", user_email)

    return JSONResponse({"ok": True, "rid": rid, "pdf": has_pdf})
