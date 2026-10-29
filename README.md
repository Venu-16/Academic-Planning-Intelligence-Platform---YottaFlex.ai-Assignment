# Academic Demand Forecasting & Faculty Allocation System

A reproducible synthetic-data prototype for forecasting course demand, proposing sections, assigning eligible faculty, validating operational constraints, and reporting deliverable capacity and unmet demand.

## Business problem and solution

Academic planners need to compare expected course demand with the seats that can actually be delivered. This project demonstrates an end-to-end planning workflow: it forecasts enrollment from historical course data, proposes room-sized sections, allocates qualified and available faculty within workload limits, validates assignments and schedules, then reports planned capacity separately from operational capacity and course-level unmet demand.

The supplied data is synthetic. The system is a demonstrator, not a production student information or scheduling system.

## Architecture and data flow

1. `generator.py` creates reproducible programs, courses, terms, faculty, skills, availability, rooms, student plans, registration interests, and historical enrollments.
2. `validation.py` checks source relationships, registration eligibility, proposed sections, and faculty assignments.
3. `forecasting.py` evaluates a Random Forest against a last-observation baseline using a chronological held-out term, then forecasts future enrollment.
4. `planning.py` proposes sections and calculates final section status, operational capacity, course-level unmet demand, and run-level metrics.
5. `optimizer.py` uses OR-Tools CP-SAT to allocate qualified, available faculty within workload and same-slot conflict constraints. The pipeline validates assignments again before counting operational seats.
6. `allocation_diagnostics.py` explains unstaffed sections and candidate faculty blockers.
7. `pipeline.py` exports CSV/JSON artifacts, a metrics report, and a run-specific archive. With persistence enabled, it initializes PostgreSQL, upserts source records, writes run-scoped results, and stores planning and diagnostic audit events.
8. `app_dashboard.py` displays generated reports and can read latest persisted metrics.

See [docs/architecture.md](docs/architecture.md), [docs/business_rules.md](docs/business_rules.md), and [docs/data_dictionary.md](docs/data_dictionary.md) for additional detail.

## Technology

- Python 3.11+
- Pandas, NumPy, scikit-learn
- OR-Tools CP-SAT
- PostgreSQL 16, SQLAlchemy, psycopg
- Streamlit, Plotly
- pytest

## Setup (Windows PowerShell)

From the project directory:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

