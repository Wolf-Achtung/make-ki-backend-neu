"""
FastAPI-Backend für KI-Readiness-Report (korrigiert)
- Sprachumschaltung (DE/EN) für Templates
- Base64-Assets (Logos) ins Template injiziert (renderer-sicher)
- Asynchroner Report-Job mit Gating (Förderprogramme nur bei Interesse)
- ROBUSTER Versand an PDF-Service mit Logging + Status im Job
- Optionaler /pdf_test Smoke-Test (nur Admin)
"""

import os
import json
import uuid
import base64
import logging
from datetime import datetime, timedelta
from pathlib import Path
from mimetypes import guess_type

import bcrypt
import jwt
import markdown
import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jinja2 import Template

# ---- GPT-Analyse-Funktionen ----
from gpt_analyze import (
    generate_full_report,
    gpt_generate_section,
    summarize_intro,
    generate_glossary,
    calc_score_percent,
    fix_encoding,
    generate_preface,
    checklist_markdown_to_html,
)

# ---------- Setup ----------
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY", "my-secret")
PDF_SERVICE_URL = (os.getenv("PDF_SERVICE_URL") or "").rstrip("/")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://make.ki-sicherheit.jetzt",
        "http://localhost",
        "http://127.0.0.1",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- DB & Auth ----------
def get_db():
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    except Exception as e:
        logger.error(f"[DB] Verbindung fehlgeschlagen: {e}")
        raise HTTPException(status_code=500, detail="DB-Verbindung fehlgeschlagen.")

def verify_token(auth_header: str):
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth_header.split(" ")[1]
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

def verify_admin(auth_header: str):
    payload = verify_token(auth_header)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return payload.get("email")

# ---------- Template-Assets ----------
TPL_DIR = Path("templates")

def as_data_uri(name: str) -> str:
    try:
        p = TPL_DIR / name
        mime = guess_type(p.name)[0] or "application/octet-stream"
        return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode("ascii")
    except Exception:
        return ""

# ---------- PDF-Service Versand ----------
def send_html_to_pdf_service(html: str, email: str) -> tuple[bool, str]:
    """
    1) POST als text/html (raw)
    2) Fallback: POST als JSON {"html": "...", "to": "..."}
    Loggt Statuscodes/Fehler – damit sind Probleme in Railway sofort sichtbar.
    """
    if not PDF_SERVICE_URL:
        logger.warning("[PDF] PDF_SERVICE_URL ist nicht gesetzt – Versand übersprungen.")
        return False, "PDF_SERVICE_URL missing"

    endpoint = f"{PDF_SERVICE_URL}/generate-pdf"
    size = len(html.encode("utf-8"))
    try:
        logger.info(f"[PDF] POST {endpoint} len={size}B user={email or '-'} (text/html)")
        r = requests.post(
            endpoint,
            data=html.encode("utf-8"),
            headers={"Content-Type": "text/html; charset=utf-8", "X-User-Email": email or ""},
            timeout=(10, 120),
        )
        if 200 <= r.status_code < 300:
            logger.info(f"[PDF] OK {r.status_code} (text/html)")
            return True, f"{r.status_code} html"
        logger.warning(f"[PDF] Non-2xx {r.status_code} (text/html) → JSON-Fallback")
        r2 = requests.post(
            endpoint,
            json={"html": html, "to": email},
            timeout=(10, 120),
        )
        if 200 <= r2.status_code < 300:
            logger.info(f"[PDF] OK {r2.status_code} (json)")
            return True, f"{r2.status_code} json"
        logger.error(f"[PDF] Fehlgeschlagen: {r2.status_code} body={r2.text[:300]}")
        return False, f"{r.status_code}/{r2.status_code}"
    except Exception as e:
        logger.exception(f"[PDF] Exception beim Versand: {e}")
        return False, str(e)

