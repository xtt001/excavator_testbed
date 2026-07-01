# Oracle Terrain Residual Planner Closed-Loop Profile

This document is the workflow profile for closed-loop development of
`Oracle Terrain Residual Planner v0`. It turns the user-confirmed design
discussion into a durable reference that planner and executor prompts must copy
or cite before every bounded slice.

## Canonical Hard Rules

Every planner-to-executor prompt, planner resume, callback audit, recovery
prompt, and context-compaction handoff must include this block near the top.
Executor prompts must put `thinking: xhigh` or `thinking: high` as the first
non-empty line before the block.

```markdown
Hard rules:
- Planner owns goal, target lock, scope, reflection, recovery, closure, and the next slice.
- Planner must challenge unnecessary existing code and choose slices that solve the user's problem, not only protect the old shape.
- Planner owns work allocation: bundle tightly coupled work, split only for distinct ownership/risk/verification.
- Executor performs one bounded slice only and returns facts, not strategy, advice, or next tasks.
- Event-driven loop: planner yields after dispatch and resumes only on callback, blocker, or user update; no empty polling.
- Failure is a callback: executor reports exact failure facts and stops; planner redeploys or escalates.
- Reflection: lightweight after every callback; deep every 3 accepted callbacks and after any failed or misaligned callback, against the user-confirmed reference base copied into recursive prompts.
- Verification is role-specific: executor runs slice checks; planner audits diff/scope/evidence and avoids duplicate reruns unless a distinct risk requires them.
- Config: use only `thinking: xhigh` or `thinking: high`; do not invent model/tool/runtime values; do not change runtime config unless explicitly allowed, sourced, and verified.
- Closure: executor green is not accepted closure; planner rechecks target lock, diff/status, docs/prompts/guards, verification, and audit log before the next dispatch.
```

## Confirmed Reference Base

- User objective: before connecting an LLM planner, prove whether a numerical
  terrain residual planner can make a target pit shape converge over multiple
  excavation cycles.
- Ideal target state: with simulation ground-truth terrain, the system can
  compute target/current removed-depth residual, generate bucket-aware candidate
  cuts, score effect/capability risk, execute through the existing ACT
  interface, and show residual convergence under bucket-aware tolerance.
- Source-of-truth documents:
  - `docs/llm_planner_closed_loop_terrain_conclusion.md`
  - `docs/oracle_terrain_residual_planner_v0_plan.md`
  - `docs/planner_to_act_conceptual_contract.md`
  - `docs/data_processing_hdf5_qc_contract.md`
  - `docs/training_setup.md`
  - `AGENTS.md`
- Current baseline commit after the pre-development cleanup:
  `cd787074ea001025c04b99030b17b10053df88e9`.
- Current local branch:
  `tx/oracle-terrain-residual-planner-v0`.
- Current upstream note: the local branch still tracks
  `origin/tx/v2_6-llm-planner`; do not push or change upstream unless the user
  explicitly asks.

Historical planner-refactor memory is useful only as workflow context. Paths,
branch names, old guard script names, and HEAD locks from earlier planner
refactor rounds are stale until rechecked live.

## Scope

The route is:

```text
target terrain
-> current terrain
-> residual
-> candidate cuts
-> effect / capability scoring
-> ACT local execution
-> terrain update
-> residual convergence review
```

This workflow does not start by connecting an LLM to low-level cut selection.
LLM/VLM work is deferred until the numerical residual loop has evidence.

## Non-Goals

- Do not directly connect an LLM planner to low-level cut selection.
- Do not put a full height grid into ACT.
- Do not train a large end-to-end grid world model in v0.
- Do not block v0 on real-machine terrain reconstruction.
- Do not change production dig gate semantics without shadow evidence and user
  confirmation.
- Do not use `success=1.0`, completed cycle count, or mean payload as the main
  acceptance criterion.
- Do not change branch, upstream, remote, dependencies, runtime config,
  feature flags, checkpoint contracts, token dimensions/order, or public eval
  success semantics unless explicitly authorized and verified.

## Ownership Boundaries

- `data` owns HDF5 I/O, rollout data reading, schema constants, and derived
  data fields.
- `eval` owns residual metrics, baseline reports, and offline review.
- `planner` owns target selection, candidate cuts, handoff, gates, and replan
  decisions.
- `policy` and adapters own ACT inputs/outputs, checkpoint loading, and
  normalization; they do not own task-level terrain semantics.
- CLI modules only parse arguments and orchestrate; complex logic must live in
  focused library modules.

New long-term modules must be named by stable responsibility, such as terrain
state, residual metrics, candidate generation, effect model, capability filter,
or residual planner. Do not name library code after a date, one run, or a
temporary experiment.

## Phase Order

### Phase 0: Metric Provenance And Interface Contract

- Identify the current removed-depth / height-grid source, frame, resolution,
  timestamp, and confidence assumptions.
- Document or implement the minimal `TerrainStateProvider` data contract.
- Separate local-surface command-depth tracking from historical plane-depth
  diagnostics.
- Project the current main run onto residual / overdig / payload baseline
  metrics.

Acceptance:

- Every metric has a source field and computation rule.
- Current rollout review can reproduce the key residual / overdig / payload
  values used as baseline evidence.

