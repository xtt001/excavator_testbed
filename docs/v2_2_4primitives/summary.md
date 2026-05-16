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
- A live smoke with scalar `dump_ready_max_horizontal_distance_m=0.60` exposed a new mismatch: cycle2 stayed in `carry`, began curl-out around `horizontal ~= 0.79m`, spilled the bucket before `dump_ready`, then oscillated with empty bucket. Later dump-area-footprint smokes at `0.82m` and `0.70m` switched earlier but caused left cycle2 to empty outside the target. The current smoke returns to `0.60m` and isolates the post-dump fix by disabling immediate `dump_end` boundary switching.
- Success video: [`rollout_000_safe_dump_260427_success.mp4`](rollout_000_safe_dump_260427_success.mp4)
- Final safe-dump smoke:
  - `success_rate=1.0`, `cycle1/2/3_success_rate=1.0`
  - `completed_transition_count=2`, `transition_timeout_count=0`
  - `avg_final_success_signal=3740.48kg`, `avg_final_bucket_mass=0.0kg`
  - `avg_hard_target_collision_count=0`
  - Remaining quality debt: `avg_spill_before_target_count=227`, `avg_unsafe_target_distance_count=103`, `avg_quality_issue_count=336`
  - Key switches: cycle1 `carry->dump` at `horizontal=0.729m,height=0.668m`; cycle2 at `0.785m,0.666m`; cycle3 at `0.724m,0.662m`

## 2026-04-28 Planner Switch Fix

- Root cause found during good20 strict rollout comparison: configs that set
  `dump_ready_require_over_footprint=false` were unintentionally bypassing all
  position checks. Those smokes switched to `dump` as soon as height/mass were
  acceptable, even when `bucket_dump_area_footprint_outside_distance_m` was still
  around `2.4-3.0m`.
- Planner semantics are now corrected: in `dump_area_relative` mode,
  `bucket_dump_area_footprint_outside_distance_m` must satisfy the configured limit
  regardless of whether the Unity footprint mask is required. The footprint
  flag is optional evidence, not permission to ignore dump-area-relative geometry.
- Human good20 data shows two distinct moments: approach ownership begins
  near `dump_area_outside ~= 1.35m`, while official dump/release is much later
  around median `dump_area_outside ~= 0.49m`. Four primitives keep both inside
  `dump`, so the runtime switch must match the dump training start and not
  collapse into a pure height trigger.
- Fixed-planner smoke with `dump_area_outside<=1.25`, `height>=0.30`, and no
  over-footprint/clearance requirement succeeded without hard collision, but
  cycle2 waited in `carry` for `1426` steps. The blocker was the position gate:
  cycle2 first reached height at `t=1345` with `dump_area_outside=1.888`, then hovered
  around `1.26-1.43` until `t=2498`, when it finally crossed `1.25` for the
  3-step hold. Offline replay of the same log shows a corrected
  `dump_area_outside<=1.35` gate would have switched cycle2 at `t=1516`, much closer
  to the human approach-start distribution, while still preserving the fixed
  position check.
- The planner now supports signed dump-area-relative windows. The current pushed 4p
  smoke config uses the tighter successful 5-cycle handoff corridor:
  `outside<=1.35`, `-4.30<=bucket_dump_area_relative_x_m<=2.00`, and
  `2.75<=bucket_dump_area_relative_z_m<=3.50`. The unsigned `outside` scalar is kept
  only as a coarse proximity gate; it is no longer sufficient by itself because
  it cannot distinguish truck tail, middle, and front.
- Data/configs that lack 16-field dump-area-relative geometry, or experiments that
  switch from `outside` alone, are retained only as diagnostics. They should not
  be mixed into the current V2.2 middle-handoff carry/dump training or treated as
  acceptance evidence.
- Live signed-corridor smoke:
  `runs/eval/agx_v2_2_4primitives_good20_strict_signedcorridor_260428_smoke`
  - video:
    `runs/eval/agx_v2_2_4primitives_good20_strict_signedcorridor_260428_smoke/videos/rollout_000.mp4`
  - `success_rate=1.0`, `cycle1/2/3_success_rate=1.0`
  - `completed_transition_count=2`, `transition_timeout_count=0`,
    `hard_target_collision_count=0`
  - switch points:
    cycle1 `t=570`, `outside=1.301`, `x=-3.917`, `z=3.183`;
    cycle2 `t=1514`, `outside=1.340`, `x=-1.636`, `z=3.213`;
    cycle3 `t=2572`, `outside=1.269`, `x=-4.324`, `z=3.018`
  - deposit quality still needs work:
    `cycle1/2/3_deposited_fraction=0.701/0.485/0.646`, with no post-dump
    target mass drop. The signed corridor fixed the planner waiting/position
    bug, but the current dump/carry policies still do not put enough of each
    bucket into the target.
