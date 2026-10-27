from pathlib import Path
import json
import pandas as pd
import streamlit as st
import plotly.express as px
from academic_planner.config import OUTPUT_DIR
from academic_planner.database import get_engine,load_latest_capacity_metrics
st.set_page_config(page_title="Academic Planner",page_icon="🎓",layout="wide")
st.title("🎓 Academic Demand Forecasting & Faculty Allocation")
st.caption("Synthetic reproducible demo · Seed 20261022")
configured_output=Path(OUTPUT_DIR)
output_dirs=[configured_output]
reports_dir=Path("reports")
if reports_dir.exists():
    output_dirs.extend(
        directory.parent
        for directory in reports_dir.glob("*/evaluation_report.json")
    )
output_dirs=list(dict.fromkeys(directory.resolve() for directory in output_dirs))
available_dirs=[
    directory for directory in output_dirs
    if (directory/"evaluation_report.json").is_file()
]
if not available_dirs:
    st.warning("Run the pipeline first: `python -m academic_planner.cli --no-db`")
    st.stop()
selected_output=st.sidebar.selectbox(
    "Planning run output",
    available_dirs,
    format_func=lambda directory:directory.name,
)
p=Path(selected_output)
m=json.loads((p/"evaluation_report.json").read_text()); f=pd.read_csv(p/"forecasts.csv"); s=pd.read_csv(p/"sections.csv"); a=pd.read_csv(p/"workload_assignments.csv"); u=pd.read_csv(p/"unmet_demand.csv")
st.caption(f"Planning run: {m['planning_run_id']} · Output: {p}")
c1,c2,c3,c4=st.columns(4); c1.metric("Courses forecasted",len(f)); c2.metric("Sections proposed",len(s)); c3.metric("Sections staffed",m["allocation"]["sections_staffed"]); c4.metric("Unmet demand",m["unmet_demand"]["total_unmet"])
capacity=m.get("capacity",{})
if capacity:
    st.subheader("Planned and operational capacity")
    c1,c2,c3=st.columns(3)
    c1.metric("Planned seats",capacity["planned_capacity"])
    c2.metric("Operational deliverable seats",capacity["operational_capacity"])
    c3.metric("Forecast demand",capacity["forecast_demand"])
    c1,c2,c3=st.columns(3)
    c1.metric("Operationally covered demand",capacity["operationally_covered_demand"])
    c2.metric("Courses with unmet demand",capacity["courses_with_unmet"])
    c3.metric("Blocked sections",capacity["blocked_section_count"])
    st.caption(
        f"Proposed sections: {capacity['proposed_section_count']} · "
        f"Operational sections: {capacity['operational_section_count']} · "
        f"Sections without an eligible faculty member: "
        f"{capacity['sections_without_eligible_faculty']}"
    )
    if capacity.get("blocked_sections_by_rule"):
        st.dataframe(
            pd.DataFrame([
                {"rule":rule,"unique_blocked_sections":count}
                for rule,count in capacity["blocked_sections_by_rule"].items()
            ]),
            use_container_width=True,
        )
left,right=st.columns(2)
left.plotly_chart(px.histogram(f,x="forecast_enrollment",nbins=20,title="Forecast distribution"),use_container_width=True)
right.json(m["forecast"])
st.subheader("Course forecasts"); st.dataframe(f.sort_values("forecast_enrollment",ascending=False),use_container_width=True)
st.subheader("Sections"); st.dataframe(s,use_container_width=True)
if (p/"operational_capacity.csv").exists():
    operational_sections=pd.read_csv(p/"operational_capacity.csv")
    st.subheader("Section operational-capacity checks")
    st.dataframe(operational_sections,use_container_width=True)
st.subheader("Faculty assignments"); st.dataframe(a,use_container_width=True)
st.subheader("Course-level capacity and unmet demand"); st.dataframe(u,use_container_width=True)
if capacity.get("by_program"):
    st.subheader("Program-level capacity and unmet demand")
    st.dataframe(pd.DataFrame(capacity["by_program"]),use_container_width=True)
st.subheader("Solver and validation"); st.json({"solver":m["solver"],"allocation_diagnostics":m.get("allocation_diagnostics"),"validation":m["validation"]})
if st.checkbox("Load latest persisted database metrics"):
    persisted=load_latest_capacity_metrics(get_engine())
    if persisted is None:
        st.info("The database has no persisted planning runs.")
    else:
        st.subheader("Persisted database results")
        st.caption(f"Planning run: {persisted['planning_run_id']}")
        st.json({"capacity":persisted["capacity"],"sections":persisted["sections"]})
        st.dataframe(
            pd.DataFrame([
                {"rule":rule,"unique_blocked_sections":count}
                for rule,count in persisted.get("blocked_sections_by_rule",{}).items()
            ]),
            use_container_width=True,
        )
        st.dataframe(pd.DataFrame(persisted["courses"]),use_container_width=True)
        st.dataframe(pd.DataFrame(persisted["by_program"]),use_container_width=True)
if (p/"allocation_diagnostics.json").exists():
    diagnostic_report=json.loads((p/"allocation_diagnostics.json").read_text())
    st.subheader("Unstaffed section diagnostics")
    diagnostic_columns=["section_id","course_id","day_of_week","slot_id","room_id","candidate_blocking_reasons","feasible_faculty_ids","accounted","diagnosis"]
    st.dataframe(pd.DataFrame(diagnostic_report["sections"])[diagnostic_columns],use_container_width=True)
for n in ["source_manifest.json","ground_truth.csv","validation_report.json","section_validation.json","planning_validation.json","evaluation_report.json","allocation_diagnostics.json","operational_capacity.csv","operational_capacity.json","unmet_demand.csv","unmet_demand.json"]:
    if (p/n).exists(): st.download_button("Download "+n,(p/n).read_bytes(),file_name=n)
