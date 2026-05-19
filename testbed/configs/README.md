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
  `bucket_over_target_footprint_mask`、`dump_clearance_ok_mask`。V2.2 Unity
  bridge 还会输出 `bucket_dump_area_relative_x_m`、`bucket_dump_area_relative_z_m`、
  `bucket_dump_area_footprint_outside_distance_m`；`bucket_over_target_footprint_mask`
  表示 bucket proxy 是否在 dump-area 可倒料区域上方，严格 release 深度由
  outside distance 判断。`min_distance_to_target_m` 现在只是 DumpArea footprint
  outside-distance 的 scalar mirror，不作为 clearance fallback。
- 当前 `tb-label-v2_1` 的 work-stage 版本为
  `v2_1d_work_stage_7cls_bedtop16`。这个 attr 名称保留了历史版本字符串，
  但当前 16-field Unity 数据的几何语义已经是 DumpArea，不是 truck bed。在这类数据上，
  `approach_dump` 使用 dump-area-top geometry 提前识别最终 dump 对齐阶段；primitive
  builder 仍单独要求更严格的 safe release intent，不能把 early curl-out
  自动吞进训练窗口。
- `dump_clearance_ok_mask` 由 Unity 作为 target-clearance source of truth
  输出；DumpArea 可使用水平 dump 容差，但垂直方向仍要求
  `bucket_height_above_target_rim_m >= 0.0`。
- 当前成功/QC 使用的 `deposited_mass_in_target_box_kg` 是 Unity 输出的
  reset-relative delivered mass；`mass_in_target_box_kg` / `deposited`
  都来自 DumpArea unique particle-entry ledger：terrain particle 第一次进入
  DumpArea 测量体积时按自身 AGX mass 计一次；Unity ledger 使用全局
  `particle.hash()` 去重，并在 particle 消失后释放 hash，避免同一粒子经多个
  terrain provider 暴露时被双计，同时允许后续铲次复用 hash 后重新计入。这个口径不依赖
  `DumpTerrainReceiver` 高度场密度换算、settled/live 状态拼接，且不包含
  bucket-unload 推断量。早于这个语义更新录制的数据只能作为诊断参考。
- 2026-05-14 V2.2 YuLong bridge 将 `env_state` 从旧 `28D` add-only
  扩展到 `64D`：前 0-27 位不变，追加 bucket tip local pose、3x2
  surface/removed/target depth grid、valid mask、bucket mass delta、dump/offtarget
  deposition 标志和 contact/collision masks。`offtarget_deposited_mass_kg=-1.0`
  表示当前场景没有可靠 off-target mass sensor。
- 同日，`tb-label-v2_1` 的 `/v2/cycle` 会追加 stage success 字段：
  `dig_success`、`carry_success`、`dump_success`、`return_success`、
  `return_required`、`stage_success` 和诊断量
  `payload_gain_kg` / `carry_loss_before_dump_kg` /
  `dump_deposited_fraction`。这些字段用于 pilot QC 和 gold/silver/diagnostic
  分层；旧 `cycle_success` 语义保持不变，避免影响已有 workskill/transition
  builder。

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

现在，V2.2 **4-primitives smoke** 也已经接入新分支：

- 新增 `tb-build-cell-entry-v2_2`
- 新增 `tb-build-primitives-v2_2`
- 新增 `act_agx_v2_2_4primitives_{dig,carry,dump,return}_qvel_e500.yaml`
- 新增 `eval_agx_v2_2_4primitives_qvel_3cycle_smoke.yaml`
- 当前 carry-tail cleaned 数据 root: `data/agx_v2_2_4primitives_carrytrim120_leftboost_260427`
- 当前数据计数：
  - `dig = 64`，median `8` steps
  - `carry = 63`，safe carry `27` + new clean carry `3 x 12`
  - `dump = 27`，median `118` steps
  - `return = 120`，median `298.5` steps
- low-level primitive ACT 默认只用 `qpos + qvel`
- Unity `env_state` / target geometry 只用于离线切分、scripted switch、QC 和 rollout 日志，不作为低维 policy input
- YuLong V2.2 主线固定为：
  `immutable raw -> relabel VDS -> operator-first relabel VDS -> 4 primitive VDS -> conditioned dig -> primitive_planner_act live token injection`。
  不再把 one full-task ACT/GC-ACT 作为正式 rollout 主线；已生成的 full-task checkpoint
  只作为 diagnostic 对照。