PostgreSQL is optional for a no-database run. For persistence, set `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `DATABASE_URL` in your local environment before starting the Compose service. `DATABASE_URL` has no embedded default credentials; persistence fails explicitly if it is missing. Do not commit `.env` or credentials.

```powershell
# Set POSTGRES_USER, POSTGRES_PASSWORD, and DATABASE_URL locally before this command.
docker compose up -d postgres
python -m academic_planner.cli --seed 20261022
```

## Generate synthetic data and run the pipeline

Run the end-to-end pipeline without PostgreSQL:

```powershell
python -m academic_planner.cli --no-db --seed 20261022
```

The default output location is `data/generated`; a run refreshes these generated source and report files. Inspect existing outputs before running if they contain local changes you need to keep. To preserve the current output set, choose a new directory:

```powershell
python -m academic_planner.cli --no-db --seed 20261022 --output-dir data/demo-20261022
```

The pipeline generates source CSV/JSON files, `ground_truth.csv`, `source_manifest.json`, forecast and section outputs, workload assignments, validation reports, allocation diagnostics, operational capacity, unmet demand, and `evaluation_report.json`. Each invocation also archives its artifacts under `runs/<planning_run_id>/`.

The backward-compatible default is the starter scale (10 programs, 100 courses, 50 faculty, and 1,000 student plans). Run the target configuration through the complete pipeline with:

```powershell
python -m academic_planner.cli --no-db --seed 20261022 --scale target --output-dir reports/target-run
```

`--scale target` selects 100 programs, 1,000 courses, 500 faculty, and 20,000 student plans. Override individual dimensions with `--programs`, `--courses`, `--faculty`, or `--student-plans`; positive integers are required. The source manifest records the requested scale, seed, row counts, and CSV checksums. The evaluation report records elapsed time and Python allocation peak (it excludes native-library allocations).

The seed controls synthetic source data and the forecasting estimator. CP-SAT allocation uses multiple workers, so do not assume allocations are identical between separate runs. Use the same run's exported data and metrics for reconciliation.

The current audited starter run (seed `20261022`, no database, default starter profile) produces 215 proposed sections, 170 operational sections, 45 unstaffed sections, 8,600 planned seats, 6,800 operational seats, 6,769 forecast demand, 5,615 covered demand, and 1,154 unmet demand. The normal target baseline (seed `20261022`, `--scale target`) produces 2,160 proposed sections, 1,690 operational sections, 470 unstaffed sections, 86,400 planned seats, 67,600 operational seats, 66,425 forecast demand, 54,531 covered demand, and 11,894 unmet demand. These are measured from the current generated exports and are not hardcoded target expectations.

The constrained room-scarcity scenario remains explicitly available through `--room-scarcity`; it reproduces the low-inventory stress case intentionally: 2,160 proposals, 348 operational sections, 1,760 room-blocked sections, 52 unstaffed sections, 13,920 operational seats, and 55,495 unmet demand. This mode is meant for validation of scarcity behavior and is not the normal default institution model.

Each generated proposal retains `proposal_status=PROPOSED`; final `status` distinguishes `OPERATIONAL`, `UNSTAFFED`, `BLOCKED`, and `REJECTED`. Non-operational sections provide zero seats, and room-day-slot conflicts remain disallowed.

## Run the dashboard

After generating the default reports:

```powershell
streamlit run app_dashboard.py
```

The dashboard reads the configured `OUTPUT_DIR` (default `data/generated`) and can select any report directory under `reports/` that contains an `evaluation_report.json`. It displays the selected run identifier, final section and assignment states, forecasts, diagnostics, planned and operational seats, covered demand, unmet demand, and validation information.

## Testing

Run the complete suite:

```powershell
python -m pytest -q -rs
python -m compileall -q src tests
git diff --check
```

Focused checks include:

```powershell
python -m pytest tests/test_ground_truth.py -q
python -m pytest tests/test_faculty_eligibility.py tests/test_room_timetable.py -q
python -m pytest tests/test_capacity_reconciliation.py tests/test_allocation_diagnostics.py -q
```

PostgreSQL integration tests skip when `TEST_DATABASE_URL` is not set. When configured, it must point to a dedicated disposable test database; tests create and drop only a uniquely named temporary schema in that database. They never use `DATABASE_URL` as a fallback. For example, with an independently launched disposable PostgreSQL service:

```powershell
# Set TEST_DATABASE_URL locally to the dedicated disposable test database URL.
python -m pytest tests/test_database_integration.py -q
Remove-Item Env:TEST_DATABASE_URL
```

Use temporary test infrastructure and credentials that are not production credentials. Do not point `TEST_DATABASE_URL` at the application database. The test suite does not manage or delete database volumes.

For an isolated local run using Docker Desktop and the checked-in `postgres:16` image, open a fresh PowerShell session in the project directory:

```powershell
$env:POSTGRES_USER = "planner_test"
$env:POSTGRES_PASSWORD = [guid]::NewGuid().ToString("N")
$env:POSTGRES_DB = "academic_planner_test"
docker run -d --name academic-planner-test-db --tmpfs /var/lib/postgresql/data -e "POSTGRES_USER=$env:POSTGRES_USER" -e "POSTGRES_PASSWORD=$env:POSTGRES_PASSWORD" -e "POSTGRES_DB=$env:POSTGRES_DB" -p 55432:5432 postgres:16
do {
    Start-Sleep -Seconds 2
    docker exec academic-planner-test-db pg_isready -U $env:POSTGRES_USER -d $env:POSTGRES_DB
} until ($LASTEXITCODE -eq 0)
$env:TEST_DATABASE_URL = "postgresql+psycopg://$($env:POSTGRES_USER):$($env:POSTGRES_PASSWORD)@localhost:55432/$($env:POSTGRES_DB)"
python -m pytest -q -rs tests/test_database_integration.py
$testExitCode = $LASTEXITCODE
docker rm -f academic-planner-test-db
Remove-Item Env:TEST_DATABASE_URL, Env:POSTGRES_PASSWORD, Env:POSTGRES_USER, Env:POSTGRES_DB
if ($testExitCode -ne 0) { throw "Database integration tests failed: $testExitCode" }
```

The container uses a temporary filesystem (no named volume), a dedicated test-only database, and a generated test-only password. Do not use this sample against a production database.

## Demo walkthrough

1. Run `python -m academic_planner.cli --no-db --seed 20261022`. This refreshes the generated artifacts read by the dashboard.
2. Inspect `evaluation_report.json` and compare the reported model and baseline MAE/RMSE. A lower error is better; the model is not assumed to beat the baseline.
3. Open `sections.csv` and `operational_capacity.csv`. A valid allocation has an assignment and `section_status=OPERATIONAL`, with operational seats equal to validated planned seats. For the acceptance run, an example is any row whose `section_status` is `OPERATIONAL`.
4. Inspect `section_validation.json` and `operational_capacity.csv` for proposals blocked by real generated constraints; the target-scale acceptance run, for example, has blocked sections because room assignments are unavailable. To reproduce a faculty-skill rejection in an isolated synthetic test, run `python -m pytest "tests/test_ground_truth.py::test_pipeline_blocks_invalid_assignment_from_operational_capacity[FACULTY_OUTSIDE_SKILL-FACULTY_OUTSIDE_SKILL]" -q`. That fixture removes the assigned faculty member's course skill; the pipeline reports the rule, rejects the assignment, and gives that section zero operational capacity. The test mutation is not added to baseline data.
5. Compare `unmet_demand.csv` with the run summary. Unmet demand is calculated separately for each course, so excess seats in another course cannot offset a shortage.
6. Launch the dashboard with `streamlit run app_dashboard.py`. Use the sidebar's **Planning run output** selector to choose the default output or a completed run under `reports/`.

Lifecycle values are finalized in the exports: sections are `OPERATIONAL`, `UNSTAFFED`, `BLOCKED`, or `REJECTED`; accepted assignments are `APPROVED` and invalid/rejected assignments are `REJECTED`. A proposal is not operational until validation and staffing complete. Run-scoped state transitions are exported to `decision_events.json` and persisted when database mode is enabled.

The exact counts and errors depend on the chosen seed and optimizer allocation. Consult the current run's files rather than relying on example numbers.

## Current limitations and future improvements

- All planning data and the 2027-SPRING term dates are synthetic.
- Forecast evaluation uses a limited historical series and one chronological held-out term; it is not evidence of production forecasting performance.
- The last-observation baseline may perform as well as or better than the Random Forest.
- Room selection is not jointly optimized with faculty/time slots. Schedule conflicts are checked for identical term/day/slot IDs; real clock-time overlaps cannot be verified without slot-time metadata.
- Course-required room types/facilities and reliable student cohort schedules are not represented.
- Source records are upserted for a single-user demonstration; historical planning outputs and audit events are run-scoped. The application is not designed for multi-user concurrency or production data governance.
- Further work should use institution-approved data, stronger temporal backtesting, authoritative calendars and slot times, and a joint room/faculty timetable optimizer before operational deployment.
