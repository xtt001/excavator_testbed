# Planner Function Core-Degree Classification

Status: **historical cleanup management note** for
`PrimitivePlannerACTPolicy` glue classification.

This note records how the cleanup program classifies remaining policy-shell
functions and mappings. It does not replace the architecture plan or rollout
evidence log.

## Degrees

- Target anchor for the next phase: `PrimitivePlannerACTPolicy` should converge
  to the external communication/API adapter surface only. Internal runtime
  state, decision/effect handling, report/input assembly, token, coverage, and
  transition work should live behind stable owner/runtime/service boundaries.
  This note classifies glue for that migration; it does not approve broad
  phase-2 movement by itself.

- A: core shell responsibilities. Keep in `PrimitivePlannerACTPolicy` when the
  code owns public adapter lifecycle, active shell state, policy dispatch order,
  or the orchestration order for focused owners/services.
- B: necessary owner/service welds. Keep small direct connectors such as
  focused owner accessors, report/status projections, and explicit port
  assembly when they are the shortest stable path between the shell and the
  focused owner.
- C: private method compatibility facades. Keep temporarily when tests,
  diagnostics, or bridge code still need the method name, but do not add new
  behavior behind it.
- D: old-name private property compatibility facades and duplicate writeback
  mappings. Remove by owner cluster after callers move to the focused owner.
- E: public schema shells. Keep deprecated/disabled public debug, summary, and
  trace schema surfaces unless an explicit removal slice approves deletion.
- F: residual helpers. Audit before cleanup; classify as live owner/service
  weld, public schema shell, compatibility, test-only, or dead glue before
  removal.

## Accepted Cleanup Status

- Observation-injection D-property cleanup is accepted: the policy no longer
  exposes old private injected-flag property facades, and reset writes only the
  `_observation_injection_state` owner.
- Cycle/progress D-property cleanup is accepted by this slice: cycle/progress
  public/report values stay owned by `PrimitiveCycleRuntimeState`; the policy no
  longer exposes old private cycle/progress property facades, and reset writes
  only the `_cycle_state` owner.
- Return-runtime D-property cleanup is accepted by this slice: non-token return
  handoff/runtime cache values stay owned by `PrimitiveReturnRuntimeState`; the
  policy no longer exposes old private return runtime property facades, and
  reset writes only the `_return_state` owner for those values.
- Token-runtime D-property cleanup is accepted by this slice: dig/return token
  arrays, sources/fallbacks, start-envelope prior-bound flags, and pending
  next-dig token/raw/exemplar fields stay owned by
  `PrimitiveTokenRuntimeState`; the policy no longer exposes old private
  token/pending property facades, and reset writes only the `_token_state`
  owner for those values.
- Coverage-runtime D-property cleanup is accepted by this slice: corridor
  containers, selected ids, payload/deposit counters, pass/terminal state,
  candidate scores, decision trace, and state-exemplar payload stay owned by
  `CoverageRuntimeState`; the policy no longer exposes old private coverage
  property facades.
- Scripted-bootstrap counter D-property cleanup is accepted by this slice:
  scripted bootstrap step, hold, and timeout counters stay owned by
  `PrimitiveScriptedBootstrapRuntimeState`; the policy no longer exposes old
  private scripted-bootstrap counter property facades, and reset writes only the
  `_scripted_bootstrap_state` owner for those counters.
- Report input assembly extraction is accepted by this slice:
  `PrimitiveReportRuntime` owns construction of `PrimitiveDebugReportInputs`,
  `PrimitiveRolloutSummaryInputs`, and `PrimitivePlannerTraceInputs`. The
  later report/status composition cleanup adds `PrimitiveReportCompositionRuntime`
  as the owner of `PrimitiveReportRuntimePorts` construction plus token,
  `cell_entry`, and `pre_dig_align` report-status projection. The policy keeps
  public `debug_state()`, `rollout_summary()`, and `planner_trace()` plus a
  typed report-composition weld. Old private report-runtime and report/status
  composition wrappers have been removed after runtime-kernel callbacks and
  focused tests moved to focused report contracts.
