import json

import pandas as pd
import pytest

from academic_planner.generator import Scale, TARGET_SCALE, export_dataset, generate_dataset
from academic_planner.lifecycle import (
    InvalidLifecycleTransition,
    validate_lifecycle_transition,
)
from academic_planner.pipeline import run_pipeline
from academic_planner.planning import propose_sections
from academic_planner.validation import validate_frames


def test_target_scale_is_explicit_and_scale_values_must_be_positive():
    assert TARGET_SCALE == Scale(100, 1000, 500, 20000)
    with pytest.raises(ValueError, match="courses must be a positive integer"):
        Scale(courses=0)


def test_generated_section_ids_follow_the_selected_term_year():
    forecasts=pd.DataFrame([{
        "course_id":"CRS-000001","forecast_enrollment":20,
    }])
    rooms=pd.DataFrame([{
        "room_id":"ROM-000001","capacity":40,"active":True,
    }])

    sections=propose_sections(forecasts,rooms,term_id="2028-FALL")

    assert sections.iloc[0].section_id=="SEC-2028-000001"


def test_custom_scale_manifest_records_configuration_and_counts(tmp_path):
    scale = Scale(programs=2, courses=8, faculty=5, student_plans=12)
    frames = generate_dataset(seed=92, scale=scale)

    manifest = export_dataset(frames, tmp_path, seed=92, scale=scale)

    assert manifest["seed"] == 92
    assert manifest["scale"] == {
        "programs": 2,
        "courses": 8,
        "faculty": 5,
        "student_plans": 12,
    }
    assert manifest["tables"]["courses"]["rows"] == 8
    assert manifest["tables"]["student_plans"]["rows"] == 12


def test_source_validation_rejects_unknown_and_mismatched_term_references():
    frames = generate_dataset()
    frames["registration_interests"].loc[0, "term_id"] = "2028-FALL"

    issues = validate_frames(frames)

    codes = {issue["issue"] for issue in issues}
    assert "FOREIGN_KEY:term_id->academic_terms.term_id" in codes
    assert "STUDENT_PLAN_TERM_MISMATCH" in codes


def test_source_validation_rejects_invalid_effective_date_range():
    frames = generate_dataset()
    frames["faculty_skills"].loc[0, "effective_to"] = "2025-12-31"

    issues = validate_frames(frames)

    assert any(
        issue["table"] == "faculty_skills"
        and issue["issue"] == "INVALID_EFFECTIVE_DATE_RANGE"
        for issue in issues
    )


def test_source_validation_allows_fractional_workload_but_rejects_fractional_credits():
    frames=generate_dataset()
    frames["faculty"]["max_weekly_hours"]=frames["faculty"]["max_weekly_hours"].astype(float)
    frames["faculty"].loc[0,"max_weekly_hours"]=9.5
    frames["courses"]["credits"]=frames["courses"]["credits"].astype(float)
    frames["courses"].loc[0,"credits"]=2.5

    issues=validate_frames(frames)

    assert any(
        issue["table"]=="courses" and issue["issue"]=="INVALID_INTEGER:credits"
        for issue in issues
    )
    assert not any(
        issue["table"]=="faculty" and issue["issue"]=="INVALID_VALUE:max_weekly_hours"
        for issue in issues
    )


def test_generated_prerequisite_completions_support_registered_interests():
    frames=generate_dataset()
    completions=frames["student_course_completions"]

    assert not completions.duplicated(["student_plan_id","course_id"]).any()
    assert validate_frames(frames)==[]


def test_source_validation_rejects_registered_interest_without_prerequisite_completion():
    frames=generate_dataset()
    prerequisite=frames["prerequisites"].iloc[0]
    interest_index=frames["registration_interests"].index[0]
    plan_id=frames["registration_interests"].loc[
        interest_index,"student_plan_id"
    ]
    frames["registration_interests"].loc[
        interest_index,
        ["course_id","eligible","interest_status"],
    ]=[
        prerequisite.course_id,
        True,
        "REGISTERED",
    ]
    frames["student_course_completions"]=frames[
        "student_course_completions"
    ].loc[
        ~(
            (frames["student_course_completions"].student_plan_id==plan_id)
            &(frames["student_course_completions"].course_id
              ==prerequisite.prerequisite_course_id)
        )
    ].reset_index(drop=True)

    issues=validate_frames(frames)

    violation=next(
        issue for issue in issues
        if issue["issue"]=="PREREQUISITE_SEQUENCE_VIOLATION"
    )
    assert violation["entity_ids"]==[
        frames["registration_interests"].loc[interest_index,"interest_id"]
    ]
    assert violation["decision"]=="FLAG_INELIGIBLE"


