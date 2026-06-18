# Planner Backend Interface Migration Design

## Purpose

Migrate the default primitive planner toward a backend-neutral runtime so the
same planner semantics can be executed by the legacy finite-state machine,
behavior tree, or later higher-level decision architectures.

This design is behavior-preserving. It must not change thresholds, branch order,
switch reasons, terminal reasons, token contracts, debug/rollout schemas,
checkpoint compatibility, or policy reset timing.

## Current Backup Point

Before this design was written, the current branch state was backed up in git:

- branch: `fs/v2_4-refactor-tests`
- backup branch: `backup/planner-backend-migration-base-2026-06-17`
- backup tag: `planner-backend-migration-base-2026-06-17`
- commit: `526d9ad3e9ff1804a18842dd352d8b30e82c108a`

The branch, backup branch, and tag were pushed to `origin`.

## Problem

`PrimitivePlannerACTPolicy` is still the default planner and remains large
because it currently combines these roles:

- public `Policy` adapter and config entry point
- active skill lifecycle and switch reason ownership
- runtime state storage through many `self._xxx` fields
- state-machine branch order and transition orchestration
- service construction and service call order
- low-level ACT policy dispatch and reset timing
- token assembly, token source/fallback flags, and injection state
- debug, trace, and rollout compatibility assembly
- compatibility facades for tests and legacy diagnostics

`PrimitiveActionTreeRunner` is much smaller because it is shadow-only and calls
existing private planner methods. It is not yet an independent backend.

The architecture needs an explicit boundary where planner backends return
decisions/effects instead of directly reading or writing `policy._xxx`.

## Design Goals

- Make `legacy_fsm`, `behavior_tree`, and future planners use the same runtime
  context, blackboard, capability services, and effect application path.
- Move planner state from ad hoc shell private fields toward explicit blackboard
  state objects.
- Keep `PrimitivePlannerACTPolicy` as a compatibility adapter while gradually
  moving the default planner onto the backend interface.
- Preserve current behavior at every migration step with golden trace, debug
  schema, token contract, and direct service-versus-facade parity tests.

## Non-Goals

- Do not make behavior tree the default in the first implementation phase.
- Do not rewrite all planner logic in a new backend.
- Do not duplicate gate, token, coverage, profile, or debug semantics across
  backends.
- Do not delete compatibility facades until tests no longer need them.
- Do not change 5P semantics; 5P remains compatibility-only.

## Recommended Approach

Use a backend-neutral runtime with explicit context, blackboard, tick result, and
runtime effects.

```text
PrimitivePlannerACTPolicy
  public Policy adapter
  owns config, reset/predict compatibility, low-level policy dispatch,
  debug/rollout compatibility, and effect application

PlannerRuntime
  builds PlannerTickContext from obs, boundary event, blackboard, typed backend
  ports, policies, and compatibility config

PlannerBackend
  LegacyStateMachineBackend
  BehaviorTreeBackend
  future DecisionTreeBackend / OptionSchedulerBackend

Capabilities
  coverage, dig lifecycle, dump lifecycle, return handoff, return transition,
  pre-dig alignment, token builders, reporting
```

The backend interface should be stable and small:

```python
class PlannerBackend(Protocol):
    name: str

    def tick(self, context: PlannerTickContext) -> PlannerTickResult:
        ...
```

Backends must not mutate `PrimitivePlannerACTPolicy`. They should return a
result:

```python
@dataclass(frozen=True)
class PlannerTickResult:
    node_path: tuple[str, ...]
    status: str
    reason: str
    effects: tuple[PlannerRuntimeEffect, ...]
    diagnostics: Mapping[str, object]
```

Effects are applied by the adapter/runtime layer:

- `SetSkill`
- `ResetPolicy`
- `UpdateCounter`
- `HoldToken`
- `ClearPendingPlan`
- `ApplyCoverageState`
- `ApplyPendingDigCutPlan`
- `ApplyPreDigAlignState`
- `RecordTrace`
- `RequestTerminalStop`
- `DispatchLowLevelPolicy`

## Alternatives Considered

### Thin Interface Around Current Planner

Add a `PlannerBackend` class that simply calls existing `policy._xxx` methods.

This is too weak. It would preserve the same private shell dependency and would
not let behavior-tree nodes run without `PrimitivePlannerACTPolicy`.

### Full Behavior Tree Rewrite

Build a behavior tree that directly owns all planner logic.

This is too risky. It would duplicate thresholds, token semantics, branch order,
switch reasons, and debug schema logic. It would likely create a second large
planner instead of solving the boundary problem.

### Backend-Neutral Runtime And Effects

Create small runtime/effect contracts first, then migrate one state domain at a
time. This is the recommended path because it reuses current capability services
and provides parity tests at every step.

## State Boundary

Introduce `PlannerBlackboard` incrementally. It should eventually own:

- active skill, switch reason, cycle index
- transition counters and timeout state
- dig, carry, dump, return runtime state
- pre-dig-align runtime state
- coverage runtime state or reference to coverage-specific state
- pending dig-cut, return-target, return-relocate, and depth-profile state
- token source, fallback, in-prior, and injected flags

Confirmed decision: coverage runtime state remains in `CoverageServiceState`
and is referenced by the blackboard during the initial migration phases. Do not
copy coverage fields into a generic blackboard until there is a specific
behavior-preserving reason and parity coverage for that move.

## Migration Phases

### Phase 1: Runtime Contract Skeleton

Add `PlannerTickContext`, `PlannerTickResult`, `PlannerRuntimeEffect`, and
`PlannerBackend` under the package `testbed/planner/runtime/`. Add tests for
construction, immutability where appropriate, and effect ordering.

Default runtime behavior remains unchanged.

#### Phase 1 Landing Record 2026-06-17

Implemented files:

- `testbed/planner/runtime/contracts.py`: backend-neutral
  `PlannerTickContext`, `PlannerRuntimeEffect`, `PlannerTickResult`, and
  `PlannerBackend` contracts.
- `testbed/planner/runtime/__init__.py`: package-level exports for the runtime
  contracts.
- `tests/test_planner_runtime_contracts.py`: contract tests for construction,
  immutable mapping copies, effect ordering, hashability where appropriate, and
  runtime-checkable backend protocol shape.

Scope guardrails kept:

- No `_maybe_switch_skill()` migration.
- No default planner behavior or config wiring changes.
- No `primitive_scheduler_runner` / `planner_backend` alias implementation.
- No edits to `PrimitivePlannerACTPolicy` or `PrimitiveActionTreeRunner`.
- `PlannerTickContext.coverage_state` references `CoverageServiceState`; coverage
  fields were not copied into a generic blackboard.

Verification run for this landing record:

- `pytest tests/test_planner_runtime_contracts.py -q` -> `4 passed`.
- `pytest -q tests/test_planner_golden_traces.py tests/test_primitive_action_tree.py tests/test_dig_coverage_contracts.py`
  -> `48 passed`.
- `git diff --check` -> no whitespace errors in tracked diff.
- `git diff --check --no-index /dev/null <new runtime/test file>` -> no
  whitespace errors in the new files.

#### PlannerBlackboard Skeleton Record 2026-06-18

Implemented files:

- `testbed/planner/runtime/blackboard.py`: added the first typed
  `PlannerBlackboard` contract as a frozen snapshot with only the default FSM
  tick state currently needed by the backend boundary: `current_skill`,
  `switch_reason`, `cycle_index`, `completed_transition_count`, and
  `transition_timeout_count`.
- `testbed/planner/runtime/contracts.py`: changed
  `PlannerTickContext.blackboard` from a generic mapping to
  `PlannerBlackboard` and rejects untyped dict blackboards.
- `testbed/planner/runtime/legacy_fsm.py`: changed the legacy backend to read
  `context.blackboard.current_skill` instead of dict-style `skill_name`.
- `testbed/policies/hybrid/primitive_planner.py`: thin adapter wiring only;
  `_legacy_fsm_tick_context()` builds `PlannerBlackboard` from existing shell
  fields while keeping `coverage_state=self.coverage_service.state` as a
  separate reference.
- `tests/test_planner_runtime_contracts.py`, `tests/test_legacy_fsm_backend.py`,
  and `tests/test_behavior_tree_backend_contract.py`: added and updated
  contract tests for typed blackboard construction, immutability/hashability,
  context rejection of old dict blackboards, and backend branch selection from
  `current_skill`.

Scope guardrails kept:

- No `_maybe_switch_skill()` branch order, thresholds, reason strings, policy
  reset timing, token source, debug schema, rollout schema, or default backend
  behavior changed.
- No dig/dump/return runtime state, token flags, pending-plan state, metadata,
  diagnostics, or coverage fields were added to `PlannerBlackboard`.
- `CoverageServiceState` remains referenced by `PlannerTickContext.coverage_state`
  and is not copied into the blackboard.
- `BehaviorTreeBackend` remains experimental/fail-closed; only its test context
  construction was updated to the typed blackboard contract.

Verification run for this cleanup:

- Initial RED:
  `python -m pytest -q tests/test_planner_runtime_contracts.py tests/test_legacy_fsm_backend.py tests/test_behavior_tree_backend_contract.py`
  failed during collection because `PlannerBlackboard` did not exist yet.
- `python -m pytest -p no:cacheprovider -q tests/test_planner_runtime_contracts.py tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_effects.py tests/test_legacy_fsm_backend_return.py tests/test_behavior_tree_backend_contract.py tests/test_planner_backend_config.py`
  -> `60 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_planner_golden_traces.py tests/test_primitive_action_tree.py tests/test_primitive_scheduler_facades.py`
  -> `141 passed`.

#### PlannerBlackboard Lifecycle Ownership Record 2026-06-18

Implemented files:

- `testbed/planner/runtime/blackboard.py`: added immutable update methods for
  planner lifecycle state: `with_skill()`, `with_switch_reason()`,
  `with_transition_timeout_increment()`, and
  `with_return_transition_counts()`.
- `testbed/policies/hybrid/primitive_planner.py`: made
  `self._planner_blackboard` the canonical owner for active skill, switch
  reason, primitive cycle index, completed transition count, and transition
  timeout count. The previous private fields remain as property shims for tests,
  diagnostics, and compatibility callers.
- `PrimitivePlannerACTPolicy.reset()`, `predict()`, `_set_skill()`,
  `_restart_pre_dig_align()`, `_restart_dig_with_new_cut()`,
  `_apply_failed_dig_stop_state()`, and
  `_apply_return_to_dig_transition_runtime_projection()` now update lifecycle
  state through `PlannerBlackboard` snapshots.
- `PrimitivePlannerACTPolicy._legacy_fsm_tick_context()` now passes the
  canonical `self._planner_blackboard` into `PlannerTickContext` instead of
  constructing a per-tick shadow copy.
- `tests/test_planner_runtime_contracts.py` and
  `tests/test_legacy_fsm_backend.py`: added tests for blackboard update methods,
  old private-field compatibility shims, reset initialization, and context
  identity with the canonical blackboard.

Scope guardrails kept:

- No `_maybe_switch_skill()` branch order, thresholds, reason strings, policy
  reset timing, token source, debug schema, rollout schema, default backend
  behavior, or behavior-tree wiring changed.
- No coverage state, dig/dump/return runtime state, token flags, pending
  dig-cut state, return-target state, depth-profile state, metadata, or
  diagnostics were moved into `PlannerBlackboard`.
- `PrimitivePlannerACTPolicy` remains the adapter, compatibility owner,
  low-level policy dispatch owner, and runtime effect applier.
- `planner_backend` remains the canonical config key; the removed
  `primitive_scheduler_runner` key remains rejected.

Verification run for this ownership pass:

- Initial RED:
  `python -m pytest -q tests/test_planner_runtime_contracts.py tests/test_legacy_fsm_backend.py`
  failed because `PlannerBlackboard` had no lifecycle update methods and the
  policy private fields still owned the lifecycle values.
- `python -m pytest -q tests/test_planner_runtime_contracts.py tests/test_legacy_fsm_backend.py`
  -> `29 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_planner_runtime_contracts.py tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_effects.py tests/test_legacy_fsm_backend_return.py`
  -> `45 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_planner_golden_traces.py tests/test_primitive_action_tree.py tests/test_primitive_scheduler_facades.py`
  -> `141 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_primitive_planner_debug_schema.py`
  -> `26 passed`.

#### PlannerBlackboard Transition Runtime Ownership Record 2026-06-18

Implemented files:

- `testbed/planner/runtime/blackboard.py`: extended typed
  `PlannerBlackboard` with the first transition runtime state fields needed by
  the default FSM backend: `return_step_count`,
  `return_next_dig_event_seen`, `dump_ready_hold_count`, and
  `dump_done_hold_count`. Added immutable update methods for return tick
  counting, return-to-dig event latch updates, and dump hold-count updates.
- `testbed/planner/runtime/legacy_fsm.py`: changed carry, dump, and return
  transition requests to read those transition runtime values directly from
  `context.blackboard` instead of adapter-provided service lambdas.
- `testbed/policies/hybrid/primitive_planner.py`: kept the old private fields
  as property shims while making `self._planner_blackboard` the canonical
  owner for return step count, return next-dig latch, dump-ready hold count,
  and dump-done hold count. Reset, skill-switch, dump runtime, carry runtime,
  and return-to-dig runtime projection paths update the blackboard snapshot.
- `tests/test_planner_runtime_contracts.py`,
  `tests/test_legacy_fsm_backend.py`, and
  `tests/test_legacy_fsm_backend_return.py`: added/updated contract and
  backend tests proving typed transition runtime construction, immutable
  updates, private-field shim compatibility, and backend reads from
  `PlannerBlackboard` instead of service callbacks.

Scope guardrails kept:

- No `_maybe_switch_skill()` branch order, thresholds, reason strings, policy
  reset timing, token source, debug schema, rollout schema, default backend
  behavior, or behavior-tree wiring changed.
- Coverage state remains `PlannerTickContext.coverage_state`; it was not
  copied into `PlannerBlackboard`.
- No pending dig-cut state, return-target state, depth-profile state, token
  injection flags, metadata, or diagnostics were moved into
  `PlannerBlackboard`.
- `PrimitivePlannerACTPolicy` remains the adapter, compatibility owner,
  low-level policy dispatch owner, and runtime effect applier.
- The removed `primitive_scheduler_runner` key remains rejected; this slice did
  not add compatibility aliases.

Verification run for this ownership pass:

- Initial RED:
  `python -m pytest -p no:cacheprovider -q tests/test_planner_runtime_contracts.py tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_return.py`
  -> `13 failed, 22 passed` because `PlannerBlackboard` did not yet expose the
  transition runtime fields and backend tests no longer provided old service
  callbacks.
- `python -m pytest -p no:cacheprovider -q tests/test_planner_runtime_contracts.py tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_return.py`
  -> `35 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_planner_runtime_contracts.py tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_effects.py tests/test_legacy_fsm_backend_return.py`
  -> `46 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_planner_golden_traces.py tests/test_primitive_action_tree.py tests/test_primitive_scheduler_facades.py`
  -> `141 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_primitive_planner_debug_schema.py tests/test_behavior_tree_backend_contract.py tests/test_planner_backend_config.py`
  -> `45 passed`.
- `python -m compileall -q testbed/planner/runtime/blackboard.py testbed/planner/runtime/legacy_fsm.py testbed/policies/hybrid/primitive_planner.py tests/test_planner_runtime_contracts.py tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_return.py`
  -> no output.
- `git diff --check` -> no whitespace errors.

#### Policy Observation Token Runtime Ownership Record 2026-06-18

Implemented files:

- `testbed/planner/runtime/conditioning.py`: added typed
  `PlannerConditioningState` for policy-observation token runtime ownership.
  The state composes existing domain state contracts instead of redefining
  token semantics: `DigCutRuntimeState`, `DigDepthProfileRuntimeState`, and
  `ReturnTargetConditioningRuntimeState`, plus the cell-entry injection flag.
- `testbed/planner/runtime/__init__.py`: exports `PlannerConditioningState`.
- `testbed/policies/hybrid/primitive_planner.py`: added
  `self._planner_conditioning_state` as the canonical owner for dig-cut,
  dig-depth-profile, return-target, return-relocate, return-start-envelope,
  pending dig-cut, and policy-observation injection runtime fields. The old
  private `_xxx` fields remain property shims for compatibility tests,
  diagnostics, and existing adapter callers.
- `PrimitivePlannerACTPolicy._apply_policy_observation_assembly()` now updates
  injection flags through `PlannerConditioningState` instead of writing six
  shell fields directly.
- Reset/apply entry points for dig-cut runtime state, dig-depth-profile runtime
  state, and return-target conditioning runtime state now update typed
  conditioning state. Return-target conditioning still calls the existing
  service pending-plan projection to preserve pending dig-cut projection
  semantics and copy/cast behavior.
- `tests/test_planner_runtime_contracts.py` and
  `tests/test_primitive_scheduler_facades.py`: added contract and adapter tests
  for typed conditioning defaults, runtime-state copy behavior,
  policy-observation assembly updates, and old private-field shim compatibility.

Scope guardrails kept:

- No token contract key, token order, token dimension, low-dimensional key,
  debug schema, rollout schema, reason string, branch order, policy reset
  timing, default backend, or behavior-tree wiring changed.
- Token request/gating remains owned by `PolicyObservationAssembler`; source
  and fallback-string generation remains in the existing capability services
  and builders.
- Coverage state and `_coverage_active_state_exemplar_*` stay outside
  `PlannerConditioningState`; coverage remains referenced through
  `CoverageServiceState`.
- Old private field direct-assignment compatibility is preserved. Runtime
  service apply paths still copy/cast arrays to `float32`; direct private
  shim assignment still preserves object identity where existing facade tests
  require it.

Verification run for this ownership pass:

- Initial RED:
  `python -m pytest -p no:cacheprovider -q tests/test_planner_runtime_contracts.py tests/test_primitive_scheduler_facades.py::test_policy_observation_assembly_apply_updates_injection_flags tests/test_primitive_scheduler_facades.py::test_policy_conditioning_private_fields_are_runtime_state_shims`
  failed during collection because `PlannerConditioningState` did not exist.
- After adding `PlannerConditioningState`, the same RED set failed because
  `PrimitivePlannerACTPolicy` had no canonical `_planner_conditioning_state`
  and old private token fields were still plain shell attributes.
- `python -m pytest -p no:cacheprovider -q tests/test_planner_runtime_contracts.py tests/test_primitive_scheduler_facades.py::test_policy_observation_assembly_apply_updates_injection_flags tests/test_primitive_scheduler_facades.py::test_policy_conditioning_private_fields_are_runtime_state_shims`
  -> `13 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_planner_runtime_contracts.py tests/test_policy_observation.py tests/test_dig_cut_plan_facade.py tests/test_return_target_conditioning_token_facade.py tests/test_return_target_pending_activation_facade.py tests/test_primitive_scheduler_conditioning_facades.py`
  -> `66 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_primitive_scheduler_facades.py tests/test_primitive_planner_debug_schema.py`
  -> `147 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_planner_runtime_contracts.py tests/test_policy_observation.py tests/test_dig_cut_plan_facade.py tests/test_return_target_conditioning_token_facade.py tests/test_return_target_pending_activation_facade.py tests/test_primitive_scheduler_conditioning_facades.py tests/test_primitive_scheduler_facades.py tests/test_primitive_planner_debug_schema.py tests/test_eval_rollout_records.py`
  -> `217 passed, 1 warning` from existing `datetime.utcnow()` deprecation in
  `testbed/eval/rollout_logs.py`.
- `python -m pytest -p no:cacheprovider -q tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_effects.py tests/test_legacy_fsm_backend_return.py tests/test_planner_golden_traces.py tests/test_primitive_action_tree.py tests/test_behavior_tree_backend_contract.py tests/test_planner_backend_config.py`
  -> `77 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_primitive_token_contracts.py tests/test_policy_data_contracts.py tests/test_config_semantic_matrix.py`
  -> `25 passed, 1 warning` from existing `datetime.utcnow()` deprecation in
  `testbed/data/dataset.py`.
- `python -m compileall -q testbed/planner/runtime/conditioning.py testbed/planner/runtime/__init__.py testbed/policies/hybrid/primitive_planner.py tests/test_planner_runtime_contracts.py tests/test_primitive_scheduler_facades.py`
  -> no output.
- `git diff --check` -> no whitespace errors.

#### Typed Backend Ports Boundary Record 2026-06-18

Implemented files:

- `testbed/planner/runtime/ports.py`: added the typed backend dependency
  boundary. `PlannerBackendPorts` is the tick-context port bundle, and
  `LegacyFsmBackendPorts` groups the default FSM dependencies into stable
  semantic ports: `skill_names`, `bootstrap_transition`, `pre_dig_alignment`,
  `dig_transition`, `dump_lifecycle`, `return_transition`, and
  `boundary_profile`.
- `testbed/planner/runtime/contracts.py`: replaced the old tick-context
  untyped service registry with
  `PlannerTickContext.ports: PlannerBackendPorts`. Passing the old `services=`
  keyword is now rejected by the dataclass constructor; the focused ports test
  covers this as the compatibility break for backend internals.
- `testbed/planner/runtime/legacy_fsm.py`: changed
  `LegacyStateMachineBackend` to read external dependencies through
  `context.ports.legacy_fsm` and typed semantic port fields instead of string
  lookups. The generic `run_legacy_fsm_transition` fallback remains only for
  contexts with no legacy-FSM port bundle or non-default active skills.
- `testbed/policies/hybrid/primitive_planner.py`: kept
  `_legacy_fsm_tick_context()` as thin adapter wiring. It constructs typed ports
  from existing constants, services, adapter callbacks, and config suppliers,
  then leaves side-effect application in `_apply_legacy_fsm_tick_result()`.
- `tests/test_planner_backend_ports.py`: added focused contract coverage for
  typed ports construction, rejection of the old `services` registry, and the
  dig branch gate order through typed ports. The duplicate dig projection case
  was moved out of `tests/test_legacy_fsm_backend.py` so that file stays below
  the 1000-line large-file threshold.

Scope guardrails kept:

- No branch order, thresholds, reason strings, policy reset timing,
  debug/trace/rollout schema, token contract, default backend selection, or
  behavior-tree default changed.
- At this boundary pass, `dig_to_carry_reason` remained an adapter-provided
  port because `_dig_to_carry_ready()` still owned the legacy reason write
  timing. The follow-up dig-to-carry decision port record below supersedes that
  interim shape.
- Return completion remains adapter-owned; the backend still returns only the
  return transition outcome/projection effect.
- Coverage state remains `PlannerTickContext.coverage_state`, and
  `PlannerBlackboard` / `PlannerConditioningState` remain the state owners for
  their existing domains. This slice did not migrate token contract/schema
  generation or coverage runtime state.

Verification run for this boundary pass:

- Initial RED:
  `python -m pytest -p no:cacheprovider -q tests/test_planner_backend_ports.py`
  failed during collection because the typed ports classes were not exported.
- Focused GREEN:
  `python -m pytest -p no:cacheprovider -q tests/test_planner_backend_ports.py tests/test_planner_runtime_contracts.py tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_return.py`
  -> `38 passed`.
- Backend/runtime/config/BT:
  `python -m pytest -p no:cacheprovider -q tests/test_planner_backend_ports.py tests/test_planner_runtime_contracts.py tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_effects.py tests/test_legacy_fsm_backend_return.py tests/test_planner_backend_config.py tests/test_behavior_tree_backend_contract.py`
  -> `68 passed`.
- Golden/action-tree/facade/debug schema:
  `python -m pytest -p no:cacheprovider -q tests/test_planner_golden_traces.py tests/test_primitive_action_tree.py tests/test_primitive_scheduler_facades.py tests/test_primitive_planner_debug_schema.py`
  -> `168 passed`.
- Token/data/config contract check:
  `python -m pytest -p no:cacheprovider -q tests/test_primitive_token_contracts.py tests/test_policy_data_contracts.py tests/test_config_semantic_matrix.py`
  -> `25 passed, 1 warning` from the existing `datetime.utcnow()` deprecation in
  `testbed/data/dataset.py`.
- `python -m compileall -q testbed/planner/runtime testbed/policies/hybrid/primitive_planner.py testbed/planner/primitive_action_tree.py tests/test_planner_backend_ports.py tests/test_planner_runtime_contracts.py tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_effects.py tests/test_legacy_fsm_backend_return.py`
  -> no output.
- `git diff --check` -> no whitespace errors.

#### Dig-To-Carry Decision Port Record 2026-06-18

Implemented files:

- `testbed/planner/runtime/ports.py`: replaced the default FSM dig transition
  port pair `dig_to_carry_ready` plus `dig_to_carry_reason` with one stable
  semantic port, `dig_to_carry_decision`. The provider returns the structural
  `DigToCarryDecision` protocol with explicit `ready` and `reason` fields,
  currently satisfied by the existing `DigGateDecision` produced by
  `DigLifecycleGateService`.
