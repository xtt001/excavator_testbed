# Strict-18：从连续作业恢复到实时地形目标跟随

## 当前结论与文档地位

当前授权路线已切换为**阶段 B → C → D：Dig 单铲位置 A/B 土体效果验证**。实验从同一个严格训练姿态出发，
只平移 DigArea 中的 entry-z 和 exit-z，深度、方向、长度、载荷、checkpoint、时序聚合和安全阈值不变。
实现阶段只允许准备、验证和生成 no-overwrite 合同；发送动作仍需显式的执行授权。2026-08-21 的首次
在线运行在 original 铲斗软限位时停止。随后确认旧轨迹点存在动态角点切换缺陷，在不改变默认观测的前提下
改用请求局部固定中齿点，并经用户再次授权完成新的阶段 C/D 两臂运行。

Unity 当前没有可审计的隐藏土体快照，也没有已证明的确定性土体 seed。因此即使两臂的轨迹、入土/出土几何和
六格移除效果都分开，结果仍只能标记为诊断证据（`diagnostic_only=true`、`promotion_eligible=false`）。
它可以准入下一次 Return→Dig 集成诊断，但不能改变生产或默认行为。

当前阶段 D 结果是 `action_only_no_trajectory_separation`，实际效果臂为 `2/2`。两臂都完成入土、出土和
neutral ACK，没有墙、FactoryFloor、未知/禁止接触、碰撞、输入裁剪或软限位；最大力约
`20972.54 N`/`12059.06 N`，低于 `100000 N`。raw action 的目标响应为 `100/100`，但接触轨迹中位分离
只有 `0.282983 m`，低于 `0.50 m`，alternate 没有在目标 cell 4 产生移除深度。初始可观测状态一致，隐藏
土体仍未证明。因此不进入 Return→Dig 集成；下一项研究问题是目标 token 经执行器和动力学映射到空间轨迹
时为何没有到达 alternate 位置，以及现有训练是否覆盖该联合条件。

阶段 A.6 和 A.6-S-3 的 Return 实现、实验记录与失效原因现已冻结为历史材料。不继续深挖 Return，
不补跑其旧试验臂，也不删除或覆盖两个仓库中已有的未提交材料。本文后续 A.6 章节仅供证据溯源。

已完成的离线证据是：阶段 A 的 Dig 有 9/10 段 `goal_response_plausible`、1/10 段
`out_of_support`；Return 在 v1 下均为 OOS。阶段 A.1 选择了 Return 的
`joint_regularized_mahalanobis_p99_v2`，其 9 段均在该规则支持范围内；随后 Return v2 重跑
得到 7/9 段 `goal_response_plausible` 和 2/9 段 `goal_response_invalid`。Dig 没有通过候选
验收，仍使用 v1。这些都是 teacher-forced 诊断结果，不构成闭环或生产结论。

阶段 A 至 A.5 的既有结果保持原证据边界：它们只产生 teacher-forced recorded-observation 或独立
held Return 的离线诊断证据，不构成 Unity 闭环、真实机器验证、生产证明或训练结果。阶段 A.6 是
单独授权的 Unity action-driving Return-only 诊断，但仍不训练、不创建训练 HDF5、不运行真实机器或
1×10，也不改变 production/default runtime、安全阈值或 timeout。

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

## 阶段 A.1：独立支持范围合同审计（`support_contract_v2`）（已完成）

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
   状态，同时仍拒绝预定义的明显陌生状态。该结论按 primitive 独立成立：Return 可用已选择的
   v2 重跑，而 Dig 保持 v1；保留 v1，并以相应规则在新的 no-overwrite 根重跑阶段 A。
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
`support_contract_not_selected`，这只表示不存在覆盖全部 primitive 的统一 v2；不得把它写成
“所有 primitive 都没有支持”。已选择候选的 primitive 仍保留其独立选择结果，未选择候选的
primitive 必须继续使用 `support_contract_v1`，不得要求每个 primitive 都选择 v2 后才允许
对已选择 primitive 重跑。

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

任一 primitive 只要已经选择候选、且该 primitive 的 target diagnosis 不含对齐/语义错误，就能
新建一个 primitive-scoped 的 no-overwrite 阶段 A v2 审计根；它不以顶层 `completed` 或其他
primitive 的选择结果为前提。该工件必须逐 primitive 写明实际使用的支持合同，例如 Return
使用已选择的 v2、Dig 保持 v1。这个 v2 重跑仍然只是离线证据；v1、production/default runtime、
安全阈值和 timeout 一律不变。

## 阶段 A.2：Return 响应稳定性原因审计与 Dig 联合支持合同独立验证

### 目标、固定输入与禁止项

阶段 A.2 仍然只读、离线、`diagnostic_only`。它不训练、不创建训练 HDF5、不运行 Unity/live，
不改变 Planner、checkpoint、默认 runtime、runtime handoff、安全阈值或 timeout。它也不改变
阶段 A 的四类分类、`response_threshold_axis` 或 active-frame 规则。

Return 原因审计只检查已经产生 `goal_response_invalid` 的两个原始 pair；不得换 segment、换
alternate token、换 checkpoint 或用更短窗口重做一份更容易通过的比较：

| Baseline recorded segment | 固定 alternate token source | 当前未通过原因 |
| --- | --- | --- |
| `return:898-1043:bb329f176aba` | `return:3959-4161:4afcef2eee82` | active-frame fraction 为 0.773972602739726，低于固定的 0.80。 |
| `return:3959-4161:4afcef2eee82` | `return:2323-2534:87aa0fb8c981` | active-frame fraction 为 0.7192118226600985，低于固定的 0.80。 |

两组 pair 必须复用同一 JSONL/HDF5 记录、前一帧 observation 绑定、原始 JPEG、四相机顺序、
checkpoint、normalization/stats、解析后的 evaluation config、action scale、设备确定性设置和
实际 temporal contract。所有这些输入及其 SHA 必须写入新的 no-overwrite 原因审计工件。只有
新增诊断记录可以增加，标准分类输入不得变动。

**固定的 0.80** 是阶段 A 的合格线。不得降低 0.80 门槛，不得以平均值、只检查 anchor 或
修改响应阈值把这两段判为通过；三个 anchor 仍必须同时 active，replica 一致性和 baseline
对齐规则也仍然有效。

### Return 三项原因审计

审计必须逐项给出可复查结果，不能仅输出最终标签：

1. **token 归一化**：对 raw 18D envelope 的字段顺序、dtype、模型键、有效位、训练时 token
   builder、normalization 参数和归一化后 tensor 分别取证。使用与训练/evaluation 相同的 canonical
   builder 重建每步模型可见 token；在明确 dtype/shape 后，它必须与审计路径进入模型前的 tensor
   完全一致。任一不一致是数据合同错误，当前动作响应结果不得继续作为证据。
2. **图像、`qpos`、`qvel` 的历史窗口**：对每个 policy step 记录 JSONL action step、HDF5
   action 行、前一帧 observation 行、四相机原始 JPEG 与变换后模型输入、`qpos`/`qvel` 数值、
   history index 和 reset boundary。它们必须与训练/evaluation 输入路径的实际窗口、帧偏移、
   图像变换和排序一致；任一 mismatch 必须命名为对齐/字段语义错误，而不能被归因成模型无响应。
3. **temporal aggregation**：标准重放必须在 segment 入口 reset 一次、segment 内连续运行、
   不得逐帧 reset；baseline 与 alternate 分别使用独立 cache。逐帧记录 raw `100×4` chunk 差异、
   每个实际派发动作的 cache contributor/query position/weight，以及聚合后动作差异。仅当 raw
   chunk 在同一固定门槛下稳定响应、而标准 aggregation 的已记录贡献权重使实际派发动作低于门槛，
   才能标记 `temporal_aggregation_dilution`。任何禁用 aggregation、清空 cache 或改变窗口的 replay
   只能用于解释，不能替代正式分类。

每个 pair 的结果必须为 `normalization_mismatch`、`observation_history_mismatch`、
`temporal_aggregation_dilution`、`not_explained_by_frozen_inputs`，或明确记录多个同时存在的
失配。若前三类中出现输入合同错误，先修正合同并保留旧工件，再新建完整阶段 A 重跑；若三项均
通过但 active-frame fraction 仍低于 0.80，该 pair 保持 `goal_response_invalid`，不进入阶段 B。

### Dig 联合支持合同的独立验证

Dig 审计与上述两段 Return 原因审计并行、相互独立。候选支持合同的整个 family（特征顺序、
预处理、联合距离或其他 reject rule、fit 参数、阈值 family、候选排序和验收门槛）必须在读取
任何 target rollout 前写入候选 manifest；之后不得根据 target 结果临时调参。拟合只能读取
strict-train 的 `action_loss_mask=1` 行，保留验证来源只用于验收；train、validation、target 的
primitive/source episode identity 必须 source-disjoint，缺少谱系或发生交集即 fail closed。

当前预注册的 Dig-only family 是五个 strict-train score quantile 的 regularised joint
Mahalanobis 候选，固定顺序如下：

1. `dig_joint_regularized_mahalanobis_p99_v1`（train p99）；
2. `dig_joint_regularized_mahalanobis_p995_v1`（train p99.5）；
3. `dig_joint_regularized_mahalanobis_p999_v1`（train p99.9）；
4. `dig_joint_regularized_mahalanobis_p9995_v1`（train p99.95）；
5. `dig_joint_regularized_mahalanobis_p9999_v1`（train p99.99）。

