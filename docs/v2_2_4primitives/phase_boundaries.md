# V2.2 4-Primitives Phase Boundaries

本文件是 V2.2 四 primitive 的录制、离线 builder、训练和 rollout planner 的
共同定义。目标是避免上一段 skill 学到下一段 skill 的动作，尤其避免
`carry` 学会提前 curl-out/release。

## Primitive Ownership

| Primitive | Starts At | Ends Before | Owns | Must Not Own |
| --- | --- | --- | --- | --- |
| `dig` | `qualified_dig_start` | first `carry` or `approach_dump` stage | digging, loading bucket | target approach, truck alignment, dump release |
| `carry` | first `carry` stage | first `approach_dump` stage | loaded transport with bucket closed/stable | stable curl-out, release, final dump-area alignment |
| `dump` | first `approach_dump` stage | `dump_end` plus configured post-dump hold | move to top of target, align over dump area, release, stabilize after dump | next-cycle return |
| `return` | `dump_end` after post-dump hold | next `qualified_dig_start` | empty-bucket return to reusable dig pose | new digging or loaded transport |

## Builder Rules

- `carry -> dump` training boundary is now **first `approach_dump` stage**.
- On new 16-field Unity data, `approach_dump` is detected from dump-area-top
  geometry rather than legacy target distance alone: loaded bucket,
  `bucket_height_above_target_rim_m >= 0.30`, and
  `bucket_dump_area_footprint_outside_distance_m <= 1.35`. This makes the
  approach label tolerant enough for human teleop without moving release
  ownership into `carry`.
- Stable curl-out before `approach_dump` is not automatically bad. If the
  final dump is no-crash and good-quality, the builder shifts the ownership
  boundary earlier so that `dump` owns that release entrance and `carry` does
  not learn it. If the final dump is not good-quality, it is still rejected:
  - quality-accepted source:
    `pre_approach_stable_curl_out_good_dump`
  - reject reasons:
    `carry_release_before_approach_dump_stage`,
    `release_before_approach_dump_stage`
- `dump` must contain target approach/alignment before release. It should not
  start only after the bucket is already in stable curl-out.
- Strict `dump_intent` is the first stable safe release intent inside
  `approach_dump`; it satisfies:
  - bucket qpos is curled out enough,
  - bucket action is release/curl-out,
  - bucket mass is present,
  - height is above the relaxed release-start rim margin
    (`bucket_height_above_target_rim_m >= 0.20`),
  - clearance is OK,
  - `bucket_dump_area_footprint_outside_distance_m <= 0.45`.
- Robust acceptance is also enabled for human teleop. If the strict intent
  pattern is missed, a window can still be accepted when the whole dump is:
  no hard target collision, successful cycle or sufficient deposited mass, and
  deposited fraction is high enough relative to bucket mass loss. These samples
  are tagged with `dump_acceptance_mode=good_dump_quality` instead of
  `safe_intent`.
- Dump QC allows a small post-release vertical tolerance: during the first
  20 dump steps, `bucket_height_above_target_rim_m` may dip to `-0.08m`
  without rejecting the window if there is no hard collision. This keeps the
  filter from rejecting slight conservative bucket-proxy/rim overlap while
  still rejecting real unsafe dumps.
- There is still no blind fallback to official mass-based `dump_start`. The
  official marker can be used as the release marker only after the whole dump
  passes good-dump quality acceptance.
- Old 13-field target geometry data is not valid for this ownership builder.
  V2.2 middle-handoff data must include:
  - `bucket_dump_area_relative_x_m`
  - `bucket_dump_area_relative_z_m`
  - `bucket_dump_area_footprint_outside_distance_m`
- New-env pilot data may use `--boundary-profile
  v2_2_effect_release_fallback`. This keeps the same four primitive ownership
  but treats the old `approach_dump` threshold implementation as legacy: when
  no `approach_dump` label exists, a stable effect-based release/curl-out onset
  can become the `carry -> dump` boundary if the final dump passes good-quality
  acceptance. This is used for the YuLong FarmStick pilot so `carry` does not
  learn release actions.
- Small-bucket pilots such as YuLong should relabel with
  `--qualified-dig-start-mode contact_depth`, so `dig` starts when the bucket
  reaches the dig area and goes below the dig plane instead of waiting for a
  large mass jump.

