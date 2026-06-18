"""Deterministic parser for a programme's study & examination schedule.

The thematic-area CP rules (min/max per area, required team projects, thesis CP,
total) are REGULATIONS — not something to trust an LLM to read. The curator
mis-extracted them in a real run (15/18 for areas that are actually 12-18 /
18-36 / 18-30 / 18-24). When the student uploads the schedule/appendix, we parse
it here in code and treat it as the source of truth, overriding the LLM's guesses.

Pure text → dataclass: no LLM, no network, fully unit-testable. The matching is
forgiving of PDF/OCR noise (curly quotes, line breaks, en-dashes) because real
handbook PDFs are messy — see tests/test_requirements.py for the spike on the
real Data & Knowledge Engineering schedule.
"""
from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass, field

# Quote glyphs that show up in PDFs: straight, curly double, curly single.
_Q = "\"'“”‘’"
_DASH = r"[-–—]"  # hyphen, en-dash, em-dash


@dataclass
class AreaRequirement:
    name: str                      # display name as found in the document
    min_cp: int
    max_cp: int
    project_cp: int | None = None  # a required team/group project within this area


@dataclass
class ProgramRequirements:
    """Authoritative CP rules parsed from the uploaded schedule."""
    areas: dict[str, AreaRequirement] = field(default_factory=dict)  # norm name -> req
    thesis_cp: int | None = None
    total_cp: int | None = None

    @property
    def coursework_cp(self) -> int | None:
        """Total minus thesis — the CP the student must cover in coursework areas."""
        if self.total_cp is not None and self.thesis_cp is not None:
            return self.total_cp - self.thesis_cp
        return None

    def is_empty(self) -> bool:
        return not self.areas and self.thesis_cp is None

    def render_for_prompt(self) -> str:
        """Authoritative-rules block injected into the planner/curator prompts.
        When no schedule was uploaded, tells the agents to infer from the handbook
        (the previous behaviour)."""
        if not self.areas:
            return ("No official study & examination schedule was provided. Infer the "
                    "thematic areas and their CP ranges from the module handbook, and "
                    "state any assumption you make.")
        lines = ["AUTHORITATIVE PROGRAMME RULES — from the student's official study & "
                 "examination schedule. Use THESE exact area names and CP ranges; do "
                 "not infer or change them:"]
        if self.coursework_cp is not None and self.thesis_cp is not None:
            lines.append(f"- Total {self.total_cp} CP = {self.coursework_cp} CP coursework "
                         f"+ {self.thesis_cp} CP Master's thesis.")
        elif self.thesis_cp is not None:
            lines.append(f"- Master's thesis: {self.thesis_cp} CP.")
        lines.append("- Thematic areas (each area's TOTAL CP must fall in this range):")
        for a in self.areas.values():
            extra = (f" — MUST include a team/group project worth {a.project_cp} CP"
                     if a.project_cp else "")
            lines.append(f"  • {a.name}: {a.min_cp}-{a.max_cp} CP{extra}")
        lines.append(
            "- COUNT ALREADY-COMPLETED CREDITS: from the transcript, work out how many "
            "CP the student has already earned in each area, then plan ONLY the modules "
            "still needed to bring every area to at least its minimum and reach the "
            "coursework total. Never re-take a completed module.")
        lines.append(
            "- USE AS FEW SEMESTERS AS NEEDED: if little coursework remains, produce a "
            "short plan (even a single semester) plus the thesis — do not pad to a fixed "
            "number of semesters.")
        return "\n".join(lines)

    def render_area_names_for_curator(self) -> str:
        """Exact area-name list for the module curator prompt.

        The curator must copy one of these strings verbatim into the Thematic Area
        column of every module row. Any deviation (abbreviation, & vs and, extra
        words) breaks the downstream area-budget tracking in both the planner and
        the validator. When no schedule is uploaded, returns an empty string so the
        curator falls back to inferring areas from the handbook as before.
        """
        if not self.areas:
            return ""
        lines = [
            "VALID THEMATIC AREA NAMES — copy one of these strings character-by-character "
            "into the 'Thematic Area' column of every module row. No abbreviations, "
            "no paraphrasing, no variants. These are the ONLY accepted values:"
        ]
        for a in self.areas.values():
            lines.append(f"  * {a.name}")
        lines.append(
            "If a module does not clearly belong to any of the above areas, write 'n/a'. "
            "Do NOT invent new area names."
        )
        return "\n".join(lines)


