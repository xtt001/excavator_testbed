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

Thread selection:

- Active executor thread: `019f1d6b-1367-71f3-8cb1-c4d891769109`.
- Duplicate fork `019f1d6b-4f86-7a81-86ad-65d1fb46acfe` was archived and must
  not be used for future dispatch.

## 2026-07-01: Phase 0B Callback Audit

Executor thread:

- `019f1d6b-1367-71f3-8cb1-c4d891769109`

Executor slice:

- Phase 0B: minimal offline terrain-grid/residual metric contract in rollout
  review.

Executor status:

- Partial, because the executor observed target-lock HEAD drift. The executor
  started from `c9b6c30b276ca5aa27b356a67186f824d51a68dc`; the planner later
  committed thread-routing docs and moved HEAD to
  `0dfbb97d12ff49726334210ef95fc6bdd2970bec`.
- The executor left five expected slice files in the worktree and reported the
  drift as failure facts instead of broadening scope.

Accepted implementation facts:

- Added focused owner `testbed/eval/terrain_residual_metrics.py`.
- Kept `testbed/eval/rollout_review.py` as thin integration: it imports and
  calls `build_terrain_residual_summary()` and attaches the returned diagnostic
  block.
- Added `terrain_residual` to per-rollout review output.
- Residual metrics use the latest usable compact dig-area `env_state` snapshot:
  removed-depth `[39:45]`, target-depth `[45:51]`, valid mask `[51:57]`, and
  long/short grid counts.
- Missing provenance remains explicit for confidence grid, height/elevation
  grid, cell size, origin, timestamp, and frame transform.
- Added focused tests in `tests/test_terrain_residual_metrics.py`.
- Added thin rollout-review integration coverage in `tests/test_rollout_review.py`.
- Updated `docs/training_setup.md` to document the diagnostic-only
  `terrain_residual` block.

Planner closure audit:

- Planner-side target lock after callback:
  - branch: `tx/oracle-terrain-residual-planner-v0`
  - HEAD: `0dfbb97d12ff49726334210ef95fc6bdd2970bec`
  - dirty files: only the five expected Phase 0B files.
- The callback was factual, scoped, and included the target-lock mismatch as a
  failure fact.
- The mismatch was caused by a planner-side workflow-doc commit during executor
  execution, not by executor repo mutation outside scope.
- The diff matched the Phase 0B ownership boundary and did not touch planner,
  policy, token, checkpoint, dependency, config, branch, or runtime behavior.

Planner-side verification:

- `python -m pytest -q tests/test_terrain_residual_metrics.py tests/test_rollout_review.py`
  passed, 11 tests.
- `python -m compileall testbed/eval/terrain_residual_metrics.py testbed/eval/rollout_review.py tests/test_terrain_residual_metrics.py tests/test_rollout_review.py`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-changed-docs docs/training_setup.md`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-doc-inventory`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-architecture-contract`
  passed.
- `git diff --check` passed.

Lightweight reflection:

- Reference used: user objective, Phase 0 acceptance, ownership boundaries, and
  thread execution rule.
- Alignment verdict: aligned after planner audit. Phase 0 now has a minimal
  residual diagnostic contract without changing production planner/gate/policy
  behavior.
- Efficiency verdict: useful implementation progress. The only process cost was
  the expected recovery from planner-caused HEAD drift.

Next bounded target:

- Commit the accepted Phase 0B implementation.
- Then dispatch the next slice back to active executor thread
  `019f1d6b-1367-71f3-8cb1-c4d891769109` with a refreshed HEAD.

## 2026-07-01: Phase 0C Callback Audit

Executor thread:

- `019f1d6b-1367-71f3-8cb1-c4d891769109`

Executor slice:

- Phase 0C: read-only current-run terrain residual projection using the Phase 0B
  rollout-review diagnostic contract.

Executor status:

- Success.
- Worktree stayed clean.
- HEAD stayed `868b32c4ab0898e0d52ab668f9b8f42c022d89d6`.

Accepted current-run facts:

- Inspected
  `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results`.
- Built `build_rollout_review(results_dir)` in memory only. The results
  directory file count stayed unchanged and no new files were written.
- Built review status remained `overall_status: needs_root_cause_audit`,
  `evidence_gaps: []`, and `llm_candidate_ranking_ready: false`.
- Terrain residual status was `present` from
  `rollout_jsonl_env_state_compact_dig_area_grid`.
- The latest usable compact-grid snapshot was row index `6147` with grid shape
  `[3, 2]`, six valid cells, and target depth sum `0.479999989272`.
- Removed depth grid:
  `[0.058014947921, 0.136428371072, 0.067671462893, 0.181556522846, 0.042310595512, 0.128402650356]`.
- Target depth grid:
  `[0.079999998212, 0.079999998212, 0.079999998212, 0.079999998212, 0.079999998212, 0.079999998212]`.
- Residual depth grid:
  `[0.021985050291, -0.05642837286, 0.012328535319, -0.101556524634, 0.0376894027, -0.048402652144]`.
- Positive residual depth sum was `0.07200298831`.
- Overdig depth sum was `0.206387549638`.
- Removed depth sum was `0.6143845506`.
- Target removed completion ratio was `0.8499937710015274`.

Accepted related baseline facts:

- Quality/deposit review fields were present with `quality_status: issue`,
  `quality_issue_count: 183`, `low_cycle_deposited_fraction_count: 9`, and
  `cycle_deposited_fraction_min: 0.5727734176718415`.
- Planned/actual cycle fields were present for 10 cycles, including
  `deposited_fraction`, `depth_target_m`, `depth_peak_m`, and planned/actual
  entry/exit x fields.
- Depth tracking fields were present:
  - local-surface cycle count `10`, mean error `0.03357278704643249`, and abs max
    error `0.20337753295898436`;
  - summary-plane cycle count `10`, mean error `0.15730891823768617`, and abs max
    error `0.25914466381073`;
  - expert p95 overshoot count `10`, mean `0.06820847994384767`, and max
    `0.15047275149154665`.
- Handoff fields were present with `handoff_status: ready`,
  `handoff_source: rollout_jsonl_completed_return_to_dig_transitions`,
  `return_to_dig_entry_close: true`,
  `return_to_dig_entry_error_m: 0.33865916140467844`, and
  `completed_handoff_count: 9`.
- Coverage fields were present with `coverage_decision_trace_count: 22` and
  `coverage_terminal_stop_reason: dig_area_depleted`.

Still-missing facts after Phase 0C:

- Confidence grid, height grid, elevation grid, cell size, origin, timestamp,
  and frame transform remain missing.
- Current overdig, target, and removed values are depth sums, not physical
  volumes, because cell size is missing.
- Only the latest usable compact grid snapshot is reported. A per-cycle
  residual convergence curve is not yet present.
- Payload-named fields are not exposed by the built rollout review, although
  existing summary fields include mass/deposit information.

Executor verification:

- `python -m pytest -q tests/test_terrain_residual_metrics.py tests/test_rollout_review.py`
  passed, 11 tests.
- Read-only `build_rollout_review()` current-run projection completed without
  writing files.
- Read-only key search confirmed deposit/depth/handoff availability and
  payload-named field absence.
- `git diff --check` passed.
- Final `git status --short --branch` was clean on
  `tx/oracle-terrain-residual-planner-v0`, ahead 6 from
  `origin/tx/v2_6-llm-planner`.

Planner closure audit:

- Target lock matched after callback:
  - branch: `tx/oracle-terrain-residual-planner-v0`
  - HEAD: `868b32c4ab0898e0d52ab668f9b8f42c022d89d6`
  - dirty state: clean
- Callback was factual, read-only, and scoped to current-run projection.
- No planner, production runtime, policy, token, checkpoint, dependency,
  config, branch, upstream, or eval success semantics changed.
- The callback closes Phase 0 by proving that current rollout review can
  reproduce the key residual and overdig depth-sum baseline from the latest
  compact grid snapshot.

Lightweight reflection:

- Reference used: user objective, Phase 0 acceptance in
  `docs/oracle_terrain_residual_planner_v0_plan.md`, thread execution rule in
  this log/profile, and ownership boundaries in `AGENTS.md`.
- Alignment verdict: aligned. The workflow now has source-proven current-run
  residual baseline evidence without pretending that missing grid provenance
  exists.
- Efficiency verdict: useful progress. Phase 0C was read-only but directly
  projected the latest run into the newly added residual contract, not repeated
  process.

## 2026-07-01: Deep Reflection After Three Accepted Callbacks

Trigger:

- Three accepted callbacks since the latest deep reflection gate: Phase 0A,
  Phase 0B, and Phase 0C.

Reference base:

- User objective: prove whether numerical terrain residual planning can make a
  target pit shape converge before connecting an LLM planner.
- Source-of-truth documents:
  `docs/llm_planner_closed_loop_terrain_conclusion.md`,
  `docs/oracle_terrain_residual_planner_v0_plan.md`,
  `docs/oracle_terrain_residual_planner_closed_loop_profile.md`, this log,
  `docs/planner_to_act_conceptual_contract.md`,
  `docs/data_processing_hdf5_qc_contract.md`, `docs/training_setup.md`, and
  `AGENTS.md`.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `tx/oracle-terrain-residual-planner-v0`, upstream unchanged, no push/fetch/
  pull/reset/checkout/rebase.

Deep reflection verdict:

- Phase 0 is accepted as a minimal metric-provenance baseline. The workflow now
  knows where residual depth comes from, which provenance fields remain missing,
  and what the latest current-run residual/overdig depth-sum baseline is.
- The loop should not spend another slice on read-only inventory unless a new
  blocker appears. The next useful work is a bounded Phase 1 diagnostic metric
  increment in the existing `eval` owner.
- The workflow must continue to treat current compact-grid values as depth sums
  until cell size exists. Do not rename them to volumes or infer physical volume.
- Missing confidence, height/elevation, origin, timestamp, frame transform, and
  payload-named fields are explicit constraints, not permission to invent data.
- Thread execution is now stable: the active executor thread is
  `019f1d6b-1367-71f3-8cb1-c4d891769109`; the duplicate fork remains archived
  and out of scope.

Next bounded target:

- Phase 1A should add a diagnostic residual convergence curve to the focused
  `terrain_residual_metrics` owner and rollout review.
- The curve must be derived only from usable compact-grid snapshots already
  present in rollout jsonl. It should report per-snapshot or per-completed-dig
  residual depth-sum points with source/provenance fields.
- If cycle segmentation cannot be determined unambiguously from existing
  records without broadening scope, the executor must return exact blocker
  facts instead of inventing official per-cycle semantics.
- Do not add target-shape generation, bucket-aware IoU, candidate generation,
  production planner behavior, runtime gates, token/checkpoint changes, or
  physical volume metrics in Phase 1A.

## 2026-07-01: Phase 1A Callback Audit

Executor thread:

- `019f1d6b-1367-71f3-8cb1-c4d891769109`

Executor slice:

- Phase 1A: diagnostic residual convergence curve in the existing
  `terrain_residual_metrics` owner and rollout review output.

Executor status:

- Success.
- Worktree target lock matched at start.
- HEAD stayed `1f189bbfa44aa67eee30171d4ca2ad177f701bef`.
- Four expected files were modified:
  `testbed/eval/terrain_residual_metrics.py`,
  `tests/test_terrain_residual_metrics.py`, `tests/test_rollout_review.py`, and
  `docs/training_setup.md`.

Accepted implementation facts:

- Added `residual_convergence_curve` to the diagnostic `terrain_residual` block.
- Added provenance fields:
  `residual_convergence_curve_status`,
  `residual_convergence_curve_source`, and
  `residual_convergence_curve_window`.
- The curve source is
  `rollout_jsonl_contiguous_dig_segments_final_usable_env_state_compact_dig_area_grid`.
- The curve window is the final usable compact-grid snapshot per contiguous
  rows where `skill_name == "dig"`.
- Curve points are dig-segment diagnostic evidence, not official cycle IDs.
- `dig_segment_index` is one-based over contiguous dig segments; segments
  without a usable compact grid snapshot are skipped.
- Each point records `dig_segment_index`, `snapshot_row_index`,
  positive residual depth sum, overdig depth sum, target/removed depth sum,
  completion ratio, and valid cell count.
- Latest-snapshot fields and computations remain unchanged.
- Missing provenance remains explicit. No confidence, height/elevation, cell
  size, origin, timestamp, frame transform, physical volume, candidate, or
  runtime planner semantics were invented.
- `docs/training_setup.md` now documents the curve semantics and limitations.

TDD evidence:

- The first attempted selector was not a valid red because no tests were
  selected.
- Valid red:
  `python -m pytest -q tests/test_terrain_residual_metrics.py tests/test_rollout_review.py -k "convergence_curve"`
  failed with `KeyError: 'residual_convergence_curve_status'`.
- Focused green:
  `python -m pytest -q tests/test_terrain_residual_metrics.py tests/test_rollout_review.py -k "convergence_curve or terrain_residual"`
  passed with 5 tests selected.

Planner-side current-run projection:

- Built the current run review in memory only for
  `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results`.
- No files were written.
- Latest snapshot remained row `6147`, positive residual `0.07200298831`,
  overdig `0.206387549638`, and completion ratio
  `0.8499937710015274`.
- Curve status was `present` with 10 points.
- First curve point: segment `1`, row `416`, positive residual
  `0.427303199075`, overdig `0.0`, target depth sum `0.479999989272`,
  removed depth sum `0.052696790197`, completion ratio
  `0.10978498203077769`, valid cell count `6`.
- Last curve point: segment `10`, row `5821`, positive residual
  `0.078868877143`, overdig `0.194965198636`, target depth sum
  `0.479999989272`, removed depth sum `0.596096310765`, completion ratio
  `0.8356898356130845`, valid cell count `6`.

Planner-side verification:

- `python -m pytest -q tests/test_terrain_residual_metrics.py tests/test_rollout_review.py`
  passed, 12 tests.
- `python -m compileall testbed/eval/terrain_residual_metrics.py testbed/eval/rollout_review.py tests/test_terrain_residual_metrics.py tests/test_rollout_review.py`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-changed-docs docs/training_setup.md`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-doc-inventory`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-architecture-contract`
  passed.
