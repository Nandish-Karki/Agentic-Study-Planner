"""
Phase 0 validation demo — gated, throwaway Streamlit app.

Purpose (see docs/PRODUCT_PLAN.md §10): let a real student upload their
documents, get a validated study plan, and answer a willingness-to-pay probe —
so we can measure demand BEFORE building the multi-user product.

Privacy posture (Phase 0, pre-GDPR-build):
  * Uploaded PDFs are written to a per-session TEMP dir and DELETED immediately
    after the run. They are never persisted to disk or a database by this app.
  * They ARE sent to the configured third-party LLM provider for processing —
    this is disclosed up front and the user must consent.
  * Only anonymous funnel EVENTS (+ the email they volunteer, + their WTP answer)
    are logged to events.jsonl — never document contents or the generated plan.

Run:  .venv/Scripts/python -m streamlit run demo/app.py
"""
import json
import os
import re
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

# make the package importable when run via `streamlit run demo/app.py`
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
load_dotenv()

EVENTS_FILE = Path(__file__).parent / "events.jsonl"
SAMPLE_DIR = Path(__file__).parent.parent / "sample_data"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "github")

st.set_page_config(page_title="Study Planner — demo", page_icon="🎓", layout="centered")


# ─── event logging (funnel only — never document content) ──────────────────────

def log_event(event: str, **fields):
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "session": st.session_state.session_id,
        "event": event,
        **fields,
    }
    try:
        with EVENTS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass  # logging must never break the demo


def _valid_email(s: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", s or ""))


# ─── session state ─────────────────────────────────────────────────────────────

ss = st.session_state
ss.setdefault("session_id", uuid.uuid4().hex[:12])
ss.setdefault("stage", "gate")        # gate → upload → results → done
ss.setdefault("email", "")
ss.setdefault("result", None)


# ─── stage 1: email gate + consent + disclaimer ────────────────────────────────

def render_gate():
    st.title("🎓 Personalized Study Planner")
    st.caption("Upload your transcript, module handbook, and target role — five AI "
               "agents draft a semester-by-semester plan that closes your skill gaps.")

    st.info(
        "**This is an early demo.** We're testing whether this is worth building "
        "for real. Two minutes of your time tells us a lot — thank you.",
        icon="🧪",
    )

    with st.expander("🔒 How your documents are handled (please read)", expanded=True):
        st.markdown(
            f"""
- Your uploaded files are processed **in memory and deleted immediately** after
  your plan is generated. This app does **not** store them.
- To generate the plan, your documents' **text is sent to a third-party AI
  provider** (`{LLM_PROVIDER}`) for processing.
- We log only **anonymous usage events**, the **email** you enter below, and your
  **feedback answer** — never your documents or your plan.
- Prefer not to upload personal files? Use **“Try with sample data”** on the next
  screen — a fictional student, no real data needed.
            """
        )

    email = st.text_input("Your email (so we can tell you when it launches)",
                          value=ss.email, placeholder="you@university.edu")
    consent = st.checkbox(
        "I understand my documents will be sent to a third-party AI provider to "
        "generate my plan, and are not stored by this app.")

    if st.button("Continue →", type="primary", disabled=not (email and consent)):
        if not _valid_email(email):
            st.error("That doesn't look like a valid email.")
            return
        ss.email = email
        ss.stage = "upload"
        log_event("signup", email=email)
        st.rerun()


# ─── stage 2: upload (or sample) + run ─────────────────────────────────────────

def _pdf_preview(uploaded) -> str:
    from pypdf import PdfReader
    try:
        n = len("".join(p.extract_text() or "" for p in PdfReader(uploaded).pages))
        uploaded.seek(0)
        if n < 50:
            return "⚠️ almost no text — is this a scanned image PDF?"
        return f"✓ {n:,} characters of text found"
    except Exception as e:
        return f"⚠️ could not read: {e}"


def _run_plan(data_dir: str):
    from study_planner.main import plan_studies
    return plan_studies(data_dir, save_report=False, validate=True)


def render_upload():
    st.title("Your documents")
    st.caption("Transcript, module handbook, and target role are required. "
               "CV is optional. PDFs only.")

    use_sample = st.toggle("Try with sample data (fictional student — no upload)")

    if use_sample:
        st.success("Using the bundled sample student. No personal data needed.")
        if st.button("Generate my study plan →", type="primary"):
            log_event("demo_start", mode="sample")
            _generate(str(SAMPLE_DIR))
        return

    cols = st.columns(2)
    transcript = cols[0].file_uploader("Transcript* (PDF)", type="pdf")
    handbook = cols[1].file_uploader("Module handbook* (PDF)", type="pdf")
    cols2 = st.columns(2)
    career = cols2[0].file_uploader("Target role / career* (PDF)", type="pdf")
    cv = cols2[1].file_uploader("CV (PDF, optional)", type="pdf")

    # parse-preview: cheap confirmation that we read the right files (no LLM)
    for label, up in [("Transcript", transcript), ("Handbook", handbook),
                      ("Career", career), ("CV", cv)]:
        if up is not None:
            st.caption(f"**{label}:** {_pdf_preview(up)}")

    ready = transcript and handbook and career
    if st.button("Generate my study plan →", type="primary", disabled=not ready):
        log_event("demo_start", mode="upload")
        tmp = Path(tempfile.mkdtemp(prefix="sp_demo_"))
        try:
            (tmp / "transcript.pdf").write_bytes(transcript.getvalue())
            (tmp / "module_handbook.pdf").write_bytes(handbook.getvalue())
            (tmp / "career.pdf").write_bytes(career.getvalue())
            # CV is optional; the profile task reads it if present, tolerates absence
            if cv is not None:
                (tmp / "cv.pdf").write_bytes(cv.getvalue())
            else:
                (tmp / "cv.pdf").write_bytes(transcript.getvalue())  # fallback
            _generate(str(tmp))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)   # ephemeral: always delete


