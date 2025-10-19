# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, status, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, EmailStr
from rq.job import Job
from rq import Queue
from redis import Redis

from queue_utils import get_queue, get_queue_names, get_redis_connection
from tasks import analyze_and_render

logger = logging.getLogger("ki-backend.tasks_api")
router = APIRouter(tags=["tasks"])

class AnalyzeIn(BaseModel):
    html: Optional[str] = Field(None, description="Inline HTML to render")
    url: Optional[str] = Field(None, description="URL that the PDF service should capture")
    email: Optional[EmailStr] = Field(None, description="If set, the PDF will be mailed after rendering")
    filename: Optional[str] = Field(None, description="Attachment name (default: ki-report.pdf)")
    model_config = dict(extra="ignore")

@router.post("/analyze", status_code=status.HTTP_202_ACCEPTED)
def enqueue_analyze(payload: AnalyzeIn):
    if not (payload.html or payload.url):
        raise HTTPException(status_code=400, detail="Provide 'html' or 'url'")
    q = get_queue("reports")
    job: Job = q.enqueue(analyze_and_render, payload.model_dump(), job_timeout=q.default_timeout, result_ttl=3600)
    return {"ok": True, "status": "queued", "job_id": job.id, "queue": job.origin}

@router.get("/result/{job_id}")
def get_result(job_id: str, download: bool = Query(default=False)):
    redis: Redis = get_redis_connection()
    try:
        job = Job.fetch(job_id, connection=redis)
        status_str = job.get_status()
    except Exception:
        job = None
        status_str = "unknown"
    pdf_key = f"pdf:{job_id}"
    pdf = redis.get(pdf_key)
    if download:
        if pdf:
            filename = "ki-report.pdf"
            if job and isinstance(job.result, dict) and job.result.get("filename"):
                filename = job.result["filename"]
            return StreamingResponse(iter([pdf]), media_type="application/pdf", headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            })
        raise HTTPException(status_code=202, detail="Result not ready")
    result = job.result if job and job.is_finished else None
    return JSONResponse({"ok": True, "status": status_str, "job_id": job_id, "has_pdf": bool(pdf), "result": result})

@router.get("/queue/ping")
def queue_ping():
    redis: Redis = get_redis_connection()
    pong = redis.ping()
    return {"ok": True, "redis": "ok" if pong else "down", "queues": get_queue_names()}