- `git diff --check` passed.

Planner closure audit:

- Target lock matched after callback:
  - branch: `tx/oracle-terrain-residual-planner-v0`
  - HEAD: `1f189bbfa44aa67eee30171d4ca2ad177f701bef`
  - dirty files: only the four expected Phase 1A files before planner log sync
- Callback was factual, scoped, and free of planner-directed strategy.
- Diff stayed inside the allowed eval owner, tests, and closest documentation.
- No planner runtime, gate, policy, token, checkpoint, dependency, config,
  branch, upstream, or eval success semantics changed.

Lightweight reflection:

- Reference used: user objective, Phase 1 acceptance in
  `docs/oracle_terrain_residual_planner_v0_plan.md`, `AGENTS.md` ownership
  boundaries, and the thread execution rule.
- Alignment verdict: aligned. The review can now show residual trend evidence
  across dig progress for the current compact-grid baseline.
- Efficiency verdict: useful progress. The slice added a necessary metric
  surface rather than adding another inventory pass.
- Accepted-slice count since the latest deep reflection is now `1/3`.

Next bounded target:

- Phase 1B should add a compact diagnostic convergence summary derived from
  `residual_convergence_curve`, still inside the focused eval owner.
- The summary should report start/end/delta for positive residual, overdig, and
  completion ratio, plus curve point count and a diagnostic trend status.
- It must remain depth-sum based, not physical volume based, until cell size
  exists.
- It must not add target-shape generation, bucket-aware IoU, candidate
  generation, production planner behavior, runtime gates, token/checkpoint
  changes, or official cycle-id semantics.

## 2026-07-01: Phase 1B Callback Audit

Executor thread:

- `019f1d6b-1367-71f3-8cb1-c4d891769109`

Executor slice:

- Phase 1B: diagnostic residual convergence summary derived from
  `residual_convergence_curve`.

Executor status:

- Success.
- Worktree target lock matched at start.
- HEAD stayed `6e786c7d58f7f969b13bc19251faaa2f41eba726`.
- Four expected files were modified:
  `testbed/eval/terrain_residual_metrics.py`,
  `tests/test_terrain_residual_metrics.py`, `tests/test_rollout_review.py`, and
  `docs/training_setup.md`.

Accepted implementation facts:

- Added `terrain_residual["residual_convergence_summary"]`.
- The summary is derived only from `residual_convergence_curve`.
- Summary status is:
  - `present` for at least two curve points;
  - `insufficient_points` for one curve point;
  - `missing` for zero curve points.
- Summary source is `residual_convergence_curve`.
- It reports point count, start/end dig-segment indices, start/end/delta
  positive residual depth sum, start/end/delta overdig depth sum, and
  start/end/delta target-removed completion ratio.
- Delta is always end minus start.
- Diagnostic trend values are:
  `positive_residual_reduced_overdig_increased`,
  `positive_residual_reduced_overdig_not_increased`,
  `positive_residual_not_reduced`, `insufficient_points`, and `missing`.
- Existing latest-snapshot fields and Phase 1A curve fields/computation remain
  unchanged.
- Missing provenance remains explicit. No confidence, height/elevation, cell
  size, origin, timestamp, frame transform, physical volume, candidate, target
  shape, or official cycle-id semantics were inferred.
- `docs/training_setup.md` now documents the summary field and its diagnostic
  limitations.

TDD evidence:

- Valid red:
  `python -m pytest -q tests/test_terrain_residual_metrics.py tests/test_rollout_review.py -k "convergence_summary"`
  failed with two expected `KeyError: 'residual_convergence_summary'` failures.
- Focused green for the same selector passed with 2 tests selected.

Planner-side current-run projection:

- Built the current run review in memory only for
  `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results`.
- File count stayed 10 and no files were written.
- Curve point count was 10.
- First curve point: segment `1`, row `416`, positive residual
  `0.427303199075`, overdig `0.0`, target depth sum `0.479999989272`,
  removed depth sum `0.052696790197`, completion ratio
  `0.10978498203077769`, valid cell count `6`.
- Last curve point: segment `10`, row `5821`, positive residual
  `0.078868877143`, overdig `0.194965198636`, target depth sum
  `0.479999989272`, removed depth sum `0.596096310765`, completion ratio
  `0.8356898356130845`, valid cell count `6`.
- Projected summary status was `present` with 10 points.
- Projected positive residual delta was `-0.348434321932`.
- Projected overdig delta was `0.194965198636`.
- Projected completion-ratio delta was `0.725904853582`.
- Projected diagnostic trend was
  `positive_residual_reduced_overdig_increased`.

Planner-side verification:

- `python -m pytest -q tests/test_terrain_residual_metrics.py tests/test_rollout_review.py`
  passed, 14 tests.
