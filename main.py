"""
Erweiterte Version von main.py für den KI-Readiness-Report.

Diese Variante ergänzt den bestehenden FastAPI-Service um asynchrone
Briefing-Endpunkte. Über `/briefing` kann weiterhin synchron ein Report
erstellt werden. Der Endpoint `/briefing_async` startet die
Generierung im Hintergrund und liefert sofort eine Job-ID zurück;
`/briefing_status/{job_id}` liefert den Fortschritt und das Ergebnis.

Die Logik für JWT-Authentifizierung, DB-Zugriff und Feedback bleibt
unverändert. Neue Felder wie `score_percent` und `checklisten` werden
ebenfalls im Report berücksichtigt.
"""

import os
import json
import psycopg2
import psycopg2.extras
from fastapi import FastAPI, Request, HTTPException, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from jinja2 import Template
import requests
from datetime import datetime, timedelta
import markdown
import jwt
import bcrypt
import uuid

# --- NEU: Helfer für Template-Assets & Typen ---
import base64
from mimetypes import guess_type
from pathlib import Path

from gpt_analyze import (
    generate_full_report,  # Vollständige Report-Generierung (synchron)
    gpt_generate_section,
    summarize_intro,
    generate_glossary,
    calc_score_percent,
    fix_encoding,
    generate_preface,
)

# --- ENV-VARIABLEN LADEN ---
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY", "my-secret")

# --- FASTAPI & CORS ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://make.ki-sicherheit.jetzt",
        "http://localhost",
        "http://127.0.0.1"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DB HELPER ---
def get_db():
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    except Exception as e:
        print(f"[DB][ERROR] Verbindung fehlgeschlagen: {e}")
        raise HTTPException(status_code=500, detail="Verbindung zur Datenbank fehlgeschlagen.")

# --- JWT AUTH ---
def verify_token(auth_header: str):
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except Exception as e:
        print(f"[JWT][ERROR] {e}")
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload

def verify_admin(auth_header: str):
    payload = verify_token(auth_header)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return payload.get("email")

# --- TEMPLATE-ASSET-Helfer (Base64 für Logos/Icons) ---
TPL_DIR = Path("templates")

def as_data_uri(name: str) -> str:
    """
    Liest eine Datei aus templates/ ein und liefert einen data: URI (Base64).
    Fällt auf "" zurück, falls die Datei fehlt.
    """
    try:
        p = TPL_DIR / name
        mime = guess_type(p.name)[0] or "application/octet-stream"
        return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode("ascii")
    except Exception:
        return ""

