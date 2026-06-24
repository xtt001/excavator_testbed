# Primitive Planner Package Layout Target

Status: **active package-layout design target, not an implementation plan**.

This document describes how the primitive planner code should eventually be
grouped so the repository structure reflects
`docs/planner_execution_abstraction_flow.svg`. It is a source-of-truth design
artifact for future relocation slices. It does not move files, change imports,
or alter runtime behavior by itself.

Companion responsibility-chain design references:

- `docs/planner_responsibility_chain_migration_design.md`
- `docs/planner_responsibility_chain_migration_simulation.md`

## Purpose

The current `testbed/planner/` package contains many focused
`primitive_*.py` modules. Those modules have much better ownership than the old
monolithic planner, but the package still reads as a flat migration-era list
rather than the architecture shown in the SVG.

The target is package-level lane grouping:

- public API shell remains externally stable;
- execution owns tick order and side-effect sequencing;
- facts own read-only state and observation projections;
- decision owns generic backend contracts and default legacy adapter wiring;
- effects own requested mutation application;
- token, coverage, return-handoff, and report owners stay domain-focused;
- parked compatibility surfaces are explicit instead of mixed into mainline
  runtime packages.

Line count is not the objective. Package layout changes are justified only when
they make ownership, import direction, and future migration boundaries clearer.

## Non-Goals

- no bulk `git mv` of all primitive modules in one slice;
- no behavior changes, threshold changes, branch-order changes, reason-string
  changes, token schema changes, public debug/summary/trace schema changes, or
  reset-timing changes;
- no production backend plugin/config routing system;
- no real BT/VLM/LLM backend implementation;
- no removal of current public imports without an explicit compatibility phase;
- no package move whose only purpose is line-count reduction;
- no new broad `blackboard`, planner-self port, callback bag, or config bag.

## Target Package Shape

The target package name is `testbed.planner.primitive`. Old
`testbed.planner.primitive_*` modules are not automatically preserved. Each old
path must be classified before the move:

- `public-compat`: keep a thin re-export facade until explicitly retired;
- `cross-module-compat`: keep a temporary re-export facade while consumers are
  migrated in later slices;
- `internal-only`: move the implementation and update all imports in the same
  slice; no old facade is needed;
- `test-only`: update tests to the focused owner or remove the old-path test;
- `dead-candidate`: remove rather than re-export, after approval.

This means implementation slices may update imports and avoid old facades when
the path is proven internal-only. Re-export is a compatibility tool, not the
default goal.

```text
testbed/planner/primitive/
  __init__.py
  shell/
    __init__.py
    runtime_kernel.py
  config/
    __init__.py
    adapter.py
  execution/
    __init__.py
    runtime.py
    state.py
    reset_lifecycle.py
    tick_finalization.py
    action_dispatch.py
    boundary_event.py
    dig_progress.py
    skill_lifecycle.py
    scripted_bootstrap.py
  facts/
    __init__.py
    observation.py
    decision.py
    backend.py
  decision/
    __init__.py
    contracts.py
    runtime.py
    input.py
    capabilities.py
    backends/
      __init__.py
      legacy_fsm.py
      legacy_capability_provider.py
  effects/
    __init__.py
    requested.py
    return_handoff.py
  token/
    __init__.py
    state.py
    status.py
    tokens.py
    runtime.py
    observation_runtime.py
    planning_runtime.py
    factory.py
    dig_planning.py
    return_planning.py
  coverage/
    __init__.py
    config.py
    state.py
    status.py
    selection.py
    selection_runtime.py
    facts.py
    effects.py
    effect_runtime.py
    reports.py
    report_runtime.py
    exemplars.py
  report/
    __init__.py
    runtime.py
    debug_report.py
    rollout_summary.py
    planner_trace.py
  compatibility/
    __init__.py
    cell_entry.py
    pre_dig_align.py
```

