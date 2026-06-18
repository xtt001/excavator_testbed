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
- old code parked, reclassified, or explicitly cleanup-reviewed
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

### 2026-06-18 Baseline Code Understanding Round

- Scope: code understanding only; no planner runtime code, tests, scripts, or
  behavior were changed.
- Branch constraint audit: local checkout was on `fs/v2_4-refactor-tests`, but
  HEAD was `e306eb3 Require baseline architecture reconstruction`, which is
  later local exploration history.
- Baseline correction: the branch-created baseline is
  `152350e3ed9a8816ca8d685195fc8f297ab3fcec`, not
  `f004d5ae2b38630456e3b1a58c602f655eb5de12`. Local reflog records
  `fs/v2_4-refactor-tests` as created from `tx/2_4-YuLong_Planner` at
  `152350e` on 2026-06-04 13:09:01 +0800. The later `f004d5a` ref is only a
  pushed checkpoint and must not be treated as the creation baseline.
- Baseline source used for architecture reconstruction: `152350e`, read through
  local `git show` paths without fetch, pull, or push.
- Current HEAD treatment: inspected only as patch history and workflow context;
  it was not used as the target architecture source of truth.
- Baseline method chain recorded in
  `docs/planner_baseline_architecture_map.md`: rollout/eval calls
  `PrimitivePlannerACTPolicy.predict()`, `predict()` updates boundary/dig
  progress, `_maybe_switch_skill()` runs the inline FSM branch order directly
  inside `primitive_planner.py`, and `_set_skill()` plus branch-local code apply
  side effects before dispatching scripted/pre-dig/ACT action.
- Baseline data-flow map recorded: active skill, counters, token arrays,
  pending return/dig state, coverage corridor state, debug/summary facts, and
  low-level policy reset timing are all owned by the large policy adapter at
  `152350e`. There is no baseline `PlannerBlackboard`,
  `PlannerConditioningState`, `LegacyStateMachineBackend`, or `DigCoverageMixin`
  source-of-truth boundary.
- No rollout evidence packet was selected. No path was classified
  `confirmed-live`; future migration slices must still bind a real rollout
  artifact, observed skill/reason/token/debug signal, branch-baseline method
  chain, and parity command.
- Cleanup strategy was not executed. The architecture map now lists candidate
  docs/hooks/scripts to review for preservation before any later selective
  reset or code rollback.

### 2026-06-18 Selective Baseline Code Rollback And Backend Analysis

- Scope: selective code rollback plus architecture analysis only; no planner
  behavior migration was implemented.
- Code rollback: restored planner/runtime/eval/data/policy code and ordinary
  tests to branch-created baseline `152350e`.
- Preserved artifacts: current `docs/**`, `AGENTS.md`, `.githooks/pre-commit`,
  `.pre-commit-config.yaml`, `scripts/planner_refactor_guard.py`, and
  `tests/test_planner_rollout_refactor_workflow.py`.
- Verification of rollback shape: `testbed/policies/hybrid/primitive_planner.py`
  is 6516 lines and has no diff from `152350e`.
- Added `docs/planner_execution_backend_abstraction_analysis.md` to analyze the
  target shape: first extract the public tick execution template from the
  state-machine-coupled giant planner, then put state machine, behavior tree,
  VLM, and future decision schemes behind one effect-oriented backend protocol.
- No rollout evidence packet was selected. No path was classified
  `confirmed-live`; future code migrations still require rollout/golden parity.

### 2026-06-18 Execution Backend Architecture Plan

- Scope: architecture planning only; no planner runtime code was changed.
- Added `docs/planner_execution_backend_abstraction_plan.md` as the active
  architecture plan for the execution-kernel and decision-backend route.
- The planned target is:
  `PrimitivePlannerACTPolicy` public adapter -> primitive planner execution
  kernel -> capability port -> decision backend -> validated planner effects.
- The first recommended code slice is execution-template extraction from
  `predict()`, while preserving `_maybe_switch_skill()` as the only decision
  behavior until rollout or golden-trace parity is locked.
- Updated the active refactor plan and goal prompt to read the new architecture
  plan and diagram before future migration work.
- No rollout evidence packet was selected. No path was classified
  `confirmed-live`; future code migrations still require rollout/golden parity.

### 2026-06-18 Planner Evidence Trace Tool

- Scope: evidence tooling and documentation only; no planner runtime behavior
  was changed and no planner code was deleted.
