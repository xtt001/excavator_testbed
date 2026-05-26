# Next Full Excavation Framework Plan

Date: 2026-05-12

本文不是 V2.2 当前实现说明，而是下一阶段完整挖掘框架的设计文档。

我们从 V2.2 重新出发，是因为 V2.2 的四 primitive ownership 证明过比 V2.3 更稳；
但 V2.2 本身不能满足新任务需求。下一阶段的目标不是恢复 V2.2，而是在保留其有效经验
的基础上，建立能完成完整作业区挖掘的新框架。

## 核心判断

V2.2 是起点，不是终点。

保留：

- `dig -> carry -> dump -> return` 四 primitive ownership；
- `dump` 作为一个混合 primitive，包含 approach、alignment、release、post-dump hold；
- 不恢复默认 5P split；
- 固定 dump area 阶段不加 dump-area-token；
- selected target 和 actual outcome 必须分开记录；
- 错误 cell 的实际执行不能 rebind 成成功。

降级为 legacy note：

- 当前 V2.2 `BoundaryDetector` 的具体阈值实现；
- V2.1/V2.2 sector-level `left/mid/right` planner；
- `target_cycle_gate`、bootstrap、旧 smoke 配置等工程细节；
- 旧 10D sector `goal_tokens` 语义。

这些东西可以短期复用来跑 smoke 或做对照，但不应该成为新框架的核心定义。

## 新任务目标

下一阶段目标是让系统完成一个自然完整的作业循环：

```text
给定作业区和目标深度
  -> 选择下一铲区域
  -> 选择 bite / entry / depth
  -> 自然挖掘并装斗
  -> 运输到 dump area
  -> 倾倒
  -> 返回下一次 entry
  -> 重复直到作业区达到目标
```

因此，新框架必须回答：

- 当前作业区哪里还需要挖？
- 下一铲应该挖哪个 cell？
- 在该 cell 内应该从哪里入土、挖多深？
- return 应该把空斗带到哪个 next entry？
- ACT 实际是否到达了这个 entry？
- soil 实际从哪里被移除？
- soil 实际倒到了哪里？
- 如果失败，是 planner 选错、return 没到、dig 没按条件执行，还是 dump 失败？

## 新场景引入原则

整个仿真场景已经变化，因此下一步不能直接进入专业师傅大规模采集。新场景本身会带来
协议、量测、动力学、土体、dump area、任务终止条件等风险。

推荐三段式推进：

1. **new-env pilot**：我们先在新场景录少量内部数据，验证记录、量测、视频、relabel、
   primitive split、smoke eval 链路都正常；
2. **pro data collection**：pilot 通过后，再邀请专业师傅大规模录自然 full-cycle 数据；
3. **new model training**：基于新任务、新场景、新数据训练新模型，按 conditioned ACT
   路线逐步实现完整作业目标。

pilot 数据的目标不是追求性能，而是验证系统能否正确“看见”和“记录”新任务。没有通过
pilot gate 前，不应消耗专业师傅录制成本。

## 最终分层框架

目标框架如下：

```text
Task Objective
  -> World State / Surface Estimator
  -> Mission Planner
  -> Area / Cell Planner
  -> Bite / Entry Planner
  -> Planner Decision Auditor / Unity Target Overlay
  -> Primitive Scheduler
  -> Conditioned Primitive ACT
  -> Outcome Evaluator / Data Builder
```

### Task Objective

定义任务要完成什么，而不是怎么操作手柄。

例子：

```text
把指定作业区挖到目标深度，并把土倒到指定 dump area。
```

它负责：

- 作业区范围；
- 目标深度或目标 surface；
- dump area；
- episode 成功条件；
- 是否继续下一铲。

### World State / Surface Estimator

这一层给 planner 提供事实，不直接做动作决策。

需要逐步具备：

- 作业区局部坐标系；
- surface / depth grid；
- bucket tip 或 bucket proxy 在作业区局部坐标中的位置；
- bucket payload mass；
- 每个 cell 的 remaining depth / removed depth；
- dump area 局部几何；
- deposited mass / off-target deposit；
- hard collision / contact 信息。

如果 Unity 可以直接给这些量，就直接记录。否则离线 estimator 可以从已有 env state、
bucket pose、soil metrics 中重建。

### Mission Planner

Mission Planner 判断整个任务层面的事情：

- 是否继续挖下一铲；
- 当前作业区是否完成；
- 是否切换作业区域；
- 是否进入收尾或失败处理。

它不选择 joystick action，也不决定单铲具体 path。

### Area / Cell Planner

Cell Planner 负责回答：

```text
下一铲挖哪个 cell？
```

输入：

- surface / depth grid；
- 每个 cell 的 remaining depth；
- 每个 cell 的 visit count；
- 最近几铲的 actual removal；
- blocked / collision / low-productivity 标记。

输出：

- target cell；
- target depth 或 desired removal；
- 可选优先级和失败原因。

它不能因为模型实际挖到了别处，就把目标静默改成别处成功。

### Bite / Entry Planner

Bite / Entry Planner 负责回答：

```text
在这个 cell 里，从哪里入土，挖多深，下一次 entry 应该在哪里？
```

输出应包含：

- target cell；
- bite point 或 bucket tip local x/z；
- target depth；
- planned entry target，例如 bucket tip local x/z/y 和预期 bucket 姿态范围；
- planned entry envelope，例如位置 / 深度 / bucket pitch 的容差范围；
- local surface context；
- entry intent，例如切入方向、预期 bucket 姿态范围；
- next entry target，供 return 使用。

这层是 V2.3 `paramdig` 需要重做的地方。V2.3 的问题不是“参数化 dig 方向错”，而是
target 语义太粗，同时 return、planner、dump 数据边界一起变化，导致归因失控。

### Planner Decision Auditor

规则 planner 阶段必须先保证 planner 输出可解释、可审计，再把目标交给 ACT。每次
planner 输出后，应立即生成一条 decision audit，而不是只写一个 target token。

audit 至少检查：

- selected cell 是否 valid；
- remaining depth 是否足够；
- target depth 是否超出可挖范围；
- bite point 是否在 cell 内；
- entry envelope 是否与当前 bucket pose 大致可达；
- 当前 bucket pose 相对 planned entry 的 `entry_delta` 是否仍在可修正范围内；
- 是否离边界、硬碰撞区域或 dump area 太近；
- 是否重复选择刚刚低产、blocked 或失败的 cell；
- 该 cell / depth / local surface 是否在训练数据覆盖范围内。

audit 结果应包含 `planner_ok`、risk flags 和 reason codes。失败不能只记录为 rollout
失败，而要能区分：

```text
planner_invalid
planner_high_risk
planner_out_of_distribution
```

### Unity Target Overlay

规则 planner 阶段建议在 Unity 中实时显示 planner intent 和 actual outcome。这个 overlay
不是为了好看，而是为了让人眼能快速判断 planner 给的目标是否合理。

至少显示：

- selected cell 高亮；
- bite point；
- target depth 平面或深度标尺；
- planned entry envelope / corridor；
- next entry target；
- bucket tip actual trajectory；
- actual accepted start；
- actual bite；
- actual removal cell；
- invalid / blocked cell。

建议固定颜色语义：

```text
blue   = planner selected target
green  = actual accepted start
yellow = actual bite
red    = target miss / off-target removal
gray   = invalid / blocked cell
```

如果 Unity overlay 暂时做不了，离线视频 overlay 也可以作为第一版 pilot gate。

## Primitive Ownership

下一阶段仍使用四 primitive：

```text
dig -> carry -> dump -> return
```

### dig

职责：

