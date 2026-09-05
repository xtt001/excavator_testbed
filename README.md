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
- Repo B — `AGXUnityE85ExcavatorSim`：Unity / C# 场景与桥接；历史
  asset 路径仍保留 `Assets/AGXUnity_Excavator/...`
- Repo C — `sim-protocol`：共享协议、schema、常量、评测定义

---

## 当前状态

状态日期：`2026-05-16`

| 组件 | 实现状态 | 当前验证状态 |
|---|---|---|
| AGX 二进制 step-ack 协议客户端 | 已实现 | 已在本地 Unity 上通过 live strict smoke |
| `AGXSimBackend` | 已实现 | `GET_INFO / RESET / STEP / reward tracker` 最小 live 链路已打通 |
| HDF5 schema v1.1 | 已实现 | 支持 `timestamps`、`action_source`、`fpv`、`env_state` |
| Repo A `/v2` add-only extension | 已实现 | 当前主线为 V2.1 Stage 1 multicycle labeler、10D `goal_tokens`、phase/mode/boundary 标签、细粒度 `work_stage_id`，并新增 V2.2 stage success、3x2 Cell Entry planned/actual/audit 字段、`cell_entry_tokens`、operator-first `dig_cut_tokens` |
| 当前 AGX 任务协议 | 已实现 | 当前 target-safety + Cell Entry 目标协议是 add-only `env_state`；YuLong/AGX V2.2 live bridge 使用 `64D` contract，前 0-27 项保持兼容 |
| `tb-record-teleop` | 已实现 | `v1` 保持兼容；当前 V2 主线已切到 `teleop_multi_raw + target_dump_count` |
| `tb-replay` | 已实现 | 支持单文件或整个目录批量回放；`fulltest` 已验证，`v1` 仍建议补一轮正式 batch QA |
| `tb-dataset-videos` | 已实现 | 从 HDF5 离线导出 MP4 视频（无需连 AGX） |
| `tb-label-v2_1` | 已实现 | 给 `teleop_multi_raw` 生成兄弟目录 relabeled 数据集并补写 Stage-1 `/v2` 标签 |
| `tb-build-workskill-v2_1` | 已实现 | 从 sibling relabeled 数据集中裁出 `qualified_dig_start -> dump_end` 的 Stage-3 workskill 数据集 |
| `tb-build-transition-v2_1` | 已实现 | 从 sibling relabeled 数据集中裁出 `dump_end -> next qualified_dig_start` 的 transition feasibility 数据集 |
| `tb-build-cell-entry-v2_2` | 已实现 | 从 raw 数据生成 enriched raw，追加 3x2 Cell Entry planned/actual/audit `/v2` 字段与 JSON summary |
| `tb-build-operator-first-v2_2` | 已实现 | 从 relabeled VDS 数据生成 operator-first wrapper，追加 effective deposit、professional cut corridor、return target 与 `/v2/step/dig_cut_tokens`，不修改 raw |
| `tb-build-primitives-v2_2` | 已实现 | 从 V2.1 workskill/raw 数据集中裁出 V2.2 `dig/carry/dump/return` 四个 primitive sibling 数据集；new-env pilot 可用 effect-release fallback profile |
| `tb-build-v2_4-hindsight-pipeline` | 已实现 | 串联 V2.4 label/operator-first/hindsight/primitive VDS 与并行 materialize copy，每个阶段写 tail-friendly log |
| `tb-materialize-vds` | 已实现 | 把 VDS wrapper 解析成实体 HDF5，并按完整 frame chunk 写图像，用于训练吞吐对照 |
| `tb-cleanup-training-artifacts` | 已实现 | 训练成功后删除可由 primitive VDS 重建的 materialized copy，并只保留 `policy_best.ckpt` |
| `tb-virtualize-images` | 已实现 | 把历史 copy HDF5 的 `/observations/images/*` 反向改成 VDS 引用，只保留低维数组本地化，用于低损归档 |
| `tb-audit-target-geometry` | 已实现 | 检查数据集是否带齐 target-safety 训练所需的 7 个 target/dump-area geometry 字段 |
| `tb-audit-return-windows` | 已实现 | 汇总 accepted/rejected return 窗口里的动作范数、qpos 变化、dig-area 距离、bucket mass/depth，用于判断 realign/overlong reject 是否是真动作片段 |
| `tb-audit-return-ckpt` | 已实现 | 对 conditioned return checkpoint 做离线 teacher-forcing 审计，比较原始 `return_start_envelope_tokens_v1` 与 depth/spatial mask 变体，用于区分 ckpt、token 数值和 planner 在线状态问题 |
| `tb-audit-dig-ckpt` | 已实现 | 对 conditioned dig checkpoint 做 recorded-stream first-action 与 ACT chunk 审计，用于区分 dig ckpt 浅挖、planner handoff/replan 和 live 部署 mismatch |
| `tb-audit-dig-depth-semantics` | 已实现 | 对 dig primitive 离线重构 relative-y/surface-depth depth profile，比较 removed-depth token、payload 和 plane-depth 偏差 |
| `tb-build-dig-depth-profile-tokens-v1` | 已实现 | 给 qc6 dig copy 追加 `/v2/step/dig_depth_profile_tokens_v1`，用于后续 dig depth-profile ACT 重训 |
| `tb-train` / ACT trainer | 已实现 | 已完成 `fulltest(qpos)`、`fulltest(qpos+qvel)` 与 `v1(qpos)` 三条训练线 |
| `tb-eval` | 已实现 | 已完成正式 live eval；当前支持 V2.1 Stage 1 多轮 boundary / continuity 指标 |
| `hybrid_planner_act` | 已实现 | 已接入最小 Stage 2 deploy 链；当前已在 `s0_truck` 上通过 live `2-cycle` gate，并完成一次 `3-cycle smoke` |
| `primitive_planner_act` | 已实现（V2.2/V2.4 smoke 入口） | 加载 `dig/carry/dump/return` 四个 ACT checkpoint；YuLong operator-first 主线只给 `dig` 注入 `dig_cut_tokens`，carry/dump/return 保持 `qpos+qvel`；V2.4 可用 `operator_prior_coverage` 在不改 checkpoint 的情况下按 corridor 覆盖选择 dig token |
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
- YuLong new-env pilot 当前已按小斗 `contact_depth` 规则重切 V2.2 四 primitive root：
  `data/yulong_farmstick_3cycle_replay20_contact_depth_v2_2_4primitives_effect_release_20260514`
  （`dig=40 / carry=40 / dump=40 / return=40`，reject 为 0），训练入口为
  `act_yulong_farmstick_3cycle_replay20_contact_depth_v2_2_4p_{dig,carry,dump,return}_qvel.yaml`，
  rollout 入口为 `eval_yulong_farmstick_3cycle_replay20_contact_depth_v2_2_4p_qvel_smoke.yaml`；
  多轮验证使用 `eval_yulong_farmstick_3cycle_replay20_contact_depth_v2_2_4p_qvel_3cycle_smoke.yaml`
