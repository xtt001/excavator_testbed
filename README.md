# Excavator Testbed (Repo A — Python)

用于 AGXUnity 挖掘机任务的 Python 侧数据、训练、评测仓库。

Repo A 负责：
- AGX step-ack socket 客户端与 `AGXSimBackend`
- teleop 录制到 HDF5
- 录制回放与 QA
- 离线 ACT 训练
- live policy rollout 评测
- 基于 Unity 导出 `env_state` 的任务奖励与成功判定

三仓结构：
- Repo A — 本仓库：Python testbed
- Repo B — `AGXUnity_Excavator`：Unity / C# 场景与桥接
- Repo C — `sim-protocol`：共享协议、schema、常量、评测定义

---

## 当前状态

状态日期：`2026-04-27`

| 组件 | 实现状态 | 当前验证状态 |
|---|---|---|
| AGX 二进制 step-ack 协议客户端 | 已实现 | 已在本地 Unity 上通过 live strict smoke |
| `AGXSimBackend` | 已实现 | `GET_INFO / RESET / STEP / reward tracker` 最小 live 链路已打通 |
| HDF5 schema v1.1 | 已实现 | 支持 `timestamps`、`action_source`、`fpv`、`env_state` |
| Repo A `/v2` add-only extension | 已实现 | 当前主线为 V2.1 Stage 1 multicycle labeler、10D `goal_tokens`、phase/mode/boundary 标签，并新增细粒度 `work_stage_id` |
| 当前 AGX 任务协议 | 已实现 | 当前 target-safety 目标协议是 `env_state (13,)`，新增水平距离、高度与 dump clearance 字段；legacy `env_state (9,)` 只保留作非 target-geometry 用途 |
| `tb-record-teleop` | 已实现 | `v1` 保持兼容；当前 V2 主线已切到 `teleop_multi_raw + target_dump_count` |
| `tb-replay` | 已实现 | 支持单文件或整个目录批量回放；`fulltest` 已验证，`v1` 仍建议补一轮正式 batch QA |
| `tb-dataset-videos` | 已实现 | 从 HDF5 离线导出 MP4 视频（无需连 AGX） |
| `tb-label-v2_1` | 已实现 | 给 `teleop_multi_raw` 生成兄弟目录 relabeled 数据集并补写 Stage-1 `/v2` 标签 |
| `tb-build-workskill-v2_1` | 已实现 | 从 sibling relabeled 数据集中裁出 `qualified_dig_start -> dump_end` 的 Stage-3 workskill 数据集 |
| `tb-build-transition-v2_1` | 已实现 | 从 sibling relabeled 数据集中裁出 `dump_end -> next qualified_dig_start` 的 transition feasibility 数据集 |
| `tb-build-primitives-v2_2` | 已实现 | 从 refreshed V2.1 workskill/raw 数据集中裁出 V2.2 `dig/carry/dump/return` 四个 primitive sibling 数据集 |
| `tb-audit-target-geometry` | 已实现 | 检查数据集是否带齐 target-safety 训练所需的 4 个 target geometry 字段 |
| `tb-train` / ACT trainer | 已实现 | 已完成 `fulltest(qpos)`、`fulltest(qpos+qvel)` 与 `v1(qpos)` 三条训练线 |
| `tb-eval` | 已实现 | 已完成正式 live eval；当前支持 V2.1 Stage 1 多轮 boundary / continuity 指标 |
| `hybrid_planner_act` | 已实现 | 已接入最小 Stage 2 deploy 链；当前已在 `s0_truck` 上通过 live `2-cycle` gate，并完成一次 `3-cycle smoke` |
| `primitive_planner_act` | 已实现（V2.2 smoke 入口） | 加载 `dig/carry/dump/return` 四个 ACT checkpoint；低层只用 `qpos+qvel`，Unity target geometry 只用于 scripted switch 与日志/QC |
| Stage 3 bootstrap work-skill | 已实现 | 已完成 `agx_teleop_v1 -> v2_1_relabeled -> v2_1_workskill`，并跑通 `qvel/gcact` smoke train；`qvel e50 + loaded_and_clear bootstrap` 已通过单轮 live success gate |
| Stage 4 rule planner | 已实现（首版目标已完成） | 已把 `RuleTaskPlanner / PlannerGoal / CycleSummary / SectorBelief` 接入现有 `hybrid_planner_act`，并完成 `planner_trace.json` 回放；正式主配置下 `3` 条 live rollout 已达到 `cycle2_success_rate = 1.0`，官方 `3-cycle smoke` 也已达到 `cycle3_success_rate = 1.0` |
| rollout timestep logs | 已实现 | `tb-eval` 现可写 `rollout_XXX.jsonl / summary / manifest` |
| `tb-dataset-qc` | 已实现 | 可写 `summary.json / episodes.csv / QC plots` |
| demo-level metadata | 已实现 | `tb-record-teleop` 支持 `operator_id / session_id / notes / config snapshot` |
| MuJoCo backend | 保留 | 仅作 legacy / 对照，不是当前主路径 |

当前重点：
- 冻结 `data/agx_teleop_v1`、`act_agx_v1.yaml`、`eval_agx_v1.yaml` 作为当前业务 baseline
- 用 `teleop_v2_1_multi_raw -> tb-label-v2_1 -> eval_agx_v2_1_stage1` 跑通 V2.1 Stage 1 多轮数据与评测链路
- 用 `eval_agx_v2_1_stage2_hybrid.yaml` 继续回归 Stage 2 最小 hybrid 闭环，并用 `eval_agx_v2_1_stage2_hybrid_3cycle_smoke.yaml` 做 3-cycle smoke
- 用 `agx_teleop_v1 -> agx_teleop_v1_v2_1_relabeled -> agx_teleop_v1_v2_1_workskill` 作为当前 Stage 3 bootstrap work-skill 链
- Stage 4 的第一版 rule planner 已经接入 Stage-2 稳线并完成首版目标；当前重点转为更大样本的多 rollout 回归与规则细化
- `/v2/step/work_stage_id` 已接入离线 relabel，用来标出 `entry_to_bite / first_bite / rebite_recovery / carry / approach_dump / dump`
- 旧的 `ready-anchor / dump_plus_ready / 单铲 ready-return` 已从当前主线删除，只保留在历史提交中
- Stage 3 当前存在一个 deploy-only bootstrap handoff：
  - `reset -> loaded_and_clear` 先由 `ACT V1` 起手
  - `loaded_and_clear -> dump_end` 再切给 Stage-3 work policy
  - 这条逻辑仅作为 live 兼容层存在，不进入协议、`/v2` schema、planner 语义或默认训练口径
