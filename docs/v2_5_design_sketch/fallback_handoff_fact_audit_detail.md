# Fallback And Handoff Fact Audit Detail

This document details Slice 3: Fallback And Handoff Fact Audit. It identifies
which facts already explain fallback and handoff behavior, which facts are
missing, and where any new facts should live.

This is a design and audit document. It does not approve a new handoff
algorithm, generic blackboard, or backend-owned runtime state.

## Scope

This design covers:

- existing fallback/handoff facts available to backend-neutral decisions;
- missing explanation facts for trace and BT/VLM future work;
- owner assignment for any new facts;
- diagnostic-check mapping into `DecisionTraceRecord`;
- tests needed before implementation.

This design does not cover:

- new handoff algorithms;
- production backend selector;
- real VLM runtime;
- moving return-handoff mutable state into a decision backend;
- copying token, coverage, policy, or ACT action state into generic trace;
- changing default `legacy_fsm` behavior.

## Current Fact Owners

### Common Decision Facts

Owner:

```text
testbed/planner/primitive/facts/decision.py
```

Existing facts:

- `current_skill_name`;
- `current_switch_reason`;
- `skill_name_before_decision`;
- `dig_progress_updated`;
- `obs`;
- `boundary_event`;
- `preparation`.

Use for:

- explaining no-change fallback;
- confirming active skill before/after decisions;
- deriving generic trace fields.

Do not use for:

- return-handoff gate internals;
- token or coverage state snapshots;
- backend-specific blackboard state.

### Backend Transition Facts Access

Owner:

```text
testbed/planner/primitive/facts/backend.py
```

Existing accessors:

- `bootstrap_decision()`;
- `dig_transition()`;
- `carry_transition()`;
- `dump_transition()`;
- `return_transition()`.

Use for:

- read-only backend-facing facts;
- branch/fallback explanation based on current skill;
- future BT branch conditions.

Do not use for:

- mutating planner state;
- exposing arbitrary planner-private fields;
- duplicating focused runtime state.

### Capability Status Records

Owner:

```text
testbed/planner/primitive/facts/capabilities.py
```

Relevant existing statuses:

- `DigTransitionStatus`;
- `CarryTransitionStatus`;
- `DumpTransitionStatus`;
- `ReturnTransitionStatus`;
- `PrimitiveObservationFacts`.

Use for:

- transition gate facts;
- handoff-ready summaries already exposed in `ReturnTransitionStatus`;
- diagnostic checks derived from stable status fields.

Do not use for:

- report/export formatting;
- backend-specific node trace format;
- mutation of counters or hold state.

### Return Handoff Readiness And Effect Runtime

Owners:

```text
testbed/planner/primitive/effects/return_handoff.py
testbed/planner/primitive/effects/return_handoff_runtime.py
```

Existing services:

- `ReturnHandoffReadinessService`;
- `ReturnStartEnvelopeGateService`;
- `ReturnDirectHandoffEffectService`;
- `PrimitiveReturnHandoffRuntime`.

Use for:

- focused return-handoff readiness computation;
- start-envelope gate checks;
- direct-handoff effect application.

Do not use for:

- generic backend blackboard;
- trace export formatting;
- backend selection;
- moving effect-side mutation decisions into trace assembly.

## Existing Fallback/Handoff Facts

### Generic Continue Fallback

Already available:

- active skill from `PrimitiveDecisionFacts`;
- no-change decision status from `PrimitiveDecisionResult`;
- empty requested effects;
- backend-specific payload such as BT continue node trace.

Trace mapping:

```text
selected_operation: "continue_current_skill"
fallback_type: "continue_current_skill" or "none"
reason_codes: ("bt_continue_fallback",) for explicit BT fallback
```

Design note:

- Use `fallback_type == "continue_current_skill"` only when the backend
  explicitly chose a fallback path.
- Use `fallback_type == "none"` for ordinary legacy no-change where no fallback
  was selected.

### Dig Fallback And Recovery

Already available in `DigTransitionStatus`:

- `dig_bad_replan_ready`;
- `dig_exit_guard_ready`;
- `dig_complete_boundary_low_payload`;
- `dig_to_carry_ready`;
- `dig_to_carry_reason`;
- `coverage_terminal_stop_requested`;
- `semantic_boundary_profile_active`;
- mass and distance facts.

Existing requested effects can represent:

- increment bad-replan count;
- increment exit-guard count;
- reject active coverage corridor;
- restart after failed dig;
- restart dig with new cut;
- switch to carry.

Trace diagnostic candidates:

```text
dig_bad_replan_ready
dig_exit_guard_ready
dig_complete_boundary_low_payload
dig_to_carry_ready
dig_to_carry_reason
coverage_terminal_stop_requested
```

Missing detail:

- no normalized "why fallback instead of carry" diagnostic bundle yet;
- no generic diagnostic-check mapping for the dig status fields yet.

Preferred v1 owner for new diagnostic projection:

```text
testbed/planner/primitive/report/decision_trace.py
```

Reason:

- v1 should map existing status fields into trace diagnostics without creating
  new runtime facts first;
- owner-side facts should be added only after a test proves the report-side
  mapper cannot explain a required trace field.

Possible later owner for stable facts:

```text
testbed/planner/primitive/facts/capabilities.py
```

only if the diagnostic becomes a backend-facing transition fact used by more
than trace/report.

### Carry-To-Dump And Carry-To-Return Handoff

Already available in `CarryTransitionStatus`:

- `carry_release_safety_done`;
- `dump_complete_event`;
- `dump_ready`;
- `next_dump_ready_hold_count`;
- `ready_to_dump`;
- `carry_to_dump_reason`;
- `carry_to_return_reason`;
- mass/deposit facts.

Existing requested effects can represent:

- set dump-ready hold count;
- capture dump-start deposited mass;
- switch to dump;
- complete dump coverage;
- set return or direct handoff.

Trace diagnostic candidates:

```text
carry_release_safety_done
dump_complete_event
dump_ready
ready_to_dump
carry_to_dump_reason
carry_to_return_reason
next_dump_ready_hold_count
```

Missing detail:

- no generic check list that explains which dump-ready condition failed;
- dump-ready geometry internals are owned by observation/capability logic and
  should not be copied into a backend blackboard.

Preferred owner for richer failure checks:

```text
testbed/planner/primitive/facts/capabilities.py
```

only if the checks are stable transition facts. Otherwise keep rich geometry
detail out of v1 trace.

### Dump-To-Return Handoff

Already available in `DumpTransitionStatus`:

- `dump_complete_event`;
- `legacy_dump_end_event`;
- `boundary_dump_done`;
- `dump_done_mass_low`;
- `next_dump_done_hold_count`;
- `ready_to_return`;
- `coverage_completion_reason`;
- `dump_to_return_reason`;
- mass/deposit facts.

Existing requested effects can represent:

- set dump-done hold count;
- complete coverage dump;
- set return or direct handoff.

Trace diagnostic candidates:

```text
boundary_dump_done
dump_done_mass_low
ready_to_return
coverage_completion_reason
dump_to_return_reason
next_dump_done_hold_count
```

Missing detail:

- no separate trace-oriented summary of why `ready_to_return` is false.

Preferred owner:

```text
testbed/planner/primitive/facts/capabilities.py
```

only if a stable status field is needed by more than trace. Otherwise derive
diagnostics in the report-side trace mapper.

### Return-To-Dig Handoff

Already available in `ReturnTransitionStatus`:

- `next_dig_event`;
- `next_or_seen_dig_event`;
- `entry_close`;
- `start_envelope_ready`;
- `handoff_ready`;
- `direct_handoff_ready`;
- `shallow_guard_ready`;
- `shallow_guard_allowed`;
- `completed_transition`;
- `next_skill`;
- `switch_reason`;
- mass, distance, and depth facts.

Already available in `ReturnHandoffReadinessService`:

- `entry_error_for_obs`;
- `entry_close`;
- `handoff_ready`;
- `direct_handoff_ready`;
- `start_envelope_ready`;
- start-envelope gate result checks are written through return runtime state.

Existing requested effects can represent:

- mark next-dig event seen;
- complete return transition;
- switch to next skill after return;
- set return or direct handoff effect-side transition.

Trace diagnostic candidates:

```text
entry_close
start_envelope_ready
handoff_ready
direct_handoff_ready
shallow_guard_ready
shallow_guard_allowed
completed_transition
next_skill
switch_reason
```

Missing detail:

- start-envelope gate check details exist inside readiness/runtime state flow,
  but the backend-facing `ReturnTransitionStatus` exposes only booleans and
  final reason fields;
- no trace-facing normalized diagnostic list for entry error, start-envelope
  checks, direct-handoff mass gate, or shallow guard reason;
- no explicit diagnostic explaining why direct handoff was not applied after a
  `SetReturnOrDirectHandoffEffect`.

Preferred owner for new stable facts:

```text
testbed/planner/primitive/effects/return_handoff.py
```

