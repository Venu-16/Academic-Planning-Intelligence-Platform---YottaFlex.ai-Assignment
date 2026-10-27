import pandas as pd

from academic_planner.planning import calculate_operational_capacity, calculate_unmet


def scenario(*, section_rows=None, assignment_rows=None, room_rows=None,
             faculty_rows=None, skill_rows=None, availability_rows=None):
    sections = section_rows or [
        {
            "section_id": "SEC-1",
            "course_id": "CRS-1",
            "term_id": "2027-SPRING",
            "room_id": "ROM-1",
            "day_of_week": 0,
            "slot_id": "S1",
            "planned_capacity": 30,
        }
    ]
    for row in sections:
        row.setdefault("term_start_date", "2027-01-01")
        row.setdefault("term_end_date", "2027-05-31")
    assignments = assignment_rows if assignment_rows is not None else [
        {
            "section_id": "SEC-1",
            "faculty_id": "FAC-1",
            "weekly_hours": 3,
            "status": "PROPOSED",
        }
    ]
    rooms = room_rows if room_rows is not None else [
        {"room_id": "ROM-1", "capacity": 40, "active": True}
    ]
    faculty = faculty_rows if faculty_rows is not None else [
        {
            "faculty_id": "FAC-1",
            "employment_status": "ACTIVE",
            "max_weekly_hours": 6,
        }
    ]
    skills = skill_rows if skill_rows is not None else [
        {
            "faculty_id": "FAC-1",
            "course_id": "CRS-1",
            "effective_from": "2027-01-01",
            "effective_to": "2027-05-31",
        }
    ]
    availability = availability_rows if availability_rows is not None else [
        {
            "faculty_id": "FAC-1",
            "term_id": "2027-SPRING",
            "day_of_week": 0,
            "slot_id": "S1",
            "available": True,
            "effective_from": "2027-01-01",
            "effective_to": "2027-05-31",
        }
    ]
    for row in skills:
        row.setdefault("effective_from", "2027-01-01")
        row.setdefault("effective_to", "2027-05-31")
    for row in availability:
        row.setdefault("term_id", "2027-SPRING")
        row.setdefault("effective_from", "2027-01-01")
        row.setdefault("effective_to", "2027-05-31")
    return (
        pd.DataFrame(sections),
        pd.DataFrame(assignments, columns=[
            "section_id", "faculty_id", "weekly_hours", "status"
        ]),
        pd.DataFrame(rooms),
        pd.DataFrame(faculty),
        pd.DataFrame(skills, columns=[
            "faculty_id", "course_id", "effective_from", "effective_to"
        ]),
        pd.DataFrame(availability, columns=[
            "faculty_id", "term_id", "day_of_week", "slot_id", "available",
            "effective_from", "effective_to",
        ]),
    )


def capacity_report(data, forecast=25):
    sections, assignments, rooms, faculty, skills, availability = data
    section_capacity = calculate_operational_capacity(
        sections, assignments, rooms, faculty, skills, availability
    )
    courses = pd.DataFrame([
        {"course_id": "CRS-1", "program_id": "PRG-1"},
        {"course_id": "CRS-2", "program_id": "PRG-1"},
    ])
    forecasts = pd.DataFrame([
        {"course_id": course_id, "forecast_enrollment": forecast}
        for course_id in sections.course_id.unique()
    ])
    return section_capacity, calculate_unmet(forecasts, section_capacity, courses)


def test_fully_staffed_room_feasible_section_counts_operational_capacity():
    section_capacity, unmet = capacity_report(scenario(), forecast=25)

    assert section_capacity.iloc[0].planned_capacity == 30
    assert section_capacity.iloc[0].operational_capacity == 30
    assert unmet.iloc[0].unmet == 0


def test_partially_staffed_course_counts_only_staffed_section_capacity():
    sections = [
        {
            "section_id": f"SEC-{i}",
            "course_id": "CRS-1",
            "term_id": "2027-SPRING",
            "room_id": f"ROM-{i}",
            "day_of_week": i - 1,
            "slot_id": "S1",
            "planned_capacity": 30,
        }
        for i in (1, 2)
    ]
    assignments = [
        {
            "section_id": "SEC-1",
            "faculty_id": "FAC-1",
            "weekly_hours": 3,
            "status": "PROPOSED",
        }
    ]
    rooms = [
        {"room_id": f"ROM-{i}", "capacity": 40, "active": True}
        for i in (1, 2)
    ]
    data = scenario(section_rows=sections, assignment_rows=assignments, room_rows=rooms)
    section_capacity, unmet = capacity_report(data, forecast=50)

    assert section_capacity.planned_capacity.sum() == 60
    assert section_capacity.operational_capacity.sum() == 30
    assert unmet.iloc[0].unmet == 20


def test_unstaffed_section_has_no_operational_capacity():
    data = scenario(assignment_rows=[])
    section_capacity, unmet = capacity_report(data, forecast=25)

    assert section_capacity.iloc[0].operational_capacity == 0
    assert "UNSTAFFED" in section_capacity.iloc[0].blocking_reasons
    assert unmet.iloc[0].unmet == 25


