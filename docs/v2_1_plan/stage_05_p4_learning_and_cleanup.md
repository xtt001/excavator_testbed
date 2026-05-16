# Stage 05 — P4 Learning Transition and Cleanup

## Goal

先把 `learned transition` 从 feasibility 提升到可部署候选，并在此基础上建立受控 fallback 与清理主线。

## Status

- State: `in_progress`
- Priority: `current`

## In Scope

- transition imitation
- `clean_v2` transition dataset
- high-quality `workskill_clean_v2` dataset
- `hybrid_online_logs`
- scripted fallback
- learned/scripted compare 回归
- 过渡代码清理

## Out of Scope

- learned high-level planner 的正式落地

## Main Deliverables

- learned transition 数据闭环
- `transition_clean_v2` 数据清洗规则与 `summary.json`
- transition teacher/student 训练流程
- hybrid online logs
- scripted fallback 机制
- Stage-5 compare 配置
- cleanup 变更清单

## Transition Learning Plan

### Teacher Source

- scripted transition rollout 作为 imitation teacher

### Training Data

- scripted transition 片段
- 自然 teleop transition 片段

当前 feasibility 路径已经有最小落地能力：

- `tb-build-transition-v2_1`
- `data/agx_teleop_v2_1_multi_raw_transition`
- `act_agx_v2_1_multi_raw_transition_qvel.yaml`
- `data/agx_teleop_v2_1_multi_raw_transition_clean`
- `act_agx_v2_1_multi_raw_transition_clean_qvel.yaml`
- `data/agx_teleop_v2_1_multi_raw_transition_clean_v2`
- `act_agx_v2_1_multi_raw_transition_clean_v2_qvel.yaml`

这条线当前只用于验证 `dump_end -> next qualified_dig_start` 的 natural teleop transition 是否可学，
不改变当前 scripted transition 的默认部署地位。

当前 Stage 5 已把 clean 主线正式提升为：

- `tb-build-transition-v2_1 --clean-profile stage5`
- 输出目录：`data/agx_teleop_v2_1_multi_raw_transition_clean_v2`
- 训练配置：`testbed/configs/act_agx_v2_1_multi_raw_transition_clean_v2_qvel.yaml`

当前 `stage5` clean 规则固定包含两层：

- 长度过滤：
  - `transition_len <= 420`
- 行为过滤：
  - `late_qds_failure`
  - 高 `pause_ratio` 的明显犹豫样本

builder 会同步写出 `summary.json`，至少包含：

- 输入样本数
- 保留样本数
- reject reason 计数
- 长度分布
- gap 分布

当前首轮 `clean_v2` 构建结果已经落地为：

- 输入 transition windows: `40`
- 保留样本数: `31`
- reject reasons:
  - `late_qds_failure = 6`
  - `overlong_transition_len = 3`
- 当前保留集长度分布：
  - `min = 219`
  - `max = 412`
  - `mean = 299.6`

### Deployment Strategy

- learned transition 接入 hybrid policy
- scripted transition 作为 fallback 保留

当前 Stage 5 的部署边界固定为：

- `clear_target -> corridor_align`：
  - 继续 scripted
- `wait_next_dig`：
  - 默认尝试 learned transition
- learned 仅在 `wait_next_dig` 子段接管，不替换 Stage-4 的 rule planner，也不改 work policy 输入

当前 compare / deploy 入口已经接上：

- `testbed/configs/eval_agx_v2_1_stage4_rule_planner_learned_transition_3cycle_smoke.yaml`
- `testbed/configs/eval_agx_v2_1_stage4_rule_planner_learned_transition_clean_3cycle_smoke.yaml`
- `testbed/configs/eval_agx_v2_1_stage5_scripted_transition_compare_5rollouts.yaml`
- `testbed/configs/eval_agx_v2_1_stage5_learned_transition_clean_v2_compare_5rollouts.yaml`
- `testbed/configs/eval_agx_v2_1_stage5_learned_transition_clean_v2_fallback_compare_5rollouts.yaml`

当前 fallback 语义已经接入 `hybrid_planner_act`：

- learned transition 超过局部预算或持续无进展时，可在当次 rollout 中切回 scripted `wait_next_dig`
- fallback 只作用于当前 transition，不中断 rollout
- rollout / summary 额外输出：
  - `transition_policy_mode`
  - `transition_fallback_count`
  - `transition_fallback_reason`

