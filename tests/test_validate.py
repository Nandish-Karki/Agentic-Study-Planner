"""
Unit + integration tests for the deterministic plan validator.

Run:  .venv/Scripts/python -m pytest tests/ -q
"""
import pathlib

from study_planner.validate import (
    validate_plan,
    parse_markdown_tables,
    parse_catalog,
    parse_area_budgets,
    parse_plan,
    parse_completed,
    _parse_take_limit,
    _best_match,
    build_correction,
    render_area_budget_table,
    ValidationReport,
    Finding,
)

# A small handbook mirroring sample_data, as the curator would emit it.
CATALOG_MD = """
| Module | CP | Semester offered | Key skills taught | Prerequisites |
|---|---|---|---|---|
| Advanced Databases | 6 | Winter | SQL, indexing | none |
| Machine Learning Foundations | 6 | Winter | supervised learning | none |
| Distributed Systems | 6 | Winter | replication | none |
| Cloud Computing | 6 | Winter | containers | none |
| Data Warehouse Technologies | 6 | Winter | OLAP, ELT | Advanced Databases |
| Stream Processing | 6 | Winter | Kafka, Flink | Big Data Engineering |
| Database Systems Implementation | 6 | Winter | storage engines | Advanced Databases |
| Data Mining I | 6 | Summer | clustering | none |
| Big Data Engineering | 6 | Summer | Spark, Airflow | Advanced Databases |
| Advanced Machine Learning | 6 | Summer | deep learning | Machine Learning Foundations |
| MLOps in Practice | 6 | Summer | CI/CD, model serving, MLflow | Machine Learning Foundations |
| Software Engineering for Data Science | 6 | Summer | CI/CD, agile | none |
| Data Visualization | 3 | Summer | dashboards | none |
| Scientific Team Project | 6 | Winter & Summer | teamwork | none; at most twice |
| Seminar Data Engineering | 3 | Winter & Summer | writing | none; at most twice |
| Master Thesis | 30 | Winter & Summer | research | 60 CP completed |
"""

PROFILE_MD = """
Programme: M.Sc. DKE.

| Module | CP | Grade |
|---|---|---|
| Advanced Databases | 6 | 1.7 |
| Machine Learning Foundations | 6 | 2.0 |
| Distributed Systems | 6 | 2.3 |
| Cloud Computing | 6 | 1.3 |
| Seminar Data Engineering | 3 | 1.0 |
"""


# ─── parsing ───────────────────────────────────────────────────────────────────

def test_parse_tables_by_header_not_position():
    t = parse_markdown_tables("| B | A |\n|---|---|\n| 2 | 1 |")[0]
    assert t.rows[0]["A"] == "1" and t.rows[0]["B"] == "2"


def test_parse_catalog_extracts_take_limit():
    cat = parse_catalog(CATALOG_MD)
    assert cat["scientific team project"].take_limit == 2
    assert cat["advanced databases"].take_limit is None
    assert cat["data warehouse technologies"].prerequisites.strip() == "Advanced Databases"


def test_parse_take_limit_word_and_digit():
    assert _parse_take_limit("none; at most twice") == 2
    assert _parse_take_limit("may be taken 3 times") == 3
    assert _parse_take_limit("Advanced Databases") is None


def test_parse_completed():
    done = parse_completed(PROFILE_MD)
    assert "Cloud Computing" in done and "Advanced Databases" in done
    assert len(done) == 5


def test_fuzzy_match_handles_abbreviation():
    cands = ["Software Engineering for Data Science", "Data Mining I"]
    m, score = _best_match("Software Engineering for Data", cands)
    assert m == "Software Engineering for Data Science" and score >= 0.86


# ─── checks (synthetic plans) ──────────────────────────────────────────────────

def _plan(*sem_bodies: str) -> str:
    out = []
    for i, body in enumerate(sem_bodies, 1):
        out.append(f"### Semester {i}\n\n{body}\n")
    return "\n".join(out)


