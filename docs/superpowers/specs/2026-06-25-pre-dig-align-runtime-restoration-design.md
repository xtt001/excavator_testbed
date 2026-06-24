# Pre-Dig-Align Runtime Restoration Design

Status: user-approved design target, implementation not started.

This document specifies how to restore `pre_dig_align` runtime behavior under
the current SVG-aligned primitive planner package structure. It is a design and
execution contract for the next implementation slice. It is not a production
backend import contract, and it does not define behavior-tree, VLM, or LLM
backend support.

## Decision

Restore `pre_dig_align` as an opt-in primitive runtime capability.

The restoration is justified by fresh Unity rollout evidence: the current
tracked config with `pre_dig_align.enabled=false` failed in the current HEAD and
in the parent baseline with matching summary fields, while older YuLong v2.4.5
qc6 runs using the same checkpoint family and `pre_dig_align.enabled=true`
reached successful or high-payload behavior. The current package refactor did
not introduce the failure, but the evidence is strong enough to reclassify
`pre_dig_align` from permanently removed runtime material to a user-approved
runtime capability.

The default config behavior should remain unchanged unless a specific eval
config is intentionally edited. Enabled `pre_dig_align` configs should become
valid again only after the runtime chain is restored.

## Non-Goals

- Do not revert the old implementation into
  `testbed/policies/hybrid/primitive_planner.py`.
- Do not make `pre_dig_align` a default mainline requirement.
- Do not add behavior-tree, VLM, LLM, plugin routing, or external backend
  production support.
- Do not change checkpoint selection, token dimensions, token order, public
  report keys, reason strings, branch order, reset timing, or semantic
  thresholds except where explicitly required to restore the old
  `pre_dig_align` behavior.
- Do not restore `cell_entry` or 5P runtime behavior in this slice.

## Architecture Placement

The restored runtime belongs in the execution lane:

- New focused owner:
  `testbed/planner/primitive/execution/pre_dig_align.py`
- Existing compatibility/report state:
  `testbed/planner/primitive/compatibility/pre_dig_align.py`
- Action dispatch integration:
  `testbed/planner/primitive/execution/action_dispatch.py`
- Legacy FSM decision integration:
  `testbed/planner/primitive/decision/backends/legacy_fsm.py`
  and its capability/facts inputs
- Failed-dig recovery integration:
  `testbed/planner/primitive/execution/dig_recovery.py`
- Return direct-handoff integration:
  `testbed/planner/primitive/effects/return_handoff.py`
  and `testbed/planner/primitive/effects/return_handoff_runtime.py`
- Report projection integration:
  `testbed/planner/primitive/report/runtime.py`
- Public shell wiring only:
  `testbed/policies/hybrid/primitive_planner.py`

`PrimitivePlannerACTPolicy` remains the external API shell and composition root.
It may construct config/state/ports and call the new service, but it must not
own restored algorithm logic or reintroduce policy-private
`_pre_dig_align_*` methods.

## Restored Service Shape

Create a focused execution module with explicit dataclasses:

- `PrimitivePreDigAlignRuntimeConfig`
- `PrimitivePreDigAlignRuntimeState`
- `PrimitivePreDigAlignPorts`
- `PrimitivePreDigAlignService`

The service owns these algorithms from the old implementation:

- `should_pre_dig_align_before_dig`
- `should_pre_dig_align_after_failed_dig`
- `surface_guard_triggered_for_state`
- `surface_guard_can_handoff`
- `ready`
- `timeout_can_handoff`
- `start_envelope_ready`
- `entry_close_handoff_ready`
- `entry_intent_handoff_ready`
- `target_from_token`
- `target`
- `entry_error`
- `action`
- `pd_servo_action`

The service may depend on explicit ports for planner-owned effects and facts:

- ensure a dig-cut plan for the current cycle
- read current dig-cut tokens
- read the active coverage corridor
- reject the active coverage corridor
- build operator-prior coverage dig-cut tokens for replan handoff
- set dig token state after successful pre-dig replan
- read bucket-tip and bucket-dig-area pose facts
- read local-surface depth and contact fallback facts

It must not receive the policy object, a planner `self`, a blackboard, a
callback bag, or design documents.

## Runtime State

Use one live runtime state owner for counters and reportable values:

- `step_count`
- `hold_count`
- `timeout_count`
- `completed_count`
- `replan_count`
- `target_qpos`
- `error`
- `entry_error_m`
- `start_envelope_ready`
- `entry_close_handoff_ready`
- `entry_intent_handoff_ready`
- `timeout_handoff_reason`
- `surface_depth_m`
- `surface_guard_triggered`
- `surface_guard_count`

The current compatibility state already has these fields. Implementation may
either rename it to a runtime-capable owner while keeping import compatibility,
or add a runtime owner in `execution/pre_dig_align.py` and keep
`compatibility/pre_dig_align.py` as report-schema compatibility. The preferred
implementation is to keep public report dataclasses in the compatibility module
and move live behavior into the execution module.

## Decision Flow

The legacy FSM should regain one ordered branch for active `pre_dig_align`.

When the current skill is not `pre_dig_align`, this branch does not handle the
tick.

When the current skill is `pre_dig_align`, preserve the old decision order:

1. Surface guard:
   - increment `surface_guard_count`
   - reset `hold_count`
   - if handoff is allowed, increment `completed_count` and switch to `dig`
     with `pre_dig_align_to_dig_surface_guard`
   - otherwise reject the active corridor with
     `pre_align_surface_penetration_entry_gap` and restart dig with
     `pre_dig_align_to_dig_surface_guard_replan`
2. Ready:
   - increment `completed_count`
   - switch to `dig` with `pre_dig_align_to_dig_ready`
