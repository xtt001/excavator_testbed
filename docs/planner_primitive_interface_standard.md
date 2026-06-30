# Primitive Planner Interface Standard

Status: **active interface target and implementation standard**.

This document defines the target primitive planner interface boundaries and
compares them with the current Phase 9.91 implementation. It is intentionally
not a snapshot-only inventory. Use it to decide whether future refactor slices
move the code toward the current architecture entry point in
`docs/planner_current_architecture.md` and the backend guide in
`docs/planner_scheduling_backend_design.md`.

The current implementation is best described as **default legacy FSM
backendified with focused services** plus a non-default behavior-tree shadow
backend skeleton. It is not yet a fully backend-agnostic planner where
behavior-tree, VLM, or learned decision backends can be swapped in without
additional interface work.

Current maturity statement: `default legacy FSM backendified with focused services`.

## Source Documents

- `docs/planner_current_architecture.md`
- `docs/planner_scheduling_backend_design.md`
- `docs/planner_decision_backend_contract.md`
- `docs/planner_to_act_conceptual_contract.md`
- `docs/v2_5_rollout_issue_record_2026_06_30.md`
- `AGENTS.md`

## Active Reference Set

Planner interface work must use the following explicit reference set instead of
relying on memory, deleted development plans, or unnamed old documents:

- primary architecture target: `docs/planner_current_architecture.md` and this
  interface standard;
- future backend target:
  `docs/planner_scheduling_backend_design.md`;
- conceptual control contract:
  `docs/planner_to_act_conceptual_contract.md`;
- decision backend, trace, validation, and backend-selection contract:
  `docs/planner_decision_backend_contract.md`;
- V2.5 rollout configuration context:
  `docs/v2_5_rollout_issue_record_2026_06_30.md`;
- repository governance: `AGENTS.md`;
- live code facts: `testbed/policies/hybrid/primitive_planner.py`, focused
  modules under `testbed/planner/`, and focused primitive tests.

Deleted planner migration plans, evidence reports, archived refactor drafts, and
prompt templates are historical scaffolding only. Do not recreate them as active
sources of truth for this branch.

## Maturity Statement

Current maturity:

- public adapter compatibility: **mostly achieved**
- tick execution ordering: **achieved for one-tick execution**
- boundary-event tick source boundary: **achieved for prev-action gating and
  typed observation projection through `PrimitiveBoundaryEventRuntimeService`;
  the policy shell no longer owns the live `BoundaryDetector.update(...)`
  argument assembly**
- legacy FSM mainline branch conversion to requested effects: **achieved**
- capability/status provider boundary for legacy FSM: **achieved for the
  current legacy-FSM transition-status chain;
  dig/carry/dump/return transition status assembly is focused, and dig-exit
  overshoot now derives from observation facts plus the coverage state owner
  rather than a policy callback; old policy-private backend-status wrappers
  are retired**
- effect request/application boundary: **achieved for current requested effects**
- focused token, coverage, handoff, dispatch, report, reset, config services:
  **mostly achieved**
- coverage debug-field projection: **achieved for
  `CoverageReportService.debug_fields_from_state(...)`; coverage debug inputs
  now project from `CoverageRuntimeState` plus explicit coverage report config
  and coverage selection service facts instead of policy-side manual snapshot
  assembly**
- coverage trace/report projection: **achieved for the planner-trace coverage
  subset through `CoverageTraceReportStatus` and
  `CoverageReportService.trace_status_from_state(...)`**
- coverage rollout-summary projection: **achieved for the rollout-summary
  coverage subset through `CoverageSummaryReportStatus` and
  `CoverageReportService.summary_status_from_state(...)`**
- coverage decision-event bucket snapshot projection: **achieved through
  `CoverageReportService.bucket_snapshot(...)` over typed
  `PrimitiveObservationFacts`; the policy shell no longer owns the live
  mass/deposit/env-state bucket snapshot projection**
- coverage report/decision-event composition boundary: **achieved through
  `PrimitiveCoverageReportRuntime`; the policy shell no longer directly
  constructs coverage report config/state/service objects or keeps old private
  coverage report helper wrappers**
- coverage static config boundary: **achieved through
  `PrimitiveCoverageStaticConfig`; coverage report, selection/planning-fact,
  state-exemplar, update, and runtime config snapshots are constructed in the
  coverage lane, while policy runtime port methods keep only dynamic
  state/callback welds**
- effect-side observation metric fact-source boundary: **achieved for
  requested-effect dump-start deposited mass and failed-dig current bucket mass
  through typed `PrimitiveObservationFacts` providers; policy-built scalar
  metric callbacks are no longer exposed on those effect-side ports**
- raw observation helper facade cleanup: **achieved after the typed fact-source
  migrations; `PrimitivePlannerACTPolicy` no longer exposes private
  `_mass_in_bucket`, `_deposited_mass`, `_min_distance_to_dig_area`,
  `_bucket_depth_*`, `_bucket_dig_area_*`, `_dig_cell_id`, or `_env_state`
  helper facades**
- coverage planning fact-source boundary: **achieved for coverage selection
  facts, coverage raw-field projection, state-conditioned exemplar
  projection/writeback, exemplar distance/id projection, and remaining-depth
  facts through `CoveragePlanningFactService`; env-state and bucket-pose reads
  now use typed `PrimitiveObservationFacts`, while the existing
  `first_dig_qpos_delta` callback remains explicit because it still touches
  parked pre-dig-align target material; scoring/selection algorithms remain in
  the existing coverage services**
- coverage selection/fact composition boundary: **achieved through
  `PrimitiveCoverageSelectionRuntime`; the policy shell no longer directly
  constructs `CoverageSelectionRuntimePorts`, `CoverageSelectionConfig`,
  `CoveragePlanningFactConfig`, or `CoveragePlanningFactService`; old private
  coverage selection/fact policy helper wrappers have been retired after
  callers/tests moved to the focused runtime/service contracts**
- policy test-only / dead-candidate helper facade cleanup: **achieved for the
  current adapter/config helper, prior-loading, scripted-bootstrap
  target-reached, coverage-candidate-builder, and token conversion helper
  cluster; tests now call `primitive_adapter_config`,
  `PrimitiveScriptedBootstrapRuntimeService`,
  `PrimitiveDigTokenPlanningService`, `PrimitiveReturnTokenPlanningService`,
  `DigCutTokenPlanner`, `CoverageCandidateBuilder`, or focused runtime
  contracts directly instead of preserving old policy-private helper names**
- bootstrap end fact-source boundary: **achieved for non-scripted bootstrap
  end gates through `PrimitiveObservationFacts` and `BootstrapStatus`; scripted
  bootstrap still takes precedence through `PrimitiveScriptedBootstrapRuntimeService`,
  while first-qualified-dig-start, loaded-and-clear, disabled, and unsupported
  mode behavior are projected by the existing bootstrap status owner**
- token planning observation fact-source boundary: **achieved for active dig
  and return token planning through a typed `PrimitiveObservationFacts`
  provider; separate policy-built bucket pose, deposited-mass, env-state, qpos,
  and qvel callbacks are no longer exposed on the token planning ports**
- coverage selection runtime mutable state owner: **achieved for corridor
  list, candidate scores, active/last-selected ids, and all-depleted checks;
  selection runtime sequencing now consumes `CoverageRuntimeState` directly
  instead of policy-built getter/setter callbacks**
- coverage effect runtime mutable state owner: **achieved for coverage
  completion/rejection/reopen/terminal-stop mutable state; effect runtime
  sequencing now consumes `CoverageRuntimeState` directly instead of
  policy-built getter/setter callbacks**
- coverage effect fact-source boundary: **achieved for coverage
  complete-dig mass, complete-dump facts, rejection facts, reopen facts, and
  terminal-stop facts through `CoverageEffectFactService`; the policy no
  longer builds coverage effect fact dataclasses through callback ports, and
  the old private policy fact helper facades have been removed**
- coverage effect/update composition boundary: **achieved through
  `PrimitiveCoverageEffectRuntime`; the policy shell no longer directly
  constructs `CoverageUpdateConfig`, `CoverageUpdateService`,
  `CoverageRuntimeConfig`, `CoverageRuntimeService`, or
  `CoverageEffectRuntimePorts`, and old private coverage effect/update helper
  wrappers have been removed after callers/tests moved to the focused runtime
  contract**
- coverage effect owner-state setter boundary: **achieved through
  `CoverageRuntimeState`; old private policy setter/update wrappers for
  coverage payload, dump, low-productivity, pass, active-corridor,
  rejected-exemplar, and terminal-stop owner fields have been removed**