- `tb-build-cell-entry-v2_2 --storage-mode vds` 会写 lightweight enriched wrapper：
  `observations/images/*`、`qpos/qvel/env_state`、`action`、`rewards`、`timestamps`
  和已有 `/v2/step/*` 走 HDF5 VDS，新增 Cell Entry planned/actual/audit 字段与
  `/v2/cycle` QC 小字段直接写入 wrapper，并生成 `lineage.json`。
- `tb-build-operator-first-v2_2 --storage-mode vds` 从已有 relabeled root 追加
  operator-first 字段：effective deposit、专业师傅实际 entry/exit cut corridor、
  return next-entry target 与 `/v2/step/dig_cut_tokens`。旧 Cell Entry planner 字段
  继续保留为 `legacy_rule_alignment` 诊断，不作为 reject gate。
- `tb-build-primitives-v2_2 --storage-mode vds --raw-dir <operator-first-root>`
  可直接从 operator-first enriched raw 切 `dig/carry/dump/return`，不再需要复制大型
  workskill 图像 root；`--storage-mode manifest` 只产出 `window_manifest.json` 和
  `summary.json`，用于 dry-run QC。
- 两个 builder 都会写 `lineage.json`，默认拒绝覆盖已有 episode；只有显式
  `--overwrite` 才会替换 builder output。需要在 `data/` 下保留当前候选入口时，
  使用 `--current-symlink <path>` 更新 symlink；如果该路径是真实目录，builder 会拒绝替换。
- conditioned dig 已接入两条语义：legacy `cell_entry_tokens` 与 operator-first
  `dig_cut_tokens` 都是固定 10D low-dim key。当前 YuLong pro 主线使用
  `act_yulong_v2_2_operator_first_4p_dig_cut_qvel.yaml` 训练
  `qpos + qvel + dig_cut_tokens` 的 dig；`carry/dump/return` 继续保持
  `qpos + qvel`。live 时 `primitive_planner_act` 只在调用 `dig` policy 时注入
  `dig_cut_tokens`，不会把 dig token 喂给 carry/dump/return。
