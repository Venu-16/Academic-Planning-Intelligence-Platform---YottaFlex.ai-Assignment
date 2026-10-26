<<<<<<< HEAD
# Academic-Planning-Intelligence-Platform---YottaFlex.ai-Assignment
=======
# Academic Demand Forecasting & Faculty Allocation System

A runnable synthetic-data project for a 48-hour hiring challenge. It includes deterministic data generation, PostgreSQL schema, forecasting, section planning, OR-Tools faculty assignment, validation, anomaly ground truth, audit events, evaluation metrics, CSV/JSON exports and a Streamlit dashboard.

## Stack
Python 3.11+, PostgreSQL 16, SQLAlchemy/psycopg, Pandas, NumPy, scikit-learn, OR-Tools CP-SAT, Streamlit, Plotly, pytest.

## Quick start (Windows PowerShell)
```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
docker compose up -d postgres
python -m academic_planner.cli
streamlit run app_dashboard.py
```
No-Postgres smoke test:
```powershell
python -m academic_planner.cli --no-db
pytest
```
macOS/Linux: use `python3.11 -m venv .venv`, `source .venv/bin/activate`, and `cp .env.example .env`.

## Outputs
Source CSV/JSON tables, ground_truth.csv, source_manifest.json, validation_report.json, forecasts.csv, sections.csv, workload_assignments.csv, unmet_demand.csv, evaluation_report.json.

## Scale and reproducibility
10 programs, 100 courses, 50 faculty, 1,000 student plans, seed 20261022. Generator uses a configurable `Scale` object and stable ID formats. Regenerate twice with the same seed and compare manifest checksums.

## Important limitations
This is a synthetic-data prototype, not a production university information system. Forecast performance must be assessed against the baseline. Room selection is not jointly optimized with faculty/time slots. Ground truth documents five anomaly fixtures; use separate negative-test fixtures rather than corrupting baseline tables. Database reruns refresh source/result tables and are intended for a single-user demo.
>>>>>>> c72bab9 (First Run)
