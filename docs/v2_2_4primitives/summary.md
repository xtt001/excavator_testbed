# V2.2 4-Primitives Smoke Report

Date: 2026-04-26
Branch: `fs/v2_1-dev-4primitives`

## Artifact

- Success video: [`rollout_000_success_3cycle.mp4`](rollout_000_success_3cycle.mp4)
- Full local rollout output: `runs/eval/agx_v2_2_4primitives_qvel_3cycle_smoke/`
- Earlier diagnostic failures were preserved locally as:
  - `runs/eval/agx_v2_2_4primitives_qvel_3cycle_smoke_strictmask_fail_2604261957/`
  - `runs/eval/agx_v2_2_4primitives_qvel_3cycle_smoke_hdist020_digdist020_fail_2604262004/`

## What Changed

- Built a V2.2 primitive dataset root with four sibling datasets:
  - `dig`: 64 episodes, len min/median/max `2 / 8 / 12`
  - `carry`: 64 episodes, len min/median/max `354 / 457 / 618`
  - `dump`: 64 episodes, len min/median/max `79 / 138.5 / 303`
  - `return`: 120 episodes, len min/median/max `175 / 298.5 / 757`
- Trained four ACT primitives for 500 epochs using `qpos + qvel`.
- Added `PrimitivePlannerACTPolicy`, which loads `dig/carry/dump/return` checkpoints and logs `skill_name`, `skill_switch_reason`, and checkpoint path.
- Kept low-level ACT inputs non-privileged. Unity target geometry is used only for scripted switching and diagnostics.

## Checkpoints

Checkpoint root: `/data/pingfan/excavator_testbed_runs/ckpts/v2_2_4primitives/`

| Primitive | Best epoch | Best val loss |
|---|---:|---:|
| dig | 435 | 0.1112 |
| carry | 495 | 0.2791 |
| dump | 475 | 0.2071 |
| return | 370 | 0.2885 |

The redundant periodic `policy_epoch_*` checkpoints were removed after training, saving about 46 GiB. `policy_best.ckpt`, `policy_latest.ckpt`, and `policy_last.ckpt` were kept.

## Smoke Result

Final smoke command:

```bash
conda run -n aloha python -m testbed.cli.eval \
  --config testbed/configs/eval_agx_v2_2_4primitives_qvel_3cycle_smoke.yaml
```

Outcome:

| Metric | Value |
|---|---:|
| success_rate | 1.0 |
| cycle1_success_rate | 1.0 |
| cycle2_success_rate | 1.0 |
| cycle3_success_rate | 1.0 |
| completed_transition_count | 2 |
| transition_timeout_count | 0 |
| final deposited mass | 5142.47 kg |
| final bucket mass | 0.0 kg |
| episode length | 2397 steps |
| rollout stop reason | `target_cycle_gate_terminal_hold_reached` |

Important switch points from the successful rollout:

| Step | Switch | Bucket mass | Deposited mass | Horizontal | Height above rim |
|---:|---|---:|---:|---:|---:|
| 594 | carry -> dump | 2243.7 kg | 45.0 kg | 0.148 m | 0.097 m |
| 1349 | carry -> dump | 2095.7 kg | 1769.4 kg | 0.159 m | 0.066 m |
| 2254 | carry -> dump | 2312.2 kg | 3018.4 kg | 0.129 m | 0.100 m |

This directly addresses the earlier cycle2 early-dump concern: dump was triggered by target-relative geometry while the bucket was horizontally close and still above the rim, not by fixed swing qpos.

## Debug Lessons

Two rollout failures were useful:

- Strict footprint-mask readiness missed the valid dump window. The bucket was already within about `0.20m` horizontally and above the rim, but `bucket_over_target_footprint_mask` flipped true only after the bucket had dropped below the rim. Fix: readiness now accepts `bucket_over_target_footprint_mask OR target_horizontal_distance_m <= 0.20m`, while still requiring height above rim and clearance.
- `dig -> carry` originally required `min_distance_to_dig_area_m >= 0.20`, which made cycle3 stay in `dig` even after loading. Fix: `dig -> carry` now switches once the bucket is loaded; leaving the dig area is carry's job.

## Remaining Risk

