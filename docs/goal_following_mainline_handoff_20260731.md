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

The offline benchmark and its fixed corpus contract are implemented before any
ACT change. The corpus loader was checked against the current gold dig manifest:
433 windows were accepted, 374 assigned to train, and 59 assigned to held-out
sources 33/34; seven silver dig windows were excluded. The current rollout
contract accepts nine completed evaluation segments and one censored tenth
handoff, and makes the censored record ineligible for ACT tracking or predictor
training.

- Expert scope: 433 dig windows, split by source into 374 train and 59 held-out
  windows. Do not randomly split primitives.
- The 374/59 split is a source-partition contract, not proof that a complete
  continuous-goal label exists. After the real-data audit, expert
  `predictor_training_label` and `predictor_evaluation_label` remain false
  until an approved pseudo-goal contract and trusted builder exist.
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

The benchmark has a checked-in synthetic/offline golden report whose canonical
JSON SHA is locked by test. That fixture is not real rollout evidence. A real
four-way decision has not been emitted yet because the 433 expert cycles and
nine rollout cycles have not yet been assembled with complete reference,
actual, forward-kinematics, terrain, and effect arrays. Until that evidence
artifact exists, ACT remains frozen.

## Predictor v1 contract

The predictor contract, trainer, calibration, persistence, and planner-facing
offline bridge are implemented. They are not enabled by any default
configuration and are not connected to live execution. No real predictor
artifact has been trained from the 433-window corpus because that corpus does
not contain authoritative planner-goal intent; the exact blocker is recorded
below.

One centralized `terrain_signature_v1` is assembled from schema field names. It
is the 89-dimensional v2.3-compatible terrain base and excludes the v2.4
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

Artifacts are written to a new directory only, with five member checkpoints,
file hashes, a canonical manifest hash, source-fold ownership, normalization,
OOD, conformal calibration, and code lineage. Strict loading revalidates both
the hashes and the fixed model semantics. Historical v1 inputs remain
readable, but inference requires v2 and there is no nearest-trajectory
fallback.

The fixed calibration inventory is exactly 59 windows: 29 from source 33 and
30 from source 34. A smaller, larger, or differently distributed calibration
set is rejected rather than mislabeled as a 95% guarantee. Each ensemble
member owns a normalization fitted only from that member's training sources;
its validation sources do not enter preprocessing. The exported normalization
lineage binds the full-training OOD transform and all five member transforms.
The predictor code SHA is computed from the fixed source-file inventory and is
rechecked during construction, prediction, save, and load; callers cannot
substitute an arbitrary 64-character value.

The planner-facing bridge builds v2 input from the actual handoff state and
validates every output field again before exposing a reference to the
independent 3D sweep evaluator. A missing provider, OOD sample, missing
calibration, malformed path/bounds, first-row drift, non-finite output, or
lineage mismatch returns a blocker. The bridge requires an exact static
lineage inventory for normalization, checkpoint, calibration, and predictor
code; missing, partial, or extra lineage fields fail closed. This bridge is
offline-only and does not replace the frozen legacy entry point.

### Real training-label readiness

A read-only audit of all 433 gold dig windows found that qpos, qvel, the 89D
terrain state, and the expert path are structurally usable, but a complete
planner-issued `ContinuousCutGoal` cannot be reconstructed without inventing
semantics:

- no window contains a plan-side `selected_cell_id`; all 433 declare
  `planner_fields_status=missing_not_generated_by_replay`;
- `dominant_removed_depth_cell_id` is the hindsight cell with the largest
  observed removal, not the planned target cell;
- `operator_cut_payload_gain_kg` and `dig_outcome_payload_gain_kg` are the same
  measured outcome in all 433 windows, not a recorded payload intent;
- operator entry, exit, and depth describe the executed expert cut and were
  reconstructed after execution, not issued as a planner goal.

The outcome cell agrees with the handoff bucket cell for only 190 of 433
windows and with the operator-entry cell for only 180 of 433. Relabeling either
as `target_cell_id` would therefore be both lossy and semantically wrong. The
reference path alignment also needs an explicit contract: 161 paths start at
operator entry, while 272 start 1 to 76 steps after operator entry.