def test_clean_plan_passes():
    plan = _plan(
        "| Module | CP | Why |\n|---|---|---|\n"
        "| Big Data Engineering | 6 | x |\n| Data Mining I | 6 | x |\n"
        "| Data Visualization | 3 | x |\n\n**Total CP:** 15",
    )
    rep = validate_plan(plan, CATALOG_MD, PROFILE_MD)
    assert rep.ok, rep.summary()


def test_hallucinated_module_flagged():
    plan = _plan(
        "| Module | CP | Why |\n|---|---|---|\n"
        "| Quantum Astrology 101 | 6 | x |\n\n**Total CP:** 6")
    rep = validate_plan(plan, CATALOG_MD, PROFILE_MD)
    assert not rep.ok
    assert any(f.rule == "grounding" for f in rep.errors)


def test_retake_of_completed_flagged():
    plan = _plan(
        "| Module | CP | Why |\n|---|---|---|\n"
        "| Cloud Computing | 6 | x |\n\n**Total CP:** 6")
    rep = validate_plan(plan, CATALOG_MD, PROFILE_MD)
    assert any(f.rule == "retake" for f in rep.errors), rep.summary()


def test_cp_arithmetic_mismatch_flagged():
    plan = _plan(
        "| Module | CP | Why |\n|---|---|---|\n"
        "| Big Data Engineering | 6 | x |\n| Data Mining I | 6 | x |\n\n"
        "**Total CP:** 20")   # real sum is 12
    rep = validate_plan(plan, CATALOG_MD, PROFILE_MD)
    assert any(f.rule == "cp-total" for f in rep.errors), rep.summary()


def test_take_limit_violation_flagged():
    body = "| Module | CP | Why |\n|---|---|---|\n| Scientific Team Project | 6 | x |\n\n**Total CP:** 6"
    plan = _plan(body, body, body)   # scheduled 3x, limit is 2
    rep = validate_plan(plan, CATALOG_MD, PROFILE_MD)
    assert any(f.rule == "take-limit" for f in rep.errors), rep.summary()


def test_prerequisite_not_met_warns():
    # Stream Processing needs Big Data Engineering, which is never scheduled.
    plan = _plan(
        "| Module | CP | Why |\n|---|---|---|\n"
        "| Stream Processing | 6 | x |\n\n**Total CP:** 6")
    rep = validate_plan(plan, CATALOG_MD, PROFILE_MD)
    assert any(f.rule == "prerequisite" for f in rep.warnings), rep.summary()


def test_prerequisite_scheduled_earlier_ok():
    plan = _plan(
        "| Module | CP | Why |\n|---|---|---|\n| Big Data Engineering | 6 | x |\n\n**Total CP:** 6",
        "| Module | CP | Why |\n|---|---|---|\n| Stream Processing | 6 | x |\n\n**Total CP:** 6",
    )
    rep = validate_plan(plan, CATALOG_MD, PROFILE_MD)
    assert not any(f.rule == "prerequisite" for f in rep.warnings), rep.summary()


# ─── area budgets ──────────────────────────────────────────────────────────────

CATALOG_WITH_AREAS = """
| Module | CP | Semester offered | Key skills taught | Prerequisites | Thematic Area |
|---|---|---|---|---|---|
| Advanced Databases | 6 | Winter | SQL | none | Fundamentals of Data Science |
| Machine Learning Foundations | 6 | Winter | ML | none | Fundamentals of Data Science |
| Big Data Engineering | 6 | Summer | Spark | Advanced Databases | Data Processing |
| Data Visualization | 3 | Summer | dashboards | none | Applied Data Science |
| Scientific Team Project | 6 | Winter & Summer | teamwork | none; at most twice | Applied Data Science |

| Thematic Area | Min CP | Max CP |
|---|---|---|
| Fundamentals of Data Science | 12 | 18 |
| Data Processing | 6 | 18 |
| Applied Data Science | 6 | 12 |
"""