- Token observation/runtime composition extraction is accepted by this slice:
  `PrimitiveTokenObservationRuntime` owns policy-observation assembly,
  observation-injection clear/apply timing, assembler-port construction, and
  token-runtime coordinator port construction. The old private policy wrappers
  for observation assembly, token-provider sequencing, plan ensure hooks, and
  token-runtime coordinator/ports access have been removed after production
  ports and focused tests moved to the focused runtime contract. The policy
  keeps typed token-observation runtime ports/runtime factory as B owner welds.
- Token planning service composition extraction is accepted by this slice:
  `PrimitiveTokenPlanningRuntime` owns dig/return token planning service
  construction, dig/return planning ports construction, and token-planning
  helper delegation. The old private policy wrappers for active dig token
  planning, dig-depth-profile helpers, return-target planning,
  return-start-envelope helpers, live-pose raw fields, and operator-prior token
  helpers have been removed after production ports and focused tests moved to
  the focused runtime/service contracts. The policy keeps typed token-planning
  runtime ports/runtime factory as B owner welds.
- Coverage selection/fact composition extraction is accepted by this slice:
  `PrimitiveCoverageSelectionRuntime` owns coverage selection runtime ports,
  coverage selection config/service construction, and coverage planning fact
  config/service construction. The old private policy compatibility wrappers
  for coverage selection/fact access are retired; production and focused tests
  use the focused runtime/service contracts directly. The policy keeps only
  typed coverage-selection runtime ports/runtime factory as B owner welds.
- Coverage scoring/exemplar helper wrapper retirement is accepted by this
  slice: candidate/scoring, first-dig, state-exemplar, and coverage state-owner
  writeback helpers now use `PrimitiveCoverageSelectionRuntime`,
  `CoverageSelectionService`, `CoveragePlanningFactService`,
  `CoverageCandidateBuilder`, or `CoverageRuntimeState` directly. The old
  private policy compatibility helper names for that cluster are retired.
- Skill/recovery token-plan wrapper retirement is accepted by this slice:
  dig-cut plan clear/invalidate actions are routed through
  `PrimitiveTokenObservationRuntime` and its token runtime coordinator, and
  failed-dig restart/stop handling is routed through
  `PrimitiveDigRecoveryService`. The old private policy wrappers for that
  cluster are retired while `_set_skill(...)` remains a shell lifecycle weld.
- Coverage effect/update composition extraction is accepted by this slice:
  `PrimitiveCoverageEffectRuntime` owns coverage update/runtime config
  construction, update/runtime service construction, and effect runtime
  port/coordinator construction. Old private coverage effect/update helper
  wrappers were removed after callers/tests moved to the focused runtime
  contract; the policy keeps typed coverage-effect runtime ports and the
  focused runtime factory as owner welds.
- Coverage effect owner-state setter wrapper retirement is accepted by this
  slice: mutable coverage payload, dump, low-productivity, pass, active
  corridor, rejected-exemplar, and terminal-stop state writes use
  `CoverageRuntimeState` owner methods or focused coverage runtimes directly.
  The old private policy setter/update helper names for that cluster are
  retired.
- Cycle/return/dump transition wrapper retirement is accepted by this slice:
  dump hold/deposit writes, return next-dig marking, return transition
  completion, next-skill selection after return, and dig replan counters use
  `PrimitiveCycleRuntimeState`, `PrimitiveReturnRuntimeState`, and
  `RequestedEffectApplier` contracts directly. The old private policy
  transition wrapper names for that cluster are retired while `_set_skill(...)`
  remains a shell lifecycle weld.
- Requested-effect runtime composition cleanup is accepted by this slice:
  `PrimitiveRequestedEffectRuntime` owns `RequestedEffectApplierPorts`
  construction from explicit typed state/service/runtime inputs. The policy
  shell keeps only `_primitive_requested_effect_runtime*` as a typed weld and
  no longer exposes `_requested_effect_applier()` or
  `_requested_effect_applier_ports()`. Tests use focused requested-effect
  runtime/applier contracts or the new policy runtime weld instead of old
  private policy wrappers.
