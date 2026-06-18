"""
Deterministic study-plan validator (FUTURE.md 1.1).

The planner LLM is told the rules in its prompt, but prompt rules are
suggestions a model ignores ~some of the time (it scheduled a "take at most
twice" module three times in our own sample run). This module re-checks the
rules in code, the second layer of defense-in-depth.

Design:
  * Parsing is separated from checking so each is testable.
  * Markdown tables are parsed by COLUMN HEADER, never by position, so the
    LLM reordering or renaming columns does not silently break the checks.
  * Module-name matching is FUZZY (difflib, stdlib) because the planner
    abbreviates ("Software Engineering for Data" vs "...for Data Science").
    Exact-match blocking false-flags real modules — the anti-hallucination
    lesson from the playbook: fuzzy + advisory before hard-fail.
  * Findings carry a severity: ERROR (a real rule break) vs WARNING (likely,
    but matching/parse uncertainty means a human should glance).

Public API:
    report = validate_plan(plan_md, catalog_md, profile_md)
    report.ok           # bool — no ERRORs
    report.findings     # list[Finding]
    print(report.summary())
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

# Per-semester ECTS sanity band. Outside this is a soft WARNING, not an ERROR —
# a light final semester or a thesis-only semester is legitimate.
CP_MIN, CP_MAX = 12, 36
# How close two module names must be (0..1) to count as "the same module".
NAME_MATCH_THRESHOLD = 0.86


# ─── parsing ──────────────────────────────────────────────────────────────────

@dataclass
class Table:
    headers: list[str]
    rows: list[dict[str, str]]  # each row keyed by header text


def parse_markdown_tables(text: str) -> list[Table]:
    """Extract every GitHub-style pipe table from a markdown blob.

    A table is a header row, a separator row of dashes, then body rows. Cells
    are trimmed; the leading/trailing empty cells from outer pipes are dropped.
    """
    tables: list[Table] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if _is_table_row(lines[i]) and i + 1 < len(lines) and _is_separator(lines[i + 1]):
            headers = _split_row(lines[i])
            rows: list[dict[str, str]] = []
            j = i + 2
            while j < len(lines) and _is_table_row(lines[j]):
                cells = _split_row(lines[j])
                if len(cells) < len(headers):
                    cells += [""] * (len(headers) - len(cells))
                rows.append({h: cells[k] for k, h in enumerate(headers)})
                j += 1
            tables.append(Table(headers=headers, rows=rows))
            i = j
        else:
            i += 1
    return tables


def _is_table_row(line: str) -> bool:
    return line.count("|") >= 2 and line.strip().startswith("|")


def _is_separator(line: str) -> bool:
    return bool(re.fullmatch(r"\s*\|[\s:|-]+\|\s*", line)) and "-" in line


def _split_row(line: str) -> list[str]:
    parts = line.strip().split("|")
    # outer pipes produce empty first/last entries
    if parts and parts[0].strip() == "":
        parts = parts[1:]
    if parts and parts[-1].strip() == "":
        parts = parts[:-1]
    return [p.strip() for p in parts]


def _find_col(headers: list[str], *aliases: str) -> str | None:
    """Return the header whose normalized text contains any alias keyword."""
    norm = {h: _norm(h) for h in headers}
    for alias in aliases:
        a = _norm(alias)
        for h in headers:
            if a in norm[h]:
                return h
    return None


# ─── normalization & fuzzy matching ───────────────────────────────────────────

def _norm(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[*_`]", "", s)                 # markdown emphasis
    s = re.sub(r"[–—]", "-", s)        # en/em dash → hyphen
    s = re.sub(r"[^a-z0-9]+", " ", s)            # punctuation → space
    return re.sub(r"\s+", " ", s).strip()


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _best_match(name: str, candidates: list[str]) -> tuple[str | None, float]:
    """Best fuzzy match for `name` among candidates; also treats a substring
    containment (one name inside the other) as a strong match, since the
    planner often shortens a long official title."""
    best, best_score = None, 0.0
    n = _norm(name)
    for c in candidates:
        nc = _norm(c)
        score = _similar(name, c)
        if n and (n in nc or nc in n):
            score = max(score, 0.92)
        if score > best_score:
            best, best_score = c, score
    return best, best_score


def _to_int(s: str) -> int | None:
    m = re.search(r"\d+", s or "")
    return int(m.group()) if m else None


# ─── domain extraction ─────────────────────────────────────────────────────────

@dataclass
class CatalogModule:
    name: str
    cp: int | None
    prerequisites: str
    take_limit: int | None  # e.g. "at most twice" → 2
    thematic_area: str = ""


@dataclass
class PlannedModule:
    name: str
    cp: int | None
    semester_index: int     # 0-based order of appearance


@dataclass
class Semester:
    label: str
    modules: list[PlannedModule]
    stated_total: int | None


def parse_catalog(catalog_md: str) -> dict[str, CatalogModule]:
    """The curator's module table → {normalized name: CatalogModule}."""
    out: dict[str, CatalogModule] = {}
    for t in parse_markdown_tables(catalog_md):
        mcol = _find_col(t.headers, "module", "name")
        if not mcol:
            continue
        cpcol = _find_col(t.headers, "cp", "credit", "ects")
        prereqcol = _find_col(t.headers, "prerequisite", "prereq")
        areacol = _find_col(t.headers, "thematic area", "area", "subject area", "category")
        for row in t.rows:
            name = row.get(mcol, "").strip()
            if not name or _norm(name) in {"module", "name"}:
                continue
            prereq = row.get(prereqcol, "") if prereqcol else ""
            area = row.get(areacol, "") if areacol else ""
            out[_norm(name)] = CatalogModule(
                name=name,
                cp=_to_int(row.get(cpcol, "")) if cpcol else None,
                prerequisites=prereq,
                take_limit=_parse_take_limit(prereq + " " + " ".join(row.values())),
                thematic_area=area if area.lower() not in {"n/a", "na", ""} else "",
            )
    return out


