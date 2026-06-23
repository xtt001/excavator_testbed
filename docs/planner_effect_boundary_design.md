# Planner Effect Boundary Design

Status: **Phase 8 design source for planner effect-boundary work**.

This document defines the intended `PlannerEffect` boundary for the primitive
planner refactor. It is a design document only: no planner runtime behavior is
changed by this document.

The goal is to make the future decision backend return ordered, validated
effect requests while the execution kernel remains the only layer that applies
planner state mutations. This closes the largest remaining gap between the
current implementation and the execution/backend abstraction diagram.

For the broader ideal-vs-current interface target across public adapter,
runtime kernel, decision backend, capability facts, effects, state, token,
coverage, reporting, config, and parked paths, use
`docs/planner_primitive_interface_standard.md`.

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

Current status after Phase 9.69: the default 4P mainline branch chain no longer
falls through to the broad `LegacyFSMBackendAdapter -> _maybe_switch_skill()`
callback, and branch ordering is no longer hand-written in the large policy
shell. The decision runtime now selects a backend factory through
`PrimitiveDecisionRuntimePorts.backend_factories` instead of receiving a
`legacy_fsm_branch_set` callable. `LegacyFSMDecisionBackendFactory` owns
legacy branch-set construction/reuse plus requested and legacy compatibility
backend construction; `legacy_fsm` remains the only supported backend and
unsupported names still fail fast before branch-set construction. Token runtime
mutable storage is now owned by `PrimitiveTokenRuntimeState`: dig/return token
arrays, token source/fallback fields, return start-envelope prior flags, and
pending next-dig token/raw/exemplar fields are no longer independent policy
attributes. The policy keeps legacy private token field names as
property-backed compatibility facades over that state owner. Live token arrays
and source fields project through `TokenStatus`, while pending/dig-cut report
metadata projects through `PrimitiveTokenReportStatus` for debug, summary, and
trace consumers. `PrimitiveTokenRuntimePorts` now carries that focused token
state owner directly, so `PrimitiveTokenRuntimeCoordinator` no longer receives
policy-built getter/setter callbacks for the same token storage fields. The
same token runtime boundary now also carries `CoverageRuntimeState` directly
for the pending next-dig state-exemplar handoff: exemplar ids, exemplar
distance, profile token copy source, and active-exemplar clear timing no longer
flow through policy-built callbacks. Skill lifecycle sequencing now carries
focused execution, cycle, return, pre-dig-align compatibility, and coverage
runtime state owners through `PrimitiveSkillLifecyclePorts`, so skill/reason
writes and target-specific counter resets no longer require policy-built
storage setter callbacks. The service still keeps explicit external action
ports for low-level active policy reset and dig-cut plan clearing. The
FSM transition-status provider boundary now also follows the focused owner
pattern: `PrimitiveFSMCapabilityProviderPorts` carries cycle, coverage, and
return runtime state owners directly, so dig counters, terminal-stop state,
cycle-start deposit, dump hold/start fields, return cached flags, and the
dig-to-carry reason mirror no longer flow through policy-built storage
fields/callbacks. Threshold/config values, semantic-boundary profile reads,
explicit return handoff refresh, and `pre_dig_align` gate reads remain explicit
ports. Since Phase 9.75, dig-exit overshoot calculation is owned by the
capability provider from observation facts plus the active coverage corridor
rather than a policy callback. Requested-effect application
now carries focused cycle and return runtime state owners directly, so return
next-dig marking, return-cycle completion, dig replan counters, dump hold
counts, and dump start deposited mass updates no longer pass through
policy-built state-mutation callbacks. Skill switching, coverage/cell-entry/
restart actions, return handoff routing, and deposited-mass observation reads
remain explicit ports. The
coverage selection runtime boundary now follows the same state-owner pattern:
`CoverageSelectionRuntimePorts` carries `CoverageRuntimeState`, and
`CoverageSelectionRuntimeCoordinator` reads/writes corridor lists, candidate
scores, active/last-selected ids, and all-depleted checks through that owner
instead of receiving policy-built coverage-state getter/setter callbacks.
Coverage effect runtime has also moved its mutable storage coupling to
`CoverageRuntimeState`: current payload gain, last payload/deposit, completed
dump count, global low-productivity streak, rejected exemplar ids, pass index,
active corridor id, terminal-stop state, active corridor lookup, corridor
lists, and all-depleted checks now flow through the coverage state owner while
mode/config, update/runtime services, facts builders, low-productivity
thresholds, and decision-event recording remain explicit external ports. The
active dig token planning boundary now follows the same owner pattern:
`PrimitiveDigTokenPlanningPorts` carries `PrimitiveTokenRuntimeState` and
`CoverageRuntimeState`, and `PrimitiveDigTokenPlanningService` reads/writes
pending dig route state, dig-cut source/fallback/prior flags,
dig-depth-profile source/fallback fields, active corridor ids, payload/deposit
baselines, and state-exemplar payload through those owners instead of
policy-built storage callbacks. Config facts, token planner algorithms,
observation facts, coverage corridor selection, and coverage raw-field building
remain explicit external ports.
Phase 9.84 narrows the active dig and return token planning observation
fact-source boundary further. Both token planning port sets now receive a
typed `PrimitiveObservationFacts` provider instead of separate policy-built
bucket pose, deposited-mass, env-state, qpos, and qvel callbacks. The token
planning services still keep planner algorithms, coverage corridor selection,
and coverage raw-field building as explicit ports, and this does not change
policy observation token injection order or token schemas.

