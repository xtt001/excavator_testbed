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