The policy class itself can remain at
`testbed/policies/hybrid/primitive_planner.py` for public import stability. The
target is to make that file a shell over lane-shaped planner packages, not to
rename the public policy path.

## SVG Lane Mapping

| SVG lane / box | Target package | Ownership rule |
| --- | --- | --- |
| External layer / public Policy API | `testbed.policies.hybrid.primitive_planner` plus `primitive.shell` | Expose constructor, `reset`, `predict`, `debug_state`, `rollout_summary`, and `planner_trace`; no domain internals. |
| PrimitivePlannerExecutionBase | `primitive.execution` | Own prepare/decide/apply/dispatch/finalize tick order and runtime state lifecycle. |
| Capability Port | `primitive.facts` plus domain facts modules | Own read-only observation, backend, decision, and capability facts. |
| Decision Backends | `primitive.decision` | Own generic backend protocols, runtime selection, backend input, and default legacy-FSM adapter containment. |
| DecisionResult / PlannerEffect application | `primitive.effects` | Own requested-effect application and effect-side services. |
| Token state and token assembly | `primitive.token` | Own token state, token planning, observation injection, and token planner factories. |
| Coverage planning/effects/reports | `primitive.coverage` | Own corridor state, selection, scoring, facts, updates, effects, and coverage report projection. |
| Stable outputs and compatibility reports | `primitive.report` and `primitive.compatibility` | Own public debug/summary/trace assembly and parked compatibility payloads. |

## Current File Mapping

The table gives the likely target lane and a conservative migration note. The
note is not a blanket requirement to preserve old imports. If a relocation audit
proves a path is internal-only and all imports can be updated in the same slice,
prefer direct migration without a re-export facade.

