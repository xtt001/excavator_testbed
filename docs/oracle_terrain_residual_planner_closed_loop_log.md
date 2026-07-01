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

## 2026-07-01: Phase 1L Callback Audit

Executor thread:

- `019f1d6b-1367-71f3-8cb1-c4d891769109`

Executor slice:

- Phase 1L: durable baseline report refresh for shape-overlap diagnostics.

Executor status:

- Success.
- Worktree target lock matched at start.
- HEAD stayed `62ef7914461532e0bb983acc2950b8e9a041f7f3`.
- Expected docs-only slice file was modified:
  `docs/oracle_terrain_residual_baseline_report.md`.

Accepted document facts:

- Refreshed the report's observed branch ahead count to `18`.
- Refreshed the observed HEAD to
  `62ef7914461532e0bb983acc2950b8e9a041f7f3`.
- Added `Target Shape Overlap / Tolerance Summary`.
- Added first / last / latest shape-overlap table:
  - first convergence row `416`: raw IoU `0.333333333333`, raw outside
    removed-depth sum `0.050789695233`, one-cell dilated IoU
    `0.333333333333`, saturation `1.0`, outside-dilated removed-depth sum
    `0.0`
  - last convergence row `5821`: raw IoU `0.333333333333`, raw outside
    removed-depth sum `0.479643445462`, one-cell dilated IoU `1.0`,
    saturation `1.0`, outside-dilated removed-depth sum `0.0`
  - latest row `6147`: raw IoU `0.333333333333`, raw outside removed-depth sum
    `0.488698139786`, one-cell dilated IoU `1.0`, saturation `1.0`,
    outside-dilated removed-depth sum `0.0`
- Added explicit interpretation warning that one-cell Chebyshev / 8-neighbor
  dilation saturates all valid cells in the current `3 x 2` grid, so dilated
  IoU `1.0` at the last/latest points is not target-shape success.
- Added meter tolerance profile table showing `narrow_0_30m` and
  `bucket_0_50m` both as `cell_size_missing`.
- Updated interpretation to note that raw IoU stayed `0.333333333333` while raw
  outside-target removed-depth grew from `0.050789695233` to
  `0.479643445462` over the convergence points.
- Updated non-goal wording to allow diagnostic overlap/tolerance fields while
  preserving no pass/fail and no official boundary-tolerance semantics.

Planner-side current-run smoke report:

- Used explicit non-official example spec:
  `grid_shape=[3, 2]`, `row_start=0`, `row_end=2`, `col_start=0`,
  `col_end=1`, `target_depth_m=0.25`.
- Read
  `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results/rollouts/rollout_000.jsonl`.
- File count under the results directory stayed `10 -> 10`; no new run files
  were created.
- Report status was `present`; convergence curve point count was `10`.
- First row `416`: raw IoU `0.333333333333`, raw outside removed-depth sum
  `0.050789695233`, one-cell dilated IoU `0.333333333333`, saturation `1.0`,
  outside-dilated removed-depth sum `0.0`, meter statuses `cell_size_missing`
  / `cell_size_missing`.
- Last row `5821`: raw IoU `0.333333333333`, raw outside removed-depth sum
  `0.479643445462`, one-cell dilated IoU `1.0`, saturation `1.0`,
  outside-dilated removed-depth sum `0.0`, meter statuses `cell_size_missing`
  / `cell_size_missing`.
- Latest row `6147`: raw IoU `0.333333333333`, raw outside removed-depth sum
  `0.488698139786`, one-cell dilated IoU `1.0`, saturation `1.0`,
  outside-dilated removed-depth sum `0.0`, meter statuses `cell_size_missing`
  / `cell_size_missing`.

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
  - HEAD: `62ef7914461532e0bb983acc2950b8e9a041f7f3`
  - dirty files: only expected Phase 1L baseline report doc before planner log
    sync
- Callback was factual, scoped, and free of planner-directed strategy.
- Diff stayed in the durable baseline report document.
- No code, tests, generated run artifacts, rollout-review schema, official T1
  defaults, pass/fail semantics, runtime planner/gate/policy behavior,
  token/checkpoint/config/dependency, branch/upstream, or meter-derived IoU
  inference changed.

Lightweight reflection:

- Reference used: user objective, Phase 1 baseline report requirement in
  `docs/oracle_terrain_residual_planner_v0_plan.md`, the Phase 1K diagnostic
  contract in `docs/training_setup.md`, and the current
  `docs/oracle_terrain_residual_baseline_report.md`.
- Alignment verdict: aligned. The durable report now exposes the same
  shape-overlap and tolerance facts as the committed metric chain.
- Efficiency verdict: necessary doc sync. This was the expected short
  report-only slice after a real metric addition.
- Accepted-slice count since the latest deep reflection is now `1/3`.

Next bounded target:

- Phase 1M should create a Phase 1 acceptance / transition packet:
  - update `docs/oracle_terrain_residual_planner_v0_plan.md` Phase 1 checklist
    status without claiming pass/fail semantics;
  - add a compact Phase 1 acceptance summary to the closed-loop log;
  - identify remaining evidence gaps and the default Phase 2 direction.
- This should be docs-only unless the plan guard requires a narrow doc allowlist
  update.
- Do not add more Phase 1 metric variants.
- Do not change code, tests, rollout-review schema, production planner/gate,
  official target defaults, pass/fail semantics, config, token, checkpoint,
  dependency, branch, or upstream behavior.

## 2026-07-01: Phase 1M Executor Transition Packet

Executor slice:

- Phase 1M: Phase 1 acceptance / transition packet.

Executor status:

- Pending planner callback audit.
- Expected docs-only files:
  - `docs/oracle_terrain_residual_planner_v0_plan.md`
  - `docs/oracle_terrain_residual_planner_closed_loop_log.md`

Factual Phase 1 closure recorded:

- Phase 1 checklist now marks the implemented diagnostic pieces complete:
  explicit target-grid generation, target residual / overdig / completion
  metrics, residual convergence curve and summary, target-interior depth-error
  diagnostics, raw/dilated shape overlap, dual tolerance profile records, and
  the durable current-run baseline report.
- Phase 1 explicitly does not mark official T1 defaults, meter-derived
  tolerance, physical volume, official cycle IDs, target-shape pass/fail, or
  production planner improvement as complete.
- Phase 1 acceptance note records the current evidence as diagnostic baseline
  evidence: target positive residual and target-interior depth error decrease,
  while raw outside-target removed-depth grows and the one-cell dilated mask
  saturates the current `3 x 2` grid.
- Remaining provenance gaps recorded: cell size, origin, frame transform,
  height/elevation/confidence grid, physical volume conversion, official cycle
  IDs, and official target defaults.

Default Phase 2 direction recorded:

- Shape guard shadow audit only; no production gate change.
- Default shadow events:
  `low_payload_shape_guard_stop`, `overdig_guard_stop`,
  `depth_budget_exhausted`, `outside_protected_removed_increased`.
- Default interpretation: measure whether these shadow events would reduce
  overdig risk without materially reducing payload / cycle efficiency.

Next bounded target for Phase 2A:

- Define the shape guard shadow-audit event contract and review surface without
  changing production planner/gate behavior or official pass/fail semantics.

## 2026-07-01: Phase 1M Planner Callback Audit

Planner-side callback acceptance:

- Callback status: success.
- Target lock matched:
  - branch/status: `## tx/oracle-terrain-residual-planner-v0...origin/tx/v2_6-llm-planner [ahead 19]`
  - HEAD: `5dfbc6f09fffffa4f0e1884b16d13c8fd9f26010`
  - dirty files: only the expected Phase 1M docs before planner closure sync
- Accepted changed files:
  - `docs/oracle_terrain_residual_planner_v0_plan.md`
  - `docs/oracle_terrain_residual_planner_closed_loop_log.md`
- Callback was factual and scoped to documentation status / transition updates.

Planner-side verification:

- `python scripts/planner_architecture_doc_guard.py --check-changed-docs docs/oracle_terrain_residual_planner_v0_plan.md docs/oracle_terrain_residual_planner_closed_loop_log.md`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-doc-inventory`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-architecture-contract`
  passed.
- `git diff --check` passed.

Closure audit:

- Phase 1 diagnostic baseline is now documented as accepted.
- The plan marks implemented diagnostic components complete and keeps
  official T1 defaults, meter-derived tolerance, physical volume, official
  cycle IDs, target-shape pass/fail, and production planner improvement out of
  scope.
- The Phase 2 default is shadow-audit-only; no production gate, eval pass/fail,
  planner success, rollout-review schema, runtime planner/gate/policy behavior,
  token/checkpoint/config/dependency, branch, upstream, or generated run
  artifact behavior changed.

Lightweight reflection:

- Reference used: user objective, Phase 1 baseline report, current plan/log
  docs, `docs/training_setup.md`, and the closed-loop planner/executor rules.
- Alignment verdict: aligned. Phase 1 is closed as diagnostic evidence, not as
  official target-shape success or planner improvement.
- Efficiency verdict: acceptable. The transition packet prevented Phase 1 from
  expanding into more metric variants and set a bounded Phase 2A target.
- Accepted-slice count since latest recorded deep reflection is now `2/3`.
  This callback does not trigger the three-accepted-slice deep-reflection gate.

Next bounded target:

- Phase 2A: define a shape guard shadow-audit event contract and review surface.
- Keep it shadow-audit-only, with explicit evidence/status fields and no
  production gate changes, official pass/fail semantics, rollout-review schema
  integration, official T1 defaults, or generated run artifacts.

## 2026-07-01: Phase 2A Planner Callback Audit And Deep Reflection

Executor slice:

- Phase 2A: shape guard shadow-audit event contract and review surface.

Planner-side callback acceptance:

- Callback status: success.
- Target lock matched:
  - branch/status: `## tx/oracle-terrain-residual-planner-v0...origin/tx/v2_6-llm-planner [ahead 20]`
  - HEAD: `cdc83bdbfee8ea3cb19b558e24268168d3dda822`
  - dirty files: expected Phase 2A files only
- Accepted changed files:
  - `testbed/eval/terrain_shape_guard_shadow.py`
  - `tests/test_terrain_shape_guard_shadow.py`
  - `docs/training_setup.md`
- Callback was factual and scoped to a pure eval shadow-audit owner, focused
  tests, and source-of-truth documentation.

Contract accepted:

- New owner: `testbed.eval.terrain_shape_guard_shadow.build_shape_guard_shadow_audit()`.
- Schema/source: `terrain_shape_guard_shadow_audit_v1` /
  `explicit_target_shape_guard_shadow_audit`.
- Event names:
  `low_payload_shape_guard_stop`, `overdig_guard_stop`,
  `depth_budget_exhausted`, `outside_protected_removed_increased`.
- Event statuses: `triggered`, `not_triggered`, `not_evaluated`,
  `invalid_input`.
- The owner reads existing nested baseline report facts only; it does not
  recompute target-grid, residual metric, projection, or report formulas.
- Thresholds and payload constraints are explicit inputs only. Missing evidence
  or thresholds produce `not_evaluated`; invalid numeric inputs produce
  `invalid_input`.

Planner-side verification:

- `python -m pytest -q tests/test_terrain_shape_guard_shadow.py` passed:
  `4 passed`.
- `python -m pytest -q tests/test_terrain_shape_guard_shadow.py tests/test_terrain_target_report.py tests/test_terrain_target_projection.py tests/test_terrain_target_metrics.py tests/test_terrain_target_grid.py tests/test_terrain_residual_metrics.py tests/test_rollout_review.py`
  passed: `49 passed`.