def _generate(data_dir: str):
    with st.spinner("Five agents are reading your documents and drafting a plan — "
                    "this takes 1–2 minutes…"):
        try:
            ss.result = _run_plan(data_dir)
            ss.stage = "results"
            v = ss.result.get("validation")
            log_event("plan_completed",
                      ok=(v.ok if v else None),
                      errors=(len(v.errors) if v else None))
            st.rerun()
        except Exception as e:
            log_event("plan_error", error=str(e)[:200])
            st.error(f"Something went wrong generating the plan: {e}")


# ─── stage 3: results + validity badges ────────────────────────────────────────

def render_results():
    res = ss.result
    val = res.get("validation")

    st.title("Your study plan")

    if val is not None:
        if val.ok:
            st.success("✅ **Validated** — the plan satisfies all hard rules "
                       "(every module is real, no retakes, credit totals add up, "
                       "limits respected).", icon="✅")
        else:
            st.warning(f"⚠️ **{len(val.errors)} rule issue(s) found** — the AI broke "
                       "a constraint. We catch these automatically so you don't "
                       "follow a broken plan:", icon="⚠️")
            for f in val.errors:
                st.markdown(f"- **{f.rule}:** {f.message}")
        if val.warnings:
            with st.expander(f"{len(val.warnings)} softer warning(s)"):
                for f in val.warnings:
                    st.markdown(f"- **{f.rule}:** {f.message}")

    st.markdown("---")
    st.markdown(res["study_plan"])

    with st.expander("Skill-gap analysis"):
        st.markdown(res["skill_gaps"])

    st.download_button("⬇️ Download plan (Markdown)",
                       data=res["study_plan"], file_name="study_plan.md")

    st.markdown("---")
    render_survey()


# ─── stage 4: willingness-to-pay probe (the Phase 0 signal) ────────────────────

def render_survey():
    st.subheader("Two quick questions (this decides whether we build it)")
    with st.form("wtp"):
        would_use = st.radio("Would you actually use this to plan your semesters?",
                             ["Yes", "Maybe", "No"], horizontal=True, index=1)
        price = st.radio(
            "What would you pay for unlimited re-plans + PDF/calendar export?",
            ["€0 — free only", "€3", "€5", "€9", "More"], horizontal=True, index=0)
        advisor = st.text_input(
            "Are you a study advisor / work at a university? Leave an email to "
            "talk about a pilot (optional):", placeholder="optional")
        comment = st.text_area("Anything wrong with the plan, or missing? (optional)")
        if st.form_submit_button("Submit feedback", type="primary"):
            log_event("wtp_response", would_use=would_use, price=price,
                      advisor_contact=advisor.strip(), comment=comment.strip()[:500])
            ss.stage = "done"
            st.rerun()


def render_done():
    st.title("🙏 Thank you")
    st.markdown("Your feedback is logged. We'll email you at "
                f"**{ss.email}** if this becomes a real product.")
    st.balloons()
    if st.button("Plan another (start over)"):
        for k in ("stage", "result"):
            ss.pop(k, None)
        ss.stage = "gate"
        st.rerun()


# ─── router ────────────────────────────────────────────────────────────────────

PAGES = {"gate": render_gate, "upload": render_upload,
         "results": render_results, "done": render_done}
PAGES.get(ss.stage, render_gate)()
