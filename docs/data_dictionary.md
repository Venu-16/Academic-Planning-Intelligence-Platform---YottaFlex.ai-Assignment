# Data dictionary

IDs are deterministic immutable strings. Dates are ISO `YYYY-MM-DD`; term IDs are `YYYY-TERM`; null `effective_to` means open-ended.

| Entity | Primary key | Fields and rules |
|---|---|---|
| AcademicTerm | term_id | Inclusive start_date and end_date for term-specific eligibility validation |
| Program | program_id | Unique name; department required |
| Course | course_id | program FK, unique code, credits 1-6, level 1-4, elective flag |
| Prerequisite | prerequisite_id | Course and prerequisite-course FKs; no self-edge; effective dates |
| StudentPlan | student_plan_id | Student, program FK, term, year 1-4; unique student/term |
| RegistrationInterest | interest_id | Plan/course FKs, term, status enum, date, eligibility; unique plan/course/term |
| Faculty | faculty_id | Department, positive weekly workload cap, ACTIVE/ON_LEAVE/INACTIVE |
| FacultySkill | faculty_skill_id | Faculty/course FKs, skill level 1-5, effective dates |
| Availability | availability_id | Faculty FK, term, weekday 0-4, slot, availability flag, effective dates |
| Room | room_id | Building, LECTURE/LAB, positive capacity, active flag |
| HistoricalEnrollment | historical_enrollment_id | Course FK, term, eligible, registrations, enrolled, unmet; enrolled <= registrations and unmet = registrations - enrolled |
| Section | section_id | Course/optional room FK, term, section number, day, slot, capacity, demand, lifecycle status |
| WorkloadAssignment | workload_assignment_id | Section/faculty FKs, positive hours, status; unique section/faculty |
| PlanningRun | planning_run_id | Seed, model, solver status, notes |
| Forecast | forecast_id | Run/course FKs, target term, nonnegative enrollment, model |
| UnmetDemand | unmet_demand_id | Run/course FKs, demand, planned capacity, operational capacity, accommodated, unmet, reason; unmet reconciles against accommodated demand |
| DecisionEvent | event_id | Run FK, entity, event, actor, reason, JSON payload |

## Cardinality
Program 1:N Course and StudentPlan. StudentPlan 1:N RegistrationInterest; Course 1:N RegistrationInterest. Faculty N:M Course via FacultySkill. Faculty 1:N Availability. Course 1:N Section. Faculty N:M Section via WorkloadAssignment. PlanningRun 1:N Forecast, UnmetDemand and DecisionEvent.

## Lifecycle
Sections: PROPOSED -> ALLOCATED/PARTIAL/CANCELLED. Assignments: PROPOSED -> APPROVED/REJECTED. The demo persists proposal outcomes and a run event; production transition enforcement belongs in a service layer.

Operational capacity is reported separately from proposed capacity and counts only sections with a non-rejected faculty assignment, active room with capacity at least the planned section capacity, and no faculty/room timetable conflict. The calculation also checks faculty activity, course skill, availability, workload, and weekday/slot validity. Course unmet demand is `max(0, forecast demand - operational capacity)`; program demand and unmet demand are sums of their courses.

Room records contain `room_type` but courses have no required room type/facility fields. Schedule data contains weekday and discrete slot IDs only; there are no slot-time or student-cohort entities. Consequently room-type/facility matching, cohort conflicts, and clock-time overlap between different slot IDs are unsupported. Room and faculty conflicts are checked for identical term/day/slot values.
