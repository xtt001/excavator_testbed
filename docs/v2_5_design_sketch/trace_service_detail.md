# Trace Service Detail

This document details Slice 1: Generic Decision Trace Service. It follows the
core graph contract in `graph_contract_detail.md` and the schema sketch in
`decision_trace_protocol.md`.

The trace service is sidecar/report-owned. It does not change planner behavior,
select backends, or apply requested effects.

## Scope

This design covers:

- `DecisionTraceRecord`;
- `DecisionEffectSummary`;
- `DecisionDiagnosticCheck`;
- tick metadata accepted by the assembler;
- sidecar assembly from `PrimitiveDecisionResult`, `backend_payload`, and
  metadata;
- compact online export;
- rich offline export;
- first-slice tests.

This design does not cover:

- production backend selection;
- Unity transport or sockets;
- offline replay writer integration;
- first-class `DecisionIntent`;
- VLM runtime, prompt configuration, or model calls;
- new fallback or handoff algorithms.

## Proposed Owner

Preferred owner:

```text
testbed/planner/primitive/report/decision_trace.py
```

Reason:

- the service is report/trace-owned, not backend-owned;
- existing planner report code already assembles public planner trace payloads;
- online and offline eval should consume exported trace dictionaries without
  importing backend modules.

The exact file name can be adjusted during implementation if a nearby existing
report module is a better focused owner.

Validation trace projection is report-owned but kept in a focused helper:

```text
testbed/planner/primitive/report/decision_validation_trace.py
```

Reason:

- `decision_trace.py` owns the generic record, assembler, and export schema;
- validation projection owns conversion from proposal-validation results into
  trace metadata, diagnostic checks, and safe rich payload summaries;
- the decision validation layer must not import report or trace modules.

Eval-facing trace export is also report-owned and kept in a focused adapter:

```text
testbed/planner/primitive/report/decision_trace_export.py
```

Reason:

- `decision_trace.py` owns the record and serialization methods;
- the adapter exposes stable compact/rich entrypoints for online and offline
  consumers without importing eval, backend, socket, writer, or runtime code.

## Data Records

### DecisionTraceRecord

Role: backend-neutral sidecar record.

Fields:

```text
schema_version: str = "primitive_decision_trace_v1"

backend_name: str
backend_kind: str
decision_source: str

decision_status: str
trace_status: str
validation_status: "accepted" | "rejected" | "skipped"

skill_before: str
skill_after: str
switch_reason: str

selected_operation: str
fallback_type: str
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

Required fields:

- `backend_name`;
- `backend_kind`;
- `decision_source`;
- `decision_status`;
- `trace_status`;
- `validation_status`;
- `skill_before`;
- `skill_after`;
- `selected_operation`;
- `fallback_type`;
- `reason_codes`;
- `requested_effects_summary`;
- `diagnostic_checks`;
- `backend_payload`.

Optional fields:

- `switch_reason`, allowed to be empty string;
- `confidence`;
- `score`;
- `tick_id`;
- `episode_id`;
- `sim_time_s`.

### DecisionEffectSummary

Role: safe summary of runtime effects for trace/export.

Fields:

```text
effect_type: str
reason: str
already_applied: bool
payload_keys: tuple[str, ...]
```

Rules:

- summarize only effect metadata;
- do not expose callbacks, planner objects, mutation ports, or large payloads;
- `payload_keys` is enough for v1 rich trace unless a later revision approves
  safe payload summaries.

### DecisionDiagnosticCheck

Role: backend-neutral diagnostic check for fallback, handoff, or validation.

Fields:

```text
name: str
status: "pass" | "fail" | "skipped" | "unknown"
reason: str
value: object | None
```

Rules:

- `name` should describe a stable domain check, not a temporary experiment;
- `status` should be one of the four allowed values;
- `value` must be JSON-compatible or omitted.

### DecisionTraceMetadata

Role: optional tick/run context for assembling a trace.

Fields:

```text
backend_name: str
backend_kind: str
tick_id: str | None
episode_id: str | None
sim_time_s: float | None
selected_operation: str | None
fallback_type: str | None
validation_status: "accepted" | "rejected" | "skipped"
reason_codes: tuple[str, ...]
diagnostic_checks: tuple[DecisionDiagnosticCheck, ...]
confidence: float | None
score: float | None
```

Rules:

- `backend_name` and `backend_kind` are required for generic trace assembly;
- `validation_status` defaults to `skipped` when no proposal-validation
  projection is attached;
- tick metadata must not contain backend internals;
- backend internals belong in `backend_payload`.

## Assembly API

Suggested role:

```text
DecisionTraceAssembler.assemble(
    *,
    result: PrimitiveDecisionResult,
    backend_payload: Mapping[str, object] | None,
    metadata: DecisionTraceMetadata,
) -> DecisionTraceRecord
```

Assembly rules:

- copy runtime fields from `PrimitiveDecisionResult`;
- copy backend identity and tick metadata from `DecisionTraceMetadata`;
- normalize `backend_payload` to an empty mapping when omitted;
- summarize each effect in `result.effects`;
- never mutate planner state;
- never validate whether requested effects should be applied; that remains the
  requested-effect contract's job.

## Field Derivation Rules

### Runtime fields

From `PrimitiveDecisionResult`:

```text
decision_source = result.decision_source
decision_status = result.status
skill_before = result.skill_before
skill_after = result.skill_after
switch_reason = result.switch_reason
requested_effects_summary = summarize(result.effects)
```

### Trace status

Default derivation:

```text
if fallback_type not in ("", "none"):
    trace_status = "fallback"
