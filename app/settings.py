from __future__ import annotations

import os
from typing import List, Optional
from pydantic import BaseModel
from pydantic_settings import BaseSettings

def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    # allow both comma and whitespace separated
    parts = [p.strip() for p in value.replace("\n", ",").replace(" ", ",").split(",")]
    return [p for p in parts if p]

class Settings(BaseSettings):
    # App meta
    APP_NAME: str = "KI-Status-Report Backend"
    ENV: str = os.getenv("ENV", "production")
    VERSION: str = os.getenv("VERSION", "2025.10")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Networking / CORS
    CORS_ALLOW_ORIGINS: list[str] = _split_csv(os.getenv("CORS_ALLOW_ORIGINS"))
    CORS_ALLOW_HEADERS: list[str] = _split_csv(os.getenv("CORS_ALLOW_HEADERS", "Authorization,Content-Type"))
    CORS_ALLOW_METHODS: list[str] = _split_csv(os.getenv("CORS_ALLOW_METHODS", "GET,POST,PUT,PATCH,DELETE,OPTIONS"))

    # Auth / Admin
    ADMIN_TOKEN: Optional[str] = os.getenv("ADMIN_TOKEN")
    BASIC_AUTH_USER: Optional[str] = os.getenv("BASIC_AUTH_USER")
    BASIC_AUTH_PASSWORD: Optional[str] = os.getenv("BASIC_AUTH_PASSWORD")
    AUTH_MODE: str = os.getenv("AUTH_MODE", "env")  # "env" | "db" | "demo"
    JWT_SECRET: str = os.getenv("JWT_SECRET") or os.getenv("ADMIN_TOKEN", "change-me")
    JWT_ALG: str = os.getenv("JWT_ALG", "HS256")
    JWT_EXPIRE_SECONDS: int = int(os.getenv("JWT_EXPIRE_SECONDS", "3600"))
    DEMO_LOGIN_EMAILS: list[str] = _split_csv(os.getenv("DEMO_LOGIN_EMAILS"))

    # Storage / Queue
    DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL")
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL")
    QUEUE_ENABLED: bool = os.getenv("QUEUE_ENABLED", "false").lower() == "true"

    # External Services
    PDF_SERVICE_URL: Optional[str] = os.getenv("PDF_SERVICE_URL")
    PDF_TIMEOUT: int = int(os.getenv("PDF_TIMEOUT", "45000"))

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    class Config:
        case_sensitive = False

settings = Settings()

def allowed_origins() -> list[str]:
    return settings.CORS_ALLOW_ORIGINS