五者共用同一 strict-train mean/covariance、precision 和 ridge
`max(trace(covariance) / D * 1e-6, 1e-12)`；每个阈值均以 strict-train squared Mahalanobis
score 的 `linear` 分位数计算。它们的唯一区别是上列已冻结的 train score quantile。该 Dig-only
family 与 A.1 的 `support_contract_v2` 候选 family 不同：A.1 的 axis / Return 候选不能作为这次
Dig 选择的成员，Dig 的结果也不重新选择或修改 Return v2。

每个候选必须报告三类预注册验证：

- 全部正常 held-out validation 的接受率；
- `validation_v1_edge` cohort 的接受率：该 cohort 在读取 target 前固定为“被
  `axis_p01_p99_v1` 拒绝、但属于 held-out validation 的正常 Dig 行”；
- 预注册明显陌生负对照的拒绝率。若只有 synthetic 负对照，只能报告
  `synthetic_obvious_ood_rejection`，不得把它表述为真实现场陌生状态证明。

合格候选必须同时达到 `validation_normal_coverage >= 0.99`、非空
`validation_v1_edge_coverage >= 0.99`、以及 `synthetic_obvious_ood_rejection >= 0.99`。
合格候选按 `synthetic_obvious_ood_rejection` 降序、`validation_normal_coverage` 降序、上述固定
family 顺序依次选择。三项门槛、负对照和 selection order 一经 manifest 固定便不能事后变更。
没有合格候选、edge cohort 为空、来源泄漏或 target 调参时，Dig 保持 v1；不得放宽范围，不得改
runtime handoff。

### 条件性完整阶段 A 重跑

仅当 Return 原因审计与 Dig 独立验证都以 `completed` 状态写完各自 no-overwrite 工件后，才启动
新的 **完整、no-overwrite 的阶段 A 重跑**，输出根固定为
`act_goal_condition_sensitivity_v3/`。该重跑覆盖全部 10 个 Dig 与 9 个 Return stable segment，
保留原始 pair 选择、baseline replica、80% 门槛、三 anchor、四类分类优先级和 teacher-forced
证据标签。

重跑 manifest 必须逐 primitive 写明实际支持合同和原因审计 lineage：Return 在没有发现输入合同
错误时继续使用已选择的 v2；发现错误则先修正并建立新的冻结输入 lineage。Dig 只有独立验证选中
候选时才使用该候选，否则继续使用 v1。无论哪种情况，都不能覆盖 v1、Return v2 或阶段 A.2
工件；任何仍在 OOS、`goal_response_invalid` 或 `artifact_invalid` 的 primitive 保持该结论。

完整重跑只回答 Dig、Return 是否能在各自可信支持范围内稳定读取目标条件。只有两者都在其冻结
合同下完成有效重跑并获得 `goal_response_plausible`，才有资格准备后续 Unity 单铲目标效果对照；
v3 本身不进入阶段 B，仍不证明“指哪挖哪”、地形效果、安全或 production readiness。

## 阶段 A.3：Dig 数值支持范围异常的对齐与覆盖审计

### 固定对象、边界与输入

本阶段只审计 v3 中唯一的 Dig OOS 段
`dig:1044-1083:37a4b7afda73`。它保持同一 JSONL/HDF5、同一 strict Dig training config、同一
`axis_p01_p99_v1` 和同一 Stage-A 分类；不改 p01/p99、不选择新候选、不训练、不创建训练 HDF5、
不改 runtime handoff、Planner、安全阈值、timeout、Unity 或真实设备。

工件必须以 no-overwrite 根 `dig_support_outlier_audit_v1/` 输出逐帧 table、对齐结果、分布结果、
处理决定和所有输入 SHA。每份输出固定标记
`teacher_forced_recorded_observation`、`diagnostic_only=true`、
`promotion_eligible=false`、`closed_loop_claim=false`。

### 先排除数据合同错误

每帧必须保留 action JSONL/HDF5 index、action step、前一帧 observation step、`qpos`、`qvel`、
完整 10D `dig_cut_tokens` 以及 v1 每维 p01/p99。审计必须证明 action 使用前一帧 observation、
JSONL/HDF5 action 行连续、token 稳定、没有段内 skill switch 或 policy reset。

`qvel[1]` 的字段名只能从 HDF5 metadata 记录为 `boom_speed`；没有显式单位或 qvel-specific scale
metadata 时，物理单位固定写为 `not_inferred`。它必须与 strict-train Dig HDF5 的 dtype、字段顺序和
原始表示一致。严格训练支持范围只允许 `action_loss_mask=1` 的行；mask=0、其他 primitive 和被
split 排除的 Dig primitive 窗口只能作为诊断对照，不能回填或扩展支持范围。

若上述任一对齐、字段或时间合同失败，处理决定只能是 `repair_data_contract_then_rerun_stage_a`；
不得把当前 OOS 解释为 ACT 能力限制。

### 覆盖与保留验证边界

对通过对齐的段，报告 qvel[1] 的整个段区间和仅 OOS 帧区间、连续 OOS run、每帧最近 strict-train
Dig state（固定的 v1-span-normalised L2 仅作描述）、同 qvel[1] OOS 数值区间在 strict-train
mask=1、held validation、mask=0、其他 primitive、排除 Dig 窗口中的行数与谱系。最近邻和单轴数值
相近都不能自动证明完整状态已获支持，也不能成为新阈值。

held validation 只能展示正常状态在既有 v1 下的位置；目标段不得参与任何候选拟合、分位数、距离
阈值、排序或验收。此前 Dig 五种预注册 joint family 均未通过保留验证的 normal/edge/OOD 三项门槛，
所以 A.3 即使发现 qvel[1] 在训练中有数值先例，也不能宣称 v1 过于保守或放宽 runtime。

### 处理决定

1. 对齐错误：修正数据合同后，以新 lineage 完整重跑阶段 A。
2. 短暂记录异常：只有逐帧证据确实显示孤立异常或采集/QC 失配时，标为不适合作为能力证据并追查
   采集；不能凭 OOS 标签自行断言异常。
3. 没有已验证的完整状态支持：保持 v1，在 runtime 对该 Return→Dig handoff 拒绝或停止。若任务
   确实要求覆盖这类姿态/速度组合，采集对应专家数据并在新的 source-disjoint 合同下重训。

本阶段不进入阶段 B。它只决定当前 OOS 能否作为可靠能力证据，以及在没有新证据时必须保持何种
fail-closed 处理。

### A.3 已完成的离线结论

固定段的对齐检查已通过：40 帧 action 均绑定前一帧 observation，JSONL/HDF5 行连续，token
稳定；`qvel[1]` 的 metadata 字段为 `boom_speed`、表示为 raw float32，但物理单位仍为
`not_inferred`。OOS 是 action 1048–1064 的连续 17 帧，不是单帧突刺，也没有段内 reset 或
skill switch。

该 OOS 帧的 `qvel[1]` 数值区间在 strict-train、`action_loss_mask=1` 中有 253 行，在 held
validation 中有 116 行；所以不能把单轴速度 OOS 直接说成训练从未见过。但这也不能把该段列为
受支持状态：五种 Dig joint 候选仍未通过 held-validation 合同。当前处理决定是保持 v1，并在
runtime 对这类 Return→Dig handoff 拒绝或停止；若后续任务必须允许它，应采集对应完整状态的专家
数据并在新的 source-disjoint 合同下重训。

## 阶段 A.4：Dig 局部完整状态支持合同验证

### 预注册规则与来源边界

此阶段只读取 strict-train Dig 的 `action_loss_mask=1` 行：完整 18D
`qpos + qvel + dig_cut_tokens`、对应 4D 专家 action 和 source episode provenance。每一维尺度只能
从 strict-train 计算，按 median、IQR/1.3489795003921634、MAD/0.6744897501960817、相对 epsilon
fallback 的固定顺序处理；不能让 `qvel[1]` 单独主导距离。

固定候选 family 为：

1. `dig_local_complete_state_k8_sources2_v1`：8 个邻居、至少 2 个不同 source episode；
2. `dig_local_complete_state_k16_sources2_v1`：16 个邻居、至少 2 个不同 source episode；
3. `dig_local_complete_state_k32_sources3_v1`：32 个邻居、至少 3 个不同 source episode。

每个 strict-train source 最多固定均匀抽取 128 个 calibration query；该 query 的同 source 行必须
从参考集排除，参考集仍为全部其它 strict-train source 行。每候选的 kth-neighbour robust-scaled
18D L2 半径、邻居 action 到分量中位数的总 L2 偏差和四轴最大偏差，均以这些 strict-train calibration
query 的 `linear` p99 冻结。候选需要同时满足近邻数量、跨来源数、距离和总/各轴动作一致性。

### 保留验证选择与目标隔离

候选冻结后才在 source-disjoint held validation 上测正常状态接受率，并对 validation-derived
frozen obvious-OOD 数值负对照测拒绝率。合格条件固定为：

```text
validation_normal_coverage >= 0.99
synthetic_obvious_ood_rejection >= 0.99
```

合格候选按 OOD 拒绝率降序、正常验证覆盖率降序、上述固定顺序选择。目标 OOS 段、其分类、动作、
token 和任何派生统计不得进入拟合、scale、近邻数、来源数、距离阈值、动作一致性阈值、排序或验收。
validation/OOD 只能写紧凑摘要与 digest；完整邻居 action/provenance 只在已选择候选后的独立 target
诊断工件中出现。

局部规则只代表 Dig 的离线候选，不能直接成为 runtime 通用放行。若没有候选通过，保持 v1 拒绝；
若有候选通过，仍需独立审计固定 OOS 段，并且只把它视为正常尾部候选，不进入阶段 B、Unity 或
production runtime。

### A.4 已完成的离线结论

