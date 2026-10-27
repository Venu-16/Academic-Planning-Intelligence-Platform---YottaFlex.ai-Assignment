import math
import pandas as pd
from .validation import validate_assignment_outputs

def propose_sections(forecasts,rooms,term_id="2027-SPRING",academic_terms=None):
    active=rooms[rooms["active"]].sort_values("capacity")
    max_room=int(active["capacity"].max()) if not active.empty else 40
    cap=min(40,max_room); rows=[]; room_slots=set()
    term_year=str(term_id).split("-",1)[0]
    for _,r in forecasts.iterrows():
        n=max(1,math.ceil(int(r.forecast_enrollment)/cap))
        for i in range(1,n+1):
            idx=len(rows)+1
            day=(idx-1)%5; slot=f"S{((idx-1)//5)%4+1}"
            candidates=active[active["capacity"]>=cap]
            room_id=None
            for _,room in candidates.iterrows():
                if (room.room_id,day,slot) not in room_slots:
                    room_id=room.room_id; room_slots.add((room_id,day,slot)); break
            rows.append({"section_id":f"SEC-{term_year}-{idx:06d}","course_id":r.course_id,"term_id":term_id,
                "section_number":i,"room_id":room_id,"day_of_week":day,"slot_id":slot,
                "planned_capacity":cap,"forecast_demand":int(r.forecast_enrollment),
                "status":"PROPOSED" if room_id else "PARTIAL"})
    sections=pd.DataFrame(rows)
    if academic_terms is not None and not academic_terms.empty:
        term=academic_terms.loc[academic_terms.term_id==term_id]
        if not term.empty:
            sections["term_start_date"]=term.iloc[0].start_date
            sections["term_end_date"]=term.iloc[0].end_date
    return sections

