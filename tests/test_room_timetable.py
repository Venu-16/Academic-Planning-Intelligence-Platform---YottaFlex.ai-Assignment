import pandas as pd
import json

from academic_planner.planning import calculate_operational_capacity
from academic_planner.validation import (
    validate_assignment_outputs,
    validate_section_outputs,
)


TERM_ID = "2027-SPRING"
TERM_START = "2027-01-01"
TERM_END = "2027-05-31"


def section(section_id="SEC-1", *, room_id="ROM-1", day=0, slot="S1",
            term_id=TERM_ID, course_id="CRS-1", planned_capacity=30):
    return {
        "section_id": section_id,
        "course_id": course_id,
        "term_id": term_id,
        "term_start_date": TERM_START,
        "term_end_date": TERM_END,
        "section_number": 1,
        "room_id": room_id,
        "day_of_week": day,
        "slot_id": slot,
        "planned_capacity": planned_capacity,
        "forecast_demand": planned_capacity,
    }


def rooms():
    return pd.DataFrame([
        {
            "room_id": "ROM-1",
            "room_type": "LECTURE",
            "capacity": 40,
            "active": True,
        },
        {
            "room_id": "ROM-2",
            "room_type": "LAB",
            "capacity": 20,
            "active": True,
        },
    ])


def terms():
    return pd.DataFrame([
        {
            "term_id": TERM_ID,
            "start_date": TERM_START,
            "end_date": TERM_END,
        }
    ])


def assignment(section_id, faculty_id="FAC-1", assignment_id=None):
    return {
        "workload_assignment_id": assignment_id or f"WLA-{section_id}",
        "section_id": section_id,
        "faculty_id": faculty_id,
        "weekly_hours": 3,
        "status": "PROPOSED",
    }


def faculty():
    return pd.DataFrame([{
        "faculty_id": "FAC-1",
        "employment_status": "ACTIVE",
        "max_weekly_hours": 6,
    }])


def skills(course_ids=("CRS-1", "CRS-2")):
    return pd.DataFrame([
        {
            "faculty_id": "FAC-1",
            "course_id": course_id,
            "effective_from": TERM_START,
            "effective_to": TERM_END,
        }
        for course_id in course_ids
    ])


def availability(section_rows):
    return pd.DataFrame([
        {
            "faculty_id": "FAC-1",
            "term_id": row["term_id"],
            "day_of_week": row["day_of_week"],
            "slot_id": row["slot_id"],
            "available": True,
            "effective_from": TERM_START,
            "effective_to": TERM_END,
        }
        for row in section_rows
    ])


def reasons(report, section_id):
    return next(
        issue["issues"]
        for issue in report["issues"]
        if issue["section_id"] == section_id
    )


def test_room_capacity_sufficiency_and_shortfall_use_planned_seats():
    sufficient = validate_section_outputs(
        pd.DataFrame([section(planned_capacity=40)]), rooms(), terms()
    )
    insufficient = validate_section_outputs(
        pd.DataFrame([section(room_id="ROM-2", planned_capacity=30)]),
        rooms(),
        terms(),
    )

    assert sufficient["passed"]
    assert "ROOM_CAPACITY_TOO_LOW" in reasons(insufficient, "SEC-1")


def test_room_double_booking_is_rejected_but_different_slot_is_allowed():
    conflicting = validate_section_outputs(
        pd.DataFrame([
            section("SEC-1"),
            section("SEC-2", course_id="CRS-2"),
        ]),
        rooms(),
        terms(),
    )
    adjacent_slots = validate_section_outputs(
        pd.DataFrame([
            section("SEC-1"),
            section("SEC-2", course_id="CRS-2", slot="S2"),
        ]),
        rooms(),
        terms(),
    )

    assert "ROOM_TIMETABLE_CONFLICT" in reasons(conflicting, "SEC-1")
    assert "ROOM_TIMETABLE_CONFLICT" in reasons(conflicting, "SEC-2")
    assert adjacent_slots["passed"]


def test_faculty_identical_slot_conflict_is_rejected_and_adjacent_slot_is_valid():
    same_slot_sections = [
        section("SEC-1", room_id="ROM-1"),
        section("SEC-2", room_id="ROM-2", course_id="CRS-2"),
    ]
    same_slot = validate_assignment_outputs(
        pd.DataFrame([assignment("SEC-1"), assignment("SEC-2")]),
        pd.DataFrame(same_slot_sections),
        faculty(),
        skills(),
        availability(same_slot_sections),
    )
    adjacent_sections = [
        section("SEC-1", room_id="ROM-1"),
        section("SEC-2", room_id="ROM-2", course_id="CRS-2", slot="S2"),
    ]
    adjacent = validate_assignment_outputs(
        pd.DataFrame([assignment("SEC-1"), assignment("SEC-2")]),
        pd.DataFrame(adjacent_sections),
        faculty(),
        skills(),
        availability(adjacent_sections),
    )

    assert all(
        "FACULTY_TIMETABLE_CONFLICT" in issue["issues"]
        for issue in same_slot["issues"]
    )
    assert adjacent["passed"]


def test_unknown_room_and_unknown_section_references_are_reported():
    section_report = validate_section_outputs(
        pd.DataFrame([section(room_id="ROM-MISSING")]), rooms(), terms()
    )
    section_refs = pd.DataFrame([section("SEC-1")])
    assignment_report = validate_assignment_outputs(
        pd.DataFrame([assignment("SEC-NOT-FOUND")]),
        section_refs,
        faculty(),
        skills(),
        availability(section_refs.to_dict("records")),
    )

    assert "UNKNOWN_ROOM" in reasons(section_report, "SEC-1")
    assert "UNKNOWN_SECTION" in assignment_report["issues"][0]["issues"]