- `python -m compileall testbed/eval/terrain_residual_metrics.py testbed/eval/rollout_review.py tests/test_terrain_residual_metrics.py tests/test_rollout_review.py`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-changed-docs docs/training_setup.md`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-doc-inventory`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-architecture-contract`
  passed.
- `git diff --check` passed.

Planner closure audit:

- Target lock matched after callback:
  - branch: `tx/oracle-terrain-residual-planner-v0`
  - HEAD: `6e786c7d58f7f969b13bc19251faaa2f41eba726`
  - dirty files: only the four expected Phase 1B files before planner log sync
- Callback was factual, scoped, and free of planner-directed strategy.
- Diff stayed inside the allowed eval owner, tests, and closest documentation.
- No planner runtime, gate, policy, token, checkpoint, dependency, config,
  branch, upstream, or eval success semantics changed.

Lightweight reflection:

- Reference used: user objective, Phase 1 acceptance in
  `docs/oracle_terrain_residual_planner_v0_plan.md`, `AGENTS.md` ownership
  boundaries, and the thread execution rule.
- Alignment verdict: aligned. The review now directly summarizes whether
  residual decreased and what overdig cost was observed in the compact-grid
  baseline.
- Efficiency verdict: useful progress. This slice converted the Phase 1A curve
  into a compact diagnostic signal, not a separate process artifact.
- Accepted-slice count since the latest deep reflection is now `2/3`.

Next bounded target:

- Phase 1C should add a pure eval target-grid contract/generator for explicit
  T1-like rectangular shallow-pit specs.
- The generator should accept explicit grid shape, valid mask, rectangle cell
  selection, and target depth. It must not invent official T1 default size,
  depth, cell size, origin, or physical area semantics.
- Keep this in focused eval code with tests and docs. It should produce a
  target-depth grid and target-region mask that later residual metrics can
  consume.
- Do not connect the generator to runtime planner behavior, rollout success
  semantics, candidate generation, bucket-aware IoU, boundary metrics, physical
  volumes, or official cycle IDs in Phase 1C.

## 2026-07-01: Phase 1C Callback Audit

Executor thread:

- `019f1d6b-1367-71f3-8cb1-c4d891769109`

Executor slice:

- Phase 1C: explicit target-grid contract/generator for T1-like rectangular
  shallow-pit specs.

Executor status:

- Success.
- Worktree target lock matched at start.
- HEAD stayed `d75d7aac3cf12e779d07b21680b37a3993154804`.
- Expected slice files were modified or added:
  `testbed/eval/terrain_target_grid.py`,
  `tests/test_terrain_target_grid.py`, and `docs/training_setup.md`.

Accepted implementation facts:

- Added new focused eval owner `testbed/eval/terrain_target_grid.py`.
- Added public function `build_rectangular_target_grid()`.
- The generator uses explicit parameters only:
  `grid_shape`, `valid_mask`, half-open row/column rectangle bounds,
  `target_depth_m`, and optional `profile`.
- Source is `explicit_rectangular_target_grid_spec`.
- Default profile is `explicit_t1_like_rectangular_shallow_pit`; this names a
  diagnostic profile, not an inferred runtime target.
- Grid ordering is row-major. For grid shape `[3, 2]`, index is
  `row_index * 2 + col_index`.
- Present output includes status, source, profile, grid shape, target-depth
  grid, target-region mask, valid cell count, target cell count, target depth
  sum, invalid target cell count, rectangle bounds, validation errors, and
  explicit missing provenance statuses.
- Implemented validation statuses:
  `invalid_grid_shape`, `invalid_valid_mask`, `invalid_target_depth`,
  `invalid_rectangle_bounds`, and `invalid_target_region_mask`.
- Rectangle selections that include invalid cells are rejected as
  `invalid_target_region_mask`; invalid cells are not silently treated as
  target cells.
- No rollout-review integration was added in this slice.
- No official T1 default dimensions, default target depth, cell size, origin,
  physical area, world-frame semantics, physical volume, eval success semantics,
  or runtime planner behavior were introduced.

TDD evidence:

- Initial red:
  `python -m pytest -q tests/test_terrain_target_grid.py` failed during
  collection with `ModuleNotFoundError: No module named 'testbed.eval.terrain_target_grid'`.
- Additional validation red:
  `python -m pytest -q tests/test_terrain_target_grid.py -k "invalid_mask_value"`
  failed because the expected invalid-mask-value message was not yet returned.
- Focused target-grid green passed with 7 tests.

Planner-side verification:

- `python -m pytest -q tests/test_terrain_target_grid.py tests/test_terrain_residual_metrics.py tests/test_rollout_review.py`
  passed, 21 tests.
- `python -m compileall testbed/eval/terrain_target_grid.py testbed/eval/terrain_residual_metrics.py testbed/eval/rollout_review.py tests/test_terrain_target_grid.py tests/test_terrain_residual_metrics.py tests/test_rollout_review.py`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-changed-docs docs/training_setup.md`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-doc-inventory`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-architecture-contract`
  passed.
- `git diff --check` passed.

Planner closure audit:

- Target lock matched after callback:
  - branch: `tx/oracle-terrain-residual-planner-v0`
  - HEAD: `d75d7aac3cf12e779d07b21680b37a3993154804`
  - dirty files: only the expected Phase 1C files before planner log sync
- Callback was factual, scoped, and free of planner-directed strategy.
- Diff stayed inside the allowed eval owner, focused tests, and closest
  documentation.
- No planner runtime, gate, policy, token, checkpoint, dependency, config,
  branch, upstream, or eval success semantics changed.

Lightweight reflection:

- Reference used: user objective, Phase 1 target-shape evaluation requirements
  in `docs/oracle_terrain_residual_planner_v0_plan.md`, `AGENTS.md` ownership
  boundaries, and the thread execution rule.
- Alignment verdict: aligned. The workflow now has an explicit target-grid
  contract for later shape metrics instead of relying only on the rollout's
  current compact target field.
- Efficiency verdict: useful progress. This was a necessary bridge from
  baseline residual diagnostics to specified target-shape evaluation.
- Accepted-slice count since the latest deep reflection is now `3/3`.

## 2026-07-01: Deep Reflection After Phase 1A-1C

Trigger:

- Three accepted callbacks since the latest deep reflection gate: Phase 1A,
  Phase 1B, and Phase 1C.

Reference base:

- User objective: prove whether numerical terrain residual planning can make a
  specified target pit shape converge before connecting an LLM planner.
- Phase 1 acceptance in `docs/oracle_terrain_residual_planner_v0_plan.md`:
  the report must answer whether the current planner moves toward a specified
  pit shape, not only whether it completed cycles.
- Source-of-truth documents:
  `docs/llm_planner_closed_loop_terrain_conclusion.md`,
  `docs/oracle_terrain_residual_planner_v0_plan.md`,
  `docs/oracle_terrain_residual_planner_closed_loop_profile.md`, this log,
  `docs/planner_to_act_conceptual_contract.md`,
  `docs/data_processing_hdf5_qc_contract.md`, `docs/training_setup.md`, and
  `AGENTS.md`.
- Target lock: cwd `/home/pingfan/PACT/excavator_testbed`, branch
  `tx/oracle-terrain-residual-planner-v0`, upstream unchanged, no push/fetch/
  pull/reset/checkout/rebase.

Deep reflection verdict:

- Phase 1A and Phase 1B were aligned: they made residual trend and overdig cost
  visible across dig progress for the current compact-grid baseline.
- Phase 1C was aligned: it adds an explicit target-grid contract so the workflow
  can stop conflating the current rollout target field with the task-specified
  target shape.
- The loop is still serving the original objective. It is moving from baseline
  diagnostics toward target-shape evaluation without touching runtime planner
  behavior.
- The major remaining gap is target-shape residual metrics: the repo can now
  generate an explicit target grid, but it cannot yet compute final or
  per-segment target-shape residual metrics from that target grid and observed
  removed-depth snapshots.
- Verification is still proving meaningful behavior, not only local green
  checks: tests cover missing provenance, curve construction, summary deltas,
  and explicit target-grid validation.
- Non-goals still hold. Do not add official T1 defaults, physical volumes,
  world-frame semantics, bucket-aware IoU, boundary tolerance, candidate
  generation, runtime gates, or eval pass/fail semantics until the required
  source facts and user decisions exist.
- Thread execution remains stable through the active executor thread
  `019f1d6b-1367-71f3-8cb1-c4d891769109`.

Next bounded target:

- Phase 1D should add standalone explicit-target residual metrics that compare
  observed removed-depth grids against a caller-supplied target-depth grid and
  target-region mask.
- The metrics should be pure eval diagnostics and should likely live in a
  focused module or in the existing target-grid owner if that remains the
  narrowest responsibility.
- It should compute depth-sum metrics only: target-region positive residual,
  target-region overdig, target completion ratio, outside-target removed-depth
  sum, and validity/status fields.
- It should accept explicit arrays and masks only. Do not read rollout files,
  infer official T1 defaults, infer physical volume, or integrate with
  rollout_review in Phase 1D unless strictly needed for focused tests.
- After Phase 1D, a later slice can connect the explicit target-grid and
  target-shape metrics to current-run offline projection.

## 2026-07-01: Phase 1D Callback Audit

Executor thread:

- `019f1d6b-1367-71f3-8cb1-c4d891769109`

Executor slice:

- Phase 1D: standalone explicit-target residual metrics.

Executor status:

- Success.
- Worktree target lock matched at start.
- HEAD stayed `824c3349e31eebb30bcd1c30f3939c31984c245d`.
- Expected slice files were modified or added:
  `testbed/eval/terrain_target_metrics.py`,
  `tests/test_terrain_target_metrics.py`, and `docs/training_setup.md`.

Accepted implementation facts:

- Added new focused eval owner `testbed/eval/terrain_target_metrics.py`.
- Added public function `build_target_residual_metrics()`.
- Inputs are explicit arrays only:
  `removed_depth_grid_m`, `target_depth_grid_m`, `target_region_mask`, and
  `valid_mask`.
- Source is `explicit_target_grid_removed_depth_comparison`.
- Default profile is `explicit_target_shape_residual_metrics`.
- Output includes `residual_depth_grid_m = target_depth_grid_m - removed_depth_grid_m`
  in matching row-major order.
- Present output includes status, source, profile, cell counts, valid target and
  outside-target counts, target positive residual depth sum, target overdig
  depth sum, target depth sum, target removed-depth sum, target completion
  ratio, outside-target removed-depth sum, invalid target cell count,
  validation errors, and explicit missing provenance statuses.
- Metrics are depth sums only, not physical volumes.
- Target metrics are computed over valid target cells only.
- Outside-target removed-depth sum is computed over valid non-target cells.
- Completion ratio is `sum(min(removed, target)) / target_depth_sum_m` when
  target depth sum is positive, otherwise `None`.
- Implemented validation statuses: `invalid_grid_lengths`,
  `invalid_depth_values`, `invalid_mask_values`, and
  `invalid_target_region_mask`.
- Target cells outside the valid mask are rejected as
  `invalid_target_region_mask` and are not silently counted.
- No rollout-review integration was added in this slice.
- No official T1 default dimensions, default target depth, cell size, origin,
  world-frame semantics, physical volume, bucket-aware IoU, boundary tolerance,
  protected-area band, depth RMSE, candidate/effect/capability semantics, eval
  success semantics, or official cycle IDs were introduced.

TDD evidence:

- Initial red:
  `python -m pytest -q tests/test_terrain_target_metrics.py` failed during
  collection with `ModuleNotFoundError: No module named 'testbed.eval.terrain_target_metrics'`.
- Focused metric green passed with 7 tests.

Planner-side verification:

- `python -m pytest -q tests/test_terrain_target_metrics.py tests/test_terrain_target_grid.py tests/test_terrain_residual_metrics.py tests/test_rollout_review.py`
  passed, 28 tests.
- `python -m compileall testbed/eval/terrain_target_metrics.py testbed/eval/terrain_target_grid.py testbed/eval/terrain_residual_metrics.py testbed/eval/rollout_review.py tests/test_terrain_target_metrics.py tests/test_terrain_target_grid.py tests/test_terrain_residual_metrics.py tests/test_rollout_review.py`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-changed-docs docs/training_setup.md`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-doc-inventory`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-architecture-contract`
  passed.
- `git diff --check` passed.

Planner closure audit:

- Target lock matched after callback:
  - branch: `tx/oracle-terrain-residual-planner-v0`
  - HEAD: `824c3349e31eebb30bcd1c30f3939c31984c245d`
  - dirty files: only the expected Phase 1D files before planner log sync
- Callback was factual, scoped, and free of planner-directed strategy.
- Diff stayed inside the allowed eval owner, focused tests, and closest
  documentation.
- No planner runtime, gate, policy, token, checkpoint, dependency, config,
  branch, upstream, or eval success semantics changed.

Lightweight reflection:

- Reference used: user objective, Phase 1 target-shape evaluation requirements
  in `docs/oracle_terrain_residual_planner_v0_plan.md`, `AGENTS.md` ownership
  boundaries, and the thread execution rule.
- Alignment verdict: aligned. The workflow can now compute explicit
  target-shape residual metrics independently of the rollout's current compact
  target field.
- Efficiency verdict: useful progress. This slice created the missing metric
  primitive needed before current-run explicit target projection.
- Accepted-slice count since the latest deep reflection is now `1/3`.

Next bounded target:

- Phase 1E should add a standalone offline projection helper that applies an
  explicit rectangular target spec to rollout records and computes latest
  target-shape residual metrics from the latest usable compact-grid snapshot.
- The helper should compose the existing target-grid generator and
  target-shape metric owner. Avoid duplicating metric formulas.
- It should accept explicit target spec parameters only and should not define
  official T1 defaults.
- It may read current-run records in tests or an optional read-only projection,
  but it must not write generated review artifacts or change rollout-review
  schema/eval success semantics in Phase 1E.
- Keep physical volumes, cell size, world-frame semantics, bucket-aware IoU,
  boundary tolerance, candidate generation, runtime gates, and official cycle
  IDs out of scope.

## 2026-07-01: Phase 1E Callback Audit

Executor thread:

- `019f1d6b-1367-71f3-8cb1-c4d891769109`

Executor slice:

- Phase 1E: standalone explicit-target latest-snapshot rollout projection.

Executor status:

- Success.
- Worktree target lock matched at start.
- HEAD stayed `b2f5b09fe76ae2a3378bfbc4a38c802f37be7218`.
- Expected slice files were modified or added:
  `testbed/eval/terrain_target_projection.py`,
  `tests/test_terrain_target_projection.py`, and `docs/training_setup.md`.

Accepted implementation facts:

- Added new focused eval owner `testbed/eval/terrain_target_projection.py`.
- Added public function `build_latest_target_residual_projection()`.
- Source is `rollout_jsonl_latest_compact_grid_explicit_target_projection`.
- The projection reads explicit rollout records, extracts the latest usable
  compact-grid removed-depth and valid-mask snapshot, builds an explicit
  rectangular target grid, and calls `build_target_residual_metrics()`.
- It uses schema constants for compact-grid long count, short count,
  removed-depth slice, and valid-mask slice.
- It uses observed `removed_depth_grid_m` and `valid_mask` from the latest
  snapshot plus the explicit target spec. It does not use the rollout's current
  target-depth grid as the task target.
- Output includes status, source, snapshot row index, observed grid shape,
  target spec grid shape, observed removed-depth grid, valid mask, target grid,
  target residual metrics, and explicit missing provenance statuses.
- No usable compact-grid snapshot returns `missing_snapshot` with empty observed
  arrays and no target grid or metrics.
- Target-grid validation failures are surfaced as projection status, with
  target metrics left unset.
- If observed compact grid counts do not match six cells, observed grid shape
  is `None` while the explicit target spec and metrics can still be reported
  from the six-cell compact arrays.
- No rollout-review integration or schema change was added.
- No official T1 default dimensions, default target depth, cell size, origin,
  physical area, world-frame semantics, physical volume, eval success
  semantics, or runtime planner behavior was introduced.

TDD evidence:

- Initial red:
  `python -m pytest -q tests/test_terrain_target_projection.py` failed during
  collection with `ModuleNotFoundError: No module named 'testbed.eval.terrain_target_projection'`.
- Focused projection green passed with 4 tests.

Planner-side current-run smoke projection:

- Used explicit non-official example spec:
  `grid_shape=[3, 2]`, `row_start=0`, `row_end=2`, `col_start=0`,
  `col_end=1`, `target_depth_m=0.25`, `official_t1_default=False`.
- Read
  `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results/rollouts/rollout_000.jsonl`.
- File count stayed 10 and no files were written.
- Projection status was `present`.
- Snapshot row index was `6147`.
- Observed grid shape was `[3, 2]`.
- Target grid status was `present`.
- Target cell count was `2`.
- Target depth sum was `0.5`.
- Target residual metric status was `present`.
- Target positive residual depth sum was `0.374313589186`.
- Target overdig depth sum was `0.0`.
- Target removed completion ratio was `0.251372821628`.
- Outside-target removed depth sum was `0.488698139786`.

Planner-side verification:

- `python -m pytest -q tests/test_terrain_target_projection.py tests/test_terrain_target_metrics.py tests/test_terrain_target_grid.py tests/test_terrain_residual_metrics.py tests/test_rollout_review.py`
  passed, 32 tests.
- `python -m compileall testbed/eval/terrain_target_projection.py testbed/eval/terrain_target_metrics.py testbed/eval/terrain_target_grid.py testbed/eval/terrain_residual_metrics.py testbed/eval/rollout_review.py tests/test_terrain_target_projection.py tests/test_terrain_target_metrics.py tests/test_terrain_target_grid.py tests/test_terrain_residual_metrics.py tests/test_rollout_review.py`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-changed-docs docs/training_setup.md`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-doc-inventory`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-architecture-contract`
  passed.
- `git diff --check` passed.

Planner closure audit:

- Target lock matched after callback:
  - branch: `tx/oracle-terrain-residual-planner-v0`
  - HEAD: `b2f5b09fe76ae2a3378bfbc4a38c802f37be7218`
  - dirty files: only the expected Phase 1E files before planner log sync
- Callback was factual, scoped, and free of planner-directed strategy.
- Diff stayed inside the allowed eval owner, focused tests, and closest
  documentation.
- No planner runtime, gate, policy, token, checkpoint, dependency, config,
  branch, upstream, or eval success semantics changed.

Lightweight reflection:

- Reference used: user objective, Phase 1 target-shape evaluation requirements
  in `docs/oracle_terrain_residual_planner_v0_plan.md`, `AGENTS.md` ownership
  boundaries, and the thread execution rule.
- Alignment verdict: aligned. The workflow can now project an explicit target
  spec onto current rollout evidence without changing rollout review schema.
- Efficiency verdict: useful progress. This slice composed existing focused
  owners into the missing latest-snapshot projection instead of duplicating
  target metric formulas.
- Accepted-slice count since the latest deep reflection is now `2/3`.

Next bounded target:

- Phase 1F should add a standalone explicit-target residual convergence curve
  over contiguous `dig` segments, using final usable compact-grid snapshots per
  segment and the explicit rectangular target spec.
- The implementation should compose the existing latest-snapshot projection,
  target-grid owner, and target-metric owner where practical, avoiding copied
  formulas.
- It should output per-segment target-shape metrics plus a compact summary of
  start/end/delta for target positive residual, target overdig, target
  completion ratio, and outside-target removed-depth sum.
- It must remain explicit-parameter, depth-sum-only, diagnostic-only, and
  standalone. Do not add rollout-review integration, official T1 defaults,
  physical volume, boundary tolerance, bucket-aware IoU, candidate generation,
  runtime gates, eval success semantics, or official cycle IDs in Phase 1F.

## 2026-07-01: Phase 1F Callback Audit

Executor thread:

- `019f1d6b-1367-71f3-8cb1-c4d891769109`

Executor slice:

- Phase 1F: standalone explicit-target residual convergence projection.

Executor status:

- Success.
- Worktree target lock matched at start.
- HEAD stayed `3cdd82228ddb5c31f20e3d5b1b94d11aec81a135`.
- Expected slice files were modified:
  `testbed/eval/terrain_target_projection.py`,
  `tests/test_terrain_target_projection.py`, and `docs/training_setup.md`.

Accepted implementation facts:

- Added public function `build_target_residual_convergence_projection()` to the
  focused eval owner `testbed/eval/terrain_target_projection.py`.
- Source is `rollout_jsonl_dig_segments_explicit_target_residual_convergence`.
- Curve window is the final usable compact-grid snapshot per contiguous row
  segment where `skill_name == "dig"`.
- Contiguous dig segments are numbered one-based; segments without a usable
  compact-grid snapshot are skipped.
- The function builds the explicit rectangular target grid with
  `build_rectangular_target_grid()` and computes each point with
  `build_target_residual_metrics()`.
- Output includes status, source, curve window, target spec, target grid, curve,
  summary, and explicit missing provenance statuses.
- Curve points include dig-segment index, snapshot row index, target positive
  residual depth sum, target overdig depth sum, target removed completion ratio,
  outside-target removed-depth sum, and the full target residual metrics block.
- Summary status is `present` for at least two curve points,
  `insufficient_points` for one point, and `missing` for zero points.
- Summary reports point count plus start, end, and delta values for target
  positive residual, target overdig, target removed completion ratio, and
  outside-target removed-depth sum.
- Diagnostic trend values are
  `target_positive_residual_reduced_outside_removed_increased`,
  `target_positive_residual_reduced_outside_removed_not_increased`,
  `target_positive_residual_not_reduced`, `insufficient_points`, and `missing`.
- Invalid target specs surface the target-grid validation status without
  building a fallback curve.
