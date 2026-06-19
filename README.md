# Agentic Study Planner

A multi-agent AI application that reads a student's CV, academic transcript, target career path, and a 908-page university module handbook — then generates a validated, semester-wise study plan enforcing real programme rules (credit totals, per-area min/max, prerequisites, thesis placement).

**Live demo:** https://agentic-study-planner.vercel.app &nbsp;|&nbsp; Free to use &nbsp;|&nbsp; Upload your own PDFs

---

## How it works

Five CrewAI agents run in two stages. Three analysts read documents in parallel; two synthesis agents reason over what was extracted.

```
profile_analyst   ── reads cv.pdf + transcript.pdf ──┐
career_analyst    ── reads career.pdf ────────────────┤
module_curator    ── reads module_handbook.pdf ───────┤
                                                      ▼
gap_analyst         profile vs. career → prioritized skill gaps
                                                      ▼
study_planner       semester-wise plan (~30 CP/semester,
                    prerequisites respected, gaps closed first)
```

After the crew finishes, **deterministic Python** validates and, if needed, rebuilds the plan:

- Completed credits per thematic area are parsed from the transcript in code, not inferred by the LLM (LLMs miscounted 81 CP as 46 — arithmetic moved to Python).
- A deterministic validator re-checks every hard rule (area min/max, credit total, horizon, no retakes, thesis last).
- If validation fails a backstop assembler rebuilds the plan from a curated module menu — the LLM only contributes per-module narrative; all scheduling arithmetic is in code.
- The "Credits per area" badge and sidebar table are the validator's output, not the LLM's.

---

## Key engineering decisions

**No RAG.** A regex parser pulls modules from the 908-page handbook PDF in under a second. No embeddings, no hallucination risk on catalogue data.

**LLMs don't count — Python does.** Transcript credit attribution and all credit arithmetic are deterministic. The model only formats the result.

**Prompt rules aren't enforcement.** Every hard constraint has a second layer: a separate deterministic validator that the model never sees.

**Free-tier quotas are a hard ceiling.** Groq gives ~100k tokens/day (~1 full crew run). The app shows an honest "come back later" message instead of spinning or silently failing.

**Email verification is built, not wired.** Render's free tier blocks outbound SMTP. The fix (Resend HTTPS) is coded and ready; it's dormant until a domain is attached — deliberate, not missing.

---

## Local development (Docker Compose — recommended)

Mirrors the production topology: Postgres + Redis + API + worker + frontend + Mailpit for email.

```bash
# 1. Copy env and set at least one LLM key (see "LLM providers" below)
cp .env.example .env

# 2. Start everything
docker compose up --build

# Frontend → http://localhost:5173
# API docs  → http://localhost:8000/docs
# Email UI  → http://localhost:8025  (Mailpit — catches all outbound mail locally)
```

Scale workers:
```bash
docker compose up --scale worker=3
```

### LLM providers

Set `LLM_PROVIDER` in `.env`:

| Provider | Env var | Notes |
|---|---|---|
| `github` (default) | `GITHUB_TOKEN` | GitHub Models — needs `models:read` scope; gpt-4o-mini (fast agents) + gpt-4o (synthesis) |
| `groq` | `GROQ_API_KEY` | llama-3.3-70b — free tier: ~100k tokens/day |
| `mixed` | both keys | Groq primary, Gemini Flash fallback (`GEMINI_API_KEY`), GitHub GPT-4o for synthesis — production config |

### Without Docker (Python + venv)

```bash
# Windows
.\setup.ps1

# macOS / Linux
./setup.sh
```

Both scripts create a venv, install dependencies, and run a preflight check (`python -m study_planner.check`).

For dev mode without Redis, set `JOB_MODE=eager` in `.env` — the plan crew runs inline in the API process (no worker needed).

---

## Running tests

```bash
# Backend (91 tests, no LLM or external services needed)
.\.venv\Scripts\python -m pytest

# TypeScript type check
cd frontend && npx tsc --noEmit
```