def calculate_operational_capacity(sections,assignments,rooms,faculty,skills,availability,assignment_issues=None):
    """Return per-section deliverable capacity after checking staffing and hard constraints."""
    assignment_groups={
        section_id:group
        for section_id,group in assignments.groupby("section_id")
    } if not assignments.empty else {}
    room_by_id=(
        rooms.set_index("room_id").to_dict("index")
        if "room_id" in rooms.columns else {}
    )
    faculty_by_id=faculty.set_index("faculty_id").to_dict("index")
    skill_pairs=set(zip(skills.faculty_id,skills.course_id))
    availability_columns={"faculty_id","term_id","day_of_week","slot_id","available"}
    available_slots=set()
    if availability_columns.issubset(availability.columns):
        available=availability.loc[availability.available.fillna(False).astype(bool)]
        available_slots=set(zip(
            available.faculty_id,
            available.term_id,
            available.day_of_week.astype(int),
            available.slot_id,
        ))

    assigned_hours={}
    room_slots={}
    faculty_slots={}
    for section in sections.itertuples(index=False):
        try:
            day=int(section.day_of_week)
            slot=(section.term_id,day,section.slot_id)
            if 0<=day<=4 and section.slot_id and pd.notna(section.room_id):
                room_slots.setdefault((section.room_id,*slot),[]).append(section.section_id)
        except (TypeError,ValueError):
            pass
        group=assignment_groups.get(section.section_id)
        if group is None or len(group)!=1:
            continue
        assignment=group.iloc[0]
        if "status" in group.columns and assignment.status=="REJECTED":
            continue
        fid=assignment.faculty_id
        workload_key=(fid,section.term_id)
        assigned_hours[workload_key]=assigned_hours.get(workload_key,0.0)+float(assignment.weekly_hours)
        try:
            day=int(section.day_of_week)
            slot=(section.term_id,day,section.slot_id)
            if 0<=day<=4 and section.slot_id:
                faculty_slots.setdefault((fid,*slot),[]).append(section.section_id)
        except (TypeError,ValueError):
            pass

    workload_exceeded={
        key for key,hours in assigned_hours.items()
        if key[0] not in faculty_by_id
        or hours>float(faculty_by_id[key[0]]["max_weekly_hours"])
    }
    faculty_conflicts={
        section_id
        for section_ids in faculty_slots.values() if len(section_ids)>1
        for section_id in section_ids
    }
    room_conflicts={
        section_id
        for section_ids in room_slots.values() if len(section_ids)>1
        for section_id in section_ids
    }

    rows=[]
    assignment_issues={
        section_id:list(reasons)
        for section_id,reasons in (assignment_issues or {}).items()
    }
    checked=validate_assignment_outputs(
        assignments,sections,faculty,skills,availability
    )
    for issue in checked["issues"]:
        assignment_issues.setdefault(issue["section_id"],[]).extend(issue["issues"])
    for section in sections.itertuples(index=False):
        blockers=list(assignment_issues.get(section.section_id,[]))
        if getattr(section,"validation_status",None)=="BLOCKED":
            blockers.extend(
                reason for reason in str(
                    getattr(section,"validation_issues","")
                ).split(";")
                if reason
            )
        group=assignment_groups.get(section.section_id)
        assignment=group.iloc[0] if group is not None and len(group)==1 else None
        if assignment is None:
            blockers.append("UNSTAFFED" if group is None else "MULTIPLE_FACULTY_ASSIGNMENTS")
        else:
            fid=assignment.faculty_id
            rejected="status" in group.columns and assignment.status=="REJECTED"
            if rejected:
                blockers.append("ASSIGNMENT_REJECTED")
            person=faculty_by_id.get(fid) if not rejected else None
            if not rejected and person is None:
                blockers.append("UNKNOWN_FACULTY")
            elif person is not None and person.get("employment_status")!="ACTIVE":
                blockers.append("FACULTY_NOT_ACTIVE")
            if person is not None and (fid,section.course_id) not in skill_pairs:
                blockers.append("MISSING_SKILL")
            if person is not None:
                try:
                    slot=(fid,section.term_id,int(section.day_of_week),section.slot_id)
                except (TypeError,ValueError):
                    slot=None
                if slot is None or slot not in available_slots:
                    blockers.append("UNAVAILABLE")
                if (fid,section.term_id) in workload_exceeded:
                    blockers.append("WORKLOAD_LIMIT")

        try:
            day=int(section.day_of_week)
            valid_schedule=0<=day<=4 and bool(section.slot_id)
        except (TypeError,ValueError):
            valid_schedule=False
        if not valid_schedule:
            blockers.append("INVALID_TIMETABLE")
        if section.section_id in faculty_conflicts:
            blockers.append("FACULTY_TIMETABLE_CONFLICT")
        if section.section_id in room_conflicts:
            blockers.append("ROOM_TIMETABLE_CONFLICT")

        section_room_id=getattr(section,"room_id",None)
        room=(
            room_by_id.get(section_room_id)
            if section_room_id is not None and pd.notna(section_room_id)
            else None
        )
        if room is None or not bool(room.get("active")):
            blockers.append("NO_ACTIVE_ROOM")
            room_capacity=0
        else:
            room_capacity=int(room["capacity"])
            if room_capacity<int(section.planned_capacity):
                blockers.append("ROOM_CAPACITY_TOO_LOW")

        blockers=sorted(set(blockers))
        assignment_status=(
            assignment.status
            if assignment is not None and "status" in group.columns
            else "UNSTAFFED" if assignment is None else "PROPOSED"
        )
        mandatory_blockers=set(blockers)-{"UNSTAFFED"}
        if assignment_status=="REJECTED":
            lifecycle_status="REJECTED"
        elif mandatory_blockers:
            lifecycle_status="BLOCKED"
        elif assignment is not None:
            lifecycle_status="OPERATIONAL"
        else:
            lifecycle_status="UNSTAFFED"
        try:
            raw_capacity=section.planned_capacity
            planned_capacity=int(raw_capacity)
            if isinstance(raw_capacity,bool) or float(raw_capacity)!=planned_capacity or planned_capacity<=0:
                raise ValueError
        except (AttributeError,TypeError,ValueError,OverflowError):
            planned_capacity=pd.NA
            blockers.append("INVALID_PLANNED_CAPACITY")
            lifecycle_status="BLOCKED"
        rows.append({
            "section_id":section.section_id,
            "course_id":section.course_id,
            "term_id":section.term_id,
            "room_id":section.room_id,
            "faculty_id":assignment.faculty_id if assignment is not None else None,
            "planned_capacity":planned_capacity,
            "room_capacity":room_capacity,
            "operational_capacity":(
                planned_capacity
                if not blockers and pd.notna(planned_capacity) else 0
            ),
            "operational":not blockers and pd.notna(planned_capacity),
            "assignment_status":assignment_status,
            "section_status":lifecycle_status,
            "blocking_reasons":";".join(blockers),
        })
    return pd.DataFrame(rows,columns=[
        "section_id","course_id","term_id","room_id","faculty_id",
        "planned_capacity","room_capacity","operational_capacity",
        "operational","assignment_status","section_status","blocking_reasons",
    ])


