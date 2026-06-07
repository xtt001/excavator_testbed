# 数据处理、HDF5 字段与 QC 逻辑

本文是当前数据录制、relabel、primitive 切分、HDF5 字段和 QC 逻辑的集中说明。
Planner/ACT 层级契约只描述 policy 消费哪些 token；数据如何产生、如何筛选、如何证明可训练，
以本文为准。

## 当前依据

当前实现依据这些代码路径：

- HDF5 schema 和 `env_state` 顺序：`testbed/data/schema.py`
- 原始 episode QC：`testbed/data/qc.py`
- operator-first token relabel：`testbed/data/operator_first_v2_2.py`
- V2.4 hindsight outcome relabel：`testbed/data/hindsight_goal_v2_4.py`
- 四 primitive 切分：`testbed/data/primitives_v2_2.py`
- V2.4.5 pipeline 和 pre-materialize QC：`testbed/cli/build_v2_4_hindsight_pipeline.py`
- 边界可视化审计：`testbed/cli/audit_primitive_boundaries.py`
- VDS / materialize / virtualize：`testbed/data/vds.py`、`testbed/data/materialize.py`、
  `testbed/data/virtualize_images.py`

## 总体链路

当前主线是分阶段的，不是从 raw 一步直接写最终训练集。

```text
raw full-cycle / replay refreshed root
  -> tb-dataset-qc                         # 原始 HDF5 可读性、shape、NaN、长度、图像检查
  -> tb-label-v2_1                         # add-only /v2 基础标签和 cycle 搜索坐标
  -> tb-build-operator-first-v2_2           # dig_cut_tokens / return_target_tokens / operator cycle fields
  -> tb-build-hindsight-goal-v2_4           # dig/return outcome targets、removed-depth outcome
  -> tb-build-primitives-v2_2
       --boundary-profile v2_4_5_spatial_mass
                                           # material-cycle ownership 切 dig/carry/dump/return
  -> gate1: 04_pre_materialize_qc.json      # primitive VDS 数字 QC
  -> gate2: tb-audit-primitive-boundaries   # timeline、videos、contact sheets、人工边界复核
  -> tb-materialize-vds                     # 写 materialized primitive training copy
  -> gate1b: materialized-copy QC           # 图像必须不再是 virtual
  -> train / eval / offline audit
```

分阶段的原因：

- `tb-label-v2_1` 提供稳定 `/v2` 标签层和旧专业操作边界锚点，例如
  `qualified_dig_start`、`dump_end`、cycle 搜索窗口。当前主线不把它当最终
  ownership 真相，但仍用它做 replay refresh、跨版本重切和错误诊断的坐标系。
- `tb-build-primitives-v2_2` 保留四 primitive sibling dataset 的输出契约和 CLI 入口。
  当前通过 `--boundary-profile v2_4_5_spatial_mass` 使用 V2.4.5 material-cycle 语义；
  文件名里有 `v2_2` 不代表还在使用 V2.2 的旧边界。
- VDS 中间层让大图像继续指向 source episode，只把 `/v2` overlay、metadata、lineage 和
  QC 字段本地 materialize。坏边界可以停在轻量 VDS 阶段修，不必先复制大量图像。
- replay refreshed root 只提供新的 `env_state`、removed-depth 和图像；如果重新用 progress
  detector 推断 `/v2` cycle，可能漏掉下一次 dig-start，把多个周期粘成超长 return。
  因此刷新 replay 时必须用 `--v2-label-source-dir <已QC的v2_2 relabeled root>` 转移原始
  `/v2` 边界，再用 V2.4.5 material-cycle 语义重切。

## 版本层和 qc6

`qc6` 是数据重切/QC 的 run tag，常见于
`v2_4_5_process_boundary_qc6_20260522`、`qc6labels_scale080`。它不是传感器名、
模型结构名，也不是通用质量分数。它表示 V2.4.5 process-boundary/surface-depth 这条线
经过 `qc4 -> qc5 -> qc6` 人工 contact-sheet 复核和边界收紧后，被接受为 copy/train/eval
主数据源的标签版本。

