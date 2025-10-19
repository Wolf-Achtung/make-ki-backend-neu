from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field

class LoginRequest(BaseModel):
    email: EmailStr = Field(..., description="E-Mail des Users (Einladung)")
    password: str = Field(..., min_length=1, description="Passwort aus Einladung")

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

class HealthResponse(BaseModel):
    ok: bool = True
    env: str
    version: str
    queue_enabled: bool
    pdf_service: bool
    status: str = "ok"
