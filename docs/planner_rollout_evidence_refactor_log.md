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
- Backed up the old service-object-first plan in git history, then removed it
  from the live tree so future agents do not read stale guidance.
- Added `docs/planner_rollout_evidence_refactor_plan.md` as the active plan.
- Kept this separate log file for execution records.
- Added `scripts/planner_refactor_guard.py` and matching tests to keep future
  rounds from writing new records into the plan or recreating the old plan path.
- Updated the `excavator-planner-safe-refactor` skill to point to the new plan
  and require rollout log evidence before migration.

### 2026-06-18 Priority Correction

- Clarified that refactoring, abstraction, and useful live-code extraction are
  the primary goals.
- Reframed behavior protection as a secondary constraint for confirmed-live
  rollout behavior, not a reason to preserve abandoned or unobserved paths.
- Removed the old historical plan document from the live tree. The backup is git
  history, not a file agents should read before acting.

### 2026-06-18 Baseline Architecture Correction

- Added a required branch baseline reconstruction gate before future planner
  migration slices.
- Added `docs/planner_baseline_architecture_map.md` as a separate architecture
  map so target design is rebuilt from baseline code and rollout evidence
  instead of inferred from the current partially-refactored HEAD.
- Updated the goal prompt, skill, guard, and workflow tests to require the
  baseline architecture map before planner code migration.
