"""Synthesize a role-specific career-goals PDF for the public demo.

The demo has no real user career document. The visitor chooses a target role
(data_engineer, ml_engineer, or data_analyst) and this module synthesises a
short but realistic career-goals PDF so the career analyst, skill-gap analysis,
and thesis-topic suggestions visibly reflect their choice.
"""
from __future__ import annotations

import pathlib

DEMO_ROLES: dict[str, dict] = {
    "data_engineer": {
        "label": "Data Engineer",
        "target": "Target Role: Data Engineer / Data Platform Engineer",
        "intro": (
            "I am a first-semester DKE Master's student aiming to build and"
            " operate large-scale data infrastructure. My long-term goal is a"
            " senior Data Engineer role at a tech company or data-driven"
            " organisation, designing reliable pipelines and data platforms."
        ),
        "must_have": [
            "Distributed data processing (Spark, Flink, or Airflow)",
            "Database design and query optimisation (SQL and NoSQL)",
            "Data pipeline design, orchestration, and monitoring",
            "Data warehouse and data lake architectures (dimensional modelling)",
            "Container-based deployment (Docker, Kubernetes basics)",
        ],
        "nice_to_have": [
            "Stream processing with Kafka",
            "Cloud platforms (AWS, GCP, or Azure) for data infra",
            "MLOps basics (model serving, monitoring)",
            "Data quality and observability tooling",
            "Knowledge graphs and graph databases",
        ],
        "thesis": (
            "I am open to a research-oriented thesis in scalable data"
            " processing, real-time pipelines, or data-quality at scale."
        ),
    },
    "ml_engineer": {
        "label": "AI / ML Engineer",
        "target": "Target Role: Machine Learning Engineer / AI Engineer",
        "intro": (
            "I am a first-semester DKE Master's student aiming to design,"
            " train, and deploy machine learning systems in production. My"
            " long-term goal is an ML Engineer or Applied Scientist role at"
            " a product company or research lab."
        ),
        "must_have": [
            "Machine learning model development and evaluation (scikit-learn, PyTorch)",
            "Deep learning architectures (CNNs, Transformers, LLMs)",
            "MLOps: model serving, monitoring, CI/CD for ML (MLflow, BentoML)",
            "Feature engineering and large-scale training data pipelines",
            "Experiment tracking and reproducibility",
        ],
        "nice_to_have": [
            "Distributed training (Horovod, DeepSpeed) and GPU infrastructure",
            "Natural language processing and LLM fine-tuning",
            "Explainability and fairness in ML models",
            "Knowledge representation and reasoning",
            "Cloud ML platforms (SageMaker, Vertex AI)",
        ],
        "thesis": (
            "I am open to a research-oriented thesis in deep learning,"
            " LLM alignment, efficient model training, or applied AI for"
            " real-world decision systems."
        ),
    },
    "data_analyst": {
        "label": "Data Analyst / Analytics Engineer",
        "target": "Target Role: Data Analyst / Analytics Engineer",
        "intro": (
            "I am a first-semester DKE Master's student aiming to turn"
            " complex datasets into actionable business insights. My long-term"
            " goal is a Senior Data Analyst or Analytics Engineering role"
            " bridging data engineering and business intelligence."
        ),
        "must_have": [
            "Advanced SQL and data modelling (dimensional / dbt style)",
            "Data visualisation and dashboarding (Tableau, Power BI, or similar)",
            "Statistical analysis and hypothesis testing",
            "ETL/ELT pipelines feeding analytical stores",
            "Data storytelling and communicating findings to stakeholders",
        ],
        "nice_to_have": [
            "Python for data analysis (pandas, matplotlib, seaborn)",
            "Machine learning basics for predictive analytics",
            "A/B testing and experimentation frameworks",
            "Cloud data warehouses (BigQuery, Snowflake, Redshift)",
            "Knowledge graph querying (SPARQL, graph analytics)",
        ],
        "thesis": (
            "I am open to a research-oriented thesis in data-driven"
            " decision making, causal inference, or explainable analytics."
        ),
    },
}

DEFAULT_ROLE = "data_engineer"


def _generic_config(role_label: str) -> dict:
    """Generic career config for a custom/unknown role string."""
    return {
        "label": role_label,
        "target": f"Target Role: {role_label}",
        "intro": (
            f"I am a first-semester DKE Master's student aiming to build a"
            f" career as a {role_label}. I want to combine strong data and"
            f" knowledge engineering fundamentals with practical skills that"
            f" are directly relevant to this role."
        ),
        "must_have": [
            "Strong foundation in data management and processing",
            "Programming skills for data-driven tasks (Python, SQL)",
            "Understanding of machine learning and AI methods",
            "Experience with modern data infrastructure and tooling",
            "Ability to communicate technical findings clearly",
        ],
        "nice_to_have": [
            "Knowledge graphs and semantic data representation",
            "Cloud platforms and containerised deployment",
            "Real-time and streaming data processing",
            "MLOps and model lifecycle management",
            "Domain-specific tooling relevant to the target industry",
        ],
        "thesis": (
            f"I am open to a research-oriented thesis that bridges the DKE"
            f" programme's core areas with practical challenges relevant to"
            f" a {role_label} career."
        ),
    }


def synthesize_demo_career(dest: str | pathlib.Path,
                           role: str | None = None) -> pathlib.Path:
    """Write a role-specific DKE career-goals PDF to ``dest`` and return its path.

    ``role`` may be a preset key from DEMO_ROLES or any short custom string.
    Custom strings get a generic template with the role name substituted in.
    """
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    key = (role or DEFAULT_ROLE).strip()
    if key in DEMO_ROLES:
        cfg = DEMO_ROLES[key]
    elif key:
        cfg = _generic_config(key)
    else:
        cfg = DEMO_ROLES[DEFAULT_ROLE]

    lines = [
        "Career Goals - Data & Knowledge Engineering",
        "",
        cfg["target"],
        "",
        cfg["intro"],
        "",
        "Must-have competencies:",
        *[f"- {s}" for s in cfg["must_have"]],
        "",
        "Nice-to-have competencies:",
        *[f"- {s}" for s in cfg["nice_to_have"]],
        "",
        cfg["thesis"],
    ]

    dest = pathlib.Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    pdf = FPDF()
    pdf.set_margins(15, 15, 15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for line in lines:
        pdf.multi_cell(pdf.epw, 6, line if line else " ",
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.output(str(dest))
    return dest
