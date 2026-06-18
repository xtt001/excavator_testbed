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
directly into new focused runtime modules. Code without mainline evidence is
kept out of the target architecture and parked as legacy/diagnostic material
until an explicit later cleanup review decides whether removal is warranted.

Change records do not belong in this file. Record execution history in
`docs/planner_rollout_evidence_refactor_log.md`.

## Priority Rule

The primary goal is refactoring: reduce coupling, extract the useful live
logic, and clarify abstraction boundaries. Removing functions is not the
primary goal; non-mainline code should first be isolated, reclassified, or
parked so the architecture can be split cleanly without treating deletion as
the measure of progress.

Protection is secondary. It exists to keep confirmed-live behavior intact while
the refactor happens. Protection must not preserve abandoned, unobserved,
test-only, or obsolete code by default, and it must not justify adding adapter
layers that make the main logic harder to understand.

When these goals conflict, prefer the smallest evidence-backed refactor that can
move live behavior behind a clear boundary and park unclear legacy code outside
the mainline. Stop for user confirmation if the only way to "protect" behavior
is to keep unclear old logic entangled with the new architecture.

## Baseline Architecture Reconstruction Gate

Every migration round must start from the branch-created baseline, not from
whatever shape the current refactor stack or latest pushed branch ref has
accumulated. The current branch-created baseline is
`152350e3ed9a8816ca8d685195fc8f297ab3fcec`, recorded in the local reflog as
`branch: Created from tx/2_4-YuLong_Planner` for `fs/v2_4-refactor-tests`.
Do not substitute `origin/fs/v2_4-refactor-tests`, a later pushed checkpoint, or
`git merge-base HEAD origin/fs/v2_4-refactor-tests` for this creation baseline.
Do not fetch or pull just to refresh this value during a no-remote round.

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

The current code-grounded architecture target is
`docs/planner_current_code_architecture_plan.md`. The earlier
`docs/planner_execution_backend_abstraction_plan.md` and
`docs/planner_execution_abstraction_flow.svg` remain supporting concept
references, but the current-code plan is the implementation source of truth.

The plan intentionally starts with the public tick execution template before
introducing pluggable decision backends. Do not jump straight to behavior-tree,
VLM, or legacy-FSM backend migration while the baseline execution loop remains
implicit in `PrimitivePlannerACTPolicy.predict()`.

Use `docs/planner_evidence_trace_tool.md` and the `tb-planner-evidence`
classifier to turn rollout JSONL, planner trace, rollout summary, or future
instrumented evidence JSONL into a retention decision table before selecting a
migration slice. Successful mainline evidence that does not show a capability
contributing, or failure evidence that does not highlight it as a missing cause,
is enough to classify non-compatibility code as `dead-candidate`; the immediate
action is to keep it out of the mainline migration and park it as legacy or
diagnostic material, not to make deletion the current task.

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
- Which old code will be reclassified, parked, or later cleanup-reviewed after
  parity passes?
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
- `not-observed`: absent from selected evidence but not yet eligible for a
  cleanup decision because evidence is below threshold or explicit protection
  exists
- `test-only`: required only by tests, diagnostics, or compatibility facades
- `compatibility`: public or legacy entry that must remain as a thin wrapper
- `dead-candidate`: no rollout evidence and no required compatibility owner

Only `confirmed-live` paths should receive new runtime implementation work.
`test-only`, `compatibility`, and `dead-candidate` paths should be documented in
the round record. `dead-candidate` paths should not be migrated into the
execution-kernel/backend architecture; keep them in legacy parking until legacy
config, diagnostic, test-only, and compatibility owners are audited.

## New-File Extraction Rule

Do not implement new planner behavior inside large legacy files. For
`PrimitivePlannerACTPolicy`, allowed edits are limited to:

- import a new focused module
- build explicit input data for the new module
- call the new module
- apply returned adapter-side effects
- replace old inline ownership with a thin facade, compatibility owner, or
  legacy parking record after parity passes

The new file must be named by stable responsibility, not by the old method name.
It must accept explicit inputs and return explicit results or effects. It must
not receive `PrimitivePlannerACTPolicy`, call shell-private lifecycle methods,
or become a pass-through wrapper around old private methods.

## Parking And Reclassification Rule

Extraction is incomplete until the old live implementation path is either moved
behind the new boundary or explicitly reclassified. After tests and rollout
parity pass:

- keep only a thin public compatibility entry if still required
- park non-mainline code as legacy, diagnostic, test-only, or compatibility
  material with a documented owner
- move test coverage from private facade tests to the new module contract
- document any retained compatibility wrapper, parking owner, and later cleanup
  condition

Do not preserve old code only for comfort, but also do not make removal the
current architecture goal. Removal is a later cleanup action after the owner
audit and architecture split make the old path clearly unnecessary.

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
10. Park/reclassify: leave only the thin compatibility facade or legacy parking
    owner for old code that is no longer part of the mainline architecture.
11. Record: append the round result to
    `docs/planner_rollout_evidence_refactor_log.md`.

## Stop Conditions

Stop and ask for a decision when:

- no real rollout log proves the path is live
- branch baseline architecture has not been reconstructed for the slice
- a proposed module would mainly wrap old private methods
- preserving branch order, threshold, reason string, token schema, debug schema,
  rollout schema, or reset timing is uncertain
- the old path cannot be parked, reclassified, or assigned a compatibility owner
  after the migration
- the work starts expanding across multiple responsibility chains

## Required Verification

Each migration round chooses the smallest useful subset, but must justify the
choice:

- new focused tests for the new runtime module
- parking, reclassification, or compatibility tests for the old path
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
