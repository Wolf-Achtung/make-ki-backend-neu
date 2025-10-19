# filename: updated_backend/settings.py
# -*- coding: utf-8 -*-
"""
Project settings for the KI‑Status‑Report backend.

This module uses ``pydantic-settings`` to provide configuration values from
environment variables, an optional ``.env`` file and sensible defaults.  The
parsing of CORS origins is intentionally permissive:

* ``CORS_ALLOW_ORIGINS_RAW`` may be a JSON array (e.g. ``["https://a.com","https://b.com"]``),
  a comma-separated string (``https://a.com,https://b.com``), a single
  origin or the wildcard ``*``.  Empty values default to ``['*']``.
* The computed field ``CORS_ALLOW_ORIGINS`` returns a list of strings and
  is used by the application to configure CORS middleware.
* Other feature flags (``QUEUE_ENABLED``, ``PDF_SERVICE_ENABLED``) are
  boolean fields that default to ``False``.

If this module fails to import, the application will fall back to a minimal
internal settings class defined in ``main.py``, allowing the server to
respond to health checks with at least basic information.
"""

from __future__ import annotations

import json
import os
from typing import List, Optional

from pydantic import computed_field, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_origins(raw: Optional[str]) -> list[str]:
    """
    Convert the raw CORS origins value into a list of strings.

    Accepts JSON arrays, comma-separated strings, a single origin or the
    wildcard ``*``.  If parsing fails or the input is empty, returns
    ``['*']``.  The returned list is stripped of whitespace and empty
    strings are ignored.
    """
    if raw is None:
        return ["*"]
    s = str(raw).strip()
    if s in ("", "*"):
        return ["*"]
    # Try JSON first
    try:
        parsed = json.loads(s)
        if isinstance(parsed, str):
            return [parsed.strip()]
        if isinstance(parsed, (list, tuple)):
            items = []
            for x in parsed:
                if x is None:
                    continue
                items.append(str(x).strip())
            return [i for i in items if i]
    except Exception:
        pass
    # Fallback: comma-separated list
    parts = [p.strip() for p in s.split(",") if p.strip()]
    return parts if parts else ["*"]


class Settings(BaseSettings):
    """Central application settings configured via environment variables."""

    # Basic metadata
    APP_NAME: str = "KI‑Status‑Report Backend"
    APP_VERSION: str = os.getenv("APP_VERSION", "2025.10")
    ENV: str = os.getenv("ENV", "production")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # CORS configuration: use RAW so pydantic-settings doesn't attempt to
    # coerce this to a list and fail if the value isn't valid JSON.
    CORS_ALLOW_ORIGINS_RAW: Optional[str] = Field(
        default=None,
        description="JSON array, comma-separated string or '*' representing allowed origins",
    )
    CORS_ALLOW_CREDENTIALS: bool = False
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]

    # Feature flags
    QUEUE_ENABLED: bool = False
    PDF_SERVICE_URL: Optional[str] = None
    PDF_SERVICE_ENABLED: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @computed_field(return_type=list[str])  # type: ignore[misc]
    @property
    def CORS_ALLOW_ORIGINS(self) -> list[str]:
        """Return a list of allowed origins parsed from the RAW value or fallback."""
        raw = self.CORS_ALLOW_ORIGINS_RAW or os.getenv("CORS_ALLOW_ORIGINS")
        return _parse_origins(raw)


# Instantiate a single settings object for the application to use
settings = Settings()

# Backwards compatibility: some modules import ``allowed_origins`` directly
allowed_origins = settings.CORS_ALLOW_ORIGINS