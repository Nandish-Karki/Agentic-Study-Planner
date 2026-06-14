# Build Plan — Production Study Planner (all phases)

This is the **execution-level** companion to `PRODUCT_PLAN.md`. The product plan
decides *what and why*; this decides *how we build it*, concretely enough to code
from. Frontend is deliberately deferred (the VANGUARD-style SPA comes in the last
phase); everything here builds the **backend, agent engine, data model, auth,
security and compliance** so the UI is a thin layer on top when we get there.

Written through four lenses, as requested: **Product Manager** (scope/UX),
**Architect** (system/data), **Senior Full-Stack Engineer** (security/compliance),
**Agentic AI Engineer** (multi-user agent runtime).

Status of inputs folded into this plan:
- ✅ Thematic-area CP budgets (already built — curator + validator).
- 🆕 **Degree time-horizon input** ("finish in N semesters").
- 🆕 **Per-semester CP preferences** ("I want 20 CP this semester, 30 next").
- 🆕 **View-only plans** in the user's account (no download/export for now).
- 🆕 **Concurrent multi-user agent runtime**.
- 🆕 **Production auth + legal/compliance** (the checklist screenshot).

---

## 1. Product Manager lens — scope & user experience

### 1.1 What the product does (one paragraph)
A student signs up, uploads four documents (CV, transcript, target-career
description, module handbook), tells us **how many semesters they want to finish
in** and **any per-semester credit preferences**, and gets a validated,
semester-by-semester study plan they can **view in their account** and re-generate
anytime. Every plan is checked by the deterministic validator (real modules, no
retakes, prerequisites, take-limits, thematic-area budgets, CP totals, and now the
new time-horizon and CP-preference rules).

### 1.2 Core user journey (backend-observable, UI later)
1. **Sign up** → email verification (or Google OAuth) → consent to Privacy Policy + ToS.
2. **New plan** → upload 4 PDFs → set constraints (semesters, CP preferences).
3. **Submit** → async job runs the 5-agent crew → status updates → plan ready.
4. **View plan** → rendered in-account (markdown → HTML), with validity badges and
   per-area / per-semester CP breakdown.
5. **Re-plan** → change constraints, run again; old plans stay in history.
6. **Delete account** → full erasure (GDPR).

### 1.3 The 4 things a user must see (carried from PRODUCT_PLAN §3)
1. The semester plan (the artifact).
2. Which gaps each module closes (the "why").
3. Validity badges (the trust signal — our differentiator).
4. CP accounting: per-semester totals **and** per-thematic-area progress vs budget.

### 1.4 Explicitly NOT in this build
Download/PDF/calendar export, drag-to-reschedule editing, payments, the polished
SPA, B2B advisor dashboard. (Triggers to revisit are in PRODUCT_PLAN §8.)

---

## 2. The new planning-constraints feature (build first — it's pure engine work)

This is independent of auth/infra and can land immediately on the existing engine.

### 2.1 Input shape
```python
# src/study_planner/inputs.py  (new)
@dataclass
class PlanConstraints:
    degree_type: str                 # "bachelor" | "master"
    target_semesters: int            # finish remaining coursework in N semesters
    default_cp_per_semester: int | None = None   # soft target, e.g. 30
    cp_overrides: dict[int, int] = field(default_factory=dict)
    # cp_overrides maps a 1-based *remaining* semester index to a CP target,
    # e.g. {1: 20, 2: 30}  → "20 CP next semester, 30 the one after".
```

### 2.2 How it flows through the system
1. **Captured** at request time (API payload; later the form).
2. **Injected into the planner prompt** (`plan_task`) as explicit constraints:
   > "The student wants to complete remaining coursework in **{target_semesters}
   > semesters**. Target credit load per remaining semester: **{rendered prefs}**.
   > Distribute modules to honor these targets where the rules allow; if a target
   > is infeasible, get as close as possible and note it."
3. **Re-checked by the validator** (deterministic, the enforceable layer).

### 2.3 New validator checks (added to `validate.py`)
| Rule | Severity | What it checks |
|---|---|---|
| `horizon` | ERROR | number of planned semesters ≤ `target_semesters` |
| `cp-preference` | WARNING | each semester's CP within ±3 of its override / default target |
| `feasibility` | ERROR | `remaining_required_CP ≤ target_semesters × MAX_SANE_LOAD` (default 36). If the student physically can't finish in N semesters, say so up front instead of emitting a fake plan |