- `python -m compileall testbed/eval/terrain_shape_guard_shadow.py testbed/eval/terrain_target_report.py testbed/eval/terrain_target_projection.py testbed/eval/terrain_target_metrics.py tests/test_terrain_shape_guard_shadow.py tests/test_terrain_target_report.py tests/test_terrain_target_projection.py tests/test_terrain_target_metrics.py`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-changed-docs docs/training_setup.md`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-doc-inventory`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-architecture-contract`
  passed.
- Read-only current-run smoke audit passed with results file count `10 -> 10`.
- `git diff --check` passed.

Planner-side current-run smoke audit:

- Explicit non-official target spec:
  `grid_shape=[3, 2]`, `row_start=0`, `row_end=2`, `col_start=0`,
  `col_end=1`, `target_depth_m=0.25`.
- Explicit smoke-only thresholds:
  `max_target_overdig_depth_sum_m=0.0`,
  `max_target_positive_residual_depth_sum_m=0.4`,
  `max_outside_target_removed_depth_delta_m=0.0`.
- Payload inputs were absent.
- Baseline report status: `present`.
- Shadow audit status: `present`.
- Triggered events:
  `depth_budget_exhausted`, `outside_protected_removed_increased`.
- Not evaluated events: `low_payload_shape_guard_stop`.
- `overdig_guard_stop`: `not_triggered` with latest target overdig `0.0`
  against explicit max `0.0`.
- `depth_budget_exhausted`: `triggered` with latest target positive residual
  `0.374313589186` against explicit max `0.4`.
- `outside_protected_removed_increased`: `triggered` with outside-target
  removed-depth delta `0.428853750229` against explicit max `0.0`.
- `low_payload_shape_guard_stop`: `not_evaluated` because explicit payload
  inputs were absent.

Closure audit:

- No production planner/gate/policy/runtime behavior changed.
- No rollout-review schema integration, eval pass/fail, planner success
  semantics, official T1 defaults, default thresholds, generated run artifacts,
  physical volume, meter-derived current-run IoU, official cycle IDs,
  candidate/effect/capability implementation, payload inference, dependency,
  config, branch, or upstream behavior changed.
- Existing target metric/projection/report behavior was preserved.

Deep reflection:

- Trigger: this callback is the third accepted callback since the latest
  recorded deep reflection.
- Reference set: user objective, current target lock, Phase 1 accepted
  diagnostic baseline, `docs/oracle_terrain_residual_planner_v0_plan.md`,
  `docs/oracle_terrain_residual_baseline_report.md`,
  `docs/training_setup.md`, and closed-loop hard rules.
- Objective alignment: aligned. The loop has moved from metric discovery to a
  concrete shadow-audit contract while preserving the user's default of
  no-production-gate change.
- Non-goal check: still holding. Official T1 defaults, default thresholds,
  pass/fail semantics, production planner changes, rollout-review schema
  integration, generated run artifacts, and payload inference remain out of
  scope.
- Verification quality: adequate for this stage. Tests cover explicit
  thresholds, missing nested evidence, invalid numeric inputs, and all-missing
  thresholds; planner-side smoke confirms current-run behavior without writing
  artifacts.
- Documentation state: updated. `docs/training_setup.md` owns the helper
  contract, and this plan/log now record Phase 2A acceptance.
- Slice sizing verdict: acceptable. Phase 2A was a focused code slice with one
  owner and a matching test/doc path. The next slice should be docs/report
  projection, not another metric expansion.
- Event-driven discipline: preserved. Executor returned callback facts to the
  planner thread; planner audited before accepting and dispatching.
- Prompt/config discipline: preserved. No runtime config, branch, upstream, or
  dependency changes were made.
- Accepted-slice count since latest recorded deep reflection resets to `0/3`
  after this reflection.

Next bounded target:

- Phase 2B should refresh the durable baseline report with the current-run
  shape guard shadow-audit results using explicit example thresholds.
- Keep it docs/report-only unless a narrow source-of-truth doc sync is needed.
- Do not add more shadow event code, production gates, official thresholds,
  rollout-review schema integration, pass/fail semantics, generated run
  artifacts, or payload inference.

## 2026-07-01: Phase 2B Executor Report Packet

Executor slice:

- Phase 2B: durable current-run shape guard shadow-audit report refresh.

Executor status:

- Pending planner callback audit.
- Expected docs/report files:
  - `docs/oracle_terrain_residual_baseline_report.md`
  - `docs/oracle_terrain_residual_planner_v0_plan.md`
  - `docs/oracle_terrain_residual_planner_closed_loop_log.md`

Current-run report/audit facts recorded:

- Baseline report recomputed in memory with explicit non-official target spec:
  `grid_shape=[3, 2]`, rows `[0:2]`, cols `[0:1]`,
  `target_depth_m=0.25`.
- Shape guard shadow audit recomputed in memory with explicit report-only
  example thresholds:
  - `max_target_overdig_depth_sum_m=0.0`
  - `max_target_positive_residual_depth_sum_m=0.4`
  - `max_outside_target_removed_depth_delta_m=0.0`
  - payload inputs absent
- Baseline report status: `present`.
- Shadow audit status: `present`.
- Triggered events:
  `depth_budget_exhausted`, `outside_protected_removed_increased`.
- Not-evaluated events: `low_payload_shape_guard_stop`.
- Event records:
  - `overdig_guard_stop`: `not_triggered`, latest target overdig `0.0`
    against explicit max `0.0`.
  - `depth_budget_exhausted`: `triggered`, latest target positive residual
    `0.374313589186` against explicit max `0.4`.
  - `outside_protected_removed_increased`: `triggered`,
    outside-target removed-depth delta `0.428853750229` against explicit max
    `0.0`.
  - `low_payload_shape_guard_stop`: `not_evaluated` because explicit payload
    inputs were absent.

Scope preserved:

- This report packet is shadow-only diagnostic evidence.
- It does not define official thresholds, target-shape success/failure,
  production planner/gate behavior, eval pass/fail, rollout-review schema,
  generated run artifacts, payload inference, physical volume, or official T1
  semantics.

## 2026-07-01: Phase 2B Planner Callback Audit

Planner-side callback acceptance:

- Callback status: success.
- Target lock matched:
  - branch/status: `## tx/oracle-terrain-residual-planner-v0...origin/tx/v2_6-llm-planner [ahead 21]`
  - HEAD: `8754d432db5e70eaa78df77a06e914a188ee82b6`
  - dirty files: expected Phase 2B docs only
- Accepted changed files:
  - `docs/oracle_terrain_residual_baseline_report.md`
  - `docs/oracle_terrain_residual_planner_v0_plan.md`
  - `docs/oracle_terrain_residual_planner_closed_loop_log.md`
- Callback was factual and scoped to docs/report refresh only.

Planner-side verification:

- Read-only current-run report/audit smoke passed with results file count
  `10 -> 10`.
- Recomputed shadow audit values matched the report:
  - triggered events:
    `depth_budget_exhausted`, `outside_protected_removed_increased`
  - not-evaluated events: `low_payload_shape_guard_stop`
  - `overdig_guard_stop`: `not_triggered`, latest target overdig `0.0`
    against explicit max `0.0`
  - `depth_budget_exhausted`: `triggered`, latest target positive residual
    `0.374313589186` against explicit max `0.4`
  - `outside_protected_removed_increased`: `triggered`,
    outside-target removed-depth delta `0.428853750229` against explicit max
    `0.0`
- `python scripts/planner_architecture_doc_guard.py --check-changed-docs docs/oracle_terrain_residual_baseline_report.md docs/oracle_terrain_residual_planner_v0_plan.md docs/oracle_terrain_residual_planner_closed_loop_log.md`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-doc-inventory`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-architecture-contract`
  passed.
- `git diff --check` passed.

Closure audit:

- The durable baseline report now includes the Phase 2A shadow-audit result for
  the current run.
- The plan now marks durable current-run counting of the four default shadow
  events complete.
- The recorded thresholds remain explicit report/smoke examples, not official
  defaults, runtime gate thresholds, or target-shape success criteria.
- No code, tests, rollout-review schema, generated run artifacts, official
  defaults, pass/fail semantics, eval success, planner success, production
  planner/gate/policy/runtime behavior, payload inference, physical volume,
  meter-derived current-run IoU, candidate/effect/capability implementation,
  dependency/config/branch/upstream behavior changed.

Lightweight reflection:

- Reference used: Phase 2 shadow-audit section in
  `docs/oracle_terrain_residual_planner_v0_plan.md`, the durable baseline
  report, the Phase 2A shadow-audit contract in `docs/training_setup.md`, and
  the closed-loop hard rules.
- Alignment verdict: aligned. Phase 2B converted current-run shadow events into
  durable evidence without promoting them into official thresholds or gates.
- Efficiency verdict: useful docs/report slice. The next remaining question is
  impact, not another event-contract expansion.
- Accepted-slice count since latest recorded deep reflection is now `1/3`.

Next bounded target:

- Phase 2C should analyze current-run shadow-event impact evidence: whether the
  recorded shadow events indicate reduced overdig risk and what payload /
  cycle-efficiency evidence is available or missing.
- Prefer a docs/report analysis slice if existing rollout review fields are
  sufficient. Add code only if a stable focused eval owner is necessary to
  avoid ad hoc report math.
- Keep no-production-gate, no official thresholds, no pass/fail semantics, no
  rollout-review schema integration, and no generated run artifacts.

## 2026-07-01: Phase 2C Executor Impact Evidence Packet

Executor slice:

- Phase 2C: current-run shadow-event impact evidence review.
- Scope: docs/report analysis only, using existing baseline report, shadow
  audit, rollout review, and rollout summary fields.
- No code, tests, rollout-review schema, production gate, official threshold,
  or generated run artifact changes.

Read-only recomputation:

- Results dir:
  `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results`.
- Rollout jsonl:
  `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results/rollouts/rollout_000.jsonl`.
- Explicit target spec: `grid_shape=[3, 2]`, rows `[0:2]`, cols `[0:1]`,
  target depth `0.25`.
- Explicit report-only thresholds:
  - `max_target_overdig_depth_sum_m=0.0`
  - `max_target_positive_residual_depth_sum_m=0.4`
  - `max_outside_target_removed_depth_delta_m=0.0`
  - payload inputs absent.
- Results file count stayed `10 -> 10`.

Overdig-risk evidence recorded:

- Shadow audit status: `present`.
- Triggered events:
  `depth_budget_exhausted`, `outside_protected_removed_increased`.
- Not-evaluated events: `low_payload_shape_guard_stop`.
- `outside_protected_removed_increased`: `triggered` because outside-target
  removed-depth delta is `0.428853750229` against explicit max `0.0`.
- `depth_budget_exhausted`: `triggered` because latest target positive residual
  is `0.374313589186` against explicit max `0.4`.
- `overdig_guard_stop`: `not_triggered` because latest target overdig is `0.0`
  against explicit max `0.0`.

Payload / cycle-efficiency evidence recorded:

- `build_rollout_review(results_dir)` returned overall status
  `needs_root_cause_audit`, with no evidence gaps.
- Rollout summary fields report `success=true`,
  `target_cycle_gate_success=false`, stop reason `dig_area_depleted`,
  completed dump cycles `10`, target cycle gate `15`, and `10`
  planned/actual cycle records.
- Bucket mass out mean/min/max: `61.33190612793` /
  `28.913818359375` / `79.430519104004` kg.
- Deposited fraction mean/min/max: `0.802401915908` /
  `0.572773417672` / `0.968514219634`.
- Quality fields: `quality_issue_count=183`,
  `low_cycle_deposited_fraction_count=9`, post-dump target mass drop mean/max
  `0.0` / `0.0` kg.

Evidence gaps recorded:

- The current audit is retrospective and does not simulate stopping, replanning,
  or alternate cuts at triggered events.
- `low_payload_shape_guard_stop` remains `not_evaluated` because explicit
  payload inputs are absent.
- Current bucket mass and deposited-fraction fields describe the actual run,
  not a counterfactual guarded run.
- Existing artifacts do not prove guarded cycle count, cycle time, or payload
  efficiency after hypothetical shadow stops.
- The explicit thresholds remain report/smoke examples only, not official
  defaults or production gate values.

Durable docs updated:

- `docs/oracle_terrain_residual_baseline_report.md` now includes
  `Shadow Audit Impact Evidence` with overdig-risk signal, available
  payload/cycle evidence, evidence gaps, and a conservative conclusion.
- `docs/oracle_terrain_residual_planner_v0_plan.md` records Phase 2C as
  partial evidence and keeps the impact-analysis checklist item open.

## 2026-07-01: Phase 2C Planner Callback Audit

Planner-side callback acceptance:

- Callback status: success.
- Target lock matched:
  - branch/status: `## tx/oracle-terrain-residual-planner-v0...origin/tx/v2_6-llm-planner [ahead 22]`
  - HEAD: `770489fe6c80cbbc420450865cac1f6800c40ba8`
  - dirty files: expected Phase 2C docs only
- Accepted changed files:
  - `docs/oracle_terrain_residual_baseline_report.md`
  - `docs/oracle_terrain_residual_planner_v0_plan.md`
  - `docs/oracle_terrain_residual_planner_closed_loop_log.md`