# ---------- API ----------
@app.post("/api/login")
async def login(data: dict):
    try:
        with get_db() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE email = %s", (data["email"],))
            user = cur.fetchone()
    except Exception as e:
        logger.error(f"[LOGIN] {e}")
        raise HTTPException(status_code=500, detail="DB-Fehler beim Login")
    if not user or not bcrypt.checkpw(data["password"].encode(), user["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = jwt.encode(
        {"email": user["email"], "role": user["role"], "exp": datetime.utcnow() + timedelta(days=2)},
        SECRET_KEY,
        algorithm="HS256",
    )
    return {"token": token}

@app.post("/briefing")
async def create_briefing(request: Request, authorization: str = Header(None)):
    payload = verify_token(authorization)
    email = payload.get("email")
    data = await request.json()
    lang = data.get("lang") or data.get("language") or "de"

    # Vollbericht erzeugen
    result = generate_full_report(data, lang=lang)
    result["email"] = email

    # Template-Felder
    template_fields = {
        "executive_summary": result.get("executive_summary", ""),
        "summary_klein": result.get("summary_klein", ""),
        "summary_kmu": result.get("summary_kmu", ""),
        "summary_solo": result.get("summary_solo", ""),
        "gesamtstrategie": result.get("gesamtstrategie", ""),
        "roadmap": result.get("roadmap", ""),
        "innovation": result.get("innovation", ""),
        "praxisbeispiele": result.get("praxisbeispiele", ""),
        "compliance": result.get("compliance", ""),
        "datenschutz": result.get("datenschutz", ""),
        "foerderprogramme": result.get("foerderprogramme", ""),
        "foerdermittel": result.get("foerdermittel", ""),
        "tools": result.get("tools", ""),
        "moonshot_vision": result.get("moonshot_vision", ""),
        "eu_ai_act": result.get("eu_ai_act", ""),
        "score_percent": result.get("score_percent", ""),
        "checklisten": result.get("checklisten", ""),
        "glossar": result.get("glossar", ""),
        "glossary": result.get("glossary", ""),
        "websearch_links_foerder": result.get("websearch_links_foerder", ""),
    }

    # Preface
    try:
        template_fields["preface"] = generate_preface(lang, result.get("score_percent"))
    except Exception:
        template_fields["preface"] = ""

    # Kurzfazit wählen
    summary_map = {"klein": "summary_klein", "kmu": "summary_kmu", "solo": "summary_solo"}
    ug = data.get("unternehmensgroesse", "kmu")
    template_fields["kurzfazit"] = result.get(summary_map.get(ug, "summary_kmu"), "")

    # Markdown → HTML
    for key in [
        "executive_summary", "summary_klein", "summary_kmu", "summary_solo",
        "gesamtstrategie", "roadmap", "innovation", "praxisbeispiele", "compliance",
        "datenschutz", "foerderprogramme", "foerdermittel", "tools",
        "moonshot_vision", "eu_ai_act", "kurzfazit", "glossar", "glossary"
    ]:
        if template_fields.get(key):
            template_fields[key] = markdown.markdown(template_fields[key])

    # Kontext + Logos
    template_fields.update({
        "lang": lang,
        "unternehmensgroesse": data.get("unternehmensgroesse"),
        "interesse_foerderung": data.get("interesse_foerderung"),
        "hauptleistung": data.get("hauptleistung"),
        "KI_READY_BASE64": as_data_uri("ki-ready-2025.webp"),
        "KI_SICHERHEIT_BASE64": as_data_uri("ki-sicherheit-logo.png"),
        "DSGVO_BASE64": as_data_uri("dsgvo.svg"),
        "EU_AI_BASE64": as_data_uri("eu-ai.svg"),
        "BASE_URL": os.getenv("TEMPLATE_ASSET_BASE_URL", ""),
    })

    # Template wählen + rendern
    tpl_name = "pdf_template_en.html" if str(lang).lower().startswith("en") else "pdf_template.html"
    with open(f"templates/{tpl_name}", encoding="utf-8") as f:
        template = Template(f.read())
    html_content = template.render(**template_fields)

    # Logging (Usage)
    try:
        with get_db() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO usage_logs (email, pdf_type, created_at) VALUES (%s, %s, NOW())",
                (email, "briefing"),
            )
            conn.commit()
    except Exception:
        pass

    # Optional: sofort PDF senden, wenn explizit angefordert
    pdf_sent = False
    pdf_status = ""
    if str(data.get("send_pdf", "")).lower() in {"1", "true", "yes"}:
        pdf_sent, pdf_status = send_html_to_pdf_service(html_content, email)

    return JSONResponse(content={
        "html": html_content,
        "pdf_sent": pdf_sent,
        "pdf_status": pdf_status,
    })
# ---------------- Asynchroner Job ----------------

tasks: dict[str, dict] = {}