def calculate_unmet(forecasts,section_capacities,courses):
    if "course_id" not in courses or "program_id" not in courses:
        raise ValueError("Course catalog requires course_id and program_id")
    if "course_id" not in forecasts or "forecast_enrollment" not in forecasts:
        raise ValueError("Forecasts require course_id and forecast_enrollment")
    required_capacity={"course_id","planned_capacity","operational_capacity"}
    if not required_capacity.issubset(section_capacities.columns):
        raise ValueError(
            "Section capacities require course_id, planned_capacity, and operational_capacity"
        )

    def numeric_total(values):
        converted=pd.to_numeric(values,errors="coerce")
        if converted.empty or converted.isna().any():
            return pd.NA
        if (converted<0).any():
            raise ValueError("Forecast and capacity values cannot be negative")
        return int(converted.sum())

    forecast_rows=[]
    for course_id,group in forecasts.groupby("course_id",dropna=False):
        forecast_rows.append({
            "course_id":course_id,
            "forecast_demand":numeric_total(group.forecast_enrollment),
        })
    forecast_by_course=pd.DataFrame(
        forecast_rows,columns=["course_id","forecast_demand"]
    )

    capacity_rows=[]
    if not section_capacities.empty:
        for course_id,group in section_capacities.groupby("course_id",dropna=False):
            planned=numeric_total(group.planned_capacity)
            operational=numeric_total(group.operational_capacity)
            if operational is pd.NA:
                # Missing capacity evidence fails closed; it is never counted operational.
                operational=0
            capacity_rows.append({
                "course_id":course_id,
                "planned_capacity":planned,
                "operational_capacity":operational,
                "capacity_status":(
                    "CAPACITY_MISSING"
                    if planned is pd.NA or group.operational_capacity.isna().any()
                    else "AVAILABLE"
                ),
            })
    capacity_by_course=pd.DataFrame(capacity_rows,columns=[
        "course_id","planned_capacity","operational_capacity","capacity_status"
    ])

    course_catalog=courses[["course_id","program_id"]].drop_duplicates("course_id")
    all_course_ids=pd.DataFrame({"course_id":pd.unique(pd.concat([
        course_catalog.course_id,
        forecast_by_course.course_id,
        capacity_by_course.course_id,
    ],ignore_index=True))})
    rows=all_course_ids.merge(course_catalog,on="course_id",how="left")
    rows=rows.merge(forecast_by_course,on="course_id",how="left")
    rows=rows.merge(capacity_by_course,on="course_id",how="left")
    no_capacity=rows.capacity_status.isna()
    rows.loc[no_capacity,["planned_capacity","operational_capacity"]]=[0,0]
    rows.loc[no_capacity,"capacity_status"]="NO_SECTIONS"
    rows["forecast_status"]=rows.forecast_demand.map(
        lambda value:"MISSING" if pd.isna(value) else "AVAILABLE"
    )
    rows["operationally_covered"]=pd.Series(
        pd.NA,index=rows.index,dtype="Int64"
    )
    rows["unmet"]=pd.Series(pd.NA,index=rows.index,dtype="Int64")
    known=rows.forecast_demand.notna()
    demand=rows.loc[known,"forecast_demand"].astype(int)
    operational=rows.loc[known,"operational_capacity"].astype(int)
    rows.loc[known,"operationally_covered"]=demand.where(
        demand<=operational,operational
    )
    rows.loc[known,"unmet"]=(demand-operational).clip(lower=0).astype(int)
    rows["accommodated"]=rows["operationally_covered"]

    blocker_map={}
    for course_id,group in section_capacities.groupby("course_id",dropna=False):
        reasons=set()
        if "blocking_reasons" in group.columns:
            for value in group.blocking_reasons.dropna():
                reasons.update(reason for reason in str(value).split(";") if reason)
        blocker_map[course_id]=sorted(reasons)
    for row in rows.itertuples(index=False):
        if pd.notna(row.forecast_demand) and row.forecast_demand>row.operational_capacity:
            blocker_map.setdefault(row.course_id,[]).append("SECTION_CAPACITY_TOO_LOW")
    blocker_map={course_id:sorted(set(reasons)) for course_id,reasons in blocker_map.items()}
    rows["capacity_blockers"]=rows.course_id.map(
        lambda course_id:";".join(blocker_map.get(course_id,[]))
    )
    rows["reason"]=rows.apply(
        lambda row:"FORECAST_MISSING" if row.forecast_status=="MISSING" else
        "CAPACITY_MISSING" if row.capacity_status=="CAPACITY_MISSING" else
        "NO_SECTIONS" if row.capacity_status=="NO_SECTIONS" else
        "OPERATIONAL_CAPACITY_LIMIT" if pd.notna(row.unmet) and row.unmet>0 else
        "NONE",
        axis=1,
    )
    return rows[[
        "course_id","program_id","forecast_demand","forecast_status",
        "planned_capacity","operational_capacity","capacity_status",
        "operationally_covered","accommodated","unmet","reason",
        "capacity_blockers",
    ]]


