"""
Generate the synthetic sample-data pack: four fictional PDFs in sample_data/.

The student "Alex Beispiel" is invented; the modules are OvGU-*style* but
fictional. Safe to publish — contains no real personal data.

Run:  .venv/Scripts/python scripts/make_sample_data.py
"""
import pathlib

from fpdf import FPDF

OUT = pathlib.Path(__file__).parent.parent / "sample_data"


class Doc(FPDF):
    """Minimal helper: headings, paragraphs, and simple tables."""

    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=18)
        self.add_page()

    def h1(self, text):
        self.set_font("helvetica", "B", 16)
        self.cell(0, 10, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def h2(self, text):
        self.set_font("helvetica", "B", 12)
        self.ln(3)
        self.cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")

    def p(self, text):
        self.set_font("helvetica", "", 10)
        self.multi_cell(0, 5.5, text)
        self.ln(1)

    def table(self, headers, rows, widths):
        self.set_font("helvetica", "B", 9)
        for h, w in zip(headers, widths):
            self.cell(w, 7, h, border=1)
        self.ln()
        self.set_font("helvetica", "", 9)
        for row in rows:
            # measure tallest cell, then draw all cells at that height
            line_h = 5
            n_lines = max(
                len(self.multi_cell(w, line_h, str(c), dry_run=True, output="LINES"))
                for c, w in zip(row, widths)
            )
            row_h = n_lines * line_h
            if self.get_y() + row_h > self.page_break_trigger:
                self.add_page()
            y0 = self.get_y()
            x = self.l_margin
            for c, w in zip(row, widths):
                self.set_xy(x, y0)
                self.multi_cell(w, line_h, str(c), border=1)
                x += w
            self.set_xy(self.l_margin, y0 + row_h)
        self.ln(2)


def make_cv():
    d = Doc()
    d.h1("Curriculum Vitae - Alex Beispiel")
    d.p("Email: alex.beispiel@example.org  |  Magdeburg, Germany  |  github.com/alexbeispiel")

    d.h2("Education")
    d.p("M.Sc. Data & Knowledge Engineering, Otto-von-Guericke University Magdeburg "
        "- since October 2025 (currently 2nd semester).")
    d.p("B.Sc. Computer Science, Hochschule Beispielstadt - 2021 to 2024. "
        "Final grade 2.1. Thesis: 'A REST API for sensor data collection' (grade 1.7).")

    d.h2("Work Experience")
    d.p("Working Student, Backend Development - DataWerk GmbH, 2023 to 2025. "
        "Built and maintained Python services (FastAPI) backed by PostgreSQL; wrote SQL "
        "reports; containerized two services with Docker; basic Git/GitLab CI usage.")

    d.h2("Projects")
    d.p("Weather Data Pipeline (personal): hourly ingestion of public weather API data "
        "into PostgreSQL with a small Python ETL script and a Grafana dashboard.")
    d.p("University team project: campus room-booking web app (Flask + SQLite).")

    d.h2("Technical Skills")
    d.p("Python (good), SQL/PostgreSQL (good), Git (good), Docker (basics), "
        "FastAPI/Flask (basics), Linux shell (basics). No production experience with "
        "Spark, Kafka, cloud platforms, or ML deployment yet.")

    d.h2("Languages")
    d.p("German (native), English (C1).")
    d.output(OUT / "cv.pdf")


def make_transcript():
    d = Doc()
    d.h1("Transcript of Records - Alex Beispiel")
    d.p("Programme: M.Sc. Data & Knowledge Engineering (120 CP: 90 CP coursework + 30 CP "
        "master thesis). Enrolled since Winter 2025/26. Credits earned so far: 27 CP.")

    d.h2("Completed Modules - Semester 1 (Winter 2025/26)")
    d.table(
        ["Module", "CP", "Grade"],
        [
            ["Advanced Databases", "6", "1.7"],
            ["Machine Learning Foundations", "6", "2.0"],
            ["Distributed Systems", "6", "2.3"],
            ["Cloud Computing", "6", "1.3"],
            ["Seminar Data Engineering", "3", "1.0"],
        ],
        [110, 25, 25],
    )
    d.p("Current average grade: 1.8. No failed attempts. "
        "Remaining: 63 CP coursework + 30 CP master thesis.")
    d.output(OUT / "transcript.pdf")


def make_career():
    d = Doc()
    d.h1("Target Career: Data Engineer")
    d.p("Alex wants to start as a (Junior) Data Engineer at a German tech company "
        "after graduation, building and operating data pipelines.")

    d.h2("Typical role requirements (from current job postings)")
    d.p("Must-have:\n"
        "1. Strong SQL and data modeling (warehousing, dimensional models)\n"
        "2. Python for data processing\n"
        "3. ETL/ELT pipeline design and orchestration (e.g. Spark, Airflow)\n"
        "4. Experience with at least one cloud platform (AWS, Azure, or GCP)\n"
        "5. Data warehouse / data lake architectures")
    d.p("Nice-to-have:\n"
        "1. Stream processing (Kafka, Flink)\n"
        "2. MLOps basics (model serving, monitoring)\n"
        "3. Docker and Kubernetes\n"
        "4. Dashboarding and data storytelling\n"
        "5. Agile teamwork experience")
    d.output(OUT / "career.pdf")


AREA_BUDGETS = [
    # thematic area, min CP, max CP
    ["Fundamentals of Data Science", "12", "18"],
    ["Learning Methods & Models", "18", "36"],
    ["Data Processing for Data Science", "18", "30"],
    ["Applied Data Science", "18", "24"],
]

HANDBOOK_MODULES = [
    # name, CP, offered, skills, prerequisites, thematic area
    ["Advanced Databases", "6", "Winter", "SQL, query optimization, indexing, transactions", "none", "Fundamentals of Data Science"],
    ["Machine Learning Foundations", "6", "Winter", "Supervised learning, model evaluation, scikit-learn", "none", "Fundamentals of Data Science"],
    ["Distributed Systems", "6", "Winter", "Replication, consensus, fault tolerance", "none", "Fundamentals of Data Science"],
    ["Cloud Computing", "6", "Winter", "IaaS/PaaS, virtualization, containers, Docker", "none", "Fundamentals of Data Science"],
    ["Data Mining I", "6", "Summer", "Clustering, association rules, anomaly detection", "none", "Learning Methods & Models"],
    ["Information Retrieval", "6", "Winter", "Search engines, ranking, text indexing", "none", "Learning Methods & Models"],
    ["Advanced Machine Learning", "6", "Summer", "Deep learning, ensembles, hyperparameter tuning", "Machine Learning Foundations", "Learning Methods & Models"],
    ["Database Systems Implementation", "6", "Winter", "Storage engines, query execution, buffer management", "Advanced Databases", "Learning Methods & Models"],
    ["Big Data Engineering", "6", "Summer", "Spark, ETL pipeline design, data lakes, Airflow", "Advanced Databases", "Data Processing for Data Science"],
    ["Stream Processing", "6", "Winter", "Kafka, Flink, real-time pipelines, windowing", "Big Data Engineering", "Data Processing for Data Science"],
    ["Data Warehouse Technologies", "6", "Winter", "Dimensional modeling, OLAP, ELT processes", "Advanced Databases", "Data Processing for Data Science"],
    ["MLOps in Practice", "6", "Summer", "CI/CD for ML, model serving, monitoring, MLflow", "Machine Learning Foundations", "Data Processing for Data Science"],
    ["Software Engineering for Data Science", "6", "Summer", "Testing, CI/CD, clean code, agile practices", "none", "Applied Data Science"],
    ["Data Visualization", "3", "Summer", "Dashboards, visual analytics, data storytelling", "none", "Applied Data Science"],
    ["Scientific Team Project", "6", "Winter & Summer", "Team-based applied research project", "none; at most twice", "Applied Data Science"],
    ["Seminar Data Engineering", "3", "Winter & Summer", "Literature research, scientific writing, presentation", "none; at most twice", "Applied Data Science"],
    ["Master Thesis", "30", "Winter & Summer", "Independent scientific research", "60 CP completed", "Master Thesis"],
]


def make_handbook():
    d = Doc()
    d.h1("Module Handbook (excerpt) - M.Sc. Data & Knowledge Engineering")
    d.p("Programme structure: 120 CP total = 90 CP coursework + 30 CP master thesis. "
        "Recommended workload: ~30 CP per semester.")

    d.h2("Thematic Area CP Requirements")
    d.p("Each student must earn credits within the following thematic areas:")
    d.table(
        ["Thematic Area", "Min CP", "Max CP"],
        AREA_BUDGETS,
        [100, 35, 35],
    )

    d.h2("Selectable Modules")
    d.table(
        ["Module", "CP", "Offered", "Key skills taught", "Prerequisites", "Thematic Area"],
        HANDBOOK_MODULES,
        [44, 10, 24, 54, 38, 40],
    )

    d.h2("Notes")
    d.p("Modules marked 'Winter & Summer' run every semester. The Seminar and the "
        "Scientific Team Project may each be taken at most twice. The Master Thesis "
        "requires at least 60 CP of completed coursework.")
    d.output(OUT / "module_handbook.pdf")


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    make_cv()
    make_transcript()
    make_career()
    make_handbook()
    for f in sorted(OUT.glob("*.pdf")):
        print(f"wrote {f} ({f.stat().st_size:,} bytes)")
