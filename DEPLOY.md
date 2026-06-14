# Deployment Guide

The product is four runtime pieces (BUILD_PLAN §3–§4):

```
 React SPA (static)  ──HTTPS──►  FastAPI API  ──►  Postgres (owner-scoped rows)
   (Vercel / nginx)                  │      └──►  Redis  ◄── RQ worker(s) ──► LLM provider
                                     └─ enqueues plan jobs        (run the 5-agent crew)
```

- **API** and **worker** run the *same* Docker image; only the command differs.
- **Documents are never stored** — uploads are processed in a temp dir and deleted.
- **Concurrency** = number of workers; keep it within the LLM provider's rate limits.

---

## Option A — Local full stack (Docker Compose)

The fastest way to run everything exactly like prod.

```bash
# 1. Provide the LLM key the worker needs (and a secret)
printf "GITHUB_TOKEN=YOUR_TOKEN\nSECRET_KEY=%s\n" "$(python -c 'import secrets;print(secrets.token_urlsafe(48))')" > .env

# 2. Bring up Postgres + Redis + API + 2 workers + frontend
docker compose up --build

# 3. Open
#    frontend → http://localhost:5173
#    API docs → http://localhost:8000/docs
```

Scale workers: `docker compose up --build --scale worker=3`.

---

## Option B — Managed cloud (Render + Vercel)

### Backend (API + worker + Postgres + Redis) → Render
1. Push this repo to GitHub.
2. On [render.com](https://render.com): **New → Blueprint**, pick the repo. It reads
   [`render.yaml`](render.yaml) and creates the Postgres DB, Redis, API web service,
   and the worker — all in the `frankfurt` (EU) region for GDPR residency.
3. After it provisions, set these on the **API** and **worker** services
   (Dashboard → Environment):
   - `GITHUB_TOKEN` (and/or `GROQ_API_KEY`)
   - On the API: `ALLOWED_ORIGINS` = your frontend URL (e.g. `https://study-planner.vercel.app`)
   - `SECRET_KEY` is auto-generated; the worker inherits it from the API.
4. `DATABASE_URL` is wired automatically and auto-rewritten to the async driver in
   code — nothing to do.

### Frontend (static SPA) → Vercel
```bash
cd frontend
npx vercel --prod        # or import the repo at vercel.com/new, root = frontend/
```
Set one env var in the Vercel project: `VITE_API_URL` = your Render API URL
(e.g. `https://study-planner-api.onrender.com`). [`vercel.json`](frontend/vercel.json)
handles the SPA rewrite. Rebuild after changing it (the value is baked at build time).

> Any host works: the frontend is a static bundle (also deployable via
> [`frontend/Dockerfile`](frontend/Dockerfile) behind nginx); the backend is a
> standard Docker image (Railway, Fly.io, a VPS — all fine).

---

## Required environment variables

| Var | Where | Notes |
|---|---|---|
| `SECRET_KEY` | API + worker | **required when `DEBUG=0`**. `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `DEBUG` | API | `0` in prod |
| `DATABASE_URL` | API + worker | `postgresql://…` is fine (auto-rewritten); SQLite for dev |
| `JOB_MODE` | API + worker | `rq` in prod, `eager` for dev/no-Redis |
| `REDIS_URL` | API + worker | required when `JOB_MODE=rq` |
| `ALLOWED_ORIGINS` | API | the frontend origin(s), comma-separated |
| `LLM_PROVIDER` | API + worker | `github` / `groq` / `mixed` |
| `GITHUB_TOKEN` / `GROQ_API_KEY` | API + worker | LLM credentials (secret) |
| `MAX_PLANS_PER_DAY` | API | per-user quota (cost control) |
| `VITE_API_URL` | frontend build | the API base URL |

---

## Smoke test (after deploy)

```bash
API=https://your-api-url
curl $API/healthz                       # {"status":"ok"}
curl $API/legal/privacy                 # privacy policy text
# then: open the frontend, sign up, verify (email in prod), upload the
# sample_data PDFs, set "finish in 3 semesters", and view the validated plan.
```

---

## Still to wire for a full production launch (documented gaps, not code holes)

1. **Email delivery.** Verification + password-reset tokens are returned in the API
   response only when `DEBUG=1`. For prod, plug an SMTP/email provider into
   `routes/auth.py` (the `make_verify_token` / `make_reset_token` calls) and send
   the link instead of returning it.
2. **Google OAuth.** `/auth/oauth/google` is scaffolded; set `GOOGLE_CLIENT_ID` /
   `GOOGLE_CLIENT_SECRET` and implement the redirect/callback to finish it.
3. **Alembic migrations.** Boot does `create_all` (safe/idempotent). Add Alembic
   before the first schema change in prod.
4. **DPA with your LLM provider** + the privacy policy review — you send transcript
   text to a third party; that must be disclosed (it is, in `/legal/privacy`) and
   covered by a data-processing agreement.