- YuLong operator-first rollout 默认使用 `dig_cut_planner.mode=operator_prior`，
  prior 文件为
  `testbed/configs/planner_priors/yulong_operator_first_dig_cut_prior_v1.json`。
  该 prior 固定来自 26 条专业操作 operator-first relabel 数据中的 640 条 gold
  cycle，记录 P10/P50/P90 与 lineage；旧固定模板 planner 保留为
  `dig_cut_planner.mode=conservative_pose`，baseline tag 为
  `planner-baseline-conservative-pose-20260516`。

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
| YuLong FarmStick replayx20 qvel pilot | `testbed/configs/act_yulong_farmstick_3cycle_replay20_workskill_qvel.yaml` | 读取人工 3cycle 动作经 YuLong 修正控制重放后的 work-skill 数据 |
| YuLong V2.2 pro/internal pilot 录制 | `testbed/configs/teleop_yulong_v2_2_pro_pilot.yaml` | 当前新环境人工 teleop pilot 入口；默认 3 次 `dump_end` + 100 tail，使用 `contact_depth` QDS 和 V2.2 metadata |
| YuLong V2.2 pro full-task 录制 | `testbed/configs/teleop_yulong_v2_2_pro_full_task.yaml` | 专业师傅主录制入口；`max_steps=20000` 只是安全上限，人工保存结束；success 暂按 mass/productivity，不依赖 grid depth |
| YuLong V2.2 empty-box capacity 录制 | `testbed/configs/teleop_yulong_v2_2_empty_box_capacity.yaml` | 只用于“尽量挖空可达区域”的容量标定；手动保存，默认不作为训练主数据，也不把 empty box 当 task success |
| YuLong V2.2 pro full-task 5/10/15-dig GC-ACT diagnostic | `testbed/configs/act_yulong_v2_2_pro_full_task_{5,10,15}dig_gcact.yaml` | 仅保留为 diagnostic 对照；不作为正式 rollout 主线 |
| YuLong V2.2 pro full-task 5-dig GC-ACT diagnostic smoke | `testbed/configs/eval_yulong_v2_2_pro_full_task_5dig_gcact_smoke.yaml` | 仅用于诊断 one full-task 行为，不进入正式数据/评测主线 |
| YuLong V2.2 Cell Entry enriched raw VDS | `tb-build-cell-entry-v2_2 --dataset-dir <raw-dir> --output-dir <cell-entry-root> --storage-mode vds` | 追加 3x2 Cell Entry planned/actual/audit `/v2` 字段，并用 VDS 避免复制图像 |
| YuLong V2.2 operator-first relabel VDS | `tb-build-operator-first-v2_2 --dataset-dir data/yulong_v2_2_current_relabeled --output-dir <operator-first-root> --storage-mode vds` | 追加 effective deposit、operator cut corridor、return target 与 `dig_cut_tokens`；不覆盖 legacy `deposit_delta_kg` |
| YuLong V2.2 primitive VDS dry-run | `tb-build-primitives-v2_2 --raw-dir <cell-entry-root> --output-root <primitive-root> --storage-mode manifest --skip-return` | 只生成 window manifest/summary，用于切分 QC |
| YuLong V2.2 primitive VDS build | `tb-build-primitives-v2_2 --raw-dir <operator-first-root> --output-root <primitive-root> --storage-mode vds --boundary-profile v2_2_effect_release_fallback` | 从 operator-first enriched raw 直接切 `dig/carry/dump/return`，写 VDS primitive wrapper、tier 和 lineage |
| YuLong V2.2 conditioned dig 训练 | `testbed/configs/act_yulong_v2_2_pro_conditioned_dig_cell_entry_qvel.yaml` | dig 使用 `qpos + qvel + cell_entry_tokens`，读取 VDS primitive dig root |
| YuLong V2.2 operator-first 4P 500 epoch 训练 | `testbed/configs/act_yulong_v2_2_operator_first_4p_{dig_cut,carry,dump,return}_qvel.yaml` | dig 使用 `qpos + qvel + dig_cut_tokens`；carry/dump/return 使用 `qpos + qvel` |
| YuLong V2.2 operator-first primitive planner smoke | `testbed/configs/eval_yulong_v2_2_operator_first_primitive_planner_4p_500e_smoke.yaml` | 加载 4 个 operator-first checkpoint；live 只给 dig 注入 operator-prior `dig_cut_tokens` |
| YuLong V2.2 conservative planner baseline smoke | `testbed/configs/eval_yulong_v2_2_operator_first_primitive_planner_4p_500e_conservative_pose_smoke.yaml` | 回放旧 `conservative_pose` dig token 模板，用于 A/B 和 git baseline 对照 |
| YuLong V2.2 5-cycle clean-dump smoke | `testbed/configs/eval_yulong_v2_2_operator_first_primitive_planner_4p_500e_5cycle_clean_dump_smoke.yaml` | 5 dig 压力测试；bucket 残余阈值 `15kg`，dump/terminal hold 约 `2s`，默认不写 HDF5 |
| YuLong V2.2 conditioned dig primitive planner smoke | `testbed/configs/eval_yulong_v2_2_pro_primitive_planner_conditioned_dig_smoke.yaml` | `primitive_planner_act` 只给 dig 注入 Cell Entry token；carry/dump/return 仍为 `qpos + qvel` |
| YuLong FarmStick replayx20 rollout smoke | `testbed/configs/eval_yulong_farmstick_3cycle_replay20_workskill_qvel_smoke.yaml` | 单 rollout 接回 Unity；无 YuLong bootstrap，直接 smoke work policy |
| YuLong V2.2 四 primitive contact-depth 训练 | `testbed/configs/act_yulong_farmstick_3cycle_replay20_contact_depth_v2_2_4p_{dig,carry,dump,return}_qvel.yaml` | 小斗 YuLong 主训练入口；`qualified_dig_start=contact_depth` 后重切，四类各 40 条且无 reject |

