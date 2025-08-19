import os
import json
import base64
import logging
import bcrypt
import httpx
import uuid
from hmac import compare_digest
from contextlib import contextmanager
from typing import Dict, Any, Optional

import psycopg2
import psycopg2.extras

from fastapi import FastAPI, Request, HTTPException, Header, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone

import jwt

# NEU: Jinja für echtes Template-Rendering
from jinja2 import Environment, FileSystemLoader, select_autoescape, TemplateNotFound

# ----------------------
# Config & Logging
# ----------------------
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("backend")

SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
DATABASE_URL = os.getenv("DATABASE_URL", "")
PDF_SERVICE_URL = os.getenv("PDF_SERVICE_URL", "").rstrip("/")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ADMIN_SETUP_TOKEN = os.getenv("ADMIN_SETUP_TOKEN", "")

ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "*")
allow_origins = ["*"] if ALLOWED_ORIGINS == "*" else [o.strip() for o in ALLOWED_ORIGINS.split(",") if o.strip()]

# Marken/Optik für Templates
PDF_BRAND_COLOR = os.getenv("PDF_BRAND_COLOR", "#0b6cff")
PDF_LOGO_LEFT_URL = os.getenv("PDF_LOGO_LEFT_URL", "")       # absolute URL (https://…), sonst leer
PDF_LOGO_RIGHT_URL = os.getenv("PDF_LOGO_RIGHT_URL", "")     # absolute URL (https://…), sonst leer
CONTACT_EMAIL_DEFAULT = os.getenv("CONTACT_EMAIL", "kontakt@ki-sicherheit.jetzt")