三条候选对 validation-derived frozen obvious-OOD 都达到 1.0 拒绝率，但 source-disjoint 正常
held validation 接受率分别仅为 0.466498、0.620476、0.583632，均低于预注册的 0.99。因此
`dig_local_state_support_validation_v1/` 的状态为 `support_contract_not_selected`，没有冻结候选可
用于固定 OOS 段的 target 支持诊断，更不能替代 v1 或进入 runtime。

这说明“单轴速度和局部最近邻存在”仍不足以证明局部合同可泛化到独立来源。因此停止继续为这一个
Dig OOS 样本设计自动放行规则，也不修改历史 v3 的 `out_of_support` 记录。研究决策是把它作为
**可接受的尾部观察样本**加入后续 Unity/闭环 Dig 单铲测试；Dig 的 9 个稳定响应段加上这个已通过
对齐审计的尾部样本，构成“Dig 可读取并跟随条件”的离线测试准入证据。它不等于 runtime 通用支持、
真实地形效果、安全或 production 放行。

若未来需要 runtime 覆盖该 handoff，仍须先采集跨来源的完整状态与一致专家 action，再重新预注册
并验证合同；不能以本次 OOS 个例调低来源数、距离或动作一致性门槛。

## 阶段 A.5：Return temporal dispatch 合同验证

### 先冻结旧策略抵消证据

`return_temporal_dispatch_forensics_v2/` 必须先复现既有 stability artifact 的 cache contributor、
legacy `predict()` 重建和 Stage-A response mask，再逐帧记录 source action step、query offset、
weight、4D raw action-delta、加权贡献和对最新 query 的反向投影。它只解释旧失败，不能用两段
`return:898-1043:bb329f176aba`、`return:3959-4161:4afcef2eee82` 选新策略。

### 预注册 temporal dispatch 候选

1. `legacy_100_oldest_first_decay_0p01`：当前 100-query oldest-first、decay 0.01，只作比较基线；
2. `newest_first_100_decay_0p01`：相同最大年龄、按最新 query 加权；
3. `newest_first_max_age_20_decay_0p01`：最新加权，明确最大 contributor age 为 20；
4. `latest_current_chunk_diagnostic`：只取当前 chunk query 0，永远 `diagnostic_only`，不可选择或上线。

每个策略必须显式 reset 于每段入口，baseline/alternate 使用独立 temporal state，且 contributor
不得跨 reset。候选只能通过 raw public ACT chunks 离线重建，不得在本阶段改默认 adapter/runtime。

### 独立 Return 保留验证与验收

验证集固定为 source-disjoint held Return 的每个 source 最多 8 个稳定段、按固定排序均匀抽样；
当前为两个 held source 共 16 段。counterfactual token 只从这批采样段的真实 Return envelope 循环
选择，coverage 固定表述为 `fixed_16_source_balanced_held_validation_segments_only`，不代表完整世界。

响应阈值固定为 `max(1e-6, 0.05 * strict_train_action_scale)`，每个 pair 和聚合都必须达到 80%。
动作质量边界只从 strict-train expert action 冻结：p01/p99 action envelope、per-axis action-delta p99
jitter/discontinuity reference。可选择候选必须逐 pair 和聚合都不比 legacy 更接近该分布边界或更不连续，
通过 replica、cache/reset、legacy 重建和 action-scale 稳定性核验，并严格提升 legacy 的聚合目标响应。

合格候选按更高聚合响应、更低 envelope violation、更低 discontinuity、更低 action-scale 比率、固定
strategy ID 排序。未选中时保持 legacy；选中时只冻结为 opt-in shadow candidate，随后才可进入 Unity/
闭环单铲验证实际铲斗轨迹、地形残差和安全约束，不能直接替换默认聚合策略。

### A.5 已完成的离线结论

历史贡献取证已确认两种机制同时存在。`return:898-1043` 有 33 个最新响应被压低的帧，其中 13 帧
是历史贡献净反向、20 帧是最新 query 权重稀释，最新权重仅 1.10%–2.66%；`return:3959-4161` 有
57 帧，其中 41 帧净反向、16 帧权重稀释，最新权重仅 0.62%–2.04%。这解释旧策略失败，但没有用于
候选选择。

独立 16 段 held Return 验证没有选出策略。legacy 的聚合响应为 0.953433，但已有两段低于 80%；
100-step newest-first 为 0.950034，最大年龄 20 的 newest-first 为 0.929640。两条可选策略都没有
严格改善 legacy 的聚合响应，并在至少一个 pair 的 envelope 或 discontinuity 质量门槛上更差，故
`return_temporal_dispatch_validation_v1/` 状态为 `dispatch_contract_not_selected`。默认 legacy 聚合
不变，不生成 opt-in shadow candidate，也不进入 Unity/闭环单铲验证。

## 阶段 A.6：受限 Return 闭环因果诊断（已授权，真实执行 `preflight_blocked`）

本阶段工件 ID 固定为 `bounded_return_closed_loop_causal_diagnostic_v1`。这是用户单独授权的 action-driving Return-only 诊断：
它会让选定的 Return policy 动作实际驱动 Unity，但不会启动完整
planner、连续作业或任何其他 primitive。整个工件固定为 `diagnostic_only=true`、
`promotion_eligible=false`；即使观察到清晰因果差异，也不能据此替换默认 temporal aggregation。

### 冻结的四个入口与 16 个试验臂

每个入口取阶段 A recorded replay 中首个 Return action 的前一帧 observation。任何 arm 都必须实际应用
完整 `qpos + qvel` fixture，不能只恢复关节位置：

| fixture | 历史段与 pre-action observation | qpos | qvel | original → alternate |
| --- | --- | --- | --- | --- |
| `F1` = `return:898-1043:bb329f176aba` | observation 897 | `[0.74795699, 0.34310636, 0.30324715, 0.24549121]` | `[-0.15910102, 0.06749017, -0.07764082, -1.59256399]` | cell 0 → cell 4 |
| `N1` = `return:3453-3664:bb329f176aba` | observation 3452 | `[0.75891024, 0.17245358, 0.46108255, 0.18568459]` | `[-0.23446512, 0.07024936, -0.20576259, -1.59381640]` | cell 0 → cell 4 |
| `F2` = `return:3959-4161:4afcef2eee82` | observation 3958 | `[0.75662756, 0.45767179, 0.32543743, 0.24470162]` | `[-0.18330808, 0.14484043, -0.35911530, -1.59288502]` | cell 4 → cell 1 |
| `N2` = `return:4437-4633:4afcef2eee82` | observation 4436 | `[0.75445473, 0.34224159, 0.36418903, 0.25357413]` | `[-0.07492465, 0.19027799, -0.20308734, -1.55695999]` | cell 4 → cell 1 |

四个 fixture 都运行 `original` / `alternate` × legacy / latest-current-chunk，共固定为
`16-arm/no-retry`。legacy 的精确 ID 是 `legacy_100_oldest_first_decay_0p01`；latest-current-chunk 的
精确 ID 是 `latest_current_chunk_diagnostic`。后者只取当前 chunk 的 query 0，并且
`latest_current_chunk_diagnostic` 只作因果诊断对照，永远不可选择、晋级或成为默认派发。

A.5 已拒绝的 `newest_first_100_decay_0p01` 和 `newest_first_max_age_20_decay_0p01` 不得复活，也不构成
A.6 的额外试验臂。每个 arm 使用独立 policy/temporal state，在 fixture 应用并完成 preflight 后只
reset 一次；目标 token、checkpoint、stats、相机顺序、action scale 和安全配置在首个动作前锁定。
执行顺序必须在工件 manifest 中预注册，不能根据前序结果调整。

### 动作前的强制 preflight

任何 arm 发出非零动作前必须同时满足：

1. fixture 服务已经实际应用完整 `qpos + qvel`，并由响应明确确认 `qpos_applied=true` 和
   `qvel_applied=true`；随后观测到的四轴位置与速度须落入预注册容差。只回显请求值不算应用成功。
2. 同一 fixture 的四个 arm 必须恢复同一完整地形状态，并匹配可观测地形状态、scene SHA、runtime build、四相机顺序和输入 SHA；
   checkpoint、dataset stats、Return config、original/alternate token
   与动作缩放也必须逐项匹配。107D 可观测地形指纹只能用于复核，不能代替隐藏土壤状态的恢复证据。
3. RESET 目前只确认 Unity managed random seed；`soil_seed_status=not_supported`，所以 seed 相同不能
   证明 AGX 隐藏土壤状态相同。动作前必须有完整地形快照恢复，或可验证的确定性 soil seed 恢复；
   只有可观测地形指纹而没有上述任一能力时，整个矩阵保持 `preflight_blocked`。
4. `scenario_id` 当前只解析、不选择场景。不得把请求中的 scenario 字符串当成场景已切换；必须以
   实际加载的 scene SHA、runtime build 和相机合同为准。

当前 Unity `REALIGN_POSE` 会清零速度并报告 `qvel_applied=false`；历史 source 也只记录可观测地形，
没有可恢复的完整土壤快照或确定性 soil seed。现有协议还没有实际施加动作、逐轴限位干预的原子遥测，
专用 runner 也尚未接入正式 Return handoff evaluator。因此真实 action-driving 执行必须保持
`preflight_blocked`。不得以 qpos-only、zero-qvel surrogate 冒充原始入口；observable-only terrain
surrogate 同样不能冒充原始地形。不得通过放宽容差、删除速度检查、前滚几步后近似命中或把请求值写进
manifest 来绕过。fixture 缺失或任一 lineage 不匹配时，该 arm 记录阻塞并结束；`no-retry` 禁止自动换
seed、换入口或补跑替代臂。

