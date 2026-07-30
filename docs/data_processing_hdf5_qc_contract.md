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

## 2026-07-23 strict-18 训练数据合同

box-emptying residual planner 本轮只允许使用以下 strict source episode：

```text
3, 6, 7, 8, 9, 13, 16, 19, 23, 24, 25, 27, 28, 29, 30, 32, 33, 34
```

公共 VDS text codec 对原始 bytes、`b'...'` 和最多四层嵌套 bytes-repr 做安全
canonical decode；无法在边界内规范化时直接报错，不保留隐式 fallback。修复链只从
strict manifest 重建新 no-overwrite VDS，禁止扫描 partial/layered salvage。固定输出为：

```text
/data/pingfan/excavator_testbed_data/yulong_strict18_terrain_residual_v0/
```

primitive 使用 `v2_4_5_spatial_mass` boundary profile，审核通过后才从 VDS
materialize 为普通 HDF5。新 primitive id 必须携带 `source_episode_id`；episode 33/34
只属于 validation，其余 16 条只属于 train。四个 primitive 各有显式 split 文件，
任何 source episode 跨 train/validation 都是 hard failure。

strict-18 数据发布 gate 同时要求：full-episode step/mask 计数与原 strict root 完全
一致；所有字符串无嵌套 repr；四路 JPEG sentinel 可解码；primitive 非空且 materialized
copy 不含 virtual dataset；lineage 中出现 partial salvage 立即失败。当前通过报告为
`qc/data_readiness.json`，batch 4 的 loader/gradient 报告为
`qc/batch4_gradient_preflight.json`。这些报告证明训练数据就绪，不替代 policy audit 或
真实 Unity closed-loop validation。

effect sample 的 pre/post 都使用 10-step stable window。pre 是 operator entry 前最后
一个稳定窗口；post 是 operator exit 后 150 steps 内第一个稳定窗口，并以
`/v2/step/work_stage_id == dump` 的首帧作为硬上界，整个窗口必须在 dump 前结束。
当前 no-overwrite 重建结果是 439/439 eligible、0 reject，写入
`qc/executed_cut_silver_{records,manifest}_predump_support_v1.*`。manifest 同时保存从
439 条 executed cut 直接计算的 strict-18 p01-p99 support envelope；planner 不得手工
放宽该 envelope 来隐藏 OOD candidate。

## 检查类型命名与边界

本文主责是 `data QC`，但训练、eval 和 LLM planner 前证据门禁会继续消费这些证据。当前
检查类型按阶段命名如下：

| 名称 | 发生阶段 | 责任边界 |
| --- | --- | --- |
| `data QC` | 训练前 | 检查 raw / VDS / materialized copy、HDF5 字段、mask、primitive 边界和 reject 统计。本文是该层主要 source of truth。 |
| `policy audit` | 训练后、eval 前 | 在 recorded stream 上离线检查 checkpoint 行为，判断 policy 是否已经不跟 token 或不跟专家。它不重做数据 QC。 |
| `policy audit manifest` | eval 前 | 汇总已有 policy audit JSON，生成可进入 rollout 的证据清单。缺失项只能标为 `missing`，不能伪造通过。 |
| `rollout review` | eval 后 | 检查真实闭环表现，包括 planned vs actual、handoff、coverage trace 和 terminal reason。它只做诊断，不改变 eval success 语义。 |
| `root-cause audit` | rollout review 发现明确症状后 | 定位问题来自 policy、token 语义、handoff、live scaling、planner belief 还是数据/QC 回流问题。 |

因此，`data QC` 通过只代表训练数据和 primitive 切分证据可用；它不能替代训练后
`policy audit`，也不能证明真实闭环 rollout 已经跟手。

## 总体链路

当前主线是分阶段的，不是从 raw 一步直接写最终训练集。

