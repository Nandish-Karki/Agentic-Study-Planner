"""Plan routes (BUILD_PLAN §3.3, §4) — owner-scoped, IDOR-safe.

Every fetch resolves ownership from the DB row and returns 404 (not 403) on
mismatch, so existence isn't disclosed. Uploads are ephemeral: written to a temp
dir, passed to the job, deleted by the job after the run.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Request,
                     UploadFile, status)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from study_planner.api.audit import audit
from study_planner.api.db import get_session
from study_planner.api.deps import client_ip, get_verified_user
from study_planner.api.jobs import enqueue
from study_planner.api.models import Plan, PlanJob, User
from study_planner.api.quota import within_quota
from study_planner.api.schemas import ConstraintsIn, JobOut, PlanOut, ValidationOut

router = APIRouter(prefix="/plans", tags=["plans"])

MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MB per file — untrusted-input cap


async def _save_upload(up: UploadFile, dest: Path) -> None:
    if up.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"{up.filename}: only PDF files are accepted")
    data = await up.read()
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            f"{up.filename}: file exceeds 10 MB")
    dest.write_bytes(data)


def _job_out(job: PlanJob) -> JobOut:
    return JobOut(id=job.id, status=job.status, provider=job.provider,
                  error=job.error, created_at=job.created_at,
                  finished_at=job.finished_at)


@router.post("", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def create_plan(
    request: Request,
    transcript: UploadFile = File(...),
    handbook: UploadFile = File(...),
    career: UploadFile = File(...),
    cv: UploadFile | None = File(None),
    constraints: str = Form("{}"),
    user: User = Depends(get_verified_user),
    session: AsyncSession = Depends(get_session),
):
    if not await within_quota(session, user.id):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Daily plan limit reached. Try again tomorrow.")
    try:
        constraints_in = ConstraintsIn(**json.loads(constraints or "{}"))
    except (json.JSONDecodeError, ValueError) as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Invalid constraints: {e}")

    tmp = Path(tempfile.mkdtemp(prefix="sp_job_"))
    await _save_upload(transcript, tmp / "transcript.pdf")
    await _save_upload(handbook, tmp / "module_handbook.pdf")
    await _save_upload(career, tmp / "career.pdf")
    if cv is not None:
        await _save_upload(cv, tmp / "cv.pdf")
    else:
        (tmp / "cv.pdf").write_bytes((tmp / "transcript.pdf").read_bytes())

    job = PlanJob(user_id=user.id, status="queued",
                  constraints_json=constraints_in.model_dump())
    session.add(job)
    await audit(session, user_id=user.id, action="create_plan",
                target_type="job", target_id=job.id, ip=client_ip(request))
    await session.commit()

    # eager: awaits the run; rq: returns immediately with status=queued
    await enqueue(job.id, str(tmp), constraints_in.model_dump(), user.id)
    await session.refresh(job)
    return _job_out(job)


@router.get("", response_model=list[JobOut])
async def list_plans(user: User = Depends(get_verified_user),
                     session: AsyncSession = Depends(get_session)):
    jobs = (await session.execute(
        select(PlanJob).where(PlanJob.user_id == user.id)
        .order_by(PlanJob.created_at.desc()))).scalars().all()
    return [_job_out(j) for j in jobs]


async def _owned_job(session: AsyncSession, job_id: str, user: User) -> PlanJob:
    """Load a job and assert ownership. 404 (not 403) on miss — no disclosure."""
    job = await session.get(PlanJob, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan not found")
    return job


@router.get("/{job_id}/status", response_model=JobOut)
async def plan_status(job_id: str, user: User = Depends(get_verified_user),
                      session: AsyncSession = Depends(get_session)):
    return _job_out(await _owned_job(session, job_id, user))


@router.get("/{job_id}", response_model=PlanOut)
async def get_plan(job_id: str, request: Request,
                   user: User = Depends(get_verified_user),
                   session: AsyncSession = Depends(get_session)):
    job = await _owned_job(session, job_id, user)
    out = PlanOut(job_id=job.id, status=job.status)
    if job.status == "succeeded":
        plan = (await session.execute(
            select(Plan).where(Plan.job_id == job.id))).scalar_one_or_none()
        if plan is not None:
            v = plan.validation_json or {}
            out.study_plan_md = plan.study_plan_md
            out.skill_gaps_md = plan.skill_gaps_md
            out.created_at = plan.created_at
            out.validation = ValidationOut(
                ok=v.get("ok", True), errors=v.get("errors", []),
                warnings=v.get("warnings", []), stats=v.get("stats", {}))
        await audit(session, user_id=user.id, action="view_plan",
                    target_type="plan", target_id=job.id, ip=client_ip(request))
        await session.commit()
    return out


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan(job_id: str, request: Request,
                      user: User = Depends(get_verified_user),
                      session: AsyncSession = Depends(get_session)):
    job = await _owned_job(session, job_id, user)
    await audit(session, user_id=user.id, action="delete_plan",
                target_type="job", target_id=job.id, ip=client_ip(request))
    await session.delete(job)  # cascade removes the Plan
    await session.commit()
