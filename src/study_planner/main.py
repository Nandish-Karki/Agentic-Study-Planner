"""
Entry point for the Agentic Study Planner crew.

CLI:   python -m study_planner.main [data-dir]      (default: data)
API:   from study_planner import plan_studies
       result = plan_studies("data")
"""
import sys
import os
import json
import time
import pathlib
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


def force_utf8_stdout() -> None:
    """Make stdout/stderr UTF-8 so non-cp1252 chars in input documents can't
    crash the run on a Windows console.

    crewai's verbose printer echoes tool results (raw PDF text) to stdout; on a
    cp1252 console a single char like the male sign or an em-dash raises
    UnicodeEncodeError and kills the whole crew mid-run — wasting LLM quota for
    nothing. Reconfiguring to UTF-8 with errors='replace' removes that failure
    mode. Call from CLI entry points only (the API/worker run on UTF-8 Linux).
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _dump_artifacts(out_dir, sections: dict) -> None:
    """Write each ``{filename: text}`` section into ``out_dir`` as UTF-8.

    Shared by the step-by-step debug dump (plan_studies) and the eval harness
    (scripts/run_eval.py) so the two artifact writers can't drift.
    """
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for fname, content in sections.items():
        (out / fname).write_text("" if content is None else str(content), encoding="utf-8")


def _select_menu_modules(
    catalog_md: str,
    requirements,
    completed_by_area: dict,
    completed_module_names: list[str],
    skill_gaps: str = "",
) -> dict | None:
    """Two-pass curation of the curator/handbook module table to the remaining
    budget. Returns a 'menu' dict consumed by BOTH _render_menu (the planner's text
    menu) and _assemble_coursework_plan (the deterministic backstop), so the offered
    menu and the code-built fallback can never disagree.

    Pass A reserves each area's remaining MINIMUM first (sum of mins <= coursework
    total, so it always fits) -- the menu can then satisfy every minimum; Pass B
    fills the rest of the budget by gap relevance / CP across areas. Still capped by
    remaining_total AND each area's max, so it can't over-plan.

    Returns None when there is nothing to curate (no requirements schedule, or an
    unparseable catalog); the caller then falls back to the raw catalog markdown.
    """
    import re
    from study_planner.validate import (
        parse_markdown_tables, _find_col, _norm, _best_match, _to_int,
        NAME_MATCH_THRESHOLD,
    )

    if not requirements or not requirements.areas:
        return None

    area_keys = list(requirements.areas.keys())          # normalized strings
    area_display = {k: a.name for k, a in requirements.areas.items()}
    all_display = list(area_display.values())

    # Find Table 1: the module catalog (has both a Module column and a Thematic Area column)
    module_table = None
    for t in parse_markdown_tables(catalog_md):
        if _find_col(t.headers, "module", "name") and _find_col(
                t.headers, "thematic area", "area", "subject area", "category"):
            module_table = t
            break
    if module_table is None:
        return None  # curator didn't produce a parseable table -- fall back

    mcol = _find_col(module_table.headers, "module", "name")
    acol = _find_col(module_table.headers, "thematic area", "area", "subject area", "category")
    # Keep all original columns EXCEPT Thematic Area (we're using it for grouping, not display)
    keep_cols = [h for h in module_table.headers if h != acol]

    # Group rows by corrected area, filtering completed modules; deduplicate by name
    by_area: dict[str, list[dict]] = {k: [] for k in area_keys}
    seen_names: set[str] = set()
    unmatched: list[dict] = []

    for row in module_table.rows:
        name = row.get(mcol, "").strip()
        if not name or _norm(name) in {"module", "name"}:
            continue
        norm_name = _norm(name)
        if norm_name in seen_names:
            continue  # deduplicate (same module listed multiple times for different semesters)
        seen_names.add(norm_name)

        # Filter already-completed modules
        if completed_module_names:
            _, score = _best_match(name, completed_module_names)
            if score >= NAME_MATCH_THRESHOLD:
                continue

        # Map curator's area string → authoritative area key
        raw_area = row.get(acol, "").strip()
        matched_key = None
        if raw_area and raw_area.lower() not in {"n/a", "na", ""}:
            matched_display, score = _best_match(raw_area, all_display)
            if matched_display and score >= 0.72:
                matched_key = next(
                    (k for k in area_keys if area_display[k] == matched_display), None)

        if matched_key:
            by_area[matched_key].append(row)
        else:
            unmatched.append(row)

    # ── Structural credit-budget guard (two-pass selection) ─────────────────
    # The planner ignores textual CP caps (proven: it planned 30 CP when 9
    # remained), so we curate the MENU itself to the remaining budget. A single
    # greedy pass capped only by each area's MAX starves the low-priority areas
    # BELOW their minimum for a new student (who must hit all four minimums at
    # once) -- the observed bug: Fundamentals 9/12, Applied 12/18. So we select
    # in two passes:
    #   Pass A reserves each area's MINIMUM first (sum of mins <= coursework
    #          total, so this always fits) -- the menu can then satisfy every min;
    #   Pass B fills the remaining budget by gap relevance / CP across all areas.
    # Still capped by remaining_total AND each area's max, so it can't over-plan.
    # When remaining CP is unknown, the menu is unchanged.
    cpcol = _find_col(module_table.headers, "cp", "credit", "ects")
    skillcol = _find_col(module_table.headers, "key skills", "skills", "skill")
    remaining_total = None
    reserve_mode = False                      # True when areas still need their min
    infeasible_areas: dict[str, int] = {}     # area key -> CP short after selection
    done_total = sum(completed_by_area.values()) if completed_by_area else 0
    if getattr(requirements, "coursework_cp", None) is not None:
        remaining_total = max(0, requirements.coursework_cp - done_total)

    if remaining_total is not None:
        gap_words = set(re.findall(r"[a-z]{4,}", (skill_gaps or "").lower()))

        def _row_cp(row) -> int:
            return (_to_int(row.get(cpcol, "")) if cpcol else None) or 0

        def _gap_score(row) -> int:
            if not gap_words:
                return 0
            text = (row.get(mcol, "") + " " +
                    (row.get(skillcol, "") if skillcol else "")).lower()
            return sum(1 for w in gap_words if w in text)

        def _still_required(key) -> int:
            a = requirements.areas[key]
            return max(0, a.min_cp - completed_by_area.get(key, 0))

        def _area_sorted(key) -> list[dict]:
            # within an area: gap-relevant first, then larger CP
            rows = [r for r in by_area[key] if _row_cp(r) > 0]
            rows.sort(key=lambda r: (_gap_score(r), _row_cp(r)), reverse=True)
            return rows

        # Any area still below its minimum -> "schedule everything" mode (a new or
        # early student); none -> a near-complete student, where over-planning is
        # the risk and we keep the "plan at most N" cap.
        reserve_mode = sum(_still_required(k) for k in area_keys) > 0

        selected: dict[str, list[dict]] = {k: [] for k in area_keys}
        running = 0
        used_per_area: dict[str, int] = {k: 0 for k in area_keys}
        picked: set[int] = set()

        def _try_add(key, row) -> bool:
            nonlocal running
            cp = _row_cp(row)
            if cp <= 0 or id(row) in picked:
                return False
            a = requirements.areas[key]
            room = max(0, a.max_cp - completed_by_area.get(key, 0)) - used_per_area[key]
            if cp <= room and running + cp <= remaining_total:
                selected[key].append(row)
                picked.add(id(row))
                running += cp
                used_per_area[key] += cp
                return True
            return False

        # Pass A -- reserve each area's MINIMUM so no area is starved below it.
        for key in area_keys:
            for row in _area_sorted(key):
                done = completed_by_area.get(key, 0)
                if done + used_per_area[key] >= requirements.areas[key].min_cp:
                    break
                _try_add(key, row)

        # Pass B -- fill the rest of the budget by gap relevance / CP, across areas.
        leftover = [(k, r) for k in area_keys for r in _area_sorted(k)
                    if id(r) not in picked]
        leftover.sort(key=lambda kr: (_gap_score(kr[1]), _row_cp(kr[1])), reverse=True)
        for k, row in leftover:
            _try_add(k, row)

        # Honest feasibility: record any area the catalog couldn't fill to its min.
        for key in area_keys:
            short = (requirements.areas[key].min_cp
                     - completed_by_area.get(key, 0) - used_per_area[key])
            if short > 0:
                infeasible_areas[key] = short

        by_area = selected

    return {
        "by_area": by_area,
        "keep_cols": keep_cols,
        "mcol": mcol,
        "cpcol": cpcol,
        "skillcol": skillcol,
        "area_keys": area_keys,
        "area_display": area_display,
        "unmatched": unmatched,
        "remaining_total": remaining_total,
        "done_total": done_total,
        "reserve_mode": reserve_mode,
        "infeasible_areas": infeasible_areas,
        "completed_by_area": dict(completed_by_area or {}),
        "requirements": requirements,
    }


def _render_menu(menu: dict) -> str:
    """Render the curated menu (from _select_menu_modules) as the area-grouped
    Markdown table the planner LLM receives, with per-area budget annotations."""
    requirements = menu["requirements"]
    area_keys = menu["area_keys"]
    by_area = menu["by_area"]
    keep_cols = menu["keep_cols"]
    unmatched = menu["unmatched"]
    remaining_total = menu["remaining_total"]
    reserve_mode = menu["reserve_mode"]
    infeasible_areas = menu["infeasible_areas"]
    completed_by_area = menu["completed_by_area"]

    header_row = "| " + " | ".join(keep_cols) + " |"
    sep_row = "|" + "|".join(["---"] * len(keep_cols)) + "|"

    lines: list[str] = []
    if remaining_total is not None:
        done_so_far = menu["done_total"]
        if reserve_mode:
            # From-scratch / unmet-minimums plan: the menu is curated to hit every
            # area minimum and the coursework total -- so schedule ALL of it. The
            # old "being short is fine" wording was written for the over-planning
            # case and wrongly licensed a new student to under-plan (63/90 CP).
            lines.append(
                f"**Schedule EVERY module listed below across your semesters.** Together "
                f"they reach each thematic area's minimum and total close to the "
                f"{remaining_total} CP of coursework you still need (you have completed "
                f"{done_so_far} of {requirements.coursework_cp}). Then schedule the "
                f"Master's Thesis as the final semester. Every area must reach AT LEAST its "
                f"minimum; never exceed an area's maximum and never run past "
                f"{remaining_total} total coursework CP. Do NOT drop modules to shorten the "
                f"plan -- omitting modules leaves an area below its minimum and FAILS "
                f"validation. Aim for ~30 CP per semester so the coursework fits as few "
                f"semesters as possible before the thesis.")
        else:
            # Near-complete continuing student: minimums already met by completed
            # credits, so the risk is OVER-planning -- keep the cap.
            lines.append(
                f"**Plan at most {remaining_total} more coursework CP in total** (you have "
                f"completed {done_so_far} of {requirements.coursework_cp}). This menu is "
                f"ALREADY capped to that budget; every module below is eligible; schedule "
                f"from it, then the Master's Thesis. If the modules don't sum to exactly "
                f"{remaining_total} CP, plan slightly fewer (being short is fine; "
                f"over-running is not).")
        lines.append("")
    for key in area_keys:
        a = requirements.areas[key]
        done = completed_by_area.get(key, 0)
        room = max(0, a.max_cp - done)
        needed = max(0, a.min_cp - done)

        if room == 0:
            budget = f"AREA FULL (max {a.max_cp} CP already reached -- do not add more)"
        elif needed > 0:
            budget = (f"need {needed} more CP to reach minimum {a.min_cp}; "
                      f"may add at most {room} more CP before hitting max {a.max_cp}")
        else:
            budget = f"minimum met; may add at most {room} more CP"

        lines.append(f"### {a.name}")
        lines.append(f"_Budget: {done} CP already completed. {budget}._")
        if key in infeasible_areas:
            short = infeasible_areas[key]
            lines.append(
                f"> NOTE: this handbook provides only {a.min_cp - short} CP of modules in "
                f"this area -- {short} CP short of the {a.min_cp} minimum. Schedule all "
                f"modules listed here; this gap cannot be closed from this handbook.")
        rows = by_area[key]
        if not rows:
            lines.append("_(no unfinished modules available in this area)_")
        else:
            lines.append(header_row)
            lines.append(sep_row)
            for row in rows:
                cells = [row.get(h, "").strip() for h in keep_cols]
                lines.append("| " + " | ".join(cells) + " |")
        lines.append("")

    if unmatched:
        lines.append("### Other / Area Unknown -- use only if the above areas all have room")
        lines.append(header_row)
        lines.append(sep_row)
        for row in unmatched:
            cells = [row.get(h, "").strip() for h in keep_cols]
            lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines)


def _build_planner_module_table(
    catalog_md: str,
    requirements,
    completed_by_area: dict,
    completed_module_names: list[str],
    skill_gaps: str = "",
) -> str:
    """Back-compat wrapper: curate then render the planner's module menu. Returns
    the raw catalog when there's nothing to curate (no requirements schedule)."""
    menu = _select_menu_modules(
        catalog_md, requirements, completed_by_area, completed_module_names,
        skill_gaps=skill_gaps)
    if menu is None:
        return catalog_md
    return _render_menu(menu)


