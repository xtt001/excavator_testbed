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
  builds PlannerTickContext from obs, boundary event, blackboard, services,
  policies, and compatibility config

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

Open decision: coverage may remain in `CoverageServiceState` and be referenced
by the blackboard, or it may be copied into a generic blackboard object. The
first implementation phase should avoid forcing that decision.

## Migration Phases

### Phase 1: Runtime Contract Skeleton

Add `PlannerTickContext`, `PlannerTickResult`, `PlannerRuntimeEffect`, and
`PlannerBackend` in a focused planner runtime module. Add tests for construction,
immutability where appropriate, and effect ordering.

Default runtime behavior remains unchanged.

### Phase 2: Coverage As First Blackboard Domain

Use the recent coverage dig-cut activation work as the first state-domain
candidate. Expose coverage state/effects through explicit runtime contracts while
keeping `DigCoverageMixin` as a compatibility adapter.

Definition of done:

- coverage selection and dig-cut activation can be tested without constructing
  `PrimitivePlannerACTPolicy`
- adapter tests verify old facade behavior
- no debug/trace/rollout key changes

### Phase 3: Legacy FSM Backend

Move `_maybe_switch_skill()` orchestration into `LegacyStateMachineBackend`
without changing behavior. Initially, it may share capability calls with the
adapter, but it must return `PlannerTickResult` and effects instead of directly
writing final state.

Definition of done:

- legacy backend golden trace matches current default planner
- switch reason, cycle index, transition counts, token source, and reset counts
  match existing tests

### Phase 4: Behavior Tree Backend

Refactor `PrimitiveActionTreeRunner` into `BehaviorTreeBackend`. It must use
`PlannerTickContext`, capability services, blackboard state, and runtime effects.
It must not read or write `policy._xxx`.

Definition of done:

- behavior tree shadow trace matches legacy backend golden traces
- divergence reports include node path, reason, and blackboard/effect diff
- behavior tree stays opt-in until explicitly promoted

### Phase 5: Default Backend Migration

Once `LegacyStateMachineBackend` is behavior-identical and the adapter applies
effects through the runtime path, make default planner execution go through the
backend interface with `legacy_fsm` selected by default.

Behavior tree or other advanced planners remain explicit experimental choices
until separately approved.

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

## User Review Questions

Before implementation, confirm:

- Should the first code phase use module name `planner_runtime.py` or a package
  such as `testbed/planner/runtime/`?
- Should coverage runtime state remain `CoverageServiceState` referenced by the
  blackboard for now?
- Should the config key stay `primitive_scheduler_runner` during migration, or
  should new code introduce `planner_backend` while keeping the old key as an
  alias?