- V2.2 当前新增四 primitive smoke 线：
  - builder: `tb-build-primitives-v2_2`
  - 当前 ownership probe root:
    `data/agx_v2_2_4primitives_ownership_boundary_260427_1ep`
  - 当前 carry/dump 训练 mix:
    `data/agx_v2_2_4primitives_ownership_history_probe_leftboost_260427`
    （旧 boundary rule baseline；新版 middle-handoff builder 需要用 16-field
    bed geometry 数据重建）
  - 当前 ownership smoke eval:
    `testbed/configs/eval_agx_v2_2_4primitives_ownership_leftboost_qvel_3cycle_smoke.yaml`
  - phase boundary source of truth:
    `docs/v2_2_4primitives/phase_boundaries.md`
  - ownership 定义：`carry` 只负责 loaded transport；`dump` 负责 move to top
    of target、alignment、release 和 post-dump hold
  - `dump` 起点固定为 `first approach_dump stage`；如果 stable curl-out 早于
    `approach_dump`，builder 会 reject 该 carry/dump window，避免把边界不清的
    teleop 数据混入新版 ownership 训练
  - 2026-04-28 middle-handoff probe 已验证：旧 refreshed sample 和此前
    ownership probe 即使刷新成 16-field geometry，也只接受 `dig`，`carry/dump`
    全部 reject；下一批训练前需要按 phase boundary 文档补录新数据
  - planner 在 `dump_done` 后保持 dump skill `30` step，再切 return；当前 smoke
    关闭即时 `dump_end` boundary 切换，避免 temporal aggregation 边界上 return
    动作把刚落入车斗的土带出
  - live eval 入口：`eval_agx_v2_2_4primitives_qvel_3cycle_smoke.yaml`
  - 首轮 reset 仍可配置 `bootstrap_policy` 到 `loaded_and_clear`，但 primitive 执行阶段不启用 fallback
---

## 概念框架

```text
                           Repo B: Unity / AGX 场景
                    (物理、场景对象、HUD、step-ack server)
                                      │
                                      │ GET_INFO / RESET / STEP
                                      ▼
                    testbed/backends/agx/protocol.py + AGXSimBackend
                                      │
          ┌───────────────────────────┼───────────────────────────┐
          │                           │                           │
          ▼                           ▼                           ▼
   testbed/actions/            testbed/tasks/logic/          testbed/data/
 (joystick / keyboard)     (reward, success, phase)   (record, replay, HDF5, dataset, QC)
          │                           │                           │
          └──────────────┬────────────┴────────────┬──────────────┘
                         │                         │
                         ▼                         ▼
                 testbed/policies/            testbed/eval/
              (ACT, dummy, future plugins)  (rollout, metrics, video)
                         │                         │
                         └──────────────┬──────────┘
                                        ▼
                                CLI / Runner 层
      tb-record-teleop / tb-replay / tb-dataset-videos / tb-dataset-qc / tb-train / tb-eval
                                        │
                                        ▼
                     testbed/configs/ + docs/training_setup.md
                  (训练 setup、实验记录规则、运行参数，不改核心接口)
```

这个框架里真正的插件边界是：
- `backends/`：环境接入层
- `actions/`：teleop 输入层
- `policies/`：策略层
- `eval/`：评测层

而训练 setup、split、run metadata、实验记录这些内容，应该放在：
- `testbed/configs/`
- [testbed/configs/README.md](/home/pingfan/PACT/excavator_testbed/testbed/configs/README.md)
- [docs/training_setup.md](/home/pingfan/PACT/excavator_testbed/docs/training_setup.md)
- `runs/...` 下的产物与元数据

也就是说，它们属于“实验管理层”，不是“核心接口层”。

如果你想快速弄清楚每个 YAML 的角色、入口命令和当前推荐用法，直接看 [testbed/configs/README.md](/home/pingfan/PACT/excavator_testbed/testbed/configs/README.md)。

---

## 当前任务定义

当前主任务：`agx_excavation_teleop`

任务范围：
- 固定工位 / stationary digging
- 4 维机械臂动作，不含行走底盘
- DigArea good-start 门控
- target hard collision 监控

动作向量：

```text
[swing_speed_cmd, boom_speed_cmd, stick_speed_cmd, bucket_speed_cmd]
```

观测：
- `qpos (4,)`：`[swing, boom, stick, bucket]`，归一化位置
- `qvel (4,)`：`[swing, boom, stick, bucket]`，速度
- `images["fpv"]`：`(H, W, 3)`，`uint8`
- `env_state (13,)`：

```text
[
  mass_in_bucket_kg,
  excavated_mass_kg,
  mass_in_target_box_kg,
  deposited_mass_in_target_box_kg,
  min_distance_to_target_m,
  target_hard_collision_count,
  target_contact_max_normal_force_n,
  min_distance_to_dig_area_m,
  bucket_depth_below_dig_area_plane_m,
  target_horizontal_distance_m,
  bucket_height_above_target_rim_m,
  bucket_over_target_footprint_mask,
  dump_clearance_ok_mask,
  bucket_bed_relative_x_m,
  bucket_bed_relative_z_m,
  bucket_bed_footprint_outside_distance_m
]
```

target-safety 相关逻辑使用显式 target geometry 字段：
`min_distance_to_target_m` 仍会记录为 legacy scalar metric，但不会被当作
`target_horizontal_distance_m` 或 clearance 的 fallback。
V2.2 的 Unity bridge 额外输出 bucket proxy center 在 truck-bed local frame
下的 `bucket_bed_relative_x_m/z_m`，以及到 bed footprint 的
`bucket_bed_footprint_outside_distance_m`；`bucket_over_target_footprint_mask`
现在表示 bucket proxy 位于 truck-top 可倒料区域上方，复用 TruckBed 已有
clearance tolerance，不再要求 strict OBB footprint 相交。
`bucket_bed_footprint_outside_distance_m` 是 unsigned proximity，只说明 bucket
proxy 离 truck-bed footprint 有多近；它不能区分 tail/middle/front。需要表达
“不要在车斗尾部交接”时，必须同时使用 signed
`bucket_bed_relative_x_m/z_m` window。
其中 `dump_clearance_ok_mask` 是 Unity 输出的 clearance source of truth：
TruckBed 水平方向允许目标侧配置的 dump 容差，但垂直方向仍要求
`bucket_height_above_target_rim_m >= 0.0`，也就是桶底必须在车厢 rim/top
之上。

