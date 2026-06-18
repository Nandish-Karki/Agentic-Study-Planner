"""RQ worker entrypoint (BUILD_PLAN §4) — production async runtime.

Run one or more of these alongside the API when JOB_MODE=rq:

    JOB_MODE=rq REDIS_URL=redis://… python -m study_planner.worker

Worker COUNT is the concurrency control: N workers = up to N crews in flight.
Keep N at or below what the LLM provider's rate limits allow (the litellm patch
adds per-call backoff on top). Each job runs in its own process with its own DB
session and carries the enqueuing user's id.
"""
from __future__ import annotations

import sys

from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    import redis
    from rq import Queue, Worker

    from study_planner.api.config import settings
    from study_planner.api.observability import init_sentry

    init_sentry("worker")  # capture crew/job failures in prod (no-op without SENTRY_DSN)
    conn = redis.from_url(settings.redis_url)
    queues = [Queue("plans", connection=conn)]
    print(f"[worker] listening on 'plans' via {settings.redis_url}")
    Worker(queues, connection=conn).work(with_scheduler=True)


if __name__ == "__main__":
    sys.exit(main())