- Metric validation failure while building the curve surfaces the metric status
  without returning partial fallback curve points.
- No rollout-review integration or schema change was added.
- No official T1 default dimensions, default target depth, cell size, origin,
  physical area, world-frame semantics, physical volume, eval success
  semantics, official cycle IDs, or runtime planner behavior was introduced.

TDD evidence:

- Initial red:
  `python -m pytest -q tests/test_terrain_target_projection.py -k "target_convergence"`
  failed during collection with
  `ImportError: cannot import name 'build_target_residual_convergence_projection'`.
- Focused target-convergence green passed with 4 tests selected and 4 deselected.

Planner-side current-run smoke projection:

- Used explicit non-official example spec:
  `grid_shape=[3, 2]`, `row_start=0`, `row_end=2`, `col_start=0`,
  `col_end=1`, `target_depth_m=0.25`, `official_t1_default=False`.
- Read
  `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results/rollouts/rollout_000.jsonl`.
- File count stayed 10 and no files were written.
- Projection status was `present`.
- Curve point count was `10`.
- First point: dig segment `1`, snapshot row `416`, target positive residual
  `0.498092905036`, target overdig `0.0`, target removed completion ratio
  `0.003814189928`, outside-target removed-depth sum `0.050789695233`.
- Last point: dig segment `10`, snapshot row `5821`, target positive residual
  `0.383547134697`, target overdig `0.0`, target removed completion ratio
  `0.232905730606`, outside-target removed-depth sum `0.479643445462`.
- Summary status was `present`.
- Summary delta values were target positive residual `-0.114545770339`,
  target overdig `0.0`, target removed completion ratio `0.229091540678`, and
  outside-target removed-depth sum `0.428853750229`.
- Diagnostic trend was
  `target_positive_residual_reduced_outside_removed_increased`.

Planner-side verification:

- `python -m pytest -q tests/test_terrain_target_projection.py tests/test_terrain_target_metrics.py tests/test_terrain_target_grid.py tests/test_terrain_residual_metrics.py tests/test_rollout_review.py`
  passed, 36 tests.
- `python -m compileall testbed/eval/terrain_target_projection.py testbed/eval/terrain_target_metrics.py testbed/eval/terrain_target_grid.py testbed/eval/terrain_residual_metrics.py testbed/eval/rollout_review.py tests/test_terrain_target_projection.py tests/test_terrain_target_metrics.py tests/test_terrain_target_grid.py tests/test_terrain_residual_metrics.py tests/test_rollout_review.py`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-changed-docs docs/training_setup.md`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-doc-inventory`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-architecture-contract`
  passed.
- `git diff --check` passed.

Planner closure audit:

- Target lock matched after callback:
  - branch: `tx/oracle-terrain-residual-planner-v0`
  - HEAD: `3cdd82228ddb5c31f20e3d5b1b94d11aec81a135`
  - dirty files: only the expected Phase 1F files before planner log sync
- Callback was factual, scoped, and free of planner-directed strategy.
- Diff stayed inside the existing focused eval owner, focused tests, and closest
  documentation.
- No planner runtime, gate, policy, token, checkpoint, dependency, config,
  branch, upstream, or eval success semantics changed.

Lightweight reflection:

- Reference used: user objective, Phase 1 target-shape evaluation requirements
  in `docs/oracle_terrain_residual_planner_v0_plan.md`, `AGENTS.md` ownership
  boundaries, and the thread execution rule.
- Alignment verdict: aligned. The workflow now has both latest-snapshot and
  per-dig-segment explicit target-shape residual projections.
- Efficiency verdict: useful progress. The slice reused the focused target-grid
  and target-metric owners rather than copying metric formulas into a report or
  review layer.
- Accepted-slice count since the latest deep reflection is now `3/3`; the deep
  reflection gate is due and recorded below before another dispatch.

## 2026-07-01: Deep Reflection After Phase 1D-1F

Reference set:

- User goal: develop an oracle terrain residual planner v0 evaluation baseline
  without inventing official semantics.
- `docs/oracle_terrain_residual_planner_v0_plan.md`.
- `docs/llm_planner_closed_loop_terrain_conclusion.md`.
- `docs/training_setup.md`.
- `AGENTS.md` governance rules.
- `closed-loop-planner-executor` thread rules and the current thread execution
  contract.

Accepted slices reviewed:

- Phase 1D added standalone explicit-target residual metrics from explicit
  row-major arrays.
- Phase 1E added standalone latest-snapshot target residual projection from
  rollout records and an explicit rectangular target spec.
- Phase 1F added standalone per-dig-segment target residual convergence
  projection and summary from the same explicit target spec.

Alignment assessment:

- The accepted work stays within eval diagnostics and focused owners.
- It advances Phase 1 from generic compact-grid residual evidence toward
  target-shape evidence without promoting the example rectangle into official
  T1 semantics.
- The current non-official example projection shows target positive residual
  decreasing from `0.498092905036` to `0.383547134697`, while outside-target
  removed-depth sum increases from `0.050789695233` to `0.479643445462`.
- Inside-target overdig remains `0.0` for the example spec, but the low target
  completion ratio ending at `0.232905730606` and the large outside-target
  removal increase mean the evidence is diagnostic only, not a quality pass.

Scope and risk assessment:

- Good: no production planner, gate, policy, token, checkpoint, dependency,
  runtime config, rollout-review schema, or eval pass/fail behavior changed.
- Good: missing cell size, origin, world transform, height/elevation,
  confidence, and physical volume remain explicit rather than inferred.
- Good: official T1 defaults, official cycle IDs, boundary tolerance,
  bucket-aware IoU, target-shape pass/fail, candidate/effect semantics, and
  runtime gate semantics remain out of scope.
- Risk: target-shape diagnostics now exist as separate primitives; the next
  useful artifact should package them into a single explicit-target baseline
  report so future slices do not keep reassembling the same evidence by hand.
- Risk: the explicit example spec is useful for smoke projection but must remain
  clearly labeled as non-official until the user approves actual target
  dimensions, depth, and provenance.

Recovery or correction needed:

- None for the accepted slices.
- Continue to avoid rollout-review integration until the report fields and
  schema policy are deliberately confirmed.

Accepted-slice count reset:

- Deep reflection completed after the third accepted callback.
- Accepted-slice count since latest recorded deep reflection resets to `0/3`.

Next bounded target:

- Phase 1G should add a standalone explicit-target baseline report builder that
  composes latest-snapshot projection and convergence projection for supplied
  rollout records plus an explicit target spec.
- The report should remain pure and diagnostic: no artifact writing by default,
  no rollout-review schema change, no official T1 defaults, and no eval
  pass/fail semantics.
- The report can expose a compact status, the target spec, latest projection,
  convergence projection, and a short diagnostic summary derived from existing
  fields.
- Tests should prove the report composes existing owners, surfaces validation
  failures, and keeps missing provenance explicit.
- A read-only current-run smoke projection may use the same non-official example
  spec as prior slices, with `official_t1_default=False` recorded in the
  callback.

## 2026-07-01: Phase 1G Callback Audit

Executor thread:

- `019f1d6b-1367-71f3-8cb1-c4d891769109`

Executor slice:

- Phase 1G: standalone explicit-target baseline report builder.

Executor status:

- Success.
- Worktree target lock matched at start.
- HEAD stayed `29499e490f71f1b06abc2d5e5e3f19b4e6bccea3`.
- Expected slice files were modified or added:
  `testbed/eval/terrain_target_report.py`,
  `tests/test_terrain_target_report.py`, and `docs/training_setup.md`.

Accepted implementation facts:

- Added new focused eval owner `testbed/eval/terrain_target_report.py`.
- Added public function `build_explicit_target_residual_baseline_report()`.
- Source is `explicit_target_residual_baseline_report`.
- Schema is `explicit_target_residual_baseline_report_v1`.
- The report composes existing
  `build_latest_target_residual_projection()` and
  `build_target_residual_convergence_projection()` outputs.
- The report embeds both nested projections and exposes a copied
  `diagnostic_summary` from nested projection and convergence-summary fields.
- Report status is `present` only when both latest and convergence projections
  are `present`; shared non-present status is surfaced; mixed status is
  reported as `partial`.
- Top-level missing provenance statuses are copied from nested projections when
  available and default to `missing`.
- No target-grid formula, target residual metric formula, rollout-review
  integration, generated artifact writing, official T1 default, eval pass/fail
  semantics, physical volume, boundary tolerance, bucket-aware IoU, candidate
  semantics, or runtime planner behavior was added.

TDD evidence:

- Initial red:
  `python -m pytest -q tests/test_terrain_target_report.py` failed during
  collection with `ModuleNotFoundError: No module named 'testbed.eval.terrain_target_report'`.
- Focused report green passed with 3 tests.

Planner-side current-run smoke report:

- Used explicit non-official example spec:
  `grid_shape=[3, 2]`, `row_start=0`, `row_end=2`, `col_start=0`,
  `col_end=1`, `target_depth_m=0.25`, `official_t1_default=False`.
- Read
  `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results/rollouts/rollout_000.jsonl`.
- File count stayed 10 and no files were written.
- Report status was `present`.
- Report schema was `explicit_target_residual_baseline_report_v1`.
- Latest projection status was `present`.
- Convergence projection status was `present`.
- Latest snapshot row was `6147`.
- Latest target positive residual depth sum was `0.374313589186`.
- Latest target overdig depth sum was `0.0`.
- Latest target removed completion ratio was `0.251372821628`.
- Latest outside-target removed depth sum was `0.488698139786`.
- Convergence point count was `10`.
- Convergence trend was
  `target_positive_residual_reduced_outside_removed_increased`.
- Convergence target positive residual start/end/delta was
  `0.498092905036` / `0.383547134697` / `-0.114545770339`.
- Convergence outside-target removed depth start/end/delta was
  `0.050789695233` / `0.479643445462` / `0.428853750229`.

Planner-side verification:

- `python -m pytest -q tests/test_terrain_target_report.py tests/test_terrain_target_projection.py tests/test_terrain_target_metrics.py tests/test_terrain_target_grid.py tests/test_terrain_residual_metrics.py tests/test_rollout_review.py`
  passed, 39 tests.
- `python -m compileall testbed/eval/terrain_target_report.py testbed/eval/terrain_target_projection.py testbed/eval/terrain_target_metrics.py testbed/eval/terrain_target_grid.py testbed/eval/terrain_residual_metrics.py testbed/eval/rollout_review.py tests/test_terrain_target_report.py tests/test_terrain_target_projection.py tests/test_terrain_target_metrics.py tests/test_terrain_target_grid.py tests/test_terrain_residual_metrics.py tests/test_rollout_review.py`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-changed-docs docs/training_setup.md`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-doc-inventory`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-architecture-contract`
  passed.