```text
raw full-cycle / replay refreshed root      # 输入：自然 full-cycle 或 replay refresh 后的 episode root
  -> tb-dataset-qc                         # 读取原始 HDF5，检查可读性、shape、NaN、长度和图像帧
  -> tb-label-v2_1                         # 写入 add-only /v2 基础标签，建立 cycle 搜索和诊断坐标
  -> tb-build-operator-first-v2_2           # 从专家轨迹反推 dig_cut/return_target tokens 和 operator cycle 字段
  -> tb-build-hindsight-goal-v2_4           # 计算并检查 dig/return outcome targets 和 removed-depth outcome
  -> tb-build-primitives-v2_2
       --boundary-profile v2_4_5_spatial_mass
                                           # 按 material-cycle ownership 重切并生成 dig/carry/dump/return primitive VDS
  -> gate1: 04_pre_materialize_qc.json      # 对 primitive VDS 做数字 QC：长度、mask、字段、边界和 reject 统计
  -> gate2: tb-audit-primitive-boundaries   # 导出 timeline、videos、contact sheets，人工复核 primitive 边界
  -> tb-materialize-vds                     # 将通过审计的 primitive VDS 写成 materialized primitive training copy
  -> gate1b: materialized-copy QC           # 复查 materialized copy：图像数据必须实体化，不再是 virtual
  -> train / policy audit / audit manifest  # 使用训练 copy 训练，并保留 eval 前 checkpoint 证据
  -> eval / rollout review / root-cause audit
                                           # 用真实闭环表现检查 planned-vs-actual、handoff、coverage 和 terminal reason
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
- `tb-replay --diagnostic-log` 的 JSONL 是 replay 刷新前后的诊断证据，不是训练字段。
  当 Unity step-ack response 携带 `warnings` 或 reset response 携带 `reset_warnings` 时，
  diagnostic step record 会透传 `warnings_before`、`warnings_after` 和
  `reset_warnings_before`，用于检查 reset seed、soil/native reset、contact-force 等
  Unity 侧诊断状态。QC/训练不得把这些 warnings 当作 HDF5 schema 字段或 gold label。
- 当前 Unity replay relabel 方差评估是单独的 silver 数据轨道：旧 HDF5 只作为只读
  trajectory source，在当前 Unity 分支下重复 replay 后，用
  `tb-terrain-replay-relabel-stats` 汇总 `payload_mass_kg`、`effective_deposit_mass_kg`
  和 removed-depth delta grid 的 repeat variance。该命令输出
  `terrain_replay_relabel_stats_v1` report 和
  `terrain_replay_relabel_cycle_sample_v1` JSONL；它不写官方
  `terrain_gold_cycle_sample_v1`，也不把旧 HDF5 label 当成 truth。
  A 档可作为 `current_unity_replay_relabel` fine relabel 候选，B 档必须携带
  uncertainty / lowered `recommended_weight`，C 档只能诊断或粗粒度使用。进入
  V2.4/V2.4.5 数据链时仍必须传入已 QC 的 `--v2-label-source-dir`，不得用 replay
  refresh 结果重新推断 `/v2` 边界。

## 2026-07-17 固定批次：清洗、Replay 与证据边界

本轮唯一允许的输入是：

```text
/data/pingfan/excavator_testbed_data/yulong_v2_2_pro_full_task_four_camera_jpeg_20260717
```

`tb-build-terrain-clean-dataset` 会先把输入解析为 realpath，再要求目录中恰好存在
`episode_0.hdf5 .. episode_35.hdf5`。旧 26 条以及任何其他目录都不能被扫描、读取或写入
lineage；目录不相等或 episode inventory 不精确时直接失败。默认输出是新的 no-overwrite
目录：

```text
/data/pingfan/excavator_testbed_data/yulong_v2_2_pro_full_task_four_camera_jpeg_20260717_cycle_clean_v1
```

固定 VDS 链为：

```text
raw 36
  -> labels_v2_1_vds
  -> operator_first_vds
  -> hindsight_vds
  -> clean_all_vds
       |-> post_fix_default_vds       # episode_22..35；默认池
       `-> pre_fix_salvage_vds        # episode_0..21；仅 salvage/ablation
```

原 HDF5 始终只读：不删行、不重采样、不覆盖。builder 在执行前后对每个 source 的 size、
mtime、realpath 及完整 HDF5 dataset shape/dtype/VDS 结构做相等性检查。核心审计产物是
`source_manifest.json`、`contamination_windows.jsonl`、`cycle_eligibility.jsonl`、
`field_gap_report.json` 和 `episode_cleaning_report.json`。每个周期分别记录
`act_training_eligible`、`effect_calibration_eligible`、`replay_candidate`、
`review_required` 与 `deposit_label_valid`，不使用单一 `usable` 字段覆盖不同用途。

局部清洗规则如下：

