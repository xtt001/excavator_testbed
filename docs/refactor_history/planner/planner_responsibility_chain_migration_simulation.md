# Primitive Planner Responsibility-Chain Migration Simulation

Status: **historical design workbook, not an implementation plan**.

This document records design-only dry runs for future primitive-planner
responsibility-chain migrations. It is used before dispatching implementation
work so the planner can choose a bounded chain, expected import changes, and
behavior locks. It does not move files or change code.

## Simulation Protocol

For each candidate, fill these fields before implementation:

- current shell touch points;
- target package lane and owner;
- old import classification;
- expected test movement;
- behavior locks;
- stop conditions;
- recommended verification.

The simulation must not decide new semantics. If a candidate needs semantic
confirmation, stop and ask before implementation.

## Candidate A: Requested Effects And Return Handoff

Target lane:

- `testbed.planner.primitive.effects`

Current shape:

- requested-effect dispatch already lives in `PrimitiveRequestedEffectRuntime`
  and `RequestedEffectApplier`;
- return direct-handoff and handoff-readiness code has focused services and a
  runtime boundary;
- `PrimitivePlannerACTPolicy` should only invoke the focused runtime through
  typed execution ports.

Simulated move:

- move `primitive_effects.py` to `primitive/effects/requested.py`;
- move return-handoff runtime/service files under `primitive/effects/` or a
  dedicated `primitive/return_handoff/` lane only after deciding where
  `PrimitiveReturnRuntimeState` belongs;
- keep old root modules as re-export facades unless import audit proves they
  are internal-only;
- update tests to import the focused effect runtime, not policy-private effect
  wrappers.

Behavior locks:

- requested-effect application order;
- validation error strings;
- skill switch reason strings;
- return/direct-handoff timing;
- terminal-stop and failed-dig recovery interactions;
- public debug/summary/trace schemas.

Stop conditions:

- the move requires importing `PrimitivePlannerACTPolicy` into effects code;
- return state must be duplicated between execution and effects lanes;
- tests require restoring old policy-private effect wrappers.

Verification:

- `tests/test_primitive_effects.py`
- `tests/test_primitive_return_handoff.py`
- `tests/test_primitive_cycle_state.py`
- runtime smoke tests;
- selected AGX return/start-envelope subset;
- import smoke for any old facade.

Simulation verdict:

- plausible as a first post-seed implementation slice if the return-state lane
  decision is made up front;
- do not combine with token or coverage migration.

## Candidate B: Token Observation And Planning

Target lane:

- `testbed.planner.primitive.token`

Current shape:

- token runtime state, token runtime sequencing, token observation runtime, and
  dig/return token-planning services already exist;
- token planner factory construction and prior helper details are not public
  shell responsibilities;
- policy shell still wires token runtimes and low-level policy observation
  dependencies.

Simulated move:

- move token state/status/tokens/runtime modules into `primitive/token/`;
- move token observation and token planning runtimes into the same lane;
- keep old root modules as re-export facades during one migration phase;
- update production imports to new lane paths in the same slice;
- update tests to lock token owners rather than policy-private token helpers.

Behavior locks:

- token order and dimensions;
- dig-cut token source/fallback strings;
- dig-depth-profile prior behavior;
- return-target, return-relocate, and return-start-envelope token outputs;
- observation-injection clear/apply timing;
- reset defaults and public report fields.

Stop conditions:

- token move changes token schema or source strings;
- token lane starts reading coverage internals directly instead of typed state
  owner/service interfaces;
- policy shell gains new token factory logic as part of the relocation.

Verification:

- token runtime/state/planning tests;
- debug/summary/trace tests for token fields;
- selected AGX dig-cut/depth-profile/return-token subset;
- compileall for moved token modules and facades.

Simulation verdict:

- high-value and coherent, but wider than effects/return-handoff because it
  touches token schema and public reports;
- suitable after package seed if verification budget includes selected AGX and
  report tests.

## Candidate C: Coverage Selection, Effects, And Reports

Target lane:

- `testbed.planner.primitive.coverage`

Current shape:

- coverage already has focused state, selection service, planning facts, effect
  runtime, and report runtime;
- many tests inspect coverage internals and selected AGX behavior;
- package layout is still flat enough that coverage imports can look like
  generic primitive-planner helpers rather than a lane.

Simulated move:

- do not move all coverage code in one blind bulk slice;
- choose one subchain first: coverage report projection, coverage selection
  runtime, or coverage effect runtime;
- keep old root modules as re-export facades until production imports and tests
  use the lane path;
- use `primitive.coverage` as the package lane, but preserve existing service
  objects and state owners.

Behavior locks:

- corridor selection, scoring, and candidate ordering;
- completion/rejection/reopen/terminal-stop behavior;
- low-productivity and pass-index behavior;
- state-exemplar payloads and decision-event payloads;
- coverage debug/summary/trace fields;
- selected AGX coverage subset.

Stop conditions:

- the slice changes scoring thresholds or candidate order;
- coverage reports lose public compatibility keys;
- coverage lane imports policy shell or broad runtime bags;
- too many coverage subchains move at once to localize failures.

Verification:

- coverage selection/facts/state/effects/report suites;
- selected AGX coverage subset;
- debug/summary/trace tests;
- source checks for policy imports and old private wrapper references.

Simulation verdict:

- highest architectural payoff but also highest blast radius;
- use a subchain simulation before implementation, not a one-shot coverage lane
  move.

## Candidate D: Report And Compatibility Payloads

Target lanes:

- `testbed.planner.primitive.report`
- `testbed.planner.primitive.compatibility`

Current shape:

- public `debug_state`, `rollout_summary`, and `planner_trace` methods already
  route through focused report runtimes;
- parked `cell_entry` and `pre_dig_align` compatibility report owners remain
  public-schema surfaces but not mainline runtime behavior.

Simulated move:

- move report runtime and report schema builders under `primitive/report/`;
- move parked compatibility state/report owners under
  `primitive/compatibility/`;
- keep old paths as facades until public report tests and compatibility tests
  target the new owners;
- do not restore parked runtime behavior.

Behavior locks:

- public debug/summary/trace key names and default values;
- disabled `cell_entry` and `pre_dig_align` schema compatibility;
- enabled pre-dig fail-fast behavior;
- report ordering where tests assert it.

Stop conditions:

- a parked path becomes a backend fact, token contract, or runtime branch;
- report move changes public payload shape;
- compatibility modules become mainline dependencies for non-report behavior.

Verification:

- debug report, rollout summary, planner trace tests;
- `cell_entry` and `pre_dig_align` compatibility tests;
- selected AGX report-sensitive subset if payload fields are touched.

Simulation verdict:

- useful after token/coverage imports settle, or as a smaller slice if public
  schema tests are strong and import impact is contained.

## Candidate E: Adapter Config Normalization

Target lane:

- `testbed.planner.primitive.config`

Current shape:

- `primitive_adapter_config.py` is large, but its responsibility is coherent:
  constructor config normalization, compatibility field updates, and focused
  config object construction;
- large file size alone is not a reason to split it.

Simulated move:

- first move the module under `primitive/config/adapter.py` with a root facade;
- split only if a stable config owner emerges, such as static backend config,
  return-handoff config, or token config;
- do not split by constructor parameter groups if that only creates pass-through
  files.

Behavior locks:

- public constructor defaults;
- config validation errors;
- legacy policy-field update compatibility;
- one source of truth for token/backend/return config semantics.

Stop conditions:

- split duplicates config semantics across train/eval/rollout paths;
- new config files are named after experiments or one-off requirements;
- production behavior changes because defaults move.

Verification:

- adapter config tests;
- focused tests for every generated config object;
- compileall and source checks for duplicated constants.

Simulation verdict:

- not the first responsibility-chain migration unless config growth blocks a
  concrete lane owner;
- acceptable as relocation-only after higher-risk runtime lanes are stable.

## Parallel Inventory Plan

The next read-only planner round may run these inventories in parallel:

- token lane import and behavior-lock inventory;
- coverage subchain inventory, split into selection/effects/reports;
- report/compatibility payload inventory;
- effects/return-handoff state-owner placement inventory.

Each inventory returns facts only: current files, target lane, old import
classification, tests to move, behavior locks, and blockers. The planner then
chooses one implementation slice.

## Current Recommendation

After the decision/facts package seed is closed, the best next implementation
candidate is likely one of:

1. requested effects plus return-handoff relocation, if the return-state lane is
   decided first;
2. token lane relocation, if token schema/report tests are selected as the
   verification bundle.

Coverage should be simulated in parallel but implemented only after its
subchain boundary is narrowed.
