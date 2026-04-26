# 配置文件索引

本文档说明 `testbed/configs/` 下各类 YAML 的当前角色。

从 `2026-04-17` 开始，Repo A 的 V2 主线已经切到 **V2.1 Stage 1**：

- 录制主入口改为 `teleop_v2_1_multi_raw.yaml`
- 录制目标改为自然连续 `3` 铲 raw episode
- 不再把 fixed ready pose / ready-anchor 作为主 stop 逻辑
- `/v2` 标注主入口改为 `tb-label-v2_1`
- Stage 1 不新增训练主线；重点是录制、离线标注和多轮评测
- target-safety workskill 现在要求显式 target geometry 字段：
  `target_horizontal_distance_m`、`bucket_height_above_target_rim_m`、
  `bucket_over_target_footprint_mask`、`dump_clearance_ok_mask`。旧的
  `min_distance_to_target_m` 不再作为这些字段的 fallback。
- `dump_clearance_ok_mask` 由 Unity 作为 target-clearance source of truth
  输出；TruckBed 可使用水平 dump 容差，但垂直方向仍要求
  `bucket_height_above_target_rim_m >= 0.0`。

同日，V2.1 **Stage 2 最小 hybrid 闭环** 也已经接入 live eval：

- 新增 `eval_agx_v2_1_stage2_hybrid.yaml`
- 新增 `eval_agx_v2_1_stage2_hybrid_3cycle_smoke.yaml`
- `WORK = ACT V1`
- `TRANSITION = scripted corridor servo`
- fixed sequence planner 当前固定为 `mid -> mid -> mid`
- 当前 live 验证默认使用 `scenario_id = s0_truck`

随后，V2.1 **Stage 3 Work-Skill Training** 也已经接入 bootstrap 链：

- `tb-build-workskill-v2_1`
- `act_agx_v2_1_workskill_qvel.yaml`
- `act_agx_v2_1_workskill_gcact.yaml`
- `eval_agx_v2_1_stage3_workskill_qvel.yaml`
- source dataset 固定只读：`data/agx_teleop_v1/`

现在，V2.1 **Stage 4 Rule Planner** 的第一版 coarse replan 也已经接入：

- `eval_agx_v2_1_stage4_rule_planner.yaml`
- `eval_agx_v2_1_stage4_rule_planner_3cycle_smoke.yaml`
- `planner.kind = rule`
- `WORK = ACT V1`
- 不启用 Stage 3 bootstrap
- planner 只驱动 `next_goal / next_entry_corridor / belief / planner_trace.json`
- 当前 Stage 4 已补上：
  - soft non-mid corridor
  - `wait_next_dig = servo_reentry_pose`
- 正式主配置下的 `3` 条 live rollout 已达到：
  - `cycle1_success_rate = 1.0`
  - `cycle2_success_rate = 1.0`
  - `transition_timeout_count = 0.0`
- 正式 `3-cycle smoke` 已跑通到：
  - `planner_sector_sequence = ["left", "right"]`
  - `completed_transition_count = 2`
  - `transition_timeout_count = 0`
  - `cycle3_success_rate = 1.0`
- 当前剩余工作：
  - 更大样本的多 rollout 回归
  - rule planner 规则细化

## 今天优先用哪些文件

| 目标 | 推荐配置 / 命令 | 说明 |
|---|---|---|
| 当前业务 baseline 录制 | `testbed/configs/teleop_v1.yaml` | 当前正式 baseline rerecord 入口，输出到 `data/agx_teleop_v1/` |
| V2.1 Stage 1 多轮 raw 录制 | `testbed/configs/teleop_v2_1_multi_raw.yaml` | 当前 V2 主录制入口；默认录满 `3` 次 `dump_end` 或到 `4000` 步 |
| 当前业务 baseline 训练 | `testbed/configs/act_agx_v1.yaml` | 当前默认 ACT 训练入口 |
| 当前业务 baseline 评测 | `testbed/configs/eval_agx_v1.yaml` | 当前默认 live eval 入口 |
| V2.1 Stage 1 多轮评测 | `testbed/configs/eval_agx_v2_1_stage1.yaml` | 用当前 baseline checkpoint 跑长 episode，多轮日志与指标输出到独立目录 |
| V2.1 Stage 2 hybrid 主评测 | `testbed/configs/eval_agx_v2_1_stage2_hybrid.yaml` | 最小 hybrid 闭环主入口；`target_cycle_gate = 2` |
| V2.1 Stage 2 hybrid 3-cycle smoke | `testbed/configs/eval_agx_v2_1_stage2_hybrid_3cycle_smoke.yaml` | 只做 3-cycle smoke，不作主门槛；默认 `episode_len = 8000` |
| V2.1 Stage 3 qvel work-skill 训练 | `testbed/configs/act_agx_v2_1_workskill_qvel.yaml` | bootstrap work-skill 主训练入口；读取 sibling cropped 数据集 |
| V2.1 Stage 3 gcact 训练 | `testbed/configs/act_agx_v2_1_workskill_gcact.yaml` | `qpos + qvel + goal_tokens` 的 held-out 对照线 |
| V2.1 Stage 3 qvel live smoke | `testbed/configs/eval_agx_v2_1_stage3_workskill_qvel.yaml` | 把 Stage-3 qvel work ckpt 接回 Stage-2 hybrid live smoke |
| V2.1 Stage 4 rule planner 主评测 | `testbed/configs/eval_agx_v2_1_stage4_rule_planner.yaml` | 第一版 coarse replan 主入口；当前使用 soft corridor + `servo_reentry_pose`，官方 `2-cycle` 主门槛已通过 |
| V2.1 Stage 4 rule planner 3-cycle smoke | `testbed/configs/eval_agx_v2_1_stage4_rule_planner_3cycle_smoke.yaml` | Stage-4 多轮 smoke 入口；官方 `3-cycle smoke` 已通过一次真实 live 检查 |
| 历史 `qpos + qvel` 对照 | `act_agx_fulltest_qvel.yaml` + `eval_agx_fulltest_qvel.yaml` | 保留为旧对照线 |
| smoke 验证 | `act_agx_smoke.yaml` + `eval_agx_smoke.yaml` | 只用于验证 train/eval 链路 |

