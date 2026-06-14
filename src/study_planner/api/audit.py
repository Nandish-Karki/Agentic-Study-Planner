"""Audit + event logging helpers (BUILD_PLAN §5.2).

audit_log records security-relevant actions (generate / view / delete / erase);
log_event records funnel/usage analytics. Both scope to user_id and never store
document contents or plan text.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from study_planner.api.models import AuditLog, Event


async def audit(session: AsyncSession, *, user_id: str | None, action: str,
                target_type: str | None = None, target_id: str | None = None,
                ip: str | None = None) -> None:
    session.add(AuditLog(user_id=user_id, action=action, target_type=target_type,
                         target_id=target_id, ip=ip))


async def log_event(session: AsyncSession, *, user_id: str | None, event: str,
                    **props) -> None:
    session.add(Event(user_id=user_id, event=event, props_json=props))
