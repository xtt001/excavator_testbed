# Primitive Planner Interface Standard

Status: **active interface target and implementation standard**.

This document defines the target primitive planner interface boundaries and
compares them with the current Phase 9.35 implementation. It is intentionally
not a snapshot-only inventory. Use it to decide whether future refactor slices
move the code toward the architecture in
`docs/planner_execution_abstraction_flow.svg`.

The current implementation is best described as **default legacy FSM
backendified with focused services**. It is not yet a fully backend-agnostic
planner where behavior-tree, VLM, or learned decision backends can be swapped in
without additional interface work.

## Source Documents

- `docs/planner_execution_abstraction_flow.svg`
- `docs/planner_current_code_architecture_plan.md`
- `docs/planner_effect_boundary_design.md`
- `docs/planner_rollout_evidence_refactor_plan.md`
- `docs/planner_rollout_evidence_refactor_log.md`

## Maturity Statement

Current maturity:

- public adapter compatibility: **mostly achieved**
- tick execution ordering: **achieved for one-tick execution**
- legacy FSM mainline branch conversion to requested effects: **achieved**
- capability/status provider boundary for legacy FSM: **partly achieved**
- effect request/application boundary: **achieved for current requested effects**
- focused token, coverage, handoff, dispatch, report, reset, config services:
  **mostly achieved**
- runtime composition root / public runtime kernel: **achieved for public
  runtime routing**
- backend-neutral fact packet for non-FSM decision strategies: **partly
  achieved for common context/skill facts only**
- behavior-tree, VLM, LLM, or learned decision backend implementation:
  **not implemented; unsupported backends must fail fast**

Do not describe the current code as "fully swappable backend architecture." The
accurate claim is: the confirmed-live 4P legacy FSM path has been backendified,
and the shell now delegates most domain work to focused services.

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
  `planner_trace()` delegate to `PrimitivePlannerRuntimeKernel`.
- The policy still builds the runtime kernel's typed ports and keeps legacy
  storage/facade methods, but it is no longer the owner of the public runtime
  route.

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
  -> PrimitivePlannerRuntimeKernel
      -> PrimitiveExecutionDriver
      -> PrimitiveDecisionRuntime
      -> RequestedEffectApplier
      -> PrimitiveActionDispatchService
      -> PrimitiveTickFinalizationService
      -> report builders
      -> token/coverage/return services
