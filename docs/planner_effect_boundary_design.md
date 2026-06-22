# Planner Effect Boundary Design

Status: **Phase 8 design source for planner effect-boundary work**.

This document defines the intended `PlannerEffect` boundary for the primitive
planner refactor. It is a design document only: no planner runtime behavior is
changed by this document.

The goal is to make the future decision backend return ordered, validated
effect requests while the execution kernel remains the only layer that applies
planner state mutations. This closes the largest remaining gap between the
current implementation and the execution/backend abstraction diagram.

## Current Problem

The current implementation has a useful execution template and a legacy FSM
backend boundary, but the backend branches still apply side effects through
callbacks:

```text
run_primitive_tick()
  -> decide_tick()
      -> LegacyFSMBackendAdapter
          -> _maybe_switch_skill()
              -> LegacyFSM*Branch.maybe_handle()
                  -> callbacks mutate PrimitivePlannerACTPolicy state
  -> dispatch_action()
  -> finalize_debug_state()
```

The existing `PrimitiveDecisionResult` intentionally records this as an
already-applied legacy outcome. That was the correct transition step, but it is
not the target abstraction. The target shape is:

```text
prepare_tick(obs)
  -> capability facts / status records
  -> decision_backend.decide_tick(facts)
  -> PrimitiveDecisionResult(effects=ordered requested effects)
  -> validate_effects(result)
  -> apply_effects_in_order(result.effects)
  -> dispatch_action(obs)
  -> finalize_debug_state()
```

Only the execution kernel or shell-side applier may mutate planner state.
Backends may choose, explain, and request effects, but must not call planner
private methods or write planner fields directly.

Current status after Phase 9.5: the default 4P mainline branch chain no longer
falls through to the broad `LegacyFSMBackendAdapter -> _maybe_switch_skill()`
callback. Bootstrap, dig, carry, dump, and return are handled through explicit
requested-effect branch decisions. Residual `pre_dig_align` behavior remains an
already-applied compatibility/parking path through a narrow residual adapter
because selected rollout evidence classifies it as not active in the mainline.

## Design Intent

This design answers one architecture question before any more code migration:
what kind of side effect is allowed to cross from a decision backend into the
execution layer?

It is not a request to immediately implement behavior trees, VLM backends, or a
full pure-effect runtime. It is the contract that future work must satisfy
before moving return handoff, direct handoff, legacy parking paths, or alternate
decision schemes.

The immediate expected outcome is:

- preserve the existing `legacy_fsm_side_effects_applied` compatibility layer;
- introduce a separate requested-effect model for future backend slices;
- make effect application order explicit in the execution template;
- prevent callback wrappers from becoming the long-term architecture;
- give return handoff and other coupled helpers a stable classification test:
  facts, decision, effect, reporting, compatibility, or legacy parking.

## Boundary Responsibilities

### Public Adapter

`PrimitivePlannerACTPolicy` remains the public policy surface for eval and
rollout. It preserves constructor compatibility, low-level policy construction,
public `reset()`, `predict()`, `debug_state()`, `rollout_summary()`, and
`planner_trace()` entry points.

The adapter should not become the permanent home for new algorithm logic. During
migration it may remain the shell that owns old private methods until each
responsibility has a focused module and parity coverage.

### Execution Kernel

The execution kernel owns tick ordering and effect application:

1. update boundary event
2. reset switch reason
3. update dig progress when the tick starts in `dig`
4. call decision backend
5. apply requested effects in order
6. account return timeout
7. dispatch action
8. record previous action
9. evaluate transition-completed/debug finalization

The important new invariant is that requested effects, once introduced, are
applied after decision and before action dispatch. That keeps the dispatched
low-level policy aligned with any skill switch, token invalidation, or terminal
request produced by the decision.

### Capability Layer

Capability modules expose read-only facts and status records. They may compute
geometry, gates, token status, coverage status, and handoff readiness facts, but
they must not apply planner state changes.

If building a status record requires mutating shell state, that path is not yet
a pure capability. It must remain a shell helper or be split into separate
read-only facts plus requested effects.

### Decision Backend

A decision backend owns decision scheme details, such as the legacy FSM branch
order, a future behavior tree, or a future constrained VLM/LLM packet.

It may:

- read tick preparation and capability facts;
- choose a branch path or node path;
- produce a switch reason from an approved reason source;
- return ordered semantic effects;
- emit diagnostics that reporting can display.

It must not:

- receive `PrimitivePlannerACTPolicy` or planner `self`;
- call private planner methods;
- mutate planner fields;
- construct low-level ACT observations;
- dispatch low-level policies;
- assemble debug or summary schemas;
- invent unconstrained public reason strings.

### Effect Applier

The effect applier is part of the execution kernel/shell boundary. It maps
semantic effect requests to existing shell operations while preserving current
observable behavior.

