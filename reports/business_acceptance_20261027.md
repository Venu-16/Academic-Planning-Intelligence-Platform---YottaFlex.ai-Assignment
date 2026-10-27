# Business acceptance report

**Overall: PARTIAL**
**Project:** `C:\Users\venum\Downloads\academic-planner\academic-planner`
**Acceptance run:** `RUN-97979BA1265D` (seed `20261022`, no database)

## Summary

The starter pipeline completed successfully and its capacity/unmet-demand exports reconcile. All five isolated anomaly scenarios and the valid control were covered by passing regression tests. PostgreSQL migration/history integration also passed against a disposable PostgreSQL 16 container. The full suite passed with that database configured.

Acceptance is **partial**, not full: the default data set is below the requested scale; target-size generation was only verified for source data, not the complete pipeline; the dashboard was inspected using `data/generated` rather than the acceptance run; and section/assignment status fields are ambiguous across exports.

## Execution and verification

| Check | Result |
|---|---|
| Fresh CLI run, seed 20261022, `--no-db` | PASS, exit 0; `RUN-97979BA1265D` |
| Focused anomaly/faculty/room/capacity/diagnostics tests | PASS, 55 passed |
| Full suite without a configured test DB | PASS, 77 passed, 2 skipped for unset `TEST_DATABASE_URL` |
| PostgreSQL integration on disposable PostgreSQL 16 | PASS, 2 passed |
| Full suite with disposable PostgreSQL configured | PASS, 79 passed, 0 skipped |
| `python -m compileall -q src tests` | PASS, exit 0 |
| `git diff --check` | PASS, exit 0; existing line-ending warnings |
| Streamlit startup and HTTP check | PASS, HTTP 200 |
| Dashboard visual inspection | PARTIAL: visually inspected, but it read `data/generated`, not the acceptance run |

The initial system-Python invocation failed with exit code 1 because it could not import the package. The project virtual-environment interpreter ran the same supported CLI successfully. Exact commands and outcomes are recorded in [business_acceptance_20261027.json](./business_acceptance_20261027.json).

No existing report was overwritten. The worktree was already dirty before this audit; no pre-existing modifications were reverted. No application database was reset, no persistent Docker volume was used or deleted, and no credentials were exposed. The application may load environment variables through its configured dotenv loader; no `.env` values were displayed.

## Data volume and integrity

| Entity | Default acceptance run | Requested target | Separate full-scale source generation |
|---|---:|---:|---:|
| Programs | 10 | 100 | 100 |
| Courses | 100 | 1,000 | 1,000 |
| Faculty | 50 | 500 | 500 |
| Student plans | 1,000 | 20,000 | 20,000 |

The default is a starter-sized dataset. Separate full-scale **source generation** also produced 213 prerequisites, 69,995 registration interests, 2,731 faculty skills, 10,000 availability rows, 30 rooms, and 3,000 historical enrollments. This was not a full forecast/planning/allocation run at scale.

The audited starter source data had no duplicate primary keys, required-field nulls, selected invalid foreign keys, self-prerequisites, or prerequisite cycles. The source manifest records seed and table checksums; `ground_truth.csv` is separate from historical enrollment inputs. Generated sections/workload IDs use 2027 because the generated term is `2027-SPRING`, while the requested examples and ground-truth fixture IDs use 2026.

Two seed-20261022 source exports in separate directories matched row counts and CSV SHA-256 checksums for all 11 source tables, and their ground-truth checksums matched. This establishes deterministic source generation for those runs; it does not establish full-pipeline determinism at target scale.

## Planning and capacity reconciliation

| Metric | Acceptance result |
|---|---:|
| Proposed sections | 221 |
| Operational sections | 170 |
| Sections without eligible faculty | 51 |
| Sections rejected/blocked by validation | 0 |
| Planned capacity | 8,840 |
| Operational capacity | 6,800 |
| Forecast demand | 6,616 |
| Operationally covered demand | 5,416 |
| Unmet demand | 1,200 |
| Courses with unmet demand | 37 |

Independent sums from `sections.csv`, `operational_capacity.csv`, `forecasts.csv`, and `unmet_demand.csv` matched these figures. Course-level unmet demand is computed from each course's forecast and operational capacity, so surplus in another course cannot mask a shortage.

