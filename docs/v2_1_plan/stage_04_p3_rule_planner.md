# Stage 04 — P3 Rule Planner and Belief Map

## Goal

让系统在 cycle boundary 根据上一轮执行 summary 选择下一铲的 coarse goal。

## Status

- State: `implemented_main_gate_passed_soft_corridor_reentry`
- Priority: `current`

## In Scope

- `PlannerGoal`
- `CycleSummary`
- `SectorBelief`
- `TerrainBeliefMap`
- `ScenarioManifest`
- `RuleTaskPlanner`

## Out of Scope

- learned planner
- `3x3 patch planner`
- world-pose protocol enhancement

## Main Deliverables

- planner goal schema
- cycle summary schema
- sector belief update
- rule planner 实现
- planner 决策回放工具
- Stage-4 live eval 配置
- `planner_trace.json` 回放产物

## Current Implementation

当前 Stage 4 第一版已经按“建立在 Stage 2 稳线之上”的口径接入，具体落地为：

- 新增 planner 类型与 manifest：
  - `testbed/planner/types.py`
  - `testbed/planner/scenario_manifest.py`
  - `testbed/planner/rule_planner.py`
- 继续复用现有 `hybrid_planner_act`，不新增新的 deploy policy class
- Stage 4 默认配置固定为：
  - `policy.class = hybrid_planner_act`
  - `planner.kind = rule`
  - `task.scenario_id = s0_truck`
  - `work_ckpt = ACT V1`
  - 不启用 Stage 3 bootstrap
  - 不启用在线 goal token 注入
- 新增评测入口：
  - `testbed/configs/eval_agx_v2_1_stage4_rule_planner.yaml`
  - `testbed/configs/eval_agx_v2_1_stage4_rule_planner_3cycle_smoke.yaml`
- 当前 replan 时机已经调整为：
  - 在 `dump_end` 关闭本轮 `CycleSummary`
  - 立即调用 `planner.replan_at_cycle_boundary(summary)`
  - 本次 transition 直接朝新 `next_goal.next_entry_corridor_id` 进入下一轮 corridor
- 当前 Stage 4 还补上了一个**只作用于 transition 的 re-entry assist**：
  - `wait_next_dig_mode = servo_reentry_pose`
  - `wait_next_dig_reentry_template_qpos = [0.50, 0.222, 0.526, 0.00015]`
  - Stage-4 的 `left / mid / right` corridor 也调整成了更接近 `mid` 的 soft band
  - 目的不是改变 planner 语义，而是在当前没有 world-pose sector 执行能力的前提下，让 coarse sector re-entry 先落到可达 corridor 上

当前 planner 只驱动：

- `next_goal`
- `next_entry_corridor`
- belief 更新
- rollout 级 planner 日志与回放

当前 planner **不** 直接改写 ACT 的 work 输入，也 **不** 回写 `/v2` 离线数据。

## Planner Scope

### Supported Granularity

planner 第一版只支持：

- sector: `left / mid / right`
- depth: `shallow / medium / deep`

### Planning Trigger

- 仅在 cycle boundary 调用 `replan_at_cycle_boundary()`
- 不做 step-level 高频 replan

### Plan Source

第一版 `plan_source` 固定为：

- `rule`

## Belief Plan

### Maintained State

- 当前 sector 级利用情况
- 上一轮 fill / deposit / collision summary
- 下一个推荐 sector / depth

### Not Included Yet

- patch 级 terrain map
- 学习式 uncertainty 建模
- world-pose 增强观测

## Policy Integration Plan

hybrid policy 需要从单目标升级为双目标：

- `current_goal`
- `next_goal`

以便在 work 与 transition 边界对齐 planner 输出。

当前已经实现到现有 wrapper 中：

- `reset()` 时：
  - `planner.reset(scenario_id)`
  - `current_goal = planner.bootstrap_first_goal()`
  - `next_goal = current_goal`
- `dump_end` 后：
  - transition 读取 `next_goal.next_entry_corridor_id`
- 下一轮 `qualified_dig_start` 后：
  - 关闭上一轮 `CycleSummary`
  - `current_goal = next_goal`
  - `next_goal = planner.replan_at_cycle_boundary(summary)`
- `current_goal / next_goal` 第一版只影响：
  - transition 目标
  - planner trace
  - rollout summary / manifest

当前 Stage 4 生成的 runtime 产物包括：

- step log 字段：
  - `planner_current_sector_id`
  - `planner_current_depth_class`
  - `planner_next_sector_id`
  - `planner_next_depth_class`
  - `planner_plan_source`
  - `planner_replan_mask`
- rollout summary 聚合字段：
  - `planner_replan_count`
  - `planner_sector_sequence`
  - `planner_blocked_sector_count`
  - `planner_done_sector_count`