def test_rejected_assignment_does_not_count_as_staffing():
    assignments = [
        {
            "section_id": "SEC-1",
            "faculty_id": "FAC-1",
            "weekly_hours": 3,
            "status": "REJECTED",
        }
    ]
    section_capacity = calculate_operational_capacity(*scenario(assignment_rows=assignments))

    assert section_capacity.iloc[0].operational_capacity == 0
    assert "ASSIGNMENT_REJECTED" in section_capacity.iloc[0].blocking_reasons


def test_room_smaller_than_planned_capacity_is_not_counted():
    data = scenario(room_rows=[{"room_id": "ROM-1", "capacity": 20, "active": True}])
    section_capacity, unmet = capacity_report(data, forecast=25)

    assert section_capacity.iloc[0].operational_capacity == 0
    assert "ROOM_CAPACITY_TOO_LOW" in section_capacity.iloc[0].blocking_reasons
    assert unmet.iloc[0].unmet == 25


def test_faculty_timetable_conflict_blocks_both_overlapping_sections():
    sections = [
        {
            "section_id": f"SEC-{i}",
            "course_id": f"CRS-{i}",
            "term_id": "2027-SPRING",
            "room_id": f"ROM-{i}",
            "day_of_week": 0,
            "slot_id": "S1",
            "planned_capacity": 30,
        }
        for i in (1, 2)
    ]
    assignments = [
        {
            "section_id": f"SEC-{i}",
            "faculty_id": "FAC-1",
            "weekly_hours": 3,
            "status": "PROPOSED",
        }
        for i in (1, 2)
    ]
    rooms = [
        {"room_id": f"ROM-{i}", "capacity": 40, "active": True}
        for i in (1, 2)
    ]
    skills = [
        {"faculty_id": "FAC-1", "course_id": f"CRS-{i}"}
        for i in (1, 2)
    ]
    data = scenario(section_rows=sections, assignment_rows=assignments, room_rows=rooms, skill_rows=skills)
    section_capacity = calculate_operational_capacity(*data)

    assert section_capacity.operational_capacity.sum() == 0
    assert section_capacity.blocking_reasons.str.contains("FACULTY_TIMETABLE_CONFLICT").all()


def test_room_timetable_conflict_blocks_both_sections():
    sections = [
        {
            "section_id": f"SEC-{i}",
            "course_id": f"CRS-{i}",
            "term_id": "2027-SPRING",
            "room_id": "ROM-1",
            "day_of_week": 0,
            "slot_id": "S1",
            "planned_capacity": 30,
        }
        for i in (1, 2)
    ]
    assignments = [
        {
            "section_id": f"SEC-{i}",
            "faculty_id": f"FAC-{i}",
            "weekly_hours": 3,
            "status": "PROPOSED",
        }
        for i in (1, 2)
    ]
    faculty = [
        {
            "faculty_id": f"FAC-{i}",
            "employment_status": "ACTIVE",
            "max_weekly_hours": 6,
        }
        for i in (1, 2)
    ]
    skills = [
        {"faculty_id": f"FAC-{i}", "course_id": f"CRS-{i}"}
        for i in (1, 2)
    ]
    availability = [
        {
            "faculty_id": f"FAC-{i}",
            "day_of_week": 0,
            "slot_id": "S1",
            "available": True,
        }
        for i in (1, 2)
    ]
    data = scenario(
        section_rows=sections,
        assignment_rows=assignments,
        faculty_rows=faculty,
        skill_rows=skills,
        availability_rows=availability,
    )
    section_capacity = calculate_operational_capacity(*data)

    assert section_capacity.operational_capacity.sum() == 0
    assert section_capacity.blocking_reasons.str.contains("ROOM_TIMETABLE_CONFLICT").all()


def test_program_rollup_sums_course_demand_and_capacity():
    data = scenario(
        section_rows=[
            {
                "section_id": "SEC-1",
                "course_id": "CRS-1",
                "term_id": "2027-SPRING",
                "room_id": "ROM-1",
                "day_of_week": 0,
                "slot_id": "S1",
                "planned_capacity": 30,
            },
            {
                "section_id": "SEC-2",
                "course_id": "CRS-2",
                "term_id": "2027-SPRING",
                "room_id": "ROM-2",
                "day_of_week": 1,
                "slot_id": "S1",
                "planned_capacity": 30,
            },
        ],
        assignment_rows=[
            {
                "section_id": "SEC-1",
                "faculty_id": "FAC-1",
                "weekly_hours": 3,
                "status": "PROPOSED",
            }
        ],
        room_rows=[
            {"room_id": f"ROM-{i}", "capacity": 40, "active": True}
            for i in (1, 2)
        ],
    )
    _, unmet = capacity_report(data, forecast=25)

    program = unmet.groupby("program_id").agg(
        forecast_demand=("forecast_demand", "sum"),
        planned_capacity=("planned_capacity", "sum"),
        operational_capacity=("operational_capacity", "sum"),
        unmet=("unmet", "sum"),
    ).iloc[0]
    assert program.forecast_demand == 50
    assert program.planned_capacity == 60
    assert program.operational_capacity == 30
    assert program.unmet == 25