- `/v2/step/work_stage_id` 已接入离线 relabel，用来标出 `entry_to_bite / first_bite / rebite_recovery / carry / approach_dump / dump`
- 旧的 `ready-anchor / dump_plus_ready / 单铲 ready-return` 已从当前主线删除，只保留在历史提交中
- Stage 3 当前存在一个 deploy-only bootstrap handoff：
  - `reset -> loaded_and_clear` 先由 `ACT V1` 起手
  - `loaded_and_clear -> dump_end` 再切给 Stage-3 work policy
  - 这条逻辑仅作为 live 兼容层存在，不进入协议、`/v2` schema、planner 语义或默认训练口径
- V2.2 当前新增四 primitive smoke 线：
  - Cell Entry builder: `tb-build-cell-entry-v2_2`
  - builder: `tb-build-primitives-v2_2`
  - 当前 ownership probe root:
    `data/agx_v2_2_4primitives_ownership_boundary_260427_1ep`
  - 当前 carry/dump 训练 mix:
    `data/agx_v2_2_4primitives_ownership_history_probe_leftboost_260427`
    （旧 boundary rule baseline；新版 middle-handoff builder 需要用 16-field
    dump area geometry 数据重建）
  - 当前 ownership smoke eval:
    `testbed/configs/eval_agx_v2_2_4primitives_ownership_leftboost_qvel_3cycle_smoke.yaml`
  - phase boundary source of truth:
    `docs/primitive_phase_boundaries.md`
  - ownership 定义：`carry` 只负责 loaded transport；`dump` 负责 move to top
    of target、alignment、release 和 post-dump hold
  - `dump` 起点固定为 `first approach_dump stage`；如果 stable curl-out 早于
    `approach_dump`，builder 会 reject 该 carry/dump window，避免把边界不清的
    teleop 数据混入新版 ownership 训练
  - 对 YuLong 这类 new-env pilot，可显式使用
    `--boundary-profile v2_2_effect_release_fallback`：当旧阈值没有打出
    `approach_dump`，但稳定 release onset 和最终 good dump 都成立时，把
    `carry -> dump` 边界前移到 effect-based release onset；这保留四 primitive
    ownership，同时不把旧阈值实现当成新框架定义
  - 2026-04-28 middle-handoff probe 已验证：旧 refreshed sample 和此前
    ownership probe 即使刷新成 16-field geometry，也只接受 `dig`，`carry/dump`
    全部 reject；下一批训练前需要按 phase boundary 文档补录新数据
  - planner 在 `dump_done` 后保持 dump skill `30` step，再切 return；当前 smoke
    关闭即时 `dump_end` boundary 切换，避免 temporal aggregation 边界上 return
    动作把刚落入dump area的土带出
  - YuLong 10-cycle clean-dump smoke 不再依赖 post-dump hold；smooth professional
    release 用累计有效入箱质量识别 `dump_start/dump_end`，return 到浅接触 entry
    后立即 handoff 给 dig，避免 return primitive 继续向下挖
  - YuLong long-cycle smoke 使用 outcome-first `carry -> dump` handoff：bucket
    已在 dump footprint 上方、离 rim 足够高、bucket mass 仍高于 `15kg` 时即可切
    dump；signed x/z window 保留为旧规则兼容，避免长 rollout 后段因土量下降或
    target-relative 坐标漂移一直停留在 carry
  - YuLong V2.4 coverage planner 保留 V2.2 4P checkpoint 和 10D
    `dig_cut_tokens` contract，只把 live `dig_cut_planner.mode` 切到
    `operator_prior_coverage`。planner 从 64D `env_state` 的 3x2
    removed/target/valid grid 与 payload/deposit outcome 维护 9 条 corridor
    (`entry_x=p10/p50/p90` × `entry_z=p10/p50/p90`)，用 attempt limit、冷却惩罚、
    低产 streak 和耗尽判断避免反复挖同一区域，并通过 optional `planner_debug_json`
    在 Unity HUD 与 DigArea 上实时显示决策。30cycle 配置是 depletion/probe，
    不是新的成功标准。
  - 2026-05-23 DigArea 几何修复后，主线继续复用
    `v2_4_removed_depth_cut_v3` 的 10D `dig_cut_tokens`：第 8 维改为
    surface-relative `cut_depth_semantic_m`，优先来自
    `bucket_depth_below_local_surface_m` peak，depth scale 为 `0.80m`；旧
    checkpoint 不再兼容。
  - `policy.pre_dig_align` 仅保留为诊断开关，V2.4 coverage 主线默认关闭。
    实测证明手写 align 在 strict / loose gate 之间很难同时满足“到点”和“自然进入
    dig”，容易形成 gap 或把对齐动作变成半个 dig primitive。长期方案是训练
    conditioned return：planner 决定下一次 entry/corridor，return policy 负责把空斗
    回到适合 dig ACT 接管的 next-entry 状态。
  - YuLong V2.4 `dig -> carry` handoff 使用 target payload / mass plateau /
    bad-dig replan：默认目标斗内质量为 `45kg`，`>=35kg` 后的 plateau 才允许半斗
    收尾；低产 bad dig 会回到 planner/replan，
    防止 carry 过早开始并继续承担挖土。
  - live eval 入口：`eval_agx_v2_2_4primitives_qvel_3cycle_smoke.yaml`
  - 首轮 reset 仍可配置 `bootstrap_policy` 到 `loaded_and_clear`；YuLong pilot
    也支持 `bootstrap_end_mode=scripted_qpos`，只用于 smoke 时进入首个
    planned/accepted entry pose；若设备归一化动作方向和 qpos 方向不一致，
    用 `scripted_bootstrap.action_signs` 显式声明每轴符号，primitive 执行阶段不启用 fallback
  - YuLong 小斗 relabel/eval 使用 `qualified_dig_start_mode=contact_depth`，
    让 `qualified_dig_start` 主要由 dig-area 距离和下挖深度触发，不等待质量增量
  - YuLong operator-first 主线保留 Cell Entry planned/actual/audit 作为 legacy diagnostic；
    正式 dig 条件目标改为 `/v2/step/dig_cut_tokens`，从专业操作的 entry/exit
    cut corridor 离线推导，`carry/dump/return` 仍默认保持 `qpos + qvel`
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
- `env_state`：旧数据保持 `28D`；2026-05-14 起 Unity V2.2 bridge
  对 YuLong/AGX 采用 add-only `64D` contract，前 0-27 位顺序完全不变。

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
  bucket_dump_area_relative_x_m,
  bucket_dump_area_relative_z_m,
  bucket_dump_area_footprint_outside_distance_m,
  bucket_dig_area_cell_in_bounds_mask,
  dig_area_long_axis,
  dig_area_grid_long_count,
  dig_area_grid_short_count,
  bucket_dig_area_relative_x_m,
  bucket_dig_area_relative_y_m,
  bucket_dig_area_relative_z_m,
  bucket_dig_area_long_norm,
  bucket_dig_area_short_norm,
  bucket_dig_area_long_index,
  bucket_dig_area_short_index,
  bucket_dig_area_cell_id
]
```

V2.2 追加的 28-63 位覆盖 plan(1) 的现场采集字段：

```text
bucket_tip_dig_area_x/y/z_m,
bucket_depth_below_local_surface_m,
bucket_depth_below_target_surface_m,
dig_area_surface_depth_m_r{0..2}_c{0..1},
dig_area_removed_depth_m_r{0..2}_c{0..1},
dig_area_target_depth_m_r{0..2}_c{0..1},
dig_area_cell_valid_mask_r{0..2}_c{0..1},
bucket_mass_delta_kg,
deposited_mass_in_dump_area_kg,
offtarget_deposited_mass_kg,
target_geometry_available,
bucket_dig_area_penetration_contact_mask,
bucket_contact_dump_area_mask,
hard_collision_count
```

其中 `offtarget_deposited_mass_kg = -1.0` 表示当前 Unity 场景没有可靠的
off-target mass sensor；对应 HDF5 metadata 会写
`offtarget_deposited_mass_source=unavailable`。

target-safety 相关逻辑使用显式 target geometry 字段：
`min_distance_to_target_m` 现在是 DumpArea footprint outside-distance 的
scalar mirror；reward/QC 仍优先使用显式的
`target_horizontal_distance_m`、`dump_clearance_ok_mask` 和
`bucket_dump_area_footprint_outside_distance_m`，不把这个 scalar 当作
clearance fallback。
当前 Unity bridge 额外输出 bucket proxy center 在 active dump area local frame
下的 `bucket_dump_area_relative_x_m/z_m`，以及到 dump-area footprint 的
`bucket_dump_area_footprint_outside_distance_m`；`bucket_over_target_footprint_mask`
表示 bucket proxy 位于 dump-area 可倒料区域上方，可结合目标侧配置的
clearance tolerance 使用。
`bucket_dump_area_footprint_outside_distance_m` 是 unsigned proximity，只说明 bucket
proxy 离 dump-area footprint 有多近；它不能表达目标局部坐标中的前后/左右位置。
需要约束 handoff corridor 时，必须同时使用 signed
`bucket_dump_area_relative_x_m/z_m` window。
其中 `dump_clearance_ok_mask` 是 Unity 输出的 clearance source of truth：
DumpArea 水平方向允许目标侧配置的 dump 容差，但垂直方向仍要求
`bucket_height_above_target_rim_m >= 0.0`，也就是桶底必须在 dump-area rim/top
之上。
`mass_in_target_box_kg` 是当前 DumpArea 的 reset-relative delivered mass：
terrain particle 第一次进入 DumpArea 测量体积时，按 AGX particle 自身质量
计一次；reset 时已经在体积内的 particle 会先作为基线 prime，不计入新增交付。
Unity 侧 ledger 使用全局 `particle.hash()` 去重，并在 particle 消失后释放 hash，
避免同一粒子经多个 terrain provider 暴露时被双计，同时允许后续铲次复用 hash 后重新计入。
`deposited_mass_in_target_box_kg` 在当前 E85 场景中使用同一套 unique
particle-entry ledger。这个正式质量源不依赖 `DumpTerrainReceiver` 高度场密度换算、
settled/live 状态拼接，也不合入 bucket-unload near target 推断量。
Cell Entry 字段固定使用 DigArea 3x2 grid：长边 3 份、短边 2 份；
`cell_id = long_index * 2 + short_index`。bucket 参考点出界时，
`bucket_dig_area_cell_in_bounds_mask = 0`，indices 与 `cell_id` 均为 `-1`。

奖励 / 成功语义：
- `loading`：只有满足 DigArea good-start 后才开始给正向装载奖励
- `approaching_target`：载荷存在且 `target_horizontal_distance_m` 有效时，朝目标水平接近给奖励
- `depositing`：目标 delivered mass 开始增长时给奖励
- `hard_target_collision`：`target_hard_collision_count` 在本步增加时给固定惩罚
- `success`：`deposited_mass_in_target_box_kg >= 100 kg` 且连续保持 `25` 步

兼容性：
- Repo A 仍可读取旧 `5D/7D env_state` 数据
- Repo A 仍可降级读取旧 `16D env_state` 数据；Cell Entry actual cell 会记为 unknown，不会被当作成功命中
- 但旧数据只用于兼容或离线 smoke，不应再作为当前任务的标准训练集

---

## Quick Start

### 1. 安装

```bash
conda activate aloha
pip install -e ".[dev]"
```

`dev` extra 包含格式化、lint 与测试入口（包括 `pytest`）。

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
  --notes "first rerecord batch with 300kg delivered-mass stop" \
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
#       filtering. Scalar min_distance_to_target_m is not used as a fallback.
#       target_horizontal_distance_m < 0.35 -> near_dump_start. This removes
#       close-call low-boom dump examples that can become hard target collisions
#       in rollout.
#       Current target-safe qualitymix has 74 cycles: left=18, mid=40, right=16.
# note: the target-safe smoke eval also enables a live WORK safety guard:
#       if loaded, target_horizontal_distance_m < 0.45, and dump clearance is
#       not ok, cap bucket dump action to -0.15 and command at least +0.08 boom
#       raise before continuing.
#       dump clearance comes from Unity's dump_clearance_ok_mask; DumpArea may
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

# 记录逐 step 诊断 JSONL，用于定位 replay 中 qpos/swing 跳变
tb-replay \
  --episode data/agx_teleop_v2_1_multi_raw/episode_0.hdf5 \
  --config testbed/configs/teleop_v2_1_multi_raw.yaml \
  --diagnostic-log runs/diagnostics/episode_0_replay_diagnostics.jsonl \
  --diagnostic-every 1
```