Failed-dig/restart recovery is now a focused service boundary rather than
direct policy implementation. `PrimitiveDigRecoveryService` consumes focused
execution, cycle, return, coverage, token, and pre-dig-align compatibility
state owners for the restart/recovery state writes previously embedded in
`PrimitivePlannerACTPolicy`. It preserves explicit ports for active-policy
reset, dig-cut plan invalidation/clear actions, operator-prior token
construction, raw-field prior checks, pre-dig entry/timeout gates, coverage
decision event recording, coverage terminal-stop requests, mass reads, and
configuration facts. This keeps failed-dig recovery cohesive while leaving
`pre_dig_align` parked/residual; it does not convert pre-dig-align into a
mainline backend-requested effect or change the selected rollout's
`cell_entry` parking decision.
Return direct-handoff effect application now follows the same focused-owner
rule for state reads and mutations. `ReturnDirectHandoffEffectPorts` carries
the execution and cycle runtime owners directly; the service reads the current
skill from `PrimitiveExecutionRuntimeState` and completes the return
transition through `PrimitiveCycleRuntimeState`. The next-skill choice is
driven by explicit `should_pre_dig_align_before_dig` and skill-name facts
rather than a policy private helper callback. `set_skill` and return-target
planning remain explicit lifecycle/algorithm ports. Return handoff readiness is
now supplied by `ReturnHandoffReadinessService`, which owns entry-target
precedence, entry-error projection, start-envelope gate input/result writeback,
`handoff_ready`, and direct-handoff mass/config gating over the focused return,
token, coverage, cycle, and execution owners.
The return token planning boundary has also
been narrowed to the same focused owners: `PrimitiveReturnTokenPlanningPorts`
carries `PrimitiveTokenRuntimeState` and `CoverageRuntimeState`, and
`PrimitiveReturnTokenPlanningService` reads/writes return start-envelope
source/prior flags plus active corridor/corridor lookup state through those
owners instead of policy-built storage callbacks. Return-target mode routing,
token planner algorithms, observation facts, coverage corridor selection, and
coverage raw-field building remain explicit external ports. The policy now
also owns non-token return handoff/runtime cache state through
`PrimitiveReturnRuntimeState`: return step count, return-to-dig entry-close
cache, return next-dig-event flag, and return start-envelope gate result/checks
are no longer independent policy attributes. The policy keeps legacy private
return field names as property-backed compatibility facades over that return
state owner. Mainline cycle/progress state is now owned by
`PrimitiveCycleRuntimeState`: dig progress counters, dump hold counters,
transition timeout/completion counters, cycle index, and dump-start deposit
baseline are no longer independent policy attributes. The policy keeps legacy
private cycle/progress field names as property-backed compatibility facades over
that cycle state owner, and live cycle/progress report/finalization projection
now lives with that owner through `PrimitiveCycleReportStatus`. Scripted
bootstrap runtime state and rules are now
owned by `PrimitiveScriptedBootstrapRuntimeState` and
`PrimitiveScriptedBootstrapRuntimeService`: scripted-qpos enabled detection,
target-reached hold gating, timeout completion, and PD bootstrap action
generation are no longer inline policy logic. The policy keeps old scripted
bootstrap private counter names as property-backed compatibility facades over
the state owner, and action dispatch still reaches the scripted action through
the existing compatibility facade. Live scripted-bootstrap report/status
projection now lives with that owner through
`PrimitiveScriptedBootstrapReportStatus`. Execution lifecycle metadata is now owned by
`PrimitiveExecutionRuntimeState`: active skill, switch reason, previous action,
and latest compact debug state are no longer independent policy attributes, and
the policy keeps their old private names as property-backed compatibility
facades. This execution state owner does not absorb effect application, token
state, coverage state, return state, cycle/progress state, scripted bootstrap
state, residual `pre_dig_align`, or `cell_entry`. The policy now
exposes backend-facing common decision facts through
`PrimitiveDecisionFacts`, built by `PrimitiveDecisionFactsSource`; the facts
packet carries context identity, current skill, and current switch reason, but
does not carry mutation ports or eager transition statuses. `LegacyFSMBranchPorts`
has been narrowed to skill-name constants plus separate
`PrimitiveDecisionFactsSource` and `PrimitiveDecisionCompatibilityActions`
dependencies. `LegacyFSMBranchSet` constructs branches and owns both requested
and legacy compatibility dispatch orders. `PrimitiveRequestedBranchRunner` and
`LegacyFSMCompatibilityDecisionBackend` now construct one
`PrimitiveBackendDecisionInput` per decision call and pass that same input
through the ordered branch chain. `LegacyFSMBootstrapBranch`,
`LegacyFSMDigBranch`, `LegacyFSMCarryBranch`, `LegacyFSMDumpBranch`, and
`LegacyFSMReturnBranch` consume that input through `decide_input(...)`; branch
dataclasses store only static config instead of facts source, compatibility
actions, the broad `PrimitiveDecisionCapabilities` facade, or individual shell
callback/status provider fields. Dig/carry/dump/return transition statuses
remain lazy and branch-local. `PrimitiveBackendFactsAccess`
now provides the backend-facing read-only access contract for bootstrap and
dig/carry/dump/return transition facts; it carries the shared common facts
identity plus private read-only bootstrap and transition readers, and it does
not expose sync, refresh, residual, effect-applier, or shell mutation APIs.
Bootstrap decisions consume `PrimitiveBackendFactsAccess.bootstrap_decision(...)`
only after the active bootstrap skill check; the read-only bootstrap facts view
preserves the existing end-mode and pre-dig gate next-skill rules without
promoting residual `pre_dig_align` into a mainline mutation path. Return handoff refresh
is now explicit: `LegacyFSMReturnBranch` calls
`PrimitiveDecisionCompatibilityActions.refresh_return_transition_state(context)` only
after the active skill check confirms `return`, and then consumes
`PrimitiveBackendFactsAccess.return_transition()`.
`PrimitiveReturnTransitionFacts` wraps the existing common facts packet and the
read-only `ReturnTransitionStatus` without carrying refresh/provider/applier
fields.
`PrimitiveFSMCapabilityProvider.return_transition_status(...)` is therefore a
read-only cached-status assembly point rather than a hidden mutation/refresh
entry. This preserves return handoff refresh timing and avoids eager status
calculation. Dig-to-carry reason mirror writeback is also no longer hidden in
the dig status read: active dig branch decisions now consume
`PrimitiveBackendFactsAccess.dig_transition()`, then
explicitly call
`PrimitiveDecisionCompatibilityActions.sync_dig_transition_reason(...)` before selecting effects from
`PrimitiveDigTransitionFacts.status`. `PrimitiveFSMCapabilityProvider.dig_transition_status(...)`
is a read-only status assembly point, while `sync_dig_transition_reason(...)`
preserves the legacy shell/debug mirror write timing, including empty reasons.
Carry and dump branch decisions now follow the same facts-view pattern through
`PrimitiveBackendFactsAccess.carry_transition()` and
`PrimitiveBackendFactsAccess.dump_transition()`.
`PrimitiveCarryTransitionFacts` and `PrimitiveDumpTransitionFacts` wrap the
existing common facts packet plus read-only carry/dump status identities without
carrying providers, appliers, effects, mutation callbacks, or refresh/sync
fields. `LegacyFSMRequestedDecisionBackend`
is the default decision backend used by the execution driver, while
`LegacyFSMCompatibilityDecisionBackend` serves the legacy `_maybe_switch_skill()`
entry without applying effects inside backend branches. Bootstrap, dig, carry,
dump, and return are handled through explicit requested-effect branch decisions
in both entry paths, and requested effects are applied by the same
`RequestedEffectApplier`. Residual `pre_dig_align` behavior remains an
already-applied compatibility/parking path through a narrow residual adapter
and the capabilities object's explicitly named residual handler because
selected rollout evidence classifies it as not active in the mainline. The
confirmed-live dig branch consumes one explicit `DigTransitionStatus` provider
through capabilities instead of five gate callbacks, matching the carry/dump/
return status-object pattern while keeping dig mutation in requested effects.
Requested-effect application lives in `RequestedEffectApplier` with typed shell
mutation ports; the policy shell only builds those ports and delegates from its
execution hook and legacy compatibility bridges. `PrimitiveFSMCapabilityProvider`
now owns observation-facts projection and dig/carry/dump/return status assembly
through typed read-only shell ports, with return refresh split into the explicit
`refresh_return_transition_state(obs)` method. The policy shell only builds the provider
ports/snapshot, retains thin diagnostic wrappers for the old private status
methods, and still owns shell-side mutation through the effect applier.
`ReturnStartEnvelopeGateService` now owns return-to-dig start-envelope
readiness and diagnostic check computation; the policy shell prepares inputs,
writes cached ready/error/check state, and retains direct-handoff read/write
ports. `ReturnDirectHandoffEffectService` now owns the ordered effect-side
return/direct-handoff mutation sequence for `SetReturnOrDirectHandoffEffect`:
set `return`, optionally ensure the return target plan, evaluate handoff and
direct-handoff readiness, complete the return transition, and switch to `dig`
or residual `pre_dig_align` with the existing `return_to_*_start_envelope_ready`
reason. `PrimitivePolicyObservationAssembler` now owns low-level policy
observation token injection: provider call order, injected key names,
copy/no-copy behavior, and immutable legacy injected-flag state calculation.
`PrimitiveObservationInjectionRuntimeState` owns the mutable per-observation
injected compatibility flags: reset defaults, clear before assembly, apply from
`PrimitiveTokenInjectionState`, and compatibility projection. The policy shell
builds typed token-provider ports and keeps old injected-flag names as
property-backed facades over that owner.
`PrimitiveCellEntryCompatibilityRuntimeState` owns parked cell-entry
compatibility/report storage: goal, goal cycle id, audit, cached token array,
seen cell id, and trace list. The policy keeps old `_cell_entry_*` names as
property-backed facades while the cell-entry planner/auditor algorithms remain
in their existing parked compatibility path. This does not promote cell-entry
tokens into the mainline token contract or decision backend facts.
Phase 9.80 extends that parked owner with `PrimitiveCellEntryReportConfig` and
`PrimitiveCellEntryReportStatus`. Parked cell-entry public debug fields,
rollout-summary enablement/trace-count fields, and planner-trace trace list
now project from the compatibility state owner plus explicit config facts.
This keeps cell-entry as compatibility/report material and does not promote
cell-entry tokens, planner/auditor behavior, or trace mutation semantics into
the mainline token contract, decision backend facts, or runtime architecture.
`PrimitiveTokenRuntimeCoordinator` now owns the dig/return token
runtime sequencing used by those providers: dig-cut gating, terminal-stop
cached-token behavior, bootstrap policy token exception, hold-cycle checks,
return-target hold-cycle checks, return relocate planning, return-start-envelope
token routing, pending next-dig plan writeback, fallback-zero invalidation, and
dig-cut/pending-plan clearing. Token planner algorithms and token contracts
remain in their existing owners. `PrimitiveReturnTokenPlanningService` now owns
return token planning orchestration in
`testbed/planner/primitive_return_token_planning.py`: return-target mode
routing, coverage-corridor selection handoff, active corridor writeback,
coverage raw-field planning with `update_state=True`, return-start-envelope
token build/apply/conditioning, source/prior-bound flag writeback, prior
token/mapping/bounds helpers, corridor-id to cell-id fallback, and token/raw
field copy semantics. The low-level `ReturnTargetTokenPlanner`,
`ReturnRelocateTokenPlanner`, and `ReturnStartEnvelopeTokenPlanner` algorithms
remain the token algorithm owners.
`PrimitiveDigTokenPlanningService` now owns active dig token planning
orchestration in `testbed/planner/primitive_dig_token_planning.py`: pending
return-target dig route application, conservative/operator-prior/
operator-prior-coverage mode routing, coverage raw-field handoff, fallback
conservative behavior, dig-cut source/fallback/in-prior writeback,
dig-depth-profile planning/apply/error writeback, live/prior helper routing,
raw-field priority, cell-id priority, and token/raw-field copy semantics. The
low-level `DigCutTokenPlanner` and `DigDepthProfileTokenPlanner` algorithms
remain the token algorithm owners.
`CoveragePlanningFactService` now owns the coverage planning fact-source
boundary in `testbed/planner/primitive_coverage_facts.py`: coverage selection
facts, coverage raw-field fallback/clamp projection, optional state-conditioned
exemplar override/writeback, exemplar distance/id projection, removed-depth
grid and weighted exemplar helper delegation, and remaining-depth projection.
The policy shell supplies explicit config/state/exemplar/observation inputs and
keeps old private names as compatibility facades. Coverage scoring/selection
algorithms, state-exemplar scoring, raw-field priority, token schema, report
schema, residual `pre_dig_align`, parked `cell_entry`, and backend fail-fast
behavior remain unchanged.
`PrimitiveDebugReportBuilder` now owns public `debug_state()` dict assembly:
base transition keys, token debug fields from `TokenStatus.to_debug_fields()`,
return gate fields, coverage fields, cell-entry compatibility fields, and
residual pre-dig fields. The policy shell builds a typed debug snapshot and
section values, then delegates report assembly to the builder.
`CoverageReportService` now also owns the planner-trace coverage sub-
projection through `CoverageTraceReportStatus` and the rollout-summary coverage
sub-projection through `CoverageSummaryReportStatus`. Phase 9.78 narrows the
coverage report snapshot boundary further: `CoverageReportService` now projects
coverage debug, trace, and summary coverage outputs from `CoverageRuntimeState`
plus explicit `CoverageReportConfig` and `CoverageSelectionService` facts. The
policy shell still builds non-coverage report inputs and passes explicit
coverage config/service facts, but it no longer hand-assembles the coverage
snapshot dictionaries/lists for those public report sections.

Phase 9.58 extends `CoverageReportService` in
`testbed/planner/primitive_coverage_reports.py` with `trace_status(...)` and
adds `CoverageTraceReportStatus`. The planner trace coverage subset now moves
as one coverage report/status object into `PrimitivePlannerTraceInputs`, while
`PrimitivePlannerACTPolicy._planner_trace_inputs()` remains a thin explicit-
facts assembler. This phase does not change public `planner_trace()` key names,
coverage decision trace count semantics, list shallow-copy behavior, corridor
debug payload values, decision trace mutation, terminal-stop behavior, coverage
debug/summary schemas, coverage algorithms, backend facts, or removed 5P
runtime status.

Phase 9.59 extends the same `CoverageReportService` with
`summary_status(...)` and adds `CoverageSummaryReportStatus`. The rollout
summary coverage subset now moves as one coverage report/status object into
`PrimitiveRolloutSummaryInputs`, while
`PrimitivePlannerACTPolicy._rollout_summary_inputs()` remains a thin explicit-
facts assembler for coverage summary status and non-coverage summary fields.
This phase does not change public `rollout_summary()` key names, bool-to-int
projection, `None`-to-`NaN` projection, debug schemas, planner trace schemas,
coverage algorithms, corridor debug payload values, decision trace mutation,
terminal-stop behavior, backend facts, or removed 5P runtime status.

Phase 9.78 extends the same report boundary with `CoverageReportConfig`,
`debug_fields_from_state(...)`, `summary_status_from_state(...)`, and
`trace_status_from_state(...)`. The coverage report service now consumes the
focused `CoverageRuntimeState` owner directly and uses the existing
`CoverageSelectionService` for row/cell/attempt/confidence facts needed by
corridor debug payloads. The policy shell remains a thin adapter that supplies
state/config/service inputs for the coverage subset and keeps non-coverage
report fields in their existing owners. This phase does not change public
debug/summary/trace key names, `NaN`/`None`/`-1` fallback semantics, list
shallow-copy behavior, candidate scores, decision trace, terminal-stop fields,
coverage selection/effect algorithms, residual `pre_dig_align`, parked
`cell_entry`, backend fail-fast behavior, or removed 5P runtime status.

Phase 9.79 narrows parked pre-dig-align report projection without promoting
pre-dig-align into the mainline backend/runtime architecture. The existing
`PrimitivePreDigAlignCompatibilityRuntimeState` now projects
`PrimitivePreDigAlignReportStatus` from its parked mutable state and explicit
`PrimitivePreDigAlignReportConfig` facts. `PrimitivePlannerACTPolicy` keeps thin
report config/status facades, `debug_state()` gets the same public pre-dig
debug keys from `PrimitivePreDigAlignReportStatus.debug_fields()`, and
`PrimitiveRolloutSummaryInputs` carries the same status object for the pre-dig
summary keys. This phase does not change pre-dig readiness, target, timeout,
surface-guard, action, replan, or handoff algorithms, and does not change branch
order, reason strings, report schemas, `cell_entry`, backend fail-fast behavior,
or removed 5P runtime status.

Phase 9.80 narrows parked cell-entry report projection without promoting
cell-entry into the mainline token/backend/runtime architecture. The existing
`PrimitiveCellEntryCompatibilityRuntimeState` now projects
`PrimitiveCellEntryReportStatus` from its parked mutable state and explicit
`PrimitiveCellEntryReportConfig` facts. `PrimitivePlannerACTPolicy` keeps thin
report config/status facades, `debug_state()` gets the same public cell-entry
debug keys from `PrimitiveCellEntryReportStatus.debug_fields()`,
`PrimitiveRolloutSummaryInputs` carries the same status object for cell-entry
summary fields, and `PrimitivePlannerTraceInputs` carries it for cell-entry
trace projection. This phase does not change cell-entry planner/auditor/token
algorithms, token dimensions, trace mutation semantics, reset semantics, branch
order, reason strings, report schemas, `pre_dig_align`, backend fail-fast
behavior, or removed 5P runtime status.

