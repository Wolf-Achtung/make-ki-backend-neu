# filename: main.py
# -*- coding: utf-8 -*-
"""
Production API für KI‑Status‑Report (Gold‑Standard+)

- /health: Konfiguration, Konnektivität, optionale Deep‑Probes (Tavily/Perplexity/OpenAI/PDF).
- /briefing_async: Report erzeugen, PDF via externem Service rendern, Versand per SMTP (User+Admin).
- /api/login: Minimal‑Auth (JWT).
- /ready: Lightweight Readiness‑Ping.

Best Practices:
- Striktes Logging (keine Secrets), PEP8, Idempotency‑Key auf Body+Empfänger
- PDF‑Service: bevorzugt /generate-pdf, Alt‑Route /render-pdf nur noch als Fallback-Pfad
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import logging
import os
import re
import smtplib
import time
import uuid
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from jose import jwt
from jose.exceptions import JWTError
from pydantic import BaseModel

# Feedback‑Router minimal-invasiv anhängen (falls vorhanden)
try:
    from feedback_api import attach_to as attach_feedback  # noqa: F401
except Exception:
    attach_feedback = None

# -----------------------------------------------------------------------------
# Konfiguration (ENV)
# -----------------------------------------------------------------------------

APP_NAME = os.getenv("APP_NAME", "make-ki-backend")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("backend")

JWT_SECRET = os.getenv("JWT_SECRET", os.getenv("SECRET_KEY", "dev-secret"))
JWT_ALGO = "HS256"

IDEMPOTENCY_TTL_SECONDS = int(os.getenv("IDEMPOTENCY_TTL_SECONDS", "3600"))  # 1 h
IDEMPOTENCY_DIR = os.getenv("IDEMPOTENCY_DIR", "/tmp/ki_idempotency")

BASE_DIR = os.path.abspath(os.getenv("APP_BASE", os.getcwd()))
TEMPLATE_DIR = os.getenv("TEMPLATE_DIR", os.path.join(BASE_DIR, "templates"))

# PDF‑Service
PDF_SERVICE_URL = (os.getenv("PDF_SERVICE_URL") or "").rstrip("/")
_pdf_timeout_raw = int(os.getenv("PDF_TIMEOUT", "45"))
PDF_TIMEOUT = _pdf_timeout_raw / 1000 if _pdf_timeout_raw > 1000 else _pdf_timeout_raw
PDF_MAX_BYTES = int(os.getenv("PDF_MAX_BYTES", str(10 * 1024 * 1024)))
PDF_STRIP_SCRIPTS = os.getenv("PDF_STRIP_SCRIPTS", "1").strip().lower() in {"1", "true", "yes"}
PDF_EMAIL_FALLBACK_TO_USER = os.getenv("PDF_EMAIL_FALLBACK_TO_USER", "1").strip().lower() in {"1", "true", "yes"}

# Versand / Empfänger
SEND_TO_USER = os.getenv("SEND_TO_USER", "1").strip().lower() in {"1", "true", "yes"}
ADMIN_NOTIFY = os.getenv("ADMIN_NOTIFY", "1").strip().lower() in {"1", "true", "yes"}
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", os.getenv("SMTP_FROM", ""))

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "noreply@example.com")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "KI‑Sicherheit")

MAIL_SUBJECT_PREFIX = os.getenv("MAIL_SUBJECT_PREFIX", "KI‑Ready")

# External APIs
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_APIKEY") or ""
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")
PERPLEXITY_MODEL = os.getenv("PERPLEXITY_MODEL", "sonar-small")

# CORS
CORS_ALLOW = [o.strip() for o in (os.getenv("CORS_ALLOW_ORIGINS") or "*").split(",") if o.strip()]
if not CORS_ALLOW:
    CORS_ALLOW = ["*"]

# -----------------------------------------------------------------------------
# Utils
# -----------------------------------------------------------------------------

def _now_str() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _sanitize_email(value: Optional[str]) -> str:
    _, addr = parseaddr(value or "")
    return addr or ""


def _lang_from_body(body: Dict[str, Any]) -> str:
    lang = str(body.get("lang") or body.get("language") or "de").lower()
    return "de" if lang.startswith("de") else "en"


def _new_job_id() -> str:
    return uuid.uuid4().hex


def _sha256(s: str) -> str:
    import hashlib
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _idem_seen(key: str) -> bool:
    path = os.path.join(IDEMPOTENCY_DIR, key)
    try:
        os.makedirs(IDEMPOTENCY_DIR, exist_ok=True)
    except Exception:
        pass
    if os.path.exists(path):
        try:
            age = time.time() - os.path.getmtime(path)
            if age < IDEMPOTENCY_TTL_SECONDS:
                return True
        except Exception:
            return True
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(_now_str())
    except Exception:
        return False
    return False


def _smtp_send(msg: EmailMessage) -> None:
    if not SMTP_HOST or not SMTP_FROM:
        log.info("[mail] SMTP deaktiviert oder unkonfiguriert")
        return
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
        try:
            s.starttls()
        except Exception:
            pass
        if SMTP_USER and SMTP_PASS:
            s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)


def _recipient_from(body: Dict[str, Any], fallback: str) -> str:
    answers = body.get("answers") or {}
    cand = (
        answers.get("to") or answers.get("email") or
        body.get("to") or body.get("email") or
        fallback
    )
    return _sanitize_email(cand)


def _display_name_from(body: Dict[str, Any]) -> str:
    for key in ("unternehmen", "firma", "company", "company_name", "organization"):
        val = (body.get("answers") or {}).get(key) or body.get(key)
        if val:
            return str(val)[:64]
    email = _recipient_from(body, ADMIN_EMAIL)
    return (email.split("@")[0] if email else "Customer").title()


def _build_subject(prefix: str, lang: str, display_name: str) -> str:
    core = "KI‑Status Report" if lang == "de" else "AI Status Report"
    return f"{prefix}/{display_name} – {core}"


def _safe_pdf_filename(display_name: str, lang: str) -> str:
    dn = re.sub(r"[^a-zA-Z0-9_.-]+", "_", display_name) or "user"
    return f"KI-Status-Report-{dn}-{lang}.pdf"


def _safe_html_filename(display_name: str, lang: str) -> str:
    dn = re.sub(r"[^a-zA-Z0-9_.-]+", "_", display_name) or "user"
    return f"KI-Status-Report-{dn}-{lang}.html"


# -----------------------------------------------------------------------------
# PDF-Service (Rendern – robust gegen Varianten)
# -----------------------------------------------------------------------------

async def _render_pdf_bytes(html: str, filename: str) -> Optional[bytes]:
    if not (PDF_SERVICE_URL and html):
        return None
    async with httpx.AsyncClient(timeout=PDF_TIMEOUT) as cli:
        payload = {"html": html, "fileName": filename, "stripScripts": PDF_STRIP_SCRIPTS, "maxBytes": PDF_MAX_BYTES}
        # 1) /render-pdf → application/pdf  (Alt; wird weiterhin als Fallback probiert)
        try:
            r = await cli.post(f"{PDF_SERVICE_URL}/render-pdf", json=payload)
            ct = (r.headers.get("content-type") or "").lower()
            if r.status_code == 200 and "application/pdf" in ct:
                return r.content
        except Exception:
            pass
        # 2) /generate-pdf → application/pdf ODER JSON {pdf_base64}
        try:
            r = await cli.post(f"{PDF_SERVICE_URL}/generate-pdf", json={**payload, "return_pdf_bytes": True})
            ct = (r.headers.get("content-type") or "").lower()
            if r.status_code == 200 and "application/pdf" in ct:
                return r.content
            if r.status_code == 200 and "application/json" in ct:
                data = r.json()
                b64 = data.get("pdf_base64") or data.get("pdf") or data.get("data")
                if b64:
                    try:
                        return base64.b64decode(b64)
                    except Exception:
                        pass
        except Exception:
            pass
    return None


async def _pdf_service_email(recipient: str, subject: str, html: str, lang: str, filename: str) -> Dict[str, Any]:
    if not PDF_SERVICE_URL:
        return {"ok": False, "status": 0, "detail": "PDF service not configured"}
    try:
        async with httpx.AsyncClient(timeout=PDF_TIMEOUT) as cli:
            payload = {
                "html": html,
                "lang": lang,
                "subject": subject,
                "recipient": recipient,
                "filename": filename,
                "stripScripts": PDF_STRIP_SCRIPTS,
                "maxBytes": PDF_MAX_BYTES,
                "meta": {"app": APP_NAME, "mode": "fallback-email"},
            }
            r = await cli.post(f"{PDF_SERVICE_URL}/generate-pdf", json=payload)
            return {"ok": r.status_code == 200, "status": r.status_code, "detail": r.text[:500]}
    except Exception as exc:
        return {"ok": False, "status": 0, "detail": str(exc)}


# -----------------------------------------------------------------------------
# SMTP‑Versand
# -----------------------------------------------------------------------------

def _send_combined_email(
    to_address: str,
    subject: str,
    html_body: str,
    html_attachment: bytes,
    pdf_attachment: Optional[bytes],
    admin_json: Optional[Dict[str, bytes]] = None,
) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((SMTP_FROM_NAME, SMTP_FROM))
    msg["To"] = to_address
    msg.set_content("This is an HTML email. Please enable HTML view.")
    msg.add_alternative(html_body or "<p></p>", subtype="html")
    msg.add_attachment(html_attachment, maintype="text", subtype="html", filename="report.html")
    if pdf_attachment:
        msg.add_attachment(pdf_attachment, maintype="application", subtype="pdf", filename="report.pdf")
    for name, data in (admin_json or {}).items():
        msg.add_attachment(data, maintype="application", subtype="json", filename=name)
    _smtp_send(msg)


# -----------------------------------------------------------------------------
# Auth / FastAPI
# -----------------------------------------------------------------------------

class LoginReq(BaseModel):
    email: str


def _issue_token(email: str) -> str:
    payload = {"sub": email, "iat": int(time.time()), "exp": int(time.time() + 14 * 24 * 3600)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


async def current_user(req: Request) -> Dict[str, Any]:
    auth = req.headers.get("authorization") or ""
    parts = auth.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        try:
            payload = jwt.decode(parts[1], JWT_SECRET, algorithms=[JWT_ALGO])
            return {"sub": payload.get("sub"), "email": payload.get("sub")}
        except JWTError:
            pass
    return {"sub": "anon", "email": ""}


app = FastAPI(title=APP_NAME)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW if CORS_ALLOW else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if attach_feedback:
    attach_feedback(app)

# -------------------------------- Health / Login -----------------------------

@app.get("/health")
async def health(
    deep: int = Query(0, ge=0, le=2, description="0=config only, 1=ping hosts, 2=mini test requests"),
) -> JSONResponse:
    """
    Health-Report ohne Secrets:
      - env: Keys/URLs vorhanden?
      - pdf: Service erreichbar?
      - apis: Tavily/Perplexity/OpenAI erreichbar (optional Deep‑Probe)
      - data/prompts: Loader/CSV/Dateien vorhanden?
    """
    out: Dict[str, Any] = {
        "ok": True,
        "app": APP_NAME,
        "ts": _now_str(),
        "deep": deep,
        "env": {
            "OPENAI_API_KEY": bool(OPENAI_API_KEY),
            "TAVILY_API_KEY": bool(TAVILY_API_KEY),
            "PERPLEXITY_API_KEY": bool(PERPLEXITY_API_KEY),
            "PDF_SERVICE_URL": bool(PDF_SERVICE_URL),
            "SMTP_CONFIGURED": bool(SMTP_HOST and SMTP_FROM),
        },
        "pdf": {},
        "apis": {},
        "data": {},
        "prompts": {},
        "notes": [],
    }

    # --- PDF service
    pdf_status = {"url": PDF_SERVICE_URL, "reachable": False, "detail": "not configured"}
    if PDF_SERVICE_URL:
        try:
            # leichte Prüfung
            async with httpx.AsyncClient(timeout=4.0) as cli:
                # bevorzugt /health
                try:
                    r = await cli.get(f"{PDF_SERVICE_URL}/health")
                    if r.status_code == 200:
                        pdf_status.update({"reachable": True, "detail": "/health:200"})
                except Exception:
                    pass
                # HEAD generate
                if not pdf_status["reachable"]:
                    try:
                        r = await cli.request("HEAD", f"{PDF_SERVICE_URL}/generate-pdf")
                        if 200 <= r.status_code < 500:
                            pdf_status.update({"reachable": True, "detail": f"HEAD /generate-pdf:{r.status_code}"})
                    except Exception:
                        pass
                # Deep Test (dry-run)
                if deep >= 2 and not pdf_status["reachable"]:
                    try:
                        r = await cli.post(f"{PDF_SERVICE_URL}/generate-pdf",
                                           json={"html": "<b>ping</b>", "return_pdf_bytes": False})
                        if r.status_code == 200:
                            pdf_status.update({"reachable": True, "detail": "POST /generate-pdf:200"})
                    except Exception as exc:
                        pdf_status["detail"] = f"POST /generate-pdf fail: {exc}"
        except Exception as exc:
            pdf_status["detail"] = str(exc)
    out["pdf"] = pdf_status
    out["ok"] &= pdf_status.get("reachable", False) or not PDF_SERVICE_URL

    # --- APIs: Tavily
    tav = {"key": bool(TAVILY_API_KEY), "host": "api.tavily.com", "reachable": False, "detail": "skipped"}
    if deep >= 1:
        try:
            async with httpx.AsyncClient(timeout=4.0) as cli:
                r = await cli.get("https://api.tavily.com")
                tav["reachable"] = r.status_code in (200, 404, 405)
                tav["detail"] = f"GET /: {r.status_code}"
        except Exception as exc:
            tav["detail"] = f"host ping failed: {exc}"
    if deep >= 2 and TAVILY_API_KEY:
        # Minimal korrekter Body, Query ≤ 400 Zeichen
        payload = {"query": "KI Tools DSGVO EU AI Act Deutschland 2025",
                   "max_results": 1, "time_range": "day", "include_answer": False}
        headers_variants = [
            {"Content-Type": "application/json", "x-api-key": TAVILY_API_KEY},
            {"Content-Type": "application/json", "Authorization": f"Bearer {TAVILY_API_KEY}"},
        ]
        for h in headers_variants:
            try:
                async with httpx.AsyncClient(timeout=6.0) as cli:
                    r = await cli.post("https://api.tavily.com/search", headers=h, json=payload)
                    if r.status_code == 200:
                        tav["reachable"] = True
                        tav["detail"] = "POST /search:200"
                        break
                    tav["detail"] = f"POST /search:{r.status_code}"
            except Exception as exc:
                tav["detail"] = f"POST fail: {exc}"
    out["apis"]["tavily"] = tav
    out["ok"] &= tav["key"]

    # --- APIs: Perplexity
    pplx = {"key": bool(PERPLEXITY_API_KEY), "host": "api.perplexity.ai", "reachable": False, "detail": "skipped"}
    if deep >= 1:
        try:
            async with httpx.AsyncClient(timeout=4.0) as cli:
                r = await cli.get("https://api.perplexity.ai")
                pplx["reachable"] = r.status_code in (200, 404, 405)
                pplx["detail"] = f"GET /: {r.status_code}"
        except Exception as exc:
            pplx["detail"] = f"host ping failed: {exc}"
    if deep >= 2 and PERPLEXITY_API_KEY:
        payload = {
            "model": PERPLEXITY_MODEL,
            "messages": [{"role": "user", "content": "Return JSON array: [{\"title\":\"ok\",\"url\":\"https://example.com\",\"date\":\"\"}] only."}],
            "max_tokens": 16,
            "temperature": 0.0,
        }
        headers = {"Authorization": f"Bearer {PERPLEXITY_API_KEY}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=6.0) as cli:
                r = await cli.post("https://api.perplexity.ai/chat/completions", headers=headers, json=payload)
                pplx["reachable"] = r.status_code == 200
                pplx["detail"] = f"POST /chat/completions:{r.status_code}"
        except Exception as exc:
            pplx["detail"] = f"POST fail: {exc}"
    out["apis"]["perplexity"] = pplx
    out["ok"] &= pplx["key"]

    # --- APIs: OpenAI (optional)
    oai = {"key": bool(OPENAI_API_KEY), "reachable": False, "detail": "skipped"}
    if deep >= 1 and OPENAI_API_KEY:
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
        try:
            async with httpx.AsyncClient(timeout=4.0) as cli:
                r = await cli.get("https://api.openai.com/v1/models", headers=headers)
                oai["reachable"] = r.status_code == 200
                oai["detail"] = f"GET /v1/models:{r.status_code}"
        except Exception as exc:
            oai["detail"] = f"GET fail: {exc}"
    out["apis"]["openai"] = oai

    # --- Daten/Loader
    tools_info = {"count": 0, "detail": "not loaded"}
    try:
        from tools_loader import filter_tools  # type: ignore
        items = filter_tools(industry="all", company_size="solo", limit=32)
        tools_info = {"count": len(items or []), "detail": "tools_loader"}
    except Exception:
        # Fallback: CSV grob zählen
        try:
            import csv
            p = os.path.join(BASE_DIR, "data", "tools.csv")
            with open(p, "r", encoding="utf-8") as f:
                tools_info = {"count": sum(1 for _ in csv.DictReader(f)), "detail": "tools.csv"}
        except Exception as exc:
            tools_info = {"count": 0, "detail": f"unavailable: {exc}"}
    out["data"]["tools"] = tools_info

    funding_info = {"count": 0, "detail": "not loaded"}
    try:
        from funding_loader import filter_funding  # type: ignore
        items = filter_funding(region="DE", limit=32)
        funding_info = {"count": len(items or []), "detail": "funding_loader"}
    except Exception:
        try:
            import csv
            p = os.path.join(BASE_DIR, "data", "foerderprogramme.csv")
            with open(p, "r", encoding="utf-8") as f:
                funding_info = {"count": sum(1 for _ in csv.DictReader(f)), "detail": "foerderprogramme.csv"}
        except Exception as exc:
            funding_info = {"count": 0, "detail": f"unavailable: {exc}"}
    out["data"]["funding"] = funding_info

    # --- Prompts (Kernbestand)
    def _exists(*parts: str) -> bool:
        return os.path.exists(os.path.join(BASE_DIR, "prompts", *parts))
    core_de = ["executive_summary_de.md", "quick_wins_de.md", "roadmap_de.md",
               "risks_de.md", "compliance_de.md", "business_de.md", "recommendations_de.md"]
    core_en = ["executive_summary_en.md", "quick_wins_en.md", "roadmap_en.md",
               "risks_en.md", "compliance_en.md", "business_en.md", "recommendations_en.md"]
    out["prompts"] = {
        "de": {name: _exists("de", name) or _exists(name) for name in core_de},
        "en": {name: _exists("en", name) or _exists(name) for name in core_en},
    }

    # Gesamtergebnis
    out["ok"] &= all(out["prompts"]["de"].values()) and all(out["prompts"]["en"].values())

    status = 200 if out["ok"] else 503
    return JSONResponse(out, status_code=status)


@app.get("/ready")
def ready() -> dict:
    return {"ok": True, "ts": _now_str()}


class LoginReq(BaseModel):
    email: str


@app.post("/api/login")
def api_login(req: LoginReq) -> Dict[str, Any]:
    email = _sanitize_email(req.email)
    if not email:
        raise HTTPException(status_code=400, detail="email required")
    token = _issue_token(email)
    return {"token": token, "email": email}


# ------------------------------- Kern‑Endpoint -------------------------------

@app.post("/briefing_async")
async def briefing_async(
    body: Dict[str, Any],
    request: Request,
    tasks: BackgroundTasks,
    user=Depends(current_user),
):
    """
    Erzeugt den Report und verschickt E‑Mails (User + Admin) mit PDF+HTML im Anhang.
    """
    lang = _lang_from_body(body)
    recipient_user = _recipient_from(body, fallback=ADMIN_EMAIL)
    if not recipient_user:
        raise HTTPException(status_code=400, detail="recipient could not be resolved")

    display_name = _display_name_from(body)
    subject = _build_subject(MAIL_SUBJECT_PREFIX, lang, display_name)
    filename_pdf = _safe_pdf_filename(display_name, lang)
    filename_html = _safe_html_filename(display_name, lang)

    nonce = str(
        body.get("nonce")
        or request.headers.get("x-request-id")
        or request.headers.get("x-idempotency-key")
        or ""
    )
    idem_key = _sha256(json.dumps({"body": body, "user": recipient_user, "lang": lang, "nonce": nonce},
                                  sort_keys=True, ensure_ascii=False))
    if _idem_seen(idem_key):
        log.info("[idem] duplicate (user=%s, lang=%s) – skipping", recipient_user, lang)
        return JSONResponse({"status": "duplicate", "job_id": _new_job_id()})

    # Import hier, damit der Start schnell bleibt
    try:
        from gpt_analyze import analyze_briefing, produce_admin_attachments  # type: ignore
    except Exception as exc:
        log.error("gpt_analyze import failed: %s", exc)
        raise HTTPException(status_code=500, detail="analysis module not available")

    # Formdaten zusammenführen
    form_data = dict(body.get("answers") or {})
    for k, v in body.items():
        form_data.setdefault(k, v)

    job_id = _new_job_id()

    # HTML erzeugen
    try:
        html = analyze_briefing(form_data, lang=lang)
        if not html or "<html" not in html.lower():
            raise RuntimeError("empty html")
    except Exception as exc:
        log.error("analyze_briefing failed: %s", exc)
        raise HTTPException(status_code=500, detail="rendering failed")

    # PDF rendern
    pdf_bytes = None
    try:
        pdf_bytes = await _render_pdf_bytes(html, filename_pdf)
    except Exception as exc:
        log.warning("PDF render failed: %s", exc)

    # Admin-Anhänge (JSON) bauen – best effort
    admin_json: Dict[str, bytes] = {}
    try:
        tri = produce_admin_attachments(form_data)  # -> dict[str,str]
        admin_json = {name: content.encode("utf-8") for name, content in tri.items()}
    except Exception:
        pass

    # Mail an User (oder Fallback über PDF-Service)
    user_result = {"ok": False, "status": 0, "detail": "skipped"}
    if SEND_TO_USER:
        try:
            _send_combined_email(
                to_address=recipient_user,
                subject=subject,
                html_body="<p>Ihr KI‑Status‑Report liegt im Anhang (PDF &amp; HTML).</p>" if lang == "de"
                else "<p>Your AI status report is attached (PDF &amp; HTML).</p>",
                html_attachment=html.encode("utf-8"),
                pdf_attachment=pdf_bytes,
            )
            user_result = {"ok": True, "status": 200, "detail": "SMTP"}
        except Exception as exc:
            log.error("[mail] user SMTP failed: %s", exc)
            if PDF_EMAIL_FALLBACK_TO_USER:
                fb = await _pdf_service_email(recipient_user, subject, html, lang, filename_pdf)
                user_result = fb

    # Mail an Admin
    admin_result = {"ok": False, "status": 0, "detail": "skipped"}
    if ADMIN_NOTIFY and ADMIN_EMAIL:
        try:
            _send_combined_email(
                to_address=ADMIN_EMAIL,
                subject=subject + (" (Admin‑Kopie)" if lang == "de" else " (Admin copy)"),
                html_body="<p>Neuer Report erstellt. Anhänge: PDF, HTML sowie JSON‑Diagnosen.</p>" if lang == "de"
                else "<p>New report created. Attachments: PDF, HTML and JSON diagnostics.</p>",
                html_attachment=html.encode("utf-8"),
                pdf_attachment=pdf_bytes,
                admin_json=admin_json,
            )
            admin_result = {"ok": True, "status": 200, "detail": "SMTP"}
        except Exception as exc:
            log.error("[mail] admin SMTP failed: %s", exc)

    return JSONResponse(
        {"status": "ok", "job_id": job_id, "user_mail": user_result, "admin_mail": admin_result}
    )


@app.post("/pdf_test")
async def pdf_test(body: Dict[str, Any]) -> Dict[str, Any]:
    lang = _lang_from_body(body)
    html = body.get("html") or "<!doctype html><meta charset='utf-8'><h1>Ping</h1>"
    pdf = await _render_pdf_bytes(html, _safe_pdf_filename("test", lang))
    return {"ok": bool(pdf), "bytes": len(pdf or b'0')}


@app.get("/")
def root() -> HTMLResponse:
    return HTMLResponse(f"<!doctype html><meta charset='utf-8'><h1>{APP_NAME}</h1><p>OK – {_now_str()}</p>")
