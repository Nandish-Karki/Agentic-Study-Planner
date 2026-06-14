"""Account routes (BUILD_PLAN §5.3) — including full GDPR erasure.

Deleting the account purges every owned row: plans, jobs, profile, consents,
events, audit records. Uploaded documents are already ephemeral (never stored),
so erasure is complete by construction.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from study_planner.api.db import get_session
from study_planner.api.deps import client_ip, get_current_user
from study_planner.api.models import (AuditLog, Consent, Event, Plan, PlanJob,
                                       Profile, User)

router = APIRouter(prefix="/me", tags=["account"])


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(request: Request,
                         user: User = Depends(get_current_user),
                         session: AsyncSession = Depends(get_session)):
    uid = user.id
    # Explicit per-table purge (don't rely solely on cascade) so erasure is
    # provable by query — the playbook's "erasure proof" gate.
    await session.execute(delete(Plan).where(Plan.user_id == uid))
    await session.execute(delete(PlanJob).where(PlanJob.user_id == uid))
    await session.execute(delete(Consent).where(Consent.user_id == uid))
    await session.execute(delete(Profile).where(Profile.user_id == uid))
    await session.execute(delete(Event).where(Event.user_id == uid))
    await session.execute(delete(AuditLog).where(AuditLog.user_id == uid))
    await session.execute(delete(User).where(User.id == uid))
    await session.commit()
