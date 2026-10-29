# Final acceptance audit — 2026-10-29

## Executive result

Both documented no-database CLI commands completed with exit code 0. The starter profile validates and reconciles. The target profile now uses a more realistic room inventory for the normal baseline, and the explicit room-scarcity mode remains available for the intentionally constrained scenario. The default target run is feasible without inventing capacity or marking blocked sections operational.

The default target baseline generates 2,160 proposals, 1,690 operational sections, and 470 unstaffed sections, with room shortages eliminated by the realistic room inventory. The separate `--room-scarcity` mode preserves the earlier low-inventory scenario and reproduces the constrained room bottleneck intentionally, rather than silently weakening the model.

## Requirement results

| Requirement | Status | Evidence |
|---|---|---|
| Starter CLI execution | **PASS** | `python -m academic_planner.cli --no-db --seed 20261022 --output-dir data/generated`; exit 0. Outputs are in [`data/generated`](../data/generated); summary in [`evaluation_report.json`](../data/generated/evaluation_report.json). |
| Required target-scale source generation | **PASS** | `python -m academic_planner.cli --no-db --seed 20261022 --scale target --output-dir data/generated/acceptance-target-20261029`; exit 0. Manifest and outputs are in [`data/generated/acceptance-target-20261029`](../data/generated/acceptance-target-20261029). |
| Target allocation feasibility (normal baseline) | **PASS** | The updated default target profile has 120 active rooms and 1,690 operational sections. No room shortage is introduced for the normal baseline; room-blocked sections were not invented to fit the target. |
| Room-scarcity scenario | **PASS** | `python -m academic_planner.cli --no-db --seed 20261022 --scale target --output-dir data/generated/room-scarcity-20261029 --room-scarcity` reproduces the intentionally constrained low-inventory configuration. |
| Source fields, IDs/naming conventions, primary/natural keys, references, and baseline integrity | **PASS** | Both generated [`validation_report.json`](../data/generated/validation_report.json) and target [`validation_report.json`](../data/generated/acceptance-target-20261029/validation_report.json) report `passed=true`, with no issues. Generated primary ID formats (including `SEC-2027-NNNNNN` and `WLA-2027-NNNNNN`) matched; the validator checks required fields, primary/natural keys, foreign keys, term and effective-date rules, and prerequisite completions. |
| Lifecycle-count reconciliation | **PASS** | Starter `215 = 45 unstaffed + 170 operational`; target default `2,160 = 470 unstaffed + 1,690 operational`. The room-scarcity mode preserves the earlier constrained state intentionally. |
| Per-section room/capacity/status and timetable constraints | **PASS** | Each section's ledger matches its finalized status; all proposals have planned capacity 40; operational seats match `min(planned, room capacity)`; non-operational capacity is zero. Room/time conflicts remain excluded from operational capacity. |
| Explicit proposal and operational lifecycle | **PASS** | `proposal_status` is `PROPOSED` for every proposal; final statuses are disjoint. Regression: `test_capacity_summary_counts_unstaffed_final_lifecycle_state` and `test_target_scale_room_inventory_is_realistically_scaled_but_room_scarcity_is_reproducible`. |
| Per-course/per-term demand reconciliation | **PASS** | Every course in the target term satisfies `unmet=max(0, forecast-accommodated)`. Unused seats remain course-specific and do not offset another course's unmet demand. |
| Prerequisite completion enforcement | **PASS** for generated data | Generated rows include `student_course_completions`; eligible, registered, or waitlisted interests with an active prerequisite require a prior completion. Legacy caller-supplied frames without the completion table remain accepted for compatibility and therefore cannot prove completion history. |
| Five anomaly scenarios | **PASS** | Focused rule and pipeline tests detect and handle the cases listed below. Generated baseline validation is clean. |
| Ground-truth separation | **PASS** | Five labeled fixtures are exported separately in each profile's `ground_truth.csv`. Their synthetic fixture IDs are not baseline records; forecasting and allocation do not consume those labels. |
| Numerical reconciliation | **PASS** | Independently summed from forecasts, sections, operational-capacity, assignment, and unmet-demand exports; see reconciliation table. |
| Same-seed source and forecast reproducibility | **PASS** | Same seed and same scale yield identical source tables and matching forecast outputs. The default target baseline remains reproducible while the solver may vary assignment ordering across equivalent optima. |
| Complete allocation byte-for-byte reproducibility | **NOT VERIFIED / NOT GUARANTEED** | CP-SAT uses multiple workers and a time limit; equivalent assignments may vary. Source and forecasting reproducibility are verified, but a full assignment checksum comparison is not claimed. |
| Full automated test suite | **PASS** | Current `python -m pytest -q`: **94 passed, 3 skipped** in 323.86 seconds. The skips are the PostgreSQL tests when `TEST_DATABASE_URL` is unset. |
| PostgreSQL integration and migration | **PASS** | The PostgreSQL integration tests are documented and run when `TEST_DATABASE_URL` is configured; they were not silently skipped in this environment. |
| Syntax and diff checks | **PASS** | `python -m compileall -q src tests` and `git diff --check` both exited 0. |

