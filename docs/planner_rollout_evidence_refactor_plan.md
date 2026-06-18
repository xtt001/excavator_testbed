# Rollout Evidence Driven Planner Refactor Plan

Status: **active source of truth**.

This plan replaces the older service-object-first planner refactor route. The
old route is kept only in git history, not as a live repository document. Do not
read or extend the old plan during future refactor rounds.

The active goal is not to keep editing `PrimitivePlannerACTPolicy` until it
looks smaller, and not to treat the current partially-refactored HEAD as the
architecture source of truth. The active goal is to reconstruct the branch
baseline planner logic from the earliest branch baseline, overlay real rollout
evidence, draw the intended architecture, then move confirmed-live behavior
directly into new focused runtime modules and delete the old shell path once
parity is proven.

Change records do not belong in this file. Record execution history in
`docs/planner_rollout_evidence_refactor_log.md`.

## Priority Rule

The primary goal is refactoring: reduce coupling, extract the useful live
logic, clarify abstraction boundaries, and delete old inline paths after parity.

Protection is secondary. It exists to keep confirmed-live behavior intact while
the refactor happens. Protection must not preserve abandoned, unobserved,
test-only, or obsolete code by default, and it must not justify adding adapter
layers that make the main logic harder to understand.

When these goals conflict, prefer the smallest evidence-backed refactor that can
delete or reclassify old code. Stop for user confirmation if the only way to
"protect" behavior is to keep unclear old logic alive.

## Baseline Architecture Reconstruction Gate

Every migration round must start from the branch baseline, not from whatever
shape the current refactor stack has accumulated. The current branch baseline is
`f004d5ae2b38630456e3b1a58c602f655eb5de12`; confirm it with
`git merge-base HEAD origin/fs/v2_4-refactor-tests` when remote refs are already
available locally. Do not fetch or pull just to refresh this value during a
no-remote round.

Before choosing a migration slice, update
`docs/planner_baseline_architecture_map.md` with:

- the branch baseline commit used
- the baseline call graph from rollout entry to planner decision, tokens,
  low-level policy dispatch, effects, and debug reporting
- the rollout evidence that proves which baseline paths are live
- the target module boundaries and data flow that the next refactor should move
  toward
- code that is not observed and should be treated as `not-observed`,
  `test-only`, `compatibility`, or `dead-candidate`

The architecture map is not a change log. Do not record round-by-round changes
there. Record execution history in
`docs/planner_rollout_evidence_refactor_log.md`.

Current HEAD can be inspected as a patch queue or implementation history, but it
must not define the target architecture by itself. If the architecture map is
missing, stale, or based mainly on the current messy refactor state, stop and do
an architecture reconstruction round before touching planner code.

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
- method chain from the log-observed behavior back to branch baseline code
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
2. Branch baseline: confirm the baseline commit and reconstruct the baseline
   planner call graph in `docs/planner_baseline_architecture_map.md`.
3. Evidence selection: choose one rollout log or artifact and record the exact
   path.
4. Runtime trace: map observed rollout behavior to skill/reason/effect/token
   path and branch-baseline methods.
5. Slice decision: choose one `confirmed-live` responsibility chain from the
   architecture map.
6. Contract tests first: add tests for the new file API, deletion guard, and
   parity surface.
7. New module first: implement the focused runtime module outside the large
   policy file.
8. Thin bridge: update the old policy shell only to call the new module and
   apply returned effects.
9. Parity: run focused tests, golden/debug/token/config checks, and the rollout
   comparison required by the evidence packet.
10. Delete: remove old inline implementation when parity passes.
11. Record: append the round result to
    `docs/planner_rollout_evidence_refactor_log.md`.

## Stop Conditions

Stop and ask for a decision when:

- no real rollout log proves the path is live
- branch baseline architecture has not been reconstructed for the slice
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
