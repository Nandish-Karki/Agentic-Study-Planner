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
    # Where uploaded PDFs are staged for a job. MUST be a filesystem shared by the
    # API and the worker when JOB_MODE=rq (separate containers have separate /tmp),
    # else the worker can't find the upload. Empty => system temp (eager/test only).
    job_workspace_dir: str
    # Outbound email (verification + password reset). Provider-agnostic SMTP:
    # Mailpit locally (host=mailpit, port=1025, no auth), any real SMTP in prod.
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from: str
    smtp_starttls: bool   # explicit TLS upgrade on a plaintext port (587)
    smtp_ssl: bool        # implicit TLS from connect (465); mutually exclusive w/ starttls
    # Resend HTTP API key. Preferred over SMTP in hosts that block outbound SMTP
    # (e.g. Render's free tier — SMTP ports are unreachable there). When set, mail
    # goes out over HTTPS to api.resend.com instead of an SMTP socket.
    resend_api_key: str
    # Base URL of the frontend, used to build verify/reset links in emails.
    app_base_url: str
    # Bundled sample inputs for the one-click "try the demo" flow (relative to CWD;
    # the Docker image copies sample_data to /app/sample_data).
    sample_data_dir: str
    # Per-user guardrails (cost control — the free tier is a direct cost center)
    max_plans_per_day: int
    # When the operator's shared free-tier LLM quota is exhausted (a daily cap that
    # backoff can't fix), plans are paused for this many hours and users get a
    # "come back later" message instead of a failing job.
    quota_cooldown_hours: int
    # Auth brute-force limit (attempts per window per IP)
    auth_rate_limit: int
    auth_rate_window_s: int
    # Guest "try the demo without signing up" flow. A guest run is a real crew run
    # (real inference cost) by an anonymous visitor, so it is capped per IP/day and
    # shares the global free-tier cooldown. The result is reachable only via a
    # short-lived signed guest token, and guest accounts are purged after retention.
    guest_enabled: bool
    guest_runs_per_day: int       # per IP per rolling 24h
    guest_token_ttl_min: int      # how long the result link stays valid
    guest_retention_hours: int    # purge guest accounts (+ their jobs/plans) older than this
    debug: bool

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def email_enabled(self) -> bool:
        """True when an email transport is configured (Resend HTTP API or SMTP).
        When False the email sender is a logged no-op, so signup still succeeds
        (link goes to logs / DEBUG)."""
        return bool(self.resend_api_key or self.smtp_host)


def _normalize_db_url(url: str) -> str:
    """Coerce a plain Postgres URL to the async driver the app needs.

    Managed hosts (Render, Heroku, Railway) hand out `postgres://` or
    `postgresql://`; SQLAlchemy-async needs `postgresql+asyncpg://`. Rewriting it
    here removes a classic deploy footgun.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url


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
        database_url=_normalize_db_url(
            os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./study_planner.db")),
        job_mode=os.getenv("JOB_MODE", "eager").lower(),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        job_workspace_dir=os.getenv("JOB_WORKSPACE_DIR", ""),
        smtp_host=os.getenv("SMTP_HOST", ""),
        smtp_port=int(os.getenv("SMTP_PORT", "1025")),
        smtp_user=os.getenv("SMTP_USER", ""),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        smtp_from=os.getenv("SMTP_FROM", "Study Planner <no-reply@studyplanner.local>"),
        smtp_starttls=os.getenv("SMTP_STARTTLS", "0") == "1",
        smtp_ssl=os.getenv("SMTP_SSL", "0") == "1",
        resend_api_key=os.getenv("RESEND_API_KEY", ""),
        app_base_url=os.getenv("APP_BASE_URL", "http://localhost:5173"),
        sample_data_dir=os.getenv("SAMPLE_DATA_DIR", "sample_data"),
        max_plans_per_day=int(os.getenv("MAX_PLANS_PER_DAY", "5")),
        quota_cooldown_hours=int(os.getenv("QUOTA_COOLDOWN_HOURS", "24")),
        auth_rate_limit=int(os.getenv("AUTH_RATE_LIMIT", "10")),
        auth_rate_window_s=int(os.getenv("AUTH_RATE_WINDOW_S", "300")),
        guest_enabled=os.getenv("GUEST_ENABLED", "1") == "1",
        guest_runs_per_day=int(os.getenv("GUEST_RUNS_PER_DAY", "1")),
        guest_token_ttl_min=int(os.getenv("GUEST_TOKEN_TTL_MIN", "120")),
        guest_retention_hours=int(os.getenv("GUEST_RETENTION_HOURS", "24")),
        debug=debug,
    )


settings = load_settings()
