import pandas as pd
import pytest

from academic_planner.optimizer import allocate_faculty
from academic_planner.planning import calculate_operational_capacity
from academic_planner.validation import validate_assignment_outputs


TERM = "2027-SPRING"
TERM_START = "2027-01-01"
TERM_END = "2027-05-31"


def section(section_id="SEC-1", course_id="CRS-1", day=0, slot="S1"):
    return {
        "section_id": section_id,
        "course_id": course_id,
        "term_id": TERM,
        "term_start_date": TERM_START,
        "term_end_date": TERM_END,
        "room_id": "ROM-1",
        "day_of_week": day,
        "slot_id": slot,
        "planned_capacity": 30,
        "forecast_demand": 30,
    }


def faculty(max_hours=6):
    return pd.DataFrame([{
        "faculty_id": "FAC-1",
        "employment_status": "ACTIVE",
        "max_weekly_hours": max_hours,
    }])


def skills(course_id="CRS-1", effective_from=TERM_START, effective_to=TERM_END):
    return pd.DataFrame([{
        "faculty_skill_id": "FSK-1",
        "faculty_id": "FAC-1",
        "course_id": course_id,
        "effective_from": effective_from,
        "effective_to": effective_to,
    }])


def availability(*, term_id=TERM, day=0, slot="S1", available=True,
                 effective_from=TERM_START, effective_to=TERM_END):
    return pd.DataFrame([{
        "availability_id": "AVL-1",
        "faculty_id": "FAC-1",
        "term_id": term_id,
        "day_of_week": day,
        "slot_id": slot,
        "available": available,
        "effective_from": effective_from,
        "effective_to": effective_to,
    }])


def assignment(section_id="SEC-1", faculty_id="FAC-1", assignment_id="WLA-1"):
    return {
        "workload_assignment_id": assignment_id,
        "section_id": section_id,
        "faculty_id": faculty_id,
        "weekly_hours": 3,
        "status": "PROPOSED",
    }


def validate(assignments, sections, faculty_frame=None, skill_frame=None, availability_frame=None):
    return validate_assignment_outputs(
        pd.DataFrame(assignments),
        pd.DataFrame(sections),
        faculty_frame if faculty_frame is not None else faculty(),
        skill_frame if skill_frame is not None else skills(),
        availability_frame if availability_frame is not None else availability(),
    )


def test_valid_term_specific_faculty_assignment_is_eligible_and_operational():
    sections = pd.DataFrame([section()])
    assignments = pd.DataFrame([assignment()])
    skill_frame = skills()
    availability_frame = availability()

    result = validate_assignment_outputs(
        assignments, sections, faculty(), skill_frame, availability_frame
    )
    capacity = calculate_operational_capacity(
        sections,
        assignments,
        pd.DataFrame([{"room_id": "ROM-1", "capacity": 40, "active": True}]),
        faculty(),
        skill_frame,
        availability_frame,
    )

    assert result["passed"]
    assert capacity.iloc[0].operational_capacity == 30


@pytest.mark.parametrize("skill_course", [None, "CRS-OTHER"])
def test_missing_or_mismatched_course_skill_is_rejected(skill_course):
    skill_frame = skills(course_id=skill_course) if skill_course else skills().iloc[0:0]
    proposed, _ = allocate_faculty(
        pd.DataFrame([section()]), faculty(), skill_frame, availability()
    )
    result = validate(
        [assignment()],
        [section()],
        skill_frame=skill_frame,
    )

    assert proposed.empty
    assert "FACULTY_OUTSIDE_SKILL" in result["issues"][0]["issues"]


def test_missing_target_term_availability_is_not_assumed_available():
    result = validate(
        [assignment()],
        [section()],
        availability_frame=availability(term_id="2026-FALL"),
    )

    assert "AVAILABILITY_MISSING" in result["issues"][0]["issues"]


def test_explicitly_unavailable_target_term_slot_is_rejected():
    result = validate(
        [assignment()],
        [section()],
        availability_frame=availability(available=False),
    )

    assert "UNAVAILABLE" in result["issues"][0]["issues"]


