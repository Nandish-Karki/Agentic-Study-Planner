"""Synthesize a blank 0-CP transcript PDF for a brand-new first-semester student.

A new DKE student has no transcript yet. Rather than special-casing the whole
pipeline (profile task, completed-CP parsing, validator), we hand it a real PDF
that simply states "enrolled, 0 CP, no modules completed". Every downstream step
then runs unchanged and computes 0 completed credits, so the planner produces a
full 90 CP + thesis plan. This mirrors scripts/make_new_student.py (the dev tool
that proved the approach); fpdf2 is a runtime dependency for exactly this.
"""
from __future__ import annotations

import pathlib

# Enrolled, nothing completed. ASCII-only (this can run in the Windows worker;
# playbook 7.8) and free of a real transcript's module rows so the completed-CP
# parser correctly reads 0.
_LINES = [
    "Transcript of Records",
    "Otto-von-Guericke-Universitaet Magdeburg",
    "Degree: Master",
    "Study Programme: Data & Knowledge Engineering",
    "",
    "Enrolment status: Newly enrolled, 1st semester.",
    "Credits earned so far: 0 CP.",
    "No modules have been completed yet.",
    "",
    "Module Grade Status CP Date",
    "(none)",
]


def synthesize_blank_transcript(dest: str | pathlib.Path) -> pathlib.Path:
    """Write a minimal 0-CP transcript PDF to ``dest`` and return its path."""
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    dest = pathlib.Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    pdf = FPDF()
    pdf.set_margins(15, 15, 15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for line in _LINES:
        pdf.multi_cell(pdf.epw, 6, line if line else " ",
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.output(str(dest))
    return dest
