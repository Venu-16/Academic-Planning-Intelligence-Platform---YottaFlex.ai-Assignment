import json
from pathlib import Path

import pandas as pd
import pytest

from academic_planner.anomaly_rules import check_assignment
from academic_planner.generator import generate_dataset
from academic_planner.validation import validate_frames


GROUND_TRUTH = Path(__file__).parents[1] / "data" / "generated" / "ground_truth.csv"
EXPECTED = {
    "FACULTY_OUTSIDE_SKILL": ("FACULTY_OUTSIDE_SKILL", "REJECT_ASSIGNMENT"),
    "WORKLOAD_EXCEEDED": ("WORKLOAD_EXCEEDED", "REJECT_OR_REASSIGN"),
    "SECTION_CAPACITY_TOO_LOW": ("SECTION_CAPACITY_TOO_LOW", "ADD_SECTION_OR_RECORD_UNMET"),
    "PREREQUISITE_SEQUENCE_VIOLATION": (
        "PREREQUISITE_SEQUENCE_VIOLATION",
        "FLAG_INELIGIBLE",
    ),
    "DUPLICATE_SECTION_ASSIGNMENT": (
        "DUPLICATE_SECTION_ASSIGNMENT",
        "REJECT_DUPLICATE",
    ),
}


def ground_truth_cases():
    cases = pd.read_csv(GROUND_TRUTH).to_dict("records")
    assert len(cases) == len(EXPECTED)
    assert {case["issue_type"] for case in cases} == set(EXPECTED)
    return cases


def rule_checker_inputs(issue_type):
    kwargs = {
        "faculty_id": "FAC-TEST",
        "course_id": "CRS-TEST",
        "section_id": "SEC-TEST",
        "weekly_hours": 3,
        "faculty": pd.DataFrame(
            [{"faculty_id": "FAC-TEST", "max_weekly_hours": 6}]
        ),
        "skills": pd.DataFrame(
            [{"faculty_id": "FAC-TEST", "course_id": "CRS-TEST"}]
        ),
    }

    if issue_type == "FACULTY_OUTSIDE_SKILL":
        kwargs["course_id"] = "CRS-UNSKILLED"
    elif issue_type == "WORKLOAD_EXCEEDED":
        kwargs["existing_assignments"] = [
            {"faculty_id": "FAC-TEST", "section_id": "SEC-OLD", "weekly_hours": 6}
        ]
    elif issue_type == "SECTION_CAPACITY_TOO_LOW":
        kwargs.update(section_capacity=30, forecast_demand=45)
    elif issue_type == "PREREQUISITE_SEQUENCE_VIOLATION":
        kwargs["prerequisite_met"] = False
    elif issue_type == "DUPLICATE_SECTION_ASSIGNMENT":
        kwargs["existing_assignments"] = [
            {
                "faculty_id": "FAC-TEST",
                "section_id": "SEC-TEST",
                "weekly_hours": 3,
            }
        ]
    else:
        raise AssertionError(f"Unknown ground-truth issue type: {issue_type}")

    return kwargs


def add_frame_validation_fixture(frames, issue_type):
    if issue_type == "SECTION_CAPACITY_TOO_LOW":
        frames["sections"] = pd.DataFrame(
            [
                {
                    "section_id": "SEC-SYNTHETIC",
                    "course_id": frames["courses"].iloc[0].course_id,
                    "term_id": "2027-SPRING",
                    "section_number": 1,
                    "room_id": None,
                    "day_of_week": 0,
                    "slot_id": "S1",
                    "planned_capacity": 30,
                    "forecast_demand": 45,
                    "status": "PARTIAL",
                }
            ]
        )
    elif issue_type == "PREREQUISITE_SEQUENCE_VIOLATION":
        frames["registration_interests"] = pd.DataFrame(
            [
                {
                    "interest_id": "INT-SYNTHETIC",
                    "student_plan_id": frames["student_plans"].iloc[0].student_plan_id,
                    "course_id": frames["courses"].iloc[0].course_id,
                    "term_id": "2027-SPRING",
                    "interest_status": "REGISTERED",
                    "interest_date": "2026-10-15",
                    "eligible": False,
                }
            ]
        )
    else:
        assignment_rows = [
            {
                "workload_assignment_id": "WLA-SYNTHETIC-1",
                "section_id": "SEC-SYNTHETIC",
                "faculty_id": frames["faculty"].iloc[0].faculty_id,
                "weekly_hours": 6 if issue_type == "WORKLOAD_EXCEEDED" else 3,
                "course_id": frames["courses"].iloc[0].course_id,
            }
        ]
        if issue_type == "DUPLICATE_SECTION_ASSIGNMENT":
            assignment_rows.append(
                {
                    **assignment_rows[0],
                    "workload_assignment_id": "WLA-SYNTHETIC-2",
                }
            )
        elif issue_type == "FACULTY_OUTSIDE_SKILL":
            assignment_rows[0]["course_id"] = "CRS-UNSKILLED"
        frames["workload_assignments"] = pd.DataFrame(assignment_rows)


