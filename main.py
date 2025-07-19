import os
import json
import psycopg2
import psycopg2.extras
from fastapi import FastAPI, Request, HTTPException, Header, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from pdf_export import export_pdf
from dotenv import load_dotenv
import datetime
import csv
import io
import jwt

# --- Load environment ---
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY", "my-secret")

# --- App & CORS Setup ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://make.ki-sicherheit.jetzt", "http://localhost:8888"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DB & Auth Helpers ---
def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

def verify_token(auth_header: str):
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload

def verify_admin(auth_header: str):
    payload = verify_token(auth_header)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return payload.get("email")

# --- LOGIN ---
class LoginData:
    email: str
    password: str

@app.post("/api/login")
async def login(data: dict):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE email = %s", (data["email"],))
            user = cur.fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="Unbekannter Benutzer")
    if user["password_hash"] != data["password"]:
        raise HTTPException(status_code=401, detail="Falsches Passwort")
    token = jwt.encode(
        {"email": user["email"], "role": user["role"], "exp": datetime.datetime.utcnow() + datetime.timedelta(days=2)},
        SECRET_KEY,
        algorithm="HS256"
    )
    return {"token": token}

# --- KI-BRIEFING (PDF-GENERIERUNG) ---
@app.post("/api/briefing")
async def create_briefing(request: Request, authorization: str = Header(None)):
    data = await request.json()
    # Token-Check (email auslesen)
    if authorization and authorization.startswith("Bearer "):
        payload = jwt.decode(authorization.split()[1], SECRET_KEY, algorithms=["HS256"])
        email = payload.get("email")
    else:
        email = data.get("email", "fallback")
    result = full_report(data)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO usage_logs (email, pdf_type, created_at) VALUES (%s, %s, NOW())", (email, "briefing"))
        conn.commit()
    pdf_filename = export_pdf(result)
    # -> Sofort-Download: Datei direkt als Response
    file_path = os.path.join(os.path.dirname(__file__), "downloads", pdf_filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="PDF nicht gefunden")
    return FileResponse(file_path, media_type="application/pdf", filename=pdf_filename)

# --- FEEDBACK ---
@app.post("/api/feedback")
async def submit_feedback(request: Request):
    data = await request.json()
    email = data.get("tipp_email") or data.get("email", "unbekannt")
    feedback_json = json.dumps(data, ensure_ascii=False)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO feedback_logs (email, feedback_data, created_at) VALUES (%s, %s, NOW())", (email, feedback_json))
        conn.commit()
    return {"status": "success", "message": "Feedback gespeichert"}

# --- PDF-DOWNLOAD ALT (NUR FALLBACK, nicht mehr empfohlen) ---
@app.get("/api/pdf-download")
async def get_pdf_download(file: str, authorization: str = Header(None)):
    # Für Legacy-Frontend, ersetzt durch Sofort-Download in /api/briefing!
    payload = verify_token(authorization)
    file_path = os.path.join(os.path.dirname(__file__), "downloads", file)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="PDF nicht gefunden")
    return FileResponse(file_path, media_type="application/pdf", filename=file)

# --- ADMIN CSV: NUTZUNG ---
@app.get("/api/export-usage")
def export_usage_logs(start: str = None, end: str = None, authorization: str = Header(None)):
    verify_admin(authorization)
    query = """
        SELECT id, email, pdf_type, created_at
        FROM usage_logs
        WHERE (%s IS NULL OR created_at >= %s)
          AND (%s IS NULL OR created_at <= %s)
        ORDER BY created_at DESC
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (start, start, end, end))
            rows = cur.fetchall()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["id", "email", "pdf_type", "created_at"])
    writer.writeheader()
    writer.writerows(rows)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=usage_logs.csv"})

# --- ADMIN CSV: FEEDBACK ---
@app.get("/api/export-feedback")
def export_feedback_logs(authorization: str = Header(None)):
    verify_admin(authorization)
    query = "SELECT * FROM feedback_logs ORDER BY created_at DESC"
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
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
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchall()

# --- STATUS ---
@app.get("/api/status")
def get_status():
    return {"status": "ok", "message": "KI-Backend läuft 🟢"}

# --- ROOT ---
@app.get("/")
def root():
    return {"message": "Willkommen im KI-Backend"}
