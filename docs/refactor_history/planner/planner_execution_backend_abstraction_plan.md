# Planner Execution Backend Abstraction Plan

Status: **historical supporting concept plan**.

The current implementation source of truth is now
`docs/planner_current_architecture.md`,
`docs/planner_scheduling_backend_design.md`, and
`docs/planner_current_code_architecture_plan.md`. Use this document for the
conceptual execution-kernel/backend direction only, not for active file
ownership, migration slices, parking decisions, or verification.
Do not execute the phases below directly; their role is background rationale for
the current-code plan.

This plan turns the current execution-backend analysis into a migration target.
It is intentionally not a runtime implementation. The next code round still
needs rollout or golden-trace evidence before moving planner behavior.

Baseline used for this plan:
`152350e3ed9a8816ca8d685195fc8f297ab3fcec`.

Reference diagram:
`docs/planner_execution_abstraction_flow.svg`.

Reference analysis:
`docs/planner_execution_backend_abstraction_analysis.md`.

## Design Goal

The target architecture is a stable primitive planner execution interface that
can host multiple atomic-action decision schemes:

- the baseline legacy finite-state machine
- a behavior-tree backend
- a VLM or LLM decision backend
- future learned, rule-table, or scheduler backends

All of those schemes must reuse the same execution semantics for observation
facts, gate metrics, token generation, coverage state, return-target planning,
debug state, rollout summary, low-level policy dispatch, and policy reset
timing.

The goal is not to make every backend inherit from the giant planner. The goal
is to extract the giant planner into an execution kernel that owns shared
capabilities and side effects, then compose decision backends behind a narrow
protocol.

## Architectural Layers

### Layer 1: Public Policy Adapter

`PrimitivePlannerACTPolicy` remains the public policy object used by rollout and
evaluation.

It keeps the stable external surface:

- `reset()`
- `predict(obs) -> action`
- `debug_state()`
- `rollout_summary()`
- `planner_trace()`

External callers should not need to know whether the active decision scheme is
the baseline state machine, a behavior tree, a VLM-backed policy, or another
backend.

Long-term responsibility:

- preserve public `Policy` compatibility
- translate config into execution-kernel construction
- expose debug and summary data in the existing public shape
- keep backend selection hidden behind stable configuration

### Layer 2: Primitive Planner Execution Kernel

The execution kernel is the first abstraction to extract because the baseline
planner couples execution order and state-machine decisions inside `predict()`.

The kernel owns the tick template:

1. prepare tick context from observation and previous action
2. update boundary event and pre-decision runtime facts
3. call the decision slot
4. validate and apply decision effects
5. dispatch scripted, pre-dig alignment, or ACT policy action
6. update previous action and post-decision counters
7. rebuild debug, trace, and rollout summary state
8. return the action

Proposed conceptual API:

- `prepare_tick(obs) -> PrimitiveTickPreparation`
- `decide_tick(preparation) -> PrimitiveDecisionResult`
- `apply_decision(result) -> None`
- `dispatch_action(obs) -> np.ndarray`
- `finalize_tick(action, result) -> np.ndarray`

At first, `decide_tick()` may still call the old inline state-machine body. That
is acceptable because the first target is to make execution order explicit
without changing behavior.

Long-term responsibility:

- state mutation
- effect application
- low-level action dispatch
- token planning and injection
- coverage and return-target runtime state
- debug, trace, and rollout summary assembly
- policy reset timing
- validation of backend-requested side effects

### Layer 3: Capability Port

Decision backends must not receive raw planner `self`. They receive a capability
port that exposes typed, stable planner facts.

The port is not a one-method-per-old-private-method facade. It groups stable
domain facts that multiple decision schemes can reuse.

Initial capability groups:

- observation and boundary facts
- bootstrap readiness
- pre-dig alignment status
- dig transition status
- carry transition status
- dump transition status
- return transition and envelope status
- coverage status
- token-source status
- timeout and hold-counter status
- low-level action-source availability

Port methods should return typed status records and diagnostics. They should not
perform irreversible state changes. Any requested mutation must come back as an
effect and be applied by the execution kernel.

### Layer 4: Decision Backend Protocol

Each backend owns only the decision scheme.