def test_old_source_frames_without_completion_table_remain_compatible():
    frames=generate_dataset()
    del frames["student_course_completions"]

    assert validate_frames(frames)==[]


def test_source_validation_rejects_prerequisite_self_references_and_cycles():
    frames = generate_dataset()
    frames["prerequisites"] = pd.DataFrame(
        [
            {
                "prerequisite_id": "PRQ-TEST-1",
                "course_id": "CRS-000001",
                "prerequisite_course_id": "CRS-000002",
                "effective_from": "2026-01-01",
                "effective_to": None,
            },
            {
                "prerequisite_id": "PRQ-TEST-2",
                "course_id": "CRS-000002",
                "prerequisite_course_id": "CRS-000001",
                "effective_from": "2026-01-01",
                "effective_to": None,
            },
            {
                "prerequisite_id": "PRQ-TEST-3",
                "course_id": "CRS-000003",
                "prerequisite_course_id": "CRS-000003",
                "effective_from": "2026-01-01",
                "effective_to": None,
            },
        ]
    )

    issues = validate_frames(frames)

    codes = {issue["issue"] for issue in issues}
    assert "PREREQUISITE_CYCLE" in codes
    assert "SELF_PREREQUISITE" in codes


def test_invalid_lifecycle_transition_is_rejected():
    with pytest.raises(InvalidLifecycleTransition, match="OPERATIONAL -> PROPOSED"):
        validate_lifecycle_transition("section", "OPERATIONAL", "PROPOSED")


def test_small_pipeline_finalizes_export_statuses_and_transition_history(tmp_path):
    scale = Scale(programs=2, courses=8, faculty=8, student_plans=20)

    metrics = run_pipeline(
        output_dir=tmp_path,
        seed=20261022,
        persist=False,
        scale=scale,
    )

    sections = pd.read_csv(tmp_path / "sections.csv")
    assignments = pd.read_csv(tmp_path / "workload_assignments.csv")
    capacity = pd.read_csv(tmp_path / "operational_capacity.csv")
    events = json.loads((tmp_path / "decision_events.json").read_text())
    report = json.loads((tmp_path / "evaluation_report.json").read_text())
    manifest = json.loads((tmp_path / "source_manifest.json").read_text())

    status_by_section = capacity.set_index("section_id").section_status
    assert sections.set_index("section_id").status.tolist() == status_by_section.tolist()
    assert sections.proposal_status.eq("PROPOSED").all()
    assert not sections.status.eq("PROPOSED").any()
    assert set(sections.status).issubset(
        {"OPERATIONAL", "UNSTAFFED", "BLOCKED", "REJECTED"}
    )
    assert (assignments.status == "APPROVED").any()
    assert assignments.loc[assignments.status == "APPROVED", "section_id"].map(
        lambda section_id: bool(
            capacity.loc[
                capacity.section_id == section_id, "operational"
            ].iloc[0]
        )
    ).all()
    assert assignments.loc[assignments.status == "REJECTED", "section_id"].map(
        lambda section_id: not bool(
            capacity.loc[
                capacity.section_id == section_id, "operational"
            ].iloc[0]
        )
    ).all()
    assert not ((sections.status == "UNSTAFFED") & (sections.section_id.isin(assignments.section_id))).any()
    assert capacity.loc[
        capacity.section_status=="BLOCKED","operational_capacity"
    ].eq(0).all()
    assert capacity.loc[
        capacity.section_status!="OPERATIONAL","operational_capacity"
    ].eq(0).all()
    assert manifest["scale"] == scale.__dict__
    assert report["planning_run_id"] == metrics["planning_run_id"]
    assert report["performance"]["elapsed_seconds"] > 0
    assert report["performance"]["python_peak_memory_bytes"] > 0
    assert len(events) == len(sections) + len(assignments)
    assert {event["planning_run_id"] for event in events} == {
        metrics["planning_run_id"]
    }
    assert all(
        event["payload"]["previous_state"] == "PROPOSED"
        and event["payload"]["new_state"]
        and event["payload"]["reason_code"]
        and event["event_time"]
        for event in events
    )
