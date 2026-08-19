# Strict-18：从连续作业恢复到实时地形目标跟随

## 当前结论与文档地位

当前唯一授权的实现任务是**阶段 A：冻结 ACT 的目标条件敏感性离线审计**。它只检查：在
完全相同的记录观测、关节状态、图像历史、checkpoint 和 temporal aggregation 条件下，
仅替换目标条件时，冻结 ACT 是否产生稳定、可解释的动作变化。

阶段 A 只产生 teacher-forced recorded-observation 证据。它不是 Unity 闭环、真实机器
验证、生产证明或训练结果；本阶段不训练、不创建训练 HDF5、不运行 Unity rollout/live/1×10，
也不改变 production/default runtime、安全阈值或 timeout。

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

### 输出、失败关闭与分类

输出写入不可覆盖根目录 `act_goal_condition_sensitivity_v1/`。每份结果至少保留：

- baseline 对齐结果；
- 起点、中段、末段的 raw `100×4` action chunk 差异；
- 整段 temporal-aggregated 实际派发动作差异；
- token/envelope、checkpoint、stats、trace、config 与代码 lineage。

出现下列任一情况立即终止，不静默放宽容差：baseline 不能复现保存动作；观测、图像、qpos、
qvel、相机顺序或非目标低维输入在条件间不一致；token/envelope 在原 segment 内漂移；输出
目录已存在。

分类只能使用：

- `goal_insensitive`
- `goal_response_invalid`
- `out_of_support`
- `goal_response_plausible`

阶段 A 完成后停止并报告证据类型、baseline 是否对齐、Dig 和 Return 是否分别响应条件、
动作变化是否稳定且方向合理、production/default 是否改变，以及下一步建议。它不在本阶段
决定四类阈值或实施后续路线。

## 后续阶段：仅保留为计划

### 阶段 B：收口目标与结果的数据合同

定义在线 `DesiredCutGoal` 与历史 `AchievedCutOutcome` 的边界，不能把专家实际结果当作
Planner 的原始意图。只有阶段 A 产生 `goal_response_plausible` 证据后，才进入 Unity 单铲
目标效果对照准备。

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
