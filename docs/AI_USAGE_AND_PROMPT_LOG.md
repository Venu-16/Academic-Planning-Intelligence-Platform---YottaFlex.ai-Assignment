# AI usage and prompt log

## Scope and evidence

This log records substantial AI-assisted work visible in the retained Copilot conversation, checked-out repository, generated artifacts, and Git history as inspected on 2026-10-29. The full historical chat export and per-turn timestamps/tool telemetry are not present in the repository. Earlier entries are therefore ordered by the retained conversation, not assigned invented dates. The exact model used for each historical turn is also unavailable.

The conversation was conducted with GitHub Copilot Chat in VS Code. Repository work used local file inspection, PowerShell/Python commands, and patch-based edits where those tool actions are present in the retained session. The records do not establish which individual lines were authored by AI versus the developer; Git commit authorship alone is not proof of authorship or review.

## Chronological work record

### 1. End-to-end acceptance and numerical audit

- **Prompt/task:** The user asked for an evidence-based acceptance audit: run starter and target generation, inspect actual exports, verify scale, anomaly cases, ground-truth separation, numerical reconciliation, reproducibility, PostgreSQL tests, and document results. Follow-up prompts specifically requested section lifecycle reconciliation, per-course unmet-demand formulas, and direct checks of room capacities and conflicts.
- **AI contribution:** Inspected generator, pipeline, planning, validation, forecasting, optimizer, tests, and exports; calculated metrics from exported records; documented profile distinctions and identified stale historical metrics. The retained records show changes across [`src/academic_planner/planning.py`](../src/academic_planner/planning.py), [`src/academic_planner/generator.py`](../src/academic_planner/generator.py), [`src/academic_planner/validation.py`](../src/academic_planner/validation.py), [`src/academic_planner/pipeline.py`](../src/academic_planner/pipeline.py), tests, and the acceptance report over the project history.
- **Repository evidence:** Commits `3395402` (“Complete academic planner validation”), `fa369a1` (“Add target-scale lifecycle acceptance checkpoint”), and `76584b5` (“target data generation and pipe line checking”) include application, test, and report files. Commit metadata records the developer's Git identity, but does not independently attribute individual code contributions.
- **Verification:** Historical audit evidence includes generated `validation_report.json`, CSV reconciliation, anomaly tests, forecast evaluation, and PostgreSQL setup/results. Current output values and the latest test run are summarized in [`reports/acceptance_audit_20261029.md`](../reports/acceptance_audit_20261029.md).
- **Personal review:** The user explicitly required actual execution, export inspection, and no fabricated claims. No retained statement identifies which code edits the user personally made or which review steps were performed outside the chat.

### 2. Forecast provenance and ground-truth separation

- **Prompt/task:** The acceptance request required inspecting generator, feature preparation, exports, and validation; proving that ground truth is separately exported and does not influence forecasts or allocation; and checking reproducibility.
- **AI contribution:** Reviewed [`src/academic_planner/forecasting.py`](../src/academic_planner/forecasting.py), [`src/academic_planner/generator.py`](../src/academic_planner/generator.py), and pipeline exports. The implementation uses historical enrollment features and eligible registration-interest counts for explicit sparse-history fallbacks; ground-truth fixtures are exported separately. Forecast outputs contain source-term and fallback traceability fields.
- **Resulting changes:** The current repository includes these behaviors and corresponding tests. The retained record does not support a reliable claim that any specific provenance field was added by one prompt or by AI alone.
- **Verification:** `tests/test_forecasting_evaluation.py`, `tests/test_ground_truth.py`, generated `forecasts.csv`, and `ground_truth.csv`; same-seed source/forecast reproducibility was previously audited. Full allocation output is not claimed to be deterministic.
- **Further validation:** This documentation task inspected code and outputs but did not independently rerun seed-comparison checks.

### 3. Prerequisite completion, lifecycle, and allocation diagnostics