- dig progress tick-update boundary: **achieved for per-dig tick progress and
  current coverage payload gain updates through
  `PrimitiveDigProgressRuntimeService`; the policy shell no longer owns the
  live mass fact-source, cycle progress update, or coverage payload max update**
- token runtime mutable state owner: **achieved for dig/return token arrays,
  source/fallback flags, prior-bound flags, pending next-dig token state, and
  live `TokenStatus` plus token/pending/dig-cut report metadata projection;
  token runtime sequencing now consumes this owner directly, and consumes
  `CoverageRuntimeState` directly for pending next-dig state-exemplar handoff
  and clear timing, instead of policy-built getter/setter callbacks**
- active dig token planning mutable state-owner boundary: **achieved for
  pending dig route, dig-cut status, dig-depth-profile status, active corridor,
  selected corridor ids, payload/deposit baselines, and state-exemplar payload;
  active dig token planning now consumes `PrimitiveTokenRuntimeState` and
  `CoverageRuntimeState` directly instead of policy-built storage callbacks**
- return token planning mutable state-owner boundary: **achieved for
  return start-envelope source/prior flags, coverage active corridor id, and
  coverage corridor lookup; return token planning now consumes
  `PrimitiveTokenRuntimeState` and `CoverageRuntimeState` directly instead of
  policy-built storage callbacks**
- return runtime mutable state owner: **achieved for return handoff counters,
  entry-close cache, next-dig-event flag, start-envelope gate cache, and live
  return report/status projection**
- return direct-handoff effect state-owner boundary: **achieved for current
  skill reads and return-transition completion through focused
  execution/cycle owners, while lifecycle switching and readiness/token
  planning remain explicit ports**
- action-dispatch state-owner boundary: **achieved for active skill,
  first-dig cycle index, and completed-dump-count reads through focused
  execution/cycle/coverage owners, while low-level policy handles,
  observation assembly, scripted bootstrap action, and residual pre-dig-align
  action remain explicit ports**
- cycle/progress runtime mutable state owner: **achieved for live 4P
  dig-progress, dump-hold, transition-count, cycle-index, dump-deposit
  baseline state, and live cycle/progress report/finalization projection**
- scripted bootstrap runtime state/service owner: **achieved for
  scripted-qpos bootstrap counters, target-reached/timeout checks, and PD
  bootstrap action generation, plus live scripted-bootstrap report/status
  projection**
- execution lifecycle runtime state owner: **achieved for active skill, switch
  reason, previous action, and latest compact debug state**
- observation injection runtime state owner: **achieved for per-observation
  token injected compatibility flags and assembler-result application**
- cell-entry compatibility runtime state owner: **achieved for parked
  cell-entry goal/audit/token-cache/trace report storage and disabled public
  debug/summary/trace report projection after primitive-planner runtime removal**
- pre-dig-align compatibility runtime state owner: **achieved for parked
  pre-dig-align counters, cached target/error arrays, readiness booleans,
  timeout reason, surface-guard report storage, and public debug/summary report
  projection**
- failed-dig/restart recovery service boundary: **achieved through
  `PrimitiveDigRecoveryService`; old private policy restart wrappers are
  retired, token-plan clear/invalidate actions route through
  `PrimitiveTokenObservationRuntime`, and `pre_dig_align` remains explicitly
  parked/residual**
- runtime composition root / public runtime kernel: **achieved for public
  runtime routing**
- decision runtime backend factory/registry: **achieved for selecting any
  backend factory registered in `PrimitiveDecisionRuntimePorts`, with default
  policy registration still limited to `legacy_fsm` and unsupported names
  failing fast**
- backend-neutral fact access for non-FSM decision strategies: **partly
  achieved for common context/skill facts plus lazy bootstrap and
  dig/carry/dump/return decision facts through `PrimitiveBackendFactsAccess`,
  carried through the legacy FSM branch chain by
  `PrimitiveBackendDecisionInput`**
- external backend contract readiness: **achieved at generic runtime-contract
  level and exercised through explicit `behavior_tree_shadow` selection tests;
  no production plugin/config selection is implemented**
- behavior-tree decision backend implementation: **partly implemented as a
  non-default shadow backend with continue-current-skill fallback, a
  return-completed transition branch, BT payload mapping, and compact/rich trace
  export tests; production routing and full BT facts are not implemented**
- VLM, LLM, or learned decision backend implementation: **not implemented**

### Backend-Ready Production Import Contract

This section is the allowed production import surface for future external
decision backend work. It is intentionally narrower than the design documents.
Design guides such as `docs/planner_scheduling_backend_design.md` remain
review artifacts and must not be imported or treated as runtime APIs.

Allowed generic decision/backend contract imports:

- `testbed.planner.primitive.decision.context.PrimitiveDecisionContext`
- `testbed.planner.primitive.decision.contracts.PrimitiveDecisionResult`
- `testbed.planner.primitive.decision.contracts.RequestedPlannerEffect`
- concrete requested-effect records from
  `testbed.planner.primitive.decision.contracts`, such as
  `SwitchSkillEffect`, coverage effects, return effects, and dump/carry
  counter effects
- `testbed.planner.primitive.decision.runtime.PrimitiveDecisionRuntime`
- `testbed.planner.primitive.decision.runtime.PrimitiveDecisionRuntimeConfig`
- `testbed.planner.primitive.decision.runtime.PrimitiveDecisionRuntimePorts`
- `testbed.planner.primitive.decision.backends.legacy_fsm.PrimitiveDecisionBackend`
- `testbed.planner.primitive.decision.backends.legacy_fsm.PrimitiveCompatibilityDecisionBackend`
- `testbed.planner.primitive.decision.backends.legacy_fsm.PrimitiveDecisionBackendFactory`

Allowed facts/input contract imports:

- `testbed.planner.primitive.facts.decision.PrimitiveDecisionFacts`
- `testbed.planner.primitive.facts.backend.PrimitiveBackendFactsPorts`
- `testbed.planner.primitive.facts.backend.PrimitiveBackendFactsSource`
- `testbed.planner.primitive.facts.backend.PrimitiveBackendFactsAccess`
- typed transition fact views from `testbed.planner.primitive.facts.decision`
- `testbed.planner.primitive.decision.input.PrimitiveBackendDecisionInput`
- `testbed.planner.primitive.decision.input.PrimitiveBackendDecisionInputBuilder`

Allowed effect application contract imports:

- `testbed.planner.primitive.effects.requested.RequestedEffectApplier`
- `testbed.planner.primitive.effects.requested.RequestedEffectApplierPorts`
- `testbed.planner.primitive.effects.requested.PrimitiveRequestedEffectRuntime`
- `testbed.planner.primitive.effects.requested.PrimitiveRequestedEffectRuntimePorts`

Shell and lane dependency rules:

- Future backend code must not import
  `testbed.policies.hybrid.primitive_planner.PrimitivePlannerACTPolicy`.
- Future backend code must not depend on policy private methods, policy private
  attributes, broad planner-self objects, blackboards, callback bags, or design
  documents.
- `PrimitivePlannerACTPolicy` remains the default production registration weld
  for `legacy_fsm` until production plugin/config routing is explicitly
  requested.
- Older fake-backend contract proof remains test-local. It proves generic
  runtime/factory selection, not production plugin discovery or a real external
  backend implementation.
- The `behavior_tree_shadow` backend is concrete code, but it is non-default
  and explicit-only. It proves harness registration, a no-change fallback, the
  first return-completed transition branch, and BT-specific node trace output.
  The trace bundle feeds the generic online/offline eval trace contract, not an
  internal-only debug artifact.

Do not describe the current code as "fully swappable backend architecture." The
accurate claim is: the confirmed-live 4P legacy FSM path has been backendified,
and the shell now delegates most domain work to focused services.

Restored/parked-path policy: primitive-planner `cell_entry` remains parked
compatibility material, while `pre_dig_align` has been explicitly re-approved
and restored as an opt-in runtime capability. Enabled `pre_dig_align` config is
valid after the Slice 1-8 runtime restoration; enabled `cell_entry`
primitive-planner runtime config must still fail fast. Historical `cell_entry`
data/HDF5/training low-dimensional support remains a compatibility contract
outside primitive planner runtime. Do not promote either path into
behavior-tree nodes, VLM packets, plugin routing, or default mainline runtime
architecture as part of ordinary refactor momentum.
After the pre-dig-align restoration, `PrimitivePlannerACTPolicy` still does not
expose the old private false predicate facades
`_should_pre_dig_align_before_dig()` or
`_should_pre_dig_align_after_failed_dig()`. The restored entry decisions read
focused `PrimitivePreDigAlignRuntimeService` predicates through explicit reset,
failed-dig, and return-handoff ports; disabled config keeps the previous
false/zero public report compatibility.