qc6 的核心变化是把 `dump_start` 从“未来会倒土”后移到“bucket 已经进入 dump-area
committed aiming / release 附近微调”。仍在明显向 dump area 移动的窗口归 `carry`，
不让 `dump` 吞掉长距离 transport。

## 数据录制和 relabel 演化

1. V1：录制固定工位、固定 truck 的单铲 demo，建立 HDF5、训练、eval、QC、视频导出链路。
2. V2.1：改成自然连续多铲 raw，用 `tb-label-v2_1` 写 add-only `/v2` labels：
   `qualified_dig_start`、`dump_start`、`dump_end`、mode/phase/work_stage、`goal_tokens`、
   `/v2/cycle/*`。早期 cycle 是 `qualified_dig_start(i) -> qualified_dig_start(i+1)`。
3. V2.1 workskill / transition：先把长任务裁成
   `qualified_dig_start -> dump_end` 和 `dump_end -> next qualified_dig_start`，避免直接训练
   full-cycle。
4. V2.2：确认四 primitive ownership 是稳定主线，从自然 full-cycle raw 离线切
   `dig/carry/dump/return`，录制规则改成 task-level：专业师傅自然完成作业，不要求按
   primitive 停顿。
5. V2.3 / V2.3.5：探索 parameterized dig、surface-depth、hard chunk barrier 和
   effect-based boundary，结论是 planner intent、policy 实际动作、removed-depth outcome、
   deposit outcome 必须分开记录。
6. V2.4 / V2.4.5：不是从无到有发现专家 actual cut，而是把专家自然操作中已经存在的
   actual cut、payload、deposit、next-entry return target 离线抽取成稳定字段，并用
   material movement 的证据重新切 `dig/carry/dump/return` 四个 primitive，使 token、
   边界和训练责任一致。

这里的 material cycle 指“一铲物料”的因果闭环，而不是旧 `/v2/cycle` 名义边界本身。
它从 bucket 接触/进入 dig area 开始，经过 bucket mass 或 removed-depth 增加、带料离开
dig area、接近 dump area、发生 release/deposit、bucket 剩余质量低位稳定，最后到达下一轮
dig-start envelope。V2.4.5 的重切逻辑就是在这个 material cycle 内重新划分：
`dig = 入土/装料责任`，`carry = 带料运输责任`，`dump = committed aiming/release/deposit 责任`，
`return = dump 完成后回到下一铲可接管入口的责任`。

## HDF5 字段

### 基础 episode 字段

当前基础 schema 是 `1.1`，`/v2` 仍是 add-only extension，不通过删除/改名破坏旧读写。

| 路径 / attr | shape / 类型 | 语义 |
| --- | --- | --- |
| `/metadata` attrs | attrs | `schema_version`、`task_name`、`sim_backend`、`seed`、`timestamp`、`control_hz`、`dt`、`camera_names`、`image_format`、`recording_mode`、`scenario_id`、`env_state_order` 等 episode 元数据 |
| `/observations/qpos` | `(T, 4) float32` | `[swing, boom, stick, bucket]` position norm |
| `/observations/qvel` | `(T, 4) float32` | 同顺序速度 |
| `/observations/env_state` | `(T, 64) float32` | AGX/Unity 状态和几何事实，见下一节 |
| `/observations/images/fpv` | `(T, H, W, 3) uint8` | FPV 图像；VDS 阶段可为 virtual，训练 copy 必须 materialized |
| `/action` | `(T, 4) float32` | `[swing, boom, stick, bucket]` actuator speed command |
| `/rewards` | `(T,) float32` optional | 诊断/兼容字段 |
| `/timestamps/step_id` | `(T,) int64` | step 序号，QC 要求单调 |
| `/timestamps/step_ns` | `(T,) int64` optional | 时间戳 |
| `/action_source/type`、`/action_source/id` | `(T,) string` | teleop / policy / scripted 来源 |