app = FastAPI(title="KI-Readiness Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------
# DB
# ----------------------
@contextmanager
def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not configured")
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# ----------------------
# Auth helpers
# ----------------------
class LoginBody(BaseModel):
    email: str
    password: str

def create_token(email: str, role: str) -> str:
    payload = {"email": email, "role": role, "exp": datetime.now(timezone.utc) + timedelta(days=2)}
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def _read_user(email: str) -> Optional[Dict[str, Any]]:
    with get_db() as conn, conn.cursor() as cur:
        cur.execute("SELECT email, role, password_hash FROM users WHERE email=%s", (email.lower(),))
        row = cur.fetchone()
        return row

def verify_token(authorization: str) -> Dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

def verify_admin(authorization: str) -> str:
    payload = verify_token(authorization)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return payload.get("email")

def verify_admin_any(authorization: str) -> str:
    """Akzeptiert Bearer JWT (admin) oder Basic admin:password"""
    if authorization and authorization.startswith("Basic "):
        try:
            raw = base64.b64decode(authorization.split(" ", 1)[1]).decode("utf-8")
            email, pwd = raw.split(":", 1)
            user = _read_user(email)
            if not user or not bcrypt.checkpw(pwd.encode("utf-8"), user["password_hash"].encode("utf-8")):
                raise HTTPException(status_code=401, detail="Invalid credentials")
            if user.get("role") != "admin":
                raise HTTPException(status_code=403, detail="Admin role required")
            return user["email"]
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid Basic header")
    # Fallback: Bearer JWT admin
    return verify_admin(authorization)

# ----------------------
# Utility
# ----------------------
def resolve_recipient(data: Dict[str, Any], default_email: str) -> str:
    """Bevorzugt Nutzer-Mail aus Payload; fällt auf Token-Mail zurück."""
    for key in ("email", "kontakt_email", "contact_email", "user_email"):
        v = (data.get(key) or "").strip()
        if v and "@" in v:
            return v
    return default_email

def _post_pdf(url: str, headers: dict, html: str, timeout: httpx.Timeout):
    """Versuch 1: text/html; Versuch 2: JSON-Fallback."""
    r1 = httpx.post(
        url,
        content=html.encode("utf-8"),
        headers={**headers, "Content-Type": "text/html; charset=utf-8"},
        timeout=timeout,
    )
    if r1.status_code == 200:
        return r1
    payload = {"html": html}
    if headers.get("X-User-Email"):
        payload["to"] = headers["X-User-Email"]
    r2 = httpx.post(url, json=payload, headers=headers, timeout=timeout)
    return r2

def send_html_to_pdf_service(html: str, user_email: str, request_id: Optional[str]=None) -> Dict[str, Any]:
    if not PDF_SERVICE_URL:
        return {"ok": False, "status": 0, "type": "unknown", "admin": "n/a", "user": "n/a", "error": "PDF_SERVICE_URL missing"}

    url = f"{PDF_SERVICE_URL}/generate-pdf"
    headers = {}
    if user_email:
        headers["X-User-Email"] = user_email
    if request_id:
        headers["X-Request-ID"] = request_id

    timeout = httpx.Timeout(120.0, connect=20.0)

    try:
        resp = _post_pdf(url, headers, html, timeout)
        ctype = resp.headers.get("content-type", "")
        kind = "pdf" if "pdf" in ctype else ("html" if "text/html" in ctype else ("json" if "json" in ctype else "unknown"))
        admin_hdr = resp.headers.get("x-email-admin", "n/a")
        user_hdr  = resp.headers.get("x-email-user",  "n/a")
        ok = (resp.status_code == 200 and ("pdf" in ctype or "application/pdf" in ctype))
        if not ok and resp.text:
            logger.error("PDF-SERVICE FAIL %s | %s", resp.status_code, resp.text[:400])
        return {
            "ok": ok,
            "status": resp.status_code,
            "type": kind,
            "admin": admin_hdr,
            "user": user_hdr,
            "error": None if ok else (resp.text[:400] if resp.text else None),
        }
    except Exception as e:
        logger.exception("[PDF] error sending to service: %s", e)
        return {"ok": False, "status": 0, "type": "unknown", "admin": "n/a", "user": "n/a", "error": str(e)}

# ----------------------
# Jinja Rendering (NEU)
# ----------------------
def _format_date(lang: str) -> str:
    now = datetime.now()
    return now.strftime("%d.%m.%Y") if str(lang).lower().startswith("de") else now.strftime("%Y-%m-%d")

def render_report_with_jinja(ctx: dict, lang: str) -> str:
    env = Environment(
        loader=FileSystemLoader("templates"),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True, lstrip_blocks=True,
    )
    tpl_name = "pdf_template_en.html" if str(lang).lower().startswith("en") else "pdf_template.html"
    try:
        template = env.get_template(tpl_name)
    except TemplateNotFound:
        raise RuntimeError(f"Template not found: templates/{tpl_name}")
    return template.render(**ctx)

# ----------------------
# Routes
# ----------------------
@app.get("/health")
async def health():
    return {"ok": True, "time_utc": datetime.now(timezone.utc).isoformat()}

@app.post("/api/login")
async def api_login(body: LoginBody):
    email = body.email.strip().lower()
    pwd = body.password
    user = _read_user(email)
    if not user or not bcrypt.checkpw(pwd.encode("utf-8"), user["password_hash"].encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(email, user["role"])
    return {"token": token, "role": user["role"]}

# ---- Admin helper: create_or_reset ----
@app.post("/admin/create_or_reset")
async def admin_create_or_reset(
    request: Request,
    authorization: str = Header(None),
    x_setup_token: str = Header(None, alias="X-Setup-Token"),
):
    authorized = False
    actor = None
    try:
        actor = verify_admin(authorization); authorized = True
    except Exception:
        authorized = False; actor = None
    if not authorized:
        setup_env = ADMIN_SETUP_TOKEN or ""
        if setup_env and x_setup_token and compare_digest(setup_env, x_setup_token):
            authorized = True; actor = "setup-token"
        else:
            raise HTTPException(status_code=403, detail="Not authorized")

    data = await request.json()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = (data.get("role") or "admin").strip().lower()
    issue_token = bool(data.get("issue_token", True))

    if not email or "@" not in email: raise HTTPException(status_code=400, detail="Valid email required")
    if len(password) < 8: raise HTTPException(status_code=400, detail="Password too short (min 8)")
    if role not in {"admin", "user", "viewer"}: raise HTTPException(status_code=400, detail="Invalid role")

    try:
        pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Hashing failed: {e}")

    try:
        with get_db() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (email, password_hash, role)
                VALUES (%s, %s, %s)
                ON CONFLICT (email) DO UPDATE SET
                    password_hash = EXCLUDED.password_hash,
                    role = EXCLUDED.role
                RETURNING email, role;
                """,
                (email, pw_hash, role),
            )
            row = cur.fetchone()
    except Exception as e:
        logger.error(f"[ADMIN:create_or_reset] DB error: {e}")
        raise HTTPException(status_code=500, detail="DB error during upsert")

    token = None
    try:
        if issue_token: token = create_token(email, role)
    except Exception:
        token = None

    out = {"ok": True, "action": "created_or_updated", "email": row["email"], "role": row["role"], "by": actor}
    if token: out["token"] = token
    return out

# ---- Admin info routes ----
@app.get("/admin/whoami")
async def admin_whoami(authorization: str = Header(None)):
    payload = verify_token(authorization)
    exp_ts = payload.get("exp")
    exp_iso = None
    remaining = None
    if exp_ts:
        dt_exp = datetime.fromtimestamp(int(exp_ts), tz=timezone.utc)
        exp_iso = dt_exp.isoformat()
        remaining = int((dt_exp - datetime.now(timezone.utc)).total_seconds())
    return {
        "email": payload.get("email"),
        "role": payload.get("role"),
        "exp": exp_ts,
        "exp_iso": exp_iso,
        "remaining_seconds": max(0, remaining or 0),
        "server_utc": datetime.now(timezone.utc).isoformat(),
    }

@app.get("/admin/list_users")
async def admin_list_users(
    authorization: str = Header(None),
    q: str = "",
    limit: int = 50,
    offset: int = 0,
    order: str = "created_at",
    direction: str = "desc",
):
    verify_admin(authorization)
    order = (order or "created_at").lower()
    if order not in {"created_at", "email", "role"}: order = "created_at"
    direction = "DESC" if str(direction).lower() == "desc" else "ASC"
    limit = max(1, min(int(limit or 50), 200))
    offset = max(0, int(offset or 0))

    where = ""; params = []
    if q:
        where = "WHERE email ILIKE %s OR role ILIKE %s"
        params = [f"%{q}%", f"%{q}%"]

    try:
        with get_db() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM users {where}", params)
            total = int(cur.fetchone()["count"])
            try:
                cur.execute(
                    f"""
                    SELECT email, role, created_at
                    FROM users
                    {where}
                    ORDER BY {order} {direction}
                    LIMIT %s OFFSET %s
                    """,
                    params + [limit, offset],
                )
                rows = cur.fetchall()
            except Exception:
                ob = "email" if order == "created_at" else order
                cur.execute(
                    f"""
                    SELECT email, role
                    FROM users
                    {where}
                    ORDER BY {ob} {direction}
                    LIMIT %s OFFSET %s
                    """,
                    params + [limit, offset],
                )
                rows = cur.fetchall()
                for r in rows:
                    r["created_at"] = None
        return {"total": total, "limit": limit, "offset": offset, "order": order, "direction": direction.lower(), "items": rows}
    except Exception as e:
        logger.error(f"[ADMIN:list_users] {e}")
        raise HTTPException(status_code=500, detail="DB error while listing users")

# ----------------------
# PDF test
# ----------------------
@app.post("/pdf_test")
async def pdf_test(authorization: str = Header(None)):
    admin_email = verify_admin_any(authorization)
    html = "<!doctype html><h1>PDF Test</h1><p>Hallo Wolf 👋</p>"
    rid = str(uuid.uuid4())
    res = send_html_to_pdf_service(html, admin_email, request_id=rid)
    return {
        "ok": res["ok"], "status": res["status"], "type": res["type"],
        "admin": res["admin"], "user": res["user"], "error": res["error"], "request_id": rid
    }

# ----------------------
# Briefing / Report generation
# ----------------------
TASKS: Dict[str, Dict[str, Any]] = {}

def _generate_html_report(data: Dict[str, Any], lang: str) -> str:
    """
    Ruft gpt_analyze auf (Kontext + Kapitel) und rendert das Jinja-Template endgültig.
    """
    try:
        import gpt_analyze as ga
    except Exception as e:
        logger.error(f"import gpt_analyze failed: {e}")
        raise

    branche = (data.get("branche") or "default").lower()

    # 1) Kontext & Kapitel generieren
    try:
        context = ga.build_context(data, branche, lang=lang) or {}
    except Exception as e:
        logger.warning(f"build_context failed: {e}")
        context = {**data}

    try:
        sections = ga.generate_full_report({**data, "branche": branche}, lang=lang) or {}
    except Exception as e:
        logger.error(f"generate_full_report failed: {e}")
        raise

    # 2) Template-Kontext zusammenführen
    ctx = {**context, **sections}

    # 3) Defaults für Template
    ctx.setdefault("lang", lang)
    ctx.setdefault("assessment_date", _format_date(lang))
    ctx.setdefault("generated_on", ctx["assessment_date"])
    ctx.setdefault("brand_color", PDF_BRAND_COLOR)
    ctx.setdefault("logo_left_url", PDF_LOGO_LEFT_URL)
    ctx.setdefault("logo_right_url", PDF_LOGO_RIGHT_URL)
    ctx.setdefault("contact_email", ctx.get("contact_email") or CONTACT_EMAIL_DEFAULT)
    ctx.setdefault("copyright_year", datetime.now().year)
    ctx.setdefault("copyright_owner", ctx.get("copyright_owner") or "Wolf Hohl")
    # Robustheit: Kernelemente nie None
    for k in ("preface","exec_summary_html","quick_wins_html","risks_html","recommendations_html","roadmap_html","sections_html"):
        ctx.setdefault(k, "")

    # 4) Jinja-Rendering (erzwingen)
    html = render_report_with_jinja(ctx, lang)
    return html

@app.post("/briefing")
async def briefing(request: Request, authorization: str = Header(None), debug_html: int = Query(0)):
    payload = verify_token(authorization)
    email = payload.get("email")
    data = await request.json()
    lang = (data.get("lang") or data.get("language") or "de").lower()

    html = _generate_html_report(data, lang)

    if debug_html:
        # Direkte Vorschau (nur Debug)
        return {"html_preview": html[:5000], "length": len(html)}

    # Optional: sofort senden
    if data.get("send_pdf_now"):
        rid = str(uuid.uuid4())
        recipient = resolve_recipient(data, email)
        res = send_html_to_pdf_service(html, recipient, request_id=rid)
        return {
            "html": True, "pdf_sent": res["ok"], "pdf_status": res["status"],
            "pdf_detail": {"admin": res["admin"], "user": res["user"], "error": res["error"]},
            "request_id": rid
        }
    return {"html": True, "length": len(html)}

@app.post("/briefing_async")
async def briefing_async(request: Request, background: BackgroundTasks, authorization: str = Header(None)):
    payload = verify_token(authorization)
    email = payload.get("email")
    data = await request.json()
    lang = (data.get("lang") or data.get("language") or "de").lower()

    job_id = str(uuid.uuid4())
    TASKS[job_id] = {"status": "queued", "progress": 0, "pdf_sent": False, "pdf_status": None, "created_at": datetime.now(timezone.utc).isoformat()}

    def run_job():
        try:
            TASKS[job_id]["status"] = "generating"; TASKS[job_id]["progress"] = 10
            html = _generate_html_report(data, lang)
            TASKS[job_id]["progress"] = 70
            rid = str(uuid.uuid4())
            recipient = resolve_recipient(data, email)
            res = send_html_to_pdf_service(html, recipient, request_id=rid)
            TASKS[job_id]["progress"] = 100
            TASKS[job_id]["status"] = "completed" if res["ok"] else "failed"
            TASKS[job_id]["pdf_sent"] = bool(res["ok"])
            TASKS[job_id]["pdf_status"] = res["status"]
            TASKS[job_id]["request_id"] = rid
            TASKS[job_id]["mail_admin"] = res["admin"]
            TASKS[job_id]["mail_user"] = res["user"]
            if res["error"]:
                TASKS[job_id]["pdf_error"] = res["error"]
        except Exception as e:
            TASKS[job_id]["status"] = "failed"; TASKS[job_id]["error"] = str(e)

    background.add_task(run_job)
    return {"job_id": job_id}

@app.get("/briefing_status/{job_id}")
async def briefing_status(job_id: str, authorization: str = Header(None)):
    verify_token(authorization)
    t = TASKS.get(job_id)
    if not t:
        raise HTTPException(status_code=404, detail="job not found")
    return t