这条线当前的主目标不是“立刻完全替换 scripted”，而是把 learned transition 做成：

- 可对照
- 可回退
- 可多 rollout 比较
- 不破坏主线部署

## Cleanup Plan

完成 learned transition 接入后，清理：

- `fixed_sequence_planner` 的临时依赖
- 旧 phase-1 ready-anchor 残件
- Stage 2 中为了最小闭环引入的过渡逻辑

## Tests

- `transition_clean_v2` 数据构建测试
- learned vs scripted 对照评测
- scripted fallback 切换测试
- continuity 指标对照
- collision 指标对照

当前 Stage 5 compare 的主口径固定为：

- 主指标：
  - `cycle3_success_rate`
  - `transition_timeout_rate`
  - `completed_transition_count`
- 次指标：
  - `dump_to_next_dig_gap_steps`
  - `pause_ratio`
  - `mean_action_jerk`
  - `boundary_jump_l1`
- 顶层 `dump_complete_final_hold_success_rate` 只作为辅助参考

同时，Stage 5 起 evaluator 必须同步输出动作质量指标，避免只看 success gate。当前至少包括：

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

同时，Stage 5 现在允许直接按质量规则重建高质量 work-skill 数据集，用来优先修复当前 `WORK` policy 的坏动作。当前入口为：

- `tb-build-workskill-v2_1 --dataset-dir data/agx_teleop_v2_1_multi_raw_relabeled --clean-profile stage5`
- 输出目录：`data/agx_teleop_v2_1_multi_raw_workskill_clean_v2`
- 训练配置：
- `testbed/configs/act_agx_v2_1_multi_raw_workskill_clean_v2_qvel.yaml`
- `testbed/configs/act_agx_v2_1_multi_raw_workskill_clean_v2_gcact.yaml`
- `testbed/configs/act_agx_v2_1_multi_raw_new_workskill_clean_v2_qvel.yaml`
- `testbed/configs/act_agx_v2_1_multi_raw_new_workskill_clean_v3_qvel.yaml`
- `testbed/configs/act_agx_v2_1_multi_raw_all_workskill_clean_v3_qvel.yaml`

当前 `stage5` workskill 过滤规则优先剔除：

- `flat_bucket_qds`
- `far_dump_start`
- `near_dump_start`
- `collision_in_cycle`
- `low_carry_efficiency`
- `high_residual_bucket_mass`
- `early_dig_escape`
- 高 `pause_ratio` 的明显犹豫样本

当前首轮 clean 结果已经落地为：

- 输入 workskill cycles: `40`
- 保留样本数: `29`
- 当前主要 reject reasons:
  - `far_dump_start = 7`
  - `flat_bucket_qds = 3`
  - `collision_in_cycle = 1`

当前 high-quality work line 的 smoke 评测入口也已接上：

- `testbed/configs/eval_agx_v2_1_stage5_workskill_clean_v2_qvel_3cycle_smoke.yaml`
- `testbed/configs/eval_agx_v2_1_stage5_workskill_clean_v2_qvel_newdata_3cycle_smoke.yaml`
- `testbed/configs/eval_agx_v2_1_stage5_workskill_clean_v3_qvel_newdata_3cycle_smoke.yaml`
- `testbed/configs/eval_agx_v2_1_stage5_workskill_clean_v3_qvel_alldata_3cycle_smoke.yaml`

为了专门压掉“下去了但没咬住”的坏动作，Stage 5 现在允许进一步启用 stricter 的 work-skill 清洗入口：

- `tb-build-workskill-v2_1 --dataset-dir data/agx_teleop_v2_1_multi_raw_new_relabeled --clean-profile stage5_strict`
- `tb-build-workskill-v2_1 --dataset-dir data/agx_teleop_v2_1_multi_raw_relabeled --clean-profile stage5_strict`

这一版会额外关注 `qualified_dig_start` 后前 `80` 步内的起挖质量，包括：

- 更严格的 `qds_bucket_qpos`
- 前 `80` 步内是否形成足够的早期增重
- 是否很快丢失 dig contact
- 是否在早期形成一点质量后又快速掉回接近空桶
- 是否很快离开 dig area

当前更严格的 `clean_v3` 主训练线已经合并旧+新两批 workskill：