- 从计划 entry 开始入土；
- 按 target cell / bite / depth 执行挖掘；
- 装斗；
- 出土到可交给 carry 的姿态。

下一阶段第一个要 conditioned 的 ACT 是 `dig`。

建议输入：

- `qpos`
- `qvel`
- target cell；
- bite point local x/z；
- target depth；
- local surface context；
- entry intent；
- planned entry target；
- current bucket local pose；
- `entry_delta = current bucket pose - planned entry target`；
- `inside_entry_envelope_mask`；
- `distance_to_entry_envelope`。

不输入：

- dump target；
- dump-area-token；
- return 目标；
- `cycle_index`，第一阶段只记录，不作为 dig ACT 的核心控制条件。

`entry_delta` 的作用是让 `dig` 适应 reset / return 带来的小起点误差，不是让 `dig`
修复错误 planner 目标或大范围 return miss。大偏差应该由 gate 拦住，进入 replan、
approach correction 或 recover。

### carry

职责：

- loaded transport；
- 从 dig 出土姿态接到 dump handoff corridor；
- 不 release；
- 不打开 bucket。

下一阶段默认不 conditioned。只有未来 dump area 大范围变化，并且 A/B 证明 carry 需要
目标语义时，才考虑增加 dump-area target。

### dump

职责：

- approach dump area；
- alignment；
- bucket release；
- post-dump hold；
- 确保不要被 return 过早接管。

固定 dump area 下，`dump` 默认不 conditioned。

只有当 dump area 变成变量时，才给 `dump` 加 dump-area target。即使未来加，也只应该
加 dump 相关目标，不把 dig cell / bite token 喂给 dump。

### return

职责：

- 从 post-dump hold 后的空斗状态返回下一次 dig entry 附近；
- 不负责选择 cell；
- 不负责偷偷修正 planner 目标；
- 不混入 dump release 尾部。

`return` 是第二个候选 conditioned ACT。只有当 `dig` 已经能按 target 工作，但旧
`return(qpos+qvel)` 无法稳定到达下一次 entry 时，才启用：

```text
return(qpos + qvel + next_entry_target)
```

return 的目标必须是：

```text
next dig entry / next accepted dig-start target
```

不是：

```text
next actual bite point after dig already starts
```

这是 V2.3.5 的关键教训。

2026-05-19 YuLong operator-first 诊断后的补充：`next_entry_target` 不应只是粗粒度
`left/middle/right` 区域，也不应是一个必须精确追到的单点。更稳的 contract 是
**next cut intent + dig-start envelope**：

- `return_target_tokens` 表达下一铲的 entry envelope / start pose prior / planned
  cut corridor 摘要；
- return 负责把空斗带到 planner 指定 cut intent 对应的可接管 start region；
- dig ACT 继续读取 `dig_cut_tokens`，根据当前作业区状态执行 entry->exit swept cut；
- target 在一个 return window 内 latch，不逐步漂移；
- planner 可以按当前 `removed_depth/target_depth/valid_mask` 选择 left/middle/right
  区域或更细 corridor，但喂给 return 的不是离散区域 id，而是该区域对应的
  next-entry envelope。

2026-05-19 YuLong 2.4 执行更新：当前 Unity `removed_depth` 在这批数据中不可作为
真实覆盖信号，因此 sweep planner 的第一版默认使用 reconstructed belief，而不是
直接使用 soil-depth grid。belief 由每轮 planned/actual cut corridor、payload gain、
effective deposit 与 low-productivity streak 更新；`return_target_tokens` 和
`dig_cut_tokens` 共用 10D cut-intent contract，但分别在 return/dig 阶段注入。
本轮重建数据使用 materialized copy root 训练，不把 VDS primitive episode 作为热训练
入口。没有下一铲目标的 terminal return window 只作为审计/reject 记录，不进入
conditioned return 训练集。live sweep 评测中，低产 dig 不能无限停留在 dig：
如果已经有 `15kg` 以上 partial payload 且长时间 plateau，则允许进入 carry；
如果长时间低于 `15kg`，则把当前 corridor 标为 low-productivity reject 并重新选择
下一条 cut intent。

2026-05-20 诊断补充：在进一步扩大 planner 覆盖范围前，必须先验证 dig ACT 是否
真正响应 `dig_cut_tokens`。当前流程先用固定观测替换多组 token 做 sensitivity
诊断，再用 materialized copy `dig` primitive 重训
`qpos + qvel + dig_cut_tokens`，最后用同一诊断比较新旧 checkpoint。只有当新 dig
在训练分布内对 token 有稳定响应时，才继续做更激进的 sweep / shape-conditioned
planner。

这样既避免 V2.3.5 的动态目标抖动，也允许挖掘动作根据当前未挖区域调整
swept cut corridor。

2026-05-20 指哪挖哪诊断结论：到这里为止，原计划的阶段性工程链路已经基本走通，
但它没有交付我们真正想要的能力。

已经完成的部分：

- 64D `env_state`、operator-first relabel、effective deposit、operator cut corridor、
  `dig_cut_tokens`、`return_target_tokens` 都已能从当前自然 pro raw 数据离线推导；
- raw -> enriched -> 4 primitive 的 VDS / materialized copy 数据链路已经可用；
- 四 primitive ACT、conditioned dig、conditioned return 都训练并接入过 live rollout；
- Unity planner debug / HUD / DigArea 入铲点显示已经用于区分 planner intent 与实际执行；
- `pre_dig_align` 已作为诊断验证过，并明确不进入长期主线；
- 5/10/15cycle milestone 证明旧安全 planner + 旧 primitive 组合可以形成可用作业循环；
- 新 copy-root conditioned dig 做过 token sensitivity 诊断，新旧 checkpoint 对
  `dig_cut_tokens` 都有反应，但反应幅度接近，不能证明已经学会稳定 command following。

未达到的目标：

- 系统还不能可靠做到“planner 指哪，ACT 就挖哪”；
- coverage / sweep planner 一旦选择训练分布外或少见 corridor，return / dig / carry
  很容易出现状态分布偏移；
- 新 dig checkpoint 在 5cycle live test 中没有立刻解决覆盖问题，反而导致后续
  `carry -> dump` handoff 漏切：土已经在 carry 阶段有效入箱，但 dump-ready gate 没接住，
  carry 继续执行并撞墙；
- 当前 `removed_depth` / actual removal 仍不足以作为真实作业区覆盖事实，planner 只能用
  payload/deposit 历史 belief，无法真正知道哪里还剩可挖土。

2026-05-20 depth bug 修复优先级：先把 Unity DigArea 3x2 surface/depth telemetry
修成可靠事实源，再继续扩大 planner 自由度。旧实现主要读取 Unity `TerrainData`
高度图；YuLong 场景的真实挖掘形变由 AGX `DeformableTerrainBase` native terrain
驱动，静态/未同步 heightmap 会导致 `removed_depth` 长期接近 0。修正后的 contract 是：

- Unity `DigAreaMeasurement` 使用与 `bucket_depth_below_dig_area_plane_m`
  相同的 DigArea Box 平面定义：terrain 上表面采样点先转到 DigArea local frame，
  再用 `max(0, -local_y)` 表示低于该平面的深度；
- 每个 3x2 cell 采多个 cell 内部点并取平均 surface depth；
- surface source 优先用从 DigArea 平面上方向下 raycast 到 `DigTerrain`
  collider 的几何命中点；live AGX deformable terrain native height 和旧 Unity
  `TerrainData` 只作为兼容 fallback；
- reset 后首次有效采样写入 baseline；
- `removed_depth = max(0, current_surface_depth - baseline_surface_depth)`，单位 m，
  正值表示 DigArea 平面下方被挖深；