### Phase 1: Bucket-Aware Task Metrics

- Implement target-grid generation for the T1 large shallow rectangle.
- Implement positive residual, negative residual, boundary tolerance,
  target-volume completion, outside protected overdig, depth RMSE, and
  bucket-aware shape IoU.
- Record a per-cycle residual convergence curve.

Acceptance:

- The report can answer whether the current planner moves toward a specified
  target shape, not only whether it completed cycles.

### Phase 2: Shape-Guard Shadow Audit

- Add shadow-only rollout review fields for shape-guard stop points.
- Do not change production gate behavior.
- Distinguish payload-driven continued digging from residual-positive continued
  digging.

Acceptance:

- The audit can show where `low_payload_shape_guard_stop`,
  `overdig_guard_stop`, or `depth_budget_exhausted` would trigger, and whether
  those events correlate with real overdig.

### Phase 3: Discrete Candidate Generation

- Generate 20-100 candidate cuts around positive residual regions.
- Include bucket footprint, boundary tolerance, depth budget, and
  return/alignment cost.
- Keep this offline until the candidate set is shown to be sane.

Acceptance:

- Candidate cuts cover major positive residual regions and reject obvious
  out-of-bound, unreachable, or guaranteed-overdig cuts.

### Phase 4: Heuristic Effect Model

- Implement a geometric swept-footprint kernel.
- Output expected delta patch, removed volume, overdig volume, payload proxy,
  and footprint.

Acceptance:

- Offline or simulated closed-loop residual planning with the heuristic effect
  model improves target residual metrics over the current planner baseline, or
  the failure is traced to candidate design, target design, or gate assumptions.

### Phase 5: Calibrated Effect And Capability

- Calibrate the effect model with gold samples using episode split.
- Add uncertainty estimates.
- Fit or implement capability filtering for `P_success`, `P_overdig`, and
  `P_low_payload`.

Acceptance:

- Candidate ranking improves over the heuristic model.
- Overdig-risk recall is treated as more important than average-error polish.

### Phase 6: Oracle Closed-Loop Simulation

- Compare:
  - A: current planner
  - B: residual planner + heuristic effect model
  - C: residual planner + calibrated effect model + capability filter
- Run T1/T2 multi-cycle simulations.

Acceptance:

- B beats A to prove residual closed-loop value.
- C beats B to prove calibration value.
- If neither beats A, pause runtime integration and diagnose target design,
  candidate generation, shape guard, terrain state, or ACT predictability.

### Phase 7: Runtime Gate Intervention

Only after Phase 2 and Phase 6 support it, add runtime shape guard behind an
explicit flag.

Acceptance:

- Overdig decreases without unacceptable payload, deposited-fraction,
  cycle-count, handoff, or state-machine regressions.

## First Executor Slice: Phase 0A

Phase 0A is read-only.

Goal:

- Audit current terrain/depth metric provenance and identify the smallest
  implementation slice needed for Phase 0.

In scope:

- `testbed/eval/rollout_review.py`
- `tests/test_rollout_review.py`
- `testbed/data/schema.py`
- `testbed/data/operator_first_v2_2.py`
- Current rollout review docs listed in the reference base.
- Current run artifacts only if present locally under `runs/eval/`.

Out of scope:

- No code edits.
- No new modules.
- No config changes.
- No branch, upstream, fetch, pull, push, reset, checkout, or rebase.
- No production gate behavior changes.

Expected callback facts:

- Current terrain/depth fields found.
- Missing terrain-grid source facts.
- Existing review fields that can serve Phase 0.
- Minimal next implementation slice proposal as facts only, not strategy.
- Verification commands run, or why read-only verification was unavailable.

## Callback Schema

Every executor callback must use this schema.

```markdown
Status: success | partial | failed
Target lock observed:
Callback route used:
TDD red:
Skill compliance block observed:
  - target lock first:
  - fact-only callback:
  - reference base copied:
  - config discipline:
  - responsibility scope:
Files changed:
Config touched: none | read-only | changed
Config values used or changed:
  - value:
  - source verified from:
  - verification command:
What changed:
What was verified:
Behavior preserved:
Phase evidence:
Failure facts, if partial/failed:
  - exact command/action that failed:
  - error text or failing assertion:
  - likely failing area, if directly evidenced:
  - partial changes left in worktree:
  - checks not run and why:
Unknowns/blockers:
Diff/status summary:
HEAD after:
```

Forbidden in callbacks:

- Strategic advice to the planner.
- Next-task instructions.
- Broad architecture recommendations.
- Claims not backed by files, diffs, tests, reports, or logs.

## Planner Closure Gate

Before accepting any callback and dispatching the next slice, the planner must:

- Recheck cwd, branch, HEAD, upstream note, and worktree status.
- Inspect changed files or confirm read-only status.
- Confirm callback scope and fact-only discipline.
- Compare evidence against the confirmed reference base.
- Sync docs, prompts, guards, or tests if workflow state changed.
- Run only the planner-side checks needed for closure risk.
- Record lightweight reflection after every callback.
- Run deep reflection after every 3 accepted callbacks or after any failed or
  misaligned callback.

Executor green is not closure.