- 旧批次：`24 / 40`
- 新批次：`31 / 40`
- 合并后主训练集：`55` 条高质量 cycles
- 因为合并进了旧批次较长窗口，当前全量 strict `WORK` 训练配置默认把 `episode_len` 提到 `1200`
- 为了给下一批 later-cycle 录数和 QC 提前铺路，当前 relabel 还会同步补写 `/v2/step/work_stage_id`：
  - `none`
  - `entry_to_bite`
  - `first_bite`
  - `rebite_recovery`
  - `carry`
  - `approach_dump`
  - `dump`
- 这套 `work_stage_id` 当前优先服务两件事：
  - later-cycle `first_bite` / `rebite_recovery` 诊断
  - truck approach / pre-dump 录数质量回看

同时，Stage 5 保留最严格的 `stage5_cleanest -> clean_v4` workskill 过滤线作为诊断工具，专门用来定位两类最烦人的坏习惯：

- `cycle3` 前 80 步那种“先浅触地、带出一点土、漏一点、再重新开始真 dig”的 `probe-then-reload`
- `cycle1` / transport approach 里那种“还没真正到 target 就提前 curl out 导致漏料”的 `pretarget_spill_proxy`

当前 `clean_v4` 结果是：

- 旧批次：`9 / 40`
- 新批次：`15 / 40`
- 合并后共有 `24` 条 cycles

这说明：

- `clean_v4` 的诊断信号有用，确实能把目标坏习惯卡得更紧
- 但当前 `24` 条 cycle 对主 `WORK` 训练太少，且分布收缩过重
- 所以它现在只适合作为：
  - severe early dump / pre-target spill 定位工具
  - 过严过滤口径的对照 smoke
  - 后续补录数据的质量提示

## Current Diagnosis

当前 rollout 的核心问题，已经不能只归因于“数据不够干净”。更准确的判断是：

- 问题不主要是数据质量，而是 supervision 方式还在教“理想路径上的单轮模仿”
- 但 live rollout 真正需要的是：
  - later-cycle 的 first-bite 果断性
  - failed-bite 后的局部 recovery
  - truck approach / dump 的安全余量与 carry 纪律

当前最需要补的不是“更多 nominal 3-cycle 成功轨迹”，而是：

- later-cycle `left/right` work 的 first-bite 高质量样本
- failed first-bite 后的“局部 re-bite / recovery”示教
- truck 顶部上方再 dump，而不是 truck tail 提前倒料
- carry 阶段保持 bucket，不在接近 truck 前提前 curl out

## Next Recording Guidance

下一批录数的目标不是“单纯增加条数”，而是**增加闭环策略覆盖**。具体按下面的口径录：

### 1. 录真正多样的 sector / cycle 组合

- 不要只录 `mid -> left -> right`
- 也要录：
  - `mid -> right -> left`
  - `mid -> left -> mid`
  - `mid -> right -> mid`
- 当前 sector 阈值固定为：
  - dig-area anchors: leftmost `0.43`, mid `0.50`, rightmost `0.56`
  - `left: swing < 0.4733`
  - `mid: 0.4733 <= swing < 0.5167`
  - `right: swing >= 0.5167`

### 2. later-cycle first bite 要录两种“高质量模式”

- **nominal 一次咬进去**
  - bucket 碰土前已卷入
  - 接触后持续 `curl in + press`
  - 前 `40-80` 步形成稳定增重
- **clean recovery**
  - 如果第一次 bite 明显偏弱，不要离开 dig area
  - 在本地做一次干净的 `re-bite`
  - 再继续 carry / dump

注意：这里需要的是“可恢复示教”，不是“乱试探、乱抖、卡很久”的坏样本。

### 3. carry / approach-to-dump 要补“纪律性”

- 允许少量中等 swing spill
- 但不允许：
  - truck tail 提前 dump
  - 接近 truck 前明显提前 curl out
  - 太贴 truck 导致擦碰

### 4. 录数时优先检查这些主观标准

- cycle2 / cycle3 第一次 bite 是否就够果断
- 如果第一次 bite 不够好，是否做了局部 clean recovery，而不是直接离开 dig area
- carry 过程中 bucket 是否一直稳住
- 是否到 truck 顶部/有效上方才开始 dump
- truck 附近是否留了 clear margin，而不是贴边硬挤

当前 `clean_v4` 的 spill 口径已调整为：

