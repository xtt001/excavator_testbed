# LLM Planner 前的闭环地形规划结论

本文记录当前关于 LLM planner、ACT 低层执行、多铲挖掘跟手性和地形闭环规划的阶段性结论。核心判断是：下一阶段不应直接接入 LLM planner，而应先验证 ACT 是否能作为可预测的粗执行器，并把主规划目标从“单铲 token 严格跟手”升级为“目标地形残差闭环收敛”。

本结论的执行版开发计划见
[`docs/oracle_terrain_residual_planner_v0_plan.md`](oracle_terrain_residual_planner_v0_plan.md)。

## 1. 当前技术方案

当前系统的主体流程是：

```text
高层 planner / FSM
-> 选择下一铲目标 token，例如 entry / exit / depth / payload
-> ACT 执行具体动作
-> 根据 gate 判断 dig / carry / dump / return 切换
```

当前方案并不是等 return 完成后才决定下一铲。为了保持连续丝滑，return 阶段会提前生成 `return_target`，并缓存下一铲的 `pending_dig_cut_*`。因此当前节奏更接近：

```text
上一铲 dig 完成
-> carry / dump / return
-> return 过程中提前决定下一铲回到哪里
-> 到位后直接 handoff 到 pre_dig_align 或 dig
```

当前方案的优点是：

- 多铲流程可以跑通。
- 挖、转、倒、回之间能保持较连续的节奏。
- planner 已经有一定 coverage / corridor 选择能力。
- 部分模式下会使用 `env_state` 中的 removed depth / target depth / coverage belief 做粗粒度闭环。

但当前方案的本质仍然是：planner 给 ACT 一个目标，ACT 自己负责完成这一刀。planner 并没有完整掌握“当前目标地形和实际地形之间还差多少”，也没有显式建模“给定某个 cut target，ACT 大概率会挖掉哪里、挖多少、是否过挖”。

## 2. 当前遇到的问题

当前主要问题不是“能不能跑 10 铲”，而是：

```text
跑通 != 严格跟手 != 能挖出指定形状
```

已经暴露的问题可以分为几类：

| 问题 | 通俗解释 |
| --- | --- |
| entry / exit / depth 不稳定 | planner 给了目标，但 ACT 实际挖的位置和深度不一定跟得上 |
| depth / payload / 执行效果不可分离 | token 同时带深度、路径和 payload intent，但 live 地形变化和 ACT 执行效果不受单独几何目标约束，payload 成功不能证明形状正确 |
| 土体状态变化导致分布外 | 第 N 铲的土体已经不是专家训练时的状态，ACT 需要在新土体条件下泛化 |
| coverage 闭环偏粗 | 当前有 removed depth / coverage belief，但还不是明确的目标坑形残差闭环 |
| success 指标太粗 | 10 铲完成、`success=1.0` 不能证明每铲形状、深度、位置都正确 |

### 2.1 当前“跟手”审查口径

这里的“跟手”不能理解成一个单一指标。当前 rollout review 能稳定审查的是三层问题：

| 层级 | 当前要求 | 当前 planned-vs-actual 是否完整 |
| --- | --- | --- |
| dig cut 跟手 | ACT 是否按 planner 给出的 entry / exit / depth / payload 执行这一铲 | 相对完整 |
| return handoff 跟手 | return 是否把机器带回下一铲 entry 附近，能否交接给 dig | 有 handoff readiness 指标 |
| carry / dump 运输质量 | 挖出来的料是否带住、是否有效倒出、是否残留或漏料 | 目前主要是质量指标，不是完整几何目标跟手 |

因此，当前 audit 不能解读成完整任务级“指哪挖哪”审查。它更准确地说是：

```text
dig cut target 跟手
+ return->dig handoff readiness
+ carry / dump transport quality
```

如果未来 planner 给出明确的 carry / dump 目标，例如 dump pose、deposit footprint、允许残留 bucket mass、指定卸料区域等，carry / dump 也应该升级成 planned-vs-actual 审查。目前还没有这一级目标，所以 deposit fraction 只能说明运输和倒料质量，不能证明 dump 几何跟手。