- Longer 5-cycle stress tests were run with target intent
  `mid -> left -> right -> left -> right`, but current 4p `qpos+qvel`
  primitives do not receive a next-sector goal. The scripted planner only
  manages `dig/carry/dump/return` boundaries, so the actual sector is whatever
  the learned `return` and `dig` policies produce before
  `qualified_dig_start` fires.
  - Baseline signed corridor, `x_min=-5.0`:
    `runs/eval/agx_v2_2_4primitives_good20_strict_signedcorridor_5cycle_mlr_lr_ep8000_260428_smoke`
    produced actual QDS sectors `mid, left, right, mid, ...`.
    It succeeded by aggregate metrics, but cycle4/5 dump had hard collision
    events and lower deposit quality:
    `cycle_deposited_fraction_mean=0.587`, min `0.502`,
    `hard_target_collision_count=11`, max post-dump target drop `89.97kg`.
  - Tighter signed corridor, `x_min=-4.3`:
    `runs/eval/agx_v2_2_4primitives_good20_strict_signedcorridor_xmin43_5cycle_260428_smoke`
    produced actual QDS sectors `mid, left, right, right, right`.
    It improved dump placement quality but still did not control the requested
    sequence: `cycle_deposited_fraction_mean=0.709`, min `0.533`,
    `hard_target_collision_count=5`, max post-dump target drop `44.98kg`.
    Cycle5 stayed in `dig` until `t=5745` because bucket mass did not reach
    the `dig_to_carry_min_bucket_mass_kg=300` threshold; it was slow digging,
    not a carry/dump planner wait.
  - Conclusion: signed dump-area-relative gates are useful for dump entry, but they
    cannot make the agent dig a requested sector. To run deterministic
    `mid-left-right-left-right`, `return/dig` must become goal-conditioned or
    the planner must own next-sector positioning before allowing
    `qualified_dig_start -> dig`.

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
  - `dump_ready_max_horizontal_distance_m=null`
  - `dump_ready_max_dump_area_footprint_outside_distance_m=0.60`
  - `dump_ready_min_height_above_rim_m=0.45`
  - `dump_done_hold_steps=30`
  - `dump_done_use_boundary_event=false`

Reason for `dump_done_hold_steps=30` and disabled immediate `dump_end` switching:
ACT predicts 100-step chunks and temporal aggregation blends future actions. With
the boundary event taking priority, cycle2 already placed soil into the truck,
but return took over while the bucket was still at the dump-area edge and pulled soil
back out. Holding dump for 30 steps lets the dump policy finish the
release/stabilization phase before return starts.

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
the hold30 smoke. The current recommended direction is to keep the four
primitive ownership boundary and improve goal conditioning / data quality
inside that structure.

## Ownership Pivot Back To 4 Primitives

Date: 2026-04-27

The diagnostic approach/release split showed that `approach_dump` is not
intuitive for human teleop: operators naturally blend swing, boom/stick
alignment, and curl-out while visually checking that soil will not spill. A
strict release-only sub-skill produced too few clean approach windows.

Current V2.2 ownership returns to four primitives:

- `dig`: dig/load.
- `carry`: loaded transport before dump ownership begins.
- `dump`: move to top of target, align, release, and post-dump hold.
- `return`: empty-bucket return to the next dig.

Phase boundary source of truth:
[`phase_boundaries.md`](phase_boundaries.md).

The key ACT rule is: do not let a training chunk cross skill ownership. The
builder now ends `carry` at the first `approach_dump` stage and starts `dump`
there. If stable curl-out appears before `approach_dump`, the window is rejected
as ambiguous ownership instead of assigning that release motion to either
`carry` or a late-starting `dump`.

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
operation better than a finer approach/release split. More data should use this
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
state that is not truly over the dump area:

- Cycle2 `carry -> dump`: `t=2012`, `horizontal=0.593m`,
  `height_above_rim=0.482m`, `over_footprint=0`, `clearance=1`
- Cycle2 official material `dump_start`: `t=2106`, `horizontal=0.698m`,
  `height_above_rim=0.561m`, `over_footprint=0`
- Cycle2 `dump_end`: `t=2140`, bucket empty, no hard collision, but visual dump
  is mostly behind/outside the dump area.