`feasibility` is computed from the **degree total** (e.g. 120 CP master, 30 of
which is thesis) minus **completed CP** (from the profile), divided across the
target semesters. This catches the "I want 15 CP/sem but need 90 CP in 3 semesters"
contradiction deterministically — a genuinely useful, honest answer.

### 2.4 Verification gate for §2
- New unit tests: feasible plan passes; over-horizon plan flagged; CP-preference
  drift warns; impossible horizon → `feasibility` ERROR with the arithmetic shown.
- Run the sample data with `target_semesters=3, cp_overrides={1:20}` and read the
  plan end-to-end (playbook: read the artifact, don't count outputs).

---

## 3. Architect lens — target system

### 3.1 Stack (recommended, rationale in §8 decisions)
| Concern | Choice | Why |
|---|---|---|
| API | **FastAPI** (async) | Python, same runtime as the crew; SSE-friendly |
| Job queue | **RQ + Redis** | process-based worker handles the long, blocking `crew.kickoff()` cleanly; Arq (async) risks blocking the loop |
| DB | **Postgres** | concurrent multi-user + row-level security |
| Auth | **FastAPI-Users + Postgres** (self-hosted) ✅ LOCKED | full control, reuses the FastAPI/JWT stack from resume-automation; we implement verify/reset/OAuth/rate-limiting ourselves (tasks in §5.2). EU-region Postgres for GDPR residency |
| Object storage | **Ephemeral temp (docs) + Postgres (plans)** ✅ LOCKED | docs processed and deleted immediately; only the derived *plan* is persisted. Re-plan = re-upload. Keeps the strong privacy posture |
| LLM | existing provider routing behind a **gateway module** | we pay for inference now; pooled keys, per-user quota, token budget, fallback chain |

### 3.2 Data model (owner_id on every row — the isolation rule)
```
users            (managed by Supabase Auth: id, email, email_confirmed_at, …)
profiles         id, user_id→users, display_name, degree_type, institution, created_at
plan_jobs        id, user_id, status[queued|running|succeeded|failed],
                 constraints_json, provider, created_at, started_at, finished_at, error
plans            id, job_id→plan_jobs, user_id, study_plan_md, skill_gaps_md,
                 module_catalog_md, profile_md, validation_json, created_at
consents         id, user_id, doc[privacy|tos], version, accepted_at, ip
events           id, user_id?(null for anon), event, props_json, created_at
audit_log        id, user_id, action, target_type, target_id, ip, created_at
```
Documents are **not** stored (ephemeral processing). `plans` holds the derived
markdown only. Every read query filters by `user_id`; Postgres **RLS** is the
second wall.

### 3.3 API surface (v1)
```
POST   /auth/*                      → delegated to Supabase (signup, login, verify, reset, oauth)
GET    /me                          → profile
POST   /plans                       → multipart: 4 PDFs + constraints_json → {job_id}
GET    /plans/{job_id}/status       → {status, error?}  (poll; SSE later)
GET    /plans/{job_id}              → the plan (owner-scoped; 404 on mismatch)
GET    /plans                       → list my plans (history)
DELETE /plans/{job_id}              → soft-delete a plan
DELETE /me                          → full account erasure (purge plans, jobs, events)
GET    /healthz                     → liveness (the one public exception, documented)
```
**Isolation rule (playbook IDOR lesson):** every `/plans/{id}` resolves ownership
from the DB row and returns **404** (not 403) on mismatch so existence isn't
disclosed. The worker carries `user_id` and asserts it on every write.

### 3.4 Engine debt cleared as part of this (from PRODUCT_PLAN §4)
1. Scope the global `litellm` monkeypatch (no import-time global mutation).
2. Build LLM per-request from gateway config, not module-level env-once.
3. Move `crew.kickoff()` into the RQ worker.
4. Structured Pydantic output for the module table (`output_pydantic`) so the
   validator stops depending on markdown parsing drift.
5. Per-user object/temp keys instead of a shared local `data/`.
6. Tests on the pure functions + an integration test of the worker path.

---

## 4. Agentic AI Engineer lens — multi-user agent runtime

This is the "agent upgradation for many users at once" you asked for.

### 4.1 From one synchronous crew → a concurrent worker pool
- A plan request becomes an **RQ job** carrying `(user_id, job_id, constraints,
  document refs)`. The web process never runs the crew.
- A **bounded worker pool** (`WORKER_CONCURRENCY`, default 3) runs crews in
  parallel. Each job gets an **isolated temp workspace** (`tempfile.mkdtemp`),
  always cleaned up in `finally` (ephemeral, the privacy posture).
- **Per-job failure isolation + retry:** transient LLM errors retry with backoff;
  permanent failures set `status=failed` with the captured error surfaced to the
  user (no silent 200-with-stale-result — playbook rule).

### 4.2 Rate limiting (playbook: sequential beats parallel for shared quota)
GitHub Models and Groq both have tight per-minute limits. A naive parallel pool
will trip them. So:
- A **shared token-bucket per provider** in Redis (requests/min + tokens/min),
  consumed by every worker before each LLM call.
- Worker concurrency is capped so the *sum* of in-flight crews stays under the
  provider ceiling; excess jobs wait in the queue (queued, not failed).
- **Per-user quota** (e.g. N plans/day) enforced at enqueue time so one user can't
  exhaust the shared budget — and so abuse can't run up the inference bill.

### 4.3 User context & safety in the worker
- The job payload is the **only** source of identity; the worker asserts `user_id`
  on every DB write (no ambient/global user). This directly closes the playbook's
  "queue worker generated with the wrong profile" leak vector.
- Uploaded PDFs are **untrusted**: enforce type + size caps, parse inside the
  isolated worker with time/memory limits, treat extracted text as **data, not
  instructions** (prompt-injection containment). The deterministic validator is
  the backstop.

### 4.4 Token budget & cost (playbook Phase 3)
- Log resolved provider + model + token counts per job (`[TOKENS]` line) so cost
  per plan is a measured number, not a guess.
- Cache derived context (curator catalog) by **document fingerprint** so a re-plan
  with changed constraints but the same handbook doesn't re-extract modules.
- Route by capability: cheap model for the four analyst passes, strong model for
  synthesis (already the pattern — verify it reaches the call site).
- Fallback chain: primary provider → secondary on quota/outage; mark fallback runs
  in `plan_jobs.provider` so quality complaints are triageable.

### 4.5 Concurrency correctness checklist
- The litellm monkeypatch must be **stateless/thread-safe** (it strips
  `cache_breakpoint` + retries — verify no shared mutable state) before running
  multiple crews in one process; otherwise isolate per worker process.
- No module-level singletons that bake in one user's config.

---

## 5. Senior Full-Stack lens — security & compliance (the screenshot checklist)

Direct mapping of your **Legal & Compliance** and **Auth & Security** screenshot to
build tasks. This is the gating workstream (PRODUCT_PLAN §5).

### 5.1 Legal & Compliance
| Item | Plan |
|---|---|
| **Privacy Policy page** | Static page: what we collect (CV, transcript, career goal, email), lawful basis (consent), **third-party LLM disclosure** (transcript text sent to provider), retention (docs ephemeral, plans until you delete), erasure rights, EU hosting. Versioned; acceptance recorded in `consents`. |
| **Terms & Conditions** | Static ToS page; acceptance recorded in `consents` at signup. "Plans are guidance, not official academic advice" disclaimer. |
| **Cookie consent (GDPR)** | Banner; only essential cookies in this build (no third-party analytics/marketing) → "essential only" notice. If we add analytics later, gate it behind opt-in. |

### 5.2 Auth & Security
| Item | Plan |
|---|---|
| **Signup / login flow** | Supabase Auth (email+password). Tested end-to-end. |
| **Email verification** | Supabase email confirmation; block plan creation until confirmed. |
| **Password reset** | Supabase reset flow. |
| **OAuth (Google)** | Supabase Google provider. |
| **Rate limiting (brute force)** | App-level limiter on auth + `/plans` (per-IP and per-user), plus per-user plan quota. Captcha on signup if abuse appears. |
| **Tenant isolation** | `owner_id` everywhere + RLS; 404-on-mismatch on every fetch; worker carries user ctx (§4.3). |
| **Encryption** | TLS everywhere; Postgres encrypted at rest (managed); secrets in env/vault, never in repo. |
| **Errors surface** | No swallowed exceptions; capture worker stderr; real job status to the user. |
| **Audit log** | `audit_log` row for generate / view / delete / erasure. |

### 5.3 GDPR erasure proof (verification gate for the compliance phase)
Delete account → query confirms every `plan`, `plan_job`, `event`, `consent`,
`audit_log` for that user is purged and no temp doc survives (they're already
ephemeral). This is the playbook-style gate: *prove* it with a query, don't assert it.

---

## 6. Phased build plan (verifiable gates — extends PRODUCT_PLAN §6)

Each phase commits working code the day it works; nothing load-bearing stays
untracked overnight. Each gate must pass before the next phase starts.

| Phase | Scope | Verification gate | Status |
|---|---|---|---|
| **B1. Planning constraints** (engine-only, no infra) | §2: `PlanConstraints`, prompt injection of semesters + CP prefs, new validator rules (`horizon`, `cp-preference`, `feasibility`), tests | Sample run with `target_semesters=3, cp_overrides={1:20}` honors the targets; impossible horizon → `feasibility` ERROR; all tests green | ✅ done (`72645a6`) — verified end-to-end |
| **B2. Engine hardening** | §3.4: scope monkeypatch, per-request LLM, swap local `data/` for per-job temp, worker-path integration test | Crew imports with no side effects; no global litellm mutation; failing job isolated + temp cleaned; tests green | ✅ done — `llm_config.py` (lazy patch + LLM factory); worker-path test green. *Pydantic module output deferred: markdown parsing is robust + tested; forcing structured output risks destabilizing the working multi-table curator. Revisit if format drift reappears.* |
| **B3. Async runtime + concurrency** | §4: FastAPI app, RQ+Redis worker (eager fallback), per-user quota, job state machine, ephemeral temp, cost/provider logging | One bad PDF fails its job only; quota caps per user; job status machine works | ✅ done — `api/jobs.py`, `worker.py`. Concurrency = RQ worker count; per-call rate limiting via litellm backoff patch |
| **B4. Auth + multi-tenancy** | §3.2–3.3 + §5.2: self-hosted JWT auth, data model, owner-scoped API, worker carries user ctx | **Isolation proof:** user A cannot read user B's plan by any ID (404); new user sees zero data | ✅ done — verified by `test_idor_isolation_404` |
| **B5. Legal & compliance** | §5.1 + §5.3: Privacy/ToS/cookie, consent capture, audit log, rate limiting, erasure | **Erasure proof** by query; auth brute-force limited; consent recorded at signup | ✅ done — verified by `test_account_erasure_purges_all_rows`, `test_auth_rate_limit_blocks_brute_force` |
| **B6. Frontend** (deferred) | React/TS SPA, VANGUARD-style hero + dashboard, SSE progress, plan viewer with validity badges + CP breakdown | A non-author completes signup→upload→constraints→view with zero help | ⬜ deferred (this API is the contract it consumes) |

B2–B5 are built and verified by 32 passing tests (`tests/`). Remaining for a real
deploy: provision Postgres (EU) + Redis, set `SECRET_KEY`/`DEBUG=0`/`JOB_MODE=rq`,
wire SMTP for the verify/reset emails, and add Google OAuth credentials. Email
verification and password-reset currently return the token in the response when
`DEBUG=1` (so the flows are testable); production sends it by email instead.

---

## 7. Future features backlog (post-build, trigger-gated)
- **Plan export** (PDF + .ics calendar) — when users ask to take the plan offline.
- **"What-if" editor** — drag a module to another semester; validator re-runs live.
- **Plan diff** — compare two generated plans side by side.
- **Multiple career targets** — plan toward role A vs role B.
- **Grade-aware optimization** — weight toward modules matching the student's strengths.
- **B2B advisor dashboard** — a department sees all students' plans (separate auth tier).
- **Self-hosted open model tier** — if a university blocks third-party LLMs.
- **SSO (university IdP)** — for B2B.
- **Notifications** — email when a plan finishes (already partly there via job status).

---

## 8. Decisions — LOCKED (2026-06-14)

1. **Auth/infra: self-hosted FastAPI-Users + Postgres.** Full control, reuses the
   FastAPI/JWT stack from resume-automation. We implement email verification,
   password reset, OAuth, and rate limiting ourselves (build tasks in §5.2).
   EU-region Postgres for GDPR residency.
2. **Documents: ephemeral + stored plans.** Uploaded PDFs are processed in a temp
   dir and deleted immediately after the run; only the derived plan is persisted.
   Re-planning requires re-upload. Keeps the strong privacy posture and avoids most
   document-retention compliance burden.
3. **Build order: start B1 (planning constraints) now** — no infra, directly
   delivers the requested feature; B2–B6 are reversible scaffolding built on top.
```
