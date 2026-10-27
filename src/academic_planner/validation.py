import pandas as pd
from .anomaly_rules import check_assignment
PRIMARY_KEYS={
    "academic_terms":"term_id","programs":"program_id","courses":"course_id",
    "prerequisites":"prerequisite_id","faculty":"faculty_id",
    "faculty_skills":"faculty_skill_id","availability":"availability_id",
    "rooms":"room_id","student_plans":"student_plan_id",
    "registration_interests":"interest_id",
    "historical_enrollments":"historical_enrollment_id",
}
REQUIRED_FIELDS={
    "academic_terms":["term_id","start_date","end_date"],
    "programs":["program_id","name","department"],
    "courses":["course_id","program_id","code","title","credits","course_level","is_elective"],
    "prerequisites":["prerequisite_id","course_id","prerequisite_course_id","effective_from"],
    "faculty":["faculty_id","name","department","max_weekly_hours","employment_status"],
    "faculty_skills":["faculty_skill_id","faculty_id","course_id","skill_level","effective_from"],
    "availability":["availability_id","faculty_id","term_id","day_of_week","slot_id","available","effective_from"],
    "rooms":["room_id","building","room_type","capacity","active"],
    "student_plans":["student_plan_id","student_id","program_id","term_id","year_of_study","created_at"],
    "registration_interests":["interest_id","student_plan_id","course_id","term_id","interest_status","interest_date","eligible"],
    "historical_enrollments":["historical_enrollment_id","course_id","term_id","eligible_students","registrations","enrolled","unmet_demand"],
}
FK={
    "courses":[("program_id","programs","program_id")],
    "prerequisites":[("course_id","courses","course_id"),("prerequisite_course_id","courses","course_id")],
    "faculty_skills":[("faculty_id","faculty","faculty_id"),("course_id","courses","course_id")],
    "availability":[("faculty_id","faculty","faculty_id"),("term_id","academic_terms","term_id")],
    "student_plans":[("program_id","programs","program_id"),("term_id","academic_terms","term_id")],
    "registration_interests":[("student_plan_id","student_plans","student_plan_id"),("course_id","courses","course_id"),("term_id","academic_terms","term_id")],
    "historical_enrollments":[("course_id","courses","course_id")],
}