def _norm(s: str) -> str:
    """Normalize an area name for matching. MUST stay in sync with validate._norm
    so requirement areas and planned-area-CP keys line up."""
    s = s.lower()
    s = re.sub(r"[*_`]", "", s)
    s = re.sub(r"[–—]", "-", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _range_from_spec(spec: str) -> tuple[int, int] | None:
    """Pull (min, max) from a CP spec fragment, in either phrasing the handbook
    uses: 'at least 18 and at most 36' or '12-18'."""
    s = spec.lower()
    m = re.search(r"at least\s*(\d+).*?at most\s*(\d+)", s)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d+)\s*" + _DASH + r"\s*(\d+)", s)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def _merge_area(areas: dict[str, AreaRequirement], name: str, lo: int, hi: int) -> None:
    key = _norm(name)
    if not key or "thesis" in key or lo > hi:
        return
    if key not in areas:
        areas[key] = AreaRequirement(name=name.strip(), min_cp=lo, max_cp=hi)


def _ok_total(v: int) -> bool:
    return 60 <= v <= 400


def _parse_total(text: str) -> int | None:
    """Programme total CP. Prefers a clean prose statement; else the 'Σ CP' row's
    last (total) cell, rejoining a total the PDF split across a line break
    ('12' + '0' → 120)."""
    for pat in (r"total of\s*(\d+)\s*cp", r"comprises[^.]*?(\d{2,3})\s*cp",
                r"(\d{2,3})\s*cp\s*in total"):
        m = re.search(pat, text, re.I)
        if m and _ok_total(int(m.group(1))):
            return int(m.group(1))

    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not re.match(r"\s*(?:Σ|sum)\s*cp\b", line, re.I):
            continue
        nums = re.findall(r"\d+", line)
        if not nums:
            continue
        last = nums[-1]
        # the final total cell is often split onto the next line by the extractor
        if i + 1 < len(lines) and re.fullmatch(r"\d{1,2}", lines[i + 1].strip()):
            cand = int(last + lines[i + 1].strip())
            if _ok_total(cand):
                return cand
        if _ok_total(int(last)):
            return int(last)
    return None


def parse_requirements(text: str) -> ProgramRequirements:
    """Parse a study & examination schedule into structured CP rules."""
    req = ProgramRequirements()
    areas: dict[str, AreaRequirement] = {}

    # 1) Prose: 'In the subject area "X", modules with <spec> CP must be selected.'
    for m in re.finditer(
        rf"subject area\s*[{_Q}]?\s*(?P<name>[^{_Q}\n(]+?)\s*[{_Q}]?\s*[,:]?\s*"
        rf"modules?\s+with\s+(?P<spec>[^.\n]+?)\bcp\b",
        text, re.I,
    ):
        rng = _range_from_spec(m.group("spec"))
        if rng:
            _merge_area(areas, m.group("name"), *rng)

    # 2) Parenthetical form (table rows / headings): 'X (12-18 CP)'
    for m in re.finditer(
        rf"(?P<name>[A-Za-z][^()\n]{{3,60}}?)\s*\(\s*(?P<lo>\d+)\s*{_DASH}"
        r"\s*(?P<hi>\d+)\s*cp\s*\)",
        text, re.I,
    ):
        _merge_area(areas, m.group("name"), int(m.group("lo")), int(m.group("hi")))

    # 3) Thesis: 'Master's Thesis (30 CP)' / 'thesis 30 CP'
    tm = re.search(rf"thesis\s*\(?\s*(\d+)\s*cp", text, re.I)
    if tm:
        req.thesis_cp = int(tm.group(1))
    # never keep a thesis row as a coursework area
    for k in [k for k in areas if "thesis" in k]:
        areas.pop(k, None)

    # 4) Required team/group project: 'For "X", a team project (6 CP) is required.'
    for m in re.finditer(
        rf"[{_Q}]?\s*(?P<name>[A-Za-z][^{_Q}\n(]{{3,60}}?)\s*[{_Q}]?\s*,?\s*"
        rf"a\s+(?:team|group)\s+project\s*\(\s*(?P<cp>\d+)\s*cp\s*\)\s*(?:is\s+)?required",
        text, re.I,
    ):
        key = _norm(m.group("name"))
        if key in areas:
            areas[key].project_cp = int(m.group("cp"))

    # 5) Programme total
    total = _parse_total(text)
    if total:
        req.total_cp = total

    req.areas = areas
    return req


