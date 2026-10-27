import json

import pandas as pd

from academic_planner.pipeline import run_pipeline
from academic_planner.planning import (
    calculate_operational_capacity,
    calculate_unmet,
    summarize_capacity_metrics,
)


TERM_ID = "2027-SPRING"
TERM_START = "2027-01-01"
TERM_END = "2027-05-31"


def section(section_id,course_id,capacity=30,room_id="ROM-1",day=0,slot="S1"):
    return {
        "section_id":section_id,
        "course_id":course_id,
        "term_id":TERM_ID,
        "term_start_date":TERM_START,
        "term_end_date":TERM_END,
        "validation_status":"VALID",
        "validation_issues":"",
        "room_id":room_id,
        "day_of_week":day,
        "slot_id":slot,
        "planned_capacity":capacity,
    }


def common_frames():
    return (
        pd.DataFrame([{
            "room_id":"ROM-1","capacity":40,"active":True
        }]),
        pd.DataFrame([{
            "faculty_id":"FAC-1","employment_status":"ACTIVE",
            "max_weekly_hours":6
        }]),
        pd.DataFrame([{
            "faculty_id":"FAC-1","course_id":"CRS-1",
            "effective_from":TERM_START,"effective_to":TERM_END
        }]),
        pd.DataFrame([{
            "faculty_id":"FAC-1","term_id":TERM_ID,"day_of_week":0,
            "slot_id":"S1","available":True,
            "effective_from":TERM_START,"effective_to":TERM_END
        }]),
    )


def assignment(section_id,status="PROPOSED"):
    return {
        "workload_assignment_id":f"WLA-{section_id}",
        "section_id":section_id,
        "faculty_id":"FAC-1",
        "weekly_hours":3,
        "status":status,
    }


def section_capacity(sections,assignments,issues=None):
    rooms,faculty,skills,availability=common_frames()
    return calculate_operational_capacity(
        pd.DataFrame(sections),
        pd.DataFrame(assignments,columns=[
            "workload_assignment_id","section_id","faculty_id","weekly_hours","status"
        ]),
        rooms,faculty,skills,availability,issues,
    )


def test_proposed_and_blocked_sections_do_not_count_as_operational():
    proposed=section("SEC-P","CRS-1")
    blocked=section("SEC-B","CRS-1",day=1)
    blocked["validation_status"]="BLOCKED"
    blocked["validation_issues"]="ROOM_CAPACITY_TOO_LOW;INVALID_TIMETABLE"
    result=section_capacity(
        [proposed,blocked],[assignment("SEC-P"),assignment("SEC-B")],
    )

    assert result.loc[result.section_id=="SEC-P","section_status"].iloc[0]=="OPERATIONAL"
    assert result.loc[result.section_id=="SEC-B","section_status"].iloc[0]=="BLOCKED"
    assert result.loc[result.section_id=="SEC-B","operational_capacity"].iloc[0]==0

    unstaffed=section_capacity([section("SEC-U","CRS-1")],[])
    assert unstaffed.iloc[0].section_status=="UNSTAFFED"
    assert unstaffed.iloc[0].operational_capacity==0


def test_rejected_assignment_is_not_counted_as_assigned_or_operational():
    sections=[section("SEC-1","CRS-1")]
    capacity=section_capacity(sections,[assignment("SEC-1","REJECTED")])
    empty_unmet=pd.DataFrame(columns=[
        "forecast_demand","unmet","operationally_covered"
    ])
    summary=summarize_capacity_metrics(
        pd.DataFrame(sections),capacity,empty_unmet,pd.DataFrame([assignment("SEC-1","REJECTED")]),
        {"sections":[]},{"issues":[]},{"issues":[]},"RUN-TEST",
    )

    assert summary["assigned_section_count"]==0
    assert summary["operational_section_count"]==0


def test_multiple_violations_count_once_per_blocked_section():
    section_rows=[section("SEC-1","CRS-1")]
    issues={"SEC-1":["MISSING_SKILL","ROOM_CAPACITY_TOO_LOW"]}
    capacity=section_capacity(
        section_rows,[assignment("SEC-1")],issues
    )
    empty_unmet=pd.DataFrame(columns=[
        "forecast_demand","unmet","operationally_covered"
    ])
    summary=summarize_capacity_metrics(
        pd.DataFrame(section_rows),capacity,empty_unmet,pd.DataFrame([assignment("SEC-1")]),
        {"sections":[]},
        {"issues":[{"section_id":"SEC-1","issues":["ROOM_CAPACITY_TOO_LOW"]}]},
        {"issues":[{"section_id":"SEC-1","issues":["MISSING_SKILL"]}]},
        "RUN-TEST",
    )

    assert summary["blocked_section_count"]==1
    assert summary["blocked_sections_by_rule"]["MISSING_SKILL"]==1
    assert summary["blocked_sections_by_rule"]["ROOM_CAPACITY_TOO_LOW"]==1
    assert summary["raw_violation_occurrences"]=={
        "ROOM_CAPACITY_TOO_LOW":1,"MISSING_SKILL":1
    }


def test_course_unmet_demand_does_not_net_surplus_from_other_courses():
    forecasts=pd.DataFrame([
        {"course_id":"CRS-1","forecast_enrollment":100},
        {"course_id":"CRS-2","forecast_enrollment":0},
    ])
    capacities=pd.DataFrame([
        {"course_id":"CRS-1","planned_capacity":50,"operational_capacity":50,"blocking_reasons":""},
        {"course_id":"CRS-2","planned_capacity":100,"operational_capacity":100,"blocking_reasons":""},
    ])
    courses=pd.DataFrame([
        {"course_id":"CRS-1","program_id":"PRG-1"},
        {"course_id":"CRS-2","program_id":"PRG-1"},
    ])

    result=calculate_unmet(forecasts,capacities,courses).set_index("course_id")

    assert result.loc["CRS-1","unmet"]==50
    assert result.loc["CRS-2","unmet"]==0
    assert result.unmet.sum()==50
    assert result.loc["CRS-1","operationally_covered"]==50


