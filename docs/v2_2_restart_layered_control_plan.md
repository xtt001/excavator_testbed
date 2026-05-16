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
- local surface context；
- entry intent，例如切入方向、预期 bucket 姿态范围；
- next entry target，供 return 使用。

这层是 V2.3 `paramdig` 需要重做的地方。V2.3 的问题不是“参数化 dig 方向错”，而是
target 语义太粗，同时 return、planner、dump 数据边界一起变化，导致归因失控。

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
- entry intent。

不输入：

- dump target；
- dump-area-token；
- return 目标。

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

当前 YuLong pilot 属于阶段 0：先按 V2.2 四 primitive ownership 重新切分和训练，
不把 `left/mid/right` planner 或旧阈值实现当成新框架定义。若新环境没有打出
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
- teacher actual accepted start；
- actual bite point；
- actual removal cell；
- target depth；
- local surface around bite；
- bucket payload gain；
- 出土后的 handoff pose。

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
- next entry target local x/z/depth；
- next accepted start local x/z/depth；
- next accepted start cell；
- target miss / timeout / repeated-cell 标记。

只有当 A/B 证明非 conditioned return 不能到达 next entry 时，才训练 target-conditioned
return。

## Outcome Evaluator / Data Builder

未来 builder 不只是切数据，也要写出 planner intent 与实际结果之间的对齐关系。

每个 cycle 至少应写：

- selected cell；
- planned entry target；
- actual accepted start；
- actual bite；
- actual removal cell；
- payload gain；
- dump target；
- actual deposit；
- target miss flags；
- primitive boundary / chunk barrier。

训练数据仍建议从自然 full-cycle raw 中离线切分：

```text
raw full-cycle
  -> relabeled full-cycle
  -> primitives/dig
  -> primitives/carry
  -> primitives/dump
  -> primitives/return
```

具体录制入口、episode 长度、stop mode、字段需求、QC 和专业师傅现场规则，以
`docs/v2_2_pro_operator_data_collection_plan.md` 为准。本文不重复录制规则。

## 下一阶段最小实施顺序

推荐顺序：

1. 新场景量测对齐：作业区局部坐标、surface/depth grid、bucket local pose、payload、
   dump area metrics。
2. 录少量 new-env pilot raw 数据，先由内部人员完成，覆盖至少几轮完整 dig/carry/dump/return。
3. 跑 pilot 验证：HDF5 schema、视频导出、target geometry audit、relabel、primitive split、
   3-cycle smoke 或离线回放都必须正常。
4. pilot 通过后，再邀请专业师傅录制大规模 full-cycle raw 数据，保持自然操作，不要求按
   primitive 停顿。
5. 写新版 relabel/builder：输出 planned/actual 对齐字段和四 primitive sibling datasets。
6. 先训练 V2.2-style 四 primitive：全部 `qpos+qvel`，确认新数据能学回基本循环。
7. 只参数化 `dig`，做 A/B：old dig vs conditioned dig，其他 checkpoint 不变。
8. 如果 return 无法到达 next entry，再参数化 `return`。
9. 只有 dump area 可变时，再参数化 `dump`。

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
