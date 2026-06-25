# Planner Decision-Theory Backend Pre-Implementation Contract

Status: **active pre-implementation contract for the first decision-theory
primitive decision backend**.

This document locks the work that should be complete before production code for
a new decision-theory backend starts. It is narrower than
`docs/planner_scheduling_backend_design.md`: the backend guide describes the
generic extension surface, while this contract defines the first scoped
decision-theory backend attempt.

Use this document with:

- `docs/planner_current_architecture.md`
- `docs/planner_scheduling_backend_design.md`
- `docs/planner_primitive_interface_standard.md`
- `tests/test_primitive_backend_ready_contract.py`
- `tests/test_primitive_decision_runtime.py`
- `tests/test_primitive_decision_contract.py`
- `tests/test_primitive_effects.py`

## Readiness Position

The repository is ready to start a **test-scoped prototype backend** because:

- `PrimitiveDecisionRuntime` can select a registered backend factory by name;
- `PrimitiveDecisionRuntimePorts.backend_factories` is the registration surface;
- fake-backend tests prove non-legacy factory selection and unsupported-backend
  fail-fast behavior;
- decision inputs, backend facts, decision results, requested effects, and
  effect application are explicit contracts;
- primitive-lane tests guard against importing the public policy shell.

The repository is not yet ready to make a new backend a production default
because:

- `PrimitivePlannerACTPolicy` registers only `legacy_fsm`;
- there is no user-facing backend selector in constructor or YAML config;
- the current backend facts packet is still transition-oriented and may not
  expose all facts a decision-theory model needs;
- no alternate backend implementation exists;
- no rollout parity or A/B acceptance target has been chosen for the new model.

## Initial Backend Scope

Working backend name: `decision_theory`.

Expected module location:

```text
testbed/planner/primitive/decision/backends/decision_theory.py
```

The first implementation must be test-scoped unless an explicit follow-up phase
adds production registration and config routing.

The first implementation may:

- implement `PrimitiveDecisionBackendFactory`;
- build a requested decision backend compatible with `PrimitiveDecisionBackend`;
- optionally build a compatibility backend only when the compatibility behavior
  is explicitly specified;
- consume `PrimitiveBackendDecisionInput`;
- read common facts and typed backend facts through
  `PrimitiveBackendFactsAccess`;
- return `PrimitiveDecisionResult.from_requested_effects(...)`;
- emit only ordered `RequestedPlannerEffect` records.

The first implementation must not:

- import `PrimitivePlannerACTPolicy` or `testbed.policies.hybrid`;
- read or write policy private attributes;
- call low-level ACT policy `predict()`;
- mutate coverage, token, return, cycle, execution, or report state directly;
- create token schemas, report schemas, or checkpoint compatibility rules;
- promote `cell_entry`, 5P, BT, VLM, LLM, or plugin routing by implication;
- become the default production backend.

## Decision Responsibility

The first backend should start with primitive scheduling decisions only:

- active primitive skill identity;
- whether the active skill should stay active;
- whether the active skill should request a transition through existing effects;
- a decision source and reason string that make the result auditable.

The first backend should not own:

- low-level action generation;
- token construction or token injection;
- coverage scoring or candidate selection;
- reset, timeout, lifecycle, or report assembly;
- return-handoff state mutation.

If the decision-theory model needs any of those domains, add a typed fact or
effect boundary first and test that boundary before adding the model rule.

## Facts Contract

Allowed initial facts:

- `PrimitiveBackendDecisionInput.common`;
- `PrimitiveDecisionContext` identity fields;
- lazy backend facts exposed by `PrimitiveBackendFactsAccess`:
  - `bootstrap_decision()`;
  - `dig_transition()`;
  - `carry_transition()`;
  - `dump_transition()`;
  - `return_transition()`.

Raw `obs` reads inside the backend are allowed only as a temporary test-only
bridge when a missing fact has been named in the test and the follow-up typed
fact owner is documented. Production backend logic should use typed facts.

Before implementation starts, decide whether the first backend needs additional
neutral facts for:

- coverage state, active corridor, rejected corridor, or remaining-depth status;
- token source, fallback, pending next-dig token, or return-envelope status;
- cycle counters, completed dumps, failed-replan counters, or target gate;
- return handoff readiness and direct-handoff gate state;
- pre-dig-align readiness, timeout, or surface-guard status.

