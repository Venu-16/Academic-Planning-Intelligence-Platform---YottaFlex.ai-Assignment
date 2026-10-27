import pandas as pd
from .anomaly_rules import check_assignment
FK={"courses":[("program_id","programs","program_id")],"prerequisites":[("course_id","courses","course_id"),("prerequisite_course_id","courses","course_id")],"faculty_skills":[("faculty_id","faculty","faculty_id"),("course_id","courses","course_id")],"availability":[("faculty_id","faculty","faculty_id")],"student_plans":[("program_id","programs","program_id")],"registration_interests":[("student_plan_id","student_plans","student_plan_id"),("course_id","courses","course_id")],"historical_enrollments":[("course_id","courses","course_id")]}
def validate_frames(frames):
    issues=[]
    for name,df in frames.items():
        pk=next((c for c in df.columns if c.endswith("_id") and c!="prerequisite_course_id"),None)
        if pk and df[pk].duplicated().any(): issues.append({"severity":"ERROR","table":name,"issue":"DUPLICATE_PRIMARY_KEY","count":int(df[pk].duplicated().sum())})
    for child,rules in FK.items():
        if child not in frames: continue
        for col,parent,parent_col in rules:
            missing=~frames[child][col].isin(frames[parent][parent_col])
            if missing.any(): issues.append({"severity":"ERROR","table":child,"issue":f"FOREIGN_KEY:{col}->{parent}.{parent_col}","count":int(missing.sum())})
    h=frames.get("historical_enrollments")
    if h is not None:
        bad=(h.enrolled>h.registrations)|(h.unmet_demand!=h.registrations-h.enrolled)
        if bad.any(): issues.append({"severity":"ERROR","table":"historical_enrollments","issue":"RECONCILIATION","count":int(bad.sum())})
    interests=frames.get("registration_interests")
    if interests is not None:
        invalid=(~interests.eligible.astype(bool)) & interests.interest_status.isin(["REGISTERED","WAITLISTED"])
        if invalid.any():
            issues.append({
                "severity":"ERROR",
                "table":"registration_interests",
                "issue":"PREREQUISITE_SEQUENCE_VIOLATION",
                "count":int(invalid.sum()),
                "entity_ids":interests.loc[invalid,"interest_id"].astype(str).tolist(),
                "decision":"FLAG_INELIGIBLE",
            })
    return issues

def _as_date(value):
    if value is None or pd.isna(value):
        return None
    result=pd.to_datetime(value,errors="coerce")
    return None if pd.isna(result) else result.date()


def _term_range(section):
    start=_as_date(section.get("term_start_date"))
    end=_as_date(section.get("term_end_date"))
    return (start,end) if start is not None and end is not None and start<=end else None


def _effective_date_issues(records,term_range,not_yet_effective,expired,missing_dates):
    if term_range is None:
        return ["TERM_DATES_UNAVAILABLE"]
    start,end=term_range
    if records.empty:
        return []
    if not {"effective_from","effective_to"}.issubset(records.columns):
        return [missing_dates]
    issues=set()
    for row in records.to_dict("records"):
        raw_end=row.get("effective_to")
        effective_from=_as_date(row.get("effective_from"))
        effective_to=_as_date(raw_end)
        if effective_from is None or (
            raw_end is not None and not pd.isna(raw_end) and effective_to is None
        ):
            issues.add(missing_dates)
            continue
        if effective_from>start:
            issues.add(not_yet_effective)
            continue
        if effective_to is not None and effective_to<end:
            issues.add(expired)
            continue
        return []
    return sorted(issues)


def faculty_term_eligibility_issues(faculty_id,course_id,section,skills,availability):
    term_range=_term_range(section)
    skill_rows=skills.loc[
        (skills.faculty_id==faculty_id)&(skills.course_id==course_id)
    ]
    if skill_rows.empty:
        skill_issues=["FACULTY_OUTSIDE_SKILL"]
    else:
        skill_issues=_effective_date_issues(
            skill_rows,
            term_range,
            "QUALIFICATION_NOT_YET_EFFECTIVE",
            "QUALIFICATION_EXPIRES_BEFORE_TERM_END",
            "QUALIFICATION_DATES_MISSING",
        )

    required={"faculty_id","term_id","day_of_week","slot_id","available"}
    date_fields={"effective_from","effective_to"}
    if availability is None or not required.issubset(availability.columns):
        availability_issues=["AVAILABILITY_MISSING"]
    else:
        matching=availability.loc[
            (availability.faculty_id==faculty_id)
            &(availability.term_id==section.get("term_id"))
            &(availability.day_of_week.astype(int)==int(section.get("day_of_week")))
            &(availability.slot_id==section.get("slot_id"))
        ]
        if matching.empty:
            availability_issues=["AVAILABILITY_MISSING"]
        else:
            available_rows=matching.loc[matching.available.fillna(False).astype(bool)]
            if available_rows.empty:
                availability_issues=["UNAVAILABLE"]
            elif not date_fields.issubset(available_rows.columns):
                availability_issues=["AVAILABILITY_DATES_MISSING"]
            else:
                availability_issues=_effective_date_issues(
                    available_rows,
                    term_range,
                    "AVAILABILITY_NOT_YET_EFFECTIVE",
                    "AVAILABILITY_EXPIRED_BEFORE_TERM_END",
                    "AVAILABILITY_DATES_MISSING",
                )
    return skill_issues+availability_issues