def test_parse_area_budgets():
    budgets = parse_area_budgets(CATALOG_WITH_AREAS)
    assert budgets["fundamentals of data science"] == ("Fundamentals of Data Science", 12, 18)
    assert budgets["data processing"] == ("Data Processing", 6, 18)


def test_area_budget_under_minimum_flagged():
    # Only Big Data Engineering (Data Processing area) is planned.
    # Fundamentals (min 12) and Applied Data Science (min 6) have 0 CP → both flagged.
    plan = _plan("| Module | CP | Why |\n|---|---|---|\n| Big Data Engineering | 6 | x |\n\n**Total CP:** 6")
    rep = validate_plan(plan, CATALOG_WITH_AREAS, "")
    budget_errors = [f for f in rep.findings if f.rule == "area-budget"]
    assert len(budget_errors) >= 2, rep.summary()
    messages = " ".join(f.message for f in budget_errors)
    assert "Fundamentals of Data Science" in messages, rep.summary()


def test_area_budget_within_range_passes():
    plan = _plan(
        "| Module | CP | Why |\n|---|---|---|\n"
        "| Advanced Databases | 6 | x |\n"
        "| Machine Learning Foundations | 6 | x |\n\n**Total CP:** 12"
    )
    rep = validate_plan(plan, CATALOG_WITH_AREAS, "")
    budget_errors = [f for f in rep.findings if f.rule == "area-budget" and "Fundamentals" in f.message]
    assert not budget_errors, rep.summary()


# ─── area budgets driven by an uploaded schedule (requirements) ────────────────

from study_planner.requirements import ProgramRequirements, AreaRequirement


def _req():
    return ProgramRequirements(areas={
        "fundamentals of data science": AreaRequirement("Fundamentals of Data Science", 12, 18),
        "data processing": AreaRequirement("Data Processing", 6, 18),
        "applied data science": AreaRequirement("Applied Data Science", 6, 12, project_cp=6),
    }, thesis_cp=30)


def test_requirements_completed_credits_count_toward_minimum():
    # Fundamentals min 12 is met entirely by COMPLETED modules (2×6 CP); the plan
    # adds nothing there. With requirements it must NOT be flagged — the whole
    # point: already-earned credits reduce what has to be planned.
    profile = ("| Module | CP | Grade |\n|---|---|---|\n"
               "| Advanced Databases | 6 | 1.7 |\n"
               "| Machine Learning Foundations | 6 | 2.0 |\n")
    plan = _plan("| Module | CP | Why |\n|---|---|---|\n| Big Data Engineering | 6 | x |\n\n**Total CP:** 6")
    rep = validate_plan(plan, CATALOG_WITH_AREAS, profile, requirements=_req())
    msgs = [f.message for f in rep.findings if f.rule == "area-budget"]
    assert not any("Fundamentals" in m for m in msgs), rep.summary()
    # Applied Data Science still has 0 CP (min 6) → flagged.
    assert any("Applied Data Science" in m for m in msgs), rep.summary()
    assert rep.stats["area_cp"]["Fundamentals of Data Science"] == 12
    assert rep.stats["area_detail"]["Fundamentals of Data Science"]["completed"] == 12


def test_requirements_team_project_warns_when_absent():
    # Applied area filled to its min with a NON-project module → still warn, since
    # the schedule requires a team project there.
    plan = _plan("| Module | CP | Why |\n|---|---|---|\n"
                 "| Data Visualization | 3 | x |\n"
                 "| Data Visualization | 3 | x |\n\n**Total CP:** 6")
    rep = validate_plan(plan, CATALOG_WITH_AREAS, "", requirements=_req())
    assert any(f.rule == "area-project" for f in rep.warnings), rep.summary()


def test_requirements_team_project_satisfied():
    plan = _plan("| Module | CP | Why |\n|---|---|---|\n| Scientific Team Project | 6 | x |\n\n**Total CP:** 6")
    rep = validate_plan(plan, CATALOG_WITH_AREAS, "", requirements=_req())
    assert not any(f.rule == "area-project" and "Applied" in f.message
                   for f in rep.warnings), rep.summary()