## 文件族

| 文件前缀 | 入口命令 | 作用 |
|---|---|---|
| `teleop_*.yaml` | `tb-record-teleop`、`tb-replay` | 录制和回放配置 |
| `act_agx_*.yaml` | `tb-train` | AGX 挖掘机 ACT 训练配置 |
| `eval_agx_*.yaml` | `tb-eval` | AGX 挖掘机 live eval 配置 |
| `act_v0.yaml` / `eval_v0.yaml` / `task_v0.yaml` | `tb-train`、`tb-eval`、`tb-record` | 早期 MuJoCo transfer-cube 验证链路 |
| `agx_v0.yaml` | 手动参考 | AGX 连接参数和向量维度说明 |

## 1. AGX 录制与回放配置

| 文件 | 当前角色 | 关键差异 |
|---|---|---|
| `teleop_v1.yaml` | 当前业务 baseline | `dump_complete_final_hold` 成功即停；成功后继续录 `50` 步尾段 |
| `teleop_v2_1_multi_raw.yaml` | 当前 V2 主入口 | `recording_mode = teleop_multi_raw`；`scenario_id = s0_truck`；`stop_mode = target_dump_count`；默认录 `3` 次有效 `dump_end` 后再保留 `50` 步 terminal tail；`task.max_steps = 4000` |
| `teleop_v0.yaml` | legacy | 兼容早期数据与旧流程 |

`tb-replay` 可以复用这些 teleop 配置连接 AGX。需要把旧 episode 的 action 序列在当前 Unity 中重新采集 observation/env_state 时，使用：

```bash
tb-replay \
  --episode data/agx_teleop_v2_1_multi_raw/episode_0.hdf5 \
  --config testbed/configs/teleop_v2_1_multi_raw.yaml \
  --record-output-dir data/agx_teleop_v2_1_multi_raw_replayed_current
```

刷新写新 HDF5 时，`tb-replay` 会把 `teleop.post_success_tail_steps`
作为 source actions 后的 zero-action tail；当前 V2.1 默认 `50` 步。这个
tail 用来保留 terminal dump 后的 plateau / `dump_end` 观测，避免刚倒完就
截断。可用 `--post-tail-steps <N>` 临时覆盖。

当前这三份 `teleop` 配置共享同一套 FarmStick 默认臂控映射，已按真机控制习惯对齐为：

- `swing <- 左主杆前后`
- `stick <- 左主杆左右`
- `boom <- 右主杆前后`
- `bucket <- 右主杆左右`，并额外做一次反向以匹配真机 bucket 手感

当前 V2.1 Stage 1 的录制新增了这些字段：

- `teleop.stop_mode = target_dump_count`
- `teleop.target_dump_count = 3`
- `teleop.post_success_tail_steps = 50`
- `task.recording_mode = teleop_multi_raw`
- `task.scenario_id`

当前正式录制默认值：

- `task.scenario_id = s0_truck`

如果一条 raw 录制以：

- `stop_reason = max_steps_reached`
- 且 `completed_dump_count = 0`

结束，则说明这条数据没有形成任何有效 `dump_end`。这类 episode 不应直接进入后续 `tb-label-v2_1` / 训练主线，建议先移到隔离目录再人工复核。

当前 V2.1 Stage 1 的录制不再依赖：

- `dump_plus_ready`
- `ready_anchor_hold_steps`
- `ready_anchor_hit_threshold`

## 2. AGX 训练配置

当前训练入口除了 baseline / 历史对照外，还新增了 Stage 3 bootstrap work-skill 主线：

