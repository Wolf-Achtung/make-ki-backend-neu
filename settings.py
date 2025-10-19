# settings.py (v3 – preferences applied)
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
from typing import Optional, List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Production whitelist default (7B)
PRODUCTION_DEFAULT_ORIGINS: list[str] = [
    "https://ki-sicherheit.jetzt",
    "https://www.ki-sicherheit.jetzt",
    "https://make.ki-sicherheit.jetzt",
    "https://www.make.ki-sicherheit.jetzt",
    "https://ki-foerderung.jetzt",
    "https://www.ki-foerderung.jetzt",
]

def _parse_origins(raw: Optional[str]) -> list[str]:
    if raw is None:
        return []
    raw = raw.strip()
    if not raw:
        return []
    if raw == "*":
        return ["*"]
    if raw.startswith("[") and raw.endswith("]"):
        try:
            data = json.loads(raw)
            return [str(x).strip() for x in data if str(x).strip()]
        except Exception:
            pass
    if "," in raw:
        return [x.strip() for x in raw.split(",") if x.strip()]
    return [raw]

class Settings(BaseSettings):
    # Meta
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    APP_NAME: str = Field(default=os.getenv("APP_NAME", "KI‑Status‑Report Backend"))
    ENV: str = Field(default=os.getenv("ENV", "production"))
    VERSION: str = Field(default=os.getenv("APP_VERSION", "2025.10"))

    # Logging (8A text logs – no JSON)
    LOG_LEVEL: str = Field(default=os.getenv("LOG_LEVEL", "INFO"))

    # CORS (7B: prod whitelist default; '*' only if explicitly set or in non-prod with no value)
    CORS_ALLOW_ORIGINS_RAW: Optional[str] = Field(default=os.getenv("CORS_ALLOW_ORIGINS_RAW"))
    CORS_ALLOW_CREDENTIALS: bool = Field(default=True)
    CORS_ALLOW_METHODS: list[str] = Field(default_factory=lambda: ["*"])
    CORS_ALLOW_HEADERS: list[str] = Field(default_factory=lambda: ["*"])

    # Security / Auth (2B: JWT-only admin)
    JWT_SECRET: Optional[str] = Field(default=os.getenv("JWT_SECRET"))
    # ADMIN_API_KEY intentionally ignored in v3

    # Database
    DATABASE_URL: Optional[str] = Field(default=os.getenv("DATABASE_URL"))

    # Queue / Redis (3B: keep local, disabled by default)
    QUEUE_ENABLED: bool = Field(default=os.getenv("QUEUE_ENABLED", "false").lower() == "true")
    REDIS_URL: Optional[str] = Field(default=os.getenv("REDIS_URL"))

    # PDF Service (4A: keep current with timeout + fallback)
    PDF_SERVICE_URL: Optional[str] = Field(default=os.getenv("PDF_SERVICE_URL"))
    PDF_SERVICE_ENABLED: bool = Field(default=os.getenv("PDF_SERVICE_ENABLED", "true").lower() == "true")
    PDF_TIMEOUT: int = Field(default=int(os.getenv("PDF_TIMEOUT", "15000")))  # ms

    # Mail (5A: always send by default – if SMTP config present)
    SEND_USER_MAIL: bool = Field(default=os.getenv("SEND_USER_MAIL", "true").lower() == "true")
    SEND_ADMIN_MAIL: bool = Field(default=os.getenv("SEND_ADMIN_MAIL", "true").lower() == "true")
    ADMIN_EMAIL: Optional[str] = Field(default=os.getenv("ADMIN_EMAIL"))
    SMTP_HOST: Optional[str] = Field(default=os.getenv("SMTP_HOST"))
    SMTP_PORT: int = Field(default=int(os.getenv("SMTP_PORT", "587")))
    SMTP_USER: Optional[str] = Field(default=os.getenv("SMTP_USER"))
    SMTP_PASSWORD: Optional[str] = Field(default=os.getenv("SMTP_PASSWORD"))
    SMTP_TLS: bool = Field(default=os.getenv("SMTP_TLS", "true").lower() == "true")
    SMTP_SSL: bool = Field(default=os.getenv("SMTP_SSL", "false").lower() == "true")

    # Misc
    DEBUG: bool = Field(default=os.getenv("DEBUG", "false").lower() == "true")

settings = Settings()

# Compute allowed origins per ENV (7B)
parsed = _parse_origins(settings.CORS_ALLOW_ORIGINS_RAW)
if parsed:
    allowed_origins: List[str] = parsed
else:
    if settings.ENV.lower() == "production":
        allowed_origins = PRODUCTION_DEFAULT_ORIGINS[:]  # strict default
    else:
        allowed_origins = ["*"]  # dev convenience