- Added `testbed/planner/evidence_trace.py` as the stable evidence schema,
  rollout-log converter, planner-trace/summary converter, conservative
  classifier, and JSON/Markdown report writer.
- Added `testbed/cli/planner_evidence.py` and `tb-planner-evidence` for
  classifying rollout JSONL, planner trace, rollout summary, and future
  instrumented evidence JSONL.
- Added focused tests:
  `tests/test_planner_evidence_trace.py` and
  `tests/test_planner_evidence_cli.py`.
- Added `docs/planner_evidence_trace_tool.md` as the tool source of truth and
  updated the active plan and goal prompt to require evidence classification
  before migration slices.
- Evidence packet analyzed:
  `runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/rollouts/rollout_000.jsonl`,
  its `rollout_000_planner_trace.json`, and `rollout_000_summary.json`.
- Generated reports:
  `docs/planner_evidence_reports/2026-06-18-baseline-aggregate_tx24.json` and
  `docs/planner_evidence_reports/2026-06-18-baseline-aggregate_tx24.md`.
- Initial retention decision from this evidence packet:
  retain-and-migrate the execution tick, FSM skill switch, action dispatch,
  goal token, dig-cut token, dig-depth-profile token, return-target token,
  return-relocate token, return-start-envelope token, dig progress metric,
  dig-to-carry gate, carry-to-dump gate, dump-to-return gate, return-to-dig
  gate, and coverage corridor logic.
- Reporting decision: retain debug state, rollout summary, and planner trace at
  reporting boundaries.
- Compatibility decision: retain `PrimitivePlannerACTPolicy` and
  `PrimitivePlannerACT5PPolicy` as compatibility owners for now.
- Hold decision: `token.cell_entry` and `gate.pre_dig_align` were not observed
  in this evidence packet and are classified `hold-unobserved`, not delete
  candidates.
- Deletion decision: delete no code from this single report. Future deletion
  requires broader Unity baseline coverage, explicit dead-candidate catalog
  marking, parity, and compatibility checks.

### 2026-06-18 Mainline Delete-Candidate Correction

- Scope: evidence classification update only; no planner runtime behavior was
  changed and no planner code was deleted.
- User decision: the `planner_compare_20260616_x99/aggregate_tx24` rollout is
  the most successful current mainline evidence packet. If `cell_entry` and
  `pre_dig_align` were not enabled or used there, they should not be preserved
  as mainline architecture targets.
- Config check: `aggregate_tx24`, `refactored_fsm`, and `action_tree_shadow`
  resolved configs all have `policy.pre_dig_align.enabled=false`, no
  `policy.cell_entry` / `cell_entry_enabled` setting, and
  `dig_low_dim_keys=[qpos, qvel, dig_cut_tokens]` without
  `cell_entry_tokens`.
- Updated `BASELINE_CAPABILITY_SPECS` so missing `token.cell_entry` and
  `gate.pre_dig_align` classify as `dead-candidate` after enough evidence
  packets.
- Regenerated
  `docs/planner_evidence_reports/2026-06-18-baseline-aggregate_tx24.json` and
  `.md`; both now classify `token.cell_entry` and `gate.pre_dig_align` as
  `delete-candidate`.
- Decision: do not migrate `cell_entry` or `pre_dig_align` into the new
  execution-kernel/backend architecture. Delete or reclassify their code only
  after legacy config and test owners are handled.

### 2026-06-18 Negative Evidence Cleanup Rule

- Scope: evidence-classification methodology update only; no planner runtime
  behavior was changed and no planner code was deleted.
- Replaced the overly conservative rule that ordinary absence should remain
  `not-observed` by default.
- New rule: successful mainline evidence that does not show a capability
  contributing, or failure evidence that does not highlight the capability as a
  missing cause, is enough to classify non-compatibility code as
  `dead-candidate`.
- Updated `testbed/planner/evidence_trace.py` so unobserved capabilities default
  to `dead-candidate` once the evidence threshold is met. Compatibility and
  test-only owners still use explicit owner classifications.
- Updated `tb-planner-evidence` default `dead_candidate_min_packets` to `1`,
  matching the current policy that a selected successful mainline evidence
  packet can be sufficient negative evidence.
- Updated `docs/planner_evidence_trace_tool.md`,
  `docs/planner_rollout_evidence_refactor_plan.md`, and the goal prompt to use
  the new cleanup rule.

### 2026-06-18 Legacy Parking Correction

- Scope: methodology and evidence-tool wording update only; no planner runtime
  behavior was changed and no planner code was deleted.
