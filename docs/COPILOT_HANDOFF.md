# Copilot project handoff

Prepared 2026-10-29 for continuing work in the YottaFlex.ai hiring-assessment repository. This document describes the current checked-out files and distinguishes recently verified evidence from earlier measurements and pending work.

## A. Project overview

This repository is a synthetic-data demonstrator for the hiring assessment: an Academic Planning Intelligence Platform that forecasts course enrollment, proposes sections, assigns qualified faculty, validates operational constraints, and reports the seats that can actually be delivered and course-level unmet demand. It is not a production student information system or an institution-ready scheduler.

Core entities include academic terms, programs, courses, prerequisites, faculty, faculty skills, faculty availability, rooms, student plans, student course completions, registration interests, historical enrollments, proposed sections, workload assignments, forecasts, unmet-demand records, planning runs, and decision events.

The workflow must respect hard constraints: prerequisite completion, valid term dates, 40-seat section planning policy, active rooms and sufficient room capacity, unique room/day/slot placement, faculty activity/skill/availability, weekly workload caps, one faculty assignment per section, and no overlapping faculty slot assignments. Forecast demand, planned seats, operational seats, accommodated demand, and unmet demand are distinct measures. A non-operational section cannot contribute operational seats.

Assessment evidence includes target-scale row counts, integrity and constraint checks, explicit lifecycle states, five injected anomaly scenarios, ground-truth separation, forecasting metrics against a baseline, reproducible source generation, tested database integration, and honest reporting of infeasibility and limitations.

## B. Repository map

### Application

- [`src/academic_planner/generator.py`](../src/academic_planner/generator.py) — seeded synthetic source generation; starter and target dimensions; terms, rooms, prerequisites, student plans, completion records, registration interests, historical enrollments, five ground-truth fixtures, source CSV/JSON export, and manifest/checksums.
- [`src/academic_planner/schema.sql`](../src/academic_planner/schema.sql) — PostgreSQL tables, checks, keys, indexes, lifecycle and run-scoped result schema.
- [`src/academic_planner/database.py`](../src/academic_planner/database.py) — connection creation, idempotent schema initialization/migrations, and loading latest persisted capacity metrics.
- [`src/academic_planner/forecasting.py`](../src/academic_planner/forecasting.py) — chronological historical holdout evaluation, Random Forest and last-observation baseline, future forecasts, explicit sparse-history fallbacks, and forecast input/source traceability.
- [`src/academic_planner/planning.py`](../src/academic_planner/planning.py) — section proposal generation, validated operational capacity, course-level unmet demand, and capacity summary aggregation. Room placement is simple and not jointly optimized with faculty/time allocation.
- [`src/academic_planner/optimizer.py`](../src/academic_planner/optimizer.py) — OR-Tools CP-SAT faculty assignment, one faculty per section, skills, availability, weekly workload, and same-slot faculty constraints.
- [`src/academic_planner/validation.py`](../src/academic_planner/validation.py) — source/relational, term/effective-date, prerequisite-completion, section, and assignment validations.
- [`src/academic_planner/anomaly_rules.py`](../src/academic_planner/anomaly_rules.py) — focused rule checks used for assignment and anomaly scenarios.
- [`src/academic_planner/allocation_diagnostics.py`](../src/academic_planner/allocation_diagnostics.py) — explanations for unstaffed sections and faculty-candidate blockers.
- [`src/academic_planner/lifecycle.py`](../src/academic_planner/lifecycle.py) — allowed lifecycle transitions and rejection of invalid transitions.
- [`src/academic_planner/pipeline.py`](../src/academic_planner/pipeline.py) — complete generation-to-forecast-to-planning-to-allocation-to-validation-to-export/persistence orchestration; archives each run and writes lifecycle events.
- [`src/academic_planner/cli.py`](../src/academic_planner/cli.py) — `python -m academic_planner.cli` command line, scale and dimension flags, database/no-database selection, seed, and output path.
- [`src/academic_planner/config.py`](../src/academic_planner/config.py) — dotenv-backed `SEED`, `DATABASE_URL`, and `OUTPUT_DIR` defaults.
- [`app_dashboard.py`](../app_dashboard.py) — Streamlit dashboard for generated or persisted reports.

### Tests, docs, reports, and data