- `testbed/planner/runtime/__init__.py`: exports
  `DigToCarryDecision` and `DigToCarryDecisionProvider` with the other typed
  runtime port contracts.
- `testbed/planner/runtime/legacy_fsm.py`: changed the dig branch to consume
  `context.ports.legacy_fsm.dig_transition.dig_to_carry_decision(...)` and
  build the same `dig_to_carry_<reason>` transition projection from the returned
  decision. The earlier gate order is unchanged: exit guard, bad replan,
  complete-low-payload, then dig-to-carry decision.
- `testbed/policies/hybrid/primitive_planner.py`: kept adapter behavior thin by
  adding `_dig_to_carry_decision()` as the legacy lifecycle-service wiring
  point. The old `_dig_to_carry_ready()` method remains a compatibility facade
  for action-tree and diagnostic callers, and still updates
  `_dig_to_carry_reason` through the decision helper.
- `tests/test_planner_backend_ports.py`,
  `tests/test_legacy_fsm_backend.py`, and
  `tests/test_primitive_scheduler_facades.py`: updated focused backend-port and
  facade tests so backend-path tests assert the explicit decision object rather
  than relying on a ready callback followed by a separate reason callback.

Scope guardrails kept:

- No branch order, thresholds, reason strings, policy reset timing,
  debug/trace/rollout schema, token contract, default backend selection, or
  behavior-tree default changed.
- The backend still does not own dig lifecycle thresholds or facts assembly; it
  consumes the typed decision returned through the port and emits the existing
  dig transition runtime projection effect.
- `PrimitivePlannerACTPolicy` remains the adapter and effect applier. The new
  `_dig_to_carry_decision()` method only wires existing lifecycle service input
  and preserves the legacy reason write timing.
- `PlannerBlackboard`, `PlannerConditioningState`, coverage state, token schema,
  and source generation ownership are unchanged.

Verification run for this slice:

- Initial RED:
  `python -m pytest -p no:cacheprovider -q tests/test_planner_backend_ports.py`
  -> failed with
  `TypeError: LegacyFsmDigTransitionPorts.__init__() got an unexpected keyword argument 'dig_to_carry_decision'`.
- Focused GREEN:
  `python -m pytest -p no:cacheprovider -q tests/test_planner_backend_ports.py tests/test_legacy_fsm_backend.py tests/test_primitive_scheduler_facades.py::test_dig_exit_guard_transition_does_not_call_later_gates tests/test_primitive_scheduler_facades.py::test_dig_complete_low_payload_preserves_reject_and_restart_reasons tests/test_primitive_scheduler_facades.py::test_dig_to_carry_transition_preserves_completion_order_and_reason`
  -> `25 passed`.
- Backend/runtime/config/BT:
  `python -m pytest -p no:cacheprovider -q tests/test_planner_backend_ports.py tests/test_planner_runtime_contracts.py tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_effects.py tests/test_legacy_fsm_backend_return.py tests/test_planner_backend_config.py tests/test_behavior_tree_backend_contract.py`
  -> `68 passed`.
- Golden/action-tree/facade/debug schema:
  `python -m pytest -p no:cacheprovider -q tests/test_planner_golden_traces.py tests/test_primitive_action_tree.py tests/test_primitive_scheduler_facades.py tests/test_primitive_planner_debug_schema.py`
  -> `168 passed`.
- Token/data/config contract check:
  `python -m pytest -p no:cacheprovider -q tests/test_primitive_token_contracts.py tests/test_policy_data_contracts.py tests/test_config_semantic_matrix.py`
  -> `25 passed, 1 warning` from the existing `datetime.utcnow()` deprecation in
  `testbed/data/dataset.py`.
- `python -m compileall -q testbed/planner/runtime testbed/policies/hybrid/primitive_planner.py testbed/planner/primitive_action_tree.py tests/test_planner_backend_ports.py tests/test_planner_runtime_contracts.py tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_effects.py tests/test_legacy_fsm_backend_return.py tests/test_primitive_scheduler_facades.py`
  -> no output.
- `git diff --check` -> no whitespace errors.

#### Carry/Dump Runtime Port Record 2026-06-18

Implemented files:

- `testbed/planner/runtime/ports.py`: replaced the legacy FSM dump-lifecycle
  port group of request builders, gate callbacks, hold-step providers, and
  dump config providers with two stable semantic providers:
  `carry_transition_runtime` and `dump_transition_runtime`. Their structural
  return protocols expose the runtime state fields consumed by the backend:
  `dump_ready_hold_count` plus `outcome`, and `dump_done_hold_count` plus
  `outcome`.
- `testbed/planner/runtime/__init__.py`: exports the carry/dump runtime
  provider and runtime protocols with the other typed backend port contracts.
- `testbed/planner/runtime/legacy_fsm.py`: changed the carry and dump branches
  to call the typed runtime providers and emit the existing
  `apply_carry_transition_runtime` / `apply_dump_transition_runtime` effects.
  Carry/dump no longer require `LegacyFsmBoundaryProfilePorts`; at this point
  return still used that boundary-profile port.
- `testbed/policies/hybrid/primitive_planner.py`: kept adapter work thin by
  wiring `LegacyFsmDumpLifecyclePorts` to `_carry_transition_runtime()` and
  `_dump_transition_runtime()`. Those helpers preserve the existing request
  builder, boundary-profile input, gate-call order, hold-step config, and
  lifecycle service calls.
- `tests/test_planner_backend_ports.py`: added the RED/GREEN contract for the
  new carry/dump typed runtime providers.
- `tests/test_legacy_fsm_backend_dump_lifecycle.py`: moved focused carry/dump
  backend behavior locks out of `tests/test_legacy_fsm_backend.py`, keeping the
  original branch-order and boundary-event skip assertions while returning the
  large backend test file below the 1000-line threshold.

Scope guardrails kept:

- No branch order, thresholds, switch reasons, coverage reasons, hold-count
  semantics, policy reset timing, debug/trace/rollout schema, token contract,
  default backend selection, or behavior-tree default changed.
- The backend still does not own dump lifecycle thresholds or observation facts.
  It consumes typed runtime states returned through explicit ports and emits
  the existing runtime effect payloads.
- `PrimitivePlannerACTPolicy` remains the adapter and effect applier. Carry/dump
  side effects still run through `_apply_carry_transition_runtime()` and
  `_apply_dump_transition_runtime()`.
- `PlannerBlackboard` remains the source of truth for dump-ready and dump-done
  hold counts. Coverage state and token state ownership are unchanged.

Verification run for this slice:

- Initial RED:
  `python -m pytest -p no:cacheprovider -q tests/test_planner_backend_ports.py`
  -> failed with
  `TypeError: LegacyFsmDumpLifecyclePorts.__init__() got an unexpected keyword argument 'carry_transition_runtime'`.
- Focused GREEN:
  `python -m pytest -p no:cacheprovider -q tests/test_planner_backend_ports.py tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_dump_lifecycle.py`
  -> `23 passed`.
- Backend/runtime/config/BT:
  `python -m pytest -p no:cacheprovider -q tests/test_planner_backend_ports.py tests/test_planner_runtime_contracts.py tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_dump_lifecycle.py tests/test_legacy_fsm_backend_effects.py tests/test_legacy_fsm_backend_return.py tests/test_planner_backend_config.py tests/test_behavior_tree_backend_contract.py`
  -> `69 passed`.
- Golden/action-tree/facade/debug schema:
  `python -m pytest -p no:cacheprovider -q tests/test_planner_golden_traces.py tests/test_primitive_action_tree.py tests/test_primitive_scheduler_facades.py tests/test_primitive_planner_debug_schema.py`
  -> `168 passed`.
- Token/data/config contract check:
  `python -m pytest -p no:cacheprovider -q tests/test_primitive_token_contracts.py tests/test_policy_data_contracts.py tests/test_config_semantic_matrix.py`
  -> `25 passed, 1 warning` from the existing `datetime.utcnow()` deprecation in
  `testbed/data/dataset.py`.
- `python -m compileall -q testbed/planner/runtime testbed/policies/hybrid/primitive_planner.py testbed/planner/primitive_action_tree.py tests/test_planner_backend_ports.py tests/test_planner_runtime_contracts.py tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_dump_lifecycle.py tests/test_legacy_fsm_backend_effects.py tests/test_legacy_fsm_backend_return.py tests/test_primitive_scheduler_facades.py`
  -> no output.
- `git diff --check` -> no whitespace errors.

#### Return Transition Runtime Port Record 2026-06-18

Implemented files:

- `testbed/planner/return_to_dig_transition.py`: added
  `ReturnToDigTransitionRuntime` as the typed runtime record that carries the
  existing return transition `outcome` and runtime `projection` together.
- `testbed/planner/runtime/ports.py`: replaced the legacy FSM return port group
  of `service`, `handoff_ready`, `direct_handoff_ready`, and
  `shallow_guard_ready` callbacks with the stable
  `return_transition_runtime` provider. `LegacyFsmBoundaryProfilePorts` was
  removed because return no longer reads boundary-profile state through a
  separate backend port.
- `testbed/planner/runtime/__init__.py`: exports the return runtime provider
  and runtime protocols with the other typed backend port contracts.
- `testbed/planner/runtime/legacy_fsm.py`: changed the return branch to consume
  the typed runtime record from `context.ports.legacy_fsm.return_transition` and
  emit the existing `apply_return_to_dig_transition_runtime` effect payload.
  The backend no longer orchestrates handoff/direct/shallow callbacks or reads a
  boundary-profile provider.
- `testbed/policies/hybrid/primitive_planner.py`: wires
  `LegacyFsmReturnTransitionPorts` to `_return_transition_runtime()`. That
  adapter method preserves the existing handoff, transition request,
  direct-handoff, shallow-guard, classify, and projection order.
- `tests/test_planner_backend_ports.py` and
  `tests/test_legacy_fsm_backend_return.py`: added and updated focused backend
  contract tests for the typed return runtime provider, while preserving the
  branch-order assertions for the adapter-built provider.

Scope guardrails kept:

- No branch order, return gate thresholds, switch reasons, next-dig latch
  semantics, policy reset timing, debug/trace/rollout schema, token contract,
  default backend selection, or behavior-tree default changed.
- The backend still does not own return handoff/direct/shallow gate facts or
  thresholds. It consumes the typed outcome/projection runtime record and emits
  the existing runtime effect payload.
- Return completion remains adapter-owned. The effect applier still applies the
  runtime projection first, then builds and applies completion so the existing
  counter-sensitive pre-dig-align timing is preserved.
- `_try_return_direct_handoff_at_current_obs()` remains adapter-owned and was
  not migrated in this slice.
- `PlannerBlackboard`, `PlannerConditioningState`, coverage state, token schema,
  and source generation ownership are unchanged.

Verification run for this slice:

- Initial RED:
  `python -m pytest -p no:cacheprovider -q tests/test_planner_backend_ports.py`
  -> failed with
  `TypeError: LegacyFsmReturnTransitionPorts.__init__() got an unexpected keyword argument 'return_transition_runtime'`.
- Focused GREEN:
  `python -m pytest -p no:cacheprovider -q tests/test_planner_backend_ports.py tests/test_legacy_fsm_backend_return.py tests/test_legacy_fsm_backend.py`
  -> `25 passed`.
- Backend/runtime/config/BT:
  `python -m pytest -p no:cacheprovider -q tests/test_planner_backend_ports.py tests/test_planner_runtime_contracts.py tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_dump_lifecycle.py tests/test_legacy_fsm_backend_effects.py tests/test_legacy_fsm_backend_return.py tests/test_planner_backend_config.py tests/test_behavior_tree_backend_contract.py`
  -> `70 passed`.
- Golden/action-tree/facade/debug schema:
  `python -m pytest -p no:cacheprovider -q tests/test_planner_golden_traces.py tests/test_primitive_action_tree.py tests/test_primitive_scheduler_facades.py tests/test_primitive_planner_debug_schema.py`
  -> `168 passed`.
- Token/data/config contract check:
  `python -m pytest -p no:cacheprovider -q tests/test_primitive_token_contracts.py tests/test_policy_data_contracts.py tests/test_config_semantic_matrix.py`
  -> `25 passed, 1 warning` from the existing `datetime.utcnow()` deprecation in
  `testbed/data/dataset.py`.