### 2.2 当前 10 铲 rollout 的修正后审查结论

以当前主 run 为例：

```text
runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results
```

在修正两个审查口径后，结论发生了变化：

- depth 跟手结论使用 `rollout_review.json` 中的
  `depth_tracking.dig_local_surface`：从 per-rollout jsonl 的连续 `dig`
  段读取 `env_state[31] bucket_depth_below_local_surface_m` 峰值，目标值来自
  `dig_cut_tokens[7] * 0.8`。`planned_actual_cycles.depth_peak_m` 仍是历史
  summary plane-depth 诊断字段，不作为 command-depth 跟手结论。
- return handoff 过滤 episode 末端残留 return 段，不再把 terminal 状态污染进 handoff 统计。

修正后的总览是：

```text
return handoff 已合格；
dig entry / exit 明显不跟手；
depth 没有之前 plane-depth 口径看起来那么糟，但仍有真实过深铲；
payload 平均接近目标；
carry / dump 的 deposit fraction 波动较大。
```

| 指标 | 当前结果 | 判断 | 解释 |
| --- | ---: | --- | --- |
| dig entry 误差 | 平均 20.4cm，最大 41.3cm | 不跟手 | 入铲点离目标偏大；55cm handoff 阈值只是能交接，不代表形状精确 |
| dig exit 误差 | 平均 39.2cm，最大 55.6cm | 明显不跟手 | 出铲点是当前最严重的几何问题 |
| exit 纵向误差 | 平均 27.1cm，最大 52.6cm | 不跟手 | 很多铲提前或滞后出铲 |
| exit 横向误差 | 平均 21.7cm，最大 47.3cm | 不跟手 | 很多铲横向偏差也明显 |
| dig local-surface depth 误差 | 平均 +3.4cm，最大 +20.3cm | 局部不跟手 | 来自 `depth_tracking.dig_local_surface`；第 7、10 铲真实过深 |
| summary plane-depth 诊断 | 平均 +15.7cm，最大 +25.9cm | 仅诊断 | 来自旧 `cycleN_depth_peak_m - cycleN_depth_target_m`，窗口和深度参考不同，不能和 local-surface 跟手口径混用 |
| payload mass out | 目标均值 58.0kg，实际均值 61.3kg | 基本接近 | 平均装载量接近目标，不能证明形状正确 |
| deposited fraction | 平均 80.2%，最低 57.3% | 不稳定 | 料能挖出来，但运输和倒料质量波动大 |
| return->dig handoff | 0.339m <= 0.55m | 合格 | 过滤 terminal 污染后，return 能交接给下一铲 dig |
| coverage trace | 存在 | 有证据 | 有 coverage 证据，但 candidate ranking 仍需要继续 root-cause |

逐铲看更直观：

| Cycle | Entry err | Exit err | Dig depth over | Deposit fraction |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 3.5cm | 52.4cm | -14.1cm | 78% |
| 2 | 22.4cm | 15.6cm | +4.7cm | 62% |
| 3 | 39.7cm | 31.3cm | +4.2cm | 82% |
| 4 | 33.3cm | 18.9cm | -6.4cm | 85% |
| 5 | 41.3cm | 43.8cm | +12.9cm | 83% |
| 6 | 9.7cm | 38.6cm | -1.6cm | 80% |
| 7 | 18.3cm | 32.9cm | +19.0cm | 89% |
| 8 | 7.8cm | 55.6cm | -1.5cm | 97% |
| 9 | 13.7cm | 52.9cm | -4.0cm | 88% |
| 10 | 14.1cm | 49.6cm | +20.3cm | 57% |

这个结果说明：

```text
当前 rollout 能跑完多铲流程，
return 也能把系统带回下一铲附近，
但 ACT 对 planner cut target 的几何跟手仍然不够。
```

