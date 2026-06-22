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

### 2026-06-19 Phase 4A PrimitiveObservationFacts

- Scope: introduced `PrimitiveObservationFacts` only. No FSM branch body,
  transition gate, token planning, coverage planning, return planning,
  `cell_entry`, `pre_dig_align`, backend selection, runtime package, behavior
  tree, VLM/LLM packet, default config, threshold, branch order, reason string,
  token schema, debug schema, rollout summary schema, or policy reset timing was
  intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `5dfa6225b9480abc7d4750039e7ddcb7a943a0b2`, no fetch, pull, or push. The
  worktree was clean before edits.
- Reflection gate:
  - Phase 1, Phase 2, and Phase 3 focused tests passed before Phase 4A edits:
    `python -m pytest -q tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `8 passed`.
  - Live evidence remains the successful
    `runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/rollouts/rollout_000.jsonl`
    packet and paired planner trace / summary / resolved config.
  - The only responsibility slice was read-only primitive observation facts from
    `qpos`, `qvel`, `env_state`, `task_metrics`, `reward_phase`, and task step
    success events.
  - `PrimitiveObservationFacts` owns typed observation projection and lazy
    target-geometry reads. Target geometry remains lazy so non-dump ticks do not
    see earlier geometry exceptions.
  - No planner `self` is passed into the capability module, and this slice does
    not wrap `_maybe_switch_skill()` or old private branch methods.
- Added `testbed/planner/primitive_capabilities.py` with
  `PrimitiveObservationFacts`. The record copies observation arrays into
  non-writeable `float32` arrays, freezes `task_metrics` behind a mapping proxy,
  preserves current missing defaults, keeps task event fields, and exposes
  legacy-compatible mass, deposited-mass, env-state scalar, and target-geometry
  accessors.
- Added `tests/test_primitive_capabilities.py`. The TDD red test failed with
  `ModuleNotFoundError` before `testbed.planner.primitive_capabilities` was
  implemented.
- Updated `docs/planner_current_code_architecture_plan.md` so the immediate next
  action no longer points at already-completed Slice 1; it now points at Slice 4
  capability status records.
- Old code parked/reclassified: no code was deleted. Existing planner helper
  methods and `_maybe_switch_skill()` remain compatibility/source-of-truth
  paths until later status or backend phases explicitly bridge them with parity
  tests.
- Verification completed during this round:
  - `python -m pytest -q tests/test_primitive_capabilities.py` returned
    `4 passed`.
  - `python -m pytest -q tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `8 passed`.
  - `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
    returned `5 passed`.
  - `python -m compileall -q testbed/planner/primitive_capabilities.py tests/test_primitive_capabilities.py`
    completed with no output.
  - `python scripts/planner_refactor_guard.py --check-plan-contract`,
    `python scripts/planner_refactor_guard.py --check-skill-contract`, and
    `git diff --check` completed with no output.
- Next action: Phase 4B should continue with `BootstrapStatus` only. Do not
  migrate dig/carry/dump/return status records, token status, coverage status,
  token planning, coverage planning, or legacy FSM backend behavior in the same
  commit.

### 2026-06-19 Phase 4B.1 BootstrapStatus

- Scope: introduced `BootstrapStatus` only. No FSM branch body, transition gate
  side effect, token planning, coverage planning, return planning, `cell_entry`,
  `pre_dig_align`, backend selection, runtime package, behavior tree, VLM/LLM
  packet, default config, threshold, branch order, reason string, token schema,
  debug schema, rollout summary schema, or policy reset timing was intentionally
  changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `81da6d9f7fc63debb8768fc48bebc3fc0c79b951`, no fetch, pull, or push. The
  worktree was clean before edits.
- Reflection gate:
  - Phase 1, Phase 2, Phase 3, and Phase 4A focused tests passed before
    Phase 4B.1 edits:
    `python -m pytest -q tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py tests/test_primitive_capabilities.py`
    returned `12 passed`.
  - Live evidence remains the successful `aggregate_tx24` rollout packet; the
    golden-window switch sequence includes bootstrap to dig with
    `bootstrap_to_dig`.
  - The only responsibility slice was read-only bootstrap transition status.
  - `BootstrapStatus` mirrors current bootstrap gate facts without calling
    `_should_end_bootstrap()` or `_scripted_bootstrap_target_reached()`, so it
    does not increment scripted hold or timeout counters.
  - Existing `_maybe_switch_skill()` bootstrap branch remains the decision and
    side-effect source of truth.
- Updated `testbed/planner/primitive_capabilities.py` with `BootstrapStatus`
  and a `PrimitiveObservationFacts.min_distance_to_dig_area_m` accessor needed
  by the legacy `loaded_and_clear` bootstrap gate.
- Updated `tests/test_primitive_capabilities.py` with focused coverage for
  first-qualified-dig-start, loaded-and-clear, scripted-qpos target reach, and
  scripted timeout facts. The TDD red test failed with `ImportError` before
  `BootstrapStatus` was implemented.
- Old code parked/reclassified: no code was deleted. `_should_end_bootstrap()`,
  `_scripted_bootstrap_enabled()`, `_scripted_bootstrap_target_reached()`, and
  the `_maybe_switch_skill()` bootstrap branch remain compatibility and
  source-of-truth paths until a later legacy FSM backend phase bridges them with
  parity tests.
- Verification completed during this round:
  - `python -m pytest -q tests/test_primitive_capabilities.py` returned
    `8 passed`.
  - `python -m pytest -q tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `16 passed`.
  - `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
    returned `5 passed`.
  - `python -m compileall -q testbed/planner/primitive_capabilities.py tests/test_primitive_capabilities.py`
    completed with no output.
  - `python scripts/planner_refactor_guard.py --check-plan-contract`,
    `python scripts/planner_refactor_guard.py --check-skill-contract`, and
    `git diff --check` completed with no output.
- Next action: Phase 4B.2 should continue with `DigTransitionStatus` only. Do
  not migrate carry, dump, return, coverage, token, token planning, coverage
  planning, or backend behavior in the same commit.

### 2026-06-19 Phase 4B.2 DigTransitionStatus

- Scope: introduced `DigTransitionStatus` only. No FSM branch body, transition
  gate side effect, coverage-corridor geometry calculation, token planning,
  coverage planning, return planning, `cell_entry`, `pre_dig_align`, backend
  selection, runtime package, behavior tree, VLM/LLM packet, default config,
  threshold, branch order, reason string, token schema, debug schema, rollout
  summary schema, or policy reset timing was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `4051b33e0b2bc1bc490dfec41c7070d3f6b1e5d8`, no fetch, pull, or push. The
  worktree was clean before edits.
- Reflection gate:
  - Phase 1, Phase 2, Phase 3, Phase 4A, and Phase 4B.1 focused tests passed
    before Phase 4B.2 edits:
    `python -m pytest -q tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `16 passed`.
  - Live evidence remains the successful `aggregate_tx24` rollout packet; the
    golden-window switch sequence includes repeated dig to carry switches with
    `dig_to_carry_dig_complete_boundary` and
    `dig_to_carry_semantic_material_loaded`.
  - The only responsibility slice was read-only dig transition status.
  - `DigTransitionStatus` records dig bad-replan, exit-guard,
    dig-complete-low-payload, dig-to-carry readiness, and dig-to-carry reason
    facts without calling `_dig_to_carry_ready()` or mutating
    `_dig_to_carry_reason`.
  - Overshoot, semantic-boundary-profile state, and coverage terminal-stop state
    remain explicit inputs so this slice does not absorb coverage, geometry, or
    planner-shell ownership.
- Updated `testbed/planner/primitive_capabilities.py` with
  `DigTransitionStatus`.
- Updated `tests/test_primitive_capabilities.py` with focused coverage for
  boundary completion, legacy loaded reason, semantic loaded reason from
  boundary metrics, bad-replan readiness, and exit-guard readiness. The TDD red
  test failed with `ImportError` before `DigTransitionStatus` was implemented.
- Old code parked/reclassified: no code was deleted. `_update_dig_progress()`,
  `_dig_bad_replan_ready()`, `_dig_exit_guard_ready()`,
  `_dig_complete_boundary_low_payload()`, `_dig_to_carry_ready()`, and the
  `_maybe_switch_skill()` dig branch remain compatibility/source-of-truth paths
  until a later legacy FSM backend phase bridges them with parity tests.
- Verification completed during this round:
  - `python -m pytest -q tests/test_primitive_capabilities.py` returned
    `12 passed`.
  - `python -m pytest -q tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `20 passed`.
  - `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
    returned `5 passed`.
  - `python -m compileall -q testbed/planner/primitive_capabilities.py tests/test_primitive_capabilities.py`
    completed with no output.
  - `python scripts/planner_refactor_guard.py --check-plan-contract`,
    `python scripts/planner_refactor_guard.py --check-skill-contract`, and
    `git diff --check` completed with no output.
- Next action: Phase 4B.3 should continue with `CarryTransitionStatus` only. Do
  not migrate dump, return, coverage, token, token planning, coverage planning,
  or backend behavior in the same commit.

### 2026-06-19 Phase 4B.3 CarryTransitionStatus

- Scope: introduced `CarryTransitionStatus` only. No FSM branch body,
  transition gate side effect, coverage completion, return handoff, token
  planning, coverage planning, dump branch behavior, `cell_entry`,
  `pre_dig_align`, backend selection, runtime package, behavior tree, VLM/LLM
  packet, default config, threshold, branch order, reason string, token schema,
  debug schema, rollout summary schema, or policy reset timing was intentionally
  changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `8a0ac5e9c3ce5c16b3c90cd2217f6e0bc2f3e32e`, no fetch, pull, or push. The
  worktree was clean before edits.
- Reflection gate:
  - Phase 1 through Phase 4B.2 focused tests passed before Phase 4B.3 edits:
    `python -m pytest -q tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `20 passed`.
  - Live evidence remains the successful `aggregate_tx24` rollout packet; the
    golden-window switch sequence includes repeated carry to dump switches with
    `carry_to_dump_dump_committed_boundary`.
  - The only responsibility slice was read-only carry transition status.
  - `CarryTransitionStatus` records carry release safety, dump committed /
    release-onset / dump-complete / legacy dump-start boundary facts,
    dump-ready hold projection, and carry-to-dump or carry-to-return reasons
    without calling `_dump_ready()` or mutating `_dump_ready_hold_count`.
  - Dump-ready geometry calculation is pure and local to the status record; it
    does not move dump branch behavior or coverage completion effects.
- Updated `testbed/planner/primitive_capabilities.py` with
  `CarryTransitionStatus` and pure helpers for dump-ready fact projection.
- Updated `tests/test_primitive_capabilities.py` with focused coverage for
  committed-boundary readiness, semantic release safety, legacy target-ready
  hold progression, and keeping legacy dump-start out of the semantic profile.
  The TDD red test failed with `ImportError` before `CarryTransitionStatus` was
  implemented.
- Old code parked/reclassified: no code was deleted. `_carry_release_safety_done()`,
  `_dump_ready()`, dump-ready geometry helpers, and the `_maybe_switch_skill()`
  carry branch remain compatibility/source-of-truth paths until a later legacy
  FSM backend phase bridges them with parity tests.
- Verification completed during this round:
  - `python -m pytest -q tests/test_primitive_capabilities.py` returned
    `16 passed`.
  - `python -m pytest -q tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `24 passed`.
  - `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
    returned `5 passed`.
  - `python -m compileall -q testbed/planner/primitive_capabilities.py tests/test_primitive_capabilities.py`
    completed with no output.
  - `python scripts/planner_refactor_guard.py --check-plan-contract`,
    `python scripts/planner_refactor_guard.py --check-skill-contract`, and
    `git diff --check` completed with no output.
- Next action: Phase 4B.4 should continue with `DumpTransitionStatus` only. Do
  not migrate return, coverage, token, token planning, coverage planning, or
  backend behavior in the same commit.

### 2026-06-19 Phase 4B.4 DumpTransitionStatus

- Scope: introduced `DumpTransitionStatus` only. No FSM branch body, transition
  gate side effect, coverage completion, return handoff, token planning,
  coverage planning, return branch behavior, `cell_entry`, `pre_dig_align`,
  backend selection, runtime package, behavior tree, VLM/LLM packet, default
  config, threshold, branch order, reason string, token schema, debug schema,
  rollout summary schema, or policy reset timing was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `7d969fd0cdabb728d7e845b417234f1d95b700b6`, no fetch, pull, or push. The
  worktree was clean before edits.
- Reflection gate:
  - Phase 1 through Phase 4B.3 focused tests passed before Phase 4B.4 edits:
    `python -m pytest -q tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `24 passed`.
  - Live evidence remains the successful `aggregate_tx24` rollout packet; the
    golden-window switch sequence includes repeated dump to return switches with
    `dump_to_return_dump_complete_boundary`.
  - The only responsibility slice was read-only dump transition status.
  - `DumpTransitionStatus` records dump-complete / legacy dump-end boundary
    facts and mass-low hold projection without calling `_dump_done()` or
    mutating `_dump_done_hold_count`.
  - Return handoff and coverage completion effects remain in the planner shell.
- Updated `testbed/planner/primitive_capabilities.py` with
  `DumpTransitionStatus`.
- Updated `tests/test_primitive_capabilities.py` with focused coverage for
  dump-complete boundary, legacy dump-end boundary, mass-low hold readiness, and
  keeping mass-low hold out of semantic profile mode. The TDD red test failed
  with `ImportError` before `DumpTransitionStatus` was implemented.
- Old code parked/reclassified: no code was deleted. `_dump_done()` and the
  `_maybe_switch_skill()` dump branch remain compatibility/source-of-truth paths
  until a later legacy FSM backend phase bridges them with parity tests.
- Verification completed during this round:
  - `python -m pytest -q tests/test_primitive_capabilities.py` returned
    `20 passed`.
  - `python -m pytest -q tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `28 passed`.
  - `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
    returned `5 passed`.
  - `python -m compileall -q testbed/planner/primitive_capabilities.py tests/test_primitive_capabilities.py`
    completed with no output.
  - `python scripts/planner_refactor_guard.py --check-plan-contract`,
    `python scripts/planner_refactor_guard.py --check-skill-contract`, and
    `git diff --check` completed with no output.
- Next action: Phase 4B.5 should continue with `ReturnTransitionStatus` only.
  Do not migrate coverage, token, token planning, coverage planning, or backend
  behavior in the same commit.

### 2026-06-19 Phase 4B.5 ReturnTransitionStatus

- Scope: introduced `ReturnTransitionStatus` only. No FSM branch body,
  transition side effect, return-start-envelope token validation, return-target
  planning, coverage planning, token planning, `cell_entry`, `pre_dig_align`,
  backend selection, runtime package, behavior tree, VLM/LLM packet, default
  config, threshold, branch order, reason string, token schema, debug schema,
  rollout summary schema, or policy reset timing was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `fd488397759b3f2895c87ff5b13cc3e48c97216f`, no fetch, pull, or push. The
  worktree was clean before edits.
- Reflection gate:
  - Phase 1 through Phase 4B.4 focused tests passed before Phase 4B.5 edits:
    `python -m pytest -q tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `28 passed`.
  - Live evidence remains the successful `aggregate_tx24` rollout packet; the
    golden-window switch sequence includes return to dig switches with
    `return_to_dig_start_envelope_ready` and
    `return_to_dig_next_dig_entry_ready`.
  - The only responsibility slice was read-only return transition status.
  - `ReturnTransitionStatus` takes `entry_close` and `start_envelope_ready` as
    explicit inputs instead of migrating return-start-envelope token checks,
    which remain Phase 5 work.
  - The status records next-dig event, remembered next-dig event, direct
    handoff, shallow guard, selected next skill, and switch reason facts without
    mutating counters or planner state.
- Updated `testbed/planner/primitive_capabilities.py` with
  `ReturnTransitionStatus` and
  `PrimitiveObservationFacts.bucket_depth_below_dig_area_plane_m`.
- Updated `tests/test_primitive_capabilities.py` with focused coverage for
  next-dig event handoff, remembered next-dig event handoff, direct handoff to
  pre-dig-align, legacy shallow guard, and keeping shallow guard out of semantic
  profile mode. The TDD red test failed with `ImportError` before
  `ReturnTransitionStatus` was implemented.
- Old code parked/reclassified: no code was deleted.
  `_return_to_dig_handoff_ready()`, `_return_to_dig_direct_handoff_ready()`,
  `_return_to_dig_shallow_guard_ready()`,
  `_return_to_dig_start_envelope_ready()`, and the `_maybe_switch_skill()`
  return branch remain compatibility/source-of-truth paths until a later legacy
  FSM backend phase bridges them with parity tests.
- Verification completed during this round:
  - `python -m pytest -q tests/test_primitive_capabilities.py` returned
    `25 passed`.
  - `python -m pytest -q tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `33 passed`.
  - `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
    returned `5 passed`.
  - `python -m compileall -q testbed/planner/primitive_capabilities.py tests/test_primitive_capabilities.py`
    completed with no output.
  - `python scripts/planner_refactor_guard.py --check-plan-contract`,
    `python scripts/planner_refactor_guard.py --check-skill-contract`, and
    `git diff --check` completed with no output.
- Next action: Phase 4C should continue with `CoverageStatus` only. Do not
  migrate token status, token planning, coverage planning/runtime, or backend
  behavior in the same commit.

### 2026-06-19 Phase 4C.1 CoverageStatus

- Scope: introduced `CoverageStatus` only. No coverage candidate construction,
  scoring, selection, completion update, rejection update, terminal-stop update,
  token planning, backend selection, runtime package, behavior tree, VLM/LLM
  packet, default config, threshold, branch order, reason string, token schema,
  debug schema, rollout summary schema, or policy reset timing was intentionally
  changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `ac62bad468aeb0211b50bca297a99d2554dada8d`, no fetch, pull, or push. The
  worktree was clean before edits.
- Reflection gate:
  - Phase 1 through Phase 4B.5 focused tests passed before Phase 4C.1 edits:
    `python -m pytest -q tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `33 passed`.
  - Live evidence remains the successful `aggregate_tx24` rollout packet; the
    golden-window contract locks selected corridor id/score, coverage terminal
    stop requested/reason, depleted count, payload gain, and effective deposit
    delta fields.
  - The only responsibility slice was read-only coverage status.
  - `testbed/planner/primitive_capabilities.py` was already 998 lines before
    this slice, so adding coverage status there would cross the repository
    large-file threshold. The stable focused owner for this slice is
    `testbed/planner/primitive_coverage_status.py`.
- Added `testbed/planner/primitive_coverage_status.py` with `CoverageStatus`.
  The record freezes selected corridor, candidate scores, terminal-stop,
  depleted, completion, and rejection observable state without owning coverage
  planning/runtime mutation.
- Added `tests/test_primitive_coverage_status.py` with focused coverage for
  selected corridor and candidate-score freezing, terminal-stop state, and
  completion/rejection observables. The TDD red test failed with
  `ModuleNotFoundError` before `testbed.planner.primitive_coverage_status` was
  implemented.
- Old code parked/reclassified: no code was deleted. Existing coverage
  candidate/scoring/update helpers and coverage fields remain
  compatibility/source-of-truth paths until the later coverage planning/runtime
  service phase bridges them with parity tests.
- Verification completed during this round:
  - `python -m pytest -q tests/test_primitive_coverage_status.py` returned
    `3 passed`.
  - `python -m pytest -q tests/test_primitive_coverage_status.py tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `36 passed`.
  - `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
    returned `5 passed`.
  - `python -m compileall -q testbed/planner/primitive_coverage_status.py tests/test_primitive_coverage_status.py`
    completed with no output.
  - `python scripts/planner_refactor_guard.py --check-plan-contract`,
    `python scripts/planner_refactor_guard.py --check-skill-contract`, and
    `git diff --check` completed with no output.
- Next action: Phase 4C.2 should continue with `TokenStatus` only. Do not
  migrate token generation, token planning, coverage planning/runtime, or
  backend behavior in the same commit.

### 2026-06-19 Phase 4C.2 TokenStatus

- Scope: introduced `TokenStatus` and `TokenVectorStatus` only. No token
  generation, token planning, observation injection, return planning, coverage
  planning/runtime, backend selection, runtime package, behavior tree, VLM/LLM
  packet, default config, threshold, branch order, reason string, token schema,
  debug schema, rollout summary schema, or policy reset timing was intentionally
  changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `e25c70c2bfce945a0d824a802990efde91fe2aab`, no fetch, pull, or push. The
  worktree was clean before edits.
- Reflection gate:
  - Phase 1 through Phase 4C.1 focused tests passed before Phase 4C.2 edits:
    `python -m pytest -q tests/test_primitive_coverage_status.py tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `36 passed`.
  - Live evidence remains the successful `aggregate_tx24` rollout packet; the
    golden-window contract locks token contract versions, dig/return low-dim
    keys, token source fields, and debug/summary surfaces.
  - The only responsibility slice was read-only token status.
  - `testbed/planner/primitive_capabilities.py` was already 998 lines before
    Phase 4C.1, so the stable focused owner for this slice is
    `testbed/planner/primitive_token_status.py`.
- Added `testbed/planner/primitive_token_status.py` with `TokenStatus` and
  `TokenVectorStatus`. The records freeze injected flags, dimensions,
  source/fallback strings, prior-range status, and current token arrays, and
  can project the legacy debug-state field names without owning token
  construction.
- Added `tests/test_primitive_token_status.py` with focused coverage for token
  array freezing, source/fallback/injected facts, and legacy debug field names.
  The TDD red test failed with `ModuleNotFoundError` before
  `testbed.planner.primitive_token_status` was implemented.
- Old code parked/reclassified: no code was deleted. `_policy_obs()`,
  `_goal_tokens()`, `_dig_cut_tokens_for_obs()`,
  `_dig_depth_profile_tokens_for_obs()`, `_return_target_tokens_for_obs()`,
  `_return_relocate_tokens_for_obs()`, and
  `_return_start_envelope_tokens_for_obs()` remain
  compatibility/source-of-truth paths until the Phase 5 token/return planning
  service slices bridge them with parity tests.
- Verification completed during this round:
  - `python -m pytest -q tests/test_primitive_token_status.py` returned
    `3 passed`.
  - `python -m pytest -q tests/test_primitive_token_status.py tests/test_primitive_coverage_status.py tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `39 passed`.
  - `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
    returned `5 passed`.
  - `python -m compileall -q testbed/planner/primitive_token_status.py tests/test_primitive_token_status.py`
    completed with no output.
  - `python scripts/planner_refactor_guard.py --check-plan-contract`,
    `python scripts/planner_refactor_guard.py --check-skill-contract`, and
    `git diff --check` completed with no output.
- Next action: Phase 5.1 should continue with the goal token provider only.
  Do not migrate dig-cut, dig-depth-profile, return-target, return-relocate,
  return-start-envelope, coverage planning/runtime, or backend behavior in the
  same commit.

### 2026-06-19 Phase 5.1 Goal Token Provider

- Scope: extracted the goal token provider only. No dig-cut token planning,
  dig-depth-profile token planning, return-target planning, return-relocate
  planning, return-start-envelope planning, observation injection key changes,
  coverage planning/runtime, backend selection, runtime package, behavior tree,
  VLM/LLM packet, default config, threshold, branch order, reason string, token
  schema, debug schema, rollout summary schema, or policy reset timing was
  intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `f806f84bd757b51cfd66d852a7b35061c100c0b2`, no fetch, pull, or push. The
  worktree was clean before edits.
- Reflection gate:
  - Phase 1 through Phase 3 focused tests passed before Phase 5.1 edits:
    `python -m pytest -q tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `8 passed`.
  - Live evidence remains the successful `aggregate_tx24` rollout packet; the
    golden-window contract locks the goal token presence in selected windows
    and the config token/low-dim contract used by the current rollout evidence.
  - The only responsibility slice was the goal token provider.
  - The stable focused owner for this slice is
    `testbed/planner/primitive_tokens.py`; it owns goal sequence normalization,
    current/lookahead sector lookup, and `build_goal_tokens()` delegation.
- Added `GoalTokenProvider` in `testbed/planner/primitive_tokens.py`.
  `PrimitivePlannerACTPolicy._goal_tokens()`, `_goal_sector_id()`,
  `_next_goal_sector_id()`, and `_normalize_goal_sequence()` remain compatibility
  facade entry points and now delegate to the provider without passing planner
  `self` into the module.
- Added `tests/test_primitive_goal_token_provider.py` with focused coverage for
  empty sequence behavior, current/lookahead token construction, current-sector
  clamping, final lookahead, and invalid sector validation. The TDD red test
  failed with `ModuleNotFoundError` before `testbed.planner.primitive_tokens`
  was implemented.
- Old code parked/reclassified: no code was deleted. `_policy_obs()` remains the
  source-of-truth injection path for the `goal_tokens` observation key until a
  later observation assembly slice is explicitly approved.
- Verification completed during this round:
  - `python -m pytest -q tests/test_primitive_goal_token_provider.py` returned
    `4 passed`.
  - `python -m pytest -q tests/test_agx_primitives_v2_2.py -k goal_tokens`
    returned `1 passed, 119 deselected`.
  - `python -m pytest -q tests/test_primitive_goal_token_provider.py tests/test_primitive_token_status.py tests/test_primitive_coverage_status.py tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `43 passed`.
  - `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
    returned `5 passed`.
  - `python -m compileall -q testbed/planner/primitive_tokens.py testbed/policies/hybrid/primitive_planner.py tests/test_primitive_goal_token_provider.py`
    completed with no output.
  - `python scripts/planner_refactor_guard.py --check-plan-contract`,
    `python scripts/planner_refactor_guard.py --check-skill-contract`, and
    `git diff --check` completed with no output.
- Next action: Phase 5.2 should continue with dig-cut token planning only. Do
  not migrate dig-depth-profile, return-target, return-relocate,
  return-start-envelope, coverage planning/runtime, or backend behavior in the
  same commit.

### 2026-06-19 Phase 5.2 Dig-Cut Token Planning

- Scope: extracted dig-cut token planning result construction only. No
  dig-depth-profile token planning, return-target planning, return-relocate
  planning, return-start-envelope planning, observation injection key changes,
  coverage candidate construction, coverage scoring/selection ownership,
  coverage state update ownership, backend selection, runtime package, behavior
  tree, VLM/LLM packet, default config, threshold, branch order, reason string,
  token schema, debug schema, rollout summary schema, or policy reset timing was
  intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `9278e79e2de021272f2598f168fd61f5a74a32bc`, no fetch, pull, or push. The
  worktree was clean before edits.
- Reflection gate:
  - Phase 1 through Phase 3 focused tests passed before Phase 5.2 edits:
    `python -m pytest -q tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `8 passed`.
  - Live evidence remains the successful `aggregate_tx24` rollout packet; its
    evidence report classifies `token.dig_cut` as confirmed-live with observed
    sources `operator_prior_coverage` and `pending_return_target`, and its
    resolved config uses `dig_cut_planner.mode=operator_prior_sweep_belief`.
  - The only responsibility slice was dig-cut token planning.
  - The stable focused owner for this slice is
    `testbed/planner/primitive_tokens.py`; it now owns `DigCutTokenPlan` and
    `DigCutTokenPlanner`, including live-pose raw fields, operator-prior raw
    fields, prior-range checking, pending-return token projection, fallback
    conservative token projection, and raw-field-to-token projection through the
    existing data contract builders.
- Updated `PrimitivePlannerACTPolicy` so `_build_dig_cut_tokens_for_obs()` and
  compatibility helpers delegate token/prior calculations to
  `DigCutTokenPlanner`. The legacy shell still owns call timing, skill gating,
  pending-return coverage state writes, coverage corridor selection, coverage
  state updates, and observation injection.
- Added `tests/test_primitive_dig_cut_token_planner.py` with focused coverage
  for conservative pose planning, operator-prior pose-clamped planning,
  operator-prior median fallback, pending-return target token copying, and
  coverage raw-field token projection. The TDD red test failed with
  `ImportError` before `DigCutTokenPlanner` was implemented.
- Old code parked/reclassified: no code was deleted. Return-target next-dig
  planning and return-start-envelope helper paths still call their existing
  planner-shell code until the later Phase 5 return-planning slices migrate
  them with parity tests. Coverage selection/update helpers remain legacy
  source-of-truth until Phase 6.
- Verification completed during this round:
  - `python -m pytest -q tests/test_primitive_dig_cut_token_planner.py`
    returned `5 passed`.
  - `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "conservative_dig_cut_mode or operator_prior_locks_token or operator_prior_uses_median or coverage_outputs_finite_token_in_prior_range or coverage_locks_token_within_dig_cycle or injects_return_target_only_for_return_and_reuses_for_dig or replan_invalidates_pending_return_target or bootstrap_policy_can_receive_dig_cut_tokens"`
    returned `8 passed, 112 deselected`.
  - `python -m pytest -q tests/test_primitive_dig_cut_token_planner.py tests/test_primitive_goal_token_provider.py tests/test_primitive_token_status.py tests/test_primitive_coverage_status.py tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `48 passed`.
  - `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
    returned `5 passed`.
  - `python -m compileall -q testbed/planner/primitive_tokens.py testbed/policies/hybrid/primitive_planner.py tests/test_primitive_dig_cut_token_planner.py`
    completed with no output.
  - `python scripts/planner_refactor_guard.py --check-plan-contract`,
    `python scripts/planner_refactor_guard.py --check-skill-contract`, and
    `git diff --check` completed with no output.
- Next action: Phase 5.3 should continue with dig-depth-profile token planning
  only. Do not migrate return-target, return-relocate, return-start-envelope,
  coverage planning/runtime, or backend behavior in the same commit.

### 2026-06-19 Phase 5.3 Dig-Depth-Profile Token Planning

- Scope: extracted dig-depth-profile token planning only. No return-target
  planning, return-relocate planning, return-start-envelope planning,
  observation injection key changes, coverage candidate construction, coverage
  scoring/selection ownership, coverage state update ownership, backend
  selection, runtime package, behavior tree, VLM/LLM packet, default config,
  threshold, branch order, reason string, token schema, debug schema, rollout
  summary schema, or policy reset timing was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `93ce9364430ccf9f6404494676004dbee48f9865`, no fetch, pull, or push. The
  worktree was clean before edits.
- Reflection gate:
  - Phase 1 through Phase 3 focused tests passed before Phase 5.3 edits:
    `python -m pytest -q tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `8 passed`.
  - Live evidence remains the successful `aggregate_tx24` rollout packet; its
    evidence report classifies `token.dig_depth_profile` as confirmed-live and
    observes source `live_plan`, while strict profile tests cover required prior
    success/failure compatibility.
  - The only responsibility slice was dig-depth-profile token planning.
  - The stable focused owner for this slice is
    `testbed/planner/primitive_tokens.py`; it now owns
    `DigDepthProfileTokenPlan`, `DigDepthProfileTokenPlanner`, and
    `DigDepthProfileTokenPlanningError`, while continuing to delegate token
    construction to the existing data contract builder.
