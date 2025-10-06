# File: feedback_api.py
# -*- coding: utf-8 -*-
"""
Feedback-API für den KI-Checkup (Gold-Standard+)
- Akzeptiert Feedback von DE/EN Formularseiten.
- Schreibt robust in Postgres (feedback_logs JSONB); optional auch nur E-Mail.
- Stellt mehrere kompatible Routen bereit: /feedback, /api/feedback, /v1/feedback
- E-Mail-Fallback: /feedback_email (falls DB nicht erreichbar)

ENV:
  DATABASE_URL               (optional, Postgres)
  SMTP_HOST, SMTP_PORT=587, SMTP_USER, SMTP_PASS, SMTP_FROM
  FEEDBACK_EMAIL_TO=bewertung@ki-sicherheit.jetzt
  CORS_ALLOW_ORIGINS="https://make.ki-sicherheit.jetzt, http://localhost:*, https://*.ki-sicherheit.jetzt"
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.text import MIMEText
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, FastAPI, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

log = logging.getLogger("feedback_api")
if not log.handlers:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

router = APIRouter()


# ------------------------------ Modelle --------------------------------------

class FeedbackIn(BaseModel):
    user_email: Optional[EmailStr] = Field(None, description="E-Mail der sendenden Person")
    email: Optional[EmailStr] = None  # alternative Feldbezeichnung
    variant: Optional[str] = None
    report_version: Optional[str] = None
    lang_ui: Optional[str] = None
    timestamp: Optional[str] = None
    # Likert / Auswahl
    hilfe: Optional[str] = None
    verstaendlich_analyse: Optional[str] = None
    verstaendlich_empfehlung: Optional[str] = None
    vertrauen: Optional[str] = None
    dauer: Optional[str] = None
    # Freitexte
    serio: Optional[str] = None
    textstellen: Optional[str] = None
    unsicher: Optional[str] = None
    features: Optional[str] = None
    freitext: Optional[str] = None
    # Empfehlung (optional)
    tipp_name: Optional[str] = None
    tipp_firma: Optional[str] = None
    tipp_email: Optional[EmailStr] = None

    class Config:
        extra = "allow"  # künftige Felder zulassen


# ------------------------------ DB -------------------------------------------

def _db_conn():
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return None
    try:
        import psycopg2  # type: ignore
    except Exception:
        log.warning("psycopg2 not available; email fallback only.")
        return None
    try:
        conn = psycopg2.connect(url)
        conn.autocommit = True
        return conn
    except Exception as e:
        log.error("DB connect failed: %s", e)
        return None


def _db_write(payload: Dict[str, Any]) -> bool:
    conn = _db_conn()
    if not conn:
        return False
    try:
        from psycopg2.extras import Json  # type: ignore
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback_logs (
                    id SERIAL PRIMARY KEY,
                    email TEXT,
                    payload JSONB,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )
            email = payload.get("user_email") or payload.get("email")
            cur.execute("INSERT INTO feedback_logs(email, payload) VALUES (%s, %s)", (email, Json(payload)))
        return True
    except Exception as e:
        log.error("DB write failed: %s", e)
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ------------------------------ Mail -----------------------------------------

def _send_admin_mail(payload: Dict[str, Any]) -> bool:
    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "").strip()
    pwd = os.getenv("SMTP_PASS", "").strip()
    mail_from = os.getenv("SMTP_FROM", user or "no-reply@ki-sicherheit.jetzt").strip()
    mail_to = os.getenv("FEEDBACK_EMAIL_TO", "bewertung@ki-sicherheit.jetzt").strip()
    if not host or not mail_to:
        log.warning("SMTP not configured or FEEDBACK_EMAIL_TO missing; skip email.")
        return False

    ts = payload.get("timestamp") or datetime.now(timezone.utc).isoformat()
    sender = payload.get("user_email") or payload.get("email") or "unbekannt"
    subject = f"KI-Checkup Feedback – {sender} – {ts}"

    pretty = json.dumps(payload, ensure_ascii=False, indent=2)
    body = f"""
    <div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;color:#0f172a">
      <h2 style="margin:0 0 8px 0">Neues Feedback zum KI-Checkup</h2>
      <p style="margin:4px 0 12px 0">Von: <b>{sender}</b> · Zeitpunkt: <code>{ts}</code></p>
      <h3 style="margin:12px 0 6px 0">Gesamtes Feedback (JSON)</h3>
      <pre style="background:#0b1220;color:#e2e8f0;padding:12px;border-radius:10px;overflow:auto">{pretty}</pre>
    </div>
    """

    try:
        msg = MIMEText(body, "html", "utf-8")
        msg["Subject"] = subject
        msg["From"] = mail_from
        msg["To"] = mail_to
        ctx = ssl.create_default_context()
        with smtplib.SMTP(host, port) as s:
            try:
                s.starttls(context=ctx)
            except Exception:
                pass
            if user and pwd:
                s.login(user, pwd)
            s.sendmail(mail_from, [mail_to], msg.as_string())
        return True
    except Exception as e:
        log.error("Send email failed: %s", e)
        return False


# ------------------------------ Helper ---------------------------------------

def _normalize_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(data)
    out["user_email"] = out.get("user_email") or out.get("email")
    out.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    lang = (out.get("lang_ui") or "").lower()
    out["lang_ui"] = "en" if lang.startswith("en") else "de"
    return out


def _handle_feedback(payload: FeedbackIn, background: BackgroundTasks) -> Dict[str, Any]:
    data = _normalize_payload(payload.dict(exclude_none=True))
    if not data.get("user_email"):
        raise HTTPException(status_code=422, detail="user_email (or email) is required")

    ok_db = _db_write(data)
    background.add_task(_send_admin_mail, data)  # immer auch E-Mail
    return {"ok": True, "stored": ok_db}


# ------------------------------ Routes ---------------------------------------

@router.post("/feedback")
@router.post("/api/feedback")
@router.post("/v1/feedback")
async def submit_feedback(payload: FeedbackIn, request: Request, background: BackgroundTasks):
    return _handle_feedback(payload, background)


@router.post("/feedback_email")
async def submit_feedback_email(payload: FeedbackIn, request: Request, background: BackgroundTasks):
    # Nur E-Mail, keine DB
    data = _normalize_payload(payload.dict(exclude_none=True))
    if not data.get("user_email"):
        raise HTTPException(status_code=422, detail="user_email (or email) is required")
    background.add_task(_send_admin_mail, data)
    return {"ok": True, "stored": False}


# ------------------------------ Integration ----------------------------------

def attach_to(app: FastAPI) -> None:
    """Minimal-invasive Integration in eine bestehende FastAPI-App."""
    app.include_router(router)
    try:
        from fastapi.middleware.cors import CORSMiddleware  # type: ignore
        origins = [o.strip() for o in os.getenv(
            "CORS_ALLOW_ORIGINS",
            "https://make.ki-sicherheit.jetzt, http://localhost:*, https://*.ki-sicherheit.jetzt"
        ).split(",")]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=False,
            allow_methods=["POST", "OPTIONS"],
            allow_headers=["*"],
        )
    except Exception:
        log.info("CORS middleware not attached (fastapi-cors not available).")