- Callback was factual and scoped to docs/report analysis.

Planner-side verification:

- A first planner-side smoke snippet failed because it accessed
  `build_rollout_review()` through a non-existent top-level `rollouts` key.
  Root cause: validation-script structure mismatch; current builder returns
  `rollout_reviews`.
- Corrected read-only smoke passed with results file count `10 -> 10`.
- Recomputed shadow audit values matched the report:
  - triggered events:
    `depth_budget_exhausted`, `outside_protected_removed_increased`
  - not-evaluated events: `low_payload_shape_guard_stop`
  - `overdig_guard_stop`: `not_triggered`, latest target overdig `0.0`
    against explicit max `0.0`
  - `depth_budget_exhausted`: `triggered`, latest target positive residual
    `0.374313589186` against explicit max `0.4`
  - `outside_protected_removed_increased`: `triggered`,
    outside-target removed-depth delta `0.428853750229` against explicit max
    `0.0`
- Recomputed payload / cycle fields matched the report:
  - review overall status and rollout status: `needs_root_cause_audit`
  - `success=True`, `target_cycle_gate_success=False`, stop reason
    `dig_area_depleted`
  - planned/actual cycle count `10`, completed dump count `10`, target cycle
    gate `15`
  - bucket mass out mean/min/max/stdev:
    `61.33190612793` / `28.913818359375` / `79.4305191040039` /
    `15.127678986711`
  - deposited fraction mean/min/max/stdev:
    `0.802401915908` / `0.5727734176718415` /
    `0.9685142196339357` / `0.114068889876`
  - target deposit delta mean/min/max:
    `49.890930366516` / `22.66865348815918` / `73.15655517578125`
  - `quality_issue_count=183`, `low_cycle_deposited_fraction_count=9`,
    post-dump target mass drop mean/max `0.0` / `0.0`
- `python scripts/planner_architecture_doc_guard.py --check-changed-docs docs/oracle_terrain_residual_baseline_report.md docs/oracle_terrain_residual_planner_v0_plan.md docs/oracle_terrain_residual_planner_closed_loop_log.md`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-doc-inventory`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-architecture-contract`
  passed.
- `git diff --check` passed.

Closure audit:

- The durable baseline now records a conservative impact review: current
  evidence supports an outside-target overdig-risk concern under explicit
  example thresholds.
- The plan correctly keeps the Phase 2 impact-analysis checklist item open.
  Current artifacts do not prove a counterfactual guarded run, guarded cycle
  count, cycle time, or payload efficiency after hypothetical shadow stops.
- `low_payload_shape_guard_stop` remains `not_evaluated` because explicit
  payload inputs are absent.
- No code, tests, rollout-review schema, generated run artifacts, official
  defaults, pass/fail semantics, eval success, planner success, production
  planner/gate/policy/runtime behavior, payload inference, physical volume,
  meter-derived current-run IoU, candidate/effect/capability implementation,
  dependency/config/branch/upstream behavior changed.

Lightweight reflection:

- Reference used: Phase 2 impact-analysis requirement in
  `docs/oracle_terrain_residual_planner_v0_plan.md`, current durable baseline
  report, Phase 2A shadow-audit contract, and closed-loop hard rules.
- Alignment verdict: aligned. Phase 2C answered the current evidence question
  without overstating it.
- Efficiency verdict: useful boundary-setting slice. The next action should
  close or hand off Phase 2 based on the evidence gap, then move toward
  counterfactual/offline candidate work rather than adding more report fields.
- Accepted-slice count since latest recorded deep reflection is now `2/3`.

Next bounded target:

- Phase 2D should write a concise Phase 2 closure / handoff note: shadow audit
  is useful as retrospective evidence, but current artifacts are insufficient
  to prove material payload/cycle impact or justify production gating.
- The recommended next development direction is to proceed to offline
  candidate/effect evidence work rather than promote a shape guard.
- Keep this as docs-only unless a guard requires narrow doc sync. Do not add
  code, tests, default thresholds, production gates, pass/fail semantics,
  rollout-review schema integration, generated run artifacts, or payload
  inference.

## 2026-07-01: Phase 2D Executor Closure Packet

Executor slice:

- Phase 2D: Phase 2 closure / Phase 3 handoff note.
- Scope: docs-only closure.
- No code, tests, metrics, report fields, rollout-review schema, generated run
  artifacts, production gate, default threshold, pass/fail, or payload
  inference changes.

Phase 2 closure facts recorded:

- Phase 2 is closed as a no-production-gate shadow-audit milestone.
- The shadow audit is useful retrospective evidence for current-run risk
  review, especially the outside-target removed-depth growth signal recorded in
  Phase 2C.
- Current artifacts are insufficient to justify production gating or to prove
  no material payload / cycle-efficiency loss.
- The Phase 2 impact-analysis checklist item remains open and is explicitly
  deferred / blocked by missing shadow-stop counterfactual evidence.
- Missing evidence remains: shadow stop / replan counterfactuals, guarded cycle
  count, cycle-time evidence, and explicit payload inputs.

Phase 3 handoff facts recorded:

- `docs/oracle_terrain_residual_planner_v0_plan.md` now states the Phase 3A
  default entry target as offline discrete candidate generator / candidate
  evidence.
- The handoff explicitly does not promote a shape guard to production planner
  integration.

Documentation changed:

- `docs/oracle_terrain_residual_planner_v0_plan.md`.
- `docs/oracle_terrain_residual_planner_closed_loop_log.md`.

## 2026-07-01: Phase 2D Planner Callback Audit And Deep Reflection

Planner-side callback acceptance:

- Callback status: success.
- Target lock matched:
  - branch/status: `## tx/oracle-terrain-residual-planner-v0...origin/tx/v2_6-llm-planner [ahead 23]`
  - HEAD: `7aa2b0ec78bed8bad0ec7165f6019f0e53fd9f79`
  - dirty files: expected Phase 2D docs only
- Accepted changed files:
  - `docs/oracle_terrain_residual_planner_v0_plan.md`
  - `docs/oracle_terrain_residual_planner_closed_loop_log.md`
- Callback was factual and scoped to docs-only closure.

Planner-side verification:

- `python scripts/planner_architecture_doc_guard.py --check-changed-docs docs/oracle_terrain_residual_planner_v0_plan.md docs/oracle_terrain_residual_planner_closed_loop_log.md`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-doc-inventory`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-architecture-contract`
  passed.
- `git diff --check` passed.

Closure audit:

- Phase 2 is now recorded as a no-production-gate shadow-audit milestone.
- The Phase 2 impact-analysis checklist remains open and explicitly deferred
  by missing shadow-stop counterfactual evidence.
- Phase 3A default entry target is now recorded as offline discrete candidate
  generator / candidate evidence, not production planner integration.
- No code, tests, metrics, report fields, rollout-review schema, generated run
  artifacts, official default thresholds, official T1 defaults, pass/fail
  semantics, eval success, planner success, production planner/gate/policy
  runtime behavior, payload inference, physical volume, meter-derived current
  run IoU, candidate/effect/capability implementation, dependency/config,
  branch, or upstream behavior changed.

Deep reflection:

- Trigger: this callback is the third accepted callback since the latest
  recorded deep reflection.
- Reference set: user objective, Phase 1 diagnostic baseline, Phase 2
  shadow-audit contract and impact notes, durable baseline report, current
  plan/log docs, `docs/training_setup.md`, and closed-loop hard rules.
- Objective alignment: aligned. Phase 2 created a concrete shadow-audit
  contract and durable evidence, then stopped before unsupported production
  gating.
- Non-goal check: still holding. Official thresholds, production gate behavior,
  eval pass/fail, planner success, rollout-review schema integration, generated
  run artifacts, and payload inference were not introduced.
- Verification quality: adequate for the current milestone. Phase 2 verified
  shadow audit mechanics, current-run report values, and payload/cycle evidence
  limits, but cannot prove counterfactual guarded performance from existing
  artifacts.
- Documentation state: current. The plan, baseline report, training setup, and
  closed-loop log now agree on the Phase 2 boundary and Phase 3A default entry.
- Slice sizing verdict: acceptable. Phase 2 avoided further report-field churn
  after the evidence gap became clear.
- Event-driven discipline: preserved. Executor callbacks returned to the
  planner thread and planner closure preceded the next dispatch.
- Next-slice implication: move to Phase 3A offline candidate evidence. Do not
  continue expanding shape-guard reports unless new counterfactual data exists.
- Accepted-slice count since latest recorded deep reflection resets to `0/3`
  after this reflection.

Next bounded target:

- Phase 3A: define the offline discrete candidate generator contract and a
  minimal focused owner/test surface for explicit target/residual inputs.
- Candidate generation must remain offline/eval-only, with no production
  planner integration, no pass/fail semantics, no official defaults, and no run
  artifacts.

## 2026-07-01: Phase 3A Executor Candidate Contract Packet

Executor slice:

- Phase 3A: offline discrete candidate generator contract.
- Scope: focused pure eval owner plus focused tests and source-of-truth docs.
- No production planner integration, rollout-review schema integration, CLI
  default, config, run artifact, official T1 default, pass/fail, physical
  volume, meter-derived current-run IoU, effect/capability scoring, dependency,
  branch, or upstream changes.

Boundary decision:

- Created new focused owner
  `testbed/eval/terrain_candidate_generation.py`.
- Existing target grid, target metrics, projection, report, rollout review, and
  shadow-audit modules do not own offline candidate-generation algorithms.

TDD evidence:

- Red command:
  `python -m pytest -q tests/test_terrain_candidate_generation.py`.
- Red failure: `ModuleNotFoundError: No module named
  'testbed.eval.terrain_candidate_generation'`.
- Green focused command passed after implementation:
  `python -m pytest -q tests/test_terrain_candidate_generation.py`.

Candidate-generation contract implemented:

- Public function:
  `build_discrete_cut_candidates(...)`.
- Inputs are explicit row-major residual depth grid, target mask, valid mask,
  grid shape, direction options, depth fraction options, and explicit min/max
  candidate count.
- Candidate anchors are valid target cells with positive residual.
- Candidate order is deterministic: row-major anchors, direction option order,
  then depth fraction option order.
- Candidate records include candidate id, anchor cell / row / col, direction,
  depth fraction, anchor positive residual depth, candidate depth, and
  `offline_only=true`.
- Statuses include `present`, `candidate_count_below_min`,
  `candidate_count_above_max`, `no_positive_residual_cells`,
  `invalid_grid_shape`, `invalid_grid_lengths`, `invalid_mask_values`,
  `invalid_residual_values`, and `invalid_candidate_options`.

Current-run candidate smoke:

- Recomputed the current-run baseline report read-only from
  `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results/rollouts/rollout_000.jsonl`.
- Explicit target spec: `grid_shape=[3, 2]`, rows `[0:2]`, cols `[0:1]`,
  `target_depth_m=0.25`.
- Candidate options:
  `direction_options=['row_forward', 'row_reverse', 'col_forward', 'col_reverse']`,
  `depth_fraction_options=[0.5, 0.75, 1.0]`,
  `min_candidate_count=20`, `max_candidate_count=100`.
- Results file count stayed `10 -> 10`.
- Candidate status: `present`.
- Positive residual target cells: `[0, 2]`.
- Candidate count / untruncated count: `24` / `24`.
- Coverage: covered cells `[0, 2]`, uncovered cells `[]`.
- First candidate: `cut_candidate_000001` at anchor cell `0`, row `0`, col
  `0`, direction `row_forward`, depth fraction `0.5`, candidate depth
  `0.095992526039`.
- Last candidate: `cut_candidate_000024` at anchor cell `2`, row `1`, col `0`,
  direction `col_reverse`, depth fraction `1.0`, candidate depth
  `0.182328537107`.

Documentation changed:

- `docs/training_setup.md` documents the offline candidate-generation contract,
  explicit options, statuses, provenance limits, and non-goals.
- `docs/oracle_terrain_residual_planner_v0_plan.md` marks the first Phase 3
  candidate-generation item complete and records Phase 3A facts; later Phase 3
  footprint, boundary, depth-budget, return/alignment, effect scoring, and
  production integration items remain incomplete.

## 2026-07-01: Phase 3A Planner Callback Audit

Callback audit:

- Accepted executor status: `success`.
- Target lock matched the expected Phase 3A base:
  `3a920bcc6895e8a4ceec44cfa5d449346fc98768`.
- Accepted changed files:
  - `testbed/eval/terrain_candidate_generation.py`
  - `tests/test_terrain_candidate_generation.py`
  - `docs/training_setup.md`
  - `docs/oracle_terrain_residual_planner_v0_plan.md`
  - `docs/oracle_terrain_residual_planner_closed_loop_log.md`
- Callback was factual and scoped to offline/eval-only candidate generation.

Planner-side verification:

- `python -m pytest -q tests/test_terrain_candidate_generation.py tests/test_terrain_target_report.py tests/test_terrain_target_projection.py tests/test_terrain_target_metrics.py tests/test_terrain_target_grid.py tests/test_terrain_residual_metrics.py tests/test_rollout_review.py`
  passed with `50 passed`.
- `python -m compileall testbed/eval/terrain_candidate_generation.py testbed/eval/terrain_target_report.py testbed/eval/terrain_target_projection.py testbed/eval/terrain_target_metrics.py tests/test_terrain_candidate_generation.py tests/test_terrain_target_report.py tests/test_terrain_target_projection.py tests/test_terrain_target_metrics.py`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-changed-docs docs/training_setup.md docs/oracle_terrain_residual_planner_v0_plan.md docs/oracle_terrain_residual_planner_closed_loop_log.md`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-doc-inventory`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-architecture-contract`
  passed.
- Read-only current-run candidate smoke kept the results file count at
  `10 -> 10`.
- `git diff --check` passed.

Closure audit:

- Phase 3A now has a deterministic offline candidate-generation contract.
- Current-run smoke generated `24` candidates from positive residual target
  cells `[0, 2]` using explicit non-official options.
- The helper remains candidate evidence only: no bucket physical footprint,
  boundary tolerance, depth budget, return/alignment cost, heuristic scoring,
  production planner integration, official defaults, pass/fail semantics, or
  run artifact writing was introduced.
- Accepted-slice count since latest recorded deep reflection: `1/3`.

Next bounded target:

- Phase 3B: add offline candidate constraint/evidence annotation for generated
  candidates.
- Keep it eval-only and explicit-input-only. It may report grid-cell footprint,
  target/outside-target cells, depth-budget evidence, and return/alignment
  proxy evidence, but must not become heuristic scoring, production planner
  integration, official thresholds, physical bucket geometry, or eval pass/fail.

## 2026-07-01: Phase 3B Executor Candidate Evidence Packet

Slice:

- Phase 3B: offline candidate constraint/evidence annotation.

Boundary:

- Added a focused eval owner, `testbed/eval/terrain_candidate_evidence.py`.
- Kept `terrain_candidate_generation.py` as candidate enumeration only.
- Did not change rollout review, target report/projection/metrics owners,
  production planner modules, runtime config, or generated run artifacts.

TDD red:

- Added `tests/test_terrain_candidate_evidence.py` before production code.
- Red command: `python -m pytest -q tests/test_terrain_candidate_evidence.py`.
- Expected failure: `ModuleNotFoundError: No module named
  'testbed.eval.terrain_candidate_evidence'`.

Implemented contract:

- Public function:
  `build_candidate_constraint_evidence(...)`.
- Inputs are explicit: candidates, target mask, valid mask, grid shape,
  `max_candidate_depth_m`, `protected_boundary_cell_radius`, and optional
  `return_origin_cell_index`.
- Per-candidate evidence preserves input order and reports candidate id, anchor
  cell, direction, candidate depth, row-major grid-cell footprint proxy,
  grid-boundary clipping, target/outside-target footprint cells, valid/invalid
  footprint cells, protected/outside-protected boundary cells, explicit
  depth-budget status, and optional Manhattan return-alignment proxy.
- Top-level output includes schema/source/status/offline-only/profile,
  candidate count, evidence records, constraint summary, validation errors, and
  missing provenance statuses.
- Statuses include `present`, `no_candidates`, `invalid_candidates`,
  `invalid_grid_shape`, `invalid_grid_lengths`, `invalid_mask_values`,
  `invalid_depth_budget`, `invalid_boundary_radius`, and
  `invalid_return_origin`.

Current-run candidate evidence smoke:

- Recomputed the current-run baseline report read-only from
  `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results/rollouts/rollout_000.jsonl`.
- Explicit target spec: `grid_shape=[3, 2]`, rows `[0:2]`, cols `[0:1]`,
  `target_depth_m=0.25`.
- Candidate options:
  `direction_options=['row_forward', 'row_reverse', 'col_forward', 'col_reverse']`,
  `depth_fraction_options=[0.5, 0.75, 1.0]`,
  `min_candidate_count=20`, `max_candidate_count=100`.
- Evidence inputs: `max_candidate_depth_m=0.2`,
  `protected_boundary_cell_radius=1`, `return_origin_cell_index=0`.
- Results file count stayed `10 -> 10`.
- Baseline status / latest row: `present` / `6147`.
- Candidate status / count: `present` / `24`; positive residual target cells
  `[0, 2]`.
- Evidence status: `present`.
- Constraint summary: depth-budget exceeded count `0`, clipped-by-grid-boundary
  count `9`, outside-target footprint candidate count `9`,
  outside-protected footprint candidate count `0`, protected-boundary
  saturation ratio `1.0`, return proxy min/max `0` / `1` cells.
- First evidence sample: `cut_candidate_000001`, anchor cell `0`, direction
  `row_forward`, candidate depth `0.095992526039`, footprint `[0, 1]`,
  outside-target footprint `[1]`, return proxy `0` cells.
- Last evidence sample: `cut_candidate_000024`, anchor cell `2`, direction
  `col_reverse`, candidate depth `0.182328537107`, footprint `[2, 0]`,
  outside-target footprint `[]`, return proxy `1` cell.

Documentation changed:

- `docs/training_setup.md` documents the offline candidate evidence contract,
  explicit inputs, statuses, proxy limitations, and non-goals.
- `docs/oracle_terrain_residual_planner_v0_plan.md` marks the second Phase 3
  checklist item complete only as grid-cell proxy/evidence fields and records
  that physical bucket swept-footprint remains Phase 4.

## 2026-07-01: Phase 3B Planner Callback Audit

Callback audit:

- Accepted executor status: `success`.
- Target lock matched the expected Phase 3B base:
  `b07ac5086736b4218d01ed5b11d3e5d9ee9fadf7`.
- Accepted changed files:
  - `testbed/eval/terrain_candidate_evidence.py`
  - `tests/test_terrain_candidate_evidence.py`
  - `docs/training_setup.md`
  - `docs/oracle_terrain_residual_planner_v0_plan.md`
  - `docs/oracle_terrain_residual_planner_closed_loop_log.md`
- Callback was factual and scoped to offline/eval-only candidate constraint
  evidence.

Planner-side verification:

- `python -m pytest -q tests/test_terrain_candidate_evidence.py tests/test_terrain_candidate_generation.py tests/test_terrain_target_report.py tests/test_terrain_target_projection.py tests/test_terrain_target_metrics.py tests/test_terrain_target_grid.py tests/test_terrain_residual_metrics.py tests/test_rollout_review.py`
  passed with `54 passed`.
- `python -m compileall testbed/eval/terrain_candidate_evidence.py testbed/eval/terrain_candidate_generation.py testbed/eval/terrain_target_report.py testbed/eval/terrain_target_projection.py testbed/eval/terrain_target_metrics.py tests/test_terrain_candidate_evidence.py tests/test_terrain_candidate_generation.py tests/test_terrain_target_report.py tests/test_terrain_target_projection.py tests/test_terrain_target_metrics.py`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-changed-docs docs/training_setup.md docs/oracle_terrain_residual_planner_v0_plan.md docs/oracle_terrain_residual_planner_closed_loop_log.md`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-doc-inventory`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-architecture-contract`
  passed.
- Read-only current-run candidate evidence smoke kept the results file count at
  `10 -> 10`.
- `git diff --check` passed.

Closure audit:

- Phase 3B now has an explicit offline constraint/evidence annotation contract
  for generated candidates.
- Current-run smoke produced evidence for `24` candidates: depth-budget
  exceeded count `0`, clipped-by-grid-boundary count `9`, outside-target
  footprint candidate count `9`, outside-protected footprint candidate count
  `0`, protected-boundary saturation ratio `1.0`, and return proxy min/max
  `0` / `1` cells.
- The helper remains grid-cell proxy evidence only. It does not implement
  physical bucket swept-footprint, heuristic scoring, sorting, top-k selection,
  production planner integration, official defaults, pass/fail semantics, or run
  artifact writing.
- Accepted-slice count since latest recorded deep reflection: `2/3`.

Next bounded target:

- Phase 3C: implement offline heuristic candidate scoring over Phase 3A/3B
  outputs.
- Keep scoring explicit-input-only and eval-only. It may compute deterministic
  score components from candidate depth, target/outside/protected footprint
  evidence, depth-budget evidence, and return proxy, but must not sort/top-k by
  default, change production planner behavior, define official weights, or
  promote pass/fail semantics.

## 2026-07-01: Phase 3C Executor Candidate Scoring Packet

Slice:

- Phase 3C: offline heuristic candidate scoring/ranking evidence.

Boundary:

- Added a focused eval owner, `testbed/eval/terrain_candidate_scoring.py`.
- Kept candidate generation as enumeration and candidate evidence as constraint
  annotation.
- Did not change rollout review, target report/projection/metrics owners,
  production planner modules, runtime config, or generated run artifacts.

TDD red:

- Added `tests/test_terrain_candidate_scoring.py` before production code.
- Red command: `python -m pytest -q tests/test_terrain_candidate_scoring.py`.
- Expected failure: `ModuleNotFoundError: No module named
  'testbed.eval.terrain_candidate_scoring'`.

Implemented contract:

- Public function:
  `build_candidate_heuristic_scores(...)`.
- Inputs are explicit: Phase 3B evidence records and caller-provided weights.
- Required weight keys: `candidate_depth_reward`,
  `target_footprint_cell_reward`, `outside_target_footprint_cell_penalty`,
  `outside_protected_boundary_cell_penalty`,
  `depth_budget_exceeded_penalty`, `grid_boundary_clipped_penalty`, and
  `return_alignment_distance_penalty`.
- Score records preserve evidence input order and report component values for
  candidate depth, target footprint, outside-target footprint, outside-protected
  footprint, depth-budget exceeded, grid-boundary clipped, and return-alignment
  distance.
- Ranking is diagnostic-only: deterministic total-score descending order with
  input-order tie break; no selected/top-k/action semantics.
- Statuses include `present`, `no_evidence_records`,
  `invalid_evidence_records`, and `invalid_weights`.

Current-run candidate scoring smoke:

- Recomputed the current-run baseline report read-only from
  `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results/rollouts/rollout_000.jsonl`.
- Explicit target spec: `grid_shape=[3, 2]`, rows `[0:2]`, cols `[0:1]`,
  `target_depth_m=0.25`.
- Candidate options:
  `direction_options=['row_forward', 'row_reverse', 'col_forward', 'col_reverse']`,
  `depth_fraction_options=[0.5, 0.75, 1.0]`,
  `min_candidate_count=20`, `max_candidate_count=100`.
- Evidence inputs: `max_candidate_depth_m=0.2`,
  `protected_boundary_cell_radius=1`, `return_origin_cell_index=0`.
- Scoring weights:
  `candidate_depth_reward=10.0`, `target_footprint_cell_reward=1.0`,
  `outside_target_footprint_cell_penalty=2.0`,
  `outside_protected_boundary_cell_penalty=4.0`,
  `depth_budget_exceeded_penalty=5.0`,
  `grid_boundary_clipped_penalty=0.5`,
  `return_alignment_distance_penalty=0.25`.
- Results file count stayed `10 -> 10`.
- Baseline status / latest row: `present` / `6147`.
- Candidate status / count: `present` / `24`.
- Evidence status: `present`.
- Scoring status / score count: `present` / `24`.
- Score summary: best candidate `cut_candidate_000009` score
  `3.91985052079`; worst candidate `cut_candidate_000013` score
  `-0.33835731446`; mean score `1.591175959447`.
- Ranking first / last: `cut_candidate_000009` /
  `cut_candidate_000019`.
- First score record: `cut_candidate_000001`, total score
  `-0.04007473961`, candidate-depth reward `0.95992526039`,
  target-footprint reward `1.0`, outside-target penalty `-2.0`,
  return-alignment penalty `0.0`.