@pytest.mark.parametrize(
    ("effective_from", "effective_to", "expected_issue"),
    [
        (TERM_START, TERM_END, None),
        ("2027-01-02", TERM_END, "QUALIFICATION_NOT_YET_EFFECTIVE"),
        (TERM_START, "2027-05-30", "QUALIFICATION_EXPIRES_BEFORE_TERM_END"),
    ],
)
def test_qualification_effective_dates_cover_the_whole_term_inclusively(
    effective_from, effective_to, expected_issue
):
    result = validate(
        [assignment()],
        [section()],
        skill_frame=skills(effective_from=effective_from, effective_to=effective_to),
    )

    issues = result["issues"][0]["issues"] if result["issues"] else []
    assert (expected_issue in issues) if expected_issue else result["passed"]


def test_missing_term_dates_fail_closed():
    section_without_dates = section()
    section_without_dates.pop("term_start_date")
    section_without_dates.pop("term_end_date")
    result = validate([assignment()], [section_without_dates])

    assert "TERM_DATES_UNAVAILABLE" in result["issues"][0]["issues"]


def test_missing_effective_date_evidence_is_not_assumed_open_ended():
    missing_skill_dates = skills().drop(columns=["effective_from", "effective_to"])
    missing_availability_dates = availability().drop(
        columns=["effective_from", "effective_to"]
    )
    result = validate(
        [assignment()],
        [section()],
        skill_frame=missing_skill_dates,
        availability_frame=missing_availability_dates,
    )

    assert "QUALIFICATION_DATES_MISSING" in result["issues"][0]["issues"]
    assert "AVAILABILITY_DATES_MISSING" in result["issues"][0]["issues"]


def test_optimizer_enforces_term_weekly_workload_limit():
    sections = pd.DataFrame([
        section("SEC-1", "CRS-1", day=0, slot="S1"),
        section("SEC-2", "CRS-2", day=1, slot="S1"),
    ])
    skill_frame = pd.concat([skills("CRS-1"), skills("CRS-2")], ignore_index=True)
    availability_frame = pd.concat(
        [
            availability(day=0, slot="S1"),
            availability(day=1, slot="S1"),
        ],
        ignore_index=True,
    )
    assignments, _ = allocate_faculty(
        sections, faculty(max_hours=3), skill_frame, availability_frame
    )

    assert len(assignments) == 1


def test_validator_flags_workload_overage_in_target_term():
    result = validate(
        [assignment("SEC-1", assignment_id="WLA-1"),
         assignment("SEC-2", assignment_id="WLA-2")],
        [section("SEC-1", "CRS-1", day=0), section("SEC-2", "CRS-1", day=1)],
        faculty_frame=faculty(max_hours=3),
        availability_frame=pd.concat(
            [availability(day=0), availability(day=1)], ignore_index=True
        ),
    )

    assert any(
        "WORKLOAD_EXCEEDED" in issue["issues"]
        for issue in result["issues"]
    )


def test_optimizer_prevents_overlapping_assignments_and_validator_flags_manual_overlap():
    sections = pd.DataFrame([
        section("SEC-1", "CRS-1"),
        section("SEC-2", "CRS-2"),
    ])
    skill_frame = pd.concat([skills("CRS-1"), skills("CRS-2")], ignore_index=True)
    assignments, _ = allocate_faculty(
        sections, faculty(), skill_frame, availability()
    )
    assert len(assignments) == 1

    manual = [assignment("SEC-1", assignment_id="WLA-1"),
              assignment("SEC-2", assignment_id="WLA-2")]
    result = validate(
        manual,
        sections.to_dict("records"),
        skill_frame=skill_frame,
    )

    assert all(
        "FACULTY_TIMETABLE_CONFLICT" in issue["issues"]
        for issue in result["issues"]
    )


def test_invalid_assignment_is_excluded_from_operational_capacity():
    sections = pd.DataFrame([section()])
    assignments = pd.DataFrame([assignment()])
    skill_frame = skills(course_id="CRS-OTHER")
    capacity = calculate_operational_capacity(
        sections,
        assignments,
        pd.DataFrame([{"room_id": "ROM-1", "capacity": 40, "active": True}]),
        faculty(),
        skill_frame,
        availability(),
    )

    assert capacity.iloc[0].operational_capacity == 0
    assert "FACULTY_OUTSIDE_SKILL" in capacity.iloc[0].blocking_reasons