The current success metrics are therefore too permissive for this failure mode:
the rollout can pass aggregate 3-cycle success while one cycle deposits poorly.
The follow-up fix is now implemented:

- Unity target geometry now emits dump-area-local bucket proxy center offsets:
  `bucket_dump_area_relative_x_m`, `bucket_dump_area_relative_z_m`, and
  `bucket_dump_area_footprint_outside_distance_m`.
- `bucket_over_target_footprint_mask` now uses the existing DumpArea clearance
  tolerance to mean the bucket proxy is above the dump-area dump region, not
  strict OBB overlap; center-relative `bucket_dump_area_relative_x_m/z_m` remains a
  diagnostic.
- The current 4p smoke position mode is `dump_area_relative`; it no
  longer switches dump from `target_horizontal_distance_m <= 0.60m` alone, and
  the current smoke config sets `dump_ready_max_horizontal_distance_m=null`.
  Unity `bucket_over_target_footprint_mask` now means bucket proxy is above the
  dump-area dump region, not strict OBB overlap. The smoke handoff uses
  `dump_area_relative` mode with `bucket_dump_area_footprint_outside_distance_m <= 0.60m`;
  the dump-area mask is diagnostic, while the strict outside distance remains
  the release-depth gate. Earlier `0.82m` / `0.70m` smokes made left cycle2
  release outside the target, and the `0.60m` dump-area-mask smoke still handed
  off near the truck tail. A `0.35m` diagnostic did not enter dump at all:
  current carry never satisfied `outside<=0.35m` while also keeping
  `height_above_rim>=0.45m`. That points to a builder/label ownership mismatch
  rather than a threshold-only fix.
- The 4p builder has been updated for middle-handoff ownership: it requires the
  new dump-area-relative geometry fields, rejects old 13-field target geometry for
  carry/dump ownership, rejects stable curl-out before `approach_dump`, and
  requires safe release intent to satisfy
  `bucket_dump_area_footprint_outside_distance_m <= 0.45m`.
- Rollout QC now reports per-cycle deposited fraction and post-dump target mass
  drop, including `cycle2_deposited_fraction` and
  `cycle2_post_dump_target_mass_drop_kg`, so aggregate success cannot hide a
  cycle2 back-edge dump.

## Middle-Handoff Data Refresh Probe

Date: 2026-04-28

The Unity protocol now writes 16-field target geometry, so two one-episode
smokes were replay-refreshed before rebuilding carry/dump:

- Historical V2.1 sample:
  `data/agx_teleop_v2_1_multi_raw_targetgeo16_smoke_260428`
  - Replay QA: qpos mean diff `0.0005`, max diff `0.0020`.
  - Env state width: `16`.
  - Workskill all cycles: `3`.
  - New middle-handoff primitive result: `dig=3`, `carry=0`, `dump=0`.
  - Rejects: cycle1/2 fail `dump_first20_height_below_rim` and clearance loss;
    cycle3 fails `missing_safe_dump_intent`.
- Recent ownership probe:
  `data/agx_v2_2_ownership_probe_raw_targetgeo16_260428`
  - Replay QA: qpos mean diff `0.0004`, max diff `0.0021`.
  - Env state width: `16`.
  - Workskill all cycles: `3`.
  - New middle-handoff primitive result: `dig=3`, `carry=0`, `dump=0`.
  - Rejects: cycle1/2 have stable curl-out before `approach_dump`
    (`carry_release_before_approach_dump_stage` /
    `release_before_approach_dump_stage`); cycle3 fails
    `missing_safe_dump_intent`.

Conclusion: old refreshed data and the earlier ownership probe are useful for
diagnosis, but they should not be used for the new middle-handoff carry/dump
training. The next dataset must be newly recorded with the phase-boundary
document in mind: carry closes and transports, approach_dump starts before any
stable release, and release begins only after the bucket is over the dump-area
middle region.

## Middle-Handoff Teleop Rerecord Check

Date: 2026-04-28

Recorded one new raw episode:

- Raw:
  `data/agx_v2_2_middlehandoff_teleop_raw_260428_rerecord_1ep`
- Relabeled:
  `data/agx_v2_2_middlehandoff_teleop_raw_260428_rerecord_1ep_relabeled`
- Workskill all:
  `data/agx_v2_2_middlehandoff_teleop_raw_260428_rerecord_1ep_workskill_all`

Basic recording quality was usable for diagnosis:

- Steps: `3485`
- Completed dumps: `3`
- Env state width: `16`
- Target geometry step coverage: `1.0`
- Hard target collisions: `0`