YuLong operator-first 训练优化不改变图像分辨率或推理输入语义。当前配置仍读取原始
`fpv` 图像，只通过 `batch_size`、`num_workers`、`prefetch_factor`、
`hdf5_cache_size`、TF32/cudnn benchmark 和较低频率的 validation/plot 来提高吞吐；
如果出现 CUDA OOM，优先把对应 primitive 的 `batch_size` 下调。
| YuLong V2.2 四 primitive contact-depth smoke | `testbed/configs/eval_yulong_farmstick_3cycle_replay20_contact_depth_v2_2_4p_qvel_smoke.yaml` | `primitive_planner_act` + `scripted_qpos` reset bootstrap；使用 contact-depth dig 起点 qpos；dig->carry 质量阈值下调到 `20kg` |
| YuLong V2.2 四 primitive contact-depth 3-cycle smoke | `testbed/configs/eval_yulong_farmstick_3cycle_replay20_contact_depth_v2_2_4p_qvel_3cycle_smoke.yaml` | 同一组 contact-depth checkpoint；`target_cycle_gate=3`，用于验证 return 是否能接回下一轮 QDS |
| YuLong V2.2 四 primitive 旧对照 | `testbed/configs/act_yulong_farmstick_3cycle_replay20_v2_2_4p_{dig,carry,dump,return}_qvel.yaml` + `testbed/configs/eval_yulong_farmstick_3cycle_replay20_v2_2_4p_qvel_smoke.yaml` | 旧 progress QDS 切分结果，仅保留作对照 |
| V2.1 Stage 3 gcact 训练 | `testbed/configs/act_agx_v2_1_workskill_gcact.yaml` | `qpos + qvel + goal_tokens` 的 held-out 对照线 |
| V2.1 Stage 3 qvel live smoke | `testbed/configs/eval_agx_v2_1_stage3_workskill_qvel.yaml` | 把 Stage-3 qvel work ckpt 接回 Stage-2 hybrid live smoke |
| V2.1 Stage 4 rule planner 主评测 | `testbed/configs/eval_agx_v2_1_stage4_rule_planner.yaml` | 第一版 coarse replan 主入口；当前使用 soft corridor + `servo_reentry_pose`，官方 `2-cycle` 主门槛已通过 |
| V2.1 Stage 4 rule planner 3-cycle smoke | `testbed/configs/eval_agx_v2_1_stage4_rule_planner_3cycle_smoke.yaml` | Stage-4 多轮 smoke 入口；官方 `3-cycle smoke` 已通过一次真实 live 检查 |
| V2.2 Cell Entry enriched raw | `tb-build-cell-entry-v2_2 --dataset-dir <raw-dir> --storage-mode vds` | 追加 3x2 Cell Entry planned/actual/audit `/v2` 字段；推荐 VDS wrapper，不复制图像 |
| V2.2 四 primitive e500 训练 | `testbed/configs/act_agx_v2_2_4primitives_{dig,carry,dump,return}_qvel_e500.yaml` | baseline primitive configs；旧 carrytrim/safe-dump 结果保留作对照 |
| V2.2 ownership carry/dump e500 | `testbed/configs/act_agx_v2_2_4primitives_{carry,dump}_ownership_leftboost_qvel_e500.yaml` | 使用 history ownership + latest probe leftboost mix，只重训 `carry`/`dump` |
| V2.2 四 primitive 3-cycle smoke | `testbed/configs/eval_agx_v2_2_4primitives_qvel_3cycle_smoke.yaml` | `primitive_planner_act`，scripted geometry switch，`dump_done_hold_steps=30`，默认 `temporal_agg = true` |
| V2.2 ownership 3-cycle smoke | `testbed/configs/eval_agx_v2_2_4primitives_ownership_leftboost_qvel_3cycle_smoke.yaml` | 加载新 ownership `carry`/`dump` checkpoint；`dig`/`return` 复用当前 e500 |
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

V1/FarmStick 的 `task_success_tail` 录制在 success 后补完 tail 自动停止时，
会写入 `stop_reason = task_success_tail`；只有真正跑满 `max_steps` 才写
`max_steps_reached`。

`tb-label-v2_1` 可用 `--config <teleop-or-eval-yaml>` 复用同一份
`success.stage_success` 与 `reward` 阈值，避免 stage success 在录制、relabel
和容量标定之间漂移。

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
| `act_yulong_farmstick_3cycle_replay20_workskill_qvel.yaml` | YuLong pilot 训练线 | `qpos + qvel`，默认读取 `data/yulong_farmstick_3cycle_replay20_varseed_fixedobs_20260514_1337_v2_1_workskill` |
| `act_yulong_v2_2_pro_full_task_{5,10,15}dig_gcact.yaml` | YuLong pro full-task GC-ACT diagnostic | 仅保留诊断 one full-task 行为，不作为正式 rollout 主线 |
| `eval_yulong_v2_2_pro_full_task_5dig_gcact_smoke.yaml` | YuLong pro full-task 5-dig diagnostic smoke | 仅用于诊断；正式主线回到四 primitive layered control |
| `act_yulong_v2_2_pro_conditioned_dig_cell_entry_qvel.yaml` | YuLong V2.2 conditioned dig 主线 | `qpos + qvel + cell_entry_tokens`，读取 VDS primitive dig root |
| `act_yulong_v2_2_operator_first_4p_dig_cut_qvel.yaml` | YuLong V2.2 operator-first dig 主线 | `qpos + qvel + dig_cut_tokens`，读取 `data/yulong_v2_2_current_primitives_operator_first/dig` |
| `act_yulong_v2_2_operator_first_4p_{carry,dump,return}_qvel.yaml` | YuLong V2.2 operator-first 其他 primitive 主线 | `qpos + qvel`，读取 `data/yulong_v2_2_current_primitives_operator_first/{carry,dump,return}` |
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
| `act_agx_v2_2_4primitives_dig_qvel_e500.yaml` | V2.2 dig primitive smoke | `qpos + qvel`，默认读取 `data/agx_v2_2_4primitives_260426/dig` |
| `act_agx_v2_2_4primitives_carry_qvel_e500.yaml` | V2.2 carry primitive smoke | `qpos + qvel`，默认读取 `data/agx_v2_2_4primitives_safe_dump_260427/carry` |
| `act_agx_v2_2_4primitives_dump_qvel_e500.yaml` | V2.2 dump primitive smoke | `qpos + qvel`，默认读取 `data/agx_v2_2_4primitives_safe_dump_260427/dump` |
| `act_agx_v2_2_4primitives_return_qvel_e500.yaml` | V2.2 return primitive smoke | `qpos + qvel`，默认读取 `data/agx_v2_2_4primitives_260426/return` |
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
    - 目的是去掉已经贴近 target 才开始 dump 的 close-call 样本，避免 BC 学到低 boom + 强 curl 的硬碰撞模式
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
    - 只拒绝“还没真正到 dump area 上方就明显提前倒、接近半桶级别”的 severe early spill
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