# --- LOGIN ---
@app.post("/api/login")
async def login(data: dict):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM users WHERE email = %s", (data["email"],))
                user = cur.fetchone()
    except Exception as e:
        print(f"[LOGIN][ERROR] {e}")
        raise HTTPException(status_code=500, detail="DB-Fehler beim Login")
    if not user:
        raise HTTPException(status_code=401, detail="Unbekannter Benutzer")
    if not bcrypt.checkpw(data["password"].encode(), user["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Falsches Passwort")
    token = jwt.encode(
        {"email": user["email"], "role": user["role"], "exp": datetime.utcnow() + timedelta(days=2)},
        SECRET_KEY,
        algorithm="HS256"
    )
    return {"token": token}

# --- BRIEFING (synchron) ---
@app.post("/briefing")
async def create_briefing(request: Request, authorization: str = Header(None)):
    payload = verify_token(authorization)
    email = payload.get("email")
    try:
        data = await request.json()

        # Sprache bestimmen; "lang" oder "language" werden unterstützt
        lang = data.get("lang") or data.get("language") or "de"
        print(f"🧠 Briefing-Daten empfangen von {email} (Sprache: {lang})")

        # Vollständigen Report synchron generieren
        result = generate_full_report(data, lang=lang)
        result["email"] = email

        # Felder für das Template vorbereiten
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
            # NEU: Live-Websuche-Links (HTML) – nicht noch mal durch Markdown jagen
            "websearch_links_foerder": result.get("websearch_links_foerder", ""),
        }

        # Preface voranstellen: Statische Einleitung basierend auf Sprache und Score
        try:
            score_val = result.get("score_percent")
            template_fields["preface"] = generate_preface(lang, score_val)
        except Exception:
            template_fields["preface"] = ""

        # Kurzfazit je nach Unternehmensgröße auswählen (Fallback auf KMU)
        summary_map = {"klein": "summary_klein", "kmu": "summary_kmu", "solo": "summary_solo"}
        unternehmensgroesse = data.get("unternehmensgroesse", "kmu")
        selected_key = summary_map.get(unternehmensgroesse, "summary_kmu")
        template_fields["kurzfazit"] = result.get(selected_key, "")

        # Markdown → HTML für die relevanten Textfelder
        markdown_fields = [
            "executive_summary", "summary_klein", "summary_kmu", "summary_solo",
            "gesamtstrategie", "roadmap", "innovation", "praxisbeispiele", "compliance",
            "datenschutz", "foerderprogramme", "foerdermittel", "tools",
            "moonshot_vision", "eu_ai_act", "kurzfazit", "glossar", "glossary"
        ]
        for key in markdown_fields:
            if template_fields.get(key):
                template_fields[key] = markdown.markdown(template_fields[key])

        # --- NEU: Kontextfelder, die das Template für Gating/Infoboxen nutzt ---
        template_fields.update({
            "lang": lang,
            "unternehmensgroesse": data.get("unternehmensgroesse"),
            "interesse_foerderung": data.get("interesse_foerderung"),
            "hauptleistung": data.get("hauptleistung"),
            # Logos/Icons als Base64 (funktioniert unabhängig vom PDF-Renderer)
            "KI_READY_BASE64": as_data_uri("ki-ready-2025.webp"),
            "KI_SICHERHEIT_BASE64": as_data_uri("ki-sicherheit-logo.png"),
            "DSGVO_BASE64": as_data_uri("dsgvo.svg"),
            "EU_AI_BASE64": as_data_uri("eu-ai.svg"),
            # Optional: Pfadbasis, falls du relative Pfade statt Base64 bevorzugst
            "BASE_URL": os.getenv("TEMPLATE_ASSET_BASE_URL", ""),
        })

        # Richtige Template-Datei je nach Sprache
        tpl_name = "pdf_template_en.html" if str(lang).lower().startswith("en") else "pdf_template.html"
        with open(f"templates/{tpl_name}", encoding="utf-8") as f:
            template = Template(f.read())
        html_content = template.render(**template_fields)

        # Usage-Log schreiben
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO usage_logs (email, pdf_type, created_at) VALUES (%s, %s, NOW())",
                    (email, "briefing")
                )
                conn.commit()

        return JSONResponse(content={"html": html_content})

    except Exception as e:
        print("❌ Fehler bei /briefing:", e)
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail="Interner Fehler")

# ---------------------------------------------------------------------------
# Asynchrone Briefing-Generierung
#
# /briefing_async startet einen Job im Hintergrund und gibt sofort eine Job-ID
# zurück. /briefing_status/{job_id} liefert den Status und ggf. das
# generierte HTML. Die Aufgaben werden in einem einfachen Dictionary
# verwaltet. Für einen produktiven Einsatz sollte eine persistente Queue
# verwendet werden.

tasks: dict[str, dict] = {}