- Updated `PrimitivePlannerACTPolicy` so
  `_build_dig_depth_profile_tokens_for_obs()` and compatibility helpers
  delegate token/source/fallback planning to `DigDepthProfileTokenPlanner`. The
  legacy shell still owns call timing, skill gating, cell-id choice,
  pending-return raw fields, coverage exemplar state, coverage runtime state,
  and observation injection.
- Added `tests/test_primitive_dig_depth_profile_token_planner.py` with focused
  coverage for live-plan token construction, state-conditioned exemplar copy,
  cell/global prior lookup, and missing required prior source/fallback error
  reporting. The TDD red test failed with `ImportError` before
  `DigDepthProfileTokenPlanner` was implemented.
- Old code parked/reclassified: no code was deleted. Return-target,
  return-relocate, and return-start-envelope planning remain in the legacy
  shell until their own Phase 5 slices. Coverage selection/update helpers remain
  legacy source-of-truth until Phase 6.
- Verification completed during this round:
  - `python -m pytest -q tests/test_primitive_dig_depth_profile_token_planner.py`
    returned `4 passed`.
  - `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "strict_depth_profile or semantic_profile_keeps_material_liveness_dig_to_carry"`
    returned `3 passed, 117 deselected`.
  - `python -m pytest -q tests/test_primitive_dig_depth_profile_token_planner.py tests/test_primitive_dig_cut_token_planner.py tests/test_primitive_goal_token_provider.py tests/test_primitive_token_status.py tests/test_primitive_coverage_status.py tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `52 passed`.
  - `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
    returned `5 passed`.
  - `python -m compileall -q testbed/planner/primitive_tokens.py testbed/policies/hybrid/primitive_planner.py tests/test_primitive_dig_depth_profile_token_planner.py`
    completed with no output.
  - `python scripts/planner_refactor_guard.py --check-plan-contract`,
    `python scripts/planner_refactor_guard.py --check-skill-contract`, and
    `git diff --check` completed with no output.
- Next action: Phase 5.4 should continue with return-target token planning
  only. Do not migrate return-relocate, return-start-envelope, coverage
  planning/runtime, or backend behavior in the same commit.

### 2026-06-19 Phase 5.4 Return-Target Token Planning

- Scope: extracted return-target token planning result construction only. No
  return-relocate planning, return-start-envelope planning, observation
  injection key changes, coverage candidate construction, coverage
  scoring/selection ownership, coverage state update ownership, backend
  selection, runtime package, behavior tree, VLM/LLM packet, default config,
  threshold, branch order, reason string, token schema, debug schema, rollout
  summary schema, or policy reset timing was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `b35493a9d8e425f851d68a4846e2da0e042c0be8`, no fetch, pull, or push. The
  worktree was clean before edits.
- Reflection gate:
  - Phase 1 through Phase 3 focused tests passed before Phase 5.4 edits:
    `python -m pytest -q tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `8 passed`.
  - Live evidence remains the successful `aggregate_tx24` rollout packet; its
    evidence report classifies `token.return_target` as confirmed-live and
    observes source `conditioned_return_operator_prior_sweep_belief`.
  - The only responsibility slice was return-target token planning.
  - The stable focused owner for this slice is
    `testbed/planner/primitive_tokens.py`; it now owns `ReturnTargetTokenPlan`
    and `ReturnTargetTokenPlanner`, while reusing `DigCutTokenPlanner` and the
    existing data token contract builders.
- Updated `PrimitivePlannerACTPolicy._build_next_dig_cut_plan_for_return()` to
  delegate return-target token/source/corridor result construction to
  `ReturnTargetTokenPlanner`. The legacy shell still owns call timing,
  return-cycle caching, pending next-dig state writes, return-start-envelope
  planning invocation, coverage corridor selection, coverage state updates, and
  observation injection.
- Added `tests/test_primitive_return_target_token_planner.py` with focused
  coverage for conservative-pose return target planning, operator-prior source
  prefixing, and coverage raw-field source/corridor projection. The TDD red
  test failed with `ImportError` before `ReturnTargetTokenPlanner` was
  implemented.
- Old code parked/reclassified: no code was deleted. Return-relocate and
  return-start-envelope planning remain in the legacy shell until their own
  Phase 5 slices. Coverage selection/update helpers remain legacy
  source-of-truth until Phase 6.
- Verification completed during this round:
  - `python -m pytest -q tests/test_primitive_return_target_token_planner.py`
    returned `3 passed`.
  - `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "injects_return_target_only_for_return_and_reuses_for_dig or replan_invalidates_pending_return_target"`
    returned `2 passed, 118 deselected`.
  - `python -m pytest -q tests/test_primitive_return_target_token_planner.py tests/test_primitive_dig_depth_profile_token_planner.py tests/test_primitive_dig_cut_token_planner.py tests/test_primitive_goal_token_provider.py tests/test_primitive_token_status.py tests/test_primitive_coverage_status.py tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `55 passed`.
  - `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
    returned `5 passed`.
  - `python -m compileall -q testbed/planner/primitive_tokens.py testbed/policies/hybrid/primitive_planner.py tests/test_primitive_return_target_token_planner.py`
    completed with no output.
  - `python scripts/planner_refactor_guard.py --check-plan-contract`,
    `python scripts/planner_refactor_guard.py --check-skill-contract`, and
    `git diff --check` completed with no output.
- Next action: Phase 5.5 should continue with return-relocate token planning
  only. Do not migrate return-start-envelope, coverage planning/runtime, or
  backend behavior in the same commit.

### 2026-06-19 Phase 5.5 Return-Relocate Token Planning

- Scope: extracted return-relocate token derivation only. No return-start-
  envelope planning, observation injection key changes, coverage planning/
  runtime, backend selection, runtime package, behavior tree, VLM/LLM packet,
  default config, threshold, branch order, reason string, token schema, debug
  schema, rollout summary schema, or policy reset timing was intentionally
  changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `3a6f41ff5d541450929ccbf273a9bd599e4a277a`, no fetch, pull, or push. The
  worktree was clean before edits.
- Reflection gate:
  - Phase 1 through Phase 3 focused tests passed before Phase 5.5 edits:
    `python -m pytest -q tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `8 passed`.
  - Live evidence remains the successful `aggregate_tx24` rollout packet; its
    evidence report classifies `token.return_relocate` as confirmed-live and
    observes source `conditioned_return_operator_prior_sweep_belief`.
  - The only responsibility slice was return-relocate token derivation.
  - The stable focused owner for this slice is
    `testbed/planner/primitive_tokens.py`; it now owns
    `ReturnRelocateTokenPlanner`.
- Updated `PrimitivePlannerACTPolicy._return_relocate_tokens_for_obs()` to
  delegate token derivation to `ReturnRelocateTokenPlanner`. The legacy shell
  still owns return-target ensure timing, `_return_relocate_tokens` state write,
  source inheritance through debug reporting, and observation injection.
- Added `tests/test_primitive_return_relocate_token_planner.py` with focused
  coverage for copying the return-target token, clearing indices 7 and 8, and
  returning a read-only token. The TDD red test failed with `ImportError` before
  `ReturnRelocateTokenPlanner` was implemented.
- Old code parked/reclassified: no code was deleted. Return-start-envelope
  planning remains in the legacy shell until Phase 5.6. Coverage
  selection/update helpers remain legacy source-of-truth until Phase 6.
- Verification completed during this round:
  - `python -m pytest -q tests/test_primitive_return_relocate_token_planner.py`
    returned `1 passed`.
  - `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "injects_return_target_only_for_return_and_reuses_for_dig"`
    returned `1 passed, 119 deselected`.
  - `python -m pytest -q tests/test_primitive_return_relocate_token_planner.py tests/test_primitive_return_target_token_planner.py tests/test_primitive_dig_depth_profile_token_planner.py tests/test_primitive_dig_cut_token_planner.py tests/test_primitive_goal_token_provider.py tests/test_primitive_token_status.py tests/test_primitive_coverage_status.py tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `56 passed`.
  - `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
    returned `5 passed`.
  - `python -m compileall -q testbed/planner/primitive_tokens.py testbed/policies/hybrid/primitive_planner.py tests/test_primitive_return_relocate_token_planner.py`
    completed with no output.
  - `python scripts/planner_refactor_guard.py --check-plan-contract`,
    `python scripts/planner_refactor_guard.py --check-skill-contract`, and
    `git diff --check` completed with no output.
- Next action: Phase 5.6 should continue with return-start-envelope token
  planning only. Do not migrate coverage planning/runtime or backend behavior
  in the same commit.

### 2026-06-19 Phase 5.6 Return-Start-Envelope Token Planning

- Scope: extracted return-start-envelope token planning only. No coverage
  planning/runtime ownership, backend selection, runtime package, behavior tree,
  VLM/LLM packet, default config, threshold, branch order, reason string, token
  schema, debug schema, rollout summary schema, or policy reset timing was
  intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `5ab14c13e88538cfa80ed87610b93d90fb0f67bb`, no fetch, pull, or push. The
  worktree was clean before edits.
- Reflection gate:
  - Phase 1 through Phase 3 focused tests passed before Phase 5.6 edits:
    `python -m pytest -q tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `8 passed`.
  - Live evidence remains the successful `aggregate_tx24` rollout packet; its
    evidence report classifies `token.return_start_envelope` as confirmed-live
    and observes source `qc6_return_start_envelope_global+relocate_spatial_linear+relocate_qpos_linear`.
  - The only responsibility slice was return-start-envelope token planning.
  - The stable focused owner for this slice is
    `testbed/planner/primitive_tokens.py`; it now owns
    `ReturnStartEnvelopeTokenPlanner`,
    `ReturnStartEnvelopeTokenPlan`, and
    `ReturnStartEnvelopeConditioningConfig`.
- Updated `PrimitivePlannerACTPolicy._build_return_start_envelope_tokens_for_obs()`
  and compatibility helpers to delegate token/prior/conditioning computation to
  `ReturnStartEnvelopeTokenPlanner`. The legacy shell still owns corridor-id to
  cell-id resolution, return-cycle timing, state writes for source/bounds flags,
  envelope gate checks, coverage runtime state, and observation injection.
- Added `tests/test_primitive_return_start_envelope_token_planner.py` with
  focused coverage for cell prior source selection, live-current-observation
  fallback token construction, and qpos/spatial relocate conditioning. The TDD
  red test failed with `ImportError` before
  `ReturnStartEnvelopeTokenPlanner` was implemented.
- Old code parked/reclassified: no code was deleted. Coverage selection/update
  helpers remain legacy source-of-truth until Phase 6, and legacy FSM branch
  execution remains in the shell until Phase 7.
- Verification completed during this round:
  - `python -m pytest -q tests/test_primitive_return_start_envelope_token_planner.py`
    returned `3 passed`.
  - `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "return_envelope or start_envelope"`
    returned `11 passed, 109 deselected`.
  - `python -m pytest -q tests/test_primitive_return_start_envelope_token_planner.py tests/test_primitive_return_relocate_token_planner.py tests/test_primitive_return_target_token_planner.py tests/test_primitive_dig_depth_profile_token_planner.py tests/test_primitive_dig_cut_token_planner.py tests/test_primitive_goal_token_provider.py tests/test_primitive_token_status.py tests/test_primitive_coverage_status.py tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `59 passed`.
  - `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
    returned `5 passed`.
  - `python -m compileall -q testbed/planner/primitive_tokens.py testbed/policies/hybrid/primitive_planner.py tests/test_primitive_return_start_envelope_token_planner.py`
    completed with no output.
  - `python scripts/planner_refactor_guard.py --check-plan-contract`,
    `python scripts/planner_refactor_guard.py --check-skill-contract`, and
    `git diff --check` completed with no output.
- Next action: Phase 6.1 should begin coverage planning/runtime service work
  with corridor candidate construction only. Do not migrate scoring/selection,
  completion/rejection updates, terminal-stop requests, decision trace/report
  projection, or backend behavior in the same commit.

### 2026-06-19 Phase 6.1 Coverage Candidate Construction

- Scope: extracted coverage corridor candidate construction only. No scoring/
  selection ownership, completion/rejection state updates, terminal-stop
  requests, decision trace/report projection, backend selection, runtime
  package, behavior tree, VLM/LLM packet, default config, threshold, branch
  order, reason string, token schema, debug schema, rollout summary schema, or
  policy reset timing was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `d1ad00c56d9d0a73d5af85e045e051960f77bed4`, no fetch, pull, or push. The
  worktree was clean before edits.
- Reflection gate:
  - Phase 1 through Phase 3 focused tests passed before Phase 6.1 edits:
    `python -m pytest -q tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `8 passed`.
  - Live evidence remains the successful `aggregate_tx24` rollout packet; its
    resolved config uses `coverage.candidate_layout=cell_weighted_3x2`, and the
    golden-window contract locks coverage selected corridor fields and trace
    surfaces.
  - The only responsibility slice was coverage corridor candidate construction.
  - The stable focused owner for this slice is
    `testbed/planner/primitive_coverage.py`; it owns `CoverageCorridorState`
    and `CoverageCandidateBuilder`.
- Updated `PrimitivePlannerACTPolicy._ensure_coverage_corridors()` and related
  compatibility helpers to delegate candidate construction to
  `CoverageCandidateBuilder`. The legacy shell still owns when candidates are
  built, scoring/selection, candidate score payloads, coverage state updates,
  terminal-stop decisions, and trace/report projection.
- Added `tests/test_primitive_coverage_candidates.py` with focused coverage for
  percentile-grid candidate construction and `cell_weighted_3x2` prior-backed
  candidate construction. The TDD red test failed with `ModuleNotFoundError`
  before `testbed.planner.primitive_coverage` was implemented.
- Old code parked/reclassified: no code was deleted. Coverage scoring,
  selection, completion/rejection updates, terminal stop, and trace/report
  projection remain legacy source-of-truth until their own Phase 6 slices.
- Verification completed during this round:
  - `python -m pytest -q tests/test_primitive_coverage_candidates.py` returned
    `2 passed`.
  - `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "coverage_keeps_legacy_percentile_grid_without_cells or coverage_outputs_finite_token_in_prior_range or coverage_first_dig_prefers_nearest_entry or coverage_first_dig_prefers_bootstrap_friendly_corridor"`
    returned `4 passed, 116 deselected`.
  - `python -m pytest -q tests/test_primitive_coverage_candidates.py tests/test_primitive_return_start_envelope_token_planner.py tests/test_primitive_return_relocate_token_planner.py tests/test_primitive_return_target_token_planner.py tests/test_primitive_dig_depth_profile_token_planner.py tests/test_primitive_dig_cut_token_planner.py tests/test_primitive_goal_token_provider.py tests/test_primitive_token_status.py tests/test_primitive_coverage_status.py tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `61 passed`.
  - `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
    returned `5 passed`.
  - `python -m compileall -q testbed/planner/primitive_coverage.py testbed/policies/hybrid/primitive_planner.py tests/test_primitive_coverage_candidates.py`
    completed with no output.
  - `python scripts/planner_refactor_guard.py --check-plan-contract`,
    `python scripts/planner_refactor_guard.py --check-skill-contract`, and
    `git diff --check` completed with no output.
- Next action: Phase 6.2 should continue with coverage scoring/selection only.
  Do not migrate completion/rejection updates, terminal-stop requests,
  decision trace/report projection, or backend behavior in the same commit.

### 2026-06-19 Phase 6.2 Coverage Scoring And Selection

- Scope: extracted coverage scoring and corridor selection only. No coverage
  completion/rejection state updates, terminal-stop request ownership,
  decision trace/report projection, backend selection, runtime package,
  behavior tree, VLM/LLM packet, default config, threshold, branch order,
  reason string, token schema, debug schema, rollout summary schema, or policy
  reset timing was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `19174b7ba28cba82466b8e956fa60b1c90b88db9`, no fetch, pull, or push. The
  worktree was clean before edits.
- Reflection gate:
  - Phase 1 through Phase 3 focused tests remained the compatibility baseline:
    `python -m pytest -q tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`.
  - Live evidence remains the successful `aggregate_tx24` rollout packet; its
    resolved config uses `coverage.candidate_layout=cell_weighted_3x2`, and the
    golden-window contract locks coverage selected corridor fields and trace
    surfaces.
  - The only responsibility slice was coverage score/payload construction and
    selected-corridor choice. Reopen/terminal-stop side effects and decision
    event recording stayed in the legacy shell.
  - The stable focused owner for this slice is
    `testbed/planner/primitive_coverage.py`; it now owns
    `CoverageSelectionConfig`, `CoverageCandidateSelectionFacts`,
    `CoverageSelectionResult`, and `CoverageSelectionService`.
- Updated `PrimitivePlannerACTPolicy._select_coverage_corridor()` to collect
  explicit observation facts, delegate scoring/selection to
  `CoverageSelectionService`, copy back candidate score payloads, and keep the
  existing decision event plus all-depleted reopen/terminal-stop sequence in
  the shell.
- Reclassified the old score, first-dig gate, rare-cell gate, recent-row
  penalty, attempt-limit, cell-confidence, and coverage cell/row helpers as
  compatibility facades over `CoverageSelectionService`. Planner-specific
  observation facts such as remaining depth, entry distance, qpos delta, and
  state exemplar lookup remain in the shell until their own extraction is
  approved.
- Added `tests/test_primitive_coverage_selection.py` with service-versus-facade
  parity coverage for selected corridor, first-dig gate availability, candidate
  score payload fields, and corridor `score`/`last_remaining_depth_m` mutation.
  The TDD red test failed with `ImportError` before
  `CoverageSelectionService` was implemented.
- Old code parked/reclassified: no coverage completion/rejection updates,
  terminal-stop request ownership, trace/report projection, or backend behavior
  was moved. Those remain legacy source-of-truth until later Phase 6/7 slices.
- Verification completed during this round:
  - `python -m pytest -q tests/test_primitive_coverage_selection.py` returned
    `1 passed`.
  - `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "coverage_first_dig or coverage_penalizes_recent_row or cell_weighted_penalizes_recent_cell_row or rare_cell or coverage_multi_pass or trace_records_terminal_depletion"`
    returned `10 passed, 110 deselected`.
  - `python -m pytest -q tests/test_primitive_coverage_selection.py tests/test_primitive_coverage_candidates.py tests/test_primitive_return_start_envelope_token_planner.py tests/test_primitive_return_relocate_token_planner.py tests/test_primitive_return_target_token_planner.py tests/test_primitive_dig_depth_profile_token_planner.py tests/test_primitive_dig_cut_token_planner.py tests/test_primitive_goal_token_provider.py tests/test_primitive_token_status.py tests/test_primitive_coverage_status.py tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `62 passed`.
  - `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
    returned `5 passed`.
  - `python -m compileall -q testbed/planner/primitive_coverage.py testbed/policies/hybrid/primitive_planner.py tests/test_primitive_coverage_selection.py`
    completed with no output.
  - `python scripts/planner_refactor_guard.py --check-plan-contract`,
    `python scripts/planner_refactor_guard.py --check-skill-contract`, and
    `git diff --check` completed with no output.
- Next action: Phase 6.3 should continue with coverage completion/rejection
  state updates only. Do not migrate terminal-stop request ownership, decision
  trace/report projection, `_maybe_switch_skill()` branch bodies, backend
  behavior, or runtime effects in the same commit.

### 2026-06-19 Phase 6.3 Coverage Completion And Rejection Updates

- Scope: extracted coverage completion/rejection state updates only. No
  terminal-stop request ownership, multi-pass reopen ownership, decision
  trace/report projection, backend selection, runtime package, behavior tree,
  VLM/LLM packet, default config, threshold, branch order, reason string, token
  schema, debug schema, rollout summary schema, or policy reset timing was
  intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `7d4147e5e92d43cd1b80f78a017a3f4adc580984`, no fetch, pull, or push. The
  worktree was clean before edits.
- Reflection gate:
  - Phase 1 through Phase 3 focused tests remained the compatibility baseline:
    `python -m pytest -q tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`.
  - Live evidence remains the successful `aggregate_tx24` rollout packet; its
    golden-window contract locks coverage selected corridor fields and trace
    surfaces.
  - The only responsibility slice was completion/rejection state mutation:
    payload/deposit accounting, belief update, low-productivity streaks,
    attempt count, depletion flags, final corridor reason, and rejected state
    exemplar ids. Trace recording, all-depleted reopen, and terminal-stop
    requests stayed in the legacy shell.
  - `testbed/planner/primitive_coverage.py` stayed at 813 lines after Phase
    6.2. To avoid pushing that focused module over the 1000-line large-file
    threshold, this slice introduced the stable owner
    `testbed/planner/primitive_coverage_updates.py` for
    `CoverageUpdateService` and its explicit completion/rejection facts.
- Updated `PrimitivePlannerACTPolicy._complete_coverage_dig()`,
  `_complete_coverage_dump()`, `_reject_active_coverage_corridor()`, and
  `_update_corridor_belief()` to delegate mutation to `CoverageUpdateService`.
  The planner shell still prepares observation facts, records the existing
  `complete_dump`/`reject_corridor` trace payloads, and owns all terminal-stop
  and reopen side effects.
- Added `tests/test_primitive_coverage_updates.py` with service-versus-facade
  parity coverage for dump completion and counted rejection. The TDD red test
  first failed with `ImportError` before `CoverageUpdateService` was
  implemented.
- Old code parked/reclassified: terminal-stop request ownership, multi-pass
  reopen, coverage decision trace/report projection, and backend behavior
  remain legacy source-of-truth until later Phase 6/7 slices.
- Verification completed during this round:
  - `python -m pytest -q tests/test_primitive_coverage_updates.py` returned
    `2 passed`.
  - `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "coverage_attempt_limit or coverage_terminal_stop_when_all_depleted or coverage_multi_pass or sweep_belief_updates_corridor_on_dump or records_coverage_decision_trace or trace_records_terminal_depletion or bad_dig_replans"`
    returned `11 passed, 109 deselected`.
  - `python -m pytest -q tests/test_primitive_coverage_updates.py tests/test_primitive_coverage_selection.py tests/test_primitive_coverage_candidates.py tests/test_primitive_return_start_envelope_token_planner.py tests/test_primitive_return_relocate_token_planner.py tests/test_primitive_return_target_token_planner.py tests/test_primitive_dig_depth_profile_token_planner.py tests/test_primitive_dig_cut_token_planner.py tests/test_primitive_goal_token_provider.py tests/test_primitive_token_status.py tests/test_primitive_coverage_status.py tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `64 passed`.
  - `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
    returned `5 passed`.
  - `python -m compileall -q testbed/planner/primitive_coverage.py testbed/planner/primitive_coverage_updates.py testbed/policies/hybrid/primitive_planner.py tests/test_primitive_coverage_updates.py`
    completed with no output.
  - `python scripts/planner_refactor_guard.py --check-plan-contract`,
    `python scripts/planner_refactor_guard.py --check-skill-contract`, and
    `git diff --check` completed with no output.
- Next action: Phase 6.4 should continue with coverage terminal-stop and
  multi-pass reopen request ownership only. Do not migrate decision
  trace/report projection, `_maybe_switch_skill()` branch bodies, backend
  behavior, or runtime effects in the same commit.

### 2026-06-19 Phase 6.4 Coverage Runtime Requests

- Scope: extracted coverage multi-pass reopen and terminal-stop request gating
  only. No decision trace/report projection ownership, backend selection,
  runtime package, behavior tree, VLM/LLM packet, default config, threshold,
  branch order, reason string, token schema, debug schema, rollout summary
  schema, or policy reset timing was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `4e06e6d6230d844e2bdbabe9598e0aaae1b91ac5`, no fetch, pull, or push. The
  worktree was clean before edits.
- Reflection gate:
  - Phase 1 through Phase 3 focused tests remained the compatibility baseline:
    `python -m pytest -q tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`.
  - Live evidence remains the successful `aggregate_tx24` rollout packet; its
    golden-window contract locks coverage selected corridor fields and trace
    surfaces.
  - The only responsibility slice was runtime request gating/state mutation:
    multi-pass reopen eligibility, reopened corridor reset, pass/global streak
    reset, rejected-exemplar clear signal, and terminal-stop replace gating.
    Trace event construction stayed in the legacy shell.
- Extended `testbed/planner/primitive_coverage_updates.py` with
  `CoverageRuntimeService`, explicit reopen/terminal facts, and result records.
  The planner shell now prepares remaining-depth facts, applies returned
  pass/terminal state, and records the existing `reopen_coverage_pass` and
  `terminal_stop` trace events without changing their schema.
- Added `tests/test_primitive_coverage_runtime.py` with service-versus-facade
  parity coverage for multi-pass reopen and terminal-stop replace gating. The
  TDD red test failed with `ImportError` before `CoverageRuntimeService` was
  implemented.
- Old code parked/reclassified: coverage decision trace/report projection,
  `_maybe_switch_skill()` branch bodies, backend behavior, and runtime effects
  remain legacy source-of-truth until later slices.
- Verification completed during this round:
  - `python -m pytest -q tests/test_primitive_coverage_runtime.py` returned
    `2 passed`.
  - `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "coverage_multi_pass or coverage_terminal_stop_when_all_depleted or trace_records_terminal_depletion or coverage_attempt_limit or records_coverage_decision_trace"`
    returned `7 passed, 113 deselected`.
  - `python -m pytest -q tests/test_primitive_coverage_runtime.py tests/test_primitive_coverage_updates.py tests/test_primitive_coverage_selection.py tests/test_primitive_coverage_candidates.py tests/test_primitive_return_start_envelope_token_planner.py tests/test_primitive_return_relocate_token_planner.py tests/test_primitive_return_target_token_planner.py tests/test_primitive_dig_depth_profile_token_planner.py tests/test_primitive_dig_cut_token_planner.py tests/test_primitive_goal_token_provider.py tests/test_primitive_token_status.py tests/test_primitive_coverage_status.py tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `66 passed`.
  - `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
    returned `5 passed`.
  - `python -m compileall -q testbed/planner/primitive_coverage_updates.py testbed/policies/hybrid/primitive_planner.py tests/test_primitive_coverage_runtime.py`
    completed with no output.
  - `python scripts/planner_refactor_guard.py --check-plan-contract`,
    `python scripts/planner_refactor_guard.py --check-skill-contract`, and
    `git diff --check` completed with no output.
- Next action: Phase 6.5 should continue with coverage decision trace/report
  projection only. Do not migrate `_maybe_switch_skill()` branch bodies,
  backend behavior, or runtime effects in the same commit.

### 2026-06-19 Phase 6.5 Coverage Report Projection

- Scope: extracted coverage corridor debug payloads and coverage decision-event
  payload construction only. No `_maybe_switch_skill()` branch bodies, backend
  selection, runtime package, behavior tree, VLM/LLM packet, default config,
  threshold, branch order, reason string, token schema, debug schema, rollout
  summary schema, or policy reset timing was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `5805e0dbde1ad6b8400f85c79cb70ced87b12b53`, no fetch, pull, or push. The
  worktree was clean before edits.
- Reflection gate:
  - Phase 1 through Phase 3 focused tests remained the compatibility baseline:
    `python -m pytest -q tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`.
  - Live evidence remains the successful `aggregate_tx24` rollout packet; its
    golden-window contract locks coverage selected corridor fields and trace
    surfaces.
  - The only responsibility slice was pure projection: `CoverageCorridorState`
    to debug dict and explicit coverage event snapshots to trace payload dict.
    Event append timing and top-level policy report composition stayed in the
    planner shell.