Python 侧先用已有阶段 A v3 与 source-disjoint Return 验证工件生成 no-overwrite runtime lock；这一步只读
源码和工件，不连接 Unity：

```bash
python -m testbed.cli.return_closed_loop_probe \
  --stage-a-v3-root <act_goal_condition_sensitivity_v3> \
  --return-training-config <return_training_config.yaml> \
  --return-validation <return_temporal_dispatch_validation_v1/validation.json> \
  --runtime-lock <new_runtime_lock.json> \
  --output-root <new_probe_root> \
  --prepare-runtime-lock-only
```

随后去掉 `--prepare-runtime-lock-only` 运行正式 preflight。只有 lock 与全部 16 个 arm 的动作前检查都通过，
并另有明确动作授权时，才可加 `--execute`。当前预计结果是 `preflight_blocked`，且
`nonzero_action_count=0`；blocked 工件仍须写出 `manifest.json`、`preflight.json`、`arms.json`、
`results.json` 和 `report.md`，作为没有运动的能力审计证据。

### Return-only 执行与安全终止

每个 arm 的硬上限为 420 个 STEP。只允许冻结 Return checkpoint 产生 4D action，禁止 scheduler
转入其他 primitive。运行中只观测 Return→Dig handoff；观察到 handoff、达到 420 步上限或触发任何
安全停止后，都执行 zero action → neutral acknowledgement，然后结束该 arm。不得进入 Dig、Carry 或 Dump。

动作边界、碰撞、高力、非法 contact lineage、硬底、卡死和 timeout 沿用当前冻结安全合同；
不修改 production/default runtime、安全阈值或 timeout。任一安全停止都保持原始失败结果，不允许 latest 路径、
替代目标或自动重试绕过。

### 必须记录的闭环证据

no-overwrite 工件至少逐 STEP 记录：

- 同步图像、`qpos/qvel`、请求动作、实际施加动作、逐轴限位干预和 temporal contributor；
- 铲斗轨迹、目标包络命中、轨迹分离起点、动作抖动/跳变/边界、碰撞与安全停止；
- 每个目标的最终位置与姿态误差、首次进入及持续保持包络的时间、handoff observation；
- RESET/fixture 报告、可观测地形指纹、scene/build/camera/SHA lineage、停止原因和 neutral ACK。

解释边界固定如下：legacy 下 original/alternate 已分开，支持 teacher-forced 限制是离线失败的重要原因；
legacy 趋同而 latest 分开，只支持“历史聚合可能压制条件响应”；两者都趋同，原因更可能位于目标表达、
ACT 条件能力或动力学执行；两者都分开但 latest 更抖、越界或触发安全停止，说明 legacy 平滑具有价值。
这些结论都不允许 latest-current-chunk 晋级，也不允许修改默认策略；任何生产候选仍需另行预注册、实现和批准。

## 阶段 A.6-S：Return 在线 pose-matched 因果冒烟测试（独立低证据诊断）

这是独立于严格 A.6 的 opt-in 快速诊断，工件根固定为
`return_online_pose_matched_causal_smoke_v0/`。它不会修改、放宽或绕过 A.6 的完整状态恢复和
fail-closed 合同，也不能把 zero-qvel、可观测 107D 或当前场景冒充历史失败状态复现。

### A.6-S-0：四姿态无动作 REALIGN/readback 预检

任何新的 16-arm 工件目录、ACT policy、世界位姿 probe 或非零动作之前，必须先通过独立的
`return_online_pose_matched_realign_preflight_vN/`。它只运行 F1、F2、N1、N2：每组固定
`RESET(seed=1000)` → `REALIGN(qvel=0, hold=true, lock-application=1 STEP)` → 20 个严格 4D 零动作
保持锁定。RESET 内部零步与 REALIGN 的 1 个锁定应用步都不计入这 20 步。结束时另发一次显式
`zero + release_realign_pose`，记录 transport ACK 后才断开，避免留下诊断锁会话。

预检在 REALIGN 后、第一条 neutral 后和第 20 条 neutral 后都写入 Unity 原始关节位置、由观测端
生成的协议归一化关节位置、原始关节速度、observer profile 路径/SHA/四轴范围、锁状态、速度控制器
状态和 hold 生命周期。qvel 的 Unity 语义固定为 `raw_identity`；请求零 qvel 表示清刚体速度和力，
不是历史非零 qvel 回放。归一化的唯一所有者是 `ActObservationCollector`：REALIGN 的反归一化、
diagnostics 的归一化与 controller 的临时 soft-limit 视图都从该 live owner 取得同一份四轴范围。

通过条件不能只看“锁 target 已写入”。四组都必须在冻结 `1e-6` 下读回 requested normalized qpos，
20 步后原始 qvel 收敛到 `<=1e-6`，20 步期间 lock 不得被普通 neutral 解除，最后显式 release 必须
得到 ACK。训练时物理 qpos profile 的 SHA、范围和顺序还必须能从冻结 HDF5/训练 lineage 证明，并与
live observer profile 完全一致；同名 `YuLong_norm.json`、当前场景或 ACT 的 z-score stats 都不是该证明。
缺少这项来源证据的固定阻断项是 `training_qpos_normalization_unproven`。

早期 `.../return_online_pose_matched_realign_preflight_v0/` 与 v1 的 20-step 检查说明：偏差从
REALIGN readback 就出现，不是第一条 neutral 解除锁；F1/F2/N1/N2 的最大 normalized qpos 误差为
0.387385、0.365194、0.255008、0.326443，20 步后仍不收敛且 F1、F2、N2 出现 bucket ×
`Dig_ZMin_Board` 接触。该工件只说明较长 live 物理演化会失控，不足以判定目标 pose 本身穿入板体。

为分开三类原因，独立的
`.../return_realign_no_motion_calibration_v0/` 固定改为：`RESET` →
`REALIGN(hold=true,burn_in=0)` → 物理步前 diagnostics → **一条** held-zero physical STEP →
物理步后 diagnostics → zero-release。四组均未加载 policy、未进入 Return、未发送非零动作。实际结果是：

- 当前 `YuLong_norm.json` 的请求 normalized qpos、Python 以 live min/max 独立反归一化的 raw qpos、
  Unity `requested_qpos_raw` 和四个 lock target 在 `1e-6` 内一致；四个 lock 均写入
  `swing_joint/boom_joint/stick_joint/bucket_joint` 且 enabled。因此现有 profile 解释下，不是
  “归一化映射错”或“lock target 写到错误约束”。
- 现有无碰撞独立 hinge 链以固定 128 solver steps 对四个 raw target 全部收敛，逐轴误差为零；
  按当前 profile 解释 normalized qpos 后，当前场景的 shadow-FK convex-cover 四墙 endpoint 查询也全部 clear，F1/F2 对 `Dig_ZMin_Board`
  的最小 clearance 分别约 1.474m/1.517m。首条 held-zero physical STEP 没有板、地板或外部 bucket
  接触。因此不能把 F1/F2 称为“当前场景中天然穿入该板”；早期 20-step 接触是 live 物理路径中的独立
  失败，不能被忽略，但也不能倒推为 target-pose 穿入。
- 四组首条物理步后的 qpos 仍分别距请求 0.387385、0.365194、0.255008、0.326443，raw qvel 峰值约
  1.24/1.24/1.23/1.24。这保留为 `physical_reachability_unresolved_after_one_held_physical_step`：
  当前 live 物理链没有把正确的锁目标变成 readback pose；一步证据不能声称绝对不可达，更不能归因于 ACT。

历史物理 qpos 归一化谱系现正式为 `unknown`。训练 Return 的 422 个 HDF5、其 17 个原始来源和冻结
rollout 只记录 qpos order；均没有 profile path/SHA/raw min/max。rollout 虽记录 base commit
`2ef274…`，也明确 `unity_git_dirty=1`。当前 live profile SHA 是 `1a73cf05…`，base profile SHA 是
`f3e4d105…`，四轴范围不同，故两者都不能当成训练 profile。F1/F2/N1/N2 从此只能称为
**normalized-qpos pose surrogate**，绝不能称为历史物理姿态复现。

### A.6-S-1：当前 RESET fixture 在线路线

在线 ACT 测试不再要求历史 F1/F2/N1/N2 physical profile、隐藏土体恢复或 16 臂历史矩阵先通过。
历史 fixture 只保留给离线 temporal aggregation 归因。当前在线路线固定为：从当前 Unity `RESET` 的实际
readback 开始，不 REALIGN 到历史 qpos；执行固定 20 个零动作 settling；冻结最终的真实 qpos/qvel、107D、
四路 decoded RGB SHA、profile SHA、scene/build/camera 合同为一个新 fixture。每个 original/alternate ×
legacy/latest arm 都独立 `RESET + 同一 settling`，并且必须同时匹配该 fixture；任一 pair 不一致，全部四臂
在 policy 创建前阻断。latest 仍只作诊断，legacy 默认不变。

`.../return_current_reset_fixture_v0/` 已实际通过：最终 qpos 为
`[0.5, 0.262185544, 0.694795728, 0.346762478]`，profile SHA 为 `1a73cf05…`，最大 qvel 约
`5.66e-8`，20 步内无接触。它是 current-reset fixture，不是历史姿态或土体复现。

`.../return_current_reset_goal_response_v0/` 首次以冻结 N1 的 original/alternate target pair 预检四臂。
qpos、qvel、107D 连续字段、scene/build/camera descriptor 全部一致；但 original/latest 的 `eye_right`
decoded RGB SHA 变为 `5b005877…`，而 fixture 及其他三臂为 `20b90c27…`，所以 4/4 在 policy 前阻断，
实际非零动作数为 0。该 v0 不表示 ACT 不响应，只表示视觉输入的严格字节相等还未建立。