- `python -m compileall -q testbed/planner/runtime testbed/planner/return_to_dig_transition.py testbed/policies/hybrid/primitive_planner.py testbed/planner/primitive_action_tree.py tests/test_planner_backend_ports.py tests/test_planner_runtime_contracts.py tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_dump_lifecycle.py tests/test_legacy_fsm_backend_effects.py tests/test_legacy_fsm_backend_return.py tests/test_primitive_scheduler_facades.py`
  -> no output.
- `git diff --check` -> no whitespace errors.
- `rg "context\\.services|services\\[|LegacyFsmBoundaryProfilePorts|ports\\.boundary_profile|boundary_ports" testbed/planner testbed/policies/hybrid tests -n`
  -> no matches.

### Phase 2: Coverage As First Blackboard Domain

Use the recent coverage dig-cut activation work as the first state-domain
candidate. Expose coverage state/effects through explicit runtime contracts while
keeping `DigCoverageMixin` as a compatibility adapter.

Definition of done:

- coverage selection and dig-cut activation can be tested without constructing
  `PrimitivePlannerACTPolicy`
- adapter tests verify old facade behavior
- no debug/trace/rollout key changes

#### Phase 2 Slice 1 Landing Record 2026-06-17

Implemented files:

- `testbed/planner/runtime/coverage.py`: projection from
  `CoverageActionResult` to backend-neutral `PlannerRuntimeEffect` objects.
- `tests/test_coverage_runtime_effects.py`: contract tests for empty coverage
  actions, terminal-stop projection, and `replace` payload preservation.

Scope guardrails kept:

- No `_maybe_switch_skill()` migration.
- No default planner behavior or config wiring changes.
- No `CoverageService` decision, threshold, reason-string, debug, trace, or
  rollout schema changes.
- No edits to `PrimitivePlannerACTPolicy`, `PrimitiveActionTreeRunner`, or
  `DigCoverageMixin`; the new helper only projects a service action result into
  explicit `request_coverage_terminal_stop` runtime effects.
- The coverage adapter still applies terminal-stop requests through the existing
  facade path. Runtime effect application is intentionally left for a later
  behavior-preserving slice.

Verification run for this slice:

- `pytest tests/test_coverage_runtime_effects.py -q` -> `3 passed`.
- `pytest -q tests/test_planner_runtime_contracts.py::test_runtime_effect_payload_is_an_immutable_hashable_copy tests/test_planner_runtime_contracts.py::test_tick_result_preserves_effect_order_and_hashable_scalar_contract tests/test_dig_coverage_contracts.py::test_coverage_service_defers_terminal_stop_to_policy_facade tests/test_dig_coverage_contracts.py::test_coverage_terminal_stop_reason_preserves_first_request tests/test_primitive_scheduler_facades.py::test_failed_dig_stop_state_apply_preserves_side_effect_order`
  -> `5 passed`.
- `pytest -q tests/test_dig_coverage_contracts.py tests/test_planner_golden_traces.py tests/test_primitive_action_tree.py`
  -> `48 passed`.
- `git diff --check` and the no-index whitespace check for new files -> no
  whitespace errors.

#### Phase 2 Slice 2 Landing Record 2026-06-17

Implemented files:

- `testbed/planner/runtime/coverage.py`: added
  `apply_coverage_runtime_effects()` and
  `CoverageTerminalStopRequester` for adapter-owned terminal-stop application.
- `testbed/planner/dig_coverage/facade.py`: changed
  `_apply_coverage_action_result()` to project `CoverageActionResult` into
  runtime effects, then apply those effects through the existing
  `_request_coverage_terminal_stop()` adapter callback.
- `tests/test_coverage_runtime_effects.py`: added adapter parity and isolated
  import-order tests for the coverage runtime bridge.

Scope guardrails kept:

- No `_maybe_switch_skill()` migration.
- No default planner behavior or config wiring changes.
- No `CoverageService` decision, threshold, reason-string, debug, trace, or
  rollout schema changes.
- No changes to `PrimitivePlannerACTPolicy`, `PrimitiveActionTreeRunner`, or
  coverage selection/progress code.
- Runtime coverage imports avoid importing the `dig_coverage` package at runtime
  to prevent a `runtime.coverage` -> `dig_coverage.__init__` -> `facade` import
  cycle.

Verification run for this slice:

- `pytest tests/test_coverage_runtime_effects.py -q` -> `6 passed`.
- `pytest tests/test_coverage_runtime_effects.py tests/test_planner_runtime_contracts.py -q`
  -> `10 passed`.
- `pytest -q tests/test_dig_coverage_contracts.py::test_coverage_service_defers_terminal_stop_to_policy_facade tests/test_dig_coverage_contracts.py::test_coverage_terminal_stop_reason_preserves_first_request tests/test_primitive_scheduler_facades.py::test_failed_dig_stop_state_apply_preserves_side_effect_order tests/test_planner_runtime_contracts.py::test_runtime_effect_payload_is_an_immutable_hashable_copy tests/test_planner_runtime_contracts.py::test_tick_result_preserves_effect_order_and_hashable_scalar_contract`
  -> `5 passed`.
- `pytest -q tests/test_dig_coverage_contracts.py tests/test_planner_golden_traces.py tests/test_primitive_action_tree.py`
  -> `48 passed`.
- Direct Python import of `testbed.planner.runtime.coverage` before
  `testbed.planner.dig_coverage.facade` succeeds.
- `git diff --check` and the no-index whitespace check for new files -> no
  whitespace errors.

#### Phase 2 Completion Record 2026-06-17

Additional test-only landing:

- `tests/test_coverage_service_runtime_domain.py`: constructs
  `CoverageService`, `CoverageServiceConfig`, `CoverageServiceState`, and
  `CoverageObservationFacts` directly, without constructing
  `PrimitivePlannerACTPolicy`, and exercises both
  `select_next_corridor_result()` and `activate_dig_cut_corridor()`.

Phase 2 is considered complete for the runtime-contract skeleton migration:

- coverage selection and dig-cut activation now have direct service-level tests
  independent of the policy adapter;
- `DigCoverageMixin._apply_coverage_action_result()` has adapter parity tests
  for the old terminal-stop facade behavior;
- runtime effects are limited to coverage terminal-stop request projection and
  adapter-owned application;
- no debug/trace/rollout key changes, default planner changes, config default
  changes, `_maybe_switch_skill()` migration, branch-order changes, threshold
  changes, or reason-string changes are part of this phase.

Verification run for Phase 2 completion:

- `pytest -p no:cacheprovider tests/test_coverage_runtime_effects.py tests/test_planner_runtime_contracts.py tests/test_coverage_service_runtime_domain.py -q`
  -> `12 passed`.
- `pytest -p no:cacheprovider -q tests/test_dig_coverage_contracts.py::test_coverage_service_defers_terminal_stop_to_policy_facade tests/test_dig_coverage_contracts.py::test_coverage_terminal_stop_reason_preserves_first_request tests/test_primitive_scheduler_facades.py::test_failed_dig_stop_state_apply_preserves_side_effect_order`
  -> `3 passed`.
- `pytest -p no:cacheprovider -q tests/test_dig_coverage_contracts.py tests/test_planner_golden_traces.py tests/test_primitive_action_tree.py`
  -> `48 passed`.
- `pytest -p no:cacheprovider -q tests/test_primitive_planner_debug_schema.py::test_debug_state_default_schema_is_stable tests/test_primitive_planner_debug_schema.py::test_rollout_summary_facts_use_coverage_summary_snapshot tests/test_primitive_planner_debug_schema.py::test_planner_trace_schema_is_stable tests/test_primitive_planner_debug_schema.py::test_planner_trace_facts_use_coverage_trace_snapshot`
  -> `4 passed`.

### Phase 3: Legacy FSM Backend

Move `_maybe_switch_skill()` orchestration into `LegacyStateMachineBackend`
without changing behavior. Initially, it may share capability calls with the
adapter, but it must return `PlannerTickResult` and effects instead of directly
writing final state.

Definition of done:

- legacy backend golden trace matches current default planner
- switch reason, cycle index, transition counts, token source, and reset counts
  match existing tests

#### Phase 3 Slice 1 Landing Record 2026-06-17

Implemented files:

- `testbed/planner/runtime/legacy_fsm.py`: `LegacyStateMachineBackend`, the
  `run_legacy_fsm_transition` runtime effect, and the adapter-side effect
  applier.
- `testbed/planner/runtime/__init__.py`: package exports for the legacy FSM
  backend bridge.
- `testbed/policies/hybrid/primitive_planner.py`: thin adapter wiring so
  `_maybe_switch_skill()` builds a `PlannerTickContext`, calls
  `LegacyStateMachineBackend.tick()`, and applies returned runtime effects
  through the preserved legacy transition implementation.
- `tests/test_legacy_fsm_backend.py`: contract tests for backend tick result
  shape, effect ordering, adapter wiring, and parity between the backend path
  and direct legacy transition implementation.

Scope guardrails kept:

- The legacy branch logic was not rewritten; it is preserved in
  `_run_legacy_fsm_transition()` as the compatibility implementation.
- No `_set_skill()` semantics, reset timing, branch order, thresholds, reason
  strings, token contracts, debug/trace/rollout schemas, default config, or
  behavior-tree defaults changed.
- `PrimitivePlannerACTPolicy` remains the public adapter and runtime effect
  applier.

Remaining Phase 3 work:

- Move individual active-skill branches out of `_run_legacy_fsm_transition()`
  into backend-owned decision logic one stable slice at a time.
- Keep the adapter applying side effects and dispatching low-level policies.

Verification run for this slice:

- `pytest -p no:cacheprovider -q tests/test_legacy_fsm_backend.py tests/test_planner_runtime_contracts.py`
  -> `8 passed`.
- `pytest -p no:cacheprovider -q tests/test_planner_golden_traces.py tests/test_primitive_action_tree.py tests/test_legacy_fsm_backend.py`
  -> `25 passed`.
- `pytest -p no:cacheprovider -q tests/test_primitive_scheduler_facades.py`
  -> `120 passed`.
- `pytest -p no:cacheprovider -q tests/test_dig_coverage_contracts.py tests/test_planner_golden_traces.py tests/test_primitive_action_tree.py tests/test_legacy_fsm_backend.py`
  -> `52 passed`.
- `pytest -p no:cacheprovider -q tests/test_agx_primitives_v2_2.py`
  -> `121 passed`.

#### Phase 3 Slice 2 Landing Record 2026-06-17

Implemented files:

- `testbed/planner/runtime/legacy_fsm.py`: added the
  `apply_bootstrap_transition_decision` runtime effect and moved the
  `bootstrap` active-skill end-transition orchestration into
  `LegacyStateMachineBackend.tick()`. At landing time the backend used explicit
  adapter services/callbacks from the tick context; it did not mutate
  `PrimitivePlannerACTPolicy` directly. This untyped registry was superseded by
  the typed backend ports record below.
- `testbed/planner/runtime/__init__.py`: package exports for the bootstrap
  decision effect and callback protocol.
- `testbed/policies/hybrid/primitive_planner.py`: thin adapter wiring for
  legacy-FSM tick context construction and bootstrap decision effect
  application through the existing `_apply_bootstrap_transition_decision()`
  facade.
- `tests/test_legacy_fsm_backend.py`: contract tests for bootstrap running
  ticks with no effects, bootstrap end-transition decision effects, effect
  application order, required adapter callbacks, and policy adapter wiring that
  avoids the generic legacy fallback for `bootstrap`. The tests also verify
  that missing explicit bootstrap service wiring still uses the generic legacy
  transition effect rather than treating an empty skill name as bootstrap.

Scope guardrails kept:

- Only the `bootstrap` active-skill branch was moved behind the backend
  contract. `pre_dig_align`, `dig`, `carry`, `dump`, and `return` still use the
  preserved `run_legacy_fsm_transition` fallback effect.
- `_set_skill()` remains the only owner of skill switch side effects and policy
  reset timing. The backend returns a decision effect; the adapter applies it.
- `bootstrap` end-condition, transition request, transition decision, switch
  reason, pre-dig-align selection, branch order, thresholds, debug/trace/rollout
  schemas, default config, and behavior-tree defaults were not changed.
- The backend recognizes the bootstrap branch only through explicit adapter
  skill-name wiring, rather than introducing a new skill-name source of truth in
  the runtime module.

Verification run for this slice:

- Initial TDD check:
  `pytest tests/test_legacy_fsm_backend.py -q` failed during collection because
  `APPLY_BOOTSTRAP_TRANSITION_DECISION_EFFECT` did not exist yet.
- `python -m pytest tests/test_legacy_fsm_backend.py -q` -> `10 passed`.
- `python -m pytest tests/test_primitive_action_tree.py::test_action_tree_tick_transition_matches_legacy_bootstrap tests/test_primitive_action_tree.py::test_action_tree_tick_transition_matches_legacy_bootstrap_to_pre_dig_align -q`
  -> `2 passed`.