def test_requirements_overplanning_is_error():
    """Core 'plan only remaining credits' rule: scheduling more coursework than
    the student still needs is an ERROR (the planner did this — 33 CP for 9)."""
    # total 24 CP = 18 coursework + 6 thesis; 12 already completed → only 6 remain.
    req = ProgramRequirements(areas={
        "fundamentals of data science": AreaRequirement("Fundamentals of Data Science", 6, 18),
        "data processing": AreaRequirement("Data Processing", 6, 18),
    }, thesis_cp=6, total_cp=24)
    completed_by_area = {"fundamentals of data science": 12}
    # plan schedules 12 CP (6 Fundamentals + 6 Data Processing) → 24 total > 18 req.
    plan = _plan("| Module | CP | Why |\n|---|---|---|\n"
                 "| Advanced Databases | 6 | x |\n"
                 "| Big Data Engineering | 6 | x |\n\n**Total CP:** 12")
    rep = validate_plan(plan, CATALOG_WITH_AREAS, "", requirements=req,
                        completed_by_area=completed_by_area)
    overplan = [f for f in rep.findings if f.rule == "coursework-overplan"]
    assert overplan and overplan[0].severity == "ERROR", rep.summary()
    assert not rep.ok, rep.summary()


def test_requirements_exact_remaining_no_overplan_error():
    """Planning exactly the remaining coursework must NOT trigger the overplan ERROR."""
    req = ProgramRequirements(areas={
        "fundamentals of data science": AreaRequirement("Fundamentals of Data Science", 6, 18),
        "data processing": AreaRequirement("Data Processing", 6, 18),
    }, thesis_cp=6, total_cp=24)
    completed_by_area = {"fundamentals of data science": 12}
    # only 6 remain; plan schedules exactly 6 (Big Data Engineering, Data Processing).
    plan = _plan("| Module | CP | Why |\n|---|---|---|\n| Big Data Engineering | 6 | x |\n\n**Total CP:** 6")
    rep = validate_plan(plan, CATALOG_WITH_AREAS, "", requirements=req,
                        completed_by_area=completed_by_area)
    assert not any(f.rule == "coursework-overplan" for f in rep.findings), rep.summary()


# ─── planning constraints (horizon / cp-preference / feasibility) ──────────────

from study_planner.inputs import PlanConstraints


def test_constraints_render_for_prompt():
    c = PlanConstraints(target_semesters=3, cp_overrides={1: 20},
                        default_cp_per_semester=30)
    text = c.render_for_prompt()
    assert "3 semester" in text and "semester 1: ~20 CP" in text and "~30 CP" in text


def test_constraints_reject_bad_degree_and_horizon():
    import pytest
    with pytest.raises(ValueError):
        PlanConstraints(degree_type="phd")
    with pytest.raises(ValueError):
        PlanConstraints(target_semesters=0)


def test_horizon_exceeded_is_error():
    # plan has 2 semesters, student wants to finish in 1
    plan = _plan(
        "| Module | CP | Why |\n|---|---|---|\n| Big Data Engineering | 6 | x |\n\n**Total CP:** 6",
        "| Module | CP | Why |\n|---|---|---|\n| Data Mining I | 6 | x |\n\n**Total CP:** 6",
    )
    c = PlanConstraints(target_semesters=1)
    rep = validate_plan(plan, CATALOG_MD, PROFILE_MD, c)
    assert any(f.rule == "horizon" for f in rep.errors), rep.summary()


def test_cp_preference_drift_warns():
    # semester 1 target is 20 CP, plan puts 6 → drift > 3 → warning
    plan = _plan(
        "| Module | CP | Why |\n|---|---|---|\n| Big Data Engineering | 6 | x |\n\n**Total CP:** 6")
    c = PlanConstraints(target_semesters=4, cp_overrides={1: 20})
    rep = validate_plan(plan, CATALOG_MD, PROFILE_MD, c)
    assert any(f.rule == "cp-preference" for f in rep.warnings), rep.summary()


