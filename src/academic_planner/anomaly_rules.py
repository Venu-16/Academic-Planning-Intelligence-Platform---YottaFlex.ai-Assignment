def check_assignment(*, faculty_id, course_id, section_id, weekly_hours, faculty,
                     skills, existing_assignments=None, section_capacity=None,
                     forecast_demand=None, prerequisite_met=True):
    """Return rule-based issue codes for one proposed assignment; labels never enter ML features."""
    existing_assignments = existing_assignments or []
    issues=[]
    f=faculty.loc[faculty.faculty_id==faculty_id]
    if f.empty:
        return ["UNKNOWN_FACULTY"]
    if (faculty_id,course_id) not in set(zip(skills.faculty_id,skills.course_id)):
        issues.append("FACULTY_OUTSIDE_SKILL")
    current=sum(float(x.get("weekly_hours",0)) for x in existing_assignments if x.get("faculty_id")==faculty_id)
    if current+float(weekly_hours)>float(f.iloc[0].max_weekly_hours):
        issues.append("WORKLOAD_EXCEEDED")
    if section_capacity is not None and forecast_demand is not None and int(forecast_demand)>int(section_capacity):
        issues.append("SECTION_CAPACITY_TOO_LOW")
    if not prerequisite_met:
        issues.append("PREREQUISITE_SEQUENCE_VIOLATION")
    if any(x.get("section_id")==section_id and x.get("faculty_id")==faculty_id for x in existing_assignments):
        issues.append("DUPLICATE_SECTION_ASSIGNMENT")
    return issues