- `python -m pytest tests/test_primitive_scheduler_facades.py::test_bootstrap_end_transition_facade_uses_service_decision tests/test_primitive_scheduler_facades.py::test_bootstrap_end_transition_facade_delegates_decision_application tests/test_primitive_scheduler_facades.py::test_bootstrap_transition_decision_apply_facade_delegates_skill_switch -q`
  -> `3 passed`.
- `python -m pytest -p no:cacheprovider tests/test_legacy_fsm_backend.py tests/test_planner_runtime_contracts.py -q`
  -> `14 passed`.
- `python -m pytest -p no:cacheprovider tests/test_planner_golden_traces.py tests/test_primitive_action_tree.py tests/test_legacy_fsm_backend.py -q`
  -> `31 passed`.
- `python -m pytest -p no:cacheprovider tests/test_primitive_scheduler_facades.py -q`
  -> `120 passed`.
- `python -m pytest -p no:cacheprovider tests/test_agx_primitives_v2_2.py -q`
  -> `121 passed`.

#### Phase 3 Slice 3 Landing Record 2026-06-17

Implemented files:

- `testbed/planner/runtime/legacy_fsm.py`: added the
  `apply_pre_dig_align_outcome` runtime effect and moved the
  `pre_dig_align` active-skill outcome orchestration into
  `LegacyStateMachineBackend.tick()`. At landing time the backend called an
  explicit `pre_dig_align_outcome` adapter callback from the tick context and
  returned an adapter-applied outcome effect. This untyped registry was
  superseded by the typed backend ports record below.
- `testbed/planner/runtime/__init__.py`: package exports for the pre-dig-align
  outcome effect and callback protocol.
- `testbed/policies/hybrid/primitive_planner.py`: thin adapter wiring for
  `pre_dig_align_outcome` service callback injection and outcome effect
  application through the existing `_apply_pre_dig_align_outcome()` facade.
- `tests/test_legacy_fsm_backend.py`: contract tests for backend outcome effect
  shape, effect application order, required adapter callback, and policy adapter
  wiring that avoids the generic legacy fallback for `pre_dig_align`.

Scope guardrails kept:

- Only the `pre_dig_align` active-skill branch was moved behind the backend
  contract. `dig`, `carry`, `dump`, and `return` still use the preserved
  `run_legacy_fsm_transition` fallback effect.
- `_apply_pre_dig_align_outcome()` remains the owner of outcome projection and
  side-effect application, including `_set_skill()`, replan handoff, restart,
  coverage rejection, and pre-dig-align runtime-state mutation.
- No pre-dig-align readiness, surface-guard, timeout, replan, restart,
  threshold, switch reason, branch order, reset timing, debug/trace/rollout
  schema, default config, or behavior-tree default changed.
- The backend recognizes the pre-dig-align branch only through explicit adapter
  skill-name wiring.

Verification run for this slice:

- Initial TDD check:
  `python -m pytest tests/test_legacy_fsm_backend.py -q` failed during
  collection because `APPLY_PRE_DIG_ALIGN_OUTCOME_EFFECT` did not exist yet.
- `python -m pytest tests/test_legacy_fsm_backend.py -q` -> `14 passed`.
- `python -m pytest tests/test_primitive_action_tree.py::test_action_tree_tick_transition_matches_legacy_pre_dig_align_ready tests/test_primitive_action_tree.py::test_action_tree_tick_transition_matches_legacy_pre_dig_align_surface_guard_replan tests/test_primitive_action_tree.py::test_action_tree_tick_transition_matches_legacy_pre_dig_align_timeout_replan -q`
  -> `3 passed`.
- `python -m pytest tests/test_primitive_scheduler_facades.py::test_pre_dig_align_outcome_runtime_projection_apply_facade_preserves_order tests/test_primitive_scheduler_facades.py::test_pre_dig_align_outcome_apply_facade_projects_current_runtime_state tests/test_primitive_scheduler_facades.py::test_pre_dig_align_surface_guard_handoff_applies_projection_before_set_skill tests/test_primitive_scheduler_facades.py::test_pre_dig_align_timeout_replan_applies_projection_before_replan_attempt tests/test_primitive_scheduler_facades.py::test_try_replan_pre_dig_align_handoff_applies_service_runtime_projection tests/test_primitive_scheduler_facades.py::test_restart_pre_dig_align_applies_service_runtime_projection -q`
  -> `6 passed`.
- `python -m pytest -p no:cacheprovider tests/test_legacy_fsm_backend.py tests/test_planner_runtime_contracts.py -q`
  -> `18 passed`.
- `python -m pytest -p no:cacheprovider tests/test_planner_golden_traces.py tests/test_primitive_action_tree.py tests/test_legacy_fsm_backend.py -q`
  -> `35 passed`.
- `python -m pytest -p no:cacheprovider tests/test_primitive_scheduler_facades.py -q`
  -> `120 passed`.
- `python -m pytest -p no:cacheprovider tests/test_agx_primitives_v2_2.py -q`
  -> `121 passed`.

#### Phase 3 Slice 4 Landing Record 2026-06-17

Implemented files:

- `testbed/planner/runtime/legacy_fsm.py`: added the
  `apply_dig_transition_runtime_projection` runtime effect and moved the `dig`
  active-skill gate orchestration into `LegacyStateMachineBackend.tick()`. The
  backend evaluates the same adapter-provided gate callbacks in the legacy
  short-circuit order and returns a `DigTransitionRuntimeProjection` effect.
- `testbed/planner/runtime/__init__.py`: package exports for the dig transition
  projection effect and callback protocol.
- `testbed/policies/hybrid/primitive_planner.py`: thin adapter wiring for
  dig-lifecycle gate callback injection and projection effect application
  through the existing `_apply_dig_transition_runtime_projection()` facade.
- `tests/test_legacy_fsm_backend.py`: contract tests for dig projection effect
  shape, exit-guard short-circuiting, effect application order, required adapter
  callback, and policy adapter wiring that avoids the generic legacy fallback
  for `dig`.

Scope guardrails kept:

- Only the `dig` active-skill branch was moved behind the backend contract.
  `carry`, `dump`, and `return` still use the preserved
  `run_legacy_fsm_transition` fallback effect.
- `_apply_dig_transition_runtime_projection()` remains the owner of all dig
  transition side effects, including counter increments, active coverage
  rejection, failed-dig restart, cell-entry completion, coverage completion,
  `_set_skill("carry", ...)`, and policy reset timing.
- The backend still calls adapter callbacks such as `_dig_to_carry_ready()` so
  `_dig_to_carry_reason` is written at the same point as before; it does not
  call lower-level service gates in a way that would bypass adapter state.
- No dig exit-guard, bad-replan, complete-boundary-low-payload, dig-to-carry,
  threshold, switch reason, branch order, reset timing, debug/trace/rollout
  schema, default config, or behavior-tree default changed.

Verification run for this slice:

- Initial TDD check:
  `python -m pytest tests/test_legacy_fsm_backend.py -q` failed during
  collection because `APPLY_DIG_TRANSITION_RUNTIME_PROJECTION_EFFECT` did not
  exist yet.
- `python -m pytest tests/test_legacy_fsm_backend.py -q` -> `19 passed`.
- `python -m pytest -q tests/test_primitive_scheduler_facades.py::test_dig_exit_guard_transition_does_not_call_later_gates tests/test_primitive_scheduler_facades.py::test_dig_complete_low_payload_preserves_reject_and_restart_reasons tests/test_primitive_scheduler_facades.py::test_dig_transition_runtime_projection_apply_facade_preserves_side_effect_order tests/test_primitive_scheduler_facades.py::test_dig_to_carry_transition_preserves_completion_order_and_reason`
  -> `4 passed`.
- `python -m pytest -q tests/test_primitive_action_tree.py::test_action_tree_tick_transition_matches_legacy_dig_bad_replan tests/test_primitive_action_tree.py::test_action_tree_tick_transition_matches_legacy_dig_complete_low_payload tests/test_primitive_action_tree.py::test_action_tree_tick_transition_matches_legacy_dig_carry_dump_return_chain tests/test_primitive_action_tree.py::test_action_tree_predict_trace_records_dispatch_resets_and_counter_deltas`
  -> `4 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_legacy_fsm_backend.py tests/test_planner_runtime_contracts.py`
  -> `23 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_planner_golden_traces.py tests/test_primitive_action_tree.py tests/test_legacy_fsm_backend.py`
  -> `40 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_primitive_scheduler_facades.py`
  -> `120 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_agx_primitives_v2_2.py`
  -> `121 passed`.

#### Phase 3 Slice 5 Landing Record 2026-06-17

Implemented files:

- `testbed/planner/runtime/legacy_fsm.py`: added the
  `apply_carry_transition_runtime` runtime effect and moved the `carry`
  active-skill request/gate orchestration into `LegacyStateMachineBackend.tick()`.
  The backend calls adapter-provided callbacks and the existing
  dump-lifecycle request/runtime service to preserve short-circuit order.
- `testbed/planner/runtime/__init__.py`: package exports for the carry
  transition runtime effect and callback protocol.
- `testbed/policies/hybrid/primitive_planner.py`: thin adapter wiring for carry
  lifecycle callback injection and carry runtime effect application through the
  existing `_apply_carry_transition_runtime()` facade.
- `tests/test_legacy_fsm_backend.py`: contract tests for carry runtime effect
  shape, boundary-event short-circuiting of `_dump_ready`, effect application
  order, required adapter callback, and policy adapter wiring that avoids the
  generic legacy fallback for `carry`.

Scope guardrails kept:

- Only the `carry` active-skill branch was moved behind the backend contract.
  `dump` and `return` still use the preserved `run_legacy_fsm_transition`
  fallback effect.
- `_apply_carry_transition_runtime()` remains the owner of all carry transition
  side effects, including `_dump_ready_hold_count`, coverage dump completion,
  return/direct handoff selection, `_dump_start_deposited_mass_kg`,
  `_set_skill("dump", ...)`, and policy reset timing.
- The backend still uses `build_carry_transition_runtime_request()` and
  `DumpLifecycleGateService.carry_transition_runtime()` as the source of truth
  for release-safety, dump-complete, dump-committed, release-onset,
  legacy-dump-start, dump-ready hold count, and switch reason projection.
- No carry release-safety, dump-ready, hold-count, boundary-event, switch
  reason, branch order, reset timing, debug/trace/rollout schema, default
  config, or behavior-tree default changed.

Verification run for this slice:

- Initial TDD check:
  `python -m pytest tests/test_legacy_fsm_backend.py -q` failed during
  collection because `APPLY_CARRY_TRANSITION_RUNTIME_EFFECT` did not exist yet.
- `python -m pytest tests/test_legacy_fsm_backend.py -q` -> `24 passed`.
- `python -m pytest -q tests/test_primitive_scheduler_facades.py::test_dump_transition_runtime_apply_facades_preserve_side_effect_order tests/test_primitive_scheduler_facades.py::test_carry_transition_request_uses_lifecycle_builder tests/test_primitive_scheduler_facades.py::test_carry_boundary_event_does_not_call_dump_ready_gate tests/test_primitive_scheduler_facades.py::test_carry_dump_complete_event_preserves_ready_hold_count tests/test_primitive_action_tree.py::test_action_tree_tick_transition_matches_legacy_dig_carry_dump_return_chain`
  -> `5 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_legacy_fsm_backend.py tests/test_planner_runtime_contracts.py`
  -> `28 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_planner_golden_traces.py tests/test_primitive_action_tree.py tests/test_legacy_fsm_backend.py`
  -> `45 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_primitive_scheduler_facades.py`
  -> `120 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_agx_primitives_v2_2.py`
  -> `121 passed`.

#### Phase 3 Slice 6 Landing Record 2026-06-17

Implemented files:

- `testbed/planner/runtime/legacy_fsm.py`: added the
  `apply_dump_transition_runtime` runtime effect and moved the `dump`
  active-skill request/gate orchestration into `LegacyStateMachineBackend.tick()`.
  The backend calls adapter-provided callbacks and the existing dump-lifecycle
  request/runtime service to preserve short-circuit order.
- `testbed/planner/runtime/__init__.py`: package exports for the dump transition
  runtime effect and callback protocol.
- `testbed/policies/hybrid/primitive_planner.py`: thin adapter wiring for dump
  lifecycle callback injection and dump runtime effect application through the
  existing `_apply_dump_transition_runtime()` facade.