奖励 / 成功语义：
- `loading`：只有满足 DigArea good-start 后才开始给正向装载奖励
- `approaching_target`：载荷存在且 `target_horizontal_distance_m` 有效时，朝目标水平接近给奖励
- `depositing`：目标 retained mass 开始增长时给奖励
- `hard_target_collision`：`target_hard_collision_count` 在本步增加时给固定惩罚
- `success`：`deposited_mass_in_target_box_kg >= 100 kg` 且连续保持 `25` 步

兼容性：
- Repo A 仍可读取旧 `5D/7D env_state` 数据
- 但旧数据只用于兼容或离线 smoke，不应再作为当前任务的标准训练集

---

## Quick Start

### 1. 安装

```bash
conda activate aloha
pip install -e ".[dev]"
```

### 2. 先验证 live 协议

```bash
python scripts/agx_smoke.py --host 127.0.0.1 --port 5057 --steps 200
python scripts/agx_smoke.py --host 127.0.0.1 --port 5057 --steps 200 --strict
```

这一步必须先过。

如果这里在 `GET_INFO` 超时：
- 不要继续跑 `tb-record-teleop`
- 不要继续跑 `tb-eval`
- 先回到 Repo B / Unity 修 step-ack 响应

### 3. 录制新的 9D 数据

建议不要直接覆盖旧样本目录，先写到新目录：

```bash
tb-record-teleop \
  --config testbed/configs/teleop_v1.yaml \
  --input joystick \
  --num-episodes 20 \
  --operator-id alice \
  --session-id baseline-v1 \
  --notes "first rerecord batch with 300kg retained-mass stop" \
  --output-dir data/agx_teleop_v1
```

当前 `tb-record-teleop` 默认会在两种情况下结束并保存当前 episode：
- 达到任务 success
- 达到 `task.max_steps`

当前推荐录制配置是 [testbed/configs/teleop_v1.yaml](/home/pingfan/PACT/excavator_testbed/testbed/configs/teleop_v1.yaml)：
- 输出目录默认写到 `data/agx_teleop_v1`
- 录制期 success 切到 `dump_complete_final_hold`
- `deposited_mass_in_target_box_kg >= 300kg`
- `mass_in_bucket_kg <= 100kg`
- 连续保持 `25` 步
- 成功后再继续录制 `50` 步尾段，保留 dump 后半段和收尾动作

V2.1 Stage 1 多轮 raw 录制入口：

```bash
tb-record-teleop --config testbed/configs/teleop_v2_1_multi_raw.yaml --num-episodes 10
tb-label-v2_1 --dataset-dir data/agx_teleop_v2_1_multi_raw
```

这条线的关键边界是：
- 录制停止条件改成“第 `3` 次有效 `dump_end`”
- 当前默认 `task.max_steps = 4000`
- 达到第 `3` 次 `dump_end` 后继续录 `teleop.post_success_tail_steps = 50` 步，保留 terminal dump 的 post-step observation
- 不再要求回 fixed ready pose，也不要求回 ready-anchor
- `scenario_id` 仍会透传到 Repo B reset preset
- `/v2` 标签默认离线生成到兄弟目录副本，不原地改写 raw 数据
- 当前主线的 `/v2` 语义已经切到 multicycle 事件体系：`qualified_dig_start / dump_start / dump_end / boundary_mask`

V2.1 Stage 2 最小 hybrid live eval 入口：

```bash
tb-eval --config testbed/configs/eval_agx_v2_1_stage2_hybrid.yaml
tb-eval --config testbed/configs/eval_agx_v2_1_stage2_hybrid_3cycle_smoke.yaml
```

这条线当前固定采用：

- `ACT V1 checkpoint` 负责 `WORK`
- scripted corridor servo 负责 `TRANSITION`
- fixed sequence planner 固定为 `mid -> mid -> mid`
- 当前 live 默认 `scenario_id = s0_truck`
- 主配置 `target_cycle_gate = 2`
- `3-cycle` 配置只作 smoke，默认 `episode_len = 8000`

V2.1 Stage 3 bootstrap work-skill 入口：

