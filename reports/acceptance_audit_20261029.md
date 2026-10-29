# Final acceptance audit — 2026-10-29

## Executive result

Both documented no-database CLI commands completed with exit code 0. The starter profile validates and reconciles. The target profile generates the required full-scale source data, but its plan is **not feasible**: the room inventory permits only 400 room-time placements, leaving 1,760 proposed sections blocked. No capacity was invented or counted as operational.

The final lifecycle ledger is explicit: all 2,160 target sections retain `proposal_status=PROPOSED`; finalized `status` is `OPERATIONAL` (348), `UNSTAFFED` (52), or `BLOCKED` (1,760). Only operational sections contribute seats. A targeted fix also corrected the capacity report's unstaffed-section count.

## Requirement results

| Requirement | Status | Evidence |
|---|---|---|
| Starter CLI execution | **PASS** | `python -m academic_planner.cli --no-db --seed 20261022 --output-dir data/generated`; exit 0. Outputs are in [`data/generated`](../data/generated); summary in [`evaluation_report.json`](../data/generated/evaluation_report.json). |
| Required target-scale source generation | **PASS** | `python -m academic_planner.cli --no-db --seed 20261022 --scale target --output-dir data/generated/acceptance-target-20261029`; exit 0. Manifest and outputs are in [`data/generated/acceptance-target-20261029`](../data/generated/acceptance-target-20261029). |
| Target allocation feasibility | **FAIL — resource-constrained** | 1,760 sections have no room (`ROOM_REQUIRED`); 52 roomed sections are unstaffed; 348 are operational. [`planning_validation.json`](../data/generated/acceptance-target-20261029/planning_validation.json) reports 1,760 invalid sections and zero invalid assignments. |
| Source fields, IDs/naming conventions, primary/natural keys, references, and baseline integrity | **PASS** | Both generated [`validation_report.json`](../data/generated/validation_report.json) and target [`validation_report.json`](../data/generated/acceptance-target-20261029/validation_report.json) report `passed=true`, with no issues. Generated primary ID formats (including `SEC-2027-NNNNNN` and `WLA-2027-NNNNNN`) matched; the validator checks required fields, primary/natural keys, foreign keys, term and effective-date rules, and prerequisite completions. |
| Explicit section lifecycle and capacity accounting | **PASS** | `proposal_status` is `PROPOSED` for every proposal; final statuses are disjoint. Non-operational sections have zero operational capacity. Regression: `test_capacity_summary_counts_unstaffed_final_lifecycle_state`. |
| Prerequisite completion enforcement | **PASS** for generated data | Generated rows include `student_course_completions`; eligible, registered, or waitlisted interests with an active prerequisite require a prior completion. Legacy caller-supplied frames without the completion table remain accepted for compatibility and therefore cannot prove completion history. |
| Five anomaly scenarios | **PASS** | Focused rule and pipeline tests detect and handle the cases listed below. Generated baseline validation is clean. |
| Ground-truth separation | **PASS** | Five labeled fixtures are exported separately in each profile's `ground_truth.csv`. Their synthetic fixture IDs are not baseline records; forecasting and allocation do not consume those labels. |
| Numerical reconciliation | **PASS** for arithmetic; target feasibility remains **FAIL** | Independently summed from forecasts, sections, operational-capacity, assignment, and unmet-demand exports; see reconciliation table. |
| Same-seed source and forecast reproducibility | **PASS** | Two current target generator runs produced identical serialized hashes for all 12 source tables and identical forecasts. Seed `20261023` changed both. CSV-serialized forecast DataFrame SHA-256 for seed `20261022` (excluding run metadata): `1e52fc3dffcc8fb2e3ae834cba86858460722a551dc3a69f428f584fefda96c7`. |
| Complete allocation byte-for-byte reproducibility | **NOT VERIFIED / NOT GUARANTEED** | CP-SAT uses eight workers and a time limit; equal-quality assignments may differ. Source and forecasting reproducibility are verified, but a full allocation checksum comparison is not claimed. |
| Full automated test suite | **PASS** | `python -m pytest -q`: **93 passed, 3 skipped** in 322.92 seconds. The skips are the PostgreSQL tests when `TEST_DATABASE_URL` is unset; those tests were run separately and passed. |
| PostgreSQL integration and migration | **PASS** | `python -m pytest -q -rs tests/test_database_integration.py` against an isolated, disposable PostgreSQL 16 Docker container: **3 passed** in 87.49 seconds. No production credentials or database were used. |
| Syntax and diff checks | **PASS** | `python -m compileall -q src tests` and `git diff --check` both exited 0. Git emitted only existing line-ending normalization warnings. |

