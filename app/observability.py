
# file: app/observability.py
# -*- coding: utf-8 -*-
"""
Observability endpoints and lightweight metrics for KI‑Status‑Report (Gold‑Standard+).

Provides:
- /healthz  → JSON with schema/prompt versions, provider flags, throttles and CORS
- /metrics  → Prometheus‑compatible text exposition (5xx / 429 alerts)

Drop‑in usage (preferred):
    from app.observability import router, MetricsMiddleware
    app.add_middleware(MetricsMiddleware)
    app.include_router(router)

If you cannot edit main.py right now, you may temporarily enable the auto‑attach
behaviour by importing app.observability somewhere that is guaranteed to run
at startup. That import will try to attach to a global FastAPI app named
`app` in the `main` module. This is only a convenience and not recommended
for long‑term use.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, Iterable, List, Optional, Tuple

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware

log = logging.getLogger("observability")

# -----------------------------
# Configuration via ENV
# -----------------------------
APP_NAME = os.getenv("APP_NAME", "KI-Status-Report")
BASE_DIR = Path(os.getenv("APP_BASE", os.getcwd())).resolve()
SCHEMA_FILE = Path(os.getenv("HEALTH_SCHEMA_FILE", str(BASE_DIR / "shared" / "report_schema.json")))
PROMPT_DE = Path(os.getenv("COACH_PROMPT_DE", str(BASE_DIR / "prompts" / "de" / "business_de.md")))
PROMPT_EN = Path(os.getenv("COACH_PROMPT_EN", str(BASE_DIR / "prompts" / "en" / "business_en.md")))

# Metrics window and alert thresholds
WIN_SECONDS = int(os.getenv("METRICS_WINDOW_SECONDS", "3600"))  # rolling window
ALERT_5XX = float(os.getenv("METRICS_ALERT_5XX_RATE", "0.05"))  # 5%
ALERT_429 = float(os.getenv("METRICS_ALERT_429_RATE", "0.05"))  # 5%

# Feature flags (already present in the project’s ENV – defaults are safe)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")                     # fileciteturn0file0
EXEC_SUMMARY_MODEL = os.getenv("EXEC_SUMMARY_MODEL", "gpt-4o")           # fileciteturn0file0
EXEC_SUMMARY_FALLBACK = os.getenv("EXEC_SUMMARY_MODEL_FALLBACK", "gpt-4o")# fileciteturn0file0
OPENAI_MODEL_DEFAULT = os.getenv("OPENAI_MODEL_DEFAULT", "gpt-4o")       # fileciteturn0file0
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")     # fileciteturn0file0
PPLX_USE_CHAT = os.getenv("PPLX_USE_CHAT", "0")                          # fileciteturn0file0
SEARCH_PROVIDER = os.getenv("SEARCH_PROVIDER", "hybrid")                 # fileciteturn0file0
HYBRID_LIVE = os.getenv("HYBRID_LIVE", "1")                              # fileciteturn0file0
LIVE_CACHE_ENABLED = os.getenv("LIVE_CACHE_ENABLED", "1")                # fileciteturn0file0
EU_FUNDING_ENABLED = os.getenv("EU_FUNDING_ENABLED", "true")             # fileciteturn0file0
CORS_ALLOW_ORIGINS = os.getenv("CORS_ALLOW_ORIGINS", "")                 # fileciteturn0file0
PDF_SERVICE_URL = os.getenv("PDF_SERVICE_URL", "")                       # fileciteturn0file0
EU_THROTTLE_RPM = os.getenv("EU_THROTTLE_RPM", "24")                     # fileciteturn0file0
SEARCH_THROTTLE_PER_REPORT = os.getenv("SEARCH_THROTTLE_PER_REPORT", "3")# fileciteturn0file0
MAIL_THROTTLE_PER_USER_PER_HOUR = os.getenv("MAIL_THROTTLE_PER_USER_PER_HOUR", "10") # fileciteturn0file0

router = APIRouter()

# -----------------------------
# Utilities
# -----------------------------
def _sha256_of(path: Path) -> Optional[str]:
    try:
        with path.open("rb") as f:
            import hashlib
            h = hashlib.sha256()
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None

def _mtime_iso(path: Path) -> Optional[str]:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    except Exception:
        return None

def _split_origins(csv_value: str) -> List[str]:
    if not csv_value:
        return []
    return [o.strip() for o in csv_value.split(",") if o.strip()]

# -----------------------------
# Metrics implementation
# -----------------------------
@dataclass
class _Point:
    t: float
    status: int

class _RollingCounter:
    """Simple rolling window counter of HTTP status classes (2xx/3xx/4xx/5xx) plus raw 429 count."""
    def __init__(self, win_seconds: int = WIN_SECONDS) -> None:
        self.win = win_seconds
        self.q: Deque[_Point] = deque()  # type: ignore[var-annotated]
        self.lock = threading.Lock()

    def add(self, status: int) -> None:
        now = time.time()
        with self.lock:
            self.q.append(_Point(now, status))
            self._evict(now)

    def _evict(self, now: Optional[float] = None) -> None:
        if now is None:
            now = time.time()
        cutoff = now - self.win
        while self.q and self.q[0].t < cutoff:
            self.q.popleft()

    def snapshot(self) -> Dict[str, Any]:
        now = time.time()
        with self.lock:
            self._evict(now)
            total = len(self.q)
            buckets = defaultdict(int)
            for p in self.q:
                code = p.status
                if code == 429:
                    buckets["429"] += 1
                buckets[f"{code // 100}xx"] += 1
            return {
                "total": total,
                "by_class": dict(buckets),
                "rate_5xx": (buckets.get("5xx", 0) / total) if total else 0.0,
                "rate_429": (buckets.get("429", 0) / total) if total else 0.0,
            }

_rolling = _RollingCounter()

class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response
        try:
            response = await call_next(request)
        except Exception:
            # If the downstream raised, we still account it as 500.
            _rolling.add(500)
            raise
        # record
        try:
            status = int(getattr(response, "status_code", 200))
        except Exception:
            status = 200
        _rolling.add(status)
        return response

# -----------------------------
# Endpoints
# -----------------------------
@router.get("/healthz", response_class=JSONResponse)
async def healthz() -> JSONResponse:
    """Self‑contained status document useful for CI/monitors."""
    schema_hash = _sha256_of(SCHEMA_FILE)
    prompts = []
    for p, lang in [(PROMPT_DE, "de"), (PROMPT_EN, "en")]:
        prompts.append({
            "lang": lang,
            "path": str(p),
            "present": p.exists(),
            "sha256": _sha256_of(p),
            "mtime": _mtime_iso(p),
        })
    payload = {
        "status": "ok",
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "app": APP_NAME,
        "env_summary": {
            "llm_provider": LLM_PROVIDER,                     # fileciteturn0file0
            "exec_summary_model": EXEC_SUMMARY_MODEL,         # fileciteturn0file0
            "exec_summary_fallback": EXEC_SUMMARY_FALLBACK,   # fileciteturn0file0
            "openai_default": OPENAI_MODEL_DEFAULT,           # fileciteturn0file0
            "claude_model": CLAUDE_MODEL,                     # fileciteturn0file0
            "pplx_use_chat": PPLX_USE_CHAT,                   # fileciteturn0file0
            "search_provider": SEARCH_PROVIDER,               # fileciteturn0file0
            "hybrid_live": HYBRID_LIVE,                       # fileciteturn0file0
            "live_cache_enabled": LIVE_CACHE_ENABLED,         # fileciteturn0file0
            "eu_funding_enabled": EU_FUNDING_ENABLED,         # fileciteturn0file0
            "pdf_service_url": PDF_SERVICE_URL,               # fileciteturn0file0
            "cors_allow_origins": _split_origins(CORS_ALLOW_ORIGINS),  # fileciteturn0file0
        },
        "schema": {
            "path": str(SCHEMA_FILE),
            "present": SCHEMA_FILE.exists(),
            "sha256": schema_hash,
            "mtime": _mtime_iso(SCHEMA_FILE),
        },
        "prompts": prompts,
        "throttles": {
            "eu_throttle_rpm": EU_THROTTLE_RPM,                         # fileciteturn0file0
            "search_throttle_per_report": SEARCH_THROTTLE_PER_REPORT,   # fileciteturn0file0
            "mail_throttle_user_hour": MAIL_THROTTLE_PER_USER_PER_HOUR, # fileciteturn0file0
        },
        "metrics_window_seconds": WIN_SECONDS,
    }
    return JSONResponse(payload)

def _prom_line(metric: str, value: float, labels: Optional[Dict[str, str]] = None) -> str:
    lbl = ""
    if labels:
        # escape quote and backslash per Prometheus text format
        esc = lambda s: str(s).replace("\\", "\\\\").replace('"', '\\"')
        parts = [f'{k}="{esc(v)}"' for k, v in sorted(labels.items())]
        lbl = "{" + ",".join(parts) + "}"
    return f"{metric}{lbl} {value}\n"

@router.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> PlainTextResponse:
    """Prometheus exposition for Railway monitoring."""
    snap = _rolling.snapshot()
    total = snap.get("total", 0)
    by = snap.get("by_class", {})
    rate_5xx = float(snap.get("rate_5xx", 0.0))
    rate_429 = float(snap.get("rate_429", 0.0))
    lines = []
    lines.append("# HELP http_requests_total Total requests observed by middleware") 
    lines.append("# TYPE http_requests_total counter")
    lines.append(_prom_line("http_requests_total", float(total)))
    for cls in ("2xx", "3xx", "4xx", "5xx", "429"):
        v = float(by.get(cls, 0))
        lines.append(_prom_line("http_requests_class_total", v, {"class": cls}))
    lines.append("# HELP http_requests_error_rate_5xx Fraction of 5xx responses in window")
    lines.append("# TYPE http_requests_error_rate_5xx gauge")
    lines.append(_prom_line("http_requests_error_rate_5xx", rate_5xx))
    lines.append("# HELP http_upstream_throttle_rate_429 Fraction of 429s in window")
    lines.append("# TYPE http_upstream_throttle_rate_429 gauge")
    lines.append(_prom_line("http_upstream_throttle_rate_429", rate_429))

    # Simple boolean alerts based on thresholds
    lines.append("# HELP alert_5xx_rate_over_threshold 1 if 5xx rate exceeds threshold")
    lines.append("# TYPE alert_5xx_rate_over_threshold gauge")
    lines.append(_prom_line("alert_5xx_rate_over_threshold", 1.0 if rate_5xx > ALERT_5XX else 0.0, {"threshold": str(ALERT_5XX)}))
    lines.append("# HELP alert_429_rate_over_threshold 1 if 429 rate exceeds threshold")
    lines.append("# TYPE alert_429_rate_over_threshold gauge")
    lines.append(_prom_line("alert_429_rate_over_threshold", 1.0 if rate_429 > ALERT_429 else 0.0, {"threshold": str(ALERT_429)}))

    # Build info (useful labels for dashboards)
    build = {
        "llm_provider": LLM_PROVIDER,
        "exec_summary_model": EXEC_SUMMARY_MODEL,
        "openai_default": OPENAI_MODEL_DEFAULT,
        "claude_model": CLAUDE_MODEL,
        "pplx_use_chat": PPLX_USE_CHAT,
        "search_provider": SEARCH_PROVIDER,
        "hybrid_live": HYBRID_LIVE,
        "live_cache_enabled": LIVE_CACHE_ENABLED,
        "eu_funding_enabled": EU_FUNDING_ENABLED,
    }
    lines.append("# HELP app_build_info LLM/search flags as labels") 
    lines.append("# TYPE app_build_info gauge")
    lines.append(_prom_line("app_build_info", 1.0, build))

    text = "".join(lines)
    return PlainTextResponse(content=text, media_type="text/plain; version=0.0.4; charset=utf-8")


# Optional: auto‑attach if imported at startup and main.app exists.
try:
    import main as _main_mod  # type: ignore
    _maybe_app = getattr(_main_mod, "app", None)
    if _maybe_app is not None:
        _maybe_app.add_middleware(MetricsMiddleware)
        _maybe_app.include_router(router)
        log.info("observability: attached router and middleware to main.app")
except Exception:  # pragma: no cover – best effort only
    pass
