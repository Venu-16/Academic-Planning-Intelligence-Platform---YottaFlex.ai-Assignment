import json, uuid
import shutil
from pathlib import Path
import pandas as pd
from sqlalchemy import MetaData, Table, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from .config import SEED,OUTPUT_DIR
from .database import get_engine,initialize_database
from .generator import generate_dataset,export_dataset
from .validation import (
    validate_frames,
    validate_assignment_outputs,
    validate_section_outputs,
)
from .forecasting import forecast_demand
from .planning import (
    propose_sections,
    calculate_operational_capacity,
    calculate_unmet,
    summarize_capacity_metrics,
)
from .optimizer import allocate_faculty
from .allocation_diagnostics import diagnose_unstaffed_sections


def _archive_run_outputs(output_dir,planning_run_id,frame_names):
    run_dir=output_dir/"runs"/planning_run_id
    run_dir.mkdir(parents=True,exist_ok=False)
    names={"ground_truth.csv","source_manifest.json"}
    for frame_name in frame_names:
        names.update({f"{frame_name}.csv",f"{frame_name}.json"})
    names.update({
        "forecasts.csv","sections.csv","workload_assignments.csv",
        "validation_report.json","section_validation.json",
        "planning_validation.json","allocation_diagnostics.json",
        "operational_capacity.csv","operational_capacity.json",
        "unmet_demand.csv","unmet_demand.json","evaluation_report.json",
    })
    for name in sorted(names):
        source=output_dir/name
        if source.exists():
            shutil.copy2(source,run_dir/name)
    return run_dir

def _upsert_source_frame(conn,table_name,frame):
    if frame.empty:
        return
    table=Table(table_name,MetaData(),autoload_with=conn)
    primary_keys=[column.name for column in table.primary_key.columns]
    if not primary_keys:
        raise ValueError(f"Cannot upsert {table_name}: table has no primary key")
    stmt=pg_insert(table)
    update_values={
        column.name:getattr(stmt.excluded,column.name)
        for column in table.columns
        if column.name not in primary_keys
    }
    clean=frame.astype(object).where(pd.notna(frame),None)
    for offset in range(0,len(clean),500):
        records=clean.iloc[offset:offset+500].to_dict("records")
        conn.execute(
            stmt.values(records).on_conflict_do_update(
                index_elements=primary_keys,
                set_=update_values,
            )
        )