def dke_requirements() -> ProgramRequirements:
    """Built-in CP rules for the DKE M.Sc. — the only supported programme.

    Data & Knowledge Engineering at Otto-von-Guericke-Universität Magdeburg. These
    four thematic areas and their min/max CP are fixed regulations; we build them in
    so area min/max enforcement is always on, even when no study & examination
    schedule PDF was uploaded (e.g. a brand-new first-semester student). Coursework
    = total 120 - 30 thesis = 90 CP. Future programmes would add their own factory.
    """
    areas: dict[str, AreaRequirement] = {}
    for name, lo, hi in [
        ("Fundamentals of Data Science", 12, 18),
        ("Learning Methods & Models", 18, 36),
        ("Data Processing for Data Science", 18, 30),
        ("Applied Data Science", 18, 24),
    ]:
        areas[_norm(name)] = AreaRequirement(name=name, min_cp=lo, max_cp=hi)
    return ProgramRequirements(areas=areas, thesis_cp=30, total_cp=120)


def parse_requirements_file(path: str | pathlib.Path) -> ProgramRequirements:
    """Read a schedule document (PDF/text) and parse it. Empty result if the file
    is missing or yields no extractable text (e.g. a scanned image)."""
    p = pathlib.Path(path)
    if not p.exists():
        return ProgramRequirements()
    if p.suffix.lower() == ".pdf":
        text = _pdf_text(p)
    else:
        text = p.read_text(encoding="utf-8", errors="replace")
    return parse_requirements(text)


def _pdf_text(path: str | pathlib.Path) -> str:
    """Extract text from a PDF (empty string on any failure / scanned image)."""
    from pypdf import PdfReader
    try:
        return "\n".join((pg.extract_text() or "") for pg in PdfReader(str(path)).pages)
    except Exception:
        return ""


# A graded, PASSED transcript row ends: <Att> <CP> <SWS> <dd.mm.yyyy>, after "BE"
# (BE = bestanden/passed; NB = failed → no CP earned, so we don't count it). The
# CP is the first number after the attempt count.
_TRANSCRIPT_CP_ROW = re.compile(
    r"\bBE\b\s+\d+\s+(\d+)\s+\d+\s+\d{1,2}\.\d{1,2}\.\d{2,4}")


def parse_completed_cp_from_transcript(transcript_text: str) -> int:
    """Total completed CP from the transcript, WITHOUT needing a schedule.

    Sums the CP of every passed (BE) row regardless of thematic-area header. This
    works even when the student uploaded no study & examination schedule (so
    `parse_completed_by_area` returns {}), which is exactly the case where the
    planner otherwise re-plans the whole degree. Deterministic; no LLM.
    """
    return sum(int(m.group(1)) for m in _TRANSCRIPT_CP_ROW.finditer(transcript_text))


