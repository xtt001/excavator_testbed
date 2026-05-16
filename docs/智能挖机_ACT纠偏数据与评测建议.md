---
title: 智能挖机 ACT 纠偏数据与评测建议
created: 2026-05-13
tags:
  - excavator
  - act
  - imitation-learning
  - correction-data
  - evaluation
---

## 3. 加 recovery / correction 数据

当前完整连续任务训练容易失败的核心原因之一是：

> 数据主要覆盖了专家轨迹附近的一条细线，但 policy rollout 时会出现微小偏差；一旦偏离，数据里缺少“从偏离状态拉回正常流程”的样本。

因此，下一步不只是继续录更多完美完整 episode，而是要主动采集 recovery / correction 数据。

### 采集方式

让当前 policy 先在仿真中 rollout，当它出现轻微偏差或阶段衔接不稳时，由人工接管，把系统拉回正确流程，并记录这一段：

```text
policy 偏离状态
  -> human takeover
  -> expert correction
  -> 回到正常任务轨迹
```

这些片段可以单独保存，也可以作为完整 raw episode 的一部分保留，再通过离线 labeler 标出：

- 偏离发生时间。
- 偏离阶段。
- 人工接管开始时间。
- correction 结束时间。
- 回到哪个正常 phase / primitive。
- 是否成功恢复。

### 推荐记录的 correction 类型

```text
dig 偏离:
  入土点偏、入土角度不对、挖空、铲斗姿态过高或过低

carry 偏离:
  抬升不足、姿态不稳、提前撒料、回转路径不合理

dump 偏离:
  未到目标区提前释放、倒偏、倒不干净、dump 姿态不合理

return 偏离:
  没回到下一铲可开始位置、姿态不对、目标点偏移

handoff 偏离:
  dig -> carry 过早或过晚
  carry -> dump 过早或过晚
  dump -> return 判断错误
```

### 价值

recovery / correction 数据比重复录制大量完美 episode 更有价值，因为它让模型看到：

```text
偏离专家轨迹后，应该如何回到合理状态
```

这相当于温和版本的 DAgger 思路，不一定一开始实现完整 DAgger pipeline，但可以先做人工接管式 correction collection。

## 6. 对 ACT 的 action chunk 做实验

ACT 的 action chunk 长度会影响策略行为：

- chunk 太长：容易变成半开环动作播放，对实时偏差不敏感。
- chunk 太短：闭环频率更高，但动作可能不够平滑，训练也可能更难。

完整连续任务中，不同 primitive 对 chunk 长度的需求可能不同，不建议只用一个固定配置解释所有问题。

### 建议实验对象

比较以下几种训练方式：

```text
monolithic full-episode ACT:
  一个 ACT 直接学习完整连续任务

phase-conditioned ACT:
  一个 ACT，但输入 phase token / goal token / target token

separate primitive ACTs:
  dig_ACT / carry_ACT / dump_ACT / return_ACT 分开训练
```

### 建议按 primitive 调 chunk

```text
dig:
  可以尝试稍长 chunk，因为动作连续性强，局部动作结构明显

carry:
  使用中等 chunk，重点观察姿态稳定和是否提前撒料

dump:
  可以尝试较短 chunk，便于根据是否到达目标区、是否倒干净进行调整

return:
  使用中等 chunk，重点观察是否回到下一铲可开始状态
```

### 建议对比指标

每组 chunk 配置都记录：

- train / val action loss。
- rollout 是否完成。
- 每个 primitive 的成功率。
- handoff 是否稳定。
- 是否出现半开环动作播放。
- 是否对轻微偏差有纠正能力。
- 动作是否抖动或不连续。

### 实验结论应避免过宽

如果某个 chunk 配置在固定场景下跑通，只能说明：

```text
该配置适合当前固定任务和当前数据分布
```

不能直接说明它适合多场景、多初态或真机部署。

## 7. 评测按阶段拆

完整连续任务不能只看最终是否成功。最终成功率太粗，会掩盖真正的问题来源。

评测应该拆成阶段级指标：

```text
dig 是否成功
carry 是否稳定
dump 是否有效
return 是否到位
handoff 是否合理
recovery 是否触发正确
```

### 推荐阶段指标

#### dig 阶段

- 是否成功入土。
- 入土点是否合理。
- 入土角度是否合理。
- 是否挖空。
- dig_end 时铲斗姿态是否适合进入 carry。
- 单铲挖出量是否达到最低要求。

#### carry 阶段

- 是否提前撒料。
- bucket 姿态是否稳定。
- carry 轨迹是否过低或过高。
- 是否在到达目标区前丢失主要载荷。
- carry_end 时是否处于合理 dump 起点。

#### dump 阶段

- 是否到达目标区后再 dump。
- dump 是否倒偏。
- dump 是否倒干净。
- dump_complete 判断是否过早或过晚。
- 目标区有效沉积量是否达到要求。

#### return 阶段

- 是否回到下一铲可开始位置。
- return target 是否合理。
- 铲斗姿态是否适合下一次 dig。
- 是否残留错误姿态或不必要动作。

#### handoff / boundary

- dig -> carry 是否过早或过晚。
- carry -> dump 是否过早或过晚。
- dump -> return 是否过早或过晚。
- return -> next dig 是否满足下一铲启动条件。

### 推荐日志字段

每次 rollout 至少记录：

```text
episode_id
cycle_id
phase
primitive
phase_start_time
phase_end_time
handoff_reason
success_flag
quality_metrics
failure_stage
failure_reason
whether_recovered
```

### 评测目标

阶段化评测的目标不是让指标变复杂，而是让每次失败都能回答：

```text
是哪个阶段失败？
是 policy 动作没学好？
是 handoff 时机错误？
是 planner 目标选择错误？
是 observation / estimated state 不够？
是 action chunk 配置不合适？
还是数据里缺少 correction 样本？
```

只有这样，下一轮采数和训练才不会变成盲目增加 episode 数量。