特别要注意，handoff 合格和 entry 精确不是一回事。handoff 阈值是为了判断“能不能进入下一铲”，通常会比较宽；而未来如果要挖指定形状，entry / exit 的绝对误差必须明显更小。因此当前结果不能证明系统已经具备稳定的“指哪挖哪”能力。

我们认可的关键判断是：

```text
要求 ACT 在多铲动态土体里严格跟手，
本质上是在要求它对自己造成的土体变化后的状态继续泛化。
```

这对纯 BC / ACT 是很高要求。ACT 训练时学到的是专家分布下的动作映射；推理时，多铲挖掘会持续改变土体，使后续观测逐渐偏离专家数据分布。因此，不应该把全部闭环控制责任都压给 ACT。

## 3. 下一步计划与最终可以达到的目标

下一步更合理的架构方向是地形闭环：

```text
语义任务
-> 目标地形 / 目标坑形
-> 当前地形观测或地形 belief
-> 形状残差：哪里没挖够，哪里已经挖过
-> 下一铲 cut plan
-> ACT 粗执行
-> 观测或估计实际地形变化
-> 更新残差并继续规划
```

在这个架构里，ACT 的定位需要变化：

```text
从“严格执行给定 entry / exit / depth”
变成“在指定区域产生大致可预测的挖掘效果”
```

最终目标仍然可以是语义级挖掘任务，例如：

```text
挖一个指定形状 / 指定用途 / 指定约束的坑，
机器在可行范围内自由选择路径完成。
```

但“自由选择路径”的主体应该是地形残差 planner，而不是 ACT 自由发挥。LLM 更适合放在最上层，把自然语言任务转成目标几何、约束和验收标准；不应让 LLM 直接控制低层动作。

闭环规划也不意味着破坏连续丝滑。正确实现方式应是流水线：

```text
dig 期间记录实际效果
carry / dump 期间更新地形 belief
return 期间提前规划下一铲
handoff 前锁定目标
必要时只做小范围修正
```

因此，未来目标不是“每铲结束后停下来重新想”，而是“边执行、边估计、边准备下一铲”。这和当前提前生成 return target / pending dig cut 的方向是一致的，只是未来需要把当前较粗的 coverage/corridor 选择升级成显式地形残差规划。

### 3.1 当前地形如何获得

地形闭环的第一前提是系统能知道“当前坑是什么形状”。这里需要的是度量地形状态，而不是单纯给 ACT 更多 RGB 图像。

在仿真阶段，最便宜可靠的做法是直接使用现有 `env_state` / height grid / removed-depth grid：

```text
sim ground truth terrain
-> dig_area 坐标系下的 current height / removed depth / target depth
-> residual planner
```

真实机器上则必须补一个可用的地形感知方案，目标是得到：

```text
dig_area 坐标系下的 elevation / removed_depth / confidence map
```

可选传感器路线如下：

| 方案 | 作用 | 主要风险 |
| --- | --- | --- |
| 3D LiDAR / depth sensor / stereo | 直接重建 dig area elevation map | 灰尘、遮挡、阳光、标定和同步 |
| 多 GMSL 相机 | 可做多视角感知，也可辅助重建 | 需要标定和深度估计，不能只当 RGB 输入 |
| 斗尖轨迹 + 接触 / 深度估计 | 可补充“斗经过哪里、可能挖到哪里” | 稀疏、间接，不能完整重建坑形 |
| 仿真 ground truth | 研发上层 residual planner 最快 | 到真实机器前还要迁移传感器链路 |

因此真实传感器优化的重点不是“让 ACT 看更多画面”，而是让上层 planner 拿到可量化的地形状态和不确定性。

### 3.2 实时残差如何计算

语义任务需要先落到目标地形。例如：

```text
挖一个 2m x 1m x 0.4m 的坑
-> target_depth_grid[x, z]
```

实时感知或仿真状态给出：

```text
current_removed_depth_grid[x, z]
confidence_grid[x, z]
```