3. Timeout:
   - increment `timeout_count`
   - if timeout handoff is allowed, switch to `dig` with the service-provided
     timeout reason or `pre_dig_align_to_dig_timeout_close_enough`
   - otherwise reject the active corridor with `align_entry_gap_timeout`
   - then try pre-dig replan handoff, or restart pre-dig with
     `pre_dig_align_retry_entry_gap`

The restored reason strings are part of the behavior contract:

- `pre_dig_align_to_dig_surface_guard`
- `pre_dig_align_to_dig_surface_guard_replan`
- `pre_align_surface_penetration_entry_gap`
- `pre_dig_align_to_dig_ready`
- `pre_dig_align_to_dig_timeout_no_entry_gate`
- `pre_dig_align_to_dig_timeout_intent_aligned`
- `pre_dig_align_to_dig_timeout_close_enough`
- `align_entry_gap_timeout`
- `pre_dig_align_replan_to_dig_entry_close`
- `pre_dig_align_retry_entry_gap`

## Action Dispatch

`PrimitiveActionDispatchService` should dispatch `pre_dig_align` before normal
ACT policy lookup.

If `skill_name == pre_dig_align`, call
`PrimitivePreDigAlignService.action(obs)`.

The action behavior must preserve the old semantics:

- raise when called while disabled
- increment `step_count`
- return zero action when surface guard triggers
- compute target qpos from the active dig-cut token
- update `target_qpos`, `error`, and `entry_error_m`
- apply PD servo action:
  `kp * (target_qpos - qpos) - kd * qvel`
- multiply by configured action signs
- clip by configured action clip
- zero uncontrolled dimensions

## Dig Recovery

`PrimitiveDigRecoveryService` should regain pre-dig restart and replan helpers
without depending on policy-private methods.

Restored behavior:

- `restart_pre_dig_align(reason)` switches to `pre_dig_align`, records the
  reason, resets active policy, resets pre-dig counters needed for a fresh
  attempt, resets dig progress, clears current payload, clears active corridor,
  clears pending return next-dig event, invalidates pending dig-cut plan, and
  clears the active dig-cut plan.
- `try_replan_pre_dig_align_handoff(obs)` rebuilds a coverage dig-cut token
  when coverage mode allows it, updates pre-dig entry error, and switches to
  `dig` with `pre_dig_align_replan_to_dig_entry_close` when timeout handoff
  becomes valid.
- `restart_after_failed_dig(reason, obs)` should route through pre-dig when
  `should_pre_dig_align_before_dig()` or
  `should_pre_dig_align_after_failed_dig()` is true; otherwise it keeps the
  existing stop-or-retry behavior.

## Return Handoff

Return direct-handoff should regain the ability to select `pre_dig_align` as
the next skill when `should_pre_dig_align_before_dig()` is true.

This belongs in the return-handoff runtime ports as an explicit pre-dig
readiness function and skill-name input, not as a policy-private helper call.

## Config

`testbed/planner/primitive/config/adapter.py` should stop fail-fasting only
after the runtime service and tests exist.

The adapter should restore `pre_dig_align_enabled` from the input config and
keep all existing normalized fields as the single source of runtime config
truth.

No config should silently enable pre-dig by default.

## Reporting

`PrimitiveReportCompositionRuntime.pre_dig_align_report_status()` should project
the live pre-dig runtime state, not a fresh disabled/default state.

Public debug, rollout summary, and trace key names should remain compatible.

When disabled, reports should still produce the same zero/default field shape.
When enabled, counters and diagnostic arrays should reflect the live service
state.

## Tests

Replace removal-lock tests with restoration contract tests.

Required focused tests:

- enabled adapter config is accepted and normalized
- disabled adapter config keeps old report defaults
- pre-dig action computes clipped signed PD output and zeros uncontrolled dims
- surface guard produces zero action and the correct transition behavior
- ready transition switches to dig with `pre_dig_align_to_dig_ready`
- timeout transition uses the preserved timeout reason strings
- failed-dig recovery can restart pre-dig through typed service ports
- return direct-handoff can select pre-dig when the runtime says it should
- report runtime reads live pre-dig counters instead of fresh default state
- primitive lanes do not import `PrimitivePlannerACTPolicy`

Required verification after implementation:

- focused pre-dig tests
- action dispatch, dig recovery, return handoff, adapter config, report tests
- backend decision contract and fake backend contract tests
- `python -m compileall` for touched modules
- `python scripts/planner_refactor_guard.py --check-plan-contract`
- `python scripts/planner_refactor_guard.py --check-skill-contract`
- `git diff --check`

Required Unity validation after unit verification:

1. Run a historical `pre_dig_align.enabled=true` YuLong v2.4.5 qc6 config or an
   equivalent config with the same checkpoint family.
2. Confirm the run reaches pre-dig runtime without dispatch/config failure.
3. Compare key rollout fields against the known historical signal:
   `pre_dig_align_enabled`, `pre_dig_align_completed_count`,
   `pre_dig_align_timeout_count`, `max_bucket_mass`, `rollout_stop_reason`,
   and target-cycle completion.
4. Run the current disabled config as a no-regression smoke to confirm the
   default-disabled path still executes.

## Implementation Slicing

Slice 1 should be tests-first and service-local:

- add runtime config/state/service in `execution/pre_dig_align.py`
- add service unit tests for target/action/readiness/timeout/surface guard
- keep policy shell untouched except imports and minimal wiring if needed for
  tests

Slice 2 should reconnect runtime lanes:

- action dispatch
- legacy FSM branch
- decision facts/capability provider inputs
- dig recovery
- return handoff

Slice 3 should reopen config/report and rollout validation:

- adapter enabled config support
- report live state projection
- docs and rollout evidence log update
- focused tests, guards, compileall, and Unity rollout verification

Each slice should preserve the public shell as a thin composition root.
