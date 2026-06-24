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
- `docs/planner_package_layout_target.md`
- `docs/planner_policy_shell_target_interface.md`
- `docs/planner_responsibility_chain_migration_design.md`
- `docs/planner_responsibility_chain_migration_simulation.md`
- `docs/superpowers/specs/2026-06-25-pre-dig-align-runtime-restoration-design.md`
- `docs/planner_effect_boundary_design.md`
- `docs/planner_primitive_interface_standard.md`

Non-goals for this plan:

- no planner code migration
- no behavior-tree or VLM backend implementation
- no deletion of `cell_entry`, `pre_dig_align`, or other legacy code
- no change to thresholds, branch order, reason strings, token schemas, debug
  schema, rollout summary, policy reset timing, or default config semantics

Target anchor for the next phase: `PrimitivePlannerACTPolicy` should converge
to the external communication/API adapter surface only. Internal planner
runtime, state, decision, effect, report/input assembly, token, coverage, and
transition work should continue moving behind stable owner/runtime/service
boundaries. This anchor records the target direction; it does not start broad
phase-2 migration in this slice.

Responsibility-chain migration design now separates two decisions:
package-layout relocation decides where code belongs under
`testbed/planner/primitive/...`; responsibility-chain simulation decides which
production owner, behavior locks, old import classifications, and tests make a
future migration slice valid. Future implementation prompts should not merge
layout relocation with semantic responsibility changes unless the simulation
proves the target chain is narrow and behavior-locked.

## Current Three-Step Contract Direction

The user-confirmed contract direction for the current cleanup phase is three
large responsibility slices, not many small private-facade removals:

1. **Backend-neutral facts contract consolidation.** This is the largest
   backend-facing block and is now accepted as the first completed slice.
   `PrimitiveBackendFactsSource`, `PrimitiveBackendDecisionInputBuilder`, and
   backend facts access make legacy FSM the first consumer/adapter rather than
   the main interface concept.
2. **Decision/capability/effect composition contract cleanup.** This slice is
   accepted enough to enter contract-readiness closure. Its goal was to remove
   remaining legacy-FSM-specific names
   and policy-private composition wrappers from the backend-facing interface
   surface. Factory, registry, backend ports, capability composition, and
   requested-effect composition should read as generic backend contracts, with
   legacy FSM contained as the default concrete adapter. The accepted
   decision-runtime composition, static capability-provider config,
   return-handoff runtime composition, generic decision-runtime accessor,
   requested-effect runtime composition, generic backend factory protocol, and
   default legacy-backend factory composition slices are partial progress
   inside this second block, not separate end states. The generic runtime
   interface now exposes backend-neutral requested and compatibility backend
   protocols, and default legacy-FSM composition is contained in the concrete
   legacy backend factory boundary instead of
   `primitive/decision/runtime.py`.
3. **Contract readiness closure.** This is now represented in the current code
   and docs by fake-backend contract tests, external-backend readiness notes,
   and compatibility-surface classification. The closure proves that the
   generic decision runtime can select a registered backend factory without
   editing `PrimitivePlannerACTPolicy` main decision flow. It does not add a
   production backend plugin/config system.

Protection remains a constraint rather than the target. Private wrappers that
look important only because tests mention them must be migrated to focused
contracts or classified as compatibility/test-only material; they must not be
preserved as production architecture.

## Current Code Reality

The current worktree does not contain the earlier partially-refactored runtime
backend implementation. There is no active `testbed/planner/runtime/`,
`LegacyStateMachineBackend`, `PlannerBlackboard`, behavior-tree backend,
`primitive_config.py`, `primitive_debug.py`, or extracted coverage package in
the current code shape.

Current relevant Python files:

| File | Lines | Current role |
| --- | ---: | --- |
| `testbed/policies/hybrid/primitive_planner.py` | 1556 | public primitive policy adapter and typed owner/runtime weld shell; old owner-state D-property facades plus token/report/coverage/return-handoff, requested-effect composition, legacy FSM transition/status/backend/decision, default legacy backend factory composition, execution hook/action, tick-finalization/return-timeout, test-only helper, execution-composition, public-runtime-kernel, and report/status composition facade clusters removed |
| `testbed/planner/primitive/config/adapter.py` | 1355 | public adapter config normalizer, legacy policy-field update payload assembly, static FSM capability-provider config, static return-handoff readiness config, and opt-in pre-dig-align enabled config normalization |
| `testbed/planner/primitive/shell/runtime_kernel.py` | 146 | public runtime-kernel route plus public-runtime composition owner for reset, predict, and reports |
| `testbed/planner/primitive/execution/boundary_event.py` | 53 | live boundary-event tick source over focused execution state, boundary detector, and typed observation facts |
| `testbed/planner/primitive/decision/input.py` | 85 | per-tick backend decision input builder carrying context, backend facts access, and explicit compatibility actions through ordered branches |
| `testbed/planner/primitive/decision/backends/legacy_fsm.py` | 1046 | generic requested/compatibility backend protocols, legacy FSM branch set including opt-in active pre-dig-align handling, requested/compatibility orders, per-branch decisions, and concrete legacy FSM backend factory composition consuming typed runtime ports and backend facts source |
| `testbed/planner/primitive/decision/runtime.py` | 156 | backend-name normalization, generic backend factory/backend accessors, unsupported-backend fail-fast, and backend factory registry selection for primitive decision runtime |
| `testbed/planner/primitive/facts/backend.py` | 282 | backend-facing facts source/ports plus lazy read-only facts access for bootstrap and dig/carry/dump/return transition views |
| `testbed/planner/primitive/facts/decision.py` | 258 | backend-neutral common decision facts packet plus lazy dig/carry/dump/return transition facts views |
| `testbed/planner/primitive/decision/contracts.py` | 601 | primitive decision result/effect contracts and effect-contract validation; old `primitive_decision.py` remains only as a public-compat re-export facade |
| `testbed/planner/primitive/decision/context.py` | 42 | primitive decision context packet for tick observation, boundary event, and preparation identity; old `primitive_decision_context.py` remains only as a cross-module-compat re-export facade |
| `testbed/planner/primitive/facts/capabilities.py` | 1027 | read-only observation facts plus bootstrap/dig/carry/dump/return transition status projections and dump-ready geometry predicates |
| `testbed/planner/primitive/decision/backends/legacy_capability_provider.py` | 328 | legacy FSM transition-status provider over focused cycle/coverage/return owners, observation facts, and return handoff readiness service |
| `testbed/planner/primitive/decision/capabilities.py` | 262 | compatibility facade over backend facts source plus explicit compatibility actions for older focused diagnostics |
| `testbed/planner/primitive/execution/state.py` | 49 | mutable execution lifecycle state owner for active skill, switch reason, previous action, and latest debug state |
| `testbed/planner/primitive/execution/pre_dig_align.py` | 529 | opt-in pre-dig-align runtime config, state, ports, target/readiness/surface/timeout/action algorithms, and live counter mutation owner |
| `testbed/planner/primitive/execution/reset_lifecycle.py` | 146 | reset lifecycle state and initial-skill selection, including opt-in pre-dig-align reset state and bootstrap precedence |
| `testbed/planner/primitive/facts/observation.py` | 181 | policy observation assembler plus mutable per-observation injected-flag runtime state owner |
| `testbed/planner/primitive/compatibility/cell_entry.py` | 137 | parked cell-entry compatibility/report runtime state owner, reset defaults, and debug/summary/trace report projection |
| `testbed/planner/primitive/compatibility/pre_dig_align.py` | 210 | schema-neutral pre-dig-align report-status projection helpers retained for disabled/default compatibility while live runtime state is owned in execution |
| `testbed/planner/primitive/report/runtime.py` | 430 | public report/status composition runtime plus debug, rollout summary, planner trace input assembly, and live pre-dig-align report-status projection |
| `testbed/planner/primitive/token/tokens.py` | 916 | goal, dig-cut, dig-depth-profile, return-target, return-relocate, and return-start-envelope token planner classes |
| `testbed/planner/primitive/token/factory.py` | 137 | token planner factory config and focused construction owner for goal/dig/return token planners |
| `testbed/planner/primitive/token/state.py` | 195 | mutable dig/return token runtime state owner, reset defaults, live token-status projection, and token report metadata projection |
| `testbed/planner/primitive/token/status.py` | 205 | immutable token status vector/debug projection records |
| `testbed/planner/primitive/token/runtime.py` | 255 | dig/return token runtime sequencing over focused token and coverage state owners plus explicit external config/algorithm ports |
| `testbed/planner/primitive/token/observation_runtime.py` | 191 | token observation composition runtime that owns policy observation assembly, observation-injection clear/apply timing, assembler ports, and token runtime ports |
| `testbed/planner/primitive/token/planning_runtime.py` | 275 | token planning service composition runtime that owns dig/return token planning ports and service construction |
| `testbed/planner/primitive/token/dig_planning.py` | 354 | active dig token planning orchestration over focused token and coverage state owners plus explicit external config/algorithm ports and typed observation facts |
| `testbed/planner/primitive/execution/dig_progress.py` | 63 | live per-dig tick progress and coverage current-payload update boundary over focused cycle/coverage state owners plus typed observation facts |
| `testbed/planner/primitive/execution/dig_recovery.py` | 196 | failed-dig/restart recovery orchestration over focused execution/cycle/return/coverage/token owners plus explicit external algorithm/action ports, typed observation metric facts, and opt-in pre-dig-align restart/replan ports |
| `testbed/planner/primitive/effects/return_handoff.py` | 563 | return direct-handoff effect service, return handoff readiness source, and return start-envelope gate over focused execution/cycle/return/token/coverage owners |
| `testbed/planner/primitive/effects/return_handoff_runtime.py` | 115 | return-handoff runtime composition boundary that builds readiness, start-envelope gate, and direct-handoff effect services from typed state/config/algorithm ports |
| `testbed/planner/primitive/token/return_planning.py` | 226 | return token planning orchestration over focused token and coverage state owners plus explicit external config/algorithm ports and typed observation facts |
| `testbed/planner/primitive/execution/return_state.py` | 141 | mutable non-token return handoff/runtime state owner, reset defaults, and live return report/status projection |
| `testbed/planner/primitive/execution/cycle_state.py` | 123 | mutable live 4P cycle/progress runtime state owner, reset defaults, and live report/finalization projection |
| `testbed/planner/primitive/execution/scripted_bootstrap.py` | 144 | scripted bootstrap runtime state, readiness checks, timeout, PD action service, and live report/status projection |
| `testbed/planner/primitive/coverage/selection.py` | 909 | coverage candidate/scoring/selection services; selection runtime sequencing consumes the focused coverage state owner directly plus explicit external ports |
| `testbed/planner/primitive/coverage/config.py` | 204 | static coverage config snapshot owner that builds report, selection, planning-fact, state-exemplar, update, and runtime config objects for coverage runtimes |
| `testbed/planner/primitive/coverage/selection_runtime.py` | 388 | coverage selection/fact composition runtime that owns dynamic selection runtime ports, coverage selection service construction, and planning-fact service construction through `PrimitiveCoverageStaticConfig` |
| `testbed/planner/primitive/coverage/state.py` | 139 | mutable coverage runtime state owner for corridors, selection ids, candidate scores, completion counters, terminal-stop state, decision trace, and state-exemplar payload |
| `testbed/planner/primitive/coverage/effect_runtime.py` | 149 | coverage effect/update composition runtime that owns service, effect-port, and coordinator construction through `PrimitiveCoverageStaticConfig` plus explicit live effect ports |
| `testbed/planner/primitive/coverage/effects.py` | 698 | coverage completion/rejection/reopen/terminal-stop effect runtime sequencing and effect fact projection over focused coverage/cycle state plus typed observation facts |
| `testbed/planner/primitive/coverage/report_runtime.py` | 176 | coverage report/decision-event composition runtime that owns report state/service composition, bucket snapshot projection, decision-event recording, and active/corridor report helper projection through `PrimitiveCoverageStaticConfig` |
| `testbed/planner/primitive/coverage/reports.py` | 626 | coverage report config, coverage corridor debug, coverage decision-event bucket snapshot, and coverage debug/trace/summary projection from focused runtime state |
| `testbed/planner/primitive/effects/requested.py` | 234 | requested-effect runtime composition plus requested-effect application over focused cycle/return owners, explicit external action ports, return-handoff runtime, coverage/dig recovery runtimes, and typed observation metric facts |
| `testbed/planner/primitive/coverage/facts.py` | 332 | coverage planning fact-source owner for selection facts, raw-field projection, state-conditioned exemplar projection/writeback, remaining-depth facts, and typed observation fact access |
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

The planner started this refactor as one large class with embedded subdomains.
The table below preserves the migration-origin responsibility map. Current line
ranges are no longer exact after the accepted cleanup slices; when a row names
old private helper methods, the later Phase-2 notes below are authoritative for
whether those names still exist or have been retired.

| Range | Responsibility | Main methods | Main state read/written | Architecture target |
| --- | --- | --- | --- | --- |
| 149-430 | public adapter construction and config normalization facade | `__init__`, `_apply_adapter_config_state` | policy handles, boundary detector, normalized adapter config state | `PrimitivePlannerAdapterConfigNormalizer` plus public adapter facade |
| 842-1120 | public runtime route and execution composition weld | `reset`, `predict`, `_primitive_runtime_kernel_runtime`, `_primitive_execution_runtime` | public-runtime ports, reset state, execution runtime ports | `PrimitivePlannerPublicRuntime` plus `PrimitiveExecutionRuntime` / `PrimitiveExecutionDriver` |
| 1121-1590 | public reporting facades | `debug_state`, `rollout_summary`, `planner_trace`, `_primitive_report_composition_runtime` | debug state, token flags, coverage fields, summary counters | `PrimitiveReportCompositionRuntime` / `PrimitiveReportRuntime` plus report builders called through public runtime kernel |
| 1550-1819 | historical 4P FSM branch order | legacy FSM backend branches and requested-effect applier; old `_maybe_switch_skill` policy facade retired | active skill, boundary event, counters, coverage completion/reject, pending plans | legacy FSM parity backend after execution template exists |
| 1820-1954 | skill mutation and restart effects | `_set_skill`, `_restart_*`, failed-dig stop/restart | active skill, reset timing, hold counters, dig-cut clear/invalidate, terminal stop | kernel-owned effect application |
| 1955-2353 | bootstrap and pre-dig config/report welds | `_should_end_bootstrap`, `_pre_dig_align_report_*` | bootstrap config, pre-dig opt-in config/report facts | bootstrap mainline status; pre-dig-align opt-in runtime config and public schema compatibility |
| 2361-3187 | gate and observation facts | `_update_dig_progress`, `_dig_to_carry_ready`, `_dump_ready`, `_return_to_dig_*`, geometry helpers | mass, deposit, qpos/qvel, env_state, boundary profile, hold counters | capability port status records |
| 3193-3350 | policy observation and token injection | historical `_policy_obs` / token-provider wrappers; now `PrimitiveTokenObservationRuntime` welds | token flags, token arrays, active skill, return planner state | policy observation assembler plus token-observation runtime |
| 3351-3627 | active dig token planning | `_ensure_dig_cut_plan_for_cycle`, depth-profile builders, raw fields | dig-cut tokens, depth-profile tokens, fallback/source fields | token planning service |
| 3628-3914 | return-target and envelope planning | `_build_next_dig_cut_plan_for_return`, `_build_return_start_envelope_tokens_for_obs`, envelope priors | pending next-dig state, return tokens, coverage active corridor | return planning service |
| 3915-4058 | config/value helpers and operator prior token builders | normalizers, prior lookup, raw-field checks | prior JSON, raw fields, token ranges | data/config helper modules after source-of-truth check |
| 4059-5159 | coverage candidate construction and selection | historical selection/scoring/exemplar wrappers; now `PrimitiveCoverageSelectionRuntime` welds | coverage corridors, candidate scores, active corridor, decision trace | coverage planning service plus selection/fact runtime |
| 5160-5636 | coverage completion, rejection, terminal-stop diagnostics | `_complete_coverage_dig`, `_complete_coverage_dump`, `_reject_active_coverage_corridor`, `_request_coverage_terminal_stop` | coverage belief, attempts, payload/deposit, terminal-stop state | coverage runtime service plus kernel effects |
| 5637-5818 | plan invalidation, config validation, prior helpers | `_clear_dig_cut_plan`, `_invalidate_pending_dig_cut_plan`, `_load_dig_cut_prior`, `_prior_percentile` | token plan ids, pending plans, prior file content | token/config helper modules |
| 5819-5940 | removed cell-entry primitive runtime region | cell-entry pose/cell-id helpers retained only where still referenced; `_cell_entry_tokens_for_obs` and `_complete_cell_entry_dig` removed | disabled cell-entry report/schema compatibility | no primitive-planner token injection or completion runtime |
| 5941-6075 | goal tokens, action dispatch service wiring, debug-state construction | `PrimitiveTokenPlannerFactory`, `_action_dispatch_service`, `_make_debug_state` | goal sequence, active skill, policy handles, debug fields | token factory, dispatch service, report/finalization boundary |
| removed | 5P runtime planner | removed `PrimitivePlannerACT5PPolicy` subclass | old 5P approach/dump-release runtime path retained only in git history | cleanup-approved removed runtime path |