def test_cp_preference_on_target_no_warning():
    # semester 1 target 18, plan has 18 → within tolerance, no cp-preference warning
    plan = _plan(
        "| Module | CP | Why |\n|---|---|---|\n"
        "| Big Data Engineering | 6 | x |\n| Data Mining I | 6 | x |\n"
        "| Data Visualization | 3 | x |\n| Information Retrieval | 6 | x |\n\n**Total CP:** 21")
    c = PlanConstraints(target_semesters=4, cp_overrides={1: 21})
    rep = validate_plan(plan, CATALOG_MD, PROFILE_MD, c)
    assert not any(f.rule == "cp-preference" for f in rep.warnings), rep.summary()


def test_feasibility_impossible_horizon_warns():
    # master: 90 CP coursework, 27 completed → 63 remaining; 1 semester × 36 = 36 < 63
    plan = _plan(
        "| Module | CP | Why |\n|---|---|---|\n| Big Data Engineering | 6 | x |\n\n**Total CP:** 6")
    c = PlanConstraints(degree_type="master", target_semesters=1)
    rep = validate_plan(plan, CATALOG_MD, PROFILE_MD, c)
    assert any(f.rule == "feasibility" for f in rep.warnings), rep.summary()


def test_feasibility_reasonable_horizon_ok():
    # 63 remaining over 3 semesters × 36 = 108 capacity → feasible, no warning
    plan = _plan(
        "| Module | CP | Why |\n|---|---|---|\n| Big Data Engineering | 6 | x |\n\n**Total CP:** 6")
    c = PlanConstraints(degree_type="master", target_semesters=3)
    rep = validate_plan(plan, CATALOG_MD, PROFILE_MD, c)
    assert not any(f.rule == "feasibility" for f in rep.findings), rep.summary()


# ─── no-schedule coursework overplan (the load-bearing guard without a schedule) ─

# A student who has already completed 84 of 90 coursework CP — only 6 remain.
HIGH_COMPLETED_PROFILE = """
Programme: M.Sc. DKE.

| Module | CP | Grade |
|---|---|---|
| Completed Coursework Block | 84 | 1.0 |
"""


def test_no_schedule_overplan_is_error():
    """No schedule uploaded, so the per-area guards are off. Planning more than the
    remaining coursework (deterministic: 90 - 84 = 6) must still ERROR — this is the
    real-world bug where the planner re-planned the whole degree for an 81-CP student."""
    plan = _plan("| Module | CP | Why |\n|---|---|---|\n"
                 "| Data Mining I | 6 | x |\n"
                 "| Software Engineering for Data Science | 6 | x |\n\n**Total CP:** 12")
    c = PlanConstraints(degree_type="master", target_semesters=4)
    rep = validate_plan(plan, CATALOG_MD, HIGH_COMPLETED_PROFILE, c)
    overplan = [f for f in rep.findings if f.rule == "coursework-overplan"]
    assert overplan and overplan[0].severity == "ERROR", rep.summary()
    assert not rep.ok, rep.summary()


def test_no_schedule_exact_remaining_no_overplan():
    """Planning exactly the remaining coursework (6 CP) must NOT trip the ERROR."""
    plan = _plan("| Module | CP | Why |\n|---|---|---|\n| Data Mining I | 6 | x |\n\n**Total CP:** 6")
    c = PlanConstraints(degree_type="master", target_semesters=4)
    rep = validate_plan(plan, CATALOG_MD, HIGH_COMPLETED_PROFILE, c)
    assert not any(f.rule == "coursework-overplan" for f in rep.findings), rep.summary()


