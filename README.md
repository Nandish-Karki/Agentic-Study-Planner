# Agentic Study Planner


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

**Grounding design:** the two synthesis agents (`gap_analyst`, `study_planner`) have **no tools** — they can only reason over what the three analyst agents extracted from the real documents. This grounds them in *provenance*: the planner's module vocabulary is limited to the curator's catalog, so it won't pull a module out of thin air.

What this does **not** guarantee is *constraint compliance* — being tool-less stops the planner inventing modules, but it does not force it to obey every rule in its context (e.g. a "take at most twice" limit). LLMs still violate such rules; see the known limitation noted in [sample_data/expected_output_example.md](sample_data/expected_output_example.md). The robust fix is a deterministic post-run validator that checks the plan in code, not just in the prompt — see [FUTURE.md](FUTURE.md) item 1.1.

## Workshop quickstart (5 steps, ~10 minutes)

Works out of the box with the bundled **synthetic sample data** (`sample_data/` — a
fictional student, safe to share). Your own PDFs come later and never leave your machine.

1. **Clone** the repo and open a terminal in it.
2. **Get a free LLM token** (pick one):
   - *GitHub Models (recommended):* GitHub → Settings → Developer settings →
     [Fine-grained personal access tokens](https://github.com/settings/personal-access-tokens) →
     Generate new token → under **Account permissions** set **Models: Read-only** → copy the `github_pat_…` token.
   - *Groq:* create a free key at [console.groq.com/keys](https://console.groq.com/keys), and set `LLM_PROVIDER=groq` in `.env`.
3. **Run setup** — `.\setup.ps1` (Windows) or `./setup.sh` (macOS/Linux).
   It creates the venv, installs dependencies, and creates `.env` from the template.
4. **Paste your token into `.env`**, then run setup again. It finishes with a
   preflight check — every line should say `[ OK ]`.
5. **Run it:**
   ```powershell
   $env:PYTHONUTF8 = "1"                                   # Windows only
   .\.venv\Scripts\python -m study_planner.main sample_data
   ```
   Watch the five agents work; the plan lands in `outputs/study_plan.md`.
   Compare with `sample_data/expected_output_example.md` to see what success looks like.

**Then try your own documents:** put `cv.pdf`, `transcript.pdf`, `career.pdf`,
`module_handbook.pdf` into `data/` (gitignored — they stay local) and run
`... -m study_planner.main data`.

### Troubleshooting

| Symptom | Fix |
|---|---|
| Anything fails | Run `.\.venv\Scripts\python -m study_planner.check sample_data` — every failure prints its specific fix |
| `pip install` fails resolving wheels | You're on Python 3.14 — install Python 3.10–3.13 and delete `.venv`, re-run setup |
| `401`/`permission` on LLM call | Token missing the **Models: Read-only** scope (GitHub) or expired — regenerate, update `.env` |
| `UnicodeEncodeError` on Windows | Set `$env:PYTHONUTF8 = "1"` before running |
| Rate-limit messages mid-run | Normal on free tiers — the run waits and retries automatically. Persistent? Switch `LLM_PROVIDER=groq` (or back) |
| Garbage module table | Your handbook PDF has no text layer (scanned). Export a text-based PDF |

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
│   ├── check.py                 # preflight check: python -m study_planner.check
│   ├── config/
│   │   ├── agents.yaml          # 5 agent definitions
│   │   └── tasks.yaml           # 5 tasks with output constraints + context chains
│   └── tools/pdf_tools.py       # read_document, search_document, list_input_files
├── sample_data/                 # synthetic test PDFs (fictional student — committed)
├── scripts/make_sample_data.py  # regenerates sample_data/
├── setup.ps1 / setup.sh         # one-command setup + preflight
├── data/                        # YOUR input PDFs (gitignored — personal documents)
├── outputs/study_plan.md        # generated plan (gitignored)
├── docs/                        # lifecycle verification (LaTeX) + distribution plan
├── FUTURE.md                    # roadmap: validators, metrics, UI
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
