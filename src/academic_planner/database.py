from pathlib import Path
from sqlalchemy import create_engine, text
from .config import DATABASE_URL
def get_engine(url=None):
    database_url=url or DATABASE_URL
    if not database_url:
        raise RuntimeError("Set DATABASE_URL before using PostgreSQL persistence")
    return create_engine(database_url, future=True, pool_pre_ping=True)
def initialize_database(engine):
    sql=Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    with engine.begin() as conn:
        for stmt in sql.split(";"):
            if stmt.strip(): conn.execute(text(stmt))
        conn.execute(text(
            "ALTER TABLE sections DROP CONSTRAINT IF EXISTS sections_status_check"
        ))
        has_lifecycle_check=conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM pg_constraint "
            "WHERE conname='sections_lifecycle_status_check' "
            "AND conrelid='sections'::regclass)"
        )).scalar_one()
        if not has_lifecycle_check:
            conn.execute(text(
                "ALTER TABLE sections ADD CONSTRAINT sections_lifecycle_status_check "
                "CHECK(status IN ('PROPOSED','OPERATIONAL','BLOCKED','UNSTAFFED',"
                "'REJECTED','ALLOCATED','PARTIAL','CANCELLED'))"
            ))
        has_proposal_check=conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM pg_constraint "
            "WHERE conname='sections_proposal_status_check' "
            "AND conrelid='sections'::regclass)"
        )).scalar_one()
        if not has_proposal_check:
            conn.execute(text(
                "ALTER TABLE sections ADD CONSTRAINT sections_proposal_status_check "
                "CHECK(proposal_status='PROPOSED')"
            ))
        has_run_fk=conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM pg_constraint "
            "WHERE conname='sections_planning_run_id_fkey' "
            "AND conrelid='sections'::regclass)"
        )).scalar_one()
        if not has_run_fk:
            conn.execute(text(
                "ALTER TABLE sections ADD CONSTRAINT sections_planning_run_id_fkey "
                "FOREIGN KEY (planning_run_id) REFERENCES planning_runs(planning_run_id)"
            ))
        term_foreign_keys={
            ("student_plans","term_id"):"student_plans_term_id_fkey",
            ("registration_interests","term_id"):"registration_interests_term_id_fkey",
            ("availability","term_id"):"availability_term_id_fkey",
            ("sections","term_id"):"sections_term_id_fkey",
            ("forecasts","target_term"):"forecasts_target_term_fkey",
            ("unmet_demand","target_term"):"unmet_demand_target_term_fkey",
        }
        for (table,column),constraint in term_foreign_keys.items():
            exists=conn.execute(text(
                "SELECT EXISTS (SELECT 1 FROM pg_constraint "
                "WHERE conname=:constraint AND conrelid=CAST(:table AS regclass))"
            ),{"constraint":constraint,"table":table}).scalar_one()
            if not exists:
                conn.execute(text(
                    f"ALTER TABLE {table} ADD CONSTRAINT {constraint} "
                    f"FOREIGN KEY ({column}) REFERENCES academic_terms(term_id) NOT VALID"
                ))

