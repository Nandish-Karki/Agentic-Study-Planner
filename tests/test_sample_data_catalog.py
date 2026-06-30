"""Regression guard: the demo sample handbook must be structurally feasible.

Every area's available catalog CP must fit within that area's max_cp, and the
sum of per-area-capped availability must equal the programme's coursework
requirement (90 CP) — otherwise the deterministic menu-curation (which respects
area maxes) can never assemble a complete plan from the demo dataset, and every
Try Demo run will silently report a CP shortfall.

This test imports make_sample_data constants directly (no PDF read needed) so
it catches a bad edit to the generator before the PDF is even regenerated.
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "scripts"))
from make_sample_data import AREA_BUDGETS, HANDBOOK_MODULES  # type: ignore

COURSEWORK_CP = 90  # 120 total − 30 thesis


def _catalog_by_area() -> dict[str, int]:
    totals: dict[str, int] = {}
    for row in HANDBOOK_MODULES:
        name, cp_str, *_, area = row
        if area == "Master Thesis":
            continue
        totals[area] = totals.get(area, 0) + int(cp_str)
    return totals


def test_no_area_exceeds_its_max():
    """Available catalog CP per area must not exceed that area's max_cp.

    If it does, the deterministic assembler is forced to leave CP on the table
    (it correctly refuses to over-fill an area) and the total will fall short
    of COURSEWORK_CP regardless of how the code is written.
    """
    catalog = _catalog_by_area()
    for area, min_cp, max_cp in AREA_BUDGETS:
        avail = catalog.get(area, 0)
        assert avail <= int(max_cp), (
            f"'{area}': catalog offers {avail} CP but area max is {max_cp} CP — "
            f"{avail - int(max_cp)} CP is stranded and can never be scheduled, "
            f"making the demo plan structurally short. Move the excess module(s) "
            f"to an area with room, or raise the area's max_cp."
        )


def test_max_reachable_equals_coursework_requirement():
    """Sum of per-area-capped catalog CP must equal COURSEWORK_CP (90).

    Even if no individual area exceeds its max, the catalog could still be
    under-supplied (not enough modules offered) or over-supplied-but-capped
    (areas with room but no modules to fill them). This catches both.
    """
    catalog = _catalog_by_area()
    max_reachable = 0
    for area, _min_cp, max_cp in AREA_BUDGETS:
        avail = catalog.get(area, 0)
        max_reachable += min(avail, int(max_cp))
    assert max_reachable == COURSEWORK_CP, (
        f"Max reachable CP from demo catalog is {max_reachable}, "
        f"but the programme requires {COURSEWORK_CP} CP coursework. "
        f"Adjust HANDBOOK_MODULES or AREA_BUDGETS so the totals match."
    )