| 文件 | 当前角色 | 说明 |
|---|---|---|
| `act_agx_v1.yaml` | 当前业务 baseline | 正式 baseline 训练入口 |
| `act_agx_fulltest.yaml` | 历史 `qpos` 对照 | 保留给旧 run 对照 |
| `act_agx_fulltest_qvel.yaml` | 当前输入消融对照 | 历史 `qpos + qvel` 对照 |
| `act_agx_v2_1_workskill_qvel.yaml` | Stage 3 bootstrap 主线 | `qpos + qvel`，默认读取 `data/agx_teleop_v1_v2_1_workskill` |
| `act_agx_v2_1_workskill_gcact.yaml` | Stage 3 held-out 对照 | `qpos + qvel + goal_tokens`，本阶段不进 live |
| `act_agx_v2_1_multi_raw_workskill_qvel.yaml` | 当前多轮 raw 主训练线 | `qpos + qvel`，默认读取 `data/agx_teleop_v2_1_multi_raw_workskill` |
| `act_agx_v2_1_multi_raw_workskill_gcact.yaml` | 当前多轮 raw goal-token 对照线 | `qpos + qvel + goal_tokens`，默认读取 `data/agx_teleop_v2_1_multi_raw_workskill` |
| `act_agx_v2_1_multi_raw_workskill_clean_v2_qvel.yaml` | 当前高质量 work-skill 主训练线 | `qpos + qvel`，默认读取 `data/agx_teleop_v2_1_multi_raw_workskill_clean_v2` |
| `act_agx_v2_1_multi_raw_workskill_clean_v2_gcact.yaml` | 当前高质量 work-skill goal-token 对照线 | `qpos + qvel + goal_tokens`，默认读取 `data/agx_teleop_v2_1_multi_raw_workskill_clean_v2` |
| `act_agx_v2_1_multi_raw_new_workskill_clean_v2_qvel.yaml` | 新补录高质量 work-skill 主训练线 | `qpos + qvel`，默认读取 `data/agx_teleop_v2_1_multi_raw_new_workskill_clean_v2` |
| `act_agx_v2_1_multi_raw_new_workskill_clean_v3_qvel.yaml` | 新补录 stricter 高质量 work-skill 主训练线 | `qpos + qvel`，默认读取 `data/agx_teleop_v2_1_multi_raw_new_workskill_clean_v3` |
| `act_agx_v2_1_multi_raw_all_workskill_clean_v3_qvel.yaml` | 全量 stricter 高质量 work-skill 主训练线 | `qpos + qvel`，默认读取旧+新合并后的 `data/agx_teleop_v2_1_multi_raw_all_workskill_clean_v3`；因合并了旧批次长窗口，默认 `episode_len = 1200` |
| `act_agx_v2_1_multi_raw_all_workskill_clean_v3_qualitymix_qvel.yaml` | 当前 target-safe 质量补录 mix 主训练候选 | `qpos + qvel`，默认读取旧 `clean_v3` 加 `2604241251` 质量补录 terminal-fix v3 后再剔除 `near_dump_start` 的 `74` 条 symlink mix；用于本轮 v3-only retrain |
| `act_agx_v2_1_multi_raw_all_workskill_clean_v3b_qvel.yaml` | 过严诊断 work-skill 线 | `qpos + qvel`，默认读取旧+新合并后的 `data/agx_teleop_v2_1_multi_raw_all_workskill_clean_v3b`；当前不作为主训练线 |
| `act_agx_v2_1_multi_raw_all_workskill_clean_v4_qvel.yaml` | 最严诊断 work-skill 线 | `qpos + qvel`，默认读取旧+新合并后的 `data/agx_teleop_v2_1_multi_raw_all_workskill_clean_v4`；当前不作为主训练线 |
| `act_agx_v2_1_multi_raw_transition_qvel.yaml` | 当前 transition feasibility 训练线 | `qpos + qvel`，默认读取 `data/agx_teleop_v2_1_multi_raw_transition` |
| `act_agx_v2_1_multi_raw_transition_clean_qvel.yaml` | 当前 clean-by-length transition 对照线 | `qpos + qvel`，默认读取 `data/agx_teleop_v2_1_multi_raw_transition_clean` |
| `act_agx_v2_1_multi_raw_transition_clean_v2_qvel.yaml` | Stage 5 learned transition 主训练线 | `qpos + qvel`，默认读取 `data/agx_teleop_v2_1_multi_raw_transition_clean_v2` |
| `act_agx_smoke.yaml` | smoke | 只验证训练链路 |

说明：

- Stage 1 已把 `/v2/step/goal_tokens` 语义切到 **10D sector-first**
- Stage 3 已把 bootstrap work-skill 训练线接入：
  - source dataset: `data/agx_teleop_v1`
  - sibling relabeled: `data/agx_teleop_v1_v2_1_relabeled`
  - sibling workskill: `data/agx_teleop_v1_v2_1_workskill`
- 当前 bootstrap cropped work window 的默认 `episode_len = 760`
- 当前新录 `teleop_v2_1_multi_raw` 的 sibling workskill 训练线也已接入：
  - sibling relabeled: `data/agx_teleop_v2_1_multi_raw_relabeled`
  - sibling workskill: `data/agx_teleop_v2_1_multi_raw_workskill`
  - 由于这批 work window 最长达到 `1166` 步，新的训练配置默认把 `episode_len` 提到 `1200`
- 当前新录 `teleop_v2_1_multi_raw` 的高质量 workskill 主线也已接入：
  - sibling clean dataset: `data/agx_teleop_v2_1_multi_raw_workskill_clean_v2`
  - builder: `tb-build-workskill-v2_1 --clean-profile stage5`
  - 当前 `stage5` 规则先按 cycle 过滤：
    - `flat_bucket_qds`
    - `far_dump_start`
    - `collision_in_cycle`
    - `low_carry_efficiency`
    - `high_residual_bucket_mass`
    - `early_dig_escape`
    - 高 `pause_ratio` 的明显犹豫样本
