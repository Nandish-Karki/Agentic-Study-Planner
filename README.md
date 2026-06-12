# Agentic Study Planner

> OvGU Workshop AgenticAI — Group Work · June 2026

A multi-agent study planner built with **CrewAI**. It reads a student's CV, academic transcript, target career path, and the university module handbook — all real PDFs — and generates a **personalized semester-wise study plan**.

---

## How it works

Five agents follow the workshop's *model-driven agentification* approach: three parallel analyses feeding a two-stage synthesis.

```
profile_analyst   ── reads cv.pdf + transcript.pdf ──┐
career_analyst    ── reads career.pdf ───────────────┤
module_curator    ── reads module_handbook.pdf ──────┤
                                                     ▼
gap_analyst         profile vs. career → prioritized skill gaps
                                                     ▼
study_planner       semester-wise plan (~30 ECTS/semester,
                    prerequisites respected, gaps closed first)
```

Output: `outputs/study_plan.md` — semester tables with credits and per-module justifications, plus the skill-gap analysis.

**Grounding design:** the two synthesis agents (`gap_analyst`, `study_planner`) have **no tools** — they can only reason over what the three analyst agents extracted from the real documents. The planner is explicitly constrained to modules from the curator's catalog, so it cannot invent coursework.

## Quickstart

```powershell
# 1. Python 3.10 venv (CrewAI deps have no Python 3.14 wheels on Windows)
py -3.10 -m venv .venv
.\.venv\Scripts\pip install -e .

# 2. Keys
copy .env.example .env    # then fill in GITHUB_TOKEN or GROQ_API_KEY

# 3. Input documents → data/   (see data/README.md for expected filenames)
#    cv.pdf, transcript.pdf, career.pdf, module_handbook.pdf

# 4. Run
$env:PYTHONUTF8 = "1"
.\.venv\Scripts\python -m study_planner.main data
```

## Use from another project

```python
from study_planner import plan_studies

result = plan_studies("path/to/data")
print(result["study_plan"])    # semester-wise plan (Markdown)
print(result["skill_gaps"])    # prioritized gap analysis
print(result["report_path"])   # saved outputs/study_plan.md
```

## Project structure

```
agentic-study-planner/
├── src/study_planner/
│   ├── main.py                  # CLI + plan_studies() public API
│   ├── crew.py                  # @CrewBase crew, LLM provider switch, litellm patches
│   ├── config/
│   │   ├── agents.yaml          # 5 agent definitions
│   │   └── tasks.yaml           # 5 tasks with output constraints + context chains
│   └── tools/pdf_tools.py       # read_document, search_document, list_input_files
├── data/                        # input PDFs (gitignored — personal documents)
├── outputs/study_plan.md        # generated plan (gitignored)
├── spike_pdf.py                 # standalone PDF-extraction verification
└── test_llm.py                  # standalone LLM-provider verification
```

## LLM configuration

Set `LLM_PROVIDER` in `.env`:

| Provider | Models | Notes |
|---|---|---|
| `github` (default) | gpt-4o-mini (analysts) / gpt-4o (synthesis) | Needs `GITHUB_TOKEN` with `models:read` |
| `groq` | llama-3.3-70b-versatile | Free tier: 12k tokens/request, 100k/day |

The resolved provider and models are printed at startup (`[llm config] …`) so a misconfigured `.env` is visible immediately.

## Tech stack

CrewAI 1.14 · LiteLLM · pypdf · Python 3.10

## Author

Nandish Karki — M.Sc. Data & Knowledge Engineering, OvGU Magdeburg
