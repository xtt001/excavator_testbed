# Planner 到 ACT 的概念控制契约

本文不按当前仓库的代码模块分层，而按控制系统里的概念职责说明：
上层 planner 如何把任务目标逐层变成低层 ACT 可以执行的条件输入，以及每层需要什么
输入、输出什么信息。

核心原则：

- Planner 负责提出任务级意图、维护地形和进度 belief、选择下一段 primitive、判断交接是否成立。
- ACT 负责连续动作执行，输出真实 4D 控制动作。
- Planner 的输出应是 goal、token、active skill、handoff/replan decision，而不是 joystick
  轨迹或逐步 qpos 轨迹。
- ACT 的输入应是图像、机器人自身状态和紧凑条件 token，而不是完整 privileged `env_state`。

## 总体信息流

```text
任务目标 / 历史结果 / 当前观测
          |
          v
上层任务 planner
  选择下一轮 material objective
  更新 coverage / depth / productivity belief
          |
          v
意图 planner
  选择 dig cell / corridor / entry / exit / target depth / target payload
  选择 return 应回到的 dig-start 分布 envelope
          |
          v
条件 token builder
  把 planner 意图压缩成 ACT 可吃的 low-dim token
          |
          v
skill scheduler + handoff gates
  选择当前 primitive: dig / carry / dump / return
  根据事件和 readiness gate 决定切换、重试或停止
          |
          v
primitive ACT
  image + qpos/qvel + optional token -> 4D action
          |
          v
机器 / 仿真环境
  action -> next observation -> planner 继续闭环
```

换句话说，planner 不直接“开挖机”，它只是不断回答三个问题：

1. 下一铲应该挖哪里、挖多深、期望装多少？
2. 当前应该交给哪个 primitive ACT 执行？
3. 当前 primitive 是否已经完成、失败、需要重规划，或可以交接到下一段？

## 层级职责和 I/O

| 概念层 | 主要问题 | 输入 | 输出 | 不应该做什么 |
| --- | --- | --- | --- | --- |
| 任务 planner | 这个任务下一轮 material cycle 应该推进哪里？ | 任务配置、目标区域、dump 目标、历史 cycle outcome、coverage belief、失败/碰撞记录 | 下一轮目标 cell/corridor、目标深度/载荷、终止或继续信号、更新后的 belief | 不输出 4D action，不手写 qpos 轨迹 |
| 地形/coverage belief | 哪些区域已挖、哪些区域低产或耗尽？ | 6-cell removed-depth grid、目标深度 grid、上轮 payload/deposit、attempts、low-productivity streak | 每个 cell/corridor 的 remaining/depleted/attempt score | 不代替 ACT 做动作修正 |
| dig 意图 planner | 当前 dig ACT 应该朝哪个 cut intent 工作？ | 当前 belief、专家 prior、state exemplars、bucket 相对 dig area 状态、当前/历史失败原因 | entry、exit、direction、length、cut depth、target payload、candidate score、token source | 不手写 entry/exit 对齐轨迹；执行精度由 ACT/token 训练和 rollout report 负责 |
| return 意图 planner | return ACT 应该把空斗带回怎样的 dig-start 分布？ | return-start envelope prior、当前 qpos/qvel、当前 bucket 与 dig area 相对状态；下一轮 dig intent 只给 handoff/debug 使用 | return conditioning token、return->dig readiness 所需 envelope、planner 侧 pending dig token | 不把 return 变成硬编码位置控制器，不把下一铲 depth/payload/cell 直接塞给 return ACT |
| boundary/event detector | 物理事件是否发生？ | 当前和上一帧 env facts、上一帧 action、qpos、质量/沉积/接触/深度/几何指标 | `dig_start`、`dig_complete`、`dump_committed_start`、`release_onset`、`dump_complete`、`next_dig_entry_ready` | 不选择目标，不维护长周期策略 |
| skill scheduler | 现在该调用哪个 ACT？ | active skill、boundary event、handoff gates、timeout、replan/terminal 状态 | active primitive、switch reason、policy reset 信号、debug state | 不生成动作，只选择谁生成动作 |
| primitive ACT | 给定当前 skill 和条件，下一步怎么动？ | camera image、`qpos`、`qvel`、当前 skill 需要的 token | 4D action: `[swing, boom, stick, bucket]`，可选 outcome head | 不维护 coverage belief，不决定下一铲目标 |
| 环境/机器 | 执行动作并产生反馈 | 4D action | next observation、图像、qpos/qvel、env facts、metrics | 不参与策略推理 |

## 向下传递的信息

Planner 向 ACT 传递的信息必须尽量是稳定、低维、语义清楚的条件，而不是把内部状态全部暴露给
ACT。

| 信息 | 典型载体 | 消费方 | 语义 |
| --- | --- | --- | --- |
| 当前 primitive | active skill id/name | scheduler / log | 决定调用 dig、carry、dump 还是 return ACT |
| 当前 dig cut intent | `dig_cut_tokens` | dig ACT | entry/exit/direction/length/depth/payload/valid |
| 扩展 dig depth profile | `dig_depth_profile_tokens_v1` | depth-profile dig ACT | cell、目标深度、payload、reference depth、surface penetration、contact fraction |
| return-start envelope | `return_start_envelope_tokens_v1` | return ACT 和 handoff gate | dig-start 状态分布；若只用 global prior，会把 return 拉向平均 dig-start 姿态 |
| pending 下一轮 dig plan | planner 内部 held `dig_cut_tokens` | scheduler / handoff / 下一轮 dig ACT | 用于 entry-close gate 和下一轮 dig；当前主线不作为 return ACT low-dim 输入 |
| return relocation intent | `return_relocate_tokens_v1` | return-relocate ACT / envelope conditioner | 下一铲 entry/exit/direction/length；不能替代安全 handoff gate |
| 交接/重规划信号 | switch reason、timeout、terminal reason | scheduler / eval log | 解释为什么切 skill、重试、终止 |

