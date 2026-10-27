# Remediation Acceptance Report

**Overall status: PARTIAL**
**Run:** `RUN-9D6C37525FBC`
**Seed / scale:** `20261022` / 100 programs, 1,000 courses, 500 faculty, 20,000 student plans
**Generated:** 2026-10-27

## Executive summary

The final target-scale no-database pipeline completed successfully and produced 39 files in the new output directory [`acceptance_remediation_run_20261027_174500`](./acceptance_remediation_run_20261027_174500). The source data passed baseline validation, artifacts reconcile arithmetically, all 1,781 unstaffed sections were accounted for by diagnostics, and every run-scoped output checked carries the same run ID.

The run is not fully acceptable as a staffing plan: only 345 of 2,126 proposed sections became operational. 1,726 were blocked for missing room assignments, and 55 had no accepted faculty assignment. This leaves 55,434 seats unmet across 850 courses. These sections were not incorrectly counted as operational; the constraints were enforced rather than relaxed.

The full test suite passed against a dedicated disposable PostgreSQL 16 database. The database tests exercised starter-scale runs; target-scale persistence was not run and remains unverified. The dashboard rendered the final report and displayed its run ID and summary metrics. All five labelled anomaly scenarios have passing rule/test coverage, though individual test-generated anomalies are not persisted as run-scoped ground-truth-linked evidence.

## Requirement results

| Requirement | Status | Evidence and business impact |
|---|---|---|
| Target-scale entity volumes | **PASS** | Generated 100 programs, 1,000 courses, 500 faculty, 20,000 student plans, 69,995 registration interests, 213 prerequisites, 2,731 faculty skills, 10,000 availability rows, 30 rooms, and 3,000 historical enrollments. The pipeline produced 2,126 sections, 345 workload assignments, 1,000 forecasts, and 1,000 unmet-demand rows. |
| Generation provenance and repeatability | **PASS** | `source_manifest.json` records seed, scale, per-table row counts and CSV SHA-256 values, plus a separate five-row ground-truth checksum. Two current-code target-scale source generations in separate temporary directories matched for every CSV checksum and row count. The temporary directories were automatically removed. |
| Source validation, term IDs, and run traceability | **PASS** | The source `validation_report.json` passed. The planning term is `2027-SPRING`; IDs begin `SEC-2027-...` and `WLA-2027-...`. Sections, capacity, assignments, forecasts, unmet demand, and decision events each carry only `RUN-9D6C37525FBC`. Ground-truth labels remain in their separate catalog. |
| End-to-end planning and staffing | **PARTIAL** | The CLI exited 0 and ran generation through exports. `planning_validation.json` correctly reports `passed=false`: 1,726 sections have `ROOM_REQUIRED`. The resulting status counts are 345 `OPERATIONAL`, 1,726 `BLOCKED`, and 55 `UNSTAFFED`. The business impact is low deliverable capacity, not a false-positive success count. |
| Room and faculty blocking / operational exclusion | **PASS** | 1,726 unique blocked sections have zero operational capacity. The validation report contains 1,726 `ROOM_REQUIRED` issue records; the capacity summary also categorizes the same blocked population as `NO_ACTIVE_ROOM`. Those categories overlap and must not be summed as distinct sections. There are 287 sections without an eligible faculty member. |
| Capacity and unmet-demand arithmetic | **PASS** | Independently recomputed planned capacity = 85,040; operational capacity = 13,800; demand = 66,408; covered demand = 10,974; unmet demand = 55,434 across 850 courses. For every course, unmet equals `max(0, forecast demand - operational capacity)`. No forecast was missing. Non-operational sections contributed zero operational seats. |
| Unstaffed diagnostics | **PASS** | `allocation_diagnostics.json` reports 1,781 unstaffed sections and `fully_accounted=true`; this equals 1,726 blocked plus 55 without an accepted assignment. It separately identifies 287 sections without an eligible faculty candidate. |
| Forecast holdout and baseline | **PASS** | The chronological `2026-FALL` holdout contains 1,000 observations. Random Forest MAE/RMSE: **7.7838 / 9.6574**. Last-observation baseline MAE/RMSE: **8.6830 / 10.9375**. The model performed better on this holdout only; that is not evidence of production performance. Inputs use earlier-term enrollment, registrations, and unmet demand to predict later-term enrollment. |
| Five labelled anomaly cases | **PARTIAL** | All five ground-truth rows are present separately and the associated tests passed. Pipeline-level rejection/capacity assertions cover skill mismatch, workload exceeded, low capacity, and duplicate assignment; prerequisite ineligibility is blocked before allocation. The isolated test outputs do not persist a run-scoped link from each injected case to its ground-truth row, and not every case asserts that its code appears in `allocation_diagnostics.json`. See the scenario table below. |
| PostgreSQL migration and run history | **PARTIAL** | Three database integration tests passed against an isolated disposable PostgreSQL 16 instance. They cover fresh/repeated initialization, legacy-record preservation, term/relationship constraints, two distinct runs, run associations, event history, and metric reconciliation for starter-scale pipeline runs. Target-scale persistence is not verified. The application database container and its data were not used or changed. |
| Dashboard | **PASS** | Streamlit loaded at `http://127.0.0.1:8765`; the selector loaded `RUN-9D6C37525FBC` and the page displayed 2,126 proposed, 345 staffed/operational, 1,726 blocked, and 287 without eligible faculty. The server was stopped after inspection. CSV/JSON arithmetic was checked independently; every table row was not manually inspected in the browser. |
| Scheduling constraints and room requirements | **PARTIAL** | Identical discrete term/day/slot conflicts are validated. Clock-time overlap between different slot IDs, cohort conflicts, and course-required room facilities/type matching cannot be verified because the model lacks reliable slot times, cohort schedules, and course room-requirement fields. |

