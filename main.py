# --- IMPORTS & SETUP ---
import os
import json
import psycopg2
import psycopg2.extras
from fastapi import FastAPI, Request, HTTPException, Header, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from dotenv import load_dotenv
import datetime
import csv
import io
import jwt
import bcrypt
import traceback

from gpt_analyze import analyze_full_report   # Zentrales GPT-Modul
from pdf_export import export_pdf             # PDF-Modul im /downloads/ Ordner

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
    # Passwort-Hash-Check (bcrypt)
    if not bcrypt.checkpw(data["password"].encode(), user["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Falsches Passwort")
    token = jwt.encode(
        {"email": user["email"], "role": user["role"], "exp": datetime.datetime.utcnow() + datetime.timedelta(days=2)},
        SECRET_KEY,
        algorithm="HS256"
    )
    return {"token": token}

# --- KI-BRIEFING (Analyse + PDF, Sofort-Download, Logging inkl. E-Mail) ---
@app.post("/api/briefing")
async def create_briefing(request: Request, authorization: str = Header(None)):
    try:
        data = await request.json()
    except Exception as e:
        print(f"[BRIEFING][ERROR] Ungültiges JSON: {e}")
        raise HTTPException(status_code=400, detail="Ungültige JSON-Daten")

    # Token auslesen (E-Mail für Logging)
    email = None
    if authorization and authorization.startswith("Bearer "):
        try:
            payload = jwt.decode(authorization.split()[1], SECRET_KEY, algorithms=["HS256"])
            email = payload.get("email")
        except Exception as e:
            print(f"[JWT][WARN] {e}")
            email = data.get("email", "fallback")
    else:
        email = data.get("email", "fallback")
    print(f"🧠 Briefing-Daten empfangen von {email}")

    try:
        result = analyze_full_report(data)      # Zentrale GPT-Analyse
    except Exception as e:
        print(f"[GPT][ERROR] Analyse fehlgeschlagen: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="KI-Analyse fehlgeschlagen.")

    # Logging mit E-Mail und Rohdaten
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO usage_logs (email, pdf_type, created_at, raw_data) VALUES (%s, %s, NOW(), %s)",
                    (email, "briefing", json.dumps(data, ensure_ascii=False))
                )
                conn.commit()
    except Exception as e:
        print(f"[DB][WARN] Logging fehlgeschlagen: {e}")

    try:
        pdf_filename = export_pdf(result)       # PDF wird erzeugt und im downloads/ Ordner gespeichert
        file_path = os.path.join(os.path.dirname(__file__), "downloads", pdf_filename)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="PDF nicht gefunden")
    except Exception as e:
        print(f"[PDF][ERROR] Export oder Zugriff fehlgeschlagen: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="PDF-Export fehlgeschlagen.")
    # Direkter Download als Response
    return FileResponse(file_path, media_type="application/pdf", filename=pdf_filename)

# --- PDF-DOWNLOAD ALT (Legacy, nur für alte Frontends) ---
@app.get("/api/pdf-download")
async def get_pdf_download(file: str, authorization: str = Header(None)):
    verify_token(authorization)
    file_path = os.path.join(os.path.dirname(__file__), "downloads", file)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="PDF nicht gefunden")
    return FileResponse(file_path, media_type="application/pdf", filename=file)

# --- FEEDBACK ---
@app.post("/api/feedback")
async def submit_feedback(request: Request):
    try:
        data = await request.json()
        email = data.get("tipp_email") or data.get("email", "unbekannt")
        feedback_json = json.dumps(data, ensure_ascii=False)
    except Exception as e:
        print(f"[FEEDBACK][ERROR] {e}")
        raise HTTPException(status_code=400, detail="Ungültige Feedback-Daten")
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO feedback_logs (email, feedback_data, created_at) VALUES (%s, %s, NOW())", (email, feedback_json))
                conn.commit()
    except Exception as e:
        print(f"[DB][WARN] Feedback-Logging fehlgeschlagen: {e}")
        raise HTTPException(status_code=500, detail="Feedback konnte nicht gespeichert werden")
    return {"status": "success", "message": "Feedback gespeichert"}

# --- ADMIN CSV: NUTZUNG inkl. Rohdaten (Download aller Analysen inkl. E-Mail) ---
@app.get("/api/export-usage")
def export_usage_logs(start: str = None, end: str = None, authorization: str = Header(None)):
    verify_admin(authorization)
    query = """
        SELECT id, email, pdf_type, created_at, raw_data
        FROM usage_logs
        WHERE (%s IS NULL OR created_at >= %s)
          AND (%s IS NULL OR created_at <= %s)
        ORDER BY created_at DESC
    """
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (start, start, end, end))
                rows = cur.fetchall()
    except Exception as e:
        print(f"[ADMIN][ERROR] Export-Usage-Logs: {e}")
        raise HTTPException(status_code=500, detail="Fehler beim Export der Nutzungsdaten.")
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["id", "email", "pdf_type", "created_at", "raw_data"])
    writer.writeheader()
    writer.writerows(rows)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=usage_logs.csv"})

# --- ADMIN CSV: FEEDBACK ---
@app.get("/api/export-feedback")
def export_feedback_logs(authorization: str = Header(None)):
    verify_admin(authorization)
    query = "SELECT * FROM feedback_logs ORDER BY created_at DESC"
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                rows = cur.fetchall()
    except Exception as e:
        print(f"[ADMIN][ERROR] Export-Feedback-Logs: {e}")
        raise HTTPException(status_code=500, detail="Fehler beim Export der Feedbackdaten.")
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["id", "email", "feedback_data", "created_at"])
    writer.writeheader()
    writer.writerows(rows)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=feedback_logs.csv"})

# --- ADMIN JSON: FEEDBACK EINSEHEN ---
@app.get("/api/feedback-logs")
def get_feedback_logs(authorization: str = Header(None)):
    verify_admin(authorization)
    query = "SELECT email, feedback_data, created_at FROM feedback_logs ORDER BY created_at DESC"
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                return cur.fetchall()
    except Exception as e:
        print(f"[ADMIN][ERROR] Feedback-Logs abrufen: {e}")
        raise HTTPException(status_code=500, detail="Feedbackdaten konnten nicht abgerufen werden.")

# --- ADMIN: Einzelne Analyse/Briefing als JSON einsehen (inkl. E-Mail) ---
@app.get("/api/usage-detail")
def get_usage_detail(usage_id: int, authorization: str = Header(None)):
    verify_admin(authorization)
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM usage_logs WHERE id = %s", (usage_id,))
                entry = cur.fetchone()
    except Exception as e:
        print(f"[ADMIN][ERROR] Usage-Detail: {e}")
        raise HTTPException(status_code=500, detail="Eintrag konnte nicht geladen werden.")
    if not entry:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")
    return entry

# --- STATUS ---
@app.get("/api/status")
def get_status():
    return {"status": "ok", "message": "KI-Backend läuft 🟢"}

# --- ROOT ---
@app.get("/")
def root():
    return {"message": "Willkommen im KI-Backend"}
