# Planner Current-Code Architecture Plan

Status: **active architecture source of truth for implementation planning**.

This document converts the baseline architecture map, current worktree reality,
and rollout evidence report into a concrete architecture plan. It is a planning
artifact only: no planner runtime behavior is changed by this document.

Do not use the partially refactored 2026-06-17 runtime/backend stack as the
target design. Those files are absent from the current worktree after the
branch-created baseline rollback. Use that history only as a reference for risks
and naming lessons.

## Inputs And Scope

Repository state used for this plan:

- branch: `fs/v2_4-refactor-tests`
- local HEAD: `e306eb3 Require baseline architecture reconstruction`
- branch-created baseline:
  `152350e3ed9a8816ca8d685195fc8f297ab3fcec`
- no fetch, pull, or push was used for this planning round
- current worktree is intentionally dirty because planner/runtime/eval/data and
  ordinary tests were selectively restored toward the branch-created baseline

Current evidence inputs:

- `docs/planner_baseline_architecture_map.md`
- `docs/planner_evidence_reports/2026-06-18-baseline-aggregate_tx24.md`
- `runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/rollouts/rollout_000.jsonl`
- `runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/rollouts/rollout_000_planner_trace.json`
- `runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/rollouts/rollout_000_summary.json`
- `runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/eval_resolved_config.yaml`

Supporting design references:

- `docs/planner_execution_backend_abstraction_plan.md`
- `docs/planner_execution_abstraction_flow.svg`
- `docs/planner_effect_boundary_design.md`
- `docs/planner_primitive_interface_standard.md`

Non-goals for this plan:

- no planner code migration
- no behavior-tree or VLM backend implementation
- no deletion of `cell_entry`, `pre_dig_align`, or other legacy code
- no change to thresholds, branch order, reason strings, token schemas, debug
  schema, rollout summary, policy reset timing, or default config semantics

## Current Code Reality

The current worktree does not contain the earlier partially-refactored runtime
backend implementation. There is no active `testbed/planner/runtime/`,
`LegacyStateMachineBackend`, `PlannerBlackboard`, behavior-tree backend,
`primitive_config.py`, `primitive_debug.py`, or extracted coverage package in
the current code shape.

Current relevant Python files:

| File | Lines | Current role |
| --- | ---: | --- |
| `testbed/policies/hybrid/primitive_planner.py` | 5000+ | public primitive policy adapter plus compatibility facades over focused planner services |
| `testbed/planner/primitive_runtime_kernel.py` | 72 | public runtime composition root for reset, predict, and reports |
| `testbed/planner/primitive_backend_input.py` | 52 | per-tick legacy FSM backend decision input carrying context, backend facts access, and explicit compatibility actions through ordered branches |
| `testbed/planner/primitive_backend.py` | 795 | legacy FSM branch set, requested/compatibility orders, per-branch decisions, and legacy FSM backend factory |
| `testbed/planner/primitive_decision_runtime.py` | 162 | backend-name normalization and backend factory registry selection for primitive decision runtime |
| `testbed/planner/primitive_backend_facts.py` | 250 | backend-facing lazy read-only facts access for bootstrap and dig/carry/dump/return transition views |
| `testbed/planner/primitive_decision_facts.py` | 258 | backend-neutral common decision facts packet plus lazy dig/carry/dump/return transition facts views |
| `testbed/planner/primitive_execution_state.py` | 49 | mutable execution lifecycle state owner for active skill, switch reason, previous action, and latest debug state |
| `testbed/planner/primitive_observation.py` | 176 | policy observation assembler plus mutable per-observation injected-flag runtime state owner |
| `testbed/planner/primitive_cell_entry_state.py` | 81 | parked cell-entry compatibility/report runtime state owner, reset defaults, and debug-field projection |
| `testbed/planner/primitive_pre_dig_align_state.py` | 46 | parked pre-dig-align compatibility/report runtime state owner and reset defaults |
| `testbed/planner/primitive_token_state.py` | 135 | mutable dig/return token runtime state owner, reset defaults, and live token-status projection |
| `testbed/planner/primitive_return_state.py` | 56 | mutable non-token return handoff/runtime state owner and reset defaults |
| `testbed/planner/primitive_cycle_state.py` | 75 | mutable live 4P cycle/progress runtime state owner and reset defaults |
| `testbed/planner/primitive_scripted_bootstrap.py` | 116 | scripted bootstrap runtime state, readiness checks, timeout, and PD action service |
| `testbed/planner/primitive_coverage_reports.py` | 282 | coverage corridor debug, coverage decision-event, and coverage debug-field payload builders |
| `testbed/planner/boundary_detector.py` | 891 | event extraction from previous action, obs facts, and semantic boundary profile |
| `testbed/planner/cell_entry.py` | 540 | legacy cell-entry planner/auditor helpers, not active in mainline rollout |
| `testbed/planner/evidence_trace.py` | 972 | evidence classifier and report writer for rollout-driven refactor decisions |
| `testbed/planner/corridor_servo.py` | 392 | standalone corridor servo helper, not current primitive planner backend |
| `testbed/planner/rule_planner.py` | 217 | older rule planner surface, not the 4P primitive planner execution path |
| `testbed/planner/types.py` | 116 | small shared planner types |
| `testbed/runtime/_eval.py` | 1310 | eval/runtime policy construction and rollout orchestration |
| `testbed/eval/suite.py` | 2100 | eval suite orchestration, large and not a planner logic target |
| `testbed/data/primitives_v2_2.py` | 4895 | data-building semantics, not online planner decision logic |

Current test reality:

- Current worktree still has general AGX/data/eval tests and the new evidence
  tool tests.
- Earlier backend, behavior-tree, golden-trace, runtime-contract, and many
  private facade tests are absent in this baseline-shaped worktree.
- Any implementation phase that needs golden/backend parity must first create a
  small current-code parity harness from the selected rollout artifact instead
  of relying on deleted historical tests.

## Primitive Planner Responsibility Map

The current planner implementation is one large class with embedded subdomains.
The table below is the responsibility map future migrations must use.

| Range | Responsibility | Main methods | Main state read/written | Architecture target |
| --- | --- | --- | --- | --- |
| 149-430 | public adapter construction and config normalization facade | `__init__`, `_apply_adapter_config_state` | policy handles, boundary detector, normalized adapter config state | `PrimitivePlannerAdapterConfigNormalizer` plus public adapter facade |
| 842-1120 | public runtime route and execution facade | `reset`, `predict`, `_runtime_kernel`, `_execution_driver` | runtime-kernel ports, reset state, execution driver ports | `PrimitivePlannerRuntimeKernel` plus `PrimitiveExecutionDriver` |
| 1121-1649 | public reporting facades | `debug_state`, `rollout_summary`, `planner_trace` and report input builders | debug state, token flags, coverage fields, summary counters | report builders called through runtime kernel |
| 1550-1819 | inline 4P FSM branch order | `_maybe_switch_skill`, return direct handoff helpers | active skill, boundary event, counters, coverage completion/reject, pending plans | legacy FSM parity backend after execution template exists |
| 1820-1954 | skill mutation and restart effects | `_set_skill`, `_restart_*`, failed-dig stop/restart | active skill, reset timing, hold counters, dig-cut clear/invalidate, terminal stop | kernel-owned effect application |
| 1955-2359 | bootstrap and pre-dig-align logic | `_should_end_bootstrap`, `_pre_dig_align_*`, `_pre_dig_align_action` | bootstrap config, pre-dig counters, qpos target/error, surface guard | bootstrap mainline status; pre-dig-align legacy parking |
| 2361-3187 | gate and observation facts | `_update_dig_progress`, `_dig_to_carry_ready`, `_dump_ready`, `_return_to_dig_*`, geometry helpers | mass, deposit, qpos/qvel, env_state, boundary profile, hold counters | capability port status records |
| 3193-3350 | policy observation and token injection | `_policy_obs`, `_return_*_tokens_for_obs`, `_dig_cut_tokens_for_obs`, `_dig_depth_profile_tokens_for_obs` | token flags, token arrays, active skill, return planner state | policy observation assembler owned by kernel |
| 3351-3627 | active dig token planning | `_ensure_dig_cut_plan_for_cycle`, depth-profile builders, raw fields | dig-cut tokens, depth-profile tokens, fallback/source fields | token planning service |
| 3628-3914 | return-target and envelope planning | `_build_next_dig_cut_plan_for_return`, `_build_return_start_envelope_tokens_for_obs`, envelope priors | pending next-dig state, return tokens, coverage active corridor | return planning service |
| 3915-4058 | config/value helpers and operator prior token builders | normalizers, prior lookup, raw-field checks | prior JSON, raw fields, token ranges | data/config helper modules after source-of-truth check |
| 4059-5159 | coverage candidate construction and selection | `_select_next_coverage_corridor`, `_ensure_coverage_corridors`, `_select_coverage_corridor`, scoring/exemplar helpers | coverage corridors, candidate scores, active corridor, decision trace | coverage planning service |
| 5160-5636 | coverage completion, rejection, terminal-stop diagnostics | `_complete_coverage_dig`, `_complete_coverage_dump`, `_reject_active_coverage_corridor`, `_request_coverage_terminal_stop` | coverage belief, attempts, payload/deposit, terminal-stop state | coverage runtime service plus kernel effects |
| 5637-5818 | plan invalidation, config validation, prior helpers | `_clear_dig_cut_plan`, `_invalidate_pending_dig_cut_plan`, `_load_dig_cut_prior`, `_prior_percentile` | token plan ids, pending plans, prior file content | token/config helper modules |
| 5819-5940 | cell-entry legacy path | `_cell_entry_tokens_for_obs`, `_complete_cell_entry_dig`, cell pose/cell id helpers | cell-entry goal/audit/trace | legacy diagnostic parking, not mainline backend |
| 5941-6075 | goal tokens, policy dispatch, debug-state construction | `_goal_tokens`, `_active_policy`, `_all_policies`, `_make_debug_state` | goal sequence, active skill, policy handles, debug fields | goal-token service, dispatch facade, report boundary |
| removed | 5P runtime planner | removed `PrimitivePlannerACT5PPolicy` subclass | old 5P approach/dump-release runtime path retained only in git history | cleanup-approved removed runtime path |