- 质量归因 removal fallback 只允许作为显式 opt-in 诊断代理，默认关闭，不能当作
  几何真实土面；
- `actual_removal` 后续要从 dig window 前后 `removed_depth` delta 推导，而不是继续只用
  first bite bucket cell proxy。

2026-05-21 执行补充：Unity telemetry 修改后不再手动监督 Play Mode。Repo B 新增
`CodexPlayModeBootstrap` Editor automation；Repo A 新增 `tb-unity-restart-smoke`
wrapper，固定执行“退出 Play Mode -> 等待编译/domain reload -> 打开 YuLong 主场景 ->
进入 Play Mode -> 等待 step-ack server listening -> strict `agx_smoke`”。可选
`--replay-episode/--record-output-dir/--check-removed-depth` 会继续刷新 1-2 条 HDF5，
并要求 `env_state[:,39:45]` 产生 removed-depth 时间变化，不通过就停止。

同日 swing 误差归因补充：不在 replay/rollout 侧加 guard 掩盖问题，而是在
`tb-replay` 增加 `--diagnostic-log` JSONL。每个 step 记录 action、source/replay
qpos/qvel、qpos error、bucket 相对 DigArea 坐标、contact/collision、
removed-depth grid 和 bucket mass delta；`tb-unity-restart-smoke` 可通过
`--replay-diagnostic-dir` 给每个刷新 episode 写独立诊断文件。复现误差后先用
`tb-replay-diagnostics --input <jsonl-or-dir>` 找首个 qpos error/jump 与接触、
碰撞、surface delta 的时间关系，再回到 Unity/AGX 参数层修真实原因。
对已确认来自旧原始数据、且修复后无法随机复现的 actuator pose 跳变，replay 刷
removed-depth 时允许启用 `--realign-on-qpos-error --realign-axis all`：
在持续 qpos 偏差后通过 Unity `REALIGN_POSE` 把当前仿真 4D qpos 拉回 source，
再继续生成新的 image/env_state/depth。这个入口只用于保护重新生成的数据一致性，
不支持事后批量篡改旧 HDF5 qpos；`swing` 单轴模式只作为调试保留。
replay 写入的 `replay_pose_realign_steps` 是高敏感弃置信号：primitive split 时，
只要某个完整逻辑 cycle 覆盖 realign step，就把该 cycle 写入 reject summary，
不进入对应 primitive 训练集。完整逻辑 cycle 指本轮 dig start 到 return
完成/下一次 qualified dig start 之前的半开窗口；如果 realign 正好落在下一轮
qualified dig start 帧，只归属下一轮。实际写 `dig/carry/dump` 训练片段时仍只
裁到 `dump_end_step`，避免 `dump` 吞入 return。覆盖 realign step 的 return
transition window 也会单独 reject，但同样不包含下一轮 qualified dig start 帧。

标注与重建数据链时沿用过去高 CPU 利用率的两段式脚本风格：先多进程/多线程切 VDS，
再从 primitive VDS 并行 materialize 带 image 信息的 primitive copy，避免在 relabel、
primitive build 和 image materialize 阶段串行等待。

同日 token contract 收口：`dig_cut_tokens` / `return_target_tokens` 维度仍是 10D，
但版本 bump 为 `v2_4_removed_depth_cut_v3`。第 8 维不再表示 bucket peak depth，
而是本铲 `max(actual_removed_depth_delta_grid)`，按 `0.25m` 归一化；旧 checkpoint
视为不兼容。operator-first gold tier 和 hindsight valid mask 只接受
`depth_outcome_source=env_state_removed_depth_delta` 的 cycle，没有可靠 removed-depth 的
cycle 只能作为 silver/无效 outcome 留作诊断。

2026-05-22 QC 流程补充：第一轮 `0.15m` scale 虽然让 p10/p50/p90 分离，但 depth
token 饱和率约 `8%`，高于 `<2%` 验收线；`0.22m` 在 gold-only 训练集上仍约
`2.6%`。用 replay 后 gold dig cycle 统计重估后，真实 removed-depth p10/p50/p90
约为 `0.046/0.085/0.157m`，因此 scale 改为 `0.25m` 并新增
`yulong_removed_depth_dig_cut_prior_v3.json`；旧 v1/v2 checkpoint 不进入 live rollout。

新增 `tb-build-v2_4-hindsight-pipeline` 作为这条链路的统一 job runner。它支持从
raw、relabeled 或 operator-first root 接入，阶段日志固定写到
`runs/jobs/<job>/logs/*.log`，长任务可用 `--detach` 后 `tail -f` 观察；数据落盘顺序是
label/operator-first/hindsight VDS -> primitive VDS -> parallel materialized primitive
copy。正式跑全流程时必须用 `--detach` 后台执行，避免 Cursor 和数据保存/materialize
同时占用内存。
primitive VDS 完成后必须先跑 pre-materialize QC：检查 gold depth token 饱和率、
depth p10/p50/p90 分离、可靠 `env_state_removed_depth_delta` 占比和 return window
最大长度。QC 不通过时直接停止，不写 image copy、不训练。
return window 必须与训练 horizon 对齐：V2.4 return ACT 当前 `episode_len=512`，
所以 pipeline 默认 `--return-max-transition-len 512`。超过该长度的 dump-end 到下一次
qualified-dig-start gap 多半是长等待、恢复或重新找下一铲，不应作为干净 return
primitive 训练样本。

失败原因不是“专业师傅没按规则操作”，也不是“需要给师傅更多 live target”。大规模真实
采集必须尽量保持专业师傅自然操作。真正的问题是：我们把自然数据 hindsight 得到的
`dig_cut_tokens` 当成了 live command token，但普通 BC/ACT 没有被强制学习“同一观测下，
不同 token 应该导致不同目标动作”。在自然数据里，token 和当前状态、师傅习惯、上一铲位置
高度相关；模型可以主要靠图像/qpos/qvel 复现平均专业动作，而把 token 当成弱相关辅助量。
因此 planner 在 live 时给一个合理但分布少见的 token，模型不一定会按它执行。

这说明原计划需要增加一个新的中间阶段：**outcome-grounded hindsight goal-conditioned
learning**。它仍然使用自然 pro 数据，不要求师傅按外部 token 操作，但训练时必须把
“目标 token -> 实际 outcome”变成显式监督，而不是只把 token 拼到 low-dim 输入里。

下一阶段修订：

1. 保持自然采集原则：
   - 不要求专业师傅挖指定 cell；
   - 不要求 live overlay 指挥师傅；
   - raw 数据只记录自然完整作业；
   - 离线用 hindsight relabel 抽取实际 entry、exit、swept corridor、payload、deposit、
     handoff pose 和下一次 return target。

2. 升级数据语义：
   - `dig_cut_tokens` 不再只作为输入 token，还必须有对应的 realized outcome 字段；
   - 每个 dig 样本记录 commanded/hindsight token、actual entry、actual exit、actual swept
     segment、payload gain、bucket start/end pose、handoff pose；
   - 每个 return 样本记录 target next-entry envelope、actual return end pose、entry gap、
     是否进入 dig 可接管状态；
   - 每个 carry/dump 样本记录 smooth release onset、first effective deposit、dump ownership
     start，避免专业连续开斗被错误留在 carry。

3. 训练不再只是 BC：
   - `dig` 使用 `qpos + qvel + image + dig_cut_tokens` 做 action BC；
   - 同时增加 outcome 辅助头，预测 entry/exit/payload/handoff pose；
   - 增加 token consistency loss：模型预测 outcome 必须接近输入 token 所描述的目标；
   - 增加 contrastive / token-swap 诊断：同一观测替换不同 token，动作和预测 outcome
     必须发生方向一致的变化；
   - 如果 token-swap 下动作几乎不变，该 checkpoint 不允许进入 coverage planner live eval。

