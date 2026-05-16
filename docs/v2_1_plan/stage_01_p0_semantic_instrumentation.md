# Stage 01 — P0 Semantic Instrumentation and Mainline Migration

## Goal

把主线从“单轮 + ready-anchor stop”切换到“多轮 raw + 事件切窗 + 多轮评测”。

本阶段只做语义仪表化与主线迁移，不改在线控制，不引入 hybrid policy。

## Status

- State: `implemented`
- Priority: `highest`
- Owner: `Repo A mainline migration`
- Synced to repo: `2026-04-17`

## In Scope

- 新录制入口 `teleop_v2_1_multi_raw`
- 统一事件检测器 `boundary_detector`
- 新离线标注入口 `tb-label-v2_1`
- `/v2` 新字段扩展
- 多轮 continuity / boundary metrics
- 旧 phase-1 主线删除与文档迁移

## Out of Scope

- scripted transition controller
- hybrid deploy policy
- rule planner
- learned transition
- 新模型训练
- Repo C 协议升级

## Main Deliverables

- `teleop_v2_1_multi_raw.yaml`
- `testbed/planner/boundary_detector.py`
- `tb-label-v2_1`
- `/v2` step/cycle schema 扩展
- `testbed/eval/multi_cycle_metrics.py`
- 主文档和主配置从 ready-anchor 主语义退场

## Recorder Plan

### Recording Mode

- 主录制模式固定为 `teleop_multi_raw`
- episode 为自然连续示教
- 不再要求操作者回 fixed ready pose
- 默认入口配置为 `teleop_v2_1_multi_raw.yaml`
- 默认原始数据目录为 `data/agx_teleop_v2_1_multi_raw`

### Stop Rule

- 主规则：达到 `target_dump_count = 3`
- 达到目标 dump count 后继续录 `teleop.post_success_tail_steps = 50` 步 terminal tail
- 兜底：达到 `task.max_steps = 4000`

### Required Metadata

录制 metadata 必须至少写入：

- `scenario_id`
- `recording_mode = teleop_multi_raw`
- `goal_token_version = v2_1c_sector10d_digarea13`
- `phase_version = v2_1_mode_phase_7cls`
- `target_dump_count = 3`
- `stop_reason = target_dump_count_reached | max_steps_reached`

## Boundary Detector Plan

### Outputs

统一输出以下事件与 mask：

- `qualified_dig_start`
- `dump_start`
- `dump_end`
- `boundary_mask`
- `pause_mask`

### Formal Threshold Table

#### `qualified_dig_start`

至少满足以下条件组合：

- `min_distance_to_dig_area_m <= 0.05`
- `bucket_depth_below_dig_area_plane_m >= 0.02`
- 默认 `qualified_dig_start_mode = "progress"` 时，还需要满足下面二选一：
  - `reward_phase in {"good_dig_start", "load_progress"}`
  - `mass_in_bucket_kg` 在最近 `K = 5` 步内的增量超过 `delta_mass_start`
- 小斗或质量传感器滞后的环境可使用 `qualified_dig_start_mode = "contact_depth"`，
  此时只用上述 dig-area 距离和低于平面的几何条件触发，不要求质量增量。

默认：

- `delta_mass_start = 5 kg`
- `qualified_dig_start_mode = "progress"`

#### `dump_start`

至少满足：

- `min_distance_to_target_m <= target_approach_distance_m`
- `deposited_mass_in_target_box_kg` 正在增长

#### `dump_end`

至少满足：

- 该 cycle 内已经发生过 `dump_start`
- `mass_in_bucket_kg <= residual_bucket_mass_thresh`
- `deposited_mass_in_target_box_kg` 平台持续 `N = 3` 步

#### `pause_mask`

- `||action||_1 < 0.05`

## Labeler Plan

### Tool

- 新增 `tb-label-v2_1`

### Input / Output

- 输入：`teleop_multi_raw` 原始 episode
- 默认输出到兄弟目录副本：`data/agx_teleop_v2_1_multi_raw_relabeled`

Stage 1 默认不原地改写 raw 数据，优先保护原始数据。

### Label Contents

必须支持：

- 多 cycle 切分
- `cycle_id`
- `mode_id`
- `phase_id`
- `phase_progress`
- `goal_tokens(10D)`
- cycle summary

## `/v2` Schema Plan

### `/v2/step`

- `cycle_id`
- `mode_id`
- `phase_id`
- `phase_progress`
- `goal_tokens`
- `planner_replan_mask`
- `qualified_dig_start_mask`
- `dump_start_mask`
- `dump_end_mask`
- `boundary_mask`
- `pause_mask`

### `/v2/cycle`

- `cycle_id`
- `start_step`
- `dump_end_step`
- `end_step`
- `curr_src_sector_id`
- `curr_cut_depth_class`
- `next_src_sector_id`
- `next_cut_depth_class`
- `dst_target_id`
- `fill_peak_kg`
- `deposit_delta_kg`
- `peak_bucket_depth_m`
- `collision_count_delta`
- `transition_source`
- `cycle_success`
- `plan_source`

