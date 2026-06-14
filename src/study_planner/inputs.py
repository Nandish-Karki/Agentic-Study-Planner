"""
Student planning constraints (BUILD_PLAN.md §2).

These are the knobs a student sets before a plan is generated:
  * how many semesters they want to finish remaining coursework in, and
  * how many credit points (CP) they want to take in specific semesters.

The constraints flow two ways:
  1. into the planner LLM prompt as soft targets ("aim for this"), and
  2. into the deterministic validator as enforceable checks (horizon /
     cp-preference / feasibility) — because prompt targets are suggestions a
     model ignores some of the time. The validator is the second line of defense.

This module is pure data + rendering: no LLM, no I/O. It is unit-testable on its
own and carries no per-user state.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Sane upper bound on a single semester's CP load. A request to finish in N
# semesters that would force more than this per semester is flagged infeasible.
MAX_SANE_LOAD = 36

# Default remaining COURSEWORK credit totals by degree (thesis excluded), used by
# the feasibility check when the handbook doesn't state an explicit total. German
# ECTS norms: 120-CP master = 90 coursework + 30 thesis; 180-CP bachelor ≈ 168
# coursework + ~12 thesis. These are approximations — feasibility is a WARNING,
# never a hard fail, precisely because the real total varies by programme.
DEFAULT_COURSEWORK_CP = {"master": 90, "bachelor": 168}


@dataclass
class PlanConstraints:
    """What the student wants from the plan, beyond the documents themselves."""
    degree_type: str = "master"               # "bachelor" | "master"
    target_semesters: int = 4                 # finish remaining coursework in N
    default_cp_per_semester: int | None = None  # soft per-semester target
    # 1-based remaining-semester index → CP target, e.g. {1: 20, 2: 30}
    cp_overrides: dict[int, int] = field(default_factory=dict)
    # Explicit remaining coursework CP; if None, fall back to the degree default.
    total_coursework_cp: int | None = None

    def __post_init__(self):
        self.degree_type = (self.degree_type or "master").strip().lower()
        if self.degree_type not in ("bachelor", "master"):
            raise ValueError(
                f"degree_type must be 'bachelor' or 'master', got {self.degree_type!r}")
        if self.target_semesters < 1:
            raise ValueError("target_semesters must be >= 1")
        # normalize override keys to ints
        self.cp_overrides = {int(k): int(v) for k, v in self.cp_overrides.items()}

    def coursework_cp(self) -> int:
        """Remaining-coursework CP total to plan for (explicit or degree default)."""
        if self.total_coursework_cp is not None:
            return self.total_coursework_cp
        return DEFAULT_COURSEWORK_CP[self.degree_type]

    def target_for_semester(self, one_based_index: int) -> int | None:
        """CP target for the i-th remaining semester: an override, else the default."""
        if one_based_index in self.cp_overrides:
            return self.cp_overrides[one_based_index]
        return self.default_cp_per_semester

    def render_for_prompt(self) -> str:
        """A compact, human-readable constraints line for the planner prompt."""
        parts = [
            f"Finish remaining coursework in {self.target_semesters} semester(s)."
        ]
        if self.cp_overrides:
            spec = ", ".join(
                f"semester {i}: ~{cp} CP"
                for i, cp in sorted(self.cp_overrides.items()))
            parts.append(f"Per-semester credit targets — {spec}.")
        if self.default_cp_per_semester:
            parts.append(
                f"For other semesters aim for ~{self.default_cp_per_semester} CP.")
        parts.append(
            "Honor these targets where the rules allow; if a target is "
            "infeasible, get as close as possible and say so explicitly.")
        return " ".join(parts)
