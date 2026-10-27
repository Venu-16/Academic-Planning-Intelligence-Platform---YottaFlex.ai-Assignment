import pandas as pd

from academic_planner.allocation_diagnostics import diagnose_unstaffed_sections
from academic_planner.forecasting import forecast_demand
from academic_planner.generator import generate_dataset
from academic_planner.optimizer import allocate_faculty
from academic_planner.planning import propose_sections


def inputs(*, skilled=True, available=True, max_hours=6, existing=None):
    sections = [
        {
            "section_id": "SEC-1",
            "course_id": "CRS-1",
            "term_id": "2027-SPRING",
            "term_start_date": "2027-01-01",
            "term_end_date": "2027-05-31",
            "day_of_week": 0,
            "slot_id": "S1",
            "room_id": "ROM-1",
            "planned_capacity": 40,
        }
    ]
    assignments = []
    if existing:
        sections.append(
            {
                "section_id": "SEC-2",
                "course_id": "CRS-2",
                "term_id": "2027-SPRING",
                "term_start_date": "2027-01-01",
                "term_end_date": "2027-05-31",
                "day_of_week": existing["day"],
                "slot_id": existing["slot"],
                "room_id": "ROM-1",
                "planned_capacity": 40,
            }
        )
        assignments.append(
            {
                "section_id": "SEC-2",
                "faculty_id": "FAC-1",
                "weekly_hours": existing["hours"],
            }
        )

    return (
        pd.DataFrame(sections),
        pd.DataFrame(
            [
                {
                    "faculty_id": "FAC-1",
                    "employment_status": "ACTIVE",
                    "max_weekly_hours": max_hours,
                }
            ]
        ),
        pd.DataFrame(
            [{
                "faculty_id": "FAC-1",
                "course_id": "CRS-1",
                "effective_from": "2027-01-01",
                "effective_to": "2027-05-31",
            }]
            if skilled
            else [],
            columns=["faculty_id", "course_id", "effective_from", "effective_to"],
        ),
        pd.DataFrame(
            [
                {
                    "faculty_id": "FAC-1",
                    "term_id": "2027-SPRING",
                    "day_of_week": 0,
                    "slot_id": "S1",
                    "available": available,
                    "effective_from": "2027-01-01",
                    "effective_to": "2027-05-31",
                }
            ],
            columns=[
                "faculty_id", "term_id", "day_of_week", "slot_id", "available",
                "effective_from", "effective_to",
            ],
        ),
        pd.DataFrame(
            assignments,
            columns=["section_id", "faculty_id", "weekly_hours"],
        ),
    )


def diagnose(data):
    sections, faculty, skills, availability, assignments = data
    result = diagnose_unstaffed_sections(
        sections, faculty, skills, availability, assignments, "OPTIMAL"
    )
    return result["sections"][0]


def test_missing_skill_is_reported_as_confirmed_blocker():
    assert "MISSING_SKILL" in diagnose(inputs(skilled=False))["candidate_blocking_reasons"]


def test_unavailability_is_reported_as_confirmed_blocker():
    assert "UNAVAILABLE" in diagnose(inputs(available=False))["candidate_blocking_reasons"]


def test_workload_limit_is_reported_as_confirmed_blocker():
    data = inputs(max_hours=3, existing={"day": 1, "slot": "S2", "hours": 3})
    assert "WORKLOAD_LIMIT" in diagnose(data)["candidate_blocking_reasons"]


def test_timetable_conflict_is_reported_as_confirmed_blocker():
    data = inputs(max_hours=6, existing={"day": 0, "slot": "S1", "hours": 3})
    assert "TIMETABLE_CONFLICT" in diagnose(data)["candidate_blocking_reasons"]


def test_all_applicable_blockers_are_reported_for_a_candidate():
    data = inputs(
        available=False,
        max_hours=3,
        existing={"day": 0, "slot": "S1", "hours": 3},
    )
    assert diagnose(data)["candidate_blocking_reasons"] == [
        "TIMETABLE_CONFLICT",
        "UNAVAILABLE",
        "WORKLOAD_LIMIT",
    ]


def test_unresolved_feasible_candidate_is_not_mislabeled_as_blocked():
    result = diagnose(inputs())
    assert result["candidate_blocking_reasons"] == []
    assert result["accounted"] is False
    assert result["diagnosis"] == "UNEXPLAINED_FEASIBLE_CANDIDATE"


def test_invalid_section_is_accounted_even_when_faculty_candidate_is_feasible():
    data=inputs()
    data[0].loc[0,"validation_status"]="BLOCKED"
    data[0].loc[0,"validation_issues"]="ROOM_REQUIRED"

    result=diagnose(data)

    assert result["feasible_faculty_ids"]==["FAC-1"]
    assert result["candidate_blocking_reasons"]==["ROOM_REQUIRED"]
    assert result["accounted"] is True
    assert result["diagnosis"]=="BLOCKED_BY_SECTION_VALIDATION"


def test_generated_unstaffed_sections_are_all_accounted_for():
    frames = generate_dataset()
    forecasts, _ = forecast_demand(frames["historical_enrollments"])
    sections = propose_sections(
        forecasts, frames["rooms"], academic_terms=frames["academic_terms"]
    )
    assignments, solver_metrics = allocate_faculty(
        sections, frames["faculty"], frames["faculty_skills"], frames["availability"]
    )
    report = diagnose_unstaffed_sections(
        sections,
        frames["faculty"],
        frames["faculty_skills"],
        frames["availability"],
        assignments,
        solver_metrics["status"],
    )

    assert report["unstaffed_sections"] == solver_metrics["unassigned"]
    assert report["accounted_unstaffed_sections"] == report["unstaffed_sections"]
    assert report["fully_accounted"] is True
