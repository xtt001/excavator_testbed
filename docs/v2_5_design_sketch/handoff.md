# V2.5 Decision Backend Handoff

This handoff records the current state after Slice 8a. It is a compact
resumption artifact, not a replacement for the detailed design files.

## Target Lock

```text
cwd: /home/pingfan/PACT/excavator_testbed
branch: fs/v2_5-BT-test
HEAD: ff7fa5035fa8624dd12a2646f76bb230e147a195
```

The worktree intentionally contains unstaged V2.5 docs/code/test files. The
executor did not stage, commit, push, or open a PR.

## Accepted Slices

- Slice 1: generic `DecisionTraceRecord` and compact/rich export helpers.
- Slice 2: legacy FSM and BT shadow payload parity into generic traces.
- Slice 3: fallback/handoff diagnostics projected from existing status facts.
- Slice 5a: strict proposal validator shell.
- Slice 5b: shadow/eval-only validator rejected fallback conversion.
- Slice 5c: validation outcome projection into generic traces.
- Slice 6a: backend selection contract lock with production names limited to
  `legacy_fsm`.
- Slice 7a: report-side decision trace export adapter entrypoint.
- Slice 8a: first real `behavior_tree_shadow` return-transition branch.

## Files And Owners

- `testbed/planner/primitive/decision/backends/behavior_tree.py`
  - non-default BT shadow backend and BT node behavior.
  - Slice 8a added `ReturnCompletedTransitionNode` before the continue
    fallback.
- `testbed/planner/primitive/decision/validation.py`
  - strict proposal validation and shadow fallback conversion.
- `testbed/planner/primitive/decision/runtime.py`
  - backend selection contract and production backend-name export.
- `testbed/planner/primitive/report/decision_trace.py`
  - backend-neutral trace record, assembler, payload mapping, and diagnostics.
- `testbed/planner/primitive/report/decision_validation_trace.py`
  - validation result to trace projection.
- `testbed/planner/primitive/report/decision_trace_export.py`
  - compact online and rich offline trace adapter entrypoints.
- `tests/test_primitive_behavior_tree_backend.py`
  - real BT shadow backend tests, including Slice 8a return-transition path.
- `tests/test_primitive_decision_trace.py`
  - generic trace, payload, and diagnostic mapping tests.
- `tests/test_primitive_decision_proposal_validation.py`
  - strict validator and shadow fallback tests.
- `tests/test_primitive_decision_validation_trace.py`
  - validation projection tests.
- `tests/test_primitive_decision_backend_selection.py`
  - backend selection contract tests.
- `tests/test_primitive_decision_trace_eval_integration.py`
  - trace export adapter tests.

## Verification Bundle

```bash
/home/pingfan/miniconda3/bin/python -m pytest -q \
  tests/test_primitive_behavior_tree_backend.py \
  tests/test_primitive_decision_trace_eval_integration.py \
  tests/test_primitive_decision_backend_selection.py \
  tests/test_primitive_decision_proposal_validation.py \
  tests/test_primitive_decision_trace.py \
  tests/test_primitive_decision_validation_trace.py

/home/pingfan/miniconda3/bin/python -m compileall \
  testbed/planner/primitive/decision \
  testbed/planner/primitive/report

git diff --check

git status --short --branch
```

Additional Slice 8a source checks:

```bash
grep -R -n -E "fake_external|external_shadow|external_requested" \
  testbed/planner/primitive/decision/backends/behavior_tree.py \
  tests/test_primitive_behavior_tree_backend.py || true

grep -n -E "refresh_return_transition_state|sync_dig_transition_reason" \
  testbed/planner/primitive/decision/backends/behavior_tree.py || true
```

## Current Behavior

- Production default remains `legacy_fsm`.
- Production backend names remain exactly `("legacy_fsm",)`.
- `behavior_tree_shadow` is explicit-only: callers must register its factory
  and select it by name.
- `PrimitiveDecisionResult -> RequestedEffectApplier` remains the only mutation
  path.
- The real BT return-transition branch reads existing `ReturnTransitionStatus`
  only when the current skill is `return`.
- Completed return status returns approved requested effects only:
  `CompleteReturnTransitionEffect`,
  `SwitchToNextSkillAfterReturnEffect`, and
  `MarkReturnNextDigEventSeenEffect` when `next_dig_event` is true.
- Incomplete or irrelevant BT return checks fail with node trace and fall back
  to explicit no-change continue-current-skill behavior.
- Compact online trace stays backend-payload-free by default.
- Rich offline trace may include safe BT backend payload and validation summary.

## Preserved No-Goals

- No production default backend change.
- No automatic production registration of `behavior_tree_shadow`.
- No VLM runtime, prompt, model, or config surface.
- No `DecisionIntent`.
- No generic blackboard.
- No Unity socket, offline writer, replay loader, or eval runner integration.
- No direct planner mutation from BT nodes.
- No legacy compatibility action calls from BT nodes.
- No requested-effect applier semantic changes.
- No legacy FSM branch-order or reason-string changes.

## Stopping Point

Slice 8a implemented and tested the first real BT return-transition branch.
This executor round stops here and leaves continuation to a future
user-approved planner slice.
