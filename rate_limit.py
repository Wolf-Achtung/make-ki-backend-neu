# filename: backend/rate_limit.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from typing import Dict

class TokenBucket:
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = max(1, capacity)
        self.tokens = float(capacity)
        self.refill_rate = float(refill_rate)
        self.last = time.time()

    def allow(self) -> bool:
        now = time.time()
        delta = now - self.last
        self.last = now
        self.tokens = min(self.capacity, self.tokens + delta * self.refill_rate)
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False

class RateLimiter:
    """Simple in-memory limiter per key (e.g., client IP)."""
    def __init__(self, capacity: int = 10, refill_rate: float = 0.2):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.buckets: Dict[str, TokenBucket] = {}

    def allow(self, key: str) -> bool:
        b = self.buckets.get(key)
        if b is None:
            b = self.buckets[key] = TokenBucket(self.capacity, self.refill_rate)
        return b.allow()
