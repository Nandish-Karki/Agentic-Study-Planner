"""Spike + regression for the deterministic requirements parser.

The fixture is the real Data & Knowledge Engineering study & examination schedule
(the appendix the student uploads), transcribed with the messiness a PDF
extractor produces: curly quotes, an en-dash, and the Σ total split across a line
break ('12\\n0'). The parser must recover the true CP rules the LLM got wrong.
"""
from study_planner.requirements import (
    parse_requirements, parse_completed_by_area, render_completed_status, _norm,
    parse_completed_cp_from_transcript, render_minimal_completed_status,
)

# Curly quotes (“ ”) on purpose — this is what pypdf emits for this document.
SCHEDULE = """
Appendix A: Study and examination schedule Data & Knowledge Engineering

The study course "Master MDKE" consists of a series of topics. Each subject area
contains the numbers of CPs (or the minimum and maximum numbers) which must be obtained:
  1. In the subject area “Fundamentals of Data Science”, modules with 12-18 CP must be selected.
  2. In the subject area “Learning Methods & Models for Data Science”, modules with a total of at least 18 and at most 36 CP must be selected.
  3. In the subject area “Data Processing for Data Science”, modules with a total of at least 18 and at most 30 CP must be selected.
  4. In the subject area “Applied Data Science”, modules with a total of at least 18 and at most 24 CP must be selected.
  5. For “Applied Data Science”, a team project (6 CP) is required.

No   1st Semester 2nd Semester 3rd Semester 4th Semester Σ
1. Fundamentals of Data Science (12-18 CP) 12 12
2. Learning Methods & Models for Data Science (18-36 CP) 12 12 12 36
3. Data Processing for Data Science (18-30 CP) 6 6 12 24
4. Applied Data Science (18-24 CP) 12 6 18
6. Master's Thesis (30 CP) 30 30
Σ CP 30 30 30 30 12
0
"""

EXPECTED = {
    "fundamentals of data science": (12, 18),
    "learning methods models for data science": (18, 36),
    "data processing for data science": (18, 30),
    "applied data science": (18, 24),
}


def test_area_min_max_extracted_correctly():
    req = parse_requirements(SCHEDULE)
    got = {k: (a.min_cp, a.max_cp) for k, a in req.areas.items()}
    for key, rng in EXPECTED.items():
        assert key in got, f"missing area {key!r}; got {list(got)}"
        assert got[key] == rng, f"{key}: expected {rng}, got {got[key]}"


def test_thesis_is_not_an_area_and_is_captured():
    req = parse_requirements(SCHEDULE)
    assert req.thesis_cp == 30
    assert not any("thesis" in k for k in req.areas)


def test_team_project_caveat_attached_to_applied():
    req = parse_requirements(SCHEDULE)
    applied = req.areas[_norm("Applied Data Science")]
    assert applied.project_cp == 6
    # other areas have no project requirement
    assert req.areas[_norm("Fundamentals of Data Science")].project_cp is None


def test_total_and_coursework_cp():
    req = parse_requirements(SCHEDULE)
    assert req.total_cp == 120          # Σ CP row, recovered across the line break
    assert req.coursework_cp == 90      # 120 − 30 thesis


def test_parenthetical_only_still_parses():
    """Even without the prose list, the '(12-18 CP)' table form must work."""
    text = "1. Fundamentals of Data Science (12-18 CP)\n2. Applied Data Science (18-24 CP)"
    req = parse_requirements(text)
    assert req.areas[_norm("Fundamentals of Data Science")].min_cp == 12
    assert req.areas[_norm("Applied Data Science")].max_cp == 24


# A transcript transcribed with the messiness pypdf emits: ALL-CAPS area headers,
# rows ending "<Att> <CP> <SWS> <date>" after BE, a multi-line module name, an
# umlaut, a failed (NB) row that must NOT count, and the Σ-total line (81) that
# also must not be mistaken for a module's CP.
TRANSCRIPT = """
Data & Knowledge Engineering Grade Status Att. CP SWS Date
vorläufige Durchschnittsnote 2,4   1 81 45 18.03.2026
FUNDAMENTALS OF DATA SCIENCE
Introduction to Simulation 2,7 BE 1 5 4 04.02.2025
Maschinelles Lernen 4,0 BE 1 5 4 05.02.2025
Principles and Practices of Scientific Work and Soft Skills 1,7 BE 1 6 0 08.07.2025
LEARNING METHODS & MODELS FOR DATA SCIENCE
AI-based Decision Support II 2,3 BE 1 6 3 28.07.2025
Data Mining II - Advanced Topics in Data Mining 1,3 BE 1 6 4 25.02.2026
A Failed Attempt 5,0 NB 1 6 4 25.02.2026
DATA PROCESSING FOR DATA SCIENCE
Distributed Data Management 1,7 BE 1 6 4 26.03.2025
APPLIED DATA SCIENCE
Wissenschaftliches Teamprojekt / Detection and Removal of Audio
Steganography
1,7 BE 1 6 2 05.09.2025
"""


def test_completed_by_area_sums_passed_cp_per_area():
    req = parse_requirements(SCHEDULE)
    cba = parse_completed_by_area(TRANSCRIPT, req)
    assert cba[_norm("Fundamentals of Data Science")] == 16          # 5+5+6
    assert cba[_norm("Learning Methods & Models for Data Science")] == 12  # 6+6, NB excluded
    assert cba[_norm("Data Processing for Data Science")] == 6
    assert cba[_norm("Applied Data Science")] == 6                   # multi-line name counted


def test_completed_by_area_excludes_total_line_and_failures():
    req = parse_requirements(SCHEDULE)
    cba = parse_completed_by_area(TRANSCRIPT, req)
    # 81 total line is NOT a module; the NB(fail) row earns 0 → sum is the passed CP only
    assert sum(cba.values()) == 16 + 12 + 6 + 6


def test_completed_by_area_empty_without_schedule():
    from study_planner.requirements import ProgramRequirements
    assert parse_completed_by_area(TRANSCRIPT, ProgramRequirements()) == {}


def test_total_completed_cp_from_transcript_needs_no_schedule():
    # Sums every BE (passed) row regardless of area header; the NB fail is excluded.
    # 5+5+6 (Fundamentals) + 6+6 (Learning, NB excluded) + 6 (Processing) + 6 (Applied) = 40.
    assert parse_completed_cp_from_transcript(TRANSCRIPT) == 40


def test_minimal_completed_status_states_exact_remaining():
    s = render_minimal_completed_status(81, 90, 30)
    assert "Plan EXACTLY 9 more coursework CP" in s
    assert "81 of 90" in s
    assert "30 CP Master's Thesis" in s


def test_minimal_completed_status_empty_for_fresh_student():
    # A brand-new student (0 CP) gets no anchor — they must plan the whole degree.
    assert render_minimal_completed_status(0, 90, 30) == ""


def test_render_completed_status_states_exact_remaining_and_thesis():
    req = parse_requirements(SCHEDULE)
    cba = {
        _norm("Fundamentals of Data Science"): 16,
        _norm("Learning Methods & Models for Data Science"): 24,
        _norm("Data Processing for Data Science"): 23,
        _norm("Applied Data Science"): 18,
    }
    s = render_completed_status(req, cba)
    assert "Plan EXACTLY 9 more coursework CP" in s   # 90 coursework − 81 done
    assert "30 CP Master's Thesis" in s
    assert "at most 6 further CP" in s                # Applied: 24 − 18