### V2.2 primitive 数据构建

先对 raw 数据补写 Cell Entry planned/actual/audit 字段：

```bash
tb-build-cell-entry-v2_2 \
  --dataset-dir data/agx_teleop_v2_1_multi_raw_refreshed_targetgeo_tail50_260424183039 \
  --output-dir data/agx_teleop_v2_1_multi_raw_refreshed_targetgeo_tail50_cell_entry_v2_2
```

这个 builder 只生成 enriched raw 和 `cell_entry_summary.json`；后续
`tb-build-primitives-v2_2` 会把 `/v2/step` 中已有字段随 primitive window 一起切片，
并在来源 cycle 标签存在时保留一行 `/v2/cycle`，同时把 `stage_success`、
`cycle_success`、Cell Entry audit 等常用 cycle 级 QC 标量镜像到 primitive
metadata，方便后续训练集过滤。planner/audit 决策不放在 primitive builder 中重做。

当前四 primitive root 由下面命令生成到 data disk，并通过 `data/` 下 symlink 暴露：

```bash
tb-build-primitives-v2_2 \
  --workskill-dir data/agx_teleop_v2_1_refresh_tail50_workskill_clean_v3_targetsafe_v2_1c_260424183039 \
  --raw-dir data/agx_teleop_v2_1_multi_raw_refreshed_targetgeo_tail50_260424183039 \
  --raw-dir data/agx_teleop_v2_1_multi_raw_new_refreshed_targetgeo_tail50_260424183039 \
  --raw-dir data/agx_teleop_v2_1_multi_raw_carryfix_refreshed_targetgeo_tail50_260424183039 \
  --raw-dir data/agx_teleop_v2_1_multi_raw_quality_2604241251_refreshed_targetgeo_tail50_260424183039 \
  --output-root /data/pingfan/excavator_testbed_data_archive/agx_v2_2_4primitives_safe_dump_260427
ln -sfn /data/pingfan/excavator_testbed_data_archive/agx_v2_2_4primitives_safe_dump_260427 \
  data/agx_v2_2_4primitives_safe_dump_260427
```

切分语义：

- `dig`: `qualified_dig_start` 到 `carry/approach_dump` 前
- `carry`: `carry_start -> first approach_dump stage`，只负责 loaded transport
- `dump`: `first approach_dump stage -> dump_end`，负责 move to top of target、
  alignment、release 和 post-dump hold
- `return`: full raw 中的 `dump_end -> next qualified_dig_start`

`dump ownership boundary` 使用 deterministic rule：`first approach_dump stage`。
如果 stable pre-dump curl-out 早于 `approach_dump`，新版 builder 会 reject 该
carry/dump window，而不是把这段混合动作分给 `carry` 或 `dump`。V2.2 builder 不再
fallback 到官方 mass-based `dump_start`；找不到带 dump area geometry 的安全 onset 的
dump window 会被 reject，并写入 `summary.json`。完整 phase boundary 定义见
`docs/v2_2_4primitives/phase_boundaries.md`。

YuLong new-env pilot 使用额外的边界 profile：

```bash
tb-build-primitives-v2_2 \
  --workskill-dir data/yulong_farmstick_3cycle_replay20_varseed_fixedobs_20260514_1337_v2_1_workskill \
  --raw-dir data/yulong_farmstick_3cycle_replay20_varseed_fixedobs_20260514_1337_v2_1_relabeled \
  --output-root data/yulong_farmstick_3cycle_replay20_v2_2_4primitives_effect_release_20260514 \
  --return-max-transition-len 600 \
  --boundary-profile v2_2_effect_release_fallback
```

