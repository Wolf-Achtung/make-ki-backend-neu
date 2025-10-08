# filename: main.py
# -*- coding: utf-8 -*-
"""
Production API für KI‑Status‑Report (Gold‑Standard+, Render‑only)

- /health           → JSON Health (mit Deep‑Probes)
- /health/html      → HTML‑Dashboard
- /metrics          → Prometheus
- /briefing_async   → Report erzeugen, PDF via externem Service rendern, SMTP‑Versand

Siehe Logs: Tavily 401→400, Perplexity 400→200 sowie /render-pdf 404→/generate-pdf 200.  :contentReference[oaicite:7]{index=7}
"""

from __future__ import annotations

import base64, datetime as dt, json, logging, os, re, smtplib, time, uuid
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from typing import Any, Dict, List, Optional

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from jose import jwt
from jose.exceptions import JWTError
from pydantic import BaseModel

# --- Prometheus --------------------------------------------------------------
try:
    from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
    PROM = True
    REG = CollectorRegistry(auto_describe=True)
    REQ_TOTAL = Counter("kiapi_http_requests_total","HTTP requests",["method","route","status"],registry=REG)
    REQ_LAT   = Histogram("kiapi_http_request_seconds","Request duration",["route"],registry=REG,buckets=(0.05,0.1,0.25,0.5,1,2,4,8,15))
    RENDER_LAT= Histogram("kiapi_pdf_render_seconds","PDF render seconds",registry=REG,buckets=(0.1,0.25,0.5,1,2,4,8,15))
    INFLIGHT  = Gauge("kiapi_inflight_requests","in flight",registry=REG)
except Exception:
    PROM = False

APP_NAME = os.getenv("APP_NAME","make-ki-backend")
LOG_LEVEL = os.getenv("LOG_LEVEL","INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("backend")

JWT_SECRET = os.getenv("JWT_SECRET", os.getenv("SECRET_KEY","dev-secret"))
JWT_ALGO = "HS256"
IDEMPOTENCY_TTL_SECONDS = int(os.getenv("IDEMPOTENCY_TTL_SECONDS","3600"))
IDEMPOTENCY_DIR = os.getenv("IDEMPOTENCY_DIR","/tmp/ki_idempotency")
BASE_DIR = os.path.abspath(os.getenv("APP_BASE", os.getcwd()))

PDF_SERVICE_URL = (os.getenv("PDF_SERVICE_URL") or "").rstrip("/")
_pdf_timeout_raw = int(os.getenv("PDF_TIMEOUT","45"))
PDF_TIMEOUT = _pdf_timeout_raw / 1000 if _pdf_timeout_raw > 1000 else _pdf_timeout_raw
PDF_MAX_BYTES = int(os.getenv("PDF_MAX_BYTES", str(10*1024*1024)))
PDF_STRIP_SCRIPTS = os.getenv("PDF_STRIP_SCRIPTS","1").strip().lower() in {"1","true","yes"}

SEND_TO_USER = os.getenv("SEND_TO_USER","1").strip().lower() in {"1","true","yes"}
ADMIN_NOTIFY = os.getenv("ADMIN_NOTIFY","1").strip().lower() in {"1","true","yes"}
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", os.getenv("SMTP_FROM",""))

SMTP_HOST=os.getenv("SMTP_HOST"); SMTP_PORT=int(os.getenv("SMTP_PORT","587"))
SMTP_USER=os.getenv("SMTP_USER"); SMTP_PASS=os.getenv("SMTP_PASS")
SMTP_FROM=os.getenv("SMTP_FROM", SMTP_USER or "noreply@example.com")
SMTP_FROM_NAME=os.getenv("SMTP_FROM_NAME","KI‑Sicherheit")
MAIL_SUBJECT_PREFIX=os.getenv("MAIL_SUBJECT_PREFIX","KI‑Ready")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY","")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY","")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY","")
PERPLEXITY_MODEL = os.getenv("PERPLEXITY_MODEL","sonar-small")

