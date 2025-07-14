import os
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from dotenv import load_dotenv
from gpt_analyze import analyze_full_report
from pdf_export import export_pdf
import psycopg2
import psycopg2.extras
import jwt
import datetime
import io
import csv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY", "notsosecret")

app = FastAPI()

ALLOWED_ORIGINS = [
    "https://make.ki-sicherheit.jetzt",
    "http://localhost",
    "http://127.0.0.1"
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

def verify_token(auth_header):
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload["sub"], payload.get("role", "user")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def verify_admin(auth_header):
    email, role = verify_token(auth_header)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: Not admin")
    return email
@app.get("/health")
def healthcheck():
    return {"status": "ok"}

@app.post("/api/login")
async def login(req: Request):
    data = await req.json()
    email = data.get("email")
    password = data.get("password")
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE email=%s", (email,))
            user = cur.fetchone()
            if user and user["password_hash"] and \
               psycopg2.extensions.adapt(password).getquoted().decode() in user["password_hash"]:
                token = jwt.encode({
                    "sub": email,
                    "role": user.get("role", "user"),
                    "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=2)
                }, SECRET_KEY, algorithm="HS256")
                return {"token": token}
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.post("/briefing")
async def create_briefing(request: Request, authorization: str = Header(None)):
    email, _ = verify_token(authorization)
    data = await request.json()
    report_data = analyze_full_report(data)
    report_data.setdefault("ScoreVisualisierung", f"<b>Score: {report_data.get('score_percent', 0)}%</b>")
    pdf_path = export_pdf(report_data)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO usage_logs (email, pdf_type) VALUES (%s, %s)",
                (email, "KI-Readiness-Report")
            )
    return JSONResponse({"pdf_url": f"/download/{os.path.basename(pdf_path)}"})

@app.get("/download/{pdf_file}")
def download(pdf_file: str):
    file_path = os.path.join(os.path.dirname(__file__), "downloads", pdf_file)
    if os.path.exists(file_path):
        return FileResponse(path=file_path, media_type='application/pdf', filename=pdf_file)
    return JSONResponse({"error": "Datei nicht gefunden"}, status_code=404)

@app.get("/api/stats")
def stats(start: str = None, end: str = None, authorization: str = Header(None)):
    verify_admin(authorization)
    query = """
        SELECT email, COUNT(*) AS total, MAX(created_at) AS last_use
        FROM usage_logs
        WHERE (%s IS NULL OR created_at >= %s)
          AND (%s IS NULL OR created_at <= %s)
        GROUP BY email
        ORDER BY total DESC
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (start, start, end, end))
            return cur.fetchall()

@app.get("/api/export-logs")
def export_logs(start: str = None, end: str = None, authorization: str = Header(None)):
    verify_admin(authorization)
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
    writer = csv.DictWriter(output, fieldnames=["id","email","pdf_type","created_at"])
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return StreamingResponse(iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=usage_logs.csv"})
