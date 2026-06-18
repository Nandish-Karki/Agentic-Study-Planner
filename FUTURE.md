# Future Work — Agentic Study Planner

> Roadmap derived from verifying the project against the workshop's
> process-driven agentification lifecycle (see `docs/process_model_verification.tex`).
> The forward half of the cycle (Redesign → Agentification) is solid;
> everything below exists to **close the loop**: Evaluation → Monitoring → next Analysis.

## 1. Close the loop (highest priority)

### 1.1 Deterministic plan validator (eval harness) — ✅ DONE
Implemented in `src/study_planner/validate.py`, wired into `plan_studies`
(returns a `ValidationReport`) and surfaced in the CLI + Streamlit demo as
pass/fail badges. Checks, in code, after every run:

- every module in the plan appears in the curator's module table (grounding) — ERROR
- no planned module appears in the transcript's completed list (no re-takes) — ERROR
- per-semester CP totals are arithmetically correct (ERROR) and within band (WARNING)
- module take-limits ("at most twice") respected — ERROR
- prerequisites of each planned module are completed or scheduled earlier — WARNING

Markdown tables are parsed by column header (not position) and module names
matched fuzzily (difflib) so LLM formatting/abbreviation drift doesn't false-flag.
13 unit + integration tests in `tests/test_validate.py`. In live runs it has
already caught two distinct hallucination classes the prompt failed to prevent:
a take-limit violation and an invented "Elective" module.

**Remaining:** flip from advisory to blocking (re-plan loop on ERROR) — best done
in Phase 1 as a LangGraph-style validate→replan edge, or a bounded retry in the worker.

### 1.2 Run metrics sidecar (Monitoring stage)
Write `outputs/run_metrics.json` per run: per-task latency, model used,
token counts, retry count, validator score. A run history makes
"did this prompt change help?" answerable with numbers instead of vibes.

### 1.3 Independent user evaluation (User Evaluation stage)
Distribute to workshop students (see `docs/WORKSHOP_DISTRIBUTION_PLAN.md`)
with a 4-question feedback rubric: Did it run? Is every module real?
Would you follow this plan? What's wrong with it?
Collected feedback = the "Impact" edge of the lifecycle.

## 2. Robustness

- **Structured outputs:** the module table is free-form Markdown today; a Pydantic
  `output_pydantic` model for `modules_task` would make the validator (1.1) trivial
  and stop table-format drift between runs.
- **Input flexibility:** tolerate filename variants (`CV.pdf`, `lebenslauf.pdf`) via
  `list_input_files` + a small routing step; support `.txt`/`.md` inputs for testing.
- **Large handbooks:** the chunked `read_document`/`search_document` approach works for
  the current handbook; for 300+ page handbooks, add an embedding index (RAG) so the
  curator retrieves rather than pages through chunks.
- **Provider fallback chain:** on persistent 429/auth failure on one provider,
  automatically fall back to the other (github ⇄ groq) and mark the run as degraded.

## 3. Usability

- **Streamlit upload-and-run UI:** drag in four PDFs, watch agent progress, download the
  plan. Prerequisite for any hosted demo.
- **One-command start:** `run.ps1` / `run.sh` that activates the venv, checks `.env`,
  and runs the crew (Playbook Phase 0 rule — currently it takes 3 commands).
- **Preflight check:** `python -m study_planner.check` — Python version, deps importable,
  API key valid (1-token test call), all four input files present and parseable.
- **Real transactional email (verification + password reset).** Code is already in
  place but dormant: `api/email.py` sends via the **Resend HTTP API** when
  `RESEND_API_KEY` is set (HTTPS — needed because Render's free tier blocks outbound
  SMTP: `[Errno 101] Network is unreachable`), else falls back to SMTP. To turn it on
  for public users you only need (no code change): (1) own a domain, (2) verify it in
  Resend (add the SPF/DKIM DNS records), (3) set `RESEND_API_KEY` + `SMTP_FROM=…@yourdomain`
  on Render, (4) set `DEBUG=0`. Until then the app runs with `DEBUG=1`, which returns the
  verify link in the signup response and shows a "Verify now" button — fine for the
  operator/demo, not for arbitrary strangers. `onboarding@resend.dev` works as an interim
  sender but only delivers to your own Resend account email.

## 4. Process-model formalization (report material)

- Draw the **as-is BPMN** (manual study planning) and **to-be BPMN** (agentified flow)
  to fully satisfy the Process Modelling stage formally, not just in prose.
- Quantify the as-is baseline once: how long does a student take to draft a
  semester plan by hand? That number is the headline "Impact" metric.

## 5. Explicitly NOT building (and the trigger that would change it)

| Deferred | Trigger to revisit |
|---|---|
| Multi-university handbook support | A second university's handbook is actually needed |
| Database/run-history persistence | More than ~20 evaluation runs to compare |
| Hosted multi-user web service | Workshop feedback says local setup is too hard |
| Critic/reviewer agent (6th agent) | Validator (1.1) shows recurring rule violations the prompt can't fix |