CORS_ALLOW=[o.strip() for o in (os.getenv("CORS_ALLOW_ORIGINS") or "*").split(",") if o.strip()] or ["*"]

def _now_str()->str: return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def _sanitize_email(v:Optional[str])->str: _,addr=parseaddr(v or ""); return addr or ""
def _lang_from_body(b:Dict[str,Any])->str:
    lang=str(b.get("lang") or b.get("language") or "de").lower(); return "de" if lang.startswith("de") else "en"
def _sha256(s:str)->str:
    import hashlib; return hashlib.sha256(s.encode("utf-8")).hexdigest()
def _idem_seen(key:str)->bool:
    p=os.path.join(IDEMPOTENCY_DIR,key); os.makedirs(IDEMPOTENCY_DIR, exist_ok=True)
    if os.path.exists(p):
        try:
            age=time.time()-os.path.getmtime(p)
            if age < IDEMPOTENCY_TTL_SECONDS: return True
        except Exception: return True
    try:
        with open(p,"w",encoding="utf-8") as f: f.write(_now_str())
    except Exception: return False
    return False

def _smtp_send(msg:EmailMessage)->None:
    if not SMTP_HOST or not SMTP_FROM: log.info("[mail] SMTP disabled/unconfigured"); return
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
        try: s.starttls()
        except Exception: pass
        if SMTP_USER and SMTP_PASS: s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)

def _recipient_from(body:Dict[str,Any], fallback:str)->str:
    ans=body.get("answers") or {}
    cand=ans.get("to") or ans.get("email") or body.get("to") or body.get("email") or fallback
    return _sanitize_email(cand)

def _display_name_from(body:Dict[str,Any])->str:
    for key in ("unternehmen","firma","company","company_name","organization"):
        val=(body.get("answers") or {}).get(key) or body.get(key)
        if val: return str(val)[:64]
    email=_recipient_from(body, ADMIN_EMAIL)
    return (email.split("@")[0] if email else "Customer").title()

def _build_subject(prefix:str, lang:str, name:str)->str:
    core="KI‑Status Report" if lang=="de" else "AI Status Report"
    return f"{prefix}/{name} – {core}"

def _safe_pdf_filename(name:str, lang:str)->str:
    dn=re.sub(r"[^a-zA-Z0-9_.-]+","_",name) or "user"
    return f"KI-Status-Report-{dn}-{lang}.pdf"