Early implementations may call old private methods internally. That is allowed
only inside the applier, not inside the backend. The applier is the transition
point where old shell mutation is gradually replaced by focused services.

## Effect Model

Effects should be semantic, ordered requests. They should not expose arbitrary
planner field names.

Initial fields:

```python
@dataclass(frozen=True)
class PlannerEffect:
    effect_type: str
    already_applied: bool = False

@dataclass(frozen=True)
class RequestedPlannerEffect(PlannerEffect):
    effect_type: str
    reason: str = ""
```

`already_applied=True` is reserved for the legacy compatibility layer. New
backend work should use requested effects with `already_applied=False`.

`PrimitiveDecisionResult` must remain able to represent both modes during the
transition:

```python
@dataclass(frozen=True)
class PrimitiveDecisionResult:
    decision_source: str
    status: PrimitiveDecisionStatus
    skill_before: str
    skill_after: str
    switch_reason: str
    effects: tuple[PlannerEffect, ...]
    side_effects_applied: bool
```

Target interpretation:

- `side_effects_applied=True`: legacy adapter already mutated state; the kernel
  records the outcome and does not apply requested effects.
- `side_effects_applied=False`: backend returned ordered requests; the kernel
  validates and applies them before dispatch.

## Allowed Effect Families

The first effect vocabulary should be intentionally small and semantic.

| Family | Example effects | Owner that applies it |
| --- | --- | --- |
| Skill lifecycle | `SwitchSkill(skill, reason)`, `RestartDigWithNewCut(reason)`, `RestartAfterFailedDig(reason)` | execution kernel / shell applier |
| Counters and holds | `IncrementDigBadReplanCount`, `SetDumpReadyHoldCount(value)`, `SetDumpDoneHoldCount(value)` | shell applier until counter ownership moves |
| Return cycle | `MarkReturnNextDigEventSeen`, `CompleteReturnTransition`, `SwitchToNextDigAfterReturn(reason_suffix)` | shell applier, then return handoff service |
| Coverage updates | `CompleteCoverageDig`, `CompleteCoverageDump(reason)`, `RejectCoverageCorridor(reason)` | coverage runtime service through applier |
| Coverage runtime | `RequestCoverageTerminalStop(reason, replace=False)`, `MaybeReopenCoveragePass(reason)` | coverage runtime service through applier |
| Token and plan lifecycle | `EnsureDigCutPlan`, `EnsureReturnTargetPlan`, `ClearDigCutPlan`, `InvalidatePendingDigCutPlan` | token/return planning services through applier |
| Diagnostics | `RecordCoverageDecisionEvent(event, payload)`, `RecordDecisionTrace(payload)` | reporting/coverage report boundary through applier |

Composite effects are allowed when the current behavior is itself a semantic
operation. For example, `RestartAfterFailedDig(reason)` is preferable to a long
list of low-level counter and token-field writes until that restart behavior is
separately extracted.

## Forbidden Effect Shapes

These shapes are not allowed because they preserve the current coupling behind a
new name:

- `SetPlannerAttr(name, value)`
- `CallPlannerMethod(name, args)`
- effects that carry callables, lambdas, bound methods, or planner `self`
- effects named after a single old private method when the method is not a
  stable domain responsibility
- effects created only because a private test expects them
- effects that promote `cell_entry` or `pre_dig_align` into the mainline backend
  without new rollout evidence and explicit approval

If a future backend seems to need one of these forbidden shapes, the migration
must stop and classify the path again.

## Ordering Rules

Effect ordering is part of the contract.

1. The backend returns effects in the exact order required for observable
   behavior.
2. The kernel validates the sequence before applying it.
3. Skill lifecycle effects that change the active policy must happen before
   action dispatch.
4. Token invalidation or plan creation must preserve the current timing relative
   to skill switch and policy reset.
5. Coverage completion, rejection, and terminal-stop events must preserve
   current debug/trace/summary payload order.
6. Reporting may read the result of applied effects, but reporting cannot apply
   effects or decide transitions.

Any uncertain ordering around branch order, reason strings, policy reset timing,
token clearing, coverage trace payloads, or terminal-stop requests is a stop
condition.

## Validation Rules

The effect applier must reject effect sequences that break the architecture
contract:

- `already_applied=True` mixed with requested effects in the same result;
- requested effects returned from a backend marked as legacy already-applied;
- unknown effect types;
- callable or planner-object payloads;
- arbitrary attribute names;
- reason strings not produced by approved legacy reason helpers or explicit
  backend contracts;
- effect families not allowed for the current path classification.

Early validation can be implemented with focused tests before every effect
family has concrete classes.

## Migration Strategy

### Stage 1: Keep Legacy Outcome Compatibility