def parse_area_budgets(catalog_md: str) -> dict[str, tuple[str, int, int]]:
    """Extract the area CP budget table the curator outputs.

    Returns {normalized_area_name: (original_name, min_cp, max_cp)}.
    """
    budgets: dict[str, tuple[str, int, int]] = {}
    for t in parse_markdown_tables(catalog_md):
        area_col = _find_col(t.headers, "thematic area", "area", "subject area")
        min_col = _find_col(t.headers, "min", "minimum")
        max_col = _find_col(t.headers, "max", "maximum")
        if not (area_col and min_col and max_col):
            continue
        for row in t.rows:
            area = row.get(area_col, "").strip()
            mn = _to_int(row.get(min_col, ""))
            mx = _to_int(row.get(max_col, ""))
            if area and mn is not None and mx is not None:
                budgets[_norm(area)] = (area, mn, mx)
    return budgets


_NUM_WORDS = {"once": 1, "twice": 2, "two": 2, "three": 3, "thrice": 3}


def _parse_take_limit(text: str) -> int | None:
    """Detect 'at most twice' / 'may be taken 2 times' style limits."""
    t = text.lower()
    if "at most" in t or "may be taken" in t or "taken at most" in t:
        for word, n in _NUM_WORDS.items():
            if word in t:
                return n
        m = re.search(r"(\d+)\s*times?", t)
        if m:
            return int(m.group(1))
    return None


def parse_plan(plan_md: str) -> list[Semester]:
    """The planner's output → ordered semesters with their module rows.

    Semester boundaries are markdown headings that look like a semester
    ('### Semester 3', '#### 4th Semester (Winter ...)'). Each semester owns the
    tables and the '**Total CP:** N' line that follow it until the next heading.
    """
    semesters: list[Semester] = []
    # split on headings, keeping the heading text
    blocks = re.split(r"(?m)^(#{2,4}\s+.*)$", plan_md)
    # blocks: [pre, heading1, body1, heading2, body2, ...]
    sem_order = 0
    for k in range(1, len(blocks), 2):
        heading = blocks[k].strip("# ").strip()
        body = blocks[k + 1] if k + 1 < len(blocks) else ""
        if not _looks_like_semester(heading):
            continue
        mods: list[PlannedModule] = []
        for t in parse_markdown_tables(body):
            mcol = _find_col(t.headers, "module", "name")
            cpcol = _find_col(t.headers, "cp", "credit", "ects")
            if not mcol:
                continue
            for row in t.rows:
                name = row.get(mcol, "").strip()
                if not name or _norm(name) in {"module", "name", "total"}:
                    continue
                mods.append(PlannedModule(
                    name=name,
                    cp=_to_int(row.get(cpcol, "")) if cpcol else None,
                    semester_index=sem_order,
                ))
        stated = _stated_total(body)
        semesters.append(Semester(label=heading, modules=mods, stated_total=stated))
        sem_order += 1
    return semesters