使用 `--record-output-dir` 做数据刷新时，`tb-replay` 会读取 teleop config
里的 `post_success_tail_steps`，当前 V2.1 默认是 `50` 步，并在 source
actions 结束后追加 zero-action hold tail。这样旧数据刷新成 13D
`env_state` 时不会把 terminal dump 的 plateau / `dump_end` 观察截断。
需要临时覆盖时可用 `--post-tail-steps <N>`。刷新 replay 只读取 source
episode 的 actions/qpos/metadata，不加载旧 image dataset；新的 image
帧来自当前 Unity 后端。

`--diagnostic-log` 会写 JSONL，每行记录 replay step 的 action、Unity 返回的
qpos/qvel、与 source qpos 的误差、bucket 相对 DigArea 位置、contact/collision、
removed-depth grid 等字段。日志可用 `tail -f` 实时看，也可用
`tb-replay-diagnostics --input <jsonl-or-dir> --top 20` 汇总首个/最大的 qpos
误差、qpos jump、碰撞和接触点。

如果旧 source episode 自身包含已修复且随机的 actuator pose 跳变，刷新
removed-depth 时可以加 `--realign-on-qpos-error --realign-axis all`。这会在
replay 过程中通过 Unity `REALIGN_POSE` 对齐当前仿真 4D qpos，再继续生成新的
image/env_state/depth；不要事后直接改旧 HDF5 qpos，因为旧 image/action/env_state
不会随之同步。

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
- `final_hold`：episode 结束时仍满足 delivered-mass hold 条件
- `strict_final_hold`：在 `final_hold` 基础上，还要求指定失败项计数不超过阈值
- `dump_complete_final_hold`：推荐主口径，episode 结束时既要交付足够多的 delivered mass，也要把 bucket 余土降到阈值以下
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