- `tests/test_legacy_fsm_backend.py`: contract tests for dump runtime effect
  shape, dump-complete short-circuiting of `_dump_done`, effect application
  order, required adapter callback, and policy adapter wiring that avoids the
  generic legacy fallback for `dump`.

Scope guardrails kept:

- Only the `dump` active-skill branch was moved behind the backend contract.
  `return` still uses the preserved `run_legacy_fsm_transition` fallback effect.
- `_apply_dump_transition_runtime()` remains the owner of all dump transition
  side effects, including `_dump_done_hold_count`, coverage dump completion,
  return/direct handoff selection, `_set_skill("return", ...)`, and policy
  reset timing.
- The backend still uses `build_dump_transition_runtime_request()` and
  `DumpLifecycleGateService.dump_transition_runtime()` as the source of truth
  for dump-complete, legacy-dump-end, dump-done, dump-done hold count, and
  switch reason projection.
- No dump-done threshold, boundary-event short-circuit, hold-count, switch
  reason, branch order, reset timing, debug/trace/rollout schema, default
  config, or behavior-tree default changed.

Verification run for this slice:

- Initial TDD check:
  `python -m pytest tests/test_legacy_fsm_backend.py -q` failed during
  collection because `APPLY_DUMP_TRANSITION_RUNTIME_EFFECT` did not exist yet.
- `python -m pytest tests/test_legacy_fsm_backend.py -q` -> `29 passed`.
- `python -m pytest -q tests/test_primitive_scheduler_facades.py::test_dump_transition_runtime_apply_facades_preserve_side_effect_order tests/test_primitive_scheduler_facades.py::test_dump_transition_request_uses_lifecycle_builder tests/test_primitive_scheduler_facades.py::test_dump_complete_event_does_not_call_dump_done_gate tests/test_primitive_action_tree.py::test_action_tree_tick_transition_matches_legacy_dig_carry_dump_return_chain`
  -> `4 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_legacy_fsm_backend.py tests/test_planner_runtime_contracts.py`
  -> `33 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_planner_golden_traces.py tests/test_primitive_action_tree.py tests/test_legacy_fsm_backend.py`
  -> `50 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_primitive_scheduler_facades.py`
  -> `120 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_agx_primitives_v2_2.py`
  -> `121 passed`.

#### Phase 3 Slice 7 Landing Record 2026-06-17

Implemented files:

- `testbed/planner/runtime/legacy_fsm.py`: added the
  `apply_return_to_dig_transition_runtime` runtime effect and moved the
  `return` active-skill gate orchestration into `LegacyStateMachineBackend.tick()`.
  The backend calls adapter-provided callbacks in the legacy order and uses
  `ReturnToDigTransitionService` for request/classify/projection semantics.
- `testbed/planner/runtime/__init__.py`: package exports for the return-to-dig
  transition runtime effect and callback protocol.
- `testbed/policies/hybrid/primitive_planner.py`: thin adapter wiring for
  return transition callback injection and return runtime effect application.
  The adapter applies the runtime projection first, then builds and applies
  completion so `_should_pre_dig_align_before_dig()` still observes the updated
  cycle/transition counters.
- `tests/test_legacy_fsm_backend.py`: contract tests for return runtime effect
  shape, next-dig event short-circuiting of direct/shallow gates, direct-handoff
  gate order, effect application order, required adapter callback, and policy
  adapter wiring that avoids the generic legacy fallback for `return`.

Scope guardrails kept:

- The `return` active-skill branch is now behind the backend contract, but all
  return side effects remain adapter-owned.
- `_apply_return_to_dig_transition_runtime_projection()` remains the owner of
  `_return_next_dig_event_seen`, `_completed_transition_count`, and
  `_cycle_index` updates.
- `_apply_return_to_dig_transition_completion()` remains the owner of final
  `_set_skill()` and policy reset timing.
- Completion next-skill selection remains after runtime projection application;
  the backend intentionally returns `outcome + projection` rather than
  precomputing completion.
- `_try_return_direct_handoff_at_current_obs()` remains adapter-owned and was
  not moved in this slice.
- No return handoff/direct/shallow gate threshold, next-dig latch behavior,
  switch reason, branch order, reset timing, debug/trace/rollout schema,
  default config, or behavior-tree default changed.

Verification run for this slice:

- Initial TDD check:
  `python -m pytest tests/test_legacy_fsm_backend.py -q` failed during
  collection because `APPLY_RETURN_TO_DIG_TRANSITION_RUNTIME_EFFECT` did not
  exist yet.
- `python -m pytest tests/test_legacy_fsm_backend.py -q` -> `34 passed`.
- `python -m pytest -q tests/test_return_handoff_service.py::test_return_transition_prioritizes_next_event_over_direct_and_shallow tests/test_return_handoff_service.py::test_return_transition_latches_next_event_until_handoff_ready tests/test_return_handoff_service.py::test_return_transition_direct_handoff_precedes_legacy_shallow_guard tests/test_return_handoff_service.py::test_return_transition_shallow_guard_requires_legacy_profile_and_handoff tests/test_return_handoff_service.py::test_return_transition_request_skips_direct_when_next_event_is_ready tests/test_return_handoff_service.py::test_return_transition_request_skips_direct_when_latched_event_can_handoff tests/test_return_handoff_service.py::test_return_transition_request_gates_direct_and_legacy_shallow_guard tests/test_primitive_scheduler_facades.py::test_return_transition_facade_applies_completion_projection tests/test_primitive_scheduler_facades.py::test_return_transition_facade_delegates_completion_application tests/test_primitive_scheduler_facades.py::test_return_next_dig_event_skips_direct_and_shallow_gates tests/test_primitive_scheduler_facades.py::test_return_transition_runtime_projection_apply_facade_updates_lifecycle_state_only tests/test_primitive_scheduler_facades.py::test_return_transition_completion_apply_facade_delegates_skill_switch tests/test_primitive_scheduler_facades.py::test_return_direct_handoff_facade_preserves_gate_call_order tests/test_primitive_scheduler_facades.py::test_set_return_or_direct_handoff_can_same_frame_switch_to_pre_dig_align`
  -> `14 passed`.
- `python -m pytest -q tests/test_legacy_fsm_backend.py tests/test_primitive_action_tree.py::test_action_tree_tick_transition_matches_legacy_dig_carry_dump_return_chain tests/test_primitive_action_tree.py::test_action_tree_tick_transition_matches_legacy_return_direct_handoff tests/test_primitive_action_tree.py::test_action_tree_tick_transition_matches_legacy_return_shallow_guard tests/test_primitive_action_tree.py::test_action_tree_predict_matches_legacy_return_timeout_counter_trace tests/test_planner_golden_traces.py::test_spatial_mass_boundary_events_drive_planner_golden_trace`
  -> `39 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_legacy_fsm_backend.py tests/test_planner_runtime_contracts.py`
  -> `38 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_planner_golden_traces.py tests/test_primitive_action_tree.py tests/test_legacy_fsm_backend.py`
  -> `55 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_primitive_scheduler_facades.py`
  -> `120 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_agx_primitives_v2_2.py`
  -> `121 passed`.

#### Phase 3 Closure Pass 2026-06-17

Implemented files:

- `testbed/policies/hybrid/primitive_planner.py`: collapsed the repeated
  compatibility fallback dispatcher in `_run_legacy_fsm_transition()` into the
  thin `_tick_legacy_fsm_backend()` helper used by both `_maybe_switch_skill()`
  and the legacy fallback facade. This removes duplicated backend tick/apply
  wiring without changing backend decisions or adapter side effects.
- `tests/test_legacy_fsm_backend_effects.py`: moved legacy FSM runtime effect
  application order and required-callback tests out of the main backend test
  file.
- `tests/test_legacy_fsm_backend_return.py`: moved return-specific backend
  contract and adapter-wiring tests out of the main backend test file.
- `tests/test_legacy_fsm_backend.py`: retains backend branch-shape, policy
  wiring, and direct legacy-facade parity tests. The file is back under the
  repository large-file threshold after the split.

Closure status:

- All active default FSM skills now have explicit backend branches:
  `bootstrap`, `pre_dig_align`, `dig`, `carry`, `dump`, and `return`.
- The generic `run_legacy_fsm_transition` effect remains only as a compatibility
  fallback for unsupported non-explicit contexts. A backend returning this
  fallback for an explicit default FSM skill is rejected to avoid recursive
  adapter re-entry.
- `PrimitivePlannerACTPolicy` remains the adapter/effect applier and low-level
  policy dispatcher.
- No branch order, thresholds, reason strings, reset timing, debug/trace/rollout
  schema, default backend selection, or behavior-tree default changed.

Verification run for this closure pass:

- `python -m pytest -q tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_effects.py tests/test_legacy_fsm_backend_return.py`
  -> `34 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_effects.py tests/test_legacy_fsm_backend_return.py tests/test_planner_runtime_contracts.py`
  -> `38 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_planner_golden_traces.py tests/test_primitive_action_tree.py tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_effects.py tests/test_legacy_fsm_backend_return.py`
  -> `55 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_primitive_scheduler_facades.py`
  -> `120 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_agx_primitives_v2_2.py`
  -> `121 passed`.
- `git diff --check` -> no whitespace errors.

#### Phase 3 Post-Closure Boundary Fix 2026-06-17

The post-closure review found that `_run_legacy_fsm_transition()` no longer owns
the old inline default-skill FSM implementation after all default skills moved
behind explicit backend branches. Its role is now a guard rail for
`run_legacy_fsm_transition` effects from unsupported non-explicit contexts.

Implemented adjustment:

- `PrimitivePlannerACTPolicy._run_legacy_fsm_transition()` now rejects
  `bootstrap`, `pre_dig_align`, `dig`, `carry`, `dump`, and `return` when reached
  through the generic fallback effect. This prevents recursive backend re-entry
  if an under-wired backend returns the generic fallback for an explicit default
  FSM skill.
- The previous backend-versus-direct transition test was replaced with a focused
  fallback recursion guard test, because the direct private method is no longer
  an independent legacy implementation.

Scope guardrails kept:

- No default backend selection, active-skill branch order, thresholds, reason
  strings, reset timing, debug/trace/rollout schema, token contract, or behavior
  tree default changed.
- `PrimitivePlannerACTPolicy` remains the runtime effect applier.

### Phase 4: Behavior Tree Backend

Refactor `PrimitiveActionTreeRunner` into `BehaviorTreeBackend`. It must use
`PlannerTickContext`, capability services, blackboard state, and runtime effects.
It must not read or write `policy._xxx`.

Definition of done:

- behavior tree shadow trace matches legacy backend golden traces
- divergence reports include node path, reason, and blackboard/effect diff
- behavior tree stays opt-in until explicitly promoted

#### Phase 4 Pre-Slice Landing Record 2026-06-17

Implemented files:

- `testbed/planner/runtime/behavior_tree.py`: experimental
  `BehaviorTreeBackend` contract skeleton. It implements the backend protocol
  shape and fails closed with `NotImplementedError` until runtime nodes and
  effects are implemented.
- `testbed/planner/runtime/__init__.py`: package exports for the experimental
  behavior-tree backend name and class.
- `tests/test_behavior_tree_backend_contract.py`: contract tests for
  fail-closed behavior, protocol shape, and the import boundary that keeps the
  runtime backend module independent from the existing shadow runner and planner
  shell modules.

Scope guardrails kept:

- `PrimitiveActionTreeRunner` remains a shadow-only compatibility reference and
  was not renamed or promoted to a runtime backend.
- No default backend selection, config default, branch order, thresholds, reason
  strings, reset timing, debug/trace/rollout schema, token contract, or planner
  behavior changed.
- The experimental backend is not wired into `PrimitivePlannerACTPolicy`,
  `planner_backend`, eval, or rollout paths.
- This is the backend-interface Phase 4 pre-slice; it is not the separate
  reporting-cleanup Phase 4 listed in the broader scheduler refactor plan.

#### Phase 4 Slice 1 Return Runtime Node 2026-06-18

Implemented files:

- `testbed/planner/runtime/effects.py`: added the backend-neutral source of
  truth for runtime effect type names. `legacy_fsm.py` still re-exports these
  constants for compatibility, but `BehaviorTreeBackend` no longer imports the
  legacy FSM module to build an effect.
- `testbed/planner/runtime/ports.py`: added top-level `PlannerSkillNames` and
  `PlannerReturnTransitionPorts` so behavior-tree and legacy-FSM backends can
  share the return transition dependency without going through
  `LegacyFsmBackendPorts`. The old `LegacyFsmSkillNames` and
  `LegacyFsmReturnTransitionPorts` names remain compatibility aliases.
