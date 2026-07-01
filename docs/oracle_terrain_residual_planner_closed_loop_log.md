# Oracle Terrain Residual Planner Closed-Loop Log

This log records accepted executor callbacks, planner closure audits, reflection
verdicts, and the next bounded target for `Oracle Terrain Residual Planner v0`.

## 2026-07-01: Pre-Development Baseline

Accepted baseline commits:

- `cd787074ea001025c04b99030b17b10053df88e9`
  - Added the terrain residual planner conclusion and v0 plan.
  - Updated rollout review to keep local-surface command-depth separate from
    historical plane-depth diagnostics.
  - Updated return handoff review to ignore terminal-only incomplete return
    segments when completed `return -> dig` transitions are available.
- `342f813678aa7d47c489e2683be6f06589a881ee`
  - Added the closed-loop workflow profile and Phase 0A executor prompt.
  - Added the new workflow documents to the curated documentation guard.

Target lock after baseline:

- cwd: `/home/pingfan/PACT/excavator_testbed`
- branch: `tx/oracle-terrain-residual-planner-v0`
- HEAD: `342f813678aa7d47c489e2683be6f06589a881ee`
- upstream note: local branch still tracks `origin/tx/v2_6-llm-planner`
- dirty state before Phase 0A dispatch: clean

Verified before Phase 0A dispatch:

- `python -m pytest -q tests/test_rollout_review.py tests/test_planner_architecture_doc_contract.py`
- `python -m compileall testbed/eval/rollout_review.py tests/test_rollout_review.py scripts/planner_architecture_doc_guard.py tests/test_planner_architecture_doc_contract.py`
- `python scripts/planner_architecture_doc_guard.py --check-changed-docs ...`
- `python scripts/planner_architecture_doc_guard.py --check-doc-inventory`
- `python scripts/planner_architecture_doc_guard.py --check-architecture-contract`
- `git diff --check`

## 2026-07-01: Phase 0A Callback Audit

Executor slice:

- Phase 0A: terrain/depth metric provenance and baseline gap audit.
- Read-only. No code, docs, config, branch, or upstream edits allowed.

Executor status:

- Success.
- Worktree stayed clean.
- HEAD stayed `342f813678aa7d47c489e2683be6f06589a881ee`.

Accepted facts:

- `testbed/eval/rollout_review.py` builds diagnostic `depth_tracking`; it does
  not change eval success semantics.
- Local-surface command-depth uses contiguous jsonl `dig` rows:
  `dig_cut_tokens[7] * 0.8` as target and `env_state[31]` as
  `bucket_depth_below_local_surface_m` observed peak.
- Summary plane-depth diagnostics use summary `cycleN_depth_*` fields and the
  `env_state[8] bucket_depth_below_dig_area_plane_m` reference. This remains a
  historical diagnostic path, not the command-depth tracking source.
- `testbed/data/schema.py` exposes compact grid slices in `env_state`:
  surface-depth `[33:39]`, removed-depth `[39:45]`, target-depth `[45:51]`,
  and valid mask `[51:57]`.
- The HDF5 cycle contract exposes `/v2/cycle/actual_removed_depth_delta_grid`,
  `dominant_removed_depth_cell_id`, and `depth_outcome_source`.
- `testbed/cli/audit_dig_depth_semantics.py` already reads surface grid,
  removed-depth grid, plane depth, local depth, and cycle removed-depth arrays
  for audit.
- Rollout review does not currently output residual grids or bucket-aware
  residual metrics.

Current local artifact inventory:

- `runs/eval/` contains 121 `rollout_manifest.json` files, 119
  `rollout_000_summary.json` files, 91 `rollout_000_planner_trace.json` files,
  119 `rollout_000.jsonl` files, and 7 `rollout_review.json` files.
- The sampled current main run
  `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results/rollout_review.json`
  already has 10-cycle depth tracking, no evidence gaps, and handoff evidence
  from completed return-to-dig transitions.
- Sampled jsonl rows have `env_state` length 64 and contain the grid slices at
  `[33:57]`.

Missing Phase 0 facts:

- No current `TerrainStateProvider`, `terrain_state`, or `residual_metrics`
  implementation exists.
- No rollout review output field exists for current residual grid,
  bucket-aware residual metrics, confidence grid, grid frame, origin, cell
  size, or timestamp.
- No height/elevation grid source was found in current code/tests; only docs
  mention height/elevation.
- Existing review artifacts expose depth tracking and planned-vs-actual cycles,
  but not full target/current removed-depth residual curves.

Executor verification:

- `python -m pytest -q tests/test_rollout_review.py`: passed, 7 tests.
- `git diff --check`: passed.
- Read-only source checks used focused `rg`, `find`, `nl/sed`, and `jq`.

Planner closure audit:

- Target lock matched after callback.
- Callback was factual, scoped, and free of planner-directed strategy.
- No diff was left by the executor.
- The slice advanced the workflow by replacing a vague Phase 0 start with
  concrete source facts and missing facts.

Lightweight reflection:

- Reference used: user objective, Phase 0 acceptance in
  `docs/oracle_terrain_residual_planner_v0_plan.md`, and ownership boundaries
  in `AGENTS.md`.
- Alignment verdict: aligned. The callback confirmed that current rollout
  review has enough compact grid slices to start residual metric work, but not
  enough published residual outputs or terrain-state contract.
- Efficiency verdict: useful progress. This was a necessary read-only audit, not
  repeated verification or process-only churn.

Next bounded target:

- Phase 0B should define the minimal terrain-grid/residual metric contract for
  offline rollout review without changing production planner or gate behavior.
- The next executor prompt must refresh the live HEAD and dirty state before
  dispatch.

## 2026-07-01: Thread Execution Correction

User correction:

- Executor work should use newly created Codex conversation threads, not
  subagents, so the execution context is preserved as normal thread history.

Planner action:

- Closed the mistakenly spawned Phase 0B subagent before accepting any work from
  it.
- Updated `docs/oracle_terrain_residual_planner_closed_loop_profile.md` with a
  thread-only executor rule.

Workflow rule from this point:

- The planner dispatches bounded executor prompts through Codex threads.
- Callback collection is done by a thread message back to the planner.
- The planner must not poll while waiting; reading the executor thread is only a
  recovery fallback if callback delivery fails.
- Multi-agent subagents are out of scope unless the user explicitly reopens
  that mode.
