"""Eval harness: run the real crew on a data folder, save every artifact, and
print the deterministic validator verdict. Lets us iterate on plan quality with
a measurable gate instead of eyeballing (playbook: eval script before tuning).

    python scripts/run_eval.py <data_dir> <label> [target_semesters]

Writes outputs/eval_<label>/{plan,profile,catalog,available,gaps,validation}.md
and prints an "=== EVAL RESULT <label> ===" block (validator summary + areas).
"""
import sys
import json
import pathlib

from study_planner.main import plan_studies, _dump_artifacts, force_utf8_stdout
from study_planner.inputs import PlanConstraints

force_utf8_stdout()  # non-cp1252 chars in inputs must not crash the run on Windows

data_dir = sys.argv[1] if len(sys.argv) > 1 else "data"
label = sys.argv[2] if len(sys.argv) > 2 else "run"
target_sem = int(sys.argv[3]) if len(sys.argv) > 3 else 4

constraints = PlanConstraints(target_semesters=target_sem)

print(f"=== RUNNING EVAL {label} (data={data_dir}, target_semesters={target_sem}) ===",
      flush=True)
res = plan_studies(data_dir, save_report=False, validate=True, constraints=constraints)

out = pathlib.Path("outputs") / f"eval_{label}"

val = res["validation"]
val_text = val.summary() if val else "(no validation)"
sections = {
    "plan.md": res["study_plan"],
    "profile.md": res["profile"],
    "catalog.md": res["module_catalog"],          # raw curator output
    "available.md": res.get("available_modules", ""),  # Python-normalized table
    "gaps.md": res["skill_gaps"],
    "validation.md": val_text,
}
if val:
    sections["stats.json"] = json.dumps(val.stats, indent=2)
_dump_artifacts(out, sections)

print(f"\n=== EVAL RESULT {label} ===", flush=True)
print(val_text, flush=True)
print(f"\nartifacts: {out.resolve()}", flush=True)