- 当前 stricter `stage5_strict` 线已经覆盖旧+新两批 workskill：
  - `data/agx_teleop_v2_1_multi_raw_workskill_clean_v3`: `24 / 40`
  - `data/agx_teleop_v2_1_multi_raw_new_workskill_clean_v3`: `31 / 40`
  - 合并主训练集：`data/agx_teleop_v2_1_multi_raw_all_workskill_clean_v3`，共 `55` 条高质量 cycles
  - relabel 现在还会同步补写 `/v2/step/work_stage_id`：
    - `none`
    - `entry_to_bite`
    - `first_bite`
    - `rebite_recovery`
    - `carry`
    - `approach_dump`
    - `dump`
  - current sector split after the narrow-band relabel fix:
    - `left = 15`
    - `mid = 31`
    - `right = 9`
  - sector relabeling now uses `qualified_dig_start` swing bins calibrated to the real dig-area coverage:
    - dig-area anchors: leftmost `0.43`, mid `0.50`, rightmost `0.56`
    - `swing < 0.4733 -> left`
  - target-safe 过滤现在也启用在 `stage5_strict`/v3 上：
    - `target_horizontal_distance_m < 0.35 -> near_dump_start`
    - 缺少任一 target geometry 字段会被标成 `missing_target_geometry`
    - 目的是去掉已经贴近 truck/target 才开始 dump 的 close-call 样本，避免 BC 学到低 boom + 强 curl 的硬碰撞模式
  - 当前 target-safe qualitymix：`74` 条，高质量补录 mix sector split 为 `left = 18`, `mid = 40`, `right = 16`
  - 当前 target-safe smoke eval 额外启用 live WORK safety guard：
    - loaded 且 `target_horizontal_distance_m < 1.25` 且 clearance 不满足时，approach 区先把强 dump action 软限到不小于 `-0.30`，并至少给 boom `+0.04`
    - loaded 且 `target_horizontal_distance_m < 0.45` 且 clearance 不满足时，hard guard 区再把 bucket dump action 下限收回到 `-0.15`
    - hard guard 区同时至少给 boom `+0.08` raise command，用来先把 bucket 从 target 边缘抬开
    - rollout summary 会记录 `work_target_guard_count`
    - `eval.target_cycle_gate_terminal_hold_steps = 25`，避免第 3 次 `dump_end` 立刻截断 `dump_complete_final_hold` 的末尾 hold 计数
    - `0.4733 <= swing < 0.5167 -> mid`
    - `>= 0.5167 -> right`
  - transition corridor naming is now aligned to the same physical convention:
    - lower swing = `left`
    - higher swing = `right`
  - runtime will auto-normalize older mirrored `transition.bands` configs so
    historical YAMLs do not silently report `left/right` backwards
  - current target-dump recording keeps a `50`-step terminal tail after the
    online `dump_end`; offline relabel still infers terminal `dump_end` for
    legacy no-tail raw episodes from `completed_dump_count` metadata
- 当前 balanced `stage5_balanced` 线位于 `clean_v3` 与 `clean_v4` 之间，但已经判断为过严，当前只作为诊断过滤线：
  - `data/agx_teleop_v2_1_multi_raw_workskill_clean_v3b`: `18 / 24`（从旧批次 `clean_v3` 基线再剔除 `far_dump_start` 与 severe `pretarget_spill_proxy`）
  - `data/agx_teleop_v2_1_multi_raw_new_workskill_clean_v3b`: `27 / 31`
  - 合并诊断集：`data/agx_teleop_v2_1_multi_raw_all_workskill_clean_v3b`，共 `45` 条 cycles
  - 这条线保留了 `clean_v3` 的 later-cycle bite 覆盖，同时继续压掉过早 dump / severe pre-target spill
- 当前最严的 `stage5_cleanest` 线也已接入，但已经判断为过严，当前只作为诊断过滤线：
  - `data/agx_teleop_v2_1_multi_raw_workskill_clean_v4`: `9 / 40`
  - `data/agx_teleop_v2_1_multi_raw_new_workskill_clean_v4`: `15 / 40`
  - 合并最严诊断集：`data/agx_teleop_v2_1_multi_raw_all_workskill_clean_v4`，共 `24` 条 cycles
  - 当前主要 reject reasons 已经收缩到：
    - `pretarget_spill_proxy`
    - `far_dump_start`
    - `flat_bucket_qds`
    - `low_carry_efficiency`
    - `collision_in_cycle`
  - 这条线当前的 spill 口径已放松为：
    - 允许中等 swing spill
    - 只拒绝“还没真正到 truck 顶部就明显提前倒、接近半桶级别”的 severe early spill
  - 当前 `24` 条 cycle 太小且过严，不作为主训练集；只用于定位 severe early dump / severe pre-target spill
- 当前新录 `teleop_v2_1_multi_raw` 的 sibling transition feasibility 训练线也已接入：
  - sibling transition: `data/agx_teleop_v2_1_multi_raw_transition`
  - transition 窗口语义固定为 `dump_end -> next qualified_dig_start`