- Best score record: `cut_candidate_000009`, total score `3.91985052079`,
  candidate-depth reward `1.91985052079`, target-footprint reward `2.0`,
  no outside-target/protected/depth/clipped/return penalty.

Documentation changed:

- `docs/training_setup.md` documents the offline candidate scoring contract,
  explicit weights, statuses, ranking-evidence-only boundary, and non-goals.
- `docs/oracle_terrain_residual_planner_v0_plan.md` marks the third Phase 3
  checklist item complete only as offline heuristic scoring/ranking evidence
  and records that calibrated effect/capability models remain out of scope.

## 2026-07-01: Phase 3C Planner Callback Audit And Deep Reflection

Callback audit:

- Accepted executor status: `success`.
- Target lock matched the expected Phase 3C base:
  `c828c16d6f7eda7320f4f296beee911996b860b4`.
- Accepted changed files:
  - `testbed/eval/terrain_candidate_scoring.py`
  - `tests/test_terrain_candidate_scoring.py`
  - `docs/training_setup.md`
  - `docs/oracle_terrain_residual_planner_v0_plan.md`
  - `docs/oracle_terrain_residual_planner_closed_loop_log.md`
- Callback was factual and scoped to offline/eval-only heuristic score
  evidence.

Planner-side verification:

- `python -m pytest -q tests/test_terrain_candidate_scoring.py tests/test_terrain_candidate_evidence.py tests/test_terrain_candidate_generation.py tests/test_terrain_target_report.py tests/test_terrain_target_projection.py tests/test_terrain_target_metrics.py tests/test_terrain_target_grid.py tests/test_terrain_residual_metrics.py tests/test_rollout_review.py`
  passed with `58 passed`.
- `python -m compileall testbed/eval/terrain_candidate_scoring.py testbed/eval/terrain_candidate_evidence.py testbed/eval/terrain_candidate_generation.py testbed/eval/terrain_target_report.py testbed/eval/terrain_target_projection.py testbed/eval/terrain_target_metrics.py tests/test_terrain_candidate_scoring.py tests/test_terrain_candidate_evidence.py tests/test_terrain_candidate_generation.py tests/test_terrain_target_report.py tests/test_terrain_target_projection.py tests/test_terrain_target_metrics.py`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-changed-docs docs/training_setup.md docs/oracle_terrain_residual_planner_v0_plan.md docs/oracle_terrain_residual_planner_closed_loop_log.md`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-doc-inventory`
  passed.
- `python scripts/planner_architecture_doc_guard.py --check-architecture-contract`
  passed.
- Read-only current-run candidate scoring smoke kept the results file count at
  `10 -> 10`.
- `git diff --check` passed.

Closure audit:

- Phase 3 now has three focused eval-only owners for candidate enumeration,
  candidate constraint evidence, and heuristic score/ranking evidence.
- Current-run smoke produced `24` score records. Best evidence label:
  `cut_candidate_000009` with score `3.91985052079`; worst evidence label:
  `cut_candidate_000013` with score `-0.33835731446`.
- Ranking remains diagnostic-only: it contains ordered candidate ids, not
  selected/top-k/action semantics.
- No production planner integration, rollout-review schema integration,
  official/default weights, pass/fail semantics, generated run artifacts,
  calibrated effect/capability model, payload inference, physical volume, or
  config/dependency changes were introduced.

Deep reflection:

- Trigger: this callback is the third accepted callback since the latest
  recorded deep reflection.
- Reference set: user objective, Phase 1 target-residual diagnostic baseline,
  Phase 2 shadow-audit boundary, Phase 3 candidate evidence plan, durable
  baseline report, current plan/log docs, `docs/training_setup.md`, and
  closed-loop hard rules.
- Objective alignment: aligned. Phase 3 created the missing offline candidate
  evidence ladder before any production planner integration.
- Non-goal check: still holding. The loop did not introduce official target
  defaults, official candidate/default weights, top-k action selection,
  rollout-review schema changes, production gates, eval pass/fail, planner
  success semantics, generated run artifacts, or payload inference.
- Verification quality: adequate for the milestone. Candidate generation,
  constraint evidence, scoring evidence, source docs, and current-run smoke
  were all exercised, but the scoring remains heuristic evidence and has not
  been validated against real effect outcomes.
- Documentation state: current. The plan, training setup, and closed-loop log
  agree that Phase 3 is offline evidence only and Phase 4 owns effect modeling.
- Slice sizing verdict: acceptable. Phase 3 did necessary work in three owner
  slices instead of folding scoring into generation or evidence modules.
- Efficiency verdict: still useful. The last three callbacks moved code and
  tests forward rather than only process/report churn.
- Next-slice implication: move to Phase 4A geometric swept-footprint /
  expected-delta kernel with explicit inputs. Do not infer current-run cell size
  or bucket geometry.
- Accepted-slice count since latest recorded deep reflection resets to `0/3`
  after this reflection.

Next bounded target:

- Phase 4A: define a focused eval-only geometric swept-footprint / expected
  delta patch kernel.
- Keep all geometry inputs explicit. Current-run smoke may use labeled
  non-official example values, but must not infer cell size, bucket geometry,
  physical volume, production planner behavior, official defaults, or pass/fail
  semantics from the current run.

## 2026-07-02: Phase 4A Executor Geometric Effect Packet

Scope:

- Phase 4A: offline geometric swept-footprint / expected delta patch kernel.
- This executor packet records implementation facts only; planner reflection is
  not written here.

Boundary decision:

- No existing small owner owned candidate effect modeling.
- Added focused eval owner
  `testbed/eval/terrain_candidate_effect_model.py`.
- Kept candidate generation, candidate evidence, candidate scoring, target
  report/projection/metrics, rollout review, and production planner modules out
  of the effect-model responsibility.

TDD red:

- Added `tests/test_terrain_candidate_effect_model.py` before production code.
- Red command: `python -m pytest -q tests/test_terrain_candidate_effect_model.py`.
- Expected failure observed: `ModuleNotFoundError: No module named
  'testbed.eval.terrain_candidate_effect_model'`.

Contract implemented:

- Public owner:
  `build_geometric_swept_footprint_effect(...)`.
- Inputs are explicit: candidate, removed-depth grid, target-depth grid,
  target-region mask, valid mask, grid shape, cell size, bucket width, bucket
  length, and optional penetration depth.
- Candidate validation requires candidate id, anchor cell / row / col,
  direction, candidate depth, and `offline_only=true`.
- Directions match Phase 3 row-major semantics: `row_forward`, `row_reverse`,
  `col_forward`, `col_reverse`.
- Footprint model is explicitly
  `centerline_rectangular_swept_footprint_approximation`, not calibrated bucket
  physics.
- Expected delta patch is row-major and uses `candidate_depth_m` as penetration
  source unless explicit `penetration_depth_m` is supplied.
- Summary metrics include expected removed depth/volume, target removed
  depth/volume, outside-target removed depth/volume, and overdig depth/volume
  delta.
- Statuses include `present`, `invalid_candidate`, `invalid_grid_shape`,
  `invalid_grid_lengths`, `invalid_mask_values`, `invalid_depth_values`,
  `invalid_geometry`, and `no_valid_footprint_cells`.

Current-run effect smoke:

- Source rollout:
  `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results/rollouts/rollout_000.jsonl`.
- Explicit target spec: grid shape `[3, 2]`, rows `[0:2]`, cols `[0:1]`,
  target depth `0.25`.
- Phase 3 candidate/scoring inputs reused with explicit smoke-only weights and
  constraints.
- Effect geometry inputs were non-official smoke values:
  `cell_size_m=0.25`, `bucket_width_m=0.25`, `bucket_length_m=0.5`,
  `penetration_depth_m=None`.
- Results file count remained `10 -> 10`.
- Candidate count `24`; diagnostic best candidate `cut_candidate_000009` with
  score `3.91985052079`.
- Effect status `present`; footprint cells `[0, 2, 4]`; clipped `true`.
- Penetration depth `0.191985052079`, source `candidate_depth_m`.
- Expected removed depth sum / volume: `0.575955156237` /
  `0.035997197265`.
- Target removed delta sum / volume: `0.383970104158` / `0.02399813151`.
- Outside-target delta sum / volume: `0.191985052079` / `0.011999065755`.
- Overdig delta sum / volume: `0.201641567051` / `0.012602597941`.
- First / last nonzero patch facts: cell `0` / `4`, both
  `0.191985052079`.

Documentation changed:

- `docs/training_setup.md` documents the offline geometric effect contract,
  explicit geometry inputs, centerline rectangular approximation, volume
  semantics, statuses, provenance, and non-goals.
- `docs/oracle_terrain_residual_planner_v0_plan.md` marks only the first
  Phase 4 checklist item complete and records Phase 4A current-run smoke facts.
- Expected delta / payload output and calibrated effect/capability model remain
  incomplete.

Verification:

- `python -m pytest -q tests/test_terrain_candidate_effect_model.py` passed with
  `5 passed`.
- `python -m pytest -q tests/test_terrain_candidate_effect_model.py tests/test_terrain_candidate_scoring.py tests/test_terrain_candidate_evidence.py tests/test_terrain_candidate_generation.py tests/test_terrain_target_report.py tests/test_terrain_target_projection.py tests/test_terrain_target_metrics.py tests/test_terrain_target_grid.py tests/test_terrain_residual_metrics.py tests/test_rollout_review.py`
  passed with `63 passed`.
- `python -m compileall testbed/eval/terrain_candidate_effect_model.py testbed/eval/terrain_candidate_scoring.py testbed/eval/terrain_candidate_evidence.py testbed/eval/terrain_candidate_generation.py testbed/eval/terrain_target_report.py testbed/eval/terrain_target_projection.py testbed/eval/terrain_target_metrics.py tests/test_terrain_candidate_effect_model.py tests/test_terrain_candidate_scoring.py tests/test_terrain_candidate_evidence.py tests/test_terrain_candidate_generation.py tests/test_terrain_target_report.py tests/test_terrain_target_projection.py tests/test_terrain_target_metrics.py`
  passed.

Behavior preserved:

- No production planner/gate/policy/runtime integration.
- No rollout-review schema integration.
- No generated run artifacts.
- No official/default cell size, bucket geometry, penetration depth, weights,
  target shape, top-k selection, pass/fail, eval success, or planner success
  semantics.

## 2026-07-02: Phase 4A Planner Acceptance

Planner acceptance status:

- Accepted as Phase 4A geometric effect kernel evidence.
- Accepted-slice count since the latest recorded deep reflection is now `1/3`.
- No deep reflection is required for this acceptance.

Planner-side verification:

- Re-read the new effect owner, focused tests, and changed plan/training/log
  documentation.
- Re-ran the focused candidate/effect bundle:
  `tests/test_terrain_candidate_effect_model.py`,
  `tests/test_terrain_candidate_scoring.py`,
  `tests/test_terrain_candidate_evidence.py`,
  `tests/test_terrain_candidate_generation.py`, target projection/report/metric
  tests, terrain residual metric tests, and rollout review tests; result:
  `63 passed`.
- Re-ran compile checks for the new effect owner and related candidate/target
  owners and tests; result: passed.
- Re-ran changed-doc guard, docs inventory guard, architecture contract guard,
  and whitespace diff check; result: passed.
- Recomputed the current-run effect smoke read-only; results directory file
  count remained `10 -> 10`, best diagnostic candidate remained
  `cut_candidate_000009`, and effect output matched the executor packet.

Acceptance rationale:

- The slice adds a focused offline owner for explicit geometric swept-footprint
  and expected delta patch evidence.
- It keeps geometry inputs explicit and labels the model as a centerline
  rectangular approximation, not calibrated bucket physics.
- It does not change planner runtime, rollout review schema, config, official
  defaults, action selection, or success semantics.

Next bounded target:

- Phase 4B should add offline candidate effect summary / payload proxy evidence
  from explicit effect records and explicit payload capacity.
- It must remain eval-only and explicit-input-only: no calibrated model, no
  production planner integration, no top-k action semantics, no default payload
  capacity, and no generated run artifacts.

## 2026-07-02: Phase 4B Executor Effect Summary Packet

Scope:

- Phase 4B: offline candidate effect summary / payload proxy evidence.
- This executor packet records implementation facts only; planner reflection is
  not written here.