Do not rewrite the current backend branches immediately. Keep
`LegacyFSMBackendAdapter` and `PrimitiveDecisionResult.from_legacy_fsm_outcome`
as the already-applied compatibility path.

Phase 9.5 retires this broad adapter from the default mainline decision path.
`LegacyFSMBackendAdapter` may remain only as compatibility/test scaffolding for
the old callback shape; it is no longer the architecture source of truth for
bootstrap/dig/carry/dump/return.

This preserves parity while the requested-effect contract is introduced and
tested independently.

### Stage 2: Add Requested Effect Contract

Phase 8.1 implements the foundation for this stage only. It extends the
decision contract so a result can be either:

- a legacy already-applied outcome with `side_effects_applied=True`; or
- an ordered requested-effect result with `side_effects_applied=False`.

The execution template validates the decision contract and invokes the
requested-effect applier after `decide_tick()` and before return-timeout
accounting or action dispatch. The current `PrimitivePlannerACTPolicy` bridge
keeps the default legacy FSM path as already-applied, so no requested effects
are applied in normal rollout/eval behavior.

The Phase 8.1 validator is intentionally foundational. It rejects mixed
already-applied/requested results, callable payloads, planner `self` payloads,
and method-call or arbitrary planner-attribute effect shapes. It does not yet
define concrete effect-family classes, migrate a branch, or approve a requested
effect vocabulary for live behavior.

Phase 8.2 tightens the real `PrimitivePlannerACTPolicy` shell bridge. The fake
execution-template hook may still apply requested effects in ordering tests,
but the production planner shell now treats non-empty requested effects as a
contract error until concrete live effect-family appliers are implemented.
Empty requested-effect tuples remain a no-op so future pure-decision backends
can represent "no requested mutation" without changing tick behavior.

Phase 8.3 defines the first concrete requested-effect family,
`SwitchSkillEffect(target_skill_name, switch_reason)`. The real shell applier
may apply only this family by calling the existing `_set_skill(skill, reason)`.
All other requested effects continue to fail fast in the real shell. This phase
does not convert bootstrap, dig, carry, dump, return, direct handoff, or any
legacy branch to emit `SwitchSkillEffect`.

Introduce requested-effect result support without changing planner behavior:

- `PrimitiveDecisionResult` can represent `side_effects_applied=False`;
- `run_primitive_tick()` has a narrow apply-effects hook after decision and
  before return timeout/action dispatch;
- fake backend tests prove ordered effect delivery;
- validation tests reject forbidden shapes.

This stage still does not migrate a live branch.

### Stage 3: Convert One Confirmed-Live Branch

Convert exactly one confirmed-live branch from callback mutation to requested
effects. The likely first branch is the simplest branch that can prove the
model, not necessarily the most coupled branch.

Candidate order:

1. bootstrap branch: `SwitchSkill(next_skill, bootstrap_to_*)`
2. return branch event latch only: `MarkReturnNextDigEventSeen`
3. carry/dump hold-count update only

Do not start with direct handoff or failed-dig restart. Those paths combine
skill lifecycle, coverage, token planning, and return state, so they should wait
until the simple effect path is proven.

Phase 9.1 converts only the 4P mainline bootstrap branch to the requested
`SwitchSkillEffect` path. The backend branch now returns
`PrimitiveDecisionResult(side_effects_applied=False)` with
`SwitchSkillEffect(target_skill_name=next_skill, switch_reason=f"bootstrap_to_{next_skill}")`,
and the execution hook applies it through the real shell applier before action
dispatch. The compatibility `maybe_handle()` facade remains for legacy callers,
but the default tick decision path no longer completes bootstrap by direct
callback mutation. This phase does not migrate dig, carry, dump, return,
direct handoff, coverage, token planning, or `pre_dig_align` internals.

Phase 9.2 converts the 4P mainline `return` branch to ordered return-cycle
requested effects. The backend branch now emits
`MarkReturnNextDigEventSeenEffect`, `CompleteReturnTransitionEffect`, and
`SwitchToNextSkillAfterReturnEffect(reason_suffix)` in the same order as the
old callback mutation path. The shell applier still owns the actual mutations:
it latches next-dig events, completes the return transition/cycle counters, then
computes the next skill with `_next_skill_after_return_transition()` before
calling `_set_skill(next_skill, f"return_to_{next_skill}_{reason_suffix}")`.
This preserves the historical requirement that the cycle index is updated
before the pre-dig gate chooses `dig` or `pre_dig_align`. This phase does not
migrate direct-handoff helper internals, dig, carry, dump, coverage, token
planning, or `pre_dig_align` branch behavior.