`PrimitiveRolloutSummaryBuilder` now owns public `rollout_summary()` dict
assembly: summary key layout, bool-like `int(...)` projections, `None` to
`NaN` fallback fields, compact coverage/return/pre-dig/cell-entry
compatibility summary fields, and legacy scalar conversions. The policy shell
builds a typed summary snapshot and delegates report assembly to the builder;
`PrimitivePlannerTraceBuilder` now owns public `planner_trace()` dict assembly:
trace key layout, token contract version/string fields, top-level list
projection for cell-entry trace, coverage corridors, and coverage decision
trace, coverage config/status fields, and terminal-stop fields. The policy
shell builds typed trace inputs and preprojects coverage corridor payloads
through the existing coverage report service facade; coverage decision trace
recording, coverage scoring/runtime updates, and token planning remain in
their existing owners. `PrimitiveActionDispatchService` now owns primitive
action dispatch and low-level policy selection: scripted bootstrap
short-circuit, residual pre-dig-align action short-circuit, first-dig policy
selection, active-policy lookup, all-policy ordering, and low-level policy
`predict(policy_obs)` action shaping. The policy shell builds typed dispatch
ports and retains thin compatibility wrappers for `_dispatch_tick_action()`,
`_active_policy()`, `_all_policies()`, and `_first_dig_policy_active()`.
`PrimitiveTickFinalizationService` now owns primitive tick finalization rules:
previous-action copy semantics, dispatch-after transition-completed reason
prefix detection, and compact `PrimitivePlannerDebugState` assembly for the
default 4P planner. The policy shell prepares typed finalization inputs, writes
`_prev_action` / `_debug_state`, and retains thin compatibility wrappers for
the execution hooks. `PrimitiveResetLifecycleService` now owns 4P reset
lifecycle sequencing in `testbed/planner/primitive_reset_lifecycle.py`:
low-level policy reset order, boundary detector reset, bootstrap/pre-dig
initial-skill selection, counter/token/pending/coverage/debug defaults, and
fresh `CoverageRuntimeState` creation. Public `reset()` only builds reset ports,
applies the returned reset state, and creates the initial compact debug state.
The 5P runtime planner subclass has been removed by explicit cleanup decision;
old 5P runtime behavior is preserved only in branch/git history.
`PrimitivePlannerAdapterConfigNormalizer` now owns public adapter config
normalization in `testbed/planner/primitive_adapter_config.py`: constructor
config expansion, optional float/vector parsing, goal-sequence normalization,
plane-depth and failed-dig replan normalization, dig-cut prior loading,
dig-planner validation, cell-entry compatibility object construction,
coverage/state-exemplar config normalization, pre-dig-align vectors, scripted
bootstrap vectors, and legacy policy-field update payload assembly.
`PrimitivePlannerACTPolicy.__init__` keeps the same public signature and only
stores low-level policy handles plus the boundary detector before applying the
normalized config state and calling `reset()`. This is an adapter config
normalization boundary only; it is not a kernel factory, backend selector,
BT/VLM/LLM implementation, or `pre_dig_align`/`cell_entry` cleanup.
`PrimitivePlannerRuntimeKernel` now owns the public runtime route in
`testbed/planner/primitive_runtime_kernel.py`: `reset()`, `predict(obs)`,
`debug_state()`, `rollout_summary()`, and `planner_trace()`. The policy shell
builds typed runtime-kernel ports and keeps compatibility facades/storage, while
the kernel composes the reset lifecycle service, execution driver, and report
builders. This closes the public composition-root gap without changing backend
support; `legacy_fsm` remains the only supported decision backend and
BT/VLM/LLM remain unsupported parked scope.
`CoverageRuntimeState` now owns mutable coverage runtime state in
`testbed/planner/primitive_coverage_state.py`: corridor storage, selected ids,
payload/deposit counters, pass/terminal state, candidate scores, decision trace,
and state-exemplar runtime fields. The 4P policy shell initializes a fresh state
owner on reset and keeps the old `_coverage_*` private names as property-backed
compatibility facades so existing tests and diagnostics still observe and mutate
the same stored containers. Coverage selection/effect coordinators read and
write through the state owner via typed ports; candidate construction, scoring,
effect sequencing, report schemas, and public trace/summary/debug payloads
remain unchanged.
`CoverageStateExemplarPlanner` now owns coverage state-conditioned exemplar
planning in `testbed/planner/primitive_coverage_exemplars.py`: exemplar
loading/validation, removed-depth grid projection, exemplar distance and
temperature weighting, weighted dig-cut raw-field assembly, weighted
dig-depth-profile token assembly, rejected-exemplar filtering, and pure plan
selection. The policy shell keeps compatibility facades for the old private
methods and owns only runtime writeback from a selected plan into
`CoverageRuntimeState` and the active corridor debug fields.
`PrimitiveExecutionDriver` now owns the public primitive tick execution route
in `testbed/planner/primitive_execution.py`: boundary-event preparation,
switch-reason reset, dig-progress update when the tick starts in `dig`,
decision backend invocation, requested-effect application before return-timeout
accounting and action dispatch, previous-action recording,
transition-completed check, and debug finalization. `PrimitivePlannerACTPolicy`
builds typed `PrimitiveExecutionPorts` and delegates `predict()` to the driver;
`run_primitive_tick()` and `PrimitiveTickCallbacks` remain compatibility
facades over the same driver ordering.
`PrimitiveDecisionRuntime` now owns the decision-backend selector boundary in
`testbed/planner/primitive_decision_runtime.py`. The execution driver calls the
policy's generic `_decide_tick()` bridge, which delegates to this runtime. The
runtime currently supports only the confirmed-live `legacy_fsm` backend, builds
the `LegacyFSMBranchSet` through typed ports, routes both requested decisions
and legacy `_maybe_switch_skill()` compatibility decisions through the same
selector, and fail-fasts unsupported names such as behavior-tree or VLM
backends instead of falling back to broad legacy mutation. This is still
`default legacy FSM backendified`, not evidence that alternate backends are
implemented or swappable.
`PrimitiveDecisionContext` now owns the read-only decision input packet shape in
`testbed/planner/primitive_decision_context.py`: `obs`, `boundary_event`, and
`PrimitiveTickPreparation`, with convenience fields for the skill before
decision and dig-progress update status. `PrimitiveDecisionRuntime`,
`LegacyFSMRequestedDecisionBackend`, `LegacyFSMCompatibilityDecisionBackend`,
`PrimitiveRequestedBranchRunner`, and the legacy FSM branch objects are
context-driven internally. The older scatter-argument `decide_tick(...)` methods
remain thin compatibility facades that immediately construct the shared context
packet.
`CoverageEffectRuntimeCoordinator` now owns coverage requested-effect runtime
sequencing for `CompleteCoverageDigEffect`, `CompleteCoverageDumpEffect`, and
`RejectActiveCoverageCorridorEffect`: coverage-mode no-op gating, update service
calls, coverage state writeback order, decision-event emission, all-depleted
reopen/terminal handling, global low-productivity terminal handling, and
physics-artifact terminal requests. Coverage state storage now lives in
`CoverageRuntimeState`; the policy shell builds typed ports and keeps
report/facts helper facades, while `_complete_coverage_dig()`,
`_complete_coverage_dump()`, `_reject_active_coverage_corridor()`,
`_maybe_reopen_coverage_pass()`, and `_request_coverage_terminal_stop()` are now
thin coordinator-backed wrappers.
`CoverageSelectionRuntimeCoordinator` now owns coverage corridor selection
runtime sequencing: prior/empty-candidate checks, candidate ensure/writeback,
selection-service invocation, candidate-score writeback, `select_corridor`
event emission, all-depleted reopen/terminal handling, and selected corridor id
writeback. Coverage state storage now lives in `CoverageRuntimeState`; the
policy shell keeps raw facts/helper facades and report event append mechanics.
Coverage candidate construction and scoring algorithms remain in
`CoverageCandidateBuilder` and `CoverageSelectionService`.

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
- `PrimitiveExecutionDriver` has a narrow apply-effects hook after decision and
  before return timeout/action dispatch, with `run_primitive_tick()` retained as
  a compatibility facade;
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

Phase 9.5 removed the broad already-mutating legacy fallback from the default
decision bridge. At that point the branch order was explicit:
bootstrap -> dig -> carry -> dump -> return -> residual pre-dig-align parking.
That residual path used a narrow `LegacyFSMResidualPreDigAlignAdapter` and the
shell helper `_maybe_handle_pre_dig_align_skill(obs)` so parked pre-dig-align
behavior could remain already-applied without allowing a hidden callback
backdoor for mainline branches. Phase 9.92 later removed that parked runtime
route; unknown or unclassified skills still fail fast instead of silently
re-entering `_maybe_switch_skill()`.

Phase 9.6 extracts that default branch order into
`PrimitiveRequestedBranchRunner`. The large `PrimitivePlannerACTPolicy` shell
now constructs the requested branches and residual adapter, then delegates the
decision to the runner through a legacy-named bridge. The runner is the
decision backend for ordered primitive branch dispatch: it returns the first
non-`None` branch result, stops calling later branches, and owns the fail-fast
contract when no branch handles the current skill. The policy shell remains the
public adapter and requested-effect applier; it does not regain broad
`LegacyFSMBackendAdapter` fallback behavior.

Phase 9.7 extracts legacy-FSM branch wiring into `LegacyFSMBranchPorts`,
`LegacyFSMBranchSet`, and `LegacyFSMRequestedDecisionBackend`. The policy shell
no longer imports or constructs individual branch classes for the default 4P
decision path. It exposes one typed ports object made of shell callbacks/config,
then delegates requested decisions to the backend. The branch set owns branch
construction, the requested order
bootstrap -> dig -> carry -> dump -> return -> residual, and the compatibility
facade order bootstrap -> residual pre-dig-align -> dig -> carry -> dump ->
return. `_maybe_switch_skill()` remains only as a legacy compatibility facade
and delegates to the branch set rather than hand-writing branch order.

Phase 9.8 converts the dig branch fact boundary from multiple shell gate
callbacks to explicit `DigTransitionStatus`. `LegacyFSMBranchPorts` now wires
`dig_transition_status(obs, boundary_event)` for dig facts; `LegacyFSMDigBranch`
reads that status only after confirming the active skill is `dig`, then
preserves the old priority order: exit guard, bad dig replan,
dig-complete low payload, dig-to-carry, no-change. The policy shell owns
`_dig_transition_status_for_backend(...)`, which maps current shell config/state
into `DigTransitionStatus.from_inputs(...)` and keeps `_dig_to_carry_reason` as
a compatibility/debug mirror. Old dig helper methods remain available as
diagnostic/compatibility helpers, but the default backend branch no longer calls
them as individual gate callbacks.

Phase 9.9 extracts requested-effect application into
`RequestedEffectApplier` and `RequestedEffectApplierPorts` in
`testbed/planner/primitive_effects.py`. The applier owns requested-effect type
dispatch, non-empty skill/reason validation that previously lived in the policy
shell, ordered application, and fail-fast behavior for unsupported requested
effects. The policy shell exposes `_requested_effect_applier_ports()` and
delegates `_apply_requested_tick_effects(obs, effects)` to the applier. Shell
state mutation for simple cycle/return state effects now goes through the
focused cycle and return runtime owners, while external action/algorithm
effects remain explicit ports. The applier does not decide branches, compute
status facts, dispatch low-level ACT policies, or promote `cell_entry` beyond
its explicit compatibility effect.

Phase 9.87 narrows the remaining effect-side observation metric boundary.
`RequestedEffectApplierPorts` now receives a typed `PrimitiveObservationFacts`
provider instead of a policy-built `deposited_mass` scalar callback, and
`RequestedEffectApplier` reads
`deposited_mass_in_target_box_kg` from that typed fact source when applying
`SetDumpStartDepositedMassFromObservationEffect`. `PrimitiveDigRecoveryPorts`
uses the same typed observation facts provider instead of a policy-built
`mass_in_bucket` callback for failed-dig stop payloads. This preserves
requested-effect order, dump-start deposited mass writeback, failed-dig payload
max calculation, coverage decision-event extra keys, terminal-stop request
ordering, parked `pre_dig_align`, and parked `cell_entry`.