4. planner 先降级为分布内 intent generator：
   - 不再把 coverage planner 当成强规则控制器；
   - planner 只选择训练数据支持的 intent family，并输出分布内 token；
   - 对未覆盖区域的推进先通过 learned belief / outcome predictor 排序，而不是直接强行
     选极端 corridor；
   - token 超出训练支持或 return 起点离 target envelope 太远时，进入 replan / recover，
     不强交给 dig ACT。

5. primitive ownership 继续收紧：
   - `carry -> dump` 必须 outcome-first：一旦 bucket 到达 dump footprint/near window 且
     deposit 开始，就把 ownership 转给 dump；
   - 不再用过窄 signed x/z window 阻止专业 smooth release；
   - `dig -> carry` 要以 payload / plateau / handoff pose 共同决定，避免半斗或 bad pose
     污染 carry；
   - 所有 ownership failure 都进入 structured attribution，而不是只看 episode success。

6. 下一轮验证顺序：
   - 先离线做 token-swap + outcome-prediction 验证；
   - 再做 1-cycle / 3-cycle command-following smoke；
   - 再回归 5cycle milestone；
   - 只有 5cycle 不退化，才重新测试 15cycle；
   - 30cycle 仍只作为 depletion / coverage probe，不作为当前 success 标准。

因此，当前结论是：原计划的 staged layered-control 方向仍然正确，但“conditioned ACT =
把 token 拼进输入然后做 BC”这个实现假设不够。下一阶段必须让 token 通过 outcome loss、
counterfactual token-swap 和 ownership outcome gate 变成 ACT 必须遵守的任务条件。

2026-05-20 boundary / label 第一性原理补充：这是后续必须持续处理的设计风险，
但不阻塞当前 V2.4 hindsight-goal 训练流水线。当前 relabel 和 primitive split 的输出
必须被视为 **rule-derived weak label**，不是绝对 ground truth。`env_state`、mass、
deposit、stage event 和 boundary rule 都是强证据，但它们可能提前、滞后、受 physics
artifact 影响，或者无法表达专业师傅的连续动作语义。后续每次重建训练数据前都应先问：
“这个窗口的动作因果责任是不是确实属于这个 primitive？”

因此新增一层 boundary audit：

- primitive boundary 不是一个无厚度瞬间，而是可能存在过渡区间；
- builder 仍输出确定的 `source_start_step` / `source_end_step_exclusive`，但 audit
  需要记录 `boundary_start_candidate`、`boundary_end_candidate`、`boundary_confidence`、
  `boundary_sources` 和 `boundary_or_label_uncertain`；
- 判断依据优先按因果责任：
  - `dig`：导致 bucket mass 增加和 soil removal 的主要切削动作；
  - `carry`：保持 payload 并把 bucket 送向 dump area 的 loaded transport；
  - `dump`：导致有效 deposit 的 release / alignment / post-release 动作；
  - `return`：回到下一次 dig start envelope 的动作；
- 如果视觉上已经开始 release 或 deposit，即使旧 official dump_start 还没到，也不应继续把
  这段动作训练给 carry；
- 如果视觉上 return 还没进入下一次 dig 可接管姿态，就不应把后续 dig 的失败完全归因给
  dig policy；
- 过渡窗口可以丢弃、降权或标记为 uncertain，不能硬塞进某个 primitive 当作干净 gold。

第一版工具入口：

```bash
tb-audit-primitive-boundaries \
  --primitive-root data/yulong_v2_4_hindsight_goal_primitives_vds \
  --output-dir runs/audit/yulong_v2_4_boundary_audit_20260520 \
  --camera fpv \
  --pre-steps 100 \
  --post-steps 100 \
  --max-videos 24 \
  --sample top-risk
```

该工具读取 `window_manifest.json`，从 source episode / VDS 图像中导出边界前后短视频，
并写 `summary.json`、`boundary_audit.csv`、`selected_boundary_videos.json`。
视频叠加 primitive、cycle、boundary step、payload/deposit/return gap 和风险 flags。
这不是最终自动视觉标注器，而是第一层人工可审计证据：先看 label/split 是否视觉上成立，
再决定修 rule、增加 transition drop window、降权 uncertain 样本，或重建 primitive。

## Internal Phase / BT Skeleton

当前不建议把控制 ownership 直接拆成更多独立 ACT policy。外层仍保持四 primitive：

```text
dig -> carry -> dump -> return
```

但为了诊断和后续扩展，内部应显式记录更细的 phase / BT node：

| ownership | internal phase / node | 用途 |
| --- | --- | --- |
| `dig` | `approach_soil` / `dig_contact` / `cut_fill` / `lift_clear` / `dig_handoff` | 诊断 entry、入土、装斗和出土 handoff |
| `carry` | `swing_to_dump` / `dump_handoff_corridor` | 诊断 loaded transport 是否污染 release |
| `dump` | `dump_approach` / `alignment` / `release` / `post_dump_hold` | 保留 mixed dump，不拆碎成多个 policy |
| `return` | `return_to_entry` / `wait_next_dig` | 诊断 return 是否到达 next entry |
| fallback | `recover` | 处理 timeout、碰撞风险、低产、miss，不进入默认成功路径 |

这些 phase 第一阶段只作为规则式 BT/FSM 的节点、日志和 predicate 载体。不要因为加了这些
名字，就立刻训练 7 个或更多 policy。

每个 primitive 或 phase 都应有：

- precondition：进入该节点前应满足什么；
- termination：什么时候退出；
- success predicate：这段是否完成了自己的职责；
- failure reason：失败原因必须结构化记录。

例子：

```text
dig precondition:
  bucket in planned entry envelope
  selected cell valid
  bucket empty enough
  target depth reachable

dig success:
  actual bite near planned bite
  payload gain above threshold
  selected cell removed depth increased
  handoff pose acceptable for carry
```

第一阶段应显式采用 gate 逻辑，而不是只要进入某个旧 QDS 状态就调用 `dig`：

```text
if planner_invalid or planner_high_risk:
  replan_or_recover
elif entry_delta too large or not inside_entry_envelope:
  approach_soil_or_return_to_entry_correction
else:
  call conditioned dig ACT with entry_delta
```

这样 `entry_delta` 只处理小偏差。planner 目标错、return 没到、entry envelope 之外的状态
都不应该强行交给 `dig ACT` 吃掉。

## Start / Boundary 的新定义

未来不要把当前 V2.2 `BoundaryDetector` 的阈值当成框架定义。

新框架里应区分三件事：

1. **planned entry target**：planner 希望 bucket 到达的位置和姿态范围；
2. **actual accepted start**：执行效果上确认这次 dig 已经有效开始；
3. **actual bite / removal**：soil 实际开始被切削和最终被移除的位置。

当前 legacy `qualified_dig_start` 可以作为短期替代信号；YuLong 小斗环境使用
`qualified_dig_start_mode=contact_depth`，让它先表达 dig-area 接触和下挖深度，
不再等待质量增量。最终仍应升级为更清楚的 effect-based event：

- bucket 进入目标作业区局部范围；
- bucket 相对 local surface 达到可挖深度；
- 出现 soil interaction / payload gain / good-dig 信号；
- actual start cell 与 planned cell 可比较；
- 如果 start 错 cell，记录 miss，而不是重绑成功。

因此，未来不需要保留旧 `BoundaryDetector` 的具体阈值说明。需要保留的是：