用户明确选择不追逐逐帧绝对像素相等后，独立的零动作相机等价性标定先运行同一 RESET 内四次采样，
再运行四个独立 RESET cycle。`.../return_current_reset_camera_equivalence_v1/` 的跨 RESET 结果中，
只有 `eye_right` 在一组比较出现变化：最大通道差 4、平均通道差约 0.000936、变化像素比例约 0.1085%；
其余三路为零差异。使用同一 N1 original token、冻结 qpos/qvel/env state 和独立 reset cache 的 ACT 推理，
legacy 与 latest 的最大首动作差均为 `3.70e-6`，远低于既有 strict-train action-delta 合同。该工件只把
这一已测量的小幅视觉变化标为 current-reset 起点的动作等价，不改变相机、policy、legacy 默认或安全阈值。

基于该冻结等价合同，`.../return_current_reset_goal_response_v1/` 实际执行 4/4 臂，Unity 对 111 次非零
命令给出 transport ACK，四臂均在首次土壤接触时 zero→neutral ACK 终止。首次接触前，original/alternate
bucket-tip 轨迹都满足 2cm、连续 3 帧分离：legacy 在第 4 帧首次分离、共同 28 帧内最大距离约 0.315m；
latest 在第 5 帧首次分离、共同 19 帧内最大距离约 0.164m。可是 legacy original/alternate 分别在第
36/29 步接触，latest original/alternate 分别在第 26/20 步接触，全部是 soil contact。因此正式结论为
`safety_window_short`：当前 RESET fixture 下存在接触前的目标条件轨迹分离诊断证据，但安全窗口不足，
不得把它提升为完整在线目标响应、目标包络成功、ACT physical-effect 或生产结论；更不能把接触后的轨迹
用于目标响应判断。

为人工核查“首次土体接触是否与 token 所要求的运动一致”，同一已授权的四臂矩阵另以全帧四相机录制方式
写入 `.../return_current_reset_goal_response_v2_video_capture_v0/`。每臂保存四路单视角 MP4 与一个 2×2
合成 MP4；视频帧带有 camera 名称、帧号和接触状态，并且在首次 soil contact 帧后立即停止。这个工件仅供
观察接触前后的画面，未改变 policy、默认 legacy temporal aggregation、安全阈值或上述
`safety_window_short` 结论；视频本身也不能证明接触是 token 必然要求还是异常动力学结果，须结合 token 和
首次接触前的 trace 判断。

旧的 `.../return_current_profile_origin_v0/` / `return_current_profile_goal_response_v0/` 是本路线改写前的
过渡工件：后者仅执行 1/4，30 次非零命令后发生土壤接触并安全停止，状态为 `partial_execution/invalid`。
它不构成 current-reset 路线的 ACT 结论，也不应被补跑或与新工件混合。

### A.6-S-2：自动候选 Return 起点与 legacy-first 在线路线

新的独立入口 `tb-return-auto-candidate-goal-response` 从 Stage-A v3 的全部 9 个 Return segment 读取
`action_step-1` 的首个 pre-action observation。历史 normalized qpos 只作为当前 live profile 下的
runtime-only override 种子。旧 HDF5 的物理 qpos 归一化谱系继续固定为 `unknown`，不恢复历史 qvel、土体
或接触状态，也不把选中结果称为历史姿态复现。

候选资格与排序在连接 Unity 前冻结。original/alternate 必须通过既有 26D Return 支持模型和阈值
`73.96288339909502`；历史首帧不得有 dig/soil、墙、地板或 hard collision。历史 DumpArea mask 只记录，
不作为淘汰项。顺序固定为正常段优先，再按 DigArea 距离降序、qvel L2 升序、两目标最差支持余量降序和
起始 step 升序。9 个候选全部只做一次无动作预览，最终始终取该顺序中的第一个通过者，不按 policy 输出、
轨迹或接触结果重排。

每个候选与每个执行臂都进入独立 Play 会话。新的 Editor 桥只切换当前场景的 Play/Edit 状态，不调用场景
或资产保存，也不打开场景。候选执行 `RESET(seed=1000)`、`REALIGN(burn_in=0,hold=true,qvel=0)` 和 20 个
held-zero STEP。门控包括同一 normalization owner 的映射/lock target、`1e-6` readback 与末三帧稳定性、
四块 DigArea 板的 shadow-FK convex-cover clear、完整无接触遥测、四相机合同、FK 世界位姿以及 settled
qpos/qvel 对两枚 token 的冻结支持。任一失败只淘汰该候选；不放宽阈值，不重跑挑结果。
接触监控必须在每个 STEP 明确返回 `worktool_contact_monitor_status_v1:status=ready`；只有这个 ready
哨兵存在时，缺省的 `bucket_contact_diagnostic:contact_count` 才解释为零。ready 缺失、monitor missing 或
not_registered 都按接触遥测不完整停止，不能靠 107D 中的零值推断无外部接触。

选中后冻结 `selected_fixture.json`，再在同一 RESET/settle 状态下采集四次零动作图像。逐相机记录最大
像素差、平均差、变化像素比例和变化通道比例；每份图像用独立 policy/cache 对同一 original token 做
legacy/latest 影子推理，首动作差必须落在既有 strict-train 阈值
`[0.077259831,0.053346492,0.068022251,0.120000005]` 内。这里不要求像素 SHA 完全相同，且影子动作绝不
下发 Unity。

在线阶段先只运行 legacy original/alternate。每臂独立重新进入 Play、RESET、override、20 步 settle、
加载 policy 并只 reset cache 一次；只允许 Return、最多 420 STEP、不重试。第一次 soil、外部 bucket、板、
墙、地板接触，碰撞、接触遥测缺失或安全停止立即 zero→neutral。trace 和视频保留首次接触响应帧，轨迹
比较严格排除该帧及以后数据。legacy 在共同接触前窗口形成 2cm、连续 3 帧的 bucket-tip 分离时，报告
`precontact_online_goal_response_observed` 并停止，不自动运行 latest。只有两条 legacy 均无接触完成 420
步且未分离，才准入 `latest_current_chunk_diagnostic` 两臂。latest 仍只用公开 chunk API 的首动作，默认
legacy temporal aggregation 不变。

默认 no-overwrite 根为 `.../run/return_auto_candidate_goal_response_v0/`。工件包含全部候选历史/Unity
四视角、readback 和淘汰原因、相机动作等价性、接触前轨迹图，以及实际执行臂的四路单视角和 2×2 合成
MP4。该路线只能回答“当前 profile、当前场景、可验证一致起点上，只换 Return token 时，接触前真实轨迹
是否改变”。它不解释历史 F1/F2，不证明 applied action、目标包络完成、Return→Dig handoff 或生产能力。

2026-08-20 的首次 `return_auto_candidate_goal_response_v0` 真实运行完成了 9/9 候选的首个 held-zero
预览，但在第一步把接触监控的 `status=ready` 哨兵误解析成接触对象，因此 9 个候选都被错误提前停止。
该工件执行臂为 0、非零命令为 0，只能作为 blocked 工件；它不证明候选发生了物理接触，也不构成 ACT
目标响应结论。解析器已增加回归测试并修复，同时将 20 步中的瞬态运动与 settled 末态 readback 分开；
遵守 no-overwrite/no-retry 边界，本次没有覆盖或补跑 v0。后续如获准运行，应使用新的工件版本根。

后续 v1 证明该自动路线的候选摆姿方法本身不适合作为在线首门：它通过旧 `REALIGN` 从 RESET 姿态沿物理
路径运动到候选，六个候选在过渡途中碰到 `Dig_ZMin_Board`，其余三个在 20 步内也没有到达各自请求姿态。
这些接触发生在 policy 创建和 token 动作之前，不能用于判断 ACT。该路线保留为失败诊断，不再补跑，也不
再把 `REALIGN` 当作下面人工预览路线的实现。

### A.6-S-3：人工选择、Play Mode 临时 pose override 的 Return 诊断

新入口 `tb-return-manual-pose-matched` 第一阶段只生成 6–12 个候选的历史/当前 Unity 四视角预览，随后停在
等待操作者明确选择的状态。候选仍来自冻结 Return segment 的 `action_step-1` observation，正常段优先；
历史 normalized qpos 只作为当前 profile 的关节姿态种子。该阶段不构建 policy、不进入 Return、不发送非零
动作，也不自动选择候选。

候选姿态使用独立协议 `runtime_pose_override_v1`，不调用 `REALIGN_POSE`。服务只存在于当前 Play Mode，
宿主使用 `HideAndDontSave`。安装期间临时关闭挖机碰撞形状，用四个主关节的 constraint lock 在隔离状态下
收敛；恢复原碰撞状态后只做一个接触验证物理步并采集 qpos/qvel、107D、四相机和 bucket-tip 世界位姿。
这个过程避免铲斗沿 RESET→候选的现场路径扫过挡板。目标姿态本身若与土壤、板、墙或地板接触，仍按当前
物理接触淘汰，不能因安装阶段隔离碰撞而忽略。

每个候选使用独立 Play 会话。退出前发送严格零动作并显式释放 override，RESET 后退出 Play Mode；Editor
控制器只切换 Play/Edit，不保存或打开场景。每次会话前后核对活动场景路径、dirty 状态和磁盘 SHA。默认
首次 `v0` 工件已如实保留为摆姿 lock 力饱和的 blocked 尝试；修复后的 no-overwrite 根为
`.../run/return_manual_pose_matched_return_smoke_v1/`，第一阶段输出
`candidates/contact_sheet.png`、`candidates/candidate_table.md`、逐候选 `preview.json`、`selection.json`、
manifest、preflight、空 arms、results 和中文 report。