## Layer 1: Public Adapter

Ideal boundary:

- `PrimitivePlannerACTPolicy` is the only public policy object used by eval and
  rollout.
- It preserves constructor/config compatibility and public methods:
  `reset()`, `predict(obs)`, `debug_state()`, `rollout_summary()`, and
  `planner_trace()`.
- It owns public API compatibility and low-level policy handles, but not
  planner domain algorithms.
- It constructs a runtime kernel or composition root, then delegates runtime
  calls.

Current boundary:

- `PrimitivePlannerACTPolicy.__init__` stores low-level policy handles and the
  boundary detector, then delegates constructor config normalization to
  `PrimitivePlannerAdapterConfigNormalizer`.
- `reset()`, `predict()`, `debug_state()`, `rollout_summary()`, and
  `planner_trace()` delegate to `PrimitivePlannerPublicRuntime`.
- The policy supplies focused runtimes/services and explicit shell writeback
  callbacks through a typed public-runtime weld, but it no longer builds
  `PrimitivePlannerRuntimeKernelPorts` or report builders directly.
- The policy supplies decision-runtime shell facts through
  `LegacyFSMDecisionBackendFactoryPorts`, registers
  `LegacyFSMDecisionBackendFactory.from_runtime_ports(...)` in
  `PrimitiveDecisionRuntimePorts.backend_factories`, and delegates backend
  selection to `PrimitiveDecisionRuntime`; it no longer constructs
  `PrimitiveFSMCapabilityProvider`, `PrimitiveDecisionCapabilities`, or
  `LegacyFSMBranchPorts` inline.
- The policy does not construct `PrimitiveFSMCapabilityProviderPorts` inline.
  Constructor-normalized static transition values flow through
  `PrimitiveFSMCapabilityProviderConfig` on `PrimitivePlannerAdapterConfigState`;
  live semantic-boundary, cycle, coverage, return, and return-handoff readiness
  inputs remain explicit typed ports into
  `LegacyFSMDecisionBackendFactoryPorts`.

Gap:

- The policy still owns many compatibility facades and port-builder methods.
  Future work should reduce those through backend-neutral facts and focused
  state owners, not by reintroducing runtime route logic into the adapter.

Standard:

- New public methods must not be added to `PrimitivePlannerACTPolicy` unless
  eval/rollout needs them.
- Existing public methods must keep their schema and behavior.
- New runtime service wiring should attach through the runtime kernel/port
  bundle instead of expanding policy-owned public runtime routes.

## Layer 2: Runtime Kernel / Composition Root

Ideal boundary:

```text
PrimitivePlannerACTPolicy
  -> PrimitivePlannerPublicRuntime
  -> PrimitivePlannerRuntimeKernel
      -> PrimitiveExecutionRuntime
      -> PrimitiveExecutionDriver
      -> PrimitiveDecisionRuntime
      -> RequestedEffectApplier
      -> PrimitiveActionDispatchService
      -> PrimitiveTickFinalizationRuntime / PrimitiveTickFinalizationService
      -> report builders
      -> token/coverage/return services
```

The public runtime owns composition of the kernel ports and builders. The
runtime kernel owns public runtime routing:

- `reset()`
- `predict(obs)`
- `debug_state()`
- `rollout_summary()`
- `planner_trace()`

The execution driver owns one-tick ordering. The runtime kernel owns the
composition of all services needed by those public calls.

Current boundary:

- `PrimitivePlannerPublicRuntime` owns construction of
  `PrimitivePlannerRuntimeKernelPorts` from focused reset, execution,
  finalization, and report runtimes plus explicit debug-state writeback.
- `PrimitivePlannerRuntimeKernel` owns the public runtime route:
  `reset()`, `predict(obs)`, `debug_state()`, `rollout_summary()`, and
  `planner_trace()`.
- `PrimitiveExecutionRuntime` owns construction of `PrimitiveExecutionPorts`
  from focused services and owners, then provides `PrimitiveExecutionDriver`
  to the kernel.
- `PrimitiveExecutionDriver` owns one-tick execution ordering under the runtime.
- `PrimitiveResetLifecycleService`, report builders, action dispatch, token
  runtime, and coverage services remain focused owners called through typed
  kernel/policy ports.

Gap:

- The kernel currently composes existing service routes through callables; it
  does not yet own a backend-neutral facts packet or domain state owners beyond
  what existing services expose.
- Policy-owned port wiring remains large, but public API routing is now
  centralized.

Standard:

- The kernel must not receive planner `self`.
- The kernel may receive explicit typed ports from the public adapter.
- The kernel must not implement planner algorithms; it routes public runtime
  calls to existing services.
- The first kernel slice should be composition-only and behavior-preserving.

## Layer 3: Execution Driver

Ideal boundary:

- Owns one tick of planner execution.
- Makes ordering explicit and testable.
- Does not choose decision strategy details.
- Does not contain token, coverage, handoff, or report algorithms.

Current boundary:

- `PrimitiveExecutionDriver` owns:
  boundary update -> switch reason reset -> current skill snapshot ->
  dig progress update if starting in `dig` -> decision runtime ->
  requested-effect validation/application -> return timeout accounting ->
  action dispatch -> previous-action recording -> transition-completed check ->
  debug finalization.
- Execution-driver ports call focused services and owner state directly for
  boundary events, switch-reason reset/current skill reads, action dispatch,
  previous-action copy, transition-completed checks, and debug-state writeback.
  The old policy-private execution hook wrappers are retired.

Gap:

- The driver is close to target for one-tick execution.
- It is now called through the runtime kernel, but its concrete execution ports
  are still assembled by the public adapter because broader port bundles and
  state owners are not fully separated yet.

Standard:

- Preserve effect timing: requested effects apply after decision and before
  return-timeout accounting/action dispatch.
- Do not add domain branches or algorithms to the driver.
- Compatibility `run_primitive_tick()` must stay a facade unless explicitly
  removed after an audit.

## Layer 4: Decision Runtime And Backend

Ideal boundary:

```python
class PrimitiveDecisionBackend(Protocol):
    name: str

    def decide_context(
        self,
        context: PrimitiveDecisionContext,
        capabilities: PrimitiveBackendFacts,
    ) -> PrimitiveDecisionResult:
        ...
```

Backends may choose, explain, and request effects. They must not apply effects,
call planner private methods, or write shell state.

Current boundary:

- `PrimitiveDecisionRuntime` selects any backend factory registered in
  `PrimitiveDecisionRuntimePorts.backend_factories` after normalizing the
  requested backend name. `PrimitivePlannerACTPolicy` still registers only the
  default `legacy_fsm` factory.
- `PrimitiveDecisionRuntimePorts` exposes a `backend_factories` registry from
  normalized backend name to a backend factory builder. The runtime selects a
  factory through that registry instead of depending on a
  `legacy_fsm_branch_set` callable.
- `LegacyFSMDecisionBackendFactory` owns `LegacyFSMBranchSet` construction and
  reuse for the default backend, plus requested and legacy-compatibility
  backend construction.
- Focused tests and policy callers that need a backend factory or backend
  instance use `PrimitiveDecisionRuntime.backend_factory_for(...)`,
  `requested_backend_for(...)`, or `compatibility_backend_for(...)` with an
  explicit backend name. Concrete legacy FSM adapter classes remain in
  `testbed/planner/primitive/decision/backends/legacy_fsm.py`, but the
  runtime-facing accessor surface is backend-neutral. The old policy-private
  backend access wrappers and old legacy-FSM-specific runtime accessors are
  retired and are not part of the current interface.
- Focused tests and execution callers that need requested/default decisions use
  `PrimitiveDecisionRuntime.decide_tick(...)`; callers that need legacy
  compatibility decision behavior use
  `PrimitiveDecisionRuntime.decide_legacy_compatibility_tick(...)`, or the
  focused backend contracts directly. The old policy-private
  `_decide_tick(...)`, `_decide_tick_with_legacy_fsm()`, and
  `_maybe_switch_skill()` facades are retired and are not part of the current
  interface.
- A future backend factory can plug into the generic runtime contract by
  implementing `PrimitiveDecisionBackendFactory`, registering a builder in
  `PrimitiveDecisionRuntimePorts.backend_factories`, and using
  `PrimitiveDecisionRuntimeConfig.backend_name` to select that registered name.
  The runtime contract does not require editing `PrimitivePlannerACTPolicy`
  main decision flow; the current policy shell still provides only the default
  legacy factory registration weld.