- `testbed/planner/runtime/behavior_tree.py`: implemented the first real
  behavior-tree runtime node for the `return` transition. It reads
  `PlannerTickContext.blackboard`, `PlannerBackendPorts.skill_names`, and
  `PlannerBackendPorts.return_transition`, then returns the same
  `apply_return_to_dig_transition_runtime` effect payload used by the legacy
  backend. Other skills remain fail-closed.
- `testbed/planner/runtime/legacy_fsm.py`: changed the legacy return branch to
  prefer the top-level `PlannerBackendPorts.return_transition` dependency while
  retaining the old legacy-bundle field as a compatibility fallback.
- `testbed/policies/hybrid/primitive_planner.py`: thin adapter wiring only.
  `_legacy_fsm_tick_context()` now builds top-level `PlannerSkillNames` and
  `PlannerReturnTransitionPorts`; return completion and effect application stay
  adapter-owned.
- `tests/test_behavior_tree_backend_contract.py` and
  `tests/test_planner_backend_ports.py`: added focused contracts proving the
  behavior-tree return node and legacy FSM return branch can run from the same
  neutral return port, and that the behavior-tree runtime module does not import
  the shadow action-tree runner, legacy FSM backend, or planner shell.

Scope guardrails kept:

- No default backend selection, config default, branch order, return gate
  threshold, reason string, next-dig latch semantics, policy reset timing,
  debug/trace/rollout schema, or token contract changed.
- `BehaviorTreeBackend` remains experimental and is not enabled by
  `planner_backend` config. Only the explicitly wired return node can run; all
  other skills still fail closed.
- `PrimitiveActionTreeRunner` remains the shadow-only compatibility reference
  and was not promoted to a runtime backend.
- Return completion remains adapter-owned. The behavior-tree return node only
  returns the existing runtime effect; it does not apply side effects or mutate
  `PrimitivePlannerACTPolicy`.

Verification run for this slice:

- Initial RED:
  `python -m pytest -p no:cacheprovider -q tests/test_behavior_tree_backend_contract.py`
  -> failed with
  `AttributeError: module 'testbed.planner.runtime' has no attribute 'PlannerSkillNames'`.
- Boundary RED:
  `python -m pytest -p no:cacheprovider -q tests/test_behavior_tree_backend_contract.py`
  -> failed because `testbed/planner/runtime/behavior_tree.py` imported
  `legacy_fsm`.
- Focused GREEN:
  `python -m pytest -p no:cacheprovider -q tests/test_behavior_tree_backend_contract.py tests/test_planner_backend_ports.py tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_return.py`
  -> `28 passed`.
- Backend/runtime/config/BT:
  `python -m pytest -p no:cacheprovider -q tests/test_behavior_tree_backend_contract.py tests/test_planner_backend_ports.py tests/test_planner_runtime_contracts.py tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_dump_lifecycle.py tests/test_legacy_fsm_backend_effects.py tests/test_legacy_fsm_backend_return.py tests/test_planner_backend_config.py`
  -> `71 passed`.
- Golden/action-tree/facade/debug schema:
  `python -m pytest -p no:cacheprovider -q tests/test_planner_golden_traces.py tests/test_primitive_action_tree.py tests/test_primitive_scheduler_facades.py tests/test_primitive_planner_debug_schema.py`
  -> `168 passed`.
- Token/data/config contract check:
  `python -m pytest -p no:cacheprovider -q tests/test_primitive_token_contracts.py tests/test_policy_data_contracts.py tests/test_config_semantic_matrix.py`
  -> `25 passed, 1 warning` from the existing `datetime.utcnow()` deprecation in
  `testbed/data/dataset.py`.
- `python -m compileall -q testbed/planner/runtime testbed/planner/return_to_dig_transition.py testbed/policies/hybrid/primitive_planner.py testbed/planner/primitive_action_tree.py tests/test_behavior_tree_backend_contract.py tests/test_planner_backend_ports.py tests/test_planner_runtime_contracts.py tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_dump_lifecycle.py tests/test_legacy_fsm_backend_effects.py tests/test_legacy_fsm_backend_return.py tests/test_primitive_scheduler_facades.py`
  -> no output.
- `git diff --check` -> no whitespace errors.
- `rg "context\\.services|services\\[|LegacyFsmBoundaryProfilePorts|ports\\.boundary_profile|boundary_ports" testbed/planner testbed/policies/hybrid tests -n`
  -> no matches.
- `rg -n "legacy_fsm|primitive_action_tree|primitive_planner|policy\\._" testbed/planner/runtime/behavior_tree.py testbed/planner/runtime/transition_nodes.py`
  -> no matches.

#### Phase 4 Slice 2 Dig Runtime Node 2026-06-18

Implemented files:

- `testbed/planner/runtime/ports.py`: added top-level
  `PlannerDigTransitionPorts` so behavior-tree and legacy-FSM backends can
  share the dig transition dependency without routing through
  `LegacyFsmBackendPorts`. `LegacyFsmDigTransitionPorts` remains a
  compatibility alias.
- `testbed/planner/runtime/transition_nodes.py`: added shared backend-neutral
  dig and return transition result builders. These builders own result/effect
  construction for the migrated nodes and do not apply side effects or import
  the planner shell, shadow action-tree runner, or legacy FSM backend.
- `testbed/planner/runtime/behavior_tree.py`: implemented the `dig` transition
  runtime node. It reads `PlannerTickContext.blackboard`,
  `PlannerBackendPorts.skill_names`, and `PlannerBackendPorts.dig_transition`,
  then delegates result construction to the shared transition-node builder.
- `testbed/planner/runtime/legacy_fsm.py`: changed the legacy dig branch to
  prefer the top-level `PlannerBackendPorts.dig_transition` dependency while
  retaining the old legacy-bundle field as a compatibility fallback. Its dig
  and return branches now use the shared transition-node builders so the
  migrated BT nodes do not duplicate branch-order/effect construction logic.
- `testbed/policies/hybrid/primitive_planner.py`: thin adapter wiring only.
  `_legacy_fsm_tick_context()` now builds top-level `PlannerDigTransitionPorts`;
  dig side effects still run through the adapter effect applier.
- `tests/test_behavior_tree_backend_contract.py` and
  `tests/test_planner_backend_ports.py`: added and updated focused contracts
  proving the behavior-tree dig node and legacy FSM dig branch can run from the
  same neutral dig port.

Scope guardrails kept:

- No default backend selection, config default, dig gate branch order, dig
  thresholds, switch reason strings, policy reset timing, debug/trace/rollout
  schema, or token contract changed.
- `BehaviorTreeBackend` remains experimental and is not enabled by
  `planner_backend` config. This slice only adds the explicitly wired dig node;
  unwired skills still fail closed.
- `PrimitiveActionTreeRunner` remains the shadow-only compatibility reference
  and was not promoted to a runtime backend.
- The behavior-tree dig node only returns the existing runtime effect. It does
  not apply side effects, mutate `PrimitivePlannerACTPolicy`, or own coverage
  completion/reject application.

Verification run for this slice:

- Initial RED:
  `python -m pytest -p no:cacheprovider -q tests/test_behavior_tree_backend_contract.py`
  -> failed with
  `AttributeError: module 'testbed.planner.runtime' has no attribute 'PlannerDigTransitionPorts'`.
- Focused GREEN:
  `python -m pytest -p no:cacheprovider -q tests/test_behavior_tree_backend_contract.py tests/test_planner_backend_ports.py tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_return.py`
  -> `29 passed`.
- `python -m compileall -q testbed/planner/runtime testbed/policies/hybrid/primitive_planner.py tests/test_behavior_tree_backend_contract.py tests/test_planner_backend_ports.py`
  -> no output.
- `rg -n "legacy_fsm|primitive_action_tree|primitive_planner|policy\\._" testbed/planner/runtime/behavior_tree.py testbed/planner/runtime/transition_nodes.py`
  -> no matches.
- Backend/runtime/config/BT:
  `python -m pytest -p no:cacheprovider -q tests/test_behavior_tree_backend_contract.py tests/test_planner_backend_ports.py tests/test_planner_runtime_contracts.py tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_dump_lifecycle.py tests/test_legacy_fsm_backend_effects.py tests/test_legacy_fsm_backend_return.py tests/test_planner_backend_config.py`
  -> `72 passed`.
- Golden/action-tree/facade/debug schema:
  `python -m pytest -p no:cacheprovider -q tests/test_planner_golden_traces.py tests/test_primitive_action_tree.py tests/test_primitive_scheduler_facades.py tests/test_primitive_planner_debug_schema.py`
  -> `168 passed`.
- Token/data/config contract check:
  `python -m pytest -p no:cacheprovider -q tests/test_primitive_token_contracts.py tests/test_policy_data_contracts.py tests/test_config_semantic_matrix.py`
  -> `25 passed, 1 warning` from the existing `datetime.utcnow()` deprecation in
  `testbed/data/dataset.py`.
- `python -m compileall -q testbed/planner/runtime testbed/planner/return_to_dig_transition.py testbed/policies/hybrid/primitive_planner.py testbed/planner/primitive_action_tree.py tests/test_behavior_tree_backend_contract.py tests/test_planner_backend_ports.py tests/test_planner_runtime_contracts.py tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_dump_lifecycle.py tests/test_legacy_fsm_backend_effects.py tests/test_legacy_fsm_backend_return.py tests/test_primitive_scheduler_facades.py`
  -> no output.
- `git diff --check` -> no whitespace errors.
- `rg "context\\.services|services\\[|LegacyFsmBoundaryProfilePorts|ports\\.boundary_profile|boundary_ports" testbed/planner testbed/policies/hybrid tests -n`
  -> no matches.
- `rg -n "legacy_fsm|primitive_action_tree|primitive_planner|policy\\._" testbed/planner/runtime/behavior_tree.py`
  -> no matches.

#### Phase 4 Slice 3 Carry/Dump Runtime Nodes 2026-06-18

Implemented files:

- `testbed/planner/runtime/ports.py`: added top-level
  `PlannerDumpLifecyclePorts` so behavior-tree and legacy-FSM backends can
  share carry/dump lifecycle runtime providers without routing through
  `LegacyFsmBackendPorts`. `LegacyFsmDumpLifecyclePorts` remains a
  compatibility alias for existing legacy tests and callers.
- `testbed/planner/runtime/transition_nodes.py`: added shared backend-neutral
  carry and dump transition result builders. These builders own the existing
  `apply_carry_transition_runtime` and `apply_dump_transition_runtime` effect
  payload construction for migrated nodes, but do not apply side effects.
- `testbed/planner/runtime/behavior_tree.py`: implemented experimental
  behavior-tree runtime nodes for `carry` and `dump`. They read
  `PlannerTickContext.blackboard`, `PlannerBackendPorts.skill_names`, and
  `PlannerBackendPorts.dump_lifecycle`, then delegate result construction to
  the shared transition-node builders.
- `testbed/planner/runtime/legacy_fsm.py`: changed legacy carry/dump branches
  to prefer the top-level `PlannerBackendPorts.dump_lifecycle` dependency while
  retaining `LegacyFsmBackendPorts.dump_lifecycle` as a compatibility fallback.
  The legacy branches now reuse the same shared transition-node builders as the
  behavior-tree nodes.
- `testbed/policies/hybrid/primitive_planner.py`: thin adapter wiring only.
  `_legacy_fsm_tick_context()` now builds top-level
  `PlannerDumpLifecyclePorts`; carry/dump lifecycle runtime calculation and
  effect application remain adapter/service-owned.
- `tests/test_behavior_tree_backend_contract.py`,
  `tests/test_planner_backend_ports.py`, and `tests/test_legacy_fsm_backend.py`:
  added focused contracts proving carry/dump nodes can run from the neutral
  runtime port and that the policy adapter wires the port at the top-level tick
  context boundary.

Scope guardrails kept:

- No default backend selection, config default, carry/dump branch order, hold
  thresholds, switch reason strings, policy reset timing, debug/trace/rollout
  schema, or token contract changed.
- `BehaviorTreeBackend` remains experimental and is not enabled by
  `planner_backend` config. This slice only adds explicitly wired carry/dump
  nodes; any unwired behavior still fails closed.
- `PrimitiveActionTreeRunner` remains the shadow-only compatibility reference
  and was not promoted to a runtime backend.
- Carry/dump runtime providers remain adapter-built callables backed by the
  existing dump lifecycle service. The backend returns runtime effects; it does
  not mutate `PrimitivePlannerACTPolicy` or own effect application.