操作者只能从标为可选的候选中明确给出 `Cxx`。第二阶段才会在各自重新进入的 Play 会话中运行 legacy
original/alternate；两臂从同一人工基准重新安装，policy/cache 独立。首次接触或安全停止即 zero→neutral，
接触帧及以后不参与目标响应判断。只有 legacy 在足够的无接触窗口内仍趋同时，才允许追加
`latest_current_chunk_diagnostic`；默认 legacy temporal aggregation 始终不变。该路线的证据类型固定为
`unity_manual_pose_matched_return_smoke`，只回答当前 profile、人工确认起点、接触前的目标单变量响应，不能
解释历史 F1/F2、完整 Return 成功或生产能力。

第一阶段 `.../run/return_manual_pose_matched_return_smoke_v1/` 已完成 9/9 候选预览，全部在当前 Unity 中
稳定且未观察到初始土壤、板、墙、地板或外部 bucket 接触。操作者明确选择 `C01`（历史 Return segment
起始 step 416）。第二阶段使用新的 no-overwrite 根
`.../run/return_manual_pose_matched_return_execution_v0/`。它不会改写第一阶段工件；`selection.json` 会冻结
选择来源及其 SHA。每次 C01 安装固定经过 RESET、`runtime_pose_override_v1` 和 20 个 held-zero STEP，
绝不调用旧姿态通道。运行前的四次零动作相机采样记录最大/平均像素差、变化像素比例及变化通道比例；同一
original token 的 legacy/latest 首动作差仍使用冻结 strict-train 逐轴阈值判定，不要求图像 SHA 完全一致。

第二阶段的 original/alternate 各自再经过独立 Play 会话的无动作起点采集；关节位置、关节速度和 107D
连续字段按 `1e-6` 比较，离散 mask、scene/build/profile/camera descriptor 精确比较。任何失败都会在 policy
执行实例创建前阻断非零动作。实际动作的第一帧显式释放 runtime override 并核对 Unity 返回的 controller
state restored 哨兵。每条结束路径再发送零动作、确认 STEP transport ACK、RESET 并退出 Play Mode；场景
路径、dirty 状态和磁盘 SHA 必须保持不变。每个实际执行臂保存四路单视角 MP4 和 2×2 合成 MP4。

首次第二阶段工件 `.../return_manual_pose_matched_return_execution_v0/` 在两个 legacy 臂各收到一条非零动作后，
因逐帧 bucket-tip probe 重用了 preparation 的 sample ID 而停止。该工件没有接触，也没有可比较世界轨迹；
它是测量链失败的 `inconclusive` 工件，不能称为安全窗口太短或 ACT 不响应。修复只让同一 Play 会话复用
同一个递增 probe session，并新增“测量链失败不得归类为安全窗口”回归测试；没有改候选、token、阈值或策略。

修复后的 no-overwrite 工件 `.../return_manual_pose_matched_return_execution_v1/` 完成了两个 legacy 臂。两臂
的 qpos、qvel 与 107D 连续字段起点误差均为 0；四次零动作相机采样仅 `stick_up` 一帧有轻微变化（最大通道
差 2、变化像素比例约 0.0732%），同一 token 的 ACT 首动作最大逐轴变化仅约
`[1.01e-6,1.56e-6,6.07e-7,4.65e-6]`，远低于冻结阈值。Unity 共确认 535 条非零 STEP；共同的 250 帧
接触前窗口中，bucket-tip 从第 10 帧开始满足 2cm、连续 3 帧分离，最大距离约 0.996m，因此结论为
`precontact_online_goal_response_observed`。original/alternate 分别在第 283/250 帧首次 soil contact 后停止，
没有板、墙、地板、外部 bucket contact 或 hard collision。alternate 在接触前第 226–245 帧进入自己的直接
目标包络，original 未进入自己的包络。因此本结果证明的是 legacy 在接触前会随 Return token 改变真实轨迹，
不证明两目标都完成、完整 Return 成功或土体效果正确。legacy 已分离，latest 按预注册规则未运行。
运行结束后的独立默认 RESET 回归又在全新 Play 会话中执行 20 个零动作 STEP；其 qpos/qvel 与运行前冻结的
RESET fixture 最大误差均为 0、无接触、非零动作数为 0，活动场景路径、dirty 状态和磁盘 SHA 也完全一致。
这项检查只证明本次 runtime-only override 已清除且默认 RESET readback 未变，不提升上述诊断的证据等级。

工件必须固定写明：

```text
evidence_kind=unity_online_pose_matched_surrogate
diagnostic_only=true
promotion_eligible=false
historical_state_replay_claim=false
production_default_changed=false
official_handoff_claim=false
```

它复用 F1/F2/N1/N2、original/alternate 和 legacy/latest 的 16-arm 矩阵，但每个 arm 只恢复 fixture
qpos，明确清零 qvel，并在 REALIGN 后执行固定 20 个 neutral STEP。original/alternate 的 post-settle
qpos、qvel、107D、四相机 RGB 指纹、scene、build 与相机合同必须在预冻结 `1e-6` 容差和精确指纹下
一致；不一致的 pair 直接 `invalid`，不重试。没有历史土壤快照、历史非零 qvel、正式 handoff evaluator、
actual applied-action 或逐轴限位遥测时，本诊断仍可运行，但这些限制必须写入 manifest。

每个 policy 独立加载并只 reset 一次。legacy 保持 `predict()` 的既有 temporal aggregation；latest 每帧
只用公开 `predict_action_chunk(obs).first_action`，永远是诊断对照，不能成为默认或上线候选。Return 期间
发生土壤、外部 bucket、墙或地板接触的 arm 标记 `contact_contaminated`；接触遥测无法确认时标记
`contact_telemetry_inconclusive`，两者都不参与目标响应结论。

线上“接近”固定为：相对 settle 后起点，bucket tip 到自身 token 世界平面中心的距离至少缩短 2 cm，且
持续 3 帧；直接 token geometry entry 另行记录，不等同正式 Return→Dig handoff。逐状态只允许报告
`legacy_online_goal_response_observed`、`temporal_aggregation_suppression_indicated`、
`online_goal_response_not_observed`（无 applied telemetry 时附加 `execution_chain_inconclusive`）、
`legacy_smoothing_value_observed` 或 `inconclusive/invalid`。不得将 blocked、部分执行、轨迹图或该 surrogate
描述为严格闭环目标跟随成功。

当前 Unity 协议没有逐帧世界 bucket/tip pose；本诊断只可使用既有、Temp-only、非原子
`FixedBucketTipFkCaptureProbe` 旁路并记录其 source SHA 和 `non_atomic_world_pose_capture` 边界。探针未在
Play Mode 前启用、每帧 capture 失败、5057 不可连接、GET_INFO/scene/四相机/107D 合同不匹配时，必须写新的
no-overwrite blocked 工件，不伪造运行结果。普通 RESET、planner、默认 temporal aggregation、安全阈值和
timeout 均不改变。

## 当前路线：Dig 单铲位置 A/B

### 实现入口与执行授权

只读校验正式 support 工件、冻结目标和合同 SHA 时使用：

```bash
tb-dig-single-shovel-ab validate
```

该命令不创建工件、不进入 Play Mode，也不发送动作。真实阶段 C/D 只能由显式授权的命令进入，
且 `--artifact-root` 必须指向一个尚不存在的新目录：

```bash
tb-dig-single-shovel-ab run \
  --artifact-root /absolute/new/artifact/path \
  --execute-authorized \
  --unity-editor-pid <PID>
```

`run` 先完成两个独立、可丢弃的 100 tick 预演；任一预演失败就不进入效果臂。进入阶段 D 后仍按
original→alternate 每臂一次执行，不允许重试或替换目标。所有结果固定保留隐藏土体未证明、仅作诊断、
不可晋级的证据边界。

进入任一 Play Mode 前还要检查本实验依赖的 Unity 运行时／Editor C# 源文件不晚于当前
`Library/ScriptAssemblies` 中对应程序集。若源码比已编译程序集新，说明 Editor 尚未完成导入或域重载，
必须以 `unity_script_assembly_stale` 在动作前停止。该时间戳检查只用于拒绝明显陈旧的运行时，不能替代
首个全零 STEP 的诊断 sidecar、协议版本、场景和运行 build 核验。运行时异常工件保留经过单行化并限制
到 300 字符的原始错误详情，避免只记录异常类型而丢失协议失败原因。

在线工件分别记录“已经完整解析并写入轨迹的 tick”和“Unity 已确认响应的效果 STEP 调用数”。后者在
收到 STEP 响应后、构造严格遥测对象前递增，因此即使响应后的 Python 校验异常，也不能把已发生的物理步
误报为零。缺少该可选计数接口的 mock/旧注入端只以完整轨迹行数作为保守下界。

JSON 工件不嵌入相机二进制。相机 JPEG 原始字节只进入四路视频；start/end 等 JSON 中对应 `data` 字段
改写为 `binary_sha256_v1` 的长度和 SHA-256 记录。固定 JSON 在创建目标文件前先完整序列化，序列化失败
不会留下看似存在的半截工件。

姿态稳定结束时，解除临时锁与首个诊断零动作必须由 Unity 在同一个 STEP 内原子完成。该请求只接受
四轴精确零动作，并在推进物理步前切换到经验证的静止锁；后续零动作继续保持，首个非零动作到来前才
恢复会话开始时快照的普通控制器配置。此交接是 Dig 实验请求局部能力，默认 STEP、生产控制参数和
既有安全阈值不变。交接后的实际 qpos/qvel 仍必须通过 `0.005`/`0.10` 原门槛，不能用该能力绕过初态核验。