这个 profile 只在没有 `approach_dump` 标签、但存在稳定 release/curl-out onset 且
最终 dump 通过 good-quality acceptance 时启用。它把 `carry -> dump` 边界前移到
effect-based release onset，避免 `carry` 学到开斗动作。当前 YuLong pilot root
构建结果为 `dig=20 / carry=20 / dump=20 / return=20`，`reject_counts={}`。

2026-04-27 ownership probe（旧 boundary rule 结果，保留作诊断 baseline）:

- Raw: `/data/pingfan/excavator_testbed_data_archive/agx_v2_2_ownership_probe_raw_260427_1ep`
- 4p root: `data/agx_v2_2_4primitives_ownership_boundary_260427_1ep`
- Counts: `dig=3`, `carry=3`, `dump=3`, `return=0` (`--skip-return`)
- Carry QC: bucket mass loss `0kg`, `tail_stable_strong_curl_out_count=0`,
  `ownership_boundary_source_counts={stable_curl_out: 3}`
- Dump QC: hard collision windows `0`, near collision windows `0`,
  dump starts `30-67` steps before official mass-based `dump_start`

2026-04-27 history ownership rebuild（旧 boundary rule 结果，不能直接代表新版
middle-handoff builder）:

- Source workskill:
  `data/agx_teleop_v2_1_refresh_tail50_workskill_clean_v3_targetsafe_v2_1c_260424183039`
- 4p history root:
  `data/agx_v2_2_4primitives_ownership_history_260427`
- Counts: `dig=64`, `carry=27`, `dump=27`, `return=0` (`--skip-return`)
- Carry QC: bucket mass loss `0kg`, `tail_stable_strong_curl_out_count=0`,
  boundary sources `{stable_curl_out: 23, approach_dump_stage: 4}`
- Rejects: `30` windows missing dump ownership boundary and `7` missing safe
  dump intent; these are not used for carry/dump training.

Current carry/dump smoke training mix:

- Root: `data/agx_v2_2_4primitives_ownership_history_probe_leftboost_260427`
- 注意：该 root 是旧 boundary rule 训练 mix。新版 builder 会要求 16-field dump-area
  geometry，并把 stable curl-out before `approach_dump` 的窗口 reject；因此需要用
  刷新后的新 geometry 数据重建 carry/dump root 后再训练。
- Mix rule: history ownership all + latest ownership probe all cycles `4x` +
  probe cycle2/source_cycle_id `1` extra `8x`
- Counts: `carry=47`, `dump=47`
- Training configs warm-start model weights from the previous V2.2 carry/dump
  best checkpoints, but reset optimizer/best-state and start this dataset at
  epoch `0`.
- Finished smoke training:
  - carry: `/data/pingfan/excavator_testbed_runs/ckpts/v2_2_4primitives/carry_qvel_ownership_history_probe_leftboost_e500_260427/policy_best.ckpt`,
    best epoch `499`, best val loss `0.1020`
  - dump: `/data/pingfan/excavator_testbed_runs/ckpts/v2_2_4primitives/dump_qvel_ownership_history_probe_leftboost_e500_260427/policy_best.ckpt`,
    best epoch `190`, best val loss `0.1109`
- Smoke eval config:
  `testbed/configs/eval_agx_v2_2_4primitives_ownership_leftboost_qvel_3cycle_smoke.yaml`

2026-04-28 middle-handoff data probe:

- `data/agx_teleop_v2_1_multi_raw_targetgeo16_smoke_260428` and
  `data/agx_v2_2_ownership_probe_raw_targetgeo16_260428` replayed cleanly with
  16-field env_state.
- The new builder accepted `dig` only and rejected all `carry/dump` windows.
- Decision: do not batch-train from these roots. Record new demonstrations with
  `docs/v2_2_4primitives/phase_boundaries.md` as the manipulation contract.

