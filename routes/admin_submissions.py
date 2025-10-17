# filename: routes/admin_submissions.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException, status
from sqlalchemy import text
from jose import jwt, JWTError
from typing import List, Dict, Any
from settings import settings
from db import get_session

router = APIRouter(prefix="/admin", tags=["admin"])

def _current_user_from_request(request: Request) -> Dict[str, Any]:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token = auth_header.split(" ", 1)[1]
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except JWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

@router.get("/submissions")
def submissions(request: Request) -> List[Dict[str, Any]]:
    claims = _current_user_from_request(request)
    if claims.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    with get_session() as s:
        rows = s.execute(text("""            SELECT id, email, created_at, 
                   CASE WHEN exists (SELECT 1 FROM information_schema.columns 
                                     WHERE table_name='tasks' AND column_name='score_percent') 
                        THEN score_percent ELSE NULL END AS score_percent
            FROM tasks
            ORDER BY created_at DESC
        """)).mappings().all()
    items: List[Dict[str, Any]] = []
    for r in rows:
        created_ts = None
        ca = r.get("created_at")
        try:
            created_ts = int(ca.timestamp()) if ca else None
        except Exception:
            created_ts = None
        items.append({
            "job_id": r.get("id"),
            "user_email": r.get("email"),
            "created": created_ts,
            "score_percent": r.get("score_percent")
        })
    return items