def _ensure_thesis(study_plan: str, requirements) -> tuple[str, bool]:
    """Append a final thesis semester when the programme requires one but the
    planner didn't schedule it (it sometimes omits the thesis despite the prompt).
    Returns (plan, appended)."""
    cp = getattr(requirements, "thesis_cp", None)
    if not cp:
        return study_plan, False
    low = study_plan.lower()
    if "thesis" in low or "masterarbeit" in low:
        return study_plan, False
    block = (
        f"\n\n### Final Semester: Master's Thesis\n"
        f"| Module | CP | Closes gap | Why |\n"
        f"|--------|----|------------|-----|\n"
        f"| Master's Thesis (Masterarbeit) | {cp} | N/A | "
        f"Final independent research thesis required to graduate. |\n\n"
        f"**Total CP: {cp}**\n"
    )
    return study_plan + block, True


def _next_semester_label(label: str) -> str:
    """Next seasonal label: 'Summer Semester Y' -> 'Winter Semester Y/Y+1' ->
    'Summer Semester Y+1'. Returns the input unchanged if it isn't seasonal."""
    import re
    m = re.search(r"(summer|winter)\s+semester\s+(\d{4})(?:\s*/\s*(\d{4}))?",
                  label, re.I)
    if not m:
        return label
    season, y1 = m.group(1).lower(), int(m.group(2))
    if season == "summer":
        return f"Winter Semester {y1}/{y1 + 1}"
    y2 = int(m.group(3)) if m.group(3) else y1 + 1
    return f"Summer Semester {y2}"