- 允许 moderate swing spill
- 不再因为中等量的 approach spill 就一票否决
- 只拒绝“还没真正到 truck 顶部就明显提前倒、接近半桶级别”的 severe early spill

也就是说，Stage 5 当前的正式 `WORK` 主训练线仍然是 `clean_v3`。`clean_v3b` / `clean_v4` 已经判断为过严，当前只作为诊断过滤线，用来观察 early dump / severe pre-target spill，而不作为主训练集。

为了诊断 `clean_v4` 是否把 later-cycle 分布削得过薄，Stage 5 也保留了一条更平衡的诊断口径：

- `tb-build-workskill-v2_1 --dataset-dir data/agx_teleop_v2_1_multi_raw_workskill_clean_v3 --clean-profile stage5_balanced --output-dir data/agx_teleop_v2_1_multi_raw_workskill_clean_v3b`
- `tb-build-workskill-v2_1 --dataset-dir data/agx_teleop_v2_1_multi_raw_new_workskill_clean_v3 --clean-profile stage5_balanced --output-dir data/agx_teleop_v2_1_multi_raw_new_workskill_clean_v3b`

这条 `stage5_balanced -> clean_v3b` 诊断规则固定为：

- 保留 `clean_v3` 的 later-cycle bite 质量约束
- 额外吸收 `v4` 中信号最强的两条规则：
  - `probe_then_reload`
  - severe `pretarget_spill_proxy`
- 同时把 `far_dump_start` 从宽松口径收回到更贴近 truck 顶部的折中阈值
- `stage5_strict`/v3 现在启用显式 target geometry contract：必须有 `target_horizontal_distance_m`、`bucket_height_above_target_rim_m`、`bucket_over_target_footprint_mask`、`dump_clearance_ok_mask`，缺任一项会标成 `missing_target_geometry`；标量 `min_distance_to_target_m` 不再作为 fallback。
- target-safe 下界改为基于 `target_horizontal_distance_m`：`target_horizontal_distance_m < 0.35` 会标成 `near_dump_start` 并剔除，用来去掉贴近 target 才开始 dump 的 close-call 样本，避免 rollouts 里低 boom + 强 curl 放大成硬碰撞。
- 当前 target-safe qualitymix 已落地为 `74` 条：旧档案 `51` 条 + `2604241251` terminal-fix 质量补录 `23` 条，sector split 为 `left = 18`, `mid = 40`, `right = 16`。
- 当前 target-safe smoke eval 也启用 live WORK safety guard：
  - approach 区：loaded 且 `target_horizontal_distance_m < 1.25` 且 dump clearance 不满足时，先把 bucket 强 dump action 软限到不小于 `-0.30`，并至少给 boom `+0.04`。
  - hard guard 区：loaded 且 `target_horizontal_distance_m < 0.45` 且 dump clearance 不满足时，把 bucket dump action 进一步限到不小于 `-0.15`，并至少给 boom `+0.08`。
  - dump clearance 以 Unity 的 `dump_clearance_ok_mask` 为准；DumpArea 水平距离可使用目标侧 dump 容差，垂直方向仍要求 `bucket_height_above_target_rim_m >= 0.0`。
  - summary 记录 `work_target_guard_count`，用于确认 guard 是否介入。
  - 当前 3-cycle smoke 配置在 `target_cycle_gate = 3` 后额外保留 `25` 步 terminal hold，避免刚出现第 3 次 `dump_end` 就截断 `dump_complete_final_hold` 的末尾连续计数。

当前旧数据 audit 结论：

- `tb-audit-target-geometry --dataset-dir data/agx_teleop_v2_1_multi_raw_all_workskill_clean_v3_qualitymix_targetsafe_2604241251_v2_1c`
- 结果：`74 / 74` episodes 都是 legacy `env_state_width = 9`，4 个 target geometry 字段覆盖率都是 `0.0`
- 决策：这批旧数据仍可留作非 target-geometry 诊断/训练材料，但不要继续混入 target-safety workskill 训练；需要按新 contract 补录新数据

当前 `clean_v3b` 结果是：

- 旧批次：`18 / 24`
- 新批次：`27 / 31`
- 合并后：`45` 条 cycles

这条线在数量上明显比 `clean_v4` 更健康，但对当前主训练仍偏严格；正式 `WORK` 训练继续优先使用 `clean_v3`。

