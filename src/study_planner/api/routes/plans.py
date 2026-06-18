"""Plan routes (BUILD_PLAN §3.3, §4) — owner-scoped, IDOR-safe.

Every fetch resolves ownership from the DB row and returns 404 (not 403) on
mismatch, so existence isn't disclosed. Uploads are ephemeral: written to a temp
dir, passed to the job, deleted by the job after the run.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Request,
                     UploadFile, status)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from study_planner.api.audit import audit
from study_planner.api.config import settings
from study_planner.api.cooldown import cooldown_remaining, retry_at as cooldown_retry_at
from study_planner.api.progress import get_phase
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
    # Live phase is only meaningful while the job is active.
    phase = get_phase(job.id) if job.status in ("queued", "running") else None
    return JobOut(id=job.id, status=job.status, phase=phase, provider=job.provider,
                  error=job.error, failure_reason=job.failure_reason,
                  retry_at=job.retry_at, created_at=job.created_at,
                  finished_at=job.finished_at)


async def _guard_can_create(session: AsyncSession, user: User) -> None:
    """Reject up front (structured 429) when the shared free tier is paused or the
    user hit their daily cap — so the UI shows a popup instead of a doomed job."""
    rem = cooldown_remaining()
    if rem > 0:
        hours = max(1, round(rem / 3600))
        at = cooldown_retry_at()
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail={
            "reason": "quota_exhausted",
            "retry_after_s": rem,
            "retry_at": at.isoformat() if at else None,
            "message": ("Our free-tier AI quota is used up right now. "
                        f"Please come back in about {hours} hour(s)."),
        })
    if not await within_quota(session, user.id):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail={
            "reason": "daily_user_limit",
            "message": ("You've reached your daily plan limit "
                        f"({settings.max_plans_per_day}/day). Try again tomorrow."),
        })


def _new_workspace() -> Path:
    """A temp dir the worker can read. With JOB_MODE=rq it MUST live on the shared
    volume (job_workspace_dir); empty falls back to system temp (eager/test)."""
    workspace = settings.job_workspace_dir or None
    if workspace:
        os.makedirs(workspace, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="sp_job_", dir=workspace))


async def _launch_job(session: AsyncSession, user: User, request: Request,
                      tmp: Path, constraints_in: ConstraintsIn, action: str) -> JobOut:
    job = PlanJob(user_id=user.id, status="queued",
                  constraints_json=constraints_in.model_dump())
    session.add(job)
    await audit(session, user_id=user.id, action=action,
                target_type="job", target_id=job.id, ip=client_ip(request))
    await session.commit()
    # eager: awaits the run; rq: returns immediately with status=queued
    await enqueue(job.id, str(tmp), constraints_in.model_dump(), user.id)
    await session.refresh(job)
    return _job_out(job)


@router.post("", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def create_plan(
    request: Request,
    handbook: UploadFile = File(...),
    career: UploadFile = File(...),
    transcript: UploadFile | None = File(None),
    cv: UploadFile | None = File(None),
    requirements: UploadFile | None = File(None),
    new_student: bool = Form(False),
    constraints: str = Form("{}"),
    user: User = Depends(get_verified_user),
    session: AsyncSession = Depends(get_session),
):
    await _guard_can_create(session, user)
    try:
        constraints_in = ConstraintsIn(**json.loads(constraints or "{}"))
    except (json.JSONDecodeError, ValueError) as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Invalid constraints: {e}")

    tmp = _new_workspace()
    # A brand-new first-semester student has no transcript. We synthesize a blank
    # 0-CP transcript so the rest of the pipeline (profile, completed-CP parsing,
    # validator) runs unchanged and plans the full degree. A continuing student
    # must still provide one.
    if transcript is not None:
        await _save_upload(transcript, tmp / "transcript.pdf")
    elif new_student:
        from study_planner.ingest.blank_transcript import synthesize_blank_transcript
        synthesize_blank_transcript(tmp / "transcript.pdf")
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "A transcript is required unless you are a new student.")
    await _save_upload(handbook, tmp / "module_handbook.pdf")
    await _save_upload(career, tmp / "career.pdf")
    if cv is not None:
        await _save_upload(cv, tmp / "cv.pdf")
    else:
        (tmp / "cv.pdf").write_bytes((tmp / "transcript.pdf").read_bytes())
    # Optional: the programme's study & examination schedule. When present it is
    # the authoritative source of thematic-area CP rules (parsed deterministically,
    # overriding the LLM's guesses). Absent → fall back to handbook extraction.
    if requirements is not None:
        await _save_upload(requirements, tmp / "requirements.pdf")

    return await _launch_job(session, user, request, tmp, constraints_in, "create_plan")


@router.post("/demo", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def create_demo_plan(request: Request,
                           user: User = Depends(get_verified_user),
                           session: AsyncSession = Depends(get_session)):
    """One-click demo on the bundled sample student — so newcomers see a real plan
    without finding/uploading their own PDFs. Same quota/cooldown rules apply
    (it's a real crew run = real inference cost)."""
    await _guard_can_create(session, user)
    src = Path(settings.sample_data_dir)
    required = ["transcript.pdf", "module_handbook.pdf", "career.pdf", "cv.pdf"]
    if not src.exists() or not all((src / f).exists() for f in required):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "The demo dataset isn't available on this server.")
    tmp = _new_workspace()
    for f in required + ["requirements.pdf"]:  # requirements optional in the sample
        if (src / f).exists():
            shutil.copyfile(src / f, tmp / f)
    return await _launch_job(session, user, request, tmp, ConstraintsIn(), "create_demo")


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
            out.profile_md = plan.profile_md
            out.module_catalog_md = plan.module_catalog_md
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
