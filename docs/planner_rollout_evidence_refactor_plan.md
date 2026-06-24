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
`docs/planner_current_architecture.md`, with detailed inventory in
`docs/planner_current_code_architecture_plan.md`. Earlier backend abstraction
plans and the older SVG flow are archived under
`docs/refactor_history/planner/` as historical context, not implementation
source of truth.

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

## Per-Round Skill Compliance Prompt Block

Every refactor/audit prompt and every executor delegation prompt in this
workflow must expose these mandatory skill rules explicitly instead of relying
on memory or implied context:

- Target lock first: verify cwd, branch/status, HEAD, and expected dirty state;
  stop on mismatch instead of self-correcting repo state.
- Event-driven loop: after dispatching one executor slice, the planner yields
  until a callback, blocker, or user correction arrives. Do not poll or
  speculate while waiting.
- Planner closure gate: executor green is not closure. The planner must audit
  target lock, scope, diff/status, docs, behavior impact, and planner-side
  verification before accepting a slice or dispatching the next one.
- Reflection cadence: lightweight reflection after every callback; deep
  reflection after every three accepted implementation callbacks and after any
  failed or misaligned callback. Do not dispatch the fourth implementation
  slice until the deep reflection is recorded or the planner stops for user
  confirmation.
- Executor boundary: executor callbacks are fact-only. The executor must not
  choose next tasks, write strategy, or broaden scope.
- Configuration discipline: every prompt starts with `thinking: xhigh` or
  `thinking: high`; do not invent model, tool, CLI, env var, path, branch,
  feature flag, schema, credential, port, or runtime config values; do not
  change runtime config unless explicitly allowed and verified.
- Refactor direction: protection is a constraint, not the objective. Do not
  preserve obsolete/test-only private glue by default once callers/tests can use
  focused owners or services directly.
- Architecture boundary: do not pass planner `self` into focused modules; do
  not add broad pass-through objects, generic blackboards, broad config bags,
  anemic services, or one-method-per-private-method callback bags.
- Behavior guardrails: preserve public schema, token order/dimensions, branch
  order, reason strings, reset timing, default legacy FSM backend, and
  BT/VLM/LLM fail-fast status unless the user explicitly approves a semantic
  change.

## Deep Reflection Reference Set

Every lightweight or three-iteration reflection must name the concrete
reference files it is comparing against. Do not write a reflection from memory,
from an unnamed old plan, or from the current code shape alone.

Primary architecture references:

- `docs/planner_current_architecture.md`: the current actual architecture
  diagram, package lanes, shell boundary, runtime flow, and parked/restored
  path policy.
- `docs/planner_primitive_interface_standard.md`: the active interface/core
  boundary standard, maturity wording, and public compatibility constraints.
- `docs/planner_scheduling_backend_design.md`: the current future-backend
  design guide and backend-ready contract checklist.

Current implementation references:

- `docs/planner_current_code_architecture_plan.md`: the live current-code
  architecture inventory, file responsibilities, line-count facts, and next
  responsibility clusters.
- `docs/refactor_history/planner/`: archived older SVG, phase design, package
  target, shell target, and migration simulation documents; use only as
  historical context when needed.
- Current code and focused tests, especially
  `testbed/policies/hybrid/primitive_planner.py`, focused modules under
  `testbed/planner/`, and the focused `tests/test_primitive_*.py` suites.

Historical/context references:

- `docs/planner_baseline_architecture_map.md`: branch-created baseline and
  rollout-evidence context. Use it to prevent current-HEAD drift, but do not
  treat it as a replacement for the current implementation standard.

Workflow references:

- `docs/planner_rollout_evidence_refactor_plan.md`: this active route,
  hard-rule block, stop conditions, and verification expectations.
- `docs/planner_rollout_evidence_refactor_log.md`: accepted callbacks,
  closure audits, failures, and previous reflection decisions.
- `docs/prompts/planner_rollout_evidence_goal_prompt.md`: prompt-surface
  contract for recursive planner/executor continuation.
- `AGENTS.md`: repository governance, large-file policy, documentation sync,
  semantic confirmation, and planner state-machine architecture rules.

Three-iteration deep reflection must explicitly answer against this set:

- whether the last accepted implementation callbacks moved toward the SVG and
  interface standard rather than preserving policy-private glue;
- whether the current code inventory and effect-boundary docs are stale after
  the callbacks;
- whether historical baseline or rollout evidence changes the classification of
  any path under review;
- whether verification is proving public behavior contracts instead of merely
  proving local green tests;
- whether the next slice should continue, widen within one responsibility
  cluster, narrow, or stop for user confirmation.

## Delegated Executor Callback Rule

When the audit/refactor thread delegates a bounded code slice to a separate
executor thread, the delegation prompt must require the executor to call
Codex `send_message_to_thread` back to the source/refactor thread before the
executor's final local reply.

The callback must be fact-only and include:

- target lock
- TDD red
- changed files
- core factual change
- verification
- behavior impact
- docs status
- git status after
- HEAD after

Every follow-up executor prompt generated by the refactor thread must repeat
this callback requirement recursively, so delegated execution remains
closed-loop and the refactor thread owns audit, documentation sync, and next
direction decisions.

Every follow-up executor prompt must also repeat the three-iteration reflection
gate explicitly. The executor does not write the reflection or choose strategy,
but its callback must preserve enough factual slice evidence for the
refactor/audit thread to decide whether the next planner turn is due for the
three-round deep-reflection stop before another executor dispatch.

## Thinking-Effort Dispatch Rule

Refactor/audit threads for this workflow must run with explicit
`thinking: xhigh`. This includes source-thread audit, documentation sync,
three-iteration reflection, direction decisions, and executor prompt
generation.

Every executor delegation prompt must explicitly state the executor thinking
effort as either `thinking: high` or `thinking: xhigh`. When the Codex thread
tool exposes a thinking parameter, the refactor/audit thread should pass the
same value at tool level instead of relying on prompt text alone.

The thinking-effort requirement is part of the recursive callback contract:
when an executor is instructed to call `send_message_to_thread` back to the
source/refactor thread, the prompt must also tell the executor that future
executor prompts generated by the refactor thread must keep this explicit
thinking-effort rule. This prevents hallucination or prompt drift from silently
weakening the reasoning mode.

## Three-Iteration Reflection Rule

After every three bounded executor implementation rounds, the refactor/audit
thread must pause before dispatching another executor task and record a
three-iteration reflection in `docs/planner_rollout_evidence_refactor_log.md`.
This reflection is owned by the refactor/audit thread, not the executor.

The reflection must answer:

- whether the last three rounds moved the implementation closer to the Deep
  Reflection Reference Set above, especially
  `docs/planner_current_architecture.md`,
  `docs/planner_scheduling_backend_design.md`, and
  `docs/planner_primitive_interface_standard.md`
- the largest remaining architecture gap
- the next core bounded slice
- whether the workflow is over-protecting old code or creating anemic
  pass-through facades
- any direction correction before the next executor prompt

Do not dispatch the fourth executor round in a sequence until this reflection is
recorded or the refactor/audit thread explicitly stops for user confirmation.
This rule must be copied into both sides of the workflow prompt surface: the
refactor/audit prompt must name the current accepted-slice count and whether the
next callback triggers the gate, and the executor prompt must remind the
executor to return fact-only evidence while leaving the deep reflection and next
dispatch decision to the refactor/audit thread.

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