- Added `testbed/planner/primitive_coverage_reports.py` with
  `CoverageReportService`, `CoverageReportState`, and
  `CoverageBucketSnapshot`. The service receives explicit snapshots and returns
  dictionaries with the same keys and values as the legacy trace/debug payloads.
- Updated `PrimitivePlannerACTPolicy._coverage_corridor_to_debug()` and
  `_record_coverage_decision_event()` to delegate payload construction to
  `CoverageReportService`. The shell still decides when to append events and
  still owns the public `debug_state()`, `planner_trace()`, and rollout summary
  surfaces.
- Added `tests/test_primitive_coverage_reports.py` with service-versus-facade
  parity coverage for corridor debug dicts and decision-event payload dicts.
  The TDD red test failed with `ModuleNotFoundError` before
  `primitive_coverage_reports.py` was implemented.
- Old code parked/reclassified: `_maybe_switch_skill()` branch bodies, backend
  behavior, runtime effects, and top-level public report composition remain
  legacy source-of-truth until later slices.
- Verification completed during this round:
  - `python -m pytest -q tests/test_primitive_coverage_reports.py` returned
    `2 passed`.
  - `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "records_coverage_decision_trace or trace_records_terminal_depletion or coverage_first_dig or coverage_multi_pass or coverage_terminal_stop_when_all_depleted" tests/test_planner_current_code_parity.py`
    returned `9 passed, 114 deselected`.
  - `python -m pytest -q tests/test_primitive_coverage_reports.py tests/test_primitive_coverage_runtime.py tests/test_primitive_coverage_updates.py tests/test_primitive_coverage_selection.py tests/test_primitive_coverage_candidates.py tests/test_primitive_return_start_envelope_token_planner.py tests/test_primitive_return_relocate_token_planner.py tests/test_primitive_return_target_token_planner.py tests/test_primitive_dig_depth_profile_token_planner.py tests/test_primitive_dig_cut_token_planner.py tests/test_primitive_goal_token_provider.py tests/test_primitive_token_status.py tests/test_primitive_coverage_status.py tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `68 passed`.
  - `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
    returned `5 passed`.
  - `python -m compileall -q testbed/planner/primitive_coverage_reports.py testbed/policies/hybrid/primitive_planner.py tests/test_primitive_coverage_reports.py`
    completed with no output.
  - `python scripts/planner_refactor_guard.py --check-plan-contract`,
    `python scripts/planner_refactor_guard.py --check-skill-contract`, and
    `git diff --check` completed with no output.
- Next action: Phase 7.1 should begin Slice 7 with the legacy FSM backend
  protocol/adapter boundary only. Do not move branch bodies, change branch
  order, change reason strings, or apply effects through the new boundary until
  a focused parity test is in place.

### 2026-06-19 Phase 7.1 Legacy FSM Backend Adapter Boundary

- Scope: introduced the legacy FSM backend protocol/adapter boundary only. No
  `_maybe_switch_skill()` branch body, branch order, reason string, threshold,
  effect application, backend selection, runtime package, behavior tree,
  VLM/LLM packet, token schema, debug schema, rollout summary schema, or policy
  reset timing was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `e87ef02d6203451ce8959ed3c73c8526765bb111`, no fetch, pull, or push. The
  worktree was clean before edits.
- Reflection gate:
  - Phase 1 through Phase 3 focused tests remained the compatibility baseline:
    `python -m pytest -q tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`.
  - Live evidence remains the successful `aggregate_tx24` rollout packet; the
    golden-window parity contract locks public tick/report behavior.
  - The only responsibility slice was the backend call boundary: call the
    existing already-mutating legacy FSM once, then wrap the observable outcome
    as `PrimitiveDecisionResult`.
- Added `testbed/planner/primitive_backend.py` with `PrimitiveDecisionBackend`
  and `LegacyFSMBackendAdapter`. The adapter receives explicit callbacks for
  `maybe_switch_skill`, current skill name, and current switch reason. It does
  not receive planner `self` and does not own any branch logic yet.
- Updated `PrimitivePlannerACTPolicy._decide_tick_with_legacy_fsm()` to
  delegate to `_legacy_fsm_backend().decide_tick(...)`. `_maybe_switch_skill()`
  and the 5P compatibility override remain unchanged legacy source-of-truth.
- Added `tests/test_primitive_backend.py` with direct adapter coverage. The TDD
  red test failed with `ModuleNotFoundError` before `primitive_backend.py` was
  implemented.
- Old code parked/reclassified: all branch bodies, effect application, backend
  selection, and alternate backend behavior remain legacy source-of-truth until
  later Phase 7 slices.
- Verification completed during this round:
  - `python -m pytest -q tests/test_primitive_backend.py tests/test_primitive_decision_contract.py`
    returned `4 passed`.
  - `python -m pytest -q tests/test_primitive_execution_template.py tests/test_planner_current_code_parity.py`
    returned `5 passed`.
  - `python -m pytest -q tests/test_primitive_backend.py tests/test_primitive_coverage_reports.py tests/test_primitive_coverage_runtime.py tests/test_primitive_coverage_updates.py tests/test_primitive_coverage_selection.py tests/test_primitive_coverage_candidates.py tests/test_primitive_return_start_envelope_token_planner.py tests/test_primitive_return_relocate_token_planner.py tests/test_primitive_return_target_token_planner.py tests/test_primitive_dig_depth_profile_token_planner.py tests/test_primitive_dig_cut_token_planner.py tests/test_primitive_goal_token_provider.py tests/test_primitive_token_status.py tests/test_primitive_coverage_status.py tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `69 passed`.
  - `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
    returned `5 passed`.
  - `python -m compileall -q testbed/planner/primitive_backend.py testbed/policies/hybrid/primitive_planner.py tests/test_primitive_backend.py`
    completed with no output.
  - `python scripts/planner_refactor_guard.py --check-plan-contract`,
    `python scripts/planner_refactor_guard.py --check-skill-contract`, and
    `git diff --check` completed with no output.
- Next action: Phase 7.2 may migrate exactly one legacy FSM branch chain behind
  the backend adapter, starting with a focused service-vs-facade parity test.
  Do not move multiple branches, change branch order, or change reason strings
  in the same commit.

### 2026-06-19 Phase 7.2 Legacy FSM Bootstrap Branch

- Scope: migrated the 4P legacy FSM bootstrap branch only. No 5P override,
  pre-dig-align, dig, carry, dump, return, direct-handoff branch body, branch
  order, reason string, threshold, effect application, backend selection,
  runtime package, behavior tree, VLM/LLM packet, token schema, debug schema,
  rollout summary schema, or policy reset timing was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `3b10ef2b2f50708f876ff8662268f9ff94f21403`, no fetch, pull, or push. The
  worktree was clean before edits.
- Reflection gate:
  - Phase 1 through Phase 3 focused tests remained the compatibility baseline:
    `python -m pytest -q tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`.
  - Live evidence remains the successful `aggregate_tx24` rollout packet; the
    golden-window parity contract locks public tick/report behavior.
  - The only responsibility slice was the first branch in the 4P
    `_maybe_switch_skill()` order: bootstrap handling. It still calls the same
    `_should_end_bootstrap()`, pre-dig-align gate, and `_set_skill()` callbacks.
- Extended `testbed/planner/primitive_backend.py` with
  `LegacyFSMBootstrapConfig` and `LegacyFSMBootstrapBranch`. The branch object
  receives explicit callbacks and does not receive planner `self`.
- Updated the 4P `PrimitivePlannerACTPolicy._maybe_switch_skill()` first check
  to delegate to `self._legacy_fsm_bootstrap_branch().maybe_handle(...)` and
  return when handled. The 5P compatibility override remains unchanged.
- Extended `tests/test_primitive_backend.py` with direct bootstrap branch
  coverage for the pre-dig-align path and non-bootstrap no-op path. The TDD red
  test failed with `ImportError` before the backend branch classes were
  implemented.
- Old code parked/reclassified: every non-bootstrap FSM branch and the 5P
  override remain legacy source-of-truth until later Phase 7 slices.
- Verification completed during this round:
  - `python -m pytest -q tests/test_primitive_backend.py tests/test_primitive_decision_contract.py tests/test_agx_primitives_v2_2.py -k "bootstrap or first_dig_policy_for_cycle_zero"`
    returned `7 passed, 119 deselected`.
  - `python -m pytest -q tests/test_primitive_execution_template.py tests/test_planner_current_code_parity.py`
    returned `5 passed`.
  - `python -m pytest -q tests/test_primitive_backend.py tests/test_primitive_coverage_reports.py tests/test_primitive_coverage_runtime.py tests/test_primitive_coverage_updates.py tests/test_primitive_coverage_selection.py tests/test_primitive_coverage_candidates.py tests/test_primitive_return_start_envelope_token_planner.py tests/test_primitive_return_relocate_token_planner.py tests/test_primitive_return_target_token_planner.py tests/test_primitive_dig_depth_profile_token_planner.py tests/test_primitive_dig_cut_token_planner.py tests/test_primitive_goal_token_provider.py tests/test_primitive_token_status.py tests/test_primitive_coverage_status.py tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `71 passed`.
  - `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
    returned `5 passed`.
  - `python -m compileall -q testbed/planner/primitive_backend.py testbed/policies/hybrid/primitive_planner.py tests/test_primitive_backend.py`
    completed with no output.
  - `python scripts/planner_refactor_guard.py --check-plan-contract`,
    `python scripts/planner_refactor_guard.py --check-skill-contract`, and
    `git diff --check` completed with no output.
- Next action: Phase 7.3 may migrate exactly one additional mainline legacy FSM
  branch chain behind the backend adapter, starting with the 4P dig branch.
  Keep pre-dig-align in legacy parking unless explicitly re-approved. Do not
  move carry/dump/return branches, change branch order, or change reason
  strings in the same commit.

### 2026-06-19 Phase 7.3 Legacy FSM Dig Branch

- Scope: migrated the 4P legacy FSM `dig` branch only. No 5P override,
  pre-dig-align legacy parking branch, carry, dump, return, direct-handoff
  branch body, branch order, reason string, threshold, backend selection,
  runtime package, behavior tree, VLM/LLM packet, token schema, debug schema,
  rollout summary schema, or policy reset timing was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `4f5472b6a6a1802d1967cc0225ffad5628bd14cf`, no fetch, pull, or push. The
  worktree was clean before edits.
- Reflection gate:
  - Phase 1 through Phase 3 focused tests remained the compatibility baseline:
    `python -m pytest -q tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`.
  - Live evidence remains the successful `aggregate_tx24` rollout packet; the
    golden-window parity contract locks public tick/report behavior.
  - The migrated branch is mainline `dig`, not the legacy parked
    `pre_dig_align` branch. The pre-dig-align branch stays in the shell unless
    explicitly re-approved.
- Extended `testbed/planner/primitive_backend.py` with `LegacyFSMDigConfig` and
  `LegacyFSMDigBranch`. The branch object receives explicit callbacks and owns
  the original `dig` branch order: exit guard, bad-dig replan, complete-boundary
  low-payload replan, then dig-to-carry handoff.
- Updated the 4P `PrimitivePlannerACTPolicy._maybe_switch_skill()` `dig` check
  to delegate to `self._legacy_fsm_dig_branch().maybe_handle(...)`. Existing
  callbacks still apply legacy side effects, so reason strings and reset timing
  stay unchanged.
- Extended `tests/test_primitive_backend.py` with direct dig branch coverage for
  the dig-to-carry path and non-dig no-op path. The TDD red test failed with
  `ImportError` before the backend dig branch classes were implemented.
- Old code parked/reclassified: carry, dump, return, direct-handoff,
  pre-dig-align, 5P override, backend selection, and alternate backend behavior
  remain legacy source-of-truth until later slices.
- Verification completed during this round:
  - `python -m pytest -q tests/test_primitive_backend.py tests/test_primitive_decision_contract.py tests/test_agx_primitives_v2_2.py -k "dig_to_carry or bad_dig_replans or dig_exit_guard or complete_low_payload or first_dig_policy_for_cycle_zero"`
    returned `9 passed, 119 deselected`.
  - `python -m pytest -q tests/test_primitive_execution_template.py tests/test_planner_current_code_parity.py`
    returned `5 passed`.
  - `python -m pytest -q tests/test_primitive_backend.py tests/test_primitive_coverage_reports.py tests/test_primitive_coverage_runtime.py tests/test_primitive_coverage_updates.py tests/test_primitive_coverage_selection.py tests/test_primitive_coverage_candidates.py tests/test_primitive_return_start_envelope_token_planner.py tests/test_primitive_return_relocate_token_planner.py tests/test_primitive_return_target_token_planner.py tests/test_primitive_dig_depth_profile_token_planner.py tests/test_primitive_dig_cut_token_planner.py tests/test_primitive_goal_token_provider.py tests/test_primitive_token_status.py tests/test_primitive_coverage_status.py tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `73 passed`.
  - `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
    returned `5 passed`.
  - `python -m compileall -q testbed/planner/primitive_backend.py testbed/policies/hybrid/primitive_planner.py tests/test_primitive_backend.py`
    completed with no output.
  - `python scripts/planner_refactor_guard.py --check-plan-contract`,
    `python scripts/planner_refactor_guard.py --check-skill-contract`, and
    `git diff --check` completed with no output.
- Next action: Phase 7.4 may migrate exactly one additional mainline legacy FSM
  branch chain, likely the 4P carry branch. Do not move dump/return branches,
  direct-handoff helpers, pre-dig-align, 5P override, change branch order, or
  change reason strings in the same commit.

### 2026-06-19 Phase 7.4 Legacy FSM Carry Branch

- Scope: migrated the 4P legacy FSM `carry` branch only. No 5P override,
  pre-dig-align legacy parking branch, dump, return, direct-handoff helper body,
  branch order, reason string, threshold, backend selection, runtime package,
  behavior tree, VLM/LLM packet, token schema, debug schema, rollout summary
  schema, or policy reset timing was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `a50eb86f2d51842c699e303645827f00442709df`, no fetch, pull, or push. The
  worktree was clean before edits.
- Reflection gate:
  - Phase 1 through Phase 3 focused tests remained the compatibility baseline:
    `python -m pytest -q tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`.
  - Live evidence remains the successful `aggregate_tx24` rollout packet; the
    evidence matrix marks `gate.carry_to_dump` as confirmed-live and the golden
    window contains `carry_to_dump_dump_committed_boundary` transitions.
  - The migrated branch is mainline `carry` only. `dump`, `return`,
    `pre_dig_align`, direct-handoff helper internals, and the 5P override remain
    outside this slice.
- Extended `testbed/planner/primitive_backend.py` with `LegacyFSMCarryConfig`
  and `LegacyFSMCarryBranch`. The branch object receives explicit callbacks,
  consumes `CarryTransitionStatus`, and preserves the old priority order:
  release-safety return handoff, dump-complete return handoff, hold-count update,
  then ready-to-dump switch.
- Updated the 4P `PrimitivePlannerACTPolicy._maybe_switch_skill()` `carry` check
  to delegate to `self._legacy_fsm_carry_branch().maybe_handle(...)`. The policy
  shell now constructs `CarryTransitionStatus` from explicit observation facts
  and existing dump-ready/dump-done config values, then applies only the legacy
  side effects requested by the branch.
- Extended `tests/test_primitive_backend.py` with direct carry branch coverage
  for release-safety return handoff, dump-committed boundary switch to dump, and
  non-carry no-op. The TDD red test failed with `ImportError` before the backend
  carry branch classes were implemented.
- Old code parked/reclassified: dump, return, direct-handoff helper internals,
  pre-dig-align, 5P override, backend selection, and alternate backend behavior
  remain legacy source-of-truth until later slices.
- Verification completed during this round:
  - `python -m pytest -q tests/test_primitive_backend.py` returned `8 passed`.
  - `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "semantic_boundary_events_drive_skill_sequence or semantic_carry_release_safety_exits_carry_after_unplanned_release or uses_dump_area_relative_readiness_not_horizontal_only or does_not_bypass_position_when_footprint_not_required or carry_to_dump"`
    returned `4 passed, 116 deselected`.
  - `python -m pytest -q tests/test_primitive_backend.py tests/test_primitive_decision_contract.py`
    returned `11 passed`.
  - `python -m pytest -q tests/test_primitive_execution_template.py tests/test_planner_current_code_parity.py`
    returned `5 passed`.
  - `python -m pytest -q tests/test_primitive_backend.py tests/test_primitive_coverage_reports.py tests/test_primitive_coverage_runtime.py tests/test_primitive_coverage_updates.py tests/test_primitive_coverage_selection.py tests/test_primitive_coverage_candidates.py tests/test_primitive_return_start_envelope_token_planner.py tests/test_primitive_return_relocate_token_planner.py tests/test_primitive_return_target_token_planner.py tests/test_primitive_dig_depth_profile_token_planner.py tests/test_primitive_dig_cut_token_planner.py tests/test_primitive_goal_token_provider.py tests/test_primitive_token_status.py tests/test_primitive_coverage_status.py tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `76 passed`.
  - `python -m pytest -q tests/test_agx_primitives_v2_2.py` returned
    `120 passed`.
  - `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
    returned `5 passed`.
- Next action: Phase 7.5 may migrate exactly one additional mainline legacy FSM
  branch chain, likely the 4P dump branch. Do not move return branches,
  direct-handoff helper internals, pre-dig-align, 5P override, change branch
  order, or change reason strings in the same commit.

### 2026-06-19 Phase 7.5 Legacy FSM Dump Branch

- Scope: migrated the 4P legacy FSM `dump` branch only. No 5P override,
  pre-dig-align legacy parking branch, return branch, direct-handoff helper
  body, branch order, reason string, threshold, backend selection, runtime
  package, behavior tree, VLM/LLM packet, token schema, debug schema, rollout
  summary schema, or policy reset timing was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `85c28e6a0f050c620d9ce61878bf3c873fb93c3c`, no fetch, pull, or push. The
  worktree was clean before edits.
- Reflection gate:
  - Phase 1 through Phase 3 focused tests remained the compatibility baseline:
    `python -m pytest -q tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`.
  - Live evidence remains the successful `aggregate_tx24` rollout packet; the
    evidence matrix marks `gate.dump_to_return` as confirmed-live and the golden
    window contains `dump_to_return_dump_complete_boundary` transitions.
  - The migrated branch is mainline `dump` only. The `return` branch,
    `pre_dig_align`, direct-handoff helper internals, and the 5P override remain
    outside this slice.
- Extended `testbed/planner/primitive_backend.py` with `LegacyFSMDumpConfig` and
  `LegacyFSMDumpBranch`. The branch object receives explicit callbacks,
  consumes `DumpTransitionStatus`, and preserves the old priority order:
  boundary dump completion first, then legacy mass-low hold completion.
- Updated the 4P `PrimitivePlannerACTPolicy._maybe_switch_skill()` `dump` check
  to delegate to `self._legacy_fsm_dump_branch().maybe_handle(...)`. The policy
  shell now constructs `DumpTransitionStatus` from explicit observation facts
  and existing dump-done config values, then applies only the legacy side effects
  requested by the branch.
- Extended `tests/test_primitive_backend.py` with direct dump branch coverage for
  boundary return handoff, mass-low hold return handoff, and non-dump no-op. The
  TDD red test failed with `ImportError` before the backend dump branch classes
  were implemented.
- Old code parked/reclassified: return branch, direct-handoff helper internals,
  pre-dig-align, 5P override, backend selection, and alternate backend behavior
  remain legacy source-of-truth until later slices.
- Verification completed during this round:
  - `python -m pytest -q tests/test_primitive_backend.py` returned `11 passed`.
  - `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "semantic_boundary_events_drive_skill_sequence or can_wait_past_dump_end_boundary_for_hold or uses_dump_end_boundary_by_default or dump_to_return or mass_low"`
    returned `3 passed, 117 deselected`.
  - `python -m pytest -q tests/test_primitive_backend.py tests/test_primitive_decision_contract.py`
    returned `14 passed`.
  - `python -m pytest -q tests/test_primitive_execution_template.py tests/test_planner_current_code_parity.py`
    returned `5 passed`.
  - `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
    returned `5 passed`.
  - `python -m pytest -q tests/test_primitive_backend.py tests/test_primitive_coverage_reports.py tests/test_primitive_coverage_runtime.py tests/test_primitive_coverage_updates.py tests/test_primitive_coverage_selection.py tests/test_primitive_coverage_candidates.py tests/test_primitive_return_start_envelope_token_planner.py tests/test_primitive_return_relocate_token_planner.py tests/test_primitive_return_target_token_planner.py tests/test_primitive_dig_depth_profile_token_planner.py tests/test_primitive_dig_cut_token_planner.py tests/test_primitive_goal_token_provider.py tests/test_primitive_token_status.py tests/test_primitive_coverage_status.py tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `79 passed`.
  - `python -m pytest -q tests/test_agx_primitives_v2_2.py` returned
    `120 passed`.
- Next action: Phase 7.6 may migrate exactly one additional mainline legacy FSM
  branch chain, likely the 4P return branch. Do not move direct-handoff helper
  internals, pre-dig-align, 5P override, change branch order, or change reason
  strings in the same commit.

### 2026-06-19 Phase 7.6 Legacy FSM Return Branch

- Scope: migrated the 4P legacy FSM `return` branch only. No 5P override,
  pre-dig-align legacy parking branch, direct-handoff helper body, branch order,
  threshold, backend selection, runtime package, behavior tree, VLM/LLM packet,
  token schema, debug schema, rollout summary schema, or policy reset timing was
  intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `76e9c9f0ab8e0fb79fc56d16fe4203c70b01d612`, no fetch, pull, or push. The
  worktree was clean before edits.
- Reflection gate:
  - Phase 1 through Phase 3 focused tests remained the compatibility baseline:
    `python -m pytest -q tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`.
  - Live evidence remains the successful `aggregate_tx24` rollout packet; the
    evidence matrix marks `gate.return_to_dig` as confirmed-live and the golden
    window contains both `return_to_dig_next_dig_entry_ready` and
    `return_to_dig_start_envelope_ready` transitions.
  - The migrated branch is mainline `return` only. The `pre_dig_align` branch,
    direct-handoff helper internals, and the 5P override remain outside this
    slice.
- Extended `testbed/planner/primitive_backend.py` with `LegacyFSMReturnConfig`
  and `LegacyFSMReturnBranch`. The branch object receives explicit callbacks,
  consumes `ReturnTransitionStatus`, latches next-dig events, completes return
  transitions, and applies the original next-dig/direct-handoff/shallow-guard
  reason suffix priority.
- Updated the 4P `PrimitivePlannerACTPolicy._maybe_switch_skill()` `return`
  check to delegate to `self._legacy_fsm_return_branch().maybe_handle(...)`.
  The policy shell still calls the existing return-to-dig entry and
  start-envelope helpers before status construction so their debug-state side
  effects remain in the shell.
- Extended `tests/test_primitive_backend.py` with direct return branch coverage
  for next-dig event latching, completion ordering, after-completion next-skill
  selection, and non-return no-op. The TDD red test failed with `ImportError`
  before the backend return branch classes were implemented.
- Verification found and fixed one ordering regression: the first full
  `tests/test_agx_primitives_v2_2.py` run failed
  `test_primitive_planner_pre_dig_align_first_dig_only_skips_after_return`
  because `next_skill` was computed before incrementing `_cycle_index`. The fix
  moved next-skill selection into a callback executed after
  `_complete_return_transition_for_backend()`, matching the old branch order.
- Old code parked/reclassified: pre-dig-align, direct-handoff helper internals,
  5P override, backend selection, and alternate backend behavior remain legacy
  source-of-truth until a later explicit audit or user approval.