```

The runtime kernel owns public runtime routing:

- `reset()`
- `predict(obs)`
- `debug_state()`
- `rollout_summary()`
- `planner_trace()`

The execution driver owns one-tick ordering. The runtime kernel owns the
composition of all services needed by those public calls.

Current boundary:

- `PrimitivePlannerRuntimeKernel` owns the public runtime route:
  `reset()`, `predict(obs)`, `debug_state()`, `rollout_summary()`, and
  `planner_trace()`.
- `PrimitiveExecutionDriver` owns one-tick execution ordering under the kernel.
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

- `PrimitiveDecisionRuntime` selects only the `legacy_fsm` backend.
- `LegacyFSMBranchSet` owns requested order and legacy compatibility order.
- Legacy FSM branches consume `PrimitiveDecisionContext` plus common
  `PrimitiveDecisionFacts` through `PrimitiveDecisionCapabilities`.
- Unsupported backend names fail fast.

Gap:

- Current capabilities are still shaped around legacy FSM transition branches.
- `PrimitiveDecisionFacts` currently covers common facts only: context identity,
  current skill name, current switch reason, and context convenience accessors.
- Return transition refresh is now explicit: the active legacy-FSM return branch
  refreshes shell-owned handoff cache state before reading return status, while
  `return_transition_status(...)` itself is read-only.
- There is no full backend-neutral fact packet for behavior-tree or VLM
  strategies because transition, token, coverage, and return handoff facts are
  not yet in a neutral packet.
- There is no alternate backend implementation.

Standard:

- Keep unsupported backends fail-fast until a backend has focused tests,
  explicit facts, and parity scope.
- New backends must return `PrimitiveDecisionResult` with ordered requested
  effects.
- New backends must not depend on policy private attributes, compatibility
  facades, or broad callback bags.
- `legacy_fsm` remains the only supported runtime backend until this document is
  updated with a concrete alternate backend contract.

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

Gap:

- Context is adequate for current FSM backend.
- The common facts packet is intentionally small; future backend-neutral facts
  still need typed views for transition, token, coverage, and return handoff
  state.

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
  status records.
- `PrimitiveFSMCapabilityProvider.refresh_return_transition_state(obs)` owns
  the explicit return handoff cache refresh step. `return_transition_status(...)`
  only reads cached return flags and observation facts.
- `PrimitiveDecisionFacts` is the first backend-neutral common facts packet. It
  contains `PrimitiveDecisionContext`, current skill name, current switch
  reason, and read-only context accessors; it does not include transition status
  providers or mutation ports.
- `PrimitiveDecisionCapabilities` maps a decision context to current skill,
  common decision facts, bootstrap status, transition statuses, and residual
  `pre_dig_align` handling.
- `PrimitiveObservationFacts` and transition status dataclasses exist.

Gap:

- The current capability object is still backend-facing for legacy FSM.
- Residual `pre_dig_align` is still a capability-side already-applied handler.
- `PrimitiveDecisionFacts` is not yet the complete `PrimitiveBackendFacts`
  target. It lacks transition, token, coverage, and return handoff views.
- Dig/carry/dump/return transition status providers intentionally remain lazy
  and branch-local. Return refresh is explicit and still timing-sensitive, so it
  must stay in the active return branch until a backend-neutral return facts
  view is designed and tested.

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
- `RequestedEffectApplier` owns effect-class dispatch and delegates state
  mutation to typed ports/services.

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
- Adding an effect requires focused tests, validation tests, and parity tests for
  any public observable surface it touches.

## Layer 8: Shell-Owned State And Mutation

Ideal boundary:

- Mutable planner runtime state lives in focused state owners.
- Effect appliers mutate state owners through typed ports.
- The public adapter stores only public compatibility handles and state owners.

Current boundary:

- `CoverageRuntimeState` owns coverage mutable state.
- Many token, return, pre-dig, debug mirror, and switch fields still live as
  policy attributes.
- Skill lifecycle, reset lifecycle, and token runtime services own sequencing,
  but write through policy-owned storage.

Gap:

- Runtime state is only partially extracted.
- The policy shell still owns a large amount of mutable storage.

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

Gap:

- This layer is close to target.
- It is reached through the runtime kernel and execution driver, but still
  receives policy handles through policy-built dispatch ports.

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
- `PrimitiveTokenRuntimeCoordinator` owns dig/return token runtime sequencing.
- `PrimitiveDigTokenPlanningService` and
  `PrimitiveReturnTokenPlanningService` own orchestration.
- Token algorithm classes remain in `primitive_tokens.py`.

Gap:

- Token mutable state still mostly lives in policy attributes.
- There is no dedicated token runtime state owner.

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
- Candidate construction, scoring, and state-exemplar planning have focused
  owners.

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
- Policy still prepares section snapshots and compatibility fields.

Gap:

- This layer is close to target.
- Section snapshot providers may be further narrowed later, but schema assembly
  is already outside the large policy class.

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
- `PrimitiveSkillLifecycleService` owns `_set_skill()` lifecycle sequencing.

Gap:

- `primitive_adapter_config.py` is already over the large-file threshold. It is
  allowed as the result of this extraction, but new config behavior should not
  continue accumulating there without a split.

Standard:

- Public constructor signature and defaults must remain compatible.
- New config semantics must have one source of truth.
- Config normalizer may build legacy field updates, but that dict must not
  spread into decision backends or runtime state owners.

## Parking And Removed Runtime Policy

Current parking:

- `pre_dig_align`: residual parking/action material. It is not target mainline
  backend capability.
- `cell_entry`: compatibility/report material. It is not target token contract
  for the selected mainline rollout.
- `5P`: removed runtime. Historical behavior is preserved only by git history;
  runtime eval may keep a fail-fast diagnostic.
- behavior-tree, VLM, and LLM backends: unsupported parked scope.

Standard:

- Do not migrate parked paths into target architecture just because code exists.
- A parked path can only be promoted after explicit evidence and user approval.
- Removed runtime paths must not be restored without explicit user direction.

## Next Implementation Order

The next code work should follow this order:

1. Expand backend-neutral facts beyond the initial common packet.
   - Keep legacy FSM capabilities working.
   - Preserve lazy transition-status timing; do not eagerly refresh or compute
     return status outside the active return branch.
   - Treat explicit return refresh plus read-only status as the starting point
     for a future backend-neutral return facts view, not as proof that return
     facts have already migrated.
   - Add only facts that are stable across backend styles.
   - Do not implement BT/VLM yet.

2. Move remaining mutable runtime state into focused state owners.
   - Prioritize token/runtime and return state before parked legacy paths.
   - Avoid generic blackboards.

3. Audit parked paths.
   - Decide whether to remove, keep diagnostic-only, or convert
     `pre_dig_align` and `cell_entry`.
   - Do not do this before the runtime kernel boundary is clear.

4. Only then prototype a new backend.
   - Start with a non-default, fail-closed backend contract test.
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
2. The implementation thread reports the exact changed files, behavioral impact,
   verification commands, commit hash, and any residual risks back to the
   refactor-thinking/audit thread.
3. The refactor-thinking/audit thread audits the code result and updates
   architecture documents, interface standards, and execution records as part of
   that audit.

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