def validate_frames(frames):
    issues=[]
    for name,df in frames.items():
        for column in REQUIRED_FIELDS.get(name,[]):
            if column not in df.columns:
                issues.append({"severity":"ERROR","table":name,"issue":f"REQUIRED_COLUMN_MISSING:{column}"})
            elif df[column].isna().any():
                issues.append({"severity":"ERROR","table":name,"issue":f"REQUIRED_VALUE_MISSING:{column}","count":int(df[column].isna().sum())})
        pk=PRIMARY_KEYS.get(name)
        if pk in df.columns and df[pk].duplicated().any():
            issues.append({"severity":"ERROR","table":name,"issue":"DUPLICATE_PRIMARY_KEY","count":int(df[pk].duplicated().sum())})
    for name, columns in {
        "programs":["name"],"courses":["code"],
        "prerequisites":["course_id","prerequisite_course_id","effective_from"],
        "student_plans":["student_id","term_id"],
        "registration_interests":["student_plan_id","course_id","term_id"],
        "faculty_skills":["faculty_id","course_id","effective_from"],
        "historical_enrollments":["course_id","term_id"],
    }.items():
        frame=frames.get(name)
        if frame is not None and set(columns).issubset(frame.columns):
            count=int(frame.duplicated(columns).sum())
            if count:
                issues.append({"severity":"ERROR","table":name,"issue":"DUPLICATE_NATURAL_KEY","columns":columns,"count":count})
    prerequisites=frames.get("prerequisites")
    if prerequisites is not None and {"course_id","prerequisite_course_id"}.issubset(prerequisites.columns):
        self_references=prerequisites.course_id==prerequisites.prerequisite_course_id
        if self_references.any():
            issues.append({"severity":"ERROR","table":"prerequisites","issue":"SELF_PREREQUISITE","count":int(self_references.sum())})
        adjacency={}
        indegree={}
        for course_id,prerequisite_id in prerequisites[
            ["course_id","prerequisite_course_id"]
        ].itertuples(index=False,name=None):
            adjacency.setdefault(course_id,[]).append(prerequisite_id)
            indegree.setdefault(course_id,0)
            indegree[prerequisite_id]=indegree.get(prerequisite_id,0)+1
        ready=[course_id for course_id,degree in indegree.items() if degree==0]
        visited=0
        while ready:
            course_id=ready.pop()
            visited+=1
            for prerequisite_id in adjacency.get(course_id,[]):
                indegree[prerequisite_id]-=1
                if indegree[prerequisite_id]==0:
                    ready.append(prerequisite_id)
        if visited<len(indegree):
            issues.append({"severity":"ERROR","table":"prerequisites","issue":"PREREQUISITE_CYCLE"})
    for child,rules in FK.items():
        if child not in frames: continue
        for col,parent,parent_col in rules:
            if col not in frames[child].columns or parent not in frames or parent_col not in frames[parent].columns:
                continue
            missing=~frames[child][col].isin(frames[parent][parent_col])
            if missing.any():
                issues.append({"severity":"ERROR","table":child,"issue":f"FOREIGN_KEY:{col}->{parent}.{parent_col}","count":int(missing.sum())})

    terms=frames.get("academic_terms")
    if terms is not None and {"start_date","end_date"}.issubset(terms.columns):
        starts=pd.to_datetime(terms.start_date,errors="coerce")
        ends=pd.to_datetime(terms.end_date,errors="coerce")
        invalid=starts.isna()|ends.isna()|(starts>ends)
        if invalid.any():
            issues.append({"severity":"ERROR","table":"academic_terms","issue":"INVALID_TERM_DATE_RANGE","count":int(invalid.sum())})

    for table in ("prerequisites","faculty_skills","availability"):
        frame=frames.get(table)
        if frame is None or "effective_from" not in frame.columns or "effective_to" not in frame.columns:
            continue
        starts=pd.to_datetime(frame.effective_from,errors="coerce")
        raw_ends=frame.effective_to
        ends=pd.to_datetime(raw_ends,errors="coerce")
        invalid_start=starts.isna()
        invalid_end=raw_ends.notna()&ends.isna()
        reversed_dates=raw_ends.notna()&ends.notna()&(starts>ends)
        count=int((invalid_start|invalid_end|reversed_dates).sum())
        if count:
            issues.append({"severity":"ERROR","table":table,"issue":"INVALID_EFFECTIVE_DATE_RANGE","count":count})

    enum_values={
        "faculty":{"employment_status":{"ACTIVE","ON_LEAVE","INACTIVE"}},
        "rooms":{"room_type":{"LECTURE","LAB"}},
        "registration_interests":{"interest_status":{"INTERESTED","REGISTERED","WAITLISTED","WITHDRAWN"}},
    }
    for table,columns in enum_values.items():
        frame=frames.get(table)
        if frame is None: continue
        for column,allowed in columns.items():
            if column in frame.columns:
                invalid=~frame[column].isin(allowed)
                if invalid.any():
                    issues.append({"severity":"ERROR","table":table,"issue":f"INVALID_ENUM:{column}","count":int(invalid.sum())})

    term_frame=frames.get("academic_terms")
    term_ids=set(term_frame.term_id) if term_frame is not None and "term_id" in term_frame else set()
    for table in ("student_plans","availability","registration_interests"):
        frame=frames.get(table)
        if frame is not None and "term_id" in frame.columns and term_ids:
            invalid=~frame.term_id.isin(term_ids)
            if invalid.any():
                issues.append({"severity":"ERROR","table":table,"issue":"UNKNOWN_ACADEMIC_TERM","count":int(invalid.sum())})
    plans=frames.get("student_plans")
    interests=frames.get("registration_interests")
    if plans is not None and interests is not None and {"student_plan_id","term_id"}.issubset(plans.columns) and {"student_plan_id","term_id"}.issubset(interests.columns):
        plan_terms=plans.set_index("student_plan_id").term_id
        expected=interests.student_plan_id.map(plan_terms)
        mismatch=expected.notna()&(expected.to_numpy()!=interests.term_id.to_numpy())
        if mismatch.any():
            issues.append({"severity":"ERROR","table":"registration_interests","issue":"STUDENT_PLAN_TERM_MISMATCH","count":int(mismatch.sum())})

    bounded={
        "courses":{"credits":(1,6),"course_level":(1,4)},
        "faculty":{"max_weekly_hours":(0,None)},
        "faculty_skills":{"skill_level":(1,5)},
        "availability":{"day_of_week":(0,4)},
        "rooms":{"capacity":(1,None)},
        "student_plans":{"year_of_study":(1,4)},
    }
    for table,columns in bounded.items():
        frame=frames.get(table)
        if frame is None: continue
        for column,(minimum,maximum) in columns.items():
            if column not in frame.columns: continue
            values=pd.to_numeric(frame[column],errors="coerce")
            invalid=values.isna()|(values<minimum)
            if maximum is not None: invalid|=values>maximum
            if invalid.any():
                issues.append({"severity":"ERROR","table":table,"issue":f"INVALID_VALUE:{column}","count":int(invalid.sum())})

    integer_fields={
        "courses":["credits","course_level"],
        "faculty_skills":["skill_level"],
        "availability":["day_of_week"],
        "rooms":["capacity"],
        "student_plans":["year_of_study"],
        "historical_enrollments":["eligible_students","registrations","enrolled","unmet_demand"],
    }
    for table,columns in integer_fields.items():
        frame=frames.get(table)
        if frame is None: continue
        for column in columns:
            if column not in frame.columns: continue
            values=pd.to_numeric(frame[column],errors="coerce")
            invalid=values.isna()|(values%1!=0)
            if invalid.any():
                issues.append({"severity":"ERROR","table":table,"issue":f"INVALID_INTEGER:{column}","count":int(invalid.sum())})
    for table,columns in {
        "courses":["is_elective"],
        "availability":["available"],
        "rooms":["active"],
        "registration_interests":["eligible"],
    }.items():
        frame=frames.get(table)
        if frame is None: continue
        for column in columns:
            if column in frame.columns and not pd.api.types.is_bool_dtype(frame[column]):
                issues.append({"severity":"ERROR","table":table,"issue":f"INVALID_BOOLEAN:{column}"})

    h=frames.get("historical_enrollments")
    if h is not None and {"enrolled","registrations","unmet_demand"}.issubset(h.columns):
        bad=(h.enrolled>h.registrations)|(h.unmet_demand!=h.registrations-h.enrolled)
        if bad.any(): issues.append({"severity":"ERROR","table":"historical_enrollments","issue":"RECONCILIATION","count":int(bad.sum())})
    interests=frames.get("registration_interests")
    if interests is not None and {"eligible","interest_status"}.issubset(interests.columns):
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
    if isinstance(records,pd.DataFrame):
        if records.empty:
            return []
        if not {"effective_from","effective_to"}.issubset(records.columns):
            return [missing_dates]
        rows=records.to_dict("records")
    else:
        rows=records
    if not rows:
        return []
    issues=set()
    for row in rows:
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
    skill_rows=skills.loc[
        (skills.faculty_id==faculty_id)&(skills.course_id==course_id)
    ]
    required={"faculty_id","term_id","day_of_week","slot_id","available"}
    if availability is None or not required.issubset(availability.columns):
        matching=[]
    else:
        matching=availability.loc[
            (availability.faculty_id==faculty_id)
            &(availability.term_id==section.get("term_id"))
            &(availability.day_of_week.astype(int)==int(section.get("day_of_week")))
            &(availability.slot_id==section.get("slot_id"))
        ]
    return faculty_term_eligibility_issues_from_records(
        course_id,section,skill_rows.to_dict("records"),
        matching.to_dict("records"),
        skills_has_dates={"effective_from","effective_to"}.issubset(skills.columns),
        availability_has_dates=(
            availability is not None
            and {"effective_from","effective_to"}.issubset(availability.columns)
        ),
    )