- `LegacyFSMBranchSet` owns requested order and legacy compatibility order.
- `PrimitiveRequestedBranchRunner` and
  `LegacyFSMCompatibilityDecisionBackend` each construct one
  `PrimitiveBackendDecisionInput` per `decide_context(...)` call and pass that
  same input identity through the ordered branch chain.
- Legacy FSM branches implement `decide_input(input)` and store only static
  config such as skill names; they no longer store facts source,
  compatibility actions, broad capabilities, or policy callbacks.
- Legacy FSM branches consume read-only facts through
  `PrimitiveBackendDecisionInput.backend_facts` and use
  `PrimitiveBackendDecisionInput.compatibility_actions` only where explicit
  shell compatibility actions are needed.
- The active bootstrap branch consumes a bootstrap-specific facts view,
  `PrimitiveBootstrapDecisionFacts`, through `PrimitiveBackendFactsAccess`.
- The active dig branch consumes a dig-specific facts view,
  `PrimitiveDigTransitionFacts`, through `PrimitiveBackendFactsAccess`, then
  explicitly syncs the legacy dig-to-carry reason mirror before effect
  selection.
- The active carry and dump branches consume carry/dump-specific facts views,
  `PrimitiveCarryTransitionFacts` and `PrimitiveDumpTransitionFacts`, through
  `PrimitiveBackendFactsAccess`.
- The active return branch consumes a return-specific facts view,
  `PrimitiveReturnTransitionFacts`, through `PrimitiveBackendFactsAccess` after
  the explicit return refresh step.
- Unsupported backend names fail fast.

Gap:

- `PrimitiveBackendFactsSource` is the backend-facing source of truth for
  common decision facts and lazy backend facts access. The older
  `PrimitiveDecisionFactsSource` name remains only as a compatibility alias
  and must not be treated as the main concept for new backend contracts.
- `PrimitiveDecisionCapabilities` is now a compatibility facade and
  construction helper, not the direct branch dependency.
- `PrimitiveDecisionFacts` currently covers common facts only: context identity,
  current skill name, current switch reason, and context convenience accessors.
- Return transition refresh is now explicit: the active legacy-FSM return branch
  refreshes shell-owned handoff cache state before reading return status, while
  `return_transition_status(...)` itself is read-only.
- Dig transition facts now have a typed read-only view, but the legacy
  dig-to-carry reason mirror sync is still an explicit compatibility step in
  the active dig branch.
- Bootstrap and dig/carry/dump/return transition facts now have typed read-only
  views exposed through one lazy `PrimitiveBackendFactsAccess`, but that access
  still covers only the legacy FSM requested-branch facts and is not yet a
  complete backend-neutral facts bundle.
- `PrimitiveBackendDecisionInput` is a per-tick legacy-FSM backend input
  packet, not a full alternate-backend packet. It carries context, backend
  facts access, and explicit compatibility actions through the branch chain,
  and provides an explicit post-compatibility-action common-facts reread for
  residual `pre_dig_align`.
- Return transition facts now have a typed read-only view, but that view is
  constructed lazily only after the active return branch has refreshed cached
  handoff state.
- The production backend registry currently contains only the `legacy_fsm`
  factory. It is a selection/construction boundary, not proof that complete
  behavior-tree, VLM, or learned backends can already consume the current facts
  packet.
- There is no full backend-neutral fact packet for behavior-tree or VLM
  strategies because transition, token, coverage, and return handoff facts are
  not yet in a neutral packet.
- `behavior_tree_shadow` is the only alternate backend implementation, and it
  is limited to an explicit no-change fallback plus trace skeleton.

Standard:

- Keep unsupported backends fail-fast until a backend has focused tests,
  explicit facts, and parity scope.
- New backends must return `PrimitiveDecisionResult` with ordered requested
  effects.
- New backends must not depend on policy private attributes, compatibility
  facades, or broad callback bags.
- `legacy_fsm` remains the only default production runtime backend.
  `behavior_tree_shadow` may be used by focused tests or explicit harnesses, but
  it is not a user-facing backend selector.
- Future generic decision trace service/export work must keep ownership split:
  each backend produces backend-specific payload details, while a
  consumer-neutral report/trace owner adapts generic decision trace records for
  online Unity eval and offline eval.

## Layer 5: Decision Context

Ideal boundary:

- Immutable per-tick packet passed to decision backends.
- Contains observation identity, boundary event, and tick preparation metadata.
- Does not include mutable shell state or service callbacks.

Current boundary:

- `PrimitiveDecisionContext` contains `obs`, `boundary_event`, and
  `PrimitiveTickPreparation`, with convenience accessors for skill before
  decision and dig-progress update status.
- `PrimitiveDecisionFacts` wraps the context without copying `obs`,
  `boundary_event`, or `preparation`, and adds current skill/reason facts.
- `PrimitiveBootstrapDecisionFacts` wraps an existing `PrimitiveDecisionFacts`
  plus a `BootstrapDecisionStatus` identity for active-bootstrap decisions.
- `PrimitiveDigTransitionFacts` wraps an existing `PrimitiveDecisionFacts` plus
  a `DigTransitionStatus` identity for active-dig decisions.
- `PrimitiveCarryTransitionFacts` wraps an existing `PrimitiveDecisionFacts`
  plus a `CarryTransitionStatus` identity for active-carry decisions.
- `PrimitiveDumpTransitionFacts` wraps an existing `PrimitiveDecisionFacts`
  plus a `DumpTransitionStatus` identity for active-dump decisions.
- `PrimitiveReturnTransitionFacts` wraps an existing `PrimitiveDecisionFacts`
  plus a `ReturnTransitionStatus` identity for active-return decisions.

Gap:

- Context is adequate for current FSM backend.
- The common facts packet is intentionally small; future backend-neutral facts
  still need a unified bundle/port shape plus token state, coverage, and return
  handoff state views.

Standard:

- Keep context read-only.
- Do not add mutation ports or service callables to context.
- New context fields must be facts needed by more than one backend style, not
  one branch's private convenience.

## Layer 6: Capability And Fact Boundary

Ideal boundary:

- Capability/fact layer is read-only.
- It exposes backend-neutral facts:
  observation facts, skill state, transition statuses, token state, coverage
  state view, return handoff state, and diagnostic-ready summaries.
- It should not be named or shaped only around one decision implementation.

Current boundary:

- `PrimitiveFSMCapabilityProvider` builds dig/carry/dump/return transition
  status records and reads live cycle, coverage, and return runtime values
  through the focused state owners.
- It also owns dig-exit overshoot projection for dig transition facts by
  combining `PrimitiveObservationFacts` bucket-tip/fallback dig-area pose with
  the active coverage corridor.
- `PrimitiveFSMCapabilityProvider.dig_transition_status(...)` only assembles
  read-only dig status. Dig-to-carry reason mirror writeback is explicit through
  `sync_dig_transition_reason(...)`.
- `PrimitiveFSMCapabilityProvider.refresh_return_transition_state(obs)` owns
  the explicit return handoff cache refresh step. That refresh now consumes
  `ReturnHandoffReadinessService` directly from provider ports, while
  `return_transition_status(...)` only reads cached return owner flags and
  observation facts.
- Legacy FSM branches and focused tests consume transition statuses through
  `PrimitiveFSMCapabilityProvider`, `PrimitiveDecisionCapabilities`, or
  `LegacyFSMBranchPorts`. The old policy-private
  `_dig/_carry/_dump/_return_transition_status_for_backend(...)` wrappers are
  retired and are not part of the current interface.
- `PrimitiveDecisionFacts` is the first backend-neutral common facts packet. It
  contains `PrimitiveDecisionContext`, current skill name, current switch
  reason, and read-only context accessors; it does not include transition status
  providers or mutation ports.
- `PrimitiveDigTransitionFacts` is a transition-specific decision facts view
  for active dig decisions. It contains an existing common facts packet and the
  read-only `DigTransitionStatus`; it does not contain provider, applier,
  callback, effect, sync, or mirror-setter fields.
- `PrimitiveCarryTransitionFacts` is a transition-specific decision facts view
  for active carry decisions. It contains an existing common facts packet and
  the read-only `CarryTransitionStatus`; it does not contain provider, applier,
  callback, effect, mutation, setter, refresh, or sync fields.
- `PrimitiveDumpTransitionFacts` is a transition-specific decision facts view
  for active dump decisions. It contains an existing common facts packet and the
  read-only `DumpTransitionStatus`; it does not contain provider, applier,
  callback, effect, mutation, setter, refresh, or sync fields.
- `PrimitiveReturnTransitionFacts` is a transition-specific decision facts view
  for active return decisions. It contains an existing common facts packet and
  the read-only
  `ReturnTransitionStatus`; it does not contain refresh, provider, applier,
  callback, or effect fields.