async def _generate_briefing_job(job_id: str, data: dict, email: str, lang: str):
    try:
        data["score_percent"] = calc_score_percent(data)
        branche = (data.get("branche") or "default").lower()
        wants_funding = str(data.get("interesse_foerderung", "")).lower() in {"ja", "unklar"}
        chapters = ["executive_summary", "tools"] + (["foerderprogramme"] if wants_funding else []) + ["roadmap", "compliance", "praxisbeispiel"]

        total_steps = len(chapters) + 1  # +1 Glossar
        tasks[job_id]["total"] = total_steps
        tasks[job_id]["progress"] = 0

        report, segments = {}, []

        for chapter in chapters:
            try:
                raw = gpt_generate_section(data, branche, chapter, lang=lang)
                section = fix_encoding(raw)
                intro = summarize_intro(section, lang=lang)
                report[chapter] = (f"<p>{intro}</p>\n\n{section}") if intro else section
                segments.append(section)
            except Exception as e:
                report[chapter] = f"[Fehler in Kapitel {chapter}: {e}]"
            tasks[job_id]["progress"] += 1

        # Glossar
        try:
            full_text = "\n\n".join(segments)
            gloss = generate_glossary(full_text, lang=lang)
        except Exception as e:
            gloss = f"[Glossar konnte nicht erstellt werden: {e}]"
        if str(lang).lower().startswith("de"):
            report["glossar"] = gloss
        else:
            report["glossary"] = gloss
        tasks[job_id]["progress"] += 1

        # Kurzfazit aus Gesamttext
        try:
            summary_text = summarize_intro("\n\n".join(segments), lang=lang)
        except Exception:
            summary_text = ""
        report["summary_klein"] = summary_text
        report["summary_kmu"] = summary_text
        report["summary_solo"] = summary_text
        report["score_percent"] = data.get("score_percent", "")

        # Checkliste (HTML)
        try:
            if os.path.exists("data/check_ki_readiness.md"):
                with open("data/check_ki_readiness.md", encoding="utf-8") as f:
                    report["checklisten"] = checklist_markdown_to_html(f.read())
            else:
                report["checklisten"] = ""
        except Exception:
            report["checklisten"] = ""

        # Mindestfelder
        for k in ["gesamtstrategie", "innovation", "praxisbeispiele", "datenschutz", "foerdermittel", "moonshot_vision", "eu_ai_act"]:
            report.setdefault(k, "")

        # Template-Felder bauen
        tf = {
            "executive_summary": report.get("executive_summary", ""),
            "summary_klein": report.get("summary_klein", ""),
            "summary_kmu": report.get("summary_kmu", ""),
            "summary_solo": report.get("summary_solo", ""),
            "gesamtstrategie": report.get("gesamtstrategie", ""),
            "roadmap": report.get("roadmap", ""),
            "innovation": report.get("innovation", ""),
            "praxisbeispiele": report.get("praxisbeispiel", report.get("praxisbeispiele", "")),
            "compliance": report.get("compliance", ""),
            "datenschutz": report.get("datenschutz", ""),
            "foerderprogramme": report.get("foerderprogramme", ""),
            "foerdermittel": report.get("foerdermittel", ""),
            "tools": report.get("tools", ""),
            "moonshot_vision": report.get("moonshot_vision", ""),
            "eu_ai_act": report.get("eu_ai_act", ""),
            "score_percent": report.get("score_percent", ""),
            "checklisten": report.get("checklisten", ""),
            "glossar": report.get("glossar", ""),
            "glossary": report.get("glossary", ""),
            "websearch_links_foerder": report.get("websearch_links_foerder", ""),
        }

        try:
            tf["preface"] = generate_preface(lang, report.get("score_percent"))
        except Exception:
            tf["preface"] = ""

        summary_map = {"klein": "summary_klein", "kmu": "summary_kmu", "solo": "summary_solo"}
        ug = data.get("unternehmensgroesse", "kmu")
        tf["kurzfazit"] = report.get(summary_map.get(ug, "summary_kmu"), "")

        # Markdown → HTML
        for key in [
            "executive_summary","summary_klein","summary_kmu","summary_solo",
            "gesamtstrategie","roadmap","innovation","praxisbeispiele","compliance",
            "datenschutz","foerderprogramme","foerdermittel","tools",
            "moonshot_vision","eu_ai_act","kurzfazit","glossar","glossary"
        ]:
            if tf.get(key):
                tf[key] = markdown.markdown(tf[key])

        # Kontext + Logos
        tf.update({
            "lang": lang,
            "unternehmensgroesse": data.get("unternehmensgroesse"),
            "interesse_foerderung": data.get("interesse_foerderung"),
            "hauptleistung": data.get("hauptleistung"),
            "KI_READY_BASE64": as_data_uri("ki-ready-2025.webp"),
            "KI_SICHERHEIT_BASE64": as_data_uri("ki-sicherheit-logo.png"),
            "DSGVO_BASE64": as_data_uri("dsgvo.svg"),
            "EU_AI_BASE64": as_data_uri("eu-ai.svg"),
            "BASE_URL": os.getenv("TEMPLATE_ASSET_BASE_URL", ""),
        })

        # Rendern
        tpl_name = "pdf_template_en.html" if str(lang).lower().startswith("en") else "pdf_template.html"
        with open(f"templates/{tpl_name}", encoding="utf-8") as f:
            template = Template(f.read())
        html_content = template.render(**tf)

        # Usage-Log
        try:
            with get_db() as conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO usage_logs (email, pdf_type, created_at) VALUES (%s, %s, NOW())",
                    (email, "briefing_async"),
                )
                conn.commit()
        except Exception:
            pass

        # --- PDF-Service aufrufen (mit Logging) ---
        ok, pdf_msg = send_html_to_pdf_service(html_content, email)

        tasks[job_id] = {
            "status": "completed",
            "html": html_content,
            "email": email,
            "progress": tasks[job_id].get("progress", total_steps),
            "total": total_steps,
            "pdf_sent": ok,
            "pdf_status": pdf_msg,
        }

    except Exception as e:
        tasks[job_id] = {
            "status": "failed",
            "error": str(e),
            "email": email,
            "progress": tasks[job_id].get("progress", 0),
            "total": tasks[job_id].get("total", 0),
        }