V2.2 scripted planner 的 dump readiness 使用 target-relative geometry：
`mass_in_bucket_kg` 足够、`bucket_height_above_target_rim_m >= 0.30`，并且位置满足
`bucket_dump_area_footprint_outside_distance_m <= dump_ready_max_dump_area_footprint_outside_distance_m`
以及可选的 signed `bucket_dump_area_relative_x_m/z_m` window。
在 `dump_area_relative` 模式下，即使 `dump_ready_require_over_footprint=false`，
也仍然必须满足 dump-area-relative 位置条件；这个开关只表示不强制 Unity 的
`bucket_over_target_footprint_mask`，不能让 planner 绕过位置检查。
Unity 的 `bucket_over_target_footprint_mask` 现在表示 dump-area mask，用于诊断
bucket 是否在dump area上方；当前 3-cycle ownership smoke 配置使用 `dump_area_relative`，并把
`dump_ready_max_horizontal_distance_m` 设为 `null`，不再让 scalar horizontal
distance 单独触发 `carry -> dump`。当前 4p approach handoff 不再只用 unsigned
`outside`；它使用 good20 teleop 分布得到的 corridor：
`outside<=1.35m`、`-4.30<=dump_area_relative_x<=2.00`、
`2.75<=dump_area_relative_z<=3.50`。`outside` 只表示离 dump-area footprint 多近，不能区分
tail/middle/front，因此不应单独作为 handoff rule。
当前 smoke config
设置 `dump_done_use_boundary_event=false`，所以 `dump_done` 后保持 dump
skill `30` step 再切 return，不让 Unity 的即时 `dump_end` event 绕过这个 hold。
这个 hold 用来跨过 ACT chunk/temporal aggregation 边界，避免 return policy 在土刚落入
dump area时立刻回摆，把土从边缘带出。
`dig -> carry` 只要求 bucket 已 loaded；从 dig 区离开属于 carry primitive 的职责，
不再要求 `min_distance_to_dig_area_m >= 0.20`。

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
| `eval_agx_v2_2_4primitives_qvel_3cycle_smoke.yaml` | V2.2 4-primitives smoke | 加载 `dig/carry/dump/return` 四个 ACT ckpt；scripted planner 只用 target-relative geometry 切换，不把 `env_state` 输入低层 ACT |
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
- `cycle_deposited_fraction_mean` / `cycle_deposited_fraction_min`
- `cycle1_deposited_fraction` / `cycle2_deposited_fraction` / `cycle3_deposited_fraction`
- `cycle_post_dump_target_mass_drop_mean_kg` / `cycle_post_dump_target_mass_drop_max_kg`
- `cycle1_post_dump_target_mass_drop_kg` / `cycle2_post_dump_target_mass_drop_kg` / `cycle3_post_dump_target_mass_drop_kg`
- `low_cycle_deposited_fraction_count`
- `high_cycle_post_dump_drop_count`
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
- `low_cycle_deposited_fraction_rate`
- `high_cycle_post_dump_drop_rate`
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

### YuLong FarmStick 3cycle replayx20 pilot

这条线用人工录制的 `data/yulong_farmstick_3cycle_raw_20260514/episode_0.hdf5`
作为动作老师，但 observation/env_state 通过当前 YuLong Unity 控制器重新采集，
用于避开早期录制中 swing 被土壤反力拖动后的状态漂移。
`replay_sources20_varseed` 中的 20 个源 HDF5 会保留同一动作序列，但把
`metadata.seed` 改成不同值，避免训练集退化成同 seed 的重复 replay。
`equipment_model: yulong` 在 train/eval/ACT 维度解析中按 YuLong/AGX 四轴挖机处理：
action 为 4 维，`qpos + qvel` 低维输入为 8 维。

1. `tb-replay --episode data/yulong_farmstick_3cycle_raw_20260514_replay_sources20_varseed --config testbed/configs/teleop_v2_1_multi_raw.yaml --record-output-dir data/yulong_farmstick_3cycle_replay20_varseed_fixedobs_20260514_1337`
2. `tb-label-v2_1 --dataset-dir data/yulong_farmstick_3cycle_replay20_varseed_fixedobs_20260514_1337 --scenario-id s0_truck --qualified-dig-start-mode contact_depth`
3. `tb-build-workskill-v2_1 --dataset-dir data/yulong_farmstick_3cycle_replay20_varseed_fixedobs_20260514_1337_v2_1_relabeled`
4. `tb-train --config testbed/configs/act_yulong_farmstick_3cycle_replay20_workskill_qvel.yaml`
5. `tb-build-primitives-v2_2 --workskill-dir data/yulong_farmstick_3cycle_replay20_varseed_fixedobs_20260514_1337_contact_depth_v2_1_workskill --raw-dir data/yulong_farmstick_3cycle_replay20_varseed_fixedobs_20260514_1337_contact_depth_v2_1_relabeled --output-root data/yulong_farmstick_3cycle_replay20_contact_depth_v2_2_4primitives_effect_release_20260514 --return-max-transition-len 600 --boundary-profile v2_2_effect_release_fallback`
6. `tb-train --config testbed/configs/act_yulong_farmstick_3cycle_replay20_contact_depth_v2_2_4p_dig_qvel.yaml`
7. `tb-train --config testbed/configs/act_yulong_farmstick_3cycle_replay20_contact_depth_v2_2_4p_carry_qvel.yaml`
8. `tb-train --config testbed/configs/act_yulong_farmstick_3cycle_replay20_contact_depth_v2_2_4p_dump_qvel.yaml`
9. `tb-train --config testbed/configs/act_yulong_farmstick_3cycle_replay20_contact_depth_v2_2_4p_return_qvel.yaml`
10. `tb-eval --config testbed/configs/eval_yulong_farmstick_3cycle_replay20_contact_depth_v2_2_4p_qvel_smoke.yaml`
11. `tb-eval --config testbed/configs/eval_yulong_farmstick_3cycle_replay20_contact_depth_v2_2_4p_qvel_3cycle_smoke.yaml`