Phase 9.10 routes the legacy compatibility `_maybe_switch_skill()` entry
through the same requested decision and centralized requested-effect applier
chain. `LegacyFSMCompatibilityDecisionBackend` uses the compatibility order
bootstrap -> residual pre-dig-align -> dig -> carry -> dump -> return and
returns `PrimitiveDecisionResult | None` without applying requested effects
itself. `_maybe_switch_skill()` now builds the compatibility tick preparation,
ignores all-miss `None`, skips reapplication for already-applied residual
`pre_dig_align`, and applies mainline requested effects through
`_apply_requested_tick_effects(...)`. Mainline branch-local `maybe_handle()`
and `_apply_effects()` mutation paths are retired; `LegacyFSMBranchPorts` keeps
decision facts/status providers and the residual parking callback, while shell
mutation callbacks belong to `RequestedEffectApplierPorts`.

Phase 9.11 extracts primitive FSM capability/status assembly into
`PrimitiveFSMCapabilityProvider` and `PrimitiveFSMCapabilityProviderPorts` in
`testbed/planner/primitive_capability_provider.py`. The provider owns
`PrimitiveObservationFacts.from_obs(...)` projection and wires the existing
`DigTransitionStatus`, `CarryTransitionStatus`, `DumpTransitionStatus`, and
`ReturnTransitionStatus` `from_inputs(...)` contracts from typed shell
snapshot/read ports. The policy shell builds the ports and exposes provider
methods to `LegacyFSMBranchPorts`; its old `_dig/_carry/_dump/_return`
backend-status helpers remain as thin compatibility/debug wrappers. Since
Phase 9.68, live cycle, coverage, and return runtime values are read through
focused state owners rather than policy-built storage fields/callbacks, and
the dig reason mirror is preserved by writing the cycle state owner. Return
handoff refresh remains an explicit provider action and status assembly only
reads cached return owner flags. `pre_dig_align`, `cell_entry`, 5P, return
direct-handoff internals, coverage metric internals, token planning, and report
schemas remain in their existing owners.

Phase 9.35 supersedes the Phase 9.11 return-refresh detail: return refresh now
lives in the explicit `refresh_return_transition_state(...)` API, while return
status assembly itself is read-only.

Phase 9.36 adds the first transition-specific decision facts view:
`PrimitiveReturnTransitionFacts`. Active return branch decisions now refresh
explicitly and then consume that facts view; non-return skills still do not
refresh or read return status/facts. This does not move return status into the
common `PrimitiveDecisionFacts` packet and does not migrate dig/carry/dump
transition facts.

Phase 9.37 adds the second transition-specific decision facts view:
`PrimitiveDigTransitionFacts`. Active dig branch decisions now consume that
facts view and explicitly synchronize the dig-to-carry reason mirror before
effect selection; non-dig skills still do not read dig status/facts or sync the
mirror. `PrimitiveFSMCapabilityProvider.dig_transition_status(...)` is now a
read-only status assembly method. This does not move dig status into the common
`PrimitiveDecisionFacts` packet and does not migrate carry/dump transition
facts.

Phase 9.38 adds `PrimitiveCarryTransitionFacts` and
`PrimitiveDumpTransitionFacts`, closing the remaining mainline transition
facts-view gap for the confirmed-live 4P FSM branches. Active carry and dump
branch decisions now consume typed facts views after their active-skill checks;
non-matching skills still do not read carry/dump facts or status. This does not
turn `PrimitiveDecisionFacts` into an eager all-status packet and does not
create a backend-neutral facts bundle or alternate backend implementation.

Phase 9.39 adds `PrimitiveBackendFactsAccess` in
`testbed/planner/primitive_backend_facts.py`, consolidating the common decision
facts plus dig/carry/dump/return transition facts views behind one lazy
read-only backend-facing access contract. The access object only reads the
requested transition status when its matching method is called, so non-matching
branches do not trigger status reads. Dig reason sync, return refresh, residual
pre-dig-align handling, effect application, and shell mutation remain explicit
capability/action responsibilities outside this access object. This does not
move bootstrap into the facts access path yet, does not turn
`PrimitiveDecisionFacts` into an eager all-status packet, and does not create an
alternate backend implementation.

Phase 9.40 adds bootstrap to `PrimitiveBackendFactsAccess` through
`BootstrapDecisionStatus`, `PrimitiveBootstrapDecisionFacts`, and a read-only
`PrimitiveBootstrapDecisionReader`. Active bootstrap branch decisions now use
`backend_facts.common` for skill checks and
`backend_facts.bootstrap_decision(...)` for bootstrap status. Non-bootstrap
skills do not call bootstrap gates or transition status readers. The old
`PrimitiveDecisionCapabilities.bootstrap_status(...)` remains a compatibility
facade over the same access path. This preserves bootstrap switch reasons and
next-skill rules, keeps residual `pre_dig_align` as a read-only gate target
rather than a promoted mainline capability, and still does not implement an
alternate backend.

Phase 9.41 splits read-only decision facts access from explicit compatibility
actions. `PrimitiveDecisionFactsSource` now owns `decision_facts(...)` and
`backend_facts(...)`, while `PrimitiveDecisionCompatibilityActions` owns only
dig reason sync, return refresh, and residual pre-dig-align handling.
`LegacyFSMBranchPorts` now carries these two dependencies explicitly instead of
`PrimitiveDecisionCapabilities`, and branch dataclasses no longer store the
mixed capabilities object. Bootstrap, carry, and dump branches receive only the
facts source; dig and return receive facts source plus compatibility actions;
the residual pre-dig adapter receives both for its already-applied
compatibility path. `PrimitiveDecisionCapabilities` remains as a compatibility
facade and construction helper over the separated objects.

Phase 9.42 introduces `PrimitiveBackendDecisionInput` in
`testbed/planner/primitive_backend_input.py`. The requested branch runner and
legacy compatibility backend each create a single input from
`PrimitiveDecisionContext`, `PrimitiveBackendFactsAccess`, and explicit
compatibility actions, then pass that input through the ordered branches.
Branches now implement `decide_input(input)` and no longer store facts source,
compatibility actions, broad capabilities, or shell callbacks. The residual
pre-dig-align adapter still handles the parked already-applied compatibility
path explicitly, and it calls
`rebuild_common_facts_after_compatibility_action()` after the shell mutation to
preserve historical `skill_after` and `switch_reason` reads. This closes the
per-tick backend input gap for the legacy FSM branch chain, while
`PrimitiveDecisionRuntime` still selects only `legacy_fsm` through a
`legacy_fsm_branch_set` factory port and does not yet expose a backend factory
or registry contract for alternate backend families.

Phase 9.43 introduces the decision-backend factory/registry boundary.
`PrimitiveDecisionBackendFactory` is the runtime-facing backend construction
contract, and `LegacyFSMDecisionBackendFactory` is the default concrete
factory. `PrimitiveDecisionRuntimePorts` now exposes
`backend_factories: Mapping[str, Callable[[], PrimitiveDecisionBackendFactory]]`
instead of `legacy_fsm_branch_set`. `PrimitiveDecisionRuntime` normalizes the
configured backend name, selects a factory from that registry, and delegates to
the factory's requested or legacy compatibility backend. The legacy FSM
compatibility facades remain but delegate through the factory path. This
removes the branch-set-specific runtime dependency without expanding backend
support: only `legacy_fsm` is registered and supported, and behavior-tree, VLM,
LLM, or learned backends remain fail-fast parked scope.

Phase 9.44 introduces `PrimitiveTokenRuntimeState` in
`testbed/planner/primitive_token_state.py`. The state owner centralizes reset
defaults and mutable storage for dig-cut tokens, dig-depth-profile tokens,
return target/relocate/start-envelope tokens, token source/fallback/prior-bound
fields, return start-envelope prior flags, and pending next-dig token/raw/
exemplar fields. `PrimitiveResetLifecycleService` now creates one fresh token
state during reset and applies it before legacy private token field names so
those compatibility names write into the same state object through property
setters. `PrimitiveTokenRuntimeCoordinator`, `PrimitiveDigTokenPlanningService`,
and `PrimitiveReturnTokenPlanningService` keep their existing responsibilities;
observation injection flags, cell-entry compatibility state, coverage state,
and return handoff state remain outside the token state owner.

Phase 9.45 introduces `PrimitiveReturnRuntimeState` in
`testbed/planner/primitive_return_state.py`. The state owner centralizes reset
defaults and mutable storage for the non-token return handoff/runtime cache:
return step count, return-to-dig entry error and close flag, return next-dig
event seen flag, and return start-envelope ready/error/check payload. The
state methods own the small state rules for marking/clearing the next-dig event
flag, applying start-envelope gate results, and writing entry-close results.
`PrimitiveResetLifecycleService` now creates one fresh return state during
reset and includes it in `PrimitiveResetLifecycleState`; legacy private return
field names remain property-backed compatibility facades over the same state
owner. Return handoff algorithms, direct-handoff effect sequencing,
return-target token fields, coverage state, token runtime state, and parked
`pre_dig_align`/`cell_entry` semantics remain in their existing owners.

Phase 9.46 introduces `PrimitiveCycleRuntimeState` in
`testbed/planner/primitive_cycle_state.py`. The state owner centralizes reset
defaults and mutable storage for confirmed-live 4P mainline cycle/progress
state: dump-ready and dump-done hold counters, dig progress and plateau
counters, dig-to-carry reason mirror, dig replan counters, transition timeout
and completion counters, cycle index, and dump-start deposited-mass baseline.
The state methods own small counter/setter rules such as complete-return
transition count/index advancement, transition-timeout increments, dig replan
increments, dig progress reset, and atomic dig progress update. Reset creates
one fresh cycle state and applies it before legacy private cycle/progress field
names, so capability provider, effect applier, tick finalization, and report
paths keep their old compatibility names while resolving to the same state
owner. Phase 9.56 extends the same owner with
`PrimitiveCycleRuntimeState.to_report_status()` and
`PrimitiveCycleReportStatus.dig_progress_debug_fields()`, so debug
dig-progress fields, rollout summary transition/cycle fields, and tick
finalization cycle inputs all use one live cycle/progress projection. Active
skill, switch reason, previous action, token state, return state, coverage
state, parked `pre_dig_align`, `cell_entry` compatibility state, dig-progress
update algorithms, and public report schema assembly remain outside this owner.

Phase 9.47 introduces `PrimitiveScriptedBootstrapRuntimeState` and
`PrimitiveScriptedBootstrapRuntimeService` in
`testbed/planner/primitive_scripted_bootstrap.py`. The state owner centralizes
the scripted bootstrap step, hold, and timeout counters, and reset creates one
fresh scripted bootstrap state before applying the legacy scripted counter
field names. The service owns the scripted-qpos runtime rules that used to live
in the policy shell: `scripted_qpos` enabled detection, target-qpos and qvel
hold gating, max-step timeout completion, missing-target error reporting, and
clipped float32 PD action generation with optional action signs. Non-scripted
bootstrap end modes, residual `pre_dig_align` action/state, `cell_entry`
compatibility/report state, token/return/cycle/coverage state owners,
BT/VLM/LLM backend support, and removed 5P runtime remain unchanged.

Phase 9.57 extends `PrimitiveScriptedBootstrapRuntimeState` in
`testbed/planner/primitive_scripted_bootstrap.py` with `to_report_status()` and
adds `PrimitiveScriptedBootstrapReportStatus.debug_fields()`. Live
scripted-bootstrap report/status projection now lives with the scripted
bootstrap runtime owner, while
`PrimitivePlannerACTPolicy._debug_report_scripted_bootstrap_fields()` remains a
thin facade and `_rollout_summary_inputs()` reuses the same status projection
for `scripted_bootstrap_timeout_count`. This phase does not change scripted
bootstrap readiness, timeout, target-reached, PD action algorithms, reset
timing, public debug key names, rollout summary key names, backend fail-fast
behavior, or removed 5P runtime status.