## Evidence-Based Retention Matrix

The current baseline report uses the successful `aggregate_tx24` rollout packet:

- event_count: 75902
- evidence_packet_count: 3
- dead_candidate_min_packets: 1
- resolved config has `policy.pre_dig_align.enabled=false`
- resolved config has no `policy.cell_entry` / `cell_entry_enabled` setting
- `dig_low_dim_keys=[qpos, qvel, dig_cut_tokens]`, not `cell_entry_tokens`
- rollout summary has `cell_entry_enabled=0`,
  `pre_dig_align_enabled=0`, `pre_dig_align_completed_count=0`

| Capability | Evidence classification | Retention | Current owner | Architecture placement |
| --- | --- | --- | --- | --- |
| `execution.predict_tick` | confirmed-live | retain-and-migrate | `predict` | execution kernel |
| `fsm.skill_switch` | confirmed-live | retain-and-migrate | `_maybe_switch_skill` / `_set_skill` | legacy FSM backend after kernel exists |
| `action.dispatch` | confirmed-live | retain-and-migrate | `predict` / `_active_policy` | kernel-owned dispatch facade |
| `token.goal` | confirmed-live | retain-and-migrate | `_goal_tokens` / `_policy_obs` | token provider used by observation assembler |
| `token.dig_cut` | confirmed-live | retain-and-migrate | `_ensure_dig_cut_plan_for_cycle` | token planning service |
| `token.dig_depth_profile` | confirmed-live | retain-and-migrate | `_dig_depth_profile_tokens_for_obs` | token planning service |
| `token.return_target` | confirmed-live | retain-and-migrate | `_ensure_return_target_plan_for_cycle` | return planning service |
| `token.return_relocate` | confirmed-live | retain-and-migrate | `_return_relocate_tokens_for_obs` | return planning service |
| `token.return_start_envelope` | confirmed-live | retain-and-migrate | `_return_start_envelope_tokens_for_obs` | return-envelope service |
| `metric.dig_progress` | support-live | retain-and-migrate | `_update_dig_progress` | capability status fact |
| `gate.dig_to_carry` | confirmed-live | retain-and-migrate | `_maybe_switch_skill` dig branch | capability status plus legacy FSM branch |
| `gate.carry_to_dump` | confirmed-live | retain-and-migrate | `_maybe_switch_skill` carry branch | capability status plus legacy FSM branch |
| `gate.dump_to_return` | confirmed-live | retain-and-migrate | `_maybe_switch_skill` dump branch | capability status plus legacy FSM branch |
| `gate.return_to_dig` | confirmed-live | retain-and-migrate | `_maybe_switch_skill` return branch | capability status plus legacy FSM branch |
| `coverage.corridor` | confirmed-live | retain-and-migrate | coverage helpers | coverage planning/runtime service |
| `debug.debug_state` | report-only | retain-report-boundary | `debug_state` / `_make_debug_state` | reporting boundary |
| `report.rollout_summary` | report-only | retain-report-boundary | `rollout_summary` | reporting boundary |
| `trace.planner_trace` | report-only | retain-report-boundary | `planner_trace` | reporting boundary |
| `policy.public_adapter` | compatibility | retain-compatibility | `PrimitivePlannerACTPolicy` | public adapter |
| `compat.5p_policy` | compatibility-cleanup | removed-runtime-cleanup | git history only | cleanup-approved removed runtime path |
| `token.cell_entry` | dead-candidate | retain-legacy-parking | `_cell_entry_tokens_for_obs` | legacy diagnostic parking |
| `gate.pre_dig_align` | dead-candidate | retain-legacy-parking | `_maybe_switch_skill` pre-dig branch plus `PrimitivePreDigAlignCompatibilityRuntimeState` | legacy diagnostic/action parking |

## Target Architecture

The target boundary is:

```text
PrimitivePlannerACTPolicy
  -> PrimitivePlannerRuntimeKernel
      -> PrimitiveCapabilityPort
      -> PrimitiveDecisionBackend
      -> PrimitiveDecisionResult
      -> PlannerEffect application
      -> action dispatch and reporting
```

The current ideal-vs-current interface standard for this boundary is
`docs/planner_primitive_interface_standard.md`. Use that document when choosing
implementation slices after Phase 9.33B; it distinguishes the target interface
from the current legacy-FSM-backendified implementation and must not be read as
a claim that alternate behavior-tree, VLM, or LLM backends are already
swappable.

Current status after Phase 9.33B: `PrimitivePlannerRuntimeKernel` owns the
public runtime route (`reset`, `predict`, `debug_state`, `rollout_summary`, and
`planner_trace`). `PrimitivePlannerACTPolicy` still constructs typed ports and
keeps compatibility facades/storage, but those public methods are now
kernel-backed thin wrappers.

### Public Adapter

`PrimitivePlannerACTPolicy` remains the only public policy surface for eval and
rollout:

- `reset()`
- `predict(obs) -> np.ndarray`
- `debug_state()`
- `rollout_summary()`
- `planner_trace()`

Long-term adapter responsibilities:

- construct low-level ACT policies and the execution kernel
- preserve public constructor/config compatibility
- expose public reporting shapes
- hide backend selection from eval/rollout callers
- keep cleanup-approved 5P runtime removal explicit; old branch/git history
  preserves historical behavior

### Execution Driver / Runtime Kernel

Candidate files: `testbed/planner/primitive_runtime_kernel.py` and
`testbed/planner/primitive_execution.py`.

The original execution-kernel target has now split into two concrete owners:
`PrimitivePlannerRuntimeKernel` owns public runtime routing, while
`PrimitiveExecutionDriver` owns one-tick execution ordering. Future work should
extend those owners rather than introducing a second kernel name.

Conceptual execution-driver methods:

```python
class PrimitiveExecutionDriver:
    def run_tick(self, obs: Mapping[str, object]) -> PrimitiveTickResult: ...
    def predict(self, obs: Mapping[str, object]) -> np.ndarray: ...
```

Execution/effect-boundary owned effects:

- `SetSkill`
- `ResetPolicyForSkill`
- `IncrementCounter`
- `ResetCounter`
- `ClearDigCutPlan`
- `InvalidatePendingDigCutPlan`
- `EnsureDigCutPlan`
- `EnsureReturnTargetPlan`
- `CompleteCoverageDig`
- `CompleteCoverageDump`
- `RejectCoverageCorridor`
- `RequestCoverageTerminalStop`
- `RecordDiagnostic`

The backend may request these effects. Only the execution route and
shell-side requested-effect applier may apply them.

### Capability Port

Candidate file: `testbed/planner/primitive_capabilities.py`.

The capability port is a read-only interface over typed facts. It must not be a
one-method-per-private-method facade.

Initial status records:

| Status record | Current source methods | Used by |
| --- | --- | --- |
| `PrimitiveObservationFacts` | `_env_state`, `_mass_in_bucket`, `_deposited_mass`, `_target_geometry` | all gates and diagnostics |
| `BootstrapStatus` | `_should_end_bootstrap`, `_scripted_bootstrap_enabled`, `_scripted_bootstrap_target_reached` | legacy FSM |
| `DigTransitionStatus` | `_update_dig_progress`, `_dig_exit_guard_ready`, `_dig_bad_replan_ready`, `_dig_to_carry_ready` | legacy FSM and future BT |
| `CarryTransitionStatus` | `_carry_release_safety_done`, `_dump_ready`, boundary-event facts | legacy FSM and future BT |
| `DumpTransitionStatus` | `_dump_done`, dump boundary event facts | legacy FSM and future BT |
| `ReturnTransitionStatus` | `_return_to_dig_handoff_ready`, `_return_to_dig_direct_handoff_ready`, `_return_to_dig_shallow_guard_ready` | legacy FSM and future BT |
| `CoverageStatus` | `_coverage_active_corridor`, `_coverage_candidate_scores`, terminal-stop fields | coverage-aware decisions and reporting |
| `TokenStatus` | token source/injected/fallback fields | reporting, VLM packet, parity checks |

Legacy-only status:

| Status record | Current source methods | Placement |
| --- | --- | --- |
| `LegacyPreDigAlignStatus` | `_pre_dig_align_*` | legacy parking, not default mainline backend |
| `LegacyCellEntryStatus` | `_cell_entry_*` | legacy diagnostic parking, not default token contract |

### Decision Backend

Candidate file: `testbed/planner/primitive_decision.py`.

The backend owns only decision scheme details. It reads `PrimitiveTickContext`
and `PrimitiveCapabilityPort`, then returns a structured result.

```python
class PrimitiveDecisionBackend(Protocol):
    name: str

    def reset(self) -> None: ...

    def tick(
        self,
        context: PrimitiveTickContext,
        capabilities: PrimitiveCapabilityPort,
    ) -> PrimitiveDecisionResult: ...
```

```python
@dataclass(frozen=True)
class PrimitiveDecisionResult:
    backend_name: str
    status: Literal["no_change", "switch", "terminal_stop", "error"]
    branch_path: tuple[str, ...]
    switch_reason: str
    effects: tuple[PlannerEffect, ...]
    diagnostics: Mapping[str, object]
```

Backend constraints:

- no direct `PrimitivePlannerACTPolicy` reference
- no direct writes to `self._xxx`
- no low-level ACT policy dispatch
- no token array construction
- no debug/summary assembly
- no unconstrained reason strings for VLM/LLM backends

### Reporting Boundary

Candidate file: `testbed/planner/primitive_reporting.py`.

Reporting must remain a boundary, not part of decision logic:

- debug state keeps the public schema stable
- coverage debug fields are projected by `CoverageReportService` from explicit
  snapshot inputs
- rollout summary keeps current aggregate fields stable
- planner trace owns structured evidence/debug payloads
- report-only fields can read kernel state but must not drive backend decisions

## Legacy Parking Catalog

Parking means the code is retained but kept out of the mainline architecture.
Parked code must not be used as a justification for new mainline services.

| Path | Evidence | Current code owner | Parking owner | Allowed use | Not allowed |
| --- | --- | --- | --- | --- | --- |
| `token.cell_entry` | absent from successful rollout; `cell_entry_enabled=0`; no `cell_entry_tokens` low-dim key | `_cell_entry_tokens_for_obs`, `_complete_cell_entry_dig`, `testbed/planner/cell_entry.py`, `PrimitiveCellEntryCompatibilityRuntimeState` | parked compatibility/report state owner plus legacy diagnostics | old configs, diagnostics, explicit legacy replay | default token contract, new backend fact, VLM decision packet |
| `gate.pre_dig_align` | successful rollout has `pre_dig_align.enabled=false`; completed/timeout counts are zero | pre-dig branch in `_maybe_switch_skill`, `_pre_dig_align_*`, `_pre_dig_align_action`, `PrimitivePreDigAlignCompatibilityRuntimeState` | parked compatibility/report state owner plus residual action diagnostics | explicit legacy config, old PD alignment replay, debug comparison | default FSM path, behavior-tree node, VLM effect unless re-approved |
| removed `PrimitivePlannerACT5PPolicy` runtime path | user-approved cleanup, not mainline evidence | git history only | removed runtime path | historical comparison from old branches | source of default 4P architecture |

Parking review before any later cleanup:

1. Search config, tests, docs, and run artifacts for references.
2. Decide whether the owner is compatibility, diagnostic, test-only, or obsolete.
3. Keep an explicit facade if public import/config compatibility remains.
4. Remove only after the owner audit and user confirmation.

## Migration Slices

### Slice 1: Current-Code Parity Harness

Purpose: create a small parity harness from the selected successful rollout so
future code movement has a current test target.

Files likely touched:

- `tests/test_planner_current_code_parity.py`
- possibly `testbed/planner/evidence_trace.py` if additional trace event
  conversion is needed

Behavior to lock:

- skill sequence and switch reasons
- action source category: scripted, pre-dig, or ACT policy
- token injected/source flags
- transition timeout/completion flags
- debug-state keys used in the rollout evidence
- planner trace fields used by the evidence classifier

Verification:

- focused pytest for the new parity harness
- `python -m compileall` for touched Python files
- `git diff --check`

### Slice 2: Extract Public Tick Execution Template

Purpose: make `predict()` read as an explicit execution template while leaving
the old decision body as the behavior source of truth.

Files likely touched:

- create `testbed/planner/primitive_execution.py`
- add focused tests for execution-step ordering
- modify `testbed/policies/hybrid/primitive_planner.py` only as a thin bridge

Allowed behavior:

- `predict()` delegates preparation, decision call, action dispatch, and
  finalization to named steps
- `_maybe_switch_skill()` remains the only decision logic
- `_active_policy()`, `_policy_obs()`, and `_make_debug_state()` can remain
  facades during this slice

Not allowed:

- backend protocol
- behavior tree
- VLM/LLM packet
- threshold/reason/schema changes
- moving token planning and coverage in the same slice

Parity:

- selected rollout parity harness
- evidence report still classifies the same capabilities
- debug/summary/trace shape unchanged

### Slice 3: Introduce Decision And Effect Contracts

Purpose: create typed result/effect contracts before moving branch logic.

Files likely touched:

- `testbed/planner/primitive_decision.py`
- tests for `PrimitiveDecisionResult` and ordered effects

Allowed behavior:

- old `_maybe_switch_skill()` can be wrapped by a temporary adapter that returns
  `PrimitiveDecisionResult`
- effect application remains in the old shell/kernel

Not allowed:

- a backend that calls many `policy._private` methods directly as its permanent
  API
- moving coverage, tokens, or reports in the same slice

### Slice 4: Extract Capability Status Records

Purpose: replace direct private-field reads in future backends with stable facts.

Recommended order:

1. `PrimitiveObservationFacts`
2. `DigTransitionStatus`
3. `CarryTransitionStatus`
4. `DumpTransitionStatus`
5. `ReturnTransitionStatus`
6. `CoverageStatus`
7. `TokenStatus`

Each status record must have focused tests and must not mutate planner state.

### Slice 5: Token And Return Planning Services

Purpose: move token generation and return planning out of the policy shell.

Candidate files:

- `testbed/planner/primitive_tokens.py`
- `testbed/planner/primitive_return_planning.py`
- `testbed/planner/primitive_observation.py`

Move only after the execution template and status records exist. Token schema,
token order, injected-key names, and source/fallback strings must stay fixed.

### Slice 6: Coverage Planning And Runtime Service

Purpose: extract coverage candidate construction, scoring, belief updates,
completion, rejection, and terminal-stop requests.

Candidate file:

- `testbed/planner/primitive_coverage.py`
- `testbed/planner/primitive_coverage_reports.py` for coverage debug and trace
  payload projection
- `testbed/planner/primitive_coverage_updates.py` for completion/rejection
  mutation and runtime request gating once `primitive_coverage.py` approaches
  the large-file threshold

This service must own real coverage state, not return temporary copies. Direct
service-versus-facade parity tests should compare candidate scores, selected
corridor, state exemplar payloads, decision trace, completion/rejection fields,
and terminal-stop reason.

### Slice 7: Move Legacy FSM Behind Backend Protocol

Purpose: make baseline branch order a backend implementation after the kernel,
effects, and capability status records exist.

Default backend:

- `legacy_fsm`

Backend boundary file:

- `testbed/planner/primitive_backend.py`

Behavior to preserve:

- branch order
- reason strings
- counter timing
- policy reset timing
- dig-cut clear/invalidate timing
- coverage completion/rejection timing
- token and debug surfaces

### Slice 8: Add Alternate Backends

Only after `legacy_fsm` is the parity default:

- behavior tree can map nodes to `PrimitiveDecisionResult`
- VLM/LLM backend can receive a constrained decision packet
- learned scheduler or rule-table backend can use the same capability port

Alternate backend rule:

- if it needs a new fact, add a capability status field
- if it needs a new mutation, add a validated effect
- it must not read or write planner private fields

## Verification Matrix

| Surface | What to compare | First required slice |
| --- | --- | --- |
| public policy API | `reset`, `predict`, `debug_state`, `rollout_summary`, `planner_trace` still callable through current eval path | Slice 1 |
| skill lifecycle | skill sequence, switch reason, transition completed/timeout counters | Slice 1 |
| action dispatch | scripted bootstrap vs pre-dig action vs ACT policy dispatch and active policy key | Slice 2 |
| token contract | key names, dimensions, injected flags, source/fallback strings | Slice 2 and Slice 5 |
| return planning | return target, relocate, start envelope, pending next-dig fields | Slice 5 |
| coverage | selected corridor, scores, state exemplar ids, completion/rejection trace, terminal stop | Slice 6 |
| reporting | debug keys, rollout summary keys, planner trace keys | every slice touching reporting |
| compatibility | `PrimitivePlannerACTPolicy` constructor/config remains compatible; removed 5P runtime fails fast through explicit runtime diagnostics | every public-surface slice |
| parking | `cell_entry` and `pre_dig_align` do not become default mainline dependencies | every slice touching tokens or gates |

Minimum verification commands for documentation-only plan changes:

```bash
git diff --check
python scripts/planner_refactor_guard.py --check-plan-contract
python scripts/planner_refactor_guard.py --check-skill-contract
```

Minimum verification commands for the first code slice:

```bash
python -m pytest -q tests/test_planner_evidence_trace.py tests/test_planner_evidence_cli.py
python -m pytest -q tests/test_planner_current_code_parity.py
python -m compileall -q testbed/planner testbed/policies/hybrid/primitive_planner.py tests/test_planner_current_code_parity.py
git diff --check
python scripts/planner_refactor_guard.py --check-plan-contract
python scripts/planner_refactor_guard.py --check-skill-contract
```

## Architecture Decisions

1. The first implementation target is the execution template, not the backend.
2. `PrimitivePlannerACTPolicy` remains the public adapter and compatibility
   owner during the migration.
3. The legacy FSM is the first backend only after a kernel and effects boundary
   exist.
4. Capability status records are grouped by domain, not by old private method
   names.
5. `cell_entry` and `pre_dig_align` stay in legacy parking unless the user later
   re-approves them as mainline behavior with new rollout evidence.
6. Reporting is a boundary. It can read state but must not become decision
   logic.
7. Old deleted runtime/backend files from the partial refactor are not the
   target source of truth.
8. Each migration slice moves one responsibility chain and keeps semantic
   behavior fixed unless explicitly approved.

## Immediate Next Action

Implementation history is tracked in
`docs/planner_rollout_evidence_refactor_log.md`. Slices 1-3 have already
established the current-code parity harness, public tick execution template,
and decision/effect result contracts.

Current status note after Phase 9.14: policy observation/token injection
assembly has moved out of the large policy shell into
`PrimitivePolicyObservationAssembler` in
`testbed/planner/primitive_observation.py`. `_policy_obs(...)` now remains as a
thin compatibility wrapper. The assembler owns provider order, injected key
names, observation copy/no-copy behavior, and immutable injected-state
calculation. Phase 9.49 adds `PrimitiveObservationInjectionRuntimeState` in the
same module as the mutable owner for clear/apply/projection of the six legacy
injected flags. Token planning algorithms and token source/fallback/debug
contracts remain in their existing owners.

Current status note after Phase 9.15: public `debug_state()` dict assembly has
moved into `PrimitiveDebugReportBuilder` in
`testbed/planner/primitive_debug_report.py`. `debug_state()` now delegates to a
typed debug snapshot/report-input builder path while token debug fields come
from `TokenStatus.to_debug_fields()`. `rollout_summary()`, `planner_trace()`,
and per-tick `_make_debug_state(...)` are intentionally unchanged in this
round.

Current status note after Phase 9.16: public `rollout_summary()` dict assembly
has moved into `PrimitiveRolloutSummaryBuilder` in
`testbed/planner/primitive_rollout_summary.py`. `rollout_summary()` now
delegates through typed summary inputs while the builder owns public summary
key layout, bool-like `int(...)` projection, and `None` to `NaN` fallback
projection. `planner_trace()`, public `debug_state()` assembly, and per-tick
`_make_debug_state(...)` are intentionally unchanged in this round.

Current status note after Phase 9.17: public `planner_trace()` dict assembly
has moved into `PrimitivePlannerTraceBuilder` in
`testbed/planner/primitive_planner_trace.py`. `planner_trace()` now delegates
through typed trace inputs while the builder owns public trace key layout,
contract version/string fields, top-level trace-list projection, coverage
config/status fields, and terminal-stop fields. Coverage decision trace
recording, public `debug_state()` and `rollout_summary()` assembly, and
per-tick `_make_debug_state(...)` are intentionally unchanged in this round.

Current status note after Phase 9.18: primitive action dispatch and active
low-level policy selection have moved into `PrimitiveActionDispatchService` in
`testbed/planner/primitive_action_dispatch.py`. `_dispatch_tick_action()`,
`_active_policy()`, `_all_policies()`, and `_first_dig_policy_active()` now
delegate through typed dispatch ports while the service owns scripted
bootstrap/pre-dig short-circuits, first-dig policy selection, all-policy order,
policy-observation dispatch, low-level `predict(...)`, and `float32` action
reshape. Reset lifecycle, `_set_skill()` mutation timing, policy observation
assembly, scripted/pre-dig action algorithms, 5P transition semantics, and
public reporting builders are intentionally unchanged in this round.

Current status note after Phase 9.19: primitive tick finalization has moved
into `PrimitiveTickFinalizationService` in
`testbed/planner/primitive_tick_finalization.py`. The service owns
previous-action copy semantics, dispatch-after transition-completed reason
prefix detection, and compact `PrimitivePlannerDebugState` assembly. The 4P
policy shell now keeps thin wrappers for `_record_tick_previous_action()`,
`_transition_completed_after_tick_dispatch()`, `_make_debug_state()`, and
`_finalize_tick_debug_state()`, while 5P supplies only a compatibility
finalization input mapping for its skill ids and approach/dump-release hold
counters. Public `debug_state()`, `rollout_summary()`, `planner_trace()`,
reset lifecycle, `_set_skill()` mutation timing, action dispatch, branch
ordering, and token/coverage/runtime semantics are intentionally unchanged in
this round.

