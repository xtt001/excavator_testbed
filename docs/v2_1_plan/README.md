# V2.1 Hybrid Multicycle Execution Plan

## Overview

本目录用于承接 `docs/v2_1_hybrid_multicycle_technical_draft.md` 的执行化拆解。

技术草案负责说明为什么要做 V2.1；本目录负责说明接下来按什么顺序做、每个阶段做什么、做到什么算完成。

V2.1 的核心目标不是继续围绕固定 `ready pose` 打补丁，而是建立一个可以连续运行 `2~3` 铲的 hybrid multicycle 主线。

## Global Decisions

### Cycle Boundary

- `cycle_i.start = qualified_dig_start(i)`
- `cycle_i.end = qualified_dig_start(i+1)`

V2.1 的闭环边界以事件定义，不再以 `dump -> ready_anchor` 作为主收尾逻辑。

### Ready Anchor Status

- `ready_anchor` 不再作为主 stop 逻辑。
- 如果后续保留相关代码或数据位，其角色只能降级为：
  - 分析标签
  - fallback corridor 模板参考
  - 调试辅助信息

### Protocol and Runtime Scope

- Stage 1 不改 live STEP protocol。
- V2.1 第一版不改 action 维度，继续沿用现有 `4D action`。
- Repo C 在前几个阶段只做文档同步，不做协议主版本升级。

### Planning Granularity

- 第一版 planner 采用 sector-first，不做 `3x3 patch planner`。
- 第一版 coarse planning granularity 固定为：
  - sector: `left / mid / right`
  - depth: `shallow / medium / deep`

### Goal Tokens

- `/v2/step/goal_tokens` 固定切到 `10D sector-first`。
- Stage 1 的 token 由离线规则重建，不依赖在线 planner 已存在。

### Policy Division of Labor

- ACT 第一版只负责 `qualified_dig_start -> dump_end` 的 `work skill`。
- transition 第一版由 scripted controller 负责。
- hybrid 闭环在 Stage 2 才进入主线。

### Bootstrap Compatibility Layer

Stage 3 为了把 bootstrap work-skill 的 live 路径先打通，当前允许在 deploy wrapper 中保留一个临时 bootstrap handoff：

- `reset -> loaded_and_clear` 由 `ACT V1` 起手
- `loaded_and_clear -> dump_end` 再切给 Stage-3 work policy

这条逻辑目前只允许存在于 **Repo A 的 live deploy / eval wrapper** 中，必须遵守以下边界：

- 不进入协议
- 不进入 `/v2` schema
- 不进入 cycle / phase / planner 语义
- 不默认作为训练 teacher 数据
- 不自动视为长期架构的一部分

后续 Stage 4 / Stage 5 可以在有 bootstrap 的情况下推进，但必须始终把它视为 **deploy-only compatibility layer**，并保留未来删除它的能力。

## Global Interface Decisions

### `/v2/step`

- `goal_tokens`: shape `(T, 10)`
- `phase_id`: `0..6`
- `mode_id`:
  - `0 = work`
  - `1 = transition`

### Recorder Mainline

- 主录制入口改为 `teleop_v2_1_multi_raw`
- 原始 episode 默认目标为 `3` 个 cycle
- `max_steps` 只作为兜底条件，不作为主切分逻辑

## Stage Table