@app.post("/briefing_async")
async def create_briefing_async(request: Request, background_tasks: BackgroundTasks, authorization: str = Header(None)):
    payload = verify_token(authorization)
    email = payload.get("email")
    data = await request.json()
    lang = data.get("lang") or data.get("language") or "de"
    job_id = str(uuid.uuid4())

    tasks[job_id] = {"status": "pending", "email": email, "progress": 0, "total": 0}
    background_tasks.add_task(_generate_briefing_job, job_id, data, email, lang)
    return {"job_id": job_id}

@app.get("/briefing_status/{job_id}")
async def briefing_status(job_id: str, authorization: str = Header(None)):
    payload = verify_token(authorization)
    email = payload.get("email")
    job = tasks.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job nicht gefunden")
    if job.get("email") != email:
        raise HTTPException(status_code=403, detail="Zugriff verweigert")
    return {
        "status": job.get("status"),
        "html": job.get("html"),
        "error": job.get("error"),
        "progress": job.get("progress", 0),
        "total": job.get("total", 0),
        "pdf_sent": job.get("pdf_sent"),
        "pdf_status": job.get("pdf_status"),
    }

# -------- Feedback ----------
@app.post("/feedback")
async def feedback(request: Request, authorization: str = Header(None)):
    payload = verify_token(authorization)
    email = payload.get("email")
    data = await request.json()

    fields = [
        "kommentar","nuetzlich","hilfe","verstaendlich_analyse","verstaendlich_empfehlung",
        "vertrauen","serio","textstellen","dauer","unsicher","features",
        "freitext","tipp_name","tipp_firma","tipp_email"
    ]
    values = [data.get(k, "") for k in fields]

    try:
        with get_db() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO feedback (
                    email, kommentar, nuetzlich, hilfe,
                    verstaendlich_analyse, verstaendlich_empfehlung,
                    vertrauen, serio, textstellen, dauer, unsicher, features,
                    freitext, tipp_name, tipp_firma, tipp_email, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """,
                (email, *values),
            )
            conn.commit()
        return {"detail": "Feedback gespeichert"}
    except Exception as e:
        logger.error(f"[FEEDBACK] {e}")
        raise HTTPException(status_code=500, detail="Fehler beim Speichern")

# -------- Admin-Schnelltest (ohne Frontend) ----------
@app.post("/pdf_test")
async def pdf_test(authorization: str = Header(None)):
    admin_email = verify_admin(authorization)
    html = "<html><body><h1>PDF Test</h1><p>Hallo Wolf 👋</p></body></html>"
    ok, msg = send_html_to_pdf_service(html, admin_email)
    return {"sent": ok, "status": msg}