- User decision: the core objective is not deleting functions. The core
  objective is splitting the giant planner into a clean architecture while
  retaining non-mainline code only as isolated legacy, diagnostic, test-only, or
  compatibility material.
- Updated `dead-candidate` retention behavior from `delete-candidate` to
  `retain-legacy-parking`. The evidence classification still means the
  capability is not a mainline migration target; the immediate action is to
  park it outside the execution-kernel/backend architecture.
- Updated the active plan, evidence-tool documentation, goal prompt, guard, and
  workflow tests to use parking/reclassification as the current completion
  condition. Deletion is deferred to a later explicit cleanup review after
  owner audit and architecture parity.

### 2026-06-18 Current-Code Architecture Plan

- Scope: architecture planning only; no planner runtime behavior was changed
  and no planner code was deleted.
- Added `docs/planner_current_code_architecture_plan.md` as the active
  implementation architecture source of truth. It combines current worktree
  file reality, `primitive_planner.py` method ranges, rollout evidence
  classification, target API boundaries, migration slices, legacy parking
  catalog, and verification matrix.
- Reclassified `docs/planner_execution_backend_abstraction_plan.md` as a
  supporting concept plan. It remains useful for the execution-kernel/backend
  direction, but current implementation work should follow the current-code
  plan.
- Updated the active refactor plan, goal prompt, and
  `excavator-planner-safe-refactor` skill to read the new current-code
  architecture plan before migration work.
- Decision: the next code round should build the current-code parity harness
  from the selected successful rollout before extracting `predict()` or
  introducing decision-backend contracts.

### 2026-06-18 Historical Document Cleanup

- Scope: documentation cleanup only; no planner runtime behavior was changed
  and no planner code was deleted.
- Marked `docs/planner_execution_backend_abstraction_analysis.md` and
  `docs/planner_execution_backend_abstraction_plan.md` as supporting material
  behind `docs/planner_current_code_architecture_plan.md`.
- Marked `docs/planner_to_act_conceptual_contract.md` and
  `docs/superpowers/specs/2026-06-17-planner-backend-interface-design.md` as
  historical references where they describe pre-rollback partial backend
  migration structures.
- Updated the rollout-evidence goal prompt and
  `excavator-planner-safe-refactor` skill so old backend docs are optional
  references, not required implementation source-of-truth.
- Decision: current planner implementation work should follow
  `docs/planner_current_code_architecture_plan.md`; older docs remain useful
  only for rationale, history, or explicit compatibility audits.

### 2026-06-18 Phase 1 Current-Code Parity Harness

- Scope: Phase 1 parity harness only; no planner runtime behavior was changed,
  no default config was changed, no token schema, threshold, branch order,
  reason string, or policy reset timing was changed, and no code was deleted.
- Target lock: host local, cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, no fetch, pull, or push.
- Branch baseline audit: local reflog still records branch creation from
  `152350e` (`152350ef300c44d18e55465f0d2377f1094e755d`). The longer
  requested hash `152350e3ed9a8816ca8d685195fc8f297ab3fcec` was not a local
  object; this round did not fetch to resolve it.
- Evidence packet:
  `runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/rollouts/rollout_000.jsonl`,
  `rollout_000_planner_trace.json`, `rollout_000_summary.json`,
  `runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/eval_resolved_config.yaml`,
  and `docs/planner_evidence_reports/2026-06-18-baseline-aggregate_tx24.md`.
- Parity level achieved: structured artifact golden-window parity. The harness
  locks the recorded current-code observable contract, not full offline
  `predict()` or action replay.
- Full offline replay audit: not feasible from this artifact bundle. The bundle
  has per-step qpos/qvel/env_state/action/debug rows, planner trace, rollout
  summary, and resolved config, but lacks camera image observations or image
  frame paths, embedded checkpoint weights and normalization/runtime policy
  state, Unity/env simulator snapshot, full planner private mutable state, and
  a portable replay bundle. The artifact provenance also points at a generated
  rollout repo snapshot rather than proving current HEAD action replay.
- New harness owner:
  `testbed/planner/golden_window_parity.py`. It is a focused artifact contract
  helper and does not import or instantiate `PrimitivePlannerACTPolicy`.
- New focused test:
  `tests/test_planner_current_code_parity.py`. The test was added first and
  failed with `ModuleNotFoundError` before the helper was implemented.