The relabel now uses dump-area-top geometry for `approach_dump`, so all three cycles
received explicit approach windows:

- Cycle1: `carry 289-761`, `approach_dump 762-954`, `dump_start 955`
- Cycle2: `carry 1341-1966`, `approach_dump 1967-2051`, `dump_start 2052`
- Cycle3: `carry 2537-3068`, `approach_dump 3069-3152`, `dump_start 3153`

Strict primitive acceptance still rejected this episode for carry/dump
training:

- Primitive result: `dig=3`, `carry=0`, `dump=0`, `return` build incomplete
  because carry/dump were empty.
- Cycle1 reject: `dump_first20_height_below_rim` and
  `dump_first20_clearance_lost` after the first safe candidate.
- Cycle2 reject: `missing_safe_dump_intent`; the approach window never reached
  `bucket_dump_area_footprint_outside_distance_m <= 0.45` before official
  `dump_start`.
- Cycle3 reject: `missing_safe_dump_intent`; the bucket stayed closed through
  the approach window and never produced stable pre-dump release intent before
  official `dump_start`.

Decision: keep this raw episode as a diagnostic sample, but do not train
`carry` or `dump` from it. The next collection should make the release moment
more explicit: first move/hold over the dump-area middle, then start sustained
curl-out while height and clearance are still safely above the rim.

Follow-up adjustment: the vertical threshold was slightly relaxed because the
current teleop style separates movements and the bucket proxy can dip just
below the rim without any hard collision. `dump_intent` now starts at
`bucket_height_above_target_rim_m >= 0.20`, and first-20-step dump QC tolerates
down to `-0.08m` when no hard target collision occurs. The dump-area-relative release
depth (`bucket_dump_area_footprint_outside_distance_m <= 0.45`) and sustained
curl-out requirements remain unchanged.

After this height tolerance adjustment, the same rerecord built:

- Primitive root:
  `data/agx_v2_2_middlehandoff_teleop_rerecord_primitives_v2_2_heighttol_260428`
- Accepted: `dig=3`, `carry=1`, `dump=1`, `return=2`
- Accepted dump first-20 min height: `-0.0466m`, within the new `-0.08m`
  tolerance, with hard collision count `0`.
- Remaining rejects: `carry:missing_safe_dump_intent=2`,
  `dump:missing_safe_dump_intent=2`.

This confirms the height threshold was too strict for cycle1, while cycle2/3
are still true ownership/data issues: one does not get close enough to the
dump-area middle before release, and one does not show stable pre-dump
release intent before official `dump_start`.

## Middle-Handoff Rerecord2 Check

Date: 2026-04-28

Previous middle-handoff candidate episodes are discarded for training
selection. They remain on disk only as diagnostics. A new one-episode raw
recording was collected:

- Raw:
  `data/agx_v2_2_middlehandoff_teleop_raw_260428_rerecord2_1ep`
- Relabeled:
  `data/agx_v2_2_middlehandoff_teleop_raw_260428_rerecord2_1ep_relabeled`
- Workskill all:
  `data/agx_v2_2_middlehandoff_teleop_raw_260428_rerecord2_1ep_workskill_all`
- Primitive root:
  `data/agx_v2_2_middlehandoff_teleop_rerecord2_primitives_v2_2_260428`

Recording checks:

- Steps: `3336`
- Completed dumps: `3`
- Env state width: `16`
- Target geometry coverage: `1.0`
- Hard target collision count: `0`

Relabeled phase windows:

- Cycle1: `carry 310-835`, `approach_dump 836-1005`, `dump_start 1006`
- Cycle2: `carry 1423-1999`, `approach_dump 2000-2156`, `dump_start 2157`
- Cycle3: `carry 2575-3065`, no `approach_dump`, `dump_start 3066`

Strict primitive acceptance:

- Accepted: `dig=3`, `carry=2`, `dump=2`, `return=2`
- Rejected: `carry:missing_dump_ownership_boundary=1`,
  `dump:missing_dump_ownership_boundary=1`
- Accepted carry windows have zero pre-dump mass loss and no stable release in
  the carry tail.
- Accepted dump windows start at
  `bucket_dump_area_footprint_outside_distance_m ~= 0.434-0.444`,
  `height_above_rim ~= 0.389-0.407`, with no first-20 clearance loss and no
  hard collision.

Decision: this rerecord is the first good candidate for the new middle-handoff
carry/dump dataset, but it contributes only two usable carry/dump cycles.
Collect more episodes with the same cycle1/2 style, and for cycle3 make sure
there is a visible approach phase before release so the builder can assign
`dump` ownership cleanly.
