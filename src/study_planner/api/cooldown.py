"""Global free-tier LLM cooldown flag (shared across the api + worker processes).

When the operator's shared free-tier quota hits a DAILY cap, backoff can't recover
(the window is hours away), so we pause plan generation for everyone for a while and
show a friendly "come back later" message instead of failing jobs one by one.

The flag lives in Redis when JOB_MODE=rq (api and worker are separate processes, so
they need a shared channel). In eager/test mode — or if Redis is unreachable — it
falls back to an in-process timestamp, which is correct there because the api and
worker are the same process. Never raises: a cooldown-check failure must not break
the request path.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from study_planner.api.config import settings

_COOLDOWN_KEY = "llm:cooldown_until"
_local_until: float = 0.0  # in-process fallback (eager/test, or Redis down)


def _redis():
    """A Redis client when running with rq, else None (use the in-process flag)."""
    if settings.job_mode != "rq":
        return None
    try:
        import redis
        return redis.from_url(settings.redis_url)
    except Exception:
        return None


def set_cooldown(seconds: int) -> None:
    """Pause plan generation for `seconds` (clamped to >= 0)."""
    global _local_until
    seconds = max(0, int(seconds))
    _local_until = time.time() + seconds
    r = _redis()
    if r is not None:
        try:
            r.set(_COOLDOWN_KEY, str(_local_until), ex=max(1, seconds))
        except Exception:
            pass  # in-process fallback already set


def cooldown_remaining() -> int:
    """Seconds until plan generation resumes; 0 when not in cooldown."""
    r = _redis()
    if r is not None:
        try:
            v = r.get(_COOLDOWN_KEY)
            if v:
                rem = float(v) - time.time()
                return int(rem) if rem > 0 else 0
        except Exception:
            pass
    rem = _local_until - time.time()
    return int(rem) if rem > 0 else 0


def retry_at() -> datetime | None:
    """Absolute UTC time generation resumes, or None when not in cooldown."""
    rem = cooldown_remaining()
    return datetime.now(timezone.utc) + timedelta(seconds=rem) if rem > 0 else None


def clear_cooldown() -> None:
    """Lift the cooldown (used by tests and an admin reset)."""
    global _local_until
    _local_until = 0.0
    r = _redis()
    if r is not None:
        try:
            r.delete(_COOLDOWN_KEY)
        except Exception:
            pass