## Evidence-Based Retention Matrix

The current baseline report uses the selected current-mainline successful
`aggregate_tx24` rollout packet:

- event_count: 75902
- evidence_packet_count: 3
- dead_candidate_min_packets: 1
- resolved config has `policy.pre_dig_align.enabled=false`
- resolved config has no `policy.cell_entry` / `cell_entry_enabled` setting
- `dig_low_dim_keys=[qpos, qvel, dig_cut_tokens]`, not `cell_entry_tokens`
- rollout summary has `cell_entry_enabled=0`,
  `pre_dig_align_enabled=0`, `pre_dig_align_completed_count=0`

This selected current-mainline evidence does not claim `pre_dig_align` was
never useful. Repo-wide historical scan found 187 successful summaries among
281 scanned `runs/**/rollout_*_summary.json` files; 15 successful summaries had
`pre_dig_align_enabled=1` and 14 had completed pre-dig-align steps. The current
architecture classification is that return-start-envelope / return-to-dig
readiness supersedes that runtime route for the selected mainline primitive
planner.

| Capability | Evidence classification | Retention | Current owner | Architecture placement |
| --- | --- | --- | --- | --- |
| `execution.predict_tick` | confirmed-live | retain-and-migrate | `predict` | execution kernel |
| `fsm.skill_switch` | confirmed-live | retain-and-migrate | `PrimitiveDecisionRuntime` / `RequestedEffectApplier` / `_set_skill` | legacy FSM backend after kernel exists |
| `action.dispatch` | confirmed-live | retain-and-migrate | `predict` / `PrimitiveActionDispatchService` | kernel-owned dispatch facade |
| `token.goal` | confirmed-live | retain-and-migrate | `PrimitiveTokenPlannerFactory` / `PrimitiveTokenObservationRuntime` | token provider used by observation assembler |
| `token.dig_cut` | confirmed-live | retain-and-migrate | `_ensure_dig_cut_plan_for_cycle` | token planning service |
| `token.dig_depth_profile` | confirmed-live | retain-and-migrate | `_dig_depth_profile_tokens_for_obs` | token planning service |
| `token.return_target` | confirmed-live | retain-and-migrate | `_ensure_return_target_plan_for_cycle` | return planning service |
| `token.return_relocate` | confirmed-live | retain-and-migrate | `_return_relocate_tokens_for_obs` | return planning service |
| `token.return_start_envelope` | confirmed-live | retain-and-migrate | `_return_start_envelope_tokens_for_obs` | return-envelope service |
| `metric.dig_progress` | support-live | retain-and-migrate | `_update_dig_progress` | capability status fact |
| `gate.dig_to_carry` | confirmed-live | retain-and-migrate | `LegacyFSMDigBranch` through decision runtime/facts | capability status plus legacy FSM branch |
| `gate.carry_to_dump` | confirmed-live | retain-and-migrate | `LegacyFSMCarryBranch` through decision runtime/facts | capability status plus legacy FSM branch |
| `gate.dump_to_return` | confirmed-live | retain-and-migrate | `LegacyFSMDumpBranch` through decision runtime/facts | capability status plus legacy FSM branch |
| `gate.return_to_dig` | confirmed-live | retain-and-migrate | `LegacyFSMReturnBranch` through decision runtime/facts | capability status plus legacy FSM branch |
| `coverage.corridor` | confirmed-live | retain-and-migrate | coverage helpers | coverage planning/runtime service |
| `debug.debug_state` | report-only | retain-report-boundary | `debug_state` / `_make_debug_state` | reporting boundary |
| `report.rollout_summary` | report-only | retain-report-boundary | `rollout_summary` | reporting boundary |
| `trace.planner_trace` | report-only | retain-report-boundary | `planner_trace` | reporting boundary |
| `policy.public_adapter` | compatibility | retain-compatibility | `PrimitivePlannerACTPolicy` | public adapter |
| `compat.5p_policy` | compatibility-cleanup | removed-runtime-cleanup | git history only | cleanup-approved removed runtime path |
| `token.cell_entry` | removed primitive-runtime path | disabled-schema-and-data-compatibility | `PrimitiveCellEntryCompatibilityRuntimeState` plus historical data/HDF5 support | no primitive planner token injection |
| `gate.pre_dig_align` | user-approved opt-in runtime capability | restored-runtime | `PrimitivePreDigAlignRuntimeService`, legacy-FSM active branch, action dispatch, reset/report/recovery/return-handoff ports | opt-in primitive runtime; not default mainline and not BT/VLM/LLM/plugin routing |

Post-restoration Unity smoke evidence on 2026-06-25 confirms the restored
runtime is reachable but does not claim behavioral success. Enabled
`pre_dig_align` reached final skill `pre_dig_align` with live counters
(`completed=8`, `replan=9`, `timeout=0`) and stopped for
`low_productivity_consecutive` at 1200 steps with `max_bucket_mass=0.0`.
The default-disabled smoke kept `pre_dig_align_enabled=0`, final skill `dig`,
and the current disabled low-productivity stop shape at 926 steps.

## Target Architecture

The target boundary is:

```text
PrimitivePlannerACTPolicy
  -> PrimitivePlannerRuntimeKernel
      -> PrimitiveCapabilityPort
      -> PrimitiveDecisionBackend
      -> PrimitiveDecisionResult
      -> PlannerEffect application
      -> action dispatch and reporting
```

The current ideal-vs-current interface standard for this boundary is
`docs/planner_primitive_interface_standard.md`. Use that document when choosing
implementation slices after Phase 9.33B; it distinguishes the target interface
from the current legacy-FSM-backendified implementation and must not be read as
a claim that alternate behavior-tree, VLM, or LLM backends are already
swappable.

Current status after the Phase-2 public runtime-kernel composition cleanup:
`PrimitivePlannerPublicRuntime` owns construction of
`PrimitivePlannerRuntimeKernelPorts` from focused reset, execution,
tick-finalization, and report runtimes plus explicit shell debug-state
writeback. `PrimitivePlannerRuntimeKernel` still owns the public route
(`reset`, `predict`, `debug_state`, `rollout_summary`, and `planner_trace`).
`PrimitivePlannerACTPolicy` keeps public methods plus a typed public-runtime
weld, but the old `_runtime_kernel`, `_runtime_kernel_ports`, and report-builder
wrapper methods are retired.

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
- keep cleanup-approved 5P runtime removal explicit; old branch/git history
  preserves historical behavior

### Execution Driver / Runtime Kernel

Candidate files: `testbed/planner/primitive/shell/runtime_kernel.py` and
`testbed/planner/primitive/execution/runtime.py`.

The original execution-kernel target has now split into two concrete owners:
`PrimitivePlannerRuntimeKernel` owns public runtime routing, while
`PrimitiveExecutionRuntime` owns execution-driver composition and
`PrimitiveExecutionDriver` owns one-tick execution ordering. Future work should
extend those owners rather than introducing a second kernel name.

Conceptual execution-driver methods:

```python
class PrimitiveExecutionDriver:
    def run_tick(self, obs: Mapping[str, object]) -> PrimitiveTickResult: ...
    def predict(self, obs: Mapping[str, object]) -> np.ndarray: ...
```

Execution/effect-boundary owned effects:

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

The backend may request these effects. Only the execution route and
shell-side requested-effect applier may apply them.

### Capability Port

Candidate file: `testbed/planner/primitive/facts/capabilities.py`.

The capability port is a read-only interface over typed facts. It must not be a
one-method-per-private-method facade.

Initial status records:

| Status record | Current source methods | Used by |
| --- | --- | --- |
| `PrimitiveObservationFacts` | `_env_state`, `_mass_in_bucket`, `_deposited_mass`, `_target_geometry` | all gates and diagnostics |
| `BootstrapStatus` | `_should_end_bootstrap`, `_scripted_bootstrap_enabled`, `PrimitiveScriptedBootstrapRuntimeService.target_reached(...)` | legacy FSM |
| `DigTransitionStatus` | `_update_dig_progress`, `_dig_exit_guard_ready`, `_dig_bad_replan_ready`, `_dig_to_carry_ready` | legacy FSM and future BT |
| `CarryTransitionStatus` | `_carry_release_safety_done`, `_dump_ready`, boundary-event facts | legacy FSM and future BT |
| `DumpTransitionStatus` | `_dump_done`, dump boundary event facts | legacy FSM and future BT |
| `ReturnTransitionStatus` | `ReturnHandoffReadinessService`, `ReturnTransitionStatus.from_inputs(...)` | legacy FSM and future BT |
| `CoverageStatus` | `_coverage_active_corridor`, `_coverage_candidate_scores`, terminal-stop fields | coverage-aware decisions and reporting |
| `TokenStatus` | token source/injected/fallback fields | reporting, VLM packet, parity checks |

Legacy-only status:

| Status record | Current source methods | Placement |
| --- | --- | --- |
| `LegacyPreDigAlignStatus` | `_pre_dig_align_*` | legacy parking, not default mainline backend |
| `LegacyCellEntryStatus` | `_cell_entry_*` | legacy diagnostic parking, not default token contract |

### Decision Backend

Current contract file: `testbed/planner/primitive/decision/contracts.py`.
The old `testbed/planner/primitive_decision.py` path is only a thin
public-compat re-export facade.

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
- coverage debug fields are projected by `CoverageReportService` from explicit
  snapshot inputs
- rollout summary keeps current aggregate fields stable
- planner trace owns structured evidence/debug payloads
- report-only fields can read kernel state but must not drive backend decisions

## Legacy Parking Catalog

Parking means the code is retained but kept out of the mainline architecture.
Parked code must not be used as a justification for new mainline services.

| Path | Evidence | Current code owner | Parking owner | Allowed use | Not allowed |
| --- | --- | --- | --- | --- | --- |
| `token.cell_entry` | absent from successful rollout; `cell_entry_enabled=0`; no active primitive-planner `cell_entry_tokens` low-dim key | `PrimitiveCellEntryCompatibilityRuntimeState`, historical `testbed/planner/cell_entry.py`, data/HDF5/training support | removed primitive runtime plus disabled schema/data compatibility | historical data/checkpoint compatibility and disabled public report fields | primitive-planner token injection, default token contract, new backend fact, VLM decision packet |
| `gate.pre_dig_align` | user re-approved restoration based on historical successful/high-payload enabled YuLong v2.4.5 qc6 evidence and current disabled-config validation failure | restored focused runtime plus `PrimitivePreDigAlignCompatibilityRuntimeState` report projection helper | `PrimitivePreDigAlignRuntimeService` in execution lane plus legacy-FSM/action/recovery/return/reset/report welds | explicit opt-in primitive runtime and live public report projection | default mainline requirement, behavior-tree node, VLM effect, plugin route, or `cell_entry`/5P restoration |
| removed `PrimitivePlannerACT5PPolicy` runtime path | user-approved cleanup, not mainline evidence | git history only | removed runtime path | historical comparison from old branches | source of default 4P architecture |

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

- create `testbed/planner/primitive/execution/runtime.py`
- add focused tests for execution-step ordering
- modify `testbed/policies/hybrid/primitive_planner.py` only as a thin bridge

Allowed behavior:

- `predict()` delegates preparation, decision call, action dispatch, and
  finalization to named steps
- at that historical slice, the old policy-private decision shell remained
  the behavior source of truth; it has since been retired in favor of
  `PrimitiveDecisionRuntime` plus requested-effect application
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

- `testbed/planner/primitive/decision/contracts.py`
- `testbed/planner/primitive_decision.py` only as the public-compat facade
- tests for `PrimitiveDecisionResult` and ordered effects

Allowed behavior:

- the historical policy-private decision shell could be wrapped temporarily to
  return `PrimitiveDecisionResult`; the old facade has since been retired
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

- `testbed/planner/primitive/token/tokens.py`
- `testbed/planner/primitive_return_planning.py`
- `testbed/planner/primitive/facts/observation.py`

Move only after the execution template and status records exist. Token schema,
token order, injected-key names, and source/fallback strings must stay fixed.

### Slice 6: Coverage Planning And Runtime Service

Purpose: extract coverage candidate construction, scoring, belief updates,
completion, rejection, and terminal-stop requests.

Candidate file:

- `testbed/planner/primitive/coverage/selection.py`
- `testbed/planner/primitive/coverage/reports.py` for coverage debug and trace
  payload projection
- `testbed/planner/primitive/coverage/effects.py` for completion/rejection
  mutation and runtime request gating once `primitive/coverage/selection.py` approaches
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

- `testbed/planner/primitive/decision/backends/legacy_fsm.py`

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
| compatibility | `PrimitivePlannerACTPolicy` constructor/config remains compatible; removed 5P runtime fails fast through explicit runtime diagnostics | every public-surface slice |
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

Current status note after Phase 9.14, superseded by the Phase 2
token-observation runtime cleanup below: policy observation/token injection
assembly moved out of the large policy shell into
`PrimitivePolicyObservationAssembler` in
`testbed/planner/primitive/facts/observation.py`. The assembler owns provider order,
injected key names, observation copy/no-copy behavior, and immutable
injected-state calculation. Phase 9.49 added
`PrimitiveObservationInjectionRuntimeState` in the same module as the mutable
owner for clear/apply/projection of the six legacy injected flags. The later
`PrimitiveTokenObservationRuntime` migration retired `_policy_obs(...)` and the
old private token-runtime wrapper names from `PrimitivePlannerACTPolicy`. Token
planning algorithms and token source/fallback/debug contracts remain in their
focused owners.

Current status note after Phase 9.15: public `debug_state()` dict assembly has
moved into `PrimitiveDebugReportBuilder` in
`testbed/planner/primitive/report/debug_report.py`. `debug_state()` now delegates to a
typed debug snapshot/report-input builder path while token debug fields come
from `TokenStatus.to_debug_fields()`. `rollout_summary()`, `planner_trace()`,
and per-tick `_make_debug_state(...)` are intentionally unchanged in this
round.