| 污染 | 处理 |
| --- | --- |
| `L1(action) < 0.05` 且 `<2s` | 保留。 |
| 同类停顿 `2–5s` | active work stage 的所在周期进入 review 并从默认池屏蔽；inter-cycle/none 保留。 |
| 同类停顿 `>=5s` | 仅将停顿区间 `/v2/step/action_loss_mask` 置 `0`，不删行，也不自动否决整周期。 |
| `abs(diff(qpos)) >= 0.05` 或 `abs(diff(qvel)) >= 5.0` | 按 `step_ns` 对事件前后各加 `1s` mask guard，只否决事件所在周期。 |
| timestamp gap `>100ms` | 局部 mask；只有同时存在 step-id 缺失/回退或动态断点时，相关周期才被否决 replay。 |
| 全零动作、任何非有限数、缺失整路相机、没有完整周期 | 整条 episode 只进入 diagnostic 清单，不进入三个训练/replay 视图。 |
| 单个 JPEG 损坏 | 只 mask 对应 timestep；其他帧和周期继续保留。 |
| 不完整尾周期 | 禁止 effect/replay；此前干净 ACT 监督仍可保留。 |
| deposited fraction `<0` 或 `>1.05` | 只令 deposit label invalid，不连带否决 terrain/replay。 |

被 reject/review 的周期会同步清零已有 `dig_goal_valid_mask` 和
`return_goal_valid_mask`，防止污染窗口中的 hindsight outcome 继续参与训练。pool VDS 的
mask 还会对被 reject/review 的整周期置零；`clean_all_vds` 保留局部 mask，便于审计不同
用途的可用性。

builder 同时输出完全分离的两个训练 data overlay：

- `training_configs/post_fix_default_data.yaml`：默认启用，只指向
  `post_fix_default_vds`，并过滤 `controller_epoch=post_fix_candidate`。
- `training_configs/pre_fix_salvage_ablation_data.yaml`：默认禁用，只指向
  `pre_fix_salvage_vds`，并过滤 `controller_epoch=pre_fix_candidate`。

两者都要求 `train.action_loss_mask_scope=loss_sampling_stats`，且分别指向各自的
`lineage.json`。这些文件是待合并到具体 ACT 架构 config 的 data overlay，不会隐式决定
policy、checkpoint 或训练超参数。

### 前期 14 条的 current-controller action 校准

clean builder 的 `pre_fix_salvage` 是隔离边界，不是永久弃用结论。经逐 episode
`qvel/action` 审计、录制期场景配置核对，以及 `episode_3` 的接触前 live replay 反证，
本批存在四个归一化 action -> target-speed
合同：

| 录制阶段 | episode 范围 | `[swing, boom, stick, bucket]` max target speed |
| --- | --- | --- |
| early controller | `0..2` | `[0.5, 0.05, 0.05, 0.1]` |
| early boom tuned | `3..17` | `[0.5, 0.07, 0.05, 0.1]` |
| intermediate tuning | `18..20` | `[0.6, 0.07, 0.07, 0.15]` |
| current controller | `21..35` | `[0.7, 0.1, 0.1, 0.2]` |

旧 v1 曾把 `episode_3..17` 的 boom 误归为 `0.05`。源数据在无 digging contact、
高且稳定 action 区间的 response audit 给出 `0.070`，而 `episode_3` replay 在第 65 步
接触前便稳定越过 `qpos` 误差门；两次证据一致。因此
`..._cycle_action_calibrated_v1` 只保留为已证伪假设的诊断 lineage，不再进入 replay 或
training selection。修复只新增 v2，不覆盖 v1。

`tb-build-action-calibrated-dataset` 只读取既有 clean root，并固定选择 14 条有完整训练
内容的前期 episode：`1,3,4,6,7,8,9,10,12,13,14,16,19,20`，以及 10 条 current
reference episode：`23,24,25,27,28,29,30,32,33,34`。原 action、原 clean VDS 和 raw
HDF5 都不修改。每轴校准使用：

```text
current_equivalent_action =
    original_action * source_max_target_speed / current_max_target_speed
```

这保证校准前后的物理 target speed 逐 timestep 等价；它不是按 post action 分布做
quantile fitting，也不伪造更快的专家轨迹。新 wrapper 的顶层 `/action` 是校准后的
current-controller normalized command，`/v2/step/action_original` 永久保留原 command；
metadata 固定写入 source/target profile、四轴 scale 和
`action_contract=yulong_current_equivalent_normalized_speed_v2`。

为隔离旧 limiter 的极少量 back-driven response，builder 从 10 条 current-reference 数据
计算每轴 neutral-action (`abs(action)<0.05`) `abs(qvel)` 的 p99.5 support，并带前后各
50-step guard 写 `/v2/step/action_calibration_valid_mask`。最终训练
`action_loss_mask = clean mask AND calibration-valid mask`，只能进一步屏蔽，不能重新放开
clean mask。阈值、逐 episode mask 数和最大 target-speed 等价误差都写入
`calibration_manifest.json` / `calibration_acceptance_report.json`。