- 当前 Stage 5 已把 clean learned transition 主线提升为：
  - sibling clean dataset: `data/agx_teleop_v2_1_multi_raw_transition_clean_v2`
  - builder: `tb-build-transition-v2_1 --clean-profile stage5`
  - 当前 builder 会同步写出 `summary.json`
  - 当前 reject reason 至少包括：
    - `overlong_transition_len`
    - `late_qds_failure`
    - 高 `pause_ratio` 的明显犹豫样本

## 3. AGX Live Eval 配置

| 文件 | 当前角色 | 关键差异 |
|---|---|---|
| `eval_agx_v1.yaml` | 当前业务 baseline | 现行业务 baseline live eval |
| `eval_agx_v2_1_stage1.yaml` | 当前 V2.1 Stage 1 评测入口 | `task.episode_len = 4000`；默认写 rollout logs；输出多轮 boundary / continuity 指标 |
| `eval_agx_v2_1_stage2_hybrid.yaml` | 当前 V2.1 Stage 2 主评测入口 | `policy.class = hybrid_planner_act`；主门槛 `target_cycle_gate = 2` |
| `eval_agx_v2_1_stage2_hybrid_3cycle_smoke.yaml` | V2.1 Stage 2 smoke | `target_cycle_gate = 3`；只作 smoke；默认 `episode_len = 8000` |
| `eval_agx_v2_1_stage3_workskill_qvel.yaml` | V2.1 Stage 3 live smoke | 用 Stage-3 qvel work-policy 替换 Stage-2 的 `WORK` checkpoint |
| `eval_agx_v2_1_stage4_rule_planner.yaml` | V2.1 Stage 4 主评测入口 | `planner.kind = rule`；继续用 `ACT V1` 做 `WORK`；planner 只驱动边界、transition 与 belief |
| `eval_agx_v2_1_stage4_rule_planner_3cycle_smoke.yaml` | V2.1 Stage 4 smoke | `target_cycle_gate = 3`；继续补 Stage-4 多轮回归 |
| `eval_agx_v2_1_stage4_rule_planner_learned_transition_3cycle_smoke.yaml` | V2.1 Stage 5 feasibility compare | 保持 Stage-4 `WORK = ACT V1`，只把 `wait_next_dig` 接成 learned transition，用于和 scripted 3-cycle rollout 做 A/B 对照 |
| `eval_agx_v2_1_stage4_rule_planner_learned_transition_clean_3cycle_smoke.yaml` | clean learned feasibility compare | 使用 clean-by-length transition ckpt 做单条 3-cycle learned 对照 |
| `eval_agx_v2_1_stage5_scripted_transition_compare_5rollouts.yaml` | Stage 5 scripted compare | `5-rollout` scripted baseline compare |
| `eval_agx_v2_1_stage5_learned_transition_clean_v2_compare_5rollouts.yaml` | Stage 5 learned compare | `5-rollout` learned clean_v2 compare |
| `eval_agx_v2_1_stage5_learned_transition_clean_v2_fallback_compare_5rollouts.yaml` | Stage 5 learned+fallback compare | `5-rollout` compare，并记录 fallback 行为 |
| `eval_agx_v2_1_stage5_workskill_clean_v2_qvel_3cycle_smoke.yaml` | Stage 5 high-quality work smoke | `bootstrap + rule planner + scripted transition + clean_v2 qvel work ckpt` 的单条 3-cycle smoke |
| `eval_agx_v2_1_stage5_workskill_clean_v2_qvel_newdata_3cycle_smoke.yaml` | Stage 5 新补录高质量 work smoke | 与上一条同口径，但切到 `agx_teleop_v2_1_multi_raw_new_workskill_clean_v2` 训练出的 ckpt |
| `eval_agx_v2_1_stage5_workskill_clean_v3_qvel_newdata_3cycle_smoke.yaml` | Stage 5 新补录 stricter 高质量 work smoke | 继续同口径，但切到 `stage5_strict` 规则筛出来的 `clean_v3` 数据与 ckpt |
| `eval_agx_v2_1_stage5_workskill_clean_v3_qvel_alldata_3cycle_smoke.yaml` | Stage 5 全量 stricter 高质量 work smoke | 继续同口径，但切到旧+新 `clean_v3` 合并数据训练出的 ckpt |
| `eval_agx_v2_1_stage5_workskill_clean_v3_qualitymix_qvel_3cycle_smoke.yaml` | Stage 5 target-safe qualitymix work smoke | 使用当前 `74` 条 target-safe terminal-fix qualitymix v3 数据训练出的 `WORK` ckpt；第 3 次 dump 后保留 `25` 步 terminal hold，并启用两段 target guard |
| `eval_agx_v2_1_stage5_workskill_clean_v3b_qvel_alldata_3cycle_smoke.yaml` | Stage 5 全量 balanced 高质量 work smoke | 使用 `clean_v3b` 合并数据训练出的 `WORK` ckpt；当前默认 `task.episode_len = 5000` |
| `eval_agx_v2_1_stage5_workskill_clean_v4_qvel_alldata_3cycle_smoke.yaml` | Stage 5 全量 cleanest 高质量 work smoke | 使用 `clean_v4` 合并数据训练出的 `WORK` ckpt；当前默认 `task.episode_len = 5000` |
| `eval_agx_fulltest.yaml` | 历史 `qpos` 对照 | 保留历史对照 |
| `eval_agx_fulltest_qvel.yaml` | 历史 `qpos + qvel` 对照 | 保留历史对照 |
| `eval_agx_smoke.yaml` | smoke | 只快速检查 eval 链路 |
| `eval_agx_v0.yaml` | legacy | 早期 AGX eval 入口 |

