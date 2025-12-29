"""
web_db.py

Database models and utilities for the web UI.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from src.env import DATABASE_URL


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


class GuildConfig(Base):
    """Configuration for a Discord guild."""

    __tablename__ = "guild_config"

    guild_id: Mapped[str] = mapped_column(String(22), primary_key=True)
    timezone: Mapped[str] = mapped_column(String(100), default="UTC")
    role_id: Mapped[Optional[str]] = mapped_column(String(22), nullable=True)
    default_channel_id: Mapped[Optional[str]] = mapped_column(String(22), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    templates: Mapped[list["Template"]] = relationship("Template", back_populates="guild", cascade="all, delete-orphan")
    schedules: Mapped[list["Schedule"]] = relationship(
        "Schedule", back_populates="guild", cascade="all, delete-orphan"
    )


class Template(Base):
    """Message template for a guild."""

    __tablename__ = "template"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[str] = mapped_column(String(22), ForeignKey("guild_config.guild_id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    guild: Mapped["GuildConfig"] = relationship("GuildConfig", back_populates="templates")
    schedules: Mapped[list["Schedule"]] = relationship("Schedule", back_populates="template")


class Schedule(Base):
    """Weekly recurring schedule for territory defense reminders."""

    __tablename__ = "schedule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[str] = mapped_column(String(22), ForeignKey("guild_config.guild_id"), nullable=False)
    template_id: Mapped[int] = mapped_column(Integer, ForeignKey("template.id"), nullable=False)
    system_name: Mapped[str] = mapped_column(String(200), nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Monday, 6=Sunday
    time_local: Mapped[str] = mapped_column(String(5), nullable=False)  # HH:MM format
    timezone: Mapped[str] = mapped_column(String(100), nullable=False)
    channel_id: Mapped[Optional[str]] = mapped_column(String(22), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_user_id: Mapped[str] = mapped_column(String(22), nullable=False)
    next_run_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    advance_minutes: Mapped[int] = mapped_column(Integer, default=0)  # Minutes to send before scheduled time

    # Relationships
    guild: Mapped["GuildConfig"] = relationship("GuildConfig", back_populates="schedules")
    template: Mapped["Template"] = relationship("Template", back_populates="schedules")


# Database engine and session management
def get_engine(database_url: str | None = None):
    """Get the database engine."""
    url = database_url or DATABASE_URL
    # Convert sqlite:/// to sqlite+aiosqlite:/// for async support
    if url.startswith("sqlite:///"):
        url = url.replace("sqlite:///", "sqlite+aiosqlite:///")
    return create_async_engine(url, echo=False)


def get_session_maker(engine):
    """Get a session maker for the database."""
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db(engine):
    """Initialize the database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db_session(session_maker):
    """Get a database session."""
    async with session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