- Golden windows selected: 112 JSONL rows, consisting of rollout start, each
  observed skill-switch index plus adjacent rows, first task-success rows, and
  coverage terminal-stop/final rows. The observed switch sequence contains
  bootstrap -> dig, repeated dig/carry/dump/return boundaries, and final
  dump -> return at step 5584 with terminal stop.
- Locked row fields: `skill_name`, `skill_id`, `skill_switch_reason`,
  `goal_tokens`, dig-cut token injected/source/dim/content,
  dig-depth-profile token injected/source/dim/content, return-target,
  return-relocate, return-start-envelope token injected/source/dim/content,
  `dig_to_carry_reason`, dig counters, dump hold counters, transition flags,
  boundary masks, return-to-dig gate facts, coverage corridor id/score/depleted
  count/terminal-stop fields, `pre_dig_align_*`, `cell_entry_*` row facts,
  primitive checkpoint path/cycle ids, task success, reward phase, and selected
  task metrics.
- Locked trace/summary/config fields: planner trace token contract versions,
  coverage decision trace count, empty cell-entry trace, terminal-stop reason,
  rollout summary success/final metrics, disabled `pre_dig_align`, absent
  `cell_entry` config, and low-dimensional key lists.
- Comparison rules: missing row fields fail explicitly; list lengths are part
  of exact structure comparison; NaN is normalized as a sentinel; finite floats
  are rounded for the stored window digest and compared with a strict
  `1e-9` tolerance for direct contract values.
- Cell-entry and pre-dig-align handling: this harness locks their disabled /
  unobserved status only. It does not migrate either capability into the
  current mainline architecture.
- Phase 2 use: before extracting `PrimitivePlannerACTPolicy.predict()` into an
  execution template, run this harness against the same artifact paths. A
  migration that changes skill switch order, reason strings, token injection
  surfaces, gate/debug fields, trace contract versions, or summary metrics must
  either preserve the contract or stop for semantic confirmation.
- Risks: the harness is intentionally artifact-level and cannot detect
  action-level divergence from images or policy runtime state. It is a behavior
  lock for the observable rollout/debug contract, not a substitute for future
  Unity reruns or portable replay packaging.

### 2026-06-18 Phase 2 Predict Execution Template

- Scope: extracted the public `PrimitivePlannerACTPolicy.predict()` tick
  ordering into a focused execution-template helper only. No FSM decision
  logic, token planning, coverage service, return planning, `cell_entry`,
  `pre_dig_align`, default config, threshold, branch order, reason string,
  token schema, debug schema, rollout summary schema, or policy reset timing was
  intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD
  `e306eb3be2ffb20db28785d2c0576398e5f49c84`, no fetch, pull, or push.
  Worktree was intentionally dirty before this round and was not reset,
  checked out, or reverted.
- Reflection gate:
  - Phase 1 harness existed and passed before code edits:
    `python -m pytest -q tests/test_planner_current_code_parity.py`.
  - Live evidence remains the successful
    `runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/rollouts/rollout_000.jsonl`
    packet and paired planner trace / summary / resolved config.
  - The only responsibility slice was the public tick execution ordering around
    `predict()`.
  - New module responsibility:
    `testbed/planner/primitive_execution.py` owns typed tick preparation /
    result structures, narrow hook protocol, and the execution-step order.
  - This is not a pass-through facade stack because the new module owns a real
    invariant: boundary update, switch-reason reset, optional dig-progress
    update, FSM decision hook call, return-timeout accounting, action dispatch,
    previous-action recording, transition-completion check, and debug
    finalization order. It does not wrap old private methods one-for-one as a
    permanent API.
  - Behaviors that must remain byte-for-byte/field-for-field stable:
    `_maybe_switch_skill()` branch order and reason strings,
    `_update_dig_progress()`, `_active_policy()`, `_policy_obs()`,
    `_make_debug_state()`, token/debug/trace/summary schemas, policy reset
    timing, and rollout observable surfaces.
  - If golden-window parity failed, the intended action was to stop and inspect
    behavior drift, not update the contract.
- Added `testbed/planner/primitive_execution.py` with
  `PrimitiveTickHooks`, `PrimitiveTickCallbacks`,
  `PrimitiveTickPreparation`, `PrimitiveTickResult`, and
  `run_primitive_tick()`.
- Modified `testbed/policies/hybrid/primitive_planner.py` only as a thin
  bridge: `predict()` now calls `run_primitive_tick()` through explicit narrow
  callbacks. The adapter still owns state mutation, decision logic, action
  dispatch, previous-action storage, return timeout accounting, and debug-state
  construction through existing semantics.