for readiness/gate results, or:

```text
testbed/planner/primitive/facts/capabilities.py
```

for backend-facing summarized transition status.

Do not put these fields in:

- BT backend;
- generic trace assembler;
- Unity eval writer;
- offline replay writer.

## Missing Fact Candidates

### Candidate A: ReturnHandoffDiagnosticFacts

Status: candidate, not approved for implementation yet.

Owner:

```text
testbed/planner/primitive/effects/return_handoff.py
```

Purpose:

- expose read-only diagnostic checks from return-handoff readiness;
- preserve readiness service ownership;
- let trace/report map checks without recomputing or reading private state.

Possible fields:

```text
entry_error_m: float | None
entry_close: bool
start_envelope_ready: bool
start_envelope_error: float | None
start_envelope_checks: Mapping[str, object]
handoff_ready: bool
direct_handoff_ready: bool
mass_gate_ready: bool | None
shallow_guard_ready: bool | None
reason_codes: tuple[str, ...]
```

Pros:

- keeps return-handoff algorithm detail with the focused owner;
- gives trace and BT future branches enough explanation data;
- avoids a generic blackboard.

Cons:

- may duplicate existing `ReturnTransitionStatus` booleans if not scoped well;
- needs careful JSON-compatible check summaries;
- should not become an effect-side mutation API.

### Candidate B: TransitionDiagnosticCheck Mapper

Status: candidate, likely useful before adding new runtime facts.

Owner:

```text
testbed/planner/primitive/report/decision_trace.py
```

Purpose:

- map existing transition status fields and backend payload into generic
  `DecisionDiagnosticCheck` records;
- avoid adding runtime facts until trace evidence proves a gap.

Possible input:

```text
PrimitiveDecisionResult
backend_payload
optional known transition status
```

Pros:

- low risk;
- no new runtime owner;
- sufficient for many trace parity cases.

Cons:

- cannot explain checks that are not exposed by current status objects;
- must not reach into planner private state to enrich trace.

### Candidate C: BackendTraceFactAccess

Status: rejected for v1.

Reason:

- it risks becoming a generic blackboard;
- it would duplicate existing focused facts access;
- it could blur data, planner, report, and backend ownership.

Use existing `PrimitiveBackendFactsAccess` and focused status owners instead.

## Diagnostic Mapping

Recommended diagnostic check names:

```text
dig_bad_replan_ready
dig_exit_guard_ready
dig_to_carry_ready
carry_dump_ready
carry_return_ready
dump_return_ready
return_entry_close
return_start_envelope_ready
return_handoff_ready
return_direct_handoff_ready
return_shallow_guard_ready
```

Mapping rule:

- `status == "pass"` when the gate is true;
- `status == "fail"` when the gate is false and it was evaluated;
- `status == "skipped"` when the gate is disabled or irrelevant to the active
  skill;
- `status == "unknown"` when current facts cannot determine it.

These checks belong in `DecisionTraceRecord.diagnostic_checks`, not in
`PrimitiveDecisionResult.effects`.

## Test Contract

Slice 3 tests should cover:

1. existing dig status maps to diagnostic checks without private planner fields;
2. existing carry status maps dump/return readiness checks;
3. existing dump status maps return readiness checks;
4. existing return status maps handoff/direct-handoff checks;
5. no diagnostic mapper creates planner mutations;
6. no mapper requires BT-specific node fields;
7. no mapper reads Unity/offline eval state;
8. missing optional checks become `unknown` or `skipped`, not fabricated facts.

Candidate test files:

```text
tests/test_primitive_decision_trace.py
tests/test_primitive_fallback_handoff_facts.py
```

## First Implementation Slice For This Audit

Preferred first implementation after trace service and payload mapping:

1. implement report-side diagnostic mapping from existing status fields only;
2. add tests that prove diagnostic checks can be built for synthetic status
   examples;
3. record any missing return-handoff details as deferred owner-specific facts.

Allowed files are likely:

```text
testbed/planner/primitive/report/decision_trace.py
tests/test_primitive_fallback_handoff_facts.py
docs/v2_5_design_sketch/fallback_handoff_fact_audit_detail.md
```

Only add owner-side facts under `facts/capabilities.py` or
`effects/return_handoff.py` after a test proves report-side mapping cannot
explain a needed trace field.

Not allowed:

- generic blackboard;
- backend-owned copies of return-handoff state;
- new handoff algorithm;
- production backend selector;
- VLM runtime;
- Unity/offline I/O integration;
- default behavior change.