## Anomaly scenario results

The five labels are stored in `data/generated/ground_truth.csv`, separate from normal forecasting inputs. Tests create isolated fixtures; they do not contaminate the baseline dataset.

| Scenario | Expected decision | Actual rule and behavior | Capacity / evidence |
|---|---|---|---|
| Faculty outside skill set | `REJECT_ASSIGNMENT` | `FACULTY_OUTSIDE_SKILL`; injected assignment is marked `REJECTED`. | Section operational capacity is asserted to be 0. `test_pipeline_blocks_invalid_assignment_from_operational_capacity[FACULTY_OUTSIDE_SKILL-FACULTY_OUTSIDE_SKILL]`; label `ANM-000001`. |
| Faculty workload exceeded | `REJECT_OR_REASSIGN` | `WORKLOAD_EXCEEDED`; injected assignment is marked `REJECTED`. | Section operational capacity is asserted to be 0. `test_pipeline_blocks_invalid_assignment_from_operational_capacity[WORKLOAD_EXCEEDED-WORKLOAD_EXCEEDED]`; label `ANM-000002`. |
| Section capacity too low for demand | `ADD_SECTION_OR_RECORD_UNMET` | `SECTION_CAPACITY_TOO_LOW`; unmet demand is exported with the shortfall and blocker. The test does not require the otherwise valid smaller section to be rejected. | `test_pipeline_reports_capacity_shortfall_as_existing_ground_truth_rule`; label `ANM-000003`. |
| Course before prerequisite | `FLAG_INELIGIBLE` | `PREREQUISITE_SEQUENCE_VIOLATION`; source validation rejects the ineligible registration and prevents allocation from starting. | `test_pipeline_flags_ineligible_registration_before_allocation`; label `ANM-000004`. |
| Duplicate section assignment | `REJECT_DUPLICATE` | `DUPLICATE_SECTION_ASSIGNMENT`; duplicate/invalid assignment is rejected. | Impacted section operational capacity is asserted to be 0. `test_pipeline_blocks_invalid_assignment_from_operational_capacity[DUPLICATE_SECTION_ASSIGNMENT-DUPLICATE_SECTION_ASSIGNMENT]`; label `ANM-000005`. |
| Valid control | Remain operational | A clean baseline allocation completes with no assignment issues. | `test_valid_pipeline_assignments_remain_operational`. |

The tests prove the rule decisions and relevant exported validation/capacity results. They do **not** prove a direct foreign-key-style correspondence between each test mutation and its ground-truth catalog row, nor do they retain each fixture's generated output as a separate acceptance artifact.

## Reconciliation and output evidence

