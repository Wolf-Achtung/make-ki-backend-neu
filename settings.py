# filename: settings.py
# -*- coding: utf-8 -*-
"""
Central configuration for KI-Status-Report (Gold-Standard+)
- pydantic-settings for robust ENV parsing
- CORS_ALLOW_ORIGINS kept as CSV string to avoid JSON parsing issues in Pydantic
- Helper to expose parsed origins as list
"""
from __future__ import annotations

from typing import List, Optional
from pydantic import Field, AnyHttpUrl, EmailStr
from pydantic_settings import BaseSettings, SettingsConfigDict

def _parse_csv(value: str) -> List[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # --- Core ---
    ENVIRONMENT: str = "production"
    PORT: int = 8080
    LOG_LEVEL: str = "info"

    # --- CORS / Security ---
    # Keep as CSV string (not List[str]) to avoid JSON decoding expectation in env provider
    CORS_ALLOW_ORIGINS: str = ("https://ki-sicherheit.jetzt,https://www.ki-sicherheit.jetzt,"
                               "https://ki-foerderung.jetzt,https://make.ki-sicherheit.jetzt,"
                               "https://www.make.ki-sicherheit.jetzt")
    JWT_SECRET: str = "dev-secret"
    SECRET_KEY: str = "dev-secret"

    # --- Database ---
    DATABASE_URL: Optional[str] = None

    # --- Redis / Queue ---
    REDIS_URL: Optional[str] = None
    QUEUE_NAME: str = "reports"

    # --- Rate limit ---
    API_RATE_LIMIT_PER_HOUR: int = 20
    API_RATE_LIMIT_WINDOW_SECONDS: int = 3600

    # --- Mail ---
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 25
    SMTP_USER: Optional[str] = None
    SMTP_PASS: Optional[str] = None
    SMTP_FROM: EmailStr = "kontakt@ki-sicherheit.jetzt"
    SMTP_FROM_NAME: str = "KI-Sicherheit"
    ADMIN_EMAIL: EmailStr = "bewertung@ki-sicherheit.jetzt"
    FEEDBACK_TO: EmailStr = "kontakt@ki-sicherheit.jetzt"
    MAIL_SUBJECT_PREFIX: str = "KI-Ready"
    MAIL_THROTTLE_PER_USER_PER_HOUR: int = 10
    MAIL_TO_USER: bool = True

    # --- LLM ---
    LLM_MODE: str = "on"
    LLM_PROVIDER: str = "anthropic"  # or openai
    ANTHROPIC_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    CLAUDE_MODEL: str = "claude-sonnet-4-20250514"
    GPT_MODEL_NAME: str = "gpt-4o"
    OPENAI_MODEL_DEFAULT: str = "gpt-4o"
    OPENAI_FALLBACK_MODEL: str = "gpt-4o-mini"
    OPENAI_MAX_TOKENS: int = 1200
    OPENAI_TIMEOUT: int = 45
    EXEC_SUMMARY_MODEL: str = "gpt-4o"
    EXEC_SUMMARY_MODEL_FALLBACK: str = "gpt-4o"

    # --- PDF Service ---
    PDF_SERVICE_URL: Optional[AnyHttpUrl] = None
    PDF_TIMEOUT: int = 45000
    PDF_POST_MODE: str = "json"
    PDF_MAX_BYTES: int = 32 * 1024 * 1024
    PDF_MINIFY_HTML: bool = True
    PDF_STRIP_SCRIPTS: bool = True
    TEMPLATE_DIR: str = "templates"
    TEMPLATE_DE: str = "pdf_template.html"
    TEMPLATE_EN: str = "pdf_template_en.html"
    ASSETS_BASE_URL: str = "templates"

    # --- Feature Flags ---
    ENABLE_IDEMPOTENCY: bool = True
    ENABLE_EU_HOST_CHECK: bool = True
    EU_THROTTLE_RPM: int = 24
    EU_CACHE_TTL: int = 1200
    LIVE_CACHE_ENABLED: bool = True
    LIVE_CACHE_FILE: str = "/tmp/ki_live_cache.json"
    LIVE_CACHE_TTL_SECONDS: int = 1800
    LIVE_TIMEOUT_S: float = 8.0
    HYBRID_LIVE: bool = True
    QUALITY_CONTROL_AVAILABLE: bool = True
    MIGRATION_ENABLED: bool = False

    # --- Misc ---
    DEFAULT_LANG: str = "DE"
    DEFAULT_TIMEZONE: str = "Europe/Berlin"
    RAILWAY_HEALTHCHECK_DISABLED: bool = True

    # Helpers
    def allowed_origins(self) -> List[str]:
        return _parse_csv(self.CORS_ALLOW_ORIGINS)

settings = Settings()

def is_dev() -> bool:
    return settings.ENVIRONMENT.lower() in {"dev","development","local"}

def allowed_origins() -> List[str]:
    return ["*"] if is_dev() else settings.allowed_origins()
