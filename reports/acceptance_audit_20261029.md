# Acceptance audit — 2026-10-29

## Scope and evidence

This report distinguishes current generated exports from historical figures. The current measurements below were independently calculated from CSV/JSON files in `data/generated/`, `data/generated/acceptance-target-20261029/`, and `data/generated/room-scarcity-20261029/`. Source row counts and checksums are recorded in each `source_manifest.json`. Validation status comes from each profile's `validation_report.json`.

The three profiles were checked for this audit; the CLI syntax is also verified against `src/academic_planner/cli.py`. Re-running a CLI overwrites its output directory's current files and adds a run archive, so use a separate output directory if local generated artifacts must be preserved.

## Requirement status

| Requirement | Status | Evidence |
|---|---|---|
| Starter source profile | **PASS** | Starter manifest: 10 programs, 100 courses, 50 faculty, 1,000 student plans. |
| Full target source profile | **PASS** | Target manifest: 100 programs, 1,000 courses, 500 faculty, 20,000 student plans. |
| Generated source validation | **PASS** | Each of the current starter, target, and scarcity `validation_report.json` files reports `passed: true` and zero issues. |
| Target normal room feasibility before staffing | **PASS** | 2,160 of 2,160 proposals have a room. |
| Target normal end-to-end operational allocation | **PARTIAL** | 1,690 operational, 470 unstaffed, zero room-blocked. The pipeline is executable and valid, but not every proposal is operational. |
| Explicit room-scarcity case | **PASS** | 2,160 proposals reconcile to 348 operational, 52 unstaffed, and 1,760 room-blocked; 400 proposals have rooms. |
| Operational-capacity and unmet-demand accounting | **PASS** | Current CSV totals reconcile. Only operational sections contribute seats; unmet is calculated per course as `max(0, forecast - operational_capacity)`. |
| Five anomaly scenarios | **PASS** | Isolated test fixtures check faculty outside skill, excessive workload, insufficient section capacity, missing prerequisite completion, and duplicate assignment. See tests listed below. |
| Ground-truth separation | **PASS** | Five fixtures are separately exported in each profile's `ground_truth.csv`; forecast code operates on history and registration interest, not that fixture file. |
| Source and forecast reproducibility | **PASS in prior audit** | Previous acceptance work reports same-seed source and forecast comparisons; this task did not rerun the comparison. |
| Full allocation reproducibility | **NOT GUARANTEED** | CP-SAT uses eight workers and a time limit; equivalent assignment output may vary. |
| PostgreSQL integration | **NOT VERIFIED in this audit run** | The full suite's database cases skip when `TEST_DATABASE_URL` is unset. Earlier acceptance notes report a separately configured run, but no PostgreSQL integration was run for this documentation update. |
| Public repository | **PASS, anonymously accessible at audit time** | The configured `origin` URL is `https://github.com/Venu-16/Academic-Planning-Intelligence-Platform---YottaFlex.ai-Assignment.git`; GitHub returned the repository page without authentication. This does not mean local commits are pushed. |

`OPTIMAL` in the solver report describes its encoded faculty-assignment objective; it does not mean all proposals are staffed, or that unmodeled institutional constraints have been satisfied.

## Current generated row counts

| Source/output table | Starter | Target baseline | Target scarcity |
|---|---:|---:|---:|
| Academic terms | 1 | 1 | 1 |
| Programs | 10 | 100 | 100 |
| Courses | 100 | 1,000 | 1,000 |
| Prerequisites | 21 | 213 | 213 |
| Faculty | 50 | 500 | 500 |
| Faculty skills | 257 | 2,731 | 2,731 |
| Availability | 1,000 | 10,000 | 10,000 |
| Rooms | 30 | 120 | 30 |
| Student plans | 1,000 | 20,000 | 20,000 |
| Student course completions | 368 | 10,501 | 10,501 |
| Registration interests | 3,545 | 70,139 | 70,139 |
| Historical enrollments | 300 | 3,000 | 3,000 |
| Ground-truth fixtures | 5 | 5 | 5 |
| Forecast rows | 100 | 1,000 | 1,000 |
| Proposed sections / capacity ledger | 215 | 2,160 | 2,160 |
| Workload assignments | 170 | 1,690 | 348 |

## Numerical reconciliation

Forecast, planned, and operational seats are distinct. Planned capacity includes every proposed section; operational capacity includes only validated `OPERATIONAL` sections. Accommodated demand is `min(forecast demand, operational capacity)` per course. Unmet demand is `max(0, forecast demand - operational capacity)` per course. Course surplus cannot be transferred to a different course.

| Metric | Starter | Target baseline | Target scarcity |
|---|---:|---:|---:|
| Proposed sections | 215 | 2,160 | 2,160 |
| Roomed proposals | 215 | 2,160 | 400 |
| Operational sections | 170 | 1,690 | 348 |
| Unstaffed sections | 45 | 470 | 52 |
| Room-blocked sections | 0 | 0 | 1,760 |
| Planned seats | 8,600 | 86,400 | 86,400 |
| Operational seats | 6,800 | 67,600 | 13,920 |
| Forecast demand | 6,769 | 66,425 | 66,425 |
| Accommodated demand | 5,615 | 54,531 | 10,930 |
| Unmet demand | 1,154 | 11,894 | 55,495 |
| Courses with unmet demand | 33 | 319 | 850 |
| Courses with positive unused seats | 67 | 662 | 148 |
| Gross course-level unused seats | 1,185 | 13,069 | 2,990 |
| Net aggregate operational capacity less forecast | 31 | 1,175 | -52,505 |