token 是 ACT 的条件输入，不是 planner 写出的逐步轨迹。目标状态不是“planner 给一个参考
位置，ACT 在附近自己找地方干活”，而是让 ACT 把 token 当成可执行命令来跟随；差别在于这个
跟随能力必须通过数据、训练和报告度量获得，而不是由 planner 临时插入 joystick/qpos 补丁。
如果 ACT 没学会，planner 可以通过 bad-dig、exit-guard、attempt/depleted belief 重选目标
或 fail fast 暴露问题，但不能补一段手写挖掘轨迹来伪装成功。

## 向上传递的信息

ACT 和环境向 planner 回传的不是“计划”，而是结果事实。

| 信息 | 来源 | Planner 怎么用 |
| --- | --- | --- |
| bucket mass / payload gain | env facts / metrics | 判断 dig 是否有效、是否可进入 carry、是否 bad dig |
| deposited mass / effective deposit | env facts / metrics | 判断 dump 是否完成、更新 productivity belief |
| removed-depth grid | env facts | 更新 coverage、选择未挖或剩余深度大的 cell/corridor |
| bucket 与 dig/dump area 的相对位置 | env facts | 判断 entry readiness、dump committed band、return handoff |
| contact / depth / plane depth / local-surface depth | env facts | 判断 qualified dig start、dig-start envelope 是否满足 |
| collision / spill / unsafe metrics | env facts | 标记 blocked/risk，影响后续 planner score |
| ACT 执行后是否 timeout 或无进展 | scheduler 统计 | 触发 replan、fallback、terminal stop |

## 当前主线的 primitive 闭环

当前四 primitive 闭环可以概括成下面的状态机：

```text
bootstrap(optional)
        |
        v
dig --loaded / dig_complete--> carry --dump committed / target ready--> dump
 ^                                |                                  |
 |                                | release safety                   | dump complete
 |                                v                                  v
 +---------- return <- dump complete / mass low ------------------- return
              |
              | next_dig_entry_ready + envelope gate
              v
             dig
```

### 我们现在是不是状态机

是。当前在线控制可以理解为一个显式有限状态机，但状态机只负责 primitive 调度和
handoff/replan，不负责直接输出连续动作。

更准确地说，系统由两部分叠在一起：

1. 高层 planner 选择目标：下一铲的 corridor/cell、entry/exit、depth、payload、return
   handoff envelope，以及 coverage/depleted/retry belief。
2. 在线 scheduler 是状态机：在 `bootstrap/pre_dig_align/dig/carry/dump/return` 之间切换，
   每个状态把观测和 token 交给对应 ACT，ACT 再输出 4D action。

因此状态机的状态不是“机械臂姿态状态”，而是“当前由哪个 primitive ACT 接管控制”。状态机
不学习动作，也不生成 joystick；它只判断什么时候交接、什么时候拒绝当前目标并重规划。

长期代码结构上，`PrimitivePlannerACTPolicy` 应逐步收敛成 state machine shell：
它保留 active state、transition reason、state lifecycle、policy dispatch 和 service
调用顺序，但不再承载所有几何计算、gate 细节、token conditioning、diagnostic payload
或 schema 组装。和状态机耦合但不是调度核心的能力应迁到 service object 或 capability
模块，例如 coverage、dig-start alignment、return envelope、handoff gate、token builder
和 debug/summary schema。当前已经拆出的 facade/mixin 兼容层只是低风险过渡；长期目标是让
这些 capability 能被显式 FSM 之外的架构复用。后续迁移仍遵循同一原则：只移动职责边界，
不改变 token 语义、gate 阈值、switch reason、debug 字段或 rollout 行为。

| 状态 | 动作来源 | 进入时携带的信息 | 主要退出方向 |
| --- | --- | --- | --- |
| `bootstrap` optional | scripted qpos 或 bootstrap ACT | 第一铲 pending `dig_cut_tokens`，可选目标 qpos | 达到 scripted qpos、timeout close-enough 或首次 qualified dig start 后进入 `dig` 或 `pre_dig_align` |
| `pre_dig_align` optional | 简单 PD/entry handoff 诊断层 | 第一铲 entry intent、qpos clamp、start envelope 诊断 | entry/pose ready、surface guard handoff、timeout close-enough 后进入 `dig`；失败则 reject/replan |
| `dig` | dig ACT | 当前 held `dig_cut_tokens`，可选 `dig_depth_profile_tokens_v1` | 装料成功或 `dig_complete` 后进入 `carry`；低载荷/越界/timeout 则 reject 当前 corridor 并重选 |
| `carry` | carry ACT | 无目标 token，planner 监控质量和 dump-area 几何 | `dump_committed_start` 或 `release_onset` 后进入 `dump`；若已释放完则 safety 进入 `return` |
| `dump` | dump ACT | 无目标 token，planner 监控 release/deposit 完成 | `dump_complete` 后进入 `return` |
| `return` | return ACT | ACT 只读 `qpos`、`qvel`、`return_start_envelope_tokens_v1`；pending 下一轮 dig token 留在 planner 侧 | `next_dig_entry_ready` 已见且 handoff gate 成立后进入下一轮 `dig` 或 `pre_dig_align` |