# ------------------------------ Health ---------------------------------------
async def _gather_health(deep:int=0)->Dict[str,Any]:
    out={"ok":True,"app":APP_NAME,"ts":_now_str(),"deep":deep,"env":{
        "OPENAI_API_KEY":bool(OPENAI_API_KEY),"TAVILY_API_KEY":bool(TAVILY_API_KEY),
        "PERPLEXITY_API_KEY":bool(PERPLEXITY_API_KEY),"PDF_SERVICE_URL":bool(PDF_SERVICE_URL),
        "SMTP_CONFIGURED":bool(SMTP_HOST and SMTP_FROM)
    },"pdf":{},"apis":{},"data":{}}

    pdf={"url":PDF_SERVICE_URL,"reachable":False,"detail":"not configured"}
    if PDF_SERVICE_URL:
        try:
            async with httpx.AsyncClient(timeout=4.0) as cli:
                try:
                    r=await cli.get(f"{PDF_SERVICE_URL}/health")
                    if r.status_code==200: pdf.update({"reachable":True,"detail":"/health:200"})
                except Exception: pass
                if not pdf["reachable"]:
                    try:
                        r=await cli.request("HEAD", f"{PDF_SERVICE_URL}/generate-pdf")
                        if 200<=r.status_code<500: pdf.update({"reachable":True,"detail":f"HEAD /generate-pdf:{r.status_code}"})
                    except Exception: pass
                if deep>=2 and not pdf["reachable"]:
                    try:
                        r=await cli.post(f"{PDF_SERVICE_URL}/generate-pdf", json={"html":"<b>ping</b>","return_pdf_bytes":False})
                        if r.status_code==200: pdf.update({"reachable":True,"detail":"POST /generate-pdf:200"})
                    except Exception as exc:
                        pdf["detail"]=f"POST fail:{exc}"
        except Exception as exc: pdf["detail"]=str(exc)
    out["pdf"]=pdf; out["ok"] &= pdf.get("reachable",False) or not PDF_SERVICE_URL

    tav={"key":bool(TAVILY_API_KEY),"host":"api.tavily.com","reachable":False,"detail":"skipped"}
    if deep>=1:
        try:
            async with httpx.AsyncClient(timeout=4.0) as cli:
                r=await cli.get("https://api.tavily.com")
                tav["reachable"]= r.status_code in (200,404,405); tav["detail"]=f"GET /:{r.status_code}"
        except Exception as exc: tav["detail"]=f"host ping failed:{exc}"
    out["apis"]["tavily"]=tav; out["ok"] &= tav["key"]

    pplx={"key":bool(PERPLEXITY_API_KEY),"host":"api.perplexity.ai","reachable":False,"detail":"skipped"}
    if deep>=1:
        try:
            async with httpx.AsyncClient(timeout=4.0) as cli:
                r=await cli.get("https://api.perplexity.ai"); pplx["reachable"]= r.status_code in (200,404,405); pplx["detail"]=f"GET /:{r.status_code}"
        except Exception as exc: pplx["detail"]=f"host ping failed:{exc}"
    out["apis"]["perplexity"]=pplx; out["ok"] &= pplx["key"]

    # Daten-Counts
    try:
        import csv
        with open(os.path.join(BASE_DIR,"data","tools.csv"),"r",encoding="utf-8") as f:
            out["data"]["tools"]={"count": sum(1 for _ in csv.DictReader(f))}
    except Exception:
        out["data"]["tools"]={"count":0}

    try:
        import csv
        with open(os.path.join(BASE_DIR,"data","foerderprogramme.csv"),"r",encoding="utf-8") as f:
            out["data"]["funding"]={"count": sum(1 for _ in csv.DictReader(f))}
    except Exception:
        out["data"]["funding"]={"count":0}
    return out

app = FastAPI(title=APP_NAME)
@app.middleware("http")
async def _metrics_mw(request:Request, call_next):
    start=time.perf_counter()
    if PROM: INFLIGHT.inc()
    try:
        resp = await call_next(request); return resp
    finally:
        dur=time.perf_counter()-start
        if PROM:
            REQ_TOTAL.labels(request.method, request.url.path, str(getattr(resp,"status_code",200))).inc()
            REQ_LAT.labels(request.url.path).observe(dur)
            INFLIGHT.dec()

