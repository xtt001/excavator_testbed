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
| `testbed/policies/hybrid/primitive_planner.py` | 6516 | real planner source of truth, public policy adapter, inline FSM, tokens, coverage, reports |
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
| 149-841 | public adapter construction and config normalization | `__init__` | policy objects, config scalars, token config, coverage config, pre-dig config | public adapter plus kernel construction |
| 842-967 | reset lifecycle | `reset` | low-level policy resets, boundary detector, active skill, counters, token state, return state, coverage state | execution kernel reset plus public adapter facade |
| 968-1012 | public tick template | `predict` | `_prev_action`, boundary event, `_skill_name`, `_switch_reason`, debug state | first extraction slice: explicit execution kernel template |
| 1014-1549 | public reporting | `debug_state`, `rollout_summary`, `planner_trace` | debug state, token flags, coverage fields, summary counters | reporting boundary, not decision backend |
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
| 6083-6505 | 5P compatibility planner | `PrimitivePlannerACT5PPolicy` overrides | 5P approach/dump-release states and policy mapping | compatibility owner, not mainline architecture |

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
| `compat.5p_policy` | compatibility | retain-compatibility | `PrimitivePlannerACT5PPolicy` | compatibility owner |
| `token.cell_entry` | dead-candidate | retain-legacy-parking | `_cell_entry_tokens_for_obs` | legacy diagnostic parking |
| `gate.pre_dig_align` | dead-candidate | retain-legacy-parking | `_maybe_switch_skill` pre-dig branch | legacy diagnostic/action parking |

## Target Architecture

The target boundary is:

```text
PrimitivePlannerACTPolicy
  -> PrimitivePlannerExecutionKernel
      -> PrimitiveCapabilityPort
      -> PrimitiveDecisionBackend
      -> PrimitiveDecisionResult
      -> PlannerEffect application
      -> action dispatch and reporting
```

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
- keep 5P compatibility as a compatibility owner

### Execution Kernel

Candidate file: `testbed/planner/primitive_execution.py`.

The first code phase should introduce an execution kernel without changing the
decision source of truth. It may initially call the old `_maybe_switch_skill()`
body through a thin bridge while the public tick order is made explicit.

Conceptual methods:

```python
class PrimitivePlannerExecutionKernel:
    def reset(self) -> None: ...
    def prepare_tick(self, obs: Mapping[str, object]) -> PrimitiveTickPreparation: ...
    def decide_tick(self, preparation: PrimitiveTickPreparation) -> PrimitiveDecisionResult: ...
    def apply_decision(self, result: PrimitiveDecisionResult) -> None: ...
    def dispatch_action(self, obs: Mapping[str, object]) -> np.ndarray: ...
    def finalize_tick(
        self,
        *,
        action: np.ndarray,
        preparation: PrimitiveTickPreparation,
        decision: PrimitiveDecisionResult,
    ) -> np.ndarray: ...
```

Kernel-owned effects:

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

The backend may request these effects. Only the kernel applies them.

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
- rollout summary keeps current aggregate fields stable
- planner trace owns structured evidence/debug payloads
- report-only fields can read kernel state but must not drive backend decisions

## Legacy Parking Catalog

Parking means the code is retained but kept out of the mainline architecture.
Parked code must not be used as a justification for new mainline services.

| Path | Evidence | Current code owner | Parking owner | Allowed use | Not allowed |
| --- | --- | --- | --- | --- | --- |
| `token.cell_entry` | absent from successful rollout; `cell_entry_enabled=0`; no `cell_entry_tokens` low-dim key | `_cell_entry_tokens_for_obs`, `_complete_cell_entry_dig`, `testbed/planner/cell_entry.py` | `LegacyCellEntryDiagnostics` or compatibility notes | old configs, diagnostics, explicit legacy replay | default token contract, new backend fact, VLM decision packet |
| `gate.pre_dig_align` | successful rollout has `pre_dig_align.enabled=false`; completed/timeout counts are zero | pre-dig branch in `_maybe_switch_skill`, `_pre_dig_align_*`, `_pre_dig_align_action` | `LegacyPreDigAlignAdapter` or diagnostic note | explicit legacy config, old PD alignment replay, debug comparison | default FSM path, behavior-tree node, VLM effect unless re-approved |
| `PrimitivePlannerACT5PPolicy` | not mainline evidence, but public compatibility owner | 5P subclass | compatibility owner | old 5P configs and tests | source of default 4P architecture |

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
| compatibility | `PrimitivePlannerACTPolicy` constructor/config and 5P public class remain importable | every public-surface slice |
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
approves a new scope. Valid next scopes are a legacy pre-dig parking extraction,
5P compatibility audit, direct-handoff helper extraction, or backend selection
cleanup. Do not move `pre_dig_align`, the 5P override, direct-handoff helper
internals, change branch order, change reason strings, or apply unrelated
effects through the backend boundary without that separate evidence and
compatibility decision.

The next approved planning scope is Phase 8 effect-boundary design, recorded in
`docs/planner_effect_boundary_design.md`. It should govern later return
direct-handoff, 5P compatibility, legacy parking, and backend-selection work by
classifying each path as facts, decision, requested effect, reporting,
compatibility, or legacy parking before any code migration.
