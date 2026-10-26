from pathlib import Path
import json
import pandas as pd
import streamlit as st
import plotly.express as px
st.set_page_config(page_title="Academic Planner",page_icon="🎓",layout="wide")
st.title("🎓 Academic Demand Forecasting & Faculty Allocation")
st.caption("Synthetic reproducible demo · Seed 20261022")
p=Path("data/generated")
if not (p/"evaluation_report.json").exists():
    st.warning("Run the pipeline first: `python -m academic_planner.cli --no-db`")
    st.stop()
m=json.loads((p/"evaluation_report.json").read_text()); f=pd.read_csv(p/"forecasts.csv"); s=pd.read_csv(p/"sections.csv"); a=pd.read_csv(p/"workload_assignments.csv"); u=pd.read_csv(p/"unmet_demand.csv")
c1,c2,c3,c4=st.columns(4); c1.metric("Courses forecasted",len(f)); c2.metric("Sections proposed",len(s)); c3.metric("Sections staffed",m["allocation"]["sections_staffed"]); c4.metric("Unmet demand",m["unmet_demand"]["total_unmet"])
left,right=st.columns(2)
left.plotly_chart(px.histogram(f,x="forecast_enrollment",nbins=20,title="Forecast distribution"),use_container_width=True)
right.json(m["forecast"])
st.subheader("Course forecasts"); st.dataframe(f.sort_values("forecast_enrollment",ascending=False),use_container_width=True)
st.subheader("Sections"); st.dataframe(s,use_container_width=True)
st.subheader("Faculty assignments"); st.dataframe(a,use_container_width=True)
st.subheader("Unmet demand"); st.dataframe(u[u.unmet>0],use_container_width=True)
st.subheader("Solver and validation"); st.json({"solver":m["solver"],"validation":m["validation"]})
for n in ["source_manifest.json","ground_truth.csv","validation_report.json","evaluation_report.json"]:
    if (p/n).exists(): st.download_button("Download "+n,(p/n).read_bytes(),file_name=n)