def validate_assignment_outputs(assignments,sections,faculty,skills,availability=None):
    """Validate proposed assignments against term-scoped eligibility and workload rules."""
    section_by_id=sections.set_index("section_id").to_dict("index")
    prior=[]
    issues_by_id={}
    occupied_slots={}
    for assignment_index,row in enumerate(assignments.to_dict("records")):
        if row.get("status")=="REJECTED":
            issues_by_id[assignment_index]={
                "severity":"ERROR",
                "assignment_id":row.get("workload_assignment_id"),
                "section_id":row["section_id"],
                "course_id":None,
                "faculty_id":row.get("faculty_id"),
                "term_id":None,
                "issues":[],
            }
            continue
        section=section_by_id.get(row["section_id"])
        if section is None:
            rules=["UNKNOWN_SECTION"]
            course_id=None
            term_id=None
        else:
            course_id=section["course_id"]
            term_id=section.get("term_id")
            existing_same_term=[
                existing for existing in prior if existing.get("_term_id")==term_id
            ]
            rules=check_assignment(
                faculty_id=row["faculty_id"],
                course_id=course_id,
                section_id=row["section_id"],
                weekly_hours=row["weekly_hours"],
                faculty=faculty,
                skills=skills,
                existing_assignments=existing_same_term,
            )
            person=faculty.loc[faculty.faculty_id==row["faculty_id"]]
            if not person.empty and person.iloc[0].employment_status!="ACTIVE":
                rules.append("FACULTY_NOT_ACTIVE")
            rules.extend(
                faculty_term_eligibility_issues(
                    row["faculty_id"],course_id,section,skills,availability
                )
            )
            try:
                slot=(
                    row["faculty_id"],
                    term_id,
                    int(section["day_of_week"]),
                    section["slot_id"],
                )
                occupied_slots.setdefault(slot,[]).append((assignment_index,row))
            except (KeyError,TypeError,ValueError):
                pass
        issues_by_id[assignment_index]={
            "severity":"ERROR",
            "assignment_id":row.get("workload_assignment_id"),
            "section_id":row["section_id"],
            "course_id":course_id,
            "faculty_id":row.get("faculty_id"),
            "term_id":term_id,
            "issues":sorted(set(rules)),
        }
        prior.append({**row,"_term_id":term_id})

    for rows in occupied_slots.values():
        if len(rows)>1:
            for assignment_index,_ in rows:
                issues_by_id[assignment_index]["issues"].append(
                    "FACULTY_TIMETABLE_CONFLICT"
                )

    issues=[
        {**issue,"issues":sorted(set(issue["issues"]))}
        for issue in issues_by_id.values()
        if issue["issues"]
    ]
    return {
        "passed":not issues,
        "invalid_assignment_count":len(issues),
        "invalid_section_ids":sorted({issue["section_id"] for issue in issues}),
        "issues":issues,
    }


