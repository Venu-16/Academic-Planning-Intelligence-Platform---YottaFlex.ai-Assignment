# Academic Planning Intelligence Platform

A synthetic-data demonstrator for the YottaFlex.ai hiring assessment. It forecasts course demand, proposes sections, assigns qualified faculty, validates operational constraints, and reports deliverable seats and unmet demand. It is not a production student information system or scheduler.

## Workflow

The pipeline generates academic terms, programs, courses, prerequisite/completion records, faculty and skills, availability, rooms, student plans, registration interests, and historical enrollments. It validates inputs, evaluates and produces forecasts, proposes 40-seat sections, assigns faculty with OR-Tools CP-SAT, checks hard constraints, and exports forecasts, lifecycle states, capacity, unmet demand, diagnostics, and evaluation reports. PostgreSQL persistence and a Streamlit dashboard are optional.

For more detail, check the [`docs/`](docs/) folder:

- [Architecture](docs/architecture.md)
- [Business rules](docs/business_rules.md)
- [Design decisions](docs/DESIGN_DECISIONS.md)
- [AI usage and prompt log](docs/AI_USAGE_AND_PROMPT_LOG.md)

See the [acceptance audit](reports/acceptance_audit_20261029.md) for measured results and verification status.

## Requirements and setup

- Python 3.11 or newer
- PowerShell examples below assume Windows
- Docker Desktop/PostgreSQL 16 only for persistence or database integration tests

From the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

No database configuration is required for the CLI's `--no-db` commands. For persisted runs, set `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `DATABASE_URL` privately in the environment, then start the configured PostgreSQL service:

```powershell
docker compose up -d postgres
python -m academic_planner.cli --seed 20261022
```

The Compose service uses PostgreSQL 16 on host port 5433 and a persistent volume. Do not put credentials in the repository.
`DATABASE_URL` uses SQLAlchemy's psycopg URL form, for example `postgresql+psycopg://USER:PASSWORD@localhost:5433/academic_planner`; replace placeholders locally and do not commit the value.

## Run the profiles

Use separate output locations to keep the generated profiles distinct:

```powershell
# Starter: 10 programs, 100 courses, 50 faculty, 1,000 student plans
python -m academic_planner.cli --no-db --seed 20261022 --output-dir data/generated

# Target: 100 programs, 1,000 courses, 500 faculty, 20,000 student plans
python -m academic_planner.cli --no-db --seed 20261022 --scale target --output-dir data/generated/acceptance-target-20261029

# Target room-scarcity stress scenario
python -m academic_planner.cli --no-db --seed 20261022 --scale target --output-dir data/generated/room-scarcity-20261029 --room-scarcity
```

The CLI also supports `--programs`, `--courses`, `--faculty`, and `--student-plans` overrides. Outputs include `source_manifest.json`, `ground_truth.csv`, validation and diagnostic reports, `forecasts.csv`, `sections.csv`, `workload_assignments.csv`, `operational_capacity.csv`, `unmet_demand.csv`, `evaluation_report.json`, and an archive under `runs/<planning_run_id>/`.

## Dashboard

After generating the starter output, run:

```powershell
streamlit run app_dashboard.py
```

The dashboard reads `OUTPUT_DIR` (default `data/generated`) and provides a selector for available planning-run outputs. To point it elsewhere, set `OUTPUT_DIR` in the local environment before launch.

## Tests and checks

```powershell
python -m pytest -q
python -m compileall -q src tests
git diff --check
```

PostgreSQL integration tests are gated by `TEST_DATABASE_URL` and are skipped when it is absent. Start a dedicated disposable PostgreSQL test database separately and set `TEST_DATABASE_URL` locally to its `postgresql+psycopg` connection URL. Do not point it at the application's persistent Compose database, `DATABASE_URL`, or any production database. The tests create and drop a uniquely named temporary schema:

```powershell
# Set TEST_DATABASE_URL locally to the dedicated disposable PostgreSQL test database.
python -m pytest -q -rs tests/test_database_integration.py
```

For a disposable local test database with Docker Desktop, this PowerShell example uses a generated test-only password and a temporary filesystem (no named volume):

```powershell
$testName = "academic-planner-test-db"
$testUser = "planner_test"
$testPassword = [guid]::NewGuid().ToString("N")
$testDb = "academic_planner_test"
docker run -d --name $testName --tmpfs /var/lib/postgresql/data -e "POSTGRES_USER=$testUser" -e "POSTGRES_PASSWORD=$testPassword" -e "POSTGRES_DB=$testDb" -p 55432:5432 postgres:16
do {
    Start-Sleep -Seconds 2
    docker exec $testName pg_isready -U $testUser -d $testDb
    $ready = $LASTEXITCODE -eq 0
} until ($ready)
$env:TEST_DATABASE_URL = "postgresql+psycopg://$($testUser):$($testPassword)@localhost:55432/$($testDb)"
python -m pytest -q -rs tests/test_database_integration.py
$testExitCode = $LASTEXITCODE
docker rm -f $testName
Remove-Item Env:TEST_DATABASE_URL
Remove-Variable testName, testUser, testPassword, testDb
if ($testExitCode -ne 0) { throw "Database integration tests failed: $testExitCode" }
```

No database integration pass is implied by a no-database CLI run. This disposable setup should only target a local test container; it must not use production credentials or data.

## Latest measured outputs

The current checked-in CSV/JSON exports for seed `20261022` were independently counted; exact profile details and limitations are in the [acceptance audit](reports/acceptance_audit_20261029.md).

| Profile | Proposals | Operational | Unstaffed | Room-blocked | Operational seats | Forecast | Covered | Unmet |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Starter | 215 | 170 | 45 | 0 | 6,800 | 6,769 | 5,615 | 1,154 |
| Target baseline | 2,160 | 1,690 | 470 | 0 | 67,600 | 66,425 | 54,531 | 11,894 |
| Target scarcity | 2,160 | 348 | 52 | 1,760 | 13,920 | 66,425 | 10,930 | 55,495 |

These are output measurements, not hardcoded targets. Operational sections require validated rooms, schedules, and staffing. Unmet demand is calculated per course; spare seats in one course do not cancel another course's shortage. The synthetic data, limited historical series, abstract day/slot timetable, and optimizer results do not demonstrate production forecasting or institutional scheduling quality.
