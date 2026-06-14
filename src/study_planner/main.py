"""
Entry point for the Agentic Study Planner crew.

CLI:   python -m study_planner.main [data-dir]      (default: data)
API:   from study_planner import plan_studies
       result = plan_studies("data")
"""
import sys
import pathlib
from dotenv import load_dotenv

load_dotenv()


def plan_studies(data_dir: str = "data", save_report: bool = True,
                 validate: bool = True, constraints=None) -> dict:
    """
    Run the 5-agent study-planner crew on a folder of input documents.

    Expects in data_dir: cv.pdf, transcript.pdf, career.pdf, module_handbook.pdf

    `constraints` is an optional study_planner.inputs.PlanConstraints (target
    semesters + per-semester CP preferences). When None, a permissive default is
    used so existing callers keep working.

    Returns:
        {
          "study_plan":     str  — semester-wise plan (Markdown)
          "skill_gaps":     str  — prioritized gap analysis (Markdown)
          "module_catalog": str  — curator's module table (Markdown)
          "profile":        str  — student profile incl. completed modules
          "validation":     ValidationReport | None — deterministic rule check
          "report_path":    str | None — path to saved outputs/study_plan.md
        }
    """
    # Import here so load_dotenv() runs before crew.py module-level config
    from study_planner.crew import StudyPlannerCrew
    from study_planner.inputs import PlanConstraints

    if constraints is None:
        constraints = PlanConstraints()

    data = pathlib.Path(data_dir).resolve()
    if not data.exists():
        raise FileNotFoundError(f"Input folder not found: {data}")

    crew = StudyPlannerCrew().crew()
    result = crew.kickoff(inputs={
        "data_dir": str(data),
        "constraints": constraints.render_for_prompt(),
    })

    # Map each task's output by task name (robust to task reordering — never
    # index tasks_output by position). tasks_output is in crew.tasks order.
    by_name = {t.name: o.raw for t, o in zip(crew.tasks, result.tasks_output)}
    missing = {"gap_task", "plan_task"} - by_name.keys()
    if missing:
        raise RuntimeError(
            f"Crew finished but produced no output for: {sorted(missing)}. "
            f"Got outputs for: {sorted(by_name)}. A task likely failed mid-run."
        )
    skill_gaps = by_name["gap_task"]
    study_plan = by_name["plan_task"]
    module_catalog = by_name.get("modules_task", "")
    profile = by_name.get("profile_task", "")

    # Deterministic second layer: re-check the plan's hard rules in code
    # (prompt rules alone are not enough — see validate.py / FUTURE.md 1.1).
    validation = None
    if validate:
        from study_planner.validate import validate_plan
        validation = validate_plan(study_plan, module_catalog, profile, constraints)

    report_path = None
    if save_report:
        out_dir = pathlib.Path(__file__).parent.parent.parent / "outputs"
        out_dir.mkdir(exist_ok=True)
        out_file = out_dir / "study_plan.md"
        val_section = f"\n---\n\n# Plan Validation\n\n```\n{validation.summary()}\n```\n" \
            if validation else ""
        report = (
            f"# Personalized Study Plan\n\n"
            f"**Inputs:** `{data}`\n\n"
            f"---\n\n{study_plan}\n\n---\n\n"
            f"# Skill Gap Analysis\n\n{skill_gaps}\n"
            f"{val_section}"
        )
        out_file.write_text(report, encoding="utf-8")
        report_path = str(out_file.resolve())

    return {
        "study_plan": study_plan,
        "skill_gaps": skill_gaps,
        "module_catalog": module_catalog,
        "profile": profile,
        "validation": validation,
        "report_path": report_path,
    }


def main():
    data_dir = sys.argv[1] if len(sys.argv) > 1 else "data"
    print(f"\n{'='*60}")
    print(f"Agentic Study Planner — inputs: {data_dir}")
    print(f"{'='*60}\n")

    result = plan_studies(data_dir)

    print(f"\n{'='*60}")
    print("STUDY PLAN:\n")
    print(result["study_plan"])
    print(f"\n{'='*60}")
    if result.get("validation"):
        print("PLAN VALIDATION:\n")
        print(result["validation"].summary())
        print(f"{'='*60}")
    if result["report_path"]:
        print(f"Full report saved to: {result['report_path']}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
