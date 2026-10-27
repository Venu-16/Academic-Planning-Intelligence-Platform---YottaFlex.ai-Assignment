# Architecture

Generator -> relational validation -> historical enrollment model -> chronological holdout evaluation -> course forecasts -> section planner -> OR-Tools CP-SAT faculty allocation -> section/assignment validation -> operational-capacity and unmet-demand reconciliation -> run-scoped exports and audit events -> Streamlit dashboard.

Forecast MAE and RMSE are measured against the final historical term held out chronologically; the same observations are scored with a last-observation baseline. Report both metrics and do not assume the Random Forest is better.

PostgreSQL stores source tables, forecasts, proposed sections, workload assignments, planned and operational capacity, unmet demand, planning runs and JSONB decision events. Source rows are upserted; run outputs use run-scoped identifiers and are retained so reruns do not erase prior results or audit events. Schema initialization adds capacity/run columns to existing tables without deleting their rows. The dashboard can query the latest persisted course, program and overall capacity metrics. Set `TEST_DATABASE_URL` to a dedicated disposable PostgreSQL database to run integration tests; tests create and remove only a uniquely named temporary schema.

`--no-db` runs the pipeline without PostgreSQL for a fast smoke test. The starter optimizer handles faculty skills, availability, workload and faculty slot conflicts; room/time assignment is not jointly optimized.