@pytest.fixture(scope="module")
def baseline_frames():
    return generate_dataset()


@pytest.mark.parametrize(
    "case",
    ground_truth_cases(),
    ids=lambda case: case["issue_type"],
)
def test_ground_truth_fixture_matches_rule_checker(case):
    issue_type = case["issue_type"]
    expected_issue, expected_decision = EXPECTED[issue_type]

    actual_issues = check_assignment(**rule_checker_inputs(issue_type))

    assert actual_issues == [expected_issue]
    assert case["expected_decision"] == expected_decision


@pytest.mark.parametrize(
    "case",
    ground_truth_cases(),
    ids=lambda case: case["issue_type"],
)
def test_frame_validator_detects_prerequisite_anomaly_only(case, baseline_frames):
    issue_type = case["issue_type"]
    isolated_frames = {name: frame.copy(deep=True) for name, frame in baseline_frames.items()}
    add_frame_validation_fixture(isolated_frames, issue_type)

    actual_issues = validate_frames(isolated_frames)

    expected=issue_type=="PREREQUISITE_SEQUENCE_VIOLATION"
    assert any(issue["issue"]==issue_type for issue in actual_issues)==expected


def test_normal_baseline_remains_clean(baseline_frames):
    assert validate_frames(baseline_frames) == []


@pytest.mark.parametrize(
    ("issue_type", "expected_rule"),
    [
        ("FACULTY_OUTSIDE_SKILL", "FACULTY_OUTSIDE_SKILL"),
        ("WORKLOAD_EXCEEDED", "WORKLOAD_EXCEEDED"),
        ("DUPLICATE_SECTION_ASSIGNMENT", "DUPLICATE_SECTION_ASSIGNMENT"),
    ],
)
def test_pipeline_blocks_invalid_assignment_from_operational_capacity(
    issue_type, expected_rule, tmp_path, monkeypatch
):
    import academic_planner.pipeline as pipeline

    original_allocate = pipeline.allocate_faculty

    def allocate_with_fixture(sections, faculty, skills, availability):
        assignments, metrics = original_allocate(sections, faculty, skills, availability)
        if assignments.empty:
            pytest.fail("The valid control allocation did not produce an assignment")

        target = assignments.iloc[0].copy()
        if issue_type == "FACULTY_OUTSIDE_SKILL":
            target_course = sections.loc[
                sections.section_id == target.section_id, "course_id"
            ].iloc[0]
            skills.drop(
                skills.index[
                    (skills.faculty_id == target.faculty_id)
                    & (skills.course_id == target_course)
                ],
                inplace=True,
            )
        elif issue_type == "WORKLOAD_EXCEEDED":
            faculty.loc[faculty.faculty_id == target.faculty_id, "max_weekly_hours"] = 2
        else:
            duplicate = target.copy()
            duplicate["workload_assignment_id"] = "WLA-SYNTHETIC-DUPLICATE"
            assignments = pd.concat([assignments, duplicate.to_frame().T], ignore_index=True)
            metrics["assigned"] += 1
            metrics["unassigned"] -= 1

        return assignments, metrics

    monkeypatch.setattr(pipeline, "allocate_faculty", allocate_with_fixture)
    metrics = pipeline.run_pipeline(output_dir=tmp_path, persist=False)

    validation = json.loads((tmp_path / "planning_validation.json").read_text())
    capacity = pd.read_csv(tmp_path / "operational_capacity.csv")
    assignments = pd.read_csv(tmp_path / "workload_assignments.csv")
    assert not metrics["planning_validation"]["passed"]
    matching_issues = [
        issue
        for issue in validation["assignment_issues"]
        if expected_rule in issue["issues"]
    ]
    assert matching_issues
    for issue in matching_issues:
        section = capacity.loc[capacity.section_id == issue["section_id"]].iloc[0]
        assert section.operational_capacity == 0
        assert expected_rule in section.blocking_reasons
        assert assignments.loc[
            assignments.workload_assignment_id == issue["assignment_id"], "status"
        ].iloc[0] == "REJECTED"