async def _generate_briefing_job(job_id: str, data: dict, email: str, lang: str):
    """
    Hintergrundjob zur Erstellung des KI-Readiness-Reports mit Fortschrittsanzeige.

    Kapitel werden nacheinander generiert, der Fortschritt wird nach
    jedem Kapitel aktualisiert. Am Ende wird ein Glossar erstellt.
    """
    try:
        # Score vorab berechnen
        data["score_percent"] = calc_score_percent(data)
        # Branche (fallback "default")
        branche = data.get("branche", "default").lower()

        # --- NEU: Foerder-Gating je nach Interesse ---
        wants_funding = str(data.get("interesse_foerderung", "")).lower() in {"ja", "unklar"}
        chapters = ["executive_summary", "tools"] + (["foerderprogramme"] if wants_funding else []) + ["roadmap", "compliance", "praxisbeispiel"]

        total_steps = len(chapters) + 1  # +1 für Glossar
        tasks[job_id]["total"] = total_steps
        tasks[job_id]["progress"] = 0

        report: dict[str, str] = {}
        full_text_segments: list[str] = []

        for chapter in chapters:
            try:
                section_raw = gpt_generate_section(data, branche, chapter, lang=lang)
                section = fix_encoding(section_raw)
                intro = summarize_intro(section, lang=lang)
                section_with_intro = (f"<p>{intro}</p>\n\n{section}") if intro else section
                report[chapter] = section_with_intro
                full_text_segments.append(section)
            except Exception as e:
                report[chapter] = f"[Fehler in Kapitel {chapter}: {e}]"
            tasks[job_id]["progress"] += 1

        # Glossar generieren
        try:
            full_report_text = "\n\n".join(full_text_segments)
            glossary_text = generate_glossary(full_report_text, lang=lang)
        except Exception as e:
            glossary_text = f"[Glossar konnte nicht erstellt werden: {e}]"
        if str(lang).lower().startswith("de"):
            report["glossar"] = glossary_text
        else:
            report["glossary"] = glossary_text
        tasks[job_id]["progress"] += 1

        # Kurzfazit aus dem Gesamttext
        try:
            summary_text = summarize_intro("\n\n".join(full_text_segments), lang=lang)
        except Exception:
            summary_text = ""
        report["summary_klein"] = summary_text
        report["summary_kmu"] = summary_text
        report["summary_solo"] = summary_text

        # Score übernehmen
        report["score_percent"] = data.get("score_percent", "")

        # Checklisten (HTML) laden, falls vorhanden
        try:
            from gpt_analyze import checklist_markdown_to_html
            if os.path.exists("data/check_ki_readiness.md"):
                with open("data/check_ki_readiness.md", encoding="utf-8") as f:
                    report["checklisten"] = checklist_markdown_to_html(f.read())
            else:
                report["checklisten"] = ""
        except Exception:
            report["checklisten"] = ""

        # Felder initialisieren, die das Template erwartet
        default_keys = [
            "gesamtstrategie", "innovation", "praxisbeispiele", "datenschutz",
            "foerdermittel", "moonshot_vision", "eu_ai_act"
        ]
        for k in default_keys:
            report.setdefault(k, "")

        # Template-Felder zusammenstellen
        template_fields = {
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
            # NEU:
            "websearch_links_foerder": report.get("websearch_links_foerder", ""),
        }

        # Preface
        try:
            score_val = report.get("score_percent")
            template_fields["preface"] = generate_preface(lang, score_val)
        except Exception:
            template_fields["preface"] = ""

        # Kurzfazit je nach Unternehmensgröße
        summary_map = {"klein": "summary_klein", "kmu": "summary_kmu", "solo": "summary_solo"}
        unternehmensgroesse = data.get("unternehmensgroesse", "kmu")
        selected_key = summary_map.get(unternehmensgroesse, "summary_kmu")
        template_fields["kurzfazit"] = report.get(selected_key, "")

        # Markdown → HTML
        markdown_fields = [
            "executive_summary", "summary_klein", "summary_kmu", "summary_solo",
            "gesamtstrategie", "roadmap", "innovation", "praxisbeispiele", "compliance",
            "datenschutz", "foerderprogramme", "foerdermittel", "tools",
            "moonshot_vision", "eu_ai_act", "kurzfazit", "glossar", "glossary"
        ]
        for key in markdown_fields:
            if template_fields.get(key):
                template_fields[key] = markdown.markdown(template_fields[key])

        # --- NEU: Kontextfelder, die das Template für Gating/Infoboxen nutzt ---
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

        # HTML rendern – passendes Template je nach Sprache
        tpl_name = "pdf_template_en.html" if str(lang).lower().startswith("en") else "pdf_template.html"
        with open(f"templates/{tpl_name}", encoding="utf-8") as f:
            template = Template(f.read())
        html_content = template.render(**template_fields)

        # Usage-Log speichern (best effort)
        try:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO usage_logs (email, pdf_type, created_at) VALUES (%s, %s, NOW())",
                        (email, "briefing_async")
                    )
                    conn.commit()
        except Exception:
            pass

        tasks[job_id] = {
            "status": "completed",
            "html": html_content,
            "email": email,
            "progress": tasks[job_id].get("progress", total_steps),
            "total": total_steps,
        }

        # Optional: Direkt an PDF-Service senden
        try:
            pdf_service_url = os.getenv("PDF_SERVICE_URL")
            if pdf_service_url:
                headers = {"Content-Type": "text/html", "X-User-Email": email}
                requests.post(
                    pdf_service_url.rstrip("/") + "/generate-pdf",
                    data=html_content,
                    headers=headers,
                    timeout=60,
                )
        except Exception as e:
            print(f"[PDF-Service][WARN] Fehler beim Versand an PDF-Service: {e}")

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

    tasks[job_id] = {
        "status": "pending",
        "email": email,
        "progress": 0,
        "total": 0,  # wird im Hintergrundtask gesetzt
    }
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
    if job.get("status") == "completed":
        return {
            "status": "completed",
            "html": job.get("html"),
            "progress": job.get("progress", 0),
            "total": job.get("total", 0),
        }
    elif job.get("status") == "failed":
        return {
            "status": "failed",
            "error": job.get("error"),
            "progress": job.get("progress", 0),
            "total": job.get("total", 0),
        }
    else:
        return {
            "status": "pending",
            "progress": job.get("progress", 0),
            "total": job.get("total", 0),
        }