默认 no-overwrite 输出为：

```text
..._20260717_cycle_action_calibrated_v2/
  mixed_current_equivalent_vds/  # 14 calibrated pre + 10 identity post
  pre_calibrated_vds/            # calibrated-pre ablation
  post_reference_vds/            # post-only baseline
  training_configs/
```

该产物只达到 `offline_action_contract_calibration`：可以进入 mixed-training A/B，但不能仅凭
物理 action 等价宣称模型效果或 closed-loop 已通过。正式提升为默认训练池仍需比较
post-only、naive-mix、calibrated-mix，并在 held-out post episode 和当前 Unity 闭环上做
non-inferiority 验证。

Replay 默认的 `post_fix_raw` profile 只能从 `post_fix_replay_selection.jsonl` 选择默认池；
`calibrated_mixed_current_equivalent` profile 则只接受固定 24 条
`mixed_current_equivalent_vds`、统一 action contract 和完整 raw/clean lineage。`tb-replay
--selection-manifest` 会按 episode 合并选中周期，并执行原始 step `0` 到最后一个选中周期
结束的完整因果前缀；mask 区间仍逐 action、逐固定 Unity step 回放。selection 模式强制
zero post-tail，禁止 pose realign，不做墙钟重采样，也不跳过停顿。
`--selection-episode-id` 可用于复用已完成的 pilot、只执行其余 episode；它只过滤执行集合，
manifest 中所有候选行仍先经过 approved-root/source-path 硬门校验，不能借过滤绕过 lineage。
selection 模式强制显式提供录制对应的 `--config`；本批固定为
`testbed/configs/teleop_yulong_v2_2_pro_full_task_four_camera_jpeg.yaml`。缺少该配置会改变
boundary detector 的 `qualified_dig_start` 与 residual-mass 阈值，因此现在直接报错，不再
静默使用通用默认值。

current Unity replay 需要 `agx-sim/v2` 的 89D `agx_env_state_v2_3_89`：前 64D 不变，
新增 grid origin、长短轴单位向量、cell 长宽/面积、reference plane、6 格 baseline depth
和 6 格 surface valid fraction。每个快照同时产出 0.08m full-grid diagnostic 以及正式
T1/T2 0.25m residual，正式记录必须带 `target_id`。体积仅按 signed depth delta 的网格
积分派生：positive delta 累加为 removed volume，negative delta 单独记 refill/deposition，
二者不相互抵消；状态必须写为 `derived_grid_integral` 和
`unavailable_no_sensor`，不能称为 direct gold。

Replay 证据标记为 `replay_derived_open_loop`。它不生成 planned cut、planned/actual
entry/exit、gate、transition 或 planner actual-response 字段；这些键保持缺失，并带
`missing_not_generated_by_replay` 状态。只有后续真实 planner 闭环记录才允许填这些字段。
`episode_28` pilot 使用 `terrain_replay_pilot_gate_v2`，按用途拆开判定：源数据中的 ACT
监督资格只由 clean overlay 和 `action_loss_mask` 决定，不因碰撞后的 Replay qpos 漂移而
否决；episode 级 Replay 可用性要求无 exception、无 realign、首次合格 dig/soil contact
之前的 `qpos_max_error <= 0.02`、grid geometry 稳定、目标 cell valid fraction 均
`>=0.5`，并且至少 4/5 次满足语义门槛。每次至少应完成源完整周期数的 85%；正式 T1/T2
最终 completion 相对源下降不超过 5 个百分点，五次 completion 标准差不超过 0.05，
final grid 最大单元标准差不超过 0.06m，positive residual 不超过源值 +0.05m，
overdig/outside removal 不超过源值 + `max(0.05m, 15% * 源值)`。

碰撞后的全局 qpos error 只保留为诊断，不再作为 episode 拒绝条件。Replay 周期边界按
时间单调匹配到源周期，允许 `+-1s`；未匹配的周期不得生成 source-aligned effect 标签，
但不要求五次边界逐 step 完全一致。A/B variance tier 只决定逐周期 effect relabel 是否
可用于 fine/weak calibration；A/B 占比是信息项，不再是 pilot 硬门。C 档只屏蔽 effect
标签，不连带否决干净 ACT 监督。pilot 的 episode 语义门未通过时才停止默认池批量 Replay。
最终坑形使用完整因果前缀最后一个 Unity step 的 terminal env-state snapshot，而不是最后
一个被 detector 识别出的 dump boundary，避免边界漏检把较早的坑形误当作最终结果。
批量汇总分别报告 `process_stable` 与 `strict` effect 周期：前者要求 Replay 过程完整且
该周期 T1/T2 均为 A/B，后者还要求整个 episode 通过最终坑形语义门。二者不能混写为一个
“usable”数字。