同时，Stage 5 已修正 sector relabel 口径，避免把 dig area 内的 later-cycle workskill 全部误标成 `mid`。当前固定改为基于 `qualified_dig_start` 时的 dig-area 标定 swing 分桶：

- dig-area anchors: leftmost `0.43`, mid `0.50`, rightmost `0.56`
- `swing < 0.4733 -> left`
- `0.4733 <= swing < 0.5167 -> mid`
- `>= 0.5167 -> right`

transition / corridor 命名也同步到同一套物理方向定义：

- 低 swing = `left`
- 高 swing = `right`

运行时会自动纠正历史 YAML 中镜像的 `transition.bands` 命名，避免 rollout
日志里把物理 `right` 记成 `left`。

按这套新阈值重标后，当前 `data/agx_teleop_v2_1_multi_raw_all_workskill_clean_v3` 的 sector 分布为：

- `left = 15`
- `mid = 31`
- `right = 9`

这一步的目的不是把整个 swing 归一化范围三等分，而是只在真实 dig area 的有效窄带内划分 `left / mid / right`。

同时要注意一个 terminal dump 的数据链路细节：旧版 `target_dump_count` 录制会在在线 detector 数到最后一次 `dump_end` 后立即停止，而 recorder 写的是 step 前 observation。因此最后一次触发 `dump_end` 的 post-step observation 可能不会落进 HDF5。当前录制已恢复 `50` 步 terminal tail；离线 relabel 仍会在 metadata 明确显示 `completed_dump_count` 已达到目标时，把最后一个已记录 timestep 作为 terminal `dump_end` 近似点，避免旧 raw 的第三铲 workskill 被静默丢掉。

当前对应的诊断训练 / smoke 入口已经补上，但不作为默认主线：

- `testbed/configs/act_agx_v2_1_multi_raw_all_workskill_clean_v4_qvel.yaml`
- `testbed/configs/act_agx_v2_1_multi_raw_all_workskill_clean_v3b_qvel.yaml`
- `testbed/configs/eval_agx_v2_1_stage5_workskill_clean_v4_qvel_alldata_3cycle_smoke.yaml`
- `testbed/configs/eval_agx_v2_1_stage5_workskill_clean_v3b_qvel_alldata_3cycle_smoke.yaml`

其中 `clean_v3b` 与 `clean_v4` 合并数据集当前最长窗口都在 `812` 步量级，所以诊断训练配置默认把 `episode_len` 设为 `900`；这些线同时把 DataLoader 调到 `num_workers = 4`、`prefetch_factor = 2`、`persistent_workers = true`，优先缓解 HDF5 读取导致的 GPU 吞吐不足。live smoke 默认把 `task.episode_len` 设为 `5000`，便于更快观察 `3-cycle` 质量而不是继续沿用 `8000` 步长预算。

正式 `clean_v3` 主线固定做：

- `bootstrap + rule planner + scripted transition`
- 只替换 `WORK` ckpt 为当前 `qvel` 高质量 work 主线
- 用当前多轮主线直接看动作质量是否改善

## Acceptance Criteria

- learned transition 在多 rollout 下不再明显落后于 scripted
- fallback 机制可控，不破坏主线部署
- `pause_ratio`、`boundary_jump` 至少有一项优于 scripted baseline
- 代码库中不再残留旧 ready-anchor 主线

当前 learned transition 想升为默认部署路径，需要同时满足：

- `cycle3_success_rate >= scripted baseline`
- `transition_timeout_rate <= scripted baseline + 0.05`
- `completed_transition_count >= scripted baseline`
- `dump_to_next_dig_gap_steps` 不高于 scripted 的 `1.15x`
- `pause_ratio`、`boundary_jump_l1` 至少一项优于 scripted

在满足这些条件之前，`RuleTaskPlanner + scripted transition` 继续作为默认主线。

## Risks and Stop Conditions

- learned transition 比 scripted 更抖，则保持 scripted fallback 为默认路径
- 自然 transition 数据分布过散，则优先补 teacher 数据再继续训练
- 如果 learned 只表现为“更顺但更慢”，则继续做数据清洗与 fallback 优化，不提前切默认
- learned planner 只有在以下条件满足后才允许进入下一阶段：
  - learned transition 已通过默认部署门槛
  - non-mid sector 的 work policy 质量稳定
  - planner supervision 数据足够丰富，不再只是 `left -> right`