Phase 9.48 introduces `PrimitiveExecutionRuntimeState` in
`testbed/planner/primitive_execution_state.py`. The state owner centralizes
execution lifecycle metadata: active/current skill name, switch reason,
previous action, and latest compact debug state. Reset creates one fresh
execution state with the selected initial skill and `switch_reason="reset"`,
then the runtime kernel still finalizes the initial debug state in the existing
order. The policy's `_skill_name`, `_switch_reason`, `_prev_action`, and
`_debug_state` names remain compatibility facades over the same state owner.
This phase does not change branch order, reason strings, policy reset timing,
previous-action copy semantics, report schemas, backend fail-fast behavior,
token injection flags, residual `pre_dig_align`, `cell_entry`, or removed 5P
runtime status.

Phase 9.49 introduces `PrimitiveObservationInjectionRuntimeState` in
`testbed/planner/primitive_observation.py`. The state owner centralizes the six
per-observation token injected compatibility flags while preserving the
existing immutable `PrimitiveTokenInjectionState` returned by
`PrimitivePolicyObservationAssembler`. Reset creates one fresh observation
injection state; `_clear_policy_observation_injected_flags()` delegates to
`clear()`, and `_apply_policy_observation_assembly(...)` delegates to apply the
assembler result. The policy's old `_cell_entry_token_injected`,
`_dig_cut_token_injected`, `_dig_depth_profile_token_injected`,
`_return_target_token_injected`, `_return_relocate_token_injected`, and
`_return_start_envelope_token_injected` names remain compatibility facades over
the same owner. This phase does not change token schema, token dimensions,
injected observation key names, provider call order, copy/no-copy behavior,
public report schemas, `cell_entry`, `pre_dig_align`, backend fail-fast
behavior, or removed 5P runtime status.

Phase 9.50 introduces `PrimitiveCellEntryCompatibilityRuntimeState` in
`testbed/planner/primitive_cell_entry_state.py`. The state owner centralizes
parked cell-entry compatibility/report mutable storage: selected goal, goal
cycle id, audit result, cached token array, seen cell id, and trace list. Reset
creates one fresh cell-entry compatibility state and applies it through
`_cell_entry_state`; the old `_cell_entry_goal`,
`_cell_entry_goal_cycle_id`, `_cell_entry_audit`, `_cell_entry_tokens`,
`_cell_entry_seen_cell_id`, and `_cell_entry_trace` names remain compatibility
facades over the same owner. `_cell_entry_tokens_for_obs(...)` and
`_complete_cell_entry_dig(...)` still own the legacy compatibility algorithms in
the policy shell. This phase does not change cell-entry planner/auditor
algorithms, token dimensions, token key names, token array values, trace schema,
debug/summary/trace public schema, residual `pre_dig_align`, backend fail-fast
behavior, or removed 5P runtime status.

Phase 9.51 introduced `PrimitivePreDigAlignCompatibilityRuntimeState` in
`testbed/planner/primitive_pre_dig_align_state.py`. The state owner centralizes
parked pre-dig-align compatibility/report mutable storage: step/hold/timeout/
completed/replan counters, cached target qpos and error arrays, entry-error and
surface-depth report floats, readiness booleans, timeout handoff reason,
surface-guard trigger state, and surface-guard count. Reset creates one fresh
pre-dig-align compatibility state and applies it through
`_pre_dig_align_state`; the old `_pre_dig_align_*` names remain compatibility
facades over the same owner for disabled public schema compatibility. The
runtime algorithms that once used those counters and readiness fields were
removed in Phase 9.92; pre-dig-align is not promoted into the mainline backend,
and disabled debug/summary/trace public schema compatibility remains.

Phase 9.79 extends that parked owner with
`PrimitivePreDigAlignReportConfig` and `PrimitivePreDigAlignReportStatus`. The
public debug and rollout-summary projection for pre-dig-align now lives with the
parked compatibility owner rather than as a policy-owned report dictionary and
summary field cluster. After Phase 9.92 this report/status boundary is retained
only as disabled public schema compatibility; the action/readiness/replan
runtime implementation has been removed.

Phase 9.52 extends `CoverageReportService` in
`testbed/planner/primitive_coverage_reports.py` with
`CoverageDebugReportInputs` and `debug_fields(...)`. Coverage debug-field
public schema assembly now lives in the coverage report boundary, while
`PrimitivePlannerACTPolicy._debug_report_coverage_fields()` remains a
compatibility facade that supplies explicit snapshot values. Existing
`corridor_to_debug(...)` and `decision_event(...)` behavior remains unchanged.
This phase does not change coverage selection, scoring, effect/runtime updates,
candidate generation, public debug/summary/trace schemas, token schemas,
`cell_entry`, residual `pre_dig_align`, backend fail-fast behavior, or removed
5P runtime status.

Phase 9.53 extends `PrimitiveCellEntryCompatibilityRuntimeState` in
`testbed/planner/primitive_cell_entry_state.py` with `debug_fields(...)`.
Parked cell-entry public debug-field schema projection now lives with the
compatibility/report state owner, while
`PrimitivePlannerACTPolicy._debug_report_cell_entry_fields()` remains the thin
facade used by current debug report assembly. This phase does not change
cell-entry token generation, token dimensions, planner/auditor algorithms,
trace mutation, reset semantics, public debug key names, fallback values,
coverage reporting, residual `pre_dig_align`, backend fail-fast behavior, or
removed 5P runtime status. It is recorded as tail cleanup for an existing
parked compatibility/report owner, not as permission to continue shrinking work
into protective micro-slices.

Phase 9.54 extends `PrimitiveTokenRuntimeState` in
`testbed/planner/primitive_token_state.py` with `to_token_status(...)`. Live
token-status projection now lives with the token runtime owner, while
`PrimitivePlannerACTPolicy._token_status_for_debug_report()` remains the thin
facade that supplies explicit external facts: cell-entry enablement,
observation-injection flags, dig-depth-profile source, and dig-depth-profile
required state. The owner method uses central token dimension constants and
delegates copy/freeze behavior to `TokenStatus.from_inputs(...)`. This phase
does not change token debug key names, token values, source/fallback fields,
injected flags, dimensions, observation assembly provider order, token planning
services/coordinators, coverage behavior, parked `cell_entry`, residual
`pre_dig_align`, backend fail-fast behavior, or removed 5P runtime status.

Phase 9.60 extends `PrimitiveTokenRuntimeState` with
`to_report_status(...)` and adds `PrimitiveTokenReportStatus`. Live
token/pending/dig-cut report metadata now lives with the token runtime owner:
pending next-dig cycle/corridor ids, dig-cut injected status, planner mode,
prior id/path, token source, prior-window flag, and fallback reason.
`PrimitivePlannerACTPolicy._debug_report_pending_fields()`,
`_debug_report_dig_cut_fields()`, `_rollout_summary_inputs()`, and
`_planner_trace_inputs()` now reuse that status while remaining thin explicit-
facts assemblers for config and observation-injection facts. This phase does
not change token dimensions, token contract text/version, source/fallback
string semantics, injected observation key names, public debug/summary/trace
key names or type projection, token planning algorithms/coordinators,
dig-depth-profile planning, return token planning, coverage algorithms,
backend facts/fail-fast behavior, reset timing, policy observation provider
order, parked `cell_entry`, residual `pre_dig_align`, or removed 5P runtime
status.

Phase 9.61 narrows the token runtime port boundary in
`testbed/planner/primitive_token_runtime.py`. `PrimitiveTokenRuntimePorts` now
carries one focused `PrimitiveTokenRuntimeState` owner for dig-cut,
dig-depth-profile, return-target, return-relocate, return-start-envelope, and
pending next-dig token storage. `PrimitiveTokenRuntimeCoordinator` reads and
writes that owner directly, while current-skill/config gates, token-builder
algorithms, return-relocate planning, coverage terminal-stop status, and
coverage exemplar facts remain explicit external ports. The policy's
`_primitive_token_runtime_ports()` now passes
`self._primitive_token_runtime_state()` and no longer assembles token-state
getter/setter callbacks for this runtime boundary. This phase does not change
token dimensions, schema keys, source/fallback strings, branch order, reset
timing, backend fail-fast behavior, parked `cell_entry`, residual
`pre_dig_align`, or removed 5P runtime status.

Phase 9.62 narrows the coverage selection runtime port boundary in
`testbed/planner/primitive_coverage.py`. `CoverageSelectionRuntimePorts` now
carries one focused `CoverageRuntimeState` owner for coverage corridor lists,
candidate scores, active/last-selected corridor ids, and all-depleted checks.
`CoverageSelectionRuntimeCoordinator` reads and writes that owner directly,
while dig-cut prior/config facts, candidate builder, selection service,
selection facts, recent-row reference, reopen/terminal hooks, and
decision-event recording remain explicit external ports. The policy's
`_coverage_selection_runtime_ports()` now passes
`self._coverage_runtime_state()` and no longer assembles selection-runtime
coverage-state getter/setter callbacks. This phase does not change coverage
candidate construction, scoring/selection algorithms, first-dig gate behavior,
recent-row penalty, state-exemplar scoring, terminal-stop reason strings,
decision trace payload schema, token/return/cycle/scripted-bootstrap/
execution behavior, backend fail-fast behavior, parked `cell_entry`, residual
`pre_dig_align`, or removed 5P runtime status.

Phase 9.63 narrows the coverage effect runtime port boundary in
`testbed/planner/primitive_coverage_updates.py`. `CoverageEffectRuntimePorts`
now carries one focused `CoverageRuntimeState` owner for live coverage effect
runtime storage: current payload gain, last payload/deposit, completed dump
count, global low-productivity streak, rejected exemplar ids, pass index,
active corridor id, terminal-stop state, active corridor lookup, corridor list,
and all-depleted checks. `CoverageEffectRuntimeCoordinator` reads and writes
that owner directly, while coverage mode/config, update/runtime services,
mass/facts builders, decision-event recording, and low-productivity thresholds
remain explicit external ports. The policy's
`_coverage_effect_runtime_ports()` now passes `self._coverage_runtime_state()`
and no longer assembles coverage-state getter/setter callbacks for this effect
runtime boundary. This phase does not change coverage candidate
construction/scoring/selection algorithms, first-dig gate behavior, recent-row
penalty, state-exemplar scoring, terminal-stop reason strings, decision trace
payload schema, event ordering, report/debug/summary/trace schemas,
token/return/cycle/scripted-bootstrap/execution behavior, backend fail-fast
behavior, parked `cell_entry`, residual `pre_dig_align`, or removed 5P runtime
status.

Phase 9.85 narrows this boundary further by moving coverage effect fact
projection into `CoverageEffectFactService`. `CoverageEffectRuntimePorts` now
carries `CoverageRuntimeState`, `PrimitiveCycleRuntimeState`, a typed
`PrimitiveObservationFacts` provider, a remaining-depth provider, and a
corridor-attempt-limit provider instead of policy-built `mass_in_bucket`,
`completion_facts`, `rejection_facts`, `reopen_facts`, and `terminal_facts`
callbacks. `CoverageEffectRuntimeCoordinator` constructs complete-dig mass,
complete-dump, rejection, reopen, and terminal-stop facts inside the coverage
effect runtime boundary while keeping update/runtime services and
decision-event recording explicit. This does not change coverage update
algorithms, terminal-stop reason strings, event ordering, report schemas,
token/return/recovery semantics, parked `pre_dig_align`, or parked
`cell_entry`.

Phase 9.86 narrows the adjacent coverage decision-event reporting boundary by
moving bucket snapshot projection into `CoverageReportService.bucket_snapshot`.
The report service now projects `CoverageBucketSnapshot` from typed
`PrimitiveObservationFacts` and centralized env-state schema indexes, including
the existing task-metric mass/deposit fallback and NaN/default behavior for
short env-state vectors. `PrimitivePlannerACTPolicy._coverage_bucket_snapshot`
is only a compatibility facade that constructs the typed observation facts and
delegates. This does not change coverage decision-event payload keys, event
ordering, coverage selection/effect/update algorithms, debug/summary/trace
schemas, token/return/recovery semantics, parked `pre_dig_align`, or parked
`cell_entry`.

