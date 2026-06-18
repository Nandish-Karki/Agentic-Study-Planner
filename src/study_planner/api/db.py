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


# Additive columns introduced after the first release. create_all only creates
# MISSING tables, never new columns on an existing one, so on a Postgres that
# already has these tables we add them idempotently here (a stopgap until Alembic).
# SQLite/test DBs are created fresh by create_all, so they skip this.
_ADDITIVE_COLUMNS = {
    "plan_jobs": [
        ("failure_reason", "VARCHAR(40)"),
        ("retry_at", "TIMESTAMP WITH TIME ZONE"),
    ],
}


async def init_db() -> None:
    """Create all tables (dev/test convenience; prod uses migrations)."""
    from sqlalchemy import text
    from study_planner.api import models  # noqa: F401 — register mappers
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if not settings.is_sqlite:
            # Postgres supports ADD COLUMN IF NOT EXISTS — safe to run every boot.
            for table, cols in _ADDITIVE_COLUMNS.items():
                for name, ddl in cols:
                    await conn.execute(text(
                        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {ddl}"))


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a session, committed/rolled-back per request."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