Boundary decision:

- No existing small owner owned cross-candidate effect summary or payload proxy
  evidence.
- Added focused eval owner
  `testbed/eval/terrain_candidate_effect_summary.py`.
- Kept rollout review, production planner, target metrics/projection/report,
  candidate generation, candidate evidence, candidate scoring, and the Phase 4A
  effect kernel out of the effect-summary responsibility.

TDD red:

- Added `tests/test_terrain_candidate_effect_summary.py` before production
  code.
- Red command:
  `python -m pytest -q tests/test_terrain_candidate_effect_summary.py`.
- Expected failure observed: `ModuleNotFoundError: No module named
  'testbed.eval.terrain_candidate_effect_summary'`.

Contract implemented:

- Public owner:
  `build_candidate_effect_summary(effect_records, *, payload_capacity_m3,
  profile='explicit_candidate_effect_summary')`.
- Inputs are explicit: Phase 4A effect records in caller-supplied order and
  finite positive `payload_capacity_m3`.
- Top-level output includes schema `terrain_candidate_effect_summary_v1`,
  source `explicit_candidate_effect_summary`, status, `offline_only=true`,
  profile, effect record count, payload capacity, summary records, aggregate
  summary, diagnostic rankings, validation errors, and missing provenance.
- Per-candidate summary preserves input order and reports candidate id, effect
  status, expected / target / outside-target / overdig volumes, footprint count,
  grid-boundary clipped flag, payload proxy volume / fraction, outside-target
  volume fraction, and overdig volume fraction.
- Aggregate summary reports min/max/mean payload proxy volume and fraction,
  total expected / target / outside-target / overdig volumes, and diagnostic
  candidate ids for max payload proxy, max outside-target volume, and max
  overdig volume.
- Diagnostic rankings are evidence-only and deterministic: payload proxy
  descending, outside-target volume descending, and overdig volume descending,
  with original input order tie-breaks.
- Statuses include `present`, `no_effect_records`,
  `invalid_effect_records`, and `invalid_payload_capacity`.

Current-run effect-summary smoke:

- Source rollout:
  `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results/rollouts/rollout_000.jsonl`.
- Explicit target spec: grid shape `[3, 2]`, rows `[0:2]`, cols `[0:1]`,
  target depth `0.25`.
- Phase 3 smoke options/weights and Phase 4A geometry values were reused.
- Payload capacity input was explicit, non-official smoke value
  `payload_capacity_m3=0.04`.
- Results file count remained `10 -> 10`.
- Candidate count `24`; all `24` Phase 4A effect records had status
  `present`.
- Effect summary status `present`; summary record count `24`.
- Payload proxy volume min / max / mean: `0.005697766785` /
  `0.035997197265` / `0.015352705806`.
- Payload proxy fraction min / max / mean: `0.142444169625` /
  `0.899929931625` / `0.383817645159`.
- Expected / target / outside-target / overdig volume totals:
  `0.368464939353` / `0.263189242395` / `0.105275696958` /
  `0.105879229144`.
- Max payload proxy candidate: `cut_candidate_000009`.
- Max outside-target volume candidate: `cut_candidate_000003`.
- Max overdig volume candidate: `cut_candidate_000009`.
- Payload ranking first / last: `cut_candidate_000009` /
  `cut_candidate_000016`.
- Outside-target ranking first / last: `cut_candidate_000003` /
  `cut_candidate_000024`.
- Overdig ranking first / last: `cut_candidate_000009` /
  `cut_candidate_000024`.

Documentation changed:

- `docs/training_setup.md` documents the effect summary / payload proxy
  contract, explicit capacity input, statuses, diagnostic rankings, provenance,
  and non-goals.
- `docs/oracle_terrain_residual_planner_v0_plan.md` marks the Phase 4 payload
  proxy / volume summary evidence item complete and records Phase 4B smoke
  facts.
- Calibrated effect/capability model, production integration, default
  geometry/capacity, action selection, pass/fail, eval success, and planner
  success remain out of scope.

Verification:

- `python -m pytest -q tests/test_terrain_candidate_effect_summary.py` passed
  with `5 passed`.
- Full related bundle, compile checks, doc guards, architecture guards, smoke,
  diff check, and final status were assigned to the executor closure step.

Behavior preserved:

- No production planner/gate/policy/runtime integration.
- No rollout-review schema integration.
- No generated run artifacts.
- No default payload capacity, official bucket geometry, material density,
  cycle time, official T1 defaults, pass/fail, top-k/action selection, eval
  success, or planner success semantics.

## 2026-07-02: Phase 4B Planner Acceptance

Planner acceptance status:

- Accepted as Phase 4B offline effect-summary / payload-proxy evidence.
- Accepted-slice count since the latest recorded deep reflection is now `2/3`.
- No deep reflection is required for this acceptance.

Planner-side verification:

- Re-read the new effect-summary owner, focused tests, and changed
  plan/training/log documentation.
- Re-ran the related candidate/effect/target bundle:
  `tests/test_terrain_candidate_effect_summary.py`,
  `tests/test_terrain_candidate_effect_model.py`,
  `tests/test_terrain_candidate_scoring.py`,
  `tests/test_terrain_candidate_evidence.py`,
  `tests/test_terrain_candidate_generation.py`, target projection/report/metric
  tests, terrain residual metric tests, and rollout review tests; result:
  `68 passed`.
- Re-ran compile checks for the new effect-summary owner and related
  candidate/target owners and tests; result: passed.
- Re-ran changed-doc guard, docs inventory guard, architecture contract guard,
  and whitespace diff check; result: passed.
- Recomputed the current-run effect-summary smoke read-only; results directory
  file count remained `10 -> 10`, all `24` effect records were `present`, and
  the payload proxy / outside-target / overdig summary values matched the
  executor packet.

Acceptance rationale:

- The slice adds a focused offline owner for summarizing Phase 4A effect records
  and explicit payload-capacity proxy evidence.
- It preserves caller-supplied order, separates diagnostic rankings from action
  selection, and keeps payload capacity as an explicit smoke/report input.
- It does not introduce production planner integration, rollout-review schema
  changes, official geometry/capacity defaults, top-k selection, pass/fail, eval
  success, or planner success semantics.

Next bounded target:

- Phase 4C should close the remaining Phase 4 entry/exit expected-delta gap:
  add explicit entry/exit path evidence for the offline geometric effect model
  without making entry/exit defaults, production planner behavior, calibrated
  physics, or action-selection semantics.
- Keep the work focused on explicit inputs and read-only current-run smoke
  evidence. Do not infer official cell size, bucket geometry, payload capacity,
  material density, cycle time, or ACT capability from the current run.

## 2026-07-02: Phase 4C Executor Entry/Exit Effect Packet

Target lock observed:

- cwd `/home/pingfan/PACT/excavator_testbed`.
- Branch/status `## tx/oracle-terrain-residual-planner-v0...origin/tx/v2_6-llm-planner [ahead 29]`.
- HEAD `1ba980863c458779f7ed4fec3b2a8b9beb812381`.
- Worktree clean before edits.

Scope:

- Phase 4C: explicit entry/exit swept-footprint expected-delta evidence.
- Accepted-slice count carried in: `2/3`; executor does not write planner
  reflection.

Boundary decision:

- Existing `testbed.eval.terrain_candidate_effect_model` owns the public
  geometric-effect surface, but adding the entry/exit implementation there would
  push that file over the repository large-file policy threshold.
- Phase 4C therefore keeps a thin public re-export at
  `build_entry_exit_swept_footprint_effect()` and places the focused entry/exit
  algorithm in `testbed.eval.terrain_candidate_entry_exit_effect`.
- No rollout-review schema, production planner, target metric, projection,
  report, candidate generation, candidate evidence, candidate scoring, or
  effect-summary behavior was changed.

TDD red:

- Added focused `entry_exit` tests first.
- `python -m pytest -q tests/test_terrain_candidate_effect_model.py -k "entry_exit"`
  failed before implementation with `ImportError: cannot import name
  'build_entry_exit_swept_footprint_effect'`.

Implementation:

- Added public
  `testbed.eval.terrain_candidate_effect_model.build_entry_exit_swept_footprint_effect()`
  backed by focused owner `testbed.eval.terrain_candidate_entry_exit_effect`.
- Inputs are explicit: candidate, row-major removed/target depth grids, target
  and valid masks, grid shape, `cell_size_m`, `bucket_width_m`,
  `entry_cell_index`, `exit_cell_index`, and `target_penetration_depth_m`.
- Entry and exit cells must be valid row-major valid cells and must differ.
- The model is `entry_exit_centerline_segment_approximation`: candidate
  direction is preserved as evidence, but the swept centerline is the explicit
  segment from entry cell center to exit cell center.
- Output includes `entry_exit_path`, footprint cell sets, row-major expected
  delta grid, summary depth/volume metrics, validation errors, and provenance.
- Statuses implemented include `present`, `invalid_candidate`,
  `invalid_grid_shape`, `invalid_grid_lengths`, `invalid_mask_values`,
  `invalid_depth_values`, `invalid_geometry`, `invalid_entry_exit`, and
  `no_valid_footprint_cells`.

Current-run smoke:

- Recomputed baseline/candidates/evidence/scoring read-only from
  `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results/rollouts/rollout_000.jsonl`.
- Results directory file count remained `10 -> 10`.
- Baseline status `present`; candidate generation status `present`; candidate
  count `24`; scoring status `present`.
- Diagnostic best candidate remained `cut_candidate_000009`, candidate depth
  `0.191985052079`.
- Entry/exit smoke used explicit non-official `entry_cell_index=0`,
  `exit_cell_index=4`, `cell_size_m=0.25`, `bucket_width_m=0.25`, and
  `target_penetration_depth_m=0.191985052079`.
- Entry/exit effect status `present`; segment length `0.5`; footprint cells
  `[0, 2, 4]`; validation errors `[]`.
- Expected removed depth sum / volume: `0.575955156237` /
  `0.035997197265`.
- Target removed delta sum / volume: `0.383970104158` / `0.02399813151`.
- Outside-target delta sum / volume: `0.191985052079` / `0.011999065755`.
- Overdig delta sum / volume: `0.201641567051` / `0.012602597941`.

Documentation changed:

- `docs/training_setup.md` documents the entry/exit effect contract, explicit
  geometry / penetration inputs, segment approximation, statuses, provenance,
  and non-goals.
- `docs/oracle_terrain_residual_planner_v0_plan.md` marks the Phase 4
  entry/exit expected-delta checklist item complete and records Phase 4C smoke
  facts.
- Calibrated effect/capability model, production integration, default geometry
  / capacity / entry-exit, action selection, pass/fail, eval success, and
  planner success remain out of scope.

Verification:

- Focused green, related bundle, compile checks, doc guards, architecture
  guards, smoke, diff check, and final status were assigned to the executor
  closure step.

## 2026-07-02: Phase 4C Planner Acceptance And Deep Reflection

Planner acceptance status:

- Accepted as Phase 4C explicit entry/exit swept-footprint expected-delta
  evidence.
- Accepted-slice count since the latest recorded deep reflection is now `3/3`.
- Deep reflection was run after this acceptance, as required.

Planner-side verification:

- Re-read the focused entry/exit owner, the thin public re-export, focused
  tests, and changed plan/training/log documentation.
- Re-ran the related candidate/effect/target bundle:
  `tests/test_terrain_candidate_effect_model.py`,
  `tests/test_terrain_candidate_effect_summary.py`,
  `tests/test_terrain_candidate_scoring.py`,
  `tests/test_terrain_candidate_evidence.py`,
  `tests/test_terrain_candidate_generation.py`, target projection/report/metric
  tests, terrain residual metric tests, and rollout review tests; result:
  `71 passed`.
- Re-ran compile checks for the entry/exit owner, effect facade, related
  candidate/target owners, and tests; result: passed.
- Re-ran changed-doc guard, docs inventory guard, architecture contract guard,
  and whitespace diff check; result: passed.
- Recomputed the current-run entry/exit smoke read-only; results directory file
  count remained `10 -> 10`, best diagnostic candidate remained
  `cut_candidate_000009`, segment length was `0.5`, footprint cells were
  `[0, 2, 4]`, and summary metrics matched the executor packet.
- Checked file lengths after the split: `terrain_candidate_effect_model.py`
  has `686` lines and `terrain_candidate_entry_exit_effect.py` has `754` lines.

