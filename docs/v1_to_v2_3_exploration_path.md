# From V1 To V2.3 Exploration Path

Date: 2026-05-12

本文总结从 V1 baseline 到 V2.3 / V2.3.5 回退为止，我们围绕 AGXUnity
挖掘机任务做过的主要探索。重点不是只记录成功，而是把每一阶段的目的、尝试、
成果、不足和留下的判断都写清楚，方便后续从 V2.2 稳线重新出发。

## 一句话总览

V1 证明了 Python-Unity 数据、训练、评测链路能跑通，但只覆盖单铲短任务。
V2.1 把任务推进到多轮，把 cycle boundary 事件化。V2.2 用四 primitive
解决了 skill ownership 和 carry/dump contamination，是目前最稳定的主线。
V2.3 / V2.3.5 尝试参数化挖掘、长时程作业区规划和 effect-based atom，但一次
引入了太多语义变化，导致 dump/return 等 V2.2 已学会的能力退化，因此当前回退
到 V2.2，把有价值思想作为下一轮重启材料保留。

## V1 Baseline - 单铲业务基线

### 目的

- 建立最小可用业务闭环：teleop 录制、HDF5 数据、ACT 训练、live eval。
- 验证 Repo A 和 Unity/AGX 的 step-ack 协议、reset、action、observation、
  reward、success 规则是否能跑通。
- 得到一条可以反复比较的业务 baseline。

### 做过的尝试

- 使用 `teleop_v1.yaml` 录制当前固定工位、固定 truck 的单铲成功 demo。
- 训练 `act_agx_v1.yaml` baseline ACT。
- 建立 `eval_agx_v1.yaml` live eval。
- 追加 `fulltest(qpos)`、`fulltest(qpos+qvel)` 对照。
- 建立 dataset QC、rollout jsonl、summary、manifest、experiment record。
- 引入多种 success 口径，例如 `dump_complete_final_hold` 和
  `strict_dump_complete`。

### 获得的成果

- Python testbed 的基础链路完整跑通：
  - AGX step-ack client
  - `AGXSimBackend`
  - HDF5 schema
  - `tb-record-teleop`
  - `tb-train`
  - `tb-eval`
  - dataset video / QC
- 证明 ACT 能学到基本动作骨架：挖土、带土移动、尝试倒土。
- 建立了训练和评测管理框架：frozen split、resolved config、metadata、
  rollout logs。
- 发现图像分辨率过高会让 live teleop 发抖，固定了更合理的录制/评测分辨率。

### 不足和问题

- V1 本质上只解决单铲问题。它不要求模型完成稳定的多轮循环。
- 成功口径早期偏宽，达到 retained mass 后就可能停止，dump 后半段和稳定 hold
  记录不够完整。
- ACT 是一个 monolithic policy，整段动作都由一个模型负责，内部没有明确的
  skill 边界。
- dump 质量不稳定，模型会学到动作模式，但不一定理解倒土位置和释放时机。
- 行为克隆容易模仿人类纠偏动作的表象，例如反向拨杆减速，而不是学到真正的
  状态原因。
- 单铲成功不代表后续 cycle 的状态分布可靠。

### 留下的判断

V1 是必要的基础设施阶段，但不能作为完整作业能力的证明。它告诉我们：
接口和训练框架已经可用，后续真正困难在多轮闭环、状态分布漂移、任务边界和
skill ownership。

## V2.1 Stage 1 - 多轮 Raw 数据和事件化边界

### 目的

- 从单铲扩展到自然连续多铲。
- 放弃 fixed ready pose / ready-anchor，把 cycle 边界改成真实执行事件。
- 让数据、relabel、evaluation 都围绕 `qualified_dig_start` 和 `dump_end`
  对齐。

### 做过的尝试

- 新增 `teleop_v2_1_multi_raw.yaml`，录制自然连续 `3` 铲 raw episode。
- 使用 `tb-label-v2_1` 离线标注：
  - `qualified_dig_start`
  - `dump_end`
  - phase / mode / boundary labels
  - 10D `goal_tokens`
  - 后续细化的 `work_stage_id`
- 把 cycle 定义为：

```text
cycle_i.start = qualified_dig_start(i)
cycle_i.end   = qualified_dig_start(i + 1)
```

### 获得的成果

- 多轮任务开始有统一语义，不再依赖某个静态 ready pose。
- `transition_success` 可以定义为下一次 `qualified_dig_start` 是否被检测到。
- 为后续 workskill、transition、primitive builder 提供了共同边界。
- 形成了 goal-token 基础设施，为 planner intent 进入 ACT 打基础。

