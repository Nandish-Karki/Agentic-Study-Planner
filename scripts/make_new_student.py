"""Build data_new/ — the 'entirely new student' case: same programme, career,
handbook and schedule, but a transcript with NO completed modules (0 CP). Tests
that the planner produces a full 4-semester plan covering every area to its
minimum + thesis, instead of a remaining-only plan.
"""
import pathlib
import shutil
from fpdf import FPDF
from fpdf.enums import XPos, YPos

src = pathlib.Path("data")
dst = pathlib.Path("data_new")
dst.mkdir(exist_ok=True)

# Reuse the unchanged inputs.
for name in ["cv.pdf", "career.pdf", "module_handbook.pdf", "requirements.pdf"]:
    shutil.copy2(src / name, dst / name)

# A transcript for a freshly-enrolled student: enrolled, nothing completed.
LINES = [
    "Transcript of Records",
    "Student-ID: 254960",
    "Name: Nandish Mahadev Karki, born July 2, 1999",
    "Otto-von-Guericke-Universitaet Magdeburg",
    "Date: October 1, 2024",
    "Degree: Master",
    "Study Programme: Data & Knowledge Engineering",
    "",
    "Enrolment status: Newly enrolled, 1st semester (Winter 2024/25).",
    "Credits earned so far: 0 CP.",
    "No modules have been completed yet.",
    "",
    "Module Grade Status CP Date",
    "(none)",
]

pdf = FPDF()
pdf.set_margins(15, 15, 15)
pdf.add_page()
pdf.set_font("Helvetica", size=11)
for line in LINES:
    pdf.multi_cell(pdf.epw, 6, line if line else " ",
                   new_x=XPos.LMARGIN, new_y=YPos.NEXT)
pdf.output(str(dst / "transcript.pdf"))

print("built", dst.resolve())
for f in sorted(dst.iterdir()):
    print(f"  {f.name}  ({f.stat().st_size} bytes)")
