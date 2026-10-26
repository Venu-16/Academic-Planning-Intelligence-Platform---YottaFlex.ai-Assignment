# Architecture

Generator -> relational validation -> historical enrollment model -> course forecasts -> section planner -> OR-Tools CP-SAT faculty allocation -> unmet-demand calculation -> evaluation exports -> Streamlit dashboard.

PostgreSQL stores source tables, forecasts, proposed sections, workload assignments, unmet demand, planning runs and JSONB decision events. `--no-db` runs the pipeline without PostgreSQL for a fast smoke test. The starter optimizer handles faculty skills, availability, workload and faculty slot conflicts; room/time assignment is not jointly optimized.