else:
    trace_status = "success"
```

Explicit overrides:

- `contract_error` is reserved for failed trace/result contract assembly or a
  backend fail-closed result that is represented without applying effects;
- `skipped` is reserved for compatibility paths where a backend did not run.

The first implementation should avoid inventing more statuses.

### Selected operation

`selected_operation` is a lightweight trace label, not `DecisionIntent`.

Recommended v1 values:

```text
continue_current_skill
switch_skill
return_handoff
recover
validator_rejected_fallback
fail_closed
unknown
```

If metadata does not provide one:

- use `switch_skill` when `result.status == "skill_switch"`;
- use `continue_current_skill` when `result.status == "no_change"` and there
  are no requested effects;
- otherwise use `unknown`.

### Fallback type

Recommended v1 values:

```text
none
continue_current_skill
fail_closed
validator_rejected
defer
unknown
```

If metadata does not provide one, default to `none`.

### Reason codes

Reason codes should be short, stable, and backend-neutral when possible.

Examples:

```text
legacy_fsm_branch_selected
bt_continue_fallback
return_handoff_gate_pass
return_handoff_gate_fail
validator_rejected
contract_error
```

Backend-specific reason detail may still live in `backend_payload`.

## Export API

Suggested role:

```text
DecisionTraceExporter.compact(record: DecisionTraceRecord) -> dict[str, object]
DecisionTraceExporter.rich(record: DecisionTraceRecord) -> dict[str, object]
```

Implemented v1 adapter role:

```text
DecisionTraceExportAdapter.to_online_compact_trace(record)
DecisionTraceExportAdapter.to_offline_rich_trace(record)
to_online_compact_trace(record)
to_offline_rich_trace(record)
```

These functions are pure pass-through adapters over the record's compact/rich
methods. They are intentionally small because the stable API boundary lets
online and offline eval code consume trace dictionaries without depending on
record internals or backend modules.

### Compact export

Compact export is for online Unity eval.

Include:

- `schema_version`;
- `backend_name`;
- `backend_kind`;
- `decision_source`;
- `decision_status`;
- `trace_status`;
- `validation_status`;
- `skill_before`;
- `skill_after`;
- `selected_operation`;
- `fallback_type`;
- `reason_codes`;
- `requested_effects_summary`;
- `confidence`;
- `tick_id`;
- `sim_time_s`.

Exclude:

- `backend_payload`;
- full diagnostic-check list by default;
- large or nested backend-specific data;
- raw visual evidence.

### Rich export

Rich export is for offline eval and replay diagnostics.

Include:

- all compact export fields;
- `switch_reason`;
- `diagnostic_checks`;
- `requested_effects_summary` with payload keys;
- `episode_id`;
- `backend_payload`.

Exclude:

- non-serializable objects;
- callbacks;
- planner objects;
- mutation ports.

## Backend Payload Handling

The assembler should accept backend payload as a mapping. Backend modules may
use typed local records internally, but they must expose a safe mapping or a
converter at the report boundary.

Rules:

- missing payload becomes `{}`;
- payload keys should be strings;
- values should be JSON-compatible for rich export;
- unsafe values should be summarized or dropped by the payload producer before
  assembly.

BT payload v1 can include:

```text
root_status
selected_path
node_results
failed_conditions
```

Legacy FSM payload v1 can include:

```text
branch_name
branch_order_index
legacy_reason
side_effects_applied
```

VLM payload should remain design-only in this slice.

## Error Handling

Assembler errors should be contract errors, not silent trace drops, when:

- required metadata is missing;
- `backend_payload` is not mapping-like;
- effect summaries contain forbidden mutation handles;
- diagnostic check status is outside the allowed set.

Exporter errors should be contract errors when:

- a record cannot be converted to JSON-compatible compact/rich form;
- a compact export would include forbidden rich-only payloads.

Trace failures should not mutate planner state. The first implementation can
fail the test/harness path loudly rather than silently continuing with a broken
trace.

## Test Contract

First-slice tests should cover:

1. no-change result assembles into a success trace with no requested effects;
2. skill-switch result assembles into a success trace with one switch effect
   summary;
3. fallback metadata assembles into `trace_status == "fallback"`;
4. backend payload is nested under `backend_payload` and absent from compact
   export;
5. rich export includes backend payload and diagnostic checks;
6. invalid diagnostic status fails contract validation;
7. assembler does not require BT-specific fields;
8. compact export is JSON-compatible and small;
9. rich export is JSON-compatible for the v1 payload examples.

Recommended initial test file:

```text
tests/test_primitive_decision_trace.py
```

The tests should construct synthetic `PrimitiveDecisionResult` objects rather
than driving the full planner shell.

## First Implementation Slice

Allowed files are likely:

```text
testbed/planner/primitive/report/decision_trace.py
tests/test_primitive_decision_trace.py
docs/v2_5_design_sketch/trace_service_detail.md
```

Implementation should not touch:

- backend selection runtime;
- production backend factory registration;
- Unity eval transport;
- offline replay writer;
- token, coverage, return-handoff, policy, or ACT action modules.
