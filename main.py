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
    if not bcrypt.checkpw(data["password"].encode(), user["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Falsches Passwort")
    token = jwt.encode(
        {"email": user["email"], "role": user["role"], "exp": datetime.datetime.utcnow() + datetime.timedelta(days=2)},
        SECRET_KEY,
        algorithm="HS256"
    )
    return {"token": token}
# --- BRIEFING ---
@app.post("/briefing")
async def create_briefing(request: Request, authorization: str = Header(None)):
    payload = verify_token(authorization)
    email = payload.get("email")
    try:
        data = await request.json()
        print(f"🧠 Briefing-Daten empfangen von {email}")
        print("### DEBUG: calc_score_percent(data) wird ausgeführt ###")
        result = analyze_full_report(data)
        print(f"### DEBUG: score_percent berechnet: {result.get('score_percent')}")
        result["email"] = email
        pdf_file = export_pdf(result)
        print(f"📄 PDF-Datei erstellt: {pdf_file}")
        # Protokollierung in der Datenbank
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO usage_logs (email, pdf_type, created_at) VALUES (%s, %s, NOW())",
                    (email, "briefing")
                )
                conn.commit()
        return {"pdf_file": pdf_file}
    except Exception as e:
        print("❌ Fehler bei /briefing:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Interner Fehler")

# --- FEEDBACK SPEICHERN ---
@app.post("/feedback")
async def feedback(data: dict, authorization: str = Header(None)):
    payload = verify_token(authorization)
    email = payload.get("email")
    try:
        kommentar = data.get("kommentar", "")   # <--- Robust gegen fehlendes Feld!
        nuetzlich = data.get("nützlich", "")    # Falls "nützlich" fehlt, auch leer.
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO feedback (email, kommentar, nützlich, created_at) VALUES (%s, %s, %s, NOW())",
                    (email, kommentar, nuetzlich)
                )
            conn.commit()
        return {"message": "Feedback gespeichert"}
    except Exception as e:
        print("❌ Fehler bei /feedback:", e)
        raise HTTPException(status_code=500, detail="Feedback-Fehler")


# --- ADMIN: LISTE ALLE PDFs ---
@app.get("/admin/list")
def list_all(authorization: str = Header(None)):
    verify_admin(authorization)
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM usage_logs ORDER BY created_at DESC")
                return cur.fetchall()
    except Exception as e:
        print(f"[Admin][list] Fehler: {e}")
        raise HTTPException(status_code=500, detail="Datenbankfehler")

# --- ADMIN: ALLE ENTRIES ALS CSV ---
@app.get("/admin/export")
def export_csv(authorization: str = Header(None)):
    verify_admin(authorization)
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM usage_logs ORDER BY created_at DESC")
                rows = cur.fetchall()
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=usage_logs.csv"}
        )
    except Exception as e:
        print(f"[Admin][export] Fehler: {e}")
        raise HTTPException(status_code=500, detail="Export-Fehler")

# --- RAILWAY-KOMPATIBLER DOWNLOAD ---
@app.get("/download/{pdf_file}")
def download_pdf(pdf_file: str, authorization: str = Header(None)):
    verify_token(authorization)  # Kein Admin nötig, nur gültiger Login
    base_path = os.path.dirname(__file__)
    path = os.path.join(base_path, "downloads", pdf_file)
    print(f"⬇️ PDF-Download angefragt: {pdf_file}")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="PDF nicht gefunden")
    return FileResponse(path, media_type="application/pdf", filename=pdf_file)
