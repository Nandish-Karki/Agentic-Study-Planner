"""Deterministic handbook parser tests (Workstream 2).

Synthetic fixtures cover the parsing logic; an optional marker test runs against
the real 908-page handbook when present (spike -> regression gate).
"""
import pathlib

import pytest

from study_planner.ingest.handbook_parser import parse_handbook, render_catalog_md
from study_planner.validate import parse_markdown_tables, _find_col

SAMPLE = """
Module Name: Foo Bar
Engl. module name: Foo Bar
Credit points/ECTS: 6
Assignment to the curriculum:
FIN: M.Sc. DKE - Applied Data Science
FIN: B.Sc. INF - WPF Computer Science
Intended learning outcomes: lots of prose we don't want

Module Name: Other Programme Only
Engl. module name: Other Programme Only
Credit points/ECTS: 5
FIN: M.Sc. INF - Computer Science
Contents: prose

Module Name: Master Split CP
Engl. module name: Master Split CP
Credit points/ECTS: Bachelor:
5 credit points
Master:
6 credit points
FIN: M.Sc. DKE - Data Processing for Data Science

Module Name: Old Scheme Only
Engl. module name: Old Scheme Only
Credit points/ECTS: 6
FIN: M.Sc. DKE (old) - Models department
"""


def test_keeps_only_target_programme_modules():
    mods = parse_handbook(SAMPLE, program="DKE", degree="M.Sc.")
    names = {m.name for m in mods}
    assert "Foo Bar" in names
    assert "Master Split CP" in names
    assert "Other Programme Only" not in names   # different programme -> dropped
    assert "Old Scheme Only" not in names        # 'DKE (old)' retired scheme -> dropped


def test_extracts_cp_and_area_including_master_split():
    mods = {m.name: m for m in parse_handbook(SAMPLE)}
    assert mods["Foo Bar"].cp == 6
    assert mods["Foo Bar"].area == "Applied Data Science"
    assert mods["Master Split CP"].cp == 6        # prefers the Master value over Bachelor
    assert mods["Master Split CP"].area == "Data Processing for Data Science"


def test_valid_areas_filters_and_normalises():
    mods = parse_handbook(SAMPLE, valid_areas=["Applied Data Science"])
    names = {m.name for m in mods}
    assert "Foo Bar" in names                     # Applied -> kept
    assert "Master Split CP" not in names         # Data Processing not in valid set -> dropped


def test_render_catalog_md_is_parseable():
    md = render_catalog_md(parse_handbook(SAMPLE))
    tables = parse_markdown_tables(md)
    assert tables, "rendered catalog must contain a table"
    t = tables[0]
    assert _find_col(t.headers, "module") and _find_col(t.headers, "thematic area")


_REAL = pathlib.Path(__file__).parent.parent / "data" / "handbook_full.pdf"


@pytest.mark.skipif(not _REAL.exists(), reason="real handbook not present")
def test_real_handbook_extraction_smoke():
    from pypdf import PdfReader
    text = "\n".join((p.extract_text() or "") for p in PdfReader(str(_REAL)).pages)
    mods = parse_handbook(text, valid_areas=[
        "Fundamentals of Data Science", "Applied Data Science",
        "Learning Methods & Models for Data Science", "Data Processing for Data Science"])
    assert len(mods) >= 30, f"expected a real catalog, got {len(mods)} rows"
    assert {m.area for m in mods} <= {
        "Fundamentals of Data Science", "Applied Data Science",
        "Learning Methods & Models for Data Science", "Data Processing for Data Science"}
    assert all(m.cp for m in mods), "every parsed module should have CP"