- Verification completed during this round:
  - `python -m pytest -q tests/test_primitive_backend.py -k "return_branch"`
    first failed with an unexpected `next_skill_after_return_transition`
    argument before the backend API fix, then returned `4 passed, 11 deselected`.
  - `python -m pytest -q tests/test_agx_primitives_v2_2.py::TestPrimitivesV22::test_primitive_planner_pre_dig_align_first_dig_only_skips_after_return`
    returned `1 passed` after the ordering fix.
  - `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "return_to_dig or return_entry_frame_can_direct_handoff_without_return_action or semantic_boundary_events_drive_skill_sequence or shallow_guard"`
    returned `5 passed, 115 deselected`.
  - `python -m pytest -q tests/test_primitive_backend.py tests/test_primitive_decision_contract.py`
    returned `18 passed`.
  - `python -m pytest -q tests/test_primitive_execution_template.py tests/test_planner_current_code_parity.py`
    returned `5 passed`.
  - `python -m pytest -q tests/test_primitive_backend.py tests/test_primitive_coverage_reports.py tests/test_primitive_coverage_runtime.py tests/test_primitive_coverage_updates.py tests/test_primitive_coverage_selection.py tests/test_primitive_coverage_candidates.py tests/test_primitive_return_start_envelope_token_planner.py tests/test_primitive_return_relocate_token_planner.py tests/test_primitive_return_target_token_planner.py tests/test_primitive_dig_depth_profile_token_planner.py tests/test_primitive_dig_cut_token_planner.py tests/test_primitive_goal_token_provider.py tests/test_primitive_token_status.py tests/test_primitive_coverage_status.py tests/test_primitive_capabilities.py tests/test_planner_current_code_parity.py tests/test_primitive_execution_template.py tests/test_primitive_decision_contract.py`
    returned `83 passed`.
  - `python -m pytest -q tests/test_agx_primitives_v2_2.py` returned
    `120 passed`.
  - `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
    returned `5 passed`.
- Next action: Phase 7.7 should audit the residual 4P `_maybe_switch_skill()`
  shell after all confirmed-live mainline branches have moved behind backend
  branch objects. Do not migrate `pre_dig_align`, 5P override, direct-handoff
  helper internals, or alternate backend behavior without a separate evidence
  and compatibility decision.

### 2026-06-19 Phase 7.7 Residual FSM Shell Audit

- Scope: audit and documentation only. No planner runtime code, tests, default
  config, branch order, reason string, token schema, debug schema, rollout
  summary schema, policy reset timing, 5P override, or `pre_dig_align` behavior
  was changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `7cc74f3ee6cad3a5496cc7b724d084e76d823a2e`, no fetch, pull, or push. The
  worktree was clean before edits.
- Audit result:
  - The 4P `_maybe_switch_skill()` shell now delegates the confirmed-live
    mainline branches to backend branch objects in the original order:
    bootstrap, dig, carry, dump, and return.
  - The only remaining inline 4P branch body is `pre_dig_align`. The selected
    successful evidence packet classifies `gate.pre_dig_align` as
    `dead-candidate` / `retain-legacy-parking`, so it must not be promoted into
    the mainline backend without explicit re-approval.
  - The 5P compatibility override and direct-handoff helper internals remain
    compatibility/helper owners. Moving them now would mix responsibility chains
    or create a pass-through abstraction.
- Completion decision: stop code migration for Slice 7 at the last verified
  mainline branch commit. Further planner code movement needs a separate user
  decision for one of these scopes: legacy pre-dig parking extraction, 5P
  compatibility audit, direct-handoff helper extraction, or backend selection
  cleanup.
- Verification completed during this audit round:
  - `git diff --check` completed with no output.
  - `python scripts/planner_refactor_guard.py --check-plan-contract` completed
    with no output.
  - `python scripts/planner_refactor_guard.py --check-skill-contract` completed
    with no output.
- Next action: prepare a handoff manifest from committed Phase 4 through Phase 7
  work. Do not migrate `pre_dig_align`, the 5P override, direct-handoff helper
  internals, or alternate backend behavior without a new evidence and
  compatibility decision.

### 2026-06-19 Phase 8 Effect Boundary Design

- Scope: documentation and architecture design only. No planner runtime code,
  tests, default config, branch order, reason string, token schema, debug
  schema, rollout summary schema, policy reset timing, 5P override,
  `pre_dig_align`, `cell_entry`, direct-handoff behavior, backend behavior, or
  low-level ACT dispatch was changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, no fetch, pull, or push. The worktree was clean
  before edits.
- Added `docs/planner_effect_boundary_design.md` as the Phase 8 design source
  for the `PlannerEffect` boundary.
- Updated `docs/planner_current_code_architecture_plan.md` so the new effect
  boundary design is a supporting design reference and the next approved
  planning scope.
- Design result:
  - The current `legacy_fsm_side_effects_applied` path remains a compatibility
    layer, not the final backend architecture.
  - Future backends should return ordered requested effects with
    `side_effects_applied=False`; the execution kernel/shell applier is the
    only layer allowed to apply mutations.
  - Effect families are semantic: skill lifecycle, counters/holds, return
    cycle, coverage updates, coverage runtime, token/plan lifecycle, and
    diagnostics.
  - Forbidden shapes include arbitrary planner attribute writes, method-call
    effects, callback/lambda payloads, and effects that promote `cell_entry` or
    `pre_dig_align` into the mainline backend without new evidence and approval.
  - Return direct-handoff and other coupled paths must be evaluated under this
    design before any code migration.
- Expected architecture coverage:
  - fills the missing contract between `PrimitiveDecisionBackend` and the
    execution kernel;
  - separates decision recording from requested mutation;
  - defines effect application ownership;
  - prevents the current callback backend from becoming the final abstraction.
- Not completed by this design: concrete requested-effect classes, live branch
  conversion, behavior-tree/VLM backend implementation, 5P compatibility audit,
  or legacy cleanup/deletion.

### 2026-06-19 Phase 8.1 Requested Effect Contract Foundation

- Scope: requested-effect contract foundation and execution hook only. No
  bootstrap, dig, carry, dump, return, direct-handoff, `pre_dig_align`,
  `cell_entry`, 5P override, branch order, reason string, threshold, backend
  selection, behavior tree, VLM/LLM packet, token schema, debug schema, rollout
  summary schema, policy reset timing, or low-level ACT dispatch behavior was
  intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `c3e2d6f7175b1e7cc4ca6b63865b015aedffc531`, no fetch, pull, or push. The
  worktree was clean before edits.
- Selected evidence remains the successful mainline packet:
  `runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/rollouts/rollout_000.jsonl`,
  its paired planner trace, rollout summary, resolved config, and
  `docs/planner_evidence_reports/2026-06-18-baseline-aggregate_tx24.md`.
- Confirmed-live method chain protected by this foundation:
  public tick execution calls `decide_tick()`, receives the legacy
  already-applied `PrimitiveDecisionResult`, skips requested-effect
  application, then continues return-timeout accounting and action dispatch in
  the existing order.
- Contract added in `testbed/planner/primitive_decision.py`:
  `RequestedPlannerEffect`, `PrimitiveDecisionResult.from_requested_effects()`,
  `PrimitiveDecisionContractError`, and
  `validate_decision_effect_contract()`.
- Execution hook added in `testbed/planner/primitive_execution.py`: requested
  effects are validated and passed to the applier after `decide_tick()` and
  before `account_return_timeout()` / `dispatch_action()`.
- Thin bridge added in `PrimitivePlannerACTPolicy`: the default legacy FSM path
  still returns `side_effects_applied=True`; `_apply_requested_tick_effects()`
  is a no-op foundation hook because no live backend emits requested effects in
  this phase.
- Validation foundation: rejects mixed already-applied/requested results,
  requested results carrying legacy effects, callable payloads, planner/self
  payload keys, and planner attr/method-call effect shapes.
- Added/updated focused tests:
  `tests/test_primitive_decision_contract.py` and
  `tests/test_primitive_execution_template.py`. The TDD red run failed on
  missing requested-effect imports before implementation; the focused green run
  returned `9 passed`.
- Old code parked/reclassified: no code was deleted. Existing legacy FSM branch
  objects and `_maybe_switch_skill()` shell remain the source of truth for live
  side effects; requested effects are only a validated future backend contract.
- Next action: do not migrate return direct-handoff, `pre_dig_align`,
  `cell_entry`, 5P override, or any branch to requested effects without a
  separate evidence-backed scope and concrete effect-family tests.

### 2026-06-19 Phase 8.2 Requested Effect Applier Guard

- Scope: real planner requested-effect applier guard only. No bootstrap, dig,
  carry, dump, return, direct-handoff, `pre_dig_align`, `cell_entry`, 5P
  override, branch order, reason string, threshold, backend selection, behavior
  tree, VLM/LLM packet, token schema, debug schema, rollout summary schema,
  policy reset timing, or low-level ACT dispatch behavior was intentionally
  changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `e2b83241fea3cf57cf072689410f30db51cd5f00`, no fetch, pull, or push. The
  worktree was clean before edits.
- Selected evidence remains the successful mainline packet:
  `runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/rollouts/rollout_000.jsonl`,
  its paired planner trace, rollout summary, resolved config, and
  `docs/planner_evidence_reports/2026-06-18-baseline-aggregate_tx24.md`.
- Confirmed-live method chain protected by this guard:
  public tick execution receives the legacy already-applied
  `PrimitiveDecisionResult`, skips requested-effect application, then continues
  return-timeout accounting and action dispatch in the existing order.
- Updated `PrimitivePlannerACTPolicy._apply_requested_tick_effects()` so an
  empty requested-effect tuple remains a no-op, but any non-empty tuple raises
  `PrimitiveDecisionContractError` with a message that live requested-effect
  application is not supported by the real planner shell yet.
- Added focused tests in `tests/test_primitive_decision_contract.py` for the
  real planner bridge empty-tuple no-op and non-empty requested-effect
  fail-fast behavior. The TDD red run failed because non-empty effects were
  silently ignored; after implementation the focused green run returned
  `11 passed`.
- Existing execution-template tests still cover fake hook requested-effect
  ordering and default legacy already-applied skip behavior.
- Old code parked/reclassified: no code was deleted. Requested effects remain a
  validated future backend contract only; no live effect family or FSM branch
  conversion was introduced.
- Next action: before enabling any live requested-effect application, add a
  concrete effect-family contract and focused parity tests for exactly one
  evidence-backed branch or shell-owned operation.

### 2026-06-22 Phase 8.3 SwitchSkill Requested Effect Family

- Scope: first concrete requested-effect family contract and real shell applier
  support only. No bootstrap, dig, carry, dump, return, direct-handoff,
  `pre_dig_align`, `cell_entry`, 5P override, branch order, reason string,
  threshold, backend selection, behavior tree, VLM/LLM packet, token schema,
  debug schema, rollout summary schema, policy reset timing, or low-level ACT
  dispatch behavior was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `b9b414ec31a6ad9860abe886108148a41bb06765`, no fetch, pull, or push. The
  worktree was clean before edits.
- Selected evidence remains the successful mainline packet:
  `runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/rollouts/rollout_000.jsonl`,
  its paired planner trace, rollout summary, resolved config, and
  `docs/planner_evidence_reports/2026-06-18-baseline-aggregate_tx24.md`.
- Added `SwitchSkillEffect(target_skill_name, switch_reason)` in
  `testbed/planner/primitive_decision.py`. Validation requires non-empty target
  skill and switch reason, requires generic `switch_skill` requested effects to
  use the concrete semantic class, and preserves the existing forbidden
  callable/self/planner attr/method-call checks.
- Updated `PrimitivePlannerACTPolicy._apply_requested_tick_effects()` so an
  empty tuple remains a no-op, `SwitchSkillEffect` calls existing
  `_set_skill(skill, reason)`, and any other requested effect still raises
  `PrimitiveDecisionContractError`.
- Added focused tests in `tests/test_primitive_decision_contract.py` for
  `SwitchSkillEffect` construction/validation, invalid skill/reason rejection,
  real shell `_set_skill()` call argument order, and unknown requested-effect
  fail-fast behavior. Existing execution-template tests continue to cover fake
  requested-effect ordering and default legacy already-applied skip behavior.
- TDD red result: the first focused run failed with missing `SwitchSkillEffect`.
  After implementation and test updates, the focused green run returned
  `14 passed`.
- Old code parked/reclassified: no code was deleted. No legacy FSM branch was
  converted to emit `SwitchSkillEffect`; legacy already-applied branch behavior
  remains the default planner path.
- Next action: any branch conversion to `SwitchSkillEffect` must be a separate
  evidence-backed scope with branch-specific parity tests and no changes to
  branch order, reason strings, policy reset timing, or debug/token schemas.

### 2026-06-22 Phase 9.1 Bootstrap Branch Requested SwitchSkill Conversion

- Scope: converted only the 4P mainline bootstrap branch from direct callback
  mutation to the requested `SwitchSkillEffect` decision path. No dig, carry,
  dump, return, direct-handoff, coverage, token planning, `pre_dig_align`
  internals, `cell_entry`, 5P override, branch order, reason string, threshold,
  backend selection, behavior tree, VLM/LLM packet, token schema, debug schema,
  rollout summary schema, policy reset timing, or low-level ACT dispatch
  behavior was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `09ceea6019356a680f200c77fb486c582c9c9cfd`, no fetch, pull, or push. The
  worktree was clean before edits.
- Selected evidence remains the successful mainline packet:
  `runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/rollouts/rollout_000.jsonl`,
  its paired planner trace, rollout summary, resolved config, and
  `docs/planner_evidence_reports/2026-06-18-baseline-aggregate_tx24.md`.
- Confirmed-live method chain converted:
  `run_primitive_tick()` calls the decision bridge, the bootstrap branch returns
  `PrimitiveDecisionResult(side_effects_applied=False)` with ordered
  `SwitchSkillEffect`, the execution hook applies requested effects before
  return-timeout accounting and action dispatch, and the real shell applier
  calls existing `_set_skill(next_skill, bootstrap_to_*)`.
- Updated `LegacyFSMBootstrapBranch` with `decide_tick(...)` as the requested
  decision API. `maybe_handle()` remains a compatibility facade and reuses the
  same decision logic before applying `SwitchSkillEffect` through its existing
  `set_skill` callback.
- Updated `PrimitivePlannerACTPolicy._decide_tick_with_legacy_fsm()` so
  bootstrap ticks use the requested-effect path first. Non-bootstrap ticks
  continue through the existing legacy already-applied adapter.
- Added focused tests in `tests/test_primitive_backend.py`,
  `tests/test_primitive_decision_contract.py`, and
  `tests/test_primitive_execution_template.py` for bootstrap requested
  `SwitchSkillEffect`, non-bootstrap not-handled behavior, requested-effect
  ordering before dispatch, policy bridge no-callback decision behavior, and
  legacy already-applied behavior for other branches.
- TDD red result: the first focused run failed because
  `LegacyFSMBootstrapBranch.decide_tick()` did not exist and the policy bridge
  still directly called `_set_skill()` through bootstrap callback mutation.
  After implementation the focused green run returned `33 passed`.
- Old code parked/reclassified: no code was deleted. The bootstrap
  compatibility facade remains for legacy callers; dig/carry/dump/return
  branch bodies remain existing legacy already-applied paths.
- Next action: do not convert another branch until a separate evidence-backed
  scope locks the target branch's reason strings, ordering, policy reset timing,
  debug/token surfaces, and requested-effect family coverage.

### 2026-06-22 Phase 9.2 Return Branch Requested Effect Conversion

- Scope: converted only the 4P mainline `return` branch from direct callback
  mutation to ordered requested return-cycle effects. No dig, carry, dump,
  direct-handoff helper internals, coverage, token planning, `pre_dig_align`
  branch internals, `cell_entry`, 5P override, branch order, reason string,
  threshold, backend selection, behavior tree, VLM/LLM packet, token schema,
  debug schema, rollout summary schema, policy reset timing, or low-level ACT
  dispatch behavior was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `7473ac3c5b72c6e6d48c514da647c9b98e4f3637`, no fetch, pull, or push. The
  worktree was clean before edits.
- Selected evidence remains the successful mainline packet:
  `runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/rollouts/rollout_000.jsonl`,
  its paired planner trace, rollout summary, resolved config, and
  `docs/planner_evidence_reports/2026-06-18-baseline-aggregate_tx24.md`. The
  selected evidence marks `gate.return_to_dig` as confirmed-live and includes
  return-to-dig reason surfaces such as `return_to_dig_next_dig_entry_ready`,
  start-envelope handoff readiness, and shallow-guard coverage in tests.
- Confirmed-live method chain converted:
  `run_primitive_tick()` calls the decision bridge, the return branch returns
  `PrimitiveDecisionResult(side_effects_applied=False)` with ordered
  return-cycle requested effects, the execution hook applies those effects
  before return-timeout accounting and action dispatch, and the real shell
  applier calls existing return shell operations in order.
- Added concrete return-cycle effect contracts in
  `testbed/planner/primitive_decision.py`:
  `MarkReturnNextDigEventSeenEffect`,
  `CompleteReturnTransitionEffect`, and
  `SwitchToNextSkillAfterReturnEffect(reason_suffix)`. Validation rejects empty
  return switch reason suffixes and preserves the forbidden callable/self/
  arbitrary planner attr or method-call payload checks.
- Updated `LegacyFSMReturnBranch` with `decide_tick(...)` as the requested
  decision API. The branch returns `None` for non-return skill, an empty
  no-change requested result for unready return ticks, only the mark effect for
  next-dig events without completion, and ordered mark/complete/switch effects
  when event latch and completion happen in the same tick. `maybe_handle()`
  remains a compatibility facade and reuses the same requested decision logic
  before applying effects through its existing callbacks.
- Updated `PrimitivePlannerACTPolicy._decide_tick_with_legacy_fsm()` so the
  default bridge tries bootstrap requested effects first, then return requested
  effects, then falls back to the existing legacy already-applied adapter for
  dig, carry, dump, and legacy parking paths.
- Updated `PrimitivePlannerACTPolicy._apply_requested_tick_effects()` so
  return-cycle effects map to existing shell operations:
  `_mark_return_next_dig_event_seen()`,
  `_complete_return_transition_for_backend()`, and then
  `_next_skill_after_return_transition()` plus `_set_skill(...)`. The next
  skill is computed during effect application after completion, preserving the
  previous cycle-index/pre-dig-gate ordering.
- Added focused tests in `tests/test_primitive_backend.py`,
  `tests/test_primitive_decision_contract.py`, and
  `tests/test_primitive_execution_template.py` for return requested effects,
  non-return not-handled behavior, mark/complete/switch ordering, complete-before
  next-skill shell ordering, policy bridge no-callback decision behavior, and
  execution-hook application before dispatch.
- TDD red result: the first focused run failed at test collection because the
  return-cycle effect classes did not exist. After implementation and test
  updates, the focused green run returned `43 passed`.
- Old code parked/reclassified: no code was deleted. Direct-handoff helper
  internals, dig/carry/dump branch bodies, `pre_dig_align` internals, and 5P
  compatibility remain existing legacy or compatibility owners.
- Next action: continue converting confirmed-live branch side effects only when
  their semantic effect family and ordering can be expressed directly. Do not
  promote `pre_dig_align`, `cell_entry`, or direct-handoff internals into the
  mainline requested-effect architecture without a separate evidence-backed
  scope and compatibility decision.

### 2026-06-22 Phase 9.3 Observation-Aware Effect Applier And Carry/Dump Requested Effects Conversion

- Scope: made requested-effect application observation-aware and converted only
  the 4P mainline `carry` and `dump` branches from direct callback mutation to
  ordered requested effects. No dig branch, return direct-handoff helper
  internals, `pre_dig_align` branch internals, `cell_entry`, 5P override,
  branch order, reason string, threshold, backend selection, behavior tree,
  VLM/LLM packet, token schema, debug schema, rollout summary schema, policy
  reset timing, or low-level ACT dispatch behavior was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `5c4674862e6f8be5fb65c7540f1c558d2c7c6ee3`, no fetch, pull, or push. The
  worktree was clean before edits.
- Selected evidence remains the successful mainline packet:
  `runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/rollouts/rollout_000.jsonl`,
  its paired planner trace, rollout summary, resolved config, and
  `docs/planner_evidence_reports/2026-06-18-baseline-aggregate_tx24.md`. The
  selected evidence marks `gate.carry_to_dump` and `gate.dump_to_return` as
  confirmed-live and locks carry/dump switch reasons through the current-code
  parity harness.
- Confirmed-live method chain converted:
  `run_primitive_tick()` calls the decision bridge, the carry/dump branch
  returns `PrimitiveDecisionResult(side_effects_applied=False)` with ordered
  requested effects, the execution hook passes both `obs` and effects to the
  shell applier before return-timeout accounting and action dispatch, and the
  real shell applier calls existing carry/dump shell operations in order.
- Updated `testbed/planner/primitive_execution.py` so
  `apply_requested_effects` receives the current `obs` plus ordered effects.
  Legacy already-applied decisions still skip requested-effect application.
- Added concrete carry/dump effect contracts in
  `testbed/planner/primitive_decision.py`:
  `SetDumpReadyHoldCountEffect`,
  `SetDumpStartDepositedMassFromObservationEffect`,
  `SetDumpDoneHoldCountEffect`, `CompleteCoverageDumpEffect`, and
  `SetReturnOrDirectHandoffEffect`. Validation rejects negative hold counts,
  empty coverage/return reasons, and preserves the forbidden callable/self/
  arbitrary planner attr or method-call payload checks.
- Updated `LegacyFSMCarryBranch` with `decide_tick(...)` as the requested
  decision API. The branch now emits ordered effects for carry release-safety,
  carry dump-complete boundary, hold-count update, dump-start deposited-mass
  capture from current observation, and carry-to-dump `SwitchSkillEffect`.
  `maybe_handle()` remains a compatibility facade and reuses the same requested
  decision logic before applying effects through its existing callbacks.
- Updated `LegacyFSMDumpBranch` with `decide_tick(...)` as the requested
  decision API. The branch now emits ordered effects for dump boundary-done,
  dump done hold-count update, coverage dump completion, and return/direct
  handoff. `maybe_handle()` remains a compatibility facade and reuses the same
  requested decision logic before applying effects through its existing
  callbacks.
- Updated `PrimitivePlannerACTPolicy._decide_tick_with_legacy_fsm()` so the
  default bridge tries bootstrap requested effects first, then carry, dump,
  return requested effects, then falls back to the existing legacy
  already-applied adapter for dig and legacy parking paths.
- Updated `PrimitivePlannerACTPolicy._apply_requested_tick_effects(obs, ...)`
  so carry/dump effects map to existing shell helpers:
  `_set_dump_ready_hold_count`, `_set_dump_start_deposited_mass` with
  `_deposited_mass(obs)`, `_set_dump_done_hold_count`,
  `_complete_coverage_dump(obs, reason=...)`,
  `_set_return_or_direct_handoff(obs, reason=...)`, and existing `_set_skill`.
- Added focused tests in `tests/test_primitive_backend.py`,
  `tests/test_primitive_decision_contract.py`, and
  `tests/test_primitive_execution_template.py` for obs-aware requested-effect
  ordering, carry release-safety, carry dump-complete boundary, carry
  ready-to-dump ordering, dump boundary-done, dump ready-to-return ordering,
  real shell obs-aware applier calls, and carry/dump policy bridge
  no-callback decision behavior.
- TDD red result: the first focused run failed at test collection because the
  carry/dump effect classes did not exist. After implementation and test
  updates, the focused green run returned `53 passed`.
- Old code parked/reclassified: no code was deleted. Dig branch bodies, return
  direct-handoff helper internals, `pre_dig_align` internals, `cell_entry`, and
  5P compatibility remain existing legacy or compatibility owners.
- Next action: the remaining confirmed-live branch with direct callback
  mutation is `dig`, but it mixes coverage dig completion, cell-entry
  compatibility, failed-dig restart/replan, and skill switch effects. Convert it
  only with a separate evidence-backed scope and explicit semantic effect
  family coverage.

### 2026-06-22 Phase 9.4 Dig Branch Requested Effects Conversion

- Scope: converted the confirmed-live 4P mainline `dig` branch from direct
  callback mutation to ordered requested effects. No token planning, coverage
  metric calculation internals, return direct-handoff internals,
  `pre_dig_align`, `cell_entry` architecture promotion, 5P override, branch
  order, reason string, threshold, backend selection, behavior tree, VLM/LLM
  packet, token schema, debug schema, rollout summary schema, policy reset
  timing, or low-level ACT dispatch behavior was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `9d8154f65ecb28eb70540b07dc7615c3668af0d0`, no fetch, pull, or push. The
  worktree was clean before edits.
- Selected evidence remains the successful mainline packet:
  `runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/rollouts/rollout_000.jsonl`,
  its paired planner trace, rollout summary, resolved config, and
  `docs/planner_evidence_reports/2026-06-18-baseline-aggregate_tx24.md`. The
  selected evidence marks `gate.dig_to_carry` as confirmed-live and current
  focused tests cover bad-dig, exit-guard, complete-low-payload, and first-dig
  policy risk windows.
- Confirmed-live method chain converted:
  `run_primitive_tick()` calls the decision bridge, the dig branch returns
  `PrimitiveDecisionResult(side_effects_applied=False)` with ordered dig
  requested effects, the execution hook passes current `obs` plus effects to
  the shell applier before return-timeout accounting and action dispatch, and
  the real shell applier calls existing dig shell operations in order.
- Added concrete dig effect contracts in
  `testbed/planner/primitive_decision.py`:
  `IncrementDigExitGuardReplanCountEffect`,
  `IncrementDigBadReplanCountEffect`,
  `RejectActiveCoverageCorridorEffect(reason)`,
  `RestartAfterFailedDigEffect(reason)`,
  `CompleteCellEntryDigCompatibilityEffect`, and
  `CompleteCoverageDigEffect`. Validation rejects empty reject/restart reasons
  and preserves forbidden callable/self/arbitrary planner attr or method-call
  payload checks.
- Updated `LegacyFSMDigBranch` with `decide_tick(...)` as the requested
  decision API. The branch now emits ordered effects for dig exit-guard
  low-payload replans, bad-dig low-payload replans, dig-complete low-current
  payload replans, dig-to-carry coverage completion, and dig-to-carry
  `SwitchSkillEffect`. `maybe_handle()` remains a compatibility facade and
  reuses the same requested decision logic before applying effects through its
  existing callbacks.
- Updated `PrimitivePlannerACTPolicy._decide_tick_with_legacy_fsm()` so the
  default bridge tries bootstrap, dig, carry, dump, then return requested
  effects before falling back to the residual legacy already-applied adapter.
- Updated `PrimitivePlannerACTPolicy._apply_requested_tick_effects(obs, ...)`
  so dig effects map to existing shell helpers:
  `_increment_dig_exit_guard_replan_count`,
  `_increment_dig_bad_replan_count`,
  `_reject_active_coverage_corridor(obs, reason=...)`,
  `_restart_after_failed_dig(reason, obs)`,
  `_complete_cell_entry_dig(obs)`,
  `_complete_coverage_dig(obs)`, and existing `_set_skill`.
- `CompleteCellEntryDigCompatibilityEffect` is compatibility-only. It preserves
  the old dig-to-carry callback order when cell-entry is enabled but does not
  make `cell_entry` a target backend capability or mainline architecture
  concern.
- Added focused tests in `tests/test_primitive_backend.py`,
  `tests/test_primitive_decision_contract.py`, and
  `tests/test_primitive_execution_template.py` for dig requested effects,
  non-dig not-handled behavior, no-change dig ticks, compatibility facade
  reuse, real shell applier ordering, and policy bridge no-callback decision
  behavior.
- TDD red result: the first focused run failed at test collection because the
  dig effect classes did not exist. After implementation and compatibility test
  updates, the focused green run returned `64 passed`.
- Old code parked/reclassified: no code was deleted. The dig compatibility
  facade remains for legacy callers; `pre_dig_align`, `cell_entry` internals,
  5P compatibility, token planning, and return direct-handoff internals remain
  existing legacy or compatibility owners.
- Next action: after bootstrap/dig/carry/dump/return mainline branch conversion,
  review the residual already-applied adapter and `_maybe_switch_skill()`
  ownership. The next phase should either park residual compatibility paths
  (`pre_dig_align`, 5P/legacy-only branches) behind explicit labels or extract a
  real backend runner over the requested-effect branch list, rather than adding
  more callback wrappers.

### 2026-06-22 Phase 9.5 Retire Mainline Legacy FSM Fallback

- Scope: removed the broad already-mutating
  `LegacyFSMBackendAdapter -> _maybe_switch_skill()` fallback from the default
  4P decision bridge. Bootstrap, dig, carry, dump, and return remain the
  requested-effect mainline branch chain. `pre_dig_align` remains
  residual/parking and already-applied; it was not promoted into a mainline
  backend capability. No token planning, coverage metric internals,
  return direct-handoff internals, `cell_entry`, 5P override, branch order,
  reason string, threshold, backend selection, behavior tree, VLM/LLM packet,
  token schema, debug schema, rollout summary schema, policy reset timing, or
  low-level ACT dispatch behavior was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `9ef546b720fa5b39feee794164fac9f62ea90a34`, no fetch, pull, or push. The
  worktree was clean before edits.
- Selected evidence remains the successful mainline packet:
  `runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/rollouts/rollout_000.jsonl`,
  its paired planner trace, rollout summary, resolved config, and
  `docs/planner_evidence_reports/2026-06-18-baseline-aggregate_tx24.md`. The
  evidence classifies `gate.pre_dig_align` as dead-candidate / legacy parking
  for this mainline slice while bootstrap/dig/carry/dump/return are
  confirmed-live or compatibility surfaces.
- Default decision chain is now:
  bootstrap requested -> dig requested -> carry requested -> dump requested ->
  return requested -> explicit residual pre-dig-align adapter. Unknown or
  unclassified skills fail fast with `PrimitiveDecisionContractError` rather
  than silently re-entering broad `_maybe_switch_skill()` callback mutation.
- Added `LegacyFSMResidualPreDigAlignAdapter` in
  `testbed/planner/primitive_backend.py` with decision source
  `legacy_fsm_residual_pre_dig_align_already_applied`. It is an explicit
  already-applied compatibility boundary for parked `pre_dig_align` behavior,
  not a generic fallback for mainline branches.
- Updated `PrimitivePlannerACTPolicy._decide_tick_with_legacy_fsm()` to remove
  `_legacy_fsm_backend().decide_tick(...)` from the default path and to call the
  residual pre-dig-align adapter only after all requested mainline branches
  decline the tick.
- Extracted the old inline pre-dig-align branch body into
  `_maybe_handle_pre_dig_align_skill(obs)`. `_maybe_switch_skill()` remains a
  legacy compatibility facade for direct tests/diagnostics, but it is no longer
  the default mainline decision source of truth.
- `LegacyFSMBackendAdapter` remains in `primitive_backend.py` only as a
  compatibility/test scaffold for the historical broad callback shape. The
  default planner bridge no longer imports or constructs it.
- Added focused tests in `tests/test_primitive_backend.py` and
  `tests/test_primitive_decision_contract.py` for the residual pre-dig-align
  adapter, mainline branch miss fail-fast behavior, branch order
  bootstrap/dig/carry/dump/return before residual handling, explicit residual
  pre-dig-align handling, and unknown-skill rejection without calling broad
  `_maybe_switch_skill()`.
- TDD red result: the first focused run failed at test collection because the
  residual adapter and source constant did not exist. After implementation, the
  old broad fallback policy test failed and was reclassified to assert
  fail-fast unknown-skill behavior. The focused green run returned `68 passed`.
- Old code parked/reclassified: no code was deleted. `pre_dig_align` remains a
  residual already-applied compatibility path; `cell_entry` internals, 5P
  compatibility, token planning, and return direct-handoff internals remain
  existing legacy or compatibility owners.
- Next action: now that the mainline branch chain has no broad callback
  fallback, the next structural phase should extract an explicit requested
  branch runner or decision backend object that owns branch ordering outside the
  large policy shell, while keeping the shell as effect applier and public
  adapter.

### 2026-06-22 Phase 9.6 Extract Requested Branch Runner

- Scope: extracted default requested branch ordering from the large
  `PrimitivePlannerACTPolicy` shell into a focused runner in
  `testbed/planner/primitive_backend.py`. No requested effect family,
  branch semantics, branch order, reason string, threshold, token/debug/summary
  schema, policy reset timing, backend selection, behavior tree, VLM/LLM
  packet, `pre_dig_align` architecture status, `cell_entry`, 5P override, or
  low-level ACT dispatch behavior was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `9629713b1969f12d6a4f88e3a9cee8ce0420fc07`, no fetch, pull, or push. The
  worktree was clean before edits.
- Selected evidence remains the successful mainline packet:
  `runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/rollouts/rollout_000.jsonl`,
  its paired planner trace, rollout summary, resolved config, and
  `docs/planner_evidence_reports/2026-06-18-baseline-aggregate_tx24.md`. The
  evidence supports migrating the confirmed-live 4P mainline branch ordering
  while keeping `pre_dig_align` parked as residual compatibility.
- Added `PrimitiveDecisionBranch` protocol and
  `PrimitiveRequestedBranchRunner`. The runner owns ordered dispatch:
  bootstrap -> dig -> carry -> dump -> return -> residual pre-dig-align. It
  returns the first non-`None` result, stops calling later branches, and raises
  `PrimitiveDecisionContractError` when no branch handles the current skill.
  The fail-fast message keeps the Phase 9.5 invariant that broad legacy
  fallback is retired for default decisions.
- Updated `PrimitivePlannerACTPolicy._decide_tick_with_legacy_fsm()` into a
  thin legacy-named bridge that delegates to `_requested_branch_runner()`. The
  policy shell now owns branch wiring and requested-effect application, not
  ordered branch dispatch.
- `LegacyFSMBackendAdapter` remains only as compatibility/test scaffolding for
  the historical broad callback shape. The default planner path does not import,
  construct, or call it, and does not call broad `_maybe_switch_skill()`.
- Added focused tests in `tests/test_primitive_backend.py` and
  `tests/test_primitive_decision_contract.py` for runner first-match behavior,
  stable branch order, fail-fast all-miss behavior, and policy bridge
  delegation to the runner.
- TDD red result: the first focused run failed at test collection because
  `PrimitiveRequestedBranchRunner` did not exist. After implementation, the
  focused green run returned `66 passed`.
- Old code parked/reclassified: no code was deleted. `pre_dig_align` remains a
  residual already-applied compatibility path; `_maybe_switch_skill()` remains
  a legacy compatibility facade for direct tests/diagnostics; `cell_entry`
  internals, 5P compatibility, token planning, and return direct-handoff
  internals remain existing legacy or compatibility owners.
- Next action: continue moving toward the SVG target by extracting the next
  stable boundary that still keeps confirmed-live behavior in the policy shell,
  likely a capability/status provider or branch factory bundle that supplies
  explicit facts to the requested branch runner without passing planner `self`.

### 2026-06-22 Phase 9.7 Extract Legacy FSM Branch Ports And Branch Set

- Scope: extracted legacy-FSM branch wiring and branch-set construction from
  the large `PrimitivePlannerACTPolicy` shell into
  `testbed/planner/primitive_backend.py`. No requested effect family, branch
  semantics, branch order, reason string, threshold, token/debug/summary
  schema, policy reset timing, backend selection, behavior tree, VLM/LLM
  packet, `pre_dig_align` architecture status, `cell_entry`, 5P override, or
  low-level ACT dispatch behavior was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `99d80d8b87be444bc1944b73180d049a502b7e3d`, no fetch, pull, or push. The
  worktree was clean before edits.
- Selected evidence remains the successful mainline packet:
  `runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/rollouts/rollout_000.jsonl`,
  its paired planner trace, rollout summary, resolved config, and
  `docs/planner_evidence_reports/2026-06-18-baseline-aggregate_tx24.md`. The
  evidence supports moving confirmed-live FSM wiring out of the shell while
  keeping `pre_dig_align` and `cell_entry` out of target mainline capability.
- Added `LegacyFSMBranchPorts` as the typed shell boundary for branch wiring.
  It carries explicit callbacks/config values, not `PrimitivePlannerACTPolicy`
  or planner `self`.
- Added `LegacyFSMBranchSet` to construct/own bootstrap, dig, carry, dump,
  return, and residual pre-dig-align branches from ports. The branch set owns
  the requested dispatch order
  bootstrap -> dig -> carry -> dump -> return -> residual and the compatibility
  facade order bootstrap -> residual pre-dig-align -> dig -> carry -> dump ->
  return.
- Added `LegacyFSMRequestedDecisionBackend` as the default requested-effect
  decision backend built from the branch set. It delegates to the requested
  runner and preserves the Phase 9.6 fail-fast contract.
- Updated `PrimitivePlannerACTPolicy` so it no longer imports or constructs
  individual `LegacyFSM*Branch` / `LegacyFSM*Config` classes. It now exposes
  `_legacy_fsm_branch_ports()`, builds a branch set from those ports, and
  delegates `_decide_tick_with_legacy_fsm()` to
  `LegacyFSMRequestedDecisionBackend`.
- Updated `_maybe_switch_skill()` so the legacy compatibility facade delegates
  to `LegacyFSMBranchSet.maybe_handle_legacy_fsm(...)` instead of hand-writing
  branch order in the policy shell.
- Added focused tests in `tests/test_primitive_backend.py` and
  `tests/test_primitive_decision_contract.py` for branch ports, branch-set
  construction, requested backend order, fail-fast all-miss behavior,
  compatibility order, policy backend delegation, and policy compatibility
  facade delegation.
- TDD red result: the first focused run failed at test collection because
  `LegacyFSMBranchPorts` did not exist. After implementation, the focused green
  run returned `71 passed`.
- Old code parked/reclassified: no code was deleted. `pre_dig_align` remains a
  residual already-applied compatibility path; `_maybe_switch_skill()` remains
  a legacy compatibility facade for direct tests/diagnostics; `cell_entry`
  internals, 5P compatibility, token planning, and return direct-handoff
  internals remain existing legacy or compatibility owners.
- Next action: continue moving toward the SVG target by extracting the next
  capability/status boundary currently supplied through shell callbacks, so
  branch decisions can consume explicit facts instead of callback-heavy shell
  ports while still preserving rollout parity.

### 2026-06-22 Phase 9.8 Convert Dig Branch Gates To Explicit Transition Status

- Scope: converted the confirmed-live 4P mainline dig branch input contract
  from five shell gate callbacks to one explicit `DigTransitionStatus` provider.
  No requested effect family, effect ordering, branch priority, reason string,
  threshold, token/debug/summary schema, policy reset timing, backend selection,
  behavior tree, VLM/LLM packet, `pre_dig_align`, `cell_entry`, 5P override, or
  low-level ACT dispatch behavior was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `50bffdb16187ee430e74347c83ef43c69ea2ac80`, no fetch, pull, or push. The
  worktree was clean before edits.
- Selected evidence remains the successful mainline packet:
  `runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/rollouts/rollout_000.jsonl`,
  its paired planner trace, rollout summary, resolved config, and
  `docs/planner_evidence_reports/2026-06-18-baseline-aggregate_tx24.md`. The
  evidence keeps `gate.dig_to_carry` confirmed-live and `gate.pre_dig_align`
  parked as residual compatibility.
- Updated `LegacyFSMBranchPorts` so dig facts are exposed through
  `dig_transition_status(obs, boundary_event) -> DigTransitionStatus`. The
  ports object no longer exposes `dig_exit_guard_ready`,
  `dig_bad_replan_ready`, `dig_complete_boundary_low_payload`,
  `dig_to_carry_ready`, or `dig_to_carry_reason` as branch input callbacks.
- Updated `LegacyFSMDigBranch` so `decide_tick(...)` calls the status provider
  only after confirming the active skill is `dig`, then builds ordered requested
  effects from the status in the preserved priority order: exit guard, bad dig
  replan, dig-complete low payload, dig-to-carry, no-change. `maybe_handle()`
  continues to reuse the requested decision path for compatibility.
- Added `PrimitivePlannerACTPolicy._dig_transition_status_for_backend(...)`.
  It maps `PrimitiveObservationFacts.from_obs(...)`, semantic boundary active
  state, coverage terminal-stop state, dig step count, dig mass plateau count,
  dig-to-carry distance/payload/plateau config, dump-ready minimum payload,
  bad-dig replan config, exit-guard config, and current dig exit overshoot into
  `DigTransitionStatus.from_inputs(...)`. It also keeps `_dig_to_carry_reason`
  as a shell/debug compatibility mirror of the status reason.
- Added focused tests in `tests/test_primitive_backend.py` and
  `tests/test_primitive_decision_contract.py` for status-driven dig effects,
  status priority, non-dig not-handled behavior without status lookup, ports
  field removal, policy bridge wiring, and policy status-provider mapping.
- TDD red result: the first focused run failed because
  `LegacyFSMBranchPorts.__init__()` did not yet accept `dig_transition_status`,
  proving the new tests were exercising the intended contract boundary. After
  implementation, the focused backend/decision run returned `73 passed`, and
  the required backend/decision/execution run returned `79 passed`.
- Verification:
  `python -m pytest -q tests/test_primitive_backend.py tests/test_primitive_decision_contract.py tests/test_primitive_execution_template.py`
  returned `79 passed`;
  `python -m pytest -q tests/test_planner_current_code_parity.py` returned
  `3 passed`;
  `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "dig_to_carry or bad_dig_replans or dig_exit_guard or complete_low_payload or semantic_boundary_events_drive_skill_sequence"`
  returned `8 passed, 112 deselected`;
  `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
  returned `5 passed`;
  `python -m pytest -q tests/test_primitive_capabilities.py` returned
  `25 passed`;
  compileall and both planner guard commands completed successfully with no
  output.
