# File: live_cache.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

CACHE_FILE = os.getenv("LIVE_CACHE_FILE", "/tmp/ki_live_cache.json")
CACHE_TTL = int(os.getenv("LIVE_CACHE_TTL_SECONDS", "1800"))  # 30 Min
CACHE_ENABLED = os.getenv("LIVE_CACHE_ENABLED", "1").strip().lower() in {"1", "true", "yes"}
MAX_KEYS = 256

def _load() -> dict:
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save(data: dict) -> None:
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass

def cache_get(key: str) -> Optional[Any]:
    if not CACHE_ENABLED:
        return None
    data = _load()
    item = data.get(key)
    if not item:
        return None
    ts = float(item.get("_ts", 0))
    if time.time() - ts > CACHE_TTL:
        # abgelaufen -> entfernen
        data.pop(key, None)
        _save(data)
        return None
    return item.get("value")

def cache_set(key: str, value: Any) -> None:
    if not CACHE_ENABLED:
        return
    data = _load()
    # evtl. LRU‑Purge
    if len(data) >= MAX_KEYS:
        # remove oldest
        oldest = sorted(data.items(), key=lambda kv: kv[1].get("_ts", 0))[:16]
        for k, _ in oldest:
            data.pop(k, None)
    data[key] = {"_ts": time.time(), "value": value}
    _save(data)