### 在线状态机的判定条件

当前 V2.4.5 surface-depth/qc6 主线使用 `BoundaryDetector` 的
`v2_4_5_spatial_mass` profile 作为语义事件源。下面的数值是当前配置里的主要阈值；
它们是配置项，不是概念上不可变的常数。

当前 primitive profile/version contract 的代码 source-of-truth 是
`testbed.contracts.primitive_profile`。`boundary_profile` 名称、primitive version、
4P/5P primitive name 列表，以及 `v2_4_5_spatial_mass -> v2_4_5_spatial_mass_4primitives`
映射都应从该模块引用；primitive builder、`BoundaryDetector` 和 V2.4 pipeline CLI
只保留旧常量名作为 facade，不再各自复制 profile/version 字符串。

当前 V2.4.5 spatial-mass primitive slicing 的实现 source-of-truth 是
`testbed.data.primitive_spatial_mass`。该模块负责 material-cycle 窗口拆分、
spatial-mass boundary finder、carry/dump QC、return-start envelope token builder
以及 return overlay 组装；`testbed.data.primitives_v2_2` 继续负责 raw episode discovery、
HDF5 写入和 summary aggregation，并保留旧 helper 名称作为 facade。此次迁移只移动职责边界，
不改变 primitive window、reject reason、metadata key、return envelope token 或输出 layout。

当前在线 dump lifecycle gate 的实现 source-of-truth 是
`testbed.planner.dump_lifecycle.DumpLifecycleGateService`。该 service 负责
4P legacy dump readiness、dump-area relative / near-window geometry gate、
dump mass/deposit completion gate、carry release safety gate，以及 5P
approach-to-dump readiness gate。`PrimitivePlannerACTPolicy` 仍负责 branch order、
hold counter、coverage completion、skill transition、switch reason、policy reset
和 return direct handoff；此次迁移不改变 threshold、boundary event 优先级或 debug
schema。

当前在线 dig lifecycle gate 的实现 source-of-truth 是
`testbed.planner.dig_lifecycle.DigLifecycleGateService`。该 service 负责 dig
progress 状态更新、bad-dig readiness、exit-guard overshoot readiness、
`dig_complete` low-payload guard，以及 legacy / semantic `dig -> carry` readiness
reason。`PrimitivePlannerACTPolicy` 仍负责 dig 分支顺序、coverage reject/complete、
failed-dig stop/retry/pre-dig-align 选择、skill transition、switch reason 拼接、
policy reset 和 debug schema。

| 事件或跳转 | 当前判定逻辑 |
| --- | --- |
| `qualified_dig_start` / `dig_start` | bucket 到 dig area 的最小距离 `<= 0.05m`，并且 bucket 低于 dig-area plane `>= 0.02m`。如果使用 legacy progress 模式，还要求 reward/load progress 或 bucket/excavated mass 增量。 |
| `dig_complete` | 本轮历史 bucket mass 峰值 `>= 15kg`；当前质量相对峰值进入 plateau，epsilon `1kg`、hold `8` step；bucket 稳定离开 dig area，min-distance `>= 0.08m`、hold `3` step。 |
| `dig -> carry` | 优先消费 `dig_complete`。为避免“必须先离开 dig box 才能切 carry，但离开动作又由 carry 负责”的循环等待，semantic profile 下还有 material liveness escape：bucket mass `>= 45kg` 直接切，或 step `>= 160` 且 mass `>= 15kg`、plateau epsilon `1kg`、hold `25` step 后切。当前 `dig_to_carry_min_distance_to_dig_area_m=0.0`。 |
| dig 低产失败 | `dig_bad_replan`：dig 超过 `220` step 但当前 bucket mass `< 15kg`，reject 当前 corridor。`dig_exit_guard`：dig 至少 `80` step，bucket tip 沿 entry->exit 方向越过 planned exit `0.65m`，但 mass `< 20kg`，判为失败。若 `dig_complete` 发生但当前质量低于 carry/dump 最低需求，也按低载荷失败处理。默认兼容旧行为，直接在 dig skill 内换 cut；诊断/eval 应配置 `dig_failed_replan_next_skill=stop`，失败时退出 rollout 并在 planner trace 记录 `failed_dig_stop` 与 `dig_failed_*` terminal reason。 |
| `carry -> dump` | semantic profile 下优先消费 `dump_committed_start` 或 `release_onset`。非 semantic profile 才回退到 planner 内部 `target_ready`/legacy `dump_start`。 |
| `dump_committed_start` | bucket mass `>= 15kg`，dump 几何有效，bucket footprint outside distance 在 `[0, 0.25m]`，relative x 在 `[-0.2, 1.9]`，relative z 在 `[0.45, 2.1]`，height above rim `>= 0.45m`；短窗口稳定性要求 8-step range: outside `<= 0.06m`、relative x `<= 0.16m`、relative z `<= 0.10m`；条件 hold `3` step。 |
| `release_onset` | 已进入 dump ownership 后，bucket 位于 dump area 附近：outside distance `<= 0.45m` 或 over target footprint；同时当前步 bucket mass drop `>= 0.5kg` 或 dump/target deposit gain `>= 0.5kg`。 |
| `dump_complete` / `dump -> return` | `release_onset` 已见后，bucket residual mass 低于 success 配置阈值，当前 qc6 配置为 `15kg`，且 target/dump deposit 进入 plateau。planner 在 `dump_done_use_boundary_event=true` 时优先消费该 boundary event。 |
| `spill_before_target` | 作为质量诊断，只在 bucket mass 明显下降、同帧没有 target/dump deposit progress，并且当前不在有效 dump geometry 时计数。若 `bucket_over_target_footprint_mask=1` 且 `dump_clearance_ok_mask=1`，允许 Unity/AGX 的 bucket mass 与 deposit 传感存在 1 帧左右的更新时序差，不把这种目标内释放误报为漏土。 |
| `return -> dig` | 不是单纯等 `qualified_dig_start`。状态机先 latch `next_dig_entry_ready` 或 qualified dig start，然后要求 `_return_to_dig_handoff_ready` 成立：pending entry error `<= 0.55m`，并通过 `return_start_envelope_tokens_v1` 的 spatial/depth/contact/qpos gate。当前 gate 使用 long/short tolerance `0.10`、qpos tolerance `0.04`；若 prior cell 带 `dig_start_local_depth_m`，local depth 使用该训练分布的 p05-p95 加 `0.005m` tolerance，否则才退回 token depth min/max 加 `0.08m`。`return_to_dig_start_envelope_require_contact=true` 会独立要求 dig contact，不再依赖 token 的 `contact_flag`。`p50_floor` 在有 local-depth prior 且要求 contact 时使用 plane-depth p05-p95 作 terrain-offset 检查，否则继续用 p50 floor 防止零深度 handoff。若显式打开 `return_to_dig_start_envelope_direct_handoff_enabled`，return 在空斗低质量且 entry/envelope 已 ready 时可不等新的接触式 boundary event，直接交给下一轮 dig/pre-dig-align；如果 dump/carry 完成当帧已经满足该 gate，状态机也允许同帧 `dump/carry -> dig`，避免先执行一帧 return ACT 后错过浅接触窗口。 |