Phase 9.88 narrows the coverage planning fact-source boundary by routing
`CoveragePlanningFactService` env-state and bucket-pose reads through typed
`PrimitiveObservationFacts`. The service now receives an `observation_facts`
provider instead of separate policy-built `env_state` and
`bucket_tip_dig_area_pose` callbacks. Entry distance uses
`PrimitiveObservationFacts.bucket_tip_dig_area_pose()`, preserving bucket-tip
preferred and bucket dig-area fallback behavior. State-exemplar planning,
removed-depth grid extraction, and remaining-depth projection read
`facts.env_state`. The `first_dig_qpos_delta` callback intentionally remains
explicit because it still reaches parked/residual pre-dig-align target
material; this phase does not promote or modify that parked path.
It does not change token/return/direct-handoff/recovery semantics or parked
path status.

Phase 9.89 narrows the bootstrap end fact-source boundary. The policy's
`_should_end_bootstrap(...)` compatibility facade still delegates to
`PrimitiveScriptedBootstrapRuntimeService` first when scripted bootstrap is
enabled, preserving scripted target/hold/timeout behavior. Non-scripted
bootstrap end now builds typed `PrimitiveObservationFacts` and uses
`BootstrapStatus.from_inputs(...).should_end` for first-qualified-dig-start,
loaded-and-clear, disabled, and unsupported-mode handling. This moves live
bootstrap fact projection out of direct policy wrapper reads without changing
branch order, thresholds, error text, reset timing, backend support, report
schemas, or parked `pre_dig_align` / `cell_entry` status.

Phase 9.90 narrows the dig-progress tick-update boundary. A new
`PrimitiveDigProgressRuntimeService` owns the live support update that runs
when a tick starts in `dig`: it reads mass through typed
`PrimitiveObservationFacts`, updates `PrimitiveCycleRuntimeState` dig-progress
counters with the existing plateau epsilon, and updates
`CoverageRuntimeState` current payload gain with the existing max(old, mass)
projection. The policy's `_update_dig_progress(...)` method remains only a
compatibility facade and port constructor. This does not change execution tick
order, branch order, plateau behavior, coverage payload max behavior, public
report schemas, or parked `pre_dig_align` / `cell_entry` status.

Phase 9.91 narrows the boundary-event tick source. A new
`PrimitiveBoundaryEventRuntimeService` owns the live prev-action gate and
observation projection for `BoundaryDetector.update(...)`. It reads the
focused execution state owner for `prev_action`, returns `None` without calling
the detector when no previous action exists, and otherwise passes typed
`PrimitiveObservationFacts` env-state, qpos, reward phase, task successes, and
task metrics plus the previous action to the detector. The policy remains a
compatibility facade and port constructor. This does not change
`BoundaryDetector` algorithms, execution-driver tick order, prev-action copy
timing, decision facts, report schemas, or parked `pre_dig_align` /
`cell_entry` status.

Phase 9.64 narrows the active dig token planning port boundary in
`testbed/planner/primitive_dig_token_planning.py`.
`PrimitiveDigTokenPlanningPorts` now carries the focused
`PrimitiveTokenRuntimeState` and `CoverageRuntimeState` owners for pending dig
route, dig-cut, dig-depth-profile, selected corridor, payload/deposit, and
state-exemplar storage. `PrimitiveDigTokenPlanningService` reads and writes
those owners directly, while dig-cut planner mode/config, token planner
algorithms, bucket/env/deposit observation facts, coverage corridor selection,
and coverage raw-field building remain explicit external ports. The policy's
`_primitive_dig_token_planning_ports()` now passes
`self._primitive_token_runtime_state()` and `self._coverage_runtime_state()`
and no longer assembles token-state or coverage-state getter/setter callbacks
for this active dig planning boundary. This phase does not change token
dimensions/order/source strings, raw-field priority, cell-id priority,
pending-return-target route semantics, dig-depth-profile planning behavior,
coverage selection/effect semantics, debug/summary/trace schema, branch order,
reason strings, backend fail-fast behavior, parked `cell_entry`, residual
`pre_dig_align`, or removed 5P runtime status.

Phase 9.84 updates this boundary so active dig token planning receives
`PrimitiveObservationFacts` through a typed provider rather than separate
`bucket_dig_area_pose`, `deposited_mass`, and `env_state` callbacks. The
service reads bucket pose, deposited mass, and env-state through that typed
facts object while keeping coverage raw-field construction and token planner
algorithms explicit.

Phase 9.65 narrows the return token planning port boundary in
`testbed/planner/primitive_return_token_planning.py`.
`PrimitiveReturnTokenPlanningPorts` now carries the focused
`PrimitiveTokenRuntimeState` and `CoverageRuntimeState` owners for return
start-envelope source/prior flags, coverage active corridor id, and corridor
lookup. `PrimitiveReturnTokenPlanningService` reads and writes those owners
directly, while return-target mode/config, return token planner algorithms,
bucket/env/qpos/qvel observation facts, coverage corridor selection, and
coverage raw-field building remain explicit external ports. The policy's
`_primitive_return_token_planning_ports()` now passes
`self._primitive_token_runtime_state()` and `self._coverage_runtime_state()`
and no longer assembles return-token-planning storage callbacks for coverage
active id/corridor lookup or return start-envelope source/prior flags. This
phase does not change return-target mode routing, coverage raw-field handoff,
corridor id/cell id fallback, return start-envelope build/apply/conditioning,
prior token/mapping/bounds helper behavior, token/raw-field copy semantics,
token dimensions/order/source strings, debug/summary/trace schema, branch
order, reason strings, policy reset timing, backend fail-fast behavior, parked
`cell_entry`, residual `pre_dig_align`, or removed 5P runtime status.

Phase 9.84 updates this boundary so return token planning receives
`PrimitiveObservationFacts` through the same typed provider rather than
separate `bucket_dig_area_pose`, `env_state`, `qpos`, and `qvel` callbacks.
The service reads bucket pose, env-state, qpos, and qvel through that typed
facts object while keeping return token planner algorithms, coverage raw-field
construction, and return start-envelope behavior unchanged.

Phase 9.66 narrows the token runtime port boundary in
`testbed/planner/primitive_token_runtime.py`. `PrimitiveTokenRuntimePorts` now
carries `CoverageRuntimeState` alongside `PrimitiveTokenRuntimeState` for the
return-to-dig pending next-dig state-exemplar handoff. The runtime coordinator
reads active state-exemplar ids, distance, and profile token from the coverage
state owner, preserves the existing profile-token copy behavior when writing
pending dig-depth-profile tokens, and clears the active exemplar through
`CoverageRuntimeState.clear_active_state_exemplar()` at the existing
`clear_dig_cut_plan()` timing. The policy's
`_primitive_token_runtime_ports()` now passes `self._coverage_runtime_state()`
and no longer assembles coverage state-exemplar getter/clear callbacks. This
phase does not change the return target plan success path, pending next-dig
token/raw/exemplar writeback values, coverage exemplar profile token copy
semantics, clear dig-cut plan timing, pending invalidation, return
fallback-zero path, token dimensions/order/source strings,
debug/summary/trace schema, branch order, reason strings, policy reset timing,
backend fail-fast behavior, parked `cell_entry`, residual `pre_dig_align`, or
removed 5P runtime status.

Phase 9.55 extends `PrimitiveReturnRuntimeState` in
`testbed/planner/primitive_return_state.py` with `to_report_status(...)` and
adds `PrimitiveReturnReportStatus.debug_fields()`. Live return report/status
projection now lives with the return runtime owner, while
`PrimitivePlannerACTPolicy._debug_report_return_fields()` remains a thin
facade and `_rollout_summary_inputs()` reuses the same status projection for
return summary fields. The projection consumes explicit start-envelope config
facts plus return runtime owner values. This phase does not change public debug
key names, rollout summary fields, bool/string/float projection, `NaN`
behavior, checks dict copy projection, return handoff algorithms, start-
envelope gate evaluation, backend fail-fast behavior, or removed 5P runtime
status.

Phase 9.56 extends `PrimitiveCycleRuntimeState` in
`testbed/planner/primitive_cycle_state.py` with `to_report_status()` and adds
`PrimitiveCycleReportStatus.dig_progress_debug_fields()`. Live cycle/progress
report and finalization projection now lives with the cycle runtime owner,
while `PrimitivePlannerACTPolicy._debug_report_dig_progress_fields()` remains a
thin facade and `_rollout_summary_inputs()` / `_tick_finalization_inputs()`
reuse the same status projection for transition counts, dump-hold counts,
cycle index, and dig replan counters. This phase does not change public
dig-progress debug keys, rollout summary values, tick finalization input
values, dig-progress update algorithms, skill lifecycle behavior, reset
behavior, backend fail-fast behavior, or removed 5P runtime status.

Phase 9.12 extracts return-to-dig start-envelope readiness into
`ReturnStartEnvelopeGateService` in
`testbed/planner/primitive_return_handoff.py`. The service owns the former
nested gate/check algorithm from `_return_to_dig_start_envelope_ready(...)`,
including permissive disabled/missing/invalid token compatibility, spatial
long/short checks, local-depth and plane-depth prior modes, contact-required
payloads, qpos envelope checks, NaN handling, and `max_error` calculation. The
policy shell now constructs `ReturnStartEnvelopeGateConfig` and
`ReturnStartEnvelopeGateInputs`, delegates to the service, and writes
`_return_to_dig_start_envelope_ready_state`,
`_return_to_dig_start_envelope_error`, and
`_return_to_dig_start_envelope_checks` from the result. Direct-handoff
transition side effects, skill switching, return counters, token planning, and
return-target planning remain outside the service.

Phase 9.13 extracts the effect-side return/direct-handoff transition chain into
`ReturnDirectHandoffEffectService` in
`testbed/planner/primitive_return_handoff.py`. The requested-effect applier
still applies `SetReturnOrDirectHandoffEffect` through shell ports, but the
policy shell no longer owns the ordered cascade itself. Instead, it builds
`ReturnDirectHandoffEffectPorts` and delegates `_set_return_or_direct_handoff`
and the compatibility `_try_return_direct_handoff_at_current_obs` wrapper to
the service. The service preserves the old order: set active skill to `return`,
stop when the return target planner or direct handoff is disabled, ensure the
return target plan before readiness checks, pass the same `handoff_ready` value
into direct-handoff readiness, complete the return transition before computing
the next skill, then use `return_to_{next_skill}_start_envelope_ready`.
Start-envelope gate calculation, token planning, coverage metrics, 5P,
`pre_dig_align` internals, and `cell_entry` compatibility remain in their
existing owners.

Phase 9.76 moves return-to-dig handoff readiness into
`ReturnHandoffReadinessService` in the same return handoff module. The readiness
service owns the existing entry-target precedence, entry-error calculation from
observation facts, entry-close cache writeback, start-envelope gate input
assembly, gate-result cache writeback, `handoff_ready`, and direct-handoff
mass/config gate. `ReturnDirectHandoffEffectService` now consumes that readiness
service instead of policy-built `return_to_dig_handoff_ready` and
`return_to_dig_direct_handoff_ready` callbacks. The policy shell keeps the old
private method names as compatibility facades and still supplies explicit
return-target planning plus prior bounds/mapping algorithm ports. Return
start-envelope token planning, effect ordering, completion timing, reason
strings, token/report schemas, backend support, `pre_dig_align`, `cell_entry`,
and removed 5P runtime status remain unchanged.

Phase 9.77 closes the return-refresh edge from the capability provider to that
same readiness owner. `PrimitiveFSMCapabilityProviderPorts` now carries
`ReturnHandoffReadinessService` directly instead of a
`refresh_return_handoff_state` policy callback. `refresh_return_transition_state`
calls `handoff_ready(obs)` on the readiness service, preserving the same return
owner cache refresh behavior without routing through a policy-built callback.
The policy shell also drops the duplicate `_return_to_dig_shallow_guard_ready`
helper after confirming the shallow-guard calculation already lives in
`ReturnTransitionStatus.from_inputs(...)`. Return readiness semantics, direct
handoff effect ordering, reason strings, token planning, `pre_dig_align`,
`cell_entry`, and backend support remain unchanged.

