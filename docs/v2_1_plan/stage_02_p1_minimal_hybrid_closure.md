# Stage 02 — P1 Minimal Hybrid Closure

## Goal

在不训练新模型的前提下，先证明 `2~3` cycle 可以自动衔接跑通。

本阶段的重点是最小 hybrid 闭环，不是 planner 智能化，也不是 learned transition。

## Status

- State: `implemented_in_repo`
- Priority: `after_stage_01`
- Owner: `Repo A Stage-2 deploy chain`
- Synced to repo: `2026-04-19`
- Live status: `s0_truck_2cycle_gate_passed_and_3cycle_smoke_passed`

## In Scope

- `corridor_servo.py`
- `fixed_sequence_planner.py`
- `testbed/policies/hybrid/adapter.py`
- hybrid eval 配置
- transition 子状态机

## Out of Scope

- rule planner
- 动态 replan
- 新数据集训练
- learned transition

## Main Deliverables

- `EntryCorridorBand`
- scripted `TransitionController`
- `fixed_sequence_planner`
- `hybrid_planner_act`
- hybrid rollout metadata 和评测入口
- `eval_agx_v2_1_stage2_hybrid.yaml`
- `eval_agx_v2_1_stage2_hybrid_3cycle_smoke.yaml`

## Hybrid Plan

### Mode Split

- `WORK` 模式：继续使用现有 ACT baseline
- `TRANSITION` 模式：使用 scripted band servo

### Transition Submodes

第一版 transition 子状态固定为：

- `clear_target`
- `corridor_align`
- `wait_next_dig`

### Corridor Band

第一版只提供三个 band：

- `left_band`
- `mid_band`
- `right_band`

band 表达采用：

- `qpos_lo`
- `qpos_hi`

当前默认 band 已固定为：

- `mid_band`: `qpos_lo=[0.42, 0.574, 0.463, 0.610]`, `qpos_hi=[0.58, 0.694, 0.583, 0.770]`
- `left_band`: `qpos_lo=[0.60, 0.574, 0.463, 0.610]`, `qpos_hi=[0.76, 0.694, 0.583, 0.770]`
- `right_band`: `qpos_lo=[0.24, 0.574, 0.463, 0.610]`, `qpos_hi=[0.40, 0.694, 0.583, 0.770]`

当前 transition 默认控制律为：

- `kp = 2.0`
- `kd = 0.25`
- `action_clip = 0.35`
- `action_clip_by_joint = [0.75, 0.35, 0.35, 0.55]`
- `clear_target_min_steps = 24`
- `clear_target_max_steps = 90`
- `corridor_align_max_steps = 220`
- `wait_next_dig_max_steps = 360`

当前 live 联调后的 `wait_next_dig` 语义为：

- scripted servo 先完成 `clear_target -> corridor_align`
- 进入 `wait_next_dig` 后，动作权交回 `ACT V1`
- hybrid wrapper 保持在 transition 监视态，直到检测到下一次 `qualified_dig_start`

这样做的原因是：

- 纯 hold-servo 无法自己触发下一次 `qualified_dig_start`
- Stage 2 需要的是最小 handoff，不是 learned transition

## Planner Plan

### Planner Type

第一版只做 `fixed_sequence_planner`，不做动态 replan。

### Planning Assumption

- 目标序列由固定 coarse sector 顺序给出
- planner 只负责在 cycle boundary 提供下一个 coarse goal
- 不尝试学习式选择，不尝试 terrain belief 更新

当前主验收配置固定采用：

- `mid -> mid -> mid`
- live 默认 `scenario_id = s0_truck`
- `2-cycle` 为主门槛
- `3-cycle` 只做 smoke，当前默认 `episode_len = 8000`

## Interface / Config Changes

### Add

- `policy_class = hybrid_planner_act`
- `transition_source = scripted_band_servo`
- hybrid rollout metadata
- transition 子模式日志
- `eval.target_cycle_gate`
- `policy.work_ckpt_path / work_ckpt_dir / work_low_dim_keys`
- `policy.planner.sequence`
- `policy.transition.bands.left/mid/right`

### Keep Stable

- 不改 live STEP protocol
- 不改 action 维度
- 不引入新的 wire 字段

## Tests

- `2-cycle` smoke eval
- `3-cycle` smoke eval
- transition 子模式切换测试
- `dump_to_next_dig_gap_steps` 回归对比
- transition 碰撞率回归对比

当前仓库内已覆盖：

- `tests/test_agx_stage2_hybrid.py`
- `tests/test_agx_repoa_integration.py`

## Acceptance Criteria

- 能从 `dump_end` 自动进入 transition
- 能通过 transition 进入下一轮 `qualified_dig_start`
- 主配置以 `target_cycle_gate = 2` 跑最小 hybrid 闭环
- `3-cycle` 配置保留为 smoke
- `dump_to_next_dig_gap_steps` 相比非 hybrid baseline 明显下降
- 不再需要 fixed ready point

## Risks and Stop Conditions

- scripted band 过硬导致 oscillation，则先调 corridor 规则，不推进 Stage 3
- fixed sequence 过度理想化导致结论失真，则记录偏差并在 Stage 4 重评

## Live Validation Notes

`2026-04-19` 的 Unity live 检查里：

- `s0_baseline` 的初始 target 几何与当前 `ACT V1` checkpoint 不匹配
- `s0_truck` 才是当前 Stage 2 live 验收的有效 preset
- 在 `s0_truck + target_cycle_gate=2 + episode_len=4000` 下，最小 hybrid 已经完成：
  - 第 1 次 `dump_end`
  - scripted transition
  - 下一轮 `qualified_dig_start`
  - 第 2 次 `dump_end`

当前 live 联调结论：

- Stage-2 主配置已通过单次真实 `2-cycle` gate
- `3-cycle smoke` 已在 `episode_len = 8000` 下真实跑通
- 当前 Stage 2 的计划目标已达到，可以进入 Stage 3

额外说明：

- 多 rollout 稳定性仍然值得继续回归，但它已不再阻塞 Stage 2 关账
- `3-cycle smoke` 的通过口径以 `cycle3_success = 1`、`completed_transition_count = 2` 为主，不要求 `dump_complete_final_hold_success = true`