- `PrimitiveBootstrapDecisionFacts` is a bootstrap-specific decision facts view
  for active bootstrap decisions. It contains an existing common facts packet
  and the read-only `BootstrapDecisionStatus`; it does not contain residual
  handler, provider, callback, effect, mutation, refresh, or sync fields.
- `PrimitiveBackendFactsAccess` in
  `testbed/planner/primitive/facts/backend.py` is the backend-facing lazy
  read-only access object for bootstrap and dig/carry/dump/return transition
  facts. It holds a `PrimitiveDecisionContext`, one common
  `PrimitiveDecisionFacts` identity, a private read-only
  `PrimitiveBootstrapDecisionReader`, and a private read-only
  `PrimitiveTransitionStatusReader`; its public API is limited to
  `bootstrap_decision()`, `dig_transition()`, `carry_transition()`,
  `dump_transition()`, and `return_transition()`.
- `PrimitiveBackendFactsSource` owns read-only common facts and backend facts
  access construction from `PrimitiveBackendFactsPorts`.
- `PrimitiveDecisionCompatibilityActions` owns explicit compatibility actions:
  dig reason sync, return refresh, and residual `pre_dig_align` handling.
- `PrimitiveBackendDecisionInput` in
  `testbed/planner/primitive/decision/input.py` is the per-tick legacy-FSM
  backend input passed through requested and legacy compatibility branch
  orders. It holds the `PrimitiveDecisionContext`, one
  `PrimitiveBackendFactsAccess`, explicit compatibility actions, and the
  private facts source needed only for explicit common-facts rereads after an
  already-applied compatibility action.
- `PrimitiveDecisionBackendFactory` is the runtime-facing backend factory
  contract. It returns generic requested and compatibility backend protocols
  rather than legacy-specific compatibility types. `LegacyFSMDecisionBackendFactory`
  is the only concrete factory and owns legacy branch-set construction/reuse
  plus requested and compatibility backend construction.
- Generic backend contract surfaces are:
  `PrimitiveDecisionBackend`, `PrimitiveCompatibilityDecisionBackend`,
  `PrimitiveDecisionBackendFactory`, `PrimitiveDecisionRuntimePorts`,
  `PrimitiveDecisionRuntimeConfig`, and `PrimitiveDecisionRuntime`.
- Default concrete adapter surfaces are:
  `LegacyFSMDecisionBackendFactoryPorts`, `LegacyFSMDecisionBackendFactory`,
  `LegacyFSMBranchPorts`, `LegacyFSMBranchSet`, and the concrete `LegacyFSM*`
  branch/backend classes in
  `testbed/planner/primitive/decision/backends/legacy_fsm.py`.
- Compatibility-only/test-only removed surfaces include old private policy
  backend/composition wrappers and `PrimitiveDecisionRuntimeComposition*`; they
  should stay absent unless a public compatibility owner is explicitly added.
- `LegacyFSMDecisionBackendFactoryPorts` in
  `testbed/planner/primitive/decision/backends/legacy_fsm.py` owns default
  legacy-FSM factory composition from explicit typed runtime inputs. It builds
  `PrimitiveFSMCapabilityProviderPorts` from focused static
  `PrimitiveFSMCapabilityProviderConfig` plus explicit live state/service
  inputs, then builds the focused capability provider, decision capabilities,
  and legacy FSM branch ports inside the concrete legacy adapter boundary.
  `PrimitiveDecisionRuntime` no longer imports or owns that legacy
  composition; it selects and invokes backend factories through the generic
  registry only.
- `PrimitiveDecisionCapabilities` remains as a compatibility facade over
  facts source plus compatibility actions for older tests and diagnostics.
- `PrimitivePlannerACTPolicy` no longer exposes the old private
  capability/composition wrappers `_decision_runtime_ports()`,
  `_legacy_fsm_backend_factory()`, `_legacy_fsm_branch_ports()`,
  `_primitive_decision_capabilities*()`, or
  `_primitive_fsm_capability_provider*()`. The policy shell keeps only a typed
  decision-runtime composition weld and does not retain old wrappers because
  tests mentioned them.
- `PrimitiveObservationFacts` and transition status dataclasses exist.
  Observation facts own target geometry projection plus bucket dig-area and
  bucket-tip dig-area pose projection for transition facts.

Gap:

- Legacy FSM branches now receive one backend decision input packet per tick,
  but the packet is still tailored to the legacy FSM branch chain and its
  explicit compatibility actions.
- The runtime factory/registry boundary is present, but only the legacy FSM
  factory is registered by the production shell. The non-FSM
  `behavior_tree_shadow` factory exists for explicit harness registration, but
  does not yet include a richer backend-neutral facts packet for alternate
  strategies.
- Residual `pre_dig_align` is still a capability-side already-applied handler.
- `PrimitiveDecisionFacts` is not yet the complete `PrimitiveBackendFacts`
  target. It lacks token, coverage, and return handoff views, and the
  transition facts are still separate lazy views rather than a single
  backend-neutral facts bundle.
- Dig/carry/dump/return transition facts are lazy and active-branch scoped.
  Return refresh still happens only inside the active return branch before
  assembling the facts view.

Standard:

- New decision facts must be explicit dataclasses or typed views.
- Do not add one-method-per-private-method callback bags.
- Do not expose policy `self` or mutable field references.
- Do not promote `pre_dig_align` or `cell_entry` into mainline capability
  contracts without explicit cleanup/retention approval.

## Layer 7: Decision Result And Effects

Ideal boundary:

- Backend output is a typed `PrimitiveDecisionResult`.
- Effects are ordered, validated requests.
- Only the execution kernel or shell-side applier mutates runtime state.

Current boundary:

- `PrimitiveDecisionResult` and requested effect classes exist.
- `validate_decision_effect_contract()` rejects mixed legacy/requested shapes
  and forbidden payloads.
- `RequestedEffectApplier` owns effect-class dispatch, writes simple cycle and
  return state effects through focused runtime owners, and keeps external
  action/algorithm effects as explicit typed ports.
- `PrimitiveRequestedEffectRuntime` owns construction of
  `RequestedEffectApplierPorts` from explicit typed inputs and is the object
  passed to `PrimitiveExecutionRuntimePorts.requested_effect_applier`.
  `PrimitivePlannerACTPolicy` keeps only a typed runtime weld and no longer
  exposes `_requested_effect_applier()` or `_requested_effect_applier_ports()`.
- Old private policy transition wrappers for dump hold/deposit writes, return
  next-dig marking, return transition completion, return next-skill selection,
  and dig replan counters have been retired; tests and production callbacks use
  `PrimitiveCycleRuntimeState`, `PrimitiveReturnRuntimeState`, and
  `RequestedEffectApplier` contracts directly.

Gap:

- Some parked residual behavior still uses already-applied compatibility result
  shape.
- Effect families are current-FSM oriented; future backend effects should reuse
  these where possible instead of adding backend-specific mutation calls.

Standard:

- Effects must be dataclasses with stable names and explicit fields.
- Effects must not carry callables, `self`, planner objects, or method-call
  payloads.
- Effect order is part of the contract.
- Generic decision trace records should capture backend name, decision source,
  active skill, skill before/after, status, selected-intent or path summary,
  reasons, requested effects, optional confidence/score fields, diagnostic
  checks, and compact/rich export modes.
- Backend-specific trace details belong in nested payloads. BT node statuses
  and selected tree paths belong in a BT payload; VLM prompt ids, visual
  evidence ids, model answer summaries, confidence, refusal/fallback reasons,
  and grounding artifacts belong in a VLM payload.
- Trace export is a separate consumer-neutral boundary. Online Unity eval and
  offline eval must be able to consume the same generic trace semantics, but
  backend code must not own Unity eval I/O, offline replay file formats,
  rollout writer internals, or eval orchestration.
- Adding an effect requires focused tests, validation tests, and parity tests for
  any public observable surface it touches.

## Layer 8: Shell-Owned State And Mutation

Ideal boundary:

- Mutable planner runtime state lives in focused state owners.
- Effect appliers mutate state owners through typed ports.
- The public adapter stores only public compatibility handles and state owners.
- Next-phase target: `PrimitivePlannerACTPolicy` converges to the external
  communication/API adapter surface only; internal runtime/state/decision/
  effect/report/input assembly moves behind stable owner/runtime/service
  boundaries.

Current boundary:

- `CoverageRuntimeState` owns coverage mutable state. Tests and diagnostics use
  `_coverage_runtime_state()` directly; the policy no longer keeps old private
  coverage property facades.
