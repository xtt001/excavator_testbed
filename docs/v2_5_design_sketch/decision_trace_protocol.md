# Decision Trace Schema And Protocol Sketch

This document sketches the V2.5 backend-neutral decision trace protocol. It is
intended to guide the next implementation slices and keep online Unity eval and
offline eval aligned.

## Protocol Roles

```text
DecisionBackend
  input: PrimitiveDecisionContext
  output: PrimitiveDecisionResult
  optional output: backend_payload

DecisionTraceAssembler
  input: PrimitiveDecisionResult + backend_payload + tick metadata
  output: DecisionTraceRecord

DecisionTraceExporter
  input: DecisionTraceRecord
  output: compact online dict or rich offline dict
```

The names above are design roles. The exact Python file and class names should
follow the existing planner report package when implemented.

## Trace Lifecycle And Ownership

V2.5 v1 should keep decision traces beside the runtime decision result, not
inside `PrimitiveDecisionResult`.

Lifecycle:

1. `DecisionBackend` receives `PrimitiveDecisionContext` and returns the current
   runtime-facing `PrimitiveDecisionResult`.
2. A backend may also expose a `backend_payload`. For BT this can
   be a selected path and node outcomes. For VLM this can be prompt/evidence
   metadata. For legacy FSM this can be branch name and legacy reason.
3. The planner report/trace owner assembles `DecisionTraceRecord` from
   `PrimitiveDecisionResult`, `backend_payload`, and optional tick metadata.
4. `DecisionTraceExporter` converts `DecisionTraceRecord` into compact online
   dictionaries or richer offline dictionaries.
5. Online Unity eval and offline eval consume exported dictionaries. They do
   not import or understand BT internals directly.

Ownership:

- `PrimitiveDecisionResult` owns runtime decision/effect semantics.
- Backends own backend-specific explanation payload production.
- The planner report/trace owner owns generic trace assembly and export shape.
- Unity eval owners own transport, display, and online collection.
- Offline eval owners own persistence, replay, aggregate analysis, and mismatch
  reports.

This keeps trace additions behavior-neutral. The first trace implementation
slice should not change active skill transitions, requested effects, backend
selection, or production defaults.

The main alternative is to add `DecisionTraceRecord` as a field on
`PrimitiveDecisionResult`. Defer that option unless the sidecar approach causes
lost trace/result association, excessive plumbing, or inconsistent tick
metadata. The sidecar approach is preferred for V2.5 v1 because it avoids
expanding the existing runtime/effect contract before online and offline trace
consumers are proven.

## DecisionTraceRecord v1

`DecisionTraceRecord` is the backend-neutral record consumed by evaluation and
diagnostic paths.

Proposed fields:

```text
schema_version: "primitive_decision_trace_v1"

backend_name: str
backend_kind: "legacy_fsm" | "behavior_tree" | "vlm" | "learned" | "hybrid" | "external"
decision_source: str

decision_status: "no_change" | "skill_switch"
trace_status: "success" | "fallback" | "contract_error" | "skipped"
validation_status: "accepted" | "rejected" | "skipped"

skill_before: str
skill_after: str
switch_reason: str

selected_operation: str
fallback_type: "none" | "continue_current_skill" | "fail_closed" | "validator_rejected" | "defer"
reason_codes: tuple[str, ...]

requested_effects_summary: tuple[DecisionEffectSummary, ...]
diagnostic_checks: tuple[DecisionDiagnosticCheck, ...]

confidence: float | None
score: float | None

tick_id: str | None
episode_id: str | None
sim_time_s: float | None

backend_payload: Mapping[str, object]
```

Notes:

- `decision_status` mirrors the existing `PrimitiveDecisionResult.status`.
- `trace_status` describes trace/evaluation interpretation without expanding
  the runtime decision-status contract.
- `validation_status` exposes whether a proposal validator accepted, rejected,
  or skipped validation for this trace without dumping validator internals into
  compact export.