- `git diff --check` passed.

Planner closure audit:

- Target lock matched after callback:
  - branch: `tx/oracle-terrain-residual-planner-v0`
  - HEAD: `29499e490f71f1b06abc2d5e5e3f19b4e6bccea3`
  - dirty files: only the expected Phase 1G files before planner log sync
- Callback was factual, scoped, and free of planner-directed strategy.
- Diff stayed inside the new report composition owner, focused tests, and
  closest documentation.
- The report owner does not recompute target-grid or residual metric formulas;
  it copies and packages nested owner outputs.
- No planner runtime, gate, policy, token, checkpoint, dependency, config,
  branch, upstream, rollout-review schema, or eval success semantics changed.

Lightweight reflection:

- Reference used: user objective, Phase 1 target-shape evaluation requirements
  in `docs/oracle_terrain_residual_planner_v0_plan.md`, `AGENTS.md` ownership
  boundaries, and the thread execution rule.
- Alignment verdict: aligned. The workflow now has a reusable pure report object
  for explicit target baseline evidence.
- Efficiency verdict: useful progress. This slice reduced repeated hand-assembly
  of latest and convergence projections while staying out of schema/runtime
  integration.
- Accepted-slice count since the latest deep reflection is now `1/3`.

Next bounded target:

- Phase 1H should create a durable current-run explicit-target baseline report
  document from the pure report builder and the known current run, using the
  same non-official example target spec.
- The document must clearly state `official_t1_default=False`, list the exact
  run path and HEAD used, and preserve all current limitations.
- It should be documentation/report-only unless a tiny helper is necessary for
  reproducible extraction; prefer no new production code.
- It must not write generated artifacts under the eval run results directory,
  change `rollout_review.json`, define official target defaults, or introduce
  pass/fail semantics.
- Verification should rerun a read-only report smoke, changed-doc guards, doc
  inventory, architecture contract, and `git diff --check`.

## 2026-07-01: Phase 1H Partial Callback Audit And Recovery

Executor thread:

- `019f1d6b-1367-71f3-8cb1-c4d891769109`

Executor slice:

- Phase 1H: durable current-run explicit-target baseline report document.

Initial executor status:

- Partial.
- Worktree target lock matched at start.
- HEAD stayed `441eb1a28f06e2fd1d17e64ea6f3e0ccada4a69f`.
- Expected docs were modified or added:
  `docs/oracle_terrain_residual_baseline_report.md` and
  `docs/training_setup.md`.

Accepted document facts:

- Added English report document
  `docs/oracle_terrain_residual_baseline_report.md`.
- Added a short cross-reference from `docs/training_setup.md`.
- The report records the current run under the explicit non-official target
  spec:
  `grid_shape=[3, 2]`, `row_start=0`, `row_end=2`, `col_start=0`,
  `col_end=1`, `target_depth_m=0.25`,
  `profile=explicit_t1_like_rectangular_shallow_pit`,
  `official_t1_default=false`.
- The report records source `explicit_target_residual_baseline_report`, schema
  `explicit_target_residual_baseline_report_v1`, and report status `present`.
- It records latest projection and convergence summary values from
  `build_explicit_target_residual_baseline_report()`.
- It explicitly states diagnostic-only interpretation, missing provenance, and
  non-goals.
- It does not write generated artifacts under the eval run results directory.
- It does not change rollout review schema, official target defaults,
  pass/fail semantics, or runtime planner behavior.

Current-run smoke report facts:

- Read
  `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results/rollouts/rollout_000.jsonl`.
- File count under the results directory stayed `10 -> 10`; no new run files
  were created.
- Report status was `present`.
- Latest target positive residual depth sum was `0.374313589186`.
- Latest target overdig depth sum was `0.0`.
- Latest target removed completion ratio was `0.251372821628`.
- Latest outside-target removed depth sum was `0.488698139786`.
- Convergence point count was `10`.
- Convergence trend was
  `target_positive_residual_reduced_outside_removed_increased`.
- Convergence target positive residual start/end/delta was
  `0.498092905036` / `0.383547134697` / `-0.114545770339`.
- Convergence outside-target removed depth start/end/delta was
  `0.050789695233` / `0.479643445462` / `0.428853750229`.

Partial failure facts:

- `python scripts/planner_architecture_doc_guard.py --check-changed-docs docs/oracle_terrain_residual_baseline_report.md docs/training_setup.md`
  failed with:
  `planner-doc-guard: unexpected docs must not be recreated: docs/oracle_terrain_residual_baseline_report.md`.
- `python scripts/planner_architecture_doc_guard.py --check-doc-inventory`
  failed with:
  `planner-doc-guard: docs inventory mismatch; unexpected: docs/oracle_terrain_residual_baseline_report.md`.
- Planner-side root cause: `scripts/planner_architecture_doc_guard.py` uses
  `EXPECTED_DOCS = YULONG_DOCS | REFACTOR_DOCS`, and the new report document
  was not yet in the curated set.

Recovery dispatch:

- Recovery target was limited to guard/inventory sync.
- Allowed owner was `scripts/planner_architecture_doc_guard.py`, with
  `tests/test_planner_architecture_doc_contract.py` only if needed.
- The report document and `docs/training_setup.md` content were to be
  preserved.

Recovery callback status:

- Success.
- Reproduced both red guard failures before editing.
- Added `docs/oracle_terrain_residual_baseline_report.md` to `YULONG_DOCS` in
  `scripts/planner_architecture_doc_guard.py`.
- No guard logic was loosened or disabled.
- `tests/test_planner_architecture_doc_contract.py` did not need editing because
  it imports `EXPECTED_DOCS` dynamically.

Planner-side verification after recovery:

- `python scripts/planner_architecture_doc_guard.py --check-changed-docs docs/oracle_terrain_residual_baseline_report.md docs/training_setup.md`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-doc-inventory`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-architecture-contract`
  passed.
- `python -m pytest -q tests/test_planner_architecture_doc_contract.py` passed,
  8 tests.
- `python -m compileall scripts/planner_architecture_doc_guard.py tests/test_planner_architecture_doc_contract.py`
  passed.
- Read-only current-run report smoke passed again after recovery; results file
  count stayed `10 -> 10`.
- `git diff --check` passed.

Planner closure audit:

- Target lock matched after recovery:
  - branch: `tx/oracle-terrain-residual-planner-v0`
  - HEAD: `441eb1a28f06e2fd1d17e64ea6f3e0ccada4a69f`
  - dirty files: expected Phase 1H docs plus recovery guard allowlist
- The partial callback was factual and scoped; it stopped instead of editing
  guard code outside the docs-only prompt.
- The recovery callback was factual and scoped; it changed only the curated docs
  allowlist.
- The new report document is now accepted as a curated source-of-truth doc.
- Guard behavior still rejects unexpected docs.
- No report metrics, rollout review schema, runtime planner/gate/policy
  behavior, eval pass/fail semantics, config, branch, upstream, token order, or
  checkpoint contract changed.

Lightweight reflection:

- Reference used: user objective, Phase 1 baseline-report requirement in
  `docs/oracle_terrain_residual_planner_v0_plan.md`, `AGENTS.md` documentation
  sync rule, and the closed-loop failure-channel rule.
- Alignment verdict: aligned after recovery. The durable baseline report now
  exists and the repository guard recognizes it as curated documentation.
- Efficiency verdict: necessary recovery. The partial callback exposed a real
  source-of-truth inventory constraint; the recovery fixed the inventory rather
  than weakening the guard or deleting the report.
- Accepted-slice count would have become `2/3`, but a partial callback requires
  immediate deep reflection; the reflection below resets the cadence.

## 2026-07-01: Deep Reflection After Phase 1H Partial

Reference set:

- User goal: develop an oracle terrain residual planner v0 evaluation baseline
  with durable artifacts and without inventing official semantics.
- `docs/oracle_terrain_residual_planner_v0_plan.md`.
- `docs/llm_planner_closed_loop_terrain_conclusion.md`.
- `docs/oracle_terrain_residual_baseline_report.md`.
- `docs/training_setup.md`.
- `AGENTS.md` governance rules.
- `closed-loop-planner-executor` failure-channel and closure rules.

Failure assessment:

- The partial was not an implementation drift or report-content problem.
- The executor obeyed the docs-only prompt by stopping when code guard changes
  were needed.
- The root cause was a stale curated docs inventory after adding a new durable
  source-of-truth report.
- The recovery changed only the allowlist entry needed to make the new report a
  recognized curated doc.

Alignment assessment:

- The workflow still serves the original objective: Phase 1 now has a durable
  current-run baseline packet for explicit target residual evidence.
- The report keeps the example target spec non-official and diagnostic-only.
- The report states that target positive residual decreases under the example
  spec while outside-target removed depth increases substantially; it does not
  label this as success or failure.
- Missing cell size, origin, timestamp, frame transform, height/elevation,
  confidence, physical volume, official cycle IDs, and official target defaults
  remain explicit.

Scope and risk assessment:

- Good: no rollout-review schema, eval pass/fail, runtime planner, gate, policy,
  config, token, checkpoint, branch, or upstream behavior changed.
- Good: the docs guard still rejects unexpected docs.
- Risk: Phase 1 still has unchecked metric items in the plan, especially depth
  RMSE, boundary tolerance, and shape IoU.
- Risk: boundary tolerance and shape IoU require explicit threshold/geometry
  semantics; they should not be invented as defaults.
- Opportunity: target interior depth-error metrics such as RMSE/MAE can be added
  as diagnostic formulas without defining pass/fail thresholds.

Accepted-slice count reset:

- Deep reflection completed after the partial/recovery sequence.
- Accepted-slice count since latest recorded deep reflection resets to `0/3`.

