# Rollout Evidence Driven Planner Refactor Log

This file records execution history for
`docs/planner_rollout_evidence_refactor_plan.md`.

Do not put future plan phases here. Do not put round-by-round records in the
plan file.

## Change Record Protocol

Each completed refactor round should append:

- date and local commit
- selected rollout evidence path
- confirmed-live method chain
- new files created
- old code deleted or reclassified
- verification commands and results
- first-principles reflection outcome
- risks and next action

## Records

### 2026-06-18 Methodology Reset

- Replaced the active primitive planner refactor route with rollout-evidence
  driven extraction.
- Moved the old service-object-first plan to
  `docs/primitive_scheduler_service_refactor_plan_DO_NOT_EXTEND_HISTORY.md`.
- Added `docs/planner_rollout_evidence_refactor_plan.md` as the active plan.
- Kept this separate log file for execution records.
- Added `scripts/planner_refactor_guard.py` and matching tests to keep future
  rounds from writing new records into the plan or extending the closed
  historical plan.
- Updated the `excavator-planner-safe-refactor` skill to point to the new plan
  and require rollout log evidence before migration.