Consequently, this implementation does not create a pseudo-goal builder or a
real trained artifact. Training remains blocked until the project explicitly
defines an `expert_demonstration_goal` policy covering:

1. whether an executed expert corridor may serve as a pseudo-goal;
2. whether hindsight dominant-effect cell may serve as `target_cell_id`;
3. how measured payload/effect may be converted into intent;
4. whether the reference is the full dig window or the path after operator
   entry.

This is a data-semantics blocker, not a model-code blocker. Once approved, the
usable source lineage is:

- manifest SHA:
  `5bcdeff67845a329c154655bad5dc3c4afc62b541759188c407321f30802d8e0`;
- source split SHA:
  `cc2e1b95d0c6b7a2019344e5e8e23b65b11fcf0307785709c8e37de993dd7a40`;
- 374 training windows and 59 source-33/34 calibration windows;
- path lengths from 67 to 1730 samples, median 188.

## Safety, calibration, and ACT decision order

The mainline now contains fail-closed evidence evaluators for the 3D sweep,
effect-calibration support, ACT routing, and the four ordered promotion gates.
They validate evidence; they do not launch Unity, change a checkpoint, or
unlock a runtime by themselves.

The 3D sweep evaluator checks the nominal path and all 16 corners of the
four-joint error box at every node, adding adaptive interpolation between
nodes. Its Unity callback must return boom, stick, and bucket clearance against
all four walls, producing the complete 12 link-wall witness inventory.

The unchanged clearance condition is:

`conservative uncertainty-tube clearance - 0.01 m interpolation margin -
0.05 m ACT tracking margin >= 0.24 m`

Predictor uncertainty never replaces or reduces the 0.05 m ACT margin.

After predictor offline gates pass, controlled Unity data must still be
collected with frozen ACT. The effect gate keeps failures and negative samples,
rejects reset-group leakage, enforces planned-to-executed before
executed-to-effect, and requires at least 20 positive and 20 negative samples
across at least 3 reset groups per capability class. It also rejects fixed
expert medians, hindsight fields, and temporary-cell bindings.

- `reference_or_goal_primary`: repair goal/reference/support; keep ACT frozen.
- `effect_calibration_primary`: repair planned/effect calibration; keep ACT
  frozen.
- `act_tracking_primary`: retrain the existing goal-conditioned ACT using the
  strict source split. Add trajectory-conditioned ACT v1 only if held-out
  tracking remains outside the calibrated tube after retraining.
- Never hide ACT deviation by tightening an ad hoc planner threshold.

## Promotion gates

The evidence evaluator implements these gates strictly in order:

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

No E0/G1/W1 Unity evidence has been generated by this implementation task.
Therefore all runtime stages remain unexecuted, and the new evaluator must not
be described as a gate pass.

## Post-freeze contact semantics

The post-freeze contact change is implemented as the explicit opt-in mode
`allow_finite_bucket_contacts`. It is not part of the frozen default and no
checked-in production/default configuration enables it:

- ordinary, finite, bucket-only contact does not automatically fail;
- boom/stick/unknown-component contact, high force, non-finite telemetry,
  stuck state, timeout, and hard-bottom violations remain hard failures.

The mode is mutually exclusive with the historical diagnostic A/B and
observe-only markers. The adapter and runtime contract both reject mixed
mainline/diagnostic semantics. The default remains `interrupt`.

Request-local evaluation configuration may opt in only with:

```yaml
policy:
  box_emptying:
    safety:
      wall_first_touch_mode: allow_finite_bucket_contacts
      wall_contact_diagnostic_ab_enabled: false
      wall_contact_diagnostic_observe_only_enabled: false
```

This mode preserves the existing strict `<100000 N` finite-force condition.
It does not relax hard-bottom, stuck, timeout, neutral-stop, or unknown
component handling, and it does not by itself unlock any Unity or live gate.

## Implementation evidence

The exact implemented/unexecuted boundary, data-label blocker, and clean
worktree verification results are recorded in
`docs/goal_following_mainline_implementation_manifest_20260731.json`.