def _looks_like_semester(heading: str) -> bool:
    h = heading.lower()
    return "semester" in h or bool(re.search(r"\b\d(st|nd|rd|th)\b", h))


def _stated_total(body: str) -> int | None:
    m = re.search(r"total\s*cp[:* ]*\s*(\d+)", body, re.I)
    return int(m.group(1)) if m else None


def parse_completed(profile_md: str) -> list[str]:
    """Completed-module names from the profile analyst's table."""
    done: list[str] = []
    for t in parse_markdown_tables(profile_md):
        mcol = _find_col(t.headers, "module", "name")
        gradecol = _find_col(t.headers, "grade", "cp", "credit")
        if not mcol or not gradecol:   # a completed-modules table has both
            continue
        for row in t.rows:
            name = row.get(mcol, "").strip()
            if name and _norm(name) not in {"module", "name"}:
                done.append(name)
    return done


def parse_completed_detailed(profile_md: str) -> list[tuple[str, int]]:
    """Completed modules as (name, cp) from the profile tables (cp 0 if absent).

    Used to map already-earned credits to thematic areas, so the planner only has
    to cover what's left."""
    out: list[tuple[str, int]] = []
    for t in parse_markdown_tables(profile_md):
        mcol = _find_col(t.headers, "module", "name")
        cpcol = _find_col(t.headers, "cp", "credit", "ects")
        if not mcol or not cpcol:
            continue
        for row in t.rows:
            name = row.get(mcol, "").strip()
            if not name or _norm(name) in {"module", "name", "total"}:
                continue
            out.append((name, _to_int(row.get(cpcol, "")) or 0))
    return out


def parse_completed_cp(profile_md: str) -> int:
    """Sum of CP across completed-module tables in the profile (0 if none found)."""
    return sum(cp for _, cp in parse_completed_detailed(profile_md))


# ─── checking ──────────────────────────────────────────────────────────────────

@dataclass
class Finding:
    severity: str   # "ERROR" | "WARNING"
    rule: str
    message: str


@dataclass
class ValidationReport:
    findings: list[Finding] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not any(f.severity == "ERROR" for f in self.findings)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "ERROR"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "WARNING"]

    def summary(self) -> str:
        head = "PASS — all checks satisfied" if self.ok else \
               f"FAIL — {len(self.errors)} error(s)"
        lines = [head]
        for f in self.findings:
            lines.append(f"  [{f.severity}] {f.rule}: {f.message}")
        if self.stats:
            lines.append(f"  stats: {self.stats}")
        return "\n".join(lines)