def render_minimal_completed_status(completed_cp: int, coursework_cp: int,
                                    thesis_cp: int = 30) -> str:
    """Schedule-free 'what's left' block for the planner prompt.

    Used when no study schedule was uploaded (no per-area ranges to anchor to) but
    we still know, deterministically, how many coursework CP the student has done.
    Gives the planner the exact remaining figure so it doesn't pad the plan out to
    a full degree. ASCII-only (playbook 7.8 — this is printed by the Windows
    worker). Empty when nothing is completed (a fresh student must plan it all)."""
    if completed_cp <= 0:
        return ""
    remaining = max(0, coursework_cp - completed_cp)
    return (
        "ALREADY-COMPLETED CREDITS - computed from the transcript in code; treat "
        "this as FACT, do NOT recount or re-plan completed work:\n"
        f"  - The student has already completed {completed_cp} of {coursework_cp} "
        f"required coursework CP.\n"
        f"Plan EXACTLY {remaining} more coursework CP - NO MORE - then schedule the "
        f"{thesis_cp} CP Master's Thesis as its own final semester. Use AS FEW "
        "semesters as those remaining credits need; do NOT pad to a fixed number of "
        "semesters. Never re-take a completed module.")


def parse_completed_by_area(transcript_text: str,
                            requirements: ProgramRequirements) -> dict[str, int]:
    """Sum completed CP per thematic area straight from the transcript.

    The transcript groups passed modules under ALL-CAPS area headers that match
    the schedule's area names ("FUNDAMENTALS OF DATA SCIENCE", ...). We attribute
    each passed row's CP to the header above it. This is DETERMINISTIC on purpose:
    the planner LLM mis-attributes completed credits to the wrong area and double-
    or under-counts (observed: it read 81 CP as 46). Returns {norm_area: cp} for
    areas present in `requirements`; empty when the schedule is unknown.
    """
    if not requirements or not requirements.areas:
        return {}
    area_keys = set(requirements.areas)            # normalized names
    result: dict[str, int] = {}
    current: str | None = None
    for raw in transcript_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _norm(line) in area_keys:               # an area header line
            current = _norm(line)
            continue
        if current is None:
            continue
        m = _TRANSCRIPT_CP_ROW.search(line)
        if m:
            result[current] = result.get(current, 0) + int(m.group(1))
    return result


def render_completed_status(requirements: ProgramRequirements,
                            completed_by_area: dict[str, int]) -> str:
    """Precise, deterministic 'what's done / what's left per area' block for the
    planner prompt — so the model never has to compute the subtraction itself
    (which it gets wrong). Empty when there is no schedule to anchor to."""
    if not requirements or not requirements.areas:
        return ""
    lines = ["ALREADY-COMPLETED CREDITS — computed from the transcript in code; "
             "treat these as FACT, do NOT recount or re-attribute them:"]
    total_done = 0
    for key, a in requirements.areas.items():
        done = completed_by_area.get(key, 0)
        total_done += done
        room = max(0, a.max_cp - done)
        need = (f"{a.min_cp - done} CP still REQUIRED to reach the {a.min_cp} minimum"
                if done < a.min_cp else "minimum already met")
        lines.append(
            f"  - {a.name}: {done} CP completed (allowed range {a.min_cp}-{a.max_cp}); "
            f"{need}; at most {room} further CP may be added without exceeding the "
            f"{a.max_cp} maximum.")
    cw = requirements.coursework_cp
    thesis = requirements.thesis_cp or 30
    if cw is not None:
        remaining = max(0, cw - total_done)
        lines.append(
            f"Coursework completed: {total_done} of {cw} CP. Plan EXACTLY {remaining} "
            f"more coursework CP — placed only in areas that still have room above and "
            f"never exceeding any area's maximum — then schedule the {thesis} CP "
            f"Master's Thesis as its own final semester. Never re-take a completed "
            f"module; never add credits to an area already at its maximum.")
    return "\n".join(lines)