- Old code parked/reclassified: no code was deleted. Old private dig helper
  methods remain compatibility/diagnostic helpers; `pre_dig_align` remains a
  residual already-applied compatibility path; `_maybe_switch_skill()` remains
  a legacy compatibility facade for direct tests/diagnostics; `cell_entry`
  internals, 5P compatibility, token planning, coverage metric internals, and
  return direct-handoff internals remain existing legacy or compatibility
  owners.
- Next action: continue moving toward the SVG target by extracting the next
  callback-heavy status/fact boundary or shell-owned capability from
  `LegacyFSMBranchPorts`, while keeping mutation in requested effects and the
  shell applier until a focused service owns it.

### 2026-06-22 Phase 9.9 Extract Requested Effect Applier From Policy Shell

- Scope: extracted requested-effect application from the large
  `PrimitivePlannerACTPolicy` shell into a focused planner module. No requested
  effect class, decision branch, effect application order, branch priority,
  reason string, threshold, token/debug/summary schema, policy reset timing,
  backend selection, behavior tree, VLM/LLM packet, `pre_dig_align`,
  `cell_entry`, 5P override, or low-level ACT dispatch behavior was
  intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `3d4a06bd671d2eb0eb02bd7c122519aa1403263d`, no fetch, pull, or push. The
  worktree was clean before edits.
- Selected evidence remains the successful mainline packet:
  `runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/rollouts/rollout_000.jsonl`,
  its paired planner trace, rollout summary, resolved config, and
  `docs/planner_evidence_reports/2026-06-18-baseline-aggregate_tx24.md`. The
  evidence keeps mainline branch decisions and requested-effect application as
  confirmed-live execution behavior while `gate.pre_dig_align` and
  `token.cell_entry` remain parked or compatibility-only.
- Added `testbed/planner/primitive_effects.py` with
  `RequestedEffectApplierPorts` and `RequestedEffectApplier`. The ports object
  exposes explicit shell-owned mutation callbacks, not
  `PrimitivePlannerACTPolicy` or planner `self`.
- `RequestedEffectApplier` now owns the requested-effect type dispatch,
  non-empty skill/reason validation previously in the policy shell, ordered
  iteration over the incoming effects tuple, current-observation deposited-mass
  lookup for dump-start mass capture, return post-completion next-skill lookup,
  and fail-fast behavior for unsupported requested effect types.
- Supported effect families are unchanged:
  `SwitchSkillEffect`, `MarkReturnNextDigEventSeenEffect`,
  `CompleteReturnTransitionEffect`, `SwitchToNextSkillAfterReturnEffect`,
  `IncrementDigExitGuardReplanCountEffect`,
  `IncrementDigBadReplanCountEffect`, `RejectActiveCoverageCorridorEffect`,
  `RestartAfterFailedDigEffect`, `CompleteCellEntryDigCompatibilityEffect`,
  `CompleteCoverageDigEffect`, `SetDumpReadyHoldCountEffect`,
  `SetDumpStartDepositedMassFromObservationEffect`,
  `SetDumpDoneHoldCountEffect`, `CompleteCoverageDumpEffect`, and
  `SetReturnOrDirectHandoffEffect`.
- Updated `PrimitivePlannerACTPolicy` so `_apply_requested_tick_effects(...)`
  is a thin execution-hook bridge. It now delegates non-empty effects to
  `_requested_effect_applier().apply(obs, effects)` and builds the applier from
  `_requested_effect_applier_ports()`. The policy shell no longer imports the
  concrete requested-effect classes or owns the `isinstance(effect, ...)`
  dispatch cascade.
- `CompleteCellEntryDigCompatibilityEffect` remains compatibility-only and is
  applied through the shell callback exposed in the applier ports. This phase
  does not promote `cell_entry` into target mainline backend capability.
- Added focused tests in `tests/test_primitive_effects.py` for ordered mixed
  effect application, empty-field validation, unsupported effect fail-fast, and
  current-observation deposited-mass lookup. Updated
  `tests/test_primitive_decision_contract.py` with a policy-level delegation
  test so the policy bridge no longer proves effect-family dispatch itself.
- TDD red result: the first focused run failed at test collection because
  `testbed.planner.primitive_effects` did not exist. After implementation, the
  focused applier tests returned `10 passed`, and the applier plus decision
  contract run returned `40 passed`.
- Verification:
  `python -m pytest -q tests/test_primitive_effects.py tests/test_primitive_decision_contract.py tests/test_primitive_execution_template.py tests/test_primitive_backend.py`
  returned `90 passed`;
  `python -m pytest -q tests/test_planner_current_code_parity.py` returned
  `3 passed`;
  `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "dig_to_carry or bad_dig_replans or dig_exit_guard or complete_low_payload or carry_to_dump or dump_to_return or return_to_dig or semantic_boundary_events_drive_skill_sequence"`
  returned `11 passed, 109 deselected`;
  `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
  returned `5 passed`;
  `python -m pytest -q tests/test_primitive_capabilities.py` returned
  `25 passed`;
  compileall, both planner guard commands, and `git diff --check` completed
  successfully with no output.
- Old code parked/reclassified: no code was deleted. Backend branch
  compatibility `maybe_handle()` helpers keep their local effect application
  paths for legacy callers; `pre_dig_align` remains a residual already-applied
  compatibility path; `_maybe_switch_skill()` remains a legacy compatibility
  facade for direct tests/diagnostics; `cell_entry` internals, 5P
  compatibility, token planning, coverage metric internals, and return
  direct-handoff internals remain existing legacy or compatibility owners.
- Next action: continue toward the SVG target by extracting the next largest
  stable shell boundary, likely a capability/status provider bundle or a
  focused coverage/token/handoff owner, instead of returning to guard-only or
  cosmetic cleanup rounds.

### 2026-06-22 Phase 9.10 Route Legacy Compatibility Through Requested Effects

- Scope: routed the legacy compatibility `_maybe_switch_skill()` entry through
  the requested decision result and centralized requested-effect applier chain.
  No branch order, reason string, threshold, token/debug/summary schema, policy
  reset timing, backend selection, behavior tree, VLM/LLM packet,
  `pre_dig_align` mainline status, `cell_entry` status, 5P override, or
  low-level ACT dispatch behavior was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `08f57a0f0cb680d7425580f015241cc565bcf5d1`, no fetch, pull, push, reset,
  checkout, or rebase. The worktree was clean before edits.
- Selected evidence remains the successful mainline packet:
  `runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/rollouts/rollout_000.jsonl`,
  its paired planner trace, rollout summary, resolved config, and
  `docs/planner_evidence_reports/2026-06-18-baseline-aggregate_tx24.md`. The
  evidence keeps mainline branch decisions confirmed-live while `gate.pre_dig_align`
  remains residual legacy parking and `token.cell_entry` remains compatibility-only.
- Added `LegacyFSMCompatibilityDecisionBackend`. It owns the legacy
  compatibility order bootstrap -> residual pre-dig-align -> dig -> carry ->
  dump -> return, returns `PrimitiveDecisionResult | None`, and never applies
  requested effects locally. All-miss compatibility decisions return `None`
  instead of using the default fail-fast requested runner contract.
- Updated `PrimitivePlannerACTPolicy._maybe_switch_skill()` so it builds a
  compatibility `PrimitiveTickPreparation`, calls
  `_legacy_fsm_compatibility_decision_backend().decide_tick(...)`, no-ops on
  `None`, skips reapplication for already-applied residual results, and sends
  mainline requested effects to `_apply_requested_tick_effects(obs, effects)`.
  That bridge reaches the same `RequestedEffectApplier` used by the default
  execution hook.
- Retired branch-local mainline mutation application. `LegacyFSMBootstrapBranch`,
  `LegacyFSMDigBranch`, `LegacyFSMCarryBranch`, `LegacyFSMDumpBranch`, and
  `LegacyFSMReturnBranch` no longer expose `maybe_handle()` or `_apply_effects()`;
  they only produce requested decision results. The residual
  `LegacyFSMResidualPreDigAlignAdapter` still exposes `maybe_handle()` as an
  explicit already-applied parking path.
- Narrowed `LegacyFSMBranchPorts` by removing mainline mutation fields:
  `set_skill`, dig replan/reject/restart/completion callbacks,
  coverage-dump/return-handoff callbacks, dump hold/deposited-mass setters,
  deposited-mass reader, and return transition/switch callbacks. Those mutation
  ports remain owned by `RequestedEffectApplierPorts`.
- Added or migrated focused tests in `tests/test_primitive_backend.py` and
  `tests/test_primitive_decision_contract.py` for compatibility decision order,
  all-miss `None`, ports field removal, absence of mainline branch-local
  application methods, and `_maybe_switch_skill()` handling of requested,
  residual already-applied, and no-op compatibility outcomes.
- TDD red result: the first focused backend run failed at collection because
  `LegacyFSMCompatibilityDecisionBackend` did not exist. The first policy
  focused run failed because `_maybe_switch_skill()` still entered the old
  branch-local mutation path and requested dig transition status from an
  uninitialized policy shell. After implementation, the focused backend tests
  returned `48 passed`, and the focused decision contract tests returned
  `32 passed`.
- Verification:
  `python -m pytest -q tests/test_primitive_effects.py tests/test_primitive_decision_contract.py tests/test_primitive_execution_template.py tests/test_primitive_backend.py`
  returned `96 passed`;
  `python -m pytest -q tests/test_planner_current_code_parity.py` returned
  `3 passed`;
  `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "dig_to_carry or bad_dig_replans or dig_exit_guard or complete_low_payload or carry_to_dump or dump_to_return or return_to_dig or semantic_boundary_events_drive_skill_sequence or pre_dig_align"`
  returned `24 passed, 96 deselected`;
  `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
  returned `5 passed`;
  `python -m pytest -q tests/test_primitive_capabilities.py` returned
  `25 passed`;
  compileall, both planner guard commands, and `git diff --check` completed
  successfully with no output.
- Old code parked/reclassified: `LegacyFSMBackendAdapter` remains historical
  compatibility/test scaffolding and is not used by the default policy path or
  `_maybe_switch_skill()`. `pre_dig_align` remains residual already-applied
  parking. `CompleteCellEntryDigCompatibilityEffect` remains compatibility-only.
  5P, token planning, coverage metric internals, and return direct-handoff
  internals remain existing owners.

### 2026-06-22 Phase 9.11 Extract Primitive FSM Capability Provider

- Scope: extracted 4P mainline FSM transition-status assembly from the large
  policy shell into a focused primitive capability provider. No branch order,
  reason string, threshold, token/debug/summary schema, policy reset timing,
  backend selection, behavior tree, VLM/LLM packet, `pre_dig_align` mainline
  status, `cell_entry` status, 5P override, return direct-handoff internals,
  coverage metric internals, token planning, report schema, or low-level ACT
  dispatch behavior was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `95f657c64b5890c6961363da4e47b85f03259f85`, no fetch, pull, push, reset,
  checkout, or rebase. The worktree was clean before edits.
- Added `testbed/planner/primitive_capability_provider.py` with
  `PrimitiveFSMCapabilityProviderPorts` and `PrimitiveFSMCapabilityProvider`.
  The provider owns `PrimitiveObservationFacts.from_obs(...)` projection and
  wires existing `DigTransitionStatus`, `CarryTransitionStatus`,
  `DumpTransitionStatus`, and `ReturnTransitionStatus` `from_inputs(...)`
  contracts from explicit shell snapshot/read ports.
- Updated `PrimitivePlannerACTPolicy` so `_legacy_fsm_branch_ports()` passes
  provider methods into `LegacyFSMBranchPorts`. The policy now owns
  `_primitive_fsm_capability_provider_ports()` and
  `_primitive_fsm_capability_provider()` wiring, while
  `_dig_transition_status_for_backend(...)`,
  `_carry_transition_status_for_backend(...)`,
  `_dump_transition_status_for_backend(...)`, and
  `_return_transition_status_for_backend(...)` remain thin compatibility/debug
  wrappers that delegate to the provider.
- Preserved shell-owned compatibility behavior explicitly: dig reason mirror is
  updated through `set_dig_to_carry_reason`, and return status still calls
  `refresh_return_handoff_state(obs)` before reading cached return handoff
  flags. These are documented shell compatibility ports, not backend mutation.
- Added `tests/test_primitive_capability_provider.py` for provider-owned status
  assembly, observation projection reuse, dig reason mirror, return handoff
  refresh ordering, and the no planner/self port boundary. Updated policy
  bridge tests so branch-port status wiring comes from provider methods rather
  than the old policy status assembly wrappers.
- TDD red result: the first focused provider run failed at collection because
  `testbed.planner.primitive_capability_provider` did not exist. After adding
  the provider and changing the policy bridge, the next focused run exposed old
  object-construction test assumptions around direct policy status wrappers;
  tests were updated to use the new provider boundary and then passed.
- Verification:
  `python -m pytest -q tests/test_primitive_capability_provider.py tests/test_primitive_capabilities.py`
  returned `29 passed`;
  `python -m pytest -q tests/test_primitive_effects.py tests/test_primitive_decision_contract.py tests/test_primitive_execution_template.py tests/test_primitive_backend.py`
  returned `98 passed`;
  `python -m pytest -q tests/test_planner_current_code_parity.py` returned
  `3 passed`;
  `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "dig_to_carry or bad_dig_replans or dig_exit_guard or complete_low_payload or carry_to_dump or dump_to_return or return_to_dig or semantic_boundary_events_drive_skill_sequence or pre_dig_align"`
  returned `24 passed, 96 deselected`;
  `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
  returned `5 passed`;
  compileall, both planner guard commands, and `git diff --check` completed
  successfully with no output.
- Old code parked/reclassified: `pre_dig_align` remains residual already-applied
  parking, `CompleteCellEntryDigCompatibilityEffect` remains compatibility-only,
  `LegacyFSMBackendAdapter` remains historical/test scaffolding, and 5P remains
  its existing legacy override path.
- Next action: no implementation continuation was started in this thread; the
  result is handed back to the refactor-thinking thread for audit before any
  next bounded slice is selected.

### 2026-06-22 Phase 9.12 Extract Return Start-Envelope Gate Service

- Scope: extracted return-to-dig start-envelope readiness/check computation from
  the large policy shell into a focused return handoff service. No branch order,
  reason string, threshold, token/debug/summary schema, policy reset timing,
  backend selection, behavior tree, VLM/LLM packet, `pre_dig_align` mainline
  status, `cell_entry` status, 5P override, token planning semantics,
  direct-handoff transition side effects, or low-level ACT dispatch behavior was
  intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `1c305a0c469dc17a4a2155dc220f14b3faa18123`, no fetch, pull, push, reset,
  checkout, or rebase. The worktree was clean before edits.
- Added `testbed/planner/primitive_return_handoff.py` with
  `ReturnStartEnvelopeGateConfig`, `ReturnStartEnvelopeGateInputs`,
  `ReturnStartEnvelopeGateResult`, and `ReturnStartEnvelopeGateService`. The
  service owns the readiness/check algorithm: disabled gate, missing/invalid
  token permissive compatibility, spatial long/short checks, local-depth prior
  range, plane-depth `range` / `p50_floor` / `target_band` handling, contact
  requirements from config or token, qpos envelope checks, NaN compatibility,
  and maximum error calculation.
- Updated `PrimitivePlannerACTPolicy._return_to_dig_start_envelope_ready(...)`
  into a thin wrapper. The policy now constructs service config/inputs, calls
  the service, writes `_return_to_dig_start_envelope_ready_state`,
  `_return_to_dig_start_envelope_error`, and
  `_return_to_dig_start_envelope_checks` from the result, then returns
  `result.ready`. Policy still owns `_return_to_dig_entry_close(...)`,
  `_return_to_dig_handoff_ready(...)`, direct-handoff transition side effects,
  skill switching, completed transition counters, and return token planning.
- Kept prior/token helper facades in the policy. `ReturnStartEnvelopeGateInputs`
  carries lazy prior-bounds and prior-mapping readers so the service preserves
  the old timing: prior data is not read for disabled, missing-token, or
  invalid-token compatibility cases.
- Added `tests/test_primitive_return_handoff.py` for service-level payload
  contracts and policy wrapper writeback. Coverage includes disabled/missing/
  invalid cases, spatial check payloads, local-depth prior-range payloads,
  plane-depth `p50_floor` with local contact prior, contact-required and
  missing-contact payloads, qpos checks and qpos-missing payloads, and policy
  cached-state writeback.
- TDD red result: the first focused run failed at collection because
  `testbed.planner.primitive_return_handoff` did not exist. After service and
  policy bridge implementation, the focused suite returned `7 passed`.
- Verification:
  `python -m pytest -q tests/test_primitive_return_handoff.py` returned
  `7 passed`;
  `python -m pytest -q tests/test_primitive_return_start_envelope_token_planner.py tests/test_primitive_capability_provider.py tests/test_primitive_capabilities.py`
  returned `32 passed`;
  `python -m pytest -q tests/test_primitive_effects.py tests/test_primitive_decision_contract.py tests/test_primitive_execution_template.py tests/test_primitive_backend.py`
  returned `98 passed`;
  `python -m pytest -q tests/test_planner_current_code_parity.py` returned
  `3 passed`;
  `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "return_to_dig or return_entry_frame_can_direct_handoff_without_return_action or shallow_guard or start_envelope or pre_dig_align"`
  returned `18 passed, 102 deselected`;
  `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
  returned `5 passed`;
  compileall, both planner guard commands, and `git diff --check` completed
  successfully with no output.
- Old code parked/reclassified: direct-handoff side effects remain policy-owned,
  return start-envelope token planning remains in the token planner path,
  `pre_dig_align` remains residual already-applied parking,
  `CompleteCellEntryDigCompatibilityEffect` remains compatibility-only,
  `LegacyFSMBackendAdapter` remains historical/test scaffolding, and 5P remains
  its existing legacy override path.

### 2026-06-22 Phase 9.13 Extract Return/Direct-Handoff Effect Service

- Scope: extracted the 4P return/direct-handoff effect-side transition cascade
  from the large policy shell into a focused return handoff service. No branch
  order, reason string, threshold, token/debug/summary schema, policy reset
  timing, backend selection, behavior tree, VLM/LLM packet, `pre_dig_align`
  residual status, `cell_entry` compatibility, 5P override, token planning,
  start-envelope gate calculation, coverage metric internals, or low-level ACT
  dispatch behavior was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `a6b320064801e237e36515b7d05f5bf2bf0069aa`, no fetch, pull, push, reset,
  checkout, or rebase. The worktree was clean before edits.
- Added `ReturnDirectHandoffEffectPorts`,
  `ReturnDirectHandoffEffectResult`, and
  `ReturnDirectHandoffEffectService` to
  `testbed/planner/primitive_return_handoff.py`. The service owns the ordered
  mutation sequence for `SetReturnOrDirectHandoffEffect`: set active skill to
  `return`, stop if return-target planning or start-envelope direct handoff is
  disabled, ensure the return target plan, evaluate handoff readiness, pass the
  same `handoff_ready` into direct-handoff readiness, complete the return
  transition, compute the post-return next skill, and set
  `return_to_{next_skill}_start_envelope_ready`.
- Updated `PrimitivePlannerACTPolicy._set_return_or_direct_handoff(...)` and
  `_try_return_direct_handoff_at_current_obs(...)` into thin service-backed
  wrappers. The policy now builds `_return_direct_handoff_effect_ports()` and
  `_return_direct_handoff_effect_service()`. Shell-owned mutations still occur
  through explicit ports: `_set_skill`,
  `_ensure_return_target_plan_for_cycle`,
  `_return_to_dig_handoff_ready`,
  `_return_to_dig_direct_handoff_ready`,
  `_complete_return_transition_for_backend`, and
  `_next_skill_after_return_transition`.
- Added focused tests in `tests/test_primitive_return_handoff.py` for disabled
  direct handoff, disabled return-target planner, not-ready readiness checks,
  ready direct handoff to `dig`, ready direct handoff to residual
  `pre_dig_align`, no-op compatibility try outside `return`, and policy wrapper
  delegation. Added a policy/applier integration check in
  `tests/test_primitive_decision_contract.py` proving
  `SetReturnOrDirectHandoffEffect` enters the service-backed wrapper through
  `_apply_requested_tick_effects(...)`.
- TDD red result: the first focused run failed at collection because
  `ReturnDirectHandoffEffectPorts` did not exist. After adding the service and
  policy bridge, the focused direct-handoff tests returned `7 passed,
  8 deselected`, and the full return-handoff test file returned `15 passed`.