### 不足和问题

- `qualified_dig_start` 对齐的是可观测事件，不等于完全对齐人类状态分布。
  同样触发 QDS 的状态，bucket 速度、姿态、残余质量、土面形态可能不同。
- 多轮 raw 数据包含第二铲、第三铲，但这些是人类自己纠偏后的状态，不等于
  模型 rollout 会遇到的 off-nominal 状态。
- 10D goal token 只是 coarse sector-level intent，不是坐标级目标控制。
- 数据里有多轮，但覆盖不够系统，不能保证 later-cycle 泛化。

### 留下的判断

V2.1 Stage 1 的价值是把多轮任务事件化。它没有解决模型本身的闭环漂移，但让
后续每个失败都有了可记录、可切分、可比较的边界。

## V2.1 Stage 2 - Hybrid 闭环和 Scripted Transition

### 目的

- 不急着让 ACT 学完整多轮任务，先用规则 transition 把多轮闭环跑起来。
- 把 `dump_end -> next qualified_dig_start` 作为 transition。
- 让 planner 只负责 cycle-level intent，不直接管理 workskill 内部动作。

### 做过的尝试

- 使用 `hybrid_planner_act`：
  - `WORK = ACT V1`
  - `TRANSITION = scripted corridor servo`
- transition 子状态包括：
  - `clear_target`
  - `corridor_align`
  - `wait_next_dig`
- 固定或简单规划下一铲 sector。
- 在 rollout summary 中记录 transition timeout、completed transition count、
  boundary jump、cycle success 等指标。

### 获得的成果

- 多轮 hybrid live 闭环跑通。
- script transition 能把系统从 dump 后带回下一铲附近。
- transition 变成可测 handoff，而不是一段说不清楚的尾巴。
- 为 learned transition A/B 留出了接口。

### 不足和问题

- scripted transition 和人类 transition 的状态分布仍然不同。
- transition 能触发 `qualified_dig_start`，但不能保证交给 ACT 的 hidden state
  完全像训练数据。
- planner 想要的下一铲 sector 没有强约束 ACT，workskill 很多时候仍按常见动作
  分布模仿。
- 第二铲失败经常看起来像 dump 坏了，但漂移可能从第二铲 dig start 已经开始。

### 留下的判断

Stage 2 的价值不是“脚本化 transition 就是最终方案”，而是先把多轮系统拆成
可诊断的 work 和 transition。真正的主修复不是 learned transition，而是更清楚
的边界、handoff 和目标条件。

## V2.1 Stage 3 - Workskill 裁剪和训练

### 目的

- 从多轮 raw 或 V1 数据中裁出 `qualified_dig_start -> dump_end` 的 workskill。
- 让 ACT 只学一段完整工作技能，而不是从 reset 开始学全部过程。
- 验证 `qpos + qvel` 和 `goal_tokens` 对 workskill 的影响。

### 做过的尝试

- 使用 `tb-build-workskill-v2_1` 生成 sibling workskill 数据集。
- 训练：
  - `act_agx_v2_1_workskill_qvel.yaml`
  - `act_agx_v2_1_workskill_gcact.yaml`
  - 多轮 raw workskill clean v2/v3/v4 变体
- 增加 clean-profile，过滤明显差数据：
  - collision
  - low carry efficiency
  - high residual bucket mass
  - far dump start
  - near dump start
  - pause-heavy samples
- 引入 target-safety 相关过滤和 live guard。

### 获得的成果

- 建立了 workskill sibling dataset 构建链。
- 明确 V1 source 数据只读，relabel 和 crop 都写兄弟目录。
- qvel workskill 可以接回 live smoke。
- 数据质量过滤开始有体系，不再把所有 human raw 都直接当训练数据。

### 不足和问题

- workskill 仍然是 monolithic：`dig -> carry -> dump` 一口气完成。
- 一旦 early dig 或 carry 略偏，误差会一直积累到 dump。
- 视觉上像是 dump 失败，但真正根因可能在更早的 bite、load、carry 姿态。
- goal token 对 workskill 的约束仍然不够硬，planner intent 没有变成可靠动作。
- 严格过滤会减少数据量，过滤太松又会让坏习惯进入 BC。

### 留下的判断

Workskill 是比 V1 更干净的训练对象，但还是太长。要继续定位问题，必须把
`dig/carry/dump/return` 的 ownership 拆开。

