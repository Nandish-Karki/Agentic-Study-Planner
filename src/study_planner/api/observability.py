"""Optional error tracking (Sentry). No-op unless SENTRY_DSN is set, and never
raises — observability must not be able to break boot. Wired into both the API
(app factory) and the RQ worker so job failures in either process are captured.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger("study_planner.observability")
_done = False


def init_sentry(component: str = "api") -> bool:
    """Initialise Sentry if SENTRY_DSN is set and sentry-sdk is installed.
    Returns True if enabled. Idempotent."""
    global _done
    if _done:
        return True
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        return False
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=dsn,
            environment=os.getenv("SENTRY_ENV", "production"),
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0")),
            send_default_pii=False,  # never ship user PII to the tracker
        )
        sentry_sdk.set_tag("component", component)
        _done = True
        log.info("Sentry error tracking enabled (%s)", component)
        return True
    except Exception as e:  # missing dep / bad DSN must not break boot
        log.warning("Sentry init skipped: %s", e)
        return False
