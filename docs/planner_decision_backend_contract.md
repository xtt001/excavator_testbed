# Planner Decision Backend Contract

Status: **active decision-backend architecture and extension contract**.

This document captures the stable facts that survived the V2.5 decision-backend
work. It replaces the development sketch folder as the long-term reference for
decision backends, traces, validation, and future LLM/VLM planner integration.

It is not a slice log, handoff note, prompt, or implementation diary. When the
contract changes, update this document near the affected section.

## Current Maturity

The current planner is:

```text
default legacy FSM backendified with focused services
```

Current facts:

- production decision backend: `legacy_fsm`;
- production backend names: `("legacy_fsm",)`;
- non-default shadow backend: `behavior_tree_shadow`;
- backend selection and registration owner:
  `testbed/planner/primitive/decision/runtime.py`;
- backend decision input owner:
  `testbed/planner/primitive/decision/input.py`;
- backend-neutral trace owner:
  `testbed/planner/primitive/report/decision_trace.py`;
- trace export owner:
  `testbed/planner/primitive/report/decision_trace_export.py`;
- proposal validation owner:
  `testbed/planner/primitive/decision/validation.py`;
- validation-to-trace projection owner:
  `testbed/planner/primitive/report/decision_validation_trace.py`.

The planner is backend-ready at the contract level. It is not yet a production
system where BT, LLM, VLM, learned, hybrid, external, or plugin-routed backends
can be selected by user-facing config without additional promotion work.

## Core Runtime Graph

Decision backends choose and explain. Effect runtimes mutate focused planner
state.

```text
PrimitiveDecisionContext
  -> PrimitiveBackendDecisionInputBuilder
  -> PrimitiveBackendDecisionInput
  -> PrimitiveDecisionBackend.decide(...)
  -> PrimitiveDecisionResult
  -> DecisionProposalValidator
  -> RequestedEffectApplier
  -> focused runtime state owners

PrimitiveDecisionResult + backend_payload + tick metadata
  -> DecisionTraceRecord
  -> compact online trace / rich offline trace
```

The mutation path and trace path are separate. A backend may propose requested
effects through `PrimitiveDecisionResult`; it must not apply those effects
directly. Trace records explain the decision; they are not a second state source.

## Backend Contract

A decision backend should:

- consume `PrimitiveBackendDecisionInput`;
- read typed facts through `PrimitiveBackendFactsAccess` and focused fact views;
- return `PrimitiveDecisionResult`;
- optionally return or expose backend-specific `backend_payload`;
- rely on `RequestedEffectApplier` for mutation;
- run through proposal validation before effects are applied;
- produce traceable decisions through the report/trace owner.

A decision backend must not:

- import `testbed.policies.hybrid.primitive_planner`;
- depend on `PrimitivePlannerACTPolicy` private methods or broad planner-self
  callback bags;
- mutate coverage, token, return, cycle, execution, report, or ACT policy state
  directly;
- own Unity transport, offline replay files, rollout writers, HDF5 schema, or
  eval orchestration;
- change token order, token dimensions, switch reasons, reset timing, branch
  ordering, report keys, or default backend behavior without explicit semantic
  approval and tests.

## Decision Trace Contract

`DecisionTraceRecord` is the backend-neutral explanation record.

Stable responsibilities:

- capture backend name and backend kind;
- capture decision source and active skill before/after decision;
- capture decision status such as no-change versus skill switch;
- summarize requested effects;
- carry generic reasons and diagnostic checks;
- carry optional score or confidence fields;
- carry backend-specific payload in a nested payload field;
- support compact online export;
- support rich offline export.

Compact online traces should stay small and backend-neutral. Rich offline traces
may include sanitized backend payload details for debugging, replay, and
cross-backend comparison.

Backends do not own trace schema or export format. They only provide
backend-specific explanation payloads.

## Backend Payload Contract

`backend_payload` is explanation data. It must be JSON-compatible or safely
convertible to JSON-compatible values.

Allowed examples:

- `legacy_fsm`: branch name, legacy reason, source facts used for the decision;
- `behavior_tree_shadow`: selected node path, node statuses, fallback reason;
- future LLM/VLM backend: prompt id, evidence ids, model answer summary,
  confidence, refusal reason, grounding artifacts, fallback reason;
- future learned backend: model id, score vector summary, selected intent,
  uncertainty or confidence summary.

Forbidden payload content:

- planner objects;
- callbacks or mutation ports;
- raw images or large tensors;
- unbounded prompts or full model transcripts in compact traces;
- private policy instances;
- mutable state handles;
- duplicated token schema definitions.

## Proposal Validation Contract

`DecisionProposalValidator` is the fail-closed gate between backend output and
effect application.

The validator should reject proposals that are:

- structurally incomplete;
- unsupported for the selected backend;
- requesting effects outside the backend promotion level;
- low-confidence when a backend exposes confidence semantics;
- unsafe for the current active skill or transition state;
- inconsistent with the production backend policy.

Validation output is diagnostic. It should be visible through
`DecisionTraceRecord` so offline and online review can distinguish:

- backend made no proposal;
- backend proposed a no-op;
- backend proposal was accepted;
- backend proposal was rejected and fallback behavior was used;
- backend output was malformed or unsupported.

Validation must not become a new planner policy. It gates proposed effects; it
does not choose new targets, rewrite token semantics, or mutate runtime state.

## Registration And Selection Contract

`legacy_fsm` remains the only production backend by default.

`behavior_tree_shadow` is explicit-only:

- tests or focused harnesses may register the factory;
- production shell must not auto-register it as a user-facing alternative;
- missing shadow factory should fail fast instead of silently falling back;
- unsupported backend names should fail fast with a clear error.

Promotion of any non-default backend requires:

- explicit product decision;
- focused tests for factory registration and selection;
- proposal validation coverage;
- trace coverage through compact and rich exports;
- parity or rollout evidence for behavior-affecting branches;
- documentation update in this file and the current planner architecture doc.

## Behavior Tree Shadow Scope

`behavior_tree_shadow` is the first concrete alternate backend. Its current role
is to prove the contract, not to replace the production planner.

Current accepted scope:

- explicit harness registration;
- continue-current-skill fallback;
- node trace payloads;
- proposal validation integration;
- compact and rich trace export;
- one real return-completed transition branch.

Out of scope:

- complete BT rewrite of legacy FSM;
- generic blackboard;
- production default switch;
- backend-owned coverage, token, return, report, or ACT action state;
- silent promotion to user-facing config.

## LLM Or VLM Planner Integration Rules

Future LLM/VLM work should enter as a decision backend or as a scoped proposal
provider behind this contract. It should not bypass planner ownership.

The model-facing backend may propose:

- high-level candidate ranking;
- selected goal/cell/corridor intent;
- explanation payloads;
- confidence or refusal;
- fallback reason.

The model-facing backend must not own:

- HDF5/data schema;
- policy checkpoint loading;
- ACT action generation;
- Unity socket transport;
- coverage state mutation;
- token dimension/order definitions;
- return/dig handoff gate mutation;
- final effect application.

Model outputs should be converted into `PrimitiveDecisionResult` only after
typed parsing and validation. Raw text should never directly mutate planner
state.

## Verification Anchors

Current focused checks include:

- decision trace tests;
- behavior-tree shadow backend tests;
- proposal validation tests;
- backend selection tests;
- backend-ready import-contract tests;
- planner current-code parity tests;
- documentation inventory and architecture-contract guard.

Before changing this contract, run the smallest focused subset that covers the
changed owner and at least the documentation guard. If production backend
behavior can change, add parity or rollout evidence before claiming the backend
is promoted.
