# V2.5 Decision Backend Implementation Progress

This file records accepted implementation slices and planner reflection gates
for the V2.5 decision-backend infrastructure branch. It is a workflow log, not
a replacement for the design detail files.

Target lock for this sequence:

```text
cwd: /home/pingfan/PACT/excavator_testbed
branch: fs/v2_5-BT-test
expected base HEAD: ff7fa5035fa8624dd12a2646f76bb230e147a195
```

## Accepted Slices

### Slice 1: Generic Decision Trace Record

Status: accepted.

Planner audit:

- added backend-neutral `DecisionTraceRecord` and assembler/export helpers;
- compact trace excludes backend payload by default;
- rich trace includes JSON-safe backend payload summary;
- no runtime wiring or backend default change.

Verification observed:

```text
pytest tests/test_primitive_decision_trace.py
pytest tests/test_primitive_behavior_tree_backend.py
compileall testbed/planner/primitive/report testbed/planner/primitive/decision
git diff --check
```

### Slice 2: Trace Adoption Parity

Status: accepted.

Planner audit:

- added legacy FSM payload mapping;
- added BT shadow node-trace payload mapping;
- kept compact trace generic and payload-free;
- kept rich trace as the backend-specific payload surface;
- no runtime wiring or backend default change.

Verification observed:

```text
pytest tests/test_primitive_decision_trace.py tests/test_primitive_behavior_tree_backend.py
compileall testbed/planner/primitive/report testbed/planner/primitive/decision
git diff --check
```

### Slice 3: Fallback-Handoff Diagnostic Mapping

Status: accepted.

Planner audit:

- added report-side diagnostic mapping for dig, carry, dump, and return status
  objects;
- kept mappings shape-based over existing status fields;
- did not add new facts, new handoff semantics, or owner-side mutable state.

Verification observed:

```text
pytest tests/test_primitive_decision_trace.py tests/test_primitive_behavior_tree_backend.py
compileall testbed/planner/primitive/report testbed/planner/primitive/decision testbed/planner/primitive/facts
git diff --check
```

### Slice 5a: Strict Proposal Validator Shell

Status: accepted.

Planner audit:

- added `DecisionProposalValidator.validate(...)` strict-mode API;
- validation lives in `testbed/planner/primitive/decision/validation.py`;
- decision validation does not import report/trace modules;
- no effect application, runtime wiring, backend selection, or default backend
  change.

Verification observed:

```text
pytest tests/test_primitive_decision_proposal_validation.py tests/test_primitive_decision_trace.py tests/test_primitive_behavior_tree_backend.py
compileall testbed/planner/primitive/decision testbed/planner/primitive/report
git diff --check
```

### Slice 5b: Shadow Fallback Conversion

Status: accepted.

Planner audit:

- added `DecisionProposalValidator.validate_with_shadow_fallback(...)`;
- invalid proposals convert to safe no-change results for shadow/eval use;
- rejected requested effects are not applied or invoked;
- strict `validate(...)` still raises invalid proposals.

Verification observed:

```text
pytest tests/test_primitive_decision_proposal_validation.py tests/test_primitive_decision_trace.py tests/test_primitive_behavior_tree_backend.py
compileall testbed/planner/primitive/decision testbed/planner/primitive/report
git diff --check
```

### Slice 5c: Proposal-Validation Trace Projection

Status: accepted.

Planner audit:

- added report-side `decision_validation_trace.py` projection owner;
- added generic `validation_status` pass-through in `decision_trace.py`;
- compact trace now carries validation status while still excluding backend
  payload;
- rich trace includes a safe validation summary;
- decision validation still has no report/trace dependency.

Verification observed:

```text
pytest tests/test_primitive_decision_proposal_validation.py tests/test_primitive_decision_trace.py tests/test_primitive_behavior_tree_backend.py tests/test_primitive_decision_validation_trace.py
compileall testbed/planner/primitive/decision testbed/planner/primitive/report
git diff --check
```

### Slice 6a: Backend Selection Contract Lock

Status: accepted.

Planner audit:

- added `PRODUCTION_DECISION_BACKEND_NAMES` as the public production backend
  name contract;
- kept production backend names exactly `("legacy_fsm",)`;
- proved `behavior_tree_shadow` is explicit-only and absent from production
  names;
- proved missing or unknown backend names fail closed without legacy fallback;
- did not add a new global registry abstraction or config surface.

Verification observed:

```text
pytest tests/test_primitive_decision_backend_selection.py tests/test_primitive_decision_runtime.py tests/test_primitive_behavior_tree_backend.py tests/test_primitive_decision_proposal_validation.py tests/test_primitive_decision_trace.py tests/test_primitive_decision_validation_trace.py
compileall testbed/planner/primitive/decision testbed/planner/primitive/report
git diff --check
```

### Slice 7a: Decision Trace Export Adapter Entrypoint

Status: accepted.

Planner audit:

- added report-side `decision_trace_export.py` adapter owner;
- exposed compact online and rich offline trace dictionary entrypoints from
  `DecisionTraceRecord`;
- kept the adapter pure data projection with no backend imports, eval I/O,
  planner runtime hooks, sockets, writers, or default backend changes;
- tolerated absent trace records by returning `None`.

Verification observed:

```text
pytest tests/test_primitive_decision_trace_eval_integration.py tests/test_primitive_decision_trace.py tests/test_primitive_decision_validation_trace.py tests/test_primitive_decision_backend_selection.py tests/test_primitive_behavior_tree_backend.py tests/test_primitive_decision_proposal_validation.py
compileall testbed/planner/primitive/report testbed/planner/primitive/decision
git diff --check
```

### Slice 8a: Real BT Return-Transition Branch

Status: accepted.

Executor audit:

- added real `behavior_tree_shadow` return-completed node before the continue
  fallback;
- kept non-return ticks from reading return transition facts;
- return skill reads existing `ReturnTransitionStatus` lazily;
- completed return status returns approved requested effects only:
  `CompleteReturnTransitionEffect`,
  `SwitchToNextSkillAfterReturnEffect`, and
  `MarkReturnNextDigEventSeenEffect` when the next-dig event is present;
- proved the selected BT path through explicit runtime selection, strict
  proposal validation, generic trace assembly, and compact/rich trace export;
- kept `legacy_fsm` as the production default and kept BT explicit-only.

Verification observed:

```text
pytest tests/test_primitive_behavior_tree_backend.py tests/test_primitive_decision_trace_eval_integration.py tests/test_primitive_decision_backend_selection.py tests/test_primitive_decision_proposal_validation.py tests/test_primitive_decision_trace.py tests/test_primitive_decision_validation_trace.py
compileall testbed/planner/primitive/decision testbed/planner/primitive/report
git diff --check
```

## Deep Reflection After Slice 5c

Date: 2026-06-29.

Reference base:

- user goal: generic decision-backend infrastructure for BT, VLM, learned, and
  external backends;
- core graph:
  `DecisionBackend -> PrimitiveDecisionResult -> RequestedEffectApplier`, plus
  trace records/adapters for compact online and rich offline evaluation;
- source-of-truth docs in this folder;
- current maturity boundary: default legacy FSM remains production default, and
  this branch is not yet fully swappable backend architecture.

Verdict: aligned.

Rationale:

- Slices 5a through 5c moved a real backend-facing contract boundary:
  proposal validation, shadow fallback, and validation trace visibility.
- The work did not add a generic blackboard, VLM prompt/model config, backend
  default switch, runtime mutation path, or BT branch expansion.
- The report/decision boundary remains one-way: report consumes decision
  validation outcomes, while decision validation does not depend on report or
  trace modules.
- Verification is proving contract shape and safety behavior rather than only
  local import success.

Efficiency verdict: useful progress.

The loop is still moving infrastructure toward backend interchangeability, not
only preserving old code. The next slice should move to backend registration and
selection shell work. It should stay contract-level and avoid runtime default
changes until the selector behavior is test-locked.

## Current Stop Point After Slice 8a

User correction, 2026-06-29:

- the first backend integration test should use the real
  `behavior_tree_shadow` backend, not a fake or mock external backend;
- fake/mock backends may still be useful later for narrow contract tests, but
  they should not be the first proof that this infrastructure can run a new
  backend.

Slice 8a implemented the first real BT branch:

- added one `behavior_tree_shadow` branch for return-completed transition;
- kept `continue_current_skill` as the explicit fallback;
- used existing `ReturnTransitionStatus` and approved requested effects only;
- tested the real BT path through explicit backend selection, proposal
  validation, generic trace assembly, and compact/rich trace export;
- did not change the production default, add fake/mock backend integration, add
  VLM runtime, or move mutable planner state into BT nodes.

This round stops here after final planner-side verification and commit. Any next
backend branch or eval I/O wiring requires a new user-approved planner slice.