This is a good V2.2 smoke, not a production-clean model yet. The successful rollout still reports nonzero diagnostic quality issues (`avg_spill_before_target_count=235`, `avg_hard_target_collision_count=12`, `avg_quality_issue_count=604`). The next training pass should improve carry/dump smoothness and target clearance before treating this as a stable 2000-epoch baseline.

Recommended next step: train the same four primitives to 2000 epochs with the updated planner thresholds, then run a 5-rollout compare against the best V2.1 temporal-aggregation baseline.

## Safe-Dump Update

Date: 2026-04-27

- Recut `carry/dump` with safe pre-dump onset and no fallback to official mass-based `dump_start`.
- New root: `data/agx_v2_2_4primitives_safe_dump_260427`
- Counts: `dig=64`, `carry=27`, `dump=27`, `return=120`
- Dump QC: first 20 steps had `height_below_rim=0`, `clearance_loss=0`, `hard_collision_window_count=0`; full-window `near_collision_window_count=3`.
- Trained affected primitives only:
  - `carry_qvel_safe_dump_e500_260427`: best epoch `360`, val loss `0.2872`
  - `dump_qvel_safe_dump_e500_260427`: best epoch `400`, val loss `0.2691`
- A live smoke with `dump_ready_max_horizontal_distance_m=0.60` exposed a new mismatch: cycle2 stayed in `carry`, began curl-out around `horizontal ~= 0.79m`, spilled the bucket before `dump_ready`, then oscillated with empty bucket. The planner threshold is now `0.82m`, matching the safe dump onset max (`0.818m`) so the handoff happens before carry starts dumping.
- Success video: [`rollout_000_safe_dump_260427_success.mp4`](rollout_000_safe_dump_260427_success.mp4)
- Final safe-dump smoke:
  - `success_rate=1.0`, `cycle1/2/3_success_rate=1.0`
  - `completed_transition_count=2`, `transition_timeout_count=0`
  - `avg_final_success_signal=3740.48kg`, `avg_final_bucket_mass=0.0kg`
  - `avg_hard_target_collision_count=0`
  - Remaining quality debt: `avg_spill_before_target_count=227`, `avg_unsafe_target_distance_count=103`, `avg_quality_issue_count=336`
  - Key switches: cycle1 `carry->dump` at `horizontal=0.729m,height=0.668m`; cycle2 at `0.785m,0.666m`; cycle3 at `0.724m,0.662m`

## Carry Tail + Post-Dump Hold Update

Date: 2026-04-27

- Root: `data/agx_v2_2_4primitives_carrytrim120_leftboost_260427`
- Carry mix: `63` episodes = safe carry `27` + clean recorded carry `3 x 12`.
- Carry split: end at `min(dump_intent_start - 120, stable_curl_out_onset - 10)`.
  The `120` step trim covers ACT `chunk_size=100` plus a 20 step buffer, so the
  carry policy no longer supervises dump/curl-out tail actions.
- Carry QC: accepted safe carry `27`, accepted clean recorded carry `3`,
  `tail_stable_strong_curl_out_count=0`, carry bucket mass loss `0kg`.
- Carry checkpoint:
  `/data/pingfan/excavator_testbed_runs/ckpts/v2_2_4primitives/carry_qvel_carrytrim120_leftboost_e500_260427/policy_best.ckpt`
  - Best epoch `495`, val loss `0.1100`.
- Dump checkpoint reused:
  `/data/pingfan/excavator_testbed_runs/ckpts/v2_2_4primitives/dump_qvel_safe_dump_leftboost_e500_260427/policy_best.ckpt`
- Planner smoke config:
  - `dump_ready_max_horizontal_distance_m=0.60`
  - `dump_ready_min_height_above_rim_m=0.45`
  - `dump_done_hold_steps=30`

Reason for `dump_done_hold_steps=30`: ACT predicts 100-step chunks and temporal
aggregation blends future actions. With `dump_done_hold_steps=2`, cycle2 already
placed soil into the truck, but return took over while the bucket was still at
the bed edge and pulled roughly `370kg` back out. Holding dump for 30 steps lets
the dump policy finish the release/stabilization phase before return starts.

Current best live smoke:

- Output:
  `runs/eval/agx_v2_2_4primitives_carrytrim120_leftboost_postdump_hold30_260427_smoke/`