Current status note after Phase 9.16: public `rollout_summary()` dict assembly
has moved into `PrimitiveRolloutSummaryBuilder` in
`testbed/planner/primitive/report/rollout_summary.py`. `rollout_summary()` now
delegates through typed summary inputs while the builder owns public summary
key layout, bool-like `int(...)` projection, and `None` to `NaN` fallback
projection. `planner_trace()`, public `debug_state()` assembly, and per-tick
`_make_debug_state(...)` are intentionally unchanged in this round.

Current status note after Phase 9.17: public `planner_trace()` dict assembly
has moved into `PrimitivePlannerTraceBuilder` in
`testbed/planner/primitive/report/planner_trace.py`. `planner_trace()` now delegates
through typed trace inputs while the builder owns public trace key layout,
contract version/string fields, top-level trace-list projection, coverage
config/status fields, and terminal-stop fields. Coverage decision trace
recording, public `debug_state()` and `rollout_summary()` assembly, and
per-tick `_make_debug_state(...)` are intentionally unchanged in this round.

Current status note after Phase 9.18, superseded by the Phase-2 execution-chain
wrapper cleanup below: primitive action dispatch and active low-level policy
selection moved into `PrimitiveActionDispatchService` in
`testbed/planner/primitive/execution/action_dispatch.py`. The later cleanup retired
`_dispatch_tick_action()`, `_active_policy()`, `_all_policies()`, and
`_first_dig_policy_active()` from `PrimitivePlannerACTPolicy`; execution,
reset, skill lifecycle, recovery, and focused tests now call
`PrimitiveActionDispatchService` or typed dispatch ports directly. The service
owns scripted bootstrap short-circuit, first-dig policy selection, all-policy
order, policy-observation dispatch, low-level `predict(...)`, and `float32`
action reshape. Reset lifecycle, `_set_skill()` mutation timing, policy
observation assembly, scripted action algorithms, and public reporting builders
are intentionally unchanged.

Current status note after Phase 9.19, superseded by the Phase-2 execution-chain
and tick-finalization runtime cleanup below: primitive tick finalization lives in
`testbed/planner/primitive/execution/tick_finalization.py`. The service owns
previous-action copy semantics and dispatch-after transition-completed reason
prefix detection. `PrimitiveTickFinalizationRuntime` now owns live finalization
input snapshots, compact debug-state writeback, and return-step timeout
accounting over typed execution/cycle/return owners. The later cleanups retired
`_record_tick_previous_action()`,
`_transition_completed_after_tick_dispatch()`,
`_finalize_tick_debug_state()`, `_make_debug_state(...)`,
`_tick_finalization_inputs(...)`, `_account_return_timeout_for_tick()`, and
`_tick_finalization_service()` from `PrimitivePlannerACTPolicy`; execution and
runtime-kernel ports call the focused finalization boundary or execution state
owner directly. Public `debug_state()`, `rollout_summary()`,
`planner_trace()`, reset lifecycle, `_set_skill()` mutation timing, action
dispatch, branch ordering, and token/coverage/runtime semantics are
intentionally unchanged.

Current status note after Phase 9.20: coverage requested-effect runtime
sequencing has moved into `CoverageEffectRuntimeCoordinator` in
`testbed/planner/primitive/coverage/effects.py`. The coordinator owns
coverage-mode no-op gating, dig payload-gain completion, dump completion
state-write/event/reopen/terminal ordering, corridor rejection
state-write/event/reopen/terminal ordering, multi-pass reopen result
application, and terminal-stop result/event application. Coverage state storage
now lives in `CoverageRuntimeState`; the 4P policy shell builds typed ports and
keeps facts/report helper facades, while
`_complete_coverage_dig()`, `_complete_coverage_dump()`,
`_reject_active_coverage_corridor()`, `_maybe_reopen_coverage_pass()`, and
`_request_coverage_terminal_stop()` are thin coordinator-backed wrappers.
Coverage candidate construction, scoring/selection, corridor debug projection,
planner trace/summary/debug schemas, branch ordering, token planning, and
low-level ACT dispatch are intentionally unchanged in this round.

Current status note after Phase 9.21, superseded by the Phase-2 coverage
selection/fact runtime cleanup below: coverage corridor selection runtime
sequencing moved into `CoverageSelectionRuntimeCoordinator` in
`testbed/planner/primitive/coverage/selection.py`. The coordinator owns dig-cut prior and
empty-candidate checks, ensure-corridor no-op/build writeback, selection-service
invocation, candidate-score writeback, `select_corridor` decision-event
emission, all-depleted reopen/terminal sequencing, and active/last-selected
corridor id writeback. Coverage state storage now lives in
`CoverageRuntimeState`. The later `PrimitiveCoverageSelectionRuntime` cleanup
retired the old private policy coverage selection/fact wrapper names and moved
production/test callers to the runtime, focused services, or coverage owner
state directly. The subsequent scoring/exemplar helper cleanup retired old
private policy helper names for coverage state-owner writeback, candidate
construction, scoring/first-dig facts, state exemplar matching, and cell/row id
projection; focused callers use `PrimitiveCoverageSelectionRuntime`,
`CoverageSelectionService`, `CoveragePlanningFactService`,
`CoverageCandidateBuilder`, or `CoverageRuntimeState` directly. Coverage
candidate construction, scoring algorithm, first-dig
gate facts, state exemplar matching, raw-field/token planning, planner
trace/summary/debug schemas, branch ordering, and low-level ACT dispatch are
intentionally unchanged.

Current status note after Phase 9.22: coverage mutable runtime storage has moved
into `CoverageRuntimeState` in `testbed/planner/primitive/coverage/state.py`.
The state owner stores corridor lists, active/last-selected ids, payload/deposit
counters, completed-dump and low-productivity counters, pass and terminal-stop
state, candidate scores, decision trace, rejected exemplar ids, and active
state-exemplar payload. It also owns common state helper behavior such as
corridor lookup, active corridor lookup, depleted count, all-depleted status,
selected-id/counter/terminal writeback, and state-exemplar/rejected-id updates.
The 4P policy shell initializes a fresh state owner on reset, and tests and
diagnostics now mutate the owner through `_coverage_runtime_state()` instead of
old private `_coverage_*` property-backed compatibility facades. Coverage
selection and effect runtime ports now point at the same state owner rather
than independent policy fields. Coverage candidate construction, selection
scoring, effect
sequencing, decision trace schema, report schemas, branch ordering, and low-level
ACT dispatch are intentionally unchanged in this round.

Current status note after Phase 9.23: coverage state-conditioned exemplar
planning has moved into `CoverageStateExemplarPlanner` in
`testbed/planner/primitive/coverage/exemplars.py`. The planner owns exemplar
JSON loading/validation, relative path resolution against the dig-cut prior,
removed-depth grid projection, exemplar distance computation, temperature
weighting with the old uniform fallback, rejected exemplar filtering,
weighted dig-cut raw-field assembly, weighted dig-depth-profile token assembly,
and pure state-conditioned plan selection. The 4P policy shell keeps old private
method names as service-backed compatibility/diagnostic facades and performs
only `update_state=True` writeback into `CoverageRuntimeState` and active
`CoverageCorridorState` debug fields. Coverage candidate construction,
selection scoring, effect sequencing, token contracts, decision trace schema,
report schemas, branch ordering, and low-level ACT dispatch are intentionally
unchanged in this round.

Current status note after Phase 9.24: public primitive tick execution ordering
has moved into `PrimitiveExecutionDriver` in
`testbed/planner/primitive/execution/runtime.py`. The driver owns boundary update,
switch-reason reset, dig-progress update for `dig`, decision backend invocation,
requested-effect application before return-timeout accounting and action
dispatch, previous-action recording, transition-completed checks, debug
finalization, and `predict()` action extraction. `PrimitivePlannerACTPolicy`
now supplies focused services and owners to `PrimitiveExecutionRuntime`, which
builds typed `PrimitiveExecutionPorts` and returns the driver; `run_primitive_tick()`
and `PrimitiveTickCallbacks` remain compatibility facades over the same
ordering. Decision branches, requested-effect families, action dispatch,
finalization services, token/report schemas, branch ordering, and low-level ACT
output semantics are intentionally unchanged in this round.

Current status note after Phase 9.25: primitive decision backend selection has
moved into `PrimitiveDecisionRuntime` in
`testbed/planner/primitive/decision/runtime.py`. The execution runtime now calls
`PrimitiveDecisionRuntime.decide_tick(...)` directly instead of routing through a
policy-private decision bridge. The runtime owns
backend-name normalization, supported-backend validation, default
`legacy_fsm` requested decision routing, and legacy compatibility decision
routing through `PrimitiveDecisionRuntime.decide_legacy_compatibility_tick(...)`.
Unsupported backend names fail fast and do not fall back to
`LegacyFSMBackendAdapter` or broad policy-private mutation. The old
`_decide_tick()`, `_decide_tick_with_legacy_fsm()`, and `_maybe_switch_skill()`
policy-private facades are retired; public execution enters through the runtime
kernel and `PrimitiveExecutionRuntime`.
This preserves the current maturity claim: the default legacy FSM is
backendified, while behavior-tree, VLM/LLM, and other alternate backends remain
unimplemented parked scope.

Current status note after Phase 9.26: primitive decision backend input has
moved from scatter arguments into `PrimitiveDecisionContext` in
`testbed/planner/primitive/decision/context.py`. The context packet preserves
the `obs`, `boundary_event`, and `PrimitiveTickPreparation` object identities
for the tick and exposes the skill-before-decision and dig-progress flags as
read-only convenience fields. `PrimitiveDecisionRuntime`,
`LegacyFSMRequestedDecisionBackend`, `LegacyFSMCompatibilityDecisionBackend`,
`PrimitiveRequestedBranchRunner`, and the legacy FSM branch objects are now
context-driven internally; their scatter-argument `decide_tick(...)` methods
remain compatibility facades. This keeps the current maturity claim unchanged:
the default legacy FSM is backendified with a shared decision packet shape,
while behavior-tree, VLM/LLM, and other alternate backends remain unimplemented
parked scope.

Current status note after Phase 9.27: primitive decision backend facts now flow
through `PrimitiveDecisionCapabilities` in
`testbed/planner/primitive/decision/capabilities.py`. The policy builds typed
capability ports from current shell readers, bootstrap gates, the
`PrimitiveFSMCapabilityProvider`, and the explicitly residual pre-dig-align
handler; `LegacyFSMBranchPorts` is narrowed to skill-name constants plus that
capabilities object. Legacy FSM bootstrap/dig/carry/dump/return branches now
consume `PrimitiveDecisionContext + PrimitiveDecisionCapabilities` instead of
holding individual shell callback/status-provider fields. This keeps the
maturity claim at default legacy-FSM backendified with shared context and
capabilities shape; behavior-tree, VLM/LLM, and other alternate backends remain
unimplemented parked scope.

Current status note after Phase 9.28: 4P primitive skill switch lifecycle
sequencing now lives in `PrimitiveSkillLifecycleService` in
`testbed/planner/primitive/execution/skill_lifecycle.py`. The service owns the old
`_set_skill(...)` ordering for same-skill no-op, skill/reason writes,
active-policy reset timing, target-specific counters and mirrors, dig coverage
payload reset, and dig-cut plan clearing. `PrimitivePlannerACTPolicy._set_skill`
is now a thin service-backed facade over typed
`PrimitiveSkillLifecyclePorts`; requested-effect application still calls that
facade through its existing `set_skill` port. The 5P `_set_skill()` override,
`pre_dig_align` residual behavior, `cell_entry` compatibility material, and
alternate backend parked scope remain intentionally unchanged.

Current status note after Phase 9.29, superseded by the Phase 2
token-observation/runtime and skill/recovery token-plan wrapper retirements:
primitive dig/return token runtime
sequencing now lives in `PrimitiveTokenRuntimeCoordinator` in
`testbed/planner/primitive/token/runtime.py`. The old policy token-observation
facades and token-plan clear/invalidate wrappers have since been removed:
production callers use `PrimitiveTokenObservationRuntime` and its token runtime
coordinator directly through typed owner welds. The coordinator owns
disabled/active-skill/terminal-stop/hold-cycle gating,
dig-cut plus dig-depth-profile writeback, return-target success/fallback
writeback, pending next-dig plan state, copy semantics, and clear/invalidate
resets. Token planner algorithms, token dimensions/contracts, source/fallback
strings, observation injected-key assembly, `cell_entry` compatibility,
`pre_dig_align` residual behavior, 5P token behavior, and alternate backend
parked scope remain intentionally unchanged.

Current status note after Phase 9.30, superseded by the Phase 2
token-planning runtime cleanup below: return token planning orchestration moved
into `PrimitiveReturnTokenPlanningService` in
`testbed/planner/primitive/token/return_planning.py`.
`_build_next_dig_cut_plan_for_return(...)`,
`_unpack_return_target_token_plan(...)`,
`_build_return_start_envelope_tokens_for_obs(...)`,
`_apply_return_start_envelope_token_plan(...)`,
`_maybe_condition_return_start_envelope_qpos_from_relocate(...)`, and the
return start-envelope prior/cell-id helper methods were temporary
service-backed compatibility facades during that extraction. The later
`PrimitiveTokenPlanningRuntime` migration retired those old private policy
wrapper names. The service owns return-target mode routing, coverage corridor
selection and raw-field handoff, active coverage corridor writeback,
return-start-envelope build/apply/conditioning, source/prior-bound flag
writeback, prior token/mapping/bounds routing, and token/raw-field copy
semantics. Active dig token planning, token algorithm classes, coverage
selection/scoring/exemplar algorithms, return handoff gate/effect services,
`cell_entry`, `pre_dig_align`, 5P token behavior, and alternate backend parked
scope remain intentionally unchanged.

Current status note after the policy test-only / dead-candidate helper facade
cleanup: remaining policy-private adapter/config helper facades, prior-loading
facades, scripted-bootstrap target-reached facade, coverage-candidate-builder
facade, and token conversion helper facades have been retired. Tests now call
`primitive_adapter_config`, `PrimitiveScriptedBootstrapRuntimeService`,
`PrimitiveDigTokenPlanningService`, `PrimitiveReturnTokenPlanningService`,
`DigCutTokenPlanner`, `CoverageCandidateBuilder`, or current focused runtime
contracts directly. Public constructor normalization, token dimensions/order,
token source/fallback strings, coverage candidate construction, scripted
bootstrap behavior, report schemas, and selected AGX behavior remain unchanged.

Current status note after Phase 9.31, superseded by the Phase 2
token-planning runtime cleanup below: active dig token planning orchestration
moved into `PrimitiveDigTokenPlanningService` in
`testbed/planner/primitive/token/dig_planning.py`.
`_build_dig_cut_tokens_for_obs(...)`, `_apply_dig_cut_token_plan(...)`,
`_build_dig_depth_profile_tokens_for_obs(...)`,
`_apply_dig_depth_profile_token_plan(...)`,
`_build_live_dig_depth_profile_tokens_for_obs(...)`, dig-depth-profile
prior/raw-field/cell-id helpers, `_raw_fields_from_live_pose(...)`,
`_build_operator_prior_dig_cut_tokens(...)`, and
`_build_operator_prior_coverage_dig_cut_tokens(...)` were temporary
service-backed compatibility facades during that extraction. The later
`PrimitiveTokenPlanningRuntime` migration retired those old private policy
wrapper names. The service owns pending return-target dig plan application,
conservative/operator-prior/operator-prior-coverage and sweep-belief mode
routing, fallback conservative behavior, coverage raw-field handoff, dig-cut
source/fallback/in-prior writeback, dig-depth-profile source/fallback/error
writeback, raw-field priority, cell-id priority, and copy semantics. Return
token planning, token runtime sequencing, token algorithm classes, coverage
selection/scoring/exemplar algorithms, return handoff gate/effect services,
`cell_entry`, `pre_dig_align`, 5P token behavior, and alternate backend parked
scope remain intentionally unchanged.