def test_zero_demand_and_zero_capacity_reconcile_without_negative_unmet():
    forecasts=pd.DataFrame([
        {"course_id":"CRS-1","forecast_enrollment":0},
        {"course_id":"CRS-2","forecast_enrollment":25},
    ])
    capacities=pd.DataFrame([
        {"course_id":"CRS-1","planned_capacity":0,"operational_capacity":0,"blocking_reasons":""},
        {"course_id":"CRS-2","planned_capacity":0,"operational_capacity":0,"blocking_reasons":"UNSTAFFED"},
    ])
    courses=pd.DataFrame([
        {"course_id":"CRS-1","program_id":"PRG-1"},
        {"course_id":"CRS-2","program_id":"PRG-1"},
    ])

    result=calculate_unmet(forecasts,capacities,courses).set_index("course_id")

    assert result.loc["CRS-1","unmet"]==0
    assert result.loc["CRS-2","unmet"]==25
    assert (result.unmet.dropna()>=0).all()


def test_missing_forecast_is_unknown_and_missing_capacity_fails_closed():
    forecasts=pd.DataFrame([
        {"course_id":"CRS-1","forecast_enrollment":20},
        {"course_id":"CRS-2","forecast_enrollment":None},
    ])
    capacities=pd.DataFrame([
        {"course_id":"CRS-1","planned_capacity":None,"operational_capacity":None,"blocking_reasons":""},
    ])
    courses=pd.DataFrame([
        {"course_id":"CRS-1","program_id":"PRG-1"},
        {"course_id":"CRS-2","program_id":"PRG-1"},
        {"course_id":"CRS-3","program_id":"PRG-2"},
    ])

    result=calculate_unmet(forecasts,capacities,courses).set_index("course_id")

    assert result.loc["CRS-1","capacity_status"]=="CAPACITY_MISSING"
    assert result.loc["CRS-1","operational_capacity"]==0
    assert result.loc["CRS-1","unmet"]==20
    assert result.loc["CRS-2","forecast_status"]=="MISSING"
    assert pd.isna(result.loc["CRS-2","unmet"])
    assert result.loc["CRS-3","reason"]=="FORECAST_MISSING"
    assert pd.isna(result.loc["CRS-3","forecast_demand"])
    assert result.loc["CRS-3","operational_capacity"]==0


def test_pipeline_section_and_capacity_reports_reconcile_and_are_archived(tmp_path):
    metrics=run_pipeline(output_dir=tmp_path,persist=False)
    run_id=metrics["planning_run_id"]
    sections=pd.read_csv(tmp_path/"sections.csv")
    capacity=pd.read_csv(tmp_path/"operational_capacity.csv")
    unmet=pd.read_csv(tmp_path/"unmet_demand.csv")
    diagnostics=json.loads((tmp_path/"allocation_diagnostics.json").read_text())

    assert sections.planning_run_id.eq(run_id).all()
    assert capacity.planning_run_id.eq(run_id).all()
    assert unmet.planning_run_id.eq(run_id).all()
    assert diagnostics["planning_run_id"]==run_id
    assert len(sections)==metrics["capacity"]["proposed_section_count"]
    assert int(capacity.operational.sum())==metrics["capacity"]["operational_section_count"]
    assert int(capacity.planned_capacity.sum())==metrics["capacity"]["planned_capacity"]
    assert int(capacity.operational_capacity.sum())==metrics["capacity"]["operational_capacity"]
    assert int(unmet.unmet.sum())==metrics["capacity"]["unmet_demand"]
    assert int((unmet.unmet>0).sum())==metrics["capacity"]["courses_with_unmet"]
    assert metrics["allocation"]["sections_staffed"]==metrics["capacity"]["operational_section_count"]
    program_metrics=pd.DataFrame(metrics["capacity"]["by_program"]).set_index("program_id")
    program_unmet=unmet.groupby("program_id").unmet.sum()
    pd.testing.assert_series_equal(
        program_metrics.unmet.sort_index(),
        program_unmet.sort_index(),
        check_names=False,
        check_dtype=False,
    )

    archive=tmp_path/"runs"/run_id
    assert (archive/"evaluation_report.json").exists()
    archived_capacity=pd.read_csv(archive/"operational_capacity.csv")
    pd.testing.assert_frame_equal(capacity,archived_capacity)


def test_summary_metrics_are_repeatable_for_identical_final_ledger():
    sections=pd.DataFrame([section("SEC-1","CRS-1")])
    capacities=section_capacity(
        sections.to_dict("records"),[assignment("SEC-1")]
    )
    unmet=calculate_unmet(
        pd.DataFrame([{"course_id":"CRS-1","forecast_enrollment":20}]),
        capacities,
        pd.DataFrame([{"course_id":"CRS-1","program_id":"PRG-1"}]),
    )
    diagnostics={"sections":[]}
    validation={"issues":[]}
    assignments=pd.DataFrame([assignment("SEC-1")])
    first=summarize_capacity_metrics(
        sections,capacities,unmet,assignments,diagnostics,validation,validation,"RUN-TEST"
    )
    second=summarize_capacity_metrics(
        sections,capacities,unmet,assignments,diagnostics,validation,validation,"RUN-TEST"
    )

    assert first==second