def validate_plan(plan_md: str, catalog_md: str, profile_md: str = "",
                  constraints=None, requirements=None,
                  completed_by_area=None, offered_md=None,
                  completed_cp_override=None) -> ValidationReport:
    """Check a generated plan against the curator catalog and student profile.

    Robust to missing inputs: if the catalog is empty, grounding/prereq checks
    are skipped with a WARNING rather than crashing.

    `constraints` is an optional study_planner.inputs.PlanConstraints. When given,
    three extra checks run: horizon (ERROR), cp-preference (WARNING) and
    feasibility (WARNING). When None, behavior is unchanged (backward compatible).

    `requirements` is an optional study_planner.requirements.ProgramRequirements
    parsed from the uploaded study & examination schedule. When provided it is the
    AUTHORITATIVE source of thematic-area CP rules (overriding the LLM curator's
    guessed budgets), and unlocks: completed+planned per-area accounting,
    coursework-total and thesis checks, and the required team-project caveat. When
    None, the area-budget check uses the curator's table as before.

    `completed_by_area` is an optional {normalized_area: cp} dict parsed
    deterministically from the transcript (requirements.parse_completed_by_area).
    When given it is the AUTHORITATIVE completed-credit count per area, replacing
    the fragile fuzzy-match of the profile's module names to the catalog (which
    silently under-counted German/un-catalogued module names).
    """
    rep = ValidationReport()
    catalog = parse_catalog(catalog_md)
    semesters = parse_plan(plan_md)
    completed = parse_completed(profile_md)

    rep.stats = {
        "catalog_modules": len(catalog),
        "semesters": len(semesters),
        "planned_modules": sum(len(s.modules) for s in semesters),
        "completed_modules": len(completed),
    }

    if not semesters:
        rep.findings.append(Finding("ERROR", "parse",
            "no semesters parsed from the plan — output format may have changed"))
        return rep
    if not catalog:
        rep.findings.append(Finding("WARNING", "parse",
            "no module catalog parsed — grounding & prerequisite checks skipped"))

    catalog_names = [m.name for m in catalog.values()]
    # Eligibility set for grounding: the OFFERED menu (Python-curated + capped) when
    # provided, else the full catalog. Grounding against the menu (not just the
    # catalog) stops the planner reaching past the structural cap to any catalog
    # module — a real catalog name that wasn't offered is still off-menu. Catalog
    # lookups (CP, take-limit, area) always use the full catalog below.
    eligible_names = catalog_names
    if offered_md:
        offered = [m.name for m in parse_catalog(offered_md).values()]
        if offered:                      # fall back to catalog if the menu didn't parse
            eligible_names = offered
    # name → earliest semester index it is scheduled in (for prereq ordering)
    scheduled_at: dict[str, int] = {}
    take_counts: dict[str, int] = {}

    for sem in semesters:
        # CP arithmetic + band
        cps = [m.cp for m in sem.modules if m.cp is not None]
        actual = sum(cps)
        if sem.stated_total is not None and cps and actual != sem.stated_total:
            rep.findings.append(Finding("ERROR", "cp-total",
                f"{sem.label}: module CP sum is {actual} but stated total is "
                f"{sem.stated_total}"))
        total_for_band = sem.stated_total if sem.stated_total is not None else actual
        if total_for_band and not (CP_MIN <= total_for_band <= CP_MAX):
            rep.findings.append(Finding("WARNING", "cp-load",
                f"{sem.label}: {total_for_band} CP is outside the "
                f"{CP_MIN}-{CP_MAX} band"))

        for m in sem.modules:
            # 1. grounding: planned module must be on the eligible menu (offered
            # menu when provided, else the full catalog).
            ematch, escore = _best_match(m.name, eligible_names) if eligible_names else (None, 0)
            if eligible_names and escore < NAME_MATCH_THRESHOLD:
                where = "offered module menu" if offered_md else "module catalog"
                rep.findings.append(Finding("ERROR", "grounding",
                    f"'{m.name}' ({sem.label}) is not on the {where} "
                    f"(closest: '{ematch}' @ {escore:.2f}) — not eligible / possible hallucination"))
                continue

            # Resolve the canonical catalog entry (CP/area/take-limit) from the FULL
            # catalog, even when grounding was against the narrower offered menu.
            match, _score = _best_match(m.name, catalog_names) if catalog_names else (ematch, escore)
            canonical = match or m.name
            # 2. no retakes of completed modules
            dmatch, dscore = _best_match(m.name, completed) if completed else (None, 0)
            if completed and dscore >= NAME_MATCH_THRESHOLD:
                rep.findings.append(Finding("ERROR", "retake",
                    f"'{m.name}' ({sem.label}) was already completed "
                    f"(matches '{dmatch}')"))

            cm = catalog.get(_norm(canonical))
            # 3. CP consistency: the planned CP must match the catalog's CP.
            # The planner falsifies a module's CP to force a semester/total to a
            # target (observed: it wrote a 6 CP module as 3 CP to hit "9 CP
            # remaining"). Grounding only checks the name exists, so this slipped
            # through — an ERROR because it produces an arithmetically false plan.
            if cm and cm.cp is not None and m.cp is not None and cm.cp != m.cp:
                rep.findings.append(Finding("ERROR", "cp-mismatch",
                    f"'{canonical}' ({sem.label}) is listed as {m.cp} CP but the "
                    f"catalog says {cm.cp} CP — do not alter a module's credit value"))

            # 4. take-limit
            take_counts[canonical] = take_counts.get(canonical, 0) + 1
            if cm and cm.take_limit and take_counts[canonical] > cm.take_limit:
                rep.findings.append(Finding("ERROR", "take-limit",
                    f"'{canonical}' scheduled {take_counts[canonical]}x but the "
                    f"handbook allows at most {cm.take_limit}"))

            scheduled_at.setdefault(_norm(canonical), sem.modules[0].semester_index)
            scheduled_at[_norm(canonical)] = min(
                scheduled_at[_norm(canonical)], m.semester_index)

    # 4. prerequisites — checked after the full schedule is known
    for sem in semesters:
        for m in sem.modules:
            match, score = _best_match(m.name, catalog_names) if catalog_names else (None, 0)
            if not match or score < NAME_MATCH_THRESHOLD:
                continue
            cm = catalog[_norm(match)]
            for prereq in _split_prereqs(cm.prerequisites):
                pmatch, pscore = _best_match(prereq, catalog_names + completed)
                if pscore < NAME_MATCH_THRESHOLD:
                    continue  # free-text prereq ("60 CP completed") — skip
                done = completed and _best_match(prereq, completed)[1] >= NAME_MATCH_THRESHOLD
                earlier = (_norm(pmatch) in scheduled_at
                           and scheduled_at[_norm(pmatch)] < m.semester_index)
                if not (done or earlier):
                    rep.findings.append(Finding("WARNING", "prerequisite",
                        f"'{m.name}' ({sem.label}) needs '{prereq}', which is "
                        f"neither completed nor scheduled earlier"))

    # 5. thematic-area CP budgets.
    # Source of truth: the uploaded schedule (requirements) when provided —
    # parsed deterministically, so it fixes the curator's mis-read min/max — else
    # the curator's own table. With requirements we also count ALREADY-COMPLETED
    # credits toward each area (so only the remainder must be planned) and enforce
    # the coursework total, thesis, and required team-project caveats.
    use_req = bool(requirements is not None and getattr(requirements, "areas", None))
    if use_req:
        _check_area_budgets_with_requirements(
            rep, semesters, catalog, catalog_names, profile_md, constraints,
            requirements, completed_by_area)
    else:
        area_budgets = parse_area_budgets(catalog_md)
        if area_budgets:
            area_cp: dict[str, int] = {}
            area_display: dict[str, str] = {}
            for sem in semesters:
                for m in sem.modules:
                    match, score = _best_match(m.name, catalog_names) if catalog_names else (None, 0)
                    if not match or score < NAME_MATCH_THRESHOLD:
                        continue
                    cm = catalog.get(_norm(match))
                    if cm and cm.thematic_area:
                        key = _norm(cm.thematic_area)
                        area_cp[key] = area_cp.get(key, 0) + (m.cp or 0)
                        area_display[key] = cm.thematic_area
            # NOTE: these min/max come from the LLM curator's catalog, not an
            # authoritative schedule, so they are unreliable (a real run invented
            # min=30 for every area and pushed the planner to ADD modules). Per the
            # playbook 7.3 "ERROR only for hard rules", these are WARNINGs; the hard
            # "do not over-plan" rule is the deterministic coursework-overplan check
            # in _check_constraints, which uses transcript-counted completed CP.
            for norm_area, (orig_name, mn, mx) in area_budgets.items():
                total = area_cp.get(norm_area, 0)
                display = area_display.get(norm_area, orig_name)
                if total < mn:
                    rep.findings.append(Finding("WARNING", "area-budget",
                        f"'{display}': {total} CP planned but inferred minimum is {mn} CP"))
                elif total > mx:
                    rep.findings.append(Finding("WARNING", "area-budget",
                        f"'{display}': {total} CP planned exceeds inferred maximum of {mx} CP"))
            rep.stats["area_cp"] = {area_display.get(k, k): v for k, v in area_cp.items()}

    # 6. student constraints (time horizon + per-semester CP preferences). When
    # there is no authoritative schedule, _check_area_budgets_with_requirements did
    # not run, so the deterministic "don't over-plan the remaining credits" ERROR
    # must come from here instead (check_overplan).
    if constraints is not None:
        _check_constraints(rep, semesters, completed, profile_md, constraints,
                           check_overplan=not use_req,
                           completed_cp_override=completed_cp_override)

    return rep