```text
用执行效果确认事件，而不是用固定 ready pose 硬匹配。
```

## Conditioned ACT 路线

不要一次把所有 primitive 都改成 conditioned。推荐顺序：

| 阶段 | conditioned ACT | 目的 | 评估重点 |
| --- | --- | --- | --- |
| 0 | 无 | 用新数据复现 V2.2 四 primitive 稳定性 | dump/return 是否学回，3-cycle 是否稳定 |
| 1 | `dig` | 学会不同 cell / bite / depth 下挖掘 | selected cell vs actual bite/removal |
| 2 | `dig + return` | 让 return 到达 next entry | planned entry vs actual accepted start |
| 3 | `dig + return + dump` | 仅在 dump area 可变时启用 | target deposit vs actual deposit |

`carry` 默认保持非 conditioned。

当前 YuLong pilot 的数据构建仍先经过阶段 0 的四 primitive ownership 稳定性检查；
通过后进入阶段 1：只训练 conditioned `dig`。训练配置使用
`act_yulong_v2_2_pro_conditioned_dig_cell_entry_qvel.yaml`，输入为
`qpos + qvel + cell_entry_tokens`；live 配置使用
`eval_yulong_v2_2_pro_primitive_planner_conditioned_dig_smoke.yaml`，由
`primitive_planner_act` 只在调用 `dig` policy 时注入 live Cell Entry token，
`carry/dump/return` 仍保持 `qpos + qvel`。不把 one full-task ACT/GC-ACT 或
旧 `left/mid/right` goal-token planner 当成正式主线。若新环境没有打出
`approach_dump` 标签，但稳定 release onset 和 final good dump 都成立，可以使用
`tb-build-primitives-v2_2 --boundary-profile v2_2_effect_release_fallback`，把
`carry -> dump` 边界前移到 effect-based release onset。reset 到首个 entry 的
短期 smoke 兼容层使用 `primitive_planner_act` 的 `bootstrap_end_mode=scripted_qpos`；
若设备动作方向和 qpos 方向不一致，用 `scripted_bootstrap.action_signs` 显式声明每轴符号。
它只负责进入 planned/accepted entry 附近，不是 learned primitive，也不代表最终 planner。

### dig pose 如何强化

`dig` 不能只学一个粗 cell id。要让它学会深度变化下的 start pose，需要在数据中记录
并监督这些量：

- planned entry target；
- current bucket local pose at dig call；
- entry_delta；
- inside_entry_envelope_mask；
- distance_to_entry_envelope；
- teacher actual accepted start；
- actual bite point；
- actual removal cell；
- target depth；
- local surface around bite；
- bucket payload gain；
- 出土后的 handoff pose。

`start_source = reset / return / recovery` 和 `cycle_index` 应先写入日志和数据集，便于
诊断第一铲与后续铲的分布差异；第一阶段不建议把它们作为 `dig ACT` 的核心输入。

训练时可以先用专家数据中的 actual accepted start / actual bite 反推 teacher target，
让 ACT 学会“给定这个目标，如何自然完成一铲”。上线时再由 Bite / Entry Planner 生成
同样结构的 target。

### return 如何强化

return 的训练窗口应该是：

```text
dump_end + post_dump_hold -> next accepted dig start
```

窗口内必须排除 dump release 尾部，避免 return 学到 bucket release。

每个 return 样本要记录：

- return start pose；
- next entry envelope local x/z/depth；
- next cut corridor summary，用于区分同一 entry 下不同 swept-area 意图；
- next accepted start local x/z/depth；
- next accepted start cell；
- target miss / timeout / repeated-cell 标记。

只有当 A/B 证明非 conditioned return 不能到达 next entry 时，才训练 target-conditioned
return。

## Outcome Evaluator / Data Builder

未来 builder 不只是切数据，也要写出 planner intent 与实际结果之间的对齐关系。

每个 cycle 至少应写：

- selected cell；
- planner audit result；
- planned entry target；
- planned entry envelope；
- current bucket local pose at dig call；
- entry_delta；
- inside_entry_envelope_mask；
- distance_to_entry_envelope；
- start_source；
- cycle_index；
- actual accepted start；
- actual bite；
- actual removal cell；
- payload gain；
- dump target；
- actual deposit；
- target miss flags；
- precondition / termination / success predicate results；
- structured failure attribution；
- primitive boundary / chunk barrier。

失败归因至少应覆盖：

```text
planner_invalid
planner_high_risk
entry_delta_too_large
return_miss
dig_condition_miss
dig_low_productivity
dig_handoff_bad
carry_contamination
dump_failure
recover_triggered
boundary_or_label_uncertain
```

评估时不能只看 episode 是否完成。每一铲都要回答：

- planner 选得是否合理；
- return 是否把 bucket 带到 planned entry envelope；
- reset / return 起点误差是否仍在 `entry_delta` 可修正范围内；
- dig 是否按 target cell / bite / depth 执行；
- soil 是否从 selected cell 被移除；
- 出土 handoff 是否适合 carry；
- dump 是否在正确区域释放；
- 如果失败，是否触发 recover，recover 是否成功。

训练数据仍建议从自然 full-cycle raw 中离线切分：

```text
raw full-cycle
  -> relabeled full-cycle
  -> cell-entry/operator-first enriched raw (prefer VDS wrapper)
  -> primitives/dig
  -> primitives/carry
  -> primitives/dump
  -> primitives/return
```

当前实现入口是 `tb-build-cell-entry-v2_2`：它在 primitive split 之前对 raw
episode 追加 3x2 Cell Entry 的 planned/actual/audit `/v2` 字段与
`cell_entry_tokens`。YuLong 主线应使用
`tb-build-cell-entry-v2_2 --storage-mode vds`，让大图像、qpos/qvel/action、
env_state、timestamps 和已有 `/v2/step/*` 通过 HDF5 VDS 指向 immutable raw root，
只在 wrapper 中直接写新增 Cell Entry 字段、metadata、cycle QC 和 lineage。
`tb-build-primitives-v2_2 --storage-mode vds --raw-dir <cell-entry-root>`
直接消费 enriched raw 并切出四个 primitive sibling datasets；`--storage-mode manifest`
只写窗口 manifest/summary，用于 dry-run QC。primitive wrapper 会记录
`source_episode_path`、`source_start_step`、`source_end_step_exclusive`、
`source_cycle_id`、`primitive_name`、boundary profile 与 Cell Entry audit 标量。
两个 builder 都会写 `lineage.json`，并默认拒绝覆盖已有 episode；需要维护
`data/` 下的当前候选入口时，用 `--current-symlink <path>` 只更新 symlink，
真实历史 root 仍应保持 immutable。builder 不重新承担 planner/audit 决策。

2026-05-16 YuLong pro 数据采用 operator-first 语义修正：`cell_entry` 继续作为
legacy diagnostic，不再把离线 scripted selected cell 当成专业师傅必须执行的目标。
正式 conditioned dig 目标改为 `dig_cut_tokens`，由专业操作的实际 entry/exit
cut corridor、cut length、depth peak 和 payload gain 离线推导。对应入口为
`tb-build-operator-first-v2_2`，输入已有 relabeled VDS root，输出 add-only VDS
wrapper；新增字段包括 `cycle_effective_deposit_delta_kg`、`legacy_dump_end_deposit_delta_kg`、
`dump_window_deposit_delta_kg`、`operator_entry_*`、`operator_exit_*`、
`operator_cut_*`、`next_operator_entry_*`、`return_entry_delta_*` 与
`/v2/step/dig_cut_tokens`。该 builder 不覆盖旧 `/v2/cycle/deposit_delta_kg`，
也不修改 immutable raw。