- 每条 rollout 的：
  - `rollout_XXX_planner_trace.json`

## Bootstrap Boundary

Stage 3 为了让 bootstrap work-skill 能在 live 路径上先跑通，当前允许在 deploy wrapper 中保留一个临时 bootstrap handoff：

- `reset -> loaded_and_clear` 先由 `ACT V1` 负责
- `loaded_and_clear -> dump_end` 再切给 Stage-3 work policy

但 Stage 4 必须把这条逻辑明确当成 **deploy-only compatibility layer**，而不是新的系统主语义。具体约束固定为：

- planner 的 `PlannerGoal / CycleSummary / SectorBelief / replan_at_cycle_boundary()` 不得依赖 bootstrap 存在才能成立
- bootstrap 不得进入 `/v2` schema、协议、cycle 定义或 stage-state 语义
- bootstrap rollout 默认不得直接当作 Stage 4 正式 teacher 数据；若未来需要使用，必须单独标记来源并做显式对照
- Stage 4 的关键评测结果应尽量保留 bootstrap `on/off` 区分，避免把 deploy 兼容层收益误记成 planner 本体收益
- 一旦后续有正式 `teleop_v2_1_multi_raw` work/transition 数据和更强 work policy，bootstrap 应被视为优先尝试删除的兼容残件

因此，Stage 4 的推进原则是：

- 允许在当前 live 验证中继续使用 bootstrap 以保持已有可运行路径
- 但所有新增 planner 接口、训练数据口径和评测语义都必须假设 **bootstrap 可以被拿掉**

## Tests

- planner bootstrap 单测
- planner replan 单测
- `CycleSummary -> belief update` 单测
- planner 决策回放测试
- sector 切换行为回归检查
- `planner.kind = fixed_sequence` 的 Stage 2 回归测试
- `planner.kind = rule` 的 `_eval.py` 构造测试
- `dump_end -> transition corridor` 和 `qualified_dig_start -> replan` 的 wrapper 单测

当前已完成的自动化验证：

- `python -m unittest tests.test_agx_stage2_hybrid tests.test_agx_stage3_workskill tests.test_agx_stage4_rule_planner -q`
- `python -m unittest tests.test_agx_protocol tests.test_agx_repoa_integration -q`
- `python -m compileall testbed tests`

当前已完成的 live 验证：

- Stage 4 的主配置与 `3-cycle smoke` 配置都已经真实接上 Unity live
- 当前已确认的 planner 行为：
  - 第一轮 `dump_end` 后会生成 `CycleSummary`
  - 会立刻 replan，并把 `next_goal` 切到非 `mid` sector
  - `planner_trace.json` 能完整回放 belief / score / selected_next_goal
- 当前已经确认的 re-entry 结论：
  - 旧的极端 `left/right` corridor 会把 bucket 带出当前 dig area 的可达区域
  - `soft corridor + servo_reentry_pose` 已经证明当前 blocker 主要在 re-entry 几何，而不是 planner 本体
  - 现在正式 Stage-4 主配置已经完成 `3` 条 live 回归：
    - `cycle1_success_rate = 1.0`
    - `cycle2_success_rate = 1.0`
    - `transition_timeout_count = 0.0`
    - `planner_sector_sequences = ["left", "left", "left"]`
    - 所有 rollout 都以 `target_cycle_gate_reached` 结束
  - 正式 `3-cycle smoke` 也已经跑通主路径：
    - `planner_sector_sequence = ["left", "right"]`
    - `completed_transition_count = 2`
    - `transition_timeout_count = 0`
    - `cycle3_success = 1`
  - 当前剩余工作收缩为：
    - 继续做更大样本的多 rollout 回归
    - 根据回归结果继续细化 rule score / belief update

## Acceptance Criteria

- `cycle2_success_rate >= 0.8 * cycle1_success_rate`
- planner 决策可回放、可解释
- 非 `mid` sector 不出现明显崩溃

当前状态判断：

- `2-cycle` 主门槛：已达成，且在正式主配置下 `3` 条 live rollout 全部通过
- planner trace / belief / replan 回放：已达成
- `3-cycle smoke`：已达成，正式 `episode_len = 8000` 配置下已通过一次官方 live smoke，`cycle3_success = 1`

## Risks and Stop Conditions

- sector 粒度过粗导致收益不明显，则记录结论再评估是否进入更细粒度规划
- cycle summary 噪声过高导致 planner 不稳定，则先回头修 summary 定义
- 如果 Stage 4 的 planner 实现开始对 bootstrap handoff 形成隐性依赖，则暂停继续扩展 planner，先把这种耦合显式拆掉