def validate_section_outputs(sections,rooms,academic_terms):
    """Validate section room references, capacities, terms, and discrete schedules."""
    room_columns={"room_id","capacity","active"}
    term_columns={"term_id","start_date","end_date"}
    room_by_id=(
        rooms.set_index("room_id").to_dict("index")
        if "room_id" in rooms.columns else {}
    )
    term_by_id=(
        academic_terms.set_index("term_id").to_dict("index")
        if term_columns.issubset(academic_terms.columns) else {}
    )

    reasons_by_section={}
    room_slots={}
    section_ids=sections.section_id if "section_id" in sections else pd.Series(dtype=str)
    duplicates=set(section_ids[section_ids.duplicated(keep=False)].astype(str))

    for row in sections.to_dict("records"):
        section_id=row.get("section_id")
        reasons=set()
        if section_id is None or pd.isna(section_id) or str(section_id) in duplicates:
            reasons.add("INVALID_SECTION_REFERENCE")

        term_id=row.get("term_id")
        term=term_by_id.get(term_id)
        if term_id is None or pd.isna(term_id) or not term_by_id:
            reasons.add("TERM_DATES_UNAVAILABLE")
        elif term is None:
            reasons.add("UNKNOWN_ACADEMIC_TERM")
        else:
            term_start=_as_date(term.get("start_date"))
            term_end=_as_date(term.get("end_date"))
            if term_start is None or term_end is None or term_start>term_end:
                reasons.add("TERM_DATES_UNAVAILABLE")
            elif (
                _as_date(row.get("term_start_date")) != term_start
                or _as_date(row.get("term_end_date")) != term_end
            ):
                reasons.add("TERM_MISMATCH")

        try:
            raw_day=row.get("day_of_week")
            day=int(raw_day)
            valid_day=(
                not isinstance(raw_day,bool)
                and float(raw_day)==day
                and 0<=day<=4
            )
        except (TypeError,ValueError,OverflowError):
            valid_day=False
            day=None
        slot=row.get("slot_id")
        if not valid_day or slot is None or pd.isna(slot) or not str(slot).strip():
            reasons.add("INVALID_TIMETABLE")
        elif term_id is not None and not pd.isna(term_id):
            room_id=row.get("room_id")
            if room_id is not None and not pd.isna(room_id):
                room_slots.setdefault(
                    (term_id,day,str(slot),room_id),[]
                ).append(section_id)

        try:
            raw_capacity=row.get("planned_capacity")
            planned_capacity=int(raw_capacity)
            if (
                isinstance(raw_capacity,bool)
                or float(raw_capacity)!=planned_capacity
                or planned_capacity<=0
            ):
                reasons.add("INVALID_PLANNED_CAPACITY")
        except (TypeError,ValueError,OverflowError):
            planned_capacity=0
            reasons.add("INVALID_PLANNED_CAPACITY")

        if "room_id" not in row or row.get("room_id") is None or pd.isna(row.get("room_id")):
            reasons.add("ROOM_REQUIRED")
        elif not room_columns.issubset(rooms.columns):
            reasons.add("ROOM_DATA_UNAVAILABLE")
        else:
            room=room_by_id.get(row["room_id"])
            if room is None:
                reasons.add("UNKNOWN_ROOM")
            else:
                if not bool(room["active"]):
                    reasons.add("NO_ACTIVE_ROOM")
                try:
                    room_capacity=int(room["capacity"])
                except (TypeError,ValueError):
                    room_capacity=0
                if room_capacity<planned_capacity:
                    reasons.add("ROOM_CAPACITY_TOO_LOW")

        reasons_by_section.setdefault(section_id,set()).update(reasons)

    for section_ids_at_slot in room_slots.values():
        if len(section_ids_at_slot)>1:
            for section_id in section_ids_at_slot:
                reasons_by_section.setdefault(section_id,set()).add(
                    "ROOM_TIMETABLE_CONFLICT"
                )

    issues=[]
    explanations={
        "INVALID_SECTION_REFERENCE":"Section identifier is missing or duplicated.",
        "TERM_DATES_UNAVAILABLE":"The section term has no valid academic-term date range.",
        "UNKNOWN_ACADEMIC_TERM":"The section term is absent from the academic-term calendar.",
        "TERM_MISMATCH":"Section term dates do not match the academic-term calendar.",
        "INVALID_TIMETABLE":"Weekday must be 0-4 and slot_id must be present.",
        "INVALID_PLANNED_CAPACITY":"Planned section capacity must be a positive integer.",
        "ROOM_REQUIRED":"No room is assigned to this section.",
        "ROOM_DATA_UNAVAILABLE":"Room inventory lacks required room reference or capacity fields.",
        "UNKNOWN_ROOM":"Assigned room_id does not exist in room inventory.",
        "NO_ACTIVE_ROOM":"Assigned room is not active.",
        "ROOM_CAPACITY_TOO_LOW":"Room capacity is below the section's planned capacity.",
        "ROOM_TIMETABLE_CONFLICT":"Room is assigned to another section in the same term/day/slot.",
    }
    section_by_id={
        row.get("section_id"):row
        for row in sections.to_dict("records")
    }
    for section_id,reasons in reasons_by_section.items():
        if reasons:
            row=section_by_id.get(section_id,{})
            issues.append({
                "severity":"ERROR",
                "section_id":section_id,
                "course_id":row.get("course_id"),
                "room_id":row.get("room_id"),
                "term_id":row.get("term_id"),
                "day_of_week":row.get("day_of_week"),
                "slot_id":row.get("slot_id"),
                "issues":sorted(reasons),
                "diagnostics":[
                    {"code":reason,"message":explanations[reason]}
                    for reason in sorted(reasons)
                ],
            })
    return {
        "passed":not issues,
        "invalid_section_count":len(issues),
        "invalid_section_ids":[issue["section_id"] for issue in issues],
        "issues":issues,
    }