planner 同步采用 operator-first live token：这一版历史 baseline 的
`dig_cut_tokens` 10D schema 保持不变，训练侧无需重训；rollout 侧默认使用
`dig_cut_planner.mode=operator_prior`，读取
`testbed/configs/planner_priors/yulong_operator_first_dig_cut_prior_v1.json`。该 prior
来自当前 26 条 YuLong 专业操作 operator-first relabel 数据中的 640 条 gold cycle，
记录 P10/P50/P90 与 lineage。旧固定模板 planner 保留为
`dig_cut_planner.mode=conservative_pose`，baseline tag 为
`planner-baseline-conservative-pose-20260516`，用于 A/B 和回溯。

2026-05-19 起，YuLong V2.4 planner 优化在不改 ACT checkpoint、不改
`dig_cut_tokens` 10D schema 的前提下增加 `operator_prior_coverage` 模式。
它从现有 64D `env_state` 读取 3x2 DigArea `removed_depth/target_depth/valid_mask`
和当前 payload/deposit outcome，维护 9 条 operator-prior corridor
(`entry_x=p10/p50/p90` × `entry_z=p10/p50/p90`) 的 attempts、last payload、
last effective deposit、low-productivity streak、depleted flag 和 score，并通过
max-attempt、attempt penalty、recent-selection penalty 以及 recent-row penalty 避免长
rollout 后段继续挖空区，或在一次低产后继续沿同一 entry-z row 的相邻 corridor 反复挖。
连续低产、remaining depth 低于阈值或疑似穿模进土时，planner 输出 terminal stop
reason；30cycle 配置因此是 depletion/probe，不是新的任务成功标准。Repo A 会把压缩后的
`planner_debug_json` 作为 `STEP_REQ` optional tail 发给 Unity，用 HUD 和 DigArea
细竖针实时显示 planner 入铲点，方便区分 planner 选点问题、ACT 跟随问题和
物理伪进土。

2026-05-19 决议：`pre_dig_align` 只保留为诊断/兼容开关，不能作为长期
layered-control 方案替代 learned transition。2026-05-21 补充：conditioned return
只覆盖第二铲开始的 `return -> dig` handoff，第一铲没有上一轮 return，因此 V2.4
conditioned-return / hindsight-goal live eval 允许
`pre_dig_align.first_dig_only=true` 只在 `bootstrap -> dig` 前做一次友好的 entry
handoff，并用 `coverage.first_dig_strategy=nearest_entry` 按当前 bucket-tip 到
候选 entry 的距离选择更容易接上的 corridor；`coverage.first_dig_max_entry_distance_m`
进一步作为第一铲 reachability gate：只要有专家 corridor 在当前 bucket-tip 阈值内，
第一铲 planner 就排除更远的候选，避免把 bootstrap 位置强交给远处 green entry。
如果 replan 后新 entry 已经 close，直接 handoff 给 dig，避免 qpos proxy align 又把
bucket 推远。2026-05-22 评测暴露出另一层问题：第一铲 handoff 容易把选择
entry 的任务和大幅调整大小臂的任务混在一起，因此新增
`coverage.first_dig_max_qpos_delta` / `coverage.first_dig_qpos_delta_weight`：第一铲
候选除了 entry 距离外，还会检查该 corridor 对应的 pre-dig qpos target 离当前
qpos 有多远；需要大幅抬臂、收臂或改变 bucket 姿态的候选会被排除或降权。
同日评测还暴露出第一铲 pre-dig align 用静态 qpos
target 伺服，实际 bucket-tip 曾进入 entry close window 后又被继续推过 entry。因此新增
`pre_dig_align.first_dig_entry_close_handoff`：第 0 铲实际 entry close 且受控轴速度低于
`first_dig_entry_close_handoff_qvel_abs_max` 时，允许 handoff 给 dig，不再等待 qpos
proxy target 完全 close。但 entry close 不是充分条件，handoff 还必须满足专家
dig-start qpos envelope；scale025 eval 配置把 first-dig align 的 qpos clamp 收紧到
dig primitive 起点 qpos 近似 p05/p95，并取消固定 `bucket_target_qpos=0.0`，避免
把大小臂或铲斗带到不属于正常 dig-start 的姿态。后续铲次仍回到原计划：planner 选择 next entry/corridor，
conditioned return 学会把空斗回到适合 conditioned dig ACT 接管的 next-entry 状态；
return 切回 dig 时还要满足
`return_to_dig_max_entry_error_m`，且 entry close 时 shallow guard 可越过很窄的
max-depth 上限，防止 return 到位后继续把 bucket 压进土里。
如果第 0 铲 scripted handoff 仍承担过多抬/收大小臂动作，可以用旧 dig checkpoint
做 learned first-handoff A/B：`bootstrap_ckpt_path` 指向旧 dig，`bootstrap_low_dim_keys`
设为 `[qpos, qvel, dig_cut_tokens]`，`bootstrap_end_mode=first_qualified_dig_start`，
并关闭 `pre_dig_align`；planner 在 bootstrap policy 存在时会复用同一套 dig-cut token，
让 learned bootstrap 到达 qualified dig start 后直接交给新的 V2.4 dig。
也可以只替换第 0 铲实际 dig：配置 `first_dig_ckpt_path` 后，planner 在 cycle 0 且尚未
完成 dump 前使用该 checkpoint，第二铲起恢复普通 V2.4 dig。
本轮 live eval 还需要显式设置 `dig_to_carry_min_distance_to_dig_area_m=0.0`：
第一铲 target payload 达标即可交给 carry，不再要求 bucket 先离开 DigArea；否则旧
first-dig ckpt 会在装满后继续留在 dig，V2.4 dig 也会在峰值后继续漏料。

YuLong V2.4 live layered-control ownership:

| 对象 | 当前 owner | 不应该由谁决定 | 诊断字段 / 显示 | 当前风险与修正方向 |
|---|---|---|---|---|
| Dig area 几何与坐标系 | Unity scene + `DigAreaMeasurement` + 64D `env_state` | ACT / planner 不应改变 dig area 本身 | `env_state` bucket DigArea local pose、3x2 removed/target/valid grid | 若 DigArea 坐标方向或深度传感错误，planner 会系统性选错；需要先修 Unity/测量，不应靠 ACT 补偿 |
| Dig point / corridor | Python `operator_prior_coverage` planner | dig ACT 不应自己决定全局挖哪块 | Unity HUD + DigArea 细竖针；`coverage_corridor_id`、entry/exit、score | planner 只给未挖区域的 intent；若 ACT 没到点，是执行层问题，不应把 planner target rebind 成成功 |
| Pre-dig pose / entry execution | 第 0 铲使用 nearest-entry first corridor + first-dig reachability gate + entry-close handoff；后续铲使用 planned conditioned `return` policy + entry-error gate | planner 不直接输出完整关节轨迹；dig ACT 不应负责长距离回到目标点 | `return_target_tokens`、`coverage_first_dig_strategy`、`coverage_first_dig_max_entry_distance_m`、`pre_dig_align_first_dig_entry_close_handoff`、`return_to_dig_entry_error_m`、actual bucket-tip marker | 第一铲没有上一轮 return，需选择当前 bucket-tip 附近、可达、专家分布内的 entry，并在实际 entry close 后及时交给 dig；后续 return 应根据下一次 dig intent 回到目标 entry 附近，entry close 后要及时 handoff，避免 return 继续插土 |
| Bucket start attitude | planned conditioned `return` 准备 entry-ready 姿态，dig ACT 接管最终卷斗 | 不能用固定 `bucket qpos=1` 当 good dig start | 专业 dig start qpos 分布、bucket qpos、bucket depth | 当前专业数据 dig start bucket qpos 是低 curl 小范围；应由 conditioned return 学这个分布，而不是手写锁定 bucket |
| Local cut / scooping motion | conditioned `dig` ACT | coverage planner 不应手写完整挖掘轨迹 | `dig_cut_token_injected`、payload gain、bucket depth、mass curve | 如果 entry 到位后仍挖不满，才说明 dig ACT 对 token/pose 学得不够，需要补训或改 conditioning |
| `dig -> carry` handoff | primitive planner switch rule | carry 不应继续承担大量挖土 | bucket mass、mass plateau、dig step count、depth | 低阈值会导致半斗就切 carry，污染 ownership 并降低效率；应使用更高有效载荷目标或 mass plateau + bad-dig replan |