- Added `tests/test_primitive_execution_template.py` using fake hooks. The
  first TDD red test failed with `ModuleNotFoundError` before the execution
  module existed. A second red test failed on missing typed preparation before
  `PrimitiveTickPreparation` was added.
- Phase 1 golden-window parity remained the migration guard for observable
  rollout/debug/trace/summary behavior.
- Old code parked/reclassified: no code was deleted. The old inline
  `predict()` sequence is reclassified as public-adapter compatibility bridge
  hooks during this slice. `_maybe_switch_skill()` remains the sole FSM
  decision source of truth.
- Next action: Phase 3 should introduce decision/effect result contracts only
  after this execution template and Phase 1 parity continue to pass. Do not
  introduce backend/runtime/behavior-tree/VLM material before the decision and
  effect boundary is explicitly tested.

### 2026-06-19 Phase 3 Decision/Effect Result Contracts

- Scope: introduced typed decision/effect result contracts only. No FSM branch
  body, token planning, coverage planning, return planning, `cell_entry`,
  `pre_dig_align`, backend selection, runtime package, behavior tree, VLM/LLM
  packet, default config, threshold, branch order, reason string, token schema,
  debug schema, rollout summary schema, or policy reset timing was intentionally
  changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `5b75124ad4f9839f94d7f5da834a7cdde38568f6`, no fetch, pull, or push. The
  earlier prompt expected `e306eb3be2ffb20db28785d2c0576398e5f49c84`, but the
  user confirmed a Phase 2 commit had just advanced the branch.
- Reflection gate:
  - Phase 1 and Phase 2 focused tests existed and passed before Phase 3 edits:
    `python -m pytest -q tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py`
    returned `5 passed`.
  - Live evidence remains the successful
    `runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/rollouts/rollout_000.jsonl`
    packet and paired planner trace / summary / resolved config.
  - The only responsibility slice was the decision result contract that the
    Phase 2 tick template receives.
  - The new contract records the legacy FSM outcome after side effects have
    already been applied; it does not pretend `_maybe_switch_skill()` has been
    split into pure decision plus validated effects.
  - Side effects remain owned by `_maybe_switch_skill()`, `_set_skill()`, and
    the existing planner shell helpers they call.
  - If representing a field required guessing hidden private effects, this
    phase kept it out of the contract.
- Added `testbed/planner/primitive_decision.py` with
  `LEGACY_FSM_DECISION_SOURCE`, `PlannerEffect`,
  `LegacyDecisionOutcomeEffect`, and `PrimitiveDecisionResult`.
- Modified `testbed/planner/primitive_execution.py` so the decision hook is
  `decide_tick(...) -> PrimitiveDecisionResult` and
  `PrimitiveTickResult` carries `decision`.
- Modified `testbed/policies/hybrid/primitive_planner.py` only as a thin
  bridge: `_decide_tick_with_legacy_fsm()` captures skill before/after and
  switch reason, calls `_maybe_switch_skill()` exactly once, then returns
  `PrimitiveDecisionResult.from_legacy_fsm_outcome(...)`.
- Added `tests/test_primitive_decision_contract.py` for the contract and legacy
  bridge. The TDD red test failed with `ModuleNotFoundError` before
  `testbed.planner.primitive_decision` was implemented.
- Updated `tests/test_primitive_execution_template.py` so fake hooks prove the
  tick order still runs decision before return-timeout accounting and action
  dispatch, while the result object records the returned decision.
- Phase 1 golden-window parity remained the migration guard for observable
  rollout/debug/trace/summary behavior.
- Verification completed during this round:
  - `python -m pytest -q tests/test_primitive_decision_contract.py tests/test_primitive_execution_template.py`
    returned `5 passed` after implementation.
  - `python -m pytest -q tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `8 passed`.
  - `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
    returned `5 passed`.
  - `python -m compileall -q testbed/planner/primitive_decision.py testbed/planner/primitive_execution.py testbed/policies/hybrid/primitive_planner.py tests/test_primitive_decision_contract.py tests/test_primitive_execution_template.py`
    completed with no output.
- Old code parked/reclassified: no code was deleted. `_maybe_switch_skill()`
  remains the sole FSM decision and side-effect source of truth; the new
  contract is an observable-outcome adapter for the execution template.
- Next action: Phase 4 should extract read-only capability status records only.
  Do not move `_maybe_switch_skill()` branch bodies or apply effects outside the
  old shell until the result contract is expanded with explicitly validated
  effect application tests.