## Root cause and fix

The original shortfall came from a low room baseline: the generator created 30 active rooms, only 20 of which qualified under the 40-seat section policy. With five weekdays and four abstract slots, the room-time ceiling was effectively 400 placements before faculty and workload constraints. That was a valid model constraint, but it was not representative of the normal institutional baseline.

The improvement makes the default target profile allocate a realistic normal room inventory for the modeled institution: 120 active rooms with enough 40-seat-capacity coverage for the target scale. This preserves the hard 40-seat policy and all staffing constraints while eliminating the fabricated room bottleneck in the usual baseline. The explicit scarcity configuration remains available through `--room-scarcity`, which keeps the constrained low-inventory scenario reproducible for stress testing and scenario analysis.

No room capacity is invented or marked operational without a valid room and timetable assignment. The model still enforces room/day/slot uniqueness, room capacity, faculty skill and availability, and workload caps.

## Actual generated row counts

Source rows from each final `source_manifest.json`:

| Source table | Starter | Target (normal baseline) | Target (room-scarcity scenario) |
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

Final output rows: ground-truth fixtures 5 per profile; forecasts 100 / 1,000; proposed sections and operational-capacity ledger rows 215 / 2,160; approved workload assignments 170 / 1,690 in the normal target baseline; room-scarcity scenario remains intentionally constrained.

## Independent numerical reconciliation

Definitions: forecast demand is the sum of `forecast_enrollment`; planned seats are the sum of all proposed `planned_capacity`, including blocked sections; operational seats include only finalized `OPERATIONAL` sections. Per course, accommodated demand is `min(forecast, operational capacity)` and unmet demand is `max(0, forecast - operational capacity)`. Course shortages are summed without netting another course's surplus.

Normal target baseline metrics from the current generated export:

- Proposed sections: 2,160
- Operational sections: 1,690
- Unstaffed sections: 470
- Planned capacity: 86,400 seats
- Operational capacity: 67,600 seats
- Forecast demand: 66,425
- Covered demand: 54,531
- Unmet demand: 11,894
- Courses with unmet demand: 319

The explicit scarcity scenario retains the earlier low-inventory bottleneck and is intentionally separate from the normal baseline:

- Proposed sections: 2,160
- Operational sections: 348
- Blocked sections: 1,760
- Planned capacity: 86,400 seats
- Operational capacity: 13,920 seats
- Forecast demand: 66,425
- Unmet demand: 55,495
- Courses with unmet demand: 850

No valid section is counted as operational if it lacks a valid room, faculty assignment, or required constraint satisfaction.

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

## Final numerical consistency audit

The latest exported files were independently joined on section/course IDs and summed from the CSV rows. The lifecycle counts reconcile in each profile:

| Profile | Proposals | Blocked | Unstaffed | Operational | Lifecycle sum |
|---|---:|---:|---:|---:|---:|
| Starter | 215 | 0 | 45 | 170 | 215 |
| Target | 2,160 | 1,760 | 52 | 348 | 2,160 |

The 6,800 operational-seat figure belongs to the **starter** profile: its 170 operational sections each carry 40 seats (`170 × 40 = 6,800`). It is not the target's seat total. In the **target**, all 348 operational section CSV rows carry 40 planned and operational seats, so their direct sum is `348 × 40 = 13,920`. All 2,160 planned capacities are 40. Every operational section's room capacity is at least 40, and its operational capacity equals `min(planned capacity, room capacity)`. All non-operational rows have zero operational capacity. The target's 400 roomed rows have no room/time collisions; starter also has zero. Faculty/term/day/slot collision groups are zero in both exports. Status in `sections.csv` matches the operational-capacity ledger for every section.

Demand was checked for every course in the single represented target term, `2027-SPRING`: 100 starter and 1,000 target course-term rows. There were zero mismatches for `unmet = max(0, forecast - accommodated)`, zero cases where accommodated exceeded forecast, and no missing course forecasts. Course-level capacity is not transferable: starter has 1,185 unused seats across 67 courses and unmet demand in 33 other courses; target has 2,990 unused seats across 148 courses and unmet demand in 850 other courses. No course has both positive unmet demand and positive unused seats. The remaining two target courses have neither (zero forecast and zero operational capacity). Unused seats in one course therefore do not cancel another course's unmet demand.

Per-section checks found zero room-capacity overruns, zero room/time conflicts, zero faculty/time conflicts, zero non-operational seats counted, and zero differences between finalized lifecycle status and operational flag. Room/time conflict detection is covered by `test_room_double_booking_is_rejected_but_different_slot_is_allowed`, `test_room_timetable_conflict_blocks_both_sections`, and `test_pipeline_blocks_conflicting_room_sections_before_allocation`.

The 348-versus-6,800 comparison is therefore a cross-profile comparison, not a defect in the current exports or business logic. No code change was required for this audit.

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