- [`tests/`](../tests/) — 12 test modules: project/generator, scale/lifecycle, forecasting, ground truth, anomaly rules, capacity reconciliation, operational capacity, room/timetable, faculty eligibility, diagnostics, database configuration, and PostgreSQL integration.
- [`tests/test_database_integration.py`](../tests/test_database_integration.py) — isolated-schema PostgreSQL tests for reruns, persistence, migrations, and invalid references. Skips unless `TEST_DATABASE_URL` is set.
- [`docs/architecture.md`](architecture.md), [`docs/business_rules.md`](business_rules.md), [`docs/data_dictionary.md`](data_dictionary.md) — architecture, rules, entity definitions, cardinality, lifecycle, and known modeling limitations.
- [`reports/acceptance_audit_20261029.md`](../reports/acceptance_audit_20261029.md) — latest focused numerical/acceptance audit; use it instead of older example metrics in the README.
- [`reports/`](../reports/) — acceptance and business audit/assessment reports.
- [`data/generated/`](../data/generated/) — current starter export. Contains source CSV/JSON, forecasts, sections, assignments, validation/diagnostic reports, capacity and unmet-demand files, run archives, and events.
- [`data/generated/acceptance-target-20261029/`](../data/generated/acceptance-target-20261029/) — current target-scale export with the same output types.
- [`pyproject.toml`](../pyproject.toml), [`requirements.txt`](../requirements.txt), [`docker-compose.yml`](../docker-compose.yml) — Python packaging/dependencies, legacy requirements listing, and optional PostgreSQL 16 service configuration.

## C. Current architecture and workflow

1. `cli.py` selects `Scale()` or `TARGET_SCALE`, validates positive dimensions, and calls `run_pipeline`.
2. `generator.py` uses Python's seeded `random.Random` to create parent entities before dependent records. The target academic term is `2027-SPRING`, with synthetic dates 2027-01-01 through 2027-05-31. Generated prerequisites have corresponding student-plan-specific completion records when eligible; generated ground truth is a separate five-row export.
3. `validation.py` checks required fields, IDs/natural keys, foreign keys, enums, dates, prerequisite edges/cycles, and that eligible/registered/waitlisted students with an effective prerequisite have a completion predating the term.
4. `forecasting.py` orders historical terms, holds out the final historical term chronologically, compares a `RandomForestRegressor` (`n_estimators=80`, fixed `random_state=20261022`, `min_samples_leaf=2`) against last-observation baseline MAE/RMSE, then forecasts the target term. Sparse/new-course fallbacks use eligible registration-interest count, latest enrollment, or explicit zero as appropriate. Forecast ground truth is not a model feature.
5. `planning.py` proposes `max(1, ceil(forecast / section_capacity))` sections, where the normal planned section capacity is `min(40, largest active room capacity)`. It assigns abstract weekday/slot room placements using a simple first-fit scan and unique room/day/slot keys.
6. `optimizer.py` builds a CP-SAT maximum-assignment model. Each section gets at most one faculty member; active faculty must have effective skills and term availability; weekly assignment hours are 3 per section and capped at `max_weekly_hours`; a faculty member cannot cover two sections in the same term/day/slot. Current solver settings are a 5-second limit and 8 workers.
7. `pipeline.py` validates sections and assignments, rejects bad assignments, finalizes section lifecycle, then calculates operational capacity. Only `OPERATIONAL` sections contribute seats. It calculates accommodated demand and unmet demand by course; one course's excess seats do not offset another course's unmet seats.
8. The pipeline exports CSV/JSON artifacts, validation/diagnostic reports, `evaluation_report.json`, `decision_events.csv/json`, and `runs/<planning_run_id>/` snapshots. With persistence enabled, it initializes PostgreSQL and writes source and run-scoped rows/events.
9. `app_dashboard.py` reads output reports or persisted metrics.

Dependencies in `pyproject.toml`: Python 3.11+, pandas, NumPy, scikit-learn, OR-Tools, Streamlit, Plotly, SQLAlchemy, psycopg, PyYAML, python-dotenv, and pytest for development.

## D. Implemented features

### Implemented and evidenced