```bash
tb-label-v2_1 --dataset-dir data/agx_teleop_v1 --scenario-id s0_truck
tb-build-workskill-v2_1 --dataset-dir data/agx_teleop_v1_v2_1_relabeled
tb-train --config testbed/configs/act_agx_v2_1_workskill_qvel.yaml
tb-train --config testbed/configs/act_agx_v2_1_workskill_gcact.yaml
tb-eval --config testbed/configs/eval_agx_v2_1_stage3_workskill_qvel.yaml

# current multiround raw -> workskill training line
tb-label-v2_1 --dataset-dir data/agx_teleop_v2_1_multi_raw
tb-build-workskill-v2_1 --dataset-dir data/agx_teleop_v2_1_multi_raw_relabeled
tb-train --config testbed/configs/act_agx_v2_1_multi_raw_workskill_qvel.yaml
tb-train --config testbed/configs/act_agx_v2_1_multi_raw_workskill_gcact.yaml

# high-quality workskill line on current multiround raw demos
tb-build-workskill-v2_1 --dataset-dir data/agx_teleop_v2_1_multi_raw_relabeled --clean-profile stage5
tb-train --config testbed/configs/act_agx_v2_1_multi_raw_workskill_clean_v2_qvel.yaml
tb-train --config testbed/configs/act_agx_v2_1_multi_raw_workskill_clean_v2_gcact.yaml
tb-eval --config testbed/configs/eval_agx_v2_1_stage5_workskill_clean_v2_qvel_3cycle_smoke.yaml
tb-train --config testbed/configs/act_agx_v2_1_multi_raw_new_workskill_clean_v2_qvel.yaml
tb-eval --config testbed/configs/eval_agx_v2_1_stage5_workskill_clean_v2_qvel_newdata_3cycle_smoke.yaml
tb-build-workskill-v2_1 --dataset-dir data/agx_teleop_v2_1_multi_raw_new_relabeled --clean-profile stage5_strict
tb-train --config testbed/configs/act_agx_v2_1_multi_raw_new_workskill_clean_v3_qvel.yaml
tb-eval --config testbed/configs/eval_agx_v2_1_stage5_workskill_clean_v3_qvel_newdata_3cycle_smoke.yaml
tb-build-workskill-v2_1 --dataset-dir data/agx_teleop_v2_1_multi_raw_relabeled --clean-profile stage5_strict
tb-train --config testbed/configs/act_agx_v2_1_multi_raw_all_workskill_clean_v3_qvel.yaml
tb-eval --config testbed/configs/eval_agx_v2_1_stage5_workskill_clean_v3_qvel_alldata_3cycle_smoke.yaml
# current v3-only target-safe quality-mix retrain candidate:
# old clean_v3 + 2604241251 terminal-fix clean_v3, with near_dump_start removed
tb-train --config testbed/configs/act_agx_v2_1_multi_raw_all_workskill_clean_v3_qualitymix_qvel.yaml
tb-eval --config testbed/configs/eval_agx_v2_1_stage5_workskill_clean_v3_qualitymix_qvel_3cycle_smoke.yaml
# v3b / v4 are currently diagnostic-only; they are too strict for the main WORK train set.

# note: the combined strict clean_v3 workskill line uses episode_len=1200
# note: sector relabeling now uses dig-area calibrated qds swing bins:
#       leftmost ~= 0.43, mid ~= 0.50, rightmost ~= 0.56
#       swing < 0.4733 -> left, 0.4733 <= swing < 0.5167 -> mid, >= 0.5167 -> right
#       transition corridor naming is now aligned to the same physical convention;
#       legacy mirrored left/right band configs are auto-normalized at runtime
#       the rebuilt clean_v3 training set is no longer all-mid; current split is
#       left=15, mid=31, right=9 over 55 total cycles
# note: keep clean_v3 as the current main training profile; v3b/v4 are only
# diagnostic filters for checking early dump / severe pre-target spill.
# note: clean_v3 now requires explicit target geometry fields for target-safe
#       filtering. Legacy min_distance_to_target_m is not used as a fallback.
#       target_horizontal_distance_m < 0.35 -> near_dump_start. This removes
#       close-call low-boom dump examples that can become hard target collisions
#       in rollout.
#       Current target-safe qualitymix has 74 cycles: left=18, mid=40, right=16.
# note: the target-safe smoke eval also enables a live WORK safety guard:
#       if loaded, target_horizontal_distance_m < 0.45, and dump clearance is
#       not ok, cap bucket dump action to -0.15 and command at least +0.08 boom
#       raise before continuing.
#       dump clearance comes from Unity's dump_clearance_ok_mask; TruckBed may
#       use horizontal tolerance, but vertical clearance still requires
#       bucket_height_above_target_rim_m >= 0.0.
#       run tb-audit-target-geometry before using an old dataset for target-safe
#       workskill training.
# note: current target_dump_count recording keeps a 50-step terminal tail after
# the online dump_end event; offline relabel still recovers legacy no-tail raws
# from metadata so old final cycles are not silently dropped.

# transition feasibility line on current multiround raw demos
tb-label-v2_1 --dataset-dir data/agx_teleop_v2_1_multi_raw
tb-build-transition-v2_1 --dataset-dir data/agx_teleop_v2_1_multi_raw_relabeled
tb-train --config testbed/configs/act_agx_v2_1_multi_raw_transition_qvel.yaml
```

这条线当前锁定为：

- `data/agx_teleop_v1/` 只读
- 所有 Stage 3 产物都写到 sibling 数据集
- 当前高质量 workskill 主线已经接入：
  - `data/agx_teleop_v2_1_multi_raw_workskill_clean_v2`
  - 当前首轮 clean 结果：`40 -> 29` cycles
  - 当前主要 reject reasons：
    - `far_dump_start = 7`
    - `flat_bucket_qds = 3`
    - `collision_in_cycle = 1`
- `qvel` 负责 live smoke
- `gcact` 只做 held-out 对照
- Stage 3 live 现在会在第一次 `qualified_dig_start` 之前先用 `ACT V1` 做 bootstrap 起手，避免把 post-dig-start work-skill 模型直接接到 reset 初态
- 当前正式 handoff 条件为 `loaded_and_clear`：
  - `mass_in_bucket_kg >= 300`
  - `min_distance_to_dig_area_m >= 0.25`
- 当前正式 Stage 3 live work checkpoint 为：
  - `runs/ckpts/agx_excavation_act_v2_1_workskill_qvel_e50`

V2.1 Stage 4 rule planner 入口：

```bash
tb-eval --config testbed/configs/eval_agx_v2_1_stage4_rule_planner.yaml
tb-eval --config testbed/configs/eval_agx_v2_1_stage4_rule_planner_3cycle_smoke.yaml
tb-eval --config testbed/configs/eval_agx_v2_1_stage4_rule_planner_learned_transition_3cycle_smoke.yaml
tb-eval --config testbed/configs/eval_agx_v2_1_stage4_rule_planner_learned_transition_clean_3cycle_smoke.yaml
```

这条线当前固定采用：

- `policy.class = hybrid_planner_act`
- `planner.kind = rule`
- `WORK = ACT V1`
- learned transition 对照线只替换 `wait_next_dig` 子段，不改变 Stage-4 的 scripted `clear_target -> corridor_align`
- scripted transition 可通过 `policy.transition.scripted_bucket_qpos_target: 0.0`
  让 clear/corridor/wait 子段都把 bucket 姿态保持在接近 0，避免 transition
  期间把 bucket 强制 curl-in 到 corridor band 的旧 bucket 中心；对应的
  `scripted_bucket_qpos_tolerance` 会同步用于 corridor 对齐判定。
- 如需先清掉过长 transition 样本，再构建 sibling clean 数据集：

