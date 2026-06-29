# Online And Offline Eval Trace Integration Detail

This document details Slice 7: Online And Offline Eval Integration. It defines
how `DecisionTraceRecord` should serve both online Unity evaluation and offline
evaluation without making decision backends own eval I/O.

## Scope

This design covers:

- compact online Unity trace consumption;
- rich offline trace consumption;
- owner boundaries between planner report code and eval code;
- integration sequence;
- tests for adapter shape and consumer stability.

This design does not cover:

- Unity socket protocol changes;
- rollout file-format migration;
- HDF5 schema changes;
- BT, VLM, or learned backend implementation;
- direct eval I/O inside backend modules;
- changing default planner behavior.

## Owner Boundaries

### Planner Report Owner

Record/schema owner:

```text
testbed/planner/primitive/report/decision_trace.py
```

Responsibilities:

- define `DecisionTraceRecord`;
- assemble trace records from `PrimitiveDecisionResult`, backend payload, and
  tick metadata;
- export compact dictionaries;
- export rich dictionaries;
- summarize backend payload safely.

Forbidden:

- selecting backend names;
- writing rollout files directly;
- owning Unity transport;
- mutating planner state.

Eval-facing adapter owner:

```text
testbed/planner/primitive/report/decision_trace_export.py
```

Responsibilities:

- expose compact online trace dictionaries from `DecisionTraceRecord`;
- expose rich offline trace dictionaries from `DecisionTraceRecord`;
- tolerate absent trace records without pulling in eval/runtime owners;
- avoid backend imports, eval I/O, socket code, file writers, or planner
  mutation paths.

### Online Unity Eval Owner

Likely owners:

```text
testbed/cli/eval.py
testbed/eval/**
```

Responsibilities:

- receive compact trace dictionaries;
- attach compact per-tick trace to online eval logs or live diagnostic output;
- keep payload size bounded;
- avoid backend-specific imports when possible.

Forbidden:

- interpreting BT node lists directly in the online hot path;
- applying planner effects;
- selecting backend behavior from trace contents.

### Offline Eval And Replay Owner

Likely owners:

```text
testbed/eval/**
testbed/cli/replay.py
testbed/cli/replay_diagnostics.py
```

Responsibilities:

- persist or load rich trace dictionaries;
- compare backend decisions across runs;
- diagnose mismatches using generic fields and backend payload;
- aggregate fallback, handoff, validation, and effect summaries.

Forbidden:

- requiring decision backends to choose file formats;
- storing non-serializable backend payloads;
- using trace replay as a mutation path.

## Compact Online Trace

Compact trace is for per-tick online eval. It should be stable and small.

Recommended fields:

```text
schema_version
trace_id
tick_id
sim_time
backend_name
backend_kind
decision_source
trace_status
decision_status
skill_before
skill_after
selected_operation
fallback_type
reason_codes
effect_summary
confidence
validation_status
```

Compact trace should exclude by default:

- full BT node trace;
- VLM prompts;
- raw image/evidence payloads;
- large observations;
- nested effect payloads beyond safe summaries.

Use compact trace for:

- online smoke checks;
- live rollout dashboards;
- quick backend comparison counters;
- per-tick "why did planner continue/switch/fallback" inspection.

## Rich Offline Trace

Rich trace is for replay, mismatch diagnosis, and aggregate analysis.

Recommended fields:

```text
all compact fields
episode_id
rollout_id
switch_reason
diagnostic_checks
effect_summaries
backend_payload
validator_summary
context_summary
```

Rich trace may include:

- BT node path and node outcomes;
- legacy FSM branch payload;
- validation rejection details;
- VLM prompt/evidence identifiers and answer summary, when future VLM exists;
- diagnostic checks for fallback and handoff gates.

Rich trace must still exclude:

- callbacks;
- planner objects;
- mutation ports;
- raw image arrays by default;
- Unity transport handles.

## Integration Sequence

### Step 1: Adapter-Only Tests

