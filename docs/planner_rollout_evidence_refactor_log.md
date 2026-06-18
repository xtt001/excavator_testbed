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