def faculty_skill_issues_from_records(section,skill_records,has_dates=True):
    term_range=_term_range(section)
    if not skill_records:
        return ["FACULTY_OUTSIDE_SKILL"]
    if not has_dates:
        return ["QUALIFICATION_DATES_MISSING"]
    return _effective_date_issues(
        skill_records,
        term_range,
        "QUALIFICATION_NOT_YET_EFFECTIVE",
        "QUALIFICATION_EXPIRES_BEFORE_TERM_END",
        "QUALIFICATION_DATES_MISSING",
    )


def faculty_availability_issues_from_records(section,availability_records,has_dates=True):
    if not availability_records:
        return ["AVAILABILITY_MISSING"]
    available_rows=[
        row for row in availability_records
        if row.get("available") is not None
        and not pd.isna(row.get("available"))
        and bool(row.get("available"))
    ]
    if not available_rows:
        return ["UNAVAILABLE"]
    date_fields={"effective_from","effective_to"}
    if not has_dates or not date_fields.issubset(available_rows[0]):
        return ["AVAILABILITY_DATES_MISSING"]
    return _effective_date_issues(
        available_rows,
        _term_range(section),
        "AVAILABILITY_NOT_YET_EFFECTIVE",
        "AVAILABILITY_EXPIRED_BEFORE_TERM_END",
        "AVAILABILITY_DATES_MISSING",
    )


def faculty_term_eligibility_issues_from_records(
    course_id,section,skill_records,availability_records,
    skills_has_dates=True,availability_has_dates=True,
):
    return faculty_skill_issues_from_records(
        section,skill_records,skills_has_dates
    )+faculty_availability_issues_from_records(
        section,availability_records,availability_has_dates
    )


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