Phase 9.78 narrows the report snapshot boundary for coverage. The large policy
shell no longer owns coverage debug/summary/trace snapshot assembly; it passes
`CoverageRuntimeState`, explicit `CoverageReportConfig`, and
`CoverageSelectionService` into `CoverageReportService`. This keeps the public
report schema in report builders/services without promoting coverage report
state into decision backends or a generic planner blackboard.

Phase 9.14 extracts low-level policy observation/token injection assembly into
`PrimitivePolicyObservationAssembler` in
`testbed/planner/primitive_observation.py`. The assembler owns the old
`_policy_obs(...)` assembly contract: call token providers in order
goal -> cell-entry compatibility -> dig-cut -> dig-depth-profile ->
return-target -> return-relocate -> return-start-envelope; return the original
observation object when every provider returns `None`; otherwise create
`dict(obs)` and inject the existing keys (`goal_tokens`, `cell_entry_tokens`,
`dig_cut_tokens`, `dig_depth_profile_tokens_v1`, `return_target_tokens`,
`return_relocate_tokens_v1`, `return_start_envelope_tokens_v1`). It also
computes the legacy injected-flag state, with no goal injected flag and
`cell_entry` kept compatibility-only. Phase 9.49 moves mutable injected-flag
storage into `PrimitiveObservationInjectionRuntimeState`; the policy shell now
clears stale injected flags through that owner before assembly, delegates to the
assembler, and applies the
resulting compatibility fields. Token planning algorithms, token dimensions,
token source/fallback strings, debug/summary schemas, and golden-window
contracts remain unchanged.

Phase 9.15 extracts public `debug_state()` dict assembly into
`PrimitiveDebugReportBuilder` in `testbed/planner/primitive_debug_report.py`.
`PrimitiveDebugReportInputs` carries an explicit tick snapshot, token status,
and report sections for return gates, pending dig-cut state, dig-cut planner
metadata, coverage, cell-entry compatibility, scripted bootstrap, dig progress,
and residual pre-dig diagnostics. The builder owns final public key layout,
section merge order, and plain debug-payload projection. Token arrays/source
fields are produced through `TokenStatus.to_debug_fields()`, while pending and
dig-cut metadata now come from `PrimitiveTokenReportStatus` before reaching the
builder. The policy shell now keeps only thin snapshot helpers and does not
assemble the final debug dict inline. `rollout_summary()`, `planner_trace()`,
per-tick `_make_debug_state(...)`, token planning, coverage/runtime updates,
`cell_entry` compatibility behavior, and `pre_dig_align` residual behavior
remain unchanged.

Phase 9.16 extracts public `rollout_summary()` dict assembly into
`PrimitiveRolloutSummaryBuilder` in
`testbed/planner/primitive_rollout_summary.py`.
`PrimitiveRolloutSummaryInputs` carries an explicit summary snapshot for
transition counters, final primitive skill/cycle, return gate metrics,
token/pending/dig-cut report status, coverage status, scripted bootstrap
timeout, residual pre-dig counters, and dig replan counters. The builder owns
final public summary key layout, `bool`-like integer projection, `None` to
`NaN` fallback projection, and compact compatibility/report fields for
`cell_entry` and `pre_dig_align`. The policy shell now keeps only a thin
`_rollout_summary_inputs()` snapshot helper and delegates final summary
assembly. `planner_trace()`, public debug-state assembly, token planning,
coverage/runtime updates, `cell_entry` compatibility behavior, and
`pre_dig_align` residual behavior remain unchanged.

Phase 9.17 extracts public `planner_trace()` dict assembly into
`PrimitivePlannerTraceBuilder` in
`testbed/planner/primitive_planner_trace.py`.
`PrimitivePlannerTraceInputs` carries explicit trace values for cell-entry
trace, token report status for dig-cut planner metadata, return-target planner
enablement, coverage config/status fields, preprojected coverage corridor
payloads, coverage decision trace, and terminal-stop status. The builder owns
final public trace key layout, token contract version/string fields, coverage
trace/count fields, terminal-stop fields, and top-level list projection. The
policy shell now keeps only `_planner_trace_inputs()` plus coverage-corridor
preprojection through the existing `_coverage_corridor_to_debug(...)` facade.
Coverage decision trace recording, coverage corridor projection service
internals, public
`debug_state()` and `rollout_summary()` assembly, token planning,
coverage/runtime updates, `cell_entry` compatibility behavior, and
`pre_dig_align` residual behavior remain unchanged.

Phase 9.18 extracts primitive action dispatch and active low-level policy
selection into `PrimitiveActionDispatchService` in
`testbed/planner/primitive_action_dispatch.py`.
`PrimitiveActionDispatchPorts` exposes only typed shell values/callables:
current skill, action dimension, low-level policy handles and ordering,
first-dig/bootstrap optional policies, cycle/coverage counters, policy
observation assembly, scripted-bootstrap action entry, and residual
pre-dig-align action entry. The service owns the dispatch sequence: scripted
bootstrap short-circuit before policy observation, pre-dig-align short-circuit
before policy observation, active policy selection, policy observation
assembly, low-level policy predict, and `float32` reshape to `action_dim`.
The 4P policy methods `_dispatch_tick_action()`, `_active_policy()`,
`_all_policies()`, and `_first_dig_policy_active()` are now thin service
wrappers. The 5P compatibility subclass keeps its legacy transition overrides;
it only supplies compatible action-dispatch ports so inherited dispatch does
not reinterpret 5P skill names as 4P skills. Reset lifecycle, `_set_skill()`
mutation timing, policy observation/token planning, scripted bootstrap action
algorithm, pre-dig-align action algorithm, branch ordering, reporting schemas,
and low-level ACT outputs remain unchanged.

Phase 9.19 extracts primitive tick finalization into
`PrimitiveTickFinalizationService` in
`testbed/planner/primitive_tick_finalization.py`.
`PrimitiveTickFinalizationInputs` carries the explicit compact debug-state
snapshot: active skill, skill-id map, switch reason, checkpoint paths,
first-dig policy activity, transition-mode skill names, timeout/completion
flags, transition counters, dump hold counters, cycle index, and 5P
compatibility hold counters when present. The service owns previous-action copy
semantics, the `return_to_dig_` transition-completed prefix rule,
checkpoint-key selection including
`first_dig`, hybrid-mode selection, and construction of
`PrimitivePlannerDebugState`. The 4P policy methods
`_record_tick_previous_action()`, `_transition_completed_after_tick_dispatch()`,
`_make_debug_state()`, and `_finalize_tick_debug_state()` are now thin
service-backed wrappers. The 5P compatibility subclass no longer duplicates
compact debug-state assembly; it only supplies 5P-specific finalization inputs
such as skill ids, return-only transition mode, approach/dump-release hold
counters, and the 5P checkpoint mapping. Public debug-state report assembly,
rollout summary assembly, planner trace assembly, reset lifecycle,
`_set_skill()` mutation timing, branch ordering, token planning, coverage
runtime updates, and low-level ACT dispatch remain unchanged.

Phase 9.20 extracts coverage effect-side runtime coordination into
`CoverageEffectRuntimeCoordinator` in
`testbed/planner/primitive_coverage_updates.py`.
`CoverageEffectRuntimePorts` exposes typed shell state accessors,
update/runtime services, facts providers, coverage state writeback callbacks,
terminal-stop setters, and decision-event recording. The coordinator owns the
confirmed-live sequencing for coverage requested effects: non-coverage modes
no-op; dig completion records maximum payload gain; dump completion writes
update results before recording `complete_dump`, then applies all-depleted
reopen/terminal checks, global low-productivity terminal checks, and
physics-artifact terminal checks in the old order; corridor rejection writes
rejected exemplar ids and payload/deposit state before recording
`reject_corridor`, skips terminal/reopen checks for uncounted attempts, and
otherwise applies all-depleted and global terminal checks in the old order.
Reopen-pass and terminal-stop result application and event sequencing are also
owned by the coordinator. Coverage candidate construction, scoring/selection,
corridor debug projection, report schemas, token planning, branch ordering,
and low-level action dispatch remain unchanged.

Phase 9.21 extracts coverage corridor selection runtime coordination into
`CoverageSelectionRuntimeCoordinator` in
`testbed/planner/primitive_coverage.py`. `CoverageSelectionRuntimePorts`
exposes typed shell accessors for the dig-cut prior, corridor list storage,
candidate builder, selection service, selection facts, recent-row reference,
all-depleted/reopen/terminal hooks, candidate-score writeback, selected-id
writeback, and decision-event recording. The coordinator owns the
confirmed-live selection sequencing: `select_next_corridor(...)` checks the
prior, ensures candidates, validates non-empty candidates, calls
`select_corridor(...)`, then writes active and last-selected corridor ids;
`ensure_corridors()` preserves the existing no-op/build behavior; and
`select_corridor(...)` preserves the old all-depleted pre-reopen, service
selection, candidate-score/event emission, and post-select terminal-stop order.
Coverage candidate construction, scoring, first-dig gate facts, state exemplar
matching, raw-field/token planning, report schemas, branch ordering, and
low-level action dispatch remain unchanged.

Phase 9.22 extracts coverage mutable runtime storage into
`CoverageRuntimeState` in `testbed/planner/primitive_coverage_state.py`. The
state owner stores corridors, active/last-selected ids, payload/deposit
counters, completed dump and low-productivity counters, pass and terminal-stop
state, candidate scores, decision trace, rejected exemplar ids, and active
state-exemplar payload. It exposes the common helper behavior that was
previously scattered across the policy shell: corridor lookup, active corridor,
depleted count, all-depleted status, selected-id/counter/terminal writeback, and
state-exemplar/rejected-id updates. `PrimitivePlannerACTPolicy` now creates a
fresh `CoverageRuntimeState` on reset and keeps old `_coverage_*` private names
as property-backed compatibility facades; selection/effect runtime ports point
at the same state owner rather than separate policy fields. This is a focused
coverage runtime state boundary, not a generic blackboard. Candidate
construction, selection scoring, effect runtime sequencing, coverage report
payloads, decision trace schema, terminal-stop reasons, branch order, and
low-level action dispatch remain unchanged.

Phase 9.23 extracts coverage state-conditioned exemplar planning into
`CoverageStateExemplarPlanner` in
`testbed/planner/primitive_coverage_exemplars.py`. The planner owns the
confirmed-live state-exemplar algorithm: loading and validating exemplar JSON,
resolving paths relative to the dig-cut prior, projecting removed-depth grids,
computing exemplar distances with target-cell weighting, handling non-finite
distance weights with the old uniform fallback, filtering rejected exemplar ids
only when that leaves a non-empty candidate set, and building weighted dig-cut
raw fields plus optional weighted dig-depth-profile tokens. The policy shell
keeps old private diagnostic method names as service-backed facades and remains
responsible for `update_state=True` writeback into `CoverageRuntimeState` and
active `CoverageCorridorState` debug fields. Coverage candidate construction,
selection scoring, effect runtime sequencing, token contracts, report payload
schemas, branch order, and low-level action dispatch remain unchanged.

Phase 9.24 extracts the primitive execution driver into
`PrimitiveExecutionDriver` in `testbed/planner/primitive_execution.py`. The
driver owns the public tick/predict route and the ordering previously held by
the free `run_primitive_tick()` function: boundary update, switch-reason reset,
dig-progress update for `dig`, decision, requested-effect application, return
timeout accounting, action dispatch, previous-action recording,
transition-completed check, and debug finalization. The policy shell now exposes
typed `PrimitiveExecutionPorts` and delegates `predict()` to the driver. The old
`run_primitive_tick()` function remains as a compatibility facade over the
driver rather than the source of truth. Decision branches, requested-effect
families, action dispatch semantics, token/report schemas, branch order, and
low-level ACT output contracts remain unchanged.