### 当前关键 `env_state` 字段

`env_state_order` 的完整顺序在 `testbed/data/schema.py`。下表列出当前切分和 QC 最常用的
字段。

| index | 名称 | 用途 |
| --- | --- | --- |
| 0 | `mass_in_bucket_kg` | dig payload、dump release、dump completion、carry 掉料 |
| 3 | `deposited_mass_in_target_box_kg` | target deposit 变化 |
| 7 | `min_distance_to_dig_area_m` | dig start / return entry ready / dig departure |
| 8 | `bucket_depth_below_dig_area_plane_m` | plane-depth 参考；handoff 诊断和 fallback |
| 10 | `bucket_height_above_target_rim_m` | dump committed aiming 高度门 |
| 11 | `bucket_over_target_footprint_mask` | release/dump near-target 条件 |
| 12 | `dump_clearance_ok_mask` | dump clearance 诊断 |
| 13-15 | `bucket_dump_area_relative_x/z_m`、`bucket_dump_area_footprint_outside_distance_m` | carry/dump ownership、dump_start 稳定带 |
| 16 | `bucket_dig_area_cell_in_bounds_mask` | dig area 几何可用 / cell 内 |
| 23-24 | `bucket_dig_area_long_norm`、`bucket_dig_area_short_norm` | normalized dig box 判断 |
| 31 | `bucket_depth_below_local_surface_m` | 当前主线 dig command depth 和 entry/contact 语义 |
| 33-38 | `dig_area_surface_depth_m_r{0..2}_c{0..1}` | 3x2 dig area surface-depth grid |
| 39-44 | `dig_area_removed_depth_m_r{0..2}_c{0..1}` | 3x2 removed-depth grid，用于 outcome/QC |
| 45-50 | `dig_area_target_depth_m_r{0..2}_c{0..1}` | 3x2 target-depth grid |
| 51-56 | `dig_area_cell_valid_mask_r{0..2}_c{0..1}` | 3x2 cell valid mask |
| 57 | `bucket_mass_delta_kg` | 质量变化诊断 |
| 58 | `deposited_mass_in_dump_area_kg` | dump-area deposit |
| 59 | `offtarget_deposited_mass_kg` | off-target deposit 污染 |
| 61 | `bucket_dig_area_penetration_contact_mask` | dig contact/readiness；schema 里也作为 `bucket_contact_dig_area_mask` legacy alias |
| 62 | `bucket_contact_dump_area_mask` | dump contact 诊断 |
| 63 | `hard_collision_count` | 碰撞 QC |

### `/v2/step` 字段

| 路径 | shape | 语义 |
| --- | --- | --- |
| `/v2/step/cycle_id` | `(T,) int32` | 旧 cycle id；当前只作搜索/诊断坐标 |
| `/v2/step/mode_id`、`phase_id`、`phase_progress`、`work_stage_id` | `(T,)` | 旧 mode/phase/stage 标签；可用于 reject/QC，不是 V2.4.5 ownership 真相 |
| `/v2/step/goal_tokens` | `(T, 10) float32` | 早期 goal-conditioning 兼容字段 |
| `/v2/step/action_loss_mask` | `(T,) uint8` | 动作监督 mask |
| `/v2/step/planner_replan_mask` | `(T,) uint8` | planner replan 诊断 |
| `/v2/step/qualified_dig_start_mask` | `(T,) uint8` | V2.1 起点锚点 / material sub-cycle 搜索参考 |
| `/v2/step/dump_start_mask`、`dump_end_mask` | `(T,) uint8` | 旧 dump event；当前作为 fallback / 上界 |
| `/v2/step/cell_entry_tokens` | `(T, 10) float32` optional | legacy diagnostic-only cell entry |
| `/v2/step/dig_cut_tokens` | `(T, 10) float32` | 本轮 dig command/intention；见 token 表 |
| `/v2/step/dig_depth_profile_tokens_v1` | `(T, 12) float32` optional | dig retraining add-on depth/profile token |
| `/v2/step/return_target_tokens` | `(T, 10) float32` | 下一铲完整 cut target；当前 return ACT 不直接读取 |
| `/v2/step/return_start_envelope_tokens_v1` | `(T, 18) float32` | return handoff envelope，当前 return ACT 主输入之一 |
| `/v2/step/return_start_envelope_valid_mask` | `(T, 18) uint8` | envelope per-dim validity |
| `/v2/step/dig_outcome_targets` | `(T, 10) float32` | V2.4 hindsight dig outcome target |
| `/v2/step/return_outcome_targets` | `(T, 10) float32` | V2.4 hindsight return outcome target |
| `/v2/step/dig_goal_valid_mask`、`return_goal_valid_mask` | `(T, 10) uint8` | hindsight target validity |
| `/v2/step/pause_mask`、`boundary_mask` | `(T,) uint8` | pause / boundary diagnostics |

