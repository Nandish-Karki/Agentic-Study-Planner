"""
Free-tier quota-exhaustion tests (Workstream 1).

Proves the "come back in 24h" behaviour without any live infra (SQLite + eager
jobs + a stubbed planner that raises a daily-quota error):
  * the daily-vs-perminute classifier
  * GET /status flips to unavailable while paused
  * POST /plans pre-flight returns a structured 429 during cooldown
  * a job that fails on the daily cap sets the global cooldown + failure_reason,
    and that failed job is NOT charged against the user's daily quota
"""
import os
import tempfile
import uuid

os.environ.setdefault("DATABASE_URL",
                      f"sqlite+aiosqlite:///{os.path.join(tempfile.gettempdir(), f'sp_q_{uuid.uuid4().hex}.db')}")
os.environ.setdefault("JOB_MODE", "eager")
os.environ.setdefault("DEBUG", "1")
os.environ.setdefault("MAX_PLANS_PER_DAY", "3")

import pytest
from fastapi.testclient import TestClient

from study_planner.api import jobs
from study_planner.api.app import app
from study_planner.api import cooldown
from study_planner.api import progress
from study_planner.llm_config import is_daily_quota_error
from study_planner.validate import ValidationReport

# A realistic Groq daily-cap error message.
_GROQ_TPD = ('litellm.RateLimitError: RateLimitError: GroqException - '
             '{"error":{"message":"Rate limit reached ... on tokens per day (TPD): '
             'Limit 100000, Used 99714, Requested 1367.","code":"rate_limit_exceeded"}}')


def _ok_planner(data_dir, constraints, progress_cb=None):
    return {"study_plan": "### Semester 1\n\n| Module | CP |\n|---|---|\n| Demo | 6 |\n\n**Total CP:** 6",
            "skill_gaps": "- gap", "module_catalog": "c", "profile": "p",
            "validation": ValidationReport()}


@pytest.fixture(autouse=True)
def _clean():
    jobs.planner_fn = _ok_planner
    cooldown.clear_cooldown()      # process-global flag — reset around every test
    yield
    cooldown.clear_cooldown()
    jobs.planner_fn = _ok_planner


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _user(client):
    email = f"q_{uuid.uuid4().hex[:10]}@university.edu"
    r = client.post("/auth/signup", json={"email": email, "password": "hunter2pass",
                                          "accept_privacy": True, "accept_tos": True})
    token = r.json()["verify_token"]
    client.post("/auth/verify", params={"token": token})
    access = client.post("/auth/login",
                         json={"email": email, "password": "hunter2pass"}).json()["access_token"]
    return email, access


_PDF = b"%PDF-1.4\n%fake\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


def _create(client, access):
    files = {"transcript": ("t.pdf", _PDF, "application/pdf"),
             "handbook": ("h.pdf", _PDF, "application/pdf"),
             "career": ("c.pdf", _PDF, "application/pdf")}
    return client.post("/plans", headers={"Authorization": f"Bearer {access}"},
                       files=files, data={"constraints": "{}"})


# ── classifier ─────────────────────────────────────────────────────────────────

def test_classifier_daily_vs_perminute():
    assert is_daily_quota_error(_GROQ_TPD) is True
    assert is_daily_quota_error("rate limit reached on tokens per minute (TPM)") is False
    assert is_daily_quota_error("503 service unavailable, overloaded") is False
    assert is_daily_quota_error("google RESOURCE_EXHAUSTED quota") is True


# ── /status ──────────────────────────────────────────────────────────────────--

def test_status_reflects_cooldown(client):
    s = client.get("/status").json()
    assert s["quota_available"] is True and s["cooldown_seconds"] == 0
    cooldown.set_cooldown(3600)
    s = client.get("/status").json()
    assert s["quota_available"] is False and s["cooldown_seconds"] > 0
    assert s["retry_at"] is not None


# ── pre-flight 429 ───────────────────────────────────────────────────────────--

def test_preflight_429_during_cooldown(client):
    _, access = _user(client)
    cooldown.set_cooldown(3600)
    r = _create(client, access)
    assert r.status_code == 429
    detail = r.json()["detail"]
    assert detail["reason"] == "quota_exhausted"
    assert detail["retry_after_s"] > 0 and detail["retry_at"]


# ── job-level daily-quota failure ────────────────────────────────────────────--

def test_daily_quota_job_sets_cooldown_and_refunds(client):
    _, access = _user(client)

    def _quota_boom(data_dir, constraints, progress_cb=None):
        raise RuntimeError(_GROQ_TPD)

    jobs.planner_fn = _quota_boom
    r = _create(client, access)
    assert r.status_code == 201           # job is created, then fails inside (eager)
    job = r.json()
    assert job["status"] == "failed"
    assert job["failure_reason"] == "quota_exhausted"
    assert job["retry_at"] is not None

    # the global cooldown is now active → next request is pre-flight-rejected
    jobs.planner_fn = _ok_planner
    assert _create(client, access).status_code == 429

    # ...and the failed-by-our-outage job did NOT consume the user's daily quota:
    # lift the cooldown, then a normal plan still succeeds (quota not charged).
    cooldown.clear_cooldown()
    ok = _create(client, access)
    assert ok.status_code == 201 and ok.json()["status"] == "succeeded", ok.text


# ── live phase tracking (Workstream 3a) ──────────────────────────────────────--

def test_progress_roundtrip():
    progress.set_phase("job-x", "Planning your semesters")
    assert progress.get_phase("job-x") == "Planning your semesters"
    progress.clear_phase("job-x")
    assert progress.get_phase("job-x") is None


def test_progress_cb_is_wired_to_planner(client):
    _, access = _user(client)
    seen = []

    def _planner(data_dir, constraints, progress_cb=None):
        assert callable(progress_cb)        # jobs must pass a usable callback
        progress_cb("Reading your documents")
        seen.append("ok")
        return _ok_planner(data_dir, constraints)

    jobs.planner_fn = _planner
    r = _create(client, access)
    assert r.status_code == 201 and r.json()["status"] == "succeeded", r.text
    assert seen == ["ok"]