这里有两个容易混淆的点：

- `dump_ready_*` 仍存在于配置里，但在 `v2_4_5_spatial_mass` 下主要是 legacy fallback；
  当前主线的 carry->dump 应以 `dump_committed_start/release_onset` 为准。
- `next_dig_entry_ready` 是物理事件或 detector latch，真正切 dig 还要过 pending target 的
  entry-close gate 和 return-start envelope gate。这个设计是为了避免 return 只是“碰到土”
  就把不在 dig 起始分布里的状态交给 dig ACT。

### dig 阶段

输入：

- 图像、`qpos`、`qvel`
- `dig_cut_tokens`
- 可选 `dig_depth_profile_tokens_v1`

planner 决策：

- 选择 cell/corridor。
- 选择 entry/exit、cut depth、target payload。
- 在一个 dig skill 内通常 hold 住 token，避免每步抖动目标。
- coverage planner 的 `recent_row_selection_penalty` 按 3x2 coverage cell 的 row id
  生效；对 cell-weighted prior 不能用浮点 `entry_z` 是否相等来判断同一行，因为相邻 cell
  的统计 entry 可能并不完全共线。
- 如果长时间低载荷、越过 planned exit 仍低载荷、或 `dig_complete` 但当前质量太低，则 reject 当前
  corridor 并 replan。

输出：

- dig ACT 的 4D action。
- 若成功，记录 payload/effective deposit/removed-depth outcome，进入 carry。
- rollout quality report 会记录每铲的 `cycleN_entry_error_m`、`cycleN_exit_error_m`
  和 `cycleN_depth_error_m`，并汇总 `dig_entry_error_*`、`dig_exit_error_*`、
  `dig_exit_signed_error_*`、`dig_depth_*_error_*`。这些字段只观测 ACT 相对
  planner token 的执行精度，不参与在线补救或重新规划。
- surface-depth prior 的 `coverage_cells` 还携带每个 cell 的专家分布：
  entry/exit 的 x/z `p05/p50/p95`、相对 p50 的 radial `p75/p95`，以及
  `cut_depth_peak_m` 的 `p05/p50/p95`。rollout summary 会把每铲的 planner
  原始意图点、实际 bucket-tip 点、专家容忍范围和 hit/rate 一起输出，例如
  `cycleN_entry_planned_x_m`、`cycleN_entry_actual_x_m`、
  `cycleN_entry_expert_radial_p95_m`、`cycleN_entry_expert_radial_p95_hit`、
  `cycleN_exit_expert_*`、`cycleN_depth_expert_p95_m` 和
  `cycleN_depth_expert_p95_overshoot_m`。这些字段用于区分“没有命中 p50 但仍在专家
  支持范围内”和“真的偏离训练分布”，同样不参与在线控制。
- 这些 per-cycle 误差的参考点是 planner 本轮实际发出的 token intent，而不是 expert
  p50。expert p05/p50/p95/radial p95 是旁路 prior，用来解释 intent 是否合理、ACT
  偏差是否超过训练数据支持；它不改变在线动作，也不在失败时触发补救动作。

### carry 阶段

输入：

- 图像、`qpos`、`qvel`
- bucket mass、dump area 相对几何、clearance、沉积变化等事实只给 planner gate 使用

planner 决策：

- carry ACT 负责带料运输和 dump 前预姿态调整。
- planner 只在 dump area committed band、release onset 或 target-ready 条件成立时切到 dump。
- 如果已经发生 release safety 条件，可尽快切 return，避免 carry 继续卡住。

输出：

- carry ACT 的 4D action。
- `carry -> dump` 或 `carry -> return` 的 switch reason。

### dump 阶段

输入：