Current status note after Phase 9.32: 4P reset lifecycle sequencing now lives
in `PrimitiveResetLifecycleService` in
`testbed/planner/primitive/execution/reset_lifecycle.py`. Public
`PrimitivePlannerACTPolicy.reset()` is a thin service-backed adapter that builds
typed reset ports, applies the returned reset state, and creates the initial
compact debug state. The service owns low-level policy reset order, boundary
detector reset, bootstrap/pre-dig initial-skill selection, counters, hold
mirrors, pre-dig cached diagnostics, cell-entry compatibility defaults,
dig/return token and pending-plan defaults, injected-token flags,
source/fallback strings, and fresh `CoverageRuntimeState` creation. The 5P
runtime planner subclass has been removed by explicit cleanup decision; old
5P runtime behavior is preserved only in branch/git history, while historical
data-slicing and experiment records remain documentation/history rather than
current runtime architecture.

Current status note after Phase 9.33A: public adapter config normalization now
lives in `PrimitivePlannerAdapterConfigNormalizer` and
`PrimitivePlannerAdapterConfigState` under
`testbed/planner/primitive/config/adapter.py`. `PrimitivePlannerACTPolicy.__init__`
keeps its full public constructor signature and default values, directly stores
only the low-level policy handles and boundary detector, builds
`PrimitivePlannerAdapterConfigInputs`, applies the normalized legacy field
updates, and then calls the existing reset facade. Old private config helper
names remain compatibility facades delegating to the config module. This slice
does not build a kernel factory and does not change token planners, execution
driver wiring, decision runtime, coverage algorithms, `pre_dig_align`,
`cell_entry`, or removed 5P runtime status.

Current status note after Phase 9.34: the first backend-neutral common decision
facts packet now lives in `PrimitiveDecisionFacts` under
`testbed/planner/primitive/facts/decision.py`. It preserves the per-tick
`PrimitiveDecisionContext` identity and adds current skill/reason facts without
carrying transition status providers, mutation ports, effect appliers, planner
`self`, or policy fields. `PrimitiveDecisionCapabilities.decision_facts(...)`
builds that packet, and the legacy FSM branches now use it for common
skill/reason checks while keeping dig/carry/dump/return transition statuses lazy
and branch-local. This is an initial common-facts boundary, not full alternate
backend readiness.

Current status note after Phase 9.35: return transition cache refresh is no
longer hidden inside the return status read. `PrimitiveFSMCapabilityProvider`
now exposes `refresh_return_transition_state(obs)` for the explicit shell-owned
handoff cache refresh, and `return_transition_status(obs, boundary_event)` only
reads cached return flags. `PrimitiveDecisionCapabilities` exposes the same
split at context level, and `LegacyFSMReturnBranch` calls refresh only after the
active skill check confirms `return`, immediately before reading return status.
This preserves lazy branch timing while removing a mutation from the status-read
interface; return status is still not part of `PrimitiveDecisionFacts`.

Current status note after Phase 9.36: active return decisions now consume a
typed return-specific facts view, `PrimitiveReturnTransitionFacts`, from
`testbed/planner/primitive/facts/decision.py`. The view wraps an existing
`PrimitiveDecisionFacts` identity plus the read-only `ReturnTransitionStatus`.
`PrimitiveDecisionCapabilities.return_transition_facts(...)` assembles that view
without refreshing return state and can reuse a prebuilt common facts packet.
`LegacyFSMReturnBranch` still refreshes only after the active skill check
confirms `return`, then consumes the return facts view for effect selection.
This advances the backend-neutral facts shape for return only; dig/carry/dump
transition facts and full alternate-backend readiness remain future work.

Current status note after Phase 9.37: active dig decisions now consume a typed
dig-specific facts view, `PrimitiveDigTransitionFacts`, from
`testbed/planner/primitive/facts/decision.py`. The view wraps the same common
`PrimitiveDecisionFacts` identity plus a read-only `DigTransitionStatus`.
`PrimitiveFSMCapabilityProvider.dig_transition_status(...)` no longer writes
the shell/debug `_dig_to_carry_reason` mirror; the active dig branch now calls
`PrimitiveDecisionCapabilities.sync_dig_transition_reason(...)` explicitly after
assembling dig facts and before effect selection. Non-dig skills still do not
read dig status/facts or sync the mirror. This advances the backend-neutral
facts shape for dig and return only; carry/dump transition facts and full
alternate-backend readiness remain future work.

Current status note after Phase 9.38: active carry and dump decisions now
consume typed facts views, `PrimitiveCarryTransitionFacts` and
`PrimitiveDumpTransitionFacts`, from
`testbed/planner/primitive/facts/decision.py`. Each view wraps the existing
common `PrimitiveDecisionFacts` identity plus the read-only carry/dump status
identity. `LegacyFSMCarryBranch` and `LegacyFSMDumpBranch` only assemble these
facts after their active-skill checks, so lazy branch timing is preserved. This
means dig/carry/dump/return mainline transition branches all have explicit
facts views, but there is still no unified backend-neutral facts bundle and no
alternate backend readiness claim.

Current status note after Phase 9.39: dig/carry/dump/return transition facts
views are now reached through `PrimitiveBackendFactsAccess` in
`testbed/planner/primitive/facts/backend.py`. The access object holds the
per-tick `PrimitiveDecisionContext`, one shared `PrimitiveDecisionFacts`
identity, and a private read-only transition-status reader; it exposes lazy
`dig_transition()`, `carry_transition()`, `dump_transition()`, and
`return_transition()` methods. `LegacyFSMDigBranch`,
`LegacyFSMCarryBranch`, `LegacyFSMDumpBranch`, and `LegacyFSMReturnBranch` now
use `capabilities.backend_facts(context)` as their branch-local source of
common facts and transition facts. Dig reason sync, return refresh, residual
pre-dig-align handling, and effect application remain explicit compatibility or
mutation responsibilities outside read-only facts access. Bootstrap still uses
the separate `bootstrap_status(...)` path, so the backend input contract is not
yet complete and alternate backend readiness remains future work.

Current status note after Phase 9.40: bootstrap requested-branch facts now also
flow through `PrimitiveBackendFactsAccess`. The backend facts module owns
`BootstrapDecisionStatus`, `PrimitiveBootstrapDecisionFacts`, the read-only
`PrimitiveBootstrapDecisionReader` protocol, and
`next_skill_after_bootstrap(...)`. `LegacyFSMBootstrapBranch` now obtains
`backend_facts = capabilities.backend_facts(context)`, uses
`backend_facts.common` for the active-skill check, and calls
`backend_facts.bootstrap_decision(...)` only for active bootstrap decisions.
`PrimitiveDecisionCapabilities.bootstrap_status(...)` remains a compatibility
facade over that access path. This completes the confirmed-live legacy FSM
requested branches' migration to the backend facts-access shape, while dig
reason sync, return refresh, residual pre-dig-align handling, and effect
application remain explicit actions outside read-only facts. The next backend
contract gap is that branches still receive the mixed
`PrimitiveDecisionCapabilities` object rather than separate read-only facts
access and compatibility-action dependencies.

Current status note after Phase 9.41: legacy FSM branch dependencies are now
split into read-only facts access and explicit compatibility actions.
`PrimitiveDecisionFactsSource` owns `decision_facts(context)` and
`backend_facts(context, facts=None)`, while
`PrimitiveDecisionCompatibilityActions` owns only dig reason sync, return
refresh, and residual pre-dig-align handling. `LegacyFSMBranchPorts` now
contains `facts_source` and `compatibility_actions` instead of a broad
`capabilities` field. Bootstrap, carry, and dump branch dataclasses store only
the facts source; dig and return additionally store compatibility actions for
their explicit sync/refresh steps; the residual pre-dig adapter stores both for
its parked already-applied path. `PrimitiveDecisionCapabilities` remains
available as a compatibility facade and construction helper, but is no longer
stored by branch dataclasses. The next backend contract gap is that each branch
still creates per-tick backend facts from the facts source independently; there
is not yet one runner-owned backend decision input packet passed through the
ordered branch chain.

Current status note after Phase 9.42: the legacy FSM branch chain now receives
one per-tick `PrimitiveBackendDecisionInput`. `PrimitiveRequestedBranchRunner`
and `LegacyFSMCompatibilityDecisionBackend` each build the input once from
`PrimitiveDecisionContext`, `PrimitiveBackendFactsAccess`, and
`PrimitiveDecisionCompatibilityActions`, then pass the same input identity
through their ordered branches. Branch dataclasses now store only static config
and implement `decide_input(input)`; they no longer store facts source or
compatibility actions. The residual pre-dig-align adapter explicitly rereads
common facts after its already-applied compatibility mutation through
`rebuild_common_facts_after_compatibility_action()`. This closes the per-tick
branch input gap, but `PrimitiveDecisionRuntimePorts` still exposes a
`legacy_fsm_branch_set` factory rather than a backend factory or registry
contract, so alternate-backend readiness remains future work.

Current status note after Phase 9.43: `PrimitiveDecisionRuntimePorts` now
exposes `backend_factories`, a backend-name keyed registry of backend factory
builders. `PrimitiveDecisionRuntime` normalizes the configured backend name,
selects a factory from that registry, and calls the factory's requested or
legacy-compatibility backend. `LegacyFSMDecisionBackendFactory` in
`testbed/planner/primitive/decision/backends/legacy_fsm.py` owns legacy FSM branch-set
construction/reuse and requested/compatibility backend construction. This
removes the legacy branch-set dependency from the runtime port shape. The old
policy-private `_legacy_fsm_requested_decision_backend()`,
`_legacy_fsm_compatibility_decision_backend()`, and
`_legacy_fsm_branch_set()` wrappers are retired; tests and local callers use
the generic `PrimitiveDecisionRuntime.backend_factory_for(...)`,
`requested_backend_for(...)`, and `compatibility_backend_for(...)` accessors or
`LegacyFSMDecisionBackendFactory` contracts directly. The
only registered and supported backend remains `legacy_fsm`; BT/VLM/LLM remain
unsupported parked scope.

Current status note after the generic backend factory protocol and default
legacy composition boundary cleanup: `PrimitiveDecisionRuntime` in
`testbed/planner/primitive/decision/runtime.py` now owns only backend-name
normalization, unsupported-backend fail-fast, generic backend factory registry
access, and decision invocation. `PrimitiveDecisionBackendFactory` exposes
generic requested and compatibility backend protocols instead of a
legacy-specific compatibility return type. Default legacy-FSM composition now
lives in `testbed/planner/primitive/decision/backends/legacy_fsm.py`:
`LegacyFSMDecisionBackendFactoryPorts` carries explicit typed runtime inputs,
and `LegacyFSMDecisionBackendFactory.from_runtime_ports(...)` builds
`PrimitiveFSMCapabilityProvider`, `PrimitiveDecisionCapabilities`,
`LegacyFSMBranchPorts`, and the cached legacy branch set inside the concrete
legacy adapter boundary. `PrimitiveDecisionRuntimeComposition*` is retired from
the code/test interface. `PrimitivePlannerACTPolicy._decision_runtime()` remains
a thin weld that builds `LegacyFSMDecisionBackendFactoryPorts`, registers
`LegacyFSMDecisionBackendFactory.from_runtime_ports(...)` in
`PrimitiveDecisionRuntimePorts.backend_factories`, and passes the registry to
`PrimitiveDecisionRuntime`. Tests that previously depended on the old runtime
composition names were migrated to focused backend factory/runtime contracts
instead of preserving those names for tests. The maturity claim remains
unchanged for the production policy shell: only `legacy_fsm` is registered by
`PrimitivePlannerACTPolicy`.

Current status note after the contract-readiness closure: focused fake-backend
tests prove that `PrimitiveDecisionRuntime` can select any normalized backend
name present in `PrimitiveDecisionRuntimePorts.backend_factories` and invoke
both the requested and compatibility context paths through the generic
`PrimitiveDecisionBackendFactory` protocols. Registered non-legacy names are
selected without touching `PrimitivePlannerACTPolicy`; unregistered names still
fail fast with a direct unsupported-backend error that lists the currently
registered backend names. This proves the generic runtime contract is ready for
a future backend factory implementation. It does not add production
BT/VLM/LLM/learned backend support, and it does not add public plugin/config
selection for alternate backends.

Current status note after the generic decision-runtime interface cleanup:
`PrimitiveDecisionRuntime` no longer exposes legacy-FSM-specific runtime
accessors for branch set, backend factory, requested backend, or compatibility
backend. Focused tests that need the default concrete backend call
`backend_factory_for(LEGACY_FSM_DECISION_BACKEND_NAME)` or the generic
requested/compatibility backend accessors, then inspect
`LegacyFSMDecisionBackendFactory` or backend contracts. Concrete `LegacyFSM*`
adapter names remain in `testbed/planner/primitive/decision/backends/legacy_fsm.py`; only the
runtime/factory/registry interface surface was made backend-neutral.

Current status note after Phase 9.43D: static FSM transition configuration now
has a focused value object, `PrimitiveFSMCapabilityProviderConfig`, owned by
`testbed/planner/primitive/decision/backends/legacy_capability_provider.py`. The public adapter config
normalizer builds that config from constructor-normalized values and stores it
on `PrimitivePlannerAdapterConfigState`; the policy shell keeps the resulting
config as `_fsm_capability_provider_config`. `PrimitiveFSMCapabilityProviderPorts`
now carries that static config plus only explicit live inputs:
semantic-boundary activity, cycle/coverage/return runtime state, and
`ReturnHandoffReadinessService`. `LegacyFSMDecisionBackendFactoryPorts`
receives the static config and live state/service ports, then constructs
`PrimitiveFSMCapabilityProviderPorts` inside the concrete legacy factory
composition boundary. `PrimitivePlannerACTPolicy._decision_runtime()` no longer
imports or constructs `PrimitiveFSMCapabilityProviderPorts`; it remains a thin
typed weld over constructor-owned config and live runtime owners. This
preserves branch order, transition algorithms, reason strings, public schemas,
token/coverage/return behavior, reset timing, default legacy FSM behavior, and
unsupported backend fail-fast wording.

Current status note after the return-handoff runtime composition extraction:
`PrimitiveReturnHandoffRuntime` in
`testbed/planner/primitive/effects/return_handoff_runtime.py` owns composition of
`ReturnHandoffReadinessService`, `ReturnStartEnvelopeGateService`, and
`ReturnDirectHandoffEffectService` from explicit execution/cycle/return/token/
coverage state owners, adapter-normalized `ReturnHandoffReadinessConfig`,
return-target planning, and return start-envelope prior callbacks. The adapter
config normalizer builds the static return-handoff readiness config into
`PrimitivePlannerAdapterConfigState`; the policy shell stores that normalized
config and keeps only a typed return-handoff runtime weld. The old private
policy wrappers for return-handoff config/ports/service construction and direct
handoff effect ports are retired. Return handoff algorithms, direct-handoff
effect ordering, start-envelope readiness checks, transition cache timing,
reason strings, public report schemas, token/coverage behavior, `cell_entry`,
`pre_dig_align`, and backend maturity remain unchanged.

