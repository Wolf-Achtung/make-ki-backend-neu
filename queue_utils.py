# -*- coding: utf-8 -*-
"""Queue utilities for Redis/RQ."""
from __future__ import annotations

import os
from typing import List

from redis import Redis
from rq import Queue

def get_redis_connection() -> Redis:
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        raise RuntimeError("REDIS_URL is not set")
    return Redis.from_url(url, decode_responses=False)

def get_queue_names() -> List[str]:
    raw = os.getenv("RQ_QUEUES", "reports,emails")
    names = [n.strip() for n in raw.split(",") if n.strip()]
    return names or ["default"]

def get_queue(name: str | None = None) -> Queue:
    conn = get_redis_connection()
    default_timeout = int(os.getenv("RQ_JOB_TIMEOUT", "600"))
    qname = name or get_queue_names()[0]
    return Queue(qname, connection=conn, default_timeout=default_timeout)
