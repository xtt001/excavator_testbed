# Goal-Following Mainline Handoff

## Frozen boundary

The terrain-residual recovery work is frozen as diagnostic evidence, not as a
production promotion. The latest bounded Unity attempt completed 9 of 10
required digs and 9 of 10 dumps, then timed out in return before the tenth dig.
It used one reset and one attempt, did not retry, wrote no training HDF5, did
not relax safety thresholds, and did not change production or default
configuration.

The failed final handoff is censored evidence. After the next-dig event was
latched, spatial entry-close and the depth/qpos return envelope did not overlap.
This evidence may be evaluated by the benchmark, but it must not be used as an
ACT tracking sample or as a predictor training label.

The exact-tuple execution library and historical goal-conditioned recovery
artifacts remain diagnostic-only. They must not be copied into the new runtime
as an episode binding, expert ID binding, nearest-trajectory fallback, or
temporary-cell patch.

## Git boundary

- Convergence branch: `codex/git-convergence-20260731`
- Freeze tag: `freeze/terrain-residual-pre-goal-following-20260731`
- Mainline branch: `codex/goal-following-mainline`
- Initial dirty-tree base:
  `ec6e47253968864aea26aca0571aff7c7f12cbe4`
- External recovery snapshot:
  `/data/pingfan/excavator_testbed_git_snapshots/20260731/`
- No remote push or upstream mutation is part of this handoff.

The freeze manifest is
`docs/terrain_residual_pre_goal_following_freeze_manifest_20260731.json`.
It owns the responsibility-commit list, snapshot checksums, nine-dig artifact
lineage, safety/default boundary, and offline validation record.

## Lint and test convergence

The final freeze commit also establishes a clean repository-wide lint baseline.
Ruff applied 448 safe mechanical fixes, followed by 28 explicit fixes for
pre-existing lint findings. The enabled rules and scan scope were not reduced.
The changes are limited to import ordering/removal, annotation modernization,
unambiguous local names, equivalent statement expansion, dead local removal,
and two stale undefined-name/export corrections. The complete offline suite was
rerun after these edits; no planner, training, rollout, replay, checkpoint, or
default semantics were intentionally changed.

The exact console command `pytest -q` is now reproducible because the repository
root is declared in the centralized pytest configuration. The detached
responsibility-commit checks use isolated clean worktrees. Five four-camera
workflow tests at the telemetry commit retain their existing skip reason when
the paired Unity checkout is unavailable; no new skip rule was added.

## First mainline deliverable: goal-following benchmark

Build the benchmark before training a predictor or changing ACT.

- Expert scope: 433 dig windows, split by source into 374 train and 59 held-out
  windows. Do not randomly split primitives.
- Rollout scope: the 9 completed dig segments from the frozen attempt are
  evaluation/domain-shift evidence only. The incomplete tenth cycle is a
  censored handoff.
- Per-cycle geometry: planned and actual entry, exit, direction, length,
  terrain-relative depth, and duration.
- Joint tracking: phase-normalized MAE, RMSE, p95, maximum, and endpoint error
  per joint; preserve raw-time errors and report DTW only as an auxiliary view.
- Worktool tracking: forward-kinematics 3D error with the locked 0.05 m ACT
  tracking margin shown separately from predictor uncertainty.
- Strata: first versus repeated dig, target region, remaining-depth bins derived
  from train only, train versus held-out, and rollout cycle.
- Expert comparison: use the complete continuous goal, actual handoff qpos/qvel,
  and terrain signature. Nearest expert trajectories are diagnostic only.

The benchmark may emit only:

1. `reference_or_goal_primary`
2. `act_tracking_primary`
3. `effect_calibration_primary`
4. `insufficient_evidence`

Only `act_tracking_primary` permits the ACT retraining route. Benchmark output
does not unlock live execution.

## Predictor v1 contract

Define one centralized `terrain_signature_v1` from schema field names. It is the
89-dimensional v2.3-compatible terrain base and excludes the v2.4
contact/hard-bottom suffix from learning input.

New artifacts use `continuous_goal_worktool_sweep_input_v2` with:

- actual handoff qpos4 and qvel4;
- the complete continuous goal;
- `terrain_signature_v1`;
- no episode ID, fixed expert ID, or temporary cell binding.

The selected v1 model is fixed:

- resample expert qpos by four-joint cumulative arc length to 64 progress
  points;
- represent each joint relative to handoff with a clamped cubic B-spline using
  12 control points;
- force the first path row and starting control point to zero offset;
- train five two-layer MLP members, 64 units per layer, seeds 0 through 4, with
  Huber loss;
- use source-grouped cross-validation and held-out sources 33/34 for conformal
  calibration;
- emit per-progress, per-joint 95% absolute-error bounds;
- derive the OOD threshold from standardized train-source feature distance and
  leave-one-source-out p99, with no nearest-trajectory fallback.

Required outputs include `path_progress[64]`, `qpos_path[64,4]`,
`qpos_abs_error_bound[64,4]`, `coverage_level`, `support_status`, `ood_score`,
and normalization/checkpoint/calibration/goal/code/path lineage SHA values.
The first qpos row must equal actual handoff qpos within `1e-6`. OOD, missing
calibration, non-finite output, or lineage drift fails closed.

## Safety, calibration, and ACT decision order

Unity must sweep the nominal path and all 16 corners of the four-joint error box
at every node, adding adaptive interpolation between nodes. It must validate
boom, stick, and bucket against all four walls, producing 12 link-wall
witnesses.

The unchanged clearance condition is:

`conservative uncertainty-tube clearance - 0.01 m interpolation margin -
0.05 m ACT tracking margin >= 0.24 m`

Predictor uncertainty never replaces or reduces the 0.05 m ACT margin.

After predictor offline gates pass, collect controlled Unity data with frozen
ACT. Keep failures and negative samples, isolate reset groups, fit
planned-to-executed before executed-to-effect, and require at least 20 positive
and 20 negative samples across at least 3 reset groups per capability class.

- `reference_or_goal_primary`: repair goal/reference/support; keep ACT frozen.
- `effect_calibration_primary`: repair planned/effect calibration; keep ACT
  frozen.
- `act_tracking_primary`: retrain the existing goal-conditioned ACT using the
  strict source split. Add trajectory-conditioned ACT v1 only if held-out
  tracking remains outside the calibrated tube after retraining.
- Never hide ACT deviation by tightening an ad hoc planner threshold.

## Promotion gates

Run gates strictly in order:

1. Offline E0/G1/W1 with real handoff state, full terrain signature, predictor,
   calibrated 95% bounds, and derived return envelope.
2. Unity 3D uncertainty sweep for all three goal classes and all 12 link-wall
   witnesses.
3. One no-retry bounded Unity execution each for E0, G1, and W1.
4. One reset, one attempt, no-retry G1 1x10 with 10 valid digs, 10 dumps, and 9
   handoffs.

Passing 1x10 creates promotion evidence only. Production/default behavior still
requires separate approval. This plan contains no real-machine run and no
remote push.

## Post-freeze contact semantics

The proposed contact change is a new, explicit mainline semantic change and is
not part of the frozen default:

- ordinary, finite, bucket-only contact does not automatically fail;
- boom/stick/unknown-component contact, high force, non-finite telemetry,
  stuck state, timeout, and hard-bottom violations remain hard failures.

Implement it with tests and documentation after the freeze branch is tagged.