注意：`return_relocate_tokens_v1` 当前是 loader 派生 view，不是 HDF5 存储字段。它来自
`return_target_tokens`，但 depth/payload 被 mask 掉，只作为 return-relocate 训练/评测线的
额外 low-dim。

### `/v2/cycle` 字段

| 字段 | 语义 |
| --- | --- |
| `cycle_id`、`start_step`、`dump_end_step`、`end_step` | 旧 cycle 搜索窗口和上界 |
| `curr_src_sector_id`、`curr_cut_depth_class`、`next_src_sector_id`、`next_cut_depth_class`、`dst_target_id` | 早期 sector/target 语义 |
| `fill_peak_kg`、`deposit_delta_kg`、`peak_bucket_depth_m`、`collision_count_delta` | 旧 cycle 结果指标 |
| `cycle_success`、`dig_success`、`carry_success`、`dump_success`、`return_success`、`return_required`、`stage_success*` | stage success / failure 兼容字段 |
| `payload_gain_kg`、`carry_loss_before_dump_kg`、`dump_deposited_fraction`、`residual_bucket_mass_after_dump_kg` | stage-level 结果 |
| `cycle_effective_deposit_delta_kg`、`legacy_dump_end_deposit_delta_kg`、`dump_window_deposit_delta_kg` | operator-first deposit 重新计算字段 |
| `operator_entry/exit_*`、`operator_cut_*`、`next_operator_*` | 从专业操作实际轨迹反推的 dig cut / 下一铲 cut |
| `return_entry_delta_*`、`return_target_source` | return 是否回到下一铲 entry 附近的 outcome |
| `training_tier` | `gold` / `silver`；训练默认只用 gold |
| `actual_removed_depth_delta_grid` | `(K, 6)`，每个 cycle 的 3x2 removed-depth delta |
| `dominant_removed_depth_cell_id` | 最大 removed-depth delta 的 cell |
| `depth_outcome_source` | removed-depth outcome 来源 |
| `dig_outcome_payload_gain_kg`、`dig_outcome_effective_deposit_delta_kg` | hindsight outcome 指标 |
| `return_outcome_entry_delta_norm_m`、`handoff_outcome_source` | return handoff outcome |

### token 维度

`dig_cut_tokens` 和 `return_target_tokens` 共享 10D contract：

| dim | 语义 |
| --- | --- |
| 0-1 | entry x/z，按 `2.0m` 归一化 |
| 2-3 | exit x/z，按 `2.0m` 归一化 |
| 4-5 | cut direction x/z |
| 6 | cut length，按 `2.0m` 归一化 |
| 7 | command depth，当前主线优先使用 surface-relative penetration，按 `0.80m` 归一化 |
| 8 | payload target，按 `60kg` 归一化 |
| 9 | valid |

`dig_cut_tokens[7]` 的来源优先级是：

1. `bucket_depth_below_local_surface_m` 的窗口峰值，source 为
   `env_state_surface_penetration`。
2. `bucket_depth_below_dig_area_plane_m` fallback，source 为
   `env_state_plane_penetration_fallback`。