残差定义为：

```text
residual[x, z] = target_depth_grid[x, z] - current_removed_depth_grid[x, z]
```

解释很直接：

| residual | 含义 |
| ---: | --- |
| `> 0` | 这里还没挖够 |
| `≈ 0` | 这里基本达到目标 |
| `< 0` | 这里已经超挖 |

真实系统必须同时维护 `confidence_grid`。如果某个区域被斗、扬尘、车体或视角遮挡，就不能把该区域的 residual 当成确定事实。后续 planner 应区分：

- confirmed terrain：观测可靠，可以直接用于规划。
- estimated terrain：由上一铲效果模型或斗尖轨迹估计，需要保守使用。
- uncertain terrain：不确定，不应贸然规划深切。

### 3.3 Effect Model 和 Capability Model

Residual planner 不能只知道“哪里还没挖够”，还需要知道“某个 cut 大概会造成什么效果”和“当前 ACT 是否能可靠执行这个 cut”。

因此至少需要两个配套模型：

```text
Effect model:
当前地形 + cut plan -> 预计 removed_depth_delta_grid / payload / uncertainty

Capability model:
当前 obs + 当前地形 + cut plan -> ACT/DP 执行成功概率 / 风险
```

这里的 effect model 就是类似 world/action model 的挖掘效果模型。它不需要一开始完美，可以分阶段做：

| 阶段 | 做法 | 作用 |
| --- | --- | --- |
| 几何近似模型 | 假设 bucket 沿 entry->exit 扫过一个带状区域，按宽度和目标深度移除土 | 最快跑通 residual planner |
| 经验统计模型 | 从 sim / rollout 数据统计某类 cut 通常移除多少土、获得多少 payload、失败概率多高 | 比手写 kernel 更贴近实际 |
| 学习型 effect / WAM | 输入 terrain patch、cut token、bucket pose，预测地形变化、payload 和不确定性 | 支撑更复杂地形和更精细评分 |

Capability model 的作用是约束上层不要给 ACT 任意目标。上层应只在 ACT/DP 的 reachable envelope 内选 cut。否则 residual planner 只是更聪明地给 token，底层仍然可能执行不出来。

### 3.4 如何根据残差选择下一铲 cut plan

Residual planner 规划的不是低层动作，而是下一铲预计改变哪块地形。一个 cut plan 至少应包含：

```python
CutPlan(
    entry_xz,
    exit_xz,
    target_surface_penetration,
    target_payload,
    expected_removed_depth_patch,
    confidence,
)
```

基本流程是：

```text
1. 找 residual 为正、置信度高、机器可达的区域
2. 围绕这些区域生成多个候选 cut
3. 用 effect model 预测每个 cut 的地形变化和 payload
4. 用 capability model 判断 ACT/DP 执行风险
5. 用 scoring function 选分数最高的 cut
6. 交给 ACT/DP 作为局部执行目标
7. 执行后重新观测地形并更新 residual
```

评分函数可以先从朴素版本开始：

```text
score(cut) =
  + 预计减少的正残差
  - 预计造成的超挖
  + 预计 payload 是否合理
  - ACT/DP 执行失败风险
  - entry / handoff / return 成本
  - 预测不确定性
```

这类评分不应由 LLM 直接“凭感觉”给出，而应基于可测量的地形残差、效果预测、执行能力和安全约束。

### 3.5 ACT、DP、MPC、LLM/VLM 的位置

在这个架构里，ACT 仍然是底层局部动作执行器，但不再承担“长期形状控制”的责任。更准确的要求是：

```text
给定当前 obs 和局部 cut intent，
ACT 执行后在统计上应朝减少 residual 的方向改变地形。
```

这比要求 ACT 厘米级跟随 entry / exit / depth 弱很多。如果 ACT 连“平均减少 residual”都做不到，就说明它不适合作为该任务的底层 executor，需要换更闭环的低层控制器，或者重新训练 terrain-conditioned / effect-aware policy。

