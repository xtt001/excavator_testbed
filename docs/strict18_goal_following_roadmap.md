# Strict-18：从连续作业恢复到实时地形目标跟随

## 当前结论与文档地位

当前唯一授权的实现任务是**阶段 A.5：Return temporal dispatch 合同验证**。
它先解释 oldest-first 聚合如何抵消已记录的目标响应，再用独立 Return 保留数据选择一条 opt-in
dispatch shadow 候选。两段失败 Return 样本只用于历史取证，绝不能选择窗口、权重、年龄或阈值。
Dig 单例不再继续寻找自动放行规则；它保留为后续 Unity/闭环单铲观察样本。

已完成的离线证据是：阶段 A 的 Dig 有 9/10 段 `goal_response_plausible`、1/10 段
`out_of_support`；Return 在 v1 下均为 OOS。阶段 A.1 选择了 Return 的
`joint_regularized_mahalanobis_p99_v2`，其 9 段均在该规则支持范围内；随后 Return v2 重跑
得到 7/9 段 `goal_response_plausible` 和 2/9 段 `goal_response_invalid`。Dig 没有通过候选
验收，仍使用 v1。这些都是 teacher-forced 诊断结果，不构成闭环或生产结论。

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

`return_temporal_dispatch_forensics_v1/` 必须先复现既有 stability artifact 的 cache contributor、
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

## 后续阶段：仅保留为计划

### 阶段 B：收口目标与结果的数据合同

定义在线 `DesiredCutGoal` 与历史 `AchievedCutOutcome` 的边界，不能把专家实际结果当作
Planner 的原始意图。单一 primitive 的 v2 重跑不能进入阶段 B。只有后续 Unity 闭环所需的每个
primitive 都在各自冻结的 `support_contract_v1` 或已选择的 `support_contract_v2` 下完成阶段 A
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