Next bounded target:

- Phase 1I should add diagnostic target interior depth-error fields to
  `build_target_residual_metrics()`, such as target residual RMSE and MAE over
  valid target cells.
- The slice should remain threshold-free and diagnostic-only.
- The new fields should propagate through existing latest projection,
  convergence projection, and baseline report nested metric blocks without
  adding rollout-review schema integration.
- Update tests and `docs/training_setup.md`.
- Keep boundary tolerance, shape IoU, bucket-aware IoU, pass/fail semantics, and
  official target defaults out of scope until their semantics are explicitly
  confirmed.

## 2026-07-01: Phase 1I Callback Audit

Executor thread:

- `019f1d6b-1367-71f3-8cb1-c4d891769109`

Executor slice:

- Phase 1I: diagnostic target interior depth-error metrics.

Executor status:

- Success.
- Worktree target lock matched at start.
- HEAD stayed `8c66aa4adae1a750900e9cdcee53d9141d355c15`.
- Expected slice files were modified:
  `testbed/eval/terrain_target_metrics.py`,
  `tests/test_terrain_target_metrics.py`,
  `tests/test_terrain_target_projection.py`,
  `tests/test_terrain_target_report.py`, and `docs/training_setup.md`.

Accepted implementation facts:

- Added threshold-free target-interior depth-error diagnostics to
  `build_target_residual_metrics()`.
- Present output now includes `target_residual_depth_rmse_m`,
  `target_residual_depth_mae_m`, and
  `target_residual_depth_abs_max_m`.
- The fields are computed over valid target cells only using
  `target_depth_grid_m - removed_depth_grid_m`.
- When `target_cell_count == 0`, the three fields are `None`, not zero.
- Existing invalid input status semantics are preserved; invalid results include
  the new fields as `None`.
- Existing latest projection, convergence projection, and baseline report owners
  do not recompute these formulas. The new values propagate through nested
  `target_residual_metrics` blocks.
- No thresholds, pass/fail semantics, boundary tolerance, shape IoU,
  bucket-aware IoU, official T1 defaults, rollout-review integration, runtime
  planner or gate behavior, config, token, or checkpoint changes were added.

TDD evidence:

- Initial selector command was not a valid red:
  `python -m pytest -q tests/test_terrain_target_metrics.py tests/test_terrain_target_report.py -k "target_residual_depth"`
  selected no tests.
- Valid red before production edit:
  `python -m pytest -q tests/test_terrain_target_metrics.py tests/test_terrain_target_report.py`
  failed with 5 failures and 6 passes.
- Red failures were missing-key failures for
  `target_residual_depth_rmse_m`, `target_residual_depth_mae_m`, and
  `target_residual_depth_abs_max_m` in focused metrics and nested report tests.

Planner-side current-run smoke report:

- Used explicit non-official example spec:
  `grid_shape=[3, 2]`, `row_start=0`, `row_end=2`, `col_start=0`,
  `col_end=1`, `target_depth_m=0.25`.
- Read
  `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results/rollouts/rollout_000.jsonl`.
- File count under the results directory stayed `10 -> 10`; no new run files
  were created.
- Report status was `present`.
- Latest snapshot row was `6147`.
- Latest nested target residual depth RMSE / MAE / abs max were
  `0.187219063753` / `0.187156794593` / `0.191985052079`.
- Convergence point count was `10`.
- Convergence trend was
  `target_positive_residual_reduced_outside_removed_increased`.
- First convergence point row `416` had RMSE / MAE / abs max
  `0.24904827798` / `0.249046452518` / `0.25`.
- Last convergence point row `5821` had RMSE / MAE / abs max
  `0.191779018803` / `0.191773567348` / `0.19321956858`.

Planner-side verification:

- `python -m pytest -q tests/test_terrain_target_report.py tests/test_terrain_target_projection.py tests/test_terrain_target_metrics.py tests/test_terrain_target_grid.py tests/test_terrain_residual_metrics.py tests/test_rollout_review.py`
  passed, 40 tests.
- `python -m compileall testbed/eval/terrain_target_metrics.py testbed/eval/terrain_target_projection.py testbed/eval/terrain_target_report.py testbed/eval/terrain_target_grid.py testbed/eval/terrain_residual_metrics.py testbed/eval/rollout_review.py tests/test_terrain_target_metrics.py tests/test_terrain_target_projection.py tests/test_terrain_target_report.py tests/test_terrain_target_grid.py tests/test_terrain_residual_metrics.py tests/test_rollout_review.py`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-changed-docs docs/training_setup.md`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-doc-inventory`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-architecture-contract`
  passed.
- Read-only current-run smoke report passed with results file count `10 -> 10`.
- `git diff --check` passed.

Planner closure audit:

- Target lock matched after callback:
  - branch: `tx/oracle-terrain-residual-planner-v0`
  - HEAD: `8c66aa4adae1a750900e9cdcee53d9141d355c15`
  - dirty files: only expected Phase 1I files before planner log sync
- Callback was factual, scoped, and free of planner-directed strategy.
- Diff stayed inside the metric owner, nested propagation tests, and closest
  documentation.
- No planner runtime, gate, policy, token, checkpoint, dependency, config,
  branch, upstream, rollout-review schema, official target semantics, or eval
  success semantics changed.
- The committed baseline report document was intentionally not refreshed in this
  slice because the executor prompt kept that out of scope.

Lightweight reflection:

- Reference used: user objective, Phase 1 metric requirements in
  `docs/oracle_terrain_residual_planner_v0_plan.md`, `AGENTS.md` ownership
  boundaries, and the Phase 1H deep reflection.
- Alignment verdict: aligned. Phase 1 now has target-interior depth-error
  diagnostics that do not require threshold or geometry-semantics decisions.
- Efficiency verdict: useful progress. The slice expanded the existing metric
  owner and let nested owners carry the fields without broader schema work.
- Accepted-slice count since the latest deep reflection is now `1/3`.

Next bounded target:

- Phase 1J should refresh `docs/oracle_terrain_residual_baseline_report.md` for
  the current HEAD and include the new target interior RMSE / MAE / abs-max
  values.
- This should be a docs-only report refresh using the committed report builder
  and the same explicit non-official target spec.
- Do not write generated artifacts under the eval run results directory.
- Do not change rollout-review schema, official target defaults, pass/fail
  semantics, boundary tolerance, shape IoU, bucket-aware IoU, runtime planner,
  gate, policy, config, token, or checkpoint behavior.

## 2026-07-01: Phase 1J Callback Audit

Executor thread:

- `019f1d6b-1367-71f3-8cb1-c4d891769109`

Executor slice:

- Phase 1J: refresh durable baseline report with target-interior depth-error
  diagnostics.

Executor status:

- Success.
- Worktree target lock matched at start.
- HEAD stayed `43e911612e9833211820ede64c51cd118e0d0214`.
- Expected slice file was modified:
  `docs/oracle_terrain_residual_baseline_report.md`.

Accepted document facts:

- Refreshed the baseline report's observed branch ahead count to `16`.
- Refreshed the observed HEAD to
  `43e911612e9833211820ede64c51cd118e0d0214`.
- Added latest-projection target residual depth RMSE / MAE / abs max:
  `0.187219063753` / `0.187156794593` / `0.191985052079`.
- Added a concise target-interior depth-error summary table:
  - first convergence point row `416`: `0.24904827798` /
    `0.249046452518` / `0.25`
  - last convergence point row `5821`: `0.191779018803` /
    `0.191773567348` / `0.19321956858`
  - latest projection row `6147`: `0.187219063753` /
    `0.187156794593` / `0.191985052079`
- Updated interpretation to state that target-interior depth-error diagnostics
  decrease across this explicit non-official example convergence evidence.
- Updated non-goal wording from broad `RMSE` exclusion to
  `RMSE threshold/pass-fail`, preserving the diagnostic-only boundary while
  allowing the Phase 1I diagnostic RMSE field.
- Preserved `official_t1_default=false`, missing provenance, and all non-goal
  warnings.

Planner-side current-run smoke report:

- Used explicit non-official example spec:
  `grid_shape=[3, 2]`, `row_start=0`, `row_end=2`, `col_start=0`,
  `col_end=1`, `target_depth_m=0.25`.
- Read
  `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results/rollouts/rollout_000.jsonl`.
- File count under the results directory stayed `10 -> 10`; no new run files
  were created.
- Report status was `present`.
- Latest row and RMSE / MAE / abs max were row `6147`,
  `0.187219063753` / `0.187156794593` / `0.191985052079`.
- First convergence point row and RMSE / MAE / abs max were row `416`,
  `0.24904827798` / `0.249046452518` / `0.25`.
- Last convergence point row and RMSE / MAE / abs max were row `5821`,
  `0.191779018803` / `0.191773567348` / `0.19321956858`.

Planner-side verification:

- `python scripts/planner_architecture_doc_guard.py --check-changed-docs docs/oracle_terrain_residual_baseline_report.md`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-doc-inventory`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-architecture-contract`
  passed.
- Read-only current-run smoke report passed with results file count `10 -> 10`.
- `git diff --check` passed.

Planner closure audit:

- Target lock matched after callback:
  - branch: `tx/oracle-terrain-residual-planner-v0`
  - HEAD: `43e911612e9833211820ede64c51cd118e0d0214`
  - dirty files: only expected Phase 1J report doc before planner log sync
- Callback was factual, scoped, and free of planner-directed strategy.
- Diff stayed in the committed baseline report document.
- No code, tests, generated run artifacts, rollout-review schema, official T1
  defaults, pass/fail semantics, boundary tolerance, shape IoU, bucket-aware
  IoU, runtime planner/gate/policy behavior, config, token, checkpoint,
  dependency, branch, or upstream behavior changed.

Lightweight reflection:

- Reference used: user objective, Phase 1 baseline-report requirement in
  `docs/oracle_terrain_residual_planner_v0_plan.md`, the current
  `docs/oracle_terrain_residual_baseline_report.md`, and the Phase 1I metric
  contract.
- Alignment verdict: aligned. The durable baseline report now reflects the
  latest target-interior depth-error diagnostics.
- Efficiency verdict: necessary doc sync. This kept the committed report
  current with the metric owner without broadening into schema or runtime work.
- Accepted-slice count since the latest deep reflection is now `2/3`.

Hold-and-confirm gate:

- Phase 1 has now covered explicit target-grid generation, target residual
  sums, threshold-free target interior depth-error diagnostics, convergence
  evidence, and a durable current-run baseline report.
- Remaining Phase 1 plan items, especially boundary tolerance and shape IoU,
  require semantic decisions before code:
  - whether to use a narrow tolerance band such as `0.25m - 0.30m`, a bucket
    footprint tolerance such as `0.45m - 0.55m`, or report both as diagnostics;
  - whether shape IoU should be computed on target cells, dilated target cells,
    removed-depth active cells, or another bucket-footprint projection;
  - whether these remain diagnostic-only or become pass/fail later.
- No further implementation slice should be dispatched for boundary tolerance
  or shape IoU until these semantics are confirmed.

## 2026-07-01: Phase 1K Callback Audit

Executor thread:

- `019f1d6b-1367-71f3-8cb1-c4d891769109`

Executor slice:

- Phase 1K: dual-tolerance shape-overlap diagnostics.

Executor status:

- Success.
- Worktree target lock matched at start.
- HEAD stayed `87d3d9d45c0cf1433ae2f31ce85928550ee392f1`.
- Expected slice files were modified:
  - `testbed/eval/terrain_target_metrics.py`
  - `testbed/eval/terrain_target_projection.py`
  - `tests/test_terrain_target_metrics.py`
  - `tests/test_terrain_target_projection.py`
  - `tests/test_terrain_target_report.py`
  - `docs/training_setup.md`

Accepted implementation facts:

- `build_target_residual_metrics()` now accepts optional keyword-only
  `grid_shape` and `cell_size_m` inputs while preserving existing callers.
- Every metric result includes nested
  `target_shape_overlap_diagnostics`, including invalid validation results.
- Present diagnostics include:
  - `removed_active_depth_threshold_m: 0.0`
  - strict `raw_target_overlap`
  - `one_cell_dilated_target_overlap` using row-major Chebyshev / 8-neighbor
    dilation with `cell_radius: 1`
  - saturation ratio so small-grid dilation cannot silently look better than it
    is
  - `meter_tolerance_profiles` with `narrow_0_30m` and `bucket_0_50m`
- Current-run cell size remains missing, so meter profiles report
  `cell_size_missing` rather than inferring meter-derived IoU.
- When `cell_size_m` is explicitly supplied, meter profile radius is computed
  with `ceil(tolerance_m / cell_size_m)`.
- `build_latest_target_residual_projection()` and
  `build_target_residual_convergence_projection()` pass explicit `grid_shape`
  into nested target residual metrics.
- `terrain_target_report.py` production code was not changed; report tests only
  assert nested propagation.
- `docs/training_setup.md` documents the new diagnostics and their
  diagnostic-only limitations.

Planner-side current-run smoke report:

- Used explicit non-official example spec:
  `grid_shape=[3, 2]`, `row_start=0`, `row_end=2`, `col_start=0`,
  `col_end=1`, `target_depth_m=0.25`.
- Read
  `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results/rollouts/rollout_000.jsonl`.
- File count under the results directory stayed `10 -> 10`; no new run files
  were created.
- Report status was `present`.
- Latest projection row was `6147`.
- Latest raw IoU was `0.333333333333`.
- Latest raw outside removed-depth sum was `0.488698139786`.
- Latest one-cell dilated IoU was `1.0`.
- Latest one-cell dilated saturation ratio was `1.0`.
- Latest outside-dilated removed-depth sum was `0.0`.
- Latest `narrow_0_30m` and `bucket_0_50m` statuses were both
  `cell_size_missing`.
- Convergence point count was `10`.
- Convergence trend remained
  `target_positive_residual_reduced_outside_removed_increased`.
- First point row `416`: raw IoU `0.333333333333`, one-cell dilated IoU
  `0.333333333333`, saturation `1.0`.
- Last point row `5821`: raw IoU `0.333333333333`, one-cell dilated IoU
  `1.0`, saturation `1.0`.

Planner-side verification:

- `python -m pytest -q tests/test_terrain_target_metrics.py` passed:
  `13 passed`.
- `python -m pytest -q tests/test_terrain_target_projection.py tests/test_terrain_target_report.py tests/test_terrain_target_metrics.py tests/test_terrain_target_grid.py tests/test_terrain_residual_metrics.py tests/test_rollout_review.py`
  passed: `45 passed`.
- `python -m compileall testbed/eval/terrain_target_metrics.py testbed/eval/terrain_target_projection.py testbed/eval/terrain_target_report.py testbed/eval/terrain_target_grid.py testbed/eval/terrain_residual_metrics.py testbed/eval/rollout_review.py tests/test_terrain_target_metrics.py tests/test_terrain_target_projection.py tests/test_terrain_target_report.py tests/test_terrain_target_grid.py tests/test_terrain_residual_metrics.py tests/test_rollout_review.py`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-changed-docs docs/training_setup.md`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-doc-inventory`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-architecture-contract`
  passed.
