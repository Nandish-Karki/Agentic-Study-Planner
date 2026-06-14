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