## V2.1 Stage 4 - Rule Planner 和 Coarse Replan

### 目的

- 让 planner 管 cycle-level 目标、belief 和 trace。
- 不把低层 motion 都交给 planner，只让它决定下一铲 intent 和高层切换。
- 验证多轮 `left/right/mid` sequence 能否在现有 ACT 上执行。

### 做过的尝试

- 接入 `RuleTaskPlanner / PlannerGoal / CycleSummary / SectorBelief`。
- 记录 `planner_trace.json`。
- 固定或规划 sector sequence，例如 `left -> right`。
- 添加 soft corridor 和 `servo_reentry_pose`。
- 跑 2-cycle 主评测和 3-cycle smoke。

### 获得的成果

- 规则 planner 进入 live eval。
- 3-cycle smoke 一度跑通，说明边界和 transition 控制可以支撑多轮原型。
- `planner_trace` 让高层计划和低层实际结果可以分开分析。

### 不足和问题

- planner 只能提出 intent，不能保证 ACT 真正挖到目标 sector。
- 当前低层 primitive/workskill 如果没有接收有效 goal conditioning，实际 QDS 和
  实际挖掘位置仍可能由模型自然分布决定。
- 成功率可能掩盖目标未按计划执行的问题。

### 留下的判断

planner 必须和 policy 的目标输入、边界检测、实际效果日志同时工作。只加高层
planner，不让低层模型可靠接收目标，不能解决“想挖哪里”和“实际挖哪里”的差距。

## V2.1 Stage 5 - Learned Transition 尝试

### 目的

- 验证 `dump_end -> next qualified_dig_start` 是否可以由 ACT 学习。
- 与 scripted transition 做公平 A/B。
- 建立 fallback，而不是一次性替换稳定脚本。

### 做过的尝试

- 构建 transition dataset：
  - raw transition
  - clean-by-length transition
  - clean v2 transition
- 训练 transition ACT。
- 接入 learned transition compare。
- 加 fallback：learned transition 超时或无进展时切回 scripted wait-next-dig。

### 获得的成果

- learned transition 数据和训练链路跑通。
- transition 片段的长度、timeout、fallback 行为可以被量化。
- 确认 learned transition 是候选路线，而不是解决 V2.1 多轮失败的主因。

### 不足和问题

- learned transition 没有从根本上解决 workskill 内部漂移。
- 自然 transition 数据分布很散，单纯 imitation 不一定比 scripted 更稳。
- 在 workskill 目标条件和 ownership 不清楚前，替换 transition 收益有限。

### 留下的判断

不要把 learned transition 当成救命药。它只有在 work、boundary、目标条件都稳定后，
才值得升级为默认部署路径。

## V2.2 - 四 Primitive Ownership

### 目的

- 把 monolithic workskill 拆开，找出到底哪一段在污染哪一段。
- 防止 `carry` 学到 `dump` 的 release，防止 `return` 提前接管 dump 尾部。
- 让每个 primitive 的训练窗口、planner handoff 和 rollout 日志对齐。

### 做过的尝试

- 构建四个 sibling primitive dataset：
  - `dig`
  - `carry`
  - `dump`
  - `return`
- 分别训练四个 ACT checkpoint。
- 实现 `PrimitivePlannerACTPolicy`。
- 使用 Unity target geometry 只做切换、QC 和日志，不作为低层 policy privileged
  input。
- 清理 carry tail，避免 `carry` chunk 覆盖 dump/curl-out 动作。
- 给 dump 后增加 post-dump hold，避免 return 把刚倒出的土带出来。

### 获得的成果

- V2.2 3-cycle smoke 达到成功：
  - `cycle1/2/3_success_rate = 1.0`
  - `completed_transition_count = 2`
  - `transition_timeout_count = 0`
- 明确当前最可信 ownership：

```text
dig    = bite / dig / load
carry  = loaded transport with bucket closed
dump   = approach + align + release + post-dump hold
return = empty bucket return
```

- 发现并修正 `dig -> carry` gate：离开 dig area 是 carry 的工作，不应要求 dig
  自己先离开。
- 发现并修正 dump readiness：不能只靠 fixed swing 或单个 horizontal distance。
- 大幅改善 dump deposit fraction，尤其 carry trim + post-dump hold 后，dump 质量
  明显变好。

### 不足和问题

- V2.2 仍不是生产级。成功 smoke 中仍存在 spill、quality issue、target clearance
  等质量债。