- Return handoff readiness wrapper retirement is accepted by this slice:
  return-to-dig entry close/error/target projection, handoff readiness, direct
  handoff readiness, start-envelope gate input/result projection, and gate
  service construction use `PrimitiveReturnHandoffRuntime`,
  `ReturnHandoffReadinessService`, `ReturnStartEnvelopeGateService`,
  adapter-normalized `ReturnHandoffReadinessConfig`,
  `PrimitiveReturnRuntimeState`, and the token observation/planning runtimes
  directly. The old private policy return handoff readiness wrapper names for
  that cluster are retired; the policy keeps only a typed return-handoff runtime
  weld.
- Return direct-handoff effect wrapper retirement is accepted by this slice:
  `SetReturnOrDirectHandoffEffect` application now delegates through
  `PrimitiveReturnHandoffRuntime.apply_direct_handoff(...)`, and focused tests
  use the runtime/service/port contracts directly. The old private policy action
  wrappers for setting return, trying direct handoff, service construction,
  readiness ports/service construction, and direct-handoff effect ports are
  retired while `_set_skill(...)` remains the shell lifecycle weld.
- Coverage report/decision-event composition extraction is accepted by this
  slice: `PrimitiveCoverageReportRuntime` owns coverage report config/state/
  service composition, bucket snapshot projection, decision-event recording,
  and active/corridor report helper projection. Old private coverage report
  helper wrappers were removed after callers/tests moved to the focused runtime
  contract; the policy keeps typed coverage-report runtime ports and the
  focused runtime factory as owner welds.
- Backend-neutral facts contract consolidation is accepted by this slice:
  dig/carry/dump/return transition status reads flow through
  `PrimitiveBackendFactsSource`, `PrimitiveBackendFactsAccess`,
  `PrimitiveFSMCapabilityProvider`, and `LegacyFSMBranchPorts`. The old
  private policy `_dig/_carry/_dump/_return_transition_status_for_backend(...)`
  wrappers and the old capability/composition wrappers
  `_decision_runtime_ports()`, `_legacy_fsm_backend_factory()`,
  `_legacy_fsm_branch_ports()`, `_primitive_decision_capabilities*()`, and
  `_primitive_fsm_capability_provider*()` are retired.
- Legacy FSM backend access wrapper retirement is accepted by this slice:
  requested backend, compatibility backend, and branch-set access use
  `PrimitiveDecisionRuntime` or `LegacyFSMDecisionBackendFactory` directly.
  The old private policy `_legacy_fsm_requested_decision_backend()`,
  `_legacy_fsm_compatibility_decision_backend()`, and
  `_legacy_fsm_branch_set()` wrappers are retired while `_decision_runtime()`
  remains the policy shell's typed runtime weld.
- Generic backend factory protocol and default legacy composition boundary are
  accepted by this slice: `PrimitiveDecisionBackendFactory` exposes generic
  requested and compatibility backend protocols, while
  `LegacyFSMDecisionBackendFactoryPorts` and
  `LegacyFSMDecisionBackendFactory.from_runtime_ports(...)` own construction of
  `PrimitiveFSMCapabilityProvider`, `PrimitiveDecisionCapabilities`,
  `LegacyFSMBranchPorts`, and the concrete legacy branch-set/factory boundary.
  `PrimitiveDecisionRuntime` now owns backend-name normalization, generic
  registry selection, and decision invocation only. Test-only dependencies on
  old decision-runtime composition names were migrated to focused backend
  factory/runtime contracts instead of preserving those names.
- Contract readiness closure is evidenced by fake backend tests:
  `PrimitiveDecisionRuntime` selects any normalized backend name registered in
  `PrimitiveDecisionRuntimePorts.backend_factories` and invokes generic
  requested/compatibility backend protocols without depending on
  `PrimitivePlannerACTPolicy`. Generic contract surfaces are
  `PrimitiveDecisionBackend`, `PrimitiveCompatibilityDecisionBackend`,
  `PrimitiveDecisionBackendFactory`, `PrimitiveDecisionRuntimePorts`,
  `PrimitiveDecisionRuntimeConfig`, and `PrimitiveDecisionRuntime`. Default
  concrete adapter surfaces remain the `LegacyFSM*` factory, branch, and
  branch-set classes in `primitive/decision/backends/legacy_fsm.py`; removed
  policy-private wrappers and `PrimitiveDecisionRuntimeComposition*` stay
  classified as absent compatibility/test-only surfaces.
