# admin_user_update.py - Fügen Sie dies zum Backend hinzu

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from typing import List
import secrets
import psycopg2
import os
import json

router = APIRouter()
security = HTTPBasic()

# Admin-Credentials (ÄNDERN SIE DIESE!)
ADMIN_USERNAME = "bewertung@ki-sicherheit.jetzt"
ADMIN_PASSWORD = "passadmin11!"  # SOFORT ÄNDERN!

DATABASE_URL = os.getenv("DATABASE_URL")

class UserUpdate(BaseModel):
    email: str
    password: str
    role: str = "user"

def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    """Verifiziert Admin-Zugang"""
    correct_username = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

@router.post("/api/admin/update_users")
async def update_users_from_file(
    file: UploadFile = File(...),
    admin: str = Depends(verify_admin)
):
    """
    Aktualisiert User aus hochgeladener JSON-Datei
    Format: [{"email": "...", "password": "...", "role": "user"}, ...]
    """
    if not file.filename.endswith('.json'):
        raise HTTPException(status_code=400, detail="Nur JSON-Dateien erlaubt")
    
    try:
        content = await file.read()
        users = json.loads(content)
        
        if not isinstance(users, list):
            raise HTTPException(status_code=400, detail="JSON muss ein Array sein")
        
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # pgcrypto Extension sicherstellen
        cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
        
        updated = []
        errors = []
        
        for user in users:
            try:
                email = user.get('email')
                password = user.get('password')
                role = user.get('role', 'user')
                
                if not email or not password:
                    errors.append(f"Fehlende Daten für User: {user}")
                    continue
                
                cur.execute("""
                    INSERT INTO users (email, password_hash, role)
                    VALUES (%s, crypt(%s, gen_salt('bf')), %s)
                    ON CONFLICT (email)
                    DO UPDATE SET 
                        password_hash = EXCLUDED.password_hash,
                        role = EXCLUDED.role
                    RETURNING email
                """, (email, password, role))
                
                result = cur.fetchone()
                if result:
                    updated.append(email)
                    
            except Exception as e:
                errors.append(f"Fehler bei {email}: {str(e)}")
        
        conn.commit()
        cur.close()
        conn.close()
        
        return {
            "status": "success",
            "updated": updated,
            "count": len(updated),
            "errors": errors
        }
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Ungültiges JSON-Format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/admin/update_single_user")
async def update_single_user(
    user: UserUpdate,
    admin: str = Depends(verify_admin)
):
    """Aktualisiert einen einzelnen User"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
        
        cur.execute("""
            INSERT INTO users (email, password_hash, role)
            VALUES (%s, crypt(%s, gen_salt('bf')), %s)
            ON CONFLICT (email)
            DO UPDATE SET 
                password_hash = EXCLUDED.password_hash,
                role = EXCLUDED.role
            RETURNING email
        """, (user.email, user.password, user.role))
        
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        if result:
            return {"status": "success", "email": result[0]}
        else:
            raise HTTPException(status_code=404, detail="User update failed")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Fügen Sie dies zu Ihrer main.py hinzu:
# from admin_user_update import router as admin_router
# app.include_router(admin_router)