Unity / C# telemetry 修改后，推荐先跑自动重启与 strict smoke 门闩：

```bash
tb-unity-restart-smoke \
  --host 127.0.0.1 \
  --port 5057
```

如果 Unity Editor 已经打开，wrapper 会写入
`Temp/CodexPlayModeBootstrap.request`，由 Editor 退出 Play Mode、等待编译、
打开 YuLong 主场景、重新进入 Play Mode 并确认 `AgxSimStepAckServer`
listening；如果 Editor 没开，wrapper 会用 `UNITY_EDITOR` 或常见 Unity
安装路径通过 `-executeMethod` 触发同一个入口。随后它会自动执行
`scripts/agx_smoke.py --strict --host 127.0.0.1 --port 5057`。

需要同时刷新少量 replay 并检查 removed-depth 时：

```bash
tb-unity-restart-smoke \
  --replay-episode data/<raw_yulong_root>/episode_0.hdf5 \
  --replay-config testbed/configs/teleop_yulong_v2_2_pro_full_task.yaml \
  --record-output-dir data/<new_replayed_root> \
  --replay-diagnostic-dir runs/diagnostics/yulong_replay_probe \
  --check-removed-depth
```

`--check-removed-depth` 会要求刷新后的 HDF5 中 `env_state[:,39:45]`
出现非零时间变化；不通过时流程直接失败，不进入后续 relabel / train。
`--replay-diagnostic-dir` 会给每个被刷新的 episode 写
`*_diagnostics.jsonl`，便于在 Unity/AGX 断连或 swing 误差复现后直接分析最后
一段 step 对齐数据。
如果 source episode 已知含随机 actuator pose 跳变，可在 wrapper 上加
`--replay-realign-on-qpos-error --replay-realign-axis all`，它会转发到
`tb-replay` 并在 JSONL 中记录 `pose_realign` 事件。
刷新后的 HDF5 metadata 会保留 `replay_pose_realign_steps`；后续
`tb-build-primitives-v2_2` 把它当作高敏感数据质量信号，任何覆盖该 step 的
完整逻辑 cycle 都只写入 reject summary，不产出对应训练 primitive。这里的完整
cycle 指本轮 dig start 到 return 完成/下一次 qualified dig start 之前的半开窗口；
realign 如果正好落在下一轮 qualified dig start 帧，只归属下一轮。实际写
`dig/carry/dump` 片段时仍只裁到 `dump_end_step`，避免 `dump` 吞入 return。
覆盖该 step 的 return transition window 也会单独 reject。