Verification run for this slice:

- Initial RED:
  `python -m pytest -p no:cacheprovider -q tests/test_behavior_tree_backend_contract.py`
  -> failed with
  `AttributeError: module 'testbed.planner.runtime' has no attribute 'PlannerDumpLifecyclePorts'`.
- Focused GREEN:
  `python -m pytest -p no:cacheprovider -q tests/test_behavior_tree_backend_contract.py tests/test_planner_backend_ports.py tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_dump_lifecycle.py`
  -> `30 passed`.
- Backend/runtime/config/BT:
  `python -m pytest -p no:cacheprovider -q tests/test_behavior_tree_backend_contract.py tests/test_planner_backend_ports.py tests/test_planner_runtime_contracts.py tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_dump_lifecycle.py tests/test_legacy_fsm_backend_effects.py tests/test_legacy_fsm_backend_return.py tests/test_planner_backend_config.py`
  -> `74 passed`.
- Golden/action-tree/facade/debug schema:
  `python -m pytest -p no:cacheprovider -q tests/test_planner_golden_traces.py tests/test_primitive_action_tree.py tests/test_primitive_scheduler_facades.py tests/test_primitive_planner_debug_schema.py`
  -> `168 passed`.
- Token/data/config contract check:
  `python -m pytest -p no:cacheprovider -q tests/test_primitive_token_contracts.py tests/test_policy_data_contracts.py tests/test_config_semantic_matrix.py`
  -> `25 passed, 1 warning` from the existing `datetime.utcnow()`
  deprecation in `testbed/data/dataset.py`.
- `python -m compileall -q testbed/planner/runtime testbed/planner/return_to_dig_transition.py testbed/policies/hybrid/primitive_planner.py testbed/planner/primitive_action_tree.py tests/test_behavior_tree_backend_contract.py tests/test_planner_backend_ports.py tests/test_planner_runtime_contracts.py tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_dump_lifecycle.py tests/test_legacy_fsm_backend_effects.py tests/test_legacy_fsm_backend_return.py tests/test_primitive_scheduler_facades.py`
  -> no output.
- `git diff --check` -> no whitespace errors.
- `rg "context\\.services|services\\[|LegacyFsmBoundaryProfilePorts|ports\\.boundary_profile|boundary_ports" testbed/planner testbed/policies/hybrid tests -n`
  -> no matches.
- `rg -n "legacy_fsm|primitive_action_tree|primitive_planner|policy\\._" testbed/planner/runtime/behavior_tree.py testbed/planner/runtime/transition_nodes.py`
  -> no matches.

### Phase 5: Default Backend Migration

Once `LegacyStateMachineBackend` is behavior-identical and the adapter applies
effects through the runtime path, make default planner execution go through the
backend interface with `legacy_fsm` selected by default.

Behavior tree or other advanced planners remain explicit experimental choices
until separately approved.

Phase status note: after Phase 3, the default `_maybe_switch_skill()` path
already calls `LegacyStateMachineBackend.tick()` and applies returned runtime
effects through the adapter. Remaining Phase 5 work should therefore focus on
backend selection/config cleanup, not re-moving the same default FSM branch
logic.

#### Phase 5 Pre-Slice Landing Record 2026-06-17

Implemented files:

- `testbed/planner/planner_backend_config.py`: added
  `make_planner_backend()` as the runtime backend factory boundary. It creates
  `LegacyStateMachineBackend` for the default `legacy_fsm` backend and rejects
  `action_tree_shadow` as a shadow adapter rather than a runtime backend.
- `testbed/policies/hybrid/primitive_planner.py`: changed the default
  `_legacy_fsm_backend` construction to call `make_planner_backend()`. This is
  thin interface wiring only; all transition side effects remain adapter-owned.
- `tests/test_planner_backend_config.py`: added factory tests for default
  legacy backend construction, legacy aliases, action-tree shadow rejection, and
  fail-closed behavior-tree experimental config.

Scope guardrails kept:

- Default backend remains `legacy_fsm`.
- `action_tree_shadow` remains opt-in through the existing shadow adapter path;
  it is not treated as a runtime backend.
- `BehaviorTreeBackend` remains fail-closed and is not enabled by
  `planner_backend` config.
- No `_maybe_switch_skill()` branch order, thresholds, reason strings, policy
  reset timing, debug/rollout schema, token contract, or planner behavior
  changed.

Verification run for this pre-slice:

- Initial RED:
  `python -m pytest -q tests/test_planner_backend_config.py` failed during
  collection because `make_planner_backend` did not exist yet.
- `python -m pytest -q tests/test_planner_backend_config.py` -> `14 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_planner_backend_config.py tests/test_planner_runtime_contracts.py tests/test_behavior_tree_backend_contract.py`
  -> `20 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_effects.py tests/test_legacy_fsm_backend_return.py tests/test_primitive_action_tree.py tests/test_planner_golden_traces.py`
  -> `55 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_primitive_scheduler_facades.py`
  -> `120 passed`.
- `python -m compileall -q testbed/planner/planner_backend_config.py testbed/policies/hybrid/primitive_planner.py`
  -> no output.
- `git diff --check` -> no whitespace errors.

#### Phase 5 Selection Cleanup Record 2026-06-18

Implemented files:

- `testbed/planner/planner_backend_config.py`: added
  `PlannerBackendSelection` and
  `planner_backend_selection_from_policy_config()` so eval/runtime selection
  can explicitly distinguish runtime backends from shadow adapters while the
  existing string-returning API remains the compatibility surface.
- `tests/test_planner_backend_config.py`: added focused tests for the default
  legacy runtime selection, action-tree shadow adapter selection, selection
  immutability/hashability, and preservation of the existing string API.

Scope guardrails kept:

- Default backend remains `legacy_fsm`.
- `planner_backend_from_policy_config()` still returns the canonical backend
  string for existing eval/runtime metadata callers.
- `action_tree_shadow` remains the opt-in shadow adapter path and is still
  rejected by `make_planner_backend()`.
- `BehaviorTreeBackend` remains fail-closed and is not enabled by config.
- No `_eval.py`, `_maybe_switch_skill()` branch order, thresholds, reason
  strings, policy reset timing, debug/rollout schema, token contract, or
  planner behavior changed.

Verification run for this cleanup:

- Initial RED:
  `python -m pytest -q tests/test_planner_backend_config.py` failed during
  collection because `PlannerBackendSelection` did not exist yet.
- `python -m pytest -q tests/test_planner_backend_config.py` -> `17 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_planner_backend_config.py tests/test_primitive_action_tree.py tests/test_planner_runtime_contracts.py tests/test_behavior_tree_backend_contract.py`
  -> `43 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_agx_repoa_integration.py::RepoAAgxIntegrationTests::test_eval_policy_uses_agx_and_success_config tests/test_agx_repoa_integration.py::RepoAAgxIntegrationTests::test_experiment_record_collects_train_eval_and_qc_artifacts`
  -> `2 passed, 2 warnings` from existing `datetime.utcnow()` deprecations.
- `python -m pytest -p no:cacheprovider -q tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_effects.py tests/test_legacy_fsm_backend_return.py tests/test_planner_golden_traces.py`
  -> `35 passed`.
- `python -m compileall -q testbed/planner/planner_backend_config.py tests/test_planner_backend_config.py`
  -> no output.
- `git diff --check` -> no whitespace errors.

## Testing Strategy

Use layered tests in this order:

1. Contract tests for token/profile/schema/env-state source-of-truth.
2. Runtime contract tests for context, blackboard, result, and effects.
3. Capability tests that do not construct `PrimitivePlannerACTPolicy`.
4. Adapter parity tests that verify old private facades still behave.
5. Golden trace tests comparing default planner against legacy backend.
6. Shadow comparison tests for behavior tree backend.
7. Full repository test run before each commit that changes backend wiring.

## Rollback Plan

The pushed backup point can restore the pre-backend-interface state:

```bash
git switch fs/v2_4-refactor-tests
git reset --hard planner-backend-migration-base-2026-06-17
```

Use this only when intentionally discarding backend-interface work. Normal
development should prefer additive commits and targeted reverts.

## Implementation Guardrails

- Start with design and plan commits before runtime code.
- One migration phase per implementation slice.
- No semantic changes without explicit user confirmation.
- No new long-term module for a single helper.
- No backend may duplicate token/profile/schema constants.
- No backend may mutate `PrimitivePlannerACTPolicy` directly.
- All compatibility deletions require tests to move first and, if historically
  meaningful, deprecated records.

## Confirmed Implementation Decisions

These decisions replace the initial review questions and are the default for
the next implementation session:

- The first code phase uses the package `testbed/planner/runtime/`, not a
  standalone `planner_runtime.py` module.
- Coverage runtime state remains `CoverageServiceState` referenced by the
  blackboard for the initial phases.
- New code uses `planner_backend` as the planner backend config, metadata,
  registry, and experiment-record key. The short-lived
  `primitive_scheduler_runner` key from the action-tree shadow pre-slice was
  removed after review because it had not produced decisive experiment caches
  and duplicated the new backend-selection contract.
- Default execution remains `legacy_fsm` until the backend interface is proven
  behavior-identical. `BehaviorTreeBackend` stays opt-in and experimental until
  separately approved.
- `PrimitivePlannerACTPolicy` remains the public adapter, compatibility owner,
  low-level policy dispatch owner, and runtime effect applier while default
  planner logic migrates behind `PlannerBackend`.
- Any change to branch order, thresholds, reason strings, token contracts,
  debug/rollout schemas, default behavior, or reset timing still requires
  explicit confirmation before implementation.

#### Planner Backend Config Key Landing Record 2026-06-17

Implemented files:

- `testbed/planner/planner_backend_config.py`: owns planner backend config and
  metadata selection for eval/runtime paths.
- `testbed/planner/primitive_scheduler_runner.py`: removed. The short-lived
  `primitive_scheduler_runner` config/schema surface is not preserved as a
  compatibility alias.
- `testbed/runtime/_eval.py`: writes `planner_backend` into
  `eval_run_metadata.json` and recorded HDF5 metadata.
- `testbed/runtime/experiment_record.py`: records `eval.planner_backend`, uses
  `planner_backend` as the experiment-registry CSV column, and renders
  "Planner backend" in markdown records.
- `tests/test_planner_backend_config.py`: focused tests for canonical default,
  config parsing, removed-key rejection, metadata parsing, legacy module
  removal, and canonical-key error messaging.

Scope guardrails kept:

- Default backend remains `legacy_fsm`.
- `action_tree_shadow` remains the existing compatibility runner value; the new
  experimental `BehaviorTreeBackend` is not wired into config, eval, rollout, or
  `PrimitivePlannerACTPolicy`.
- Stale `primitive_scheduler_runner` config or metadata raises a clear error
  instead of silently falling back to `legacy_fsm`.
- No branch order, thresholds, reason strings, reset timing,
  debug/trace/rollout schema, token contract, or planner behavior changed.

Verification run for this cleanup:

- Initial RED collection:
  `python -m pytest --collect-only -q tests/test_planner_backend_config.py tests/test_primitive_action_tree.py tests/test_agx_repoa_integration.py::RepoAAgxIntegrationTests::test_eval_policy_uses_agx_and_success_config tests/test_agx_repoa_integration.py::RepoAAgxIntegrationTests::test_experiment_record_collects_train_eval_and_qc_artifacts`
  failed because `testbed.planner.planner_backend_config` did not exist yet.
- `python -m pytest -p no:cacheprovider -q tests/test_planner_backend_config.py`
  -> `10 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_primitive_action_tree.py`
  -> `20 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_agx_repoa_integration.py::RepoAAgxIntegrationTests::test_eval_policy_uses_agx_and_success_config tests/test_agx_repoa_integration.py::RepoAAgxIntegrationTests::test_experiment_record_collects_train_eval_and_qc_artifacts`
  -> `2 passed, 2 warnings` from existing `datetime.utcnow()` deprecations.
- `python -m pytest -p no:cacheprovider -q tests/test_planner_runtime_contracts.py tests/test_behavior_tree_backend_contract.py tests/test_legacy_fsm_backend.py tests/test_legacy_fsm_backend_effects.py tests/test_legacy_fsm_backend_return.py`
  -> `40 passed`.
- `python -m pytest -p no:cacheprovider -q tests/test_planner_golden_traces.py`
  -> `1 passed`.
- `git diff --check` and no-index whitespace checks for
  `testbed/planner/planner_backend_config.py` and
  `tests/test_planner_backend_config.py` -> no whitespace errors.