- 图像、`qpos`、`qvel`
- dump complete 相关事件和质量/沉积 plateau 给 planner gate 使用

planner 决策：

- dump ACT 负责真正 release/deposit。
- planner 等待 `dump_complete` 或 residual mass/deposit plateau，再切 return。
- dump 完成后更新 coverage outcome，包括 effective deposit 和低产 streak。

输出：

- dump ACT 的 4D action。
- `dump -> return` switch reason。

### return 阶段

输入：

- 图像、`qpos`、`qvel`
- `return_start_envelope_tokens_v1`
- planner 侧 pending 下一轮 `dig_cut_tokens`，但它不进入当前 return ACT low-dim

planner 决策：

- 在 return 开始或 return 过程中先选好下一轮 dig intent，并把它作为 pending plan；这个
  plan 用于下一轮 dig 和 handoff entry-close，不直接喂给 return ACT。
- 当前 surface-depth 主线把 return 当成“回到可接管分布”的 skill，不是“按下一铲 cell
  精确导航”的 skill。
- planner latch `next_dig_entry_ready`，但不会只凭一个事件切 dig；还要检查 entry error、
  spatial/depth/contact/qpos envelope。surface-depth prior 的
  `return_start_envelope_cells` 应携带从 gold dig primitive start 统计出的
  `dig_start_plane_depth_m` 和 `dig_start_local_depth_m`；handoff gate 优先用
  local-depth prior 与 contact 判断是否进入 surface-relative dig-start 分布，再用
  plane-depth prior 检查当前 terrain offset，避免 return 在 bucket 仍未接触有效
  dig-start surface 时过早交给 dig。

输出：

- return ACT 的 4D action。
- 通过 gate 后进入下一轮 dig，并复用 pending dig plan。

## 离线数据切分逻辑

离线 primitive 数据切分不是简单复用旧 `/v2/cycle`，也不是按在线状态机逐步 replay 一遍。
当前 V2.4.5 的 source of truth 是 material cycle：用 `env_state` 里的空间、质量、沉积、
removed-depth 事件验证一轮真实 material movement，再把它切成四个 ACT 训练窗口。

核心原则：

- 仍然只产出四个 primitive：`dig -> carry -> dump -> return`。
- 旧 `/v2/cycle` 只作为搜索窗口和诊断参考；最终边界由 material pulse、dig/dump 几何、
  bucket mass、deposit 和 removed-depth 决定。
- 离线 builder 可以用局部未来窗口确认 plateau、未来无新增装料、release 后稳定等事实；
  这些 oracle 只用于切数据和 QC，不能作为在线 ACT 输入。
- window 采用半开区间语义理解：某个 realign 或 material event 属于哪个窗口，要按
  `[start, end)` 归属，避免前一轮吞掉下一轮起点。

| Primitive | 起点 | 终点 | 接受/拒绝重点 |
| --- | --- | --- | --- |
| `dig` | material cycle 内 first stable dig-box contact/depth；若可靠则使用 `qualified_dig_start` | payload/removed-depth 已出现、bucket mass 峰值已出现、未来短窗口无显著新增 mass，且 bucket contact/depth 低、稳定离开 dig box | gold dig 必须有可靠 surface-relative depth / removed-depth outcome；dig 内不能出现 dump/target deposit 增加 |
| `carry` | `dig_end` | `dump_start` | 包含带料运输和 dump 前预姿态调整；只要还在接近/对准 dump area，movement 仍归 carry。若 dump 前已有明显 deposit contamination，当前红线为 `deposit_delta > 5kg AND deposit_delta / payload_loss > 10%`，reject |
| `dump` | 从 `release_onset` 向前找有限 committed aiming window；上限为 `release_onset - 120`，并要求进入 stable aiming band | release 后 bucket residual mass 低位稳定，deposit plateau | `dump_start` 不能因为未来会倒土就提前吞掉长距离 transport；当前 surface-depth band 使用 stable outside `<= 0.25m`、fallback outside `<= 0.30m`、relative x/z corridor 和 8-step 稳定阈值 |
| `return` | `dump_end` | 下一轮 first next-dig-start envelope ready / `first_next_dig_entry_ready` | return 只在存在下一轮 material dig-start 时生成；terminal cycle 不产 return，只写 reject/summary |

material cycle 的基本证据链是：

1. bucket 在 dig virtual box 内开始接触/入土。
2. removed-depth grid 或 bucket mass 出现有效增加；gold 样本要求可靠 removed-depth delta。
3. 带料离开 dig box 并接近 dump area。
4. 在 dump area 内发生 bucket mass drop，并伴随 dump/target deposit increase。
5. bucket residual mass 回到低位并稳定，然后进入 return。

多 pulse 和 realign 的处理规则：

- 如果旧 `/v2/cycle` 内出现多个 `load -> release` material pulse，优先拆成多个 material
  sub-cycle；空间/质量证据对不上时才 reject。
- material cycle 内有 `replay_pose_realign_steps`，则该子轮的 `dig/carry/dump` reject。
- realign 落在 return window 内，只 reject 对应 return。
- realign 正好落在下一轮 start/qds 帧时，只归属下一轮，不应把前一轮 clean return 丢掉。

当前实现入口是 `tb-build-primitives-v2_2 --boundary-profile v2_4_5_spatial_mass`，
上层流水线是 `tb-build-v2_4-hindsight-pipeline`。builder 输出接受的 primitive windows、
token、outcome/QC 指标和 reject reason；训练 loader 只读取已经通过这些边界和 QC 的
窗口。

## token 契约