刷新后的 raw/replay root 通过 depth QC 后，可以用 V2.4 pipeline 走“先 VDS、后并行
materialize”的数据链：

```bash
tb-build-v2_4-hindsight-pipeline \
  --raw-dir data/<replayed_raw_root> \
  --tag yulong_removed_depth_$(date +%Y%m%d_%H%M%S) \
  --materialize-workers 16 \
  --update-current-symlinks \
  --detach
```

V2.4 pipeline 默认向 primitive builder 转发 `--return-max-transition-len 512`，
与 return ACT 的 `episode_len=512` 对齐；更长的 dump-end -> next-dig gap
会被当成长等待/恢复片段丢进 reject summary，不进入 return 训练。
V2.4.5 spatial-mass return 的终点优先使用 `first_next_dig_entry_ready`：即
`dump_end` 后首次到达下一轮 dig 可接管 envelope 的帧；这避免 delayed
material-cycle start 把下一次 dig 的早期动作吞进 return，realign reject 也只看
`dump_end -> handoff` 这段。
pipeline 在 primitive VDS 写完后会先跑 pre-materialize QC，并把结果写到
`04_pre_materialize_qc.json`。这个 QC 会在写 image copy 和训练前检查 depth token
饱和率、p10/p50/p90 分离、可靠 `env_state_surface_penetration` 占比、return
window 最大长度、dump max/p95 长度以及 dump 是否混入 transition mode/phase；
不通过时流程直接停止，不进入 materialize/train。
如果 return QC 因 realign 或 overlong 停止，先运行
`tb-audit-return-windows --primitive-root <primitive-vds-root>`；它会把 accepted、
rejected 和 overlong tail-512 的动作/qpos/env-state 变化写入
`return_window_audit.json`，用于区分“真实 return 运动被 reject”和“空等待/错切分”。
如果同时传入 `--train`，dig/return 训练全部成功后会自动运行
`tb-cleanup-training-artifacts --delete`，删除本轮 materialized primitive
copy 与指向它的 current symlink，并只保留本轮 `policy_best.ckpt`。需要在训练后
继续对 copy 做诊断时，给 pipeline 加 `--no-cleanup-after-train`。
长任务默认用 `--detach` 后台运行，不建议和 Cursor 前台交互、image materialize
同时抢内存。
脚本会在 `runs/jobs/yulong_v2_4_removed_depth_<tag>/logs/` 写每个阶段的日志；
可用 `tail -f runs/jobs/yulong_v2_4_removed_depth_<tag>/pipeline.log` 或
`tail -f runs/jobs/yulong_v2_4_removed_depth_<tag>/logs/*.log` 看进度。

当前 V2.4.5 训练主线已经接受 qc6 boundary split 作为唯一数据源：

```bash
chmod +x runs/jobs/yulong_v2_4_5_process_boundary_qc6_20260522/run_qc6_materialize_train_eval.sh
TRAIN_AFTER_QC=1 RUN_EVAL_AFTER_TRAIN=0 \
  runs/jobs/yulong_v2_4_5_process_boundary_qc6_20260522/run_qc6_materialize_train_eval.sh
```