- Verification:
  `python -m pytest -q tests/test_primitive_return_handoff.py tests/test_primitive_effects.py tests/test_primitive_decision_contract.py tests/test_primitive_execution_template.py tests/test_primitive_backend.py`
  returned `114 passed`;
  `python -m pytest -q tests/test_planner_current_code_parity.py` returned
  `3 passed`;
  `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "return_to_dig or return_entry_frame_can_direct_handoff_without_return_action or shallow_guard or start_envelope or pre_dig_align"`
  returned `18 passed, 102 deselected`;
  `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
  returned `5 passed`;
  compileall, both planner guard commands, and `git diff --check` completed
  successfully with no output.
- Old code parked/reclassified: start-envelope readiness remains in
  `ReturnStartEnvelopeGateService`, token planning remains in the token planner
  path, direct-handoff decision does not move into backend branches,
  `pre_dig_align` remains residual already-applied parking,
  `CompleteCellEntryDigCompatibilityEffect` remains compatibility-only,
  `LegacyFSMBackendAdapter` remains historical/test scaffolding, and 5P remains
  its existing legacy override path.

### 2026-06-22 Phase 9.14 Extract Policy Observation Token Assembler

- Scope: extracted low-level policy observation token injection assembly from
  the large policy shell into a focused observation assembler. No token
  planning algorithm, token key name, token order, source/fallback string,
  debug/summary schema, golden-window contract, branch order, reason string,
  threshold, policy reset timing, public config behavior, `cell_entry`
  compatibility classification, `pre_dig_align` residual status, 5P override,
  or low-level ACT dispatch behavior was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `825cd1bd05ff5fb8e7e5c2b25f599ff2ae9a5758`, no fetch, pull, push, reset,
  checkout, or rebase. The worktree was clean before edits.
- Added `testbed/planner/primitive_observation.py` with
  `PrimitivePolicyObservationAssemblerPorts`,
  `PrimitiveTokenInjectionState`,
  `PrimitivePolicyObservationAssemblyResult`, and
  `PrimitivePolicyObservationAssembler`. The assembler owns token provider call
  order, observation copy/no-copy behavior, injected key names, and legacy
  injected-flag state calculation.
- Preserved `_policy_obs(...)` semantics exactly: providers are called in order
  goal -> cell-entry compatibility -> dig-cut -> dig-depth-profile ->
  return-target -> return-relocate -> return-start-envelope; all-`None`
  providers return the original observation object; any token creates
  `dict(obs)`; injected keys remain `goal_tokens`, `cell_entry_tokens`,
  `dig_cut_tokens`, `dig_depth_profile_tokens_v1`, `return_target_tokens`,
  `return_relocate_tokens_v1`, and `return_start_envelope_tokens_v1`; goal
  tokens have no legacy injected flag; `cell_entry_tokens` remains
  compatibility-only.
- Updated `PrimitivePlannerACTPolicy._policy_obs(...)` into a thin wrapper that
  clears stale injected flags before assembly, delegates to
  `_policy_observation_assembler().assemble(obs)`, writes the returned
  `PrimitiveTokenInjectionState` into the legacy injected-flag fields, and
  returns `result.policy_obs`. Token provider methods such as
  `_dig_cut_tokens_for_obs(...)`, `_return_target_tokens_for_obs(...)`, and
  `_goal_tokens()` remain in their existing owners.
- Added `tests/test_primitive_observation.py` for all-`None` identity behavior,
  copy/injected-key behavior, provider order, goal-token no-flag behavior,
  cell-entry compatibility-only injected flag behavior, and policy wrapper
  delegation/writeback.
- TDD red result: the first focused run failed at collection because
  `testbed.planner.primitive_observation` did not exist. After adding the
  assembler module and policy bridge, `python -m pytest -q
  tests/test_primitive_observation.py` returned `5 passed`.
- Verification:
  `python -m pytest -q tests/test_primitive_observation.py` returned
  `5 passed`;
  `python -m pytest -q tests/test_primitive_goal_token_provider.py tests/test_primitive_dig_cut_token_planner.py tests/test_primitive_dig_depth_profile_token_planner.py tests/test_primitive_return_target_token_planner.py tests/test_primitive_return_relocate_token_planner.py tests/test_primitive_return_start_envelope_token_planner.py tests/test_primitive_token_status.py`
  returned `23 passed`;
  `python -m pytest -q tests/test_primitive_return_handoff.py tests/test_primitive_effects.py tests/test_primitive_decision_contract.py tests/test_primitive_execution_template.py tests/test_primitive_backend.py`
  returned `114 passed`;
  `python -m pytest -q tests/test_planner_current_code_parity.py` returned
  `3 passed`;
  `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
  returned `5 passed`;
  compileall, both planner guard commands, and `git diff --check` completed
  successfully with no output.
- Old code parked/reclassified: token planning remains in the existing token
  planner/provider methods, `cell_entry` token injection remains
  compatibility-only, `pre_dig_align` remains residual already-applied parking,
  `CompleteCellEntryDigCompatibilityEffect` remains compatibility-only,
  `LegacyFSMBackendAdapter` remains historical/test scaffolding, and 5P remains
  its existing legacy override path.

### 2026-06-22 Phase 9.15 Extract Public Debug State Report Builder

- Scope: extracted public `PrimitivePlannerACTPolicy.debug_state()` dict
  assembly from the large policy shell into a focused reporting module. No
  `rollout_summary()`, `planner_trace()`, per-tick `_make_debug_state(...)`,
  token planning algorithm, token/debug/summary schema, golden-window contract,
  branch order, reason string, threshold, policy reset timing, public config
  behavior, `cell_entry` compatibility classification, `pre_dig_align`
  residual status, 5P override, or low-level ACT dispatch behavior was
  intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `3d1cabe3b4968bf12b52dbdb953e152ae3ba715a`, no fetch, pull, push, reset,
  checkout, or rebase. The worktree was clean before edits.
- Added `testbed/planner/primitive_debug_report.py` with
  `PrimitiveDebugStateSnapshot`, `PrimitiveDebugReportInputs`, and
  `PrimitiveDebugReportBuilder`. The builder owns final public debug key
  assembly, token debug-field merge, report-section merge, and plain
  dict/list payload projection.
- Updated `PrimitivePlannerACTPolicy.debug_state()` into a thin wrapper that
  delegates to `_debug_report_builder().build(_debug_report_inputs())`. The
  policy shell now prepares typed snapshots/sections only:
  `_debug_state_snapshot_for_report()`, `_token_status_for_debug_report()`,
  return/pending/dig-cut/coverage/cell-entry/scripted-bootstrap/dig-progress/
  pre-dig section helpers.
- Token-related debug fields now enter the public debug report through
  `TokenStatus.to_debug_fields()`, preserving legacy keys such as
  `dig_cut_token_source`, `return_target_tokens`,
  `return_start_envelope_tokens`, `fallback_reason`, and
  `dig_cut_token_in_prior_p10_p90` without duplicating that mapping in the
  policy shell or report builder.
- Preserved representative observable fields in focused tests:
  `skill_name`, `skill_id`, `skill_switch_reason`, `transition_source`,
  `transition_policy_mode`, `completed_transition_count`,
  `primitive_cycle_index`, return start-envelope fields, coverage corridor
  fields, depleted/terminal-stop fields, pre-dig counters, and cell-entry
  compatibility fields.
- TDD red result: the first focused run failed at collection because
  `testbed.planner.primitive_debug_report` did not exist. After adding the
  builder module and policy bridge, `python -m pytest -q
  tests/test_primitive_debug_report.py` returned `3 passed`.
- Verification:
  `python -m pytest -q tests/test_primitive_debug_report.py` returned
  `3 passed`;
  `python -m pytest -q tests/test_primitive_token_status.py tests/test_primitive_observation.py`
  returned `8 passed`;
  `python -m pytest -q tests/test_primitive_goal_token_provider.py tests/test_primitive_dig_cut_token_planner.py tests/test_primitive_dig_depth_profile_token_planner.py tests/test_primitive_return_target_token_planner.py tests/test_primitive_return_relocate_token_planner.py tests/test_primitive_return_start_envelope_token_planner.py`
  returned `20 passed`;
  `python -m pytest -q tests/test_primitive_return_handoff.py tests/test_primitive_effects.py tests/test_primitive_decision_contract.py tests/test_primitive_execution_template.py tests/test_primitive_backend.py`
  returned `114 passed`;
  `python -m pytest -q tests/test_planner_current_code_parity.py` returned
  `3 passed`;
  `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
  returned `5 passed`;
  compileall completed successfully with no output.
- Old code parked/reclassified: `rollout_summary()` and `planner_trace()`
  remain in their existing owners for a later audit, `_make_debug_state(...)`
  remains the per-tick compact debug-state finalizer, token planning remains in
  existing token providers, `cell_entry` remains compatibility/debug material,
  `pre_dig_align` remains residual parking/debug material,
  `LegacyFSMBackendAdapter` remains historical/test scaffolding, and 5P remains
  its existing legacy override path.

### 2026-06-22 Phase 9.16 Extract Public Rollout Summary Report Builder

- Scope: extracted public `PrimitivePlannerACTPolicy.rollout_summary()` dict
  assembly from the large policy shell into a focused reporting module. No
  `planner_trace()`, public `debug_state()` assembly, per-tick
  `_make_debug_state(...)`, token planning algorithm, token/debug/summary
  schema, golden-window contract, branch order, reason string, threshold,
  policy reset timing, public config behavior, `cell_entry` compatibility
  classification, `pre_dig_align` residual status, 5P override, or low-level
  ACT dispatch behavior was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `390eca74deea77df36879e716cf7e7d98154b614`, no fetch, pull, push, reset,
  checkout, or rebase. The worktree was clean before edits.
- Added `testbed/planner/primitive_rollout_summary.py` with
  `PrimitiveRolloutSummaryInputs` and `PrimitiveRolloutSummaryBuilder`. The
  builder owns final public summary key layout, bool-like `int(...)`
  projection, `None` to `NaN` fallback projection, and compact scalar
  conversions for transition, return, pending/dig-token, coverage,
  scripted-bootstrap, residual pre-dig, cell-entry compatibility, and dig
  replan fields.
- Updated `PrimitivePlannerACTPolicy.rollout_summary()` into a thin wrapper
  that delegates to
  `_rollout_summary_builder().build(_rollout_summary_inputs())`. The policy
  shell now prepares a typed scalar summary snapshot only; `planner_trace()`
  remains in its existing owner.
- Preserved public summary behavior in focused tests: representative keys such
  as `transition_source`, `transition_policy_mode`,
  `transition_timeout_count`, `completed_transition_count`,
  `primitive_final_skill`, `primitive_cycle_index`, `cell_entry_enabled`,
  `cell_entry_trace_count`, `dig_cut_token_dim`, `return_target_token_dim`,
  `return_target_token_source`, return start-envelope fields, pending fields,
  dig-token fields, coverage fields, scripted bootstrap timeout, pre-dig
  fields, and dig replan counters are still emitted. Bool-like fields remain
  integers, and `None` values for optional numeric summary fields still project
  to `NaN`.
- TDD red result: the first focused run failed at collection because
  `testbed.planner.primitive_rollout_summary` did not exist. After adding the
  builder module and policy bridge, `python -m pytest -q
  tests/test_primitive_rollout_summary.py` returned `3 passed`.
- Verification:
  `python -m pytest -q tests/test_primitive_rollout_summary.py` returned
  `3 passed`;
  `python -m pytest -q tests/test_primitive_debug_report.py tests/test_primitive_token_status.py tests/test_primitive_observation.py`
  returned `11 passed`;
  `python -m pytest -q tests/test_primitive_goal_token_provider.py tests/test_primitive_dig_cut_token_planner.py tests/test_primitive_dig_depth_profile_token_planner.py tests/test_primitive_return_target_token_planner.py tests/test_primitive_return_relocate_token_planner.py tests/test_primitive_return_start_envelope_token_planner.py`
  returned `20 passed`;
  `python -m pytest -q tests/test_primitive_return_handoff.py tests/test_primitive_effects.py tests/test_primitive_decision_contract.py tests/test_primitive_execution_template.py tests/test_primitive_backend.py`
  returned `114 passed`;
  `python -m pytest -q tests/test_planner_current_code_parity.py` returned
  `3 passed`;
  `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
  returned `5 passed`;
  `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "semantic_boundary_events_drive_skill_sequence or return_to_dig or pre_dig_align or start_envelope"`
  returned `18 passed, 102 deselected`;
  compileall, both planner guard commands, and `git diff --check` completed
  successfully with no output.
- Old code parked/reclassified: `planner_trace()` remains in its existing
  owner for a later audit, `_make_debug_state(...)` remains the per-tick
  compact debug-state finalizer, public `debug_state()` remains in
  `PrimitiveDebugReportBuilder`, token planning remains in existing token
  providers, `cell_entry` remains compatibility/report material,
  `pre_dig_align` remains residual parking/report material,
  `LegacyFSMBackendAdapter` remains historical/test scaffolding, and 5P remains
  its existing legacy override path.

### 2026-06-22 Phase 9.17 Extract Public Planner Trace Report Builder

- Scope: extracted public `PrimitivePlannerACTPolicy.planner_trace()` dict
  assembly from the large policy shell into a focused reporting module. No
  coverage decision trace recording, coverage event payload schema, coverage
  corridor debug projection service, coverage scoring/runtime updates, public
  `debug_state()` assembly, public `rollout_summary()` assembly, token planning
  algorithm, token/debug/summary/trace schema, golden-window contract, branch
  order, reason string, threshold, policy reset timing, public config behavior,
  `cell_entry` compatibility classification, `pre_dig_align` residual status,
  5P override, or low-level ACT dispatch behavior was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `620727bb5ce9cb3345da9c6537777cc46bcc2052`, no fetch, pull, push, reset,
  checkout, or rebase. The worktree was clean before edits.
- Added `testbed/planner/primitive_planner_trace.py` with
  `PrimitivePlannerTraceInputs` and `PrimitivePlannerTraceBuilder`. The builder
  owns final public planner-trace key layout, token contract version/string
  fields, top-level list projection for `cell_entry_trace`,
  `coverage_corridors`, and `coverage_decision_trace`, coverage config/status
  fields, coverage decision trace count, and terminal-stop fields.
- Updated `PrimitivePlannerACTPolicy.planner_trace()` into a thin wrapper that
  delegates to `_planner_trace_builder().build(_planner_trace_inputs())`. The
  policy shell now prepares typed trace inputs and preprojects coverage
  corridor payloads through the existing `_coverage_corridor_to_debug(...)`
  facade; coverage decision trace recording remains in its existing owner.
- Preserved public trace behavior in focused tests: exact token contract
  version fields, exact dig-cut/return-target/return-start-envelope contract
  strings, coverage config/status fields, terminal-stop fields,
  `coverage_decision_trace_count`, and top-level list-copy behavior for
  cell-entry trace, coverage corridors, and coverage decision trace.
- TDD red result: the first focused run failed at collection because
  `testbed.planner.primitive_planner_trace` did not exist. After adding the
  builder module and policy bridge, `python -m pytest -q
  tests/test_primitive_planner_trace.py` returned `3 passed`.
- Verification:
  `python -m pytest -q tests/test_primitive_planner_trace.py` returned
  `3 passed`;
  `python -m pytest -q tests/test_primitive_rollout_summary.py tests/test_primitive_debug_report.py tests/test_primitive_token_status.py tests/test_primitive_observation.py`
  returned `14 passed`;
  `python -m pytest -q tests/test_primitive_coverage_reports.py tests/test_primitive_coverage_runtime.py`
  returned `4 passed`;
  `python -m pytest -q tests/test_primitive_return_handoff.py tests/test_primitive_effects.py tests/test_primitive_decision_contract.py tests/test_primitive_execution_template.py tests/test_primitive_backend.py`
  returned `114 passed`;
  `python -m pytest -q tests/test_planner_current_code_parity.py` returned
  `3 passed`;
  `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
  returned `5 passed`;
  `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "planner_trace or coverage_decision_trace or terminal_depletion or semantic_boundary_events_drive_skill_sequence"`
  returned `3 passed, 117 deselected`;
  compileall, both planner guard commands, and `git diff --check` completed
  successfully with no output.
- Old code parked/reclassified: coverage decision trace recording remains in
  the existing coverage runtime/report path, coverage corridor projection stays
  behind `CoverageReportService` and the existing policy facade, public
  `debug_state()` remains in `PrimitiveDebugReportBuilder`, public
  `rollout_summary()` remains in `PrimitiveRolloutSummaryBuilder`,
  `_make_debug_state(...)` remains the per-tick compact debug-state finalizer,
  token planning remains in existing token providers, `cell_entry` remains
  compatibility/report material, `pre_dig_align` remains residual
  parking/report material, `LegacyFSMBackendAdapter` remains historical/test
  scaffolding, and 5P remains its existing legacy override path.

### 2026-06-22 Phase 9.18 Extract Primitive Action Dispatch Service

- Scope: extracted primitive action dispatch and active low-level policy
  selection from the large policy shell into a focused service. No reset
  lifecycle, `_set_skill(...)` state mutation/reset timing, policy observation
  token assembly, token planning, scripted bootstrap action algorithm,
  pre-dig-align action algorithm, branch order, reason string, threshold,
  token/debug/summary/trace schema, public config behavior, 5P transition
  semantics, or low-level ACT output behavior was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `3d4628940543beae288b08fa1395341cc6e0efd8`, no fetch, pull, push, reset,
  checkout, or rebase.
- Added `testbed/planner/primitive_action_dispatch.py` with
  `PrimitiveActionDispatchPorts` and `PrimitiveActionDispatchService`. The
  service owns scripted-bootstrap dispatch short-circuit, residual
  `pre_dig_align` action short-circuit, active low-level policy selection,
  first-dig activation, all-policy ordering, policy-observation invocation,
  low-level policy `predict(...)`, and `float32` reshape to `action_dim`.
- Updated `PrimitivePlannerACTPolicy._dispatch_tick_action(...)`,
  `_active_policy()`, `_all_policies()`, and `_first_dig_policy_active()` into
  thin wrappers backed by `_action_dispatch_service()`. The policy shell now
  builds typed action-dispatch ports and retains lifecycle/state mutation
  ownership.
- Added a 5P compatibility `_action_dispatch_ports()` mapping so inherited
  dispatch can use the 5P skill/policy set without migrating 5P transition
  semantics. Existing 5P `_active_policy()` / `_all_policies()` overrides
  remain legacy compatibility entry points.
- TDD red result: the first focused run failed at collection because
  `testbed.planner.primitive_action_dispatch` did not exist. After adding the
  service module and policy bridge, `python -m pytest -q
  tests/test_primitive_action_dispatch.py` returned `10 passed`.
- Verification:
  `python -m pytest -q tests/test_primitive_action_dispatch.py` returned
  `10 passed`;
  `python -m pytest -q tests/test_primitive_execution_template.py tests/test_primitive_observation.py`
  returned `11 passed`;
  `python -m pytest -q tests/test_primitive_planner_trace.py tests/test_primitive_rollout_summary.py tests/test_primitive_debug_report.py tests/test_primitive_token_status.py`
  returned `12 passed`;
  `python -m pytest -q tests/test_primitive_return_handoff.py tests/test_primitive_effects.py tests/test_primitive_decision_contract.py tests/test_primitive_backend.py`
  returned `108 passed`;
  `python -m pytest -q tests/test_planner_current_code_parity.py` returned
  `3 passed`;
  `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
  returned `5 passed`;
  `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "first_dig_policy_for_cycle_zero or semantic_boundary_events_drive_skill_sequence or pre_dig_align or scripted_bootstrap or return_to_dig"`
  returned `18 passed, 102 deselected`;
  compileall, both planner guard commands, and `git diff --check` completed
  successfully with no output.
- Old code parked/reclassified: reset lifecycle and `_set_skill(...)` remain in
  the policy shell, policy observation/token assembly remains in
  `PrimitivePolicyObservationAssembler`, scripted-bootstrap and pre-dig-align
  action algorithms remain in their existing owners, public report builders
  remain unchanged, `cell_entry` remains compatibility/report material,
  `pre_dig_align` remains residual parking/action material,
  `LegacyFSMBackendAdapter` remains historical/test scaffolding, and 5P remains
  its existing legacy override path.

### 2026-06-22 Phase 9.19 Extract Primitive Tick Finalization Service

- Scope: extracted primitive tick finalization from the large policy shell into
  a focused service. No `run_primitive_tick()` ordering, reset lifecycle,
  `_set_skill(...)` mutation/reset timing, decision branches, requested
  effects, policy observation/token planning, scripted bootstrap/pre-dig action
  algorithms, coverage runtime/scoring updates, return handoff internals,
  branch order, reason string, threshold, token/debug/summary/trace schema,
  public config behavior, 5P transition semantics, or low-level ACT dispatch
  output contract was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `b14600a173c340bf2c4564cdf19e5f85efb28836`, no fetch, pull, push, reset,
  checkout, or rebase.
- Added `testbed/planner/primitive_tick_finalization.py` with
  `PrimitivePlannerDebugState`, `PrimitiveTickFinalizationInputs`, and
  `PrimitiveTickFinalizationService`. The service owns previous-action copy
  semantics, dispatch-after transition-completed reason-prefix detection, and
  compact per-tick debug-state assembly.
- Moved `PrimitivePlannerDebugState` into the focused module and re-imported it
  from `testbed.policies.hybrid.primitive_planner` for compatibility with
  existing private/reporting consumers.
- Updated `PrimitivePlannerACTPolicy._record_tick_previous_action()`,
  `_transition_completed_after_tick_dispatch()`, `_make_debug_state()`, and
  `_finalize_tick_debug_state()` into service-backed wrappers. The policy shell
  now prepares typed finalization inputs and writes `_prev_action` /
  `_debug_state`.
- Replaced the 5P compatibility `_make_debug_state()` assembly body with a
  5P-specific `_tick_finalization_inputs(...)` mapping. The shared service now
  owns compact debug-state assembly for both 4P and the parked 5P compatibility
  planner, while 5P transition branches and active-policy overrides remain
  unchanged.
- TDD red result: the first focused run failed at collection because
  `testbed.planner.primitive_tick_finalization` did not exist. After adding the
  service module and policy bridge, `python -m pytest -q
  tests/test_primitive_tick_finalization.py` returned `10 passed`.
- Verification:
  `python -m pytest -q tests/test_primitive_tick_finalization.py` returned
  `10 passed`;
  `python -m pytest -q tests/test_primitive_execution_template.py tests/test_primitive_action_dispatch.py`
  returned `16 passed`;
  `python -m pytest -q tests/test_primitive_planner_trace.py tests/test_primitive_rollout_summary.py tests/test_primitive_debug_report.py tests/test_primitive_token_status.py`
  returned `12 passed`;
  `python -m pytest -q tests/test_primitive_return_handoff.py tests/test_primitive_effects.py tests/test_primitive_decision_contract.py tests/test_primitive_backend.py`
  returned `108 passed`;
  `python -m pytest -q tests/test_planner_current_code_parity.py` returned
  `3 passed`;
  `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
  returned `5 passed`;
  `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "first_dig_policy_for_cycle_zero or semantic_boundary_events_drive_skill_sequence or pre_dig_align or scripted_bootstrap or return_to_dig"`
  returned `18 passed, 102 deselected`;
  compileall, both planner guard commands, and `git diff --check` completed
  successfully with no output.
- Old code parked/reclassified: reset lifecycle and `_set_skill(...)` remain in
  the policy shell, public report builders remain unchanged, action dispatch
  remains in `PrimitiveActionDispatchService`, policy observation/token
  assembly remains in `PrimitivePolicyObservationAssembler`, scripted-bootstrap
  and pre-dig-align action algorithms remain in their existing owners,
  `cell_entry` remains compatibility/report material, `pre_dig_align` remains
  residual parking/action material, `LegacyFSMBackendAdapter` remains
  historical/test scaffolding, and 5P remains its existing legacy override path.

### 2026-06-22 Phase 9.20 Extract Primitive Coverage Effect Runtime Coordinator

- Scope: extracted coverage requested-effect runtime sequencing from the large
  policy shell into a focused coordinator. No coverage candidate construction,
  coverage scoring/selection, corridor debug payload schema, coverage decision
  trace payload schema, planner trace/summary/debug schema, terminal-stop
  reason string, branch order, reason string, threshold, token schema, reset
  timing, public config behavior, pre-dig-align internals, cell-entry
  compatibility, 5P transition semantics, return handoff internals, or
  low-level ACT dispatch behavior was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `560974571cb539e47e012c02d8e9c27c79587dfa`, no fetch, pull, push, reset,
  checkout, or rebase. The worktree was clean before edits.
- Added `CoverageEffectRuntimePorts` and `CoverageEffectRuntimeCoordinator` to
  `testbed/planner/primitive_coverage_updates.py`. The coordinator owns
  coverage-mode no-op gating, dig payload-gain completion, dump completion
  writeback/event/reopen/terminal ordering, corridor rejection
  writeback/event/reopen/terminal ordering, multi-pass reopen result
  application, and terminal-stop result/event application.
- Updated `PrimitivePlannerACTPolicy._complete_coverage_dig()`,
  `_complete_coverage_dump()`, `_reject_active_coverage_corridor()`,
  `_maybe_reopen_coverage_pass()`, and `_request_coverage_terminal_stop()` into
  coordinator-backed thin wrappers. The policy shell now builds
  `_coverage_effect_runtime_ports()` from existing coverage state storage,
  facts/report helper facades, update/runtime service factories, and explicit
  state writeback callbacks.
- Added `tests/test_primitive_coverage_effect_runtime.py` with focused coverage
  for non-coverage no-op behavior, dig payload max update, dump completion
  event/terminal ordering, corridor rejection counted and uncounted paths,
  reopen-pass writeback/event ordering, terminal-stop duplicate suppression, and
  policy wrapper delegation.
- TDD red result: the first focused run failed at collection because
  `CoverageEffectRuntimeCoordinator` did not exist in
  `testbed.planner.primitive_coverage_updates`. After adding the coordinator and
  policy bridge, `python -m pytest -q
  tests/test_primitive_coverage_effect_runtime.py` returned `10 passed`.
- Verification:
  `python -m pytest -q tests/test_primitive_coverage_effect_runtime.py`
  returned `10 passed`;
  `python -m pytest -q tests/test_primitive_coverage_updates.py tests/test_primitive_coverage_runtime.py tests/test_primitive_coverage_reports.py`
  returned `6 passed`;
  `python -m pytest -q tests/test_primitive_effects.py tests/test_primitive_decision_contract.py tests/test_primitive_backend.py`
  returned `93 passed`;
  `python -m pytest -q tests/test_primitive_planner_trace.py tests/test_primitive_rollout_summary.py tests/test_primitive_debug_report.py tests/test_primitive_tick_finalization.py`
  returned `19 passed`;
  `python -m pytest -q tests/test_planner_current_code_parity.py` returned
  `3 passed`;
  `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
  returned `5 passed`;
  `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "coverage_decision_trace or terminal_depletion or semantic_boundary_events_drive_skill_sequence or dig_to_carry or dump_to_return or return_to_dig"`
  returned `9 passed, 111 deselected`;
  compileall and both planner guard commands completed successfully with no
  output.
- Old code parked/reclassified: coverage candidate construction and
  scoring/selection remain in the existing coverage planning path, corridor
  debug/report payload projection remains behind `CoverageReportService`,
  coverage facts helpers and mutable state storage remain in the policy shell,
  requested-effect dispatch remains in `RequestedEffectApplier`, public report
  builders remain unchanged, `cell_entry` remains compatibility/report
  material, `pre_dig_align` remains residual parking/action material,
  `LegacyFSMBackendAdapter` remains historical/test scaffolding, and 5P remains
  its existing legacy override path.

### 2026-06-22 Phase 9.21 Extract Primitive Coverage Selection Runtime Coordinator

- Scope: extracted coverage corridor selection runtime sequencing from the
  large policy shell into a focused coordinator. No coverage candidate
  construction algorithm, coverage scoring algorithm, first-dig gate facts,
  state-exemplar matching, raw-field/token planning, corridor debug payload
  schema, coverage decision trace payload schema, planner trace/summary/debug
  schema, terminal-stop reason string, branch order, reason string, threshold,
  token schema, reset timing, public config behavior, pre-dig-align internals,
  cell-entry compatibility, 5P transition semantics, return handoff internals,
  or low-level ACT dispatch behavior was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `db86769cb84968e9f1ce0201884d055a411819c9`, no fetch, pull, push, reset,
  checkout, or rebase. The worktree was clean before edits.
- Added `CoverageSelectionRuntimePorts` and
  `CoverageSelectionRuntimeCoordinator` to
  `testbed/planner/primitive_coverage.py`. The coordinator owns dig-cut prior
  and empty-candidate checks, ensure-corridor no-op/build writeback,
  selection-service invocation, candidate-score writeback, `select_corridor`
  decision-event emission, all-depleted reopen/terminal sequencing, and
  active/last-selected corridor id writeback.
- Updated `PrimitivePlannerACTPolicy._select_next_coverage_corridor()`,
  `_ensure_coverage_corridors()`, and `_select_coverage_corridor()` into
  coordinator-backed thin wrappers. The policy shell now builds
  `_coverage_selection_runtime_ports()` from existing coverage mutable state
  storage, candidate builder/service factories, selection facts providers,
  recent-row reference helper, existing reopen/terminal wrappers, and explicit
  state writeback callbacks.
- Added `tests/test_primitive_coverage_selection_runtime.py` with focused
  coverage for ensure no-op/build behavior, old prior/empty-candidate error
  messages, select-next ordering and selected-id writeback, all-depleted
  pre-select reopen, select event payload ordering, post-select terminal stop,
  and policy wrapper delegation.
- TDD red result: the first focused run failed at collection because
  `CoverageSelectionRuntimeCoordinator` did not exist in
  `testbed.planner.primitive_coverage`. After adding the coordinator and
  policy bridge, `python -m pytest -q
  tests/test_primitive_coverage_selection_runtime.py` returned `7 passed`.
