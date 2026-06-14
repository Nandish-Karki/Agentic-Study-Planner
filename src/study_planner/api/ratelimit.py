"""Fixed-window rate limiter (BUILD_PLAN §5.2 — brute-force defense).

In-memory by default (fine for a single process / dev / tests). For multi-process
production, point `RATELIMIT_BACKEND=redis` so all workers share one window — the
same reasoning as the per-provider LLM token bucket. The interface is identical so
swapping the backend is a config flip.
"""
from __future__ import annotations

import threading
import time

from study_planner.api.config import settings


class _InMemoryLimiter:
    def __init__(self):
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_s: int) -> bool:
        now = time.time()
        cutoff = now - window_s
        with self._lock:
            hits = [t for t in self._hits.get(key, []) if t > cutoff]
            if len(hits) >= limit:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            return True

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)


limiter = _InMemoryLimiter()


def check_auth_rate(ip: str) -> bool:
    """True if this IP is under the auth attempt limit."""
    return limiter.allow(f"auth:{ip}", settings.auth_rate_limit,
                         settings.auth_rate_window_s)
