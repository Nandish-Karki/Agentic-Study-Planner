# Phase 0 Validation Demo

A throwaway Streamlit app to **measure demand before building the product**
(see `docs/PRODUCT_PLAN.md` §10). A student uploads their documents (or uses
sample data), gets a validated study plan, and answers a willingness-to-pay
probe. We read the funnel with `funnel.py`.

## Run locally

```powershell
.\.venv\Scripts\pip install -e ".[demo]"     # installs streamlit
copy .env.example .env                         # add GITHUB_TOKEN or GROQ_API_KEY
$env:PYTHONUTF8 = "1"
.\.venv\Scripts\python -m streamlit run demo/app.py
```

Open the printed Local URL. Try **“Try with sample data”** first — no upload needed.

## Read the results (the Phase 0 gate)

```powershell
.\.venv\Scripts\python demo/funnel.py
```

Prints unique signups, completed plans, validator pass rate, and the
willingness-to-pay breakdown against the success gate (≥100 signups, ≥30 plans,
≥15% non-zero price / a pilot lead).

## Deploy (throwaway host) — Streamlit Community Cloud

1. Push this repo to GitHub (it already is, or will be).
2. On [share.streamlit.io](https://share.streamlit.io): New app → pick the repo →
   main file `demo/app.py`.
3. **Secrets** (App → Settings → Secrets) — paste your LLM credentials, e.g.:
   ```toml
   LLM_PROVIDER = "github"
   GITHUB_TOKEN = "github_pat_..."
   ```
   Streamlit exposes these as environment variables, which `app.py` reads via
   `load_dotenv()` + `os.getenv`. **Never commit real tokens.**
4. Share the URL in student channels (the waitlist link from the landing page can
   point here, or vice-versa).

## Privacy posture (important — this is pre-GDPR-build)

- Uploaded PDFs are written to a per-session temp dir and **deleted immediately**
  after the run. The app never persists them.
- Document text **is sent to the third-party LLM provider** to generate the plan.
  This is disclosed in-app and the user must consent before uploading.
- `events.jsonl` logs only funnel events + the volunteered email + the feedback
  answer — **never** document contents or the plan. It is **gitignored**.
- This is acceptable for a short validation demo. Real storage, encryption,
  erasure, and a DPA come in Phase 2/4 — do **not** turn this demo into the
  product.

## What this demo is NOT

- Not multi-user, not authenticated, not persistent. One run at a time; the
  60–120s synchronous crew call blocks the session (a job queue is Phase 1).
- A throwaway. If Phase 0 passes, the real app is built fresh per the product plan.
