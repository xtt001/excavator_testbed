# Strict-18：从连续作业恢复到实时地形目标跟随

## 当前结论与文档地位

当前唯一授权的实现任务是**阶段 A.1：独立支持范围合同审计（`support_contract_v2`）**。
它先解释阶段 A 中的数值支持范围拒绝来自哪里，再决定能否以新的、经过保留验证来源检验的
合同重跑阶段 A；它不重新定义目标，也不把本次目标条件审计的 OOS 结果拿来调阈值。

阶段 A 与阶段 A.1 都只产生 teacher-forced recorded-observation 的离线诊断证据。它们不是
Unity 闭环、真实机器验证、生产证明或训练结果；本轮不训练、不创建训练 HDF5、不运行 Unity
rollout/live/1×10，也不改变 production/default runtime、安全阈值或 timeout。

本文固定后续实现边界。它不改写
[历史 handoff](goal_following_mainline_handoff_20260731.md) 或
[implementation manifest](goal_following_mainline_implementation_manifest_20260731.json) 中已记录的
实验、证据与当时承诺。

## 冻结控制架构

```text
目标地形 + 当前地形/机械状态
        ↓
Terrain Residual Planner 生成下一铲任务级目标
        ↓
Goal 生命周期服务锁定 goal_id，并生成同源 return envelope
        ↓
Primitive Scheduler 选择 Return / Dig / Carry / Dump
        ↓
Goal-conditioned ACT 根据观测、历史、状态和目标直接输出四轴动作块
        ↓
独立滚动安全盾检查当前动作及短期可能扫掠
        ↓
底层执行器 → 实际轨迹、接触、载荷和地形效果 → 更新剩余地形
```

责任边界已经冻结：

- Planner 只生成任务级目标，不生成 joystick、qpos setpoint 或必须逐点跟踪的控制轨迹。
- ACT 直接输出 4D action，顺序为 `[swing, boom, stick, bucket]`。完整 qpos path 不是
  ACT 输入。
- 专家 qpos path 只用于离线数据支持、诊断和未来模型标定。专家路径安全不能证明 ACT
  的安全。
- 若执行前需要预测风险，预测对象必须是冻结 ACT 在当前状态、目标、历史缓冲和动作聚合
  配置下可能产生的短期运动范围；优先使用 Unity 影子预演。
- 墙面、硬底、高力、boom/stick 接触、异常数据、卡死和超时仍由独立硬安全链处理。不得
  放宽阈值、延长 timeout、使用 nearest-expert fallback，或用旧 runtime 绕过门控。
- `exact-tuple` 与现有 continuous qpos predictor 是 `diagnostic_legacy`。它们只保留给
  历史诊断、离线校准和失败归因，不进入 production runtime。
- 历史 outcome 标签描述专家实际达到的结果；在线 Planner 的 desired goal 是另一类对象。
  不得把 achieved effect cell 或实际 payload 冒充 planner intent。

当前严格配置下，Dig 使用 `qpos + qvel + dig_cut_tokens`，Return 使用
`qpos + qvel + return_start_envelope_tokens_v1`，Carry/Dump 使用 `qpos + qvel`；四个
primitive 都输出 4D action。

## 当前证据边界

- 旧 aggregate-TX24 十铲只证明连续循环可运行。入口、出口和深度误差较大，不能证明
  严格目标跟随。
- Strict-18 九次 dump 是诊断性恢复，不是正式实时目标跟随验收；第十铲前 return 的
  entry、depth、qpos 条件没有同时满足。
- continuous qpos predictor 的代码、训练、校准和 artifact 校验框架存在，但没有可信训练
  artifact；它不进入 ACT，也尚未形成真实在线 Unity 三维放行闭环。
- 历史 433 个专家窗口的 qpos、qvel、89D terrain 和专家路径可用；planner-issued target
  cell、payload/effect intent 和统一 path-start 合同不能从历史记录直接恢复。
- 已有 outcome-grounded hindsight 标签；不追索历史中并未记录的专家 planner 原始意图。

任何报告必须把离线、影子、Unity 诊断和正式闭环分开表述。旧十铲或九铲都不是
production proof。

## 阶段 A：冻结 ACT 的目标条件敏感性离线审计

### 目标与允许的结论

审计比较相同 recorded observation stream 下的基线和反事实条件。它的结论只限于 ACT 是否
读取了当前条件，以及动作变化是否稳定、可解释。

每份输出必须标记：

```text
teacher_forced_recorded_observation
diagnostic_only
promotion_eligible=false
```

baseline 对齐失败时，所有反事实结果无效。即使通过，也不能推出反事实轨迹安全、Unity
闭环成功、地形效果正确或 production ready。

### `support_contract_v1`：阶段 A 的正式判定合同