- Seeded starter and target profiles; dimensions are configurable with positive CLI flags.
- Generated primary IDs, foreign-key relationships, skill/availability records, historical records, and completion-aware student registration interests.
- Chronological historical forecasting evaluation, baseline comparison, and source/method/fallback traceability.
- Five explicit anomaly labels: `FACULTY_OUTSIDE_SKILL`, `WORKLOAD_EXCEEDED`, `SECTION_CAPACITY_TOO_LOW`, `PREREQUISITE_SEQUENCE_VIOLATION`, and `DUPLICATE_SECTION_ASSIGNMENT`.
- Ground-truth fixtures exported separately from operational source records and not used to drive forecast/allocation.
- Separate `proposal_status=PROPOSED` and finalized section statuses (`OPERATIONAL`, `UNSTAFFED`, `BLOCKED`, `REJECTED`); zero operational seats for non-operational sections.
- Room capacity and same-slot room conflict validation; faculty skill/activity/availability/workload/timetable validation.
- Course-level accommodated/unmet demand and unique blocked-section metrics, with missing evidence handled explicitly.
- PostgreSQL schema initialization and migrations, upserted source rows, run-scoped outputs/events, and integration tests.
- Stable same-seed source generation and forecasts were verified in the prior acceptance work; different seed changes generated source/forecast data.

### Simplified, incomplete, or not guaranteed

- Room/time assignment is not jointly optimized with faculty allocation. It currently scans 20 modeled weekday/slot combinations (five days × four discrete slots) and selects an unused qualifying room for each proposal.
- Current synthetic room inventory has only 20 rooms of capacity at least 40; therefore the existing 40-seat policy permits at most 400 room/time placements.
- No course-to-room-type/facility requirement, student cohort timetable, or slot start/end times exist. Conflicts for identical day/slot are checked; real-world clock overlap between distinct slot IDs cannot be proven.
- Legacy caller-provided frames without `student_course_completions` remain accepted for compatibility and cannot prove real prerequisite completion history. Newly generated data includes completion records.
- Target-scale CLI process success means the workflow completed; it does not mean all proposals are feasible.
- CP-SAT uses multiple workers and a time limit. Complete allocation byte-identical reproducibility is not guaranteed or claimed.
- Forecast evaluation uses only a small synthetic historical series and one chronological held-out term; it is not evidence of production forecast performance.

## E. Current verified status

### Latest exported profile figures

The numerical audit independently inspected the current `sections.csv`, `operational_capacity.csv`, `forecasts.csv`, `unmet_demand.csv`, source manifests, and validation reports. The latest CLI commands exited 0 in the previous acceptance run; during the handoff task the current exports were reread and reconciled, but CLI commands were not rerun.

| Metric | Starter (`data/generated`) | Target (`data/generated/acceptance-target-20261029`) |
|---|---:|---:|
| Programs / courses / faculty / student plans | 10 / 100 / 50 / 1,000 | 100 / 1,000 / 500 / 20,000 |
| Prerequisites / course completions / registration interests | 21 / 368 / 3,545 | 213 / 10,501 / 70,139 |
| Faculty skills / availability / rooms / historical enrollment | 257 / 1,000 / 30 / 300 | 2,731 / 10,000 / 30 / 3,000 |
| Forecast rows / demand | 100 / 6,769 | 1,000 / 66,425 |
| Proposed / blocked / unstaffed / operational sections | 215 / 0 / 45 / 170 | 2,160 / 1,760 / 52 / 348 |
| Planned seats / operational seats | 8,600 / 6,800 | 86,400 / 13,920 |
| Accommodated demand / unmet demand | 5,615 / 1,154 (33 courses) | 10,930 / 55,495 (850 courses) |
| Solver status / invalid assignments | OPTIMAL / 0 | OPTIMAL / 0 |

Target lifecycle equation: `2,160 = 1,760 + 52 + 348`. Starter lifecycle equation: `215 = 0 + 45 + 170`. All proposals are 40 planned seats. Thus the 6,800 figure is starter `170 × 40`, not target operational capacity; target is `348 × 40 = 13,920`.

The latest consistency audit verified both exports satisfy, for every course in `2027-SPRING`, `unmet = max(0, forecast - accommodated)`. There were zero mismatches, over-accommodated courses, non-operational seats counted, room-capacity overruns, room/time conflict groups, or faculty/time conflict groups. Both source datasets passed `validate_frames` with zero issues and all checked primary keys unique. Ground-truth rows are five per profile.