Acceptance rationale:

- The slice closes the remaining Phase 4 entry/exit expected-delta implementation
  item while preserving explicit-input-only semantics.
- The implementation was correctly split into a focused entry/exit owner with a
  thin public re-export from the existing effect model surface, avoiding a large
  mixed-responsibility effect-model file.
- It does not introduce production planner integration, rollout-review schema
  changes, official geometry/capacity/entry-exit defaults, calibrated physics,
  ACT capability, top-k selection, pass/fail, eval success, or planner success
  semantics.

Deep reflection against reference base:

- Alignment verdict: aligned. The last three accepted slices created the
  Phase 4 effect-model evidence layer requested by the plan without promoting it
  to runtime behavior.
- Reference base used: AGENTS responsibility rules, the Oracle Terrain Residual
  Planner v0 plan, the closed-loop terrain conclusion/profile/log docs,
  `docs/training_setup.md`, the current eval owners/tests, and the explicit
  non-official current-run smoke inputs.
- Progress verdict: substantive. The loop added three focused eval owners or
  focused owner extensions: geometric effect kernel, effect summary / payload
  proxy, and entry/exit effect evidence. These are not process-only callbacks.
- Scope verdict: controlled. No production planner/gate/policy/runtime path,
  rollout-review schema, config, dependency, branch/upstream, or generated
  run artifact was changed.
- Boundary verdict: acceptable. The entry/exit implementation was split out
  before the effect facade crossed the large-file threshold, and public imports
  remain stable through a thin re-export.
- Evidence verdict: useful but still offline. Current-run smoke confirms the
  helpers compose over the existing rollout facts, but it does not prove that a
  residual planner using the heuristic effect model beats the current planner.
- Known gaps: no official cell size, bucket geometry, entry/exit default,
  payload capacity, material density, cycle time, calibrated bucket physics,
  ACT capability model, gold-sample calibration, or Phase 6 closed-loop baseline
  comparison.
- Efficiency verdict: continue, but move to data evidence. More heuristic
  helpers would add diminishing value until gold-sample availability and schema
  are made explicit.
- Accepted-slice count resets to `0/3` after this deep reflection.

Phase 4 closure:

- Phase 4 is closed as an offline heuristic effect evidence milestone.
- This closure does not satisfy the Phase 4 performance standard that residual
  planner + heuristic effect model must outperform current planner in offline or
  simulation closed loop. That proof remains a Phase 6 baseline-comparison
  requirement.

Next bounded target:

- Phase 5A: build a gold-sample calibration inventory / schema evidence helper
  or report.
- The next slice should first identify available candidate gold/calibration
  sources, required fields, episode split keys, usable sample counts, and missing
  provenance. It should not fit a calibrated model yet and should not infer
  official sample semantics from filenames alone.

## 2026-07-02: Phase 5A Executor Calibration Inventory Packet

Target lock observed:

- cwd `/home/pingfan/PACT/excavator_testbed`.
- Branch/status `## tx/oracle-terrain-residual-planner-v0...origin/tx/v2_6-llm-planner [ahead 30]`.
- HEAD `c1d92faaf7a6c743c0964d036cfcb33bd73b8299`.
- Worktree clean before edits.

Scope:

- Phase 5A: gold-sample calibration inventory / schema evidence.
- Accepted-slice count carried in: `0/3`; executor does not write planner
  reflection.

Boundary decision:

- No existing small eval owner owned calibration source inventory or schema
  evidence.
- Added focused owner `testbed.eval.terrain_calibration_inventory`.
- Did not modify rollout review, production planner, target metrics,
  target projection/report, candidate generation/evidence/scoring, effect
  model, effect summary, or runtime behavior.

TDD red:

- Added `tests/test_terrain_calibration_inventory.py` before production code.
- `python -m pytest -q tests/test_terrain_calibration_inventory.py` failed
  before implementation with `ModuleNotFoundError: No module named
  'testbed.eval.terrain_calibration_inventory'`.

Implementation:

- Added
  `build_gold_sample_calibration_inventory(source_paths, *, required_fields,
  episode_split_key_candidates,
  profile='explicit_gold_sample_calibration_inventory')`.
- The helper is offline-only inventory evidence, not a trainer and not a
  calibrated effect/capability model.
- Inputs are explicit source paths, explicit required fields, and explicit
  split-key candidates.
- Directories are recursively walked only under the explicit root paths supplied
  by the caller.
- Supported record sources are JSONL object records and JSON list-of-object
  records.
- JSON metadata dicts are reported as metadata documents, not calibration
  records.
- Unsupported files and parser errors are preserved as source-level facts.
- A usable record requires all explicit required fields and at least one
  explicit split key.
- Top-level output reports schema/source/status/offline/profile, source counts,
  record counts, usable record count, source summaries, field summary, split
  summary, validation errors, and missing provenance.
- Statuses implemented: `present`, `no_sources`, `invalid_source_paths`,
  `invalid_required_fields`, `invalid_split_keys`, and
  `no_supported_sources`.

Current-repo smoke:

- Explicit source roots checked:
  `runs/calibration/v2_3_reachability_live` and
  `runs/jobs/yulong_v2_4_5_surface_depth_replay_train_eval_20260523/frame_audit`.
- File counts remained `9 -> 9` and `17 -> 17`; no files were written under
  `runs`.
- Explicit required fields used:
  `candidate_id`, `expected_removed_volume_m3`,
  `target_removed_volume_m3`, `outside_target_removed_volume_m3`,
  `overdig_volume_delta_m3`, `payload_volume_m3`, `success`,
  `overdig_event`, `low_payload_event`.
- Explicit split-key candidates used: `episode_id`, `rollout_id`, `run_id`.
- Inventory status `present`.
- Source count `26`; supported / unsupported source count `9` / `17`.
- Source status counts: metadata documents `5`, present record sources `4`,
  unsupported sources `17`.
- Total record count `14639`; usable record count `0`.
- Detected split keys `[]`; records with any split key `0`; distinct split
  group counts were `0` for `episode_id`, `rollout_id`, and `run_id`.
- Missing required field counts were `14639` for every explicit required field.
- Parser error sources `[]`.

Documentation changed:

- `docs/training_setup.md` documents the calibration inventory helper,
  explicit inputs, supported file kinds, usable-record rule, statuses, parser
  facts, missing provenance, and non-goals.
- `docs/oracle_terrain_residual_planner_v0_plan.md` marks only the Phase 5A
  inventory/schema-evidence item complete and records current smoke facts.
- Model calibration, uncertainty, capability filter fitting, official sample
  schema, official split semantics, labels, pass/fail, eval success, planner
  success, and production integration remain incomplete/out of scope.

Verification:

- Focused green, related bundle, compile checks, doc guards, architecture
  guards, smoke, diff check, and final status were assigned to the executor
  closure step.

## 2026-07-02: Phase 5A Planner Acceptance

Planner acceptance status:

- Accepted as Phase 5A gold-sample calibration inventory / schema evidence.
- Accepted-slice count since the latest recorded deep reflection is now `1/3`.
- No deep reflection is required for this acceptance.

Planner-side verification:

- Re-read the new calibration inventory owner, focused tests, and changed
  plan/training/log documentation.
- Re-ran the related calibration/candidate/effect/target bundle:
  `tests/test_terrain_calibration_inventory.py`,
  `tests/test_terrain_candidate_effect_model.py`,
  `tests/test_terrain_candidate_effect_summary.py`,
  `tests/test_terrain_candidate_scoring.py`,
  `tests/test_terrain_candidate_evidence.py`,
  `tests/test_terrain_candidate_generation.py`, target projection/report/metric
  tests, terrain residual metric tests, and rollout review tests; result:
  `76 passed`.
- Re-ran compile checks for the new inventory owner and related eval owners and
  tests; result: passed.
- Re-ran changed-doc guard, docs inventory guard, architecture contract guard,
  and whitespace diff check; result: passed.
- Recomputed the current-repo inventory smoke read-only; inspected directory
  file counts remained `9 -> 9` and `17 -> 17`, inventory status was `present`,
  total records were `14639`, usable records were `0`, and no split keys were
  detected for the explicit candidates `episode_id`, `rollout_id`, and `run_id`.
- Planner-side source-field spot check found the inspected JSONL records are
  reachability/live telemetry shaped: top observed fields include `t`,
  `step_id`, `action`, `qpos`, `qvel`, `mass_in_bucket_kg`,
  `excavated_mass_kg`, `soil_grid_mass_kg`, `label`, and `source_id`.

Acceptance rationale:

- The slice correctly blocks premature calibrated modeling by proving that the
  inspected sources do not satisfy the explicit future effect/capability
  calibration schema.
- It records parser and unsupported-source facts without inventing labels,
  official sample schema, official split semantics, pass/fail, eval success, or
  planner success.
- It does not change runtime behavior, rollout-review schema, production
  planner paths, config, dependencies, or run artifacts.

Next bounded target:

- Phase 5B should make the source-schema gap more actionable by adding an
  observed field catalog / required-field gap matrix for the explicit
  calibration sources.
- It should remain inventory/schema evidence only: no model fitting, no label
  inference, no official required fields, no generated run artifacts, and no
  production planner integration.

## 2026-07-02: Phase 5B Executor Observed Field Catalog Packet

Target lock observed:

- cwd `/home/pingfan/PACT/excavator_testbed`.
- Branch/status `## tx/oracle-terrain-residual-planner-v0...origin/tx/v2_6-llm-planner [ahead 31]`.
- HEAD `7a3f1ca5a7f3139e57e6e285a3779be5edd5b7e3`.
- Worktree clean before edits.

Scope:

- Phase 5B: observed calibration source field catalog / required-field gap
  matrix.
- Accepted-slice count carried in: `1/3`; executor does not write planner
  reflection.

Boundary decision:

- Existing owner `testbed.eval.terrain_calibration_inventory` already owns
  calibration source inventory and schema evidence.
- Extended that owner rather than creating a new module; the owner remained
  under the large-file threshold and no model-fitting responsibility was added.

TDD red:

- Added focused assertions for `observed_field_catalog` and
  `schema_gap_summary` before production code.
- `python -m pytest -q tests/test_terrain_calibration_inventory.py` failed
  before implementation with `KeyError: 'observed_field_catalog'`.

Implementation:

- Preserved the existing `build_gold_sample_calibration_inventory(...)`
  contract and statuses.
- Added deterministic `observed_field_catalog` with total observed field count,
  stable `field_ascending` sort order, and per-field record presence counts for
  supported JSON/JSONL object records.
- Added deterministic `schema_gap_summary` with required fields absent from all
  records, partially present, present in all records, split-key candidates
  absent/present, total/usable record counts, missing-required-field record
  count, records with any split key, and usable-record implication.
- No alias inference, label inference, official required fields, pass/fail,
  eval success, planner success, generated run artifacts, or production
  integration were introduced.

Current-repo smoke:

- Explicit source roots checked:
  `runs/calibration/v2_3_reachability_live` and
  `runs/jobs/yulong_v2_4_5_surface_depth_replay_train_eval_20260523/frame_audit`.
- File counts remained `9 -> 9` and `17 -> 17`; no files were written under
  `runs`.
- Inventory status `present`; source count `26`; supported / unsupported source
  count `9` / `17`; total records `14639`; usable records `0`.
- Observed field count `19`.
- Top observed fields by record count include `action`,
  `bucket_tip_depth_plane_m`, `bucket_tip_depth_surface_m`, `bucket_tip_x_m`,
  `bucket_tip_y_m`, `bucket_tip_z_m`, `excavated_mass_kg`,
  `mass_in_bucket_kg`, `qpos`, `qvel`, `soil_grid_mass_kg`, `step_id`, `t`,
  `target_hard_collision_count`, and `warnings`, each present in `14639`
  records.
- `label` appeared in `11639` records and `source_id` appeared in `6371`
  records, recorded only as raw observed fields.
- All explicit future calibration required fields were absent from all `14639`
  records.
- Split-key candidates `episode_id`, `rollout_id`, and `run_id` were absent
  from all records.
- `schema_gap_summary.usable_record_implication` was
  `no_usable_records_for_explicit_required_fields_and_split_keys`.

Documentation changed:

- `docs/training_setup.md` documents observed field catalog and schema gap
  summary semantics, explicit-input-only behavior, stable sorting, and
  no-inference boundary.
