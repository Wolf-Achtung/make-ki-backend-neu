# filename: queue_redis.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Optional

try:
    from redis import Redis
    from rq import Queue
except Exception:
    Redis = None  # type: ignore
    Queue = None  # type: ignore

from settings import settings

_redis_cli: Optional["Redis"] = None
_queue: Optional["Queue"] = None

def enabled() -> bool:
    return settings.REDIS_URL is not None and Redis is not None and Queue is not None

def _get_queue() -> Optional["Queue"]:
    global _redis_cli, _queue
    if _queue is not None:
        return _queue
    if not enabled():
        return None
    _redis_cli = Redis.from_url(settings.REDIS_URL)
    _queue = Queue(settings.QUEUE_NAME, connection=_redis_cli, default_timeout=900)  # 15 min
    return _queue

def enqueue_report(report_id: str, payload: dict) -> Optional[str]:
    q = _get_queue()
    if not q:
        return None
    # Import here so worker can import the same module path
    from worker_tasks import process_report  # type: ignore
    job = q.enqueue(process_report, report_id, payload)
    return job.id
