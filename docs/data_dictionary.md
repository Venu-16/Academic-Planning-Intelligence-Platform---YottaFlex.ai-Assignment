# Data dictionary

IDs are deterministic immutable strings. Dates are ISO `YYYY-MM-DD`; term IDs are `YYYY-TERM`; null `effective_to` means open-ended.

| Entity | Primary key | Fields and rules |
|---|---|---|
| AcademicTerm | term_id | Inclusive start_date and end_date for term-specific eligibility validation |
| Program | program_id | Unique name; department required |
| Course | course_id | program FK, unique code, credits 1-6, level 1-4, elective flag |
| Prerequisite | prerequisite_id | Course and prerequisite-course FKs; no self-edge; effective dates |
| StudentPlan | student_plan_id | Student, program and academic-term FKs, year 1-4; unique student/term |
| RegistrationInterest | interest_id | Plan/course/academic-term FKs, status enum, date, eligibility; unique plan/course/term |
| StudentCourseCompletion | completion_id | StudentPlan/course FKs, completed_on before the plan term; unique plan/course pair |
| Faculty | faculty_id | Department, positive weekly workload cap, ACTIVE/ON_LEAVE/INACTIVE |
| FacultySkill | faculty_skill_id | Faculty/course FKs, skill level 1-5, effective dates |
| Availability | availability_id | Faculty and academic-term FKs, weekday 0-4, slot, availability flag, effective dates |
| Room | room_id | Building, LECTURE/LAB, positive capacity, active flag |
| HistoricalEnrollment | historical_enrollment_id | Course FK, term, eligible, registrations, enrolled, unmet; enrolled <= registrations and unmet = registrations - enrolled |
| Section | section_id | Course/optional room FKs, academic-term FK, section number, day, slot, capacity, demand, finalized lifecycle status |
| WorkloadAssignment | workload_assignment_id | Section/faculty FKs, positive hours, lifecycle status; unique section/faculty |
| PlanningRun | planning_run_id | Seed, model, solver status, notes |
| Forecast | forecast_id | Run/course/target-term FKs, nonnegative enrollment, method, source historical term, historical input values, eligible interest count, fallback flag and reason; historical source term is a label, not a target-calendar FK |
| UnmetDemand | unmet_demand_id | Run/course/academic-term FKs, demand, planned capacity, operational capacity, accommodated, unmet, reason; unmet reconciles against accommodated demand |
| DecisionEvent | event_id | Run FK, entity type and ID, event type, actor, reason, timestamp, JSON payload including prior/new states and reason code for state transitions |

## Cardinality
Program 1:N Course and StudentPlan. StudentPlan 1:N RegistrationInterest and StudentCourseCompletion; Course 1:N RegistrationInterest, StudentCourseCompletion and Section. Faculty N:M Course via FacultySkill. Faculty 1:N Availability. Faculty N:M Section via WorkloadAssignment. PlanningRun 1:N Forecast, UnmetDemand and DecisionEvent.

## Lifecycle
`proposal_status=PROPOSED` identifies every section proposal. Its separate finalized `status` is `OPERATIONAL`, `UNSTAFFED`, `BLOCKED`, or `REJECTED`; a blocked section retains proposal status but contributes zero operational seats. Assignment states are `PROPOSED` before validation and `APPROVED` or `REJECTED` after validation. Legacy database statuses (`ALLOCATED`, `PARTIAL`, `CANCELLED`) remain permitted for historical compatibility and are not rewritten. New section and assignment transitions are appended as run-scoped events; no transition is invented for records predating event capture.

When student completion records are present, an eligible or registered/waitlisted interest for a course with an effective prerequisite requires a completion record for every prerequisite before the target term. Older caller-provided source frames without the completion table remain accepted for compatibility; generated datasets include it.

The CLI defaults to the starter scale (10 programs, 100 courses, 50 faculty, 1,000 student plans). `--scale target` uses 100 programs, 1,000 courses, 500 faculty, and 20,000 student plans; individual dimensions can be overridden with positive `--programs`, `--courses`, `--faculty`, and `--student-plans` values. The source manifest records seed, scale, counts, and CSV checksums.

Operational capacity is reported separately from proposed capacity and counts only sections with a non-rejected faculty assignment, active room with capacity at least the planned section capacity, and no faculty/room timetable conflict. The calculation also checks faculty activity, course skill, availability, workload, and weekday/slot validity. Course unmet demand is `max(0, forecast demand - operational capacity)`; program demand and unmet demand are sums of their courses.

Forecast output records the target term and latest historical source term with the model's historical inputs. Courses with fewer than two historical observations use eligible registration-interest counts when available, otherwise the last enrollment; courses with neither use an explicit zero fallback. If no model training transitions exist, the latest enrollment is used. Fallback application and reason are persisted with each forecast.

Room records contain `room_type` but courses have no required room type/facility fields. Schedule data contains weekday and discrete slot IDs only; there are no slot-time or student-cohort entities. Consequently room-type/facility matching, cohort conflicts, and clock-time overlap between different slot IDs are unsupported. Room and faculty conflicts are checked for identical term/day/slot values.