- `PrimitiveTokenRuntimeState` owns mutable token and pending next-dig token
  runtime state. The policy no longer keeps old private token/pending property
  facades or duplicate reset snapshot writeback entries for those fields.
- `PrimitiveReturnRuntimeState` owns mutable return handoff/runtime cache state:
  return step count, entry-close result, next-dig-event flag, and return
  start-envelope gate result/checks. It also owns live return report/status
  projection from explicit start-envelope config facts. The policy no longer
  keeps old private return-runtime property facades or duplicate reset snapshot
  writeback entries for those fields.
- `PrimitiveCycleRuntimeState` owns confirmed-live 4P cycle/progress state:
  dig progress counters, dump hold counters, transition counters, cycle index,
  and dump-start deposited-mass baseline. It also owns live cycle/progress
  report/finalization projection through `PrimitiveCycleReportStatus`. The
  policy no longer keeps old private cycle/progress property facades or
  duplicate reset snapshot writeback entries for those fields.
- `PrimitiveScriptedBootstrapRuntimeState` owns scripted bootstrap counters:
  step count, target-reached hold count, and timeout count. It also owns live
  scripted-bootstrap report/status projection through
  `PrimitiveScriptedBootstrapReportStatus`. The policy no longer keeps old
  private scripted-bootstrap counter property facades or duplicate reset
  snapshot writeback entries for those counters.
- `PrimitiveScriptedBootstrapRuntimeService` owns scripted-qpos bootstrap
  runtime rules: enabled detection, target-reached hold gating, timeout
  completion, and PD action generation.
- `CoverageReportService` owns coverage corridor debug projection, decision
  event payloads, coverage debug-field assembly, and planner-trace/rollout-
  summary coverage sub-projections. Coverage report snapshots now start from
  `CoverageRuntimeState` plus explicit `CoverageReportConfig` and
  `CoverageSelectionService` facts instead of policy-built coverage dictionaries.
- `PrimitiveExecutionRuntimeState` owns execution lifecycle metadata: active
  skill, switch reason, previous action, and latest compact debug state. The
  policy keeps `_skill_name`, `_switch_reason`, `_prev_action`, and
  `_debug_state` as property-backed compatibility facades over that owner.
- `PrimitiveObservationInjectionRuntimeState` owns per-observation token
  injected compatibility flags. The policy now reads this owner directly for
  debug/summary/trace projection and no longer keeps old private injected-flag
  property facades or reset snapshot writeback entries.
- `PrimitiveCellEntryCompatibilityRuntimeState` owns parked cell-entry
  compatibility/report storage: goal, goal cycle id, audit, cached token array,
  seen cell id, trace list, and disabled public debug/summary/trace report
  projection through `PrimitiveCellEntryReportStatus` from explicit
  `PrimitiveCellEntryReportConfig` facts. After the primitive-planner
  `cell_entry` runtime cleanup, the policy no longer keeps the old
  `_cell_entry_*` runtime field facades or reset snapshot writeback; report
  helpers project fresh disabled/default values instead of reading mutable
  policy cell-entry state.
- `PrimitivePreDigAlignRuntimeState` and
  `PrimitivePreDigAlignRuntimeService` own the restored opt-in pre-dig-align
  runtime counters, target/error state, readiness, timeout, surface guard,
  action, and entry predicates. Public pre-dig debug and rollout-summary fields
  are projected from live runtime state through
  `PrimitivePreDigAlignReportStatus` and explicit
  `PrimitivePreDigAlignReportConfig` facts, while
  `PrimitivePreDigAlignCompatibilityRuntimeState` remains a schema-compatible
  projection helper for disabled/default compatibility. The policy no longer
  keeps old `_pre_dig_align_*` runtime field facades or reset snapshot
  writeback; it only welds focused runtime/config/state services together.
- Skill lifecycle, reset lifecycle, and token runtime services own sequencing,
  but only write through remaining policy compatibility facades for live or
  retained private names.

Gap:

- Runtime state is only partially extracted.
- The policy shell still owns some compatibility/report algorithms and
  compatibility facades, but no longer stores pre-dig-align or cell-entry
  mutable report state, pre-dig-align/cell-entry debug projection,
  pre-dig-align/cell-entry summary projection, cell-entry planner-trace
  projection, or raw observation metric/env-state helper projection as
  independent policy responsibilities.

Standard:

- New mutable state should move into focused state owners when it is more than a
  compatibility mirror.
- Do not create a generic blackboard.
- State owners must be domain-specific, for example coverage runtime state or
  token runtime state.

## Layer 9: Action Dispatch And Low-Level Policies

Ideal boundary:

- Execution layer delegates low-level ACT policy selection and action shaping to
  an action dispatch service.
- Backend decisions do not call low-level policies.

Current boundary:

- `PrimitiveActionDispatchService` owns scripted bootstrap short-circuit,
  residual pre-dig action short-circuit, first-dig policy selection,
  active-policy lookup, all-policy order, `policy_obs` call, and action shape.
- It reads active skill from `PrimitiveExecutionRuntimeState`, first-dig cycle
  index from `PrimitiveCycleRuntimeState`, and completed dump count from
  `CoverageRuntimeState` instead of receiving policy-built state callbacks.
- The scripted bootstrap short-circuit calls the policy's compatibility facade,
  but the underlying runtime rules and state now live in
  `PrimitiveScriptedBootstrapRuntimeService` and
  `PrimitiveScriptedBootstrapRuntimeState`.

Gap:

- This layer is close to target.
- It is reached through the runtime kernel and execution driver, but still
  receives low-level policy handles, observation assembly, scripted bootstrap
  action, and residual pre-dig-align action through policy-built dispatch ports.
- Reset lifecycle, skill lifecycle, recovery, execution ports, and focused
  tests use `PrimitiveActionDispatchService` or typed dispatch ports directly;
  the old policy-private action-dispatch helper names are retired.

Standard:

- Preserve action dtype and shape contract.
- Preserve first-dig selection semantics.
- Do not let decision backends call low-level policy `predict()`.

## Layer 10: Observation And Token Runtime

Ideal boundary:

- Observation assembler owns token injection order and copy semantics.
- Token runtime coordinator owns runtime gating and cached/pending token state
  sequencing.
- Token planning services own orchestration.
- Token algorithm classes own low-level token math and contracts.

Current boundary:

- `PrimitivePolicyObservationAssembler` owns injection order, keys, and injected
  flag projection.
- `PrimitiveObservationInjectionRuntimeState` owns reset-default,
  per-observation clear, assembler-result application, and compatibility
  projection for the injected flags reported through debug/summary/trace paths.
- `PrimitiveTokenObservationRuntime` owns the composition boundary between
  policy observation assembly and token runtime sequencing: it builds
  `PrimitivePolicyObservationAssemblerPorts`, builds `PrimitiveTokenRuntimePorts`,
  clears/applies observation-injection state, and delegates dig/return token
  sequencing to `PrimitiveTokenRuntimeCoordinator`. The policy shell keeps
  typed token-observation runtime ports/runtime factory only; old private
  token-observation and token-runtime wrapper names have been retired after
  callers/tests moved to the focused runtime contract.
- `PrimitiveTokenRuntimeState` owns mutable dig/return token arrays, token
  source/fallback/prior-bound fields, return start-envelope prior flags, and
  pending next-dig token/raw/exemplar fields. It also owns live `TokenStatus`
  projection from explicit cell-entry enablement, observation-injection flags,
  and dig-depth-profile config facts, plus token/pending/dig-cut report
  metadata projection through `PrimitiveTokenReportStatus`. Old private
  token/pending policy property facades and duplicate reset writeback entries
  have been removed.
- `PrimitiveReturnRuntimeState` owns non-token return handoff/runtime cache
  fields, so return-target token state and return handoff cache state are no
  longer mixed in the policy shell. Return token and pending next-dig token
  private compatibility properties remain outside this return-runtime owner
  cleanup.
- `ReturnHandoffReadinessService` owns return-to-dig entry-target precedence,
  entry-error calculation, entry-close cache writeback, return start-envelope
  gate input/result writeback, `handoff_ready`, and direct-handoff mass/config
  gating over focused execution/cycle/return/token/coverage state owners.
  `PrimitiveReturnHandoffRuntime` now owns composition of that readiness
  service, the start-envelope gate service, and direct-handoff effect service
  from typed state ports, adapter-normalized `ReturnHandoffReadinessConfig`,
  and explicit return-target/prior algorithm ports. The old private policy
  return handoff readiness wrappers are retired; `PrimitivePlannerACTPolicy`
  retains only a return-handoff runtime weld.