## Planner Handoff Rules

- Runtime `carry -> dump` switching must use the same target-relative concept
  as the builder. In `dump_area_relative` mode, the planner must satisfy
  `bucket_dump_area_footprint_outside_distance_m <=
  dump_ready_max_dump_area_footprint_outside_distance_m` and, when configured, the
  signed `bucket_dump_area_relative_x_m/z_m` window. Disabling
  `dump_ready_require_over_footprint` only relaxes the Unity
  `bucket_over_target_footprint_mask`, it does not disable the position check.
- `bucket_over_target_footprint_mask` is a diagnostic/mask signal, not a
  substitute for dump-area-relative handoff when the config says `dump_area_relative`.
- `bucket_dump_area_footprint_outside_distance_m` is an unsigned proximity scalar:
  it says how close the bucket proxy is to the dump-area footprint, but not
  whether the bucket is near the tail, middle, or front. Do not use it alone as
  the V2.2 handoff rule.
- Current 4p approach handoff uses a signed dump-area-relative approach corridor
  derived from the good20 teleop distribution and tightened by the successful
  5-cycle smoke:
  - `bucket_dump_area_footprint_outside_distance_m <= 1.35`
  - `-4.30 <= bucket_dump_area_relative_x_m <= 2.00`
  - `2.75 <= bucket_dump_area_relative_z_m <= 3.50`
  - `bucket_height_above_target_rim_m >= 0.30`
- A valid 4-primitive dump handoff means: loaded bucket, enough rim height, the
  selected target-relative position rule is true for the configured hold, and
  optional clearance is satisfied if enabled. It should not switch merely
  because the bucket is high while still far behind the truck.
- The V2.2 planner can optionally inject the existing 10D
  `/v2/step/goal_tokens` format into primitive ACT observations from
  `policy.goal_sequence`, for example `["mid", "left", "right", "left",
  "right"]`. This is a low-frequency task-intent signal for skills that were
  trained with `goal_tokens`; it is not Unity `env_state`, and it does not
  replace the target-relative geometry gates for `carry -> dump`.
- `primitive_goal_curr_sector_id` and `primitive_goal_next_sector_id` are
  written into rollout JSONL so that a failed long rollout can be separated
  into "planner intended this sector" versus "dig/return ACT did not realize
  that sector".
- For pilots without a learned reset-to-entry policy, `primitive_planner_act`
  can start in `bootstrap_end_mode=scripted_qpos`. This is a deterministic
  reset bootstrap into the first planned/accepted entry pose; it is a smoke
  compatibility layer, not a learned primitive and not a replacement for
  planned entry / actual accepted start auditing. Equipment whose normalized
  actuator direction differs from normalized qpos direction should set
  `scripted_bootstrap.action_signs` per axis.

## Recording Vs Training Acceptance

Raw teleop episodes should be kept even when the movement is not trainable;
they are useful diagnostics. The stricter filter applies only when building
primitive training windows:

- Recording acceptance: complete 3 dumps, no hard target collision, 16-field
  target geometry present.
- Training acceptance: `carry` must not include material loss or hard collision.
  `dump` can enter through strict safe intent or through good-dump quality
  acceptance. Good-quality human entrances are kept for robustness instead of
  being blocked by one geometry/action standard.
- Do not let `carry` own release. If release starts before the current
  `approach_dump` label but the dump is good, shift the boundary earlier into
  `dump`.

## Human Teleop Expectation

During recording, the operator can move fluently, but the intended ownership is:

1. `carry`: keep the bucket closed while transporting soil toward the truck.
2. `approach_dump`: begin the final visual approach to the dump area; mild
   mixed swing/boom/stick adjustment is fine.
3. `release`: only begin stable curl-out when the bucket is clearly over the
   dump-area middle region, not at the tail edge.
4. `post-dump hold`: after soil leaves the bucket, hold long enough that return
   does not pull material back out of the dump area.

If a demonstration starts stable curl-out before the `approach_dump` phase,
it can be used when the final dump is visibly/quantitatively good and no hard
collision occurs. The builder should move the ownership boundary, not discard
that style just because it misses one strict entrance pattern.