Current status note after Phase 9.20: coverage requested-effect runtime
sequencing has moved into `CoverageEffectRuntimeCoordinator` in
`testbed/planner/primitive_coverage_updates.py`. The coordinator owns
coverage-mode no-op gating, dig payload-gain completion, dump completion
state-write/event/reopen/terminal ordering, corridor rejection
state-write/event/reopen/terminal ordering, multi-pass reopen result
application, and terminal-stop result/event application. Coverage state storage
now lives in `CoverageRuntimeState`; the 4P policy shell builds typed ports and
keeps facts/report helper facades, while
`_complete_coverage_dig()`, `_complete_coverage_dump()`,
`_reject_active_coverage_corridor()`, `_maybe_reopen_coverage_pass()`, and
`_request_coverage_terminal_stop()` are thin coordinator-backed wrappers.
Coverage candidate construction, scoring/selection, corridor debug projection,
planner trace/summary/debug schemas, branch ordering, token planning, and
low-level ACT dispatch are intentionally unchanged in this round.

Current status note after Phase 9.21: coverage corridor selection runtime
sequencing has moved into `CoverageSelectionRuntimeCoordinator` in
`testbed/planner/primitive_coverage.py`. The coordinator owns dig-cut prior and
empty-candidate checks, ensure-corridor no-op/build writeback, selection-service
invocation, candidate-score writeback, `select_corridor` decision-event
emission, all-depleted reopen/terminal sequencing, and active/last-selected
corridor id writeback. Coverage state storage now lives in
`CoverageRuntimeState`; the 4P policy shell keeps raw facts helper facades and
report-event append mechanics, while
`_select_next_coverage_corridor()`, `_ensure_coverage_corridors()`, and
`_select_coverage_corridor()` are thin coordinator-backed wrappers. Coverage
candidate construction, scoring algorithm, first-dig gate facts, state exemplar
matching, raw-field/token planning, planner trace/summary/debug schemas, branch
ordering, and low-level ACT dispatch are intentionally unchanged in this round.

Current status note after Phase 9.22: coverage mutable runtime storage has moved
into `CoverageRuntimeState` in `testbed/planner/primitive_coverage_state.py`.
The state owner stores corridor lists, active/last-selected ids, payload/deposit
counters, completed-dump and low-productivity counters, pass and terminal-stop
state, candidate scores, decision trace, rejected exemplar ids, and active
state-exemplar payload. It also owns common state helper behavior such as
corridor lookup, active corridor lookup, depleted count, all-depleted status,
selected-id/counter/terminal writeback, and state-exemplar/rejected-id updates.
The 4P policy shell initializes a fresh state owner on reset and preserves old
private `_coverage_*` names as property-backed compatibility facades, so tests
and diagnostics still mutate the same stored containers. Coverage selection and
effect runtime ports now point at the same state owner rather than independent
policy fields. Coverage candidate construction, selection scoring, effect
sequencing, decision trace schema, report schemas, branch ordering, and low-level
ACT dispatch are intentionally unchanged in this round.

Current status note after Phase 9.23: coverage state-conditioned exemplar
planning has moved into `CoverageStateExemplarPlanner` in
`testbed/planner/primitive_coverage_exemplars.py`. The planner owns exemplar
JSON loading/validation, relative path resolution against the dig-cut prior,
removed-depth grid projection, exemplar distance computation, temperature
weighting with the old uniform fallback, rejected exemplar filtering,
weighted dig-cut raw-field assembly, weighted dig-depth-profile token assembly,
and pure state-conditioned plan selection. The 4P policy shell keeps old private
method names as service-backed compatibility/diagnostic facades and performs
only `update_state=True` writeback into `CoverageRuntimeState` and active
`CoverageCorridorState` debug fields. Coverage candidate construction,
selection scoring, effect sequencing, token contracts, decision trace schema,
report schemas, branch ordering, and low-level ACT dispatch are intentionally
unchanged in this round.

Current status note after Phase 9.24: public primitive tick execution ordering
has moved into `PrimitiveExecutionDriver` in
`testbed/planner/primitive_execution.py`. The driver owns boundary update,
switch-reason reset, dig-progress update for `dig`, decision backend invocation,
requested-effect application before return-timeout accounting and action
dispatch, previous-action recording, transition-completed checks, debug
finalization, and `predict()` action extraction. `PrimitivePlannerACTPolicy`
now builds typed `PrimitiveExecutionPorts` and delegates public `predict()` to
the driver; `run_primitive_tick()` and `PrimitiveTickCallbacks` remain
compatibility facades over the same ordering. Decision branches,
requested-effect families, action dispatch, finalization services, token/report
schemas, branch ordering, and low-level ACT output semantics are intentionally
unchanged in this round.

Current status note after Phase 9.25: primitive decision backend selection has
moved into `PrimitiveDecisionRuntime` in
`testbed/planner/primitive_decision_runtime.py`. The execution driver now calls
the policy's generic `_decide_tick()` bridge, which delegates to the runtime
instead of naming the legacy FSM bridge as the default source. The runtime owns
backend-name normalization, supported-backend validation, default
`legacy_fsm` requested decision routing, and legacy `_maybe_switch_skill()`
compatibility decision routing. Unsupported backend names fail fast and do not
fall back to `LegacyFSMBackendAdapter` or broad `_maybe_switch_skill()`
mutation. This preserves the current maturity claim: the default legacy FSM is
backendified, while behavior-tree, VLM/LLM, and other alternate backends remain
unimplemented parked scope.

Current status note after Phase 9.26: primitive decision backend input has
moved from scatter arguments into `PrimitiveDecisionContext` in
`testbed/planner/primitive_decision_context.py`. The context packet preserves
the `obs`, `boundary_event`, and `PrimitiveTickPreparation` object identities
for the tick and exposes the skill-before-decision and dig-progress flags as
read-only convenience fields. `PrimitiveDecisionRuntime`,
`LegacyFSMRequestedDecisionBackend`, `LegacyFSMCompatibilityDecisionBackend`,
`PrimitiveRequestedBranchRunner`, and the legacy FSM branch objects are now
context-driven internally; their scatter-argument `decide_tick(...)` methods
remain compatibility facades. This keeps the current maturity claim unchanged:
the default legacy FSM is backendified with a shared decision packet shape,
while behavior-tree, VLM/LLM, and other alternate backends remain unimplemented
parked scope.

Current status note after Phase 9.27: primitive decision backend facts now flow
through `PrimitiveDecisionCapabilities` in
`testbed/planner/primitive_decision_capabilities.py`. The policy builds typed
capability ports from current shell readers, bootstrap gates, the
`PrimitiveFSMCapabilityProvider`, and the explicitly residual pre-dig-align
handler; `LegacyFSMBranchPorts` is narrowed to skill-name constants plus that
capabilities object. Legacy FSM bootstrap/dig/carry/dump/return branches now
consume `PrimitiveDecisionContext + PrimitiveDecisionCapabilities` instead of
holding individual shell callback/status-provider fields. This keeps the
maturity claim at default legacy-FSM backendified with shared context and
capabilities shape; behavior-tree, VLM/LLM, and other alternate backends remain
unimplemented parked scope.

Current status note after Phase 9.28: 4P primitive skill switch lifecycle
sequencing now lives in `PrimitiveSkillLifecycleService` in
`testbed/planner/primitive_skill_lifecycle.py`. The service owns the old
`_set_skill(...)` ordering for same-skill no-op, skill/reason writes,
active-policy reset timing, target-specific counters and mirrors, dig coverage
payload reset, and dig-cut plan clearing. `PrimitivePlannerACTPolicy._set_skill`
is now a thin service-backed facade over typed
`PrimitiveSkillLifecyclePorts`; requested-effect application still calls that
facade through its existing `set_skill` port. The 5P `_set_skill()` override,
`pre_dig_align` residual behavior, `cell_entry` compatibility material, and
alternate backend parked scope remain intentionally unchanged.