Current status note after Phase 9.44: mutable dig/return token runtime state is
now owned by `PrimitiveTokenRuntimeState` in
`testbed/planner/primitive/token/state.py`. Reset creates a fresh token state
and applies it through `_token_state`; the old private token/pending property
facades and duplicate reset snapshot writeback entries are removed. The owner
covers dig-cut and dig-depth-profile tokens, return target/relocate/
start-envelope tokens, token source/fallback/prior-bound fields, return
start-envelope prior flags, and pending next-dig raw/token/exemplar fields.
Observation-injection flags now live in `PrimitiveObservationInjectionRuntimeState`;
cell-entry compatibility state, coverage state, return handoff state, token
runtime sequencing, and token planning algorithms remain in their existing
focused owners.

Current status note after Phase 9.45: mutable non-token return handoff/runtime
cache state is now owned by `PrimitiveReturnRuntimeState` in
`testbed/planner/primitive/execution/return_state.py`. Reset creates a fresh return state
and applies it through `_return_state`; the old private return-runtime property
facades and duplicate reset snapshot writeback entries are removed. This state
owner does not absorb return-target token fields, pending next-dig token fields,
coverage fields, return handoff algorithms, or direct-handoff effect
sequencing.

Current status note after Phase 9.56: mutable confirmed-live 4P cycle/progress
state is now owned by `PrimitiveCycleRuntimeState` in
`testbed/planner/primitive/execution/cycle_state.py`. Reset creates a fresh cycle state
and applies it through `_cycle_state`; the old private cycle/progress property
facades and duplicate reset snapshot writeback entries are removed.
`PrimitiveCycleRuntimeState.to_report_status()` and
`PrimitiveCycleReportStatus.dig_progress_debug_fields()` now own live
cycle/progress report/finalization projection for debug, rollout summary, and
tick-finalization inputs. The owner does not absorb active skill/switch reason,
previous action, token state, return state, coverage state, pre-dig-align
state, cell-entry compatibility state, backend facts, dig-progress update
algorithms, or public report schema assembly.

Current status note after Phase 9.57: scripted bootstrap runtime state and
runtime rules are now owned by `PrimitiveScriptedBootstrapRuntimeState` and
`PrimitiveScriptedBootstrapRuntimeService` in
`testbed/planner/primitive/execution/scripted_bootstrap.py`. Reset creates a fresh
scripted bootstrap state and applies it through `_scripted_bootstrap_state`;
the old private scripted counter property facades and duplicate reset snapshot
writeback entries are removed. The service owns
scripted-qpos enabled detection, target-reached hold gating, max-step timeout
completion, missing-target runtime error text, and clipped float32 PD action
generation. `PrimitiveScriptedBootstrapRuntimeState.to_report_status()` and
`PrimitiveScriptedBootstrapReportStatus.debug_fields()` now own live
scripted-bootstrap report/status projection for debug and rollout-summary
inputs. Non-scripted bootstrap modes, residual `pre_dig_align`, cell-entry
compatibility/report state, token/return/cycle/coverage state owners,
BT/VLM/LLM support, scripted bootstrap algorithms, reset timing, public report
schemas, and removed 5P runtime remain unchanged.

Current status note after Phase 9.48: execution lifecycle metadata is now owned
by `PrimitiveExecutionRuntimeState` in
`testbed/planner/primitive/execution/state.py`. Reset creates a fresh execution
state with the selected initial skill, `switch_reason="reset"`, and
`prev_action=None`; `PrimitivePlannerRuntimeKernel.reset()` still finalizes the
initial compact debug state after applying the reset state. The policy keeps
`_skill_name`, `_switch_reason`, `_prev_action`, and `_debug_state` as
property-backed compatibility facades.

Current status note after Phase 9.49: per-observation token injected
compatibility flags are now owned by `PrimitiveObservationInjectionRuntimeState`
in `testbed/planner/primitive/facts/observation.py`. Reset creates a fresh
observation-injection state and applies it through `_observation_injection_state`;
the policy no longer keeps the old private injected-flag property facades or
duplicate reset snapshot writeback entries for those flags.
`PrimitivePolicyObservationAssembler` still owns provider order, key names,
copy/no-copy behavior, and immutable `PrimitiveTokenInjectionState` projection;
token schema, `cell_entry`, and `pre_dig_align` behavior remain unchanged.

Current status note after the parked cell-entry runtime cleanups: parked
cell-entry compatibility/report schema projection still lives in
`PrimitiveCellEntryCompatibilityRuntimeState` in
`testbed/planner/primitive/compatibility/cell_entry.py`, but primitive-planner runtime
execution and the policy-owned private `_cell_entry_*` field facades/reset
writeback have been removed. Policy report helpers project fresh disabled/default
cell-entry values. Historical cell-entry planner/data/HDF5/training
compatibility remains outside primitive planner runtime, and `cell_entry`
remains non-mainline compatibility/report material rather than a backend
capability.

Current status note after Phase 9.51 and the later parked pre-dig-align
cleanups: parked pre-dig-align compatibility/report projection defaults are
owned by `PrimitivePreDigAlignCompatibilityRuntimeState` in
`testbed/planner/primitive/compatibility/pre_dig_align.py`. Phase 9.51 introduced a
mutable parked state owner and private policy facades for the old runtime
counters, cached arrays, readiness flags, timeout handoff reason, surface
depth, and surface-guard fields. After the parked runtime cleanup and private
facade cleanup, reset no longer creates or writes `_pre_dig_align_state`, and
`PrimitivePlannerACTPolicy` no longer exposes the old `_pre_dig_align_*`
runtime field facades. Public debug/summary/report keys remain through fresh
disabled/default report projection. This parked-cleanup status was superseded
by the 2026-06-25 user-approved opt-in runtime restoration: live
`pre_dig_align` behavior is now owned by
`testbed/planner/primitive/execution/pre_dig_align.py`, while the old
policy-private facades remain absent. The later false predicate cleanup also
removed the policy-private
`_should_pre_dig_align_before_dig()` and
`_should_pre_dig_align_after_failed_dig()` facades; tests now lock their
absence rather than monkeypatching them.

Current status note after the 2026-06-25 pre-dig-align restoration:
`PrimitivePreDigAlignReportConfig` still carries explicit report config facts,
but `PrimitiveReportRuntime` now projects public pre-dig debug and rollout
summary fields from the live opt-in runtime state through
`pre_dig_align_report_status_from_state(...)`. The old
`_debug_report_pre_dig_align_fields()` policy wrapper remains removed. Runtime
readiness, target, timeout, surface guard, action, replan, failed-dig entry,
return handoff, reset, and report projection are restored through focused
execution/effect/report owners rather than policy-private methods.

Current status note after Phase 9.52: coverage debug-field public schema
assembly is now owned by `CoverageReportService.debug_fields(...)` in
`testbed/planner/primitive/coverage/reports.py`. `CoverageDebugReportInputs`
captures explicit coverage report values, and
`PrimitiveReportRuntime` and `PrimitiveCoverageReportRuntime` now consume the
focused coverage state/config/service facts directly; the old
`_debug_report_coverage_fields()` policy wrapper has been removed.
Coverage corridor debug payloads and coverage decision-event payloads remain in
the same report service. Coverage selection, scoring, effect/runtime updates,
candidate generation, public key names, scalar conversions, `NaN`/`-1`
fallbacks, and list projection semantics remain unchanged.

Current status note after Phase 9.78: the coverage report snapshot boundary now
starts from the focused `CoverageRuntimeState` owner instead of a hand-assembled
coverage snapshot in the large policy shell. `CoverageReportConfig` captures the
coverage report config facts, and `CoverageReportService` projects coverage
debug fields, rollout-summary coverage status, and planner-trace coverage status
from `CoverageRuntimeState` plus explicit `CoverageReportConfig` and
`CoverageSelectionService` where row/cell/attempt/confidence facts are needed.
`PrimitiveReportRuntime` now passes the focused state owner/config/service into
the report service for the coverage subset, while the policy supplies typed
report-runtime ports without old private report helper wrappers.
Coverage debug/summary/trace key names, `NaN`/`None`/`-1` fallback semantics,
list shallow-copy behavior, corridor debug payload values, candidate scores,
decision trace, terminal-stop fields, coverage selection/effect algorithms,
`pre_dig_align`, `cell_entry`, backend fail-fast behavior, and removed 5P
runtime status remain unchanged.

Current status note after Phase 9.53: parked cell-entry debug-field public
schema projection is now owned by
`PrimitiveCellEntryCompatibilityRuntimeState.debug_fields()` in
`testbed/planner/primitive/compatibility/cell_entry.py`.
`PrimitiveReportRuntime` now consumes the cell-entry report status directly;
the old `_debug_report_cell_entry_fields()` policy wrapper has been removed.
Cell-entry token
generation, token dimensions, planner/auditor algorithms, trace mutation,
reset semantics, and public debug key/fallback values remain unchanged. This
phase is accepted as a small cleanup of the parked compatibility/report owner,
but it is not a template for continuing parked-path micro-slices.

Current status note after Phase 9.54 and later report/status composition cleanup:
live token-status projection is now owned by
`PrimitiveTokenRuntimeState.to_token_status(...)` in
`testbed/planner/primitive/token/state.py`, and
`PrimitiveReportCompositionRuntime` supplies the explicit report-time facts:
current observation-injection flags, dig-depth-profile source, and
dig-depth-profile required state. The old policy-private
`_token_status_for_debug_report()` facade is retired. The projection uses
central token dimension constants and still relies on `TokenStatus.from_inputs(...)`
for token array copy/freeze behavior. Token debug key names, token list values, source/fallback
fields, injected flags, dimensions, observation provider order, token planning
services/coordinators, `cell_entry`, `pre_dig_align`, backend fail-fast, and
removed 5P runtime status remain unchanged.

Current status note after Phase 9.55: live return report/status projection is
now owned by `PrimitiveReturnRuntimeState.to_report_status(...)` and
`PrimitiveReturnReportStatus.debug_fields()` in
`testbed/planner/primitive/execution/return_state.py`.
`PrimitiveReportRuntime` now consumes the same return status projection for
debug and summary fields; the old `_debug_report_return_fields()` and
`_rollout_summary_inputs()` policy wrappers have been removed. The projection
consumes explicit
start-envelope config facts and the return runtime owner values. Public debug
key names, rollout summary fields, bool/string/float projection, `NaN`
behavior, checks dict copy projection, return handoff algorithms, start-
envelope gate evaluation, backend fail-fast, and removed 5P runtime status
remain unchanged.

Current status note after Phase 9.56: live cycle/progress report/finalization
projection is now owned by `PrimitiveCycleRuntimeState.to_report_status()` and
`PrimitiveCycleReportStatus.dig_progress_debug_fields()` in
`testbed/planner/primitive/execution/cycle_state.py`.
`PrimitiveReportRuntime` and tick finalization now reuse the same cycle status
projection for
transition counts, dump-hold counts, cycle index, and dig replan counters.
The old `_debug_report_dig_progress_fields()` and `_rollout_summary_inputs()`
policy wrappers have been removed.
Public dig-progress debug keys, rollout summary values, tick finalization input
values, dig-progress update algorithms, skill lifecycle behavior, reset
behavior, backend fail-fast, and removed 5P runtime status remain unchanged.

Current status note after Phase 9.57: live scripted-bootstrap report/status
projection is now owned by
`PrimitiveScriptedBootstrapRuntimeState.to_report_status()` and
`PrimitiveScriptedBootstrapReportStatus.debug_fields()` in
`testbed/planner/primitive/execution/scripted_bootstrap.py`.
`PrimitiveReportRuntime` now reuses the same scripted-bootstrap status
projection for debug fields and `scripted_bootstrap_timeout_count`; the old
`_debug_report_scripted_bootstrap_fields()` and `_rollout_summary_inputs()`
policy wrappers have been removed. Scripted bootstrap
readiness, timeout, target-reached, PD action algorithms, reset timing, public
debug key names, rollout summary key names, backend fail-fast, token/coverage/
return/cycle owners, `cell_entry`, `pre_dig_align`, and removed 5P runtime
status remain unchanged.

Current status note after Phase 9.58: live planner-trace coverage sub-
projection is now owned by `CoverageReportService.trace_status(...)` and
`CoverageTraceReportStatus` in
`testbed/planner/primitive/coverage/reports.py`.
`PrimitivePlannerTraceInputs` now carries that coverage status object instead
of many independent coverage trace fields, and `PrimitiveReportRuntime` owns
trace-input assembly. The old `_planner_trace_inputs()` policy wrapper has
been removed.
Public `planner_trace()` key names, coverage decision trace count semantics,
list shallow-copy behavior, corridor debug payload values, decision trace
mutation, terminal-stop behavior, coverage debug/summary schemas, coverage
algorithms, backend facts, token/return/cycle/scripted-bootstrap owners,
`cell_entry`, `pre_dig_align`, and removed 5P runtime status remain unchanged.

Current status note after Phase 9.59: live rollout-summary coverage sub-
projection is now owned by `CoverageReportService.summary_status(...)` and
`CoverageSummaryReportStatus` in
`testbed/planner/primitive/coverage/reports.py`.
`PrimitiveRolloutSummaryInputs` now carries that coverage status object instead
of many independent coverage summary fields, and `PrimitiveReportRuntime` owns
summary-input assembly. The old `_rollout_summary_inputs()` policy wrapper has
been removed.
Public `rollout_summary()` key names, bool-to-int projection, `None`-to-`NaN`
projection, debug schemas, planner trace schemas, coverage algorithms,
corridor debug payload values, decision trace mutation, terminal-stop behavior,
backend facts, token/return/cycle/scripted-bootstrap owners, `cell_entry`,
`pre_dig_align`, and removed 5P runtime status remain unchanged.

Current status note after Phase 9.60: live token/pending/dig-cut report
metadata projection is now owned by
`PrimitiveTokenRuntimeState.to_report_status(...)` and
`PrimitiveTokenReportStatus` in `testbed/planner/primitive/token/state.py`.
The status carries pending next-dig cycle/corridor ids, dig-cut injected
status, planner mode, prior id/path, token source, prior-window flag, and
fallback reason. `PrimitiveReportRuntime` now reuses that status for pending,
dig-cut, summary, and trace report inputs; the old private policy wrappers
`_debug_report_pending_fields()`, `_debug_report_dig_cut_fields()`,
`_rollout_summary_inputs()`, and `_planner_trace_inputs()` have been removed.
Public
debug/summary/trace key names and type projection, token dimensions, token
contract text/version, token planning algorithms/coordinators,
dig-depth-profile planning, return token planning, coverage algorithms,
backend facts/fail-fast, reset timing, policy observation provider order,
`cell_entry`, `pre_dig_align`, and removed 5P runtime status remain unchanged.

Current status note after Phase 9.61: live token runtime sequencing no longer
uses policy-built getter/setter callbacks for token state storage.
`PrimitiveTokenRuntimePorts` in `testbed/planner/primitive/token/runtime.py`
now carries the focused `PrimitiveTokenRuntimeState` owner directly, and
`PrimitiveTokenRuntimeCoordinator` reads/writes dig-cut, dig-depth-profile,
return-target, return-relocate, return-start-envelope, and pending next-dig
token fields through that owner. `PrimitivePlannerACTPolicy` still assembles
explicit external ports for current skill, config gates, token-builder
algorithms, return-relocate planning, coverage terminal-stop status, and
coverage exemplar facts. Token dimensions, schema keys, source/fallback
strings, branch order, reset timing, backend fail-fast behavior, `cell_entry`,
`pre_dig_align`, and removed 5P runtime status remain unchanged.

