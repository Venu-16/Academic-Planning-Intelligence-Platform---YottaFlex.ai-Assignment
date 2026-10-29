# Design decisions and trade-offs

This note explains the current implementation in the checked-out project. It distinguishes modeled behavior from real institutional scheduling and reports measured synthetic outputs, not design targets.

## Synthetic data and seeds

- **Chosen approach:** `generator.py` uses a local `random.Random(seed)` to create linked synthetic source tables. IDs and table relationships are generated in a controlled order. The CLI exposes a starter profile and a target profile, plus explicit dimension overrides.
- **Reason/trade-off:** This supports repeatable examples, isolated testing, and target-scale validation without access to student or employee data. Synthetic distributions and generated term dates are assumptions, not institution-derived facts.
- **Evidence:** Current starter and target manifests record their seed, configuration, source row counts, and CSV SHA-256 checksums. The current profiles contain 10/100/50/1,000 and 100/1,000/500/20,000 programs/courses/faculty/student plans respectively.
- **Limitations:** A seed does not make every downstream result byte-identical: run IDs/timestamps vary, and the multi-worker CP-SAT solver may select a different equivalent solution.

## Historical demand forecasting

- **Chosen approach:** `forecasting.py` chronologically orders the available historical terms and holds out the final term for evaluation. It fits a scikit-learn `RandomForestRegressor` (80 trees, fixed estimator random state, `min_samples_leaf=2`) on prior enrollment transitions, using prior enrollment, registrations, and unmet demand. It compares with a last-observation baseline.
- **Sparse-history handling:** For courses without enough transitions, the code uses eligible registration-interest count, last enrollment, or zero, and records the fallback method/reason. Outputs include source term and feature/fallback traceability. `ground_truth.csv` is not a forecast feature.
- **Reason/trade-off:** The compact model and simple baseline are explainable and runnable on generated data. The limited time series and single chronological holdout are not enough to establish production forecast quality.
- **Measured evidence:** On current synthetic exports, starter holdout MAE/RMSE are 8.137/9.992 versus baseline 8.580/10.384; target holdout MAE/RMSE are 7.869/9.674 versus baseline 8.670/10.922. These are one synthetic holdout result each, not generalization guarantees.

## Section sizing and room capacity

- **Chosen approach:** `planning.py` proposes `max(1, ceil(forecast / section_capacity))` sections per course. Section capacity is at most 40 seats and cannot exceed the largest active room. Room assignment uses a simple first-fit scan across the modeled five weekdays and four abstract slots, ensuring a room/day/slot key is not reused.
- **Normal versus scarcity inventory:** `generator.py` creates 120 rooms for the target baseline (all capacities at least 40); `--room-scarcity` restores a 30-room inventory where 20 rooms meet the 40-seat section requirement. The lower-resource setting is an explicit scenario, not the normal target profile.
- **Reason/trade-off:** A larger default inventory removes the synthetic room-slot ceiling for the target scenario without relaxing the section policy. The scarcity profile preserves a reproducible way to exercise room blocking. The 120-room count is a synthetic institutional assumption, not a measured real-world requirement.
- **Measured evidence:** All 2,160 target proposals are roomed in the normal profile. In the scarcity profile, only 400 of 2,160 receive a room (1,760 are room-blocked). Room assignments are not jointly optimized with faculty assignments.
- **Limitations:** Room type and equipment compatibility, real clock times, setup/transition times, and student cohort conflicts are not modeled.

## Faculty skills, availability, workload, and timetable

- **Chosen approach:** `optimizer.py` uses OR-Tools CP-SAT binary assignment variables. It maximizes the count of assigned sections while enforcing at most one faculty member per section, effective faculty-course skill, active employment, term availability at the assigned day/slot, a three-hour weekly load per section within each faculty member's maximum, and no same-slot duplicate assignment for a faculty member. The planner and validation code separately prevent conflicting room/day/slot placements.
- **Reason/trade-off:** A constraint solver avoids accepting assignments that violate the modeled hard constraints. The room/time plan is still generated greedily before the faculty solve, so this is not a joint timetable optimizer.
- **Evidence:** The current normal target has 1,690 operational sections and 470 unstaffed; the target scarcity profile has 348 operational and 52 unstaffed in addition to the 1,760 room-blocked proposals. The evaluation output reports `OPTIMAL` for its assignment objective. That means the solver found an optimum for this encoded model/run; it does not mean all proposals are feasible or that omitted real-world constraints have been solved.
- **Solver trade-off:** Current settings allow up to five seconds and eight workers. Multiple workers can make equivalent assignment choices differ across runs. Complete allocation byte-for-byte reproducibility is not claimed.