Implement and test compact/rich export from synthetic `DecisionTraceRecord`
instances.

No eval owner changes yet.

Slice 7a implementation note:

- `DecisionTraceExportAdapter.to_online_compact_trace(record)` and
  `to_online_compact_trace(record)` return the compact dictionary shape already
  defined by `DecisionTraceRecord`;
- `DecisionTraceExportAdapter.to_offline_rich_trace(record)` and
  `to_offline_rich_trace(record)` return the rich dictionary shape already
  defined by `DecisionTraceRecord`;
- `None` input returns `None` so older or missing trace records can be tolerated
  without adding eval owner code in this slice.

### Step 2: Planner Report Runtime Hook

Attach trace assembly near the existing planner report/trace path after a
decision result exists.

Rules:

- do not change planner decisions;
- do not apply effects from trace;
- keep trace optional if tick metadata is missing.

### Step 3: Online Eval Compact Consumer

Pass compact dictionaries to online Unity eval logging or diagnostics.

Rules:

- keep bounded payload size;
- log backend name, status, skill before/after, selected operation, and reason;
- do not import BT backend classes in eval code.

### Step 4: Offline Rich Consumer

Persist or collect rich dictionaries for replay and mismatch analysis.

Rules:

- store backend payload only after safe summary conversion;
- allow old runs without decision trace;
- compare generic fields first, backend payload second.

### Step 5: Cross-Backend Eval Comparison

Use trace records to compare `legacy_fsm` and shadow backends.

Rules:

- compare skill before/after, switch reason, selected operation, fallback type,
  and effect summary;
- keep shadow backend non-default;
- record mismatch reason without changing runtime behavior.

## Mismatch Diagnosis

Offline mismatch diagnosis should answer:

- did both backends see the same skill before decision?
- did both select the same operation?
- did both request the same effect summary?
- did one backend choose fallback?
- did validator reject one backend?
- which diagnostic checks passed, failed, or were unknown?
- what backend-specific payload explains the difference?

This keeps BT/VLM-specific detail useful without making it generic schema.

## Backward Compatibility

Eval consumers should tolerate:

- missing trace records from older runs;
- unknown backend names;
- missing optional `tick_id` or `sim_time`;
- absent backend payload in compact traces;
- extra fields in rich traces.

They should not tolerate:

- non-serializable trace records;
- trace records that imply effects were applied outside requested effects;
- compact traces that include large raw payloads by default.

## Test Contract

Integration tests should cover:

1. compact export contains only bounded generic fields;
2. rich export includes backend payload after safe summary conversion;
3. old/no-trace eval records remain loadable;
4. online consumer does not import BT backend classes;
5. offline consumer can aggregate fallback and validation reason codes;
6. mismatch comparison works from generic fields before backend payload;
7. compact and rich traces keep stable schema version;
8. backend modules do not import eval writers.

Candidate test files:

```text
tests/test_primitive_decision_trace.py
tests/test_primitive_decision_trace_eval_integration.py
tests/test_eval_rollout_decision_trace.py
```

## First Implementation Slice For This Detail

Preferred first implementation after backend selection design:

1. implement compact/rich adapter unit tests;
2. add optional planner report hook that produces records without changing
   behavior;
3. add offline collection before online live transport changes;
4. add online compact logging only after payload-size tests exist;
5. add cross-backend comparison only after shadow backend selection is stable.

Allowed files are likely:

```text
testbed/planner/primitive/report/decision_trace.py
testbed/eval/**
testbed/cli/eval.py
testbed/cli/replay_diagnostics.py
tests/test_primitive_decision_trace.py
tests/test_primitive_decision_trace_eval_integration.py
docs/v2_5_design_sketch/online_offline_eval_trace_integration_detail.md
```

Not allowed:

- backend-owned eval file format;
- BT or VLM imports in generic eval consumers;
- trace-driven planner mutation;
- raw image/evidence payloads in compact online trace;
- production default backend change.