def summarize_capacity_metrics(
    sections,section_capacity,unmet,assignments,diagnostics,
    section_validation,assignment_validation,planning_run_id,
):
    """Build mutually consistent run-level counts from the finalized section ledger."""
    blocked_ids=set(
        section_capacity.loc[
            section_capacity.section_status.isin(["BLOCKED","REJECTED"]),
            "section_id",
        ]
    )
    blockers_by_rule={}
    for row in section_capacity.itertuples(index=False):
        reasons=set(reason for reason in str(row.blocking_reasons).split(";") if reason)
        for reason in reasons:
            if reason=="UNSTAFFED":
                continue
            blockers_by_rule.setdefault(reason,set()).add(row.section_id)
    raw_violations={}
    for issue in section_validation["issues"]+assignment_validation["issues"]:
        for code in issue["issues"]:
            raw_violations[code]=raw_violations.get(code,0)+1

    if "section_status" in section_capacity:
        section_status_counts={
            str(status):int(count)
            for status,count in section_capacity.section_status.value_counts().items()
        }
    else:
        section_status_counts={}
    feasible_candidates={
        section["section_id"]
        for section in diagnostics["sections"]
        if not section["feasible_faculty_ids"]
    }
    known_forecasts=unmet.forecast_demand.dropna()
    known_unmet=unmet.unmet.dropna()
    covered=unmet.operationally_covered.dropna()
    planned=pd.to_numeric(section_capacity.planned_capacity,errors="coerce")
    planned_total=planned.sum(min_count=1)
    return {
        "planning_run_id":planning_run_id,
        "proposed_section_count":len(sections),
        "assigned_section_count":int(
            section_capacity.loc[
                section_capacity.faculty_id.notna()
                &section_capacity.assignment_status.ne("REJECTED"),
                "section_id",
            ].nunique()
        ),
        "operational_section_count":int(section_capacity.operational.sum()),
        "blocked_section_count":len(blocked_ids),
        "section_status_counts":section_status_counts,
        "planned_capacity":int(planned_total) if pd.notna(planned_total) else 0,
        "sections_with_missing_planned_capacity":int(planned.isna().sum()),
        "operational_capacity":int(section_capacity.operational_capacity.sum()),
        "forecast_demand":int(known_forecasts.sum()),
        "forecast_missing_courses":int(unmet.forecast_demand.isna().sum()),
        "forecast_demand_complete":bool(unmet.forecast_demand.notna().all()),
        "operationally_covered_demand":int(covered.sum()),
        "unmet_demand":int(known_unmet.sum()),
        "courses_with_unmet":int((unmet.unmet.fillna(0)>0).sum()),
        "courses_with_missing_forecast":int(unmet.forecast_demand.isna().sum()),
        "sections_without_eligible_faculty":len(feasible_candidates),
        "sections_without_eligible_faculty_ids":sorted(feasible_candidates),
        "sections_unstaffed":int(
            section_capacity.section_status.eq("PROPOSED").sum()
        ),
        "raw_violation_occurrences":raw_violations,
        "blocked_sections_by_rule":{
            rule:len(section_ids)
            for rule,section_ids in sorted(blockers_by_rule.items())
        },
        "blocked_section_ids":sorted(blocked_ids),
    }
