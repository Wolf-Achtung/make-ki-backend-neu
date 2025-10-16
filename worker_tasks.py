# filename: worker_tasks.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from analyzer import run_analysis
from db import get_session, init_db
from models import Task

logger = logging.getLogger("worker-tasks")

# Ensure DB is initialized when worker process starts
try:
    init_db()
except Exception as e:
    logger.error("DB init failed in worker: %s", e)
    raise

def process_report(report_id: str, payload: dict) -> None:
    """RQ job function to process a report and persist HTML into DB."""
    try:
        html = asyncio.run(run_analysis(payload))
        with get_session() as s:
            task = s.get(Task, report_id)
            if task:
                task.status = "done"
                task.html = html
                task.finished_at = datetime.utcnow()
            else:
                # create if missing
                task = Task(id=report_id, status="done", html=html, finished_at=datetime.utcnow())
                s.add(task)
        logger.info("report %s processed", report_id)
    except Exception as e:
        logger.exception("report %s failed: %s", report_id, e)
        with get_session() as s:
            task = s.get(Task, report_id)
            if task:
                task.status = "failed"
                task.error = str(e)
                task.finished_at = datetime.utcnow()