DP 可能改善低层动作质量，因为它通常能生成更平滑、更可重采样的动作轨迹。但 DP 本身仍然不是地形 residual planner。除非 DP 的输入和训练目标显式包含 terrain residual 和地形变化，否则它只是更强的 imitation executor，而不是“指哪挖哪”的上层规划器。

MPC 的优势是显式使用模型预测未来状态，但完整土体物理 MPC 成本很高。更现实的路线是先做：

```text
高层 residual cut planner
-> effect / capability model
-> ACT/DP 或简单 feedback controller 执行局部 cut
```

LLM/VLM 更适合做语义层和辅助判断：

| 适合 LLM/VLM | 不适合 LLM/VLM |
| --- | --- |
| 把自然语言任务转成目标坑形、约束和验收标准 | 厘米级 grid residual 数值优化 |
| 识别场景、障碍、dump 区和高层风险 | 直接决定 bucket entry / exit / depth |
| 解释失败原因、生成候选策略、做人机交互 | 替代 effect model / capability model |

因此未来 planner 可以使用 LLM/VLM，但核心闭环仍应是数值的：

```text
target terrain map + current terrain map
-> residual
-> candidate cut planning
-> effect / capability scoring
-> low-level execution
-> terrain re-observation
```

## 4. 开始计划前需要验证的东西

在正式进入地形闭环 planner 或 LLM planner 前，需要先验证以下问题。

### 4.1 ACT 是否能作为可预测的粗执行器

需要验证：

- 同类地形状态 + 同类 cut target 下，ACT 是否大概率在指定区域移除土。
- 浅切、深切、长切、短切是否能产生可区分的统计效果。
- ACT 是否存在明显不可达或高失败率的区域、姿态、深度组合。
- 给定目标时，entry / exit / depth / payload 的误差分布是否稳定。

如果 ACT 的执行效果完全不可预测，那么 residual planner 也无法稳定收敛。这时应优先升级低层控制、反馈控制或训练范式，而不是接 LLM。

### 4.2 当前地形状态是否可信

需要验证：

- `env_state` 中的 removed depth / target depth 是否真实反映坑形变化。
- removed-depth grid 的更新是否及时、稳定、无遮挡或错位。
- 当前 coverage belief 和真实地形残差之间是否一致。
- 是否能区分 confirmed terrain、estimated terrain 和 uncertain terrain。

如果地形观测本身不准，planner 根据残差做出的下一铲选择就是错的。

### 4.3 当前 return 提前规划机制是否能承接新 planner

当前机制已经能在 return 阶段提前生成 return target 和 pending dig cut。下一步需要确认：

- 未来 terrain residual planner 是否能接入当前 `pending_dig_cut_*` 机制。
- return 过程中是否可以使用最新地形 belief 更新候选，但在 handoff 前锁定目标。
- 目标锁定后是否能避免临门跳变，保持连续性。
- 如果 return 过程中发现原目标不可达，是否有清晰 fallback 策略。

这一步的目标是保留“丝滑”，而不是把系统改成停顿式重规划。

### 4.4 区分 planner 目标问题和 ACT 执行能力问题

后续 audit 需要继续区分：

- planner 给出的 entry / exit / depth 是否合理。
- ACT 实际是否跟随这些目标。
- 土体变化后是否应该重新规划目标。
- payload 不足是否导致继续深挖。
- 过挖是否发生，以及过挖是否不可逆。
- success=1.0 的 rollout 是否真的满足形状、位置、深度质量要求。

## 总结

当前路线已经能证明：

```text
多铲流程可以跑。
```

但它还不能证明：

```text
系统能按目标形状稳定挖。
```

下一阶段应该先验证 ACT 是否能作为可预测的粗执行器，然后把主规划能力从 token 跟手升级为地形残差闭环规划。如果这个验证通过，最终的语义挖坑目标是可达的；如果验证不通过，就需要优先升级低层控制、反馈控制或训练数据，而不是直接接入 LLM。
