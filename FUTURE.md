# Future Work — Agentic Study Planner

> Roadmap derived from verifying the project against the workshop's
> process-driven agentification lifecycle (see `docs/process_model_verification.tex`).
> The forward half of the cycle (Redesign → Agentification) is solid;
> everything below exists to **close the loop**: Evaluation → Monitoring → next Analysis.

## 1. Close the loop (highest priority)

### 1.1 Deterministic plan validator (eval harness)
The plan's hard rules currently live only in the prompt. Per the
defense-in-depth rule, enforce them a second time in code — a
`validate_plan.py` that checks, after every run:

- every module in the plan appears in the curator's module table (grounding check)
- no planned module appears in the transcript's completed list (no re-takes)
- per-semester CP totals are arithmetically correct and within 24–33 ECTS
- prerequisites of each planned module are completed or scheduled earlier

Output: a pass/fail report with named violations. Advisory first, blocking later.
This turns "the plan looks good" into a measurable number per run.

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