该脚本从
`/fastdata/pingfan/excavator_testbed_data_hot/yulong_v2_4_removed_depth_hindsight_goal_primitives_vds_v2_4_5_process_boundary_qc6_20260522`
materialize 到
`/fastdata/pingfan/excavator_testbed_data_hot/yulong_v2_4_removed_depth_hindsight_goal_primitives_copy_v2_4_5_process_boundary_qc6_20260522`，
先检查四个 primitive 都不是 VDS、episode/gold 数匹配、return max len `<=512`、
gold depth source fraction `>=0.95`、depth token saturation `<=0.02`，再按
`dig -> return -> carry -> dump` 训练到
`runs/ckpts/yulong_v2_4_5_process_boundary_qc6_20260522/{dig,return,carry,dump}`。

Planner 同步切到 qc6 的语义边界和 3x2 weighted coverage：`BoundaryDetector`
在 `boundary.profile: v2_4_5_spatial_mass` 下输出
`dig_complete / dump_committed_start / release_onset / dump_complete /
next_dig_entry_ready`，planner 只消费事件、目标 token 和 coverage 状态；新的
surface-depth 后续配置把 `dump_committed_start` 收紧到小场景尺度的稳定 aiming band：
dump-area outside distance `<=0.25m`、signed relative corridor
`x=[-0.2,1.9]`、`z=[0.45,2.1]`，并要求 rolling window 内 outside/relative
变化量低于 `0.06/0.16/0.10m`，避免 carry 末端刚靠近 dump area 就过早切到 dump。
离线 primitive split 使用同一 tightened band，planner 不再通过旧 `0.45m` 宽门 fallback；
`release_onset` 仍保留 `0.45m` release-area 近邻门，只用于已经接管 dump 后识别真实掉料。
`coverage.candidate_layout: cell_weighted_3x2` 读取
`yulong_removed_depth_dig_cut_prior_v3.json` 的 `coverage_cells` 生成 6 条
cell corridor。旧 prior 没有 `coverage_cells` 时仍走 3x3 percentile grid。
qc6 人工复核分布记录为 `0:64, 1:163, 2:142, 3:180, 4:18, 5:82`，其中 cell 4
默认作为稀缺 cell 限制 first-dig 和 attempt 次数。
最新 depth-profile eval 还开启
`coverage.state_conditioned_exemplars`，读取
`yulong_removed_depth_dig_cut_state_exemplars_qc6.json`。planner 根据当前 6-cell
removed-depth grid 在同一 cell 内匹配 qc6 gold expert 样本，直接生成
`dig_cut_tokens` 和 `dig_depth_profile_tokens_v1`；bad-dig/exit-guard replan 会清掉
return pending token，避免旧浅挖计划被复用。
`pre_dig_align.replan_after_failed_dig=true` 使失败 replan 先回到 entry-align skill，
再交给 dig，避免让 dig checkpoint 承担它未学习的“移动到新 entry/预姿态”职责。
V2.4.5 semantic boundary 下，`dig_complete` 仍由 detector 定义；live rollout 中若
ACT 已经获得目标载荷/质量 plateau 但尚未离开 dig box，planner 会用
`semantic_material_loaded/plateau` liveness escape 切到 carry，避免 dig/carry handoff
因为互相等待而消失。

---

## 文档入口

当前权威文档：
- 本 README：仓库说明、当前状态、quick start
- [docs/strict18_goal_following_roadmap.md](docs/strict18_goal_following_roadmap.md)：Strict-18 当前 Dig 单铲位置 A/B 的阶段 B→C→D 合同；Return A.6 仅保留为冻结历史
- [docs/strict18_realtime_goal_following_handoff_prompt_20260820.md](docs/strict18_realtime_goal_following_handoff_prompt_20260820.md)：Dig 单铲实验的当前交接入口，包含诊断证据边界、Git 状态、安全阻断和执行次序
- [docs/dig_short_trajectory_conditioned_act_development_plan.md](docs/dig_short_trajectory_conditioned_act_development_plan.md)：下一阶段短轨迹条件 ACT 的 Phase 0→A→B→C 开发、停门和分支启动计划
- [docs/goal_conditioned_act_data_identifiability.md](docs/goal_conditioned_act_data_identifiability.md)：说明目标条件 ACT 的数据可辨识性、Hindsight 标签边界、长时序接触任务的数据要求，以及学习与传统控制的合理分工
- [docs/planner_to_act_conceptual_contract.md](/home/pingfan/PACT/excavator_testbed/docs/planner_to_act_conceptual_contract.md)：从概念上说明上层 planner 到低层 ACT 的控制结构、职责边界和输入输出
- [docs/planner_current_architecture.md](/home/pingfan/PACT/excavator_testbed/docs/planner_current_architecture.md)：当前 primitive planner 架构、decision backend / trace 边界和扩展规则
- [docs/planner_scheduling_backend_design.md](/home/pingfan/PACT/excavator_testbed/docs/planner_scheduling_backend_design.md)：未来 scheduling / decision backend 接入指南
- [docs/planner_decision_backend_contract.md](/home/pingfan/PACT/excavator_testbed/docs/planner_decision_backend_contract.md)：当前 decision backend、trace、proposal validation、backend selection 和未来 LLM/VLM 接入契约
- [docs/v2_1_failure_retrospective.md](/home/pingfan/PACT/excavator_testbed/docs/v2_1_failure_retrospective.md)：V2.1 初期多轮失败原因、script/human transition gap、goal-conditioned ACT 与 V2.2 修复复盘
- [docs/data_processing_hdf5_qc_contract.md](/home/pingfan/PACT/excavator_testbed/docs/data_processing_hdf5_qc_contract.md)：数据处理、HDF5 字段、primitive 切分和 QC 逻辑
- [docs/primitive_phase_boundaries.md](/home/pingfan/PACT/excavator_testbed/docs/primitive_phase_boundaries.md)：`dig/carry/dump/return` 四 primitive ownership 契约
- [docs/training_setup.md](/home/pingfan/PACT/excavator_testbed/docs/training_setup.md)：训练配置字段、实验记录项、失效归因时应保留的证据链