当前锁定口径：

- source raw 数据集继续只读
- YuLong 小斗满载质量约 `50kg`，`qualified_dig_start` 用
  `contact_depth` 模式，以 dig-area 距离和下挖深度为主，不再依赖质量增量
- 当前 contact-depth V2.2 root 为
  `data/yulong_farmstick_3cycle_replay20_contact_depth_v2_2_4primitives_effect_release_20260514`，
  计数为 `dig=40 / carry=40 / dump=40 / return=40`，reject 为 0；由于 dig
  起点早于旧 progress QDS，smoke planner 的 `dig_to_carry_min_bucket_mass_kg`
  使用 `20kg`，避免继续按旧大斗/旧切分的 `55kg` 口径拖住 dig skill
- sibling 输出固定为：
  - `data/yulong_farmstick_3cycle_replay20_varseed_fixedobs_20260514_1337_contact_depth_v2_1_relabeled`
  - `data/yulong_farmstick_3cycle_replay20_varseed_fixedobs_20260514_1337_contact_depth_v2_1_workskill`
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
- ACT 训练/eval 支持 `policy.image_mask`，用于把 RGB 输入先变成 masked RGB，再送进
  现有 3-channel ResNet backbone。最小配置示例：

```yaml
policy:
  image_mask:
    enabled: true
    mode: multiply
    cameras:
      fpv:
        rect_xyxy_norm: [0.10, 0.35, 0.90, 0.95]
```

`rect_xyxy_norm` 是 `[x0, y0, x1, y1]` 的归一化像素窗口，mask 外像素置零。
如果后续数据集或 Unity 输出真实 mask，也可以把 camera spec 改成
`mask_dataset: "/observations/image_masks/fpv"`；设置
`require_mask_dataset: true` 时缺失 mask 会直接报错。这个 mask 只改视觉输入，
不把 `env_state` 加进 ACT low-dim 输入。
- 旧低频 sector `goal_tokens` 只作为 diagnostic/legacy 对照。正式 YuLong V2.2
  主线使用 Cell Entry token，只参数化 `dig`：

```yaml
policy:
  class: "primitive_planner_act"
  cell_entry:
    enabled: true
  dig_low_dim_keys: ["qpos", "qvel", "cell_entry_tokens"]
  return_low_dim_keys: ["qpos", "qvel"]
  carry_low_dim_keys: ["qpos", "qvel"]
  dump_low_dim_keys: ["qpos", "qvel"]
```

live planner 会把 planned cell / entry envelope 转成 10D `cell_entry_tokens`，
并且只在调用 `dig` policy 时注入。rollout JSONL 会记录
`cell_entry_selected_cell_id`、planned entry、audit reason 和
`cell_entry_token_injected`，用于区分 planner miss、return miss、dig miss 与 dump fail。
- eval 支持 `eval.stream_rollout_logs: true`，会在 rollout 过程中写
  `rollout_XXX.partial.jsonl`，中途停止时也能保留第 2/第 3 cycle 的逐步证据。
- compare 的主口径固定为：
  - `cycle3_success_rate`
  - `transition_timeout_rate`
  - `completed_transition_count`
- 顶层 `dump_complete_final_hold_success_rate` 只作为辅助参考
- 如需把最新 YuLong 四 primitive checkpoint 直接 rollout 成带 V2.2 字段的
  HDF5，使用：
  `tb-eval --config testbed/configs/eval_yulong_farmstick_3cycle_replay20_contact_depth_v2_2_4p_qvel_3cycle_record_hdf5.yaml`
  输出目录默认为
  `data/yulong_v2_2_plan_fields_contact_depth_4p_policy_rollout_20260514`。

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