- Verification:
  `python -m pytest -q tests/test_primitive_coverage_selection_runtime.py`
  returned `7 passed`;
  `python -m pytest -q tests/test_primitive_coverage_selection.py tests/test_primitive_coverage_candidates.py`
  returned `3 passed`;
  `python -m pytest -q tests/test_primitive_coverage_effect_runtime.py tests/test_primitive_coverage_updates.py tests/test_primitive_coverage_runtime.py tests/test_primitive_coverage_reports.py`
  returned `16 passed`;
  `python -m pytest -q tests/test_primitive_effects.py tests/test_primitive_decision_contract.py tests/test_primitive_backend.py`
  returned `93 passed`;
  `python -m pytest -q tests/test_primitive_planner_trace.py tests/test_primitive_rollout_summary.py tests/test_primitive_debug_report.py tests/test_primitive_tick_finalization.py`
  returned `19 passed`;
  `python -m pytest -q tests/test_planner_current_code_parity.py` returned
  `3 passed`;
  `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
  returned `5 passed`;
  `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "coverage_decision_trace or terminal_depletion or semantic_boundary_events_drive_skill_sequence or operator_prior_coverage or first_dig or return_to_dig"`
  returned `14 passed, 106 deselected`;
  compileall and both planner guard commands completed successfully with no
  output.
- Old code parked/reclassified: coverage candidate construction remains in
  `CoverageCandidateBuilder`, coverage scoring remains in
  `CoverageSelectionService`, raw-field/state-exemplar/first-dig fact helpers
  remain in the policy shell, coverage effect runtime remains in
  `CoverageEffectRuntimeCoordinator`, corridor debug/report payload projection
  remains behind `CoverageReportService`, requested-effect dispatch remains in
  `RequestedEffectApplier`, public report builders remain unchanged,
  `cell_entry` remains compatibility/report material, `pre_dig_align` remains
  residual parking/action material, `LegacyFSMBackendAdapter` remains
  historical/test scaffolding, and 5P remains its existing legacy override path.

### 2026-06-22 Phase 9.22 Extract Primitive Coverage Runtime State Owner

- Scope: extracted mutable coverage runtime storage from the large policy shell
  into a focused `CoverageRuntimeState` owner. No coverage candidate
  construction, selection scoring, first-dig gate, state-exemplar matching,
  raw-field/token planning, coverage effect sequencing, decision trace payload
  schema, candidate score payload schema, terminal-stop reason string, branch
  order, reason string, threshold, token/debug/summary/trace schema, reset
  timing, public config behavior, pre-dig-align internals, cell-entry
  compatibility, 5P transition semantics, return handoff internals, or low-level
  ACT dispatch behavior was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `a3270c3e3b27ea80b858006dd23e86e8255ec233`, no fetch, pull, push, reset,
  checkout, or rebase. The worktree was clean before edits.
- Added `testbed/planner/primitive_coverage_state.py` with
  `CoverageRuntimeState`. The state owner stores corridor containers,
  active/last-selected ids, payload/deposit counters, completed dump and global
  low-productivity counters, pass and terminal-stop state, candidate scores,
  decision trace, rejected state exemplar ids, and active state-exemplar payload.
  It owns corridor lookup, active corridor lookup, depleted count,
  all-depleted status, selected-id/counter/terminal setters, and
  active/rejected state-exemplar updates. This is a focused coverage runtime
  state owner, not a generic blackboard.
- Updated `PrimitivePlannerACTPolicy.reset()` to initialize a fresh
  `CoverageRuntimeState`. The previous `_coverage_*` private names now remain
  as property-backed compatibility facades, so tests and diagnostics that read
  or mutate `_coverage_corridors`, `_coverage_decision_trace`,
  `_coverage_rejected_state_exemplar_ids`, `_coverage_candidate_scores`, and
  scalar coverage fields still operate on the same source-of-truth state owner.
- Updated coverage state helper/facade methods so selection and effect runtime
  ports read and write through `CoverageRuntimeState`: `_set_coverage_*`
  wrappers delegate to state methods, `_coverage_corridor_by_id()`,
  `_coverage_active_corridor()`, `_coverage_depleted_count()`, and
  `_coverage_all_depleted()` delegate to the owner, and active state-exemplar
  writeback/clear paths update the owner.
- Added `tests/test_primitive_coverage_state.py` with focused coverage for
  default reset values, stored mutable container identity, corridor helper
  behavior, runtime setter/update helpers, policy compatibility facades, and
  selection/effect ports sharing the same state owner.
- TDD red result: the first focused run failed at collection because
  `testbed.planner.primitive_coverage_state` did not exist. After adding the
  state owner and policy compatibility bridge, `python -m pytest -q
  tests/test_primitive_coverage_state.py` returned `6 passed`.
- Verification:
  `python -m pytest -q tests/test_primitive_coverage_state.py` returned
  `6 passed`;
  `python -m pytest -q tests/test_primitive_coverage_selection_runtime.py tests/test_primitive_coverage_effect_runtime.py`
  returned `17 passed`;
  `python -m pytest -q tests/test_primitive_coverage_selection.py tests/test_primitive_coverage_candidates.py tests/test_primitive_coverage_updates.py tests/test_primitive_coverage_runtime.py tests/test_primitive_coverage_reports.py tests/test_primitive_coverage_status.py`
  returned `12 passed`;
  `python -m pytest -q tests/test_primitive_effects.py tests/test_primitive_decision_contract.py tests/test_primitive_backend.py`
  returned `93 passed`;
  `python -m pytest -q tests/test_primitive_planner_trace.py tests/test_primitive_rollout_summary.py tests/test_primitive_debug_report.py tests/test_primitive_tick_finalization.py`
  returned `19 passed`;
  `python -m pytest -q tests/test_planner_current_code_parity.py` returned
  `3 passed`;
  `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
  returned `5 passed`;
  `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "coverage_decision_trace or terminal_depletion or semantic_boundary_events_drive_skill_sequence or operator_prior_coverage or first_dig or return_to_dig"`
  returned `14 passed, 106 deselected`;
  compileall and both planner guard commands completed successfully with no
  output; `git diff --check` completed successfully.
- Old code parked/reclassified: coverage candidate construction remains in
  `CoverageCandidateBuilder`, coverage scoring remains in
  `CoverageSelectionService`, coverage selection sequencing remains in
  `CoverageSelectionRuntimeCoordinator`, coverage effect sequencing remains in
  `CoverageEffectRuntimeCoordinator`, raw-field/state-exemplar/first-dig fact
  helpers remain policy facades, corridor debug/report payload projection
  remains behind `CoverageReportService`, requested-effect dispatch remains in
  `RequestedEffectApplier`, public report builders remain unchanged,
  `cell_entry` remains compatibility/report material, `pre_dig_align` remains
  residual parking/action material, `LegacyFSMBackendAdapter` remains
  historical/test scaffolding, and 5P remains its existing legacy override path.

### 2026-06-22 Phase 9.23 Extract Primitive Coverage State-Exemplar Planner

- Scope: extracted confirmed-live coverage state-conditioned exemplar planning
  from the large policy shell into a focused planner service. No token schema,
  token key, contract version, debug/summary/trace schema, coverage candidate
  construction, coverage selection scoring, coverage effect sequencing, coverage
  decision trace payload schema, branch order, reason string, threshold, reset
  timing, public config behavior, pre-dig-align internals, cell-entry
  compatibility, 5P transition semantics, return handoff internals, or low-level
  ACT dispatch behavior was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `1efd88ee99e69907d87410fa96a624095f8ca90f`, no fetch, pull, push, reset,
  checkout, or rebase. The worktree was clean before edits.
- Added `testbed/planner/primitive_coverage_exemplars.py` with
  `CoverageStateExemplarPlannerConfig`, `CoverageStateExemplarPlanInputs`,
  `CoverageStateExemplarPlanResult`, and `CoverageStateExemplarPlanner`. The
  planner owns exemplar JSON loading/validation, path resolution relative to the
  dig-cut prior, removed-depth grid projection, exemplar distance computation,
  temperature weighting with the old uniform fallback for non-finite/degenerate
  weights, rejected-exemplar filtering, weighted dig-cut raw-field assembly,
  weighted dig-depth-profile token assembly, and pure state-conditioned plan
  selection.
- Updated `PrimitivePlannerACTPolicy` so `_load_coverage_state_exemplars()`,
  `_coverage_removed_depth_grid()`,
  `_coverage_state_exemplar_distance_for_grid()`, `_state_exemplar_weights()`,
  `_weighted_state_exemplar_raw_fields()`, and
  `_weighted_state_exemplar_profile_token()` are service-backed compatibility
  facades. `_coverage_state_conditioned_plan(...)` now calls the planner for the
  pure plan and remains responsible only for `update_state=True` writeback into
  `CoverageRuntimeState` and active `CoverageCorridorState` debug fields.
- Added `tests/test_primitive_coverage_exemplars.py` with focused coverage for
  disabled/no-plan behavior, load/validation errors, removed-depth grid length
  and finite/clipping behavior, exemplar distance/weight fallback,
  rejected-exemplar filtering including empty-string ids, weighted raw/profile
  token dtype and copy semantics, and policy facade writeback behavior.
- TDD red result: the first focused run failed at collection because
  `testbed.planner.primitive_coverage_exemplars` did not exist. After adding the
  service and policy facades, `python -m pytest -q
  tests/test_primitive_coverage_exemplars.py` returned `6 passed`.
- Verification:
  `python -m pytest -q tests/test_primitive_coverage_exemplars.py` returned
  `6 passed`;
  `python -m pytest -q tests/test_primitive_coverage_state.py tests/test_primitive_coverage_selection_runtime.py tests/test_primitive_coverage_selection.py tests/test_primitive_coverage_candidates.py`
  returned `16 passed`;
  `python -m pytest -q tests/test_primitive_dig_depth_profile_token_planner.py tests/test_primitive_token_status.py`
  returned `7 passed`;
  `python -m pytest -q tests/test_primitive_coverage_effect_runtime.py tests/test_primitive_coverage_updates.py tests/test_primitive_coverage_runtime.py tests/test_primitive_coverage_reports.py tests/test_primitive_coverage_status.py`
  returned `19 passed`;
  `python -m pytest -q tests/test_primitive_effects.py tests/test_primitive_decision_contract.py tests/test_primitive_backend.py`
  returned `93 passed`;
  `python -m pytest -q tests/test_primitive_planner_trace.py tests/test_primitive_rollout_summary.py tests/test_primitive_debug_report.py tests/test_primitive_tick_finalization.py`
  returned `19 passed`;
  `python -m pytest -q tests/test_planner_current_code_parity.py` returned
  `3 passed`;
  `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
  returned `5 passed`;
  `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "state_conditioned_exemplar or dig_depth_profile or coverage_decision_trace or operator_prior_coverage or first_dig or return_to_dig"`
  returned `13 passed, 107 deselected`;
  compileall and both planner guard commands completed successfully with no
  output.
- Old code parked/reclassified: coverage candidate construction remains in
  `CoverageCandidateBuilder`, coverage scoring remains in
  `CoverageSelectionService`, coverage runtime state remains in
  `CoverageRuntimeState`, coverage selection sequencing remains in
  `CoverageSelectionRuntimeCoordinator`, coverage effect sequencing remains in
  `CoverageEffectRuntimeCoordinator`, first-dig/raw observation facts remain
  policy facades, corridor debug/report payload projection remains behind
  `CoverageReportService`, requested-effect dispatch remains in
  `RequestedEffectApplier`, public report builders remain unchanged,
  `cell_entry` remains compatibility/report material, `pre_dig_align` remains
  residual parking/action material, `LegacyFSMBackendAdapter` remains
  historical/test scaffolding, and 5P remains its existing legacy override path.

### 2026-06-22 Phase 9.24 Extract Primitive Execution Driver

- Scope: extracted the public primitive tick execution route from the free
  `run_primitive_tick()` function and policy-owned hook assembly into a focused
  `PrimitiveExecutionDriver`. No tick ordering, requested-effect application
  timing, decision branch, requested-effect family, branch order, reason string,
  threshold, policy reset timing, token/debug/summary/trace schema, coverage
  trace payload schema, public config behavior, pre-dig-align internals,
  cell-entry compatibility, 5P transition semantics, return handoff internals,
  or low-level ACT dispatch output contract was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `7490563ce08b2b8d138687497845658e9f09152a`, no fetch, pull, push, reset,
  checkout, or rebase. The worktree was clean before edits.
- Added `PrimitiveExecutionPorts` and `PrimitiveExecutionDriver` to
  `testbed/planner/primitive_execution.py`. The driver owns the tick/predict
  route: boundary event update, switch-reason reset, dig-progress update for
  ticks that start in `dig`, decision backend invocation, requested-effect
  validation/application after decision and before return-timeout accounting,
  action dispatch, previous-action recording, transition-completed check, and
  debug finalization. This is the execution-kernel ordering boundary, not a
  pass-through wrapper around policy private methods.
- Reclassified `run_primitive_tick()` as a compatibility facade over
  `PrimitiveExecutionDriver.from_hooks(...).run_tick(...)`, and kept
  `PrimitiveTickCallbacks` as the compatibility callable bundle. Existing tests
  and diagnostics can still use the function entry, but it is no longer the
  source of truth for ordering.
- Updated `PrimitivePlannerACTPolicy` so `_execution_driver_ports()` builds the
  typed driver ports and `_execution_driver()` constructs the driver.
  `_tick_execution_hooks()` remains a compatibility facade over the same port
  wiring. Public `predict(obs)` now delegates directly to
  `self._execution_driver().predict(obs)`.
- Added `tests/test_primitive_execution_driver.py` with focused coverage for
  full driver tick ordering, dig-progress gating, requested-effect application
  timing, `predict()` action extraction, `run_primitive_tick()` compatibility
  delegation, and policy `predict()` delegation.
- TDD red result: the first focused run failed at collection because
  `PrimitiveExecutionDriver` did not exist in
  `testbed.planner.primitive_execution`. After adding the driver and policy
  bridge, `python -m pytest -q tests/test_primitive_execution_driver.py`
  returned `6 passed`.
- Verification:
  `python -m pytest -q tests/test_primitive_execution_driver.py tests/test_primitive_execution_template.py`
  returned `12 passed`;
  `python -m pytest -q tests/test_primitive_action_dispatch.py tests/test_primitive_tick_finalization.py`
  returned `20 passed`;
  `python -m pytest -q tests/test_primitive_effects.py tests/test_primitive_decision_contract.py tests/test_primitive_backend.py`
  returned `93 passed`;
  `python -m pytest -q tests/test_primitive_coverage_exemplars.py tests/test_primitive_coverage_state.py tests/test_primitive_coverage_selection_runtime.py tests/test_primitive_coverage_effect_runtime.py`
  returned `29 passed`;
  `python -m pytest -q tests/test_primitive_planner_trace.py tests/test_primitive_rollout_summary.py tests/test_primitive_debug_report.py tests/test_primitive_observation.py tests/test_primitive_token_status.py`
  returned `17 passed`;
  `python -m pytest -q tests/test_planner_current_code_parity.py` returned
  `3 passed`;
  `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
  returned `5 passed`;
  `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "semantic_boundary_events_drive_skill_sequence or scripted_bootstrap or pre_dig_align or first_dig_policy_for_cycle_zero or return_to_dig or coverage_decision_trace"`
  returned `19 passed, 101 deselected`;
  compileall completed successfully with no output; both planner guard commands
  and `git diff --check` completed successfully with no output.
- Old code parked/reclassified: `run_primitive_tick()` remains a compatibility
  facade, `PrimitiveTickCallbacks` remains compatibility hook material,
  `_tick_execution_hooks()` remains a policy compatibility wrapper, decision
  backends remain in `primitive_backend.py`, requested-effect dispatch remains
  in `RequestedEffectApplier`, action dispatch remains in
  `PrimitiveActionDispatchService`, tick finalization remains in
  `PrimitiveTickFinalizationService`, public report builders remain unchanged,
  `cell_entry` remains compatibility/report material, `pre_dig_align` remains
  residual parking/action material, `LegacyFSMBackendAdapter` remains
  historical/test scaffolding, and 5P remains its existing legacy override path.

### 2026-06-22 Phase 9.25 Extract Primitive Decision Runtime

- Scope: extracted primitive decision backend selection from the policy's
  legacy-named bridge into a focused `PrimitiveDecisionRuntime`. No decision
  branch, requested-effect family, branch order, reason string, threshold,
  policy reset timing, token/debug/summary/trace schema, coverage trace payload
  schema, public config behavior, pre-dig-align internals, cell-entry
  compatibility, 5P transition semantics, return handoff internals, or
  low-level ACT dispatch output contract was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `75d323e9dba8932a3a56906eac0803ddf683eb51`, no fetch, pull, push, reset,
  checkout, or rebase. The worktree was clean before edits.
- Added `testbed/planner/primitive_decision_runtime.py` with
  `LEGACY_FSM_DECISION_BACKEND_NAME`, `PrimitiveDecisionRuntimeConfig`,
  `PrimitiveDecisionRuntimePorts`, and `PrimitiveDecisionRuntime`. The runtime
  owns backend-name normalization, supported-backend validation, default
  `legacy_fsm` requested decision routing, legacy compatibility decision
  routing, and explicit fail-fast for unsupported backend names. Unsupported
  backends do not construct legacy branches and do not fall back to
  `LegacyFSMBackendAdapter` or broad `_maybe_switch_skill()` mutation.
- Updated `PrimitivePlannerACTPolicy` so `_execution_driver_ports().decide_tick`
  points at generic `_decide_tick()`, which delegates to
  `PrimitiveDecisionRuntime`. `_maybe_switch_skill()` now uses the runtime's
  legacy compatibility decision path. `_legacy_fsm_requested_decision_backend()`,
  `_legacy_fsm_compatibility_decision_backend()`, and `_legacy_fsm_branch_set()`
  remain compatibility/debug facades over the same runtime source.
- Added `tests/test_primitive_decision_runtime.py` with focused coverage for
  default `legacy_fsm` requested routing, compatibility order
  `bootstrap -> residual -> dig -> carry -> dump -> return`, compatibility miss
  returning `None`, unsupported backend fail-fast without branch construction,
  policy execution-driver wiring through generic `_decide_tick()`, and legacy
  wrapper delegation through the same runtime.
- TDD red result: the first focused run failed at collection because
  `testbed.planner.primitive_decision_runtime` did not exist. After adding the
  runtime and policy bridge, `python -m pytest -q
  tests/test_primitive_decision_runtime.py` returned `7 passed`.
- Verification:
  `python -m pytest -q tests/test_primitive_decision_runtime.py` returned
  `7 passed`;
  `python -m pytest -q tests/test_primitive_execution_driver.py tests/test_primitive_execution_template.py`
  returned `12 passed`;
  `python -m pytest -q tests/test_primitive_backend.py tests/test_primitive_decision_contract.py tests/test_primitive_effects.py`
  returned `93 passed`;
  `python -m pytest -q tests/test_primitive_action_dispatch.py tests/test_primitive_tick_finalization.py`
  returned `20 passed`;
  `python -m pytest -q tests/test_primitive_coverage_exemplars.py tests/test_primitive_coverage_state.py tests/test_primitive_coverage_selection_runtime.py tests/test_primitive_coverage_effect_runtime.py`
  returned `29 passed`;
  `python -m pytest -q tests/test_primitive_planner_trace.py tests/test_primitive_rollout_summary.py tests/test_primitive_debug_report.py tests/test_primitive_observation.py tests/test_primitive_token_status.py`
  returned `17 passed`;
  `python -m pytest -q tests/test_planner_current_code_parity.py` returned
  `3 passed`;
  `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
  returned `5 passed`;
  `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "semantic_boundary_events_drive_skill_sequence or scripted_bootstrap or pre_dig_align or first_dig_policy_for_cycle_zero or return_to_dig or coverage_decision_trace"`
  returned `19 passed, 101 deselected`;
  compileall completed successfully with no output; both planner guard commands
  and `git diff --check` completed successfully with no output.
- Old code parked/reclassified: `LegacyFSMBranchSet` remains the branch-set
  owner for the only supported backend, `LegacyFSMRequestedDecisionBackend` and
  `LegacyFSMCompatibilityDecisionBackend` remain backend objects constructed by
  the runtime, `LegacyFSMBackendAdapter` remains historical/test scaffolding,
  `run_primitive_tick()` remains a compatibility facade over
  `PrimitiveExecutionDriver`, `cell_entry` remains compatibility/report
  material, `pre_dig_align` remains residual parking/action material, behavior
  tree and VLM/LLM backends remain unsupported parked scope, and 5P remains its
  existing legacy override path.

### 2026-06-22 Phase 9.26 Introduce Primitive Decision Context Packet

- Scope: introduced a shared read-only primitive decision context packet and
  migrated the runtime, legacy FSM backends, branch runner, and legacy FSM
  branches to consume that packet internally. No decision branch,
  requested-effect family, branch order, reason string, threshold, policy reset
  timing, token/debug/summary/trace schema, coverage trace payload schema,
  public config behavior, pre-dig-align internals, cell-entry compatibility, 5P
  transition semantics, return handoff internals, or low-level ACT dispatch
  output contract was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `5615ebe1c69be44784c2f853174963bd5e28f6c7`, no fetch, pull, push, reset,
  checkout, or rebase. The worktree was clean before edits.
- Added `testbed/planner/primitive_decision_context.py` with
  `PrimitiveDecisionContext`. The packet preserves tick `obs`,
  `boundary_event`, and `PrimitiveTickPreparation` identities and exposes
  convenience fields for `skill_name_before_decision` and
  `dig_progress_updated`.
- Updated `PrimitiveDecisionRuntime` so scatter-argument `decide_tick(...)` and
  `decide_legacy_compatibility_tick(...)` immediately construct a
  `PrimitiveDecisionContext` and delegate to context-based source-of-truth
  methods. Unsupported backend fail-fast behavior remains unchanged and still
  avoids legacy branch construction or broad fallback.
- Updated `PrimitiveDecisionBackend`, `PrimitiveDecisionBranch`,
  `PrimitiveRequestedBranchRunner`, `LegacyFSMRequestedDecisionBackend`,
  `LegacyFSMCompatibilityDecisionBackend`, and the legacy FSM branch objects to
  use `decide_context(...)` internally. Existing `decide_tick(...)` methods
  remain thin compatibility facades for execution-driver ports, direct tests,
  and diagnostics.
- Added `tests/test_primitive_decision_context.py` and updated backend/runtime
  focused tests to prove context identity preservation, one-context routing
  through requested order `bootstrap -> dig -> carry -> dump -> return ->
  residual`, one-context routing through compatibility order
  `bootstrap -> residual -> dig -> carry -> dump -> return`, and policy/runtime
  behavior through the existing scatter-argument facade.
- TDD red result: the first focused run failed at collection because
  `testbed.planner.primitive_decision_context` did not exist. After adding the
  context packet and migrating runtime/backend/branch paths, the focused
  context/runtime/backend subset returned `4 passed, 55 deselected`, and the
  full context/runtime/backend/decision/effect suite returned `104 passed`.
- Verification:
  `python -m pytest -q tests/test_primitive_decision_context.py tests/test_primitive_decision_runtime.py`
  returned `9 passed`;
  `python -m pytest -q tests/test_primitive_backend.py tests/test_primitive_decision_contract.py tests/test_primitive_effects.py`
  returned `95 passed`;
  `python -m pytest -q tests/test_primitive_execution_driver.py tests/test_primitive_execution_template.py`
  returned `12 passed`;
  `python -m pytest -q tests/test_primitive_action_dispatch.py tests/test_primitive_tick_finalization.py`
  returned `20 passed`;
  `python -m pytest -q tests/test_primitive_coverage_exemplars.py tests/test_primitive_coverage_state.py tests/test_primitive_coverage_selection_runtime.py tests/test_primitive_coverage_effect_runtime.py`
  returned `29 passed`;
  `python -m pytest -q tests/test_primitive_planner_trace.py tests/test_primitive_rollout_summary.py tests/test_primitive_debug_report.py tests/test_primitive_observation.py tests/test_primitive_token_status.py`
  returned `17 passed`;
  `python -m pytest -q tests/test_planner_current_code_parity.py` returned
  `3 passed`;
  `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
  returned `5 passed`;
  `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "semantic_boundary_events_drive_skill_sequence or scripted_bootstrap or pre_dig_align or first_dig_policy_for_cycle_zero or return_to_dig or coverage_decision_trace"`
  returned `19 passed, 101 deselected`;
  compileall completed successfully with no output; both planner guard commands
  and `git diff --check` completed successfully with no output.
- Old code parked/reclassified: scatter-argument `decide_tick(...)` methods
  remain compatibility facades over `PrimitiveDecisionContext`, execution-driver
  ports still call the policy's `_decide_tick(...)` facade, `LegacyFSMBranchSet`
  remains the only supported backend branch-set owner, `LegacyFSMBackendAdapter`
  remains historical/test scaffolding, `cell_entry` remains
  compatibility/report material, `pre_dig_align` remains residual
  parking/action material, behavior tree and VLM/LLM backends remain
  unsupported parked scope, and 5P remains its existing legacy override path.

### 2026-06-22 Phase 9.27 Introduce Primitive Decision Capabilities Port

- Scope: introduced a backend-facing primitive decision capabilities object and
  migrated legacy FSM branch construction so mainline branches consume
  `PrimitiveDecisionContext + PrimitiveDecisionCapabilities` instead of direct
  shell callback/status-provider fields. No branch order, reason string,
  threshold, policy reset timing, token/debug/summary/trace schema, coverage
  trace payload schema, public config behavior, pre-dig-align internals,
  cell-entry compatibility, 5P transition semantics, return handoff internals,
  or low-level ACT dispatch output contract was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `357e84505e98ad9fb7f1e735fb19dc4d2488061e`, no fetch, pull, push, reset,
  checkout, or rebase. The worktree was clean before edits.
- Added `testbed/planner/primitive_decision_capabilities.py` with
  `PrimitiveDecisionCapabilitiesPorts`, `PrimitiveDecisionCapabilities`,
  `PrimitiveTransitionStatusProvider`, and `BootstrapDecisionStatus`. The
  capabilities object maps a shared `PrimitiveDecisionContext` into current
  skill/reason, normalized bootstrap status, dig/carry/dump/return transition
  statuses from `PrimitiveFSMCapabilityProvider`, and the explicitly residual
  pre-dig-align already-applied compatibility handler.
- Updated `LegacyFSMBranchPorts` so it carries only skill-name constants and a
  `PrimitiveDecisionCapabilities` object. `LegacyFSMBootstrapBranch`,
  `LegacyFSMDigBranch`, `LegacyFSMCarryBranch`, `LegacyFSMDumpBranch`,
  `LegacyFSMReturnBranch`, and the residual pre-dig-align adapter now read
  backend facts through capabilities and the shared context. The default
  requested order remains `bootstrap -> dig -> carry -> dump -> return ->
  residual`, and compatibility order remains `bootstrap -> residual -> dig ->
  carry -> dump -> return`.
- Updated `PrimitivePlannerACTPolicy` with
  `_primitive_decision_capabilities()` and
  `_primitive_decision_capabilities_ports()` thin wiring. The policy still owns
  shell readers, bootstrap gates, provider construction, and the residual
  pre-dig handler, while backend branches no longer receive the mainline
  callback bag directly.
- Added `tests/test_primitive_decision_capabilities.py` and updated backend and
  decision-contract tests to prove context-driven status-provider calls,
  bootstrap next-skill normalization, explicit residual compatibility handling,
  `LegacyFSMBranchPorts` shrinkage, policy capabilities wiring, requested and
  compatibility order preservation, and unsupported-backend fail-fast behavior.
- TDD red result: the first focused run failed at collection with
  `ModuleNotFoundError: No module named
  'testbed.planner.primitive_decision_capabilities'`. After adding the
  capabilities module, the focused capabilities test returned `3 passed`, and
  after backend/policy migration the combined capabilities/backend suite
  returned `53 passed`.