| Current file | Target package path | Migration note |
| --- | --- | --- |
| `primitive_runtime_kernel.py` | `primitive/shell/runtime_kernel.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_adapter_config.py` | `primitive/config/adapter.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated without splitting config semantics. |
| `primitive_execution.py` | `primitive/execution/runtime.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_execution_state.py` | `primitive/execution/state.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_reset_lifecycle.py` | `primitive/execution/reset_lifecycle.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_tick_finalization.py` | `primitive/execution/tick_finalization.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_action_dispatch.py` | `primitive/execution/action_dispatch.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_boundary_event.py` | `primitive/execution/boundary_event.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_dig_progress.py` | `primitive/execution/dig_progress.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_dig_recovery.py` | `primitive/execution/dig_recovery.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_cycle_state.py` | `primitive/execution/cycle_state.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_skill_lifecycle.py` | `primitive/execution/skill_lifecycle.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_scripted_bootstrap.py` | `primitive/execution/scripted_bootstrap.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_capabilities.py` | `primitive/facts/capabilities.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated without splitting transition facts. |
| `primitive_observation.py` | `primitive/facts/observation.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_backend_facts.py` | `primitive/facts/backend.py` | Good first candidate after docs because backend-ready contracts are already closed. |
| `primitive_decision_facts.py` | `primitive/facts/decision.py` | Move with backend facts or decision input, not separately if imports become circular. |
| `primitive_decision_context.py` | `primitive/decision/context.py` | Re-export old path. |
| `primitive_decision.py` | `primitive/decision/contracts.py` | Re-export old path. |
| `primitive_decision_runtime.py` | `primitive/decision/runtime.py` | Good first candidate; generic runtime is small and stable. |
| `primitive_backend_input.py` | `primitive/decision/input.py` | Move with decision runtime/facts. |
| `primitive_backend.py` | `primitive/decision/backends/legacy_fsm.py` plus `primitive/decision/backend_protocols.py` if needed | Split generic protocols from concrete legacy-FSM adapter only when that split reduces import coupling. |
| `primitive_decision_capabilities.py` | `primitive/decision/capabilities.py` | Move with legacy backend capability composition. |
| `primitive_capability_provider.py` | `primitive/decision/backends/legacy_capability_provider.py` | It is legacy-FSM transition-status provider, not a generic shell service. |
| `primitive_effects.py` | `primitive/effects/requested.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_return_handoff.py` | `primitive/effects/return_handoff.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_return_handoff_runtime.py` | `primitive/effects/return_handoff_runtime.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_return_state.py` | `primitive/execution/return_state.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_tokens.py` | `primitive/token/tokens.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_token_state.py` | `primitive/token/state.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_token_status.py` | `primitive/token/status.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_token_runtime.py` | `primitive/token/runtime.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_token_observation_runtime.py` | `primitive/token/observation_runtime.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_token_planning_runtime.py` | `primitive/token/planning_runtime.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_dig_token_planning.py` | `primitive/token/dig_planning.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_return_token_planning.py` | `primitive/token/return_planning.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_coverage.py` | `primitive/coverage/selection.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_coverage_state.py` | `primitive/coverage/state.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_coverage_status.py` | `primitive/coverage/status.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_coverage_facts.py` | `primitive/coverage/facts.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_coverage_selection_runtime.py` | `primitive/coverage/selection_runtime.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_coverage_updates.py` | `primitive/coverage/effects.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_coverage_effect_runtime.py` | `primitive/coverage/effect_runtime.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_coverage_reports.py` | `primitive/coverage/reports.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_coverage_report_runtime.py` | `primitive/coverage/report_runtime.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_coverage_exemplars.py` | `primitive/coverage/exemplars.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_report_runtime.py` | `primitive/report/runtime.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_debug_report.py` | `primitive/report/debug_report.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_rollout_summary.py` | `primitive/report/rollout_summary.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_planner_trace.py` | `primitive/report/planner_trace.py` | Moved as `internal-only`; old root path removed after in-repo imports migrated. |
| `primitive_cell_entry_state.py` | `primitive/compatibility/cell_entry.py` | Moved as `internal-only`; public report schema compatibility is preserved by the moved owner. |
| `primitive_pre_dig_align_state.py` | `primitive/compatibility/pre_dig_align.py` | Moved as `internal-only`; parked public schema compatibility is preserved by the moved owner. |
| `cell_entry.py` | `primitive/compatibility/cell_entry_legacy.py` or remain root | Move only after confirming non-primitive consumers. |

General planner helpers such as `evidence_trace.py`, `golden_window_parity.py`,
`fixed_sequence_planner.py`, `rule_planner.py`, `scenario_manifest.py`,
`corridor_servo.py`, and `types.py` are not automatically part of the primitive
package move. They should stay in the root planner package unless a later slice
proves a stable primitive-lane owner.

### Seed Relocation Status

The primitive decision/facts/backend-ready lane has been seeded under
`testbed/planner/primitive/`:

- `primitive_backend_facts.py` moved to `primitive/facts/backend.py` and the
  old root module is removed as `internal-only`;
- `primitive_decision_facts.py` moved to `primitive/facts/decision.py` and the
  old root module is removed as `internal-only`;
- `primitive_decision_runtime.py` moved to `primitive/decision/runtime.py` and
  the old root module is removed as `internal-only`;
- `primitive_backend_input.py` moved to `primitive/decision/input.py` and the
  old root module is removed as `internal-only`;
- `primitive_backend.py` moved to `primitive/decision/backends/legacy_fsm.py`
  and the old root module is removed as `internal-only`;
- `primitive_decision_capabilities.py` moved to
  `primitive/decision/capabilities.py` and the old root module is removed as
  `internal-only`;
- `primitive_capability_provider.py` moved to
  `primitive/decision/backends/legacy_capability_provider.py` and the old root
  module is removed as `internal-only`;
- `primitive_decision.py` is now a `public-compat` thin re-export facade over
  `primitive/decision/contracts.py`;
- `primitive_decision_context.py` is now a `cross-module-compat` thin
  re-export facade over `primitive/decision/context.py`.

