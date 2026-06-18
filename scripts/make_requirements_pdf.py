"""Generate data/requirements.pdf — the real M.Sc. Data & Knowledge Engineering
study & examination schedule (Appendix A). This is the authoritative source of
the thematic-area CP rules; the product expects the student to upload it (the
New Plan form has a "Study & examination schedule" field). Text mirrors the
verified fixture in tests/test_requirements.py so the deterministic parser picks
up: areas 12-18 / 18-36 / 18-30 / 18-24, team project 6 CP, thesis 30, total 120.
"""
import pathlib
from fpdf import FPDF
from fpdf.enums import XPos, YPos

SCHEDULE_LINES = [
    "Appendix A: Study and examination schedule Data & Knowledge Engineering",
    "",
    'The study course "Master MDKE" consists of a series of topics. Each subject area',
    "contains the numbers of CPs (or the minimum and maximum numbers) which must be obtained:",
    '  1. In the subject area "Fundamentals of Data Science", modules with 12-18 CP must be selected.',
    '  2. In the subject area "Learning Methods & Models for Data Science", modules with a total of at least 18 and at most 36 CP must be selected.',
    '  3. In the subject area "Data Processing for Data Science", modules with a total of at least 18 and at most 30 CP must be selected.',
    '  4. In the subject area "Applied Data Science", modules with a total of at least 18 and at most 24 CP must be selected.',
    '  5. For "Applied Data Science", a team project (6 CP) is required.',
    "The programme comprises 120 CP in total, including the Master's Thesis.",
    "",
    "No   1st Semester 2nd Semester 3rd Semester 4th Semester Sum",
    "1. Fundamentals of Data Science (12-18 CP) 12 12",
    "2. Learning Methods & Models for Data Science (18-36 CP) 12 12 12 36",
    "3. Data Processing for Data Science (18-30 CP) 6 6 12 24",
    "4. Applied Data Science (18-24 CP) 12 6 18",
    "6. Master's Thesis (30 CP) 30 30",
    "Sum CP 30 30 30 30 120",
]

pdf = FPDF()
pdf.set_margins(15, 15, 15)
pdf.add_page()
pdf.set_font("Helvetica", size=11)
for line in SCHEDULE_LINES:
    # latin-1 safe (FPDF core font); the schedule text is plain ASCII.
    pdf.multi_cell(pdf.epw, 6, line if line else " ",
                   new_x=XPos.LMARGIN, new_y=YPos.NEXT)

out = pathlib.Path("data/requirements.pdf")
pdf.output(str(out))
print("wrote", out.resolve(), out.stat().st_size, "bytes")
