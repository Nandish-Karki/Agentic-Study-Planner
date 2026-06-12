# Workshop Distribution Plan — let every student run the Agentic Study Planner

**Status: DRAFT — awaiting approval. Nothing below has been executed.**

## Goal & what "done" looks like

Every student in the OvGU AgenticAI workshop can clone the project, run it end-to-end
within ~10 minutes on their own laptop, and see a generated study plan — first on bundled
sample data, then optionally on their own documents. **Done is proven** when at least one
person who is not the author completes a fresh-clone run without help.

This is achievable, and it doubles as the **User Evaluation stage** of the
process-driven lifecycle — their feedback is the "Impact" edge of the cycle.

## Recommended approach: GitHub repo + sample data + bring-your-own free token

Each student already has a GitHub account, and a GitHub Models token
(`models:read` scope) is **free** — so every student gets their own LLM quota and
nobody shares keys. This beats a hosted demo for a workshop: zero hosting cost,
no shared-quota collapse when 20 students run at once, and personal PDFs never
leave their machines.

A hosted Streamlit demo is listed as an optional Phase F — not recommended as the
primary route (shared API quota, privacy of uploaded personal documents).

---

## Phase A — Repo safety audit (before anything goes public)

| Step | Action | Verification |
|---|---|---|
| A1 | Scan **entire git history** for secrets: `git log -p \| grep` for token patterns (`ghp_`, `gsk_`, `sk-`), plus check no real PDF was ever committed | Zero hits; `git log --all --name-only` shows no `data/*.pdf` |
| A2 | Confirm `.gitignore` covers `.env`, `data/*.pdf`, `outputs/` (it does today) | Visual check |
| A3 | Add a `LICENSE` (MIT) so students may legally use/modify it | File exists |

**Risk if skipped:** a leaked token or a committed personal transcript is unrecoverable
once the repo is public. This phase is non-negotiable.

## Phase B — Synthetic sample data pack

Students must be able to test **without** their own documents (privacy + speed).

| Step | Action |
|---|---|
| B1 | Write `scripts/make_sample_data.py` (fpdf2/reportlab) generating four fictional PDFs into `sample_data/`: CV + transcript of an invented student ("Alex Beispiel", 2 semesters DKE), a target-career one-pager (Data Engineer), and a mini module handbook (~10 real-looking OvGU-style modules with CP, semester, prerequisites) |
| B2 | Commit the generated PDFs (they're synthetic — safe to publish) |
| B3 | Run the full crew on `sample_data/` and read the output plan end-to-end |

**Verification gate:** the sample run produces a grounded plan (only handbook modules,
~30 CP/semester). This output gets committed as `sample_data/expected_output_example.md`
so students know what success looks like.

## Phase C — Frictionless setup

| Step | Action |
|---|---|
| C1 | `setup.ps1` + `setup.sh`: create Python 3.10 venv, `pip install -e .`, copy `.env.example` → `.env` if missing, print "now add your token" |
| C2 | Preflight command `python -m study_planner.check`: Python version OK? deps import? token present and valid (1-token test call)? input files found? — every failure prints a *specific* fix instruction |
| C3 | README: add a "Workshop quickstart" section — 5 numbered steps including exact clicks to create a GitHub Models token, and a Troubleshooting table (Python 3.14 wheel issue, missing token, UTF-8 on Windows, Groq fallback) |

**Why:** the Playbook rule — "if it takes more than one command to start, it will be
mis-started weekly." For 20 students, every manual step is 20 support questions.

## Phase D — Publish & fresh-clone proof

| Step | Action | Verification |
|---|---|---|
| D1 | Create public GitHub repo `agentic-study-planner` under your account (`gh repo create`), push `master` | Repo visible |
| D2 | **Fresh-clone test:** clone into a clean temp dir on this machine, follow only the README, run on sample data | End-to-end plan generated using zero knowledge outside the README |
| D3 | Fix every snag found in D2, push, repeat until clean | Second fresh clone runs clean |

## Phase E — Share & collect evaluation

| Step | Action |
|---|---|
| E1 | Short announcement message for the workshop channel (drafted for your review): repo link + the 5-step quickstart + "try sample data first, then your own PDFs" |
| E2 | Feedback rubric as a GitHub issue template (and/or Google Form): ① Did it run? ② Open the plan — is every module really in the handbook? ③ Would you follow this plan? ④ What's wrong/missing? |
| E3 | After the workshop: summarize feedback → feeds Model Analysis of the next lifecycle iteration (and `FUTURE.md` priorities) |

## Phase F (optional, NOT recommended initially) — Hosted demo

Streamlit Community Cloud or HF Space with file upload. Deferred because:
your single API key would be shared by all students (quota collapse),
and students would upload personal documents to a third-party host (privacy).
Trigger to revisit: workshop feedback says local setup is too hard.

---

## Effort & order

A → B → C → D → E, roughly one working session for A–D, E is minutes.
Phases are committed individually (Playbook: commit working features same day).

## Risks

| Risk | Mitigation |
|---|---|
| Student has no Python 3.10 | README links the exact installer; `py -3.10` check in preflight |
| GitHub Models token confusion | Click-by-click token instructions + preflight validates the token before any run |
| Free-tier rate limits mid-run | Already handled: retry-with-wait patch in `crew.py`; Groq documented as fallback |
| macOS/Linux students | `setup.sh` + UTF-8 note (Windows-only env var) |
| Personal data anxiety | Sample data first; `data/` gitignored; explicit "your PDFs never leave your machine" note |

## Approval needed for

1. Making the repo **public** under your GitHub account (vs. private + invited collaborators — say which).
2. MIT license OK?
3. Include Phase F (hosted demo) now, or defer as written?

Reply with approval (and answers to the three points) and execution starts at Phase A.
