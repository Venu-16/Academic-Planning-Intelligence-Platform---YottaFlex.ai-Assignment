import pandas as pd
from ortools.sat.python import cp_model

SECTION_WEEKLY_HOURS=3


def _term_eligibility_sets(records,term_ranges,availability_records=False):
    eligible={}
    if not {"effective_from","effective_to"}.issubset(records.columns):
        return {term_range:set() for term_range in term_ranges}
    starts=pd.to_datetime(records.effective_from,errors="coerce")
    raw_ends=records.effective_to
    ends=pd.to_datetime(raw_ends,errors="coerce")
    open_ended=raw_ends.isna()
    valid_ends=open_ended|ends.notna()
    if availability_records and "available" in records:
        active=records.available.fillna(False).astype(bool)
        active&=records.day_of_week.notna() if "day_of_week" in records else False
    else:
        active=pd.Series(True,index=records.index)

    for term_range in term_ranges:
        start,end=term_range
        mask=(
            active
            &starts.notna()
            &(starts<=start)
            &valid_ends
            &(open_ended|(ends>=end))
        )
        selected=records.loc[mask]
        if availability_records:
            eligible[term_range]={
                (
                    row.faculty_id,
                    row.term_id,
                    int(row.day_of_week),
                    row.slot_id,
                )
                for row in selected.itertuples(index=False)
            }
        else:
            eligible[term_range]=set(zip(
                selected.faculty_id,selected.course_id
            ))
    return eligible


def allocate_faculty(sections,faculty,skills,availability,time_limit_seconds=5):
    cols=["workload_assignment_id","section_id","faculty_id","weekly_hours","status"]
    if sections.empty: return pd.DataFrame(columns=cols),{"status":"OPTIMAL","assigned":0,"unassigned":0}
    model=cp_model.CpModel(); active=faculty[faculty.employment_status=="ACTIVE"]
    x={}; ss=sections.reset_index(drop=True)
    valid_ranges=[]
    for row in ss.to_dict("records"):
        start=pd.to_datetime(row.get("term_start_date"),errors="coerce")
        end=pd.to_datetime(row.get("term_end_date"),errors="coerce")
        if not pd.isna(start) and not pd.isna(end) and start<=end:
            valid_ranges.append((start,end))
    term_ranges=set(valid_ranges)
    valid_skills=_term_eligibility_sets(
        skills,term_ranges
    )
    availability_columns={
        "faculty_id","term_id","day_of_week","slot_id","available",
        "effective_from","effective_to",
    }
    valid_availability=_term_eligibility_sets(
        availability.loc[:,list(availability_columns)]
        if availability_columns.issubset(availability.columns)
        else availability.iloc[0:0],
        term_ranges,
        availability_records=True,
    )
    for i,s in ss.iterrows():
        term_start=pd.to_datetime(s.get("term_start_date"),errors="coerce")
        term_end=pd.to_datetime(s.get("term_end_date"),errors="coerce")
        term_id=s.get("term_id")
        if (
            pd.isna(term_start)
            or pd.isna(term_end)
            or term_start>term_end
            or term_id is None
            or pd.isna(term_id)
        ):
            continue
        try:
            day=int(s.day_of_week)
        except (AttributeError,TypeError,ValueError):
            continue
        term_range=(term_start,term_end)
        eligible_skills=valid_skills.get(term_range,set())
        eligible_availability=valid_availability.get(term_range,set())
        for _,f in active.iterrows():
            if (
                (f.faculty_id,s.course_id) in eligible_skills
                and (f.faculty_id,term_id,day,s.slot_id) in eligible_availability
            ):
                x[(i,f.faculty_id)]=model.NewBoolVar(f"x_{i}_{f.faculty_id}")
    for i in range(len(ss)):
        vs=[v for (j,_),v in x.items() if i==j]
        if vs: model.Add(sum(vs)<=1)
    terms=ss.term_id.dropna().unique() if "term_id" in ss else []
    for _,f in active.iterrows():
        for term_id in terms:
            vs=[
                variable
                for (i,faculty_id),variable in x.items()
                if faculty_id==f.faculty_id and ss.iloc[i].term_id==term_id
            ]
            if vs:
                model.Add(
                    sum(variable*SECTION_WEEKLY_HOURS for variable in vs)
                    <=int(float(f.max_weekly_hours))
                )
    for fid in active.faculty_id:
        slots={}
        for (i,f),v in x.items():
            if f==fid:
                s=ss.iloc[i]; slots.setdefault((s.term_id,int(s.day_of_week),s.slot_id),[]).append(v)
        for vs in slots.values():
            if len(vs)>1: model.Add(sum(vs)<=1)
    model.Maximize(sum(x.values()) if x else 0)
    solver=cp_model.CpSolver(); solver.parameters.max_time_in_seconds=time_limit_seconds; solver.parameters.num_search_workers=8
    status=solver.Solve(model); name=solver.StatusName(status); rows=[]
    if status in (cp_model.OPTIMAL,cp_model.FEASIBLE):
        for (i,fid),v in x.items():
            if solver.Value(v):
                rows.append({"workload_assignment_id":f"WLA-2027-{len(rows)+1:06d}","section_id":ss.iloc[i].section_id,"faculty_id":fid,"weekly_hours":float(SECTION_WEEKLY_HOURS),"status":"PROPOSED"})
    out=pd.DataFrame(rows,columns=cols); n=len(set(out.section_id)) if len(out) else 0
    return out,{"status":name,"assigned":n,"unassigned":len(ss)-n,"objective_value":float(solver.ObjectiveValue()) if status in (cp_model.OPTIMAL,cp_model.FEASIBLE) else None}
