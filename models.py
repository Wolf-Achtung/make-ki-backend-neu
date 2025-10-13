# filename: backend/models.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Boolean
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(320), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=True)  # nullable to allow invitation-only email check
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
