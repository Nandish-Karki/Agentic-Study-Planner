"""Live job phase tracking, so the UI can show real progress during the
multi-minute crew run (queued -> reading -> planning -> validating) instead of an
opaque "working..." spinner.

Like cooldown.py, the phase lives in Redis when JOB_MODE=rq (api and worker are
separate processes) and in an in-process dict otherwise (eager/test). Never raises:
a progress write must not break the job.
"""
from __future__ import annotations

from study_planner.api.config import settings

_KEY = "job:phase:{}"
_PHASE_TTL_S = 1800  # phases are only meaningful while a job runs
_local: dict[str, str] = {}  # in-process fallback (eager/test, or Redis down)


def _redis():
    if settings.job_mode != "rq":
        return None
    try:
        import redis
        return redis.from_url(settings.redis_url)
    except Exception:
        return None


def set_phase(job_id: str, phase: str) -> None:
    _local[job_id] = phase
    r = _redis()
    if r is not None:
        try:
            r.set(_KEY.format(job_id), phase, ex=_PHASE_TTL_S)
        except Exception:
            pass


def get_phase(job_id: str) -> str | None:
    r = _redis()
    if r is not None:
        try:
            v = r.get(_KEY.format(job_id))
            if v is not None:
                return v.decode() if isinstance(v, bytes) else str(v)
        except Exception:
            pass
    return _local.get(job_id)


def clear_phase(job_id: str) -> None:
    _local.pop(job_id, None)
    r = _redis()
    if r is not None:
        try:
            r.delete(_KEY.format(job_id))
        except Exception:
            pass