def test_no_schedule_overplan_uses_transcript_override_not_profile():
    """completed_cp_override (deterministic transcript total) must win over the
    LLM profile's count, which under-reports. Profile says 0 completed, but the
    override says 84 -> only 6 remain -> planning 12 is still an ERROR."""
    plan = _plan("| Module | CP | Why |\n|---|---|---|\n"
                 "| Data Mining I | 6 | x |\n"
                 "| Software Engineering for Data Science | 6 | x |\n\n**Total CP:** 12")
    c = PlanConstraints(degree_type="master", target_semesters=4)
    rep = validate_plan(plan, CATALOG_MD, "", c, completed_cp_override=84)
    overplan = [f for f in rep.findings if f.rule == "coursework-overplan"]
    assert overplan and overplan[0].severity == "ERROR", rep.summary()


def test_no_schedule_thesis_not_counted_as_overplan():
    """The 30 CP thesis must not count toward the coursework-overplan total."""
    plan = _plan(
        "| Module | CP | Why |\n|---|---|---|\n| Data Mining I | 6 | x |\n\n**Total CP:** 6",
        "| Module | CP | Why |\n|---|---|---|\n| Master Thesis | 30 | x |\n\n**Total CP:** 30")
    c = PlanConstraints(degree_type="master", target_semesters=4)
    rep = validate_plan(plan, CATALOG_MD, HIGH_COMPLETED_PROFILE, c)
    assert not any(f.rule == "coursework-overplan" for f in rep.findings), rep.summary()


# ─── integration: the committed sample output ──────────────────────────────────

def test_committed_example_catches_known_take_limit_violation():
    """The committed expected_output_example.md schedules the team project 3x;
    the validator must catch exactly that (and not false-flag real modules)."""
    plan = (pathlib.Path(__file__).parent.parent
            / "sample_data" / "expected_output_example.md").read_text(encoding="utf-8")
    rep = validate_plan(plan, CATALOG_MD, PROFILE_MD)
    assert any(f.rule == "take-limit" for f in rep.errors), rep.summary()
    # the real modules in the plan must NOT be flagged as hallucinations
    assert not any(f.rule == "grounding" for f in rep.errors), rep.summary()


# ─── replan correction + deterministic budget table ────────────────────────────

def test_ensure_thesis_appends_when_missing():
    from study_planner.main import _ensure_thesis
    from study_planner.requirements import ProgramRequirements
    plan, appended = _ensure_thesis(
        "### Summer Semester 2026\n| Module | CP |\n|---|---|\n| X | 6 |",
        ProgramRequirements(thesis_cp=30))
    assert appended and "thesis" in plan.lower() and "30" in plan


def test_ensure_thesis_noop_when_present_or_not_required():
    from study_planner.main import _ensure_thesis
    from study_planner.requirements import ProgramRequirements
    # already has a thesis -> no change
    _, a1 = _ensure_thesis("Master's Thesis (Masterarbeit): 30 CP",
                           ProgramRequirements(thesis_cp=30))
    assert a1 is False
    # programme has no thesis requirement -> no change
    _, a2 = _ensure_thesis("plan body", ProgramRequirements())
    assert a2 is False


def test_cp_mismatch_flags_falsified_credit_value():
    # Big Data Engineering is 6 CP in the catalog; planning it as 3 CP must ERROR.
    plan = _plan(
        "| Module | CP | Why |\n|---|---|---|\n| Big Data Engineering | 3 | x |\n\n**Total CP:** 3")
    rep = validate_plan(plan, CATALOG_MD, PROFILE_MD)
    assert any(f.rule == "cp-mismatch" for f in rep.errors), rep.summary()


def test_cp_matching_value_has_no_mismatch():
    plan = _plan(
        "| Module | CP | Why |\n|---|---|---|\n| Big Data Engineering | 6 | x |\n\n**Total CP:** 6")
    rep = validate_plan(plan, CATALOG_MD, PROFILE_MD)
    assert not any(f.rule == "cp-mismatch" for f in rep.findings), rep.summary()


