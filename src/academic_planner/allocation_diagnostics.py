from .optimizer import SECTION_WEEKLY_HOURS
from .validation import (
    faculty_availability_issues_from_records,
    faculty_skill_issues_from_records,
)


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
        availability_rows.setdefault(key, []).append(row._asdict())
    skills_by_course = {}
    for row in skills.itertuples(index=False):
        skills_by_course.setdefault(row.course_id,{}).setdefault(
            row.faculty_id, []
        ).append(row._asdict())
    availability_by_slot = {}
    for (faculty_id,term_id,day,slot),records in availability_rows.items():
        availability_by_slot.setdefault((term_id,day,slot),{})[faculty_id]=records
    faculty_records=list(faculty.itertuples(index=False))
    active_faculty={
        person.faculty_id:person
        for person in faculty_records if person.employment_status=="ACTIVE"
    }
    active_faculty_ids=set(active_faculty)
    inactive_faculty_count=len(faculty_records)-len(active_faculty)
    term_dates={}
    for section in sections.itertuples(index=False):
        term_dates.setdefault(
            section.term_id,
            (section.term_start_date,section.term_end_date),
        )
    skill_summaries={}
    availability_summaries={}

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

    workload_limited_by_term={}
    for term_id in sections.term_id.unique():
        workload_limited_by_term[term_id]={
            faculty_id for faculty_id,person in active_faculty.items()
            if assigned_hours.get((faculty_id,term_id),0.0)
            + SECTION_WEEKLY_HOURS > float(person.max_weekly_hours)
        }
    occupied_by_slot={}
    for faculty_id,term_id,day,slot in occupied_slots:
        occupied_by_slot.setdefault((term_id,day,slot),set()).add(faculty_id)

    section_diagnostics = []
    blocker_counts = {}
    blocker_occurrences = {}
    for section in unstaffed.itertuples(index=False):
        slot = (int(section.day_of_week), section.slot_id)
        date_key=term_dates.get(section.term_id)
        section_context=section._asdict()
        skill_key=(section.course_id,section.term_id,date_key)
        if skill_key not in skill_summaries:
            context={**section_context}
            skill_counts={}
            skilled_ids=set()
            course_faculty=skills_by_course.get(section.course_id,{})
            present_active_ids=active_faculty_ids.intersection(course_faculty)
            missing_count=len(active_faculty_ids)-len(present_active_ids)
            if missing_count:
                skill_counts["MISSING_SKILL"]=missing_count
            for faculty_id in present_active_ids:
                reasons=faculty_skill_issues_from_records(
                    context,
                    course_faculty[faculty_id],
                    {"effective_from","effective_to"}.issubset(skills.columns),
                )
                if reasons:
                    for reason in reasons:
                        skill_counts[reason]=skill_counts.get(reason,0)+1
                else:
                    skilled_ids.add(faculty_id)
            skill_summaries[skill_key]=(skill_counts,skilled_ids)

        availability_key=(section.term_id,slot[0],slot[1],date_key)
        if availability_key not in availability_summaries:
            slot_faculty=availability_by_slot.get(
                (section.term_id,slot[0],slot[1]),{}
            )
            present_active_ids=active_faculty_ids.intersection(slot_faculty)
            availability_counts={}
            missing_count=len(active_faculty_ids)-len(present_active_ids)
            if missing_count:
                availability_counts["AVAILABILITY_MISSING"]=missing_count
            available_ids=set()
            for faculty_id in present_active_ids:
                reasons=faculty_availability_issues_from_records(
                    section_context,
                    slot_faculty[faculty_id],
                    {"effective_from","effective_to"}.issubset(availability.columns),
                )
                if reasons:
                    for reason in reasons:
                        availability_counts[reason]=availability_counts.get(reason,0)+1
                else:
                    available_ids.add(faculty_id)
            availability_summaries[availability_key]=(
                availability_counts,available_ids
            )

        skill_counts,skilled_ids=skill_summaries[skill_key]
        availability_counts,available_ids=availability_summaries[availability_key]
        section_blocker_counts={}
        for counts in (skill_counts,availability_counts):
            for reason,count in counts.items():
                section_blocker_counts[reason]=section_blocker_counts.get(reason,0)+count

        workload_limited=workload_limited_by_term.get(section.term_id,set())
        conflicting_faculty=occupied_by_slot.get(
            (section.term_id,slot[0],slot[1]),set()
        )
        if workload_limited:
            section_blocker_counts["WORKLOAD_LIMIT"]=len(workload_limited)
        if conflicting_faculty:
            section_blocker_counts["TIMETABLE_CONFLICT"]=len(conflicting_faculty)
        if inactive_faculty_count:
            section_blocker_counts["FACULTY_NOT_ACTIVE"]=inactive_faculty_count
        section_blockers=set(section_blocker_counts)
        validation_blockers=[
            item for item in str(
                getattr(section,"validation_issues","")
            ).split(";")
            if item
        ]
        if getattr(section,"validation_status",None)=="BLOCKED":
            section_blockers.update(validation_blockers)
            for blocker in validation_blockers:
                section_blocker_counts[blocker]=(
                    section_blocker_counts.get(blocker,0)+1
                )
        if not active_faculty_ids:
            section_blockers.add("NO_ACTIVE_FACULTY")
        feasible_faculty=sorted(
            (skilled_ids & available_ids)
            - workload_limited
            - conflicting_faculty
        )

        for blocker,count in section_blocker_counts.items():
            blocker_occurrences[blocker]=blocker_occurrences.get(blocker,0)+count

        section_blocked=getattr(section,"validation_status",None)=="BLOCKED"
        accounted = section_blocked or not feasible_faculty
        if section_blocked:
            explanation="BLOCKED_BY_SECTION_VALIDATION"
        elif feasible_faculty:
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
                "candidate_blocker_counts": section_blocker_counts,
                "feasible_faculty_ids": feasible_faculty,
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
