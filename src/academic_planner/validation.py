import pandas as pd
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
    return issues
