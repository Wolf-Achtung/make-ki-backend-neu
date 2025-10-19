"""
Centralized settings for the KI-Status-Report backend.
Robust to empty/invalid env values (notably CORS origins) to avoid Railway crashes.
"""
from __future__ import annotations

import json
import os
from typing import List, Optional

from pydantic import computed_field, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_origins(raw: Optional[str]) -> list[str]:
    """
    Accept JSON list, comma separated string, or single '*'.
    Empty/None -> ['*']
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
            return [str(x).strip() for x in parsed if str(x).strip()]
    except Exception:
        # Fallback: CSV
        parts = [p.strip() for p in s.split(",") if p.strip()]
        if parts:
            return parts
    return ["*"]

class Settings(BaseSettings):
    # General
    APP_NAME: str = "KI-Status-Report Backend"
    APP_VERSION: str = os.getenv("APP_VERSION", "2025.10")
    ENV: str = os.getenv("ENV", "production")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # CORS (RAW is read from env to avoid JSON decode issues in pydantic-settings)
    CORS_ALLOW_ORIGINS_RAW: Optional[str] = Field(default=None, description="JSON list or CSV or '*'")
    CORS_ALLOW_CREDENTIALS: bool = False
    CORS_ALLOW_METHODS: list[str] = ["*"]
    CORS_ALLOW_HEADERS: list[str] = ["*"]

    # Features
    QUEUE_ENABLED: bool = False
    PDF_SERVICE_URL: Optional[str] = None
    PDF_SERVICE_ENABLED: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @computed_field(return_type=list[str])  # type: ignore[call-arg]
    @property
    def CORS_ALLOW_ORIGINS(self) -> list[str]:
        return _parse_origins(self.CORS_ALLOW_ORIGINS_RAW or os.getenv("CORS_ALLOW_ORIGINS"))

# Singleton-like export used by the app
settings = Settings()

# Backwards-compat variable used in older main.py imports
allowed_origins = settings.CORS_ALLOW_ORIGINS