Current status note after Phase 2 token observation/runtime composition
extraction: `PrimitiveTokenObservationRuntime` in
`testbed/planner/primitive/token/observation_runtime.py` now owns
policy-observation assembly, observation-injection clear/apply timing,
`PrimitivePolicyObservationAssemblerPorts` construction, and
`PrimitiveTokenRuntimePorts` construction. The old private policy wrappers for
`_policy_obs()`, plan ensure hooks, and token-runtime coordinator/ports access
have been removed; `PrimitivePlannerACTPolicy` keeps typed token-observation
runtime ports/runtime factory as the B owner weld. Token planner construction is
now owned by `PrimitiveTokenPlannerFactory` in
`testbed/planner/primitive/token/factory.py`; the old policy-private goal token
and concrete token planner factory/proxy methods have been removed.
Token provider order, injected observation key names, token dimensions,
source/fallback strings, token planning algorithms, coverage algorithms,
return handoff behavior, public debug/summary/trace schemas, reset timing,
and backend fail-fast behavior remain unchanged.

Current status note after Phase 2 token planning service composition
extraction: `PrimitiveTokenPlanningRuntime` in
`testbed/planner/primitive/token/planning_runtime.py` now owns construction of
`PrimitiveDigTokenPlanningPorts`, `PrimitiveReturnTokenPlanningPorts`,
`PrimitiveDigTokenPlanningService`, and `PrimitiveReturnTokenPlanningService`.
The old private policy wrappers for active dig token planning,
dig-depth-profile helpers, return-target planning, return-start-envelope
helpers, live-pose raw fields, and operator-prior token helpers have been
removed; `PrimitivePlannerACTPolicy` keeps typed token-planning runtime
ports/runtime factory as the B owner weld. Token schemas,
source/fallback strings, token planning algorithms, coverage algorithms,
return handoff behavior, public debug/summary/trace schemas, reset timing,
and backend fail-fast behavior remain unchanged.

Current status note after Phase 9.62: live coverage selection runtime
sequencing no longer uses policy-built getter/setter callbacks for coverage
selection state storage. `CoverageSelectionRuntimePorts` in
`testbed/planner/primitive/coverage/selection.py` now carries the focused
`CoverageRuntimeState` owner directly, and
`CoverageSelectionRuntimeCoordinator` reads/writes coverage corridors,
candidate scores, active/last-selected ids, and all-depleted checks through
that owner. `PrimitivePlannerACTPolicy` still assembles explicit external
ports for dig-cut prior/config facts, candidate builder, selection service,
selection facts, recent-row reference, reopen/terminal hooks, and
decision-event recording. Coverage candidate construction, scoring/selection
algorithms, first-dig gate behavior, recent-row penalty, state-exemplar
scoring, terminal-stop reason strings, decision trace payload schema,
token/return/cycle/scripted-bootstrap/execution behavior, backend fail-fast
behavior, `cell_entry`, `pre_dig_align`, and removed 5P runtime status remain
unchanged.

Current status note after Phase 9.63: live coverage effect runtime sequencing
no longer uses policy-built getter/setter callbacks for coverage effect state
storage. `CoverageEffectRuntimePorts` in
`testbed/planner/primitive/coverage/effects.py` now carries the focused
`CoverageRuntimeState` owner directly, and
`CoverageEffectRuntimeCoordinator` reads/writes current payload gain, last
payload/deposit, completed dump count, global low-productivity streak,
rejected exemplar ids, pass index, active corridor id, terminal-stop state,
active corridor lookup, corridor list, and all-depleted checks through that
owner. `PrimitivePlannerACTPolicy` still assembles explicit external ports for
coverage mode/config, update/runtime services, mass/facts builders,
decision-event recording, and low-productivity thresholds. Coverage candidate
construction/scoring/selection algorithms, first-dig gate behavior, recent-row
penalty, state-exemplar scoring, terminal-stop reason strings, decision trace
payload schema, event ordering, report/debug/summary/trace schemas,
token/return/cycle/scripted-bootstrap/execution behavior, backend fail-fast
behavior, `cell_entry`, `pre_dig_align`, and removed 5P runtime status remain
unchanged.

Current status note after Phase-2 coverage effect/update composition
extraction: `PrimitiveCoverageEffectRuntime` in
`testbed/planner/primitive/coverage/effect_runtime.py` now owns
`CoverageUpdateConfig`, `CoverageUpdateService`, `CoverageRuntimeConfig`,
`CoverageRuntimeService`, and `CoverageEffectRuntimePorts` construction.
`PrimitivePlannerACTPolicy` keeps typed coverage-effect runtime ports and the
focused runtime factory; the old private coverage effect/update helper
wrappers have been deleted after callers/tests moved to the focused runtime
contract. The later coverage effect owner-state setter cleanup also removed
old private policy setter/update wrappers for payload, dump,
low-productivity, pass, active-corridor, rejected-exemplar, and terminal-stop
coverage owner fields; callers use `CoverageRuntimeState` owner methods or
focused coverage runtimes directly. Coverage update formulas,
low-productivity gates, multi-pass reopen, terminal-stop replace behavior,
corridor belief updates, decision-event payloads, coverage selection/fact
composition, coverage report composition, token/return behavior, public
debug/summary/trace schemas, parked `pre_dig_align`, parked `cell_entry`, and
backend support status remain unchanged.

Current status note after Phase-2 coverage report/decision-event composition
extraction: `PrimitiveCoverageReportRuntime` in
`testbed/planner/primitive/coverage/report_runtime.py` now owns coverage report
config/state/service composition, bucket snapshot projection, decision-event
recording, and active/corridor report helper projection. The old private
coverage report helper wrappers have been deleted after callers/tests moved to
the focused runtime contract. Coverage report/debug/summary/trace schema,
decision-event payload keys, bucket snapshot payloads, candidate scores,
coverage selection/effect behavior, token/return behavior, reset timing,
parked `pre_dig_align`, parked `cell_entry`, and backend support status remain
unchanged.

Current status note after Phase 9.64: active dig token planning no longer uses
policy-built getter/setter callbacks for token and coverage storage.
`PrimitiveDigTokenPlanningPorts` in
`testbed/planner/primitive/token/dig_planning.py` now carries
`PrimitiveTokenRuntimeState` and `CoverageRuntimeState` directly, and
`PrimitiveDigTokenPlanningService` reads/writes pending dig-cut route state,
dig-cut source/fallback/prior flags, dig-depth-profile source/fallback fields,
selected corridor ids, payload/deposit baselines, active corridor lookup, and
state-exemplar payload through those owners. `PrimitivePlannerACTPolicy` still
assembles explicit external ports for planner modes, token planner algorithms,
bucket/env/deposit observation facts, coverage corridor selection, and coverage
raw-field building. Token dimensions/order/source strings, raw-field priority,
cell-id priority, pending-return-target route semantics, dig-depth-profile
planning behavior, coverage selection/effect semantics, debug/summary/trace
schema, branch order, reason strings, backend fail-fast behavior, `cell_entry`,
`pre_dig_align`, and removed 5P runtime status remain unchanged.

Current status note after Phase 9.65: return token planning no longer uses
policy-built storage callbacks for coverage active id/corridor lookup or
return start-envelope source/prior flags.
`PrimitiveReturnTokenPlanningPorts` in
`testbed/planner/primitive/token/return_planning.py` now carries
`PrimitiveTokenRuntimeState` and `CoverageRuntimeState` directly, and
`PrimitiveReturnTokenPlanningService` reads/writes return start-envelope token
source, prior spatial/qpos flags, active corridor id, and corridor lookup
through those owners. `PrimitivePlannerACTPolicy` still assembles explicit
external ports for planner mode, return token planner algorithms,
bucket/env/qpos/qvel observation facts, coverage corridor selection, and
coverage raw-field building. Return-target mode routing, coverage raw-field
handoff, corridor id/cell id fallback, return start-envelope
build/apply/conditioning, prior token/mapping/bounds helper behavior,
token/raw-field copy semantics, token dimensions/order/source strings,
debug/summary/trace schema, branch order, reason strings, policy reset timing,
backend fail-fast behavior, `cell_entry`, `pre_dig_align`, and removed 5P
runtime status remain unchanged.

Current status note after Phase 9.66: token runtime sequencing no longer uses
policy-built coverage state-exemplar callbacks for the pending next-dig
handoff. `PrimitiveTokenRuntimePorts` in
`testbed/planner/primitive/token/runtime.py` now carries
`CoverageRuntimeState` directly alongside `PrimitiveTokenRuntimeState`, and
`PrimitiveTokenRuntimeCoordinator` reads active state-exemplar ids, distance,
and profile token from the coverage owner while preserving the existing
profile-token copy behavior. `clear_dig_cut_plan()` also clears the active
state exemplar through the coverage owner at the same timing as before.
`PrimitivePlannerACTPolicy` still assembles explicit external ports for current
skill/config gates, token-builder algorithms, return-relocate planning, and
return token planning services. Return target plan success path, pending
next-dig token/raw/exemplar writeback values, clear dig-cut timing, pending
invalidation, return fallback-zero path, token dimensions/order/source strings,
debug/summary/trace schema, branch order, reason strings, policy reset timing,
backend fail-fast behavior, `cell_entry`, `pre_dig_align`, and removed 5P
runtime status remain unchanged.

Current status note after Phase 9.67: skill switch lifecycle sequencing no
longer uses policy-built storage setter callbacks for active skill/reason,
cycle counters, return counters, parked pre-dig-align compatibility fields,
coverage current payload gain, or dig progress fields.
`PrimitiveSkillLifecyclePorts` now carries the focused execution, cycle,
return, pre-dig-align compatibility, and coverage state owners directly.
`PrimitiveSkillLifecycleService` still owns the same-skill no-op,
skill/reason write order, active-policy reset timing including the residual
`pre_dig_align` exception, target-specific reset values, and dig-cut plan clear
timing. `PrimitivePlannerACTPolicy` still assembles the explicit external
active-policy reset and dig-cut clear action ports. Branch order, reason
strings, thresholds, token schema, debug/summary/trace schema, backend
support, `pre_dig_align` algorithms, `cell_entry`, and removed 5P runtime
status remain unchanged.

Current status note after Phase 9.68: backend-facing FSM transition-status
assembly no longer receives cycle, coverage, and return runtime storage as
policy-built primitive fields/callbacks. `PrimitiveFSMCapabilityProviderPorts`
now carries `PrimitiveFSMCapabilityProviderConfig`,
`PrimitiveCycleRuntimeState`, `CoverageRuntimeState`, `PrimitiveReturnRuntimeState`,
semantic-boundary activity, and `ReturnHandoffReadinessService` directly.
`PrimitiveFSMCapabilityProvider` reads dig counters, terminal-stop state,
cycle-start deposit, dump hold/start fields, and return cached flags through
those live owners; it reads thresholds and gate configuration through the
focused static config; and it synchronizes the dig-to-carry reason mirror by
writing `PrimitiveCycleRuntimeState`. Focused branches/tests read transition
statuses through `PrimitiveFSMCapabilityProvider` or `LegacyFSMBranchPorts`
instead of old policy-private `_dig/_carry/_dump/_return_transition_status_for_backend(...)`
wrappers. Transition algorithms, branch order, reason string
semantics, thresholds, token schema, debug/summary/trace schema, backend
support, `pre_dig_align` algorithms, `cell_entry`, and removed 5P runtime
status remain unchanged.

Current status note after Phase 9.69: requested-effect application no longer
uses policy-built state-mutation callbacks for simple cycle and return runtime
effects. `RequestedEffectApplierPorts` now carries
`PrimitiveCycleRuntimeState` and `PrimitiveReturnRuntimeState` directly.
`RequestedEffectApplier` marks return next-dig events, completes return
transitions, increments dig replan counters, sets dump hold counts, and writes
dump start deposited mass through those owners while preserving ordered effect
application. `PrimitivePlannerACTPolicy` still assembles explicit external
ports for skill switching, coverage/cell-entry/restart actions, return handoff
routing, and deposited-mass observation reads. Effect order, branch order,
reason strings, thresholds, token schema, debug/summary/trace schema, backend
support, `pre_dig_align` algorithms, `cell_entry`, and removed 5P runtime
status remain unchanged.

Current status note after requested-effect runtime composition cleanup:
`PrimitiveRequestedEffectRuntime` in `testbed/planner/primitive/effects/requested.py`
owns construction of `RequestedEffectApplierPorts` from explicit typed state,
service, and runtime inputs: cycle state, return state, `set_skill`, fixed
return next-skill name, coverage effect runtime, dig recovery service,
return-handoff runtime, and `action_dim` for per-observation
`PrimitiveObservationFacts`. `PrimitivePlannerACTPolicy` keeps only a typed
`_primitive_requested_effect_runtime*` weld and passes that runtime to
`PrimitiveExecutionRuntimePorts.requested_effect_applier`; the old private
`_requested_effect_applier()` and `_requested_effect_applier_ports()` policy
wrappers are retired. Tests that depended on those old private names were
migrated to focused requested-effect runtime/applier contracts or the new
policy runtime weld.

Current status note after Phase-2 cycle/return/dump transition wrapper
retirement: the old private policy wrappers for dump ready/done hold counts,
dump-start deposited mass, return next-dig marking, return transition
completion, return next-skill selection, and dig replan counters have been
removed. Tests and production callbacks use `PrimitiveCycleRuntimeState`,
`PrimitiveReturnRuntimeState`, and `RequestedEffectApplier` contracts directly;
the requested-effect port for return next-skill now supplies the direct `dig`
target while preserving the existing `return_to_dig_next_dig_entry_ready`
reason construction and post-completion ordering.

Current status note after Phase 9.70 audit-only remaining-policy inventory:
`PrimitivePlannerACTPolicy` is still a large file because it is now serving as
the public adapter, composition root, compatibility-facade host, and residual
parking boundary rather than only as the old algorithm owner. The read-only
inventory after Phase 9.69 classifies most remaining port builders as live
composition glue over focused services and explicit external facts:
runtime-kernel ports, reset lifecycle ports, action dispatch ports, backend
decision/facts ports, execution-driver ports, token runtime/planning ports, and
coverage selection/effect runtime ports. These should not be migrated by
chasing individual callback removal unless a broader stable owner boundary is
being reduced.

The earlier inventory classified `_debug_report_coverage_fields()`,
`_rollout_summary_inputs()`, and `_planner_trace_inputs()` as report-only
snapshot assembly over already focused status/report builders. The retroactive
report-runtime wrapper-retirement slice has now grouped those old helper names
with the rest of the report-runtime private wrapper cluster and deleted them
after callers/tests moved to `PrimitiveReportRuntime`.
primitive-planner `_cell_entry_tokens_for_obs()` and
`_complete_cell_entry_dig()` have been removed. Historical cell-entry
data/HDF5/training support remains a compatibility boundary, and public
cell-entry report fields remain disabled/default schema surfaces. Do not
recreate cell-entry primitive runtime or promote it into the target
token/runtime architecture without new evidence and explicit approval.

The restart/recovery cluster originally mixed live failed-dig recovery,
coverage/token invalidation, terminal-stop diagnostics, return state clearing,
and parked pre-dig-align retry paths. The live recovery responsibility has since
been moved into `PrimitiveDigRecoveryService`, and Phase 9.92 removed the
parked pre-dig-align restart/replan path. Further changes here should only
target live failed-dig behavior or explicit compatibility deletion, not
pre-dig-align runtime revival.