```bash
tb-build-transition-v2_1 \
  --dataset-dir data/agx_teleop_v2_1_multi_raw_relabeled \
  --output-dir data/agx_teleop_v2_1_multi_raw_transition_clean \
  --max-transition-len 420
tb-train --config testbed/configs/act_agx_v2_1_multi_raw_transition_clean_qvel.yaml
```
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
- 当前剩余工作是：
  - rule planner 规则细化
  - 与 Stage 5 learned transition 的标准化 compare
- 这条 bootstrap handoff 仅是部署兼容层；进入 Stage 4 后，planner / belief / cycle summary 仍必须在语义上独立于 bootstrap 存在

V2.1 Stage 5 learned transition + fallback 入口：

```bash
tb-build-transition-v2_1 \
  --dataset-dir data/agx_teleop_v2_1_multi_raw_relabeled \
  --clean-profile stage5
tb-train --config testbed/configs/act_agx_v2_1_multi_raw_transition_clean_v2_qvel.yaml
tb-eval --config testbed/configs/eval_agx_v2_1_stage5_scripted_transition_compare_5rollouts.yaml
tb-eval --config testbed/configs/eval_agx_v2_1_stage5_learned_transition_clean_v2_compare_5rollouts.yaml
tb-eval --config testbed/configs/eval_agx_v2_1_stage5_learned_transition_clean_v2_fallback_compare_5rollouts.yaml
```

这条线当前锁定为：

- Stage 5 只推进 learned transition，不启动 learned planner
- 默认高层 planner 继续是 `RuleTaskPlanner`
- learned transition 只替换 `wait_next_dig` 子段
- fallback 允许在当次 transition 内切回 scripted `wait_next_dig`
- `transition_clean_v2` builder 会输出 `summary.json`，当前 reject reasons 至少包括：
  - `overlong_transition_len`
  - `late_qds_failure`
  - 高 `pause_ratio` 的明显犹豫样本
- compare 的主口径固定为：
  - `cycle3_success_rate`
  - `transition_timeout_rate`
  - `completed_transition_count`
- 同时 evaluator 会输出动作质量指标，避免只看 success gate：
  - `spill_before_target_count`
  - `unsafe_target_distance_count`
  - `hard_target_collision_count`
  - `flat_bucket_qds_count`
  - `peak_bucket_depth_mean`
- `far_dump_start_count`
- `near_dump_start_count`
  - `carry_efficiency_proxy_mean`
  - `high_residual_bucket_mass_count`
  - `dig_area_escape_cycle_count`
  - `quality_issue_count`
- learned planner 只有在 transition 和 work 两层都稳定后才进入下一阶段

只想测试多轮 raw 录制而不污染正式数据目录时：

```bash
tb-record-teleop --config testbed/configs/teleop_v2_1_multi_raw.yaml \
  --output-dir runs/preview/teleop_v2_1_multi_raw_preview \
  --num-episodes 1 \
  --notes "preview-only"
```

键盘 fallback：

```bash
tb-record-teleop \
  --config testbed/configs/teleop_v1.yaml \
  --input keyboard \
  --num-episodes 1 \
  --output-dir data/agx_teleop_v1
```

### 4. 回放 QA

```bash
# 单个 episode（需要连 AGX）
tb-replay \
  --episode data/agx_teleop_v1/episode_0.hdf5 \
  --config testbed/configs/teleop_v1.yaml \
  --save-video

# 批量回放整个目录（需要连 AGX）
tb-replay \
  --episode data/agx_teleop_v1/ \
  --config testbed/configs/teleop_v1.yaml \
  --save-video

# 用旧 episode 的 action 序列在当前 Unity 中重新采集 HDF5
tb-replay \
  --episode data/agx_teleop_v2_1_multi_raw/episode_0.hdf5 \
  --config testbed/configs/teleop_v2_1_multi_raw.yaml \
  --record-output-dir data/agx_teleop_v2_1_multi_raw_replayed_current
```

使用 `--record-output-dir` 做数据刷新时，`tb-replay` 会读取 teleop config
里的 `post_success_tail_steps`，当前 V2.1 默认是 `50` 步，并在 source
actions 结束后追加 zero-action hold tail。这样旧数据刷新成 13D
`env_state` 时不会把 terminal dump 的 plateau / `dump_end` 观察截断。
需要临时覆盖时可用 `--post-tail-steps <N>`。

### 4.1 数据质检

```bash
tb-dataset-qc \
  --dataset-dir data/agx_teleop_v1
```

如果目录里混有损坏或未完整写完的 `episode_*.hdf5`，`tb-dataset-qc` 现在会跳过这些文件，并把它们记录到 `summary.json` 里的 `unreadable_episode_ids` / `unreadable_episode_errors`。

### 4.2 离线导出视频

从 HDF5 中直接导出 FPV 视频，不需要连接 AGX：

```bash
# 导出整个目录（默认输出到 <dataset_dir>/videos/）
tb-dataset-videos data/agx_teleop_v1/

# 指定输出目录
tb-dataset-videos data/agx_teleop_v1/ -o runs/videos/v1

# 只导出特定 episode
tb-dataset-videos data/agx_teleop_v1/ --indices 0 3 5 10

# 单个 episode
tb-dataset-videos data/agx_teleop_v1/episode_0.hdf5
```

### 5. 训练

当前业务 baseline 直接使用 [testbed/configs/act_agx_v1.yaml](/home/pingfan/PACT/excavator_testbed/testbed/configs/act_agx_v1.yaml)。

```bash
tb-train --config testbed/configs/act_agx_v1.yaml
```

这份配置默认对应：
- 数据集 `data/agx_teleop_v1`
- `30` 条 rerecord success demo
- `qpos` 输入
- `dump_complete_final_hold` 主口径

当前训练器还内置了几项提速设置：
- 默认基线仍可用 `num_workers: 0` 保守启动；当前 clean_v3 主训练线和过严诊断线均可按需提升 `num_workers`、`persistent_workers`、`prefetch_factor` 来缓解 HDF5 I/O 瓶颈
- `val_every: 5`，不是每个 epoch 都跑完整验证
- `save_latest_every: 10`，不是每个 epoch 都刷一次 latest checkpoint
- `amp: true` + `amp_dtype: auto`，在 CUDA 上自动选 `bf16/fp16`