There is a lifecycle representation caveat: `sections.csv` has `status=PROPOSED` on every row and a separate `planning_status` with 170 `OPERATIONAL` and 51 `PROPOSED`. `workload_assignments.csv` and the ledger's `assignment_status` use `PROPOSED` even for assignments whose section is operational. The canonical acceptance decision is reflected by `operational_capacity.operational` and `operational_capacity.section_status`; consumers relying only on the generic status field could misread it.

## Forecast evaluation

Evaluation used the same 100 chronological held-out observations for the model and prior-term baseline, at `2026-FALL`.

| Model | MAE | RMSE |
|---|---:|---:|
| Random Forest | 8.9278 | 11.6660 |
| Baseline | 8.3600 | 10.7229 |

The baseline performs better on both measures. No claim that Random Forest outperforms the baseline is supported by this run.

## Negative scenarios and valid control

| Scenario | Expected decision | Actual rule/result | Operational capacity effect |
|---|---|---|---|
| Faculty outside skill set | Reject assignment | `FACULTY_OUTSIDE_SKILL`; assignment rejected | Affected section capacity is zero |
| Workload exceeded | Reject or reassign | `WORKLOAD_EXCEEDED`; assignment rejected | Affected section capacity is zero |
| Section capacity below demand | Add section or record unmet | `SECTION_CAPACITY_TOO_LOW`; course-level unmet demand recorded | Valid seats remain countable; unmet demand is not served or hidden |
| Prerequisite sequence violation | Flag ineligible | `PREREQUISITE_SEQUENCE_VIOLATION`; baseline validation fails before allocation | No allocation is produced for the invalid run |
| Duplicate section assignment | Reject duplicate | `DUPLICATE_SECTION_ASSIGNMENT`; duplicate rejected | Affected section capacity is zero |
| Valid control | Retain valid allocation | Baseline validation passes | Valid staffed sections remain operational |

The rule checker, frame validator, and pipeline fixtures run separately from normal baseline data. The five labels are recorded separately in `ground_truth.csv`. Focused evidence is in `tests/test_ground_truth.py`; the exact test names are listed in the JSON report.

## Dashboard and persistence

Streamlit started on port 8765, returned HTTP 200, and its displayed metrics/tables were visually inspected. The dashboard reads `data/generated`, whose run ID differed from this acceptance run; therefore the dashboard is launch- and UI-tested, but not verified against the fresh acceptance output.

Database integration passed on disposable PostgreSQL 16 with tmpfs storage. Tests covered fresh and repeat initialization, migration preserving legacy rows, distinct run identifiers, run isolation, export/database reconciliation, run-scoped diagnostics and metrics, and preserved history. The integration suite passed 2 tests; the full database-enabled suite passed 79 tests with no skips. The no-DB suite separately skipped its two database tests because `TEST_DATABASE_URL` was unset.

## Known gaps and unsupported constraints

1. Full target-scale source generation passed, but the complete pipeline was not run at that scale.
2. The dashboard did not load the acceptance output directory.
3. Generic status fields are ambiguous between proposed and operational lifecycle states.
4. Ground-truth fixture IDs use 2026 while generated IDs use 2027 for `2027-SPRING`.
5. Course-required room facilities/type matching is unsupported where course requirement fields are absent.
6. Cohort timetable conflicts cannot be verified without reliable cohort scheduling data.
7. Actual clock-time overlaps between different slot IDs cannot be evaluated because slot metadata has no times; identical-slot conflicts are covered.
8. Term foreign keys are not uniform, and decision-event history does not record every section/assignment transition.
9. No standalone `docs/setup.md` or `docs/schema.md` exists; guidance is distributed across the README, architecture, business rules, data dictionary, and schema code.

## Highest-priority actions

1. Expose scale configuration through the full pipeline and qualify the complete workflow at target volume.
2. Normalize final lifecycle states across section/assignment CSVs, operational-capacity outputs, database records, and dashboard summaries.
3. Improve traceability with aligned fixture IDs, appropriate term references, and durable section/assignment transition events; clearly document constraints the current schema cannot support.

The structured report, requirement-level statuses, command exit codes, scenario evidence, and metric definitions are in [business_acceptance_20261027.json](./business_acceptance_20261027.json).
