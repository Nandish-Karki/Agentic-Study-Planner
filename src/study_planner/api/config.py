"""Runtime settings, resolved from environment once (BUILD_PLAN §3).

Secrets come from env only — never the repo. SECRET_KEY must be set in any real
deployment; the dev default is obviously fake and refused if DEBUG is off.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # Auth
    secret_key: str
    access_token_ttl_min: int
    # DB — async SQLAlchemy URL. Default SQLite for dev/test; Postgres in prod, e.g.
    # postgresql+asyncpg://user:pass@host/db  (EU region for GDPR residency).
    database_url: str
    # Jobs — "eager" runs the crew inline (dev/test); "rq" uses Redis + a worker.
    job_mode: str
    redis_url: str
    # Per-user guardrails (cost control — the free tier is a direct cost center)
    max_plans_per_day: int
    # Auth brute-force limit (attempts per window per IP)
    auth_rate_limit: int
    auth_rate_window_s: int
    debug: bool

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


def load_settings() -> Settings:
    debug = os.getenv("DEBUG", "1") == "1"
    secret = os.getenv("SECRET_KEY", "")
    if not secret:
        if not debug:
            raise RuntimeError("SECRET_KEY must be set when DEBUG is off")
        secret = "dev-insecure-secret-do-not-use-in-prod"
    return Settings(
        secret_key=secret,
        access_token_ttl_min=int(os.getenv("ACCESS_TOKEN_TTL_MIN", "60")),
        database_url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./study_planner.db"),
        job_mode=os.getenv("JOB_MODE", "eager").lower(),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        max_plans_per_day=int(os.getenv("MAX_PLANS_PER_DAY", "5")),
        auth_rate_limit=int(os.getenv("AUTH_RATE_LIMIT", "10")),
        auth_rate_window_s=int(os.getenv("AUTH_RATE_WINDOW_S", "300")),
        debug=debug,
    )


settings = load_settings()