### Test/build and database evidence

- Current full-suite run during handoff preparation: `python -m pytest -q` — **93 passed, 3 skipped** in 316.27 seconds. The 3 are PostgreSQL integration cases skipped because `TEST_DATABASE_URL` was unset in that invocation.
- Last separately verified database run in the preceding acceptance task: **3 passed** against a disposable PostgreSQL 16 container. Do not describe the 3 normal-suite skips as passed within the full-suite run; distinguish the separate DB run.
- Last `python -m compileall -q src tests` and `git diff --check` evidence: passed during the preceding acceptance task. This handoff only adds documentation; no application validation was needed for this new file.
- Previous same-seed comparison: all 12 target source tables serialized identically; forecasts were identical; seed `20261023` changed source and forecast results. Full allocation identity was not verified/guaranteed.

## F. Recent changes and Git state

Current Git status was inspected. **Only** `reports/acceptance_audit_20261029.md` is modified and uncommitted before this handoff; its latest changes add independent section lifecycle/capacity and course-term demand reconciliations and update current-suite evidence. The application implementation is committed. This new file will be the only additional untracked path. Do not discard either change.

Relevant recent commits:

- `76584b5 target data generation and pipe line checking` — target generated artifacts, completion-aware generation/validation, forecast traceability, lifecycle/capacity/pipeline/database schema updates, regression tests, docs, and acceptance evidence.
- `fa369a1 Add target-scale lifecycle acceptance checkpoint` — target-scale and lifecycle handling, room/timetable validation, diagnostics, schema/persistence integration, and tests.
- `3395402 Complete academic planner validation` — broader source/assignment validation, forecasting and reconciliation, database support/tests, docs, and project setup.

These are committed-history summaries from `git show`; the only currently uncommitted application-adjacent change is the acceptance report, not source code. Generated outputs are tracked/committed according to current `git status`; do not overwrite or clean them without explicit need and user authorization.

## G. Current acceptance report

Read [`reports/acceptance_audit_20261029.md`](../reports/acceptance_audit_20261029.md) for the full evidence and exact rows.

- **PASS:** starter and target CLI execution in the latest audited run; source dimensions, key/FK/required-value validation; lifecycle sum reconciliation; per-section capacity, room, status, and room/faculty slot checks; course-term unmet-demand arithmetic; generated prerequisite completion validation; five isolated anomaly scenarios; separate ground-truth fixtures; source/forecast same-seed repeatability; full pytest suite; separately run PostgreSQL integration; prior compile/diff checks.
- **PASS:** the default target baseline is feasible without inventing capacity: 2,160 proposals, 1,690 operational sections, and 470 unstaffed sections with zero room-blocked sections under the realistic room baseline.
- **PASS:** the explicit scarcity mode remains intentionally constrained and reproducible: 2,160 proposals, 348 operational sections, 1,760 room-blocked sections, and 52 unstaffed sections.
- **NOT VERIFIED / NOT GUARANTEED:** byte-identical complete solver allocation across runs. Real clock-time overlaps, course room-type/facility fit, and student cohort conflicts are outside the current model. Legacy input frames without completion records cannot establish prerequisite history.

Do not conflate starter and target results. The README contains older illustrative metrics from a prior generator behavior; the acceptance audit and current exports in `data/generated/` and `data/generated/acceptance-target-20261029/` are the current source of truth.

## H. Immediate pending task: improve room-inventory realism

The next agent should continue the current room-realism work in the existing codebase without weakening constraints or redesigning the system:

1. Inspect `generator.py` room generation, `planning.py::propose_sections`, room/timetable validation, and the current generated exports.
2. Confirm the root cause of any room bottleneck using measured output rather than inferred assumptions: current normal baseline uses a realistic 120-room inventory; the constrained scarcity mode is intentionally low-inventory and should remain separate.
3. Preserve the hard rules for room capacity, timetable uniqueness, faculty skill/availability, and workload. Do not count blocked proposals as operational or invent capacity.
4. Keep the default baseline realistic for the modeled institution, but leave a separately configurable `--room-scarcity` scenario for legitimate stress testing.
5. Measure room assignment feasibility before faculty constraints separately from final operational feasibility; update the acceptance report with actual before-and-after metrics.
6. Run focused room/timetable tests, then the full suite, starter CLI, target CLI, integrity checks, and same-seed reproducibility checks before updating the report.

