# -*- coding: utf-8 -*-
from __future__ import annotations
from datetime import datetime
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, JSON

Base = declarative_base()

class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, default="queued", index=True)
    company: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    lang: Mapped[str] = mapped_column(String, default="DE")
    answers_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    html: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    message: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
