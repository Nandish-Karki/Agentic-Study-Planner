"""Async SQLAlchemy engine + session (BUILD_PLAN §3).

SQLite (default) for dev/test, Postgres (DATABASE_URL=postgresql+asyncpg://…) in
prod. `init_db` creates tables for SQLite/dev; real Postgres deployments use
Alembic migrations (additive — the playbook's idempotent-persistence rule).
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from study_planner.api.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    """Create all tables (dev/test convenience; prod uses migrations)."""
    from study_planner.api import models  # noqa: F401 — register mappers
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a session, committed/rolled-back per request."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