- Verification:
  `python -m pytest -q tests/test_primitive_decision_capabilities.py tests/test_primitive_decision_context.py tests/test_primitive_decision_runtime.py`
  returned `12 passed`;
  `python -m pytest -q tests/test_primitive_backend.py tests/test_primitive_decision_contract.py tests/test_primitive_effects.py`
  returned `95 passed`;
  `python -m pytest -q tests/test_primitive_capability_provider.py tests/test_primitive_capabilities.py`
  returned `29 passed`;
  `python -m pytest -q tests/test_primitive_execution_driver.py tests/test_primitive_execution_template.py`
  returned `12 passed`;
  `python -m pytest -q tests/test_primitive_action_dispatch.py tests/test_primitive_tick_finalization.py`
  returned `20 passed`;
  `python -m pytest -q tests/test_primitive_coverage_exemplars.py tests/test_primitive_coverage_state.py tests/test_primitive_coverage_selection_runtime.py tests/test_primitive_coverage_effect_runtime.py`
  returned `29 passed`;
  `python -m pytest -q tests/test_primitive_planner_trace.py tests/test_primitive_rollout_summary.py tests/test_primitive_debug_report.py tests/test_primitive_observation.py tests/test_primitive_token_status.py`
  returned `17 passed`;
  `python -m pytest -q tests/test_planner_current_code_parity.py` returned
  `3 passed`;
  `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
  returned `5 passed`;
  `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "semantic_boundary_events_drive_skill_sequence or scripted_bootstrap or pre_dig_align or first_dig_policy_for_cycle_zero or return_to_dig or coverage_decision_trace"`
  returned `19 passed, 101 deselected`;
  compileall completed successfully with no output; both planner guard commands
  and `git diff --check` completed successfully with no output.
- Old code parked/reclassified: `PrimitiveDecisionCapabilities` is a
  backend-facing legacy-FSM capability boundary, not proof of pure
  alternate-backend readiness. The default backend remains the only supported
  `legacy_fsm`; behavior tree and VLM/LLM backends remain unsupported parked
  scope, `LegacyFSMBackendAdapter` remains historical/test scaffolding,
  `cell_entry` remains compatibility/report material, `pre_dig_align` remains
  residual parking/action material, and 5P remains its existing legacy override
  path.

### 2026-06-22 Phase 9.28 Extract Primitive Skill Lifecycle Service

- Scope: extracted the 4P primitive skill switch lifecycle sequencing from
  `PrimitivePlannerACTPolicy._set_skill(...)` into
  `PrimitiveSkillLifecycleService` with typed
  `PrimitiveSkillLifecyclePorts`. No branch order, reason string, threshold,
  token/debug/summary/trace schema, coverage trace payload schema, policy reset
  timing, public config behavior, requested-effect classes, decision branches,
  pre-dig-align internals, cell-entry compatibility, 5P transition semantics,
  behavior-tree/VLM/LLM unsupported status, or low-level ACT dispatch output
  contract was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `e61669a4511cca1d87ae245cdaed90fe5576b48f`, no fetch, pull, push, reset,
  checkout, or rebase. The worktree was clean before edits.
- Added `testbed/planner/primitive_skill_lifecycle.py` with
  `PrimitiveSkillLifecyclePorts` and `PrimitiveSkillLifecycleService`. The
  service owns the old 4P `_set_skill(...)` order: same-skill no-op,
  skill/reason writes, active-policy reset except for residual
  `pre_dig_align`, target-specific counter/mirror resets, dig coverage payload
  reset, and dig-cut plan clear timing.
- Updated `PrimitivePlannerACTPolicy` with
  `_primitive_skill_lifecycle_ports()` and
  `_primitive_skill_lifecycle()` thin wiring. `_set_skill(...)` is now a
  service-backed facade, and `RequestedEffectApplier` continues to use the same
  existing `set_skill` port. The 5P `_set_skill()` override remains parked
  compatibility and was not migrated.
- Added `tests/test_primitive_skill_lifecycle.py` to lock same-skill no-op,
  switch-to-dig lifecycle resets without dig-cut clear, carry/dump/return
  counter resets plus dig-cut clear, the `pre_dig_align` no-reset/no-clear
  exception, typed-port boundary shape, and policy wrapper delegation.
- TDD red result: the first focused run failed at collection with
  `ModuleNotFoundError: No module named
  'testbed.planner.primitive_skill_lifecycle'`. After adding the service
  module, the focused test exposed the still-inline policy wrapper with
  `AttributeError: 'PrimitivePlannerACTPolicy' object has no attribute
  '_skill_name'`; after wiring policy delegation, the focused lifecycle suite
  returned `6 passed`.
- Verification:
  `python -m pytest -q tests/test_primitive_skill_lifecycle.py` returned
  `6 passed`;
  `python -m pytest -q tests/test_primitive_effects.py tests/test_primitive_decision_contract.py tests/test_primitive_backend.py`
  returned `95 passed`;
  `python -m pytest -q tests/test_primitive_execution_driver.py tests/test_primitive_execution_template.py`
  returned `12 passed`;
  `python -m pytest -q tests/test_primitive_action_dispatch.py tests/test_primitive_tick_finalization.py`
  returned `20 passed`;
  `python -m pytest -q tests/test_primitive_decision_capabilities.py tests/test_primitive_decision_context.py tests/test_primitive_decision_runtime.py`
  returned `12 passed`;
  `python -m pytest -q tests/test_planner_current_code_parity.py` returned
  `3 passed`;
  `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
  returned `5 passed`;
  `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "semantic_boundary_events_drive_skill_sequence or scripted_bootstrap or pre_dig_align or first_dig_policy_for_cycle_zero or return_to_dig or coverage_decision_trace"`
  returned `19 passed, 101 deselected`;
  compileall completed successfully with no output; both planner guard commands
  completed successfully with no output.
- Old code parked/reclassified: 5P keeps its existing `_set_skill()` override
  and transition semantics; `pre_dig_align` remains residual parking/action
  material; `cell_entry` remains compatibility/report material; behavior tree,
  VLM, and LLM backends remain unsupported parked scope.

### 2026-06-22 Phase 9.29 Extract Primitive Token Runtime Coordinator

- Scope: extracted confirmed-live 4P dig/return token runtime lifecycle
  sequencing from `PrimitivePlannerACTPolicy` into
  `PrimitiveTokenRuntimeCoordinator` with typed `PrimitiveTokenRuntimePorts`.
  No token key, dimension, contract version, source/fallback string,
  in-prior flag, copy semantics, injected flag behavior, branch order, reason
  string, threshold, policy reset timing, public config behavior, coverage trace
  payload schema, return handoff behavior, cell-entry compatibility,
  pre-dig-align residual behavior, 5P token behavior, behavior-tree/VLM/LLM
  unsupported status, or low-level ACT dispatch output contract was
  intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `efced56b1bfb1de82bd0414155a8dad4ceb6da9f`, no fetch, pull, push, reset,
  checkout, or rebase. The worktree was clean before edits.
- Added `testbed/planner/primitive_token_runtime.py` with
  `PrimitiveTokenRuntimePorts` and `PrimitiveTokenRuntimeCoordinator`. The
  coordinator owns token runtime sequencing rather than token algorithms:
  dig-cut disabled/no-token gates, terminal-stop cached-token behavior,
  active-skill and bootstrap-policy eligibility, hold-cycle rebuild
  suppression, synchronized dig-cut and dig-depth-profile writes, return-target
  eligibility and hold-cycle suppression, return relocate writes,
  return-start-envelope routing, return-target success/fallback writeback,
  pending next-dig plan writeback, and exact dig-cut/pending-plan reset
  behavior.
- Updated `PrimitivePlannerACTPolicy` with `_primitive_token_runtime_ports()`
  and `_primitive_token_runtime()` thin wiring. The old private methods
  `_dig_cut_tokens_for_obs(...)`, `_dig_depth_profile_tokens_for_obs(...)`,
  `_ensure_dig_cut_plan_for_cycle(...)`, `_return_target_tokens_for_obs(...)`,
  `_return_relocate_tokens_for_obs(...)`,
  `_return_start_envelope_tokens_for_obs(...)`,
  `_ensure_return_target_plan_for_cycle(...)`, `_clear_dig_cut_plan()`, and
  `_invalidate_pending_dig_cut_plan()` are now service-backed compatibility
  facades.
- Added `tests/test_primitive_token_runtime.py` to lock disabled/terminal-stop/
  active-skill gates, bootstrap-policy token exception, dig hold-cycle
  behavior, return eligibility and hold-cycle behavior, return relocate copy
  behavior, return-target success and fallback writeback, clear/invalidate exact
  reset fields, typed-port boundary shape, and policy facade delegation.
- TDD red result: the first focused run failed at collection with
  `ModuleNotFoundError: No module named
  'testbed.planner.primitive_token_runtime'`. After adding the coordinator, the
  focused tests exposed a terminal-stop rebuild bug and the still-inline policy
  token facades; after fixing the terminal-stop cached-token path and wiring
  policy delegation, the focused token runtime suite returned `11 passed`.
- Verification:
  `python -m pytest -q tests/test_primitive_token_runtime.py` returned
  `11 passed`;
  `python -m pytest -q tests/test_primitive_observation.py tests/test_primitive_token_status.py`
  returned `8 passed`;
  `python -m pytest -q tests/test_primitive_goal_token_provider.py tests/test_primitive_dig_cut_token_planner.py tests/test_primitive_dig_depth_profile_token_planner.py tests/test_primitive_return_target_token_planner.py tests/test_primitive_return_relocate_token_planner.py tests/test_primitive_return_start_envelope_token_planner.py`
  returned `20 passed`;
  `python -m pytest -q tests/test_primitive_skill_lifecycle.py tests/test_primitive_effects.py tests/test_primitive_decision_contract.py tests/test_primitive_backend.py`
  returned `101 passed`;
  `python -m pytest -q tests/test_primitive_execution_driver.py tests/test_primitive_execution_template.py`
  returned `12 passed`;
  `python -m pytest -q tests/test_primitive_return_handoff.py tests/test_primitive_coverage_exemplars.py tests/test_primitive_coverage_state.py tests/test_primitive_coverage_selection_runtime.py tests/test_primitive_coverage_effect_runtime.py`
  returned `44 passed`;
  `python -m pytest -q tests/test_planner_current_code_parity.py` returned
  `3 passed`;
  `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
  returned `5 passed`;
  `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "dig_depth_profile or dig_cut_tokens or return_to_dig or start_envelope or semantic_boundary_events_drive_skill_sequence or coverage_decision_trace"`
  returned `8 passed, 112 deselected`;
  compileall completed successfully with no output; both planner guard commands
  and `git diff --check` completed successfully with no output.
- Old code parked/reclassified: token planner algorithms remain in
  `DigCutTokenPlanner`, `DigDepthProfileTokenPlanner`,
  `ReturnTargetTokenPlanner`, `ReturnRelocateTokenPlanner`, and
  `ReturnStartEnvelopeTokenPlanner`; observation injected-key assembly remains
  in `PrimitivePolicyObservationAssembler`; coverage selection/scoring,
  coverage state-exemplar planning, return start-envelope gate evaluation,
  return direct-handoff effect sequencing, action dispatch, decision branches,
  and requested-effect classes remain in their existing owners; `cell_entry`
  remains compatibility/report material; `pre_dig_align` remains residual
  parking/action material; 5P remains its existing legacy token/transition
  behavior; behavior tree, VLM, and LLM backends remain unsupported parked
  scope.

### 2026-06-22 Phase 9.30 Extract Primitive Return Token Planning Service

- Scope: extracted confirmed-live 4P return token planning orchestration from
  `PrimitivePlannerACTPolicy` into
  `PrimitiveReturnTokenPlanningService` with typed
  `PrimitiveReturnTokenPlanningPorts`. No token dimension, key/schema,
  contract version, source/fallback string, prior-bound flag, copy semantics,
  observation injection order, branch order, reason string, threshold, policy
  reset timing, public config behavior, coverage trace payload schema, return
  handoff behavior, cell-entry compatibility, pre-dig-align residual behavior,
  5P token behavior, behavior-tree/VLM/LLM unsupported status, or low-level ACT
  dispatch output contract was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `7c3de79e7bf649bf718c85643da3f5aa372ec06a`, no fetch, pull, push, reset,
  checkout, or rebase. The worktree was clean before edits.
- Added `testbed/planner/primitive_return_token_planning.py` with
  `PrimitiveReturnTokenPlanningPorts` and
  `PrimitiveReturnTokenPlanningService`. The service owns return-target mode
  routing for `conservative_pose`, `operator_prior`,
  `operator_prior_coverage`, and `operator_prior_sweep_belief`; coverage
  corridor selection and active-corridor writeback; coverage raw-field planning
  with `update_state=True`; return-start-envelope token build/apply/
  conditioning; source and prior-bound flag writeback; prior token/mapping/
  bounds helper routing; corridor-id to cell-id fallback; unsupported-mode
  fail-fast; and token/raw-field copy semantics.
- Updated `PrimitivePlannerACTPolicy` with
  `_primitive_return_token_planning_ports()` and
  `_primitive_return_token_planning_service()` thin wiring. The old private
  methods `_build_next_dig_cut_plan_for_return(...)`,
  `_unpack_return_target_token_plan(...)`,
  `_build_return_start_envelope_tokens_for_obs(...)`,
  `_apply_return_start_envelope_token_plan(...)`,
  `_maybe_condition_return_start_envelope_qpos_from_relocate(...)`,
  `_return_start_envelope_prior_token(...)`,
  `_return_start_envelope_prior_mapping(...)`,
  `_return_start_envelope_prior_bounds(...)`,
  `_return_start_envelope_cell_id(...)`, and
  `_return_start_envelope_token_from_prior_mapping(...)` are now
  service-backed compatibility facades.
- Updated `PrimitiveTokenRuntimePorts.build_return_start_envelope_tokens_for_obs`
  to use the explicit `ReturnStartEnvelopeTokenBuilder` protocol so the
  existing kw-only `corridor_id` call shape is represented in the typed
  runtime interface.
- TDD red result: the first focused run failed at collection with
  `ModuleNotFoundError: No module named
  'testbed.planner.primitive_return_token_planning'`. After adding the service
  module and policy wiring, the focused return token planning suite returned
  `8 passed`.
- Verification:
  `python -m pytest -q tests/test_primitive_return_token_planning.py` returned
  `8 passed`;
  `python -m pytest -q tests/test_primitive_token_runtime.py tests/test_primitive_return_target_token_planner.py tests/test_primitive_return_start_envelope_token_planner.py tests/test_primitive_return_relocate_token_planner.py`
  returned `18 passed`;
  `python -m pytest -q tests/test_primitive_observation.py tests/test_primitive_token_status.py`
  returned `8 passed`;
  `python -m pytest -q tests/test_primitive_goal_token_provider.py tests/test_primitive_dig_cut_token_planner.py tests/test_primitive_dig_depth_profile_token_planner.py`
  returned `13 passed`;
  `python -m pytest -q tests/test_primitive_return_handoff.py tests/test_primitive_coverage_exemplars.py tests/test_primitive_coverage_state.py tests/test_primitive_coverage_selection_runtime.py tests/test_primitive_coverage_effect_runtime.py`
  returned `44 passed`;
  `python -m pytest -q tests/test_primitive_skill_lifecycle.py tests/test_primitive_effects.py tests/test_primitive_decision_contract.py tests/test_primitive_backend.py`
  returned `101 passed`;
  `python -m pytest -q tests/test_primitive_execution_driver.py tests/test_primitive_execution_template.py`
  returned `12 passed`;
  `python -m pytest -q tests/test_planner_current_code_parity.py` returned
  `3 passed`;
  `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
  returned `5 passed`;
  `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "return_to_dig or start_envelope or dig_depth_profile or dig_cut_tokens or semantic_boundary_events_drive_skill_sequence or coverage_decision_trace"`
  returned `8 passed, 112 deselected`;
  compileall completed successfully with no output; both planner guard commands
  and `git diff --check` completed successfully with no output.
- Old code parked/reclassified: active dig token planning remains in the
  existing dig token policy facades and token planner classes; token algorithms
  remain in `DigCutTokenPlanner`, `DigDepthProfileTokenPlanner`,
  `ReturnTargetTokenPlanner`, `ReturnRelocateTokenPlanner`, and
  `ReturnStartEnvelopeTokenPlanner`; coverage selection/scoring and
  state-exemplar algorithms remain in their coverage services; return
  start-envelope gate readiness and direct-handoff effect sequencing remain in
  their return handoff services; `cell_entry` remains compatibility/report
  material; `pre_dig_align` remains residual parking/action material; 5P
  remains its existing legacy token/transition behavior; behavior tree, VLM,
  and LLM backends remain unsupported parked scope.

### 2026-06-22 Phase 9.31 Extract Primitive Dig Token Planning Service

- Scope: extracted confirmed-live 4P active dig token planning orchestration
  from `PrimitivePlannerACTPolicy` into
  `PrimitiveDigTokenPlanningService` with typed
  `PrimitiveDigTokenPlanningPorts`. No token dimension, key/schema, contract
  version, source/fallback string, prior-bound flag, copy semantics,
  observation injection order, branch order, reason string, threshold, policy
  reset timing, public config behavior, coverage trace payload schema, return
  handoff behavior, cell-entry compatibility, pre-dig-align residual behavior,
  5P token behavior, behavior-tree/VLM/LLM unsupported status, or low-level ACT
  dispatch output contract was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `caecefd2e47318f57c301bed1b1fe77087d49349`, no fetch, pull, push, reset,
  checkout, or rebase. The worktree was clean before edits.
- Added `testbed/planner/primitive_dig_token_planning.py` with
  `PrimitiveDigTokenPlanningPorts` and `PrimitiveDigTokenPlanningService`.
  The service owns pending return-target dig plan application; conservative,
  operator-prior, operator-prior-coverage, and sweep-belief mode routing;
  fallback conservative behavior; coverage raw-field handoff; active coverage
  corridor/payload/deposit/state-exemplar writeback for pending and coverage
  routes; dig-cut source/fallback/in-prior writeback; dig-depth-profile
  plan/apply/error source and fallback writeback; live/prior helper routing;
  raw-field priority; cell-id priority; unsupported-mode fail-fast; and
  token/raw-field copy semantics.
- Updated `PrimitivePlannerACTPolicy` with
  `_primitive_dig_token_planning_ports()` and
  `_primitive_dig_token_planning_service()` thin wiring. The old private
  methods `_build_dig_cut_tokens_for_obs(...)`,
  `_apply_dig_cut_token_plan(...)`,
  `_build_dig_depth_profile_tokens_for_obs(...)`,
  `_apply_dig_depth_profile_token_plan(...)`,
  `_build_live_dig_depth_profile_tokens_for_obs(...)`,
  `_dig_depth_profile_prior_token(...)`,
  `_dig_depth_profile_prior_mapping(...)`,
  `_dig_depth_profile_token_from_prior_mapping(...)`,
  `_dig_depth_profile_raw_fields(...)`,
  `_dig_depth_profile_cell_id(...)`, `_raw_fields_from_live_pose(...)`,
  `_build_operator_prior_dig_cut_tokens(...)`, and
  `_build_operator_prior_coverage_dig_cut_tokens(...)` are now
  service-backed compatibility facades.
- TDD red result: the first focused run failed at collection with
  `ModuleNotFoundError: No module named
  'testbed.planner.primitive_dig_token_planning'`. After adding the service
  module and policy wiring, the focused dig token planning suite returned
  `11 passed`.
- Verification:
  `python -m pytest -q tests/test_primitive_dig_token_planning.py` returned
  `11 passed`;
  `python -m pytest -q tests/test_primitive_token_runtime.py tests/test_primitive_dig_cut_token_planner.py tests/test_primitive_dig_depth_profile_token_planner.py`
  returned `20 passed`;
  `python -m pytest -q tests/test_primitive_return_token_planning.py tests/test_primitive_return_target_token_planner.py tests/test_primitive_return_start_envelope_token_planner.py tests/test_primitive_return_relocate_token_planner.py`
  returned `15 passed`;
  `python -m pytest -q tests/test_primitive_observation.py tests/test_primitive_token_status.py tests/test_primitive_goal_token_provider.py`
  returned `12 passed`;
  `python -m pytest -q tests/test_primitive_return_handoff.py tests/test_primitive_coverage_exemplars.py tests/test_primitive_coverage_state.py tests/test_primitive_coverage_selection_runtime.py tests/test_primitive_coverage_effect_runtime.py`
  returned `44 passed`;
  `python -m pytest -q tests/test_primitive_skill_lifecycle.py tests/test_primitive_effects.py tests/test_primitive_decision_contract.py tests/test_primitive_backend.py`
  returned `101 passed`;
  `python -m pytest -q tests/test_primitive_execution_driver.py tests/test_primitive_execution_template.py`
  returned `12 passed`;
  `python -m pytest -q tests/test_planner_current_code_parity.py` returned
  `3 passed`;
  `python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
  returned `5 passed`;
  `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "dig_depth_profile or dig_cut_tokens or return_to_dig or start_envelope or semantic_boundary_events_drive_skill_sequence or coverage_decision_trace"`
  returned `8 passed, 112 deselected`;
  compileall completed successfully with no output; both planner guard commands
  and `git diff --check` completed successfully with no output.
- Old code parked/reclassified: return token planning remains in
  `PrimitiveReturnTokenPlanningService`; token runtime sequencing remains in
  `PrimitiveTokenRuntimeCoordinator`; token algorithms remain in
  `DigCutTokenPlanner`, `DigDepthProfileTokenPlanner`,
  `ReturnTargetTokenPlanner`, `ReturnRelocateTokenPlanner`, and
  `ReturnStartEnvelopeTokenPlanner`; coverage selection/scoring and
  state-exemplar algorithms remain in their coverage services; return
  start-envelope gate readiness and direct-handoff effect sequencing remain in
  their return handoff services; `cell_entry` remains compatibility/report
  material; `pre_dig_align` remains residual parking/action material; 5P
  remains its existing legacy token/transition behavior; behavior tree, VLM,
  and LLM backends remain unsupported parked scope.

### 2026-06-22 Phase 9.32 Extract Reset Lifecycle Service And Remove 5P Planner

- Scope: extracted confirmed-live 4P reset lifecycle sequencing from
  `PrimitivePlannerACTPolicy.reset()` into `PrimitiveResetLifecycleService`
  with typed `PrimitiveResetLifecyclePorts` and a reset-state result object.
  Removed the obsolete `PrimitivePlannerACT5PPolicy` runtime subclass and
  updated current runtime/tests/docs to classify 5P runtime behavior as
  cleanup-approved and available only through git history. No 4P branch order,
  reason string, threshold, token/debug/summary/trace schema, policy reset
  timing, public config behavior, coverage trace payload schema, or low-level
  ACT dispatch output contract was intentionally changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `c9cf0f2e1d0638225abfeb882fcfd70d9155467b`; no fetch, pull, push, reset,
  checkout, or rebase. The worktree was clean before edits. HEAD after this
  round is the local commit containing this record and is reported in the final
  handoff because a commit cannot embed its own final hash.
- Added `testbed/planner/primitive_reset_lifecycle.py` with
  `PrimitiveResetLifecyclePorts`, `PrimitiveResetLifecycleState`, and
  `PrimitiveResetLifecycleService`. The service owns old 4P reset ordering for
  low-level policy resets, boundary-detector reset, bootstrap/scripted/
  pre-dig initial-skill selection, switch reason and previous-action defaults,
  hold counters, return/dig/cycle counters, pre-dig cached diagnostics,
  cell-entry compatibility state, dig/return token arrays and injected flags,
  source/fallback strings, pending next-dig plan state, fresh
  `CoverageRuntimeState` creation, and initial debug transition flags.
- Updated `PrimitivePlannerACTPolicy.reset()` to build reset ports, invoke the
  service, apply the returned reset state to policy storage, and initialize the
  compact debug state. The policy shell keeps mutable storage and compatibility
  private names; the reset sequencing source of truth is now the service.
- Removed `PrimitivePlannerACT5PPolicy` and its 5P-specific reset,
  `_maybe_switch_skill`, `_set_skill`, active-policy/all-policy, action-dispatch,
  and tick-finalization runtime overrides. Runtime eval now fail-fasts
  `PRIMITIVE_PLANNER_ACT_5P` with an explicit removed-runtime message. The AGX
  test that directly exercised 5P runtime switching was removed; data slicing
  and historical experiment material were not deleted.
- TDD red result: the first focused run failed at collection with
  `ModuleNotFoundError: No module named
  'testbed.planner.primitive_reset_lifecycle'`. After adding the service module
  and policy wiring, the focused reset lifecycle suite returned `9 passed`.
- Verification:
  `python -m pytest -q tests/test_primitive_reset_lifecycle.py` returned
  `9 passed`;
  `python -m pytest -q tests/test_primitive_execution_driver.py tests/test_primitive_action_dispatch.py tests/test_primitive_tick_finalization.py tests/test_primitive_skill_lifecycle.py`
  returned `32 passed`;
  `python -m pytest -q tests/test_primitive_effects.py tests/test_primitive_decision_contract.py tests/test_primitive_backend.py`
  returned `95 passed`;
  `python -m pytest -q tests/test_primitive_dig_token_planning.py tests/test_primitive_return_token_planning.py tests/test_primitive_token_runtime.py`
  returned `30 passed`;
  `python -m pytest -q tests/test_planner_current_code_parity.py tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
  returned `8 passed`;
  `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "semantic_boundary_events_drive_skill_sequence or scripted_bootstrap or pre_dig_align or first_dig_policy_for_cycle_zero or return_to_dig or coverage_decision_trace or dig_depth_profile or dig_cut_tokens"`
  returned `20 passed, 99 deselected`;
  compileall completed successfully with no output for the touched reset,
  execution, action-dispatch, tick-finalization, skill-lifecycle, policy,
  runtime eval, evidence trace, and reset-test modules; both planner guard
  commands and `git diff --check` completed successfully with no output.
- Structural check:
  `rg -n "PrimitivePlannerACT5PPolicy|PRIMITIVE_SKILL_IDS_5P|approach_dump_policy|dump_release_policy|carry_to_approach_dump|dump_release_to_return" testbed/policies/hybrid/primitive_planner.py testbed/planner tests/test_primitive_* tests/test_agx_primitives_v2_2.py`
  returned no current runtime dependency hits.
- Old code parked/reclassified: `pre_dig_align` remains residual parking/action
  material; `cell_entry` remains compatibility/report material; behavior tree,
  VLM, and LLM backends remain unsupported parked scope; 5P runtime behavior is
  removed from current code by explicit cleanup decision and retained only by
  git history, not as a live compatibility owner.

### 2026-06-22 Phase 9.33A Extract Primitive Public Adapter Config Normalizer

- Scope: extracted public adapter config normalization from
  `PrimitivePlannerACTPolicy.__init__` into
  `testbed/planner/primitive_adapter_config.py`. The policy constructor keeps
  the full public signature and default values, directly stores only low-level
  policy handles plus the boundary detector, builds
  `PrimitivePlannerAdapterConfigInputs`, applies the normalized
  `PrimitivePlannerAdapterConfigState`, and then calls the existing reset
  facade. No 4P branch order, reason string, threshold, policy reset timing,
  token/debug/summary/trace schema, coverage trace schema, public config
  behavior, or low-level ACT dispatch output contract was intentionally
  changed.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `fs/v2_4-refactor-tests`, HEAD before this round
  `02ed2c15d551e00771230aaec311d4e67a628b8f`; no fetch, pull, push, reset,
  checkout, rebase, remote write, or branch creation. HEAD after this round is
  the local commit containing this record and is reported in the final handoff
  because a commit cannot embed its own final hash.
- Added `PrimitivePlannerAdapterConfigInputs`,
  `PrimitivePlannerAdapterConfigState`, and
  `PrimitivePlannerAdapterConfigNormalizer`. The normalizer owns constructor
  config expansion, optional float parsing, action-dimension-aware vector
  parsing, goal-sequence normalization, plane-depth and failed-dig replan
  normalization, dig-cut prior loading, dig-planner validation, cell-entry
  compatibility object construction, coverage/state-exemplar config
  normalization and exemplar loading, pre-dig-align vectors, scripted bootstrap
  vectors, and legacy policy-field update payload assembly.
- Updated old private helper names such as `_normalize_plane_depth_mode`,
  `_normalize_failed_dig_replan_skill`, `_normalize_goal_sequence`,
  `_optional_float`, `_align_vector`, `_optional_align_vector`,
  `_coverage_percentile_list`, `_coverage_percentile_name`,
  `_load_dig_cut_prior`, and `_validate_dig_cut_planner_config` into
  compatibility facades that delegate to the new config module. These helpers
  are no longer source-of-truth logic in the large policy file.
- Explicit non-goals: this was not a kernel factory extraction. Execution
  driver wiring, decision runtime, requested-effect application, reset
  lifecycle, coverage algorithms, token planner algorithms, report builders,
  `pre_dig_align` residual behavior, `cell_entry` compatibility behavior,
  removed 5P runtime status, and behavior-tree/VLM/LLM unsupported status were
  left unchanged.
- TDD red result: the first focused adapter-config test run failed at
  collection with `ImportError: cannot import name 'primitive_adapter_config'
  from 'testbed.planner'` because the module did not exist yet. After adding
  the module and policy wiring, the focused adapter config suite returned
  `13 passed`.
- Verification:
  `python -m pytest -q tests/test_primitive_adapter_config.py` returned
  `13 passed`;
  `python -m pytest -q tests/test_primitive_reset_lifecycle.py tests/test_primitive_execution_driver.py tests/test_primitive_action_dispatch.py`
  returned `25 passed`;
  `python -m pytest -q tests/test_primitive_dig_token_planning.py tests/test_primitive_return_token_planning.py tests/test_primitive_token_runtime.py`
  returned `30 passed`;
  `python -m pytest -q tests/test_primitive_coverage_exemplars.py tests/test_primitive_coverage_selection_runtime.py tests/test_primitive_coverage_effect_runtime.py`
  returned `23 passed`;
  `python -m pytest -q tests/test_planner_current_code_parity.py tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py`
  returned `8 passed`;
  `python -m pytest -q tests/test_agx_primitives_v2_2.py -k "semantic_boundary_events_drive_skill_sequence or scripted_bootstrap or pre_dig_align or first_dig_policy_for_cycle_zero or return_to_dig or coverage_decision_trace or dig_depth_profile or dig_cut_tokens"`
  returned `20 passed, 99 deselected`;
  compileall completed successfully with no output for the adapter config,
  policy, and adapter-config test modules; both planner guard commands and
  `git diff --check` completed successfully with no output.
- Old code parked/reclassified: reset lifecycle remains in
  `PrimitiveResetLifecycleService`; token runtime remains in
  `PrimitiveTokenRuntimeCoordinator`; active dig and return token planning
  remain in their focused planning services; coverage state/selection/effect
  runtime remain in their coverage modules; `pre_dig_align` remains residual
  parking/action material; `cell_entry` remains compatibility/report material;
  5P runtime behavior remains removed from current code; behavior tree, VLM,
  and LLM backends remain unsupported parked scope.