阶段 A 的四类分类只适用于完整且可验证的工件。若 preflight、action integrity 或 baseline
复刻任一项失败，工件的顶层 `status` 必须是 `artifact_invalid`，并且不得写入四类
`classification` 中的任何一个。这条边界优先于以下所有支持范围和动作响应判定。

对每个 primitive 的每个 selected frame，baseline 与 alternate 都必须逐字段通过对应
strict-train p01-p99 数值支持检查。这个已冻结规则的候选标识是
`axis_p01_p99_v1`，并构成 `support_contract_v1`。只要任一方有任何数值支持越界，该
primitive 就是 `out_of_support`；不能以动作差异、复刻稳定性或锚点通过来覆盖它。
这些上下界只由该 primitive 的 train split 内 action-loss-valid 数值行拟合，验证来源不得
参与拟合或被当作支持证据。

`support_contract_v1` 必须保留为历史基线：阶段 A 已写出的 v1 工件不得覆盖、重标或以 v2
结论替换。阶段 A.1 即使选择了 v2，也只会创建新的 no-overwrite 离线审计工件；它不会改变
production/default runtime。

baseline 要由互相独立的 replica A/B 在相同冻结条件下重放。对每个动作轴，先计算整个
selected-frame 集合中的最大绝对差，再得到唯一的基线复刻容差：

```text
baseline_tolerance_axis = max(1e-6, 10 * max_abs(baseline_replica_A - baseline_replica_B))
```

在派生这个容差前，replica 的原始 chunk 和实际派发动作都必须先通过按轴的噪声上限：

```text
replica_noise_cap_axis = max(1e-6, 0.005 * abs(action_std_axis))
```

任一 replica 差异超过该上限，或任一 replica 与保存动作的差异超过派生后的
`baseline_tolerance_axis`，工件都是 `artifact_invalid`。这里没有相对误差项，也不能根据
动作幅度临时放大容差。反事实响应阈值同样按轴固定：

```text
response_threshold_axis = max(baseline_tolerance_axis, 0.05 * abs(action_std_axis))
```

`action_std_axis` 必须来自冻结的动作归一化/训练统计工件。对每个 selected frame，只要任一
实际派发动作轴的绝对 baseline/alternate 差值严格大于该轴 `response_threshold_axis`，该帧
就是 active；否则 inactive。active-frame fraction 是 active frame 占全部 selected frame 的
比例，start/mid/end 三个 anchors 都必须是 active。

对有效工件，单个 primitive 按下面顺序分类：

1. baseline 或 alternate 有任一 selected-frame 数值支持越界：`out_of_support`。
2. 每个实际派发动作轴的 delta 都小于或等于相应 `response_threshold_axis`：`goal_insensitive`。
3. 已存在 active response，但 alternate replicas 的任一轴差异超过 `baseline_tolerance_axis`、
   active-frame fraction < 0.80，或任一 start/mid/end anchor inactive：`goal_response_invalid`。
4. 其余有效结果：`goal_response_plausible`。

跨 primitive 汇总时，先前的 `artifact_invalid` 仍不产生四类总分类。其余有效结果使用固定
优先级：any OOS -> OOS；all insensitive -> insensitive；all plausible -> plausible；otherwise ->
invalid。对应公开标签依次为 `out_of_support`、`goal_insensitive`、
`goal_response_plausible`、`goal_response_invalid`。

`direction_assessment` 必须固定为 `not_identifiable_in_teacher_forced_replay`。teacher-forced
重放中的 joint-action 符号、token 几何字段或差值方向，都不能证明真实机械运动方向、地形
效果方向或安全方向；这些问题留给后续 Unity/闭环证据。

### Dig、Return 与 Carry/Dump 的审计范围

| 对象 | 基线条件 | 反事实条件 | 可得结论 |
| --- | --- | --- | --- |
| Dig | 原始 `dig_cut_tokens` | 另一条真实记录出现过的完整有效 Dig token；支持范围内可加只改 depth 或几何字段的单因素变体 | Dig 是否对目标条件产生动作响应 |
| Return | 原始 18D return envelope | 另一条真实记录出现过的完整、有限、有效 envelope；记录其下一铲 Dig token 与 cycle provenance | Return 是否对条件产生动作响应，不能称为端到端目标跟随 |
| Carry/Dump | 原始 `qpos + qvel` 输入 | 验证无关 cut goal 没有被错误注入 | 隔离性，不要求它们响应下一铲 cut goal |

zero token 只能作为负对照，不能写成可执行目标。审计必须使用完整 token/envelope，不能
只替换其中一个字段后仍将其描述为真实目标。

### 冻结输入、对齐与 policy 状态

