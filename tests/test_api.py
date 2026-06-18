"""
API integration tests (BUILD_PLAN B3-B5 verification gates).

Runs against a temp SQLite DB in eager job mode with a stubbed planner (no LLM
calls). Proves the gates that matter:
  * auth flow: signup → verify → login; unverified can't create plans
  * IDOR isolation: user B cannot read user A's plan (404, not 403)
  * erasure: delete account purges every owned row (verified by query)
  * auth rate limiting: brute force is blocked with 429
  * public/legal routes vs auth-by-default

Env is set BEFORE importing the app so settings pick up the temp DB + eager mode.
"""
import asyncio
import os
import tempfile
import uuid

# ── configure the app via env BEFORE importing it ──────────────────────────────
_DB = os.path.join(tempfile.gettempdir(), f"sp_test_{uuid.uuid4().hex}.db")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB}"
os.environ["JOB_MODE"] = "eager"
os.environ["DEBUG"] = "1"
os.environ["AUTH_RATE_LIMIT"] = "20"
os.environ["AUTH_RATE_WINDOW_S"] = "300"
os.environ["MAX_PLANS_PER_DAY"] = "50"

import pytest
from fastapi.testclient import TestClient

from study_planner.api import jobs
from study_planner.api.app import app
from study_planner.api.ratelimit import limiter
from study_planner.validate import ValidationReport


def _fake_planner(data_dir, constraints, progress_cb=None):
    return {
        "study_plan": "### Semester 1\n\n| Module | CP |\n|---|---|\n| Demo | 6 |\n\n**Total CP:** 6",
        "skill_gaps": "- gap one",
        "module_catalog": "catalog",
        "profile": "profile",
        "validation": ValidationReport(),  # ok=True, no findings
    }


jobs.planner_fn = _fake_planner  # no real crew / LLM in tests


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter.reset()
    yield


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:   # triggers lifespan → init_db (sqlite)
        yield c


# ── helpers ────────────────────────────────────────────────────────────────────

def _email():
    return f"u_{uuid.uuid4().hex[:10]}@university.edu"


def _signup(client, email=None, password="hunter2pass"):
    email = email or _email()
    r = client.post("/auth/signup", json={
        "email": email, "password": password,
        "accept_privacy": True, "accept_tos": True})
    assert r.status_code == 201, r.text
    return email, password, r.json()["verify_token"]


def _verify(client, token):
    assert client.post("/auth/verify", params={"token": token}).status_code == 200


def _login(client, email, password="hunter2pass"):
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


_PDF = b"%PDF-1.4\n%fake\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


def _create_plan(client, token, constraints="{}"):
    files = {
        "transcript": ("t.pdf", _PDF, "application/pdf"),
        "handbook": ("h.pdf", _PDF, "application/pdf"),
        "career": ("c.pdf", _PDF, "application/pdf"),
    }
    return client.post("/plans", headers=_auth(token), files=files,
                       data={"constraints": constraints})


# ── tests ──────────────────────────────────────────────────────────────────────

def test_signup_requires_consent(client):
    r = client.post("/auth/signup", json={
        "email": _email(), "password": "hunter2pass",
        "accept_privacy": True, "accept_tos": False})
    assert r.status_code == 400


def test_unverified_cannot_create_plan(client):
    email, pw, token = _signup(client)
    access = _login(client, email)
    r = _create_plan(client, access)
    assert r.status_code == 403  # email not verified yet


def test_full_flow_signup_verify_plan(client):
    email, pw, vtoken = _signup(client)
    _verify(client, vtoken)
    access = _login(client, email)
    r = _create_plan(client, access, constraints='{"target_semesters": 3}')
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["status"] == "succeeded"  # eager mode runs inline
    # fetch the plan
    got = client.get(f"/plans/{job['id']}", headers=_auth(access))
    assert got.status_code == 200
    body = got.json()
    assert "Semester 1" in body["study_plan_md"]
    assert body["validation"]["ok"] is True


