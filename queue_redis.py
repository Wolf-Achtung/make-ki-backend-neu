# filename: queue_redis.py
# -*- coding: utf-8 -*-
# Redis/RQ-Integration für asynchrone Reportjobs (Gold-Standard+).
# - enabled()     -> True, wenn REDIS_URL gesetzt
# - enqueue_report(report_id, payload) -> legt Job in Queue, mit Retry/Timeout/TTL
# - get_stats()   -> Queue-Kennzahlen für Admin-Status

from __future__ import annotations
import os
import logging
from typing import Any, Dict, Optional

try:
    from redis import Redis
    from rq import Queue, Retry, Connection
    from rq.registry import StartedJobRegistry, FinishedJobRegistry, FailedJobRegistry, ScheduledJobRegistry, DeferredJobRegistry
    RQ_AVAILABLE = True
except Exception:
    RQ_AVAILABLE = False

logger = logging.getLogger("queue_redis")

REDIS_URL = os.getenv("REDIS_URL", "").strip()
QUEUE_NAME = os.getenv("REDIS_QUEUE_NAME", "reports")
JOB_TIMEOUT = int(os.getenv("WORKER_JOB_TIMEOUT_SECONDS", "900"))  # 15 min default
RESULT_TTL = int(os.getenv("WORKER_RESULT_TTL_SECONDS", "600"))    # 10 min default

_cached = {"queue": None, "conn": None}

def enabled() -> bool:
    return bool(REDIS_URL and RQ_AVAILABLE)

def _get_queue() -> Optional['Queue']:
    if not enabled():
        return None
    if _cached["queue"]:
        return _cached["queue"]
    try:
        conn = Redis.from_url(REDIS_URL)
        q = Queue(QUEUE_NAME, connection=conn)
        _cached["queue"] = q
        _cached["conn"] = conn
        return q
    except Exception as e:
        logger.warning("Redis queue init failed: %s", e)
        return None

def enqueue_report(report_id: str, payload: Dict[str, Any]) -> bool:
    """
    Legt den Job auf die Queue. Liefert False bei Fehler (kein Raise, um den Webflow nicht hart zu brechen).
    """
    q = _get_queue()
    if not q:
        logger.info("enqueue_report: queue not available (enabled=%s, url set=%s)", enabled(), bool(REDIS_URL))
        return False
    try:
        with Connection(q.connection):
            job = q.enqueue(
                "worker_tasks.process_report",
                report_id,
                payload,
                job_timeout=JOB_TIMEOUT,
                retry=Retry(max=2, interval=[30, 120]),
                result_ttl=RESULT_TTL
            )
            logger.info("enqueued job id=%s report_id=%s", job.id, report_id)
        return True
    except Exception as e:
        logger.exception("enqueue failed for %s: %s", report_id, e)
        return False

def get_stats() -> Dict[str, int]:
    """
    Liefert einfache Queue-Zahlen für /admin/status.
    Gibt leere Werte zurück, wenn Queue nicht aktiv ist.
    """
    q = _get_queue()
    if not q:
        return {"queued": 0, "started": 0, "finished": 0, "failed": 0, "deferred": 0, "scheduled": 0}
    try:
        started = StartedJobRegistry(queue=q).count
        finished = FinishedJobRegistry(queue=q).count
        failed = FailedJobRegistry(queue=q).count
        deferred = DeferredJobRegistry(queue=q).count
        scheduled = ScheduledJobRegistry(queue=q).count
        return {"queued": q.count, "started": started, "finished": finished, "failed": failed, "deferred": deferred, "scheduled": scheduled}
    except Exception:
        # minimal fallback
        return {"queued": q.count, "started": 0, "finished": 0, "failed": 0, "deferred": 0, "scheduled": 0}
