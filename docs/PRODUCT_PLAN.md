# Product Plan — Study Planner as a Real Product

> Status: **DRAFT for approval.** Nothing here is built. This is a strategy +
> architecture + design + go-to-market plan across four lenses (strategist,
> product designer, architect, senior engineer), with a phased roadmap whose
> early gate is *demand validation*, not infrastructure.

---

## 0. The one thing to read first (my honest recommendation)

**A workshop demo succeeding is not product validation.** Your audience was
classmates who were told to look, not strangers who chose to pay or return.
Your own execution playbook has scars from exactly this: building the full
thing before confirming anyone wanted it (the dashboard rebuilt to 4 columns,
the grounding ledger built across 3 phases then rolled back). So the plan below
deliberately **does not start by building a multi-user website.** It starts by
spending ~1 week proving demand, then builds in verifiable phases.

**My three headline calls (argued in §1–§2):**

1. **Separate product, shared account/billing backend — not a feature bolted
   into resume-automation.** The customers overlap only thinly and the jobs are
   different. But the *auth, billing, and a "career-target" engine* should be
   shared infrastructure you already 80% own.
2. **The real buyer is probably not the individual student — it's the
   university / advising office (B2B2C), or a "career-planning" angle that
   widens the audience beyond current students.** Students don't pay; this is
   the biggest threat to the product and must be tested first.
3. **Privacy is the hardest engineering constraint, not the dashboard.** You
   are processing academic transcripts (grades) and CVs — education records +
   PII, GDPR special handling, third-party-LLM disclosure. This gates launch
   and is non-optional. Budget for it from day one.

If you only take one action from this document: **run Phase 0 (validation)
before approving Phases 2–5.**

---

## 1. Strategy — feature inside resume-automation, or separate product?

### The customer/job analysis

| | Resume automation | Study planner |
|---|---|---|
| Job-to-be-done | "Help me apply for a job **now**" | "Help me choose my **next 2–4 semesters**" |
| Audience | All job seekers (huge) | Students with elective choice (narrow) |
| Use frequency | Every application (repeat) | ~Once a year (rare) |
| Willingness to pay | Higher (career stakes, employed soon) | Low (students are broke) |
| Sensitive inputs | CV, profile | CV **+ transcript (grades) + handbook** |

**Why not a feature inside resume-automation:** the resume tool's audience is
mostly *not* current students with electives to plan. Bolting a "plan my degree"
tab onto a "tailor my resume" app dilutes the resume product's focus and shows
an irrelevant feature to most of its users. The artifact (a semester plan) has
nothing to do with resumes. Feature-bolting weak-overlap products is how focused
products rot.

**Why not a naive standalone paid product either:** infrequent use + broke
customers + high-friction inputs (you need a transcript AND a machine-readable
module handbook) = weak standalone B2C economics.

**The synthesis — what's actually valuable and reusable:** both products need to
answer *"what role is this person targeting, and what skills does it require?"*
That **career-target / skill-gap engine** is the genuinely shared asset. Build it
once as a service. Resume automation consumes it to know what to emphasize; the
study planner consumes it to know what to fill.

### Recommendation: a small product family

```
            ┌──────────────────────────────────────────┐
            │   Shared platform (you already own ~80%)   │
            │   • Accounts / auth (FastAPI+JWT today)    │
            │   • Billing / quotas                       │
            │   • Career-target & skill-gap engine (new) │
            │   • LLM gateway (keys, budget, caching)    │
            └───────────────┬───────────────┬───────────┘
                            │               │
                   ┌────────▼─────┐  ┌──────▼─────────┐
                   │ Resume tool  │  │ Study planner  │
                   │ (existing)   │  │ (this product) │
                   └──────────────┘  └────────────────┘
```

- **Separate apps, separate focus, separate URLs.** Study planner validates and
  lives or dies on its own without polluting the resume product.
- **One identity + billing backend.** A user signs in once; if they use both,
  great (natural cross-sell), but neither depends on the other.
- If the study planner gets traction it's already an independent product. If it
  doesn't, you lost a landing page, not a refactor.

**This is the lowest-regret path** and it reuses the FastAPI auth, React shell,
and Docker setup you built for resume-automation.

---

## 2. Target customer & monetization (the make-or-break question)