V2.1 Stage 1 评测新增的主指标包括：

- `dump_to_next_dig_gap_steps`
- `pause_ratio`
- `boundary_jump_l1`
- `boundary_jump_l2`
- `mean_action_jerk`
- `cycle2_success_rate`
- `cycle3_success_rate`
- `carry_over_drop`

V2.1 Stage 2 在保留上面这些指标的同时，还会额外输出：

- `transition_timeout_count`
- `transition_collision_rate`
- `avg_corridor_align_steps`
- `avg_wait_next_dig_steps`
- `completed_transition_count`

V2.1 Stage 4 在保留 Stage 2 指标的同时，还会额外输出：

- `planner_replan_count`
- `planner_sector_sequence`
- `planner_blocked_sector_count`
- `planner_done_sector_count`
- `rollout_XXX_planner_trace.json`

当前 evaluator 还会额外输出一组动作质量指标，用来避免只看 success gate：

- `spill_before_target_count`
- `unsafe_target_distance_count`
- `hard_target_collision_count`
- `qds_bucket_qpos_mean` / `qds_bucket_qpos_max`
- `flat_bucket_qds_count`
- `peak_bucket_depth_mean`
- `shallow_peak_bucket_depth_count`
- `dump_start_distance_mean` / `dump_start_distance_max`
- `dump_start_horizontal_distance_mean` / `dump_start_horizontal_distance_max`
- `dump_start_geometry_missing_count`
- `target_geometry_available_rate`
- `far_dump_start_count`
- `near_dump_start_count`
- `carry_efficiency_proxy_mean`
- `low_carry_efficiency_count`
- `dump_end_residual_bucket_mass_mean` / `dump_end_residual_bucket_mass_max`
- `high_residual_bucket_mass_count`
- `dig_area_escape_cycle_count`
- `dig_area_escape_step_ratio`
- `quality_issue_count`

对应的关键 rate 版本也会一起输出，例如：

- `spill_before_target_rate`
- `unsafe_target_distance_rate`
- `hard_target_collision_rate`
- `flat_bucket_qds_rate`
- `far_dump_start_rate`
- `near_dump_start_rate`
- `low_carry_efficiency_rate`
- `high_residual_bucket_mass_rate`
- `dig_area_escape_cycle_rate`

聚合后的 `metrics.json` 会以 `avg_*` 前缀输出这些质量指标和 rate 指标，方便直接比较不同策略的动作质量。

当前 Stage 2 live 默认调参值已经按 `2026-04-19` 的 Unity 联调结果固定为：

- `task.scenario_id = s0_truck`
- `transition.action_clip_by_joint = [0.75, 0.35, 0.35, 0.55]`
- `transition.clear_target_min_steps = 24`
- `transition.clear_target_max_steps = 90`
- `transition.corridor_align_max_steps = 220`
- `transition.wait_next_dig_max_steps = 360`

说明：

- `wait_next_dig` 已不再是纯 hold-servo
- scripted servo 完成 `clear_target -> corridor_align` 后，动作会交回 `ACT V1`
- wrapper 会继续停留在 transition 监视态，直到下一次 `qualified_dig_start`

## 4. `/v2` 离线标注入口

当前主入口：

- `tb-label-v2_1 --dataset-dir data/agx_teleop_v2_1_multi_raw`
- `tb-label-v2_1 --dataset-dir data/agx_teleop_v1 --scenario-id s0_truck`
- `tb-build-workskill-v2_1 --dataset-dir data/agx_teleop_v1_v2_1_relabeled`

默认行为：

- 原始 raw 数据目录不改写
- 输出到兄弟目录：
  - `data/agx_teleop_v2_1_multi_raw_relabeled/`
  - `data/agx_teleop_v1_v2_1_relabeled/`
  - `data/agx_teleop_v1_v2_1_workskill/`

说明：

- 旧的 `tb-label-v2` 与 phase-1 单铲 `/v2` 入口已从当前分支移除
- 当前 V2.1 Stage 1 主线统一使用 `tb-label-v2_1`

## 5. 推荐工作流

### 继续业务 baseline

- `testbed/configs/teleop_v1.yaml`
- `testbed/configs/act_agx_v1.yaml`
- `testbed/configs/eval_agx_v1.yaml`

### 开始 V2.1 Stage 1

1. `tb-record-teleop --config testbed/configs/teleop_v2_1_multi_raw.yaml`
2. `tb-label-v2_1 --dataset-dir data/agx_teleop_v2_1_multi_raw`
3. `tb-eval --config testbed/configs/eval_agx_v2_1_stage1.yaml`

