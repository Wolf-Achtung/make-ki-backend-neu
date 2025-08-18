
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

from fastapi import FastAPI, Request, HTTPException, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone

import jwt

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
if ALLOWED_ORIGINS == "*":
    allow_origins = ["*"]
else:
    allow_origins = [o.strip() for o in ALLOWED_ORIGINS.split(",") if o.strip()]

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
    """Accept Bearer JWT (admin) or Basic admin:password"""
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
    for key in ("email", "kontakt_email", "contact_email", "user_email"):
        v = (data.get(key) or "").strip()
        if v and "@" in v:
            return v
    return default_email

def send_html_to_pdf_service(html: str, user_email: str, request_id: Optional[str]=None) -> (bool, str):
    """
    Sendet HTML an PDF-Service. Versucht zuerst Content-Type text/html,
    fällt bei Non-200 auf JSON zurück. Gibt (ok, status_string) zurück.
    """
    if not PDF_SERVICE_URL:
        return False, "PDF_SERVICE_URL missing"
    url = f"{PDF_SERVICE_URL}/generate-pdf"
    headers = {"X-User-Email": user_email or ""}
    if request_id:
        headers["X-Request-ID"] = request_id
    timeout = httpx.Timeout(120.0, connect=20.0)

    try:
        # 1) text/html
        r = httpx.post(url, content=html.encode("utf-8"),
                       headers={**headers, "Content-Type": "text/html; charset=utf-8"},
                       timeout=timeout)
        if r.status_code == 200:
            ct = r.headers.get("content-type", "")
            typ = "pdf" if "pdf" in ct else "html"
            return True, f"{r.status_code} {typ}"
        # 2) JSON fallback
        r2 = httpx.post(url, json={"html": html, "to": user_email}, headers=headers, timeout=timeout)
        ct = r2.headers.get("content-type", "")
        typ = "pdf" if "pdf" in ct else "json"
        return (r2.status_code == 200), f"{r2.status_code} {typ}"
    except Exception as e:
        logger.error(f"[PDF] error sending to service: {e}")
        return False, f"error: {e}"

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
    # Auth guard
    authorized = False
    actor = None
    try:
        actor = verify_admin(authorization)
        authorized = True
    except Exception:
        authorized = False
        actor = None
    if not authorized:
        setup_env = ADMIN_SETUP_TOKEN or ""
        if setup_env and x_setup_token and compare_digest(setup_env, x_setup_token):
            authorized = True
            actor = "setup-token"
        else:
            raise HTTPException(status_code=403, detail="Not authorized")

    data = await request.json()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = (data.get("role") or "admin").strip().lower()
    issue_token = bool(data.get("issue_token", True))

    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email required")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password too short (min 8)")
    if role not in {"admin", "user", "viewer"}:
        raise HTTPException(status_code=400, detail="Invalid role")

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
    if issue_token:
        try:
            token = create_token(email, role)
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
    if order not in {"created_at", "email", "role"}:
        order = "created_at"
    direction = "DESC" if str(direction).lower() == "desc" else "ASC"
    limit = max(1, min(int(limit or 50), 200))
    offset = max(0, int(offset or 0))

    where = ""
    params = []
    if q:
        where = "WHERE email ILIKE %s OR role ILIKE %s"
        params = [f"%{q}%", f"%{q}%"]

    try:
        with get_db() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM users {where}", params)
            total = int(cur.fetchone()["count"])
            # try with created_at
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
    html = "<html><body><h1>PDF Test</h1><p>Hallo Wolf 👋</p></body></html>"
    ok, msg = send_html_to_pdf_service(html, admin_email, request_id=str(uuid.uuid4()))
    return {"sent": ok, "status": msg}

# ----------------------
# Briefing / Report generation
# ----------------------
TASKS: Dict[str, Dict[str, Any]] = {}

def _generate_html_report(data: Dict[str, Any], lang: str) -> str:
    """
    Wrapper um gpt_analyze: baut Kontext, lässt Kapitel generieren und rendert Template.
    """
    try:
        import gpt_analyze as ga  # uses OpenAI etc.
    except Exception as e:
        logger.error(f"import gpt_analyze failed: {e}")
        raise

    branche = (data.get("branche") or "default").lower()
    # Build context from YAML + incoming data
    context = {}
    try:
        if hasattr(ga, "build_context"):
            context = ga.build_context(data, branche, lang=lang) or {}
        else:
            context = {**data}
    except Exception as e:
        logger.warning(f"build_context failed: {e}")
        context = {**data}

    # Generate full report (dict of sections)
    sections = {}
    try:
        if hasattr(ga, "generate_full_report"):
            sections = ga.generate_full_report({**data, "branche": branche}, lang=lang) or {}
        else:
            sections = {}
    except Exception as e:
        logger.error(f"generate_full_report failed: {e}")
        raise

    # Merge into template context
    ctx = {**context, **sections}
    # Score percent if available
    try:
        if hasattr(ga, "calc_score_percent"):
            ctx["score_percent"] = ga.calc_score_percent(data)
    except Exception:
        pass
    # Preface if available
    try:
        if "preface" not in ctx and hasattr(ga, "generate_preface"):
            ctx["preface"] = ga.generate_preface(sections, lang)
    except Exception:
        pass

    # Load template
    tpl_name = "pdf_template_en.html" if lang.startswith("en") else "pdf_template.html"
    tpl_path = os.path.join("templates", tpl_name)
    if not os.path.exists(tpl_path):
        raise RuntimeError(f"Template not found: {tpl_path}")
    template_text = open(tpl_path, "r", encoding="utf-8").read()

    # Render using ga.render_template if present, else simple replace
    try:
        if hasattr(ga, "render_template"):
            html = ga.render_template(template_text, ctx)
        else:
            html = template_text
            for k, v in ctx.items():
                html = html.replace("{{ "+k+" }}", str(v))
    except Exception as e:
        logger.error(f"render_template failed: {e}")
        raise
    return html

@app.post("/briefing")
async def briefing(request: Request, authorization: str = Header(None)):
    payload = verify_token(authorization)
    email = payload.get("email")
    data = await request.json()
    lang = (data.get("lang") or data.get("language") or "de").lower()
    html = _generate_html_report(data, lang)
    # Optional immediate send if requested
    if data.get("send_pdf_now"):
        rid = str(uuid.uuid4())
        recipient = resolve_recipient(data, email)
        ok, msg = send_html_to_pdf_service(html, recipient, request_id=rid)
        return {"html": True, "pdf_sent": ok, "pdf_status": msg, "request_id": rid}
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
            TASKS[job_id]["status"] = "generating"
            TASKS[job_id]["progress"] = 10
            html = _generate_html_report(data, lang)
            TASKS[job_id]["progress"] = 70
            rid = str(uuid.uuid4())
            recipient = resolve_recipient(data, email)
            ok, msg = send_html_to_pdf_service(html, recipient, request_id=rid)
            TASKS[job_id]["progress"] = 100
            TASKS[job_id]["status"] = "completed" if ok else "failed"
            TASKS[job_id]["pdf_sent"] = bool(ok)
            TASKS[job_id]["pdf_status"] = msg
            TASKS[job_id]["request_id"] = rid
        except Exception as e:
            TASKS[job_id]["status"] = "failed"
            TASKS[job_id]["error"] = str(e)

    background.add_task(run_job)
    return {"job_id": job_id}

@app.get("/briefing_status/{job_id}")
async def briefing_status(job_id: str, authorization: str = Header(None)):
    verify_token(authorization)  # any user
    t = TASKS.get(job_id)
    if not t:
        raise HTTPException(status_code=404, detail="job not found")
    return t