### 固定 24 条的首个合格 Replay 数据集

`tb-build-terrain-replay-dataset` 把校准后的 14 条 pre 与 10 条 post 作为 24 个固定
source identity。每条最多串行执行 5 次，严格选择执行顺序中的**第一个**单次语义门通过者；
成功立即停止该 episode，不比较多个通过 attempt 的分数，也不把 4/5 repeatability 伪装成
单条入选证据。三条代表性 smoke 顺序固定为 `episode_28`、`episode_1`、`episode_19`，之后
才依次处理其余 post、普通 pre，以及最后的高风险 `episode_9/16/20`。

默认 no-overwrite 输出为：

```text
/data/pingfan/excavator_testbed_data/
yulong_v2_2_pro_full_task_four_camera_jpeg_20260717_cycle_action_calibrated_replay_selected_control_compatible_v2
```

录制时间线和五次失败 smoke 进一步确认：action scale 校准只能统一物理 target speed，不能
恢复 `episode_0..21` 录制期使用的 target-speed limiter/zero-hold 执行语义。固定 24 条中的
14 条 pre source 因此使用显式 `--control-compatibility-profile recording_pre_fix_v1`；10 条
post reference 使用 `production`。前者恢复“实测 constraint speed 作为 limiter 状态”、
录制期 ordinary-zero-speed 行为，当前 production controller、场景 max speed、soft limit、
terrain 和 action contract 均不改变。该路由写入 run contract、attempt command、diagnostic
和 HDF5 metadata；Unity RESET 必须返回匹配的
`replay_control_compatibility_profile:*` acknowledgement，否则按协议硬错误停止。

`recording_pre_fix_v1` 只允许与 `calibrated_mixed_current_equivalent` selection profile 和固定
pre-calibration episode inventory 同时使用；直接 `--episode`、post source 或其他 lineage
都会在 Python 侧被拒绝。每个 RESET 在未请求兼容 profile 时恢复 `production`，因此一次
兼容 Replay 不会把旧控制律泄漏到后续普通运行。兼容产物仍是
`replay_derived_selected_pass` / `not_gold`，必须保留
`replay_control_compatibility_profile` provenance，不能称为 current-controller closed-loop。

每个 attempt 都保留命令、Replay 日志、diagnostics、三 target cycle samples、HDF5 audit 和
`terrain_replay_single_attempt_gate_v1`。失败 attempt 先落盘 gate 与删除意图，再只删除该
output root 内生成的大体积 HDF5；原 raw、clean、calibrated 文件永久只读。`--resume` 只有
在 run contract、24 个 source hash、selection/config 和 live runtime contract 完全一致时
才继续，已入选或已耗尽的 episode 不重复运行。

实现责任分为两层：`terrain_replay_run_contract` 唯一拥有固定 source inventory、执行顺序、
preflight、source 不变性与 resume contract；`terrain_replay_dataset_builder` 只编排 attempt、
selection 和汇总。若代表性 smoke 的技术合同全部正常、但五次单次语义门仍耗尽，summary 必须
写 `status=halted_representative_smoke_failure` 和 `batch_stop`，不得误写成协议/字段
`hard_stop`；默认情况下正式批量仍不启动。定位完成后可以显式使用
`--resume --continue-after-smoke-semantic-failure` 继续统计其余 source，但 builder 只有在该
smoke 恰好已有 5 次 attempt、每次 process/HDF5/四相机/89D 合同均通过、没有 validation
error，且唯一失败项为 `semantic_attempt_failed` 时才允许继续。该开关不降低单条 gate、
不增加第 6 次 attempt、也不把已耗尽 smoke 选入数据集；最终不足 24 条必须保持 `partial`
和 `default_enabled: false`。任何技术合同失败仍按原规则停止。

入选文件固化到 `selected_full_hdf5/episode_N.hdf5`，同一次 realization 必须同时包含四路
JPEG、逐步相同的校准 `/action`、qpos/qvel、89D env-state 和 cycle sidecar。metadata 明确
写入 `selection_policy=first_passing_attempt_v1`、
`evidence_kind=replay_derived_selected_pass`、
`repeatability_status=not_assessed_single_attempt` 和 `gold_status=not_gold`。它不是原轨迹的
字段补丁，也不能和 source 再算成第二个独立 identity。