2026-05-19 后续修正：`dig -> carry` 不再只看 `15kg` 最低质量。正式 target
payload 提高到 `45kg`，只有达到 target 或出现 `>=35kg` 后的质量 plateau 才进入
carry；如果 dig 已运行 `220` step 仍低于 `35kg`，记为 `bad_dig_low_payload` 并
回到 planner/replan。这保证 carry 不再承担挖土职责，也避免 bad pose 让 dig ACT
在错误位置空挖几千步。`pre_dig_align` 实验结论保留为诊断记录：它能暴露
return-to-entry 的需求，但不能替代 conditioned return；当前仅作为 first-dig-only
handoff 修补第一铲没有 return 的启动空洞。

2026-05-21 5cycle live probe 补充：第 4 铲卡住时，corridor 曾短暂达到约 19kg
best mass，但当前 bucket mass 已经掉回 0kg，旧 bad-dig 判据因为只看 best mass
而没有 reject，导致 dig 在同一位置空转数千步。修正后 bad-dig replan 使用当前保留
bucket mass 判断，同时 `recent_row_selection_penalty` 会惩罚刚挖过 row 的相邻
corridor，减少低产后在同一横排反复挖的概率。

2026-05-21 dig 轨迹审计补充：yellow exit marker 已经进入 `dig_cut_tokens`，
但它目前只是 goal/diagnostic，不是手写轨迹终止条件。V2.4 hindsight eval 中 ACT
常能经过 planned exit 附近，但如果此时 bucket mass 仍低，状态机会继续等待 payload
或 plateau，造成“从前挖到后、继续推到 DigArea 边界”的长动作。修正方向不是让 planner
规定专家每一步动作，而是在专家 prior 内更正确地选 goal：coverage planner 支持配置
`cut_depth_percentile` / `payload_percentile`，当前 V2.4 hindsight eval 默认请求 p90
depth/payload；同时 `dig_exit_guard_*` 会在 bucket tip 已明显越过 planned exit
但 payload 仍过低时标记 `exit_overshoot_low_payload` 并 replan。

depth 控制现状：`dig_cut_tokens` 里已有 depth field，V2.4 hindsight eval 默认请求
p90 depth/payload；但这仍是 open-loop conditioning，不是闭环深度 controller。
如果 ACT 没学会把 depth token 转成更深且及时离土的姿态，或 Unity soil/depth 反馈不足，
状态机只能通过 bad-dig / exit-overshoot guard 早停重选。后续要真正控制深度，需要将
depth trajectory/outcome 纳入训练或引入独立 depth guard。

2026-05-19 live primitive 状态机同步 operator-first dump/return 语义：YuLong
10-cycle clean-dump rollout 不再用 post-dump hold 作为主要稳定手段；smooth dump
由累计有效入箱质量触发 `dump_start/dump_end`，避免专业师傅缓慢开斗时单步
deposit spike 低于旧阈值而漏记 dump。return 阶段增加 entry-gated shallow handoff：
空斗回到 planned next-entry 附近并接触 dig-area 时立即切回 dig；entry 已 close 时不再
被过窄 shallow max-depth 卡住，避免 return primitive 到位后继续向下压。
30-cycle stress 暴露出 `carry -> dump` signed window 和 `20kg` dump-ready payload
阈值会在后段造成卡死：bucket 已在 dump footprint 上方、离 rim 足够高、bucket 里
仍有约 `15-20kg` 土，但 target-relative x/z 漂到窗口另一侧或 payload 低于旧阈值，
状态机就一直停留在 carry。因此 long-cycle smoke 改为 outcome-first handoff：
bucket 在 dump footprint 上方、height/mass 满足即可切 dump；signed x/z window 只作
旧规则兼容，不再作为专业操作的唯一 dump 起点定义。

当前 YuLong operator-first 主线命令：

```bash
tb-build-operator-first-v2_2 \
  --dataset-dir data/yulong_v2_2_current_relabeled \
  --output-dir /data/pingfan/excavator_testbed_data_archive/yulong_v2_2_pro_full_task_raw_20260515_26eps_good_operator_first_relabel_v2_2_20260516 \
  --storage-mode vds \
  --current-symlink data/yulong_v2_2_current_operator_relabel

tb-build-primitives-v2_2 \
  --raw-dir data/yulong_v2_2_current_operator_relabel \
  --output-root /data/pingfan/excavator_testbed_data_archive/yulong_v2_2_pro_full_task_raw_20260515_26eps_good_operator_first_primitives_v2_2_vds_20260516 \
  --storage-mode vds \
  --boundary-profile v2_2_effect_release_fallback \
  --current-symlink data/yulong_v2_2_current_primitives_operator_first
```

具体录制入口、episode 长度、stop mode、字段需求、QC 和专业师傅现场规则，以
`docs/v2_2_pro_operator_data_collection_plan.md` 为准。本文不重复录制规则。

## V2.4 Outcome-Grounded Hindsight Goal-Conditioned Learning

当前 V2.2/operator-first 主线已经完成了自然 pro raw、operator-first relabel、
四 primitive split、conditioned dig、conditioned return 和 coverage/sweep planner
实验。但 live rollout 暴露出一个根本问题：planner 改目标以后，低层 ACT 不一定真的
跟随目标，常常仍复现训练集中最常见的专业动作习惯。结果是“planner 指哪”和“ACT 挖哪”
脱节；规则式 align 又容易制造抖动和不自然 handoff，不能作为长期方案。

V2.4 的修正原则：

- 不要求专业师傅按 token 操作，录制仍保持自然；
- 离线从自然数据反推 actual entry/exit/cut/payload/deposit/return target，作为
  hindsight goal；
- `dig_cut_tokens` 与 `return_target_tokens` 保留 10D 维度，但 depth 语义后续
  bump 为 removed-depth delta contract；
- 新增 `dig_outcome_targets`、`return_outcome_targets` 和对应 valid mask；
- `dig`、`return` 训练时在原 ACT action BC + KL 上增加 outcome head；
- outcome head 直接从 predicted action chunk 预测 hindsight outcome，loss 会通过
  predicted action 反传，迫使动作随 token 改变；
- token-swap loss 对同一 observation 换另一个 goal token，不做 action BC，只要求
  predicted action chunk 对应 swapped hindsight outcome；
- 离线 sensitivity 必须同时看 action delta 和 predicted outcome delta。若 token
  swap 后二者仍几乎不动，不进入 live rollout。

V2.4 数据与训练入口：

