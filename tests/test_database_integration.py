import json
import os
import uuid

import pandas as pd
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import make_url

from academic_planner.database import initialize_database, load_latest_capacity_metrics
import academic_planner.pipeline as pipeline_module
from academic_planner.pipeline import run_pipeline


@pytest.fixture
def isolated_postgres():
    test_database_url = os.getenv("TEST_DATABASE_URL")
    if not test_database_url:
        pytest.skip(
            "TEST_DATABASE_URL is not set; PostgreSQL integration tests require "
            "a dedicated disposable test database"
        )

    admin_engine = create_engine(test_database_url, connect_args={"connect_timeout": 5})
    with admin_engine.connect() as conn:
        conn.execute(text("SELECT 1"))

    schema = f"academic_planner_test_{uuid.uuid4().hex}"
    with admin_engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))

    scoped_url = make_url(test_database_url).update_query_dict(
        {"options": f"-csearch_path={schema}"}
    )
    engine = create_engine(scoped_url, connect_args={"connect_timeout": 5})
    try:
        yield engine, scoped_url.render_as_string(hide_password=False)
    finally:
        engine.dispose()
        with admin_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()


def test_fresh_database_pipeline_reruns_preserve_and_reconcile(
    isolated_postgres, tmp_path, monkeypatch
):
    engine, database_url = isolated_postgres
    initialize_database(engine)
    initialize_database(engine)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO programs(program_id,name,department) "
            "VALUES('PRESERVE-001','Existing program','Test')"
        ))

    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_metrics = run_pipeline(first_dir, database_url, seed=20261022, persist=True)
    forecast_function = pipeline_module.forecast_demand

    def distinctive_forecast(history, **kwargs):
        forecasts, report = forecast_function(history, **kwargs)
        forecasts = forecasts.copy()
        forecasts.loc[forecasts.index[0], "forecast_enrollment"] += 1
        return forecasts, report

    monkeypatch.setattr(pipeline_module, "forecast_demand", distinctive_forecast)
    second_metrics = run_pipeline(second_dir, database_url, seed=20261022, persist=True)
    first_transition_count = len(json.loads((first_dir / "decision_events.json").read_text()))
    second_transition_count = len(json.loads((second_dir / "decision_events.json").read_text()))
    persisted = load_latest_capacity_metrics(engine)

    with engine.connect() as conn:
        counts = conn.execute(text(
            "SELECT (SELECT COUNT(*) FROM planning_runs) AS runs,"
            "(SELECT COUNT(*) FROM decision_events) AS events,"
            "(SELECT COUNT(*) FROM forecasts) AS forecasts,"
            "(SELECT COUNT(*) FROM sections) AS sections,"
            "(SELECT COUNT(*) FROM workload_assignments) AS assignments,"
            "(SELECT COUNT(*) FROM unmet_demand) AS unmet_rows,"
            "(SELECT COUNT(*) FROM programs WHERE program_id='PRESERVE-001') AS preserved,"
            "(SELECT COUNT(*) FROM decision_events WHERE event_type='ALLOCATION_DIAGNOSTICS') AS diagnostic_events"
        )).mappings().one()
        constraints = conn.execute(text(
            "SELECT "
            "EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='sections'::regclass "
            "AND conname='sections_planning_run_id_fkey' AND contype='f' AND convalidated) AS section_run_fk,"
            "EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='sections'::regclass "
            "AND conname='sections_proposal_status_check' AND contype='c' AND convalidated) AS proposal_status_check,"
            "EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='forecasts'::regclass "
            "AND confrelid='planning_runs'::regclass AND contype='f' AND convalidated) AS forecast_run_fk,"
            "EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='unmet_demand'::regclass "
            "AND confrelid='planning_runs'::regclass AND contype='f' AND convalidated) AS unmet_run_fk,"
            "EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='decision_events'::regclass "
            "AND confrelid='planning_runs'::regclass AND contype='f' AND convalidated) AS event_run_fk,"
            "EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='workload_assignments'::regclass "
            "AND confrelid='sections'::regclass AND contype='f' AND convalidated) AS assignment_section_fk,"
            "EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='sections'::regclass "
            "AND conname='sections_term_id_fkey' AND contype='f') AS section_term_fk,"
            "EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='student_plans'::regclass "
            "AND conname='student_plans_term_id_fkey' AND contype='f') AS student_term_fk,"
            "EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='registration_interests'::regclass "
            "AND conname='registration_interests_term_id_fkey' AND contype='f') AS interest_term_fk,"
            "EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='availability'::regclass "
            "AND conname='availability_term_id_fkey' AND contype='f') AS availability_term_fk,"
            "EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='forecasts'::regclass "
            "AND conname='forecasts_target_term_fkey' AND contype='f') AS forecast_term_fk,"
            "EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='unmet_demand'::regclass "
            "AND conname='unmet_demand_target_term_fkey' AND contype='f') AS unmet_term_fk,"
            "to_regclass('sections_course_term_section_run_uq') IS NOT NULL AS section_run_unique,"
            "to_regclass('unmet_demand_run_course_term_uq') IS NOT NULL AS unmet_run_unique"
        )).mappings().one()
        run_rows = conn.execute(text(
            "SELECT r.planning_run_id,r.seed,r.notes,"
            "(SELECT COUNT(*) FROM forecasts f WHERE f.planning_run_id=r.planning_run_id) AS forecasts,"
            "(SELECT COUNT(*) FROM sections s WHERE s.planning_run_id=r.planning_run_id) AS sections,"
            "(SELECT COUNT(*) FROM sections s WHERE s.planning_run_id=r.planning_run_id "
            " AND s.operational_capacity>0) AS operational_sections,"
            "(SELECT COUNT(*) FROM sections s WHERE s.planning_run_id=r.planning_run_id "
            " AND s.proposal_status!='PROPOSED') AS invalid_proposal_states,"
            "(SELECT COALESCE(SUM(s.planned_capacity),0) FROM sections s "
            " WHERE s.planning_run_id=r.planning_run_id) AS planned_capacity,"
            "(SELECT COALESCE(SUM(s.operational_capacity),0) FROM sections s "
            " WHERE s.planning_run_id=r.planning_run_id) AS operational_capacity,"
            "(SELECT COUNT(*) FROM workload_assignments a JOIN sections s ON s.section_id=a.section_id "
            " WHERE s.planning_run_id=r.planning_run_id) AS assignments,"
            "(SELECT COUNT(*) FROM unmet_demand u WHERE u.planning_run_id=r.planning_run_id) AS unmet_rows,"
            "(SELECT COUNT(*) FROM decision_events e WHERE e.planning_run_id=r.planning_run_id) AS events "
            "FROM planning_runs r ORDER BY r.created_at,r.planning_run_id"
        )).mappings().all()
        persisted_events = conn.execute(text(
            "SELECT planning_run_id,event_type,entity_type,entity_id,event_time,payload "
            "FROM decision_events "
            "WHERE planning_run_id IN (:first,:second)"
        ),{"first":first_metrics["planning_run_id"],"second":second_metrics["planning_run_id"]}).mappings().all()

    assert counts["runs"] == 2
    assert counts["events"] == 4 + first_transition_count + second_transition_count
    assert counts["diagnostic_events"] == 2
    assert all(constraints.values())
    assert all(row["invalid_proposal_states"] == 0 for row in run_rows)
    assert counts["forecasts"] == (
        first_metrics["forecast"]["courses_forecasted"]
        + second_metrics["forecast"]["courses_forecasted"]
    )
    assert counts["sections"] == (
        first_metrics["allocation"]["sections_proposed"]
        + second_metrics["allocation"]["sections_proposed"]
    )
    assert counts["assignments"] == (
        len(pd.read_csv(first_dir / "workload_assignments.csv"))
        + len(pd.read_csv(second_dir / "workload_assignments.csv"))
    )
    assert counts["unmet_rows"] == (
        first_metrics["forecast"]["courses_forecasted"]
        + second_metrics["forecast"]["courses_forecasted"]
    )
    assert counts["preserved"] == 1
    assert first_metrics["planning_run_id"] != second_metrics["planning_run_id"]
    assert [row["seed"] for row in run_rows] == [20261022,20261022]
    assert all(
        json.loads(row["notes"])["scale"] == {
            "programs":10,"courses":100,"faculty":50,"student_plans":1000
        }
        for row in run_rows
    )
    assert len(run_rows) == 2
    first_forecasts = pd.read_csv(first_dir / "forecasts.csv")
    second_forecasts = pd.read_csv(second_dir / "forecasts.csv")
    assert not first_forecasts.forecast_enrollment.equals(
        second_forecasts.forecast_enrollment
    )
    assert [row["events"] for row in run_rows] == [
        2 + first_transition_count, 2 + second_transition_count
    ]
    assert [row["forecasts"] for row in run_rows] == [
        first_metrics["forecast"]["courses_forecasted"],
        second_metrics["forecast"]["courses_forecasted"],
    ]
    assert [row["sections"] for row in run_rows] == [
        first_metrics["allocation"]["sections_proposed"],
        second_metrics["allocation"]["sections_proposed"],
    ]
    assert [row["operational_sections"] for row in run_rows] == [
        first_metrics["capacity"]["operational_section_count"],
        second_metrics["capacity"]["operational_section_count"],
    ]
    assert [row["planned_capacity"] for row in run_rows] == [
        first_metrics["capacity"]["planned_capacity"],
        second_metrics["capacity"]["planned_capacity"],
    ]
    assert [row["operational_capacity"] for row in run_rows] == [
        first_metrics["capacity"]["operational_capacity"],
        second_metrics["capacity"]["operational_capacity"],
    ]
    assert [row["assignments"] for row in run_rows] == [
        len(pd.read_csv(first_dir / "workload_assignments.csv")),
        len(pd.read_csv(second_dir / "workload_assignments.csv")),
    ]
    assert [row["unmet_rows"] for row in run_rows] == [
        first_metrics["forecast"]["courses_forecasted"],
        second_metrics["forecast"]["courses_forecasted"],
    ]
    assert persisted["capacity"]["planned_capacity"] == second_metrics["capacity"]["planned_capacity"]
    assert persisted["capacity"]["operational_capacity"] == second_metrics["capacity"]["operational_capacity"]
    assert persisted["capacity"]["unmet"] == second_metrics["capacity"]["unmet_demand"]
    assert persisted["sections"]["planned_capacity"] == second_metrics["capacity"]["planned_capacity"]
    assert persisted["sections"]["operational_capacity"] == second_metrics["capacity"]["operational_capacity"]
    assert sum(row["unmet"] for row in persisted["by_program"]) == persisted["capacity"]["unmet"]
    assert persisted["planning_run_id"] == second_metrics["planning_run_id"]

    for run_dir, metrics in (
        (first_dir, first_metrics),
        (second_dir, second_metrics),
    ):
        run_id = metrics["planning_run_id"]
        csv_courses = pd.read_csv(run_dir / "unmet_demand.csv").sort_values("course_id")
        with engine.connect() as conn:
            db_courses = pd.DataFrame([
                dict(row) for row in conn.execute(text(
                "SELECT u.course_id,c.program_id,u.forecast_demand,u.planned_capacity,"
                "u.operational_capacity,u.accommodated,u.unmet "
                "FROM unmet_demand u JOIN courses c ON c.course_id=u.course_id "
                "WHERE u.planning_run_id=:run ORDER BY u.course_id"
                ),{"run":run_id}).mappings().all()
            ]).sort_values("course_id")
            db_assignments = pd.DataFrame([
                dict(row) for row in conn.execute(text(
                    "SELECT s.section_id AS run_section_id,a.faculty_id,a.weekly_hours,a.status "
                    "FROM workload_assignments a JOIN sections s ON s.section_id=a.section_id "
                    "WHERE s.planning_run_id=:run ORDER BY s.section_id"
                ),{"run":run_id}).mappings().all()
            ])
        pd.testing.assert_frame_equal(
            csv_courses[
                [
                    "course_id", "program_id", "forecast_demand", "planned_capacity",
                    "operational_capacity", "accommodated", "unmet",
                ]
            ].reset_index(drop=True),
            db_courses[
                [
                    "course_id", "program_id", "forecast_demand", "planned_capacity",
                    "operational_capacity", "accommodated", "unmet",
                ]
            ].reset_index(drop=True),
            check_dtype=False,
        )

        capacity = pd.read_csv(run_dir / "operational_capacity.csv")
        section_output = pd.read_csv(run_dir / "sections.csv")
        assignments_output = pd.read_csv(run_dir / "workload_assignments.csv")
        planning_validation = json.loads(
            (run_dir / "planning_validation.json").read_text()
        )
        diagnostics = json.loads(
            (run_dir / "allocation_diagnostics.json").read_text()
        )
        expected_assignment_statuses = assignments_output.status.value_counts().sort_index()
        actual_assignment_statuses = db_assignments.status.value_counts().sort_index()
        pd.testing.assert_series_equal(
            actual_assignment_statuses,expected_assignment_statuses,
            check_names=False,check_dtype=False,
        )
        assert len(section_output) == metrics["capacity"]["proposed_section_count"]
        assert len(capacity) == len(section_output)
        assert int(capacity.operational.sum()) == metrics["capacity"]["operational_section_count"]
        assert int(capacity.planned_capacity.sum()) == metrics["capacity"]["planned_capacity"]
        assert int(capacity.operational_capacity.sum()) == metrics["capacity"]["operational_capacity"]
        assert diagnostics["planning_run_id"] == run_id
        assert planning_validation["planning_run_id"] == run_id
        assert diagnostics["fully_accounted"] == metrics["allocation_diagnostics"]["fully_accounted"]
        assert section_output.planning_run_id.eq(run_id).all()
        assert section_output.status.tolist() == capacity.set_index(
            "section_id"
        ).loc[section_output.section_id, "section_status"].tolist()
        assert not assignments_output.loc[
            assignments_output.status == "APPROVED", "section_id"
        ].map(
            capacity.set_index("section_id").operational.to_dict()
        ).eq(False).any()
        expected_assignment_rows = assignments_output[
            ["section_id","faculty_id","weekly_hours","status"]
        ].sort_values("section_id").reset_index(drop=True)
        db_assignments["section_id"] = db_assignments.run_section_id.str.removeprefix(
            f"{run_id}-"
        )
        actual_assignment_rows = db_assignments[
            ["section_id","faculty_id","weekly_hours","status"]
        ].sort_values("section_id").reset_index(drop=True)
        pd.testing.assert_frame_equal(
            actual_assignment_rows,expected_assignment_rows,
            check_dtype=False,
        )

    events_by_run = {
        row["planning_run_id"]:row for row in persisted_events
        if row["event_type"]=="ALLOCATION_DIAGNOSTICS"
    }
    plan_events_by_run = {
        row["planning_run_id"]:row for row in persisted_events
        if row["event_type"]=="PLAN_GENERATED"
    }
    assert set(events_by_run) == {
        first_metrics["planning_run_id"],second_metrics["planning_run_id"]
    }
    for run_dir, metrics in (
        (first_dir, first_metrics),
        (second_dir, second_metrics),
    ):
        plan_payload=plan_events_by_run[metrics["planning_run_id"]]["payload"]
        if isinstance(plan_payload,str):
            plan_payload=json.loads(plan_payload)
        exported_validation=json.loads(
            (run_dir/"planning_validation.json").read_text()
        )
        assert plan_payload["planning_validation"] == exported_validation
        assert plan_payload["capacity"]["blocked_sections_by_rule"] == (
            metrics["capacity"]["blocked_sections_by_rule"]
        )
        saved = events_by_run[metrics["planning_run_id"]]["payload"]
        if isinstance(saved,str):
            saved=json.loads(saved)
        file_diagnostics=json.loads(
            (run_dir/"allocation_diagnostics.json").read_text()
        )
        assert saved == file_diagnostics

    transition_events = [
        row for row in persisted_events
        if row["event_type"] == "STATE_TRANSITION"
    ]
    assert len(transition_events) == first_transition_count + second_transition_count
    assert all(
        event["event_time"] is not None
        and event["payload"]["previous_state"] == "PROPOSED"
        and event["payload"]["new_state"]
        and event["payload"]["reason_code"]
        for event in transition_events
    )

    program_columns = [
        "program_id","courses","forecast_demand","planned_capacity",
        "operational_capacity","operationally_covered","accommodated",
        "unmet","courses_with_unmet","courses_missing_forecast",
    ]
    csv_programs = pd.DataFrame(second_metrics["capacity"]["by_program"])
    csv_programs = csv_programs[program_columns].sort_values("program_id")
    db_programs = pd.DataFrame(persisted["by_program"])
    db_programs = db_programs[program_columns].sort_values("program_id")
    pd.testing.assert_frame_equal(csv_programs.reset_index(drop=True), db_programs.reset_index(drop=True), check_dtype=False)