def _semester_labels(start: str, n: int) -> list[str]:
    """n consecutive seasonal labels beginning at `start`."""
    labels = [start]
    for _ in range(max(0, n - 1)):
        labels.append(_next_semester_label(labels[-1]))
    return labels


def _llm_narrative_map(plan_md: str) -> dict:
    """{normalized module name: (closes_gap, why)} from the LLM plan's tables, so a
    deterministic rebuild can carry the model's per-module narrative where a name
    still matches."""
    from study_planner.validate import parse_markdown_tables, _find_col, _norm
    out: dict[str, tuple[str, str]] = {}
    for t in parse_markdown_tables(plan_md):
        mcol = _find_col(t.headers, "module", "name")
        if not mcol:
            continue
        gapcol = _find_col(t.headers, "closes gap", "gap", "closes")
        whycol = _find_col(t.headers, "why", "rationale", "reason")
        for row in t.rows:
            name = row.get(mcol, "").strip()
            if not name or _norm(name) in {"module", "name", "total"}:
                continue
            gap = row.get(gapcol, "").strip() if gapcol else ""
            why = row.get(whycol, "").strip() if whycol else ""
            if gap or why:
                out[_norm(name)] = (gap, why)
    return out


def _extract_uncovered_section(plan_md: str) -> str:
    """The LLM plan's 'Gaps not covered ...' section (heading + body), or '' if
    absent -- carried into a deterministic rebuild so that advice isn't lost."""
    import re
    blocks = re.split(r"(?m)^(#{2,4}\s+.*)$", plan_md)
    for k in range(1, len(blocks), 2):
        htext = blocks[k].strip("# ").strip().lower()
        if "not covered" in htext or "uncovered" in htext or \
                ("gap" in htext and "cover" in htext):
            body = blocks[k + 1] if k + 1 < len(blocks) else ""
            return blocks[k].strip() + "\n" + body.rstrip()
    return ""