def test_pipeline_flags_ineligible_registration_before_allocation(tmp_path, monkeypatch):
    import academic_planner.pipeline as pipeline

    original_generate = pipeline.generate_dataset
    allocator_called = False

    def generate_with_ineligible_registration(seed):
        frames = original_generate(seed)
        frames["registration_interests"].loc[
            frames["registration_interests"].index[0], ["eligible", "interest_status"]
        ] = [False, "REGISTERED"]
        return frames

    def unexpected_allocator(*args, **kwargs):
        nonlocal allocator_called
        allocator_called = True
        pytest.fail("Pipeline allocated before rejecting the ineligible registration")

    monkeypatch.setattr(pipeline, "generate_dataset", generate_with_ineligible_registration)
    monkeypatch.setattr(pipeline, "allocate_faculty", unexpected_allocator)

    with pytest.raises(RuntimeError, match="Baseline validation failed"):
        pipeline.run_pipeline(output_dir=tmp_path, persist=False)

    report = json.loads((tmp_path / "validation_report.json").read_text())
    assert not allocator_called
    assert not report["passed"]
    assert "PREREQUISITE_SEQUENCE_VIOLATION" in str(report["issues"])


def test_pipeline_reports_capacity_shortfall_as_existing_ground_truth_rule(
    tmp_path, monkeypatch
):
    import academic_planner.pipeline as pipeline

    original_forecast = pipeline.forecast_demand
    original_propose = pipeline.propose_sections
    target_course = "CRS-000001"

    def forecast_with_capacity_fixture(history):
        forecasts, metrics = original_forecast(history)
        forecasts.loc[
            forecasts.course_id == target_course, "forecast_enrollment"
        ] = 45
        return forecasts, metrics

    def propose_one_insufficient_section(forecasts, rooms, academic_terms=None):
        sections = original_propose(
            forecasts, rooms, academic_terms=academic_terms
        )
        target = sections[sections.course_id == target_course].head(1)
        return pd.concat(
            [target, sections[sections.course_id != target_course]],
            ignore_index=True,
        )

    monkeypatch.setattr(pipeline, "forecast_demand", forecast_with_capacity_fixture)
    monkeypatch.setattr(pipeline, "propose_sections", propose_one_insufficient_section)
    pipeline.run_pipeline(output_dir=tmp_path, persist=False)

    unmet = pd.read_csv(tmp_path / "unmet_demand.csv").set_index("course_id")
    target = unmet.loc[target_course]
    assert target.forecast_demand == 45
    assert target.operational_capacity < target.forecast_demand
    assert target.unmet == target.forecast_demand - target.operational_capacity
    assert "SECTION_CAPACITY_TOO_LOW" in target.capacity_blockers


def test_valid_pipeline_assignments_remain_operational(tmp_path):
    import academic_planner.pipeline as pipeline

    metrics = pipeline.run_pipeline(output_dir=tmp_path, persist=False)
    validation = json.loads((tmp_path / "planning_validation.json").read_text())
    capacity = pd.read_csv(tmp_path / "operational_capacity.csv")

    assert metrics["planning_validation"]["passed"]
    assert metrics["planning_validation"]["invalid_assignment_count"] == 0
    assert validation["passed"] and validation["assignment_issues"] == []
    assert capacity.operational.sum() == metrics["allocation"]["sections_staffed"]