The product's #1 risk is **"students won't pay."** Test this before building.

Three candidate markets, in order of how seriously to take them:

1. **B2B2C — universities / departments / advising offices.** They have budget,
   a real pain (advisors are overloaded, students pick electives badly), and
   already hold the transcripts and handbooks. Sell seats or a site license.
   Downside: long sales cycles, procurement, heavy compliance (SSO, DPA, data
   residency). **Highest revenue, highest effort.**
2. **B2C "career planning," widened beyond current students.** Reframe from
   "plan my electives" to "close the gap between where I am and the job I want"
   — which includes bootcamp/MOOC/cert recommendations, not just university
   modules. This widens the audience to career-changers and self-learners and
   makes the resume-tool cross-sell coherent. **Most coherent with your existing
   product; moderate willingness to pay (freemium + paid re-plans/exports).**
3. **Pure B2C student elective planner (today's demo).** Narrowest, weakest
   monetization. Fine as the free top-of-funnel, not as the business.

**Monetization model (B2C):** freemium — first plan free, pay for re-plans,
PDF/calendar export, "what-if" scenarios, and multi-target comparison.
**(B2B):** per-seat or site license with SSO + admin dashboard.

**Phase 0 metric (what proves this is worth building):** a landing page +
waitlist and a gated single-tenant demo. Target a concrete number, e.g.
*≥100 signups and ≥30 completed plans from non-friends in 2 weeks*, and at least
a handful saying "I'd pay" or one department saying "pilot it." If you can't hit
a signal like that, **do not build Phases 2–5** — iterate the pitch instead.

---

## 3. Product design (product-designer lens)

### Principle: actionable-minimal first

Your playbook's dashboard-v1 lesson applies directly: do **not** open with
analytics, histories, and scoring. Confirm the 3–4 things a user actually needs:
1. **The plan itself** (semester-by-semester, clear).
2. **Is it valid?** (does it satisfy the rules — this is where the deterministic
   validator becomes a visible trust feature, not just a backend check).
3. **Does it close my gaps?** (skill-gap coverage, visibly).
4. **Get it out** (export PDF / calendar / share link).

Everything else (history, what-if, comparisons) ships behind that, opt-in.

### User journey

1. **Sign in** (Google — students have it; university SSO for B2B).
2. **Onboarding upload** — progressive, not a 4-file wall. Start with transcript
   + a target role; CV and handbook optional/added later. Drag-drop with a
   **parse preview**: *"We read 5 completed modules, 27 CP — looks right?"* This
   turns the scary "did it read my PDF correctly?" moment into a confirmation
   step (and catches scanned-PDF failures early).
3. **Career target** — pick from templated roles or free-text; this hits the
   shared skill-gap engine.
4. **Generate** — the 5 agents working is a *delightful* live-progress moment:
   stream *"Profile Analyst reading transcript… Module Curator found 14
   modules… Planner drafting semester 3…"* via SSE. Turns a 60–120s wait into a
   story instead of a spinner.
5. **Interactive plan dashboard** (the core screen):
   - **Semester timeline** — cards per semester, CP total per semester, color by
     load (under/over target).
   - **Skill-gap coverage** — a progress/radar view: which target-role gaps each
     semester closes, which remain uncovered.
   - **Per-module "why"** — hover/expand shows the justification + which gap it
     closes + provenance ("from your handbook, p.4").
   - **Validity badges** — green check if all constraints pass; warnings list
     any violations (prereq, CP load, take-limit). The validator's output, shown.
   - **Export** — PDF, .ics calendar, shareable read-only link.
6. **Iterate** — change the target role or constraints → regenerate; later,
   "what-if" (drag a module to another semester and re-validate).
7. **History** — past plans, opt-in.

### Design system

Reuse the React shell from resume-automation. Tailwind + a component kit
(shadcn/ui) for speed. Mobile-responsive (students are on phones), but the plan
dashboard is desktop-first.

---

## 4. Architecture (architect lens)

### Current state → target state

| Concern | Today (demo) | Target (product) |
|---|---|---|
| Execution | Synchronous 60–120s CLI `kickoff()` | **Background job queue** — never in a request |
| LLM init | Module-level globals, env read once | Per-request/per-tenant config via a gateway |
| litellm | **Global monkeypatch** (leaks to importers) | Scoped wrapper / no global mutation |
| Storage | Local `data/` and `outputs/` files | Object store (per-user keys) + Postgres |
| Multi-user | None | Row-level isolation, owner on every row |
| API | None | FastAPI REST + SSE for progress |
| Frontend | None | React/TS dashboard |

### Target system

```
React/TS SPA ──HTTPS──► FastAPI API ──► Postgres (RLS, owner_id everywhere)
     │  ▲                    │     └──► Object storage (encrypted, per-user keys, signed URLs)
     │  └──SSE progress──────┤
     │                       └──► Job queue (Redis + Arq/RQ/Celery)
     │                                   │
     │                                   ▼
     │                          Worker pool ──► LLM Gateway ──► providers (OpenAI/Groq/…)
     │                          (carries user ctx)   │  (keys, per-user quota, token budget,
     └───────download plan/exports                   └──► context cache by doc fingerprint)
```

**Key decisions:**
- **Job queue is mandatory**, not optional — a 5-agent crew is minutes of
  blocking LLM calls. Arq (async-native, light) or Celery+Redis (battle-tested).
  Status via polling or SSE. Per-job failure isolation (one bad PDF ≠ dead batch).
- **Postgres, not SQLite.** Concurrent multi-user + row-level security. Every
  table carries `owner_id`; every read scopes by it; RLS as defense-in-depth.
- **Documents in object storage, not the DB.** S3-compatible (or encrypted disk
  for self-host), per-user key prefixes, encrypted at rest, short-TTL signed URLs.
- **LLM gateway service.** You pay for inference now (not the student's free
  token). Pooled keys behind a gateway that enforces per-user quotas, budgets
  tokens (playbook Phase 3), caches derived context by document fingerprint, and
  routes by capability (cheap model for extraction, strong for synthesis).
- **Provider abstraction** so a provider outage or price change is a config flip,
  with a fallback chain (playbook: degrade quality, don't halt).

### Engine debt to clear *before* scaling (these are today's real bugs)

1. **Global `litellm` monkeypatch** → scope it; it currently leaks to any importer.
2. **Module-level LLM construction reading env once** → build per-request from
   tenant/gateway config.
3. **Synchronous `kickoff()`** → move into the worker.
4. **No structured output** → Pydantic `output_pydantic` for the module table so
   the validator is trivial and table format stops drifting.
5. **The deterministic validator (FUTURE.md 1.1)** → now a *product* feature
   (the validity badges), not just hygiene. Build it early.
6. **File-path-bound tools** → swap local `data/` for per-user object-store keys.
7. **No tests** → the pure functions (chunking, key resolution, validator) get
   unit tests; the worker path gets an integration test on sample data.

---

## 5. Security, privacy, isolation (senior-engineer lens — the heavy part)

You explicitly asked for this, and it is genuinely the hardest part — harder
than the dashboard. **The inputs are academic transcripts (grades), CVs, and
career aspirations: PII + education records.** Treat this as the gating workstream.

### Data classification & legal
- Transcripts/grades + CVs = personal data, education records. If you touch EU
  students (you're in Magdeburg — you will), **GDPR applies hard**: lawful basis
  (explicit consent), data minimization, **right to erasure** (delete account →
  purge documents, plans, derived artifacts, cache), **right to access/export**,
  a **DPA** with each sub-processor (incl. the LLM provider), **EU data
  residency** (host in Frankfurt/EU region), and records of processing.
- B2B with universities raises the bar further: institutional DPA, SSO,
  possibly a no-third-party-LLM option (see below).

### Tenant isolation (your playbook's known leak vector)
- `owner_id` on every row; every query scoped; Postgres **RLS** as a second wall.
- **The worker must carry the enqueuing user's security context** — your
  playbook names "the queue worker generating with the wrong profile" as a real
  cross-user leak. Pass and assert user context into every job.
- Object-store access via per-user-scoped signed URLs only; never a shared bucket
  root. **IDOR checks** on every document/plan fetch (user A cannot GET user B's
  plan by guessing an ID).

### Encryption & secrets
- TLS everywhere; **AES-256 at rest** for documents; encrypted DB volume.
- Secrets in a vault/env, never in repo; rotation policy. (You know this one.)

### Third-party LLM exposure (the subtle, important one)
- Sending a transcript to OpenAI/Groq/GitHub Models = **third-party data
  processing that must be disclosed** in the privacy policy and covered by a DPA.
  Verify each provider's training/retention policy (OpenAI API doesn't train on
  API data by default — confirm and document per provider).
- For privacy-sensitive B2B, offer (later) a **self-hosted open model tier** so
  transcripts never leave your infra. Expensive — note as a deferred option, but
  it may be the unlock for university deals.

### Untrusted input handling
- **Uploaded PDFs are untrusted.** Validate type + size caps; run extraction in
  the **isolated worker** (a malicious/huge PDF can DoS or exploit a parser);
  time/memory-limit the parse.
- **Prompt injection:** a crafted "career goal" or text inside a PDF can carry
  instructions to the agents. Contain it (treat document text as data, not
  instructions), constrain tool scope, and validate output. The deterministic
  validator is also a backstop here.

### Operational security
- Auth on every route **by default**; each public exception (health, shared
  read-only plan link) written down with its justification.
- **Audit log** (who accessed/generated/exported what) — needed for both
  security and B2B compliance.
- Per-user **rate limits & quotas** (LLM calls cost real money; abuse = your bill).
  Captcha on signup, abuse detection.
- Errors surface (no swallowed exceptions, no 200-with-failure); capture worker
  stderr; show the user a real status, not a silent stale result.

---

## 6. Phased roadmap (verifiable gates — playbook B1→B4 style)

Each phase has a **verification** that must pass before the next starts.

| Phase | Scope | Verification gate |
|---|---|---|
| **0. Validate demand** *(do this first)* | Landing page + waitlist; gated single-tenant hosted demo on sample/own data. No multi-user build. | **Metric:** ≥ target signups + completed plans from non-friends; ≥1 "would pay"/pilot signal. **No signal → stop, re-pitch.** |
| **1. Harden the engine** | Clear §4 debt: async worker, provider gateway, structured output, the validator, scope the monkeypatch, tests. Still single-tenant. | Sample-data run goes through the **queue**; validator flags the known take-limit violation; tests green; no global litellm mutation. |
| **2. Multi-user core** | FastAPI app reusing resume-automation auth; Postgres with `owner_id` + RLS; per-user object storage; worker carries user context. | **Isolation proof** (playbook style): user A cannot read/regenerate user B's docs or plans by any ID; new user sees zero data. |
| **3. The dashboard** | React/TS app: upload+parse-preview, SSE agent progress, plan timeline, gap coverage, validity badges, export. Actionable-minimal. | A non-author completes upload→plan→export with zero help; the 4 core needs (§3) all visible. |
| **4. Privacy & compliance** | GDPR: consent, erasure (full purge), export, DPA + privacy policy, EU residency, audit log, rate limits. | **Erasure proof:** delete account → every document, plan, derived artifact, and cache entry gone (verified by query). Pen-test the IDOR/authz surface. |
| **5. Billing & GTM** | Freemium gating, quotas, payments; B2C launch and/or B2B pilot. | First real paying user or signed pilot. |

Phases 1–4 are each "commit working features the day they work"; nothing
load-bearing stays untracked overnight.

---

## 7. Cost model (you pay for inference now)

The economics flip the moment you stop using students' free tokens:
- **Per-plan LLM cost** = 5 agents × (document reads + synthesis). Measure it in
  Phase 1 (token budget is a feature). This is your unit cost; freemium math
  depends on it. Cache derived context by document fingerprint to cut repeat cost.
- **Infra:** managed Postgres + Redis + object storage + a worker host + an EU
  region. Modest at small scale, but real and recurring.
- **The free tier is a direct cost center** — gate it (one free plan, then pay)
  or abuse will run up your provider bill. Per-user quotas from day one.

---

## 8. Explicitly NOT building (and the trigger that changes it)

| Deferred | Trigger to revisit |
|---|---|
| Self-hosted private LLM tier | A university deal blocks on no-third-party-LLM |
| Drag-to-reschedule "what-if" editor | Users ask to edit, not just regenerate |
| Multi-university handbook ingestion at scale | A second institution actually onboards |
| Mobile app (native) | Web analytics show heavy mobile + retention |
| Real-time collaboration / advisor co-editing | A B2B pilot asks for advisor-in-the-loop |

---

## 9. Decisions — LOCKED (2026-06-14)

1. **Strategy: separate product, shared account/billing backend.** Standalone
   app/URL, reusing one identity+billing+career-gap backend (the FastAPI/JWT/
   React/Docker you already own from resume-automation).
2. **Phase 0 market: pure student elective planner.** *Honest caveat carried
   forward:* this is the weakest segment for direct monetization (broke users,
   ~once-a-year use). Phase 0 therefore probes willingness-to-pay explicitly and
   tests the **university/department as the likely actual buyer** even though the
   tool is student-facing. If the WTP signal is weak but a department shows
   interest, the market pivots to B2B2C without changing the product.
3. **Sequencing: validate first (Phase 0).** No multi-user infra until the
   demand gate passes.

---

## 10. Phase 0 — detailed build plan (the approved next step)

**Goal / definition of done:** prove students will sign up and complete a plan,
and surface a willingness-to-pay (or university-interest) signal — *before* any
multi-user build.

**Success gate (timebox: 2 weeks from launch):**
- ≥ **100 waitlist signups** from non-friends (student subreddits, university
  Discord/Telegram/course channels, LinkedIn student groups).
- ≥ **30 completed plans** in the gated demo (upload → plan generated).
- ≥ **a clear WTP signal:** e.g. ≥15% pick a non-zero price in the post-plan
  probe, **or** ≥1 department/advisor replies "let's pilot this."
- **Miss the gate → stop and re-pitch/re-target (likely toward B2B2C); do not
  start Phase 1.**

### Components

| # | Component | Tech | Notes |
|---|---|---|---|
| 0.1 | **Landing page** + waitlist email capture | Static page on Vercel (you already host there) | Value prop, sample-plan screenshot, email field, a fake-door "Pricing" probe |
| 0.2 | **Gated demo** (single-tenant, throwaway) | **Streamlit** — fast, disposable, right tool for validation | Email-gate → upload transcript+handbook+goal → run existing crew → show plan + validity badges |
| 0.3 | **Privacy-minimal processing** | Ephemeral | **No persistence:** in-memory only, never write user PDFs to disk/DB, delete on session end, explicit disclaimer + "third-party LLM" notice. Lowest-risk way to touch real transcripts pre-GDPR-build |
| 0.4 | **Instrumentation** | Plausible/PostHog (privacy-friendly) + event logging | Track signups, demo starts, parse-preview confirms, completed plans, drop-off |
| 0.5 | **Willingness-to-pay probe** | Post-plan micro-survey | "Would you pay for re-plans/export? €0/€3/€5/€9" + optional "are you an advisor? pilot?" capture |
| 0.6 | **Deterministic validator (FUTURE.md 1.1)** | Python, ~80 lines | Pulled forward: powers the demo's "validity badges" = the trust moment that makes the demo credible |

### What I can start locally now (reversible, nothing public)
- 0.2 Streamlit gated demo wrapping the existing crew (runs locally / throwaway host).
- 0.6 the validator + structured module output (also de-risks Phase 1).
- 0.1 landing-page copy + a deployable static page (you push to Vercel).
- 0.5 the survey + 0.4 event logging.

### What needs *you* (outward-facing — your accounts/decisions)
- Domain / Vercel project for the landing page.
- A throwaway host for the Streamlit demo (Streamlit Community Cloud or HF
  Space) — this sends demo transcripts to that host + the LLM provider, so the
  disclaimer (0.3) is mandatory and you approve the wording.
- The distribution push (where you post the waitlist link).
- Final WTP price points and the success-gate numbers above.

### Phase 0 verification
A non-friend can: land → sign up → open the demo → upload → get a validated plan
→ answer the WTP probe, with every step logged. Then read the funnel vs. the gate.

---

## 11. Open decisions for Phase 0 kickoff

1. Approve the **Streamlit throwaway demo** (vs. a longer React+FastAPI mini-app)?
2. Approve **ephemeral, no-storage** processing for the demo (vs. building real
   storage now)?
3. Want me to **start the local pieces now** (0.6 validator first, then 0.2 demo,
   0.1 copy, 0.5 survey) while you sort hosting/domain?