阶段与规划文档：
- `docs/project_history_v1_to_now.md`：V1 到当前阶段的项目复盘索引
- `docs/v1_to_v2_3_exploration_path.md`：V1 到 V2.3 的探索路径
- `docs/v2_4plan.md`、`docs/v2_4_5_spatial_mass_ownership.md`：V2.4 / V2.4.5 主线设计
- `docs/llm_planner_prework.md`：引入 LLM goal planner 前的收尾清单

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
  data_processing_hdf5_qc_contract.md
  planner_to_act_conceptual_contract.md
  planner_current_architecture.md
  planner_scheduling_backend_design.md
  planner_decision_backend_contract.md
  primitive_phase_boundaries.md
  project_history_v1_to_now.md
  llm_planner_prework.md
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
- `env_state_contract_version`
- `scene_version`
- `soil_preset_id`
- `dig_area_preset_id`
- `dump_area_preset_id`
- `task_goal_description`
- `target_depth_m`
- `recording_protocol_version`
- `warmup_or_train`
- `operator_notes`
- `observer_notes`

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
  - 可选 low-dim：`qvel`、`goal_tokens`、`cell_entry_tokens`、`dig_cut_tokens`、
    `dig_depth_profile_tokens_v1`、`return_start_envelope_tokens_v1`、
    `return_relocate_tokens_v1`
- 视觉输入可以通过 `policy.image_mask` 做 masked RGB 预处理：仍然保持
  3-channel RGB，不改 ACT/ResNet 结构。当前支持按 camera 配置 binary rectangle
  mask，或从 HDF5 的 `/observations/image_masks/...` 读取 mask；mask 外像素会置零。
  这适合先试 `dig` 区域 crop/mask，让 ACT 只看目标挖掘区域，同时避免把
  Unity `env_state` 当成 policy 输入。
- `env_state` 不作为 policy 输入；它保留给 label、data filtering、reward/QC 和 rollout
  诊断，避免把仿真/Unity 特权信息直接喂给可迁移模型
- V2.4.5 return 的 `return_start_envelope_tokens_v1` 是由下一轮 dig-start 附近
  专家状态和 `env_state` 派生出的条件 token；如果 return rollout 提前下铲，应先用
  `tb-audit-return-ckpt` 在离线 recorded stream 上比较原始 token、depth mask 与 spatial
  mask，而不是直接否定物理直觉切分出来的连续 return 边界。
- V2.4.5 dig 浅挖排查先用 `tb-audit-dig-ckpt`，不要先改 planner 阈值。该工具在
  recorded dig stream 上比较 checkpoint 的 first-action 与专家动作，并从 primitive
  起点导出完整 ACT chunk 对齐专家后续动作；如果离线 chunk 已经浅化，优先查 dig
  checkpoint/训练分布/ACT chunk 长度，如果离线贴近专家但 live 仍浅，优先查 live
  observation/action scaling、camera、temporal aggregation 或 Unity rollout 状态。
- V2.4.5 visual-policy eval 默认关闭 `eval.send_planner_debug_to_backend`。planner
  debug 仍进入 rollout JSONL，但 coverage marker/debug geometry 不再发送给 Unity
  渲染到 ACT 的 `fpv` observation；需要人工理解 planner 时可临时打开该开关，打开后的
  rollout 不作为 ACT 行为判断依据。
- qc6 live eval 的 return envelope 不再由当前 return-start `qpos/env_state` 拼接；
  `primitive_planner_act` 默认从 qc6 prior 的 `return_start_envelope_global` 注入
  median envelope，并在 rollout JSONL 写出 token/source 方便复查。coverage cell
  只用于下一次 dig 的 pending `dig_cut_tokens` 和 entry gate；除非旧实验显式设置
  `dig_cut_planner.return_start_envelope.use_cell_prior: true`，return-start envelope
  不再按 coverage cell 条件化，避免把“交接姿态”与“下一铲目标 cell”混成同一个 token。
- 2026-05-25 return relocation 重训把 `return_relocate_tokens_v1` 作为
  `return_target_tokens` 的派生 low-dim view：保留下一铲 entry/exit/direction/length
  和 valid，强制屏蔽 depth/payload。它不写入 HDF5，不改变 primitive 边界；loader
  会在 step-level target 全 0 但 metadata 有 `next_operator_*` 字段时重建该 view。
  本轮只重训 return：`qpos + qvel + return_start_envelope_tokens_v1 +
  return_relocate_tokens_v1`，复用上一轮 surface-depth dig/carry/dump ckpt。
- qc6 `return -> dig` handoff 不能只看 2D entry error。planner 现在可开启
  `return_to_dig_start_envelope_gate_enabled`，用同一个
  `return_start_envelope_tokens_v1` 的 long/short、local depth/contact 和 qpos
  p05-p95 envelope 判断 return 是否真的到达下一轮 dig-start 分布；这避免把一个
  合法的 `dig_cut_tokens` 交给一个还没到 entry envelope 的当前状态。
