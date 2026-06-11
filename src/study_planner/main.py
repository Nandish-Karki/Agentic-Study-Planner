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


def plan_studies(data_dir: str = "data", save_report: bool = True) -> dict:
    """
    Run the 5-agent study-planner crew on a folder of input documents.

    Expects in data_dir: cv.pdf, transcript.pdf, career.pdf, module_handbook.pdf

    Returns:
        {
          "study_plan":  str  — semester-wise plan (Markdown)
          "skill_gaps":  str  — prioritized gap analysis (Markdown)
          "report_path": str | None — path to saved outputs/study_plan.md
        }
    """
    # Import here so load_dotenv() runs before crew.py module-level config
    from study_planner.crew import StudyPlannerCrew

    data = pathlib.Path(data_dir).resolve()
    if not data.exists():
        raise FileNotFoundError(f"Input folder not found: {data}")

    result = StudyPlannerCrew().crew().kickoff(inputs={"data_dir": str(data)})

    # task order: profile(0) career(1) modules(2) gap(3) plan(4)
    skill_gaps = result.tasks_output[3].raw
    study_plan = result.tasks_output[4].raw

    report_path = None
    if save_report:
        out_dir = pathlib.Path(__file__).parent.parent.parent / "outputs"
        out_dir.mkdir(exist_ok=True)
        out_file = out_dir / "study_plan.md"
        report = (
            f"# Personalized Study Plan\n\n"
            f"**Inputs:** `{data}`\n\n"
            f"---\n\n{study_plan}\n\n---\n\n"
            f"# Skill Gap Analysis\n\n{skill_gaps}\n"
        )
        out_file.write_text(report, encoding="utf-8")
        report_path = str(out_file.resolve())

    return {"study_plan": study_plan, "skill_gaps": skill_gaps, "report_path": report_path}


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
    if result["report_path"]:
        print(f"Full report saved to: {result['report_path']}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
