# Rollout Evidence Driven Planner Refactor Plan

Status: **active source of truth**.

This plan replaces the older service-object-first planner refactor route. The
old route is kept only as history in
`docs/primitive_scheduler_service_refactor_plan_DO_NOT_EXTEND_HISTORY.md`.

The active goal is not to keep editing `PrimitivePlannerACTPolicy` until it
looks smaller. The active goal is to identify planner behavior that is proven
live by real rollout logs, move that behavior into new focused runtime modules,
and delete the old shell path once parity is proven.

Change records do not belong in this file. Record execution history in
`docs/planner_rollout_evidence_refactor_log.md`.

## First-Principles Reflection Gate

Every planner refactor round starts by answering these questions in the working
notes or handoff before code edits:

- What real rollout log proves this path is used?
- What exact skill, switch reason, token source, debug field, or runtime effect
  was observed?
- What user-visible behavior must remain identical?
- What new file will own the live responsibility?
- Which old code will be deleted after parity passes?
- Are we reducing coupling, or only adding another adapter layer?
- Are we following this plan, or drifting back into patching the large file?

If the round cannot answer the rollout-evidence questions, it is an audit
round, not a migration round.

## Rollout Evidence Gate

A path is eligible for migration only when it has at least one evidence packet:

- rollout artifact path or command that produced it
- observed skill sequence and switch reasons
- relevant debug keys, token source, or runtime effect payload
- method chain from the log-observed behavior back to current code
- parity command that can compare old and new behavior

Classify code before moving it:

- `confirmed-live`: observed in a real rollout log and eligible for extraction
- `not-observed`: present in code but absent from the selected rollout evidence
- `test-only`: required only by tests, diagnostics, or compatibility facades
- `compatibility`: public or legacy entry that must remain as a thin wrapper
- `dead-candidate`: no rollout evidence and no required compatibility owner

Only `confirmed-live` paths should receive new runtime implementation work.
`test-only`, `compatibility`, and `dead-candidate` paths should be documented in
the round record and removed when their owner is no longer needed.

## New-File Extraction Rule

Do not implement new planner behavior inside large legacy files. For
`PrimitivePlannerACTPolicy`, allowed edits are limited to:

- import a new focused module
- build explicit input data for the new module
- call the new module
- apply returned adapter-side effects
- delete old implementation after parity passes

The new file must be named by stable responsibility, not by the old method name.
It must accept explicit inputs and return explicit results or effects. It must
not receive `PrimitivePlannerACTPolicy`, call shell-private lifecycle methods,
or become a pass-through wrapper around old private methods.

## Deletion Rule

Extraction is incomplete until the old live implementation path is removed or
reclassified. After tests and rollout parity pass:

- delete the old inline logic from the large file
- keep only the public compatibility entry if still required
- move test coverage from private facade tests to the new module contract
- document any retained compatibility wrapper and its removal condition

If parity passes and no compatibility owner remains, do not preserve the old
code for comfort.

## Workflow

1. Target lock: record host, branch, clean/dirty status, HEAD, and no-push
   policy.
2. Evidence selection: choose one rollout log or artifact and record the exact
   path.
3. Runtime trace: map observed rollout behavior to skill/reason/effect/token
   path and current methods.
4. Slice decision: choose one `confirmed-live` responsibility chain.
5. Contract tests first: add tests for the new file API, deletion guard, and
   parity surface.
6. New module first: implement the focused runtime module outside the large
   policy file.
7. Thin bridge: update the old policy shell only to call the new module and
   apply returned effects.
8. Parity: run focused tests, golden/debug/token/config checks, and the rollout
   comparison required by the evidence packet.
9. Delete: remove old inline implementation when parity passes.
10. Record: append the round result to
    `docs/planner_rollout_evidence_refactor_log.md`.

## Stop Conditions

Stop and ask for a decision when:

- no real rollout log proves the path is live
- a proposed module would mainly wrap old private methods
- preserving branch order, threshold, reason string, token schema, debug schema,
  rollout schema, or reset timing is uncertain
- the old path cannot be deleted or reclassified after the migration
- the work starts expanding across multiple responsibility chains

## Required Verification

Each migration round chooses the smallest useful subset, but must justify the
choice:

- new focused tests for the new runtime module
- deletion or compatibility tests for the old path
- backend/runtime/config tests when backend contracts are touched
- golden trace, debug schema, token contract, and rollout parity checks when
  those surfaces are touched
- `python -m compileall` for changed Python modules
- `git diff --check`
- `python scripts/planner_refactor_guard.py --check-plan-contract`
- `python scripts/planner_refactor_guard.py --check-skill-contract`

## Hook Policy

The repository pre-commit config owns three local hooks:

- `planner-refactor-history-guard`: blocks edits to historical closed plans
- `planner-refactor-plan-contract`: validates the active plan/log split
- `planner-refactor-skill-contract`: validates the active skill points here

The hook script is `scripts/planner_refactor_guard.py`. If the workflow changes,
update tests first.