3. `actual_removed_depth_delta_grid` fallback，source 为
   `env_state_removed_depth_delta_fallback`。
4. 都不可用时写 0，source 为 `unavailable_or_legacy_zero`。

`return_start_envelope_tokens_v1` 是 18D：

| dim | 语义 |
| --- | --- |
| 0 | next dig-start `bucket_dig_area_long_norm` |
| 1 | next dig-start `bucket_dig_area_short_norm` |
| 2 | local-surface depth center |
| 3 | depth half-width，当前 builder 默认 `0.20` |
| 4-5 | depth min/max envelope |
| 6 | contact flag |
| 7-10 | qpos center |
| 11-14 | qpos half-width，来自下一轮 start 后 40-step window 的 p90-p10 半宽，clip 到 `[0.02, 0.35]` |
| 15 | qvel abs max |
| 16 | token valid |
| 17 | envelope available |

`dig_depth_profile_tokens_v1` 是 12D add-on：
`dominant_cell_id_norm`、`removed_depth_target_norm`、`payload_target_norm`、
`effective_deposit_target_norm`、`cut_length_norm`、`entry_reference_depth_norm`、
`exit_reference_depth_norm`、`peak_reference_depth_norm`、
`peak_surface_penetration_est_norm`、`plane_minus_surface_penetration_offset_norm`、
`contact_fraction`、`valid`。

## 当前四 primitive 切分

这里的 `skill` 按行为层理解，等价于四个 ACT primitive / option：
`dig`、`carry`、`dump`、`return`。下面是 V2.4.5/surface-depth/qc6 主线离线切分语义。
它是训练窗口 ownership，不等同于在线 rollout 的 causal switch。

| Primitive | 起点 / 切入 | 终点 / 切出 | 接受/拒绝重点 |
| --- | --- | --- | --- |
| `dig` | material cycle 搜索窗口内 first dig contact/depth：`dig_area_geometry_available > 0.5` 且 `bucket_contact_dig_area_mask > 0.5`，或 `bucket_depth_below_local_surface_m > 0.005m`。缺少可靠 `env_state` 时 fallback 到旧 cycle start。 | `bucket_mass` 接近本轮峰值且停止明显增长，同时 bucket 稳定离开 dig area。阈值：质量增长 `0.35kg`、近峰容差 `max(3kg, total_gain * 10%)`、未来新增容差 `max(2kg, total_gain * 3%)`、plateau `8` steps；离开 dig area 要 `min_distance_to_dig_area > 0.08m` 或不在 normalized dig box，且 `contact <= 0.5`、local depth `<= 0.02m`，hold `3` steps。 | gold dig 必须有可靠 surface-relative depth；dig 内不能出现 dump/target deposit 增加。 |
| `carry` | 从 `dig_end` 开始。 | 到 `dump_start` 为止。`dump_start` 是 release 前 committed aiming band 第一帧，不是 release 本身。 | 包含带料运输和 dump 前预姿态调整。dump 前 deposit contamination 红线是 `deposit_delta > 5kg AND deposit_delta / payload_loss > 10%`，触发 reject。 |
| `dump` | 先找 `release_onset`：dump area 近邻 `outside <= 0.45m` 或 `over_target_footprint > 0.5`，同时 `bucket_mass_drop >= 0.5kg` 或 `deposit_gain >= 0.5kg`。再从 release 往前最多 `120` steps 找 committed aiming band：`outside <= 0.25m` 或 over footprint，height above rim `>=0.45m`，relative corridor `x=[-0.2,1.9]`、`z=[0.45,2.1]`，20-step 窗口 outside range `<=0.06m`、total approach `<=0.10m`、relative x/z range `<=0.16/0.10m`。fallback 到 `outside <=0.30m` 的 late pre-release candidate，最多 release 前 `15` steps。 | release 后 residual bucket mass 低位稳定：residual limit `min(15kg, release_mass * 0.35)`，下限 `5kg`；30-step plateau 内 mass range `<=2kg` 且 deposit gain `<=2kg`；最多搜到 release 后 `480` steps。 | dump 不应吞掉长距离 transport；qc6 的主要修复就是把过早 dump ownership 后移。 |
| `return` | 从 `dump_end` 开始。 | 到下一轮 first next-dig entry ready：在下一轮 material start 附近 `dig_area_geometry_available >0.5`，且 `min_distance_to_dig_area <=0.05m`、或 `bucket_contact_dig_area_mask >0.5`、或 local depth `>=0.005m`。实现里 end 是 `handoff_step + 1`。 | terminal cycle 不产 return；transition 超过 `512` steps 作为 overlong return reject。 |