Phase 9.25 extracts the primitive decision runtime into
`PrimitiveDecisionRuntime` in
`testbed/planner/primitive_decision_runtime.py`. The runtime owns backend-name
normalization, supported-backend validation, requested-decision routing, and
legacy compatibility-decision routing. The only supported backend is the
confirmed-live `legacy_fsm`; unsupported backend names fail fast with an
explicit contract error and do not construct legacy branches or call broad
legacy fallback paths. The policy's `_decide_tick()` and `_maybe_switch_skill()`
now delegate through this runtime, while legacy FSM requested/compatibility
backend accessors remain compatibility facades over the same runtime.

Phase 9.26 introduces the primitive decision context packet in
`PrimitiveDecisionContext` in
`testbed/planner/primitive_decision_context.py`. The packet preserves the tick
`obs` identity, boundary-event identity, and `PrimitiveTickPreparation` identity,
and exposes read-only convenience fields for backend and branch dispatch. The
runtime and legacy FSM backend objects now route through `decide_context(...)`
as their source of truth; scatter-argument `decide_tick(...)` methods remain
only as compatibility facades for the execution driver and existing diagnostics.
Requested order, compatibility order, unsupported-backend fail-fast behavior,
and all branch semantics remain unchanged.

Phase 9.27 introduces the primitive decision capabilities port in
`testbed/planner/primitive_decision_capabilities.py`. The capabilities object
maps a shared `PrimitiveDecisionContext` into legacy-FSM decision facts:
current skill/reason, normalized bootstrap decision status, dig/carry/dump/
return transition statuses, and the explicitly residual pre-dig-align
already-applied handler. `LegacyFSMBranchPorts` no longer exposes the mainline
callback bag (`current_skill_name`, bootstrap gates, or transition-status
methods) directly; it carries skill-name constants plus one capabilities
object. This is a backend-facing context/capabilities boundary for the default
legacy FSM path, not a claim that alternate behavior-tree or VLM/LLM backends
are implemented or fully pure-readiness-compatible.

Phase 9.28 extracts 4P primitive skill switch lifecycle sequencing into
`PrimitiveSkillLifecycleService` in
`testbed/planner/primitive_skill_lifecycle.py`. The service owns the
same-skill no-op, skill/reason write order, active-policy reset timing including
the residual `pre_dig_align` exception, target-specific counter/mirror resets,
dig coverage payload reset, and dig-cut plan clear timing. The policy shell
builds typed `PrimitiveSkillLifecyclePorts` and keeps `_set_skill(...)` as a
thin service-backed facade used by `RequestedEffectApplier`. Since Phase 9.67,
those ports carry the focused execution, cycle, return, pre-dig-align
compatibility, and coverage state owners directly, leaving only active-policy
reset and dig-cut plan clearing as explicit external action ports. The 5P
`_set_skill()` override remains parked legacy compatibility and is not migrated
in this phase.

Phase 9.29 extracts primitive dig/return token runtime sequencing into
`PrimitiveTokenRuntimeCoordinator` in
`testbed/planner/primitive_token_runtime.py`. The coordinator owns the
confirmed-live lifecycle around existing token algorithms: disabled/no-token
gates, cached terminal-stop dig tokens, active-skill and bootstrap-policy
eligibility, dig hold-token rebuild suppression, synchronized dig-cut and
dig-depth-profile plan writes, return-target eligibility and hold-cycle
suppression, return relocate token writes, return-start-envelope token routing,
success and fallback writeback for pending next-dig plans, and exact clear/
invalidate reset semantics. The policy shell keeps the old private token
runtime method names as service-backed facades; `cell_entry` token injection
remains compatibility material outside this coordinator.

Phase 9.30 extracts return token planning orchestration into
`PrimitiveReturnTokenPlanningService` in
`testbed/planner/primitive_return_token_planning.py`. The service owns
return-target planner mode routing, the coverage corridor selection/raw-field
handoff used for operator-prior coverage and sweep-belief return plans,
return-start-envelope token build/apply/conditioning, token source and
prior-bound writeback, prior token/mapping/bounds helper routing, and copy
semantics for returned token/raw-field payloads. `PrimitivePlannerACTPolicy`
keeps the old private return token planning methods as service-backed facades,
while active dig token planning, token algorithm classes, coverage algorithms,
return handoff gate/effect services, `cell_entry`, `pre_dig_align`, 5P, and
alternate BT/VLM/LLM backend behavior remain outside this slice.

Phase 9.31 extracts active dig token planning orchestration into
`PrimitiveDigTokenPlanningService` in
`testbed/planner/primitive_dig_token_planning.py`. The service owns pending
return-target dig plan application, conservative/operator-prior/
operator-prior-coverage and sweep-belief routing, fallback conservative
behavior, coverage raw-field handoff, dig-cut plan source/fallback/in-prior
writeback, dig-depth-profile plan/apply/error writeback, live/prior helper
routing, raw-field priority, cell-id priority, and copy semantics for returned
token/raw-field payloads. `PrimitivePlannerACTPolicy` keeps the old private
dig token planning method names as service-backed compatibility facades, while
return token planning, token runtime sequencing, token algorithm classes,
coverage algorithms, return handoff gate/effect services, `cell_entry`,
`pre_dig_align`, 5P, and alternate BT/VLM/LLM backend behavior remain outside
this slice.

Phase 9.32 extracts 4P reset lifecycle sequencing into
`PrimitiveResetLifecycleService` in
`testbed/planner/primitive_reset_lifecycle.py`. The service owns low-level
policy reset order, boundary-detector reset, bootstrap/pre-dig initial-skill
selection, switch reason and previous-action defaults, hold/counter mirrors,
pre-dig cached diagnostics, cell-entry compatibility defaults, dig/return token
and pending-plan defaults, injected-token flags, token source/fallback strings,
and fresh `CoverageRuntimeState` creation. `PrimitivePlannerACTPolicy.reset()`
is now a thin service-backed facade that applies the reset state and initializes
the compact debug state. The 5P runtime planner compatibility path has been
removed by explicit user cleanup decision; old behavior is retained only in git
history, while historical data-slicing and experiment docs can remain as
history.

Phase 9.73 narrows primitive action dispatch state reads through focused owners.
`PrimitiveActionDispatchPorts` now carries
`PrimitiveExecutionRuntimeState`, `PrimitiveCycleRuntimeState`, and
`CoverageRuntimeState` directly. `PrimitiveActionDispatchService` reads active
skill, first-dig cycle index, and completed dump count from those owners instead
of through policy-built state callbacks. The policy shell still supplies
low-level policy handles and ordering, policy observation assembly, scripted
bootstrap action generation, and the residual pre-dig-align action callback as
explicit ports. This keeps action dispatch as a focused live runtime service
without promoting `pre_dig_align` into mainline backend architecture. Action
dispatch semantics, action shape/dtype, first-dig gating, scripted bootstrap,
pre-dig-align action behavior, backend support, token/report schemas, and
removed 5P runtime status remain unchanged.

Phase 9.75 narrows the transition facts / geometry gate boundary. The
dig-exit overshoot input to `DigTransitionStatus` is no longer supplied through
a policy callback. `PrimitiveObservationFacts` now projects bucket dig-area and
bucket-tip dig-area poses from `env_state`, and
`PrimitiveFSMCapabilityProvider` computes the overshoot from those observation
facts plus `CoverageRuntimeState.active_corridor()`. The large policy shell
also drops the duplicated migrated dig/carry/dump helper implementations that
were already represented by `PrimitiveObservationFacts`,
`PrimitiveFSMCapabilityProvider`, and the transition status dataclasses. Return
start-envelope gates, residual `pre_dig_align`, parked `cell_entry`, backend
branch order, reason strings, thresholds, token/report schemas, and removed 5P
runtime status remain unchanged.

Phase 9.76 narrows the return handoff readiness boundary. The policy shell no
longer owns the entry-target/error/start-envelope readiness implementation; it
only assembles typed owner/config ports and retains old private facades.
`ReturnHandoffReadinessService` consumes focused execution, cycle, return, token,
and coverage state owners plus explicit prior-bound/mapping ports. This keeps
live return readiness in the return handoff module without promoting residual
`pre_dig_align` or parked `cell_entry` material into mainline backend
architecture.

Phase 9.77 narrows the capability-provider refresh boundary. Return transition
cache refresh now reaches the same focused readiness owner directly, rather than
via a policy callback. This keeps the return transition fact path aligned with
the return handoff module and removes one more migrated duplicate helper from
the large policy shell without changing the return transition status schema.

Phase 9.78 narrows the coverage report snapshot boundary. Coverage report
projection now starts from `CoverageRuntimeState` plus explicit coverage report
config and selection-service facts. This removes the hand-built coverage report
snapshot cluster from the large policy shell while preserving report schema,
fallback values, list-copy behavior, and coverage runtime algorithms.

Phase 9.79 narrows the parked pre-dig-align report projection boundary.
Pre-dig-align public debug and summary values now project through
`PrimitivePreDigAlignReportStatus` from the compatibility state owner plus
explicit report config facts. This keeps pre-dig-align parked as compatibility
report/action material and avoids turning it into a backend fact source,
behavior-tree node, token contract, or mainline runtime responsibility.

Phase 9.80 narrows the parked cell-entry report projection boundary. Cell-entry
public debug, summary, and planner-trace values now project through
`PrimitiveCellEntryReportStatus` from the compatibility state owner plus
explicit report config facts. This keeps cell-entry parked as compatibility/
report material and avoids turning it into a token contract, backend fact
source, behavior-tree node, or mainline runtime responsibility.

Phase 9.82 narrows the coverage planning fact-source boundary. Coverage
selection facts, coverage raw-field fallback/clamp projection,
state-conditioned exemplar plan/writeback projection, exemplar distance/id
projection, removed-depth grid delegation, weighted exemplar helper delegation,
and remaining-depth projection now live in `CoveragePlanningFactService`.
`PrimitivePlannerACTPolicy` remains the adapter that supplies explicit
config/state/observation callables and preserves old private facades. This
phase does not change coverage scoring/selection, state-exemplar scoring,
raw-field priority/copy semantics, token dimensions/order/source strings,
debug/summary/trace schemas, `pre_dig_align`, `cell_entry`, backend fail-fast
behavior, or removed 5P runtime status.

Phase 9.92 removes the parked pre-dig-align runtime execution path after the
explicit checkpoint/review gate. The cleanup deletes the residual legacy-FSM
pre-dig branch route, action-dispatch pre-dig port, reset/bootstrap/return
handoff next-skill selection to pre-dig, failed-dig pre-dig replan path, and
policy-owned pre-dig readiness/target/timeout/action algorithms. Disabled
public debug/summary/report fields remain projected through
`PrimitivePreDigAlignCompatibilityRuntimeState` with disabled/zero/default
values. Enabled `pre_dig_align` config now fails fast in adapter normalization,
and active v2.4 eval configs use disabled compatibility blocks. This is a
deletion cleanup, not a migration into backend facts, token contracts,
behavior-tree nodes, VLM packets, or mainline runtime architecture. It does not
touch parked `cell_entry` and does not change backend maturity: default legacy
FSM backendified with focused services / shared backend decision
input/facts/factory; BT/VLM/LLM remain unsupported fail-fast.

### Stage 4: Expand Effect Families From Evidence

Each new family must be justified by a confirmed-live rollout behavior and a
focused parity test. The expansion order should follow the architecture plan,
not callback convenience.

## How This Governs Return Handoff And Other Coupled Paths

Return direct handoff, coverage terminal stop, and pre-dig parking must be
analyzed under this contract. The former 5P runtime compatibility path was
cleanup-approved and removed in Phase 9.32; only historical records remain.

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