### 阶段 B：收口目标与结果的数据合同

以 `ContinuousCutGoal` 作为唯一目标事实源，并用版本化的 `AchievedCutOutcome` 表示实际入土、最大深度、
出土、铲尖轨迹和六格土体变化。冻结 original/cell 2 与 alternate/cell 4，两个 10D token
只允许索引 1 和 3 不同。官方数值、目标 SHA、机械初态、成功阈值和时序合同由
`build_official_dig_effect_ab_contract()` 集中生成，运行时必须从正式 Dig v1 工件加载 18D 逐轴 p01–p99，
不复制一套支持范围。

### 阶段 C：建立短期行为安全盾

每个目标使用一个独立、可丢弃、不保存场景的 Play Mode 会话。RESET(seed=1000) 后安装冻结姿态，
零动作稳定 20 tick，并校验机械、铲尖、可观测六格地形、剩余质量、场景、build、四相机和离散 mask。
每个效果臂发送首个动作前，还必须证明它与全部已建立的预演/效果会话身份互不重复；不能等到结果汇总时
才发现会话复用。每个诊断 STEP 都必须显式给出铲斗接触计数和最大法向力，零接触也要报告 `0/0`；
缺失不能解释成没有接触。
默认 107D 的 `bucket_dig_area_penetration_contact_mask` 来自动态铲斗测量盒，是入土几何信号，并非刚体
接触回调。单铲 A/B 的正式诊断轨迹改用请求局部的固定中齿前缘点
`bucket_center_tooth_leading_edge_midpoint_v0_1`；Unity 在同一 STEP 中回报该点、局部表面深度和入土 mask，
Python 校验 schema、候选、lineage、有限值和 `0.005 m` 阈值后才使用。这样避免动态最低角点切换造成约
`0.44 m` 的伪跳变，同时不改变默认 107D 或生产观测。几何信号可以在可变形土体入侵时为真，而独立
worktool monitor 仍合法报告零刚体接触；两条证据都必须完整且各自自洽，但不要求同一 tick 同时上升。
墙、硬底、禁止/未知接触和力门槛仍由独立接触证明触发，现有停止阈值不变。
随后用独立 policy/cache 运行 100 tick 冻结 ACT 影子预演。预演不计入 A/B 效果证据，不得用专家路径替代，
也不得放宽安全阈值。墙、硬底、未知/禁止接触、碰撞、非有限值、动作裁剪、软限位、卡死、超时或
力大于等于 100000 N 都必须零动作并等待 neutral ACK 后停止。普通 bucket-only 可变形土体接触允许继续。
预演通过只记为 `diagnostic_preflight_passed`，不构成三维安全或同土证明。

### 阶段 D：同 reset 的 Unity 单铲目标效果对照

按 original→alternate 顺序运行，每臂重建 backend、Play Mode、ACTAdapter 和 cache，每臂一次、不重试，
最多 250 tick / 5 s。每个 STEP 要求默认关闭的 `actuation_diagnostics_v1` 原子回报，并保存 50 Hz 轨迹、
原始 chunk/派发/执行器动作、接触、力、六格移除深度、剩余土量和视频。任一启动失败也消耗该臂唯一机会。

最终工件固定为 `contract.json`、`preflight.json`、两臂各自的 `start.json` / `trace.jsonl` /
`end.json` / `summary.json` / video、`pair_metrics.json`、`decision.json` 和 `report.md`，全部 no-overwrite，
并绑定 Python/Unity HEAD、dirty 状态与依赖 SHA。只有两臂的轨迹、入土/深度/出土和目标 cell 效果都达标且无安全事件，
才输出 `next_experiment=return_to_dig_integration`；在隐藏土体一致性未证明时，该结论仍仅为诊断级。

2026-08-21 的在线收口使用 no-overwrite 根
`runs/eval/dig_single_shovel_ab_20260821T181507+0800/`。两个 100 tick 预演都通过；original 效果臂
保留 226 行 fsync 轨迹和 226 帧四路/合成视频，随后因铲斗轴软限位停止并完成 7 步 neutral ACK。
铲斗从第 59 步开始持续接触土体，最大局部入土深度 `0.34915972 m`，停止时六格移除深度为
`[0.00415147, 0, 0.02283448, 0, 0, 0] m`。这些局部土体变化不能覆盖“无出土 + 安全停止”的失败，
也不能单臂推断 A/B 目标效果。`decision.json` 固定为 `realised_attempt_count=1`、
`planned_attempt_count=2`、`retry_allowed=false`；场景磁盘 SHA 前后保持
`97b01deb2229b087f110defef2c117f19c4ad8e16b1ad51d154fe5cc6514b7c9`。

对该工件的姿态配对复查发现，旧轨迹点会在相邻 20 ms 内跳约 `0.44 m`，根因是每帧重新选择测量盒的
最低角点，不能代表固定物理铲尖。修复采用上述请求局部固定中齿点，并由新合同版本映射和 source SHA
绑定；普通 STEP、checkpoint、legacy oldest-first 100-step 聚合和所有安全阈值不变。修复经 Python
相关测试 `198 passed`、Unity 静态协议测试 `26 passed`、运行时/Editor 程序集编译以及当前 Editor 内
3 项 no-save 测试验证；no-save 测试前后场景路径、dirty 状态和磁盘 SHA 一致。

用户重新授权的新 no-overwrite 根为
`runs/eval/dig_single_shovel_ab_20260821T193147+0800/`。两个 100 tick 预演及两个效果臂均完成，实际臂数
`2/2`。original/alternate 分别保留 `188`/`136` 个 50 Hz 效果 STEP，均检测到入土、连续 3 tick 出土并
完成 neutral ACK；最大力 `20972.54 N`/`12059.06 N`，未发生裁剪、软限位、墙、硬底、硬碰撞、禁止或
未知接触；现有加速度限速按原配置在每臂最初 6 tick 对称工作。修复后的最大单 tick 铲尖位移为
`0.014009 m`/`0.013997 m`，场景 SHA 保持不变。

能力结论仍失败。raw chunk 目标响应为 `100/100`，但接触阶段轨迹中位分离 `0.282983 m < 0.50 m`。
original/alternate 的入土误差为 `0.452967 m`/`0.860084 m`，最大深度误差为 `0.220922 m`/`0.276756 m`，
出土误差为 `1.406151 m`/`1.432217 m`。original 对 cell 2 的移除深度为 `0.021632 m`；alternate 对
cell 4 为 `0 m`，仍在 cell 2 移除 `0.004594 m`。分类为 `action_only_no_trajectory_separation`，不进入
Return→Dig 集成。原子回报未见 dispatch mismatch、输入裁剪或软限位；两臂只有最初 6 tick 出现相同的
既有加速度限速。传输裁剪和软限位不是本次直接原因，下一轮仍需一起审计目标 token 经执行器/动力学到
空间轨迹的映射和训练覆盖。隐藏土体未证明，结果保持诊断级、不可晋级且不改变默认系统。

### 阶段 E：有界多铲 residual 闭环

在继续阶段 E 前，2026-08-22 新增了冻结物理结果约束的离线支线，详见
`docs/dig_token_swap_effect_consistency_v1.md`。该支线没有补人类成对数据，也没有提高
`token_swap_loss_weight=1.0`。静态固定中齿 FK 和 planner 范围变体已通过，但冻结 effect
ensemble 未通过轨迹、末端、六格深度和 ensemble 分歧门，因此 A/B/C 均在 checkpoint 加载前
停止为 `0/2000`。当前路线是先修复 action→物理结果 predictor；不能据此进入正式重训或恢复
Unity A/B。

该支线随后在 strict-train 内完成了四折 source-grouped 一步动力学定位。source/episode 等权后，
fixed-tip 的 1/5/10-step per-source equal 误差为 `0.000725/0.005986/0.014777 m`，但
25/50/100-step 扩大为 `0.040282/0.071962/0.225685 m`。结论固定为
`long_horizon_dynamics_accumulation`。source 33/34 未重新用于选择；轨迹门失败，因此 soil head、
最终 predictor freeze 和 ACT A/B/C 都没有启动。

同一折上的自回归课程随后按 `5→10→25→50→100` 完成，bucket 被确认从第 5 步最先发散。加入硬
`qpos∈[0,1]` 投影后，100-step trajectory/endpoint/disagreement 改善到
`0.040195/0.056302/0.021728 m`，但仍未同时满足 `0.04/0.03/0.02 m`。短 action-history
残差信号不足，现有数据又缺少 target speed、acceleration limiter 和 cylinder response；这先形成待验证
假设，不直接扩模型或加 loss 权重。

随后完成了 bucket-only 有限历史直接比较。swing/boom/stick 的 checkpoint 参数和逐步输出保持冻结，实际
最大差为 `0.0`。5/10 步 action history 对第 5 步 bucket qvel 只改善 `0.45%/0.90%`；再加入 bucket
qvel 和冻结基座残差后改善 `8.55%`，95% 区间为 `[6.16%,11.19%]`，但仍未达到预注册的 30% 门，
qpos/fixed-tip 的 `11.23%` 改善也未达到 `30%/20%`。最相似跨 episode 历史的下一步响应差中位数为
`0.00169 < 0.02`，没有形成“同历史异响应”证据。误差主要集中在关节边界：near-boundary qvel h5
为 `0.178388`，interior 为 `0.0404995`，上端 20% qpos 区间还会在 response-history 模型下轻微恶化。
完整历史窗口只覆盖 374 个 train episode 中的 331 个，source 19/23 又分别只有 90/11 个窗口。因此当前路线
改为先审计边界/异常 episode 与 source 覆盖，不把 controller cohort 相关性直接解释为标定因果，
也不启动 soil/ACT。工件位于
`predictor_source_grouped_v1/bucket_only_v1/comparison_full_v1/`。