def test_offered_menu_grounding_flags_off_menu_catalog_module():
    # Big Data Engineering is in the full catalog but NOT on the offered menu →
    # grounding against the menu must flag it (the structural-cap escape).
    offered = ("| Module | CP | Semester offered | Key skills | Prerequisites |\n"
               "|---|---|---|---|---|\n"
               "| Advanced Databases | 6 | Winter | SQL | none |\n")
    plan = _plan("| Module | CP | Why |\n|---|---|---|\n"
                 "| Big Data Engineering | 6 | x |\n\n**Total CP:** 6")
    rep = validate_plan(plan, CATALOG_WITH_AREAS, "", offered_md=offered)
    assert any(f.rule == "grounding" for f in rep.errors), rep.summary()
    # without the menu restriction the same module grounds fine (it IS in the catalog)
    rep2 = validate_plan(plan, CATALOG_WITH_AREAS, "")
    assert not any(f.rule == "grounding" for f in rep2.errors), rep2.summary()


def test_unmapped_planned_module_counts_toward_coursework_total():
    # An area-unmapped ('n/a') module used to escape the coursework total entirely
    # (the ISP escape). It must now count, so a 9 CP unmapped module exceeding the
    # 6 CP coursework budget is flagged.
    cat = ("| Module | CP | Semester offered | Key skills taught | Prerequisites | Thematic Area |\n"
           "|---|---|---|---|---|---|\n"
           "| Advanced Databases | 6 | Winter | SQL | none | Fundamentals of Data Science |\n"
           "| Independent Project | 9 | Every | research | none | n/a |\n")
    req = ProgramRequirements(
        areas={"fundamentals of data science":
               AreaRequirement("Fundamentals of Data Science", 0, 18)},
        thesis_cp=30, total_cp=36)  # coursework_cp = 6
    plan = _plan("| Module | CP | Why |\n|---|---|---|\n"
                 "| Independent Project | 9 | x |\n\n**Total CP:** 9")
    rep = validate_plan(plan, cat, "", requirements=req, completed_by_area={})
    assert any(f.rule == "coursework-overplan" for f in rep.errors), rep.summary()
    assert rep.stats.get("planned_unmapped_cp") == 9, rep.stats


def test_build_correction_empty_when_ok():
    assert build_correction(ValidationReport()) == ""  # no findings → no errors → ""


def test_build_correction_lists_every_error_and_cap():
    rep = ValidationReport(
        findings=[
            Finding("ERROR", "area-budget", "'Applied': 30 CP exceeds the maximum of 24 CP"),
            Finding("ERROR", "horizon", "plan spans 5 semesters but the student wants 4"),
            Finding("WARNING", "cp-load", "ignored — warnings are not corrections"),
        ],
        stats={"coursework_required": 90,
               "area_detail": {"A": {"completed": 81, "planned": 30, "min": 0, "max": 24}}},
    )
    out = build_correction(rep)
    assert "area-budget" in out and "horizon" in out
    assert "cp-load" not in out                       # warnings excluded
    assert "EXACTLY 9 coursework CP" in out           # 90 required - 81 completed


def test_render_area_budget_table_status_from_code_not_llm():
    rep = ValidationReport(stats={"area_detail": {
        "Applied": {"completed": 18, "planned": 12, "min": 18, "max": 24},   # 30 > 24
        "Learning": {"completed": 24, "planned": 0, "min": 18, "max": 36},   # ok
        "Core": {"completed": 4, "planned": 0, "min": 12, "max": 18},        # short
    }})
    table = render_area_budget_table(rep)
    assert "| Applied | 18 | 12 | 30 | 18 | 24 | OVER |" in table
    assert "| Learning | 24 | 0 | 24 | 18 | 36 | OK |" in table
    assert "| Core | 4 | 0 | 4 | 12 | 18 | SHORT |" in table


def test_render_area_budget_table_empty_without_detail():
    assert render_area_budget_table(ValidationReport()) == ""