Use the latest generated CSV/JSON outputs as the evidence source; do not treat historical shortfall values as current facts once the room baseline has changed.

## I. Exact setup and project commands

From the project directory in Windows PowerShell, README setup commands are:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

The project is installable with Python 3.11+; `pyproject.toml` pins supported major-version ranges. For no-database runs, PostgreSQL environment configuration is not needed.

Exact audited CLI invocations:

```powershell
python -m academic_planner.cli --no-db --seed 20261022 --output-dir data/generated
python -m academic_planner.cli --no-db --seed 20261022 --scale target --output-dir data/generated/acceptance-target-20261029
```

CLI supports `--scale starter|target`, `--programs`, `--courses`, `--faculty`, `--student-plans`, `--seed`, `--output-dir`, `--database-url`, and `--no-db`. Normal defaults are seed `20261022`, starter scale, and output `data/generated`.

README test and check commands:

```powershell
python -m pytest -q -rs
python -m compileall -q src tests
git diff --check
python -m pytest tests/test_ground_truth.py -q
python -m pytest tests/test_faculty_eligibility.py tests/test_room_timetable.py -q
python -m pytest tests/test_capacity_reconciliation.py tests/test_allocation_diagnostics.py -q
```

For regular PostgreSQL persistence, README instructs the user to set `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `DATABASE_URL` privately in the local environment, then:

```powershell
docker compose up -d postgres
python -m academic_planner.cli --seed 20261022
```

`docker-compose.yml` runs `postgres:16` on host port 5433, uses a named persistent volume, and requires user/password environment values; the database defaults to `academic_planner` if `POSTGRES_DB` is not set. Never include secret values in handoff or logs.

Database tests require a **dedicated disposable** `TEST_DATABASE_URL`; they do not fall back to `DATABASE_URL`. Run:

```powershell
python -m pytest -q -rs tests/test_database_integration.py
```

README also documents a disposable Docker Desktop `postgres:16` container with tmpfs on port 55432 and a generated test-only password. Read that block in `README.md` before executing it; ensure cleanup runs even when tests fail. Do not use the persistent Compose service or production database as an integration-test target.

Dashboard command from README:

```powershell
streamlit run app_dashboard.py
```

## J. Known problems and limitations

- Room inventory is too small for target scale under a 40-seat cap and 20 abstract weekday/slot combinations; target allocation therefore remains infeasible.
- Room assignment is a greedy/simple extension point, not jointly optimized with faculty scheduling.
- Room type/facility needs, student cohorts, slot start/end times, and cross-slot clock overlaps are not modeled.
- Faculty staffing may leave a roomed proposal unstaffed due to active status, effective skills, term availability, workload, or same-slot conflicts.
- CP-SAT settings (5-second time limit, 8 workers) do not guarantee identical full allocation output even with the same source seed.
- The current full pytest run has 3 skipped PostgreSQL tests when `TEST_DATABASE_URL` is unset; separate disposable PostgreSQL 16 run last passed 3 tests.
- PostgreSQL environment setup must be isolated and use non-production credentials. The app expects an explicitly configured `DATABASE_URL` for persistence.
- Synthetic data, term dates, and a single historical holdout do not establish institutional realism or production forecast quality.
- README includes stale prior-run example metrics; use the current acceptance report and regenerated outputs.
- Current worktree contains the uncommitted acceptance report update. No application edits are in progress.

## K. Rules for continuing development

1. Read this handoff and [`reports/acceptance_audit_20261029.md`](../reports/acceptance_audit_20261029.md) first.
2. Inspect the actual repository, current Git status/diff, relevant code, and generated outputs before editing.
3. Preserve existing commits, uncommitted changes, generated evidence, and architecture. Never reset, discard, or overwrite unrelated work.
4. Prefer minimal, testable changes and existing dependencies/patterns. Do not redesign or rebuild the platform.
5. Run focused tests before the complete test suite.
6. Never hardcode expected metrics or weaken business constraints to make acceptance numbers/tests pass.
7. Independently calculate requested metrics from records and validate both starter and target profile labels.
8. State exactly what ran, what passed/failed/skipped, and what remains unverified. A CLI exit code of zero is not proof of feasible allocation.
