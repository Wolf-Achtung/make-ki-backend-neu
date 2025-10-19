# -*- coding: utf-8 -*-
"""
Settings / Configuration for KI-Status-Report Backend (Gold-Standard+)
- Pydantic v2 settings with safe defaults
- All secrets via environment variables
- Avoid EmailStr here to not hard require email-validator on import (we include it anyway)
"""
from __future__ import annotations

import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

def _csv(val: str) -> List[str]:
    if not val:
        return []
    return [x.strip() for x in val.split(",") if x.strip()]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: str = Field(default="production")
    LOG_LEVEL: str = Field(default="INFO")

    APP_NAME: str = Field(default="KI-Status-Report Backend")
    DEFAULT_LANG: str = Field(default="DE")

    # CORS
    FRONTEND_ORIGINS: str = Field(default="")
    CORS_ALLOW_ORIGINS: List[str] = Field(default_factory=list)

    # Database
    DATABASE_URL: str = Field(default="")

    # JWT
    JWT_SECRET: str = Field(default="dev-secret")

    # PDF Service
    PDF_SERVICE_URL: str = Field(default="")
    PDF_TIMEOUT: int = Field(default=25000, description="Timeout in ms")

    # SMTP
    SMTP_HOST: str = Field(default="localhost")
    SMTP_PORT: int = Field(default=587)
    SMTP_USER: str = Field(default="")
    SMTP_PASS: str = Field(default="")
    SMTP_FROM: str = Field(default="noreply@example.com")
    SMTP_FROM_NAME: str = Field(default="KI‑Sicherheit")

    # Admin / Mails
    ADMIN_EMAIL: str = Field(default="")
    SEND_USER_MAIL: bool = Field(default=True)
    SEND_ADMIN_MAIL: bool = Field(default=True)
    ATTACH_HTML_FALLBACK: bool = Field(default=True)

    # Rate limiting
    API_RATE_LIMIT_PER_HOUR: int = Field(default=20)
    API_RATE_LIMIT_WINDOW_SECONDS: int = Field(default=3600)

    # Feature flags
    ENABLE_EU_HOST_CHECK: bool = Field(default=True)
    ENABLE_IDEMPOTENCY: bool = Field(default=True)
    QUALITY_CONTROL_AVAILABLE: bool = Field(default=True)

def allowed_origins() -> List[str]:
    s = os.getenv("FRONTEND_ORIGINS", "") or settings.FRONTEND_ORIGINS
    parsed = _csv(s)
    # Add local dev defaults if not present
    defaults = {"http://localhost:3000", "http://127.0.0.1:5500", "http://localhost:8000"}
    return list(set(parsed) | defaults)

settings = Settings()