- Read-only current-run smoke report passed with results file count `10 -> 10`.
- `git diff --check` passed.

Planner closure audit:

- Target lock matched after callback:
  - branch: `tx/oracle-terrain-residual-planner-v0`
  - HEAD: `87d3d9d45c0cf1433ae2f31ce85928550ee392f1`
  - dirty files: only expected Phase 1K files before planner log sync
- Callback was factual, scoped, and free of planner-directed strategy.
- Diff stayed within focused eval metric/projection owners, focused tests, and
  the closest source-of-truth documentation.
- No rollout-review schema, official T1 defaults, pass/fail semantics, planner
  success semantics, eval success semantics, runtime gate/policy behavior,
  token/checkpoint/config/dependency, branch/upstream, or generated run artifact
  behavior changed.

Lightweight reflection:

- Reference used: user objective, Phase 1 bucket-aware task metric requirement
  in `docs/oracle_terrain_residual_planner_v0_plan.md`, user-confirmed
  dual-tolerance / dilated-IoU default, and diagnostic-only boundary in
  `docs/training_setup.md`.
- Alignment verdict: aligned. Phase 1 now includes shape-overlap and
  boundary-tolerance diagnostics without promoting them into official
  pass/fail semantics.
- Efficiency verdict: useful progress. This was a substantive metric slice, not
  repeated process or report-only work.
- Accepted-slice count since the latest deep reflection is now `3/3`; deep
  reflection is required before the next implementation dispatch.

## 2026-07-01: Deep Reflection After Phase 1I-1K

Trigger:

- Three accepted callbacks since the latest recorded deep reflection:
  Phase 1I, Phase 1J, and Phase 1K.

Reference base:

- User objective: prove whether an oracle terrain residual planner can drive a
  target pit shape toward convergence in simulation ground-truth terrain,
  without relying on single rollout `success=1.0`.
- Phase 1 requirement in `docs/oracle_terrain_residual_planner_v0_plan.md`:
  target grid, positive/negative residual, boundary tolerance, depth RMSE,
  shape IoU, residual convergence curve, and baseline report.
- Current diagnostic contract in `docs/training_setup.md`.
- Durable baseline packet in
  `docs/oracle_terrain_residual_baseline_report.md`.
- User-confirmed default choices:
  - dual tolerance diagnostics: `0.30m` narrow and `0.50m` bucket footprint
  - raw target-cell overlap as strict contrast
  - one-cell dilated target mask IoU as current practical shape-overlap
    diagnostic
  - saturation / coverage guard fields
  - diagnostic-only until explicit promotion

What Phase 1I-1K added:

- Phase 1I added threshold-free target-interior depth-error metrics:
  RMSE, MAE, and abs max.
- Phase 1J refreshed the durable current-run baseline report with those
  depth-error diagnostics.
- Phase 1K added raw and dilated target-overlap diagnostics, dual tolerance
  profile records, and explicit `cell_size_missing` handling for current-run
  meter profiles.

Alignment verdict:

- Aligned. The loop now answers a larger part of the Phase 1 question:
  target residual decreases can be inspected together with target interior
  depth error, raw/dilated shape overlap, outside-target removed depth, and
  convergence trend.
- The implementation still respects non-goals: no production planner/gate
  change, no rollout-review schema change, no official T1 default, no
  pass/fail semantics, and no generated run artifact writes.

Verification verdict:

- Current verification is proving the right layer for Phase 1: pure eval owner
  tests, projection/report propagation tests, docs guards, compile checks, and a
  read-only current-run smoke.
- The largest remaining evidence gap is not test coverage for the new metric
  formulas; it is the missing current-run provenance needed for meter-derived
  tolerance profiles: cell size, origin, frame transform, official target
  defaults, physical volume conversion, and official cycle IDs.

Efficiency verdict:

- The last three accepted callbacks were necessary. Phase 1I and Phase 1K were
  real metric capability additions; Phase 1J was a targeted doc sync to keep the
  durable baseline packet current.
- The next report refresh should be docs-only and short. After that, Phase 1
  should close rather than adding more metric variants.

Default decisions going forward:

- Continue using dual tolerance diagnostics, not a single official threshold.
- Continue using one-cell dilated target mask IoU as the current practical
  shape-overlap diagnostic, with raw target-cell overlap as strict contrast.
- Keep meter-derived tolerance profiles explicit-input only until cell size is
  available.
- Keep all current Phase 1 fields diagnostic-only.
- Do not pause for more semantic choices unless a future slice would change
  production planner/gate behavior, official pass/fail criteria, token/schema,
  checkpoint compatibility, dependencies, or branch/upstream state.

Next bounded target:

- Phase 1L should refresh
  `docs/oracle_terrain_residual_baseline_report.md` with current-run
  `target_shape_overlap_diagnostics` facts from the committed report builder.
- It should be docs-only, use the same explicit non-official target spec, and
  keep `official_t1_default=false`.
- It should record raw IoU, one-cell dilated IoU, saturation ratio, outside
  raw/dilated removed-depth sums, and meter profile `cell_size_missing`
  statuses.
- Do not write generated artifacts under the eval run results directory.
- Do not change code, tests, rollout-review schema, official target defaults,
  pass/fail semantics, runtime planner/gate/policy behavior, config, token,
  checkpoint, branch, or upstream behavior.