def test_existing_schema_migration_preserves_rows(isolated_postgres):
    engine, _ = isolated_postgres
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE programs(program_id TEXT PRIMARY KEY,name TEXT UNIQUE NOT NULL,department TEXT NOT NULL)"
        ))
        conn.execute(text(
            "CREATE TABLE courses(course_id TEXT PRIMARY KEY,program_id TEXT NOT NULL REFERENCES programs(program_id),"
            "code TEXT UNIQUE NOT NULL,title TEXT NOT NULL,credits INT NOT NULL,course_level INT NOT NULL,is_elective BOOLEAN NOT NULL)"
        ))
        conn.execute(text(
            "CREATE TABLE rooms(room_id TEXT PRIMARY KEY,building TEXT NOT NULL,room_type TEXT NOT NULL,"
            "capacity INT NOT NULL,active BOOLEAN NOT NULL)"
        ))
        conn.execute(text(
            "CREATE TABLE planning_runs(planning_run_id TEXT PRIMARY KEY,seed BIGINT NOT NULL,"
            "created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,forecast_model TEXT NOT NULL,"
            "solver_status TEXT NOT NULL,notes TEXT NOT NULL DEFAULT '')"
        ))
        conn.execute(text(
            "CREATE TABLE sections(section_id TEXT PRIMARY KEY,course_id TEXT NOT NULL REFERENCES courses(course_id),"
            "term_id TEXT NOT NULL,section_number INT NOT NULL,room_id TEXT REFERENCES rooms(room_id),"
            "day_of_week INT NOT NULL,slot_id TEXT NOT NULL,planned_capacity INT NOT NULL,"
            "forecast_demand INT NOT NULL,status TEXT NOT NULL,"
            "UNIQUE(course_id,term_id,section_number))"
        ))
        conn.execute(text(
            "CREATE TABLE unmet_demand(unmet_demand_id TEXT PRIMARY KEY,"
            "planning_run_id TEXT NOT NULL REFERENCES planning_runs(planning_run_id),"
            "course_id TEXT NOT NULL REFERENCES courses(course_id),target_term TEXT NOT NULL,"
            "forecast_demand INT NOT NULL,accommodated INT NOT NULL,unmet INT NOT NULL,reason TEXT NOT NULL,"
            "CHECK(unmet=forecast_demand-accommodated))"
        ))
        conn.execute(text("INSERT INTO programs VALUES('P-OLD','Old program','Test')"))
        conn.execute(text("INSERT INTO courses VALUES('C-OLD','P-OLD','OLD','Old course',3,1,FALSE)"))
        conn.execute(text("INSERT INTO rooms VALUES('R-OLD','Old building','LECTURE',40,TRUE)"))
        conn.execute(text(
            "INSERT INTO planning_runs(planning_run_id,seed,forecast_model,solver_status) "
            "VALUES('RUN-OLD',1,'old-model','OPTIMAL')"
        ))
        conn.execute(text(
            "INSERT INTO sections(section_id,course_id,term_id,section_number,room_id,day_of_week,"
            "slot_id,planned_capacity,forecast_demand,status) "
            "VALUES('SEC-OLD','C-OLD','2027-SPRING',1,'R-OLD',0,'S1',40,35,'ALLOCATED')"
        ))
        conn.execute(text(
            "INSERT INTO unmet_demand VALUES('UMD-OLD','RUN-OLD','C-OLD','2027-SPRING',35,35,0,'NONE')"
        ))

    initialize_database(engine)
    initialize_database(engine)

    with engine.connect() as conn:
        old_section = conn.execute(text(
            "SELECT section_id,planned_capacity,operational_capacity,planning_run_id,"
            "proposal_status "
            "FROM sections WHERE section_id='SEC-OLD'"
        )).mappings().one()
        old_unmet = conn.execute(text(
            "SELECT unmet_demand_id,planned_capacity,operational_capacity,unmet "
            "FROM unmet_demand WHERE unmet_demand_id='UMD-OLD'"
        )).mappings().one()
        run_fk_exists = conn.execute(text(
            "SELECT EXISTS(SELECT 1 FROM pg_constraint WHERE "
            "conname='sections_planning_run_id_fkey' AND conrelid='sections'::regclass)"
        )).scalar_one()
        run_index_exists = conn.execute(text(
            "SELECT to_regclass('sections_course_term_section_run_uq') IS NOT NULL"
        )).scalar_one()
        old_unique_exists = conn.execute(text(
            "SELECT EXISTS(SELECT 1 FROM pg_constraint WHERE "
            "conname='sections_course_id_term_id_section_number_key' "
            "AND conrelid='sections'::regclass)"
        )).scalar_one()
        unmet_index_exists = conn.execute(text(
            "SELECT to_regclass('unmet_demand_run_course_term_uq') IS NOT NULL"
        )).scalar_one()
        academic_terms_exists = conn.execute(text(
            "SELECT to_regclass('academic_terms') IS NOT NULL"
        )).scalar_one()
        completion_table_exists = conn.execute(text(
            "SELECT to_regclass('student_course_completions') IS NOT NULL"
        )).scalar_one()
        proposal_check_exists = conn.execute(text(
            "SELECT EXISTS(SELECT 1 FROM pg_constraint WHERE "
            "conname='sections_proposal_status_check' AND conrelid='sections'::regclass)"
        )).scalar_one()

    assert old_section["section_id"] == "SEC-OLD"
    assert old_section["planned_capacity"] == 40
    assert old_section["operational_capacity"] == 0
    assert old_section["planning_run_id"] is None
    assert old_section["proposal_status"] == "PROPOSED"
    assert old_unmet["unmet_demand_id"] == "UMD-OLD"
    assert old_unmet["planned_capacity"] == 0
    assert old_unmet["operational_capacity"] == 0
    assert old_unmet["unmet"] == 0
    assert run_fk_exists
    assert run_index_exists
    assert not old_unique_exists
    assert unmet_index_exists
    assert academic_terms_exists
    assert completion_table_exists
    assert proposal_check_exists


def test_unknown_term_references_are_rejected_after_migration(isolated_postgres):
    engine, _ = isolated_postgres
    initialize_database(engine)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO faculty(faculty_id,name,department,max_weekly_hours,employment_status) "
            "VALUES('FAC-TERM','Faculty','Test',6,'ACTIVE')"
        ))

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO availability(availability_id,faculty_id,term_id,day_of_week,"
                "slot_id,available,effective_from) VALUES("
                "'AVL-INVALID-TERM','FAC-TERM','2099-FALL',0,'S1',TRUE,'2099-01-01')"
            ))
