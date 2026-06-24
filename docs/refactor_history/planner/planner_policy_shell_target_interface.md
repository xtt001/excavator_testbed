# Primitive Policy Shell Target Interface Design

Status: **historical design target, not a production import contract**.

This document defines the responsibility boundary used to keep
`PrimitivePlannerACTPolicy` converging toward an external API shell. It is a
planning and review artifact. Do not import it from production code, and do not
write tests that depend on the pseudo-interfaces below as runtime objects.

The immediate purpose is to judge future refactor slices. A slice should move
work only when it clarifies ownership and reduces coupling. Line count is only a
maintenance signal; it is not the target.

## Target Statement

`PrimitivePlannerACTPolicy` should expose the public primitive policy adapter:

- constructor-level adapter wiring;
- `reset(...)`;
- `predict(...)`;
- `debug_state(...)`;
- `rollout_summary(...)`;
- `planner_trace(...)`.

Focused runtime, service, backend, fact, token, coverage, return-handoff,
effect, and report owners should own planner internals. The policy shell may
hold or lazily create focused owners, but it should not own their domain logic,
state mutations, fact projection, or report assembly.

The current backend-ready phase is closed for interface readiness: backend facts
are neutral, the generic decision runtime can select registered backend
factories, default production registration remains `legacy_fsm`, and fake
backend tests prove the generic runtime contract. Production backend plugin or
config routing is intentionally not part of this target.

## Boundary Decision Rubric

Use these checks before choosing a migration slice.

| Question | Shell answer | Focused-owner answer |
| --- | --- | --- |
| Is the responsibility part of the public policy API surface? | Keep in shell. | Move out. |
| Does it need low-level policy handles, the boundary detector object, or external adapter construction? | Shell may weld it through typed ports. | It should not receive planner `self`; pass explicit handles or services. |
| Does it read or write a focused runtime state owner such as coverage, token, return, cycle, or execution state? | Shell may hold the owner object. | The focused owner/service should own internal reads, writes, and transitions. |
| Does it project observation facts or transition facts? | Shell should not own projection. | Use typed fact sources such as `PrimitiveObservationFacts` or backend facts sources. |
| Does it assemble public debug, summary, or trace schema? | Shell exposes the public method only. | Report runtimes own schema assembly and compatibility payloads. |
| Does it choose backend behavior or invoke decision backends? | Shell may choose default registration. | Runtime/backend contracts own backend selection, invocation, and fail-fast behavior. |
| Is the dependency visible only because tests call a private method? | Do not protect it. | Move tests to the focused production contract or classify the old hook as test-only. |
| Would the new module mainly forward to old private methods? | Reject the slice. | A real owner accepts typed inputs and owns a stable responsibility. |

Protection is a constraint, not the objective. It protects branch order, reason
strings, typed effects, public schemas, token/coverage/return/reset semantics,
default legacy-FSM fail-fast behavior, and parked public `cell_entry` /
`pre_dig_align` surfaces. It must not preserve private wrappers only because
tests mention them.

## Ideal Shell Shape

This sketch describes the intended shape; it is not executable code.

```python
class PrimitivePlannerPublicShell:
    def __init__(self, *, low_level_policies, boundary_detector, adapter_config):
        ...

    def reset(self) -> None:
        ...

    def predict(self, obs: dict, deterministic: bool = False):
        ...

    def debug_state(self) -> dict:
        ...

    def rollout_summary(self) -> dict:
        ...

    def planner_trace(self) -> dict:
        ...
```

Allowed shell welds:

- apply public adapter config normalization to compatibility fields while that
  public constructor surface remains stable;
- hold low-level policy handles and the boundary detector;
- construct focused runtime roots from explicit typed ports;
- hold focused state owner objects and replace them on reset;
- register the default legacy decision backend factory;
- call public runtime kernels for reset, predict, and report methods.

Forbidden shell responsibilities:

- coverage scoring, raw-field projection, candidate scoring, completion,
  rejection, reopen, terminal-stop, or coverage report internals;
- token planner algorithms, prior clamping, or
  return-envelope token planning internals;
