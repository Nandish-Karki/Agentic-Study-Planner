"""Deterministic parser for a labelled module handbook (OvGU FIN scheme).

A real handbook is ~900 pages covering MANY programmes, mostly prose (learning
outcomes, contents) the planner doesn't need. Each module is a block of
``Label: value`` fields, and crucially carries an **Assignment to the curriculum**
field listing which programme + thematic area it belongs to, e.g.:

    Module Name: Advanced Data Models
    Engl. module name: Advanced Database Models
    ...
    Credit points/ECTS: 6
    ...
    FIN: M.Sc. DKE - Data Processing for Data Science

So for a target programme (DKE) we keep ONLY modules assigned to it and extract
``{name, cp, area}`` — discarding every other programme's modules and all the prose.
This runs in code (no LLM, no token blow-up) and feeds main._build_planner_module_table
directly. Pure text in, dataclasses out — fully unit-testable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Field labels that end the "Credit points/ECTS:" value region.
_CP_STOP = (r"Prerequisites|Recommended|Intended|Contents|Examination|Grading|"
            r"Module Name:|Assignment|Teaching|Workload|Frequency")


@dataclass
class HandbookModule:
    name: str
    cp: int | None
    area: str  # the programme thematic area it's assigned to


def _entries(text: str):
    """Yield each module block (from one 'Module Name:' to the next)."""
    marks = [m.start() for m in re.finditer(r"Module Name:", text)]
    for i, s in enumerate(marks):
        e = marks[i + 1] if i + 1 < len(marks) else len(text)
        yield text[s:e]


def _name(entry: str) -> str:
    m = re.search(r"Engl\. module name:\s*(.+)", entry)
    if m and m.group(1).strip():
        return m.group(1).strip()
    m = re.search(r"Module Name:\s*(.+)", entry)
    return m.group(1).strip() if m else ""


def _cp(entry: str) -> int | None:
    """Credit points for the target degree. Handles a single number and the
    'Bachelor: 5 ... Master: 6 ...' split (prefers the Master value)."""
    m = re.search(rf"Credit points/ECTS:(.*?)(?:{_CP_STOP}|$)", entry, re.S | re.I)
    seg = m.group(1) if m else ""
    mm = re.search(r"Master[^:]*:\s*(\d+)", seg, re.I)  # prefer the master CP
    if mm:
        return int(mm.group(1))
    mm = re.search(r"(\d+)", seg)
    cp = int(mm.group(1)) if mm else None
    return cp if cp and 1 <= cp <= 60 else (cp if cp else None)


def _areas(entry: str, degree: str, program: str) -> list[str]:
    """Thematic areas this module is assigned to for `degree program`.

    Matches 'FIN: M.Sc. DKE - <area>' but NOT 'DKE (old) - ...' (the retired
    curriculum), because only the new areas line up with the study schedule."""
    pat = re.compile(
        rf"{re.escape(degree)}\s*{re.escape(program)}\s+-\s+([^\n]+)")
    out = []
    for a in pat.findall(entry):
        area = a.strip().rstrip(".")
        if area and area.lower() not in {x.lower() for x in out}:
            out.append(area)
    return out


def _canonical_area(area: str, valid_areas: list[str] | None) -> str | None:
    """Map a raw assignment area to the authoritative programme area name.

    When `valid_areas` (from the study schedule / requirements) is given, only
    areas that fuzzy-match one of them are kept — dropping stray/retired labels
    like 'Models department' and normalising to the exact requirements name so the
    catalog lines up with the validator. Without it, the raw area is kept as-is."""
    if not valid_areas:
        return area
    from study_planner.validate import _best_match
    match, score = _best_match(area, valid_areas)
    return match if (match and score >= 0.80) else None


def parse_handbook(text: str, program: str = "DKE", degree: str = "M.Sc.",
                   valid_areas: list[str] | None = None) -> list[HandbookModule]:
    """Extract modules offered to `degree program`, one row per (module, area).

    `valid_areas` (the authoritative thematic-area names) filters + normalises the
    area labels. Deduplicates by (normalized name, area) so a module appearing in
    both Part A and Part B isn't double-counted."""
    rows: list[HandbookModule] = []
    seen_names: set[str] = set()
    for entry in _entries(text):
        areas = _areas(entry, degree, program)
        if not areas:
            continue  # not offered to this programme -> drop (this is "the crap")
        name = _name(entry)
        if not name:
            continue
        norm = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
        if norm in seen_names:
            continue  # already added (Part A/B duplicate, or seen earlier)
        # ONE canonical area per module: a module listed under several areas would
        # otherwise let the menu and the validator disagree on which area it counts
        # toward (a false area-budget error). Take the first valid area.
        chosen = next(
            (a for a in (_canonical_area(r, valid_areas) for r in areas) if a), None)
        if chosen is None:
            continue  # none of its areas is a real programme area
        seen_names.add(norm)
        rows.append(HandbookModule(name=name, cp=_cp(entry), area=chosen))
    return rows


def render_catalog_md(modules: list[HandbookModule]) -> str:
    """Render parsed modules as the curator-style table that
    main._build_planner_module_table consumes (Module | CP | Thematic Area)."""
    lines = ["| Module | CP | Thematic Area |", "|---|---|---|"]
    for m in modules:
        lines.append(f"| {m.name} | {m.cp if m.cp is not None else ''} | {m.area} |")
    return "\n".join(lines)