Current status note after Phase 9.71 and Phase 9.92, superseded by the Phase 2
skill/recovery token-plan wrapper retirement: failed-dig/restart
recovery no longer lives as direct implementation in
`PrimitivePlannerACTPolicy`, and parked pre-dig-align retry/replan behavior has
been removed. `PrimitiveDigRecoveryService` in
`testbed/planner/primitive/execution/dig_recovery.py` owns restart/stop behavior directly
through typed ports; the old private policy restart wrappers have been removed.
The service uses focused execution, cycle, return, and coverage state owners for
stable storage while keeping active-policy reset, token runtime
clear/invalidation actions, coverage decision events, terminal-stop requests,
typed observation facts, and config facts as explicit ports. Failed-dig branch
choice, remaining reason strings, terminal-stop diagnostics, reset timing,
debug/summary/trace schemas, backend support, `cell_entry`, and removed 5P
runtime status remain unchanged.

Current status note after Phase 9.72: return direct-handoff effect-side
transition state no longer depends on policy-built state callbacks.
`ReturnDirectHandoffEffectPorts` now carries the focused
`PrimitiveExecutionRuntimeState` and `PrimitiveCycleRuntimeState` owners
directly. `ReturnDirectHandoffEffectService` reads the current skill from the
execution owner, completes the return transition through the cycle owner, and
after Phase 9.92 always hands off to `dig` rather than parked pre-dig-align.
The later return-handoff runtime composition extraction retired the old private
policy action/weld wrappers; requested-effect application now calls
`PrimitiveReturnHandoffRuntime.apply_direct_handoff(...)`. That runtime builds
`ReturnDirectHandoffEffectService`, `ReturnHandoffReadinessService`, and
`ReturnStartEnvelopeGateService` from typed config, state owners, and explicit
return-target/prior algorithm ports. `set_skill`, return-target planning,
handoff readiness, and direct-handoff readiness remain explicit typed ports. The old
`_complete_return_transition_for_backend()` and
`_next_skill_after_return_transition()` compatibility facades were retired by
the Phase-2 cycle/return/dump transition wrapper cleanup. Direct-handoff readiness
behavior, reason strings, return transition counts, skill lifecycle reset
timing, token schemas, debug/summary/trace schemas, backend support,
`pre_dig_align` algorithm/action behavior, `cell_entry`, and removed 5P
runtime status remain unchanged.

Current status note after Phase 9.73: primitive action dispatch no longer uses
policy-built callbacks for the state reads that choose the active policy and the
first-dig override. `PrimitiveActionDispatchPorts` now carries the focused
`PrimitiveExecutionRuntimeState`, `PrimitiveCycleRuntimeState`, and
`CoverageRuntimeState` owners directly. `PrimitiveActionDispatchService` reads
the active skill from the execution owner, first-dig cycle index from the cycle
owner, and completed dump count from the coverage owner while preserving the
scripted-bootstrap short-circuit, residual `pre_dig_align` action short-circuit,
first-dig policy gate, active-policy lookup, policy observation assembly, and
action shape contract. `PrimitivePlannerACTPolicy` still assembles explicit
ports for low-level policy handles and ordering, policy observation assembly,
scripted bootstrap action generation, and residual pre-dig-align action
generation. Action dispatch semantics, first-dig gate behavior, observation
provider order, branch order, reason strings, token schema, debug/summary/trace
schemas, backend support, `pre_dig_align` algorithm/action behavior,
`cell_entry`, and removed 5P runtime status remain unchanged.

Current status note after Phase 9.74 audit-only remaining-size inventory:
`PrimitivePlannerACTPolicy` remains 5311 lines after Phase 9.73. The remaining
large-policy responsibility is not one single algorithm block. It is split
across public adapter/runtime composition ports, reset/execution/decision
composition, report snapshot assembly, token/coverage/dig/return planning port
assembly, service-backed recovery/direct-handoff/action-dispatch facades,
property-backed compatibility facades over focused state owners, residual
`pre_dig_align` parking material, parked `cell_entry` compatibility material,
and live transition fact / geometry gate helpers.

The audit classifies report helpers as report-only snapshot assembly that
should only move as a coherent report-input boundary, not by moving one dict at
a time. It classifies `pre_dig_align` and `cell_entry` as parked material that
must not be promoted into backend facts, behavior-tree nodes, token contracts,
or mainline runtime architecture without new evidence and explicit approval.
The strongest remaining implementation candidate is a cohesive transition
facts / geometry gate boundary: dig-exit overshoot, dump-ready geometry
predicates, return-to-dig entry/shallow/start-envelope gate inputs, and the
associated capability-provider fact assembly. That candidate must preserve
thresholds, reason strings, branch order, backend facts schema, return
start-envelope behavior, and parking boundaries.

Current status note after Phase 9.75: the first transition facts / geometry
gate implementation slice moved dig-exit overshoot calculation into
`PrimitiveFSMCapabilityProvider` and removed duplicated migrated transition
helpers from `PrimitivePlannerACTPolicy`. `PrimitiveObservationFacts` now owns
read-only bucket dig-area pose and bucket-tip dig-area pose projection from
`env_state`, preserving the existing bucket-tip-preferred and bucket-pose
fallback semantics. `PrimitiveFSMCapabilityProviderPorts` no longer carries a
`dig_exit_overshoot_m` callback; the provider computes overshoot from the active
coverage corridor plus observation pose facts and feeds the existing
`DigTransitionStatus` guard logic.

The policy shell no longer contains the migrated duplicate implementations for
dig bad-replan readiness, dig-exit guard readiness, dig-to-carry readiness,
semantic dig liveness, dig-complete low-payload check, dump-ready geometry
predicates, dump-done/deposit checks, carry release-safety check, or target
geometry projection. Those facts now resolve through
`PrimitiveObservationFacts`, `PrimitiveFSMCapabilityProvider`, and the existing
transition status dataclasses. Backend branch order, reason strings,
thresholds, token schema, debug/summary/trace schemas, reset timing,
`pre_dig_align`, `cell_entry`, and BT/VLM/LLM unsupported fail-fast behavior
remain unchanged.

Current status note after Phase 9.76: return-to-dig handoff readiness is now a
focused source of truth in `ReturnHandoffReadinessService`. The service owns the
existing entry-target precedence, entry-error calculation from
`PrimitiveObservationFacts.bucket_dig_area_pose()`, entry-close runtime
writeback, return start-envelope gate input assembly, gate-result writeback,
`handoff_ready`, and direct-handoff mass/config gate. Its ports carry the
focused execution, cycle, return, token, and coverage state owners directly,
while return-target planning and return start-envelope prior bounds/mapping
remain explicit external algorithm ports.

`ReturnDirectHandoffEffectPorts` no longer carries
`return_to_dig_handoff_ready` or `return_to_dig_direct_handoff_ready`
callbacks. `ReturnDirectHandoffEffectService` now uses the readiness service for
those checks while preserving the existing ordered effect chain: set return
skill, ensure return-target plan, evaluate handoff/direct readiness, complete the
return transition, then switch to dig or residual `pre_dig_align` with the same
reason strings. The old private policy return handoff readiness wrappers have
been retired; policy supplies only the typed readiness config/ports/service weld.
Return start-envelope token build/apply/conditioning/prior mapping, backend
branch order, thresholds, debug/summary/trace schemas, reset timing,
`pre_dig_align`, `cell_entry`, and BT/VLM/LLM unsupported fail-fast behavior
remain unchanged.

Current status note after the return-handoff runtime composition extraction:
`PrimitivePlannerAdapterConfigNormalizer` builds the static
`ReturnHandoffReadinessConfig` from normalized constructor values, including the
existing `ReturnStartEnvelopeGateConfig`. `PrimitivePlannerACTPolicy` stores
that adapter-owned config under a dedicated return-handoff runtime value and no
longer builds `_return_handoff_readiness_config()`,
`_return_handoff_readiness_ports()`, `_return_handoff_readiness_service()`, or
`_return_direct_handoff_effect_ports()` private wrappers. Decision-runtime
composition receives return-handoff readiness through
`PrimitiveReturnHandoffRuntime.readiness_service()`, and requested-effect
application uses the same runtime for direct handoff. Return handoff algorithms,
direct-handoff ordering, reason strings, public report/debug/trace schemas,
token planning, coverage behavior, reset timing, and backend support remain
unchanged.

Current status note after Phase 9.77: the capability-provider return refresh
edge now consumes the focused return handoff readiness source directly.
`PrimitiveFSMCapabilityProviderPorts` carries
`ReturnHandoffReadinessService` instead of a policy-built
`refresh_return_handoff_state` callback, and
`PrimitiveFSMCapabilityProvider.refresh_return_transition_state(obs)` calls
`handoff_ready(obs)` on that service to refresh the same return owner caches.
`PrimitivePlannerACTPolicy._primitive_fsm_capability_provider_ports()` now passes
`self._return_handoff_readiness_service()` directly. The policy shell also
dropped the duplicate `_return_to_dig_shallow_guard_ready(...)` helper after the
same shallow-guard calculation was confirmed to be represented by
`ReturnTransitionStatus.from_inputs(...)` and to have no production callers.

Return transition refresh semantics, return handoff readiness semantics,
direct-handoff effect ordering, next-skill reason strings, return
start-envelope token algorithms, debug/summary/trace schemas, residual
`pre_dig_align`, parked `cell_entry`, and BT/VLM/LLM unsupported fail-fast
behavior remain unchanged.

Current status note after Phase 9.78: the coverage report snapshot cluster moved
as one bounded report-input boundary. `CoverageReportService` now owns projection
from `CoverageRuntimeState` plus explicit `CoverageReportConfig` and
`CoverageSelectionService` into coverage debug fields, coverage rollout-summary
status, and coverage planner-trace status. The policy shell no longer
hand-assembles those coverage snapshot dictionaries/lists for the public reports;
it only supplies the focused state owner and explicit config/service facts for
the coverage subset. This narrows report snapshot assembly without introducing a
generic report blackboard or planner-self port.

Current status note after Phase 9.79: the parked pre-dig-align report projection
cluster moved as one compatibility/report boundary. The large policy shell no
longer owns the public pre-dig debug dict or the pre-dig rollout-summary field
projection directly; it supplies explicit config facts and the focused parked
state owner to `PrimitivePreDigAlignReportStatus`. This narrows report assembly
without promoting residual `pre_dig_align` into backend facts, behavior-tree
nodes, token contracts, or mainline runtime architecture.

Current status note after Phase 9.80: the parked cell-entry report projection
cluster now lives with `PrimitiveCellEntryCompatibilityRuntimeState`.
`PrimitiveCellEntryReportStatus` projects the existing cell-entry public debug
fields, rollout-summary enablement/trace-count fields, and planner-trace trace
list from the parked compatibility state plus explicit report config facts.
The large policy shell keeps thin report config/status facades, while
`PrimitiveRolloutSummaryInputs` and `PrimitivePlannerTraceInputs` consume the
same status object. This keeps `cell_entry` parked as compatibility/report
material and does not promote it into the token contract, backend facts, or
mainline runtime architecture.

Current status note after Phase 2 report/status composition extraction:
`PrimitiveReportCompositionRuntime` in
`testbed/planner/primitive/report/runtime.py` owns construction of
`PrimitiveReportRuntimePorts` plus token, `cell_entry`, and `pre_dig_align`
report-status projection from focused owners/runtimes. `PrimitiveReportRuntime`
continues to own construction of `PrimitiveDebugReportInputs`,
`PrimitiveRolloutSummaryInputs`, and `PrimitivePlannerTraceInputs`.
`PrimitivePlannerACTPolicy` keeps public `debug_state()`, `rollout_summary()`,
and `planner_trace()` surfaces plus a typed report-composition weld; the old
private report/status composition wrappers have been retired. The existing
report builders still own public schema projection; public debug/summary/trace
keys, values, list-copy behavior, and compatibility fields remain unchanged.

Current status note after Phase 9.81 audit-only inventory: the large policy
shell remains 4763 lines because it still owns several different adapter
responsibilities, not because one remaining monolithic algorithm is waiting to
be moved. The confirmed-live coverage raw-field, coverage selection-fact, and
state-exemplar fact-source helpers still live in
`PrimitivePlannerACTPolicy` near the coverage planning port builders, while
coverage scoring/selection services and state-exemplar planner services already
exist in focused modules. This is the next meaningful live boundary to consider:
it can reduce real policy-side fact construction without promoting parked
`pre_dig_align` or `cell_entry`, without inventing a pass-through composition
object, and without claiming alternate backend readiness.

Current status note after Phase 9.82: the coverage planning fact-source
boundary moved out of `PrimitivePlannerACTPolicy` into
`CoveragePlanningFactService` in `testbed/planner/primitive/coverage/facts.py`.
The service now owns coverage selection facts, raw-field fallback/clamp
projection, optional state-conditioned exemplar override/writeback, exemplar
distance/id projection, removed-depth grid delegation, weighted exemplar helper
delegation, and remaining-depth projection. The policy shell supplies explicit
typed coverage-selection runtime ports; the old private policy helper names
that once wrapped this service have been retired. This narrows real coverage planning
responsibility without changing coverage scoring/selection algorithms,
state-exemplar scoring, raw-field priority, token schemas, report schemas,
parked `pre_dig_align`, parked `cell_entry`, or backend support.

Historical status note after Phase 9.83 audit-only inventory:
`PrimitivePlannerACTPolicy` remained 4637 lines at that point after the coverage
fact-source move. The then-remaining observation/raw-fact helpers were
cross-chain facts rather than one isolated residue: token planning consumes
bucket pose, deposited mass,
env-state, qpos, and qvel callbacks; coverage effect/report paths still consume
mass/deposit/env snapshots; requested effects and dig recovery still consume
one observation metric each; parked `pre_dig_align` and `cell_entry` also have
compatibility-only observation helpers. `PrimitiveObservationFacts` already owns
stable read-only projections for mass, deposit, target geometry, qpos/qvel,
env-state, and bucket dig-area/tip pose, so the next implementation should not
create a generic observation blackboard or move isolated helper wrappers.
The narrowest live bounded slice is the token planning observation fact-source
boundary: move active dig and return token planning from separate policy-built
observation callbacks to a shared typed `PrimitiveObservationFacts` input while
leaving policy observation token injection order, coverage raw-field facts,
return handoff readiness, requested effects, recovery metrics, parked
`pre_dig_align`, and parked `cell_entry` out of scope.

Current status note after Phase 9.84: active dig and return token planning now
consume a typed `PrimitiveObservationFacts` provider instead of separate
policy-built observation callbacks. `PrimitiveDigTokenPlanningPorts` no longer
exposes `bucket_dig_area_pose`, `deposited_mass`, or `env_state`;
`PrimitiveReturnTokenPlanningPorts` no longer exposes `bucket_dig_area_pose`,
`env_state`, `qpos`, or `qvel`. The policy shell constructs
`PrimitiveObservationFacts.from_obs(obs, action_dim=int(self.action_dim))` for
both token planning services and keeps remaining observation helpers only for
other live consumers or compatibility facades. This narrows the token planning
observation fact-source boundary without changing token dimensions/order/source
strings, raw-field priority, dig-depth-profile env-state/cell-id behavior,
return start-envelope qpos/qvel defaults, policy observation injection order,
coverage raw-field facts, parked `pre_dig_align`, parked `cell_entry`, or
backend support.