### 当前 surface-depth 训练配置

基础 surface-depth/qc6labels scale080 训练里，return 的 low-dim 契约曾收窄为：

```yaml
low_dim_keys:
  - qpos
  - qvel
  - return_start_envelope_tokens_v1
supervision_keys:
  - return_outcome_targets
```

对应配置是
`runs/jobs/yulong_v2_4_5_surface_depth_replay_train_eval_20260523/train_configs/act_return_surface_depth_qvel.yaml`。
eval 侧的 `return_low_dim_keys` 也是同一组 key。
如果 eval 打开 `return_to_dig_start_envelope_gate_enabled` 或
`return_to_dig_start_envelope_direct_handoff_enabled`，`return_low_dim_keys` 必须包含
`return_start_envelope_tokens_v1`；否则启动时应直接失败，避免 handoff gate 使用了
start-envelope 语义而 return ACT checkpoint 实际没有读入该 token。

ACT checkpoint 加载也必须保持同一份 low-dim 契约：`policy_config.state_dim`、
`dataset_stats.pkl` 里的 `proprio_dim` / `proprio_keys` / `proprio_mean` /
`proprio_std` 必须和当前 `low_dim_keys` 推导出的维度一致。只有 legacy
`low_dim_keys=["qpos"]` 可以显式使用旧的 `qpos_mean` / `qpos_std` stats；其它组合
缺少 `proprio_mean` / `proprio_std` 时不得静默加载。

当前 low-dim observation contract 的代码 source-of-truth 是
`testbed.contracts.low_dim`。`LOW_DIM_CONTRACT_VERSION`、supported key 列表、
每个 key 的 dim、token slice、observation assembly，以及 stats/checkpoint
兼容性校验都应从该模块引用；`dataset`、`runtime/_train.py`、`runtime/_eval.py`
和 `ACTAdapter` 只保留旧入口作为 facade，不再各自复制一份 low-dim 语义。

当前 primitive token contract 的代码 source-of-truth 是
`testbed.contracts.primitive_tokens`。`dig_cut_tokens`、
`dig_depth_profile_tokens_v1`、`return_target_tokens`、
`return_relocate_tokens_v1`、`return_start_envelope_tokens_v1` 和
`return_start_envelope_valid_mask` 的 dim、field order、HDF5 dataset path、
metadata dim attr aliases、index/slice 和 relocation 派生规则都应从该模块引用；
data builder、dataset loader、runtime/eval、ACT adapter 和 planner 只保留旧常量或
helper 作为 facade，不再复制 token 下标或 path。

当前 return start-envelope / handoff gate 的实现 source-of-truth 是
`testbed.planner.return_start_envelope`。该模块负责 live fallback token 构造、
relocate-conditioned qpos/spatial conditioning、cell/global prior fallback、prior
bounds 读取，以及 return->dig spatial/depth/contact/qpos gate 检查；
`PrimitivePlannerACTPolicy` 中的旧方法名只作为 facade 转调。此次迁移只移动职责边界，
不改变 token dim/order、prior fallback、gate 判定、debug_state 字段或 rollout 行为。

当前 dig coverage / corridor planning 的实现 source-of-truth 是
`testbed.planner.dig_coverage.CoverageService`。该 service object 负责 coverage
corridor candidate 构造、cell-weighted prior 和 percentile-grid fallback、corridor
scoring、first-dig gate、state exemplar conditioning、coverage raw fields、
belief/depletion 更新，以及 coverage decision trace payload；`DigCoverageMixin`
和 `PrimitivePlannerACTPolicy` 继续保留旧 `_coverage_*` /
`_ensure_coverage_corridors()` / `_select_coverage_corridor()` 等 private 入口作为
facade 兼容层。此次迁移只移动职责边界，不改变 coverage scoring、candidate layout、
state exemplar 语义、reject/deplete/terminal 行为或 planner trace/debug 字段。

当前 primitive planner debug/summary schema 的实现 source-of-truth 是
`testbed.planner.primitive_debug`。该模块负责 `PrimitivePlannerACTPolicy.debug_state()`
和 `rollout_summary()` 的字段组装；planner 类中的同名方法只保留为 facade。此次迁移
只移动职责边界，不改变字段名、字段顺序、默认值、字段类型、rollout JSONL 消费语义或
planner 状态机行为。

当前 rollout step/debug schema 的实现 source-of-truth 是
`testbed.eval.rollout_step_records`。该模块负责 eval policy input 组装、
逐 timestep JSONL record 字段和发送给 AGX/Unity 的 planner debug payload；
`EvalSuite._planner_debug_json` 只保留为 facade。每条 rollout 的 JSONL、summary
和 planner trace 写出编排由 `testbed.eval.rollout_artifacts` 承担，并继续复用
现有 `rollout_logs` schema helper。此次迁移只移动 EvalSuite 内部职责边界，
不改变 rollout loop、HDF5 layout、JSONL 字段、summary/manifest 字段或 planner
debug JSON 语义。

这意味着：

- return ACT 不读取 `dig_cut_tokens`。
- return ACT 不读取 `return_target_tokens`。
- return ACT 不读取 `return_relocate_tokens_v1`。
- return ACT 不直接拿下一铲的 cell、cut depth、target payload 或 removed-depth goal。
- `dig_cut_planner.return_start_envelope.use_cell_prior=false` 时，live return envelope 使用
  qc6 gold return 的 global envelope prior；cell/corridor 只影响下一轮 dig token 和
  entry-close gate，不再默认影响 return-start envelope token。
