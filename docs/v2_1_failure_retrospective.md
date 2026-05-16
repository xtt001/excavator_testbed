# V2.1 多轮失败复盘

日期：2026-04-29

本文记录当前对 V2.1 初期多轮失败的理解：为什么最开始第二铲表现差，哪些原因是真正根因，哪些是后来诊断阶段才发现的问题，以及我们到底是靠什么把系统推进到现在的 V2.2 状态。

## 原始设计

V2.1 最初的思路很清楚：

```text
planner 决定下一铲 coarse dig start / sector
scripted transition 从 dump_end 走到 next qualified_dig_start
ACT workskill 执行 qualified_dig_start -> dump_end
重复下一铲
```

当时只有两个主要执行段：

- `workskill`：一个 ACT policy 学完整的 `dig-carry-dump`。
- `transition`：脚本控制器从 `dump_end` 回到下一铲开始。

当时的 planner 是 cycle boundary 上的高层组件，主要决定下一铲的大致 sector / dig-start 意图。它不是用来管理 monolithic workskill 内部 dump 阶段的。

## 关键澄清

最初 cycle2 失败发生在 4 primitives 拆分之前，所以不能把原始失败解释成 `carry -> dump` 这种低层 planner 切换问题。

4 primitives 是后来的诊断和修复工具。它帮助我们看清 monolithic workskill 内部哪里在漂移，但它不是原始失败的原因。

## 原始系统为什么失败

### 1. Planner 的目标没有强约束 ACT

V2.1 计划里已经预留了 `/v2/step/goal_tokens`，但最早 live 主线里 goal conditioning 不是硬验收条件。实际运行时，workskill policy 很多时候仍然像一个主要看 `qpos/qvel` 的 imitation policy，而 planner 想要的下一铲 sector 没有强力进入 ACT 的动作决策。

也就是说，系统层面可以决定：

```text
下一铲应该挖 left
```

但 ACT workskill 不一定收到足够明确的输入：

```text
这一次 workskill 要执行 left dig
```

所以 policy 更像是在当前状态附近模仿数据分布里最常见的人类动作，而不是被 planner 的目标可靠驱动。

### 2. `qualified_dig_start` 对齐了语义，但没有完全对齐状态分布

V2.1 正确地放弃了固定 ready pose，改成：

```text
transition 结束 = next qualified_dig_start
workskill 开始 = qualified_dig_start
```

这比静态 ready anchor 强很多，因为 `qualified_dig_start` 要求 bucket 接近 dig area、进入 dig plane，并且出现 good-dig / load-progress / mass increase 之类信号。

但它不能保证所有隐藏状态都和 human teleop 一样：

- bucket 速度可能不同；
- boom / stick / bucket 姿态组合可能略有差异；
- bucket 里残余质量可能不同；
- 土面已经被前一铲改变；
- scripted transition 的节奏和人类 transition 不同。

所以 scripted transition 和 human teleop 都可能触发 `qualified_dig_start`，但它们交给 ACT 的起始状态分布仍然不同。

### 3. ACT / Behavior Cloning 的闭环泛化能力弱

这是典型的 covariate shift。训练数据里是人类状态，rollout 里是模型和脚本共同产生的状态。第二铲开始时只要有一点偏差，policy 就可能进入训练数据里不常见的状态。

然后误差会一路放大：

```text
第二铲 dig start 略偏
-> bite 姿态略偏
-> bucket mass / velocity 不同
-> carry 姿态漂移
-> dump 在错误的 truck-relative 位置发生
```

这就是为什么一点点 dig start random 差异就可能毁掉整个 `dig-carry-dump` action chain。

### 4. 数据里有 cycle2，但没有足够鲁棒覆盖

3-dump demonstration 当然包含第二铲。问题不是“没有 cycle2 数据”。

真正的问题是数据没有覆盖足够多的变体：

- 模型 rollout 自己产生的 post-transition 状态；
- left / mid / right 起点扰动；
- later-cycle 的土面形态；
- 不同 bucket 速度和残余质量；
- 第一铲稍微不完美之后的 off-nominal 第二铲状态。

人类数据里的 cycle2 是人类自己纠偏后的 cycle2，不等于模型经过 scripted transition 后会遇到的 cycle2。

### 5. Monolithic workskill 没有中间纠偏点

原始 ACT workskill 一口气执行：

```text
qualified_dig_start -> dump_end
```

当起点在分布内时，它会显得很流畅；但一旦早期略偏，误差会一直累积到 dump 阶段。

所以视觉上经常像是“第二铲 dump 坏了”，但真正的漂移可能从第二铲 dig start 就已经开始。

## 我们是靠 learned transition 解决 gap 的吗？

不是。至少它不是主解法。

Stage 5 确实建立过 learned transition 线：

```text
dump_end -> next qualified_dig_start
```

也构建过 clean transition dataset，训练过 transition ACT candidate，并加了 scripted fallback / compare 配置。但 learned transition 当时主要是候选路线和诊断线，不是最终解决 cycle2 问题的主修复。

真正有效的修复不是“用 learned transition 替代 scripted transition 来模仿人类”，而是：

- 让 transition / work 边界事件化、可测量；
- 稳定 scripted handoff；
- 在有用的地方把 planner goal 显式给到 ACT；
- 清理训练分布；
- 后来用 primitive ownership 拆开诊断和修复 cross-skill contamination。

## V2.1 实际解决了什么

### 1. 事件化 cycle boundary