- Video:
  [`rollout_000_carrytrim120_leftboost_postdump_hold30_260427_success.mp4`](rollout_000_carrytrim120_leftboost_postdump_hold30_260427_success.mp4)
- `success_rate=1.0`, `cycle1/2/3_success_rate=1.0`
- `completed_transition_count=2`, `transition_timeout_count=0`
- `avg_final_success_signal=6201.70kg`, `avg_hard_target_collision_count=0`
- Cycle dump quality:
  - cycle1: mass out `2198.1kg`, final target delta `2011.6kg`, fraction `0.915`, post-dump drop `0kg`
  - cycle2: mass out `2008.8kg`, final target delta `1868.1kg`, fraction `0.908`, post-dump drop `0kg`
  - cycle3: mass out `2422.1kg`, final target delta `2322.0kg`, fraction `0.959`, post-dump drop `0kg`

Residual issue: cycle2 still shows a small pre-dump micro pullback near the start
of dump. It is much smaller than before and did not cause meaningful spill in
the hold30 smoke, but this is a sign that the 4-primitive boundary is still
doing too much. If this becomes unstable across more rollouts, the next design
step should be five primitives: `dig -> carry -> approach_dump -> dump_release -> return`.

## Ownership Pivot Back To 4 Primitives

Date: 2026-04-27

The 5-primitive experiment showed that `approach_dump` is not intuitive for
human teleop: operators naturally blend swing, boom/stick alignment, and
curl-out while visually checking that soil will not spill. A strict
`approach_dump -> dump_release` split produced too few clean approach windows.

Current V2.2 ownership returns to four primitives:

- `dig`: dig/load.
- `carry`: loaded transport before dump ownership begins.
- `dump`: move to top of target, align, release, and post-dump hold.
- `return`: empty-bucket return to the next dig.

The key ACT rule is: do not let a training chunk cross skill ownership. The
builder therefore ends `carry` at the earlier of:

- first `approach_dump` stage, or
- stable pre-dump curl-out onset.

`dump` starts at the same boundary. This keeps ACT's `chunk_size=100` future
action supervision from teaching carry to perform dump/release.

One-episode ownership probe:

- Raw:
  `/data/pingfan/excavator_testbed_data_archive/agx_v2_2_ownership_probe_raw_260427_1ep`
- Workskill:
  `/data/pingfan/excavator_testbed_data_archive/agx_v2_2_ownership_probe_workskill_260427_1ep`
- 4p root:
  `/data/pingfan/excavator_testbed_data_archive/agx_v2_2_4primitives_ownership_boundary_260427_1ep`
- Repo symlink: `data/agx_v2_2_4primitives_ownership_boundary_260427_1ep`
- Counts: `dig=3`, `carry=3`, `dump=3`, `return=0` (`--skip-return`)
- Carry QC: bucket mass loss `0kg`, `tail_stable_strong_curl_out_count=0`,
  `ownership_boundary_source_counts={stable_curl_out: 3}`
- Dump QC: hard collision windows `0`, near collision windows `0`
- Dump boundary starts `30-67` steps before official mass-based `dump_start`

This probe is good evidence that the 4p ownership definition matches human
operation better than the 5p approach/release split. More data should use this
definition: carry to target vicinity without owning final alignment, then dump
owns the approach-to-release sequence.

## Ownership History Rebuild And Carry/Dump Training Mix

Date: 2026-04-27

The refreshed V2.1 tail50 + targetsafe + V2.1c history workskill root was
rebuilt with the current 4p ownership boundary:

- Source workskill:
  `/data/pingfan/excavator_testbed_data_archive/agx_teleop_v2_1_refresh_tail50_workskill_clean_v3_targetsafe_v2_1c_260424183039`
- 4p history root:
  `/data/pingfan/excavator_testbed_data_archive/agx_v2_2_4primitives_ownership_history_260427`
- Repo symlink: `data/agx_v2_2_4primitives_ownership_history_260427`
- Counts: `dig=64`, `carry=27`, `dump=27`, `return=0` (`--skip-return`)
- Carry QC: bucket mass loss `0kg`, `tail_stable_strong_curl_out_count=0`,
  boundary sources `{stable_curl_out: 23, approach_dump_stage: 4}`