当前训练器也已经支持“成功即提前结束”的变长 demo：
- 归一化统计会按所有 episode 的时间维拼接计算
- DataLoader 会按配置里的 `task.episode_len` 统一 pad action / `is_pad`
- 所以像 `data/agx_teleop_fulltest` 和 `data/agx_teleop_v1` 这种 success-truncated 数据，都可以直接训练

如果你要复现第一轮 `fulltest(qpos)` 基线，可以直接用：

```bash
tb-train --config testbed/configs/act_agx_fulltest.yaml
```

如果你要复现 `fulltest` 上的 `qpos+qvel` 对照实验，可以直接用：

```bash
tb-train --config testbed/configs/act_agx_fulltest_qvel.yaml
```

训练启动后，当前会自动在 `ckpt_dir` 下写出：
- `train_val_split.yaml`
- `resolved_config.yaml`
- `run_metadata.json`

其中：
- `train_val_split.yaml` 用来冻结 train/val episode split
- `resolved_config.yaml` 记录本次 run 的实际训练配置
- `run_metadata.json` 记录命令、环境、Repo A git 信息和训练结果摘要

快速 smoke：

```bash
tb-train \
  --config testbed/configs/act_agx_smoke.yaml \
  --epochs 5
```

### 6. 评测

```bash
tb-eval --config testbed/configs/eval_agx_smoke.yaml
tb-eval --config testbed/configs/eval_agx_v1.yaml
```

如果你当前训练的是
`testbed/configs/act_agx_fulltest.yaml`
这条 baseline，对应直接评测：

```bash
tb-eval --config testbed/configs/eval_agx_fulltest.yaml
```

如果你训练的是新的 `teleop_v1` / `act_agx_v1` 这批数据，对应直接评测：

```bash
tb-eval --config testbed/configs/eval_agx_v1.yaml
```

如果你训练的是 `qpos+qvel` 对照版本，对应评测配置是：

```bash
tb-eval --config testbed/configs/eval_agx_fulltest_qvel.yaml
```

`tb-eval` 是 live rollout 命令，需要 Unity 在目标 host/port 上正确响应 step-ack。
当前评测目录除 `metrics.json / results.csv / videos/` 外，还会额外写出：
- `rollout_manifest.json`
- `rollouts/rollout_XXX.jsonl`
- `rollouts/rollout_XXX_summary.json`
- `eval_run_metadata.json`
- `eval_resolved_config.yaml`

当前 AGX eval 现在会同时记录五套 success 口径：
- `legacy_any`：历史口径，只要 rollout 中任意时刻曾满足 mission success
- `final_hold`：episode 结束时仍满足 retained-mass hold 条件
- `strict_final_hold`：在 `final_hold` 基础上，还要求指定失败项计数不超过阈值
- `dump_complete_final_hold`：推荐主口径，episode 结束时既要保住足够多的 retained mass，也要把 bucket 余土降到阈值以下
- `strict_dump_complete`：在 `dump_complete_final_hold` 基础上，再要求指定失败项计数不超过阈值

当前推荐配置默认把主 success mode 设为 `dump_complete_final_hold`，并使用：
- `mass_thresh = 300.0 kg`
- `residual_bucket_mass_thresh = 100.0 kg`
- `hold_steps = 25`
- 3-cycle smoke 这类带 `target_cycle_gate` 的 eval，可以设置 `eval.target_cycle_gate_terminal_hold_steps = 25`，让第 N 次 `dump_end` 后继续跑完末尾 hold，而不是立刻截断 dump-complete 判定
- strict 默认阻断项：
  - `hard_target_collision = 0`
  - `spill_before_target = 0`

也就是说：
- `metrics.json` / `results.csv` 里的主 `success_rate` 现在对应 `dump_complete_final_hold`
- `rollout_manifest.json` 里会额外保留
  `legacy_success / final_hold_success / strict_final_hold_success / dump_complete_final_hold_success / strict_dump_complete_success`

当前 `tb-eval` 还会在终端里输出 rollout 进度，默认类似：

```text
  rollout 000  step 50 / 1000
```

这个频率可通过 `eval.step_log_interval` 调整，默认是 `50`。

### 6.1 实验记录

训练 run 现在会自动写：
- `train_val_split.yaml`
- `resolved_config.yaml`
- `run_metadata.json`

评测 run 现在会自动写：
- `eval_resolved_config.yaml`
- `eval_run_metadata.json`
- `metrics.json`
- `results.csv`
- `rollout_manifest.json`

如果你要把某一轮 train + eval + dataset QC 汇总成可比较的实验记录，再运行：

```bash
tb-experiment-record \
  --train-ckpt-dir runs/ckpts/agx_excavation_act_v1 \
  --eval-results-dir runs/eval/agx_excavation_act_v1/results \
  --notes "rerecord v1 baseline on 30 success demos"
```

它会写出：
- `runs/experiments/<experiment_name>/experiment_record.json`
- `runs/experiments/<experiment_name>/experiment_record.md`
- `runs/experiments/experiment_registry.csv`

---

## 数据目录说明

当前工作区里的 `data/agx_teleop/` 不是“当前新任务的标准数据集”。

它目前的用途更接近：
- 旧样本兼容性检查
- 离线 smoke 训练
- 数据 schema 向后兼容验证

已知现状：
- 这个目录里的现有示例 episode 仍然是旧 `env_state` 版本
- 不是当前 DigArea / collision / 9D 任务的正式训练数据

因此，当前推荐流程是：
- 新数据录到 `data/agx_teleop_v1/` 或其他新目录
- 在训练配置中显式切换 `dataset_dir`
- 等新数据稳定后，再决定是否替换默认目录

---

## 当前剩余补齐清单

下面这些是当前最值得补的事项，按优先级排序：

1. 给 `data/agx_teleop_v1/` 补一轮正式 `tb-replay` QA  
   现在训练、评测和 QC 都已经跑过，唯一还缺的是针对正式 `v1` 数据集的回放一致性证据。

2. 把 `strict_dump_complete` 下的失败模式整理出来  
   `v1(qpos)` 已经在主口径下 `10/10` 成功，当前真正卡住的是严格口径下的 `spill_before_target`。

3. 明确 `qvel` 在后续主线里的位置  
   当前 `qvel` 对照已经在 `fulltest` 上给出正向结果，下一步需要判断它是继续作为对照线保留，还是迁移到 `v1` 数据集上继续验证。