- 数据量仍有限，特别是高质量 carry/dump windows。
- 四 primitive 解决了 ownership，但没有解决“下一铲挖哪里”的参数化问题。
- `dig` 和 `return` 如果不接收有效目标，长 rollout 的 sector sequence 仍不可靠。
- V2.2 还是固定 truck / 固定任务区域，不能直接覆盖未来变动 dump area 或完整清空
  作业区的目标。

### 留下的判断

V2.2 是当前应该保留的稳定主线。它告诉我们：四 primitive 是有价值的，但 dump
应该保持混合 primitive，不要强拆成不自然的 release-only skill。

## V2.2 Diagnostic - 5P Approach/Release Split

### 目的

- 进一步确认 dump 是否需要拆成 `approach_dump` 和 `dump_release`。
- 试图让 release timing 更清楚。

### 做过的尝试

- 构建 5 primitive：
  - `dig`
  - `carry`
  - `approach_dump`
  - `dump_release`
  - `return`
- 给 approach 和 release 分别找边界。
- 检查人类 teleop 中是否有稳定自然的内部 dump boundary。

### 获得的成果

- 得到一个很重要的负结果：专业操作里的 dump 本来就是混合动作。
- 人类会同时 swing、boom、stick、bucket open，不会自然停在一个干净的
  `approach -> release` 离散边界。

### 不足和问题

- 5P 数据窗口少，干净 boundary 难找。
- 过度拆分让 BC 学到更碎、更不自然的动作责任。
- 它会破坏 V2.2 已经有效的 mixed dump 定义。

### 留下的判断

5P 可以作为诊断历史保留，但不应作为主线。当前固定 truck 任务中，
`dump = approach + alignment + release + post-dump hold` 是更好的定义。

## V2.3 - Parameterized Dig 和 Square Planner

### 目的

- 从“重复固定 bite”推进到“按作业区 cell/depth 挖”。
- 支持未来把 DigArea 挖空，而不是只完成固定 3 铲。
- 让 planner 根据 surface-depth 和 cell coverage 选择下一铲。

### 做过的尝试

- 增加 3x2 DigArea surface-depth fields。
- 建立 `paramdig_tokens`，表达目标 cell、depth、surface、bucket-to-target 信息。
- 增加 single-scoop 和 natural-scoops 数据录制入口。
- 实现 `SquareExcavationPlanner`：
  - coverage-first cell selection
  - surface removed / remaining depth
  - visit count
  - exhausted / blocked / low-productivity
- 尝试 V2.3 carry/dump/return 数据构建和重新训练。
- 尝试 no-token 4P、V2.2 dump checkpoint rollback A/B、dump open boost 等诊断。

### 获得的成果

- 证明 paramdig 是未来完整任务必须面对的问题。
- 建立了 DigArea grid、surface probe 和 cell-level planner 日志。
- 发现 planner 必须记录 target-centric 结果：
  - planner 选的 cell
  - bucket 实际 QDS cell
  - 实际 removed peak cell
  - target deposit fraction
- 发现简单 planner rebind 会掩盖失败。

### 不足和问题

- V2.3 一次引入太多变化：paramdig、carry/dump/return rebuild、5P、truck-token、
  planner、new metrics 同时变化，归因变困难。
- dump 和 return 反而比 V2.2 退化。表现包括：
  - dump 太慢
  - bucket opening 不够
  - return 不稳定
  - second-cycle carry/return 会 swing 过头或不停
- truck-token 对当前固定 truck 任务没有必要，增加了输入复杂度。
- paramdig 的影响理论上不应传到 dump，但因为训练/数据/边界一起变了，实际系统
  发生了能力遗忘。
- square planner 可以选目标，但低层不一定到达目标。长 rollout 中会反复挖同一两个
  cell，其他 cell 几乎不动。

### 留下的判断

paramdig 的方向是必要的，但引入方式太早、太重。下一次重启时应从 V2.2 出发，
只先参数化 `dig`，保护 V2.2 的 `carry/dump/return` 不变，等 A/B 证明 handoff
分布真的变了，再动其他 primitive。

## V2.3 Hard Chunk Barrier

### 目的

- 解决 ACT action chunking 跨 primitive 的老问题。
- 防止一个 primitive 的训练 chunk 监督到下一个 primitive 的动作。

### 做过的尝试

- 定义 `/v2/step/action_chunk_barrier`。
- 把 `qualified_dig_start` 作为 hard `return -> dig` boundary。
- 对 mixed/full-session 数据要求 barrier，cropped primitive dataset 则优先使用
  half-open slicing 和 episode padding。