In-repo production and focused-test imports for this lane use the new package
paths. Historical docs and old rollout-log entries may still name the previous
root modules as historical facts.

The primitive effects / return-handoff lane has also been seeded:

- `primitive_effects.py` moved to `primitive/effects/requested.py` and the old
  root module is removed as `internal-only`;
- `primitive_return_handoff.py` moved to
  `primitive/effects/return_handoff.py` and the old root module is removed as
  `internal-only`;
- `primitive_return_handoff_runtime.py` moved to
  `primitive/effects/return_handoff_runtime.py` and the old root module is
  removed as `internal-only`.

In-repo production and focused-test imports for this lane use the new package
paths. No old root facade is retained for these three modules.

The primitive token lane has been seeded in the same larger relocation batch:

- `primitive_tokens.py` moved to `primitive/token/tokens.py` and the old root
  module is removed as `internal-only`;
- `primitive_token_state.py` moved to `primitive/token/state.py` and the old
  root module is removed as `internal-only`;
- `primitive_token_status.py` moved to `primitive/token/status.py` and the old
  root module is removed as `internal-only`;
- `primitive_token_runtime.py` moved to `primitive/token/runtime.py` and the
  old root module is removed as `internal-only`;
- `primitive_token_observation_runtime.py` moved to
  `primitive/token/observation_runtime.py` and the old root module is removed
  as `internal-only`;
- `primitive_token_planning_runtime.py` moved to
  `primitive/token/planning_runtime.py` and the old root module is removed as
  `internal-only`;
- `primitive_dig_token_planning.py` moved to `primitive/token/dig_planning.py`
  and the old root module is removed as `internal-only`;
- `primitive_return_token_planning.py` moved to
  `primitive/token/return_planning.py` and the old root module is removed as
  `internal-only`.
- `primitive/token/factory.py` now owns focused token planner factory
  construction from explicit static token config; policy-private token planner
  factory/proxy methods are retired.

In-repo production and focused-test imports for this lane use the new package
paths. No old root facade is retained for these token modules.

The primitive coverage lane has been seeded in the next larger relocation
batch:

- `primitive_coverage.py` moved to `primitive/coverage/selection.py` and the
  old root module is removed as `internal-only`;
- `primitive_coverage_state.py` moved to `primitive/coverage/state.py` and the
  old root module is removed as `internal-only`;
- `primitive_coverage_status.py` moved to `primitive/coverage/status.py` and
  the old root module is removed as `internal-only`;
- `primitive_coverage_facts.py` moved to `primitive/coverage/facts.py` and the
  old root module is removed as `internal-only`;
- `primitive_coverage_selection_runtime.py` moved to
  `primitive/coverage/selection_runtime.py` and the old root module is removed
  as `internal-only`;
- `primitive_coverage_updates.py` moved to `primitive/coverage/effects.py` and
  the old root module is removed as `internal-only`;
- `primitive_coverage_effect_runtime.py` moved to
  `primitive/coverage/effect_runtime.py` and the old root module is removed as
  `internal-only`;
- `primitive_coverage_reports.py` moved to `primitive/coverage/reports.py` and
  the old root module is removed as `internal-only`;
- `primitive_coverage_report_runtime.py` moved to
  `primitive/coverage/report_runtime.py` and the old root module is removed as
  `internal-only`;
- `primitive_coverage_exemplars.py` moved to
  `primitive/coverage/exemplars.py` and the old root module is removed as
  `internal-only`.

The follow-up coverage static config cleanup added
`primitive/coverage/config.py` as the lane owner for static report,
selection/planning-fact/exemplar, and effect/runtime config snapshots. Policy
runtime port methods keep dynamic state/callback welds, while static
`coverage_*` and `dig_cut_*` field expansion is centralized in the policy's
thin static-config weld.