这些补齐项不会破坏 testbed 的 clean plug-support 结构，只要遵守一个原则：
- 不把实验记录逻辑硬塞进 `Policy` / `Backend` 的抽象接口
- 把它们放在 config、runtime metadata、data tooling、eval output 这些外围层

换句话说：
- “环境怎么接” 仍然归 `backends/`
- “策略怎么插” 仍然归 `policies/`
- “实验怎么记录与分析” 归 `configs/ + docs/ + runs/`

---

## 推荐验证顺序

```bash
conda activate aloha

# 1) 协议检查
python scripts/agx_smoke.py --host 127.0.0.1 --port 5057 --steps 200 --strict

# 2) 录制或复查 v1 数据
tb-record-teleop --config testbed/configs/teleop_v1.yaml --input joystick --num-episodes 1 --output-dir data/agx_teleop_v1

# 3) 离线导出视频 + 数据质检
tb-dataset-videos data/agx_teleop_v1/
tb-dataset-qc --dataset-dir data/agx_teleop_v1

# 3b) 可选：通过 AGX 批量回放 QA（需要连 AGX）
tb-replay --episode data/agx_teleop_v1/ --config testbed/configs/teleop_v1.yaml --save-video

# 3c) 可选：用已有动作重放并重新记录当前 Unity 观测/env_state
tb-replay --episode data/agx_teleop_v1/episode_0.hdf5 --config testbed/configs/teleop_v1.yaml --record-output-dir data/agx_teleop_v1_replayed_current

# 4) 训练当前业务 baseline
tb-train --config testbed/configs/act_agx_v1.yaml

# 5) live eval
tb-eval --config testbed/configs/eval_agx_v1.yaml
```

---

## 与 Unity 联调

编辑 [testbed/configs/teleop_v1.yaml](/home/pingfan/PACT/excavator_testbed/testbed/configs/teleop_v1.yaml)：

```yaml
agx:
  host: "192.168.x.x"
  port: 5057
  reset_terrain: true
  reset_pose: true
```

当前 reset 预期：
- `reset_pose: true`
- `reset_terrain: true`

Unity 侧需要保证：
- `GET_INFO` 能及时返回
- `RESET` 后第一帧可被 Python 同步取回
- terrain reset 与 episode reset 只走一条清晰路径

---

## 文档入口

当前权威文档：
- 本 README：仓库说明、当前状态、quick start
- [docs/current_status_and_plan.md](/home/pingfan/PACT/excavator_testbed/docs/current_status_and_plan.md)：详细的“已开发内容 / 当前 smoke 验证结果 / 下一步计划 / 为什么要补失效归因能力”
- [docs/v2_1_failure_retrospective.md](/home/pingfan/PACT/excavator_testbed/docs/v2_1_failure_retrospective.md)：V2.1 初期多轮失败原因、script/human transition gap、goal-conditioned ACT 与 V2.2 修复复盘
- [docs/training_setup.md](/home/pingfan/PACT/excavator_testbed/docs/training_setup.md)：训练配置字段、实验记录项、失效归因时应保留的证据链

保留文档：
- `docs/技术可行性评估与顶层架构设计.md`：技术路线与顶层架构评估
- `docs/工程机械_土堆颗粒模拟调研.md`：土体 / 颗粒模拟调研

---

## Repo Layout

```text
testbed/
  backends/
    agx/                  AGX 协议与 backend
    mujoco/               legacy MuJoCo backend
  actions/                joystick / keyboard action source
  data/                   HDF5 schema, IO, recorder, dataset
  eval/                   eval suite, metrics, video, task defs
  policies/               ACT, dummy, diffusion stub
  runtime/                runner, train/eval helpers
  configs/                teleop/train/eval configs
  cli/                    tb-record-teleop, tb-replay, tb-dataset-videos, tb-dataset-qc, tb-train, tb-eval, tb-experiment-record

docs/
  current_status_and_plan.md
  技术可行性评估与顶层架构设计.md
  工程机械_土堆颗粒模拟调研.md
```

常用产物路径：
- `data/agx_teleop_v1/episode_N.hdf5`：当前推荐的新任务录制目录
- `runs/ckpts/agx_excavation_act_smoke/`：smoke checkpoint
- `runs/ckpts/agx_excavation_act_v0/`：主训练 checkpoint
- `runs/eval/...`：评测结果与视频

---

## HDF5 Schema v1.1

```text
episode_N.hdf5
├── metadata/
├── observations/
│   ├── qpos            (T, 4) float32
│   ├── qvel            (T, 4) float32
│   ├── env_state       (T, M) float32
│   └── images/fpv      (T, H, W, 3) uint8
├── action              (T, 4) float32
├── rewards             (T,) float32
├── timestamps/
│   ├── step_id         (T,) int64
│   └── step_ns         (T,) int64
└── action_source/
    ├── type            (T,) str
    └── id              (T,) str
```

schema 规则：
- add-only
- 不重命名旧字段
- 新必需字段才 bump version

当前 HDF5 里“实际记录”的内容可以分成 4 类：

1. 训练主数据
- `observations/qpos`
- `observations/images/<camera>`
- `action`

2. 任务分析与回放辅助
- `observations/qvel`
- `observations/env_state`
- `rewards`
- `timestamps/step_id`
- `timestamps/step_ns`
- `action_source/type`
- `action_source/id`

3. 录制上下文 metadata
- `task_name`
- `param_version`
- `timestamp`
- `seed`
- `protocol_version`
- `control_hz`
- `dt`
- `action_semantics`
- `camera_names`
- `image_format`
- `camera_width`
- `camera_height`
- `camera_fps`
- `camera_row_order`
- `action_order`
- `qpos_order`
- `qvel_order`
- `env_state_order`

4. demo-level metadata
- `episode_id`
- `operator_id`
- `session_id`
- `notes`
- `teleop_input`
- `record_config_path`
- `record_config_yaml`
- joystick / keyboard 录制参数快照

一个关键点：
- 当前 ACT 模仿学习训练 **不会** 直接把 `rewards`、`task_success` 当作监督信号
- 当前 ACT data loader 实际吃的是：
  - `qpos`
  - `images`
  - `action`
  - 可选 low-dim：`qvel`、`goal_tokens`
