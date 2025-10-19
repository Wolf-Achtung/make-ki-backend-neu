#!/usr/bin/env python3
"""
Robust settings for KI-Status-Report (pydantic-settings v2)
- Tolerant gegenüber leeren/ungültigen JSON-Werten in CORS_ALLOW_ORIGINS
- Akzeptiert CSV, JSON-Array oder '*' als Wildcard
- Exportiert `settings` (Instanz) und `allowed_origins` (Liste) als Kompatibilität
"""
from __future__ import annotations

import json
import os
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    PROJECT_NAME: str = Field(default="ki-backend")
    ENV: str = Field(default=os.getenv("ENV", "prod"))
    DEBUG: bool = Field(default=(os.getenv("DEBUG", "0") or "0").lower() in {"1","true","yes","on"})
    APP_VERSION: str = Field(default=os.getenv("APP_VERSION", "2025.10"))

    # Security / Auth
    JWT_SECRET: str = Field(default=os.getenv("JWT_SECRET", "change-me"))
    JWT_ALGORITHM: str = Field(default=os.getenv("JWT_ALGORITHM", "HS256"))
    ADMIN_API_KEY: Optional[str] = Field(default=os.getenv("ADMIN_API_KEY"))

    # Connectivity
    REDIS_URL: Optional[str] = Field(default=os.getenv("REDIS_URL"))
    DATABASE_URL: Optional[str] = Field(default=os.getenv("DATABASE_URL"))
    PDF_SERVICE_URL: Optional[str] = Field(default=os.getenv("PDF_SERVICE_URL"))

    # CORS
    CORS_ALLOW_ORIGINS: List[str] = Field(default_factory=lambda: ["*"])

    @field_validator("CORS_ALLOW_ORIGINS", mode="before")
    @classmethod
    def _parse_cors(cls, v):
        # Already a Python list
        if isinstance(v, list):
            return v or ["*"]
        # None or empty --> default "*"
        if v is None:
            return ["*"]
        s = str(v).strip()
        if not s:
            return ["*"]
        if s == "*":
            return ["*"]
        # JSON array?
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
                return parsed or ["*"]
        except Exception:
            pass
        # CSV fallback
        return [p.strip() for p in s.split(",") if p.strip()] or ["*"]

settings = Settings()
allowed_origins: List[str] = settings.CORS_ALLOW_ORIGINS