- backend fact projection, concrete decision branch construction inside the
  generic runtime, or planner-self backend ports;
- requested-effect internals beyond invoking a focused requested-effect runtime;
- debug, summary, or trace schema assembly beyond exposing public methods;
- broad mutable bags, blackboards, planner-self ports, callback bags, or config
  dictionaries that recreate planner `self` indirectly.

## Owner Matrix

| Responsibility | Target owner | Shell role |
| --- | --- | --- |
| Public adapter API | `PrimitivePlannerACTPolicy` / public runtime kernel | Expose methods and preserve public compatibility. |
| Adapter config normalization | `PrimitivePlannerAdapterConfigNormalizer` and focused config owners | Invoke normalization and apply compatibility field updates. |
| Execution tick order | `PrimitiveExecutionRuntime` plus public runtime kernel | Provide typed runtime/service welds. |
| Decision backend selection | `PrimitiveDecisionRuntime` and backend factories | Register default backend factory and pass config. |
| Backend facts | backend facts and decision facts modules | No direct fact projection. |
| Requested effects | `PrimitiveRequestedEffectRuntime` / `RequestedEffectApplier` | Invoke focused runtime from execution. |
| Return handoff | `PrimitiveReturnHandoffRuntime` and return handoff services | Provide explicit state/config/service ports. |
| Coverage selection/effects/report | coverage selection/effect/report runtimes | Hold state and provide only shell-level dependencies. |
| Token observation/planning | token observation/planning runtimes and `PrimitiveTokenPlannerFactory` | Hold token state and provide a thin static factory weld. |
| Debug/summary/trace | `PrimitiveReportCompositionRuntime` and report runtimes | Expose public report methods. |
| Parked `cell_entry` / `pre_dig_align` | compatibility state/report owners | Preserve public schema while keeping behavior parked. |

## Current Boundary Assessment

The current code is aligned with the backend-ready interface target but is not a
finished API shell.

Already aligned:

- backend-neutral facts and generic decision runtime selection;
- concrete legacy-FSM factory composition contained outside the generic runtime;
- requested-effect runtime composition outside the policy shell;
- return-handoff runtime composition outside the policy shell;
- token planner factory construction outside the policy shell;
- coverage static report/selection/effect config construction outside the
  policy runtime port methods via `PrimitiveCoverageStaticConfig`;
- public runtime kernel for `reset`, `predict`, and report methods.

Remaining policy-shell assessment areas:

- coverage report/selection/effect composition is production-significant, but
  static coverage config is now owned by the coverage lane. The shell still
  welds live coverage state and callbacks for cycle index, skill name,
  observation facts, selection service, pass reopen, terminal-stop, decision
  event recording, remaining depth, and corridor attempt limits;
- token observation/planning remains production-significant; concrete token
  planner factory construction is now owned by `PrimitiveTokenPlannerFactory`;
- adapter config normalization is large but not automatically wrong. Split it
  only when a focused config owner is clearer than the current normalizer, not
  because of line count;
- lazy focused state owner construction can remain in the shell while it is only
  identity/lifecycle storage. Internal state mutation belongs to focused owners.

## Shell Weld Classification Snapshot

This 2026-06-25 snapshot classifies the current
`PrimitivePlannerACTPolicy` shape after package-layout relocation, token
planner factory cleanup, and coverage static config cleanup. It is an accepted
boundary decision, not a request to keep migrating code by line count.

Accepted shell welds:

| Current policy surface | Classification | Reason |
| --- | --- | --- |
| `__init__`, `_apply_adapter_config_state` | accepted shell weld | Public adapter construction, low-level policy handles, and constructor compatibility field application belong at the public shell. Focused config owners already normalize the stable snapshots. |
| `reset`, `predict`, `debug_state`, `rollout_summary`, `planner_trace`, `_primitive_runtime_kernel_runtime*` | do not migrate | These are public API and public-runtime-kernel routes. Moving them would hide the adapter shell rather than clarify ownership. |
| Lazy state identity owners such as `_primitive_execution_runtime_state`, `_primitive_cycle_runtime_state`, `_primitive_return_runtime_state`, `_primitive_token_runtime_state`, `_coverage_runtime_state`, and simple status properties | accepted shell weld | The shell may hold focused state object identity and reset replacement timing. State mutation and interpretation remain inside focused owners. |
| `_primitive_reset_lifecycle_*`, `_primitive_execution_runtime_*`, `_primitive_boundary_event_runtime_*`, `_primitive_tick_finalization_runtime_*`, `_action_dispatch_*` | accepted shell weld | These methods assemble typed runtime/service ports and weld low-level policy handles, boundary detector, and live state into focused owners. |
| `_decision_runtime`, `_decision_runtime_config` | do not migrate now | The shell is the default production registration point for the legacy backend factory. Generic backend selection and invocation already live in the decision runtime; production plugin/config routing is out of scope. |
| `_primitive_requested_effect_runtime_*`, `_primitive_return_handoff_runtime_*`, `_primitive_skill_lifecycle*`, `_primitive_dig_recovery*`, `_primitive_dig_progress_runtime*` | accepted shell weld | These are dynamic state/service/callback welds into focused effect, return, lifecycle, recovery, and progress owners. |
| `_primitive_coverage_static_config` | accepted shell weld | This is the single shell entry that snapshots normalized static coverage fields into `PrimitiveCoverageStaticConfig`. It replaces the previous spread of static coverage lambda ports. |
| `_primitive_coverage_report_runtime_*`, `_primitive_coverage_selection_runtime_*`, `_primitive_coverage_effect_runtime_*` | accepted shell weld | After static config extraction, these methods hold only live coverage state, cycle/skill state, observation-fact projection calls, selection/effect/report runtime calls, decision-event recording, remaining-depth, and corridor-attempt-limit wiring. |
| `_primitive_token_planner_factory`, `_primitive_token_observation_runtime_*`, `_primitive_token_planning_runtime_*` | accepted shell weld | Token planner construction is owned by `PrimitiveTokenPlannerFactory`; the shell now only wires token state, coverage state, observation facts, planner factories, and runtime cross-calls. |
| `_primitive_report_composition_runtime_*` | accepted shell weld | The port list is still broad because it wires public debug/summary/trace schema sources. Report assembly and compatibility payload ownership live in the report lane, so this should not be migrated just because it is visually large. |

Future candidates, but not current slices:

| Current policy surface | Candidate reason | Deferral reason |
| --- | --- | --- |
| `_primitive_scripted_bootstrap_runtime_config` | Small static config snapshot could eventually move beside scripted-bootstrap runtime. | Current method is narrow, behavior-covered, and not blocking backend-ready closure. |
| `_semantic_boundary_profile_active` | Contains a small profile-name predicate. | It is a tiny compatibility gate and migrating it now would create another wrapper without reducing meaningful coupling. |
| Adapter-config field application details | Some public constructor compatibility fields may eventually narrow further. | The normalizer already owns config parsing; the shell still has to apply the public adapter surface. |

Explicit non-migration decisions:

- Do not move public adapter methods, reset/predict/report shell routes, or
  report-schema source wiring only because `PrimitivePlannerACTPolicy` is still
  over one thousand lines.
- Do not split the default `legacy_fsm` backend registration unless production
  backend plugin/config routing becomes an explicit goal.
- Do not move low-level policy handle ownership or dispatch wiring out of the
  shell. Focused dispatch services own dispatch behavior; the shell owns the
  low-level handles.
- Do not preserve or recreate private wrappers only because tests mention them.
  If a path matters only in tests, migrate tests to the focused production
  contract or classify that path as test-only.

## Slice Selection Rule

For each next migration slice, write the target owner first:

1. name the production responsibility, not the private method cluster;
2. name the focused owner that should own it;
3. list behavior contracts that must not change;
4. list private policy methods/tests that may be reclassified as test-only;
5. reject the slice if the proposed owner would only forward to old private
   methods or would need planner `self`.

The next phase after this classification is contract readiness closure, not
another automatic shell cleanup. A new implementation slice should start only
when it names a production responsibility that is still wrongly owned, not when
it merely finds a long private method or a test that calls one.