def load_latest_capacity_metrics(engine):
    with engine.connect() as conn:
        latest=conn.execute(text(
            "SELECT planning_run_id FROM planning_runs "
            "ORDER BY created_at DESC, planning_run_id DESC LIMIT 1"
        )).scalar_one_or_none()
        if latest is None:
            return None

        course_rows=conn.execute(text(
            "SELECT u.course_id,c.program_id,u.forecast_demand,u.planned_capacity,"
            "u.operational_capacity,u.accommodated AS operationally_covered,"
            "u.accommodated,u.unmet,u.reason "
            "FROM unmet_demand u JOIN courses c ON c.course_id=u.course_id "
            "WHERE u.planning_run_id=:run ORDER BY c.program_id,u.course_id"
        ),{"run":latest}).mappings().all()
        program_rows=conn.execute(text(
            "SELECT c.program_id,COUNT(*) AS courses,SUM(u.forecast_demand) AS forecast_demand,"
            "SUM(u.planned_capacity) AS planned_capacity,"
            "SUM(u.operational_capacity) AS operational_capacity,"
            "SUM(u.accommodated) AS accommodated,SUM(u.unmet) AS unmet "
            "FROM unmet_demand u JOIN courses c ON c.course_id=u.course_id "
            "WHERE u.planning_run_id=:run GROUP BY c.program_id ORDER BY c.program_id"
        ),{"run":latest}).mappings().all()
        overall=conn.execute(text(
            "SELECT COALESCE(SUM(forecast_demand),0) AS forecast_demand,"
            "COALESCE(SUM(planned_capacity),0) AS planned_capacity,"
            "COALESCE(SUM(operational_capacity),0) AS operational_capacity,"
            "COALESCE(SUM(accommodated),0) AS accommodated,"
            "COALESCE(SUM(unmet),0) AS unmet,"
            "COUNT(*) FILTER (WHERE unmet>0) AS courses_with_unmet "
            "FROM unmet_demand WHERE planning_run_id=:run"
        ),{"run":latest}).mappings().one()
        sections=conn.execute(text(
            "SELECT COUNT(*) AS section_count,"
            "COUNT(*) FILTER (WHERE operational_capacity>0) AS operational_sections,"
            "COALESCE(SUM(planned_capacity),0) AS planned_capacity,"
            "COALESCE(SUM(operational_capacity),0) AS operational_capacity "
            "FROM sections WHERE planning_run_id=:run"
        ),{"run":latest}).mappings().one()
        run_event=conn.execute(text(
            "SELECT payload FROM decision_events "
            "WHERE planning_run_id=:run AND event_type='PLAN_GENERATED' "
            "ORDER BY event_time DESC,event_id DESC LIMIT 1"
        ),{"run":latest}).mappings().first()

    run_metrics=run_event["payload"] if run_event else {}
    if isinstance(run_metrics,str):
        import json
        run_metrics=json.loads(run_metrics)
    capacity_metrics=run_metrics.get("capacity",{})
    if capacity_metrics:
        overall=dict(overall)
        overall.update({
            "forecast_demand":capacity_metrics["forecast_demand"],
            "planned_capacity":capacity_metrics["planned_capacity"],
            "operational_capacity":capacity_metrics["operational_capacity"],
            "accommodated":capacity_metrics["operationally_covered_demand"],
            "unmet":capacity_metrics["unmet_demand"],
            "courses_with_unmet":capacity_metrics["courses_with_unmet"],
            "forecast_missing_courses":capacity_metrics["forecast_missing_courses"],
        })
    if run_metrics:
        sections=dict(sections)
        sections.update({
            "section_count":capacity_metrics.get(
                "proposed_section_count",sections["section_count"]
            ),
            "proposed_sections":capacity_metrics.get("proposed_section_count"),
            "assigned_sections":capacity_metrics.get("assigned_section_count"),
            "operational_sections":capacity_metrics.get(
                "operational_section_count",sections["operational_sections"]
            ),
            "blocked_sections":capacity_metrics.get("blocked_section_count"),
            "sections_without_eligible_faculty":capacity_metrics.get(
                "sections_without_eligible_faculty"
            ),
            "planned_capacity":capacity_metrics.get(
                "planned_capacity",sections["planned_capacity"]
            ),
            "operational_capacity":capacity_metrics.get(
                "operational_capacity",sections["operational_capacity"]
            ),
        })
        if capacity_metrics.get("by_program"):
            program_rows=capacity_metrics["by_program"]
    return {
        "planning_run_id":latest,
        "capacity":dict(overall),
        "sections":dict(sections),
        "definitions":capacity_metrics.get("definitions",{}),
        "blocked_sections_by_rule":capacity_metrics.get(
            "blocked_sections_by_rule",{}
        ),
        "courses":[dict(row) for row in course_rows],
        "by_program":[dict(row) for row in program_rows],
    }