material cycle 的基本证据链：

1. bucket 在 dig virtual box 内接触/入土。
2. bucket mass 或 removed-depth grid 出现有效 material movement。
3. bucket 带料离开 dig box 并接近 dump area。
4. 在 dump area 内发生 mass drop，并伴随 target/dump/offtarget deposit 增加。
5. residual bucket mass 回到低位并稳定，然后进入 return。

多 pulse 和 realign：

- 旧 `/v2/cycle` 内多个 `load -> release` material pulse，优先拆成 material sub-cycle。
- material cycle 内有 `replay_pose_realign_steps`，该子轮 `dig/carry/dump` reject。
- realign 落在 return window 内，只 reject 对应 return。
- realign 正好落在下一轮 start/qds 帧时，只归属下一轮，不污染前一轮 clean return。

## QC 逻辑

### 原始 episode QC

`tb-dataset-qc` / `testbed.data.qc.run_dataset_qc` 检查：

- episode 是否可读。
- `action/qpos/qvel/env_state/images` 是否存在、shape 是否对齐。
- episode 是否过短，默认短 episode 阈值是 `50` steps。
- `step_id` 是否单调，`step_ns` 是否存在。
- 数值是否有 NaN / Inf。
- `env_state_order` 是否一致。

输出包括 `summary.json`、`episodes.csv`、episode length / action distribution / state range plots。

### operator-first gold/silver

`tb-build-operator-first-v2_2` 根据实际操作轨迹写 `dig_cut_tokens`、
`return_target_tokens` 和 operator cycle fields。

`training_tier=gold` 的当前必要条件：

- cut pose 有效。
- depth source 可靠，即 `operator_cut_depth_source == env_state_surface_penetration`。
- `payload_gain_kg >= 35kg`。
- `effective_deposit_delta_kg >= 5kg`。
- `operator_cut_length_m >= 0.20m`。
- `operator_cut_depth_peak_m >= 0.02m`。

不满足则保留为 `silver`，用于诊断和 audit，但训练默认过滤到 gold。

### pre-materialize Gate 1

`tb-build-v2_4-hindsight-pipeline` 在 materialize image copy 前写
`runs/jobs/<job>/logs/04_pre_materialize_qc.json`。默认不跳过；失败会停在轻量 primitive VDS。

主要检查和默认阈值：

| 检查 | 默认阈值 / 条件 | 目的 |
| --- | --- | --- |
| primitive count | `dig > 0`、`dump > 0`、`return > 0` | 防止空数据继续训练 |
| gold dig depth source fraction | `>= 0.95`，required source 当前默认 `env_state_surface_penetration` | 防止用旧 removed-depth/fallback 作为主 command depth |
| gold depth token saturation | `dig_cut_tokens[:,7] >= 0.999` 的比例 `<= 0.02` | 防止 depth token 饱和失去区分度 |
| gold depth token spread | p90-p10 `>= 0.05` | 防止 depth token 分布塌缩 |
| gold depth token nonzero fraction | `>= 0.90` | 防止 depth 全部接近 0 |
| dump length | max `<= 768`，p95 `<= 640` | 防止 dump 吞入 return/next cycle |
| dump transition contamination | transition mode/phase fraction max `<= 0.0` | 防止 dump 混入 transition |
| carry deposit contamination | `deposit_delta > 5kg AND ratio > 0.10` 的 episode 数必须为 0 | 防止 carry 已经在倒土 |
| dump pre-release lead | max `<= 120` steps | 防止 dump_start 太早 |
| return envelope valid | episode-level valid fraction `>= 0.95` | 防止 return 缺少 handoff envelope |
| return/dig count ratio | `>= 0.75` | 防止 next dig-start 漏检导致 return 大量丢失 |
| return max length | `<= 512` steps | 防止 return 吞入等待/恢复片段 |
| overlong return reject ratio | `<= 0.10` | 捕获 cycle 粘连和 next QDS 漏检 |

