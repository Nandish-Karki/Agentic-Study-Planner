# Study Planner API (BUILD_PLAN B2–B5)

Self-hosted FastAPI backend: multi-user auth, ephemeral document processing, an
async plan-job pipeline that runs the 5-agent crew, and GDPR-grade isolation +
erasure. No frontend — that's B6; this is the API a SPA will call.

## Install

```bash
pip install -e ".[api]"
```

## Run (dev — SQLite, eager jobs, no Redis)

```bash
# .env: DEBUG=1, JOB_MODE=eager, DATABASE_URL=sqlite+aiosqlite:///./study_planner.db
uvicorn study_planner.api.app:app --reload
# open http://127.0.0.1:8000/docs
```

In `eager` mode the crew runs inline in the request (1–2 min) — fine for dev/demo.

## Run (production — Postgres + Redis + workers)

```bash
# .env: DEBUG=0, SECRET_KEY=<random>, JOB_MODE=rq,
#       DATABASE_URL=postgresql+asyncpg://user:pass@host/db (EU region),
#       REDIS_URL=redis://host:6379/0
uvicorn study_planner.api.app:app --host 0.0.0.0 --port 8000   # web
python -m study_planner.worker                                  # worker (run N of these)
```

Worker **count** is the concurrency control — N workers = up to N crews in flight.
Keep N within the LLM provider's rate limits (the litellm patch adds per-call
backoff). Web and workers must share a filesystem (uploads are written to a temp
dir by the web process and deleted by the worker after the run).

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/auth/signup` | – | create account (requires privacy+ToS consent) |
| POST | `/auth/verify` | – | confirm email (token) |
| POST | `/auth/login` | – | get a bearer token (rate-limited) |
| POST | `/auth/password-reset/request` · `/confirm` | – | reset password |
| GET | `/auth/oauth/google` | – | OAuth scaffold (needs GOOGLE_CLIENT_ID/SECRET) |
| GET | `/auth/me` | ✓ | current user |
| POST | `/plans` | ✓ verified | upload 4 PDFs + constraints → job |
| GET | `/plans` | ✓ | my plan history |
| GET | `/plans/{id}/status` | ✓ owner | job status |
| GET | `/plans/{id}` | ✓ owner | the plan + validity badges |
| DELETE | `/plans/{id}` | ✓ owner | delete a plan |
| DELETE | `/me` | ✓ | **erase account** (purges all owned rows) |
| GET | `/legal/privacy` · `/tos` · `/cookie` | – | legal copy (public) |
| GET | `/healthz` | – | liveness (public) |

## Security properties (verified by `tests/test_api.py`)

- **Auth by default**; the only public routes are `/healthz`, `/legal/*`, and the
  auth endpoints.
- **Tenant isolation:** every owned row carries `user_id`; every fetch scopes by it
  and returns **404 (not 403)** on owner mismatch — no existence disclosure.
- **Erasure:** `DELETE /me` purges plans, jobs, profile, consents, events, and
  audit rows; uploads were never stored. Proven by query in the test suite.
- **Brute-force:** auth endpoints are IP rate-limited (429).
- **Untrusted input:** PDFs are type/size-capped (10 MB) and processed in an
  isolated temp dir, always deleted.
- **Ephemeral documents:** only the derived plan text is persisted.
- **Quota:** `MAX_PLANS_PER_DAY` per user caps inference cost.

## What's deliberately not here yet (B6)

The React/TS frontend (VANGUARD-style hero + dashboard with the plan viewer and
validity badges). This API is the contract it will consume.