- `ReturnDirectHandoffEffectService` owns the effect-side return/direct-handoff
  sequence. `SetReturnOrDirectHandoffEffect` application now delegates through
  `PrimitiveReturnHandoffRuntime.apply_direct_handoff(...)`; the old private
  policy action wrappers for setting return, trying direct handoff, service
  construction, direct-handoff ports, and readiness ports/service construction
  are retired.
- `PrimitiveTokenRuntimeCoordinator` owns dig/return token runtime sequencing.
  Its ports now carry the focused `PrimitiveTokenRuntimeState` owner directly
  for token storage reads/writes and `CoverageRuntimeState` directly for
  pending next-dig state-exemplar handoff reads and clear timing; external
  config, token-builder algorithms, return-relocate planning, and token
  planning services remain explicit ports.
- `PrimitiveTokenPlanningRuntime` owns service and port composition for
  `PrimitiveDigTokenPlanningService` and `PrimitiveReturnTokenPlanningService`.
  The policy shell supplies typed token-planning runtime ports/runtime factory
  only; old private token-planning helper names have been retired after
  callers/tests moved to the focused runtime/service contracts.
- `PrimitiveDigTokenPlanningService` and
  `PrimitiveReturnTokenPlanningService` own orchestration.
- `CoveragePlanningFactService` owns coverage selection facts, coverage
  raw-field fallback/clamp projection, optional state-conditioned exemplar
  override/writeback, exemplar distance/id projection, removed-depth grid and
  weighted exemplar helper delegation, and remaining-depth facts from explicit
  coverage config/state/exemplar/observation inputs.
- `PrimitiveCoverageSelectionRuntime` owns coverage selection/fact composition:
  selection runtime ports, coverage selection config/service construction, and
  coverage planning fact config/service construction. The policy shell supplies
  typed coverage-selection runtime ports and runtime factory as owner welds;
  legacy private helper names for selection/fact access are retired. The later
  scoring/exemplar helper cleanup also retired old private policy helper names
  for candidate construction, scoring/first-dig facts, state-exemplar
  projection, and coverage state-owner writeback; callers use
  `PrimitiveCoverageSelectionRuntime`, focused coverage services/builders, or
  `CoverageRuntimeState` directly.
- `PrimitiveDigTokenPlanningService` ports carry `PrimitiveTokenRuntimeState`
  and `CoverageRuntimeState` directly for active dig token planning storage
  reads/writes; external config, token planners, observation facts, and
  coverage raw-field projection remain explicit ports backed by the coverage
  planning fact service.
- `PrimitiveReturnTokenPlanningService` ports carry
  `PrimitiveTokenRuntimeState` and `CoverageRuntimeState` directly for return
  start-envelope source/prior flags, active corridor id, and corridor lookup;
  external config, token planners, observation facts, coverage selection, and
  coverage raw-field projection remain explicit ports backed by the coverage
  planning fact service.
- Token algorithm classes remain in `primitive/token/tokens.py`.
- `PrimitiveTokenRuntimeState` owns the old dig/return/pending token storage
  that used to be exposed through private policy property facades. The policy
  no longer exposes those old private property names. Its token-status and
  token-report status helpers remain typed report welds that supply explicit
  external facts to the report runtime.

Gap:

- `cell_entry` primitive-planner runtime token generation, planner/auditor
  execution, and trace mutation have been removed. Historical cell-entry data,
  HDF5, and ACT low-dimensional compatibility remain outside the primitive
  planner runtime, while public planner report fields project disabled/default
  values through `PrimitiveCellEntryCompatibilityRuntimeState` without
  policy-owned private runtime facades.
- Return handoff algorithms remain in return handoff services; only mutable
  return handoff/runtime cache storage moved into `PrimitiveReturnRuntimeState`.
- Coverage planning facts are no longer policy-owned implementation, but they
  are still legacy-FSM/default-path facts rather than a complete alternate
  backend-neutral fact packet.

Standard:

- Token dimensions, key names, source strings, fallback strings, and contract
  versions must remain centrally defined and tested.
- Do not add token schema inside decision backends.
- Future token-state extraction should use a focused token state owner, not a
  generic planner state bag.

## Layer 11: Coverage Runtime

Ideal boundary:

- Coverage state, candidate construction, selection, effect sequencing,
  reporting projection, and state-exemplar planning have separate owners.

Current boundary:

- `CoverageRuntimeState` owns mutable coverage state.
- Coverage selection/effect runtime coordinators own runtime sequencing.
- `PrimitiveCoverageEffectRuntime` owns coverage effect/update composition:
  update/runtime config construction, update/runtime service construction, and
  effect runtime port/coordinator construction. The policy shell supplies
  typed coverage-effect runtime ports and keeps only the focused effect runtime
  factory as the private owner weld.
- Mutable coverage owner-field writes use `CoverageRuntimeState` methods
  directly; old private policy setter wrappers for coverage effect owner state
  have been retired.
- Candidate construction, scoring, and state-exemplar planning have focused
  owners. Old private policy helper wrappers for this cluster have been retired
  after focused tests and production callbacks moved to those owners.

Gap:

- Coverage is one of the closest domains to target.
- Remaining coupling is mostly policy facade/report wiring.

Standard:

- Do not move coverage scoring into decision backends.
- Decision backends may read coverage facts/status and request coverage effects.
- Coverage terminal-stop reason strings and trace payload schemas are public
  observable contracts.

## Layer 12: Reporting

Ideal boundary:

- Public debug, summary, and trace outputs are assembled by report builders.
- Decision backends do not own public report schema.

Current boundary:

- `PrimitiveDebugReportBuilder`, `PrimitiveRolloutSummaryBuilder`, and
  `PrimitivePlannerTraceBuilder` exist.
- `PrimitiveReportCompositionRuntime` owns construction of
  `PrimitiveReportRuntimePorts` plus token, `cell_entry`, and `pre_dig_align`
  report-status projection from focused owners/runtimes.
  `PrimitiveReportRuntime` then owns construction of
  `PrimitiveDebugReportInputs`, `PrimitiveRolloutSummaryInputs`, and
  `PrimitivePlannerTraceInputs` from those typed report ports. The policy keeps
  public report methods and a typed report-composition weld; old private
  report-runtime and report/status composition helper wrappers were retired
  after runtime-kernel callbacks and focused tests moved to focused report
  contracts.
- `CoverageReportService` owns coverage corridor debug payloads, coverage
  decision-event payloads, coverage debug-field schema projection through
  explicit `CoverageDebugReportInputs`, planner-trace coverage sub-projection
  through `CoverageTraceReportStatus`, and rollout-summary coverage sub-
  projection through `CoverageSummaryReportStatus`. For live report inputs, the
  service projects those coverage outputs through
  `PrimitiveCoverageReportRuntime` from `CoverageRuntimeState`,
  `CoverageReportConfig`, and `CoverageSelectionService` rather than from
  policy-owned private report helper methods.
- `PrimitiveTokenRuntimeState` owns token/pending/dig-cut report metadata
  projection through `PrimitiveTokenReportStatus`; debug pending/dig-cut fields,
  rollout-summary pending/dig-cut fields, and planner-trace dig-cut metadata
  reuse that status object.
- `PrimitivePreDigAlignCompatibilityRuntimeState` owns parked pre-dig-align
  debug and rollout-summary report projection through
  `PrimitivePreDigAlignReportStatus`; this is report parking only and does not
  make `pre_dig_align` a mainline backend/runtime capability.
- `PrimitiveCellEntryCompatibilityRuntimeState` owns parked cell-entry debug,
  rollout-summary, and planner-trace report projection through
  `PrimitiveCellEntryReportStatus`; this is report parking only and does not
  make `cell_entry` a mainline token/backend/runtime capability.
- Policy no longer directly constructs the public report input dataclasses.

Gap:

- This layer is closer to target.
- Section snapshot providers may be further narrowed later. Coverage debug,
  trace, and summary coverage snapshot projection are outside the large policy
  class. Parked pre-dig-align debug/summary projection and parked cell-entry
  debug/summary/trace projection are owned by their compatibility state owners.
  Report input assembly is now a focused runtime boundary, while section status
  providers and helper facades remain available for compatibility tests.

Standard:

- Public report keys, types, NaN behavior, and list-copy semantics are observable
  contracts.
- Any schema change requires explicit user approval and parity updates.

## Layer 13: Config, Reset, And Skill Lifecycle

Ideal boundary:

- Public constructor normalization lives outside the policy shell.
- Reset lifecycle has one service-owned sequence.
- Skill switch lifecycle has one service-owned sequence.

Current boundary:

- `PrimitivePlannerAdapterConfigNormalizer` owns constructor config
  normalization.
