from academic_planner.generator import generate_dataset,make_ground_truth
from academic_planner.validation import validate_frames
from academic_planner.planning import propose_sections,calculate_unmet
import pandas as pd

def test_volumes():
    d=generate_dataset()
    assert len(d["programs"])==10 and len(d["courses"])==100 and len(d["faculty"])==50 and len(d["student_plans"])==1000
def test_seed_reproducibility():
    a=generate_dataset(20261022); b=generate_dataset(20261022)
    for k in a: assert a[k].equals(b[k])
def test_baseline_integrity():
    assert validate_frames(generate_dataset())==[]
def test_ground_truth_has_five_scenarios():
    g=make_ground_truth(); assert len(g)==5 and g.issue_type.nunique()==5
def test_sections_cover_forecast():
    f=pd.DataFrame([{"course_id":"CRS-000001","forecast_enrollment":85}]); r=pd.DataFrame([{"room_id":"ROM-000001","capacity":40,"active":True}])
    s=propose_sections(f,r); assert s.planned_capacity.sum()>=85
def test_unmet_reconciles():
    f=pd.DataFrame([{"course_id":"CRS-000001","forecast_enrollment":100}]); s=pd.DataFrame([{"course_id":"CRS-000001","planned_capacity":40}])
    u=calculate_unmet(f,s).iloc[0]; assert u.unmet==u.forecast_demand-u.accommodated
