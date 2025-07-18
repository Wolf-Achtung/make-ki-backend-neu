# --- imports + Setup ---
import os
from fastapi import FastAPI, Request, HTTPException, Header, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from dotenv import load_dotenv
from gpt_analyze import analyze_full_report
from pdf_export import export_pdf
from pydantic import BaseModel  # ✅ NEU
import psycopg2
import psycopg2.extras
import jwt
import datetime
import io
import csv

# --- Load Environment ---
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("JWT_SECRET", "notsosecret")

# --- App & CORS Setup ---
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

ALLOWED_ORIGINS = [
    "https://make.ki-sicherheit.jetzt",
    "http://localhost",
    "http://127.0.0.1"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://make.ki-sicherheit.jetzt", "http://localhost:8888"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# --- DB & Auth Helpers ---
def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

def verify_admin(auth_header: str):
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        if payload.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin role required")
        return payload.get("email")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# --- LOGIN ---

class LoginData(BaseModel):
    email: str
    password: str

@app.post("/api/login")
def login(data: LoginData):
    print(f"🔐 Login-Versuch von: {data.email}")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE email = %s", (data.email,))
            user = cur.fetchone()
            if not user:
                raise HTTPException(status_code=401, detail="Unbekannter Benutzer")
            payload = {
                "email": user["email"],
                "role": user["role"],
                "exp": datetime.datetime.utcnow() + datetime.timedelta(days=2)
            }
            token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
            return {"token": token}

# --- ANALYSE + PDF ---
@app.post("/api/analyze")
async def analyze(request: Request):
    data = await request.json()
    print(f"📊 Starte Analyse für: {data.get('email')}")
    result = analyze_full_report(data)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO usage_logs (email, pdf_type, created_at) VALUES (%s, %s, NOW())",
                (data.get("email"), "full")
            )
            conn.commit()
    return result
# --- PDF-GENERIERUNG ---
@app.post("/api/pdf")
async def generate_pdf(request: Request):
    data = await request.json()
    print(f"🖨️ PDF-Erzeugung für: {data.get('email')}")
    pdf_url = export_pdf(data)
    return {"pdf_url": pdf_url}

# --- GESCHÜTZTER PDF-DOWNLOAD ---
@app.get("/api/pdf-download")
async def download_pdf(file: str, authorization: str = Header(None)):
    print(f"⬇️ Download-Anfrage für: {file}")
    verify_admin(authorization)
    file_path = f"./pdf_exports/{file}"
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Datei nicht gefunden")
    return FileResponse(file_path, media_type="application/pdf", filename=file)

# --- BRIEFING KOMBI: Analyse + PDF ---
@app.post("/api/briefing")
async def create_briefing(request: Request, authorization: str = Header(None)):
    data = await request.json()
    # E-Mail sicher aus JWT extrahieren
    email = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            email = payload.get("email")
        except Exception as e:
            print("JWT decode error:", e)
    if not email:
        email = data.get("email")  # Fallback, falls irgendwas schief läuft

    print(f"🧠 Briefing-Daten empfangen von {email}")
    result = analyze_full_report(data)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO usage_logs (email, pdf_type, created_at) VALUES (%s, %s, NOW())",
                (email, "briefing")
            )
            conn.commit()

    pdf_filename = export_pdf(result)
    return {"pdf_url": f"/api/pdf-download?file={pdf_filename}"}


# --- FEEDBACK ---
@app.post("/api/feedback")
async def submit_feedback(request: Request):
    data = await request.json()
    email = data.get("email", "unbekannt")
    print(f"💬 Feedback erhalten von: {email}")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO feedback_logs (email, feedback_data, created_at) VALUES (%s, %s, NOW())",
                (email, str(data))
            )
            conn.commit()
    return {"status": "success", "message": "Feedback gespeichert"}

# --- ADMIN CSV: NUTZUNG ---
@app.get("/api/export-logs")
def export_logs(start: str = None, end: str = None, authorization: str = Header(None)):
    email = verify_admin(authorization)
    print(f"📥 Admin {email} exportiert Logs")
    query = """
        SELECT * FROM usage_logs
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
    for row in rows:
        writer.writerow(row)
    return StreamingResponse(iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=usage_logs.csv"})
# --- ADMIN CSV: FEEDBACK ---
@app.get("/api/export-feedback")
def export_feedback(authorization: str = Header(None)):
    email = verify_admin(authorization)
    print(f"📥 Admin {email} exportiert Feedback-Logs")
    query = "SELECT * FROM feedback_logs ORDER BY created_at DESC"
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["id", "email", "feedback_data", "created_at"])
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return StreamingResponse(iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=feedback_logs.csv"})

# --- ADMIN JSON: FEEDBACK EINSEHEN ---
@app.get("/api/feedback-logs")
def get_feedback_logs(authorization: str = Header(None)):
    email = verify_admin(authorization)
    print(f"📥 Admin {email} ruft /api/feedback-logs ab")
    query = "SELECT email, feedback_data, created_at FROM feedback_logs ORDER BY created_at DESC"
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchall()

# --- LEBENSZEICHEN FÜR TESTZWECKE ---
@app.get("/api/status")
def get_status():
    return {"status": "ok", "message": "KI-Backend läuft 🎯"}

# --- ROOT-CHECK ---
@app.get("/")
def root():
    return {"message": "Willkommen im KI-Backend"}
