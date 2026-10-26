# Business rules and validation

- Generate parent/master data before dependent records. Baseline IDs and joins must validate.
- Fixed seed defaults to 20261022; source table CSVs have SHA-256 checksums in source_manifest.json.
- Forecasting uses historical terms and a chronological holdout; anomaly ground truth is not a feature.
- Report MAE, RMSE and last-observation baseline MAE.
- Sections use a target capacity of min(40, largest active room). Count = max(1, ceil(forecast / target capacity)).
- Unmet demand = max(0, forecast - total proposed seats); do not silently reduce demand.
- Faculty must be ACTIVE, skilled for the course and available at the proposed day/slot.
- Weekly workload is capped at max_weekly_hours; no overlapping same-day/same-slot assignments.
- Each section receives at most one faculty assignment.
- Five labelled anomaly fixtures live in ground_truth.csv: faculty outside skill set, workload exceeded, capacity too low, prerequisite violation, duplicate assignment. They are test oracles and are not injected into baseline inputs.
- Events are stored in decision_events. The demo refreshes synthetic source/result tables on rerun and is intended for a single-user demo.
- Room assignment is a simple extension point, not yet jointly optimized with faculty/time slots.