- `PrimitiveResetLifecycleService` owns reset sequencing.
- `PrimitiveSkillLifecycleService` owns `_set_skill()` lifecycle sequencing
  and uses the focused execution, cycle, return, pre-dig-align compatibility,
  and coverage runtime state owners directly instead of policy-built storage
  setter callbacks. Its dig-token clear hook routes through
  `PrimitiveTokenObservationRuntime` and no longer depends on an old private
  policy clear wrapper.

Gap:

- `primitive/config/adapter.py` is already over the large-file threshold. It is
  allowed as the result of this extraction, but new config behavior should not
  continue accumulating there without a split.

Standard:

- Public constructor signature and defaults must remain compatible.
- New config semantics must have one source of truth.
- Config normalizer may build legacy field updates, but that dict must not
  spread into decision backends or runtime state owners.

## Parking And Removed Runtime Policy

Current parking:

- `pre_dig_align`: restored opt-in runtime capability after explicit user
  re-approval and Slice 1-8 unit-level closure. Enabled config is valid and
  feeds the focused runtime, action dispatch, legacy-FSM active branch,
  failed-dig recovery, return handoff, reset lifecycle, and live report
  projection. Unity smoke validation on 2026-06-25 confirmed enabled routing
  reaches live `pre_dig_align` counters and default-disabled routing remains
  `pre_dig_align_enabled=0`; it did not establish target-cycle behavioral
  success. The capability is not a default mainline requirement and is not a
  behavior-tree/VLM/LLM/plugin backend contract.
- `cell_entry`: compatibility/report material. It is not target token contract
  for the selected mainline rollout. Primitive-planner private `_cell_entry_*`
  runtime facades and reset snapshot writeback have been removed; public report
  keys remain disabled/default.
- `5P`: removed runtime. Historical behavior is preserved only by git history;
  runtime eval may keep a fail-fast diagnostic.
- behavior-tree production routing and full BT decision semantics: still parked
  scope. The current `behavior_tree_shadow` code is only a non-default fallback
  and trace skeleton.
- VLM and LLM backends: unsupported parked scope.

Standard:

- Do not migrate parked paths into target architecture just because code exists.
- A parked path can only be promoted after explicit evidence and user approval.
- Removed runtime paths must not be restored without explicit user direction.

## Next Implementation Order

The next code work should follow this order:

1. Introduce a per-tick backend decision input packet for legacy FSM branches.
   - **Done in Phase 9.42** for the confirmed-live legacy FSM requested and
     compatibility branch chains.
   - Keep `PrimitiveBackendFactsAccess` lazy and branch-local; do not eagerly
     compute transition statuses in later cleanup.

2. Extract a backend factory/registry boundary for `PrimitiveDecisionRuntime`.
   - **Done in Phase 9.43** for the default `legacy_fsm` factory/registry
     boundary.
   - Keep unsupported backend names fail-fast until a concrete backend has its
     own facts contract and tests.

3. Move remaining mutable runtime state into focused state owners.
   - Token runtime mutable state is **done in Phase 9.44**.
   - Return handoff/runtime mutable state is **done in Phase 9.45**.
   - Mainline cycle/progress mutable state is **done in Phase 9.46**.
   - Scripted bootstrap runtime mutable state and action/readiness rules are
     **done in Phase 9.47**.
   - Execution lifecycle metadata is **done in Phase 9.48** for active skill,
     switch reason, previous action, and latest compact debug state.
   - Observation injected-flag mutable state is **done in Phase 9.49**.
   - Parked cell-entry compatibility/report mutable state is
     **done in Phase 9.50**; its public debug/summary/trace report projection
     is **done in Phase 9.80** as compatibility parking, not backend
     promotion.
   - Parked pre-dig-align compatibility/report mutable state is
     **done in Phase 9.51**; its public debug/summary report projection is
     **done in Phase 9.79** as compatibility parking, not backend promotion.
   - Inspect the remaining policy-owned mutable fields before choosing another
     state-owner slice; avoid extracting a generic blackboard.
   - Avoid generic blackboards.

4. Audit parked paths.
   - Decide whether to remove, keep diagnostic-only, or convert
     `pre_dig_align` and `cell_entry`.
   - Do not do this before the runtime kernel boundary is clear.

5. Continue the new-backend prototype only behind explicit selection.
   - The initial non-default `behavior_tree_shadow` backend is present for
     continue-current-skill fallback, node trace payloads, and the first
     return-completed transition branch.
   - The generic trace record/schema and compact/rich adapter boundary now live
     under the report owner for online Unity eval and offline eval consumers,
     but consumer I/O is still not wired.
   - Next backend slices must add focused BT branch facts or effects with their
     own tests before any production route selection.
   - The backend must consume decision facts and return requested effects.

## Verification Standard

Every code slice touching these interfaces must run:

- focused tests for the new or changed module
- affected execution/decision/effect tests
- affected token/coverage/report tests when relevant
- current-code golden-window parity tests
- planner evidence trace tests
- `python -m compileall` for touched Python modules
- `python scripts/planner_refactor_guard.py --check-plan-contract`
- `python scripts/planner_refactor_guard.py --check-skill-contract`
- `git diff --check`

Documentation-only changes may skip pytest, but must run `git diff --check` and
the planner guard scripts if plan contracts are touched.

## Documentation Handoff Workflow

Implementation phases after this document should separate code execution from
architecture-record ownership:

1. The implementation thread performs the bounded code slice, focused tests,
   parity checks, guard checks, and local commit when requested.
2. The implementation thread reports only factual implementation evidence: the
   exact target lock, TDD red result, changed files, core factual change,
   verification commands, behavior-impact statement, documentation status, git
   status after, HEAD after, and factual residual risks. It should not
   recommend next slices, judge the target gap, or direct the audit strategy.
3. When an executor thread is delegated from a refactor/audit thread, the
   executor prompt must require a Codex `send_message_to_thread` callback to the
   source/refactor thread before the executor's final local reply. The callback
   must carry the same fact-only result fields and must repeat this recursive
   callback rule for any follow-up executor prompt generated by the refactor
   thread.
4. Refactor/audit threads must run with explicit `thinking: xhigh`. Executor
   delegation prompts must explicitly specify `thinking: high` or
   `thinking: xhigh` in the prompt text, and should use the same tool-level
   thinking value when the thread tool exposes it. This instruction is part of
   the recursive callback rule so future prompts do not drift to an unspecified
   or weaker reasoning mode.
5. The refactor-thinking/audit thread audits the code result and updates
   architecture documents, interface standards, and execution records as part of
   that audit. Target-gap analysis, next-slice candidates, every-third-iteration
   reflection, and dispatch decisions belong to the audit thread.
6. The every-third-iteration reflection gate must be explicit in both prompt
   surfaces. The refactor/audit prompt records the accepted-slice count and
   whether the next callback triggers the gate. The executor prompt asks only
   for fact-only evidence needed by that gate and must not ask the executor to
   write the deep reflection or choose the next slice. The fourth bounded
   implementation dispatch is blocked until the audit thread records the
   reflection or stops for user confirmation.
7. Each future refactor/audit and executor prompt must copy the mandatory skill
   compliance block explicitly: target lock first; planner yields after one
   dispatch; executor green is not closure; planner-side closure gate is
   required; lightweight reflection follows every callback; deep reflection
   follows every three accepted implementation callbacks or any failed/
   misaligned callback; executor callback is fact-only; no invented runtime
   config; no unapproved config edits; protection is a constraint, not the
   objective; do not preserve removable private glue; do not pass planner
   `self` into focused modules; do not add broad pass-through objects, generic
   blackboards, broad config bags, anemic services, or one-method-per-private-
   method callback bags; preserve public schema, token contracts, branch order,
   reason strings, reset timing, default legacy FSM, and BT/VLM/LLM fail-fast
   status unless the user explicitly approves a semantic change.

This keeps strategic architecture documentation consistent across phases while
still requiring each code slice to provide enough evidence for documentation to
be updated accurately. Implementation threads may update narrowly local
docstrings or comments required by code readability, but they should not make
source-of-truth architecture-plan updates unless explicitly instructed for that
phase.

## Review Checklist For New Slices

Before accepting a slice, answer:

- Which ideal boundary did it move toward?
- Which current gap did it close?
- Did it reduce policy-shell responsibility?
- Did it avoid passing planner `self` into focused modules?
- Did it avoid a pass-through or an anemic service?
- Did it preserve branch order, reason strings, thresholds, token schema,
  debug schema, summary schema, trace schema, reset timing, and low-level action
  shape?
- Did it keep parked paths out of the target architecture?
- Did docs and tests lock the new boundary?
