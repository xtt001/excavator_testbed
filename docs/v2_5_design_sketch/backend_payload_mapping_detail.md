# Backend Payload Mapping Detail

This document details Slice 2: Trace Adoption Parity. It defines how each
backend family should provide `backend_payload` for generic decision trace
assembly.

The payload is explanation data. It must not become a second state source, a
mutation path, or an eval I/O owner.

## Scope

This design covers:

- legacy FSM payload mapping;
- BT shadow payload mapping;
- future VLM/mock payload shape;
- common payload rules;
- mapping into `DecisionTraceRecord`;
- trace parity tests for legacy FSM and BT shadow.

This design does not cover:

- production backend selection;
- new BT branches;
- real VLM runtime calls;
- prompt templates;
- Unity transport;
- offline replay writer integration;
- new fallback or handoff algorithms.

## Common Payload Rules

Every `backend_payload` must be:

- JSON-compatible or convertible to a JSON-compatible mapping;
- backend-specific, nested under `DecisionTraceRecord.backend_payload`;
- behavior-neutral;
- safe to include in rich offline trace;
- optional for compact online trace.

Every `backend_payload` must not contain:

- planner objects;
- callbacks;
- mutation ports;
- policy/model objects;
- large arrays by default;
- Unity transport handles;
- offline writer handles;
- copied token, coverage, return-handoff, or ACT action-dispatch state.

Recommended common fields:

```text
backend_family: str
payload_schema_version: str
payload_kind: str
summary: str
```

These fields are convenience fields inside the payload. The generic trace core
still owns `backend_name`, `backend_kind`, `decision_source`,
`selected_operation`, `fallback_type`, and `reason_codes`.

## Legacy FSM Payload

Legacy FSM has two current forms:

1. requested-effect branch backend, where branch classes return
   `PrimitiveDecisionResult.from_requested_effects`;
2. compatibility adapter, where the old FSM callback may already mutate state
   and returns `PrimitiveDecisionResult.from_legacy_fsm_outcome`.

Both forms should map to the same payload family:

```text
backend_family: "legacy_fsm"
payload_schema_version: "legacy_fsm_payload_v1"
payload_kind: "requested_branch" | "compatibility_outcome"
branch_name: str
branch_order_index: int | None
decision_source: str
legacy_reason: str
side_effects_applied: bool
effect_types: tuple[str, ...]
```

### Requested Branch Mapping

Known requested branch decision sources:

```text
legacy_fsm_bootstrap_requested_effect
legacy_fsm_dig_requested_effect
legacy_fsm_carry_requested_effect
legacy_fsm_dump_requested_effect
legacy_fsm_return_requested_effect
legacy_fsm_pre_dig_align_requested_effect
```

Suggested mapping:

```text
decision_source prefix -> branch_name

legacy_fsm_bootstrap_requested_effect -> bootstrap
legacy_fsm_dig_requested_effect -> dig
legacy_fsm_carry_requested_effect -> carry
legacy_fsm_dump_requested_effect -> dump
legacy_fsm_return_requested_effect -> return
legacy_fsm_pre_dig_align_requested_effect -> pre_dig_align
```

Branch order for current mainline:

```text
bootstrap: 0
dig: 1
carry: 2
dump: 3
return: 4
pre_dig_align: -1
```

`pre_dig_align` remains parked/legacy-special. It should not be treated as a
normal current-mainline branch unless a later decision reopens that path.

Suggested payload example:

```text
{
  "backend_family": "legacy_fsm",
  "payload_schema_version": "legacy_fsm_payload_v1",
  "payload_kind": "requested_branch",
  "branch_name": "dig",
  "branch_order_index": 1,
  "decision_source": "legacy_fsm_dig_requested_effect",
  "legacy_reason": "dig_to_carry_loaded",
  "side_effects_applied": false,
  "effect_types": ("complete_coverage_dig", "switch_skill"),
}
```

Mapping rules:

- derive `branch_name` from `decision_source` first;
- use `result.switch_reason` as `legacy_reason`;
- use `result.side_effects_applied`;
- derive `effect_types` from `result.effects`;
- do not inspect planner private fields to enrich payload in v1.

### Compatibility Outcome Mapping

Compatibility adapter decision source:

```text
legacy_fsm_side_effects_applied
```

Suggested payload example:

```text
{
  "backend_family": "legacy_fsm",
  "payload_schema_version": "legacy_fsm_payload_v1",
  "payload_kind": "compatibility_outcome",
  "branch_name": "unknown",
  "branch_order_index": null,
  "decision_source": "legacy_fsm_side_effects_applied",
  "legacy_reason": "carry_to_dump_target_ready",
  "side_effects_applied": true,
  "effect_types": ("legacy_decision_outcome",),
}
```

Mapping rules:

- branch name may be `"unknown"` unless it can be derived from
  `skill_before`, `skill_after`, or `switch_reason` without private state;
- do not recover branch internals from the old callback;
- do not change compatibility behavior just to improve payload detail.

## BT Shadow Payload

BT shadow currently exposes node trace records through the non-default
`behavior_tree_shadow` backend.

Current available fields:

```text
BehaviorTreeNodeTrace:
  node_name: str
  status: "success" | "failure"
  reason: str
```

BT payload v1:

```text
backend_family: "behavior_tree"
payload_schema_version: "behavior_tree_payload_v1"
payload_kind: "node_trace"
root_status: "success" | "failure"
selected_path: tuple[str, ...]
node_results: tuple[Mapping[str, object], ...]
failed_conditions: tuple[str, ...]
```

Suggested payload example for the current continue fallback:

```text
{
  "backend_family": "behavior_tree",
  "payload_schema_version": "behavior_tree_payload_v1",
  "payload_kind": "node_trace",
  "root_status": "success",
  "selected_path": ("behavior_tree_root", "continue_current_skill"),
  "node_results": (
    {
      "node_name": "behavior_tree_root",
      "status": "success",
      "reason": "selected:continue_current_skill",
    },
    {
      "node_name": "continue_current_skill",
      "status": "success",
      "reason": "continue_current_skill",
    },
  ),
  "failed_conditions": (),
}
```

Mapping rules:

- derive `root_status` from the root tick outcome when available;
- derive `selected_path` from successful selector/root trace order;
- convert each node trace into a mapping with `node_name`, `status`, and
  `reason`;
- put failed condition reason codes in `failed_conditions` only when a node
  represents a condition failure;
- do not put BT node fields in the generic trace core.

Compact export should not include full BT `node_results` by default. Rich
offline export may include the full payload.

## Future VLM Or Mock Payload

VLM payload is design-only in this stage. It should be introduced first through
a mock backend or fixture, not a real model call.

VLM payload v1 candidate:

```text
backend_family: "vlm"
payload_schema_version: "vlm_payload_v1"
payload_kind: "proposal"
prompt_id: str
evidence_ids: tuple[str, ...]
answer_summary: str
grounding: Mapping[str, object]
confidence: float | None
refusal_or_fallback_reason: str
validator_status: "not_run" | "accepted" | "rejected"
```

Rules:

- no raw images in payload;
- use evidence ids, not image bytes;
- no prompt text unless a later privacy/storage decision approves it;
- no direct requested effects from raw model answer without validation;
- rejected or refused proposals should map to `fallback_type` and reason codes
  in the generic trace.

This is where a future first-class `DecisionIntent` may become useful, but it
is still deferred.

## Mapping To Generic Trace Fields

Payload mapping should inform generic trace fields without duplicating all
payload internals.

Recommended mapping:

```text
backend_payload.backend_family -> backend_kind
backend_payload.payload_kind -> diagnostic_checks or reason_codes, when useful
result.decision_source -> decision_source
result.status -> decision_status
result.skill_before -> skill_before
result.skill_after -> skill_after
result.switch_reason -> switch_reason
result.effects -> requested_effects_summary
```

Selected operation mapping:

```text
legacy requested branch + skill_switch -> switch_skill
legacy requested branch + no_change -> continue_current_skill
legacy compatibility side effects -> switch_skill or continue_current_skill
BT continue fallback -> continue_current_skill
BT future handoff node -> return_handoff
VLM rejected proposal -> validator_reject
VLM accepted proposal -> depends on validated requested effects
```

Fallback type mapping:

```text
BT continue fallback -> continue_current_skill
VLM rejected proposal -> validator_reject
backend fail-closed -> fail_closed
ordinary legacy no-change -> none
ordinary skill switch -> none
```

Reason code mapping:

```text
legacy_fsm_branch_selected
legacy_fsm_compatibility_outcome
bt_node_selected
bt_continue_fallback
vlm_proposal_rejected
validator_reject
fail_closed
```

## Trace Parity Test Contract

Tests for Slice 2 should cover:

1. legacy requested branch result maps to `legacy_fsm_payload_v1`;
2. legacy compatibility outcome maps to `legacy_fsm_payload_v1` with
   `payload_kind == "compatibility_outcome"`;
3. BT continue fallback maps to `behavior_tree_payload_v1`;
4. generic trace assembled from legacy payload and BT payload has the same core
   field shape;
5. compact export excludes `backend_payload`;
6. rich export includes `backend_payload`;
7. payload mappings are JSON-compatible;
8. payload mapping does not require planner private fields.

Candidate test files:

```text
tests/test_primitive_decision_trace.py
tests/test_primitive_decision_backend_payload.py
```

Use focused synthetic results where possible. For BT shadow, a harness can call
`decide_context_with_trace` only when it is already available in the non-default
backend. Do not route production ticks through BT for this test.

## First Implementation Slice For Payload Mapping

Allowed files are likely:

```text
testbed/planner/primitive/report/decision_trace.py
tests/test_primitive_decision_backend_payload.py
docs/v2_5_design_sketch/backend_payload_mapping_detail.md
```

Optional if implementation needs a focused helper:

```text
testbed/planner/primitive/report/decision_payloads.py
```

Only create a separate helper if `decision_trace.py` would otherwise mix schema,
assembly, export, and backend payload mapping in one file.

Not allowed:

- production backend selector;
- default behavior change;
- new BT branch behavior;
- real VLM integration;
- Unity/offline writer integration;
- private planner state reads for trace enrichment.