app.add_middleware(CORSMiddleware, allow_origins=CORS_ALLOW, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
async def health(deep:int=Query(0,ge=0,le=2))->JSONResponse:
    out=await _gather_health(deep=deep); return JSONResponse(out, status_code=200 if out.get("ok") else 503)

@app.get("/health/html")
async def health_html(deep:int=Query(0,ge=0,le=2))->HTMLResponse:
    out=await _gather_health(deep=deep); ok=out.get("ok",False); color="#0a0" if ok else "#b00"
    def yesno(b:bool)->str: return "✔" if b else "✖"
    html=f"""<!doctype html><meta charset="utf-8"><title>{APP_NAME} – Health</title>
    <style>body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:2rem;color:#111}}
    .grid{{display:grid;grid-template-columns:repeat(3,minmax(260px,1fr));gap:1rem}}.card{{border:1px solid #e5e5e5;border-radius:12px;padding:1rem}}
    h1{{font-size:1.1rem;margin:0 0 .5rem}}.kv{{display:flex;justify-content:space-between;margin:.2rem 0}}.ok{{color:{color};font-weight:700}}.mono{{font-family:ui-monospace,Menlo,Consolas,monospace}}</style>
    <h1>{APP_NAME} – Health <span class="ok">{'OK' if ok else 'DOWN'}</span></h1>
    <div class="grid">
      <div class="card"><h1>Environment</h1><div class="kv"><span>OpenAI key</span><span>{yesno(out['env']['OPENAI_API_KEY'])}</span></div>
      <div class="kv"><span>Tavily key</span><span>{yesno(out['env']['TAVILY_API_KEY'])}</span></div>
      <div class="kv"><span>Perplexity key</span><span>{yesno(out['env']['PERPLEXITY_API_KEY'])}</span></div>
      <div class="kv"><span>PDF service URL</span><span>{yesno(out['env']['PDF_SERVICE_URL'])}</span></div></div>
      <div class="card"><h1>PDF Service</h1><div class="kv"><span>reachable</span><span>{yesno(out['pdf'].get('reachable',False))}</span></div>
      <div class="kv"><span>detail</span><span class="mono">{out['pdf'].get('detail','')}</span></div></div>
      <div class="card"><h1>Data</h1><div class="kv"><span>Tools</span><span>{out['data'].get('tools',{}).get('count',0)}</span></div>
      <div class="kv"><span>Funding</span><span>{out['data'].get('funding',{}).get('count',0)}</span></div></div>
    </div>"""
    return HTMLResponse(html)

@app.get("/metrics")
def metrics():
    if not PROM: return PlainTextResponse("# metrics disabled\n", media_type="text/plain")
    return PlainTextResponse(generate_latest(REG), media_type=CONTENT_TYPE_LATEST)

# ------------------------------ Auth & helpers --------------------------------
class LoginReq(BaseModel): email: str
def _issue_token(email:str)->str: return jwt.encode({"sub":email,"iat":int(time.time()),"exp":int(time.time()+14*24*3600)}, JWT_SECRET, algorithm="HS256")
async def current_user(req:Request)->Dict[str,Any]:
    auth=req.headers.get("authorization") or ""; parts=auth.split()
    if len(parts)==2 and parts[0].lower()=="bearer":
        try: payload=jwt.decode(parts[1], JWT_SECRET, algorithms=["HS256"]); return {"sub":payload.get("sub"),"email":payload.get("sub")}
        except JWTError: pass
    return {"sub":"anon","email":""}

@app.post("/api/login")
def api_login(req:LoginReq)->Dict[str,Any]:
    email=_sanitize_email(req.email); if not email: raise HTTPException(status_code=400, detail="email required")
    return {"token":_issue_token(email), "email":email}

# ------------------------------ PDF Render ------------------------------------
async def _render_pdf_bytes(html:str, filename:str)->Optional[bytes]:
    if not (PDF_SERVICE_URL and html): return None
    start=time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=PDF_TIMEOUT) as cli:
            payload={"html":html,"fileName":filename,"stripScripts":PDF_STRIP_SCRIPTS,"maxBytes":PDF_MAX_BYTES}
            try:
                r=await cli.post(f"{PDF_SERVICE_URL}/render-pdf", json=payload)
                if r.status_code==200 and "application/pdf" in (r.headers.get("content-type") or "").lower(): return r.content
            except Exception: pass
            r=await cli.post(f"{PDF_SERVICE_URL}/generate-pdf", json={**payload,"return_pdf_bytes":True})
            ct=(r.headers.get("content-type") or "").lower()
            if r.status_code==200 and "application/pdf" in ct: return r.content
            if r.status_code==200 and "application/json" in ct:
                try: return base64.b64decode((r.json().get("pdf_base64") or "") )
                except Exception: return None
    finally:
        if PROM: RENDER_LAT.observe(time.perf_counter()-start)
    return None