- 视觉输入可以通过 `policy.image_mask` 做 masked RGB 预处理：仍然保持
  3-channel RGB，不改 ACT/ResNet 结构。当前支持按 camera 配置 binary rectangle
  mask，或从 HDF5 的 `/observations/image_masks/...` 读取 mask；mask 外像素会置零。
  这适合先试 `dig` 区域 crop/mask，让 ACT 只看目标挖掘区域，同时避免把
  Unity `env_state` 当成 policy 输入。
- `env_state` 不作为 policy 输入；它保留给 label、data filtering、reward/QC 和 rollout
  诊断，避免把仿真/Unity 特权信息直接喂给可迁移模型
- 未放进 `low_dim_keys` 的 `qvel / rewards / timestamps / metadata` 仍主要用于：
  - replay
  - dataset QC
  - rollout analysis
  - failure diagnosis
  - experiment record

target-safety 训练还有一个额外契约：
- 数据必须带齐 `target_horizontal_distance_m`、
  `bucket_height_above_target_rim_m`、`bucket_over_target_footprint_mask`、
  `dump_clearance_ok_mask`
- `dump_clearance_ok_mask` 是 Unity source-of-truth clearance mask；TruckBed
  可放宽水平距离，但垂直仍必须满足 `bucket_height_above_target_rim_m >= 0.0`
- `bucket_over_target_footprint_mask` 是 Unity 的 truck-top mask：表示 bucket proxy
  位于 truck bed 上方可倒料区域内；它复用 TruckBed 现有 clearance tolerance，
  不新增 env_state 字段。更严格的 release 深度仍看
  `bucket_bed_footprint_outside_distance_m`。
- V2.2 middle-handoff builder 要求数据包含
  `bucket_bed_relative_x_m/z_m` 和 `bucket_bed_footprint_outside_distance_m`；
  旧 13-field target geometry 数据会被新版 carry/dump ownership builder reject，
  不再 silently 进入训练。
- V2.2 scripted primitive planner 的 dump readiness 不用固定 swing qpos；它用
  target-relative geometry，并要求
  `bucket_bed_footprint_outside_distance_m <= 1.35m` 加 signed
  `bucket_bed_relative_x_m/z_m` corridor 表明 bucket proxy 已经进入 truck-top
  approach handoff 区；当前 V2.2 smoke config 把
  `dump_ready_max_horizontal_distance_m` 设为 `null`，scalar horizontal distance
  只保留为显式 legacy mode，不再作为默认 dump 切换条件。当前 approach handoff
  corridor 是 `-4.30<=bed_relative_x<=2.00`、
  `2.75<=bed_relative_z<=3.50`，并要求 bucket 至少高出 rim `0.30m`。
  单独的 unsigned `outside` 不再作为默认 dump 切换条件，因为它不能区分车斗尾部和中部。
- V2.2 4-primitives planner 的 `dig -> carry` 切换只看 bucket 是否已 loaded；
  离开 dig 区和运载到 truck 属于 carry primitive，不要求先满足固定 escape distance
- `tb-audit-target-geometry --dataset-dir <dataset>` 会检查覆盖率
- 没有这些字段的旧数据仍可用于非 target-geometry 的诊断/训练线，但不要混进
  target-safety workskill 训练
- workskill builder 会写可选 `/v2/step/action_loss_mask`。默认 builder 现在写全
  `1`，也就是不自动删 action 监督；裸 `bucket` action 阈值会误伤 digging
  阶段，所以 pre-dump bucket action onset 只作为诊断统计，不作为默认 loss mask。

这里还要明确一点：
- 当前默认 baseline 里 ACT 的低维输入仍然只是 `qpos`
- 这不代表 ACT “天然只能吃 position”
- 在当前代码结构下，可以把低维 `robot_state` 扩成：
  - `concat(qpos, qvel)`
  - `concat(qpos, qvel, goal_tokens)`
- 也可以保持低维输入为 `qpos + qvel`，同时用 `policy.image_mask` 给 ACT 的 RGB
  输入加 binary mask。第一版 mask 不改变 checkpoint 架构；它只是把指定 camera
  的非目标区域置零，所以需要用同样的 mask 配置重新训练对应 checkpoint。
- `env_state` 只进入离线标签/筛选，不进入 ACT policy 输入线
- 当前仓库已经落了一条独立的 `qpos+qvel` 实验路径：
  - [testbed/configs/act_agx_fulltest_qvel.yaml](/home/pingfan/PACT/excavator_testbed/testbed/configs/act_agx_fulltest_qvel.yaml)
  - [testbed/configs/eval_agx_fulltest_qvel.yaml](/home/pingfan/PACT/excavator_testbed/testbed/configs/eval_agx_fulltest_qvel.yaml)
- 因为它会改变 checkpoint 兼容性和 baseline 可比性，当前仍建议把 `qvel` 版本当成独立对照实验，而不要覆盖 `qpos` baseline

因此，**单独修改 eval success 口径，不会让旧 HDF5 数据立刻失效**。

但要注意一个例外：
- `tb-record-teleop` 如果开启 `stop_on_success: true`
- episode 会在当时录制所使用的 backend `task_success` 首次满足后提前结束

这意味着：
- 如果只是把 success 逻辑从旧 eval 口径改成更严格的
  `dump_complete_final_hold / strict_dump_complete`
  - 旧 demo 仍然可以继续训练
  - 第一反应应该先重训、重评测
- 如果你后来认为“旧 demo 经常在较宽松 success 下过早截断，没有保留足够稳定、足够干净的 dump 后半段”
  - 那时才值得重新录制一批更符合新目标语义的数据

更细的字段定义以 [schema.py](/home/pingfan/PACT/excavator_testbed/testbed/data/schema.py) 和 [hdf5_io.py](/home/pingfan/PACT/excavator_testbed/testbed/data/hdf5_io.py) 为准。

---

## 扩展

新增 policy：
- 在 `testbed/policies/<name>/adapter.py` 下实现并注册到 `PolicyRegistry`

新增 backend：
- 实现 `testbed.backends.base.SimBackend`
- 在 eval/runtime 工厂处接入

---

## Legacy

原始 PACT 代码保留在 `legacy/`，不再作为当前 AGX 主路径继续扩展。
