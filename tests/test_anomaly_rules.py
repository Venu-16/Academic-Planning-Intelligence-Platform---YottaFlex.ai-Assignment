import pandas as pd
from academic_planner.anomaly_rules import check_assignment

def inputs():
    faculty=pd.DataFrame([{"faculty_id":"FAC-000001","max_weekly_hours":6}])
    skills=pd.DataFrame([{"faculty_id":"FAC-000001","course_id":"CRS-000001"}])
    return faculty,skills

def test_faculty_outside_skill():
    f,s=inputs()
    assert "FACULTY_OUTSIDE_SKILL" in check_assignment(faculty_id="FAC-000001",course_id="CRS-000002",section_id="SEC-1",weekly_hours=3,faculty=f,skills=s)

def test_workload_exceeded():
    f,s=inputs()
    issues=check_assignment(faculty_id="FAC-000001",course_id="CRS-000001",section_id="SEC-2",weekly_hours=3,faculty=f,skills=s,existing_assignments=[{"faculty_id":"FAC-000001","weekly_hours":6}])
    assert "WORKLOAD_EXCEEDED" in issues

def test_capacity_too_low():
    f,s=inputs()
    issues=check_assignment(faculty_id="FAC-000001",course_id="CRS-000001",section_id="SEC-3",weekly_hours=3,faculty=f,skills=s,section_capacity=30,forecast_demand=45)
    assert "SECTION_CAPACITY_TOO_LOW" in issues

def test_prerequisite_violation():
    f,s=inputs()
    issues=check_assignment(faculty_id="FAC-000001",course_id="CRS-000001",section_id="SEC-4",weekly_hours=3,faculty=f,skills=s,prerequisite_met=False)
    assert "PREREQUISITE_SEQUENCE_VIOLATION" in issues

def test_duplicate_assignment():
    f,s=inputs()
    old=[{"section_id":"SEC-5","faculty_id":"FAC-000001","weekly_hours":3}]
    issues=check_assignment(faculty_id="FAC-000001",course_id="CRS-000001",section_id="SEC-5",weekly_hours=3,faculty=f,skills=s,existing_assignments=old)
    assert "DUPLICATE_SECTION_ASSIGNMENT" in issues
