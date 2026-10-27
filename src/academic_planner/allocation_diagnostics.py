from .optimizer import SECTION_WEEKLY_HOURS
from .validation import faculty_term_eligibility_issues


def diagnose_unstaffed_sections(
    sections, faculty, skills, availability, assignments, solver_status,
    planning_run_id=None,
):
    active_assignments=(
        assignments.loc[assignments.status!="REJECTED"]
        if not assignments.empty and "status" in assignments
        else assignments
    )
    staffed_section_ids = set(active_assignments.section_id) if not active_assignments.empty else set()
    unstaffed = sections.loc[~sections.section_id.isin(staffed_section_ids)]
    availability_rows = {}
    for row in availability.itertuples(index=False):
        key = (row.faculty_id, row.term_id, int(row.day_of_week), row.slot_id)
        availability_rows.setdefault(key, []).append(bool(row.available))

    assigned_hours = {}
    occupied_slots = set()
    section_slots = sections.set_index("section_id")[
        ["term_id", "day_of_week", "slot_id"]
    ].to_dict("index")
    for assignment in active_assignments.itertuples(index=False):
        assigned_term=section_slots.get(assignment.section_id)
        term_id=assigned_term.get("term_id") if assigned_term else None
        workload_key=(assignment.faculty_id,term_id)
        assigned_hours[workload_key] = (
            assigned_hours.get(workload_key, 0.0) + float(assignment.weekly_hours)
        )
        assigned_slot = section_slots.get(assignment.section_id)
        if assigned_slot is not None:
            occupied_slots.add(
                (
                    assignment.faculty_id,
                    assigned_slot.get("term_id"),
                    int(assigned_slot["day_of_week"]),
                    assigned_slot["slot_id"],
                )
            )

    section_diagnostics = []
    blocker_counts = {}
    blocker_occurrences = {}
    for section in unstaffed.itertuples(index=False):
        slot = (int(section.day_of_week), section.slot_id)
        faculty_checks = []
        section_blockers = set()

        for person in faculty.itertuples(index=False):
            blockers = []
            availability_key = (
                person.faculty_id,
                section.term_id,
                slot[0],
                slot[1],
            )
            if person.employment_status != "ACTIVE":
                blockers.append("FACULTY_NOT_ACTIVE")
            else:
                eligibility_issues = faculty_term_eligibility_issues(
                    person.faculty_id,
                    section.course_id,
                    section._asdict(),
                    skills,
                    availability,
                )
                if "FACULTY_OUTSIDE_SKILL" in eligibility_issues:
                    blockers.append("MISSING_SKILL")
                blockers.extend(
                    issue for issue in eligibility_issues
                    if issue not in {"FACULTY_OUTSIDE_SKILL"}
                )

                current_hours = assigned_hours.get(
                    (person.faculty_id,section.term_id),0.0
                )
                if current_hours + SECTION_WEEKLY_HOURS > float(person.max_weekly_hours):
                    blockers.append("WORKLOAD_LIMIT")

                if availability_key in occupied_slots:
                    blockers.append("TIMETABLE_CONFLICT")

            availability_evidence = availability_rows.get(
                availability_key, []
            )
            if blockers:
                section_blockers.update(blockers)
                for blocker in blockers:
                    blocker_occurrences[blocker] = blocker_occurrences.get(blocker, 0) + 1
            faculty_checks.append(
                {
                    "faculty_id": person.faculty_id,
                    "blockers": blockers,
                    "current_weekly_hours": round(
                        assigned_hours.get((person.faculty_id,section.term_id),0.0),2
                    ),
                    "weekly_hour_limit": float(person.max_weekly_hours),
                    "availability_evidence": (
                        "AVAILABLE"
                        if any(availability_evidence)
                        else "MARKED_UNAVAILABLE"
                        if availability_evidence
                        else "NO_RECORD"
                    ),
                }
            )

        feasible_faculty = [
            item["faculty_id"] for item in faculty_checks if not item["blockers"]
        ]
        if not any(person.employment_status == "ACTIVE" for person in faculty.itertuples(index=False)):
            section_blockers.add("NO_ACTIVE_FACULTY")

        accounted = not feasible_faculty
        if feasible_faculty:
            explanation = (
                "SOLVER_DID_NOT_PROVE_OPTIMAL"
                if solver_status != "OPTIMAL"
                else "UNEXPLAINED_FEASIBLE_CANDIDATE"
            )
        else:
            explanation = "BLOCKED_BY_CONFIRMED_CONSTRAINTS"

        for blocker in section_blockers:
            blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1

        section_diagnostics.append(
            {
                "section_id": section.section_id,
                "course_id": section.course_id,
                "day_of_week": slot[0],
                "slot_id": slot[1],
                "room_id": section.room_id if hasattr(section, "room_id") else None,
                "planned_capacity": int(section.planned_capacity),
                "candidate_blocking_reasons": sorted(section_blockers),
                "feasible_faculty_ids": feasible_faculty,
                "faculty_checks": faculty_checks,
                "accounted": accounted,
                "diagnosis": explanation,
            }
        )

    accounted_count = sum(item["accounted"] for item in section_diagnostics)
    return {
        "planning_run_id":planning_run_id,
        "solver_status": solver_status,
        "total_sections": len(sections),
        "staffed_sections": len(staffed_section_ids),
        "unstaffed_sections": len(section_diagnostics),
        "accounted_unstaffed_sections": accounted_count,
        "fully_accounted": accounted_count == len(section_diagnostics),
        "sections_without_eligible_faculty":sum(
            not item["feasible_faculty_ids"] for item in section_diagnostics
        ),
        "sections_without_eligible_faculty_ids":sorted(
            item["section_id"] for item in section_diagnostics
            if not item["feasible_faculty_ids"]
        ),
        "sections_with_candidate_blocker": blocker_counts,
        "candidate_blocker_occurrences": blocker_occurrences,
        "assumptions": [
            "Confirmed blockers are evaluated against the final assignments using the allocator's current hard constraints.",
            "The allocator filters skills and availability by target term and requires effective dates to cover the full term, inclusively.",
            "Missing term dates, qualification records, or target-term availability records do not establish eligibility.",
            "An unstaffed section with a remaining feasible faculty candidate is unresolved, not attributed to an assumed blocker.",
            "Room availability is not a faculty-allocation constraint in the current optimizer.",
        ],
        "sections": section_diagnostics,
    }