## Resource-constraint root cause

The target generator creates 30 active rooms: five each with capacities 25, 30, 40, 50, 60, and 80. Section planning caps section size at 40, so only 20 rooms qualify. The model has five weekdays and four slots per day; at most `20 qualifying rooms × 5 days × 4 slots = 400` room-time placements are available. The final target output uses exactly 400, with zero duplicate room/day/slot assignments.

The planner proposes 2,160 sections at 40 seats each. Thus 1,760 proposals have no room and are correctly `BLOCKED`; this is insufficient synthetic room inventory under the existing hard 40-seat section rule, not a seat-accounting or duplicate-room-scheduling defect. Of the 400 roomed sections, 52 cannot be staffed under the skill, active-employment, availability, timetable, and workload constraints; 348 are operational. Diagnostics account for every non-operational section. The solver reports `OPTIMAL` for its constrained assignment problem; that does not make the overall plan feasible.

No rooms or seats were added, and blocked proposals are not treated as delivered capacity. The current model represents four abstract daily slots; it does not model finer clock times or room-type suitability.

## Actual generated row counts

Source rows from each final `source_manifest.json`:

| Source table | Starter | Target |
|---|---:|---:|
| Academic terms | 1 | 1 |
| Programs | 10 | 100 |
| Courses | 100 | 1,000 |
| Prerequisites | 21 | 213 |
| Faculty | 50 | 500 |
| Faculty skills | 257 | 2,731 |
| Availability | 1,000 | 10,000 |
| Rooms | 30 | 30 |
| Student plans | 1,000 | 20,000 |
| Student course completions | 368 | 10,501 |
| Registration interests | 3,545 | 70,139 |
| Historical enrollments | 300 | 3,000 |

Final output rows: ground-truth fixtures 5 per profile; forecasts 100 / 1,000; proposed sections and operational-capacity ledger rows 215 / 2,160; approved workload assignments 170 / 348; unmet-demand rows 100 / 1,000 (starter / target).

## Independent numerical reconciliation

Definitions: forecast demand is the sum of `forecast_enrollment`; planned seats are the sum of all proposed `planned_capacity`, including blocked sections; operational seats include only finalized `OPERATIONAL` sections. Per course, accommodated demand is `min(forecast, operational capacity)` and unmet demand is `max(0, forecast - operational capacity)`. Course shortages are summed without netting another course's surplus. Capacity realization is operational seats / planned seats; workload utilization is approved weekly hours / active faculty weekly limits.

| Measure | Starter | Target |
|---|---:|---:|
| Forecast demand | 6,769 | 66,425 |
| Planned seats | 8,600 | 86,400 |
| Operational seats | 6,800 | 13,920 |
| Accommodated forecast demand | 5,615 | 10,930 |
| Unmet demand | 1,154 across 33 courses | 55,495 across 850 courses |
| Capacity realization | 79.07% | 16.11% |
| Proposed / operational / unstaffed / blocked sections | 215 / 170 / 45 / 0 | 2,160 / 348 / 52 / 1,760 |
| Sections with no feasible faculty candidate | 45 | 296 |
| Courses with no candidate on any proposed section | 13 | 109 |
| Approved workload / active weekly limit | 510 / 570 hours | 1,044 / 5,668 hours |
| Aggregate workload utilization | 89.47% | 18.42% |
| Maximum individual workload utilization | 100% | 100% |
| Faculty workload violations / duplicate faculty-section pairs | 0 / 0 | 0 / 0 |
| Room-slot duplicates | 0 | 0 |
| Invalid assignments | 0 | 0 |

Direct reconciliation: `6,769 - 5,615 = 1,154` starter unmet seats; `66,425 - 10,930 = 55,495` target unmet seats. Non-operational sections have zero operational capacity. The corrected target `capacity.sections_unstaffed` metric is 52, matching the finalized section statuses.

The older starter figures (8,840 planned seats, 6,800 operational seats, 6,616 forecast demand, and 1,200 unmet seats) do **not** reproduce after the prerequisite-completion change. The updated generator adds completion-aware eligibility, changing registration-interest data and sparse-history forecast inputs; course-level section rounding also changes proposed seats. The current values above come from the final exported records, not hardcoded targets.

The synthetic held-out forecast evaluation uses `2026-FALL`: starter MAE/RMSE 8.137/9.992; target 7.869/9.674. These are synthetic evaluation metrics, not production accuracy guarantees.