单次门仍要求 0 exception、0 realign、完整固定-step 因果前缀、首次合格 contact 前
`qpos_max_error <= 0.02`、四相机/89D/协议字段完整、grid geometry 与 valid fraction 合格，
并满足源相对的周期完成率及 T1/T2 completion/residual/overdig/outside-removal 容差；接触后
qpos 仅诊断。通过后从 replay 自身状态重算 V2.1、operator-first、hindsight 和 clean VDS，
最终 `action_loss_mask = source_calibrated_mask AND replay_qc_mask`，只能继续收紧。正式训练
视图为 `selected_replay_clean_vds`；24/24 之前 config 保持 `default_enabled: false`。

聚合产物包括 `selected_manifest.jsonl`、`attempt_inventory.jsonl`、
`selected_cycle_samples.jsonl`、`post_replay_qc.json` 和
`training_configs/selected_replay_22train_2val.yaml`。每个检测周期必须恰有 0.08m diagnostic、
T1、T2 三条记录；volume 仍是 grid integral derived，planner planned-cut、entry/exit、gate、
transition 和 actual-response 仍为 missing。只有后续真实 planner closed-loop 才能填这些字段。

### 七条耗尽 episode 的分层 Replay 抢救

`tb-salvage-terrain-replay-dataset` 只接受上述 control-compatible v2 父批次、其中固定的
17 条 strict pass，以及固定失败集合 `episode_1/4/9/10/12/14/20`。默认 no-overwrite
输出为：

```text
/data/pingfan/excavator_testbed_data/
yulong_v2_2_pro_full_task_four_camera_jpeg_20260717_cycle_action_calibrated_replay_selected_control_compatible_v2_salvage_v1
```

推荐按以下顺序执行；preflight 是只读检查，严格阶段可独立停住，随后只能用相同 run
contract 显式 resume：

```bash
tb-salvage-terrain-replay-dataset --preflight-only
tb-salvage-terrain-replay-dataset --stop-after-strict
tb-salvage-terrain-replay-dataset --resume
```

strict 阶段继续使用原单次语义门，禁止 realign，按 `4:10, 9:10, 12:5, 10:5,
1:5, 14:1, 20:1` 的固定预算执行，并始终选择执行顺序中的第一个 strict pass。局部排名
不能影响 strict 选择：只在 strict 失败结果中按合法周期数、合法 action step 数、纯开环优先、
较早 attempt 的顺序保留一个 provisional HDF5。

仍未 strict 通过的 source 最多运行 3 次
`replay_corrected_partial_salvage_v1`。该 profile 固定全轴 qpos realign 合同
`0.04 / 3 steps / 200-step interval / 15-step burn-in / max 20`，且永远不能进入 strict
manifest。corrected HDF5 的 `/timestamps/step_id` 使用连续的 causal source-action index
（`replay_step_id_semantics=causal_source_action_index_v1`）；realign RPC 前后的 Unity backend
step id 原值保留在 diagnostics。这样 RPC 自身造成的 backend id 前移/重复不会被误判成漏
action，而任意 causal action 缺步仍是硬错误。realign 所在周期、前后 guard 和受影响
transition 都被隔离；局部最终 mask 固定为
`source_calibrated_mask AND replay_qc_mask AND local_cycle_mask`，只能收紧。一个局部周期还必须
满足边界单调匹配 `+-1 s`、入口及首次接触前 qpos 误差 `<=0.02`、四相机/89D/step
合同完整、grid geometry 稳定、target valid fraction `>=0.5`，并通过 replay-native V2
周期清洗。

输出将 strict 与 ablation 完全分离：`combined_strict_clean_vds` 由父 17 条加新 strict
结果组成；`layered_salvage_clean_vds` 对每个 source identity 最多引用一个 strict 或局部候选。
后者以及所有 corrected/partial 记录始终
`default_enabled=false`、`strict_pool_eligible=false`、`gold_status=not_gold`。不足 24 条 strict
时，strict 配置同样保持禁用。`episode_14/20` 若仍 strict 耗尽，只写入重录建议，不阻塞
其他结果。attempt、候选移动和 composite VDS 都采用 no-overwrite/atomic intent；`--resume`
会校验 source hash、父批次 checksum、runtime build 和已移动候选 checksum，不会重复已计数
attempt，也不会把同一 source 的 replay 当作新的独立 identity。