Current status note after Phase 9.29: primitive dig/return token runtime
sequencing now lives in `PrimitiveTokenRuntimeCoordinator` in
`testbed/planner/primitive_token_runtime.py`. `_dig_cut_tokens_for_obs(...)`,
`_dig_depth_profile_tokens_for_obs(...)`,
`_ensure_dig_cut_plan_for_cycle(...)`, `_return_target_tokens_for_obs(...)`,
`_return_relocate_tokens_for_obs(...)`,
`_return_start_envelope_tokens_for_obs(...)`,
`_ensure_return_target_plan_for_cycle(...)`, `_clear_dig_cut_plan()`, and
`_invalidate_pending_dig_cut_plan()` are service-backed compatibility facades.
The coordinator owns disabled/active-skill/terminal-stop/hold-cycle gating,
dig-cut plus dig-depth-profile writeback, return-target success/fallback
writeback, pending next-dig plan state, copy semantics, and clear/invalidate
resets. Token planner algorithms, token dimensions/contracts, source/fallback
strings, observation injected-key assembly, `cell_entry` compatibility,
`pre_dig_align` residual behavior, 5P token behavior, and alternate backend
parked scope remain intentionally unchanged.

Current status note after Phase 9.30: return token planning orchestration now
lives in `PrimitiveReturnTokenPlanningService` in
`testbed/planner/primitive_return_token_planning.py`.
`_build_next_dig_cut_plan_for_return(...)`,
`_unpack_return_target_token_plan(...)`,
`_build_return_start_envelope_tokens_for_obs(...)`,
`_apply_return_start_envelope_token_plan(...)`,
`_maybe_condition_return_start_envelope_qpos_from_relocate(...)`, and the
return start-envelope prior/cell-id helper methods are now service-backed
compatibility facades. The service owns return-target mode routing, coverage
corridor selection and raw-field handoff, active coverage corridor writeback,
return-start-envelope build/apply/conditioning, source/prior-bound flag
writeback, prior token/mapping/bounds routing, and token/raw-field copy
semantics. Active dig token planning, token algorithm classes, coverage
selection/scoring/exemplar algorithms, return handoff gate/effect services,
`cell_entry`, `pre_dig_align`, 5P token behavior, and alternate backend parked
scope remain intentionally unchanged.

Current status note after Phase 9.31: active dig token planning orchestration
now lives in `PrimitiveDigTokenPlanningService` in
`testbed/planner/primitive_dig_token_planning.py`.
`_build_dig_cut_tokens_for_obs(...)`, `_apply_dig_cut_token_plan(...)`,
`_build_dig_depth_profile_tokens_for_obs(...)`,
`_apply_dig_depth_profile_token_plan(...)`,
`_build_live_dig_depth_profile_tokens_for_obs(...)`, dig-depth-profile
prior/raw-field/cell-id helpers, `_raw_fields_from_live_pose(...)`,
`_build_operator_prior_dig_cut_tokens(...)`, and
`_build_operator_prior_coverage_dig_cut_tokens(...)` are now service-backed
compatibility facades. The service owns pending return-target dig plan
application, conservative/operator-prior/operator-prior-coverage and
sweep-belief mode routing, fallback conservative behavior, coverage raw-field
handoff, dig-cut source/fallback/in-prior writeback, dig-depth-profile
source/fallback/error writeback, raw-field priority, cell-id priority, and copy
semantics. Return token planning, token runtime sequencing, token algorithm
classes, coverage selection/scoring/exemplar algorithms, return handoff
gate/effect services, `cell_entry`, `pre_dig_align`, 5P token behavior, and
alternate backend parked scope remain intentionally unchanged.

Current status note after Phase 9.32: 4P reset lifecycle sequencing now lives
in `PrimitiveResetLifecycleService` in
`testbed/planner/primitive_reset_lifecycle.py`. Public
`PrimitivePlannerACTPolicy.reset()` is a thin service-backed adapter that builds
typed reset ports, applies the returned reset state, and creates the initial
compact debug state. The service owns low-level policy reset order, boundary
detector reset, bootstrap/pre-dig initial-skill selection, counters, hold
mirrors, pre-dig cached diagnostics, cell-entry compatibility defaults,
dig/return token and pending-plan defaults, injected-token flags,
source/fallback strings, and fresh `CoverageRuntimeState` creation. The 5P
runtime planner subclass has been removed by explicit cleanup decision; old
5P runtime behavior is preserved only in branch/git history, while historical
data-slicing and experiment records remain documentation/history rather than
current runtime architecture.

Current status note after Phase 9.33A: public adapter config normalization now
lives in `PrimitivePlannerAdapterConfigNormalizer` and
`PrimitivePlannerAdapterConfigState` under
`testbed/planner/primitive_adapter_config.py`. `PrimitivePlannerACTPolicy.__init__`
keeps its full public constructor signature and default values, directly stores
only the low-level policy handles and boundary detector, builds
`PrimitivePlannerAdapterConfigInputs`, applies the normalized legacy field
updates, and then calls the existing reset facade. Old private config helper
names remain compatibility facades delegating to the config module. This slice
does not build a kernel factory and does not change token planners, execution
driver wiring, decision runtime, coverage algorithms, `pre_dig_align`,
`cell_entry`, or removed 5P runtime status.

Current status note after Phase 9.34: the first backend-neutral common decision
facts packet now lives in `PrimitiveDecisionFacts` under
`testbed/planner/primitive_decision_facts.py`. It preserves the per-tick
`PrimitiveDecisionContext` identity and adds current skill/reason facts without
carrying transition status providers, mutation ports, effect appliers, planner
`self`, or policy fields. `PrimitiveDecisionCapabilities.decision_facts(...)`
builds that packet, and the legacy FSM branches now use it for common
skill/reason checks while keeping dig/carry/dump/return transition statuses lazy
and branch-local. This is an initial common-facts boundary, not full alternate
backend readiness.

Current status note after Phase 9.35: return transition cache refresh is no
longer hidden inside the return status read. `PrimitiveFSMCapabilityProvider`
now exposes `refresh_return_transition_state(obs)` for the explicit shell-owned
handoff cache refresh, and `return_transition_status(obs, boundary_event)` only
reads cached return flags. `PrimitiveDecisionCapabilities` exposes the same
split at context level, and `LegacyFSMReturnBranch` calls refresh only after the
active skill check confirms `return`, immediately before reading return status.
This preserves lazy branch timing while removing a mutation from the status-read
interface; return status is still not part of `PrimitiveDecisionFacts`.

Current status note after Phase 9.36: active return decisions now consume a
typed return-specific facts view, `PrimitiveReturnTransitionFacts`, from
`testbed/planner/primitive_decision_facts.py`. The view wraps an existing
`PrimitiveDecisionFacts` identity plus the read-only `ReturnTransitionStatus`.
`PrimitiveDecisionCapabilities.return_transition_facts(...)` assembles that view
without refreshing return state and can reuse a prebuilt common facts packet.
`LegacyFSMReturnBranch` still refreshes only after the active skill check
confirms `return`, then consumes the return facts view for effect selection.
This advances the backend-neutral facts shape for return only; dig/carry/dump
transition facts and full alternate-backend readiness remain future work.

Current status note after Phase 9.37: active dig decisions now consume a typed
dig-specific facts view, `PrimitiveDigTransitionFacts`, from
`testbed/planner/primitive_decision_facts.py`. The view wraps the same common
`PrimitiveDecisionFacts` identity plus a read-only `DigTransitionStatus`.
`PrimitiveFSMCapabilityProvider.dig_transition_status(...)` no longer writes
the shell/debug `_dig_to_carry_reason` mirror; the active dig branch now calls
`PrimitiveDecisionCapabilities.sync_dig_transition_reason(...)` explicitly after
assembling dig facts and before effect selection. Non-dig skills still do not
read dig status/facts or sync the mirror. This advances the backend-neutral
facts shape for dig and return only; carry/dump transition facts and full
alternate-backend readiness remain future work.

Current status note after Phase 9.38: active carry and dump decisions now
consume typed facts views, `PrimitiveCarryTransitionFacts` and
`PrimitiveDumpTransitionFacts`, from
`testbed/planner/primitive_decision_facts.py`. Each view wraps the existing
common `PrimitiveDecisionFacts` identity plus the read-only carry/dump status
identity. `LegacyFSMCarryBranch` and `LegacyFSMDumpBranch` only assemble these
facts after their active-skill checks, so lazy branch timing is preserved. This
means dig/carry/dump/return mainline transition branches all have explicit
facts views, but there is still no unified backend-neutral facts bundle and no
alternate backend readiness claim.