### Attributes

- `v2_enabled = true`
- `goal_token_version = "v2_1c_sector10d_digarea13"`
- `phase_version = "v2_1_mode_phase_7cls"`
- `transition_source = "none"`
- `scenario_manifest_version = "v2_1b"`

## Goal Token Plan

### Fixed 10D Definition

- `curr_sector_is_left`
- `curr_sector_is_mid`
- `curr_sector_is_right`
- `curr_cut_depth_norm`
- `next_sector_is_left`
- `next_sector_is_mid`
- `next_sector_is_right`
- `next_cut_depth_norm`
- `dst_target_norm`
- `has_lookahead`

### Source

Stage 1 中，所有 token 全部来自离线重建，不要求在线 planner 已存在。

## Phase Plan

统一 7 类：

- `0 dig_contact`
- `1 cut_fill`
- `2 lift_clear`
- `3 transport`
- `4 dump`
- `5 transition_corridor`
- `6 transition_wait_next_dig`

`phase_progress` 在本阶段固定按 phase span 内时间归一化生成，不做更复杂的 event-based progress。

## Metric Plan

新增多轮指标：

- `dump_to_next_dig_gap_steps`
- `pause_ratio`
- `boundary_jump_l1`
- `boundary_jump_l2`
- `mean_action_jerk`
- `cycle2_success_rate`
- `cycle3_success_rate`
- `carry_over_drop`

## Cycle Boundary Special Case

- 正常 cycle 定义保持：
  - `cycle_i.start = qualified_dig_start(i)`
  - `cycle_i.end = qualified_dig_start(i+1)`
- 但 Stage 1 主录制线按第 `3` 次 `dump_end` 停，所以最后一轮允许使用唯一 terminal 特判：
  - 当 `stop_reason = target_dump_count_reached` 时
  - 最后一轮可以在自己的 `dump_end_step` 闭合
  - 此时 `end_step = dump_end_step`
  - 当前 recorder 会在 terminal `dump_end` 后保留 `50` 步 tail，避免最后一次 post-step observation 丢失
  - 离线 relabel 对旧 no-tail raw 仍允许用 metadata 近似恢复 terminal `dump_end_step`
- 如果 episode 因 `max_steps_reached` 结束：
  - 尾轮保持 `incomplete`
  - `dump_end_step` 有则写，没有则留空
  - `end_step = -1`
  - `cycle_success = 0`
  - 不计入 `cycle2_success_rate / cycle3_success_rate / dump_to_next_dig_gap_steps`

## Interface / Config Changes

### Add

- `teleop.target_dump_count`
- `task.recording_mode = teleop_multi_raw`
- `task.scenario_id`
- `task.goal_token_version`
- `task.phase_version`

### Remove from Mainline

- `teleop.stop_mode = dump_plus_ready`
- `teleop.ready_anchor_hold_steps`
- `teleop.ready_anchor_hit_threshold`

## Deletion / Migration

### Repo A

主线删除或退场的对象包括：

- `dump_plus_ready` 作为主 stop 逻辑
- `_ReadyAnchorHoldTracker` 作为主线依赖
- 任何基于 `ready_anchor_reached` 的主 stop 逻辑
- `return_ready` 作为当前 V2 主 phase 语义
- `teleop_v2_cycle_*` 作为主线入口的角色

### Repo B

从主流程和主文档中移除：

- `Ready Anchor Guide` 作为当前主工作流说明
- `ReadyAnchorWorldMarker` 作为当前主工作流说明
- “操作者回到 anchor_mid 后停录”之类的主工作流描述

### Repo A / Repo B Docs

移除或改写：

- “当前主 primitive 是 `ready -> dig -> transport -> dump -> ready`”
- “V2 录制必须回固定 ready pose”

## Tests

- `teleop_multi_raw` smoke 录制测试
- boundary detector 单测
- labeler 多 cycle 切分单测
- `/v2` 新字段写读单测
- 多轮 metrics 单测
- 旧 `v1/v0` reader 兼容测试

## Acceptance Criteria

- 能录 1 条在第 `3` 次 `dump_end` 自动结束的 raw demo
- terminal `dump_end` 后保留约 `50` 步 tail observation
- 不要求回 ready pose
- 能离线切出 `cycle_id / start_step / end_step`
- evaluator 能产出多轮边界和 gap 指标
- 主配置和主文档中不再依赖 ready-anchor 主语义

## Risks and Stop Conditions

- 如果 `qualified_dig_start` 在自然 teleop 上误检率很高，暂停 Stage 2，先修 detector
- 如果 raw 录制无法稳定得到 `3` 个 cycle，暂停后续训练，先修 stop 规则
- 如果 `/v2` 字段定义与现有 reader 冲突，优先修 schema 兼容，不推进 Stage 2