def test_section_and_availability_term_mismatches_are_rejected():
    wrong_term_section = section(term_id="2026-FALL")
    section_report = validate_section_outputs(
        pd.DataFrame([wrong_term_section]), rooms(), terms()
    )
    valid_term_section = section()
    wrong_term_availability = availability([valid_term_section])
    wrong_term_availability["term_id"] = "2026-FALL"
    assignment_report = validate_assignment_outputs(
        pd.DataFrame([assignment("SEC-1")]),
        pd.DataFrame([valid_term_section]),
        faculty(),
        skills(),
        wrong_term_availability,
    )

    assert "UNKNOWN_ACADEMIC_TERM" in reasons(section_report, "SEC-1")
    assert "AVAILABILITY_MISSING" in assignment_report["issues"][0]["issues"]


def test_term_date_mismatch_and_missing_room_or_schedule_block_sections():
    mismatch = section()
    mismatch["term_end_date"] = "2027-05-30"
    missing = section("SEC-2", room_id=None, day="invalid", slot="")
    report = validate_section_outputs(
        pd.DataFrame([mismatch, missing]), rooms(), terms()
    )

    assert "TERM_MISMATCH" in reasons(report, "SEC-1")
    missing_reasons = reasons(report, "SEC-2")
    assert "ROOM_REQUIRED" in missing_reasons
    assert "INVALID_TIMETABLE" in missing_reasons


def test_invalid_room_conflict_sections_are_excluded_from_operational_capacity():
    section_rows = [section("SEC-1"), section("SEC-2", course_id="CRS-2")]
    section_frame = pd.DataFrame(section_rows)
    report = validate_section_outputs(section_frame, rooms(), terms())
    issue_map = {
        issue["section_id"]: issue["issues"] for issue in report["issues"]
    }
    assignments = pd.DataFrame([
        assignment("SEC-1"),
        assignment("SEC-2", faculty_id="FAC-2"),
    ])
    faculty_frame = pd.DataFrame([
        {"faculty_id": "FAC-1", "employment_status": "ACTIVE", "max_weekly_hours": 6},
        {"faculty_id": "FAC-2", "employment_status": "ACTIVE", "max_weekly_hours": 6},
    ])
    skill_frame = pd.DataFrame([
        {"faculty_id": faculty_id, "course_id": course_id,
         "effective_from": TERM_START, "effective_to": TERM_END}
        for faculty_id, course_id in (("FAC-1", "CRS-1"), ("FAC-2", "CRS-2"))
    ])
    availability_frame = pd.DataFrame([
        {"faculty_id": faculty_id, "term_id": TERM_ID, "day_of_week": 0,
         "slot_id": "S1", "available": True,
         "effective_from": TERM_START, "effective_to": TERM_END}
        for faculty_id in ("FAC-1", "FAC-2")
    ])
    capacity = calculate_operational_capacity(
        section_frame,
        assignments,
        rooms(),
        faculty_frame,
        skill_frame,
        availability_frame,
        issue_map,
    )

    assert capacity.operational_capacity.sum() == 0
    assert capacity.blocking_reasons.str.contains("ROOM_TIMETABLE_CONFLICT").all()


def test_missing_room_and_schedule_cannot_be_operational():
    section_frame = pd.DataFrame([section(room_id=None, day=8, slot="")])
    capacity = calculate_operational_capacity(
        section_frame,
        pd.DataFrame([assignment("SEC-1")]),
        rooms(),
        faculty(),
        skills(),
        availability([section()]),
    )

    assert capacity.iloc[0].operational_capacity == 0
    assert "NO_ACTIVE_ROOM" in capacity.iloc[0].blocking_reasons
    assert "INVALID_TIMETABLE" in capacity.iloc[0].blocking_reasons


def test_pipeline_blocks_conflicting_room_sections_before_allocation(
    tmp_path, monkeypatch
):
    import academic_planner.pipeline as pipeline

    original_propose = pipeline.propose_sections

    def propose_with_room_conflict(
        forecasts, room_frame, term_id=None, academic_terms=None
    ):
        proposed = original_propose(
            forecasts, room_frame, term_id=term_id, academic_terms=academic_terms
        )
        assert len(proposed) > 1
        proposed.loc[proposed.index[1], ["room_id", "day_of_week", "slot_id"]] = (
            proposed.iloc[0].room_id,
            proposed.iloc[0].day_of_week,
            proposed.iloc[0].slot_id,
        )
        return proposed

    monkeypatch.setattr(pipeline, "propose_sections", propose_with_room_conflict)
    metrics = pipeline.run_pipeline(output_dir=tmp_path, persist=False)

    sections = pd.read_csv(tmp_path / "sections.csv")
    capacity = pd.read_csv(tmp_path / "operational_capacity.csv")
    assignments = pd.read_csv(tmp_path / "workload_assignments.csv")
    validation = json.loads((tmp_path / "section_validation.json").read_text())
    conflict_ids = {
        issue["section_id"]
        for issue in validation["issues"]
        if "ROOM_TIMETABLE_CONFLICT" in issue["issues"]
    }

    assert len(conflict_ids) >= 2
    assert sections.loc[
        sections.section_id.isin(conflict_ids), "validation_status"
    ].eq("BLOCKED").all()
    assert not assignments.section_id.isin(conflict_ids).any()
    assert capacity.loc[
        capacity.section_id.isin(conflict_ids), "operational_capacity"
    ].eq(0).all()
    assert metrics["allocation"]["sections_staffed"] == capacity.operational.sum()