## Anomaly scenarios

Each condition is injected into an isolated fixture; none is intentionally present in the clean generated baseline.

| Scenario and test evidence | Injected condition | Detected issue and expected handling | Result |
|---|---|---|---|
| `test_ground_truth_fixture_matches_rule_checker[FACULTY_OUTSIDE_SKILL]`; `test_pipeline_blocks_invalid_assignment_from_operational_capacity[FACULTY_OUTSIDE_SKILL-FACULTY_OUTSIDE_SKILL]` | Remove the faculty/course pair from the skill bridge. | `FACULTY_OUTSIDE_SKILL`; reject the assignment and do not count its section as operational. | **PASS** |
| `test_ground_truth_fixture_matches_rule_checker[WORKLOAD_EXCEEDED]`; `test_pipeline_blocks_invalid_assignment_from_operational_capacity[WORKLOAD_EXCEEDED-WORKLOAD_EXCEEDED]` | Make the proposed load exceed the faculty member's maximum weekly hours. | `WORKLOAD_EXCEEDED`; reject or reassign without exceeding the cap. | **PASS** |
| `test_ground_truth_fixture_matches_rule_checker[SECTION_CAPACITY_TOO_LOW]`; `test_pipeline_reports_capacity_shortfall_as_existing_ground_truth_rule` | Demand is 45 seats while the fixture section has 30 seats. | `SECTION_CAPACITY_TOO_LOW`; retain the 15-seat unmet shortfall rather than invent capacity. | **PASS** |
| `test_source_validation_rejects_registered_interest_without_prerequisite_completion`; `test_ground_truth_fixture_matches_rule_checker[PREREQUISITE_SEQUENCE_VIOLATION]` | Remove the student's completion record for an active prerequisite while marking the target interest eligible/registered. | `PREREQUISITE_SEQUENCE_VIOLATION`; flag the interest ineligible. | **PASS** |
| `test_ground_truth_fixture_matches_rule_checker[DUPLICATE_SECTION_ASSIGNMENT]`; `test_pipeline_blocks_invalid_assignment_from_operational_capacity[DUPLICATE_SECTION_ASSIGNMENT-DUPLICATE_SECTION_ASSIGNMENT]` | Add a second assignment for the same faculty/section pair. | `DUPLICATE_SECTION_ASSIGNMENT`; reject the duplicate and do not count its section as operational. | **PASS** |

`test_generated_prerequisite_completions_support_registered_interests` and the generated `validation_report.json` also confirm that the normal generated baseline's eligible interests satisfy prerequisite completion rules.

## Reproducibility, database setup, and remaining limitations

- Two target `generate_dataset(seed=20261022, scale=TARGET_SCALE)` runs yielded identical CSV-serialized hashes for all 12 source tables. Two `forecast_demand` runs on that source yielded identical forecast rows and metrics. Seed `20261023` changed source data and forecasts.
- Full allocation identity is not promised: CP-SAT runs with eight workers and a time limit, and run IDs/timestamps also vary. No change was made to solver configuration because deterministic allocation was not necessary to correct the identified gaps.
- The three normal-suite skips all state that `TEST_DATABASE_URL` is unset and PostgreSQL integration requires a dedicated disposable test database. The suite does not fall back to `DATABASE_URL`. The documented isolated setup is in [`README.md`](../README.md): Docker Desktop, `postgres:16`, a generated test-only password, a tmpfs database container on port 55432, and `python -m pytest -q -rs tests/test_database_integration.py`. The container was removed after the successful run.
- Generated datasets include explicit prerequisite completion records. Older external frames omitting that optional table remain compatible but cannot establish actual completion history.
- The target CLI exits successfully while reporting `planning_validation.passed=false`; successful execution is not evidence that the target allocation is feasible. More appropriately sized room inventory (or a changed, explicitly approved room/section policy) is required to meet target demand.

## Commands

```powershell
python -m pip install -e ".[dev]"
python -m academic_planner.cli --no-db --seed 20261022 --output-dir data/generated
python -m academic_planner.cli --no-db --seed 20261022 --scale target --output-dir data/generated/acceptance-target-20261029
python -m pytest -q
python -m pytest -q -rs tests/test_database_integration.py
python -m compileall -q src tests
git diff --check
```

For PostgreSQL tests, follow the isolated Docker instructions in [`README.md`](../README.md); set only a dedicated disposable `TEST_DATABASE_URL`, never a production or application database URL.