V2.1 把 cycle boundary 定义为：

```text
cycle_i.start = qualified_dig_start(i)
cycle_i.end   = qualified_dig_start(i + 1)
```

这样 transition success 可以被定义为：

```text
transition_success = next qualified_dig_start detected
```

这没有完全解决 distribution shift，但它给 recording、labeling、evaluation 和 online switching 一个共同的语义边界。

### 2. Scripted transition 变成可控 handoff

scripted transition 被组织成：

```text
clear_target -> corridor_align -> wait_next_dig
```

这减少了 dump 后的明显不连续，也让 transition log 可以跨 rollout 对比。它还为后来的 learned transition compare 留出了接口，但没有把 learned transition 作为默认主解法。

### 3. 加入 goal token 基础设施

V2.1 加了 10D `goal_tokens` 接口，用来表达当前 / 下一铲的 coarse intent：

```text
current sector one-hot
current depth
next sector one-hot
next depth
dump target
lookahead flag
```

这是 goal-conditioned ACT 的第一步，但只是 sector-level conditioning，不是最终想要的 coordinate-level goal-conditioned policy。

## V2.2 进一步做了什么

### 1. 用 four primitives 做诊断和 ownership 修复

V2.2 后来回到四个 primitive：

```text
dig -> carry -> dump -> return
```

这不是原始失败原因，而是为了让 ownership 可见：

- `dig`：挖土和装料；
- `carry`：满斗运输，不 release；
- `dump`：接近目标、对齐、release、post-dump hold；
- `return`：空斗回到下一铲。

这样我们能分清失败来自 loading、transport、target approach、release 还是 return。

### 2. 清理 carry / dump ownership

人类 teleop 会自然混合 swing、alignment 和 curl-out。对人来说这是流畅操作，但对 ACT 来说可能会让前一个 skill 学到后一个 skill 的工作。

V2.2 重新固定了 ownership：

```text
carry = loaded transport only
dump  = approach + align + release + post-dump hold
```

关键规则是：ACT 的训练 chunk 不应该跨越 skill ownership 边界，导致 earlier skill 学到 later skill 的 release action。

### 3. 修正 target geometry

`outside` 这种无方向距离只能说明 bucket 离 dump-area footprint 多近，不能说明 bucket 在 tail、middle 还是 front。

V2.2 改成使用 signed dump-area-relative geometry：

```text
bucket_dump_area_relative_x_m
bucket_dump_area_relative_z_m
bucket_dump_area_footprint_outside_distance_m
```

这样 planner 不会再把“靠近dump area尾部”和“在dump area中部上方”当成同一件事。

### 4. 用 post-dump hold 减少边界 spill

ACT 有 chunk prediction 和 temporal aggregation。dump 完马上切 return，可能把刚落进dump area的土又带出来。

所以当前 smoke 路线在 dump 完成后保留短暂 hold，再切 return。这是一个实际有效的边界修复，不依赖 learned transition。

### 5. 用 `goal_sequence -> goal_tokens` 改善 sector intent

长 rollout 里可以给出：

```text
mid -> left -> right -> left -> right
```

runtime 会把它转成 10D `goal_tokens`，注入给训练时包含 goal tokens 的 primitive。典型用法是：

```text
dig    uses qpos + qvel + goal_tokens
return uses qpos + qvel + goal_tokens
carry  uses qpos + qvel
dump   uses qpos + qvel
```

这改善了 coarse sector 控制，但还不足以支持任意 “dig from point A to point B”。

## 我们如何改善泛化能力

当前泛化能力的提升是部分的、工程驱动的：

- 加 `qvel`，让 ACT 看到动态状态，不只看姿态；
- 加 `goal_tokens`，让 ACT 收到 coarse planner intent；
- 用 `qualified_dig_start`，让 transition / work 使用同一个事件边界；
- 稳定 scripted transition 和 post-dump handoff；
- 清理低质量或 ownership 含糊的训练窗口；
- 加 per-cycle metrics，避免 aggregate success 掩盖 cycle2 失败；
- 用 target-relative signed geometry 做 dump handoff；
- 在有帮助时使用视觉 mask / focused input。

这提升了鲁棒性，但没有完全解决任意 dig-start random。

## 仍未解决的问题

当前 V2.2 仍然主要是 sector-conditioned。它可以表达：

```text
dig left / mid / right
```

但还不能稳定表达：

```text
从 3D 点 A 挖到 3D 点 B，目标深度 d
```

所以下一步长期方向应该是 V2.3：

- 使用 3D / LiDAR-derived local environment representation；
- 使用 coordinate-level dig goals；
- 用 synthetic keyframe generator 生成更平滑、覆盖更广的轨迹；
- 再用 human teleop fine-tune 操作质感；
- 训练真正能适应 start variation 的 goal-conditioned dig / carry policy。

## 一句话结论

原始失败不是后来的 4-primitive planner 导致的，而是 planner、transition 和 ACT 之间的接口太弱：

```text
planner goal 没有强力进入 ACT
scripted transition 和 human transition 的状态分布不完全一致
ACT 对 dig-start 小扰动非常敏感
monolithic workskill 会把早期误差积累到 dump
数据里有 cycle2，但缺少模型自己产生的 cycle2 变体覆盖
```

我们不是主要靠 learned transition 解决它的。我们靠的是：事件化边界、稳定 scripted handoff、goal-token conditioning、数据/label 清理，以及后来用 four-primitive ownership 暴露并减少 cross-skill contamination。
