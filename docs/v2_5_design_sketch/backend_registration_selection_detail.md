# Backend Registration And Selection Detail

This document details Slice 6: Backend Selection And Registration. It defines
how decision backends become selectable, how experimental backends stay
explicit, and how unsupported names fail.

The default production backend remains `legacy_fsm`.

## Scope

This design covers:

- backend naming;
- registration owner;
- selector inputs;
- default behavior;
- shadow backend policy;
- promotion gates for future production use;
- tests for unsupported and explicit backend names.

This design does not cover:

- implementing new backend logic;
- trace schema changes;
- real VLM runtime;
- model configuration;
- Unity or offline eval file formats;
- silently promoting experimental backends.

## Current Runtime Baseline

Current owner:

```text
testbed/planner/primitive/decision/runtime.py
```

Current default:

```text
legacy_fsm
```

Current runtime shape:

- `PrimitiveDecisionRuntimeConfig.backend_name` selects a backend name;
- `PrimitiveDecisionRuntimePorts.backend_factories` supplies factory builders;
- backend names are normalized by stripping whitespace and lowercasing;
- unsupported names raise `PrimitiveDecisionContractError`;
- explicit tests can register `behavior_tree_shadow` through runtime ports.

This is a good baseline because it already separates default selection from
test/eval registration.

## Backend Names

Names must be stable snake-case strings.

Reserved or current names:

```text
legacy_fsm
behavior_tree_shadow
```

Future candidate names:

```text
vlm_shadow
learned_transition_shadow
hybrid_rule_model_shadow
external_decision_shadow
```

Naming rules:

- production-ready names should describe backend family and role;
- experimental names should include `_shadow`;
- names must not include dates, run ids, checkpoint ids, or one-off bug names;
- aliases should not be added until a compatibility need exists.

## Registration Policy

### Built-In Production Registry

Initial built-in production registry:

```text
legacy_fsm
```

Slice 6a implementation note:

- `testbed/planner/primitive/decision/runtime.py` exposes
  `PRODUCTION_DECISION_BACKEND_NAMES` as the public contract for built-in
  production backend names;
- the tuple is currently exactly `("legacy_fsm",)`;
- this export is a contract lock over the existing runtime ports/config shape,
  not a new global registry abstraction.

Policy:

- production default registry should stay minimal;
- adding a backend to the production registry is a promotion decision;
- promotion requires trace parity, validation, tests, and explicit design
  approval.

### Harness Or Eval Registry

Harness/eval code may register non-default factories explicitly.

Policy:

- shadow backends must be registered by the caller;
- shadow registration must not modify the production default;
- eval configs may select a shadow backend only through explicit backend name;
- missing shadow factory is an error, not an implicit fallback.

### Test Registry

Tests may construct `PrimitiveDecisionRuntimePorts` with a narrow registry.

Policy:

- tests should register only the backend under test and `legacy_fsm` when
  default comparison is required;
- tests should verify unsupported names fail closed.

## Selection Sources

Recommended selection order for future integration:

1. explicit test or harness argument;
2. eval config field;
3. runtime config object;
4. default `legacy_fsm`.

For v1 implementation, `PrimitiveDecisionRuntimeConfig.backend_name` is enough.
Do not add new config surfaces until a concrete caller needs them.

## Unsupported Backend Behavior

Unsupported backend names should:

- raise `PrimitiveDecisionContractError`;
- include the unsupported name;
- include registered backend names when possible;
- apply no requested effects;
- not silently fall back to `legacy_fsm`.

Reason:

- silent fallback makes eval comparisons invalid;
- production misconfiguration should be visible;
- shadow backend tests must prove they are actually using the selected backend.

## Shadow Backend Rules

A shadow backend:

- is never the default;
- must be explicitly registered;
- must be explicitly selected;
- should produce backend payload for trace;
- should run through proposal validation before requesting effects beyond
  no-change fallback;
- may support no legacy compatibility decision;
- must fail closed on contract errors.

`behavior_tree_shadow` is the current shadow backend family.

Future VLM or learned backends should start as shadow backends even if they only
emit no-change or rejected proposals.

## Promotion Gates

A backend can be considered for non-shadow or production selection only after:

1. trace parity exists against `legacy_fsm` for comparable ticks;
2. proposal validation accepts all effects it can produce;
3. fallback and handoff diagnostics are explainable;
4. online Unity compact trace and offline rich trace can consume its records;
5. tests prove unsupported names and missing factories fail closed;
6. rollout/eval evidence shows branch-order and switch-reason compatibility or
   an explicitly approved semantic change;
7. documentation states compatibility policy and non-goals.

Promotion is a separate design decision. This file does not approve promotion.

## Test Contract

Registration and selection tests should cover:

1. default runtime selects `legacy_fsm`;
2. explicit `behavior_tree_shadow` selection works only when registered;
3. unsupported backend name raises `PrimitiveDecisionContractError`;
4. unsupported backend name does not fall back to `legacy_fsm`;
5. backend names are normalized consistently;
6. missing shadow factory fails before effect application;
7. shadow backend remains absent from built-in production registry until
   explicitly promoted;
8. CLI/eval integration, when added, passes selector config into runtime
   without backend-specific imports in eval code.

Candidate test files:

```text
tests/test_primitive_decision_runtime.py
tests/test_primitive_behavior_tree_backend.py
tests/test_primitive_decision_backend_selection.py
```

## First Implementation Slice For This Detail

Preferred first implementation after validator work:

1. keep `legacy_fsm` as default;
2. document and test explicit shadow registration;
3. add focused unsupported-name tests if not already covered;
4. add eval/harness selector wiring only after trace adapters are stable;
5. avoid adding a new global registry until a second real caller needs it.

Allowed files are likely:

```text
testbed/planner/primitive/decision/runtime.py
testbed/planner/primitive/decision/backends/behavior_tree.py
tests/test_primitive_decision_runtime.py
tests/test_primitive_decision_backend_selection.py
docs/v2_5_design_sketch/backend_registration_selection_detail.md
```

Not allowed:

- silent default change;
- automatic import of every experimental backend in production runtime;
- unsupported-name fallback to `legacy_fsm`;
- selector logic inside backend modules;
- Unity/offline eval I/O in backend registry code.