### 获得的成果

- 明确了 action chunk supervision 不应跨 ownership boundary。
- 这个思想可以保留到未来所有自然 full-cycle 数据切分中。

### 不足和问题

- barrier 只能阻止错误监督，不能弥补目标覆盖不足或低层 policy 没学到目标条件。
- 如果 primitive boundary 本身定义错了，barrier 只会更坚定地学习错误切法。

### 留下的判断

Hard chunk barrier 是应保留的正确机制，但它必须建立在正确的 primitive ownership
和足够的数据覆盖上。

## V2.3.5 - Payload Atom 和 Effect-Based Boundary

### 目的

- 不再完全按人为阶段切动作，而是按 payload 生命周期切自然混合动作。
- 尝试让 primitive boundary 更泛化，不依赖 truck 或固定几何。
- 避免把专业司机的混合 dump 硬切成不自然子技能。

### 做过的尝试

- 定义三个 atom：

```text
acquire_payload:   qualified_dig_start -> stable payload acquired
deliver_payload:   stable payload acquired -> stable payload released
return_to_source:  stable payload released -> next qualified_dig_start
```

- 使用 `qualified_dig_start` 作为 E0/E3 anchor。
- 使用 payload mass stability 检测 acquired/released。
- 尝试 return target 语义：
  - next actual bite
  - QDS endpoint
  - QDS cell center
- 尝试现有数据 augmentation。
- 尝试 anti-dig recovery、swing servo、planner rebind/block A/B。

### 获得的成果

- 证明 effect-based boundary 概念上有价值，尤其适合自然混合动作。
- 明确 `return` 不应该预测穿过下一段 `dig`，return target 应该对齐下一次
  `qualified_dig_start`，而不是下一次 actual bite。
- 发现 planner rebind 可以让系统看起来继续运行，但它会把“目标失败”变成“接受偶然
  QDS cell”，不应算真成功。
- 当前数据 augmentation 路径已经基本试完，不能再轻易归因到“小修 planner”。

### 不足和问题

- return-to-source 数据太少，部分 cell 覆盖很弱。
- 即使把 return windows 从约 25 条扩到约 50 条，live 仍在第二轮 transition 失败。
- anti-dig recovery 能减少卡住时继续装土，但不能让 policy 到达选定目标。
- swing servo 能修一个轴，但不能产生合格的 QDS 姿态。
- payload atom 主线会让当前系统进一步偏离 V2.2 稳定能力。

### 留下的判断

Payload atom 是值得保留的研究方向，但不适合现在作为主线。它需要更系统的自然
full-cycle 数据和更强的 target-conditioned return 覆盖，否则会把当前任务推到
数据不足的区域。

## 当前总体结论

### 应该保留

- V2.2 四 primitive ownership：
  - `dig`
  - `carry`
  - `dump`
  - `return`
- mixed dump 定义：

```text
dump = approach + alignment + release + post-dump hold
```

- `qualified_dig_start` 作为 hard `return -> dig` boundary。
- Hard chunk barrier。
- Target-centric diagnostics：
  - selected target
  - actual QDS cell
  - actual removal cell
  - deposited fraction
  - off-target dump debt
- 自然 full-cycle 数据是未来最理想的数据源，但必须能被可靠切分。

### 暂缓或不保留为主线

- 当前固定 truck 任务下的 truck-token。
- 默认 5P split。
- payload atom mainline。
- 用 planner rebind 当成功。
- 用薄弱 return 数据训练 target-conditioned return。
- 在没有 A/B 保护的情况下同时改 dig、carry、dump、return、planner 和 success 规则。

## 推荐下一轮路线

1. 从 V2.2 四 primitive 稳线重新开始。
2. 保持 V2.2 `carry/dump/return` checkpoint 和 handoff 规则不变。
3. 只先重启 `dig` 参数化，验证 paramdig 是否能在不破坏 dump/return 的情况下提升
   作业区覆盖。
4. 评估时必须区分：
   - planner 选了哪里
   - policy 实际到了哪里
   - 土实际从哪里移除
   - 土实际倒进哪里
5. 如果未来要录新数据，优先录自然 full-cycle 专业操作，然后按 V2.2 ownership 和
   hard chunk barrier 切分。
6. 如果未来 dump target 变成可变区域，再给 `dump` 增加 dump-target token；在当前
   固定 truck 任务里不要提前加入 truck-token。