Current status note after Phase 9.85: coverage effect runtime fact projection
now lives in `CoverageEffectFactService` inside
`testbed/planner/primitive/coverage/effects.py`. `CoverageEffectRuntimePorts`
no longer exposes policy-built `mass_in_bucket`, `completion_facts`,
`rejection_facts`, `reopen_facts`, or `terminal_facts` callbacks. Instead, the
coverage effect boundary receives `CoverageRuntimeState`,
`PrimitiveCycleRuntimeState`, a typed `PrimitiveObservationFacts` provider, a
remaining-depth provider, and a corridor-attempt-limit provider, then projects
the existing `CoverageCompletionFacts`, `CoverageRejectionFacts`,
`CoverageReopenFacts`, and `CoverageTerminalFacts` internally. This removes a
live policy callback bag while preserving coverage update/runtime service
behavior, terminal-stop reason strings, decision-event payload schema, event
ordering, token/return/direct-handoff/recovery semantics, parked
`pre_dig_align`, parked `cell_entry`, and backend support status.

Current status note after coverage effect fact private facade cleanup:
`PrimitivePlannerACTPolicy` no longer exposes the old
`_coverage_completion_facts`, `_coverage_rejection_facts`,
`_coverage_reopen_facts`, or `_coverage_terminal_facts` helper facades. Focused
coverage tests now exercise `CoverageEffectFactService` directly for those
facts. This is compatibility/test-only facade cleanup after Phase 9.85; it does
not change coverage update/runtime service behavior, decision-event payloads,
event ordering, report schemas, token/return/direct-handoff/recovery semantics,
parked `pre_dig_align`, parked `cell_entry`, or backend support status.

Current status note after Phase 9.86: the live coverage decision-event bucket
snapshot projection now lives in `CoverageReportService.bucket_snapshot(...)`
inside `testbed/planner/primitive/coverage/reports.py`. The policy shell keeps
`_coverage_bucket_snapshot(...)` only as a compatibility facade that wraps the
observation in `PrimitiveObservationFacts` and delegates to the report service.
This removes policy-owned mass/deposit/env-state bucket snapshot projection
while preserving the coverage decision-event payload schema, key names, event
ordering, task-metric fallback behavior, env-state NaN/default semantics,
debug/summary/trace schemas, coverage algorithms, parked `pre_dig_align`,
parked `cell_entry`, and backend support status.

Current status note after Phase 9.87: effect-side observation metric fact
projection now uses typed `PrimitiveObservationFacts` providers in
`RequestedEffectApplierPorts` and `PrimitiveDigRecoveryPorts`. The requested
effect applier no longer receives a policy-built `deposited_mass` callback for
`SetDumpStartDepositedMassFromObservationEffect`; failed-dig recovery no longer
receives a policy-built `mass_in_bucket` callback for failed-dig stop payloads.
`PrimitivePlannerACTPolicy` now constructs explicit
`PrimitiveObservationFacts.from_obs(obs, action_dim=int(self.action_dim))`
providers for these live effect-side boundaries. Requested-effect order,
dump-start deposited mass writeback, failed-dig payload max/event payload keys,
terminal-stop request ordering, parked `pre_dig_align`, parked `cell_entry`,
and backend support status remain unchanged.

Current status note after Phase 9.88: the coverage planning fact-source
boundary now uses typed `PrimitiveObservationFacts` for env-state and bucket
pose access. `CoveragePlanningFactService` no longer carries policy-built
`env_state` or `bucket_tip_dig_area_pose` callbacks. It receives an
`observation_facts` provider and reads `facts.env_state` for state-exemplar,
removed-depth, and remaining-depth facts, and
`facts.bucket_tip_dig_area_pose()` for entry distance while preserving the
bucket-tip preferred / bucket dig-area fallback behavior. The existing
`first_dig_qpos_delta` callback remains explicit because it still touches
parked/residual pre-dig-align target material and is not part of this live
fact-source slice. Coverage selection/scoring/effect/update behavior,
candidate score payloads, token/return/direct-handoff/recovery semantics,
parked `pre_dig_align`, parked `cell_entry`, and backend support status remain
unchanged.

Current status note after Phase-2 coverage selection/fact composition
extraction: `PrimitiveCoverageSelectionRuntime` in
`testbed/planner/primitive/coverage/selection_runtime.py` now owns
`CoverageSelectionRuntimePorts`, `CoverageSelectionConfig`,
`CoveragePlanningFactConfig`, and `CoveragePlanningFactService` construction.
`PrimitivePlannerACTPolicy` keeps typed coverage-selection runtime ports and
runtime factory as owner welds; old private coverage selection/fact helper
wrappers have been retired after production/test callers moved to
`PrimitiveCoverageSelectionRuntime` and focused service contracts. Old private
scoring/exemplar helper wrappers around the same owner chain have also been
retired; production/test callers now use the focused runtime, services/builders,
or coverage owner state directly. Coverage
candidate construction, scoring/selection algorithms,
candidate score payloads, first-dig gates, rare/recent row penalties,
state-exemplar planning, remaining-depth projection, coverage effect/update
runtime, coverage report composition, token/return behavior, public
debug/summary/trace schemas, parked `pre_dig_align`, parked `cell_entry`, and
backend support status remain unchanged.

Current status note after coverage static config factory shell cleanup:
`PrimitiveCoverageStaticConfig` in
`testbed/planner/primitive/coverage/config.py` now owns the static coverage
report, selection, planning-fact, state-exemplar, update, and runtime config
snapshot. `PrimitiveCoverageReportRuntimePorts`,
`PrimitiveCoverageSelectionRuntimePorts`, and
`PrimitiveCoverageEffectRuntimePorts` receive that static config object plus
explicit live state/callback ports. `PrimitivePlannerACTPolicy` keeps one thin
`_primitive_coverage_static_config()` weld for normalized static fields, while
the three coverage runtime port methods retain only dynamic state, cycle/skill,
observation facts, selection-service, pass-reopen, terminal-stop,
decision-event, remaining-depth, and corridor-attempt-limit wiring. Coverage
selection/scoring/fact projection, effect/update behavior, report/debug/summary/
trace schemas, token/return behavior, parked `pre_dig_align`, parked
`cell_entry`, and backend support status remain unchanged.

Current status note after shell weld classification snapshot: the remaining
`PrimitivePlannerACTPolicy` private shell surface has been classified against
the target interface in `docs/planner_policy_shell_target_interface.md`.
Coverage static config and coverage runtime ports are accepted: the policy keeps
`_primitive_coverage_static_config()` as the static snapshot weld and the
report/selection/effect runtime port methods now contain only dynamic
state/callback wiring. Token planner factory, token observation runtime, and
token planning runtime wiring are accepted shell welds because token algorithm
construction lives in `PrimitiveTokenPlannerFactory` and token runtime owners.
Decision runtime default `legacy_fsm` backend registration stays in the shell
until production backend plugin/config routing is explicitly requested. Report
composition remains visually broad but is accepted as public report-schema
source wiring; the report lane owns schema assembly. Future cleanup should not
continue by line count. The next eligible phase is backend-ready contract
closure and documentation/testing confirmation.

Current status note after backend-ready contract closure: future external
decision backends may depend on the production import contracts documented in
`docs/planner_primitive_interface_standard.md`, including decision context,
decision result/effect records, generic backend protocols, decision runtime
ports/config, backend facts source/ports, common decision facts, backend
decision input builder, and requested-effect applier contracts. They must not
depend on `PrimitivePlannerACTPolicy`, policy private methods, or design-target
documents. The package lanes under `testbed/planner/primitive/...` are guarded
against reverse imports of the policy shell. The fake backend proof remains
test-local and demonstrates generic runtime/factory selection only; no
production backend plugin/config routing or real BT/VLM/LLM backend is added.

Current status note after Phase 9.89: the non-scripted bootstrap end
fact-source boundary now uses `PrimitiveObservationFacts` and
`BootstrapStatus.from_inputs(...)` instead of direct large-policy
`_mass_in_bucket` / `_min_distance_to_dig_area` wrapper reads.
`PrimitivePlannerACTPolicy._should_end_bootstrap(...)` remains the
compatibility facade and still gives `PrimitiveScriptedBootstrapRuntimeService`
precedence when scripted bootstrap is enabled. For non-scripted modes,
first-qualified-dig-start, loaded-and-clear, disabled, and unsupported-mode
behavior are projected by the existing bootstrap status owner. Scripted
bootstrap runtime state/action/timeout behavior, reset timing, backend
fail-fast behavior, token schemas, debug/summary/trace schemas, parked
`pre_dig_align`, and parked `cell_entry` remain unchanged.

Current status note after Phase 9.90: the live per-dig tick progress update
now lives in `PrimitiveDigProgressRuntimeService`. The service reads bucket
mass through a typed `PrimitiveObservationFacts` provider, updates
`PrimitiveCycleRuntimeState.update_dig_progress(...)`, and mirrors the same
mass into `CoverageRuntimeState.coverage_current_payload_gain_kg` with the
existing max(old, mass) behavior. `PrimitivePlannerACTPolicy._update_dig_progress(...)`
remains a compatibility facade and typed port constructor. Execution-driver
tick order, plateau semantics, coverage payload max semantics, debug/summary/
trace schemas, backend fail-fast behavior, parked `pre_dig_align`, and parked
`cell_entry` remain unchanged.

Current status note after Phase 9.91, superseded by the Phase-2 execution-chain
wrapper cleanup below: the boundary-event tick source now lives
in `PrimitiveBoundaryEventRuntimeService`. The service reads
`PrimitiveExecutionRuntimeState.prev_action`, skips the boundary detector when
there is no previous action, and otherwise projects typed
`PrimitiveObservationFacts` into `BoundaryDetector.update(...)` arguments.
The later cleanup retired `PrimitivePlannerACTPolicy._tick_boundary_event(...)`;
execution-driver ports call `PrimitiveBoundaryEventRuntimeService.update(...)`
directly through typed ports. Boundary-detector metrics/event algorithms,
execution-driver tick order, prev-action finalization timing, backend fail-fast
behavior, debug/summary/trace schemas, parked `pre_dig_align`, and parked
`cell_entry` remain unchanged.

Current status note after raw observation helper facade cleanup:
`PrimitivePlannerACTPolicy` no longer exposes the old private raw observation
helper facades `_mass_in_bucket`, `_deposited_mass`,
`_min_distance_to_dig_area`, `_bucket_depth_below_dig_area_plane`,
`_bucket_depth_below_local_surface`, `_bucket_dig_area_contact_mask`,
`_env_state`, `_bucket_dig_area_cell_in_bounds_mask`, `_dig_cell_id`,
`_bucket_dig_area_pose`, or `_bucket_tip_dig_area_pose`. Tests now lock typed
`PrimitiveObservationFacts`, focused services, and direct observation inputs
instead of monkeypatching those old wrappers. This is cleanup after the
observation fact-source migrations; it does not change observation fallback
semantics, env-state indexes, task-metric precedence, boundary detector inputs,
token provider order, policy observation injected key names, coverage
algorithms, return handoff semantics, bootstrap semantics, requested-effect
semantics, report schemas, parked `pre_dig_align`, parked `cell_entry`, or
backend support status.

Current status note after the 2026-06-25 pre-dig-align restoration: the earlier
parked-runtime cleanup decision has been superseded for `pre_dig_align` only.
Enabled `pre_dig_align` config is valid again and remains opt-in. The restored
path is owned by focused primitive lanes: execution runtime/action,
legacy-FSM active branch, requested effects, failed-dig recovery, return
handoff, reset lifecycle, and live report projection. `PrimitivePlannerACTPolicy`
remains a composition shell and must not regain old private `_pre_dig_align_*`,
`_should_pre_dig_align*`, `_restart_pre_dig_align`, or
`_try_replan_pre_dig_align_handoff` methods. This restoration does not touch
parked `cell_entry`, removed 5P runtime, behavior-tree/VLM/LLM support, plugin
routing, token dimensions, reason strings, branch order, checkpoint selection,
or default disabled runtime config. The maturity statement remains: default
legacy FSM backendified with focused services / shared backend decision
input/facts/factory; BT/VLM/LLM backends remain unsupported fail-fast.

Current status note after parked pre-dig-align private facade cleanup, retained
after restoration:
`PrimitivePlannerACTPolicy` no longer exposes
`_primitive_pre_dig_align_compatibility_runtime_state` or the old
`_pre_dig_align_*` runtime field facades for counters, target/error arrays,
entry/surface diagnostics, readiness flags, timeout reason, and surface-guard
state. `PrimitiveResetLifecycleState.as_policy_field_updates()` no longer emits
`_pre_dig_align_state` or those old private runtime fields. Disabled public
debug/summary/report schema compatibility remains projected through
`PrimitivePreDigAlignCompatibilityRuntimeState.fresh(...).to_report_status(...)`
and `PrimitivePreDigAlignReportStatus`; enabled runtime now projects from live
focused runtime state.

Current status note after parked pre-dig-align false predicate facade cleanup,
retained after restoration:
`PrimitivePlannerACTPolicy` no longer exposes
`_should_pre_dig_align_before_dig()` or
`_should_pre_dig_align_after_failed_dig()`. Test coverage now asserts those
private predicate facades are absent and removes monkeypatches from decision,
cycle, and AGX coverage tests. Direct return handoff now chooses `pre_dig_align`
only through the focused runtime predicate and explicit return-handoff ports;
public disabled pre-dig schema compatibility remains unchanged.

Hard constraint for future conclusions and executor prompts: protection is a
constraint, not the objective. Each next slice must be the most effective
bounded move toward the interface standard, not merely the safest smallest
cleanup. If a candidate only moves a tiny compatibility dictionary or facade
without reducing a broader stable boundary, the refactor thread must stop,
state that risk explicitly in its conclusion, and choose a larger bounded
target before dispatch.

Pre-dig restoration rule: the explicit user re-approval gate has now superseded
the parked cleanup decision for `pre_dig_align`. Treat it as an opt-in runtime
capability, while keeping default configs disabled and keeping parked
`cell_entry` cleanup separate. Do not dispatch implementation slices that
promote `cell_entry`, 5P, behavior-tree/VLM surfaces, plugin routes, or
unapproved default-mainline pre-dig behavior.

The current `pre_dig_align` restoration route has completed unit-level Slice
1-8 closure and is ready for Unity validation. Older Phase 7/8 notes below
remain as historical refactor context, not the current pre-dig implementation
route. Slice 4 status records have been established through `TokenStatus`;
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
`pre_dig_align`, which was legacy parking because the selected successful
evidence packet classified `gate.pre_dig_align` as
`dead-candidate` / `retain-legacy-parking`. The subsequent parked cleanup
removed that runtime branch while retaining disabled report/schema
compatibility.

Stop further Slice 7 code migration at this verified boundary unless the user
approves a new scope. The 5P runtime compatibility audit has been resolved by
the Phase 9.32 cleanup-approved removal of `PrimitivePlannerACT5PPolicy`; old
behavior remains available only through git history. This statement now applies
to removed 5P behavior and parked `cell_entry`, not to restored opt-in
`pre_dig_align`. For `pre_dig_align`, valid remaining scopes are Unity
validation, validation-log/docs closure, and focused bug fixes if that
validation exposes a runtime mismatch. Do not change branch order, reason
strings, token dimensions, default-disabled config behavior, or apply unrelated
effects through the backend boundary without a separate evidence and
compatibility decision.

The next approved planning scope is Phase 8 effect-boundary design, recorded in
`docs/planner_effect_boundary_design.md`. It should govern later return
direct-handoff, legacy parking, and backend-selection work by
classifying each path as facts, decision, requested effect, reporting,
compatibility, or legacy parking before any code migration.