Tests cover: auth + IDOR isolation, GDPR erasure (queries the DB for residual rows after delete), rate-limit 429 enforcement, job failure isolation, deterministic credit accounting, area-budget validation, transcript header matching, quota cooldown, OCR availability.

---

## Project structure

```
agentic-study-planner/
├── src/study_planner/
│   ├── main.py              # plan_studies() — crew orchestration + deterministic backstop
│   ├── crew.py              # CrewBase, LLM provider switch, litellm patches
│   ├── validate.py          # deterministic plan validator + render_area_budget_table
│   ├── requirements.py      # programme-rules parser (PDF → ProgramRequirements)
│   ├── inputs.py            # PlanConstraints (semester horizon, per-semester CP targets)
│   ├── worker.py            # RQ background worker entry point
│   ├── config/
│   │   ├── agents.yaml      # 5 agent definitions
│   │   └── tasks.yaml       # 5 task prompts
│   ├── tools/               # read_document, search_document (PDF tools for agents)
│   ├── ingest/              # OCR pipeline for scanned/image PDFs
│   └── api/
│       ├── app.py           # FastAPI app factory
│       ├── models.py        # SQLAlchemy models (User, Plan, Job, ConsentRecord, AuditLog)
│       ├── db.py            # async DB session + create_all
│       ├── jobs.py          # enqueue() — eager (dev) or RQ (prod)
│       ├── quota.py         # per-provider daily quota + cooldown
│       ├── security.py      # JWT auth, password hashing, brute-force protection
│       ├── email.py         # SMTP / Resend dispatch
│       └── routes/          # auth, plans, account, legal
├── frontend/                # React + TypeScript + Tailwind (Vite, deployed to Vercel)
│   └── src/
│       ├── pages/           # Login, Register, NewPlan, PlanView, AccountSettings
│       └── components/      # AreaBudgetBar, ValidationBadge, PlanProgress, etc.
├── tests/                   # pytest suite (auth, plans, validate, requirements, quota, ...)
├── sample_data/             # synthetic test PDFs (fictional student — safe to commit)
├── scripts/                 # make_sample_data.py, make_requirements_pdf.py, run_eval.py
├── docker-compose.yml       # full local stack
├── Dockerfile               # single image for api + worker (command differs)
├── render.yaml              # Render deploy config
├── pyproject.toml           # pinned deps (crewai==1.14.7, litellm==1.89.0, groq==1.4.0)
└── .env.example             # all env vars documented with examples
```

---

## Production stack

| Layer | Technology | Hosting |
|---|---|---|
| Frontend | React + TypeScript + Tailwind (Vite) | Vercel |
| Backend API | FastAPI + async SQLAlchemy | Render (Frankfurt, Docker) |
| Worker | RQ + Redis | Render (same image, `python -m study_planner.worker`) |
| Database | PostgreSQL 16 | Render Postgres (EU region) |
| AI | CrewAI 1.14 — Groq llama-3.3-70b (primary), Gemini Flash (fallback), GitHub gpt-4o (synthesis) | — |
| Email | Resend HTTPS (dormant until domain attached) / Mailpit locally | — |
| OCR | Tesseract + pdf2image (lazy import — degrades if unavailable) | — |

Dependency versions are pinned exactly in `pyproject.toml`. A litellm minor bump silently changed Groq's tool-schema format and broke every plan call — upgrade LLM deps deliberately, then re-run the full test suite and a real plan before promoting.

---

## Compliance notes

- Uploaded PDFs are processed in a temp dir and deleted in `finally` — only the generated plan is persisted.
- Each user's data is scoped by `owner_id` on every table; every read includes the owner filter. IDOR returns 404, not 403.
- Account erasure explicitly purges every owned table (not just cascade) — verified by querying for residual rows in tests.
- Consent version and timestamp are captured at signup. An audit log records generate / view / delete / erase events.

---

## Author

Nandish Karki — M.Sc. Data & Knowledge Engineering, OvGU Magdeburg

[GitHub](https://github.com/Nandish-Karki) · [LinkedIn](https://www.linkedin.com/in/nandish-karki)