### 开始 V2.1 Stage 2 最小 hybrid 闭环

1. `tb-eval --config testbed/configs/eval_agx_v2_1_stage2_hybrid.yaml`
2. 如需 3-cycle smoke，再跑：
   `tb-eval --config testbed/configs/eval_agx_v2_1_stage2_hybrid_3cycle_smoke.yaml`

当前这组配置已经在在线 Unity 上完成过单次 `2-cycle` gate 检查。

另外，`3-cycle smoke` 当前也已经在在线 Unity 上通过一次真实检查；对应的默认入口就是：

- `testbed/configs/eval_agx_v2_1_stage2_hybrid_3cycle_smoke.yaml`

说明：

- 这条 smoke 的主要通过口径是 `cycle3_success = 1`
- 它不要求 summary 顶层的 `dump_complete_final_hold_success` 一定为 `true`

### 开始 V2.1 Stage 3 bootstrap work-skill

1. `tb-label-v2_1 --dataset-dir data/agx_teleop_v1 --scenario-id s0_truck`
2. `tb-build-workskill-v2_1 --dataset-dir data/agx_teleop_v1_v2_1_relabeled`
3. `tb-train --config testbed/configs/act_agx_v2_1_workskill_qvel.yaml`
4. `tb-train --config testbed/configs/act_agx_v2_1_workskill_gcact.yaml`
5. `tb-eval --config testbed/configs/eval_agx_v2_1_stage3_workskill_qvel.yaml`

当前锁定口径：

- `data/agx_teleop_v1/` 永远只读
- Stage 3 只创建 sibling 数据集，不覆盖 source HDF5
- `qvel` 走 live smoke
- `gcact` 只做 held-out 对照
- Stage 3 live 默认会在第一次 `qualified_dig_start` 之前先用 `ACT V1` 做 bootstrap 起手
- 当前正式 bootstrap handoff 条件是：
  - `bootstrap_end_mode = loaded_and_clear`
  - `mass_in_bucket_kg >= 300`
  - `min_distance_to_dig_area_m >= 0.25`
- 当前 Stage 3 正式 live 默认 work ckpt 为：
  - `runs/ckpts/agx_excavation_act_v2_1_workskill_qvel_e50`
- 当前 Stage 3 live 已通过单轮 `dump_complete_final_hold` success gate，
  但还没有替代 Stage 2 的 multicycle 验收线

### 用当前新录的 `teleop_v2_1_multi_raw` 数据开新的 work-skill 训练线

1. `tb-label-v2_1 --dataset-dir data/agx_teleop_v2_1_multi_raw`
2. `tb-build-workskill-v2_1 --dataset-dir data/agx_teleop_v2_1_multi_raw_relabeled`
3. `tb-train --config testbed/configs/act_agx_v2_1_multi_raw_workskill_qvel.yaml`
4. `tb-train --config testbed/configs/act_agx_v2_1_multi_raw_workskill_gcact.yaml`

当前锁定口径：

- source raw 数据集继续只读
- sibling 输出固定为：
  - `data/agx_teleop_v2_1_multi_raw_relabeled`
  - `data/agx_teleop_v2_1_multi_raw_workskill`
- 这条线的 `qvel` 是当前主训练入口
- `gcact` 继续作为 held-out 对照

### 用当前新录的 `teleop_v2_1_multi_raw` 数据做高质量 work-skill 主线

1. `tb-build-workskill-v2_1 --dataset-dir data/agx_teleop_v2_1_multi_raw_relabeled --clean-profile stage5`
2. `tb-train --config testbed/configs/act_agx_v2_1_multi_raw_workskill_clean_v2_qvel.yaml`
3. `tb-train --config testbed/configs/act_agx_v2_1_multi_raw_workskill_clean_v2_gcact.yaml`
4. `tb-eval --config testbed/configs/eval_agx_v2_1_stage5_workskill_clean_v2_qvel_3cycle_smoke.yaml`

当前锁定口径：

- 这条线优先服务“高质量 3-cycle dig / transport / dump”，不是只追 success gate
- builder 会同步写出 `summary.json`
- 当前这批数据的首轮 clean 结果是：
  - 输入 `40` 个 workskill cycles
  - 保留 `29`
  - 主要 reject reasons：
    - `far_dump_start = 7`
    - `flat_bucket_qds = 3`
    - `collision_in_cycle = 1`

### 用当前新录的 `teleop_v2_1_multi_raw` 数据做 transition feasibility

1. `tb-label-v2_1 --dataset-dir data/agx_teleop_v2_1_multi_raw`
2. `tb-build-transition-v2_1 --dataset-dir data/agx_teleop_v2_1_multi_raw_relabeled`
3. `tb-train --config testbed/configs/act_agx_v2_1_multi_raw_transition_qvel.yaml`
4. 如需先剔除过长 transition，再跑：
   `tb-build-transition-v2_1 --dataset-dir data/agx_teleop_v2_1_multi_raw_relabeled --output-dir data/agx_teleop_v2_1_multi_raw_transition_clean --max-transition-len 420`
5. clean 版训练入口：
   `tb-train --config testbed/configs/act_agx_v2_1_multi_raw_transition_clean_qvel.yaml`

当前锁定口径：