- Dump QC: hard collision windows `0`, near collision windows `3`
- Rejects: `30` windows missing dump ownership boundary and `7` missing safe
  dump intent; these are excluded from carry/dump supervision.

The first ownership smoke training mix uses symlinks, not image copies:

- Mix root:
  `/data/pingfan/excavator_testbed_data_archive/agx_v2_2_4primitives_ownership_history_probe_leftboost_260427`
- Repo symlink:
  `data/agx_v2_2_4primitives_ownership_history_probe_leftboost_260427`
- Mix rule: history ownership all + latest ownership probe all cycles `4x` +
  probe cycle2/source_cycle_id `1` extra `8x`
- Counts: `carry=47`, `dump=47`
- Carry config:
  `testbed/configs/act_agx_v2_2_4primitives_carry_ownership_leftboost_qvel_e500.yaml`
- Dump config:
  `testbed/configs/act_agx_v2_2_4primitives_dump_ownership_leftboost_qvel_e500.yaml`
- Carry checkpoint:
  `/data/pingfan/excavator_testbed_runs/ckpts/v2_2_4primitives/carry_qvel_ownership_history_probe_leftboost_e500_260427/policy_best.ckpt`
  (`best_epoch=499`, `best_val_loss=0.1020`)
- Dump checkpoint:
  `/data/pingfan/excavator_testbed_runs/ckpts/v2_2_4primitives/dump_qvel_ownership_history_probe_leftboost_e500_260427/policy_best.ckpt`
  (`best_epoch=190`, `best_val_loss=0.1109`)
- Smoke eval config:
  `testbed/configs/eval_agx_v2_2_4primitives_ownership_leftboost_qvel_3cycle_smoke.yaml`

Only `carry` and `dump` are retrained in this smoke. `dig` and `return` remain
on the existing V2.2 primitive checkpoints unless the rollout shows a separate
regression.

## Ownership Carry/Dump Rollout Result

Date: 2026-04-27

Rollout config:
`testbed/configs/eval_agx_v2_2_4primitives_ownership_leftboost_qvel_3cycle_smoke.yaml`

Artifacts:

- Video:
  `runs/eval/agx_v2_2_4primitives_ownership_leftboost_260427_smoke/videos/rollout_000.mp4`
- Metrics:
  `runs/eval/agx_v2_2_4primitives_ownership_leftboost_260427_smoke/results/metrics.json`
- JSONL:
  `runs/eval/agx_v2_2_4primitives_ownership_leftboost_260427_smoke/results/rollouts/rollout_000.jsonl`
- Keyframes:
  `runs/eval/agx_v2_2_4primitives_ownership_leftboost_260427_smoke/results/diagnostics/keyframes.jpg`

Nominal metrics passed:

- `success_rate=1.0`
- `cycle1/2/3_success_rate=1.0`
- `completed_transition_count=2`
- `transition_timeout_count=0`
- `hard_target_collision_count=0`
- `final_bucket_mass=0kg`

Behavioral inspection failed acceptance. Cycle2 still dumps behind/back-edge of
the truck. The new ownership carry does not collide, and it no longer shows the
old severe pre-switch emptying, but planner `carry -> dump` still fires at a
state that is not truly over the bed:

- Cycle2 `carry -> dump`: `t=2012`, `horizontal=0.593m`,
  `height_above_rim=0.482m`, `over_footprint=0`, `clearance=1`
- Cycle2 official material `dump_start`: `t=2106`, `horizontal=0.698m`,
  `height_above_rim=0.561m`, `over_footprint=0`
- Cycle2 `dump_end`: `t=2140`, bucket empty, no hard collision, but visual dump
  is mostly behind/outside the target bed.

The current success metrics are therefore too permissive for this failure mode:
the rollout can pass aggregate 3-cycle success while one cycle deposits poorly.
The likely next fix is not more e500 training alone. The planner readiness needs
a better relative target-occupancy signal than the current
`horizontal_distance <= 0.60m` OR condition, because `bucket_over_target_footprint`
is never true in this rollout. Options:

- fix/retune Unity target footprint so `over_footprint` becomes meaningful, then
  require it or a learned visual geometry head;
- add a stricter relative offset/bed-center readiness signal instead of only
  scalar horizontal distance;
- add per-cycle deposited-fraction/post-drop acceptance metrics so this failure
  cannot hide behind aggregate success.