- 生成 cell-conditioned `return_start_envelope_cells` 时，cell 归属必须来自下一铲
  `next_operator_entry_x/z` 到 `coverage_cells.entry` 的最近匹配，而不是
  `return_start_envelope_tokens_v1` 自己的 long/short 值。后者只是 return 抵达的
  start-state 描述，直接用它分桶会把左侧 cell0 的 return 姿态错分到其它 bucket，
  造成 live planner 看起来回到平均位置。`tb-build-surface-depth-planner-prior`
  固化了这个规则。

所以当前主线里，return 的任务是回到“dig ACT 可以接管的状态分布”，而不是执行下一铲
dig plan 的前半段。下一铲 plan 仍然存在，但它停留在 planner/scheduler 侧，等真正切回
`dig` 后才作为 `dig_cut_tokens` 给 dig ACT。

同理，已经进入 dig skill 后再因为低载荷/exit guard 失败而换 cut，不能默认假设当前状态仍然
落在新 cut 的 dig-start 分布里。诊断/eval 主线用 `dig_failed_replan_next_skill=stop`
把这种情况当作真实失败暴露出来，而不是让后续 replan/return 掩盖根因。

2026-05-26 的 return-relocate 诊断表明：如果 live return 继续只注入
`qc6_return_start_envelope_global`，token 内 qpos center 会固定在全局 median
dig-start 姿态附近，rollout 视觉上就会像“回到平均点再挖”。新的
`dig_cut_planner.return_start_envelope.{spatial,qpos}_from_relocate` 选项不会脚本化
对齐动作，只是用下一铲 `return_relocate_tokens_v1` 派生 target-specific spatial
long/short 和 qpos center 覆盖 envelope token 对应字段，让 return ACT 自己执行
“回到下一铲附近”。开启这些选项时，handoff gate 对应字段默认围绕派生 token，而不是
继续使用 global prior bounds。

### `dig_cut_tokens` / `return_target_tokens`

10D，归一化后传给 ACT：

| index | 字段 | 语义 |
| --- | --- | --- |
| 0 | entry_x | 入铲点 x |
| 1 | entry_z | 入铲点 z |
| 2 | exit_x | 出铲点 x |
| 3 | exit_z | 出铲点 z |
| 4 | dir_x | cut direction x |
| 5 | dir_z | cut direction z |
| 6 | length | 计划切削长度 |
| 7 | cut_depth_semantic | 当前主线为 surface-relative depth intent |
| 8 | payload | 目标载荷或专家 payload 先验 |
| 9 | valid | token 是否有效 |

当前 V2.4.5 surface-depth 主线保持 10D 形状不变，但 depth slot 的语义是
`cut_depth_semantic_m`，优先来自 `bucket_depth_below_local_surface_m` peak。

### `dig_depth_profile_tokens_v1`

12D，用于 depth-profile dig ACT 或 ablation：

| index | 字段 |
| --- | --- |
| 0 | dominant_cell_id_norm |
| 1 | removed_depth_target_norm |
| 2 | payload_target_norm |
| 3 | effective_deposit_target_norm |
| 4 | cut_length_norm |
| 5 | entry_reference_depth_norm |
| 6 | exit_reference_depth_norm |
| 7 | peak_reference_depth_norm |
| 8 | peak_surface_penetration_est_norm |
| 9 | plane_minus_surface_penetration_offset_norm |
| 10 | contact_fraction |
| 11 | valid |

它比 10D token 显式得多，但也更依赖 prior 和训练分布。strict eval 中如果 prior cell
缺失，应 fail fast，而不是静默回退。

### `return_start_envelope_tokens_v1`

18D，用于描述“return 应把机器带回什么样的下一轮 dig-start 分布”：

| 范围 | 字段 | 语义 |
| --- | --- | --- |
| 0-1 | long_norm, short_norm | dig grid 内的位置 envelope center |
| 2 | depth_center | 目标 dig-start depth center |
| 3 | tip_radius | bucket tip 允许半径 |
| 4-5 | depth_min, depth_max | local depth gate |
| 6 | contact_flag | 当前 token 要求/记录 dig contact |
| 7-10 | qpos_center[4] | dig-start 姿态中心 |
| 11-14 | qpos_half_width[4] | 姿态 envelope 半宽 |
| 15 | qvel_abs_max | 交接时速度上限 |
| 16 | qpos_valid | qpos/qvel envelope 是否有效 |
| 17 | spatial_depth_valid | spatial/depth envelope 是否有效 |

return->dig 交接不能只看 2D entry error；它还要看 envelope gate 是否成立，尤其是
depth/contact/qpos 是否进入下一轮 dig ACT 的训练分布。

### `return_relocate_tokens_v1`

10D，和 `return_target_tokens` 同维度，但屏蔽 depth/payload，只保留 relocation 相关的
entry/exit/direction/length/valid。它适合做 return relocation ablation，让 return 学会
“回到下一铲附近”，而不是让 return 承担挖深或装料目标。

注意：它仍然不是手写对齐轨迹。return-relocate 重训可以把
`return_relocate_tokens_v1` 放回 return low-dim；live 侧也可以只把它用于
`qpos_from_relocate` envelope conditioning。两种做法都必须在实验记录里明确区分。
当 return low-dim 同时包含 `return_start_envelope_tokens_v1` 和
`return_relocate_tokens_v1` 时，ACT 的 `token_swap_outcome_loss` 必须把这两个
conditioning token slice 一起交换；只交换第一个 token 会让模型继续偏向全局
envelope，削弱 relocation 对动作的约束。
return-relocate 训练的 outcome supervision 应使用
`return_relocate_outcome_targets_v1` 这类 relocation-only 目标：只监督
entry/exit/direction/length/valid，不监督 depth/payload。return 可以用 shallow
depth/contact 字段判断是否仍在安全 handoff envelope 内，但不应该把下一铲的挖深或
装料目标当成自己要执行的动作目标。