- **Prompt/task:** The user asked to review explicit section lifecycle states, prevent blocked proposals from contributing operational seats, add student prerequisite-completion representation and validation if needed, and document PostgreSQL integration setup.
- **AI contribution:** The retained repository includes student completion generation and validation, operational section status accounting, capacity reconciliation, and unstaffed-section diagnostics.
- **Files identifiable in history:** [`src/academic_planner/generator.py`](../src/academic_planner/generator.py), [`src/academic_planner/validation.py`](../src/academic_planner/validation.py), [`src/academic_planner/planning.py`](../src/academic_planner/planning.py), [`src/academic_planner/allocation_diagnostics.py`](../src/academic_planner/allocation_diagnostics.py), [`src/academic_planner/lifecycle.py`](../src/academic_planner/lifecycle.py), [`src/academic_planner/schema.sql`](../src/academic_planner/schema.sql), and focused tests.
- **Verification:** Tests in `tests/test_scale_and_lifecycle.py`, `tests/test_capacity_reconciliation.py`, `tests/test_allocation_diagnostics.py`, `tests/test_operational_capacity.py`, and `tests/test_ground_truth.py`; the generated validation report is clean for each current profile.
- **Personal review:** The user's prompts explicitly required not breaking older generation commands and validating behavior. No independent record describes personal code authorship.

### 4. Room inventory and scarcity scenario

- **Prompt/task:** The user asked to investigate the target room bottleneck before changing code, preserve hard room/faculty constraints, improve normal synthetic inventory only when justified, keep a reproducible scarcity mode, and rerun tests and both profiles. A later prompt requested final readiness metrics and corrected documentation.
- **AI contribution:** Investigated the room generator and timetable model, then changed the normal target room inventory and exposed the constrained configuration as `--room-scarcity`. The current implementation is in [`src/academic_planner/generator.py`](../src/academic_planner/generator.py), [`src/academic_planner/cli.py`](../src/academic_planner/cli.py), and [`src/academic_planner/pipeline.py`](../src/academic_planner/pipeline.py), with regression coverage in `tests/test_scale_and_lifecycle.py`.
- **Verification:** Current exports directly show 2,160 target proposals: 2,160 roomed and 1,690 operational under the normal inventory; the scarcity export has 400 roomed, 1,760 room-blocked, 348 operational, and 52 unstaffed. Each export's source validation report has zero issues. The values and paths are in the acceptance audit.
- **Correction/qualification:** An older report and README conflated the earlier scarcity result with the normal target baseline. The current docs now separate the two profiles. Solver output and successful command exit are not equivalent to every proposal becoming operational.

### 5. Handoff and continued execution

- **Prompt/task:** The user requested a complete context handoff for a new Copilot account, then continued the room-inventory work, requested submission-readiness checks, ran the starter/target project, and asked to launch Streamlit.
- **AI contribution:** Created [`docs/COPILOT_HANDOFF.md`](COPILOT_HANDOFF.md), refreshed README and acceptance material in prior work, ran the documented CLI profiles, and launched the dashboard. The first dashboard launch exposed a missing Plotly installation in the Python 3.12 environment; Plotly was installed there (it is already declared in `pyproject.toml`) and the dashboard then loaded at localhost.
- **Verification:** The current export metrics are recalculated in this task. The preceding full-suite result was 94 passed and 3 skipped; this task runs the requested checks again and records the actual result in the acceptance audit.
- **Personal review:** The user provided the explicit acceptance criteria and reported the intended next task. The retained record does not contain a detailed first-person account of dashboard or code review.

### 6. Final documentation update

- **Prompt/task:** The user requested execution readiness, honest prompt history, engineering decision rationale, concise setup documentation, current Git/publication status, and final test/check results without committing or pushing.
- **AI contribution:** This task creates this log and [`docs/DESIGN_DECISIONS.md`](DESIGN_DECISIONS.md), updates [`README.md`](../README.md), and corrects stale profile and capacity claims in the acceptance report.
- **Verification:** Actual CSV/JSON rows and manifests were read, Git status/remotes/history were inspected, and the requested test, compile, and diff checks were run. Results are reported without claiming a database test run unless it is specifically evidenced.

## Developer review and remaining input needed

The retained evidence supports that the developer set detailed acceptance constraints, repeatedly requested verification against actual generated output, and instructed the AI not to fabricate results or publish without approval. It does **not** capture a complete prompt export, all prompt timestamps, a line-by-line human review record, or a supported account of which code the developer personally wrote or changed.

Before submission, the developer should add a short first-person statement describing what they personally inspected, tested, corrected, and understand, and attach/export the original prompt history if the assessment requires the complete transcript. Do not present this reconstructed log as a complete verbatim archive.