- `local depth` gate 使用 token 内显式的 depth min/max，而不是 qc6 prior p05/p95；
  后者在少量 return window 中会出现接近 0 的浅接触值，容易过早把第二铲交给 dig。
- qc6 第二铲复现进一步确认，dig ACT 的可切起点更稳定对应
  `bucket_depth_below_dig_area_plane`，而不是 local-surface depth。prior 因此记录
  每个 cell 的 qc6 gold dig-start plane-depth 分布，并在 `return -> dig` readiness
  中作为语义 gate。最新 qc6 eval 使用
  `return_to_dig_start_envelope_plane_depth_mode: p50_floor`，要求 return 至少回到
  cell-wise plane-depth 中位起挖带；p05 只保留作分布诊断，不再作为 live handoff
  的有效下界。`next_dig_entry_ready` 是 one-shot 事件，planner 会在 return 阶段
  latch 住它，等 envelope gate 也通过后再交接，避免旧 shallow guard 抢走
  V2.4.5 语义。
- V2.4.5 planner 不再允许低载荷 `dig_complete` 直接进入 carry：如果 detector 报
  `dig_complete` 但当前 bucket mass 低于 carry/dump 最低可用载荷，planner 会按
  bad dig 重新规划，而不是让 underloaded carry 自己执行 dump 语义。若 carry 中
  已经出现 release 完成，planner 会通过 release safety 尽快转入 return，避免继续卡
  在 carry。
- 2026-05-23 dig 深度语义审计结论更新：`bucket_depth_below_dig_area_plane`
  只保留为固定 reference-plane readiness/诊断，不作为真实入土深度。Unity 几何修复后，
  `bucket_depth_below_local_surface_m` 的设计意图仍是“铲斗相对当前局部土面的入土姿态”，
  只是实现从旧的单点 tip/reference 改为 bucket 测量代理体 corners 的最大
  surface-relative penetration。主线训练因此继续复用 10D `dig_cut_tokens`，
  第 8 维改为 `cut_depth_semantic_m`，来源为修复后的
  `bucket_depth_below_local_surface_m` peak；6-cell `dig_area_removed_depth_m_*`
  仍然交给 planner 做 coverage、下一铲 entry/exit 和剩余深度判断。12D
  `dig_depth_profile_tokens_v1` 只保留为 ablation/探针，不作为默认接口。
- 2026-05-25 决议：V2.4.5 qc6 主线关闭 first-dig `pre_dig_align`。第一铲没有上一轮
  return 的 entry 约束，planner 不再要求它先对齐到某个 coverage cell；只要当前姿态
  可以开始挖，直接把近场/coverage token 交给 dig ACT。`pre_dig_align` 仅保留为诊断
  开关；若手动启用 entry-intent 模式，timeout 也不会计入 coverage 低产/耗尽。
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
- `dump_clearance_ok_mask` 是 Unity source-of-truth clearance mask；DumpArea
  可放宽水平距离，但垂直仍必须满足 `bucket_height_above_target_rim_m >= 0.0`
- `bucket_over_target_footprint_mask` 是 Unity 的 dump-area mask：表示 bucket proxy
  位于 dump area 上方可倒料区域内；它可结合 DumpArea clearance tolerance，
  不新增 env_state 字段。更严格的 release 深度仍看
  `bucket_dump_area_footprint_outside_distance_m`。
- V2.2 middle-handoff builder 要求数据包含
  `bucket_dump_area_relative_x_m/z_m` 和 `bucket_dump_area_footprint_outside_distance_m`；
  旧 13-field target geometry 数据缺少 signed dump-area local 几何，会被新版 carry/dump ownership builder reject，
  不再 silently 进入训练。
- V2.2 scripted primitive planner 的 dump readiness 不用固定 swing qpos；它用
  target-relative geometry，并要求
  `bucket_dump_area_footprint_outside_distance_m <= 1.35m` 加 signed
  `bucket_dump_area_relative_x_m/z_m` corridor 表明 bucket proxy 已经进入 dump-area
  approach handoff 区；当前 V2.2 smoke config 把
  `dump_ready_max_horizontal_distance_m` 设为 `null`，scalar horizontal distance
  只保留为显式 legacy mode，不再作为默认 dump 切换条件。当前 approach handoff
  corridor 是 `-4.30<=dump_area_relative_x<=2.00`、
  `2.75<=dump_area_relative_z<=3.50`，并要求 bucket 至少高出 rim `0.30m`。
  单独的 unsigned `outside` 不再作为默认 dump 切换条件，因为它不能区分 dump area 的局部前后位置。
- V2.2 4-primitives planner 的 `dig -> carry` 切换只看 bucket 是否已 loaded；
  离开 dig 区和运载到 dump area 属于 carry primitive，不要求先满足固定 escape distance
- V2.2 Cell Entry enriched raw 会补写 `/v2/step/cell_entry_tokens` 和
  planned/actual/audit flat fields，供后续 conditional primitive 使用；当前默认
  primitive train/eval configs 不把这些 token 加进 low-dim 输入
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

原始 PACT 的迁移来源保留在 Git 历史中；当前 checkout 不再物化一个不可恢复的
`legacy/` 子模块，也不将它作为当前 AGX 主路径继续扩展。