Current status note after Phase 9.39: dig/carry/dump/return transition facts
views are now reached through `PrimitiveBackendFactsAccess` in
`testbed/planner/primitive_backend_facts.py`. The access object holds the
per-tick `PrimitiveDecisionContext`, one shared `PrimitiveDecisionFacts`
identity, and a private read-only transition-status reader; it exposes lazy
`dig_transition()`, `carry_transition()`, `dump_transition()`, and
`return_transition()` methods. `LegacyFSMDigBranch`,
`LegacyFSMCarryBranch`, `LegacyFSMDumpBranch`, and `LegacyFSMReturnBranch` now
use `capabilities.backend_facts(context)` as their branch-local source of
common facts and transition facts. Dig reason sync, return refresh, residual
pre-dig-align handling, and effect application remain explicit compatibility or
mutation responsibilities outside read-only facts access. Bootstrap still uses
the separate `bootstrap_status(...)` path, so the backend input contract is not
yet complete and alternate backend readiness remains future work.

Current status note after Phase 9.40: bootstrap requested-branch facts now also
flow through `PrimitiveBackendFactsAccess`. The backend facts module owns
`BootstrapDecisionStatus`, `PrimitiveBootstrapDecisionFacts`, the read-only
`PrimitiveBootstrapDecisionReader` protocol, and
`next_skill_after_bootstrap(...)`. `LegacyFSMBootstrapBranch` now obtains
`backend_facts = capabilities.backend_facts(context)`, uses
`backend_facts.common` for the active-skill check, and calls
`backend_facts.bootstrap_decision(...)` only for active bootstrap decisions.
`PrimitiveDecisionCapabilities.bootstrap_status(...)` remains a compatibility
facade over that access path. This completes the confirmed-live legacy FSM
requested branches' migration to the backend facts-access shape, while dig
reason sync, return refresh, residual pre-dig-align handling, and effect
application remain explicit actions outside read-only facts. The next backend
contract gap is that branches still receive the mixed
`PrimitiveDecisionCapabilities` object rather than separate read-only facts
access and compatibility-action dependencies.

Current status note after Phase 9.41: legacy FSM branch dependencies are now
split into read-only facts access and explicit compatibility actions.
`PrimitiveDecisionFactsSource` owns `decision_facts(context)` and
`backend_facts(context, facts=None)`, while
`PrimitiveDecisionCompatibilityActions` owns only dig reason sync, return
refresh, and residual pre-dig-align handling. `LegacyFSMBranchPorts` now
contains `facts_source` and `compatibility_actions` instead of a broad
`capabilities` field. Bootstrap, carry, and dump branch dataclasses store only
the facts source; dig and return additionally store compatibility actions for
their explicit sync/refresh steps; the residual pre-dig adapter stores both for
its parked already-applied path. `PrimitiveDecisionCapabilities` remains
available as a compatibility facade and construction helper, but is no longer
stored by branch dataclasses. The next backend contract gap is that each branch
still creates per-tick backend facts from the facts source independently; there
is not yet one runner-owned backend decision input packet passed through the
ordered branch chain.

Current status note after Phase 9.42: the legacy FSM branch chain now receives
one per-tick `PrimitiveBackendDecisionInput`. `PrimitiveRequestedBranchRunner`
and `LegacyFSMCompatibilityDecisionBackend` each build the input once from
`PrimitiveDecisionContext`, `PrimitiveBackendFactsAccess`, and
`PrimitiveDecisionCompatibilityActions`, then pass the same input identity
through their ordered branches. Branch dataclasses now store only static config
and implement `decide_input(input)`; they no longer store facts source or
compatibility actions. The residual pre-dig-align adapter explicitly rereads
common facts after its already-applied compatibility mutation through
`rebuild_common_facts_after_compatibility_action()`. This closes the per-tick
branch input gap, but `PrimitiveDecisionRuntimePorts` still exposes a
`legacy_fsm_branch_set` factory rather than a backend factory or registry
contract, so alternate-backend readiness remains future work.

Current status note after Phase 9.43: `PrimitiveDecisionRuntimePorts` now
exposes `backend_factories`, a backend-name keyed registry of backend factory
builders. `PrimitiveDecisionRuntime` normalizes the configured backend name,
selects a factory from that registry, and calls the factory's requested or
legacy-compatibility backend. `LegacyFSMDecisionBackendFactory` in
`testbed/planner/primitive_backend.py` owns legacy FSM branch-set
construction/reuse and requested/compatibility backend construction. The policy
shell now provides the default registry through `_legacy_fsm_backend_factory()`
instead of passing a `legacy_fsm_branch_set` callable to the runtime. This
removes the legacy branch-set dependency from the runtime port shape, but the
only registered and supported backend remains `legacy_fsm`; BT/VLM/LLM remain
unsupported parked scope.

Current status note after Phase 9.44: mutable dig/return token runtime state is
now owned by `PrimitiveTokenRuntimeState` in
`testbed/planner/primitive_token_state.py`. Reset creates a fresh token state
and applies it before legacy token private field names, so those compatibility
names write through property setters into the same state object. The owner
covers dig-cut and dig-depth-profile tokens, return target/relocate/
start-envelope tokens, token source/fallback/prior-bound fields, return
start-envelope prior flags, and pending next-dig raw/token/exemplar fields.
Observation-injection flags now live in `PrimitiveObservationInjectionRuntimeState`;
cell-entry compatibility state, coverage state, return handoff state, token
runtime sequencing, and token planning algorithms remain in their existing
focused owners.

Current status note after Phase 9.45: mutable non-token return handoff/runtime
cache state is now owned by `PrimitiveReturnRuntimeState` in
`testbed/planner/primitive_return_state.py`. Reset creates a fresh return state
and applies it through `_return_state`; legacy private fields such as
`_return_step_count`, `_return_to_dig_entry_close_state`,
`_return_next_dig_event_seen`, and
`_return_to_dig_start_envelope_checks` are property-backed compatibility
facades over the same owner. This state owner does not absorb return-target
token fields, coverage fields, return handoff algorithms, or direct-handoff
effect sequencing.

Current status note after Phase 9.46: mutable confirmed-live 4P cycle/progress
state is now owned by `PrimitiveCycleRuntimeState` in
`testbed/planner/primitive_cycle_state.py`. Reset creates a fresh cycle state
and applies `_cycle_state` before legacy cycle/progress private field names;
fields such as `_dump_ready_hold_count`, `_dump_done_hold_count`,
`_dig_step_count`, `_dig_best_mass_kg`, `_dig_to_carry_reason`,
`_completed_transition_count`, `_transition_timeout_count`, `_cycle_index`, and
`_dump_start_deposited_mass_kg` are now property-backed compatibility facades
over the same owner. The owner does not absorb active skill/switch reason,
previous action, token state, return state, coverage state, pre-dig-align
state, cell-entry compatibility state, backend facts, or report schemas.

Current status note after Phase 9.47: scripted bootstrap runtime state and
runtime rules are now owned by `PrimitiveScriptedBootstrapRuntimeState` and
`PrimitiveScriptedBootstrapRuntimeService` in
`testbed/planner/primitive_scripted_bootstrap.py`. Reset creates a fresh
scripted bootstrap state and applies it before legacy scripted counter private
field names; `_scripted_bootstrap_step_count`,
`_scripted_bootstrap_hold_count`, and `_scripted_bootstrap_timeout_count` are
property-backed compatibility facades over that owner. The service owns
scripted-qpos enabled detection, target-reached hold gating, max-step timeout
completion, missing-target runtime error text, and clipped float32 PD action
generation. Non-scripted bootstrap modes, residual `pre_dig_align`, cell-entry
compatibility/report state, token/return/cycle/coverage state owners,
BT/VLM/LLM support, and removed 5P runtime remain unchanged.