- 这条线只做 feasibility check，不直接替换 scripted transition
- transition 窗口固定取 `dump_end -> next qualified_dig_start`
- 当前先只做 `qpos + qvel` 主线，不引入在线 goal token 注入

### 开始 V2.1 Stage 5 learned transition + fallback

1. `tb-build-transition-v2_1 --dataset-dir data/agx_teleop_v2_1_multi_raw_relabeled --clean-profile stage5`
2. `tb-train --config testbed/configs/act_agx_v2_1_multi_raw_transition_clean_v2_qvel.yaml`
3. `tb-eval --config testbed/configs/eval_agx_v2_1_stage5_scripted_transition_compare_5rollouts.yaml`
4. `tb-eval --config testbed/configs/eval_agx_v2_1_stage5_learned_transition_clean_v2_compare_5rollouts.yaml`
5. `tb-eval --config testbed/configs/eval_agx_v2_1_stage5_learned_transition_clean_v2_fallback_compare_5rollouts.yaml`

当前锁定口径：

- Stage 5 只推进 learned transition，不启动 learned planner
- `RuleTaskPlanner` 继续作为默认高层 planner
- learned transition 只替换 `wait_next_dig` 子段
- fallback 只在当次 transition 内切回 scripted `wait_next_dig`
- scripted transition 可设置 `policy.transition.scripted_bucket_qpos_target: 0.0`，
  让 clear/corridor/wait 子段都以接近 0 的 bucket qpos 作为目标，便于和旧的
  corridor-band bucket curl-in 行为做 A/B rollout；`scripted_bucket_qpos_tolerance`
  会同步替代 corridor band 里旧的 bucket 区间判定。
- work-policy 主线不把 `env_state` 放进 `policy.low_dim_keys` 或
  `policy.work_low_dim_keys`。target geometry 只用于离线筛选、label、reward/QC 与
  rollout 诊断，避免把 Unity 特权状态喂给模型。
- workskill 数据可带 `/v2/step/action_loss_mask`。ACT loader 会把 mask 为 `0`
  的 timestep 当作 action-loss padding；默认 workskill builder 现在写全 `1`，
  不再按裸 bucket action 阈值自动屏蔽，因为这个阈值会误伤 digging 监督。
- eval 支持 `eval.stream_rollout_logs: true`，会在 rollout 过程中写
  `rollout_XXX.partial.jsonl`，中途停止时也能保留第 2/第 3 cycle 的逐步证据。
- compare 的主口径固定为：
  - `cycle3_success_rate`
  - `transition_timeout_rate`
  - `completed_transition_count`
- 顶层 `dump_complete_final_hold_success_rate` 只作为辅助参考

### 开始 V2.1 Stage 4 rule planner

1. `tb-eval --config testbed/configs/eval_agx_v2_1_stage4_rule_planner.yaml`
2. 如需继续压多轮，再跑：
   `tb-eval --config testbed/configs/eval_agx_v2_1_stage4_rule_planner_3cycle_smoke.yaml`
3. 如需和 learned transition 做对照，再跑：
   `tb-eval --config testbed/configs/eval_agx_v2_1_stage4_rule_planner_learned_transition_3cycle_smoke.yaml`
4. 如需验证 clean learned transition，再跑：
   `tb-eval --config testbed/configs/eval_agx_v2_1_stage4_rule_planner_learned_transition_clean_3cycle_smoke.yaml`

当前锁定口径：

- `planner.kind = rule`
- `WORK = ACT V1`
- 不启用 Stage 3 bootstrap
- 不启用在线 goal token 注入
- planner 只驱动：
  - `next_goal`
  - `next_entry_corridor`
  - belief 更新
  - `planner_trace.json` 回放

当前已完成的 Stage 4 live 结果包括：

- 第一轮 `dump_end` 后能正确 replan
- `planner_replan_count = 1`
- `planner_sector_sequence = ["left"]`
- Stage 4 当前已经固定启用：
  - soft non-mid corridor
  - `wait_next_dig = servo_reentry_pose`
- 正式主配置下的 `3` 条 live rollout 已达到：
  - `cycle1_success_rate = 1.0`
  - `cycle2_success_rate = 1.0`
  - `transition_timeout_count = 0.0`
- 正式 `3-cycle smoke` 已跑通到：
  - `planner_sector_sequence = ["left", "right"]`
  - `completed_transition_count = 2`
  - `transition_timeout_count = 0`
  - `cycle3_success_rate = 1.0`
- 当前剩余工作：
  - rule planner 规则细化
  - 与 Stage 5 learned transition 的标准化 compare
- Stage 5 当前明确不启动 learned planner；默认 planner 继续保持 `RuleTaskPlanner`

### 只想验证多轮日志而不污染正式数据目录

- 录制时用：
  - `--output-dir runs/preview/teleop_v2_1_multi_raw_preview`
- 标注时用：
  - `--output-dir runs/preview/teleop_v2_1_multi_raw_preview_relabeled`

## 6. 历史说明

旧的 phase-1 单铲 ready-anchor 配置和 `tb-label-v2` 入口已经从当前分支删除。

如果需要回看那条旧路线，请直接查历史提交，而不要再把它当成当前实现的一部分。