The primitive report and parked compatibility lanes were seeded in the same
larger relocation batch:

- `primitive_report_runtime.py` moved to `primitive/report/runtime.py` and the
  old root module is removed as `internal-only`;
- `primitive_debug_report.py` moved to `primitive/report/debug_report.py` and
  the old root module is removed as `internal-only`;
- `primitive_rollout_summary.py` moved to `primitive/report/rollout_summary.py`
  and the old root module is removed as `internal-only`;
- `primitive_planner_trace.py` moved to `primitive/report/planner_trace.py` and
  the old root module is removed as `internal-only`;
- `primitive_cell_entry_state.py` moved to
  `primitive/compatibility/cell_entry.py` and the old root module is removed as
  `internal-only`;
- `primitive_pre_dig_align_state.py` moved to
  `primitive/compatibility/pre_dig_align.py` and the old root module is removed
  as `internal-only`.

In-repo production and focused-test imports for these lanes use the new package
paths. No old root facade is retained for the coverage, report, or parked
compatibility modules. Public debug/summary/trace schema compatibility remains
the responsibility of the moved report and compatibility owners.

The primitive config, shell, execution, and facts-observation lanes were seeded
in the final large primitive-root relocation batch:

- `primitive_adapter_config.py` moved to `primitive/config/adapter.py` and the
  old root module is removed as `internal-only`;
- `primitive_runtime_kernel.py` moved to `primitive/shell/runtime_kernel.py`
  and the old root module is removed as `internal-only`;
- `primitive_execution.py` moved to `primitive/execution/runtime.py` and the
  old root module is removed as `internal-only`;
- `primitive_execution_state.py` moved to `primitive/execution/state.py` and
  the old root module is removed as `internal-only`;
- `primitive_cycle_state.py` moved to `primitive/execution/cycle_state.py` and
  the old root module is removed as `internal-only`;
- `primitive_return_state.py` moved to `primitive/execution/return_state.py`
  and the old root module is removed as `internal-only`;
- `primitive_reset_lifecycle.py` moved to
  `primitive/execution/reset_lifecycle.py` and the old root module is removed
  as `internal-only`;
- `primitive_tick_finalization.py` moved to
  `primitive/execution/tick_finalization.py` and the old root module is
  removed as `internal-only`;
- `primitive_action_dispatch.py` moved to
  `primitive/execution/action_dispatch.py` and the old root module is removed
  as `internal-only`;
- `primitive_boundary_event.py` moved to
  `primitive/execution/boundary_event.py` and the old root module is removed as
  `internal-only`;
- `primitive_dig_progress.py` moved to
  `primitive/execution/dig_progress.py` and the old root module is removed as
  `internal-only`;
- `primitive_dig_recovery.py` moved to
  `primitive/execution/dig_recovery.py` and the old root module is removed as
  `internal-only`;
- `primitive_skill_lifecycle.py` moved to
  `primitive/execution/skill_lifecycle.py` and the old root module is removed
  as `internal-only`;
- `primitive_scripted_bootstrap.py` moved to
  `primitive/execution/scripted_bootstrap.py` and the old root module is
  removed as `internal-only`;
- `primitive_capabilities.py` moved whole to
  `primitive/facts/capabilities.py` and the old root module is removed as
  `internal-only`;
- `primitive_observation.py` moved to `primitive/facts/observation.py` and the
  old root module is removed as `internal-only`.

In-repo production and focused-test imports for these lanes use the new package
paths. No old root facade is retained for the config, shell, execution,
return-state/recovery, scripted-bootstrap, facts-capability, or observation
modules. The public policy class path remains
`testbed.policies.hybrid.primitive_planner`, and only
`primitive_decision.py` / `primitive_decision_context.py` remain as accepted
thin root facades.

## Import Migration Strategy

Each relocation slice should use this sequence:

1. create the target package and target module;
2. move the implementation to the target module;
3. classify the old import path as `public-compat`, `cross-module-compat`,
   `internal-only`, `test-only`, or `dead-candidate`;
4. for `public-compat` or `cross-module-compat`, replace the old module with a
   thin re-export facade using the same `__all__`;
5. for `internal-only`, update all production imports to the target path in the
   same slice and remove the old module;
6. update focused tests to prefer the target path unless the test is explicitly
   checking old-path compatibility;
7. run compile, focused tests, selected AGX when relevant, guards, and
   `git diff --check`.

Temporary re-export facades should not emit runtime warnings during normal
tests. A warning policy can be added later after production and test imports are
mostly migrated.

## Import Direction Rules

Allowed direction:

```text
public policy shell
  -> primitive.shell / primitive.execution
  -> primitive.decision / primitive.effects / primitive.token / primitive.coverage / primitive.report
  -> primitive.facts and focused state/config owners
```

Forbidden direction:

- any `primitive.*` package importing `PrimitivePlannerACTPolicy`;
- generic decision runtime importing concrete coverage/token/report runtimes;
- facts modules importing execution/effects/report modules;
- compatibility modules becoming mainline dependencies;
- old re-export facades becoming new production owners.

Cross-domain coordination should use typed ports, state owners, and service
interfaces. If a package move requires importing planner `self`, a broad dict,
or a callback bag, reject the move and redesign the owner.

## Recommended Migration Order

1. **Decision/facts package seed.** Move the already-stabilized backend facts,
   decision facts, generic decision runtime, backend input, and default legacy
   backend adapter behind `primitive.facts` and `primitive.decision`.
   This has the clearest current contract and fake-backend readiness proof.
2. **Requested effects / return handoff.** Move requested-effect and
   return-handoff composition after decision/facts imports are stable.
3. **Token package.** Move token state, token planner factories, token planning,
   and token observation runtime as one lane after import classification.
4. **Coverage package.** Move coverage state, selection, effects, reports, and
   facts. This is a high-value lane but should follow the lower-risk package
   seed because many tests inspect coverage internals.
5. **Report and compatibility packages.** Move public report composition and
   parked `cell_entry` / `pre_dig_align` owners once coverage/token imports are
   stable.
6. **Shell cleanup.** Keep the public policy path stable; remove only old
   re-export facades that are proven unused or explicitly classified as
   test-only/dead-candidate.

This order may be revised if a target lock, import-cycle audit, or behavior
contract shows a lower-risk first slice. Do not let executor threads choose a
different order without planner approval.

The responsibility-chain migration design and simulation documents should be
used before selecting a non-trivial lane implementation. Package relocation is
the layout boundary; responsibility-chain simulation is the ownership and
behavior-risk boundary.

## Slice Acceptance Criteria

A package relocation slice is accepted only when all of these are true:

- moved files map to one target lane and one stable responsibility;
- old import paths still work or are explicitly classified and approved for
  removal;
- behavior contracts remain unchanged;
- production code imports the new target owner where appropriate;
- tests no longer protect old private wrappers unless the test is explicitly a
  compatibility test;
- source checks show no planner-self, blackboard, callback-bag, or broad config
  bag in the new package;
- docs and rollout log record the relocation boundary and compatibility policy.

Minimum verification for a relocation slice:

- focused tests for the moved package;
- import smoke for old and new paths;
- selected AGX subset when the moved lane affects token, coverage, return, or
  decision behavior;
- `python -m compileall` for moved modules and import facades;
- both planner refactor guards;
- `git diff --check`.

## Open Decisions For Future Planner Slices

- Whether generic backend protocols should stay in
  `primitive.decision.contracts` or split into
  `primitive.decision.backend_protocols` should be decided when moving
  `primitive_backend.py`; avoid a split if it only creates pass-through files.
- Whether `cell_entry.py` should move under primitive compatibility or remain a
  root legacy helper depends on non-primitive import usage at migration time.