优先只读使用以下 run：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
carry_dump_ownership_priority_10cycle_four_camera_reproduction_20260731_v1/run/results/
```

必须核验并记录 `eval_resolved_config.yaml`、`rollouts/rollout_000.jsonl`、
`hdf5_rollouts/episode_0.hdf5`，以及配置、JSONL、HDF5、checkpoint、normalization 和代码 SHA。
temporal aggregation 必须记录运行时实际解析值，不能只依据 YAML 是否显式书写。

对每个比较条件，必须固定 checkpoint、归一化文件、四相机顺序、qpos、qvel、图像、历史
窗口、policy reset 点、action scale 和 temporal aggregation。除被替换 token 外，所有低维
输入必须一致。

每个条件必须各自拥有独立 policy 实例、独立 temporal cache 和独立 reset。条件之间不得
共享 cache，且不能每帧重置 policy。

### 输出与失败关闭

输出写入不可覆盖根目录 `act_goal_condition_sensitivity_v1/`。每份结果至少保留：

- baseline 对齐结果；
- 起点、中段、末段的 raw `100×4` action chunk 差异；
- 整段 temporal-aggregated 实际派发动作差异；
- token/envelope、checkpoint、stats、trace、config 与代码 lineage。

除正式判定合同中的 `artifact_invalid` 外，出现下列任一情况也必须失败关闭，且不得静默
放宽容差：观测、图像、qpos、qvel、相机顺序或非目标低维输入在条件间不一致；token/envelope
在原 segment 内漂移；输出目录已存在。

阶段 A 完成后停止并报告证据类型、baseline 是否对齐、Dig 和 Return 是否分别响应条件、
动作变化是否稳定、固定的方向不可识别结论、production/default 是否改变，以及下一步建议。
当前出现 `out_of_support` 时，不直接进入阶段 B，而是先执行以下阶段 A.1。

## 阶段 A.1：独立支持范围合同审计（`support_contract_v2`）

### 目的、边界与原因分支

这是一项只读、离线的支持范围合同审计。它只回答“记录到的状态是否属于冻结 ACT 的已验证
数值支持范围”，不判断动作方向、地形效果、轨迹安全或“指哪挖哪”。它不训练、不重跑
Unity/live，也不把 `support_contract_v2` 接入 production/default runtime。

对每个 Return stable segment，审计必须保留并可视化其每一轴实际 `qpos`/`qvel` 相对 strict-train
分布的位置，同时记录 JSONL action step、HDF5 action 行、前一帧 observation 行、primitive
episode/source episode、`action_loss_mask`、字段名、单位/形状和 token/envelope。图表与原始
数值必须能区分下列互斥的处理分支：

1. **时间对齐或字段语义错误**：动作与 JSONL/HDF5 不一致、前一帧 observation 关系不连续、
   primitive/source 映射、字段维度、单位或 token 键不一致。修正数据合同后，使用 v1 重新跑
   阶段 A；不得用更宽阈值掩盖错误。
2. **v1 规则过于保守**：严格 source-disjoint 训练/验证预注册证明某个 v2 候选能覆盖正常验证
   状态，同时仍拒绝预定义的明显陌生状态。保留 v1，并以选定 v2 在新的 no-overwrite 根重跑
   阶段 A。
3. **真实训练覆盖缺口**：对齐正确且没有候选通过预注册验证，或目标状态仍被选定 v2 拒绝。
   不得以放宽规则继续；后续只能在 Return handoff 拒绝该状态，或采集这些起始姿态/速度下的
   专家数据并重训。

### 不得用目标审计调参

不得用阶段 A target audit 调参：`act_goal_condition_sensitivity_v1` 的 Return OOS 帧、segment、
动作差异、token 选择和任何派生统计都不得参与 v2 候选拟合、分位数/距离阈值、合格判定、
候选排序或 synthetic OOD 的构造。它只能在 v2 选择已锁定后作为 target diagnosis 的被测对象。

训练与验证必须 source-disjoint；每行都要保留 partition、primitive episode、source episode、
step index、step id 与 `action_loss_mask` 谱系。候选拟合只能读取 strict-train 的
`action_loss_mask=1` 行；验证来源只用于预注册验收，target rollout 不得泄漏到任何支持规则的
标定过程，即使它无法被映射为一个独立的 primitive source identity 也同样如此。

### 预注册候选与验收

每个 primitive 都对完整 ACT 数值低维输入判定支持范围：`qpos[0:4] + qvel[0:4] +` 该 primitive
完整 conditioned token/envelope（Dig 10D，Return 18D）。报告必须另行按 `qpos`、`qvel` 与 token
三组归因，不能把 token 越界误写成 Return 姿态问题。

候选集合、参数和优先顺序在读取 target 前固定如下：

| 候选 ID | train-only 拟合规则 |
| --- | --- |
| `axis_p01_p99_v1` | 每个完整输入维度的 p01–p99；它是 v1 对照，不会被修改。 |
| `axis_p0005_p9995_v2` | 每个完整输入维度的 p0.05–p99.95。 |
| `joint_regularized_mahalanobis_p99_v2` | 完整输入向量的 strict-train 均值与协方差；使用确定性 ridge `max(trace(covariance) / D * 1e-6, 1e-12)`，以 strict-train squared Mahalanobis distance 的 p99 为阈值。 |

冻结的明显陌生状态负对照只来自 held-out validation：每个验证行是 anchor，对每一个特征做
确定性的交替符号扰动，幅度固定为 `32 * max(abs(anchor_feature), validation_feature_span, 1.0)`。
必须保留 anchor、字段、符号和扰动后的值谱系；不得从 target 或 train 行生成该负对照。

每个候选必须同时满足：

```text
validation_normal_coverage >= 0.99
synthetic_obvious_ood_rejection >= 0.99
```

不满足前者的状态是 `rejected_validation_coverage`，不满足后者的是
`rejected_obvious_ood_rejection`，两者都不满足时必须同时记录。合格候选按
`synthetic_obvious_ood_rejection` 降序、`validation_normal_coverage` 降序排序；仍相同时按固定
优先级 `axis_p01_p99_v1`、`joint_regularized_mahalanobis_p99_v2`、
`axis_p0005_p9995_v2` 选择。任何一项 primitive 没有合格候选，审计顶层状态必须为
`support_contract_not_selected`，不得对 target 给出“v2 已支持”的结论。

### 工件、重跑与运行时边界

`support_contract_v2` 输出必须写入一个新的 no-overwrite 根，至少包含候选拟合、验证验收、
每段 Return target diagnosis、选择理由、全部输入 SHA 与 code SHA。每个 Return segment 还必须
生成确定性的 `plots/return_<segment-id>.svg`（`segment-id` 必须先作确定性的文件名安全规范化）：
八个 `qpos`/`qvel` 轨迹 panel 各自叠加 strict-train p01/p99 与支持判定注释。图只服务于原因审计，
不是候选阈值、排序或验收的输入。每份输出都标记：

```text
teacher_forced_recorded_observation
diagnostic_only=true
promotion_eligible=false
closed_loop_claim=false
```

只有状态为 `completed`、每个 primitive 已选择候选、且 target diagnosis 不含对齐/语义错误时，
才能以选定的 `support_contract_v2` 新建另一个 no-overwrite 的阶段 A 审计根。该 v2 重跑仍然
只是离线证据；v1、production/default runtime、安全阈值和 timeout 一律不变。

## 后续阶段：仅保留为计划

### 阶段 B：收口目标与结果的数据合同

定义在线 `DesiredCutGoal` 与历史 `AchievedCutOutcome` 的边界，不能把专家实际结果当作
Planner 的原始意图。只有在 `support_contract_v1` 或已选择的 `support_contract_v2` 下完成阶段 A
重跑并产生 `goal_response_plausible` 证据后，才进入 Unity 单铲目标效果对照准备。

### 阶段 C：建立短期行为安全盾

基于 Unity 影子预演或 ACT rollout，评估冻结 ACT 在当前状态、条件、历史与 temporal
aggregation 下的短期扫掠风险。该阶段不得用专家 qpos path 代替 ACT 实际可能运动。

### 阶段 D：同 reset 的 Unity 单铲目标效果对照

在相同 reset 下比较目标改变后的实际运动和地形效果。它是 Unity 诊断证据，不是多铲
闭环验收。

### 阶段 E：有界多铲 residual 闭环

在显式目标生命周期、独立安全门控和 stop rule 下，验证 residual 更新能否安全驱动下一铲
规划。结果须和阶段 A、C、D 的证据类型分开报告。

### 阶段 F：正式十铲目标跟随验收

仅在前述门控全部通过后，申请一次正式十铲目标跟随验收。它需要独立批准；通过也不自动
改变 production/default 行为。

## 实现与报告纪律

阶段 A 优先复用 recorded replay 对齐、完整 action chunk 提取和现有 Dig/Return replay 基础，
但不向旧 `exact-tuple` 或 regression 工具堆叠新的目标敏感性语义。稳定职责应由共享 ACT
推理接口、独立的 Dig/Return 条件反事实回放模块和薄 CLI 承担。

每次报告先说明完成的是哪种证据、实际观察到什么、是否保留了安全边界、production/default
是否改变；随后再列 token、checkpoint、路径、SHA 和内部实验标识。没有相应 Unity 或正式
闭环证据时，不得使用“已实现实时目标跟随”或同义结论。
