from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    jobs: Mapped[list[CronJob]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class AuthSession(Base):
    __tablename__ = "sessions"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CronJob(Base):
    __tablename__ = "cron_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    message: Mapped[str] = mapped_column(Text, default="")
    cron_expr: Mapped[str] = mapped_column(String(50), default="")  # legacy cron (optional)
    interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)  # repeat interval in minutes
    send_once_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # one-shot reminder (UTC naive)
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Tehran")
    email_to: Mapped[str | None] = mapped_column(String(120), nullable=True)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship(back_populates="jobs")
    logs: Mapped[list[JobLog]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class JobLog(Base):
    __tablename__ = "job_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("cron_jobs.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[str] = mapped_column(String(20))  # email | telegram
    status: Mapped[str] = mapped_column(String(20))  # success | failed | skipped
    detail: Mapped[str] = mapped_column(Text, default="")
    executed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job: Mapped[CronJob] = relationship(back_populates="logs")