## 信息边界

应该进入 planner 的信息：

- privileged env facts，例如 removed-depth grid、bucket mass、deposit、relative geometry。
- boundary event、failure reason、coverage outcome。
- prior 和 state exemplars。

应该进入 ACT 的信息：

- image。
- `qpos`、`qvel`。
- 当前 skill 需要的紧凑 token。

不应该进入 ACT 的信息：

- 完整 planner debug。
- 完整 privileged `env_state`。
- 未来 outcome 或离线 oracle 标签。

不应该由 planner 输出的信息：

- 每步 joystick command。
- 每步 qpos setpoint 轨迹。
- 为了补偿 ACT 失败而写死的 bucket/boom/stick 运动脚本。

## 当前设计状态

截至 2026-05-26/27，当前实现可以分成三条已收敛的主线：

1. 10-cycle smooth milestone 已经通过
   `runs/jobs/yulong_v2_4_5_return_relocate_train_eval_20260525/eval/10cycle_return_relocate`
   跑通：10 次 dump 后由 `target_cycle_gate_terminal_hold_reached` 停止，且没有 spill 或
   hard target collision。这个结果证明四 primitive 闭环和 return-relocate 路径能连续运转，
   但它不是严格“指哪挖哪”的最终验收，因为当时还没有新加的 per-cycle
   intent/execution/prior 精度表，且 gate tail 只有 1 step。
2. 最新报告契约已经能输出每铲 intent vs execution vs expert prior：planner planned
   entry/exit/depth、实际 bucket-tip/peak depth、expert box/radial p95 hit、depth range
   hit 和 overshoot。它的用途是定位问题属于 planner 点位不合理、token 没接上、handoff
   初始状态不对、ACT 不按 token，还是 boundary 让 dig 挖太久。
3. coverage/depletion 已改成 pass-local 语义：`depleted` 只是当前 pass 的尝试状态。
   当 env removed-depth grid 仍显示 remaining depth 时，planner 可以记录
   `reopen_coverage_pass` 并重开 cell；只有没有 remaining-depth 证据或 multi-pass 用尽时，
   `dig_area_depleted` 才是终止理由。

当前未完成的目标也很明确：planner 已经能规划覆盖和输出精度诊断，但 ACT 对 entry/exit/depth
token 的跟随还不是严格的命令式控制。后续要提升的是 ACT 条件化和 handoff 起点一致性，而不是
在 planner 里加入新的手写补救动作。

## 典型失败与职责归因

| 现象 | 优先怀疑层 | 排查信号 |
| --- | --- | --- |
| planner 反复选空区 | coverage belief / prior | `coverage_candidate_scores`、removed-depth grid、attempt/depleted |
| dig token 很深但 ACT 仍浅挖 | dig ACT / 训练分布 / live observation | offline ACT audit、first action、chunk alignment、camera/action scaling |
| dig 很久低载荷 | ACT 或 entry 状态，也可能是 planner 选点 | `dig_bad_replan_count`、exit overshoot、payload trace、entry error |
| return 到点附近但不切 dig | handoff gate | entry error、envelope checks、plane depth、qpos envelope |
| return 太早切 dig 导致第二铲浅挖 | handoff gate 过宽 | `return_to_dig_start_envelope_checks`、`next_dig_entry_ready` latch 状态 |
| planner 报 `dig_area_depleted` 但 depth grid 仍有余量 | coverage pass 语义 | `coverage_pass_index`、`reopen_coverage_pass` trace、remaining depth grid |
| 稀有 cell 成功一铲后过早 depleted | attempt limit 与实时 depth 冲突 | `last_reason=attempt_limit_reached`、`last_remaining_depth_m`、`rare_cell_max_attempts` |
| carry 提前切 dump | boundary/profile gate | dump committed band、outside distance、relative x/z stability |
| ACT 动作突然错向 | ACT/action scaling 或 checkpoint | low_dim stats、action order、temporal aggregation、ckpt config |

## 当前实现里的对应关系

本文是概念文档，但当前实现大致对应：

| 概念 | 当前命名 |
| --- | --- |
| primitive skill scheduler | `primitive_planner_act` |
| 4 primitive ACT | `dig_policy`、`carry_policy`、`dump_policy`、`return_policy` |
| cut intent token | `dig_cut_tokens` |
| depth/profile token | `dig_depth_profile_tokens_v1` |
| return envelope token | `return_start_envelope_tokens_v1` |
| return relocation token | `return_relocate_tokens_v1` |
| boundary/event detector | `BoundaryDetector` |
| online state machine | `PrimitivePlannerACTPolicy._maybe_switch_skill` |
| offline primitive slicer | `tb-build-primitives-v2_2 --boundary-profile v2_4_5_spatial_mass` |
| coverage belief | `coverage_corridors`、attempts、low-productivity streak、depleted |
| coverage decision trace | `coverage_decision_trace`，记录 `select_corridor` / `complete_dump` / `reject_corridor` / `terminal_stop` 的候选分数、remaining depth、payload/deposit 与 depleted reason |
| old coarse planner | `RuleTaskPlanner`，用于 Stage-4 sector/depth rule planner |