def _semester_cp(sem: "Semester") -> int:
    """A semester's CP: the stated total if present, else the module CP sum."""
    if sem.stated_total is not None:
        return sem.stated_total
    return sum(m.cp for m in sem.modules if m.cp is not None)


def _check_constraints(rep: ValidationReport, semesters: list["Semester"],
                       completed: list[str], profile_md: str, constraints,
                       check_overplan: bool = False,
                       completed_cp_override: int | None = None) -> None:
    """horizon (ERROR), cp-preference (WARNING), feasibility (WARNING), and —
    when check_overplan — coursework-overplan (ERROR) for the no-schedule path.

    `completed_cp_override`, when given, is the deterministic transcript-derived
    completed-CP total used instead of the LLM profile's count (which under-reports
    — it read 81 as 46), so the over-plan threshold is exact."""
    # horizon — the plan must not span more semesters than the student wants
    if len(semesters) > constraints.target_semesters:
        rep.findings.append(Finding("ERROR", "horizon",
            f"plan spans {len(semesters)} semesters but the student wants to "
            f"finish in {constraints.target_semesters}"))

    # cp-preference — each semester's load should be near its stated target
    for i, sem in enumerate(semesters, start=1):
        target = constraints.target_for_semester(i)
        if target is None:
            continue
        actual = _semester_cp(sem)
        if actual and abs(actual - target) > 3:
            rep.findings.append(Finding("WARNING", "cp-preference",
                f"{sem.label}: {actual} CP planned but the student asked for "
                f"~{target} CP"))

    # feasibility — can the remaining coursework even fit in the target horizon?
    from study_planner.inputs import MAX_SANE_LOAD
    completed_cp = (completed_cp_override if completed_cp_override is not None
                    else parse_completed_cp(profile_md))
    remaining = constraints.coursework_cp() - completed_cp
    capacity = constraints.target_semesters * MAX_SANE_LOAD
    rep.stats["remaining_coursework_cp"] = remaining

    # coursework-overplan (ERROR) — the no-schedule equivalent of the check in
    # _check_area_budgets_with_requirements. Without a schedule the per-area guards
    # are off, so this deterministic "plan only what's left" rule (completed CP from
    # the transcript-derived profile, coursework total from the degree default) is
    # the load-bearing protection against re-planning the whole degree. Over is an
    # ERROR (triggers a re-plan); being short stays a WARNING (a partial plan is OK).
    if check_overplan:
        planned_cw = sum(
            m.cp for sem in semesters for m in sem.modules
            if m.cp and "thesis" not in _norm(m.name)
            and "masterarbeit" not in _norm(m.name))
        need = max(0, remaining)
        if planned_cw > need:
            rep.findings.append(Finding("ERROR", "coursework-overplan",
                f"plan schedules {planned_cw} coursework CP but only {need} remain "
                f"({completed_cp} of {constraints.coursework_cp()} CP already "
                f"completed) — plan only the remaining credits, then the thesis"))

    if remaining > capacity:
        need = -(-remaining // constraints.target_semesters)  # ceil
        rep.findings.append(Finding("WARNING", "feasibility",
            f"~{remaining} CP of coursework remain but only {capacity} CP fit in "
            f"{constraints.target_semesters} semesters at {MAX_SANE_LOAD} CP each "
            f"(~{need} CP/semester needed) — finishing in "
            f"{constraints.target_semesters} may be infeasible"))


def _check_area_budgets_with_requirements(rep: ValidationReport, semesters,
                                          catalog, catalog_names, profile_md,
                                          constraints, requirements,
                                          completed_by_area=None) -> None:
    """Authoritative area-budget check using the uploaded schedule.

    Counts completed + planned CP per thematic area (so already-earned credits
    reduce what must be planned), enforces each area's [min,max], the coursework
    total, the thesis, and any required team/group project.

    Completed credits per area come from `completed_by_area` (deterministic,
    parsed from the transcript) when provided; otherwise they fall back to fuzzy-
    matching the profile's completed-module names to the catalog."""
    def _area_of(name: str):
        match, score = _best_match(name, catalog_names) if catalog_names else (None, 0)
        if not match or score < NAME_MATCH_THRESHOLD:
            return None, None
        cm = catalog.get(_norm(match))
        if cm and cm.thematic_area:
            return _norm(cm.thematic_area), cm
        return None, cm

    areas = requirements.areas  # norm_key -> AreaRequirement
    planned: dict[str, int] = {}
    display = {k: a.name for k, a in areas.items()}
    # Planned coursework CP that maps to NO thematic area (and isn't the thesis).
    # Such modules used to escape the coursework-total entirely, hiding over-
    # planning (a 9 CP unmapped "Individual Scientific Project" slipped through a
    # PASS). They are still coursework, so they must count toward the total.
    planned_unmapped_cp = 0

    for sem in semesters:
        for m in sem.modules:
            key, cm = _area_of(m.name)
            if not key:
                nm = _norm(m.name)
                if "thesis" not in nm and "masterarbeit" not in nm:
                    planned_unmapped_cp += (m.cp or 0)
                continue
            planned[key] = planned.get(key, 0) + (m.cp or 0)
            display.setdefault(key, cm.thematic_area if cm else key)

    # Completed credits per area: authoritative deterministic counts from the
    # transcript when provided, else fuzzy-map the profile's module names.
    completed_names = [n for n, _ in parse_completed_detailed(profile_md)]
    if completed_by_area is not None:
        done: dict[str, int] = dict(completed_by_area)
    else:
        done = {}
        for name, cp in parse_completed_detailed(profile_md):
            key, _cm = _area_of(name)
            if key:
                done[key] = done.get(key, 0) + cp

    # Required team/group project — satisfied if any completed OR planned module
    # name looks like a team project. We scan names directly because the real
    # one ("Wissenschaftliches Teamprojekt") never fuzzy-matches the English
    # catalog, so the per-area mapping would miss it and false-warn.
    planned_names = [m.name for s in semesters for m in s.modules]
    has_team_project = any(
        ("teamprojekt" in _norm(n) or "team project" in _norm(n)
         or "teamproject" in _norm(n) or "project" in _norm(n))
        for n in completed_names + planned_names)

    # per-area [min,max] on completed + planned
    for key, a in areas.items():
        d, p = done.get(key, 0), planned.get(key, 0)
        total, name = d + p, display.get(key, a.name)
        if total < a.min_cp:
            rep.findings.append(Finding("ERROR", "area-budget",
                f"'{name}': {total} CP (completed {d} + planned {p}) is below the "
                f"minimum of {a.min_cp} CP"))
        elif total > a.max_cp:
            rep.findings.append(Finding("ERROR", "area-budget",
                f"'{name}': {total} CP (completed {d} + planned {p}) exceeds the "
                f"maximum of {a.max_cp} CP"))
        if a.project_cp and not has_team_project:
            rep.findings.append(Finding("WARNING", "area-project",
                f"'{name}' requires a team/group project ({a.project_cp} CP) — "
                f"none detected among planned or completed modules"))

    # coursework total: completed + planned across all areas should equal the
    # programme's coursework requirement (e.g. 90 = 120 total − 30 thesis).
    # OVER-planning is an ERROR — the core "plan only the remaining credits" rule:
    # scheduling modules the student doesn't need to graduate is a real defect
    # (the planner did exactly this — 33 CP planned when 9 remained). Falling
    # SHORT stays a WARNING (a deliberately partial plan is legitimate).
    cw_target = requirements.coursework_cp
    if cw_target is None and constraints is not None:
        cw_target = constraints.coursework_cp()
    # Count area-mapped planned + completed AND any unmapped planned coursework.
    total_cw = sum(done.get(k, 0) + planned.get(k, 0) for k in areas) + planned_unmapped_cp
    if cw_target and total_cw > cw_target:
        planned_cw = sum(planned.get(k, 0) for k in areas) + planned_unmapped_cp
        needed = cw_target - sum(done.get(k, 0) for k in areas)
        rep.findings.append(Finding("ERROR", "coursework-overplan",
            f"plan schedules {planned_cw} coursework CP but only {max(0, needed)} "
            f"remain ({total_cw} completed+planned vs the {cw_target} CP required) "
            f"— plan only the remaining credits"))
    elif cw_target and total_cw < cw_target:
        rep.findings.append(Finding("WARNING", "coursework-total",
            f"coursework totals {total_cw} CP (completed + planned) but the "
            f"programme requires {cw_target} CP — {cw_target - total_cw} CP short"))

    # thesis present (scheduled or already done)?
    if requirements.thesis_cp:
        all_names = [m.name for s in semesters for m in s.modules] + \
                    [n for n, _ in parse_completed_detailed(profile_md)]
        if not any("thesis" in _norm(n) for n in all_names):
            rep.findings.append(Finding("WARNING", "thesis",
                f"no Master's thesis ({requirements.thesis_cp} CP) is scheduled "
                f"or completed"))

    # breakdowns for the UI
    rep.stats["area_cp"] = {display.get(k, k): done.get(k, 0) + planned.get(k, 0)
                            for k in areas}
    rep.stats["area_detail"] = {
        display.get(k, k): {"completed": done.get(k, 0), "planned": planned.get(k, 0),
                            "min": a.min_cp, "max": a.max_cp, "project_cp": a.project_cp}
        for k, a in areas.items()}
    rep.stats["coursework_total"] = total_cw
    if planned_unmapped_cp:
        rep.stats["planned_unmapped_cp"] = planned_unmapped_cp
    if cw_target:
        rep.stats["coursework_required"] = cw_target


def build_correction(report: "ValidationReport") -> str:
    """Turn a failed report into a blunt correction directive for a re-plan.

    The planner ignores the up-front 'plan EXACTLY N CP' instruction (proven on a
    real run). Feeding the SPECIFIC errors back — with the offending numbers the
    validator already computed — is the enforcement layer: the model corrects far
    more reliably against concrete 'you did X, it must be Y' feedback than against
    a general rule. Returns '' when the plan passed (no correction needed)."""
    if report.ok:
        return ""
    lines = ["CORRECTION REQUIRED - your previous plan FAILED these deterministic "
             "checks. Fix EVERY one without introducing new violations:"]
    for f in report.errors:
        lines.append(f"  - [{f.rule}] {f.message}")
    st = report.stats or {}
    req = st.get("coursework_required")
    if req is not None:
        done = sum(d.get("completed", 0) for d in st.get("area_detail", {}).values())
        lines.append(f"Plan EXACTLY {max(0, req - done)} coursework CP in total (you have "
                     f"{done} of {req}); do NOT exceed any area's maximum; then the thesis.")
    elif st.get("remaining_coursework_cp") is not None:
        # No-schedule path: no per-area detail, but the remaining total is known.
        rem = max(0, st["remaining_coursework_cp"])
        lines.append(f"Plan EXACTLY {rem} coursework CP in total — no more — then the "
                     f"thesis. Being a little short is acceptable; over-running is not.")
    lines.append("Remove or swap modules until every area is within [Min, Max] and the "
                 "plan fits the requested number of semesters.")
    lines.append("NEVER change a module's credit value to hit a total — use each module's "
                 "exact CP from the available list. If no combination reaches the target "
                 "without exceeding an area maximum, plan FEWER CP (being a little short is "
                 "acceptable; over-running a maximum or faking a CP value is not).")
    return "\n".join(lines)


def render_area_budget_table(report: "ValidationReport") -> str:
    """Deterministic area budget table from the validator's own counts.

    The planner's self-computed budget table is unreliable (it labelled a 30/max-24
    area 'OK'). This renders the SAME columns from `stats['area_detail']`, which is
    computed in code — so the validity the user sees is trustworthy. Empty when no
    area detail is available (no requirements schedule)."""
    detail = (report.stats or {}).get("area_detail")
    if not detail:
        return ""
    lines = ["| Area | Completed CP | Newly Planned CP | Total | Min | Max | Status |",
             "|---|---|---|---|---|---|---|"]
    for name, d in detail.items():
        total = d.get("completed", 0) + d.get("planned", 0)
        mn, mx = d.get("min", 0), d.get("max", 0)
        status = "OK" if mn <= total <= mx else ("OVER" if total > mx else "SHORT")
        lines.append(f"| {name} | {d.get('completed', 0)} | {d.get('planned', 0)} | "
                     f"{total} | {mn} | {mx} | {status} |")
    return "\n".join(lines)


def _split_prereqs(text: str) -> list[str]:
    t = (text or "").strip()
    if not t or _norm(t) in {"none", "n a", "na", ""}:
        return []
    # strip free-text tails like "; at most twice", "60 CP completed"
    parts = re.split(r"[,;]| and ", t)
    out = []
    for p in parts:
        p = p.strip()
        if not p or _norm(p) in {"none", "n a", "na"}:
            continue
        if re.search(r"\bcp\b|\bcredits?\b|at most|times?", p.lower()):
            continue
        out.append(p)
    return out