完成报告中的 `local_eligible_cycle_count` 与 `local_valid_action_step_count` 只汇总每个 source
最终保留的唯一 partial 候选；`all_attempt_local_eligible_cycle_count` 和
`local_cycle_audit_row_count` 单独描述全量 attempt 审计历史，禁止把多次尝试的周期重复计入
最终可用监督量。

Pilot determinism failures may be isolated with the explicit
`tb-replay --diagnostic-terrain-mode` reset ablations. Supported modes are
`production`, `no_dynamic_mass`, `no_excavation_force_feedback`, and
`terrain_disabled`. They are diagnostic-only: the omitted flag is the only
normal replay default, Unity restores production native settings before every
RESET, and ablation outputs cannot enter replay acceptance, relabeling, or
closed-loop evidence. Use a bounded selection manifest and a new no-overwrite
diagnostic output path for each mode.

The bounded `episode_28` cycle-0 diagnosis on 2026-07-20 found two coupled
failure mechanisms. Across five 631-step production repeats, qpos repeat spread
first exceeded `1e-5` at step 193 after soil-particle creation began, then
exceeded `0.02` at step 614. With `no_dynamic_mass`, five repeats remained
within `1.91e-7` qpos spread for the whole prefix, but each still exceeded the
then-current source-qpos gate (`~0.031`) when the bucket contacted
`CodexFactoryLayout/CodexDigAreaBoards/Dig_XMax_Board` from step 612. Therefore
the ablation proves a repeat-variance source but is not a determinism fix: dynamic
soil creation introduces the early stochastic trajectory difference, and the
physical XMax board contact amplifies it. Disabling only
shovel excavation force feedback did not remove variance. The source episode is
64D and lacks `runtime_build_id`, so exact source/current build parity remains
unprovable. The durable diagnostic report is
`..._cycle_clean_v1/replay_determinism_diagnosis_episode28_cycle0_v1/diagnosis_summary_v2.json`;
that old whole-trajectory gate is superseded only for data Replay evaluation by
`terrain_replay_pilot_gate_v2`. The semantic pilot passed, so post-fix batch Replay may proceed.
Planner closed-loop evidence remains a separate later phase.

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

### 当前四相机 JPEG 录制契约

当前 YuLong 四相机录制的确定顺序是
`stick_up,stick_down,eye_left,eye_right`。新录制使用
`testbed/configs/teleop_yulong_v2_2_pro_full_task_four_camera_jpeg.yaml`，Unity 每个 control step
对每路画面只编码一次 JPEG，HDF5 直接保存收到的 bytes，不先解码再编码。这里的
“MJPEG-style”指按 timestep 独立保存的一串 JPEG frame，不是 HDF5 内嵌的单体 `.mjpeg`、AVI
或 H.264 视频流。JPEG/MJPEG-style 是有损视觉压缩；当前 Unity wire 默认是 `512x288`、JPEG
quality `95`（`AgxSimStepAckServer` Inspector 字段可调），而 Python 端只接受 wire 声明的
`jpeg` frame，不根据文件扩展名猜编码。

性能实现约束：这四个 camera 是 capture-only camera，组件必须保持 disabled，仅由 step-ack
捕获路径显式调用 `Camera.Render()`；否则 Unity 会先自动渲染、录制时再手动渲染，造成重复
camera pass。GPU readback 的 `RenderTexture` 和 CPU `Texture2D` 在分辨率不变时应跨 step
复用，`ReadPixels` 后不得为了 JPEG 编码调用 `Apply()` 回传 GPU。以上约束只减少重复渲染、
资源抖动和无效 GPU 上传，不改变 frame 顺序、尺寸、JPEG quality、bytes 或 step 对齐语义。
bucket mass/contact 等逐步诊断仍保留在 wire warnings 中，但 Unity Editor 的文本日志必须按
配置间隔限流；只有失败响应可以绕过间隔立即记录，避免正常遥测 warning 触发逐 step I/O。
step-ack 的单请求/单响应语义不变；连接建立后，网络线程最多以 1 ms 间隔检查新请求，并在
主线程把 response 入队时由信号立即唤醒，不得在每个请求和响应阶段各固定 sleep 5 ms。
step-ack 组件启用并接管控制权时，必须在首个客户端请求到达前停止现有机构运动并关闭 AGX
自动步进，避免 EpisodeManager 被禁用后遗留的执行器目标继续驱动机器；组件禁用时恢复接管前
的自动步进模式。该预连接停车不替代客户端 RESET，RESET 仍拥有正式 episode 初态。

