import pandas as pd
from ortools.sat.python import cp_model

def allocate_faculty(sections,faculty,skills,availability,time_limit_seconds=5):
    cols=["workload_assignment_id","section_id","faculty_id","weekly_hours","status"]
    if sections.empty: return pd.DataFrame(columns=cols),{"status":"OPTIMAL","assigned":0,"unassigned":0}
    model=cp_model.CpModel(); active=faculty[faculty.employment_status=="ACTIVE"]
    skill=set(zip(skills.faculty_id,skills.course_id))
    av=set(zip(availability.loc[availability.available,"faculty_id"],availability.loc[availability.available,"day_of_week"].astype(int),availability.loc[availability.available,"slot_id"]))
    x={}; ss=sections.reset_index(drop=True)
    for i,s in ss.iterrows():
        for _,f in active.iterrows():
            if (f.faculty_id,s.course_id) in skill and (f.faculty_id,int(s.day_of_week),s.slot_id) in av:
                x[(i,f.faculty_id)]=model.NewBoolVar(f"x_{i}_{f.faculty_id}")
    for i in range(len(ss)):
        vs=[v for (j,_),v in x.items() if i==j]
        if vs: model.Add(sum(vs)<=1)
    for _,f in active.iterrows():
        vs=[v for (i,fid),v in x.items() if fid==f.faculty_id]
        if vs: model.Add(sum(v*3 for v in vs)<=int(float(f.max_weekly_hours)))
    for fid in active.faculty_id:
        slots={}
        for (i,f),v in x.items():
            if f==fid:
                s=ss.iloc[i]; slots.setdefault((int(s.day_of_week),s.slot_id),[]).append(v)
        for vs in slots.values():
            if len(vs)>1: model.Add(sum(vs)<=1)
    model.Maximize(sum(x.values()) if x else 0)
    solver=cp_model.CpSolver(); solver.parameters.max_time_in_seconds=time_limit_seconds; solver.parameters.num_search_workers=8
    status=solver.Solve(model); name=solver.StatusName(status); rows=[]
    if status in (cp_model.OPTIMAL,cp_model.FEASIBLE):
        for (i,fid),v in x.items():
            if solver.Value(v):
                rows.append({"workload_assignment_id":f"WLA-2027-{len(rows)+1:06d}","section_id":ss.iloc[i].section_id,"faculty_id":fid,"weekly_hours":3.0,"status":"PROPOSED"})
    out=pd.DataFrame(rows,columns=cols); n=len(set(out.section_id)) if len(out) else 0
    return out,{"status":name,"assigned":n,"unassigned":len(ss)-n,"objective_value":float(solver.ObjectiveValue()) if status in (cp_model.OPTIMAL,cp_model.FEASIBLE) else None}