# --- FEEDBACK SPEICHERN ---
@app.post("/feedback")
async def feedback(request: Request, authorization: str = Header(None)):
    payload = verify_token(authorization)
    email = payload.get("email")
    try:
        data = await request.json()
        kommentar = data.get("kommentar", "")
        nuetzlich = data.get("nuetzlich", "")
        hilfe = data.get("hilfe", "")
        verstaendlich_analyse = data.get("verstaendlich_analyse", "")
        verstaendlich_empfehlung = data.get("verstaendlich_empfehlung", "")
        vertrauen = data.get("vertrauen", "")
        serio = data.get("serio", "")
        textstellen = data.get("textstellen", "")
        dauer = data.get("dauer", "")
        unsicher = data.get("unsicher", "")
        features = data.get("features", "")
        freitext = data.get("freitext", "")
        tipp_name = data.get("tipp_name", "")
        tipp_firma = data.get("tipp_firma", "")
        tipp_email = data.get("tipp_email", "")
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO feedback (
                        email, kommentar, nuetzlich, hilfe,
                        verstaendlich_analyse, verstaendlich_empfehlung,
                        vertrauen, serio, textstellen, dauer, unsicher, features,
                        freitext, tipp_name, tipp_firma, tipp_email, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    """,
                    (
                        email, kommentar, nuetzlich, hilfe,
                        verstaendlich_analyse, verstaendlich_empfehlung,
                        vertrauen, serio, textstellen, dauer, unsicher, features,
                        freitext, tipp_name, tipp_firma, tipp_email
                    )
                )
                conn.commit()
        return {"detail": "Feedback gespeichert"}
    except Exception as e:
        print("❌ Fehler beim Speichern des Feedbacks:", e)
        raise HTTPException(status_code=500, detail="Interner Fehler beim Speichern des Feedbacks")
