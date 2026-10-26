import json, uuid
from pathlib import Path
import pandas as pd
from sqlalchemy import text
from .config import SEED,OUTPUT_DIR
from .database import get_engine,initialize_database
from .generator import generate_dataset,export_dataset
from .validation import validate_frames
from .forecasting import forecast_demand
from .planning import propose_sections,calculate_unmet
from .optimizer import allocate_faculty

def run_pipeline(output_dir=None,database_url=None,seed=SEED,persist=True):
    out=Path(output_dir or OUTPUT_DIR); out.mkdir(parents=True,exist_ok=True)
    frames=generate_dataset(seed); export_dataset(frames,out,seed)
    issues=validate_frames(frames)
    (out/"validation_report.json").write_text(json.dumps({"passed":not issues,"issues":issues},indent=2))
    if issues: raise RuntimeError(f"Baseline validation failed: {issues}")
    forecasts,fm=forecast_demand(frames["historical_enrollments"]); forecasts.to_csv(out/"forecasts.csv",index=False)
    sections=propose_sections(forecasts,frames["rooms"]); sections.to_csv(out/"sections.csv",index=False)
    assignments,sm=allocate_faculty(sections,frames["faculty"],frames["faculty_skills"],frames["availability"]); assignments.to_csv(out/"workload_assignments.csv",index=False)
    unmet=calculate_unmet(forecasts,sections); unmet.to_csv(out/"unmet_demand.csv",index=False)
    metrics={"seed":seed,"dataset_rows":{k:len(v) for k,v in frames.items()},"forecast":fm,"solver":sm,"allocation":{"sections_proposed":len(sections),"sections_staffed":sm["assigned"],"staffing_rate":round(sm["assigned"]/max(1,len(sections)),4)},"unmet_demand":{"total_unmet":int(unmet.unmet.sum()),"courses_with_unmet":int((unmet.unmet>0).sum())},"validation":{"passed":True,"issues":issues}}
    (out/"evaluation_report.json").write_text(json.dumps(metrics,indent=2))
    if persist:
        engine=get_engine(database_url); initialize_database(engine)
        # Single-user demo refreshes source and result tables; audit rows are recorded per run.
        with engine.begin() as conn:
            for t in ["unmet_demand","forecasts","workload_assignments","sections","registration_interests","student_plans","availability","faculty_skills","historical_enrollments","prerequisites","courses","faculty","rooms","programs"]:
                conn.execute(text(f"DELETE FROM {t}"))
            for name,df in frames.items():
                if len(df): df.to_sql(name,conn,if_exists="append",index=False,method="multi",chunksize=500)
            runid="RUN-"+uuid.uuid4().hex[:12].upper()
            conn.execute(text("INSERT INTO planning_runs(planning_run_id,seed,forecast_model,solver_status,notes) VALUES(:id,:seed,:model,:status,:notes)"),{"id":runid,"seed":seed,"model":"RandomForestRegressor","status":sm["status"],"notes":"Synthetic reproducible planning run"})
            for _,r in forecasts.iterrows():
                conn.execute(text("INSERT INTO forecasts(forecast_id,planning_run_id,course_id,target_term,forecast_enrollment,model_name) VALUES(:id,:run,:course,:term,:demand,:model)"),{"id":"FCT-"+r.course_id[-6:],"run":runid,"course":r.course_id,"term":"2027-SPRING","demand":int(r.forecast_enrollment),"model":"RandomForestRegressor"})
            facmap=assignments.set_index("section_id").faculty_id.to_dict() if len(assignments) else {}
            for _,s in sections.iterrows():
                conn.execute(text("INSERT INTO sections(section_id,course_id,term_id,section_number,room_id,day_of_week,slot_id,planned_capacity,forecast_demand,status) VALUES(:id,:course,:term,:num,:room,:day,:slot,:cap,:demand,:status)"),{"id":s.section_id,"course":s.course_id,"term":s.term_id,"num":int(s.section_number),"room":s.room_id if pd.notna(s.room_id) else None,"day":int(s.day_of_week),"slot":s.slot_id,"cap":int(s.planned_capacity),"demand":int(s.forecast_demand),"status":"ALLOCATED" if s.section_id in facmap and pd.notna(s.room_id) else "PARTIAL"})
            for _,a in assignments.iterrows():
                conn.execute(text("INSERT INTO workload_assignments(workload_assignment_id,section_id,faculty_id,weekly_hours,status) VALUES(:id,:section,:faculty,:hours,:status)"),{"id":a.workload_assignment_id,"section":a.section_id,"faculty":a.faculty_id,"hours":float(a.weekly_hours),"status":a.status})
            for _,u in unmet.iterrows():
                conn.execute(text("INSERT INTO unmet_demand(unmet_demand_id,planning_run_id,course_id,target_term,forecast_demand,accommodated,unmet,reason) VALUES(:id,:run,:course,:term,:demand,:accom,:unmet,:reason)"),{"id":"UMD-"+u.course_id[-6:],"run":runid,"course":u.course_id,"term":"2027-SPRING","demand":int(u.forecast_demand),"accom":int(u.accommodated),"unmet":int(u.unmet),"reason":u.reason})
            conn.execute(text("INSERT INTO decision_events(event_id,planning_run_id,entity_type,entity_id,event_type,actor,reason,payload) VALUES(:id,:run,:type,:entity,:event,:actor,:reason,CAST(:payload AS JSONB))"),{"id":"EVT-000001","run":runid,"type":"planning_run","entity":runid,"event":"PLAN_GENERATED","actor":"pipeline","reason":"Forecast and allocation workflow completed","payload":json.dumps(metrics)})
    return metrics