- Static FSM transition config extraction is accepted by this slice:
  `PrimitiveFSMCapabilityProviderConfig` owns static transition thresholds and
  gate knobs; `PrimitivePlannerAdapterConfigNormalizer` populates it from
  constructor-normalized public inputs; the default legacy factory boundary now
  constructs `PrimitiveFSMCapabilityProviderPorts` from that config plus
  explicit live state/service ports. The policy shell no longer imports or
  constructs `PrimitiveFSMCapabilityProviderPorts`. Object-constructed tests
  that only made post-init policy-field mutation appear important were migrated
  to focused config/provider contracts instead of preserving mutable policy
  field mirrors.
- Legacy decision bridge/facade retirement is accepted by this slice:
  requested/default decisions use `PrimitiveDecisionRuntime.decide_tick(...)`
  through `PrimitiveExecutionRuntime`; legacy compatibility decisions use
  `PrimitiveDecisionRuntime.decide_legacy_compatibility_tick(...)` plus
  requested-effect application where needed. The old private policy
  `_decide_tick()`, `_decide_tick_with_legacy_fsm()`, and
  `_maybe_switch_skill()` facades are retired while `_decision_runtime*` remains
  a typed B owner weld. Legacy-FSM-specific runtime backend accessors have also
  been retired from `PrimitiveDecisionRuntime`; focused tests use generic
  backend factory/backend accessors with the explicit backend name instead.
- Execution-driver hook/action/finalization wrapper retirement is accepted by
  this slice: execution-driver ports call
  `PrimitiveBoundaryEventRuntimeService`, `PrimitiveActionDispatchService`,
  `PrimitiveTickFinalizationService`, and `PrimitiveExecutionRuntimeState`
  directly for boundary events, action dispatch, previous-action copy,
  transition-completed checks, and debug-state writeback. The old private policy
  wrappers for tick boundary/update hooks, action dispatch, active/all-policy
  selection, first-dig policy activity, and finalization writeback are retired.
- Public runtime-kernel composition extraction is accepted by this slice:
  `PrimitivePlannerPublicRuntime` owns construction of
  `PrimitivePlannerRuntimeKernelPorts` and report builders from focused reset,
  execution, tick-finalization, and report runtimes. The old private policy
  `_runtime_kernel`, `_runtime_kernel_ports`, `_debug_report_builder`,
  `_rollout_summary_builder`, and `_planner_trace_builder` wrappers are retired.
- Report/status composition extraction is accepted by this slice:
  `PrimitiveReportCompositionRuntime` owns construction of
  `PrimitiveReportRuntimePorts` plus token, `cell_entry`, and `pre_dig_align`
  report-status projection from focused owners/runtimes. The old private policy
  `_primitive_report_runtime_ports`, `_primitive_report_runtime`,
  `_token_status_for_debug_report`, `_token_report_status`,
  `_cell_entry_report_config`, `_cell_entry_report_status`,
  `_pre_dig_align_report_config`, and `_pre_dig_align_report_status` wrappers
  are retired.
- Tick finalization runtime / return-timeout boundary cleanup is accepted by
  this slice: `PrimitiveTickFinalizationRuntime` now owns live finalization
  input snapshots, compact debug-state writeback, and return-step timeout
  accounting over typed execution/cycle/return owners. The old private policy
  `_make_debug_state(...)`, `_tick_finalization_inputs(...)`,
  `_account_return_timeout_for_tick()`, and `_tick_finalization_service()`
  wrappers are retired.
- Policy test-only / dead-candidate helper facade cleanup is accepted by this
  slice: adapter config helper tests now use
  `testbed.planner.primitive_adapter_config` directly, scripted-bootstrap target
  checks use `PrimitiveScriptedBootstrapRuntimeService`, token conversion helper
  users rely on `PrimitiveDigTokenPlanningService` /
  `PrimitiveReturnTokenPlanningService`, and coverage candidate tests use
  `CoverageCandidateBuilder` directly. The old private policy helper facades
  for this cluster are retired without changing public schemas or planner
  algorithms.
- E public schema shells remain deprecated/disabled compatibility surfaces.
  Internal dead glue may be removed when it is classified and covered by a
  bounded cleanup slice.