For the target baseline, 67,600 operational seats exceed the 66,425 total forecast by 1,175 in aggregate, but 319 courses still have unmet demand. The 13,069 unused seats are spare capacity in courses whose own forecast is lower than their operational capacity; this capacity cannot satisfy shortages in other courses. The scarcity profile has 2,990 spare seats distributed across courses while still reporting 55,495 unmet seats. These are not accounting errors; capacity is course-specific.

Current section lifecycle sums reconcile exactly:

- Starter: `215 = 170 operational + 45 unstaffed`.
- Target baseline: `2,160 = 1,690 operational + 470 unstaffed`.
- Target scarcity: `2,160 = 348 operational + 52 unstaffed + 1,760 blocked`.

Every current target-baseline proposal and every starter proposal is roomed. In the scarcity profile, only 400 proposals are roomed. The generator and planner preserve the 40-seat section rule; no non-operational section contributes operational seats.

## Forecast evaluation

The current `evaluation_report.json` files evaluate on the chronological `2026-FALL` holdout:

| Profile | Model MAE / RMSE | Last-observation baseline MAE / RMSE |
|---|---:|---:|
| Starter | 8.137 / 9.992 | 8.580 / 10.384 |
| Target baseline and scarcity | 7.869 / 9.674 | 8.670 / 10.922 |

These are synthetic single-holdout measurements. The Random Forest has lower MAE and RMSE than the baseline on these particular holdouts, but one synthetic holdout does not establish reliable generalization or production accuracy.

## Anomaly test evidence

The clean generated baseline reports no validation issues. Negative conditions are injected into isolated tests rather than seeded into normal data:

| Scenario | Test evidence | Expected issue/handling |
|---|---|---|
| Faculty assigned outside skill set | `test_ground_truth_fixture_matches_rule_checker[FACULTY_OUTSIDE_SKILL]`; pipeline invalid-assignment test | `FACULTY_OUTSIDE_SKILL`; reject assignment, zero operational capacity for that section |
| Faculty workload exceeds maximum | `test_ground_truth_fixture_matches_rule_checker[WORKLOAD_EXCEEDED]`; pipeline invalid-assignment test | `WORKLOAD_EXCEEDED`; reject or reassign without exceeding cap |
| Section capacity insufficient | `test_ground_truth_fixture_matches_rule_checker[SECTION_CAPACITY_TOO_LOW]`; `test_pipeline_reports_capacity_shortfall_as_existing_ground_truth_rule` | `SECTION_CAPACITY_TOO_LOW`; retain unmet demand |
| Prerequisite completion missing | `test_source_validation_rejects_registered_interest_without_prerequisite_completion`; ground-truth rule test | `PREREQUISITE_SEQUENCE_VIOLATION`; flag interest ineligible |
| Duplicate faculty/section assignment | `test_ground_truth_fixture_matches_rule_checker[DUPLICATE_SECTION_ASSIGNMENT]`; pipeline invalid-assignment test | Reject duplicate; do not make section operational |

## Tests and database integration

Latest full-suite result for this audit: `python -m pytest -q` — **94 passed, 3 skipped in 326.26 seconds**. The three PostgreSQL integration tests skip because `TEST_DATABASE_URL` is absent; the fixture explicitly skips for that reason and does not fall back to `DATABASE_URL`. `python -m compileall -q src tests` and `git diff --check` both exited 0. To execute the database tests, configure a dedicated disposable PostgreSQL test database, export `TEST_DATABASE_URL` locally, then run:

```powershell
python -m pytest -q -rs tests/test_database_integration.py
```

Do not use the persistent application Compose database or production credentials as the test target. The integration fixture creates a unique temporary schema and drops that schema after the tests.

## Commands

Run from the repository root in an environment installed using `pip install -e ".[dev]"`:

```powershell
python -m academic_planner.cli --no-db --seed 20261022 --output-dir data/generated
python -m academic_planner.cli --no-db --seed 20261022 --scale target --output-dir data/generated/acceptance-target-20261029
python -m academic_planner.cli --no-db --seed 20261022 --scale target --output-dir data/generated/room-scarcity-20261029 --room-scarcity
streamlit run app_dashboard.py
python -m pytest -q
python -m compileall -q src tests
git diff --check
```

See [`README.md`](../README.md) for setup and optional PostgreSQL configuration.

## Limitations and historical metrics

- The data is synthetic, with a limited historical series and one held-out term.
- The timetable uses abstract weekdays and slots; room types/facilities, real times, and student cohort conflicts are not modeled.
- Room assignment is greedy and precedes faculty optimization; the system does not jointly solve room and faculty timetables.
- The solver's multi-worker search does not guarantee byte-for-byte identical full allocation output.
- PostgreSQL integration was skipped in this audit's no-configuration test run; a successful no-database CLI run is not database validation.
- Earlier target counts of 1,726 room-blocked and 345 operational describe a previous data/configuration state, not the current normal baseline. They are superseded by the profile-specific current rows above. Earlier starter seat figures such as 8,840 planned and 1,200 unmet likewise do not describe the current starter export.
- Do not infer publication or synchronization from a configured Git remote. At audit time, local `main` was two commits ahead of `origin/main`; no commit or push was made for this documentation work.