- `docs/oracle_terrain_residual_planner_v0_plan.md` marks only the Phase 5B
  observed-field/gap evidence item complete and keeps calibrated model,
  capability model, official schema, and production integration incomplete.

## 2026-07-02: Phase 5B Planner Acceptance

Planner acceptance status:

- Accepted as Phase 5B observed calibration source-field catalog / schema-gap
  evidence.
- Accepted-slice count since the latest recorded deep reflection is now `2/3`.
- No deep reflection is required for this acceptance.

Planner-side audit:

- Rechecked target lock in `/home/pingfan/PACT/excavator_testbed`: branch
  `tx/oracle-terrain-residual-planner-v0` was ahead `31`, HEAD
  `7a3f1ca5a7f3139e57e6e285a3779be5edd5b7e3`, with only the five expected
  Phase 5B files modified.
- Re-read the changed calibration inventory owner, focused tests, and changed
  plan/training/log documentation.
- Confirmed the implementation stayed in the existing focused inventory owner;
  `testbed/eval/terrain_calibration_inventory.py` remained below the large-file
  threshold at `598` lines.
- Confirmed the new catalog records raw top-level field presence only and does
  not infer aliases from telemetry fields such as `label`, `source_id`,
  `mass_in_bucket_kg`, or `excavated_mass_kg`.

Planner-side verification:

- Re-ran the related calibration/candidate/effect/target bundle:
  `tests/test_terrain_calibration_inventory.py`,
  `tests/test_terrain_candidate_effect_model.py`,
  `tests/test_terrain_candidate_effect_summary.py`,
  `tests/test_terrain_candidate_scoring.py`,
  `tests/test_terrain_candidate_evidence.py`,
  `tests/test_terrain_candidate_generation.py`, target projection/report/metric
  tests, terrain residual metric tests, and rollout review tests; result:
  `76 passed`.
- Re-ran compile checks for the inventory owner and related eval owners and
  tests; result: passed.
- Re-ran changed-doc guard, docs inventory guard, architecture contract guard,
  and whitespace diff check; result: passed.
- Recomputed the current-repo inventory smoke read-only; inspected directory
  file counts remained `9 -> 9` and `17 -> 17`, inventory status was `present`,
  total records were `14639`, usable records were `0`, observed field count was
  `19`, and all explicit future calibration required fields and split-key
  candidates were absent from the supported records.

Acceptance rationale:

- The slice makes the Phase 5A blocker actionable: the repo now records both
  the raw fields that actually exist and the explicit future schema fields that
  are missing.
- It preserves the correct boundary for Phase 5: inventory/schema evidence only,
  with no model fitting, fake labels, official schema, split semantics,
  pass/fail, eval success, planner success, generated artifacts, or production
  integration.
- The next decision should use these raw field facts to define a separate,
  explicit calibration extraction contract rather than silently mapping
  telemetry fields to labels.

Next bounded target:

- Phase 5C should add an explicit calibration-record extraction/spec proposal
  layer that remains offline and inactive by default.
- It should consume the observed field catalog as evidence, but any mapping from
  raw telemetry fields to future calibration labels must be explicit,
  caller-provided, and documented as provisional unless the user later promotes
  it into an official schema.

## 2026-07-02: Phase 5C Executor Explicit Extraction Packet

Target lock observed:

- cwd `/home/pingfan/PACT/excavator_testbed`.
- Branch/status `## tx/oracle-terrain-residual-planner-v0...origin/tx/v2_6-llm-planner [ahead 32]`.
- HEAD `0bd39a0000fc7c506b3c7c6f98a78711fe3256fd`.
- Worktree clean before edits.

Scope:

- Phase 5C: explicit calibration extraction spec / mapping feasibility
  evidence.
- Accepted-slice count carried in: `2/3`; executor does not write planner
  reflection.

Boundary decision:

- `testbed.eval.terrain_calibration_inventory` remains inventory/schema-gap
  owner.
- Added focused owner `testbed.eval.terrain_calibration_extraction` because
  explicit caller-provided mapping and extraction are a distinct evidence
  responsibility from inventory.

TDD red:

- Added `tests/test_terrain_calibration_extraction.py` before production code.
- `python -m pytest -q tests/test_terrain_calibration_extraction.py` failed
  before implementation with `ModuleNotFoundError: No module named
  'testbed.eval.terrain_calibration_extraction'`.

Implementation:

- Added
  `build_explicit_calibration_record_extraction(source_paths, *,
  field_mapping, required_output_fields, episode_split_key_candidates,
  profile='explicit_calibration_record_extraction')`.
- The helper is offline-only extraction evidence, not model fitting and not an
  official sample schema.
- Inputs are explicit source paths, caller-provided output-to-raw
  `field_mapping`, explicit required output fields, and explicit split-key
  candidates.
- Supported record sources are JSONL object records and JSON list-of-object
  records; JSON metadata dicts are reported as metadata documents, not
  extracted records.
- Extracted records contain only mapped output fields; raw fields are not
  carried.
- Usable extracted records require all explicit required output fields and at
  least one explicit split key.
- Top-level output reports schema/source/status/offline/profile, source counts,
  mapping summary, extracted record counts, missing output-field summary, split
  summary, bounded sample record shape evidence, validation errors, and missing
  provenance.
- Statuses implemented: `present`, `no_sources`, `invalid_source_paths`,
  `invalid_field_mapping`, `invalid_required_output_fields`,
  `invalid_split_keys`, `no_supported_sources`, and `no_records`.

Current-repo smoke:

- Explicit source roots checked:
  `runs/calibration/v2_3_reachability_live` and
  `runs/jobs/yulong_v2_4_5_surface_depth_replay_train_eval_20260523/frame_audit`.
- File counts remained `9 -> 9` and `17 -> 17`; no files were written under
  `runs`.
- Provisional telemetry-only mapping used:
  `telemetry_time_s <- t`, `telemetry_step_id <- step_id`,
  `telemetry_label <- label`, `telemetry_source_id <- source_id`,
  `telemetry_mass_in_bucket_kg <- mass_in_bucket_kg`,
  `telemetry_excavated_mass_kg <- excavated_mass_kg`, and
  `telemetry_soil_grid_mass_kg <- soil_grid_mass_kg`.
- Provisional extraction status `present`; source count `26`; supported /
  unsupported source count `9` / `17`; total source records `14639`; extracted
  records `14639`; usable extracted records `3371`.
- Provisional required output missing counts: `telemetry_time_s=0`,
  `telemetry_step_id=0`, `telemetry_label=3000`,
  `telemetry_mass_in_bucket_kg=0`, `telemetry_excavated_mass_kg=0`,
  `telemetry_soil_grid_mass_kg=0`.
- `telemetry_source_id` was detected in `6371` records with `1` distinct group.
- Negative smoke with explicit future calibration identity mapping still
  produced `usable_extracted_record_count=0`; all nine Phase 5A future required
  fields were missing from all `14639` records, and `episode_id`, `rollout_id`,
  and `run_id` were not detected.

Documentation changed:

- `docs/training_setup.md` documents the explicit extraction helper, explicit
  mapping inputs, provisional mapping boundary, no-inference rule, statuses,
  and missing provenance.
- `docs/oracle_terrain_residual_planner_v0_plan.md` marks only the Phase 5C
  explicit extraction/mapping feasibility evidence item complete and keeps
  statistical calibration, uncertainty, capability filter, and episode-split
  evaluation incomplete.

## 2026-07-02: Phase 5C Planner Acceptance And Deep Reflection

Planner acceptance status:

- Accepted as Phase 5C explicit calibration extraction / mapping feasibility
  evidence.
- Accepted-slice count since the latest recorded deep reflection is now `3/3`.
- Deep reflection was run after this acceptance, as required.

Planner-side audit:

- Rechecked target lock in `/home/pingfan/PACT/excavator_testbed`: branch
  `tx/oracle-terrain-residual-planner-v0` was ahead `32`, HEAD
  `0bd39a0000fc7c506b3c7c6f98a78711fe3256fd`, with only the expected Phase 5C
  docs and new extraction owner/test modified or untracked.
- Re-read the new extraction owner, focused tests, and changed
  plan/training/log documentation.
- Confirmed `testbed/eval/terrain_calibration_inventory.py` remains inventory /
  schema-gap owner, while `testbed/eval/terrain_calibration_extraction.py`
  owns explicit caller-provided mapping/extraction evidence.
- Confirmed the extraction owner is below the large-file threshold at `625`
  lines; the inventory owner remains `598` lines.
- Confirmed extracted records contain only mapped output fields, and the tests
  prove unmapped raw fields such as `label`, `source_id`, and
  `mass_in_bucket_kg` are not inferred or carried.

Planner-side verification:

- Re-ran the related calibration/candidate/effect/target bundle:
  `tests/test_terrain_calibration_extraction.py`,
  `tests/test_terrain_calibration_inventory.py`,
  `tests/test_terrain_candidate_effect_model.py`,
  `tests/test_terrain_candidate_effect_summary.py`,
  `tests/test_terrain_candidate_scoring.py`,
  `tests/test_terrain_candidate_evidence.py`,
  `tests/test_terrain_candidate_generation.py`, target projection/report/metric
  tests, terrain residual metric tests, and rollout review tests; result:
  `81 passed`.
- Re-ran compile checks for the new extraction owner, inventory owner, related
  eval owners, and tests; result: passed.
- Recomputed the current-repo extraction smoke read-only; inspected directory
  file counts remained `9 -> 9` and `17 -> 17`.
- Provisional telemetry mapping produced status `present`, extracted records
  `14639`, usable extracted records `3371`, and `raw_fields_carried=False`.
- Negative future-schema identity mapping produced status `present`, extracted
  records `14639`, usable extracted records `0`, and no detected
  `episode_id`, `rollout_id`, or `run_id`.

Acceptance rationale:

- The slice cleanly separates two facts: provisional telemetry extraction is
  mechanically possible under an explicit mapping, while future calibration
  records remain unavailable under the explicit effect/capability schema.
- It does not silently promote telemetry fields into success, payload, split,
  pass/fail, eval success, planner success, or official calibration schema
  semantics.
- It does not change production planner behavior, rollout-review schema, run
  artifacts, config, dependencies, or branch/upstream state.

Deep reflection against reference base:

- Alignment verdict: aligned. Phase 5 now has inventory, raw-field catalog,
  schema-gap summary, and explicit extraction feasibility evidence without
  inventing gold labels or fitting a model from unsuitable records.
- Reference base used: AGENTS governance, the Oracle Terrain Residual Planner
  v0 plan, closed-loop log, training setup, current calibration inventory /
  extraction owners and tests, and the explicit no-inference boundary from the
  user-confirmed workflow.
- Progress verdict: useful and substantive. The last three accepted slices
  added code-level evidence owners and tests, not just process documentation.
- Scope verdict: controlled. No production planner/gate/policy/runtime path,
  rollout-review schema, config, dependency, generated run artifact, official
  schema, label semantics, or split semantics was introduced.
- Verification verdict: sufficient for evidence readiness. Tests and smokes
  prove source availability, raw-field presence, explicit extraction behavior,
  and the blocker for future calibration labels.
- Blocker verdict: statistical calibration is not responsibly executable from
  the currently inspected artifacts. The current data has telemetry fields and
  provisional labels, but no confirmed target fields for effect/capability
  model training.
- Efficiency verdict: stop adding calibration helper layers for now. More
  Phase 5 code would mostly formalize missing data rather than unlock model
  fitting.
- Accepted-slice count resets to `0/3` after this deep reflection.

Phase 5 closure:

- Phase 5 is closed as a calibration evidence / schema-readiness milestone.
- It is not closed as a calibrated effect/capability model milestone.
- Statistical calibration, uncertainty, capability filter, and episode-split
  evaluation remain deferred until official schema/labels/split semantics and
  usable gold samples exist.

Next bounded target:

- Phase 6A should start a heuristic-only offline baseline-comparison scaffold.
- The scaffold should compare current-run/current-planner evidence against the
  existing heuristic residual candidate/effect pipeline where possible, while
  marking the calibrated-model branch `not_evaluated` because Phase 5 found no
  usable gold samples for that path.
- It must remain offline/report evidence only: no production planner
  integration, no action selection promoted to runtime, no official success
  semantics, no generated run artifacts unless explicitly scoped and
  non-destructive, and no calibrated-model fallback invented from telemetry.
