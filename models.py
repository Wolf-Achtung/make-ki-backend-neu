# filename: models.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from sqlalchemy import String, Text, DateTime, func, JSON, Integer
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped

class Base(DeclarativeBase):
    pass

class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # report_id (UUID or job id)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    company: Mapped[str] = mapped_column(String(256))
    email: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    lang: Mapped[str] = mapped_column(String(2), default="DE")
    answers_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    html: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)

class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(256), index=True)
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
