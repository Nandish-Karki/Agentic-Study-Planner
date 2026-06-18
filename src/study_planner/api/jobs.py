"""Async plan job pipeline (BUILD_PLAN §4 — the multi-user agent runtime).

A plan request becomes a PlanJob row, then runs either:
  * eager  — inline (dev/test, JOB_MODE=eager), or
  * rq     — pushed to Redis and executed by a separate worker process (prod).

Either way the same `run_plan_job` does the work: mark running → run the 5-agent
crew on the ephemeral temp workspace → persist the Plan → mark succeeded/failed →
always delete the temp dir. Per-job failure isolation: one bad upload fails only
its own job. The worker carries the enqueuing user's id and asserts it on write
(the playbook's "wrong-profile worker" leak vector).

Concurrency control in prod is the RQ worker count; per-LLM-call rate limiting is
handled by the litellm retry/backoff patch (llm_config). Per-user volume is capped
by quota.py at enqueue time.
"""
from __future__ import annotations

import asyncio
import os
import shutil
from datetime import datetime, timezone

from sqlalchemy import select

from study_planner.api.config import settings
from study_planner.api.db import SessionLocal
from study_planner.api.models import Plan, PlanJob


def _now():
    return datetime.now(timezone.utc)


def _serialize_validation(v) -> dict:
    """ValidationReport → JSON-able dict (None-safe)."""
    if v is None:
        return {}
    return {
        "ok": v.ok,
        "errors": [{"rule": f.rule, "message": f.message} for f in v.errors],
        "warnings": [{"rule": f.rule, "message": f.message} for f in v.warnings],
        "stats": v.stats,
    }


# Indirection so tests can inject a fake planner without LLM calls / API keys.
# progress_cb (optional) receives user-facing phase strings during the run.
def _default_planner(data_dir: str, constraints, progress_cb=None):
    from study_planner.main import plan_studies
    return plan_studies(data_dir, save_report=False, validate=True,
                        constraints=constraints, progress_cb=progress_cb)


planner_fn = _default_planner


async def run_plan_job(job_id: str, data_dir: str, constraints_dict: dict,
                       owner_id: str) -> None:
    """Execute one plan job with its own DB session. Cleans up the temp dir."""
    from study_planner.inputs import PlanConstraints

    async with SessionLocal() as session:
        job = (await session.execute(
            select(PlanJob).where(PlanJob.id == job_id))).scalar_one_or_none()
        if job is None or job.user_id != owner_id:
            # never run for the wrong owner — defense against a poisoned payload
            shutil.rmtree(data_dir, ignore_errors=True)
            return
        job.status = "running"
        job.started_at = _now()
        job.provider = os.getenv("LLM_PROVIDER", "mixed")
        await session.commit()

        try:
            from study_planner.api.progress import set_phase
            constraints = PlanConstraints(**constraints_dict) if constraints_dict else PlanConstraints()
            # crew.kickoff is blocking; run off the event loop so eager mode
            # doesn't stall the server. progress_cb writes the live phase the UI polls.
            result = await asyncio.to_thread(
                planner_fn, data_dir, constraints,
                lambda ph: set_phase(job_id, ph))

            plan = Plan(
                job_id=job.id, user_id=owner_id,
                study_plan_md=result.get("study_plan", ""),
                skill_gaps_md=result.get("skill_gaps", ""),
                module_catalog_md=result.get("module_catalog", ""),
                profile_md=result.get("profile", ""),
                validation_json=_serialize_validation(result.get("validation")),
            )
            session.add(plan)
            job.status = "succeeded"
            job.finished_at = _now()
            await session.commit()
        except Exception as e:  # per-job isolation — surface, never swallow
            from study_planner.llm_config import is_daily_quota_error
            await session.rollback()
            job = (await session.execute(
                select(PlanJob).where(PlanJob.id == job_id))).scalar_one()
            job.status = "failed"
            job.finished_at = _now()
            if is_daily_quota_error(str(e)):
                # OUR shared free tier is spent. Pause generation for everyone and
                # tell the user to come back later (quota.py won't charge this job).
                from datetime import timedelta
                from study_planner.api.cooldown import set_cooldown
                cooldown_s = settings.quota_cooldown_hours * 3600
                set_cooldown(cooldown_s)
                job.failure_reason = "quota_exhausted"
                job.retry_at = _now() + timedelta(seconds=cooldown_s)
                job.error = "Our free-tier AI quota is used up right now."
            else:
                job.error = str(e)[:1000]
            await session.commit()
        finally:
            from study_planner.api.progress import clear_phase
            clear_phase(job_id)  # phase only meaningful while running
            shutil.rmtree(data_dir, ignore_errors=True)  # ephemeral: always delete


def run_plan_job_sync(job_id: str, data_dir: str, constraints_dict: dict,
                      owner_id: str) -> None:
    """RQ entry point — RQ runs sync callables; bridge to the async worker."""
    asyncio.run(run_plan_job(job_id, data_dir, constraints_dict, owner_id))


async def enqueue(job_id: str, data_dir: str, constraints_dict: dict,
                  owner_id: str) -> None:
    """Dispatch a job per JOB_MODE. Eager awaits it; rq pushes to Redis."""
    if settings.job_mode == "rq":
        import redis
        from rq import Queue
        q = Queue("plans", connection=redis.from_url(settings.redis_url))
        q.enqueue(run_plan_job_sync, job_id, data_dir, constraints_dict, owner_id,
                  job_timeout=600)
    else:
        await run_plan_job(job_id, data_dir, constraints_dict, owner_id)