def run_pipeline(output_dir=None,database_url=None,seed=SEED,persist=True):
    out=Path(output_dir or OUTPUT_DIR); out.mkdir(parents=True,exist_ok=True)
    runid="RUN-"+uuid.uuid4().hex[:12].upper()
    frames=generate_dataset(seed); export_dataset(frames,out,seed)
    issues=validate_frames(frames)
    (out/"validation_report.json").write_text(json.dumps({"passed":not issues,"issues":issues},indent=2))
    if issues: raise RuntimeError(f"Baseline validation failed: {issues}")
    forecasts,fm=forecast_demand(frames["historical_enrollments"])
    forecasts["planning_run_id"]=runid
    forecasts.to_csv(out/"forecasts.csv",index=False)
    sections=propose_sections(
        forecasts,frames["rooms"],academic_terms=frames["academic_terms"]
    )
    sections["planning_run_id"]=runid
    section_validation=validate_section_outputs(
        sections,frames["rooms"],frames["academic_terms"]
    )
    section_issues={
        issue["section_id"]:issue["issues"]
        for issue in section_validation["issues"]
    }
    sections["validation_status"]=sections.section_id.map(
        lambda section_id:"BLOCKED" if section_id in section_issues else "VALID"
    )
    sections["validation_issues"]=sections.section_id.map(
        lambda section_id:";".join(section_issues.get(section_id,[]))
    )
    sections.to_csv(out/"sections.csv",index=False)
    (out/"section_validation.json").write_text(
        json.dumps({"planning_run_id":runid,**section_validation},indent=2)
    )
    allocatable_sections=sections.loc[
        ~sections.section_id.isin(section_issues)
    ]
    assignments,sm=allocate_faculty(
        allocatable_sections,
        frames["faculty"],
        frames["faculty_skills"],
        frames["availability"],
    )
    assignments["planning_run_id"]=runid
    assignment_validation=validate_assignment_outputs(
        assignments,sections,frames["faculty"],frames["faculty_skills"],frames["availability"]
    )
    if "status" in assignments.columns and assignment_validation["invalid_assignment_count"]:
        invalid_assignment_ids={
            issue["assignment_id"] for issue in assignment_validation["issues"]
        }
        assignments.loc[
            assignments.workload_assignment_id.isin(invalid_assignment_ids),
            "status",
        ]="REJECTED"
    assignments.to_csv(out/"workload_assignments.csv",index=False)
    assignment_issues={}
    for section_id,reasons in section_issues.items():
        assignment_issues[section_id]=set(reasons)
    for issue in assignment_validation["issues"]:
        assignment_issues.setdefault(issue["section_id"],set()).update(issue["issues"])
    assignment_issues={section_id:sorted(rules) for section_id,rules in assignment_issues.items()}
    planning_validation={
        "planning_run_id":runid,
        "passed":assignment_validation["passed"] and section_validation["passed"],
        "invalid_section_count":section_validation["invalid_section_count"],
        "section_issues":section_validation["issues"],
        "invalid_assignment_count":assignment_validation["invalid_assignment_count"],
        "assignment_issues":assignment_validation["issues"],
    }
    (out/"planning_validation.json").write_text(json.dumps(planning_validation,indent=2))
    diagnostics=diagnose_unstaffed_sections(
        sections,frames["faculty"],frames["faculty_skills"],
        frames["availability"],assignments,sm["status"],runid,
    )
    (out/"allocation_diagnostics.json").write_text(json.dumps(diagnostics,indent=2))
    section_capacity=calculate_operational_capacity(sections,assignments,frames["rooms"],frames["faculty"],frames["faculty_skills"],frames["availability"],assignment_issues)
    section_capacity["planning_run_id"]=runid
    final_status=section_capacity.set_index("section_id").section_status.to_dict()
    sections["planning_status"]=sections.section_id.map(final_status)
    sections.to_csv(out/"sections.csv",index=False)
    section_capacity.to_csv(out/"operational_capacity.csv",index=False)
    section_capacity.to_json(
        out/"operational_capacity.json",orient="records",indent=2
    )
    unmet=calculate_unmet(forecasts,section_capacity,frames["courses"]); unmet.to_csv(out/"unmet_demand.csv",index=False)
    unmet["planning_run_id"]=runid
    unmet.to_csv(out/"unmet_demand.csv",index=False)
    unmet.to_json(out/"unmet_demand.json",orient="records",indent=2)
    by_program=unmet.groupby("program_id",dropna=False).agg(
        courses=("course_id","count"),
        forecast_demand=("forecast_demand","sum"),
        planned_capacity=("planned_capacity","sum"),
        operational_capacity=("operational_capacity","sum"),
        operationally_covered=("operationally_covered","sum"),
        accommodated=("accommodated","sum"),
        unmet=("unmet","sum"),
        courses_with_unmet=("unmet",lambda values:int((values.fillna(0)>0).sum())),
        courses_missing_forecast=("forecast_demand",lambda values:int(values.isna().sum())),
    ).reset_index().to_dict("records")
    capacity_metrics=summarize_capacity_metrics(
        sections,section_capacity,unmet,assignments,diagnostics,
        section_validation,assignment_validation,runid,
    )
    capacity_metrics["by_program"]=by_program
    capacity_metrics["definitions"]={
        "planned_capacity":"Sum of planned seats across all proposed sections, including blocked sections.",
        "operational_capacity":"Sum of section seats only where section_status is OPERATIONAL after all validations.",
        "operationally_covered_demand":"Per-course sum of min(forecast demand, operational capacity); this is coverage, not observed enrollment.",
        "unmet_demand":"Sum over courses of max(0, forecast demand - operational capacity); missing forecasts are excluded from known totals and counted explicitly.",
        "missing_capacity":"A course with no section capacity evidence is reported with zero proven operational capacity; missing forecast values remain unknown, not zero.",
        "blocked_sections_by_rule":"Unique section count for each rule code, excluding sections whose only blocker is UNSTAFFED. raw_violation_occurrences counts validation issue occurrences separately.",
    }
    operational_sections=capacity_metrics["operational_section_count"]
    metrics={"planning_run_id":runid,"run_artifacts_path":f"runs/{runid}","seed":seed,"dataset_rows":{k:len(v) for k,v in frames.items()},"forecast":fm,"solver":sm,"allocation":{"sections_proposed":capacity_metrics["proposed_section_count"],"sections_assigned":capacity_metrics["assigned_section_count"],"sections_staffed":operational_sections,"sections_operational":operational_sections,"staffing_rate":round(operational_sections/max(1,len(sections)),4)},"allocation_diagnostics":{"unstaffed_sections":diagnostics["unstaffed_sections"],"accounted_unstaffed_sections":diagnostics["accounted_unstaffed_sections"],"fully_accounted":diagnostics["fully_accounted"],"sections_without_eligible_faculty":diagnostics["sections_without_eligible_faculty"],"sections_without_eligible_faculty_ids":diagnostics["sections_without_eligible_faculty_ids"]},"planning_validation":planning_validation,"capacity":capacity_metrics,"unmet_demand":{"total_unmet":capacity_metrics["unmet_demand"],"courses_with_unmet":capacity_metrics["courses_with_unmet"],"missing_forecast_courses":capacity_metrics["forecast_missing_courses"]},"validation":{"passed":True,"issues":issues}}
    (out/"evaluation_report.json").write_text(json.dumps(metrics,indent=2))
    if persist:
        engine=get_engine(database_url); initialize_database(engine)
        with engine.begin() as conn:
            for name,df in frames.items():
                _upsert_source_frame(conn,name,df)
            conn.execute(text("INSERT INTO planning_runs(planning_run_id,seed,forecast_model,solver_status,notes) VALUES(:id,:seed,:model,:status,:notes)"),{"id":runid,"seed":seed,"model":"RandomForestRegressor","status":sm["status"],"notes":"Synthetic reproducible planning run"})
            for _,r in forecasts.iterrows():
                if pd.isna(r.forecast_enrollment):
                    continue
                conn.execute(text("INSERT INTO forecasts(forecast_id,planning_run_id,course_id,target_term,forecast_enrollment,model_name) VALUES(:id,:run,:course,:term,:demand,:model)"),{"id":f"{runid}-FCT-{r.course_id[-6:]}","run":runid,"course":r.course_id,"term":r.get("term_id","2027-SPRING"),"demand":int(r.forecast_enrollment),"model":"RandomForestRegressor"})
            facmap=assignments.set_index("section_id").faculty_id.to_dict() if len(assignments) else {}
            db_section_ids={section_id:f"{runid}-{section_id}" for section_id in sections.section_id}
            section_capacity_by_id=section_capacity.set_index("section_id").to_dict("index")
            invalid_section_ids=set(section_validation["invalid_section_ids"])
            for _,s in sections.iterrows():
                if s.section_id in invalid_section_ids or pd.isna(s.planned_capacity):
                    continue
                capacity=section_capacity_by_id[s.section_id]
                conn.execute(text("INSERT INTO sections(section_id,course_id,term_id,section_number,room_id,day_of_week,slot_id,planned_capacity,operational_capacity,forecast_demand,planning_run_id,status) VALUES(:id,:course,:term,:num,:room,:day,:slot,:planned,:operational,:demand,:run,:status)"),{"id":db_section_ids[s.section_id],"course":s.course_id,"term":s.term_id,"num":int(s.section_number),"room":s.room_id if pd.notna(s.room_id) else None,"day":int(s.day_of_week),"slot":s.slot_id,"planned":int(capacity["planned_capacity"]),"operational":int(capacity["operational_capacity"]),"demand":int(s.forecast_demand),"run":runid,"status":"ALLOCATED" if capacity["operational_capacity"]>0 else "PARTIAL"})
            for _,a in assignments.iterrows():
                conn.execute(text("INSERT INTO workload_assignments(workload_assignment_id,section_id,faculty_id,weekly_hours,status) VALUES(:id,:section,:faculty,:hours,:status)"),{"id":f"{runid}-{a.workload_assignment_id}","section":db_section_ids[a.section_id],"faculty":a.faculty_id,"hours":float(a.weekly_hours),"status":a.status})
            for _,u in unmet.iterrows():
                if pd.isna(u.forecast_demand) or pd.isna(u.unmet) or pd.isna(u.accommodated):
                    continue
                conn.execute(text("INSERT INTO unmet_demand(unmet_demand_id,planning_run_id,course_id,target_term,forecast_demand,planned_capacity,operational_capacity,accommodated,unmet,reason) VALUES(:id,:run,:course,:term,:demand,:planned,:operational,:accom,:unmet,:reason)"),{"id":f"{runid}-UMD-{u.course_id[-6:]}","run":runid,"course":u.course_id,"term":"2027-SPRING","demand":int(u.forecast_demand),"planned":int(u.planned_capacity),"operational":int(u.operational_capacity),"accom":int(u.accommodated),"unmet":int(u.unmet),"reason":u.reason})
            conn.execute(text("INSERT INTO decision_events(event_id,planning_run_id,entity_type,entity_id,event_type,actor,reason,payload) VALUES(:id,:run,:type,:entity,:event,:actor,:reason,CAST(:payload AS JSONB))"),{"id":f"EVT-{runid}","run":runid,"type":"planning_run","entity":runid,"event":"PLAN_GENERATED","actor":"pipeline","reason":"Forecast and allocation workflow completed","payload":json.dumps(metrics)})
            conn.execute(text("INSERT INTO decision_events(event_id,planning_run_id,entity_type,entity_id,event_type,actor,reason,payload) VALUES(:id,:run,:type,:entity,:event,:actor,:reason,CAST(:payload AS JSONB))"),{"id":f"EVT-{runid}-DIAGNOSTICS","run":runid,"type":"planning_run","entity":runid,"event":"ALLOCATION_DIAGNOSTICS","actor":"pipeline","reason":"Run-scoped faculty allocation diagnostics","payload":json.dumps(diagnostics)})
    _archive_run_outputs(out,runid,frames)
    return metrics
