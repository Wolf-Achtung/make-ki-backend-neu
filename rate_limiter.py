# filename: rate_limiter.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import time
import logging
from typing import Optional

try:
    from redis import Redis
except Exception:
    Redis = None  # type: ignore

from settings import settings

logger = logging.getLogger("rate-limit")
_redis_cli: Optional["Redis"] = None
_local_store: dict[str, tuple[int, float]] = {}  # key -> (count, reset_ts)

def _get_redis() -> Optional["Redis"]:
    global _redis_cli
    if _redis_cli is not None:
        return _redis_cli
    if not settings.REDIS_URL or Redis is None:
        return None
    _redis_cli = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_cli

def is_limited(key: str, limit: int | None = None, window_seconds: int | None = None) -> tuple[bool, int]:
    """Increment and check if limit exceeded.
    Returns (blocked, remaining) where remaining may be negative when blocked.
    """
    limit = limit or settings.API_RATE_LIMIT_PER_HOUR
    window_seconds = window_seconds or settings.API_RATE_LIMIT_WINDOW_SECONDS

    cli = _get_redis()
    if cli:
        now = int(time.time())
        window = now // window_seconds
        k = f"rl:{key}:{window}"
        count = cli.incr(k)
        if count == 1:
            cli.expire(k, window_seconds)
        remaining = limit - count
        return (remaining < 0, remaining)

    # fallback local process store (non-shared)
    now = time.time()
    count, reset = _local_store.get(key, (0, now + window_seconds))
    if now > reset:
        count, reset = 0, now + window_seconds
    count += 1
    _local_store[key] = (count, reset)
    remaining = limit - count
    return (remaining < 0, remaining)