只读分层定位随后确认边界是主因素：距边界不超过 0.05 时，h5 bucket qvel source 等权误差是内部的
`4.772× [3.363,6.784]`；移除误差质量最高的 17 个 episode 后仍为
`3.105× [2.537,5.127]`。top 5% episode 虽占 per-window 误差 `43.67%`，但移除后 source 等权只改善
`11.00%`，未达到 episode 集中门。source 24/30 的 leave-one-source-out 改善为 `7.42%/4.45%`，但
qpos/qvel/前 5 步 action 配对后没有 source 通过样本数、平衡和 99% 区间门；epoch 的 h1/h5 配对区间也
都跨 0。当前路线因此固定为先收紧 predictor 证据范围，而不是删 episode 或追标定差异。

固定距离分箱给出的非对称离线可信支持候选为 `bucket qpos normalized ∈ [0.05,0.80]`。该值当前只写入
`bucket_only_v1/read_only_localization_v2/` 的诊断工件，默认 support、planner、ACT 和生产 joint limits
均未修改。只有将它接入 predictor 离线 gate 并重新通过轨迹/末端/分歧门后，才重新讨论 soil head 或
ACT A/B/C。

冻结 checkpoint 的内部范围复评随后完成。筛选只用真实 qpos/qvel/action：初始和真实未来 100 步 bucket
qpos 均在 `[0.05,0.80]`，过去 10 步、当前与未来 100 步 qvel/action 均通过原 strict-train p01-p99。
12,922/35,573 个窗口被保留。100 步 full-tip trajectory `0.031580 m` 和三成员分歧 `0.013407 m`
分别通过 `0.04/0.02 m` 门，但 endpoint `0.046381 m > 0.03 m`，所以 metric gate 仍失败。

覆盖门同时失败：仅 197 个 episode、14 个 source，source 19/23 完全没有保留窗口。结论固定为
`audit_actuator_state_or_change_predictor_structure`；边界只是最明显症状，收紧范围仍不足以冻结动力学模型。
当前路线是检查缺失的执行器响应状态或更换长程 predictor 结构，不训练 soil head、不加载 ACT，也不修改
planner/真实挖机 joint range。工件位于 `bucket_only_v1/internal_support_eval_v1/`。

一步残差状态归因随后完成。53,229 个内部 qpos/current-support 行上，OOF bucket qvel 一步 MAE 为
`0.015436`。静态载荷有描述性差异，但 empty/loaded 匹配仅 97 对、balance `0.1045` 且 99% 区间跨 0；
载荷变化率对照有 727/819 个平衡匹配，效果仍小且区间跨 0。depth、几何 contact、最近反向和
controller epoch/profile 也没有同时通过样本数、匹配平衡和 cluster bootstrap 门。

当前 HDF5 的 contact mask 几乎恒为 1，目标箱 force 在 Dig 中恒为 0；缺少 worktool/soil force、最终目标
速度、加速度/软限位 mask、bucket cylinder position/velocity 和液压压力/执行器力。路线因此固定为
`collect_missing_actuator_and_contact_telemetry`。只允许同初态、同 bucket 序列、no-contact/controlled-contact
各少量重复的 bucket-only 采集；其他三轴冻结，不运行昂贵 Dig A/B，不训练 ACT。工件位于
`bucket_only_v1/residual_state_audit_v3/`。

在实际补遥测前，周期性真实状态重锚给出了更低成本的路线判别。复用同一 12,922 个内部范围窗口时，
每 1/5/10/25 步重锚 qpos/qvel 的 100 步 endpoint source 等权误差为
`0.000433/0.003097/0.006721/0.016091 m`，全部低于 3 cm。worst-source 在 1/5/10 步间隔也通过，25 步
间隔的 source 24 为 `0.032449 m`，因此最大稳定间隔为 10 步。结论改为
`autoregressive_accumulation_primary`：当前观察足以支持短段预测，主要失败来自自回归累计。

下一路线只允许同预算比较小型 direct-trajectory 与 compact-hidden-state 模型。覆盖门仍因 197 episode、
14 source 失败，因此即使新结构过 3 cm 也不能直接晋级；还必须补内部自然操作覆盖。若新结构不能同时通过
3 cm source-equal/worst-source 双门和覆盖门，正式停止该离线物理约束支线，禁止用 5 cm 门重标成功。
工件位于 `bucket_only_v1/reanchor_eval_v2/`。

最终的等预算结构比较没有挽救该路线。direct full-trajectory MLP 与 compact action-history GRU 分别为
226,400/181,208 参数，使用相同 folds、三个 seed、sample schedules 和每成员 2,000 updates。direct 的
trajectory/endpoint/worst-source/disagreement 为 `0.109417/0.116209/0.184532/0.092906 m`；GRU 为
`0.091635/0.122010/0.181832/0.052354 m`。两者四项门全部失败，覆盖门也仍失败。

路线结论固定为 `stop_offline_predictor_route`。不冻结 dynamics predictor，不训练 soil effect model，
不恢复 token-swap A/B/C 或 ACT，也不把 endpoint 门从 3 cm 放宽到 5 cm。后续若继续 Dig 目标跟随，必须
另开具有新观测/新数据合同的路线，不能沿用本支线失败工件宣称物理约束已通过。工件位于
`bucket_only_v1/structure_comparison_full_v1/`。

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

## Dig dispatch 路线判定（2026-08-23）

已完成默认关闭的 `dig_act_receding_horizon_dispatch_diagnostic_v1`。112 个 planner-reachable 位置变体
各使用 100 帧相同 recorded observation，legacy contributor age 覆盖完整 `0–99`。物理侧只在每个
episode 的 91 个真实状态锚点做 5/10 步短投影，避免再次使用已失败的长程 predictor。

latest-chunk 的 10-step direction/ranking 为 `24.34%/50.26%`，legacy 为 `26.72%/50.33%`；两项都
没有达到 80%，也没有相对提高 15 个百分点。latest projected separation p10 只有 `0.485 mm`，低于
`20 mm` 门；direction 与 separation 的 paired bootstrap 还确认 latest 更差。raw goal response
仍有 `80.89%`，所以这不是 goal condition response 回归。action support violation 只增加
`0.27` 个百分点，没有超过 1 个百分点限制。

路线结论为 `temporal_dispatch_not_primary`。不修改默认 ACT dispatch，也不申请最小 Unity 单铲测试。
下一阶段改为 `goal_conditioned_act_vs_diffusion_policy` 架构对照；对照仍需冻结数据、相同 observation、
相同目标变体、source/episode 分组和独立 policy state。任何短期 FK/dynamics 结果都继续标记为
`short_horizon_projection_only`，不能代替 Unity 接触轨迹或目标 cell 土体效果。

权威工件位于
`runs/eval/dig_act_receding_horizon_dispatch_diagnostic_20260823T184504+0800/`。ACT checkpoint、训练、
Unity、planner 和 production/default 行为均未改变。

## ACT-vs-DP 前置数据门（2026-08-23）

公平架构对照尚未启动。先执行的 `dig_goal_action_identifiability_precheck_v1` 使用 primitive t0、完整
100-step 监督、正式 18D support、四相机和相同 controller metadata 检查“同状态、多目标、动作随目标变化”。

241 个可用 episode 中有 2,021 个同 source/metadata 组合，但 qpos `≤0.005`、qvel `≤0.02` 后为 0；因此
同目标噪声 pair 和 0.1/0.2 m 位置目标 pair 都为 0。112 个冻结目标的 planner base/alternate 自然示范覆盖
也是 `0/112`。该结果在动作或模型比较前就触发 fail-closed，不是 ACT 或 DP 效果判定。

路线改为 `paired_goal_action_demonstrations`。最小数据应满足：相同可恢复初态、相同相机与 terrain、至少两个
planner-reachable 位置目标、每目标独立示教、完整 100-step action 与 source/session lineage。先让 t0 状态门、
四相机门、同目标噪声基线、八个平移 bin 覆盖和 source/episode bootstrap 全部通过，再创建同预算 ACT/DP
训练 job。

不调整 temporal decay/window/weight，不启动 Unity，不训练土体模型。权威工件位于
`runs/eval/dig_goal_action_identifiability_precheck_20260823T205439+0800/`。

## 最小 DP 架构响应探针（2026-08-24）

为确认“换成 Diffusion Policy 是否会在相同数据上自行恢复 goal response”，完成了一次纯离线、不可晋级的
最小探针。它使用相同 strict-train source split、38,853 个 100-step 窗口、四相机、18D observation、10D
Dig token、三训练 seed 和三 inference-noise seed。每帧重新采样，只派发最新 chunk 的第一个动作，完全关闭
temporal aggregation。

结果没有形成架构改善：正确目标变化的 first-action L2 p10 仅 `0.000560`，raw goal response 为 0；
diffusion noise p95 为 `1.428145`，远大于 goal effect。direction/ranking 为 `30.08%/50.01%`，10-step
separation p10 为 `0.0274 mm`，训练 seed 方向一致率为 `6.65%`。动作 support 没有恶化且无非有限值，
但方向、排序、分离、bootstrap、noise 和 seed 一致性门全部失败。

路线分类为 `minimal_dp_probe_noise_dominates`。数据可辨识性门仍失败，因此该探针即使局部指标变好也不可晋级；
当前更没有理由调整 denoising steps、模型宽度或预算。下一步保持 `paired_goal_action_demonstrations`，不启动
Unity。权威工件为 `runs/eval/dig_minimal_diffusion_probe_20260824T150222+0800/`。
