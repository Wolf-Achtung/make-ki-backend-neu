# filename: live_logger.py
from __future__ import annotations
import json
import logging
import os
from typing import Any, Dict, Optional

"""
Structured logging for the live layer.
- Emits JSON lines via logging (logger "live_layer") and optionally to stdout
  (controlled by ENV LIVE_LOG_STDOUT, default '1').
- Safe: logging failure must never break the request flow.
"""

logger = logging.getLogger("live_layer")
# Avoid "No handler found" in library contexts; still propagates to root.
if not logger.handlers:
    logger.addHandler(logging.NullHandler())

def log_event(
    provider: str,
    model: Optional[str],
    status: str,
    latency_ms: int,
    count: int = 0,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    payload = {
        "evt": "live_search",
        "provider": provider,
        "model": model,
        "status": status,
        "latency_ms": int(latency_ms),
        "count": int(count),
    }
    if extra:
        payload.update({k: v for k, v in extra.items() if v is not None})
    try:
        logger.info(json.dumps(payload, ensure_ascii=False))
    except Exception:
        # Logging must never block the flow
        pass
    # Also emit to stdout unless explicitly disabled
    try:
        if (os.getenv("LIVE_LOG_STDOUT", "1").strip().lower() in {"1", "true", "yes"}):
            print(json.dumps(payload, ensure_ascii=False))
    except Exception:
        pass