Proposed conceptual API:

- `reset() -> None`
- `tick(context, capabilities) -> PrimitiveDecisionResult`

The backend may choose branch order, behavior-tree node traversal, VLM decision
constraints, or other decision logic. It may read facts from the capability
port. It must not mutate planner state directly.

`PrimitiveDecisionResult` should contain:

- backend name
- decision status
- node or branch path
- switch reason
- ordered effects
- backend diagnostics

### Layer 5: Effect Application

Backends request side effects through explicit `PlannerEffect` values.

Candidate effects:

- `SetSkill`
- `ResetPolicyForSkill`
- `IncrementCounter`
- `ResetCounter`
- `EnsureDigCutPlan`
- `ClearDigCutPlan`
- `EnsureReturnTargetPlan`
- `CompleteCellEntryDig`
- `CompleteCoverageDig`
- `CompleteCoverageDump`
- `RejectCoverageCorridor`
- `RestartPreDigAlign`
- `RestartDigWithNewCut`
- `RequestCoverageTerminalStop`
- `RecordBackendDiagnostic`

The execution kernel owns effect validation and application order. This keeps
state mutation centralized and makes backend behavior auditable.

## Backend Fit

### Legacy State Machine Backend

This is the parity backend. It must reproduce the baseline `_maybe_switch_skill()`
branch order, reason strings, counter updates, reset timing, token flags, and
debug-visible outputs.

It should be introduced only after the execution template and enough capability
facts exist to express the baseline decisions without direct planner mutation.

### Behavior Tree Backend

A behavior tree should compile each tick into the same
`PrimitiveDecisionResult` contract.

Tree nodes may read capability-port facts and return effects, but they must not
own token assembly, coverage mutation, debug assembly, or low-level policy
dispatch.

### VLM Or LLM Decision Backend

A VLM backend should receive a constrained decision packet derived from the same
capability port.

The packet may include:

- active skill and lifecycle counters
- gate statuses
- compact geometry and coverage metrics
- token-source summaries
- allowed next effects
- current transition constraints

The model output must be parsed into a validated structured decision. Unsupported
effects, unknown skills, unconstrained reason strings, and direct planner
mutation must be rejected by the adapter.

### Future Decision Backends

Any learned scheduler, rule table, option policy, or experimental backend should
use the same backend protocol. If it needs new data, add a stable fact to the
capability port instead of reading planner-private fields.

## Migration Phases

### Phase 0: Baseline Rollback And Architecture Record

Status: completed for this working tree.

Completed scope:

- restored planner/runtime/eval/data/policy code to branch-created baseline
- preserved current docs, workflow guard, hook, and skill-support files
- documented baseline architecture
- added execution-backend analysis and SVG architecture diagram

No planner behavior migration occurred in this phase.

### Phase 1: Baseline Evidence Lock

Purpose: choose the first live behavior path and make it measurable.

Required outputs:

- selected rollout artifact or golden trace
- observed skill sequence
- observed switch reasons
- relevant debug keys
- relevant token-source flags
- relevant action-source decisions
- baseline method chain from `predict()` to decision, effect, dispatch, and
  debug update
- parity command for this path

Stop if no real rollout or golden trace can prove the path.

### Phase 2: Extract The Execution Template

Purpose: make the public tick execution order explicit before moving branch
logic.

Allowed large-file changes:

- split `predict()` into narrowly named execution-step methods
- keep old inline state-machine decisions as the only decision behavior
- preserve external `Policy` behavior and all debug/token/reset surfaces

Not allowed:

- behavior-tree backend
- VLM backend
- new switch thresholds
- changed reason strings
- token schema changes
- debug or rollout schema changes

Definition of done:

- `predict()` reads as a stable execution template
- old decision body is still behavior source of truth
- selected evidence path has parity for action source, switch reason, token
  flags, timeout state, and debug fields

### Phase 3: Introduce Decision Contracts

Purpose: create the typed boundary without moving branch logic yet.

New modules should be named by stable responsibility. Candidate ownership:

- `testbed/planner/primitive_execution.py` for execution contracts and effect
  application concepts
- `testbed/planner/primitive_capabilities.py` for capability-port protocols and
  typed status records