def _assemble_coursework_plan(menu: dict, requirements, constraints,
                              current_semester: str, llm_plan_md: str) -> str:
    """Deterministically build the plan body from the curated menu so every area
    reaches its minimum, the coursework total is covered, and the horizon fits.

    Used as a backstop only when the LLM plan fails validation -- the menu already
    OFFERED enough; the model just didn't schedule it. Per the playbook, code
    counts/distributes; the LLM's per-module narrative (Closes gap / Why) is carried
    over where a name matches, else a short code-written note is used.
    """
    import math
    from study_planner.validate import _to_int, _norm, _best_match, NAME_MATCH_THRESHOLD

    area_display = menu["area_display"]
    by_area = menu["by_area"]
    mcol, cpcol, skillcol = menu["mcol"], menu["cpcol"], menu["skillcol"]

    # Foundational-first ordering reduces prerequisite warnings in the rebuild.
    def _area_rank(key: str) -> int:
        n = _norm(area_display[key])
        if "fundamental" in n:
            return 0
        if "data processing" in n:
            return 1
        if "learning" in n:
            return 2
        if "applied" in n:
            return 3
        return 4
    ordered_keys = sorted(menu["area_keys"], key=_area_rank)

    narr = _llm_narrative_map(llm_plan_md)
    narr_keys = list(narr.keys())

    modules: list[tuple[str, int, str, str, str]] = []  # name, cp, area, gap, why
    for key in ordered_keys:
        for row in by_area.get(key, []):
            name = row.get(mcol, "").strip()
            cp = (_to_int(row.get(cpcol, "")) if cpcol else None) or 0
            if not name or cp <= 0:
                continue
            skills = row.get(skillcol, "").strip() if skillcol else ""
            gap, why = "", ""
            if narr_keys:
                km, score = _best_match(name, narr_keys)
                if km and score >= NAME_MATCH_THRESHOLD:
                    gap, why = narr[km]
            why = why or skills or f"Builds {area_display[key]} competency."
            gap = gap or skills or f"Reaches the {area_display[key]} minimum."
            modules.append((name, cp, area_display[key], gap, why))

    total_cp = sum(m[1] for m in modules)
    thesis_cp = requirements.thesis_cp or 30

    # Coursework semesters: ~30 CP each, capped so coursework + thesis fits the
    # target horizon. A >36 CP load (if forced to fit) is only a WARNING.
    coursework_slots = max(1, constraints.target_semesters - 1)
    n = max(1, math.ceil(total_cp / 30)) if total_cp else 1
    n = min(n, coursework_slots)
    target_per = math.ceil(total_cp / n) if n else total_cp

    bins: list[list[tuple]] = [[] for _ in range(n)]
    loads = [0] * n
    for mod in modules:
        idx = next((i for i in range(n) if loads[i] + mod[1] <= target_per), None)
        if idx is None:
            idx = loads.index(min(loads))
        bins[idx].append(mod)
        loads[idx] += mod[1]
    bins = [b for b in bins if b]

    labels = _semester_labels(current_semester, len(bins) + 1)  # +1 for the thesis

    out: list[str] = ["## Summary",
                      (f"This plan schedules the {total_cp} CP of remaining coursework "
                       f"across {len(bins)} semester(s) so every thematic area reaches "
                       f"its required minimum, followed by the {thesis_cp} CP Master's "
                       f"Thesis. The module selection and credit balance were computed "
                       f"in code to satisfy the programme's area rules."), ""]
    for label, b in zip(labels, bins):
        out.append(f"### {label}")
        out.append("| Module | CP | Thematic Area | Closes gap | Why |")
        out.append("|--------|----|---------------|------------|-----|")
        for name, cp, area_name, gap, why in b:
            out.append(f"| {name} | {cp} | {area_name} | {gap} | {why} |")
        out.append(f"\n**Total CP: {sum(m[1] for m in b)}**\n")

    thesis_label = labels[len(bins)] if len(labels) > len(bins) \
        else _next_semester_label(labels[-1] if labels else current_semester)
    out.append(f"### {thesis_label}: Master's Thesis")
    out.append("| Module | CP | Thematic Area | Closes gap | Why |")
    out.append("|--------|----|---------------|------------|-----|")
    out.append(f"| Master's Thesis (Masterarbeit) | {thesis_cp} | n/a | N/A | "
               f"Final independent research thesis required to graduate. |")
    out.append(f"\n**Total CP: {thesis_cp}**\n")

    uncovered = _extract_uncovered_section(llm_plan_md)
    if uncovered:
        out.append(uncovered)

    return "\n".join(out)