| Stage   | Name                        | Goal                                           | Deliverables                                                                          | Entry Criteria                            | Exit Criteria                                | Blocking Dependencies |
| ------- | --------------------------- | ---------------------------------------------- | ------------------------------------------------------------------------------------- | ----------------------------------------- | -------------------------------------------- | --------------------- |
| Stage 1 | P0 Semantic Instrumentation | 把主线切到多轮 raw + 事件切窗 + 多轮评测                      | `teleop_v2_1_multi_raw`, `boundary_detector`, `tb-label-v2_1`, 新 `/v2` 字段, 多轮 metrics | 技术方向已确认废弃 ready-anchor 主线                 | 能录 `3-cycle raw`, 能切 cycle, evaluator 产出多轮指标 | 无                     |
| Stage 2 | P1 Minimal Hybrid Closure   | 在不训练新模型的前提下跑通 `2~3` 铲自动衔接                      | `corridor_servo`, `fixed_sequence_planner`, `hybrid_planner_act`                      | Stage 1 事件和数据链路稳定                         | 能自动从 `dump_end` 进入 transition 并进入下一轮 dig     | Stage 1               |
| Stage 3 | P2 Work-Skill Training      | 把 ACT 训练窗口切到 `qualified_dig_start -> dump_end` | `workskill_relabel`, 10D token 训练通路, 新 train/eval configs                             | Stage 1 的 relabel 和 schema 已稳定            | 单轮 `work skill` 不低于现基线                       | Stage 1               |
| Stage 4 | P3 Rule Planner             | 在 cycle boundary 进行 coarse replan              | `RuleTaskPlanner`, `PlannerGoal`, `CycleSummary`, `SectorBelief`                      | Stage 2 hybrid 可跑, Stage 3 work skill 可用  | `cycle2_success_rate` 维持在合理区间, planner 决策可回放 | Stage 2, Stage 3      |
| Stage 5 | P4 Learning + Cleanup       | 把 learned transition 提升为可部署候选，并完成 fallback 与清理 | learned transition, `transition_clean_v2`, hybrid online logs, scripted fallback, cleanup | Stage 2 scripted transition 已形成稳定 teacher | learned transition 多 rollout 不再明显落后于 scripted     | Stage 2, Stage 3      |


## Global Deletions

旧的 phase-1 主线不再作为长期兼容目标，后续迁移默认以删除为导向。重点包括：

- `dump_plus_ready`
- `ready_anchor_hold_steps`
- `ready_anchor_hit_threshold`
- 以 `return_ready` 为主闭环的 phase / eval / stop 逻辑
- `teleop_v2_cycle_*` 旧主配置

Repo B 中与 `Ready Anchor Guide / ReadyAnchorWorldMarker` 相关的内容，如果仍然存在，只能作为历史残件或调试入口，不再作为主工作流说明。

## Working Rule

- 后续每次实施只打开当前阶段文件。
- 未进入的阶段只允许参考，不允许顺手混做。
- 任何真正实施都必须同时同步：
  - Repo A 文档
  - Repo B 文档
  - Repo C 文档
  - 当前阶段文件里的状态区

## Stage Files

- [Stage 01 — P0 Semantic Instrumentation](./stage_01_p0_semantic_instrumentation.md)
- [Stage 02 — P1 Minimal Hybrid Closure](./stage_02_p1_minimal_hybrid_closure.md)
- [Stage 03 — P2 Work-Skill Training](./stage_03_p2_workskill_training.md)
- [Stage 04 — P3 Rule Planner](./stage_04_p3_rule_planner.md)
- [Stage 05 — P4 Learning and Cleanup](./stage_05_p4_learning_and_cleanup.md)

## Current Stage

当前已完成 **Stage 1 / P0 Semantic Instrumentation**、**Stage 2 / P1 Minimal Hybrid Closure**、**Stage 3 / P2 Work-Skill Training**，并已把 **Stage 4 / P3 Rule Planner** 的第一版 coarse replan 接到 live eval 主链。

当前仓库已经具备：

- 主录制入口已切到 `teleop_v2_1_multi_raw`
- 主停止规则已切到 `target_dump_count = 3`
- `tb-label-v2_1` 已落地并默认输出 sibling relabeled 数据集
- `/v2` 已切到 Stage-1 multicycle 事件语义
- Stage-2 `hybrid_planner_act` 已接入 `tb-eval`
- Stage-2 scripted corridor servo / fixed-sequence planner 已落地
- Stage-2 hybrid 评测入口已落地：
  - `testbed/configs/eval_agx_v2_1_stage2_hybrid.yaml`
  - `testbed/configs/eval_agx_v2_1_stage2_hybrid_3cycle_smoke.yaml`
- Stage-3 bootstrap 数据与训练入口已落地：
  - `tb-build-workskill-v2_1`
  - `testbed/configs/act_agx_v2_1_workskill_qvel.yaml`
  - `testbed/configs/act_agx_v2_1_workskill_gcact.yaml`
  - `testbed/configs/eval_agx_v2_1_stage3_workskill_qvel.yaml`
- Stage-4 rule planner 入口已落地：
  - `testbed/planner/types.py`
  - `testbed/planner/scenario_manifest.py`
  - `testbed/planner/rule_planner.py`
  - `testbed/configs/eval_agx_v2_1_stage4_rule_planner.yaml`
  - `testbed/configs/eval_agx_v2_1_stage4_rule_planner_3cycle_smoke.yaml`
