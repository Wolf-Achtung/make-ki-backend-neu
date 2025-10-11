
# live_logger.py
# Strukturierte Ereignis-Logs für Live-Suche (Perplexity/Tavily)
from __future__ import annotations
import json
import logging
import time
from typing import Any, Dict, Optional

_LOGGER_NAME = "live_layer"
logger = logging.getLogger(_LOGGER_NAME)

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
        "latency_ms": latency_ms,
        "count": int(count),
    }
    if extra:
        payload.update(extra)
    try:
        logger.info(json.dumps(payload, ensure_ascii=False))
    except Exception:
        # best-effort logging; never raise
        pass