Final run artifacts are under `reports/acceptance_remediation_run_20261027_174500/`. The directory contains the source CSV/JSON files, `source_manifest.json`, `ground_truth.csv`, `forecasts.csv`, `sections.csv`, `workload_assignments.csv`, `section_validation.json`, `planning_validation.json`, `allocation_diagnostics.json`, `operational_capacity.csv/json`, `unmet_demand.csv/json`, `decision_events.csv/json`, and `evaluation_report.json`.

| Metric | Independently checked value |
|---|---:|
| Proposed / operational / blocked / unstaffed sections | 2,126 / 345 / 1,726 / 55 |
| Planned / operational capacity | 85,040 / 13,800 |
| Forecast / covered / unmet demand | 66,408 / 10,974 / 55,434 |
| Courses with unmet demand | 850 |
| Faculty-ineligible sections | 287 |
| Decision events | 2,471 |
| Forecasts / unmet-demand records | 1,000 / 1,000 |

Capacity definitions follow `docs/business_rules.md`: planned capacity includes every proposed section; operational capacity includes only validated `OPERATIONAL` sections; covered demand is the sum of per-course `min(demand, operational capacity)`; unmet demand is the per-course sum of `max(0, demand - operational capacity)`. Missing forecasts remain unknown and are reported separately, not silently replaced by zero.

## Verification commands and results

Commands were run from the project directory. The PostgreSQL test URL was set only in the test process and pointed to a dedicated ephemeral container; credentials are intentionally not recorded.

| Command | Result |
|---|---|
| `.\.venv\Scripts\python.exe -m academic_planner.cli --no-db --seed 20261022 --scale target --output-dir "C:\Users\venum\Downloads\academic-planner\academic-planner\reports\acceptance_remediation_run_20261027_174500"` | Exit **0**; run `RUN-9D6C37525FBC`; 39 files produced. |
| `.venv\Scripts\python.exe -m pytest -q -rs` with `TEST_DATABASE_URL` set to the dedicated disposable PostgreSQL 16 database | Exit **0**; **90 passed** in 239.27 seconds; no skips. This includes all three database integration tests. |
| `.venv\Scripts\python.exe -m compileall -q src tests` | Exit **0**. |
| `git diff --check` | Exit **0**. Git emitted only informational LF-to-CRLF warnings for generated `src/academic_planner.egg-info` metadata. |
| Same-seed source reproducibility: call `generate_dataset(seed=20261022, scale=TARGET_SCALE)` and `export_dataset(...)` in two separate temporary directories; compare each manifest's table rows and `sha256_csv` plus ground-truth SHA-256 | Exit **0**; all source-table and ground-truth checksums matched. |
| `.\.venv\Scripts\streamlit.exe run app_dashboard.py --server.address 127.0.0.1 --server.port 8765 --server.headless true` | Launch and browser rendering verified; selected final run and inspected displayed metrics; server stopped afterward. |

## Safety and database scope

- The initial pipeline run used `--no-db`.
- PostgreSQL integration tests used a newly launched disposable `postgres:16` container with no mounted volume. That exact test container was stopped and auto-removed after the tests.
- The already-running application PostgreSQL container was left untouched. No application database was reset, migrated, or queried for this acceptance run.
- `.env` and credentials were not opened, printed, or modified. No credentials are included in this report.
- Existing reports and generated directories were preserved; this report and the final run use new paths.

## Limitations and prioritized actions

1. **Increase viable room supply and room assignment coverage.** Only 345 of 2,126 proposed sections became operational; missing-room blockers account for 1,726 blocked sections. Resolve this before treating target-scale capacity as a usable plan.
2. **Improve faculty coverage without weakening constraints.** 287 sections have no eligible faculty candidate and 55 remain unassigned after other section validation. Add feasible faculty/availability inputs or improve assignment coverage, retaining skill, term availability, workload, and timetable rules.
3. **Retain scenario-level evidence with explicit ground-truth links.** Persist isolated anomaly fixture IDs, rule outcomes, blocked/operational capacity, diagnostics, and expected labels together in reproducible test artifacts.
4. **Exercise target-scale PostgreSQL persistence.** The schema/run-history integration tests passed at starter scale, but writing and reconciling the 100/1,000/500/20,000 dataset at target scale was not performed.
5. **Add authoritative scheduling data before claiming full timetable validation.** Real slot times, course room requirements/facilities, and reliable cohort schedules are unsupported.

The current result is therefore **PARTIAL**, not a claim of full production readiness.