Current status note after Phase 9.48: execution lifecycle metadata is now owned
by `PrimitiveExecutionRuntimeState` in
`testbed/planner/primitive_execution_state.py`. Reset creates a fresh execution
state with the selected initial skill, `switch_reason="reset"`, and
`prev_action=None`; `PrimitivePlannerRuntimeKernel.reset()` still finalizes the
initial compact debug state after applying the reset state. The policy keeps
`_skill_name`, `_switch_reason`, `_prev_action`, and `_debug_state` as
property-backed compatibility facades.

Current status note after Phase 9.49: per-observation token injected
compatibility flags are now owned by `PrimitiveObservationInjectionRuntimeState`
in `testbed/planner/primitive_observation.py`. Reset creates a fresh
observation-injection state and applies it through `_observation_injection_state`;
the old `_cell_entry_token_injected`, `_dig_cut_token_injected`,
`_dig_depth_profile_token_injected`, `_return_target_token_injected`,
`_return_relocate_token_injected`, and
`_return_start_envelope_token_injected` names are property-backed facades.
`PrimitivePolicyObservationAssembler` still owns provider order, key names,
copy/no-copy behavior, and immutable `PrimitiveTokenInjectionState` projection;
token schema, `cell_entry`, and `pre_dig_align` behavior remain unchanged.

Current status note after Phase 9.50: parked cell-entry compatibility/report
storage is now owned by `PrimitiveCellEntryCompatibilityRuntimeState` in
`testbed/planner/primitive_cell_entry_state.py`. Reset creates a fresh
cell-entry state and applies it through `_cell_entry_state`; the old
`_cell_entry_goal`, `_cell_entry_goal_cycle_id`, `_cell_entry_audit`,
`_cell_entry_tokens`, `_cell_entry_seen_cell_id`, and `_cell_entry_trace` names
are property-backed facades. `cell_entry` planner/auditor algorithms, token
dimensions, token key names, token values, and report/trace schemas remain
unchanged, and `cell_entry` remains parked compatibility/report material rather
than a mainline backend capability.

Current status note after Phase 9.51: parked pre-dig-align
compatibility/report storage is now owned by
`PrimitivePreDigAlignCompatibilityRuntimeState` in
`testbed/planner/primitive_pre_dig_align_state.py`. Reset creates a fresh
pre-dig-align compatibility state and applies it through
`_pre_dig_align_state`; the old `_pre_dig_align_step_count`,
`_pre_dig_align_hold_count`, `_pre_dig_align_timeout_count`,
`_pre_dig_align_completed_count`, `_pre_dig_align_replan_count`,
`_pre_dig_align_target_qpos`, `_pre_dig_align_error`,
`_pre_dig_align_entry_error_m`, `_pre_dig_align_start_envelope_ready`,
`_pre_dig_align_entry_close_handoff_ready`,
`_pre_dig_align_entry_intent_handoff_ready`,
`_pre_dig_align_timeout_handoff_reason`,
`_pre_dig_align_surface_depth_m`, `_pre_dig_align_surface_guard_triggered`,
and `_pre_dig_align_surface_guard_count` names are property-backed facades.
The parked readiness, timeout, target, surface-guard, and PD action algorithms
remain in the policy shell; `pre_dig_align` remains residual parking/action
material rather than a mainline backend capability.

Current status note after Phase 9.52: coverage debug-field public schema
assembly is now owned by `CoverageReportService.debug_fields(...)` in
`testbed/planner/primitive_coverage_reports.py`. `CoverageDebugReportInputs`
captures explicit coverage report values, and
`PrimitivePlannerACTPolicy._debug_report_coverage_fields()` now remains a thin
compatibility facade that builds the snapshot and delegates to the service.
Coverage corridor debug payloads and coverage decision-event payloads remain in
the same report service. Coverage selection, scoring, effect/runtime updates,
candidate generation, public key names, scalar conversions, `NaN`/`-1`
fallbacks, and list projection semantics remain unchanged.

Current status note after Phase 9.53: parked cell-entry debug-field public
schema projection is now owned by
`PrimitiveCellEntryCompatibilityRuntimeState.debug_fields()` in
`testbed/planner/primitive_cell_entry_state.py`.
`PrimitivePlannerACTPolicy._debug_report_cell_entry_fields()` remains a thin
compatibility facade that delegates to the state owner. Cell-entry token
generation, token dimensions, planner/auditor algorithms, trace mutation,
reset semantics, and public debug key/fallback values remain unchanged. This
phase is accepted as a small cleanup of the parked compatibility/report owner,
but it is not a template for continuing parked-path micro-slices.

Current status note after Phase 9.54: live token-status projection is now owned
by `PrimitiveTokenRuntimeState.to_token_status(...)` in
`testbed/planner/primitive_token_state.py`.
`PrimitivePlannerACTPolicy._token_status_for_debug_report()` remains a thin
compatibility facade that supplies explicit external facts: cell-entry
enablement, current observation-injection flags, dig-depth-profile source, and
dig-depth-profile required state. The projection uses central token dimension
constants and still relies on `TokenStatus.from_inputs(...)` for token array
copy/freeze behavior. Token debug key names, token list values, source/fallback
fields, injected flags, dimensions, observation provider order, token planning
services/coordinators, `cell_entry`, `pre_dig_align`, backend fail-fast, and
removed 5P runtime status remain unchanged.

Hard constraint for future conclusions and executor prompts: protection is a
constraint, not the objective. Each next slice must be the most effective
bounded move toward the interface standard, not merely the safest smallest
cleanup. If a candidate only moves a tiny compatibility dictionary or facade
without reducing a broader stable boundary, the refactor thread must stop,
state that risk explicitly in its conclusion, and choose a larger bounded
target before dispatch.

The current implementation route is **Slice 7: Move Legacy FSM Behind Backend
Protocol**. Slice 4 status records have been established through `TokenStatus`;
Phase 5.1 has extracted the goal token provider; Phase 5.2 has extracted dig-cut
token planning result construction; Phase 5.3 has extracted dig-depth-profile
token planning; Phase 5.4 has extracted return-target token planning result
construction; Phase 5.5 has extracted return-relocate token planning; Phase 5.6
has extracted return-start-envelope token planning; Phase 6.1 has extracted
coverage corridor candidate construction; Phase 6.2 has extracted coverage
scoring/selection; Phase 6.3 has extracted coverage completion/rejection state
updates; Phase 6.4 has extracted coverage terminal-stop and multi-pass reopen
request ownership; Phase 6.5 has extracted coverage corridor debug and
decision-event payload projection; Phase 7.1 has introduced the legacy FSM
backend protocol/adapter boundary without moving branch bodies; Phase 7.2 has
migrated only the 4P bootstrap branch behind the backend adapter; Phase 7.3 has
migrated only the 4P dig branch behind the backend adapter; Phase 7.4 has
migrated only the 4P carry branch behind the backend adapter; Phase 7.5 has
migrated only the 4P dump branch behind the backend adapter; Phase 7.6 has
migrated only the 4P return branch behind the backend adapter; Phase 7.7 has
audited the residual 4P `_maybe_switch_skill()` shell and legacy parking
boundary. The confirmed-live mainline branches now delegate to backend branch
objects in the original order. The remaining inline 4P branch body is
`pre_dig_align`, which stays legacy parking because the selected successful
evidence packet classifies `gate.pre_dig_align` as
`dead-candidate` / `retain-legacy-parking`.

Stop further Slice 7 code migration at this verified boundary unless the user
approves a new scope. The 5P runtime compatibility audit has been resolved by
the Phase 9.32 cleanup-approved removal of `PrimitivePlannerACT5PPolicy`; old
behavior remains available only through git history. Valid remaining scopes are
legacy pre-dig parking cleanup/reclassification, direct-handoff helper
extraction, backend selection cleanup, or a focused audit of any remaining
policy-owned storage.
Do not move `pre_dig_align`, direct-handoff helper internals, change branch
order, change reason strings, or apply unrelated effects through the backend
boundary without that separate evidence and compatibility decision.

The next approved planning scope is Phase 8 effect-boundary design, recorded in
`docs/planner_effect_boundary_design.md`. It should govern later return
direct-handoff, legacy parking, and backend-selection work by
classifying each path as facts, decision, requested effect, reporting,
compatibility, or legacy parking before any code migration.