- `testbed/planner/primitive_decision.py` for backend protocol and decision
  result records

Exact file names may be adjusted after checking current small-module ownership.

Definition of done:

- contracts have focused tests
- no backend becomes a pass-through wrapper around old private methods
- `PrimitivePlannerACTPolicy` behavior is unchanged

### Phase 4: Extract Capability Port By Domain

Purpose: make reusable planner facts available to all backends without exposing
raw planner mutation.

Recommended order:

1. boundary and observation facts
2. pre-dig alignment status
3. dig transition status
4. carry and dump transition status
5. return transition and envelope status
6. token-source status
7. coverage status

Each slice must produce a typed status object or capability method that a future
backend can reuse.

Stop if the port starts mirroring old private method names one by one.

### Phase 5: Move Legacy FSM Behind Backend Protocol

Purpose: make the baseline state machine the first real backend.

Required behavior:

- exact baseline branch order
- exact reason strings unless explicitly approved otherwise
- exact effect order for the selected evidence path
- preserved policy reset timing
- preserved token and debug surfaces

Migration rule:

- backend returns effects
- execution kernel applies effects
- old inline branch body is deleted or reclassified after parity

Definition of done:

- legacy backend is the default parity path
- old inline state-machine implementation is removed or reduced to a thin
  compatibility entry with a removal condition

### Phase 6: Add Alternate Backends

Purpose: enable behavior tree, VLM, or future decision schemes only after the
legacy backend proves the shared contract.

Requirements:

- backend selection is hidden behind stable config
- backend outputs the same `PrimitiveDecisionResult`
- backend uses capability-port facts
- backend requests only validated effects
- rollout/eval callers continue using the same public policy surface

## Verification Matrix

Every code migration round chooses the smallest relevant subset, but must state
why the subset is sufficient.

Baseline and documentation rounds:

- `python scripts/planner_refactor_guard.py --check-plan-contract`
- `python scripts/planner_refactor_guard.py --check-skill-contract`
- `python -m pytest -q tests/test_planner_rollout_refactor_workflow.py`
- `git diff --check`

Execution-template extraction:

- focused tests for `predict()` action-source parity
- selected rollout or golden-trace parity
- debug schema check
- token flag check
- `python -m compileall` for changed modules
- guard checks

Contract and capability extraction:

- focused contract tests for status records and effects
- old-path compatibility or deletion tests
- selected evidence parity
- guard checks

Legacy backend migration:

- backend contract tests
- branch-order parity tests
- effect-order parity tests
- selected rollout or golden trace
- debug, rollout summary, and token-surface parity
- deletion or reclassification check for old inline code

Alternate backend addition:

- backend-specific contract tests
- invalid effect rejection tests
- selected rollout or dry-run validation
- no public API drift in eval/rollout callers

## Stop Conditions

Stop before code migration if:

- branch-created baseline has not been confirmed
- selected path has no rollout or golden-trace evidence
- baseline architecture map does not cover the selected path
- the proposed module mainly wraps old private methods
- behavior preservation depends on unverified assumptions
- effect order, reset timing, reason string, token schema, or debug schema is
  uncertain
- backend implementation needs raw planner mutation
- the large file is receiving new semantic branches instead of thin interface
  work

## First Slice Recommendation

The first code slice should be Phase 2, not backend extraction.

Recommended slice:

- keep `PrimitivePlannerACTPolicy.predict()` as the public entry point
- extract the tick skeleton into execution-step methods
- keep `_maybe_switch_skill()` as the only decision implementation
- prove selected-path parity

Reason:

The baseline planner is coupled at the execution-loop level. A backend boundary
introduced before the execution loop is explicit would either duplicate action,
token, debug, and reset semantics or become another pass-through facade.

## Design Principles

- Execution owns mutation.
- Backends own decisions.
- Capabilities expose facts, not planner internals.
- Effects are the only backend-to-execution mutation channel.
- Public rollout and eval APIs stay stable.
- Legacy FSM is the parity backend, not the architecture goal.
- Behavior tree and VLM backends are consumers of the same contract, not special
  paths.
- Delete or reclassify old inline code after parity; do not preserve it for
  comfort.