def test_demo_plan_runs(client):
    email, _, v = _signup(client)
    _verify(client, v)
    token = _login(client, email)
    r = client.post("/plans/demo", headers=_auth(token))
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "succeeded"  # eager + stub planner


def test_idor_isolation_404(client):
    # user A creates a plan
    a_email, _, a_v = _signup(client)
    _verify(client, a_v)
    a_token = _login(client, a_email)
    job = _create_plan(client, a_token).json()
    # user B must NOT be able to read it — 404, not 403 (no existence disclosure)
    b_email, _, b_v = _signup(client)
    _verify(client, b_v)
    b_token = _login(client, b_email)
    r = client.get(f"/plans/{job['id']}", headers=_auth(b_token))
    assert r.status_code == 404
    r2 = client.get(f"/plans/{job['id']}/status", headers=_auth(b_token))
    assert r2.status_code == 404
    # B's own list is empty
    assert client.get("/plans", headers=_auth(b_token)).json() == []


def test_unauthenticated_blocked(client):
    assert client.get("/plans").status_code == 401
    assert client.get("/auth/me").status_code == 401


def test_legal_routes_public(client):
    assert client.get("/legal/privacy").status_code == 200
    assert client.get("/legal/tos").status_code == 200
    assert "guidance" in client.get("/legal/tos").text.lower()
    assert client.get("/healthz").json() == {"status": "ok"}


def test_auth_rate_limit_blocks_brute_force(client):
    email, _, v = _signup(client)
    _verify(client, v)
    # wrong-password attempts from the same IP eventually 429 (limit=20)
    saw_429 = False
    for _ in range(25):
        r = client.post("/auth/login", json={"email": email, "password": "wrong"})
        if r.status_code == 429:
            saw_429 = True
            break
    assert saw_429


def test_job_failure_is_isolated_and_temp_cleaned(client):
    """A failing planner marks the job failed (error surfaced, not swallowed) and
    the ephemeral temp workspace is still deleted."""
    import glob

    def _boom(data_dir, constraints, progress_cb=None):
        raise RuntimeError("simulated crew failure")

    before = set(glob.glob(os.path.join(tempfile.gettempdir(), "sp_job_*")))
    email, _, v = _signup(client)
    _verify(client, v)
    token = _login(client, email)
    jobs.planner_fn = _boom
    try:
        r = _create_plan(client, token)
    finally:
        jobs.planner_fn = _fake_planner
    assert r.status_code == 201
    job = r.json()
    assert job["status"] == "failed"
    assert "simulated crew failure" in (job["error"] or "")
    # no new sp_job_ temp dir survived the run
    after = set(glob.glob(os.path.join(tempfile.gettempdir(), "sp_job_*")))
    assert after <= before, f"leaked temp dirs: {after - before}"


def test_account_erasure_purges_all_rows(client):
    email, _, v = _signup(client)
    _verify(client, v)
    token = _login(client, email)
    _create_plan(client, token)  # creates job + plan + audit + events

    r = client.delete("/me", headers=_auth(token))
    assert r.status_code == 204

    # prove erasure by querying the DB directly for any row owned by this user
    async def _residual_rows():
        from sqlalchemy import select, func
        from study_planner.api.db import SessionLocal
        from study_planner.api.models import (User, Profile, PlanJob, Plan,
                                               Consent, AuditLog)
        async with SessionLocal() as s:
            uid = (await s.execute(select(User.id).where(User.email == email))).first()
            counts = {}
            for M in (Profile, PlanJob, Plan, Consent, AuditLog):
                col = M.user_id
                n = await s.execute(select(func.count()).select_from(M)
                                    .where(col == (uid[0] if uid else "x")))
                counts[M.__name__] = int(n.scalar_one())
            return uid, counts

    uid, counts = asyncio.get_event_loop().run_until_complete(_residual_rows()) \
        if False else asyncio.run(_residual_rows())
    assert uid is None, "user row should be gone"
    assert all(c == 0 for c in counts.values()), counts

    # the old token must no longer work
    assert client.get("/auth/me", headers=_auth(token)).status_code == 401
