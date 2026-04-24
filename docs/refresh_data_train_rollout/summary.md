# Refresh Data Train Rollout Summary

Date: 2026-04-24, Asia/Shanghai

## Result

- Refreshed historical v2_1 raw data with the new 13D target geometry protocol and tail50 replay recording.
- Used v2_1c newer labeling/building rules: `v2_1c_sector10d_digarea13` + `stage5_strict` clean_v3 target-safe workskill.
- Built a combined workskill training set with 64 cycles; max crop length 759 steps; training used `episode_len=1200`.
- Trained ACT qpos+qvel for 2000 epochs. Best checkpoint: epoch 1985, val loss 0.146864.
- Rollout video: `rollout_000.mp4`. Smoke rollout success: 1/1, avg return 8273.48.

## Data Refresh

| refreshed group | eps | 3-dump eps | tail ok | env 13D ok | max qpos diff |
|---|---:|---:|---:|---:|---:|
| `agx_teleop_v2_1_multi_raw_refreshed_targetgeo_tail50_260424183039` | 20 | 20 | 20 | 20 | 0.0077 |
| `agx_teleop_v2_1_multi_raw_new_refreshed_targetgeo_tail50_260424183039` | 20 | 20 | 20 | 20 | 0.0167 |
| `agx_teleop_v2_1_multi_raw_carryfix_refreshed_targetgeo_tail50_260424183039` | 5 | 5 | 5 | 5 | 0.0166 |
| `agx_teleop_v2_1_multi_raw_quality_2604241251_refreshed_targetgeo_tail50_260424183039` | 15 | 14 | 15 | 15 | 0.0193 |

Overall qpos max diff: 0.0193. Target geometry audit: 100% coverage for horizontal distance, height-above-rim, footprint mask, and dump-clearance mask across all refreshed groups.

Incomplete raw replay episodes:
- `agx_teleop_v2_1_multi_raw_quality_2604241251_refreshed_targetgeo_tail50_260424183039/episode_12.hdf5`: completed_dump_count=2, stop_reason=replay_complete.

Conclusion: the old data is still usable after refresh for workskill training. I would not discard it or immediately re-record everything. The one 2-dump raw episode should be noted, but the cycle crop builder can still use its successful cycles.

## Workskill Build

| source workskill group | source eps | candidate cycles | kept cycles | main rejects |
|---|---:|---:|---:|---|
| `agx_teleop_v2_1_multi_raw_refreshed_targetgeo_tail50_260424183039_workskill_clean_v3_targetsafe_v2_1c` | 20 | 60 | 21 | near_dump_start:21, flat_bucket_qds:6, far_dump_start:5, low_carry_efficiency:4 |
| `agx_teleop_v2_1_multi_raw_new_refreshed_targetgeo_tail50_260424183039_workskill_clean_v3_targetsafe_v2_1c` | 20 | 60 | 18 | near_dump_start:34, flat_bucket_qds:4, low_carry_efficiency:2, collision_in_cycle:1 |
| `agx_teleop_v2_1_multi_raw_carryfix_refreshed_targetgeo_tail50_260424183039_workskill_clean_v3_targetsafe_v2_1c` | 5 | 15 | 9 | near_dump_start:4, far_dump_start:1, flat_bucket_qds:1 |
| `agx_teleop_v2_1_multi_raw_quality_2604241251_refreshed_targetgeo_tail50_260424183039_workskill_clean_v3_targetsafe_v2_1c` | 15 | 45 | 16 | near_dump_start:23, far_dump_start:3, low_carry_efficiency:3 |

Combined dataset: `data/agx_teleop_v2_1_refresh_tail50_workskill_clean_v3_targetsafe_v2_1c_260424183039`. Train/val split: 51/13 episodes.

## Training

- Config: `runs/refresh_data_train_rollout_260424183039/train_refresh_tail50_v2_1c_e2000.yaml`
- Checkpoint dir: `/data/pingfan/excavator_testbed_runs/ckpts/agx_excavation_act_v2_1_refresh_tail50_clean_v3_targetsafe_v2_1c_qvel_e2000_260424183039`
- Best checkpoint: `/data/pingfan/excavator_testbed_runs/ckpts/agx_excavation_act_v2_1_refresh_tail50_clean_v3_targetsafe_v2_1c_qvel_e2000_260424183039/policy_best.ckpt`
- Best epoch/loss: 1985 / 0.146864
- Low-dim keys: qpos, qvel; max dataset length: 759; loader length: 1200.

## Rollout

- Eval config: `runs/refresh_data_train_rollout_260424183039/eval_refresh_tail50_v2_1c_3cycle_smoke.yaml`
- Video: `docs/refresh_data_train_rollout/rollout_000.mp4`
- Success: True; dump-complete final hold: True; strict dump-complete: False
- Stop reason: `target_cycle_gate_terminal_hold_reached`; cycles: 1, 1, 1; planner sectors: left->right->right
- Deposited target mass: final 4466.3 kg; final bucket mass 0.0 kg; hard collisions 0.
- Quality warnings: spill_before_target_count=187, unsafe_target_distance_count=49, near_dump_start_count=2, dump_start_horizontal_distance_mean=0.326 m.

## Recommendation

- Keep the refreshed old data. It now has the required target geometry and produced a useful 64-cycle v2_1c workskill set.
- The model can complete 3 cycles, but strict safety still fails because it sometimes starts dumping too near the target and spills before target. This looks more like target-approach/dump gating behavior than a total data failure.
- Next improvement should be scripted policy/guard first: block or reshape dump actions until target horizontal distance and height-above-rim satisfy the stricter geometry gate, and consider tightening the workskill filter toward `dump_start_horizontal_distance >= 0.45 m` for the next comparison run.
- New recording is useful after the guard comparison, not as the immediate first move.
