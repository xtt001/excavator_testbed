# V2.5 Rollout 卡住问题记录

记录时间：2026-06-30
相关产物目录：`runs/eval/*20260625`

## 背景

本次目标是在新的 V2.5 分支上重新 rollout，并保存视频，确认 planner 重构后是否还能复现重构前的 10 铲连续、顺滑挖掘表现。

## 遇到的问题

最初的对照 rollout 出现卡住/失败：

- `runs/eval/pre_dig_align_restored_enabled_3cycle_20260625`
  - `success=false`
  - `completed_dump_count=0`
  - `qualified_dig_start_count=0`
  - 最终 skill 为 `pre_dig_align`
  - `pre_dig_align_completed_count=8`
  - `pre_dig_align_replan_count=9`
  - `dig_exit_guard_replan_count=9`
  - `rollout_stop_reason=low_productivity_consecutive`

随后关闭 `pre_dig_align` 做对照：

- `runs/eval/pre_dig_align_restored_disabled_3cycle_20260625`
  - `success=false`
  - `completed_dump_count=0`
  - `qualified_dig_start_count=0`
  - 最终 skill 为 `dig`
  - `dig_exit_guard_replan_count=9`
  - `rollout_stop_reason=low_productivity_consecutive`

因此，失败现象不是单纯由视频保存或 Unity 连接造成的，而是 planner/配置组合在第 0 cycle 没有形成有效挖掘，随后被低产保护终止。

## 原因分析

这次卡住主要是配置路径不一致导致的，不是 planner 重构本身直接破坏了 10 铲主线。

`pre_dig_align` 是 V2.4/V2.4.5 阶段保留的诊断开关，最初用于补第 0 铲没有上一轮 return 时的 handoff 盲点。文档里也明确写过：长期 `return -> dig` 主线应由 conditioned return 学会回到 next-entry 状态，手写 align 不替代后续铲的 learned transition。

这次失败的 3-cycle 对照使用的是另一套配置组合：

- prior：`testbed/configs/planner_priors/yulong_removed_depth_dig_cut_prior_v3.json`
- checkpoint：`runs/ckpts/yulong_v2_4_5_process_boundary_qc6_20260522/...`
- `target_cycle_gate=3`
- enabled 对照还重新打开了 `pre_dig_align.enabled=true`

而重构前能跑通的 aggregate TX24 主线使用的是：

- `pre_dig_align.enabled=false`
- surface-depth tight dump checkpoint：`v2_4_5_surface_depth_tight_dump_qc6labels_scale080_20260524`
- relocated return checkpoint：`v2_4_5_return_relocate_token_swap_all_surface_depth_qc6labels_scale080_20260526`
- surface-depth / next-entry-cells planner prior 与 exemplar
- `dig_failed_replan_next_skill=stop`

所以“上一个分支测试没问题、这次 2.5 测试卡住”的核心差异是：上一个成功测试走的是 aggregate TX24 已验证配置；这次一开始测试的是 restored/pre-dig 对照配置，prior、checkpoint、handoff 开关都不一致。

## 解决过程

1. 重新 rollout 并开启视频保存，确认失败不是因为原视频文件无法打开。
2. 查看 `rollout_000_summary.json`、`rollout_000.jsonl` 和 `rollout_000_planner_trace.json`，定位到失败发生在第 0 cycle，且没有任何 `qualified_dig_start` / `dump_start` / `dump_end`。
3. 做 `pre_dig_align.enabled=true/false` 对照。关闭后仍失败，说明根因不只是 pre-dig align 本身，还包括与成功主线不一致的 prior/checkpoint 配置。
4. 改用 aggregate TX24 兼容配置重新 rollout，并保存视频。

## 最终结果

`runs/eval/reproduce_aggregate_tx24_20260625` 成功复现 10 铲：

- 视频：`runs/eval/reproduce_aggregate_tx24_20260625/videos/rollout_000.mp4`
- `success=true`
- `completed_dump_count=10`
- `qualified_dig_start_count=10`
- `dump_start_count=10`
- `dump_end_count=10`
- `target_cycle_gate=15`
- `target_cycle_completed_dump_count=10`
- `rollout_stop_reason=dig_area_depleted`
- `hard_target_collision_count=0`
- `spill_before_target_count=0`

结论：新的 V2.5 分支在 aggregate TX24 兼容配置下可以复现重构前的 10 铲连续挖掘。后续回归应优先使用该成功配置或从它裁剪出 3-cycle smoke；`pre_dig_align_restored_*` 这类配置应只作为诊断对照，不应作为判断 planner 重构是否退化的主回归入口。