新 episode 的图像契约是：

- `/metadata` attrs 中 `camera_names` 必须按上述顺序保存，`image_format=jpeg`；顺序由录制/训练
  config 明确拥有，不按 HDF5 group key 的字典序猜测。
- 每路存到 `/observations/encoded_images/<camera>`，shape 为 `(T,)` HDF5 vlen `uint8`，dataset
  attr 为 `encoding=jpeg`；默认不同时写一份 `/observations/images/<camera>` dense raw copy。
- reader、ACT dataset 和视频预览在消费边界解码为 RGB `uint8 HWC`。训练仍按 config 中的
  `camera_names` 堆成 camera tensor；JPEG 只是存储表示，不改变低维 token、action 或 ACT
  action dimension。
- `tb-dataset-qc` 必须检查 metadata/stored camera set 和显式期望顺序、每路长度等于 `T`、
  vlen `uint8`/`encoding=jpeg`、逐帧可解码、以及每路 decoded HWC shape 稳定。失败报告必须带
  camera 名和 frame index，不能只写通用 `missing_images`。
- VDS、materialize 和 image virtualization 必须原样转移 JPEG bytes 和 attrs，禁止在数据变换
  中 decode/re-encode；训练 copy 中 encoded dataset 必须是实体 dataset，不能遗留 unresolved
  VDS/external link。
- rollout/replay 的 HDF5 recorder 直接透传 `encoded_images`。保存 MP4 预览时只解码第一个
  configured camera；该预览解码不回写 HDF5，也不产生第二份 JPEG。

兼容边界：旧 `/observations/images/fpv` dense raw RGB episode、旧单 `fpv` config 和对应 checkpoint
继续按原契约读取，不批量改写，也不宣称它们天然支持四相机。新四相机 checkpoint/config 与旧
单相机 checkpoint/config 是不同输入契约；是否混合旧/新数据必须作为显式训练实验决定，不能靠
loader fallback 静默拼接。

### 基础 episode 字段

当前基础 schema 是 `1.1`，`/v2` 仍是 add-only extension，不通过删除/改名破坏旧读写。

| 路径 / attr | shape / 类型 | 语义 |
| --- | --- | --- |
| `/metadata` attrs | attrs | `schema_version`、`task_name`、`sim_backend`、`seed`、`timestamp`、`control_hz`、`dt`、`camera_names`、`image_format`、`recording_mode`、`scenario_id`、`env_state_order` 等 episode 元数据 |
| `/observations/qpos` | `(T, 4) float32` | `[swing, boom, stick, bucket]` position norm |
| `/observations/qvel` | `(T, 4) float32` | 同顺序速度 |
| `/observations/env_state` | `(T, 64 or 89) float32` | 2026-07-17 raw 是 64D；当前 `agx-sim/v2` replay/runtime 是 append-only 89D，见下一节 |
| `/observations/images/fpv` | `(T, H, W, 3) uint8` | FPV 图像；VDS 阶段可为 virtual，训练 copy 必须 materialized |
| `/observations/encoded_images/<camera>` | `(T,)` vlen `uint8` | 新四相机逐帧 JPEG bytes，dataset `encoding=jpeg`；与 dense raw layout episode 内互斥 |
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
| 64-72 | grid origin、long/short axis unit vectors | 锁定 3x2 网格在 world frame 的位置和方向 |
| 73-76 | cell long/short size、cell area、reference plane local Y | 网格积分与几何一致性 |
| 77-82 | `dig_area_baseline_depth_m_r{0..2}_c{0..1}` | reset 时的 6 格 surface baseline |
| 83-88 | `dig_area_surface_valid_fraction_r{0..2}_c{0..1}` | 每格实际成功采样比例；pilot target cell 要求不低于 0.5 |

### `/v2/step` 字段

| 路径 | shape | 语义 |
| --- | --- | --- |
| `/v2/step/cycle_id` | `(T,) int32` | 旧 cycle id；当前只作搜索/诊断坐标 |
| `/v2/step/mode_id`、`phase_id`、`phase_progress`、`work_stage_id` | `(T,)` | 旧 mode/phase/stage 标签；可用于 reject/QC，不是 V2.4.5 ownership 真相 |
| `/v2/step/goal_tokens` | `(T, 10) float32` | 早期 goal-conditioning 兼容字段 |
| `/v2/step/action_loss_mask` | `(T,) uint8` | 动作监督 mask；clean config 的 `loss_sampling_stats` 还将它用于采样起点和 action/proprio 统计 |
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