Phase 9.3 makes the requested-effect applier observation-aware and converts the
4P mainline `carry` and `dump` branches to ordered requested effects. The
execution hook still runs after `decide_tick()` and before return-timeout
accounting or action dispatch, but it now passes the current `obs` to the shell
applier so semantic effects can use current observation facts without carrying
callbacks or planner objects. The converted carry/dump branches emit hold-counter
effects, dump-start deposited-mass-from-observation, coverage-dump completion,
return/direct-handoff requests, and existing `SwitchSkillEffect` for
carry-to-dump. The shell applier maps these effects to the existing shell
helpers and preserves old effect ordering. This phase does not migrate the dig
branch, direct-handoff helper internals, `pre_dig_align`, `cell_entry`, token
planning, or backend selection.

Phase 9.4 converts the remaining confirmed-live 4P mainline `dig` branch to
ordered requested effects. The branch now emits concrete dig semantic effects
for exit-guard failed replans, bad-dig replans, dig-complete low-payload
replans, coverage corridor rejection, failed-dig restart, coverage-dig
completion, and the existing `SwitchSkillEffect` for dig-to-carry. The
execution shell applies those effects in order using existing helper methods.
`CompleteCellEntryDigCompatibilityEffect` exists only to preserve the old
cell-entry completion callback when the old dig-to-carry path would have called
it; it is explicitly compatibility-only and does not promote `cell_entry` into
the target backend architecture. This phase does not migrate token planning,
coverage metric internals, return direct-handoff internals, `pre_dig_align`,
5P paths, behavior-tree/VLM/LLM backend selection, or planner runtime
directories.

Phase 9.5 removes the broad already-mutating legacy fallback from the default
decision bridge. The default branch order is now explicit:
bootstrap -> dig -> carry -> dump -> return -> residual pre-dig-align parking.
The residual path uses a narrow `LegacyFSMResidualPreDigAlignAdapter` and the
shell helper `_maybe_handle_pre_dig_align_skill(obs)` so parked pre-dig-align
behavior can remain already-applied without allowing a hidden callback backdoor
for mainline branches. Unknown or unclassified skills now fail fast instead of
silently re-entering `_maybe_switch_skill()`.

### Stage 4: Expand Effect Families From Evidence

Each new family must be justified by a confirmed-live rollout behavior and a
focused parity test. The expansion order should follow the architecture plan,
not callback convenience.

## How This Governs Return Handoff And Other Coupled Paths

Return direct handoff, coverage terminal stop, pre-dig parking, and 5P
compatibility must be analyzed under this contract.

For each path, answer:

1. Is the path confirmed-live, compatibility, report-only, legacy parking, or
   dead-candidate?
2. Which fields are read-only facts?
3. Which branch choice is a decision?
4. Which state changes are requested effects?
5. Which state changes must remain shell-owned during transition?
6. Which observable fields are protected by the golden-window parity harness?
7. Does the proposed effect reduce coupling, or is it a callback wrapper with a
   new name?

If a path cannot answer these questions cleanly, it is not ready for migration.

## Expected Architecture Coverage

Completing this design fills these pieces of the overall architecture:

- defines the missing contract between `PrimitiveDecisionBackend` and execution
  kernel;
- separates decision result recording from requested mutation;
- defines which layer owns effect application;
- gives alternate backends a stable mutation interface without access to planner
  private methods;
- keeps `cell_entry` and `pre_dig_align` out of the mainline backend unless
  future evidence re-approves them;
- provides a rule for evaluating return direct handoff and other coupled helper
  chains after the top-level effect model is accepted;
- prevents the current callback-based legacy backend from becoming the final
  abstraction.

It does not complete these pieces:

- implementation of concrete requested-effect classes;
- conversion of any live branch from callbacks to requested effects;
- behavior-tree or VLM backend implementation;
- 5P compatibility audit;
- legacy parking cleanup or deletion.

## Verification Plan

Documentation-only changes that introduce or update this design should run:

```bash
git diff --check
python scripts/planner_refactor_guard.py --check-plan-contract
python scripts/planner_refactor_guard.py --check-skill-contract
```

The first implementation slice based on this design should additionally run:

```bash
python -m pytest -q tests/test_primitive_decision_contract.py tests/test_primitive_execution_template.py
python -m pytest -q tests/test_planner_current_code_parity.py
python -m compileall -q testbed/planner/primitive_decision.py testbed/planner/primitive_execution.py testbed/policies/hybrid/primitive_planner.py
```

Any slice that converts a real branch must also run the focused branch tests and
golden-window parity harness that cover that branch's observable behavior.

## Stop Conditions

Stop before implementation when:

- an effect needs arbitrary planner attribute writes;
- an effect mainly wraps an old private method without a stable semantic name;
- effect ordering relative to skill switch, policy reset, token clearing, or
  coverage reporting is uncertain;
- the path lacks rollout evidence and is not a compatibility owner;
- the path would promote `cell_entry` or `pre_dig_align` into mainline
  architecture without explicit approval;
- the first implementation slice tries to convert multiple branches or multiple
  effect families at once.
