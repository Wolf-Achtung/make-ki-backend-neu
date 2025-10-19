# -*- coding: utf-8 -*-
from __future__ import annotations
import time
from typing import Tuple
import os

_memory_store = {}

def _redis_client():
    try:
        import redis  # type: ignore
        url = os.environ.get("REDIS_URL")
        return redis.from_url(url, decode_responses=True) if url else None
    except Exception:
        return None

def is_limited(key: str, limit_per_hour: int, window_seconds: int) -> Tuple[bool, int]:
    """Return (blocked, remaining). Uses Redis if available, else in-process memory."""
    if limit_per_hour <= 0:
        return (False, limit_per_hour)
    rc = _redis_client()
    now = int(time.time())
    window = window_seconds or 3600
    if rc:
        pipe = rc.pipeline()
        bucket = f"ratelimit:{key}:{now // window}"
        pipe.incr(bucket, 1)
        pipe.expire(bucket, window + 5)
        count, _ = pipe.execute()
        remaining = max(0, limit_per_hour - int(count))
        return (remaining <= 0, remaining)
    # memory fallback
    bucket = f"{key}:{now // window}"
    _memory_store.setdefault(bucket, 0)
    _memory_store[bucket] += 1
    remaining = max(0, limit_per_hour - _memory_store[bucket])
    return (remaining <= 0, remaining)
