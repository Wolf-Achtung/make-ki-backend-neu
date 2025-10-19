# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Dict, Any
import os

def enabled() -> bool:
    return bool(os.getenv("REDIS_URL"))

def enqueue_report(report_id: str, payload: Dict[str, Any]) -> bool:
    if not enabled():
        return False
    try:
        import redis
        from rq import Queue
        from worker_tasks import process_report
        conn = redis.from_url(os.environ["REDIS_URL"], decode_responses=False)
        q = Queue("reports", connection=conn, default_timeout=900)
        q.enqueue(process_report, report_id, payload)
        return True
    except Exception:
        return False

def get_stats() -> Dict[str, int]:
    if not enabled():
        return {"queued": 0, "started": 0, "finished": 0, "failed": 0, "deferred": 0, "scheduled": 0}
    try:
        import redis
        from rq import Queue
        conn = redis.from_url(os.environ["REDIS_URL"], decode_responses=False)
        q = Queue("reports", connection=conn)
        return {
            "queued": len(q.jobs),
            "started": 0,
            "finished": 0,
            "failed": len(q.failed_job_registry),
            "deferred": len(q.deferred_job_registry),
            "scheduled": len(q.scheduled_job_registry),
        }
    except Exception:
        return {"queued": 0, "started": 0, "finished": 0, "failed": 0, "deferred": 0, "scheduled": 0}