```bash
tb-build-hindsight-goal-v2_4 \
  --dataset-dir data/yulong_v2_4_return_target_operator_relabel_copy \
  --output-dir data/yulong_v2_4_hindsight_goal_relabel_copy

tb-build-primitives-v2_2 \
  --raw-dir data/yulong_v2_4_hindsight_goal_relabel_copy \
  --output-root data/yulong_v2_4_hindsight_goal_primitives_copy \
  --storage-mode copy \
  --boundary-profile v2_2_effect_release_fallback

tb-train --config testbed/configs/act_yulong_v2_4_hindsight_goal_dig_qvel.yaml
tb-train --config testbed/configs/act_yulong_v2_4_hindsight_goal_return_qvel.yaml
```

训练配置默认只读取 `training_tier=gold` primitive episode；terminal return 没有
下一次 operator target 时仍由 primitive builder 排除。`carry/dump` 本轮不重训，
继续使用 V2.2 500e milestone checkpoint。旧 raw 若没有可靠 removed-depth，
`actual_removed_depth_delta_grid` 写 0，`depth_outcome_source` 写
`unavailable_or_legacy_zero`；修复后新录或 replay-derived root 才启用真实 depth-delta
监督。

2026-05-20 训练运行记录：hindsight dig/return 的 outcome head 会在每个 train
batch 上额外执行 token-swap forward。16GB 级 GPU 在桌面、Unity 或远程桌面占用显存时，
早先 `batch_size=24` 在 Step 7 dig 训练首个 train batch OOM。该 OOM 的一个放大因素是
validation 后 best-checkpoint snapshot 曾在 GPU 上常驻一份模型权重；trainer 已改为
CPU clone。当前先恢复 `batch_size=24`、`prefetch_factor=4` 重训，保持和既有 YuLong
conditioned runs 一致；只有再次确认 OOM 后，才降到 `batch_size=16`。

V2.4 rollout 顺序：

```bash
tb-eval --config testbed/configs/eval_yulong_v2_4_hindsight_goal_1cycle_smoke.yaml
tb-eval --config testbed/configs/eval_yulong_v2_4_hindsight_goal_3cycle_smoke.yaml
tb-eval --config testbed/configs/eval_yulong_v2_4_hindsight_goal_5cycle_smoke.yaml
tb-eval --config testbed/configs/eval_yulong_v2_4_hindsight_goal_10cycle.yaml
tb-eval --config testbed/configs/eval_yulong_v2_4_hindsight_goal_15cycle.yaml
tb-eval --config testbed/configs/eval_yulong_v2_4_hindsight_goal_30cycle_probe.yaml
```

30cycle 仍然只是 depletion probe，不是固定成功标准。若 V2.4 dig/return 离线证明
开始听 token，planner 才逐步放大自由度；短期 planner 仍是 rule/belief goal proposer，
不是 learned planner。

## 下一阶段最小实施顺序

推荐顺序：

1. 新场景量测对齐：作业区局部坐标、surface/depth grid、bucket local pose、payload、
   dump area metrics。
2. 定义 planner trace / audit / overlay schema：selected target、entry envelope、entry_delta、
   inside-envelope mask、risk flags、predicate result 和 failure attribution 必须有稳定字段。
3. 做规则式 BT/FSM 骨架和 Unity target overlay，先能显示 planned vs actual，再谈训练提升。
4. 录少量 new-env pilot raw 数据，先由内部人员完成，覆盖至少几轮完整 dig/carry/dump/return。
5. 跑 pilot 验证：HDF5 schema、视频导出、target geometry audit、overlay、relabel、
   primitive split、predicate attribution、3-cycle smoke 或离线回放都必须正常。
6. pilot 通过后，再邀请专业师傅录制大规模 full-cycle raw 数据，保持自然操作，不要求按
   primitive 停顿。
7. 写新版 relabel/builder：先用 `tb-build-operator-first-v2_2` 输出 operator cut
   corridor、effective deposit、return target 与 `dig_cut_tokens`，旧
   `cell_entry` 字段只保留诊断，再由 primitive builder 产出四 primitive sibling datasets。
8. 先训练 V2.2-style 四 primitive：全部 `qpos+qvel`，确认新数据能学回基本循环。
9. 只参数化 `dig`，做 A/B：old dig vs operator-first conditioned dig，其他 checkpoint 不变。
10. 如果 return 无法到达 next entry，再参数化 `return`。
11. 只有 dump area 可变时，再参数化 `dump`。

## 上一轮经验保留

V1：

- 单铲成功不代表完整任务成功；
- success 不能过早截断，否则 dump 后半段学不完整。

V2.1：

- 多轮 raw 和离线 relabel 是正确方向；
- planner intent 如果不进入 policy，只是日志，不是控制。

V2.2：

- 四 primitive ownership 是当前最可靠基础；
- `dump` 必须保持混合 primitive；
- `carry` 不能学 release；
- post-dump hold 有价值。

V2.3 / V2.3.5：

- paramdig 是必要方向，但不能和 carry/dump/return 同时大改；
- 5P split 不适合专业司机自然 dump；
- dump-area-token 对dump area 没价值；
- return 的 target 不能定义成 next actual bite；
- planner rebind 会掩盖失败，不能算成功；
- 旧 detector / 旧 planner 可以作为过渡工具，但不是新框架定义。

## 未来升级 backlog

这些方向有价值，但不应该压到第一阶段主线里。第一阶段先把规则 planner、overlay、
predicate、failure attribution 和 V2.2 四 primitive 稳线跑通。

### 学习式 Bite / Entry Planner

当规则 planner 的 trace 和专家数据的 planned/actual 对齐稳定后，可以训练学习式高层：

```text
world state / surface grid / history
  -> selected cell
  -> bite point
  -> target depth
  -> entry intent
```

训练方式可以从 supervised imitation 开始。label 来自专家数据反推：

- teacher actual accepted start；
- actual bite point；
- actual removal cell；
- effective target depth；
- early dig bucket pose / qpos pattern；
- payload gain；
- handoff pose。

也可以改成 candidate ranking：给多个 candidate bite / entry，预测哪个更像专家、产土更高、
miss 更少、handoff 更好。

### 高层 BC / Skill Policy

可以从遥操作和脚本运行日志里标注 phase，训练 shadow high-level BC：

```text
state / history -> next_skill + params
```

第一版不建议直接上线替代规则 BT/FSM。更稳的做法是 shadow eval：

- 规则 planner 实际控制；
- high-level BC 同步输出建议；
- 对比二者在 skill choice、target cell、bite point、target depth 上的差异；
- 只在离线表现稳定后，替换局部规则。

### Affordance Model

可以训练 affordance model 预测：

```text
P(skill_success | state, skill, params)
```

它优先用于 candidate ranking、risk flag、fallback trigger，而不是直接输出动作。可预测：

- 当前 cell / bite 是否可挖；
- return 是否能到 entry envelope；
- dig 是否可能有足够 payload gain；
- carry / dump handoff 是否高风险；
- 是否应该触发 recover 或换目标。

### Transition Skills

如果过渡不丝滑，优先补 transition / recover 能力，而不是让 `dig` 背所有阶段的责任。

候选方向：

- learned return-to-entry；
- approach-soil correction；
- anti-collision recovery；
- low-productivity rebite；
- missed-entry reattempt；
- dump-posture recovery。

这些可以先作为 BT/FSM 中的 fallback node，再根据数据量决定是否训练独立 policy。

### Diffusion Policy A/B

如果 ACT 在连续轨迹段显得僵硬，可以对 bounded skill 做 Diffusion Policy A/B，尤其是：

- `swing_to_dump`；
- `dump`；
- `return_to_entry`；
- recovery trajectory。

不建议一开始用 Diffusion Policy 替换整套 `dig/carry/dump/return`。先在边界清楚、评价明确、
数据覆盖足够的 skill 上比较轨迹自然度、成功率、推理延迟和安全 predicate。