- Stage-5 learned transition 主线已开始：
  - `tb-build-transition-v2_1 --clean-profile stage5`
  - `data/agx_teleop_v2_1_multi_raw_transition_clean_v2`
  - `testbed/configs/act_agx_v2_1_multi_raw_transition_clean_v2_qvel.yaml`
  - `testbed/configs/eval_agx_v2_1_stage5_scripted_transition_compare_5rollouts.yaml`
  - `testbed/configs/eval_agx_v2_1_stage5_learned_transition_clean_v2_compare_5rollouts.yaml`
  - `testbed/configs/eval_agx_v2_1_stage5_learned_transition_clean_v2_fallback_compare_5rollouts.yaml`

`2026-04-19` 的 live 联调已经完成：

- `s0_truck` 主配置下，Stage-2 已通过单次真实 `2-cycle` gate
- `3-cycle smoke` 已在 `episode_len = 8000` 下跑通
- Stage-3 bootstrap sibling 数据链已完成：
  - `agx_teleop_v1 -> agx_teleop_v1_v2_1_relabeled -> agx_teleop_v1_v2_1_workskill`
- Stage-3 smoke 训练已完成：
  - `qvel` best val loss = `40.9493`
  - `gcact` best val loss = `25.3733`
- Stage-3 `qvel` / `gcact` 的 `e50` 训练已完成：
  - `qvel e50` best val loss = `0.6962`
  - `gcact e50` best val loss = `0.6463`
- Stage-3 正式 live 默认现已提升为：
  - `qvel e50 + loaded_and_clear bootstrap`
- 这条 Stage-3 live 路径已通过单轮真实 `dump_complete_final_hold` success gate
  - 但还没有替代 Stage-2 的 multicycle 验收线
- Stage-4 第一版 rule planner 已完成 live 接线、trace、belief 和 replan 回放：
  - `planner_replan_count = 1`
  - `planner_sector_sequence = ["left"]`
  - 并已写出 `rollout_XXX_planner_trace.json`
  - 当前已经补上 Stage-4 专用的 `soft corridor + servo_reentry_pose`
  - 正式主配置下的 `3` 条 live rollout 已达到：
    - `cycle1_success_rate = 1.0`
    - `cycle2_success_rate = 1.0`
    - `transition_timeout_count = 0.0`
  - 正式 `3-cycle smoke` 已跑通到：
    - `planner_sector_sequence = ["left", "right"]`
    - `completed_transition_count = 2`
    - `transition_timeout_count = 0`
    - `cycle3_success_rate = 1.0`
- 因此 Stage-4 第一版 coarse replan 的首版目标已经完成
  - 后续剩余工作转为：
    - planner 规则细化
    - 与 Stage-5 learned transition 的标准化 compare
- Stage-5 当前已完成：
  - `transition_clean_v2` 数据构建
  - `summary.json` reject reason 统计
  - clean_v2 qvel 训练主线
  - learned transition 的 scripted fallback 机制
  - rollout / summary 的 fallback 调试字段
- Stage-5 当前尚未开始：
  - learned planner
  - planner supervision 训练线

因此当前可以认为 **Stage 3 的 bootstrap 计划目标已达到**，且 **Stage 4 的第一版 coarse replan 已经落地主链，并已通过正式主配置的 `2-cycle` 主门槛和官方 `3-cycle smoke`**。  
接下来的重点变成：

- 保持 Stage-4 rule planner 为默认高层 planner
- 继续推进 Stage-5 learned transition 主线
- 用 `transition_clean_v2`、fallback 和标准化 compare 把 learned transition 做成可部署候选
- 暂不启动 learned planner

当前 Stage 5 的固定边界是：

- 默认 planner 继续是 `RuleTaskPlanner`
- learned transition 只替换 `wait_next_dig` 子段
- fallback 允许在当次 transition 中切回 scripted `wait_next_dig`
- 不新增 learned planner policy class
- 不改 `/v2` schema、协议、action 维度

继续推进 Stage 5 时需要特别记住一条工程纪律：

- planner、belief、cycle summary 和 replan 接口必须独立成立，不能把当前 bootstrap handoff 当成隐含前提
- learned planner 只有在 transition 和 work 两层都稳定后才允许进入下一阶段