- `selected_operation` is a lightweight trace label, not a formal
  `DecisionIntent`.
- `backend_payload` is the only place for backend-specific internals.

## Effect Summary

`DecisionEffectSummary` should describe requested effects without exposing
planner mutation ports or callbacks.

Proposed fields:

```text
effect_type: str
reason: str
already_applied: bool
payload_keys: tuple[str, ...]
```

Compact export may include only `effect_type`, `reason`, and
`already_applied`. Rich export may include safe payload summaries if the payload
does not contain callbacks, planner objects, large arrays, or private mutable
state.

## Diagnostic Checks

`DecisionDiagnosticCheck` should make fallback and handoff explainable without
forcing every backend to use BT-style nodes.

Proposed fields:

```text
name: str
status: "pass" | "fail" | "skipped" | "unknown"
reason: str
value: object | None
```

Examples:

- `return_handoff_gate`: pass/fail with a reason code.
- `dump_ready_gate`: pass/fail with a hold-count value.
- `vlm_grounding_check`: pass/fail with evidence id references.
- `bt_node_selected`: pass with selected node name.

## Compact Online Export

Online Unity eval needs a low-overhead per-tick trace. The compact export should
avoid nested node lists, visual evidence payloads, large arrays, and full
planner reports.

Suggested compact fields:

```text
schema_version
backend_name
backend_kind
decision_source
decision_status
trace_status
validation_status
skill_before
skill_after
selected_operation
fallback_type
reason_codes
requested_effects_summary
confidence
tick_id
sim_time_s
```

The compact trace should be stable enough for Unity-side live debugging and
online eval dashboards.

## Rich Offline Export

Offline eval needs richer replay and mismatch diagnosis.

Suggested rich fields:

```text
all compact fields
switch_reason
diagnostic_checks
requested_effects_summary with safe payload summaries
episode_id
backend_payload
```

The rich trace can be written as JSON-compatible dictionaries by offline eval or
replay owners. The trace protocol should not force a specific file format in
the backend layer.

## Backend Payload Examples

BT payload:

```text
root_status: "success" | "failure"
selected_path: tuple[str, ...]
node_results:
  - node_name: str
    status: "success" | "failure" | "skipped"
    reason: str
failed_conditions: tuple[str, ...]
```

VLM payload:

```text
prompt_id: str
evidence_ids: tuple[str, ...]
answer_summary: str
grounding: Mapping[str, object]
confidence: float | None
refusal_or_fallback_reason: str
```

Legacy FSM payload:

```text
branch_name: str
branch_order_index: int | None
legacy_reason: str
side_effects_applied: bool
```

## Fallback And Handoff Semantics

Fallback and handoff should be represented through generic trace fields plus
backend payload, not by moving domain ownership into the trace schema.

Required v1 cases:

- `continue_current_skill`: valid no-change fallback.
- `fail_closed`: backend could not produce a safe result.
- `validator_rejected`: a backend proposal was rejected before requested
  effects.
- `defer`: backend intentionally leaves the current skill unchanged because
  another owner should decide later.

Handoff remains a domain decision represented through typed facts and requested
effects. The trace schema may explain a handoff decision, but it does not own
handoff algorithms or mutable handoff state.

## Implementation Slice Guardrails

The first implementation slice should not change planner behavior.

Allowed:

- add a focused trace schema/assembler under the planner report/trace owner;
- add tests that build a trace from existing `PrimitiveDecisionResult` objects;
- adapt the BT shadow backend's current trace payload into `backend_payload`;
- add compact/rich export helpers returning JSON-compatible dictionaries.

Not allowed in the first slice:

- production backend selector;
- new `DecisionIntent` dataclass;
- generic blackboard;
- Unity socket/protocol I/O;
- offline replay writer changes;
- token, coverage, return-handoff, or ACT action dispatch migrations.
