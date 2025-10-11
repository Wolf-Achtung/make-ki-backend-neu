# filename: live_logger.py
from __future__ import annotations
import json, logging
from typing import Any, Dict, Optional

logger = logging.getLogger("live_layer")

def log_event(provider: str, model: Optional[str], status: str, latency_ms: int, count: int = 0, extra: Optional[Dict[str, Any]] = None) -> None:
    payload = {"evt": "live_search", "provider": provider, "model": model, "status": status, "latency_ms": latency_ms, "count": int(count)}
    if extra: payload.update(extra)
    try:
        logger.info(json.dumps(payload, ensure_ascii=False))
    except Exception:
        pass