# ------------------------------- Kern-Endpoint --------------------------------
@app.post("/briefing_async")
async def briefing_async(body:Dict[str,Any], request:Request, tasks:BackgroundTasks, user=Depends(current_user)):
    lang=_lang_from_body(body); recipient=_recipient_from(body, fallback=ADMIN_EMAIL)
    if not recipient: raise HTTPException(status_code=400, detail="recipient could not be resolved")

    name=_display_name_from(body); subject=_build_subject(MAIL_SUBJECT_PREFIX, lang, name)
    filename_pdf=_safe_pdf_filename(name, lang)

    nonce=str(body.get("nonce") or request.headers.get("x-request-id") or request.headers.get("x-idempotency-key") or "")
    idem_key=_sha256(json.dumps({"body":body,"user":recipient,"lang":lang,"nonce":nonce}, sort_keys=True, ensure_ascii=False))
    if _idem_seen(idem_key): return JSONResponse({"status":"duplicate","job_id":uuid.uuid4().hex})

    try:
        from gpt_analyze import analyze_briefing, produce_admin_attachments  # type: ignore
    except Exception as exc:
        log.error("gpt_analyze import failed: %s", exc); raise HTTPException(status_code=500, detail="analysis module not available")

    # form fusion
    form=dict(body.get("answers") or {}); [form.setdefault(k,v) for k,v in body.items()]

    try:
        html=analyze_briefing(form, lang=lang)
        if not html or "<html" not in html.lower(): raise RuntimeError("empty html")
    except Exception as exc:
        log.error("analyze_briefing failed: %s", exc); raise HTTPException(status_code=500, detail="rendering failed")

    pdf=None
    try: pdf=await _render_pdf_bytes(html, filename_pdf)
    except Exception as exc: log.warning("PDF render failed: %s", exc)

    # Mail an User
    user_result={"ok":False,"status":0,"detail":"skipped"}
    if SEND_TO_USER:
        try:
            msg=EmailMessage()
            msg["Subject"]=subject; msg["From"]=formataddr((SMTP_FROM_NAME, SMTP_FROM)); msg["To"]=recipient
            msg.set_content("This is an HTML email. Please enable HTML view.")
            msg.add_alternative("<p>Ihr KI‑Status‑Report liegt im Anhang (PDF &amp; HTML).</p>" if lang=="de" else "<p>Your AI status report is attached (PDF &amp; HTML).</p>", subtype="html")
            msg.add_attachment(html.encode("utf-8"), maintype="text", subtype="html", filename="report.html")
            if pdf: msg.add_attachment(pdf, maintype="application", subtype="pdf", filename="report.pdf")
            _smtp_send(msg); user_result={"ok":True,"status":200,"detail":"SMTP"}
        except Exception as exc: log.error("[mail] user SMTP failed: %s", exc)

    # Mail an Admin
    admin_result={"ok":False,"status":0,"detail":"skipped"}
    if ADMIN_NOTIFY and ADMIN_EMAIL:
        try:
            admin_json={}
            try:
                tri=produce_admin_attachments(form)  # -> dict[str,str]
                admin_json={n: c.encode("utf-8") for n,c in tri.items()}
            except Exception: pass
            msg=EmailMessage()
            msg["Subject"]=subject + (" (Admin‑Kopie)" if lang=="de" else " (Admin copy)")
            msg["From"]=formataddr((SMTP_FROM_NAME, SMTP_FROM)); msg["To"]=ADMIN_EMAIL
            msg.set_content("This is an HTML email. Please enable HTML view.")
            msg.add_alternative("<p>Neuer Report erstellt. Anhänge: PDF, HTML sowie JSON‑Diagnosen.</p>" if lang=="de" else "<p>New report created. Attachments: PDF, HTML and JSON diagnostics.</p>", subtype="html")
            msg.add_attachment(html.encode("utf-8"), maintype="text", subtype="html", filename="report.html")
            if pdf: msg.add_attachment(pdf, maintype="application", subtype="pdf", filename="report.pdf")
            for n,d in (admin_json or {}).items(): msg.add_attachment(d, maintype="application", subtype="json", filename=n)
            _smtp_send(msg); admin_result={"ok":True,"status":200,"detail":"SMTP"}
        except Exception as exc: log.error("[mail] admin SMTP failed: %s", exc)

    return JSONResponse({"status":"ok","job_id":uuid.uuid4().hex,"user_mail":user_result,"admin_mail":admin_result})

@app.get("/")
def root()->HTMLResponse: return HTMLResponse(f"<!doctype html><meta charset='utf-8'><h1>{APP_NAME}</h1><p>OK – {_now_str()}</p>")