## Proposed, staffed, and operational lifecycle

- **Chosen approach:** Every proposal has `proposal_status=PROPOSED`; final lifecycle state is separately recorded as `OPERATIONAL`, `UNSTAFFED`, `BLOCKED`, or `REJECTED`. `calculate_operational_capacity` grants seats only when required checks pass. Non-operational sections have zero operational capacity.
- **Reason/trade-off:** This preserves proposed planning intent without representing an unroomed or unstaffed section as deliverable. A successfully executed pipeline can still return a plan with unstaffed or blocked sections.
- **Measured evidence:** Current profile lifecycle counts reconcile: starter `215 = 170 operational + 45 unstaffed`; target `2,160 = 1,690 + 470`; scarcity `2,160 = 348 operational + 52 unstaffed + 1,760 blocked`. The current validation reports for all three profiles contain zero source validation issues.

## Operational seats and unmet demand

- **Chosen approach:** Planned capacity includes every proposed section. Operational capacity sums only validated operational sections. For each course, accommodated demand is `min(forecast_demand, operational_capacity)` and unmet demand is `max(0, forecast_demand - operational_capacity)`. Course shortages are not netted against another course's surplus.
- **Reason/trade-off:** Seats assigned to one course cannot automatically satisfy demand for a different course. Therefore aggregate operational seats can exceed aggregate forecast while substantial course-specific unmet demand remains.
- **Measured evidence:** In the target baseline there are 67,600 operational seats, 66,425 forecast demand, 54,531 covered demand, and 11,894 unmet. The net aggregate capacity surplus is 1,175 seats, but 319 courses have unmet demand and 662 have course-level surplus capacity; the gross course-level unused capacity is 13,069 seats. Those surpluses and shortfalls coexist because capacity is course-specific. In starter, 6,800 seats support 6,769 forecast demand, yet there are 1,154 unmet and 1,185 unused seats at other courses.
- **Limitations:** This measure does not reassign students across courses, model substitutions, or optimize seats across programs.

## Ground truth and anomaly fixtures

- **Chosen approach:** `ground_truth.csv` stores five documented issue fixtures separately from ordinary operational source tables. The rules cover faculty outside skill, excessive workload, insufficient section capacity, prerequisite sequence violations, and duplicate faculty/section assignment. Tests inject these conditions into isolated data or pipeline fixtures and assert their issue type and handling.
- **Reason/trade-off:** Keeping labels separate reduces direct leakage into baseline forecasts and allocations. The fixtures are synthetic test cases, not naturally observed prevalence data or a machine-learning training label set.
- **Evidence:** `tests/test_ground_truth.py` checks the five issue types, rule results, and selected pipeline/validation handling. Baseline `validation_report.json` is clean for the current three generated profiles.
- **Limitations:** A clean generated source validation does not establish that the synthetic distributions represent real-world anomaly rates.

## Database and exports

- **Chosen approach:** PostgreSQL is optional. No-database runs write CSV/JSON artifacts and an archive per planning run. Persisted runs initialize the PostgreSQL schema, upsert source records, and store planning outputs/events. Database integration tests require `TEST_DATABASE_URL` and isolate each test in a uniquely named schema.
- **Reason/trade-off:** File exports support a simple reviewer workflow; PostgreSQL exercises persistence and relational constraints separately.
- **Evidence and qualification:** The full test suite skips the PostgreSQL tests when `TEST_DATABASE_URL` is absent. A no-database CLI run is not evidence that persistence passed. See the acceptance audit and README for the latest test result and isolated test setup.

## Current profile measurements

All values below were summed from current generated CSVs; they are also reported in [`reports/acceptance_audit_20261029.md`](../reports/acceptance_audit_20261029.md).

| Profile | Proposals | Roomed | Operational | Unstaffed | Room-blocked | Operational seats | Forecast | Covered | Unmet |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Starter | 215 | 215 | 170 | 45 | 0 | 6,800 | 6,769 | 5,615 | 1,154 |
| Target baseline | 2,160 | 2,160 | 1,690 | 470 | 0 | 67,600 | 66,425 | 54,531 | 11,894 |
| Target scarcity | 2,160 | 400 | 348 | 52 | 1,760 | 13,920 | 66,425 | 10,930 | 55,495 |

These are one seeded synthetic run per profile. No metric is an expected-value constant in the implementation.
