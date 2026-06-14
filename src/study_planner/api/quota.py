"""Per-user plan quota (BUILD_PLAN §4.2 — cost control).

The free tier is a direct cost center: every plan is real inference spend. Cap
plans per rolling 24h per user so one account can't run up the bill.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from study_planner.api.config import settings
from study_planner.api.models import PlanJob


async def plans_today(session: AsyncSession, user_id: str) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    result = await session.execute(
        select(func.count()).select_from(PlanJob)
        .where(PlanJob.user_id == user_id, PlanJob.created_at >= cutoff))
    return int(result.scalar_one())


async def within_quota(session: AsyncSession, user_id: str) -> bool:
    return await plans_today(session, user_id) < settings.max_plans_per_day