def _ensure_area_minimums(study_plan: str, validation, menu: dict | None,
                          requirements, constraints,
                          current_semester: str) -> tuple[str, bool]:
    """Deterministic backstop: when the LLM plan still FAILS validation, rebuild the
    coursework body from the curated menu so area minimums, the coursework total and
    the semester horizon are guaranteed in code rather than in the prompt. A PASSING
    plan is returned untouched (a continuing student's good plan is never rewritten).
    Returns (plan, replaced)."""
    if validation is None or validation.ok:
        return study_plan, False
    if not menu or menu.get("remaining_total") is None:
        return study_plan, False  # no curated menu (legacy flow) -- leave as-is
    rebuilt = _assemble_coursework_plan(
        menu, requirements, constraints, current_semester, study_plan)
    return rebuilt, True


def plan_studies(data_dir: str = "data", save_report: bool = True,
                 validate: bool = True, constraints=None,
                 debug_dir: str | None = None, max_replans: int = 1,
                 progress_cb=None) -> dict:
    """
    Run the 5-agent study-planner crew on a folder of input documents.

    Expects in data_dir: cv.pdf, transcript.pdf, career.pdf, module_handbook.pdf

    `constraints` is an optional study_planner.inputs.PlanConstraints (target
    semesters + per-semester CP preferences). When None, a permissive default is
    used so existing callers keep working.

    `debug_dir` (optional): when set, every intermediate output is written there
    in pipeline order (00_inputs_extraction.md .. 07_validation.md) plus
    timings.json and manifest.md, so a defect can be traced to the exact step
    that produced it.

    Returns:
        {
          "study_plan":        str  — semester-wise plan (Markdown)
          "skill_gaps":        str  — prioritized gap analysis (Markdown)
          "module_catalog":    str  — curator's RAW module table (Markdown)
          "available_modules": str  — Python-normalized table fed to the planner
          "profile":           str  — student profile incl. completed modules
          "validation":        ValidationReport | None — deterministic rule check
          "report_path":       str | None — path to saved outputs/study_plan.md
        }
    """
    # Import here so load_dotenv() runs before crew.py module-level config
    from study_planner.crew import StudyPlannerCrew
    from study_planner.inputs import PlanConstraints
    from study_planner.validate import parse_completed

    if constraints is None:
        constraints = PlanConstraints()

    data = pathlib.Path(data_dir).resolve()
    if not data.exists():
        raise FileNotFoundError(f"Input folder not found: {data}")

    # Optional study & examination schedule → authoritative CP rules (min/max per
    # area, thesis, total, required team projects). Empty if not uploaded.
    from study_planner.requirements import (
        parse_requirements_file, parse_completed_by_area, render_completed_status,
        _pdf_text,
    )

    requirements = parse_requirements_file(data / "requirements.pdf")
    # Only DKE is supported today, and its area CP rules are fixed regulations.
    # When no schedule PDF was uploaded, fall back to the built-in DKE rules so the
    # area-grouped menu, menu-capping, and the validator's min/max ERRORs are always
    # active — including for a brand-new first-semester student (0 completed CP).
    if requirements.is_empty():
        from study_planner.requirements import dke_requirements
        requirements = dke_requirements()

    # Deterministic completed-credits-per-area from the transcript (the planner
    # mis-attributes these), fed to BOTH the prompt (exact remaining per area) and
    # the validator (authoritative completed counts). Empty without a schedule.
    completed_by_area = parse_completed_by_area(
        _pdf_text(data / "transcript.pdf"), requirements)
    completed_status = render_completed_status(requirements, completed_by_area)

    # Total completed CP straight from the transcript (deterministic, no schedule
    # needed). The LLM-generated profile under-counts completed credits (it read
    # 81 as 46), so this is the AUTHORITATIVE completed count handed to the
    # validator's no-schedule over-plan check below.
    from study_planner.requirements import (
        parse_completed_cp_from_transcript, render_minimal_completed_status,
    )
    completed_cp_total = parse_completed_cp_from_transcript(
        _pdf_text(data / "transcript.pdf"))

    # No schedule uploaded -> render_completed_status is empty and the per-area
    # guards are off, which is exactly when the planner re-plans the whole degree
    # (observed: 132 CP scheduled for a student who needs 9). We can STILL compute
    # the total completed CP without a schedule, so inject a minimal "plan EXACTLY
    # N more CP" anchor in that case.
    if not completed_status:
        completed_status = render_minimal_completed_status(
            completed_cp_total, constraints.coursework_cp(), requirements.thesis_cp or 30)

    # Deterministic handbook parse: a real handbook is ~900 pages of mostly prose
    # the LLM curator can't traverse (it would time out / hallucinate). When the
    # handbook is the labelled FIN scheme, extract {module, CP, area} in code and
    # skip the LLM curator entirely. Falls back to the curator when the parse is
    # thin (a differently-structured handbook). Needs requirements for area names.
    parsed_catalog_md = None
    if requirements.areas:
        try:
            from study_planner.ingest.ocr import extract_text
            from study_planner.ingest.handbook_parser import parse_handbook, render_catalog_md
            hb_text, _used_ocr = extract_text(data / "module_handbook.pdf")
            area_names = [a.name for a in requirements.areas.values()]
            parsed = parse_handbook(hb_text, valid_areas=area_names)
            if len(parsed) >= 5:  # trust the parser only with a real catalog
                parsed_catalog_md = render_catalog_md(parsed)
                # The thesis isn't tagged to a thematic area in the handbook, so the
                # parser drops it — add it back (area "n/a" -> the planner's Other
                # section) so a thesis can be scheduled.
                if requirements.thesis_cp:
                    parsed_catalog_md += (
                        f"\n| Master's Thesis (Masterarbeit) | "
                        f"{requirements.thesis_cp} | n/a |")
        except Exception:
            parsed_catalog_md = None  # any parse failure -> fall back to the curator

    now = datetime.now()
    month, year = now.month, now.year
    if 4 <= month <= 9:
        current_semester = f"Summer Semester {year}"
    elif month >= 10:
        current_semester = f"Winter Semester {year}/{year + 1}"
    else:
        current_semester = f"Winter Semester {year - 1}/{year}"

    if debug_dir:
        # Clean per-run fallback count for the manifest (process-global list).
        from study_planner.llm_config import reset_fallback_events
        reset_fallback_events()
        # Remove our own artifacts from a prior run so a stale file (e.g. an
        # 08_error.md from a previous failure, or a 06 from a run that got
        # further) can't masquerade as belonging to this run.
        _dbg_dir = pathlib.Path(debug_dir)
        if _dbg_dir.is_dir():
            for _f in ("00_inputs_extraction.md", "01_profile.md", "02_career.md",
                       "03_modules_catalog_raw.md", "04_available_modules.md",
                       "05_skill_gaps.md", "06_study_plan.md", "07_validation.md",
                       "08_error.md", "timings.json", "manifest.md"):
                (_dbg_dir / _f).unlink(missing_ok=True)

    crew_inst = StudyPlannerCrew()
    shared_inputs = {
        "data_dir": str(data),
        "constraints": constraints.render_for_prompt(),
        "requirements": requirements.render_for_prompt(),
        "completed_status": completed_status,
        "area_names": requirements.render_area_names_for_curator(),
        "current_semester": current_semester,
    }

    timings: dict[str, float] = {}
    t_start = time.perf_counter()

    def _emit(phase: str) -> None:
        """Report a user-facing progress phase (best-effort; never breaks the run)."""
        if progress_cb:
            try:
                progress_cb(phase)
            except Exception:
                pass

    # ── Crash-resilient debug dump ──────────────────────────────────────────
    # The crew commonly dies mid-run (daily LLM quota, provider 4xx). If we only
    # dumped on success, a failed run would leave nothing to debug — the worst
    # case, since a failed run already cost quota. So we accumulate sections and
    # _flush() after every step AND in the except handler, writing whatever
    # completed plus a traceback. Inputs diagnosis costs no LLM, so it's first.
    _dbg: dict[str, str] = {}

    def _flush_debug() -> None:
        if not debug_dir:
            return
        from study_planner.tools.pdf_tools import diagnose_inputs, format_input_diagnosis
        from study_planner.llm_config import resolve_models, get_fallback_events
        try:
            fast_model, smart_model = resolve_models()
        except Exception:
            fast_model = smart_model = "(unresolved)"
        fb = get_fallback_events()
        manifest = (
            f"# Run manifest\n\n"
            f"- timestamp: {datetime.now().isoformat(timespec='seconds')}\n"
            f"- data_dir: `{data}`\n"
            f"- LLM_PROVIDER: `{os.getenv('LLM_PROVIDER', 'mixed')}`\n"
            f"- llm fast model: `{fast_model}`\n"
            f"- llm smart model: `{smart_model}`\n"
            f"- requirements schedule loaded: {bool(requirements and requirements.areas)}\n"
            f"- cross-provider fallback fired: {len(fb)} time(s)"
            + (f" ({'; '.join(fb)})" if fb else "") + "\n\n"
            f"## Constraints\n\n```\n{constraints.render_for_prompt()}\n```\n"
        )
        sections = {
            "00_inputs_extraction.md": format_input_diagnosis(diagnose_inputs(data)),
            "timings.json": json.dumps(timings, indent=2),
            "manifest.md": manifest,
        }
        sections.update(_dbg)
        _dump_artifacts(debug_dir, sections)

    _flush_debug()  # write inputs diagnosis immediately, before any LLM cost

    try:
        # ── Phase 1: profile, career, (modules), gap ────────────────────────
        # Skip the LLM curator when we already parsed the handbook deterministically.
        _emit("Reading your documents")
        p1_crew = crew_inst.phase1_crew(include_modules=parsed_catalog_md is None)
        p1_result = p1_crew.kickoff(inputs=shared_inputs)
        timings["phase1_crew_s"] = round(time.perf_counter() - t_start, 2)

        p1_by_name = {t.name: o.raw for t, o in zip(p1_crew.tasks, p1_result.tasks_output)}
        profile = p1_by_name.get("profile_task", "")
        # Prefer the deterministic catalog; else the curator's table.
        module_catalog = parsed_catalog_md or p1_by_name.get("modules_task", "")
        skill_gaps = p1_by_name.get("gap_task", "")
        _dbg.update({
            "01_profile.md": profile,
            "02_career.md": p1_by_name.get("career_task", ""),
            "03_modules_catalog_raw.md": module_catalog,
            "05_skill_gaps.md": skill_gaps,
        })

        # ── Python normalization: build a clean, area-grouped module table ───
        completed_module_names = parse_completed(profile)
        menu = _select_menu_modules(
            module_catalog, requirements, completed_by_area, completed_module_names,
            skill_gaps=skill_gaps)
        available_modules = _render_menu(menu) if menu else module_catalog
        _dbg["04_available_modules.md"] = available_modules
        _flush_debug()

        # ── Phase 2: planner with Python-curated inputs, validate→replan ────
        # The planner ignores the up-front 'plan EXACTLY N CP' instruction (a real
        # run scheduled 30 CP when 9 remained). Prompting alone is proven
        # insufficient, so we ENFORCE: validate the plan in code, and on ERRORs
        # feed the specific violations back for a bounded re-plan. Capped by
        # max_replans to protect free-tier token budget.
        from study_planner.validate import validate_plan, build_correction
        study_plan = ""
        validation = None
        correction = ""
        attempts = 0
        for attempt in range(max_replans + 1):
            attempts = attempt + 1
            _emit("Planning your semesters" if attempt == 0 else "Revising the plan")
            t_phase2 = time.perf_counter()
            p2_crew = crew_inst.phase2_crew()
            p2_result = p2_crew.kickoff(inputs={
                **shared_inputs,
                "profile_summary": profile,
                "career_summary": p1_by_name.get("career_task", ""),
                "gap_summary": skill_gaps,
                "available_modules": available_modules,
                "correction": correction,
            })
            suffix = "" if attempt == 0 else f"_replan{attempt}"
            timings[f"phase2_crew_s{suffix}"] = round(time.perf_counter() - t_phase2, 2)

            p2_by_name = {t.name: o.raw for t, o in zip(p2_crew.tasks, p2_result.tasks_output)}
            if "plan_task_v2" not in p2_by_name:
                raise RuntimeError(
                    f"Phase 2 crew finished but produced no plan_task_v2 output. "
                    f"Got: {sorted(p2_by_name)}. A task likely failed mid-run."
                )
            study_plan = p2_by_name["plan_task_v2"]

            if not validate:
                _dbg["06_study_plan.md"] = study_plan
                break

            _emit("Validating the plan")
            t_val = time.perf_counter()
            validation = validate_plan(study_plan, module_catalog, profile, constraints,
                                       requirements=requirements,
                                       completed_by_area=completed_by_area,
                                       offered_md=available_modules,
                                       completed_cp_override=completed_cp_total)
            timings[f"validation_s{suffix}"] = round(time.perf_counter() - t_val, 2)

            # Keep each attempt's artifacts so the replan is itself debuggable.
            if attempt > 0:
                _dbg[f"06_study_plan_attempt{attempt}.md"] = study_plan
                _dbg[f"07_validation_attempt{attempt}.md"] = validation.summary()
            _dbg["06_study_plan.md"] = study_plan
            _dbg["07_validation.md"] = validation.summary()
            _flush_debug()

            if validation.ok or attempt == max_replans:
                break
            # Re-plan: feed the concrete violations back as a correction directive.
            correction = build_correction(validation)

        # Deterministic backstop + thesis guarantee. The menu already OFFERED enough
        # CP per area (two-pass curation); when the LLM still ships a FAILING plan
        # (an area below its minimum, too many semesters, short of the total), rebuild
        # the coursework body from the curated menu so the guarantee lives in code,
        # not the prompt. A PASSING plan (e.g. a continuing student's) is untouched.
        # Then ensure a thesis is present, and re-validate once (no LLM cost).
        if validate and validation is not None:
            study_plan, _rebuilt = _ensure_area_minimums(
                study_plan, validation, menu, requirements, constraints, current_semester)
            study_plan, _appended = _ensure_thesis(study_plan, requirements)
            if _rebuilt or _appended:
                validation = validate_plan(study_plan, module_catalog, profile, constraints,
                                           requirements=requirements,
                                           completed_by_area=completed_by_area,
                                           offered_md=available_modules,
                                           completed_cp_override=completed_cp_total)
                _dbg["06_study_plan.md"] = study_plan
                _dbg["07_validation.md"] = validation.summary()

        timings["plan_attempts"] = attempts
        timings["total_s"] = round(time.perf_counter() - t_start, 2)
        _flush_debug()
        if debug_dir:
            print(f"[debug] step-by-step artifacts written to: {pathlib.Path(debug_dir).resolve()}")
    except Exception:
        import traceback
        timings["total_s"] = round(time.perf_counter() - t_start, 2)
        _dbg["08_error.md"] = f"# Run failed mid-pipeline\n\n```\n{traceback.format_exc()}\n```\n"
        _flush_debug()
        if debug_dir:
            print(f"[debug] PARTIAL artifacts (run failed) written to: "
                  f"{pathlib.Path(debug_dir).resolve()}")
        raise

    # Deterministic, trustworthy budget table (the planner's own is unreliable). We
    # EMBED it in the plan body, replacing the LLM's self-computed table (removed from
    # tasks.yaml) that contradicted its own schedule (it labelled a 15/min-18 area OK).
    from study_planner.validate import render_area_budget_table
    area_budget_table = render_area_budget_table(validation) if validation else ""
    if area_budget_table:
        study_plan = (study_plan.rstrip()
                      + "\n\n## Thematic Area Budget (verified in code)\n\n"
                      + area_budget_table + "\n")

    report_path = None
    if save_report:
        out_dir = pathlib.Path(__file__).parent.parent.parent / "outputs"
        out_dir.mkdir(exist_ok=True)
        out_file = out_dir / "study_plan.md"
        # study_plan already embeds the deterministic budget table (above).
        val_section = f"\n---\n\n# Plan Validation\n\n```\n{validation.summary()}\n```\n" \
            if validation else ""
        report = (
            f"# Personalized Study Plan\n\n"
            f"**Inputs:** `{data}`\n\n"
            f"---\n\n{study_plan}\n\n"
            f"---\n\n# Skill Gap Analysis\n\n{skill_gaps}\n"
            f"{val_section}"
        )
        out_file.write_text(report, encoding="utf-8")
        report_path = str(out_file.resolve())

    return {
        "study_plan": study_plan,
        "skill_gaps": skill_gaps,
        "module_catalog": module_catalog,
        "available_modules": available_modules,
        "area_budget_table": area_budget_table,
        "profile": profile,
        "validation": validation,
        "report_path": report_path,
    }


def main():
    # Usage: python -m study_planner.main [data-dir] [--debug[=dir]]
    # --debug (or SP_DEBUG_DIR=<dir>) dumps every intermediate output to <dir>.
    force_utf8_stdout()
    debug_dir = os.getenv("SP_DEBUG_DIR")
    positional = []
    for arg in sys.argv[1:]:
        if arg == "--debug":
            debug_dir = debug_dir or "debug"
        elif arg.startswith("--debug="):
            debug_dir = arg.split("=", 1)[1]
        else:
            positional.append(arg)
    data_dir = positional[0] if positional else "data"

    print(f"\n{'='*60}")
    print(f"Agentic Study Planner -- inputs: {data_dir}")
    if debug_dir:
        print(f"Debug artifacts -> {debug_dir}")
    print(f"{'='*60}\n")

    result = plan_studies(data_dir, debug_dir=debug_dir)

    print(f"\n{'='*60}")
    print("STUDY PLAN:\n")
    print(result["study_plan"])
    print(f"\n{'='*60}")
    if result.get("validation"):
        print("PLAN VALIDATION:\n")
        print(result["validation"].summary())
        print(f"{'='*60}")
    if result["report_path"]:
        print(f"Full report saved to: {result['report_path']}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