### boundary visual Gate 2

`tb-audit-primitive-boundaries` 读取 `window_manifest.json`，导出：

- `boundary_audit/summary.json`
- `boundary_audit/boundary_audit.csv`
- `boundary_audit/videos/`
- `boundary_audit/contact_sheets/index.html`
- `boundary_audit/contact_sheets_clean_gold/index.html`

V2.4.5 主线默认在 Gate 2 暂停，要求人工审阅 contact sheet / video 后再用
`--ack-feedback-gates` 继续。

风险 flag：

- `non_gold`
- `short_window`：window length `< 40`
- `low_dig_payload`：dig payload `< 15kg`
- `low_effective_deposit`：dump effective deposit `< 15kg`
- `return_target_gap`：return entry delta `> 0.20m`
- `carry_mass_loss`：carry bucket mass loss `> 5kg`
- `carry_dump_transition_tight`：carry end 距 release `<= 2` steps
- `early_dump_ownership_vs_official`：carry/dump gap `> 120` steps
- `dump_start_outside_footprint`：dump start outside distance `> 0.30m`

`clean_gold_contact_sheet` 只选 `training_tier=gold` 且 `risk_flags=none` 的样本，用来做直观
正常样本复核；top-risk sheet 用来优先看边界异常。

### materialized-copy Gate 1b

`tb-materialize-vds` 后 pipeline 会检查 materialized primitive copy：

- `dig/carry/dump/return` episode 数。
- `dig` 和 `return` 必须非空。
- `dig` 和 `return` 的第一条 episode image dataset 必须 `is_virtual=False`。
- 首条 episode 是否有 `v2/step/dig_outcome_targets` 和
  `v2/step/return_outcome_targets`。
- metadata 中 `storage_mode`、`primitive_storage_mode` 是否符合预期。

### 训练侧过滤

当前训练默认使用 materialized primitive copy，并通过 metadata filter 选
`training_tier=gold`。全量 primitive VDS 仍保留 silver 诊断样本；silver 不应静默进入主线
训练，除非实验明确声明。

## 内存和磁盘策略

- raw 数据只读，不在原始 human raw 上覆盖 relabel。
- relabel、operator-first、hindsight、primitive split 都写 sibling directory。
- 中间层优先使用 HDF5 VDS：大图像保留在 canonical source，wrapper 本地只写小字段。
- 只有通过 pre-materialize QC 和边界审阅后，才把 primitive VDS materialize 成训练 copy。
- materialize 使用 episode/window 级并行，常用 `--materialize-workers 16`、
  `--image-batch-size 16`。
- 长任务建议 `--detach` 后台运行，避免 IDE 和 image copy 同时争用内存。
- 训练完成并确认 `policy_best.ckpt` 后，可以删除 materialized primitive copy，只保留
  primitive VDS 作为可重建来源。
- 已有 materialized 数据若要轻量归档，可用 `tb-virtualize-images` 把图像替换成指向
  canonical source episode 的 VDS link，同时保留 low-dim 本地数据。

## 维护规则

- 新 HDF5 字段必须 add-only，不删除、不改名旧字段。
- Token 维度、顺序、scale 和 source 字符串应在代码 source-of-truth 中集中定义，再被
  train/eval/rollout 读取。
- 新数据语义必须同时更新本文、schema/contract 文档和一致性测试或 QC gate。
- legacy、diagnostic、ablation 字段必须标明用途，不应静默变成主线训练输入。