If any item is required, create a focused facts contract before using it in the
backend.

## Effect Contract

The first backend should reuse existing requested effects whenever possible:

- `SwitchSkillEffect`;
- `CompleteCoverageDigEffect`;
- `RejectActiveCoverageCorridorEffect`;
- `RestartAfterFailedDigEffect`;
- `RestartDigWithNewCutEffect`;
- `ReplanOrRestartPreDigAlignEffect`;
- `SetDumpReadyHoldCountEffect`;
- `SetDumpStartDepositedMassFromObservationEffect`;
- `SetDumpDoneHoldCountEffect`;
- `CompleteCoverageDumpEffect`;
- `SetReturnOrDirectHandoffEffect`;
- `MarkReturnNextDigEventSeenEffect`;
- `CompleteReturnTransitionEffect`;
- `SwitchToNextSkillAfterReturnEffect`.

New requested effects are allowed only when all of these are true:

- the effect cannot be represented by an existing effect record;
- the state owner that will apply it is already identified;
- `validate_decision_effect_contract(...)` rejects invalid shapes;
- `RequestedEffectApplier` applies it through explicit focused ports;
- tests prove ordered application and no direct policy mutation.

## Registration Plan

Phase A: test-only registration.

- Register the factory inside focused tests through
  `PrimitiveDecisionRuntimePorts.backend_factories`.
- Select it through `PrimitiveDecisionRuntimeConfig(backend_name="decision_theory")`.
- Keep production shell registration unchanged.

Phase B: optional production opt-in.

- Add an explicit constructor/config field only after Phase A passes.
- Keep `legacy_fsm` as the default.
- Register the new factory in `PrimitivePlannerACTPolicy` only as a narrow weld.
- Update config docs and examples only for the explicit opt-in path.

Phase C: rollout or A/B evaluation.

- Run the selected focused tests first.
- Then run the agreed rollout evidence gate.
- Record the result in `docs/planner_rollout_evidence_refactor_log.md`.

## Required Tests

Before backend production registration:

- a backend unit test proves the factory builds requested and compatibility
  backends with the agreed behavior;
- a decision-input test proves the backend consumes `PrimitiveBackendDecisionInput`
  instead of policy shell state;
- a runtime test proves `decision_theory` can be selected by
  `PrimitiveDecisionRuntimeConfig.backend_name`;
- a contract test proves returned results use ordered requested effects and pass
  `validate_decision_effect_contract(...)`;
- a guard test proves primitive-lane modules still do not import
  `testbed.policies.hybrid.primitive_planner`;
- a no-default-change test proves `legacy_fsm` remains the production default;
- facts tests cover any newly exposed typed fact views;
- effect tests cover any newly introduced requested effects.

Suggested focused suites:

```text
python -m pytest -q tests/test_primitive_decision_runtime.py \
  tests/test_primitive_decision_contract.py \
  tests/test_primitive_backend_ready_contract.py \
  tests/test_primitive_backend.py \
  tests/test_primitive_effects.py
```

Add `tests/test_primitive_decision_theory_backend.py` for the new backend module.

## Acceptance Gate

Implementation may start after these decisions are explicit in the task or test
names:

- whether the first backend is parity-preserving, shadow-only, or
  semantics-changing;
- which active skills it handles first;
- whether `bootstrap` and `pre_dig_align` are handled, delegated, or rejected;
- which typed facts are sufficient for the first decision rule;
- which existing effects are sufficient for the first decision rule;
- whether production config routing is in scope for the first slice.

If any answer is unknown, start with a test-only backend that handles one narrow
skill decision and fails fast outside its declared scope.

## Documentation Sync

When backend code is added, update:

- this contract with the accepted scope;
- `docs/planner_scheduling_backend_design.md` if the generic integration surface
  changes;
- `docs/planner_primitive_interface_standard.md` when a concrete alternate
  backend contract is accepted;
- `docs/planner_current_architecture.md` only if actual runtime flow or
  production registration changes;
- `docs/planner_rollout_evidence_refactor_log.md` with tests and rollout
  evidence.
