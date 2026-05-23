# V2.4.5 Spatial-Mass Ownership Standard

本文是 YuLong removed-depth 数据重切前的 ownership 评审稿。目标是在不增加 primitive
数量的前提下，用 64D `env_state` 中的空间位置、bucket 质量、dump 沉积和安全信息，
重新定义 `dig/carry/dump/return` 的训练窗口。

## 背景

V2.2/V2.4 当前 primitive split 主要信任 `/v2` relabel 的事件和阶段标签：

- `qualified_dig_start_mask`
- `/v2/cycle/start_step/end_step/dump_end_step`
- `work_stage_id`
- `dump_start_mask/dump_end_mask`
- `approach_dump` 阶段和 bucket curl-out heuristic
- `good_dump_quality` 事后接受

这套规则在干净 label 上可用，但对当前 removed-depth replay 数据暴露出两个问题：

1. 旧 cycle boundary 可能漏掉中间真实的装料/倒料物料事件，把多个 material cycle 压进
   一个 `/v2/cycle`。
2. `pre_approach_stable_curl_out_good_dump` 会把 dump 起点提前到 official dump 前很远，
   让 dump primitive 吞入大量空间移动、等待和预姿态调整。

因此 V2.4.5 的核心改动不是增加 primitive，而是把 ownership 根标准从
“标签/阶段驱动”切换为“几何/质量物理事件驱动”。

## 设计原则

- 仍然只有四个 primitive：`dig -> carry -> dump -> return`。
- `carry` 语义扩展为 loaded transport + dump 前姿态预调整。
- bucket 提前开斗或预调整不自动属于 `dump`。
- `dump` 只负责进入 dump area 后的 committed release/deposit。
- `/v2` 标签只作为候选和诊断参考；最终窗口由 `env_state` 的空间和质量事件验证。
- 所有 planner 只做任务级决策：选择 goal/token、维护 coverage belief、切换 skill、做少量
  readiness/safety gate；不手写 joystick/qpos 轨迹，不把专家姿态 envelope 变成精确动作
  约束。
- 如果一个旧 `/v2/cycle` 内出现多个 material pulse，应拆成多个 material cycle；拆不清楚时
  reject，不能把整段糊进一个 primitive。
- realign 是高敏感弃置信号：只丢弃覆盖 realign step 的 material cycle。窗口采用半开区间，
  realign 正好落在下一轮 start 帧时只归属下一轮。
- 第一版人工审核以 timeline + 关键帧为主；短视频作为二阶段 outlier 复核工具，不作为
  第一版 QC 必需产物。

## Removed-Depth 最新标准

当前 V2.4 replay 刷新后已经有可靠的 64D `env_state` removed-depth 信息，
V2.4.5 不能再把 depth 当成可选辅助信号。新的 dig ownership 和 token/QC 必须按
`v2_4_removed_depth_cut_v3` 标准使用真实 removed-depth：

- `dig_area_removed_depth_m_r{0..2}_c{0..1}` 是本轮挖深事实源。
- `actual_removed_depth_delta_grid = removed_depth[end] - removed_depth[start]`。
- `dig_cut_tokens` 第 8 维使用 `max(actual_removed_depth_delta_grid)`，depth scale 为
  `0.25m`。
- gold dig 样本要求 depth source 为 `env_state_removed_depth_delta`。
- 没有可靠 removed-depth 的样本不能进入 gold tier；只能进入 silver/diagnostic 或 reject。
- dig QC 必须检查 depth token 饱和率、非零比例、p10/p50/p90 spread，以及 raw meter
  delta 的分布。
- `bucket_depth_below_dig_area_plane_m` 只作为 handoff/readiness 参考，不再作为真实
  入土深度真值。qc6 审计显示 relative-y/surface-depth 几何 profile 与 removed-depth
  outcome 是两个不同语义：前者更像姿态/高度 envelope，后者才是本轮地形变化。
  因此后续 dig ACT 使用可选 `dig_depth_profile_tokens_v1` 补充 cell、payload、
  entry/exit/peak reference depth、surface/plane offset 和 contact fraction，
  不把这些诊断量硬编码成 planner 的动作阈值。
- planner 侧必须优先消费 qc6 prior 中的 `dig_depth_profile_cells`。在 depth-profile
  eval 中，缺失当前 coverage cell 的 profile prior 是配置错误，应 fail fast；不能回退
  到 live-current 估算或 global profile，否则会重新引入 dataset token 与 rollout token
  的语义错配。

这意味着 V2.4.5 的 dig 边界不只看 bucket mass/payload，也要验证该窗口内是否产生了
合理的 removed-depth delta。payload 可以作为装料事实，removed-depth 才是“切了哪里、
切了多深”的几何事实。

## 可用信号

V2.4.5 依赖 `agx_env_state_v2_2_64`。当前数据已经包含需要的主要字段：

| 用途 | 字段 |
| --- | --- |
| bucket 质量 | `mass_in_bucket_kg`, `bucket_mass_delta_kg` |
| dump/target 沉积 | `deposited_mass_in_target_box_kg`, `deposited_mass_in_dump_area_kg`, `offtarget_deposited_mass_kg` |
| dig virtual box | `dig_area_geometry_available`, `bucket_dig_area_cell_id`, `bucket_dig_area_long_norm`, `bucket_dig_area_short_norm`, `bucket_tip_dig_area_x_m`, `bucket_tip_dig_area_y_m`, `bucket_tip_dig_area_z_m`, `bucket_depth_below_local_surface_m`, `bucket_contact_dig_area_mask` |
| removed-depth grid | `dig_area_surface_depth_m_*`, `dig_area_removed_depth_m_*`, `dig_area_target_depth_m_*`, `dig_area_cell_valid_mask_*` |
| dump virtual box | `target_geometry_available`, `bucket_dump_area_footprint_outside_distance_m`, `bucket_over_target_footprint_mask`, `bucket_height_above_target_rim_m`, `dump_clearance_ok_mask`, `bucket_contact_dump_area_mask` |
| 安全 | `hard_collision_count`, `target_contact_max_normal_force_n` |
| 参考标签 | `qualified_dig_start_mask`, `dump_start_mask`, `dump_end_mask`, `work_stage_id`, `/v2/cycle/*` |

## Material Cycle

V2.4.5 的基本切分单元是 material cycle，而不是旧 `/v2/cycle`。

一个 material cycle 应包含：

1. 在 dig virtual box 内开始 dig。
2. removed-depth grid 或 bucket 质量出现有效增加；gold 样本必须有可靠 removed-depth delta。
3. 带料离开 dig box 并接近 dump area。
4. 在 dump area 内发生 bucket mass drop，并伴随 dump/target deposit increase。
5. bucket 质量回到本轮 release 后的低位，进入 return。

旧 `/v2/cycle` 可用于限定搜索范围，但不能作为唯一真相。如果旧 cycle 内找到两个以上
`load -> release` 物料脉冲，第一版默认拆分为多个 material cycle，而不是整段保守
reject。拆分后的每个 material cycle 独立检查 realign：只有覆盖
`replay_pose_realign_steps` 的子轮被丢弃，未覆盖 realign 的子轮可以 salvage。如果多个脉冲
的空间/质量证据互相冲突，或 release/deposit pulse 无法和 loaded bucket 对齐，该旧 cycle
才进入 reject summary。

2026-05-22 对当前 removed-depth replay root 的快速审计给出的参考分布：

- 675 个旧 `/v2/cycle` 窗口中检测到 36 个 multi-pulse 旧 cycle。
- multi-pulse 旧 cycle 内共检测到 75 个 deposit pulse，其中 73 个子轮未覆盖 realign，
  只有 2 个子轮应因 realign reject。
- 这说明第一版采用“拆 pulse + 子轮 realign 清理”比整段 reject 更符合当前数据状态。

## Dig Ownership

`dig` 表示在 dig virtual box 内完成入土、切削、装料。

建议边界：

- `dig_start`: 优先使用 material cycle 内的 first stable dig-box contact/depth step；
  若与可靠 `qualified_dig_start` 对齐，则可直接使用 qds。
- `dig_end`: bucket 获得有效 payload/removed-depth 后，历史 bucket mass 已接近本轮峰值，
  后续短窗口内无显著新增 mass，并且 bucket 无 dig contact/有效下挖、稳定离开 dig
  virtual box 的第一段。在这些条件同时成立前，即使视觉上已经在从 return 接入 dig，
  或旧 label 认为已经 handoff，仍归 dig。

必要证据：

- dig-area geometry 可用。
- bucket 在有效 dig cell 或扩展 virtual box 内。
- bucket 有接触/下挖，或 `bucket_depth_below_local_surface_m` 达到阈值。
- removed-depth grid 出现有效增加；bucket mass/payload gain 作为装料辅助事实。
- bucket mass 的增长过程已经结束：不是要求当前帧质量一定等于峰值，而是要求历史峰值
  已经出现，并且未来窗口没有继续装料迹象。
- dig end 附近同时满足物理离开：contact mask 低、depth 接近 0，且 dig-area
  min-distance 或 long/short normalized coordinate 显示已经离开 box。
- dig window 内不应出现 dump/target deposit 增加。

建议 QC：

- 最短/最长长度分布必须稳定，过短和极长都进入审计。
- `actual_removed_depth_delta_grid`、`max_removed_depth_delta_m`、payload gain、
  dig-box fraction、hard collision delta 写入 summary。
- 没有可靠 removed-depth source 的样本降为 silver 或从 gold 中排除。

## Carry Ownership

`carry` 表示带料移动到 dump 区，并允许人类式的预姿态调整。

建议边界：

- `carry_start = dig_end`
- `carry_end = dump_start`

允许：

- 带料离开 dig box。
- swing/boom/stick/bucket 姿态调整。
- 进入 dump area 附近。
- bucket 预开斗或 release-like action，只要没有实际明显倒土。
- 向 dump area 移动过程本身。只要 dump-area footprint outside distance 仍在明显下降
  或位置仍在大幅调整，即使 bucket 姿态已经开始为倒土做准备，也优先归 carry。

禁止：

- 明显 bucket mass loss 同时伴随 dump/target deposit increase。
- target hard collision。
- 长时间空斗但仍被标成 carry。

建议 QC：

- carry 内 deposit delta 不应超过小阈值。初始红线采用
  `deposit_delta > 5kg AND deposit_delta / payload > 10%`；只超过绝对值或只超过比例时先
  进入黄色审计，不直接 reject。
- carry 内 mass loss 不应超过小阈值，初始可审计 `10kg` 或 payload 的 `20%`。
- carry end 不能太早：如果 carry 末端到 dump start 后，dump-area outside distance
  还在大幅变化，说明 dump 占用了运输/对准的一部分，应把 `dump_start` 后移到稳定接近段。
- release-like bucket action fraction 只作为风格指标，不直接判死。
- 输出 `dig_box_fraction`, `dump_box_fraction`, `mass_loss`, `deposit_delta`,
  `bucket_release_like_fraction`, `hard_collision_delta`。

当前数据分布支持这条红线：599 条 carry 中，target deposit delta 的 p50 为 `0kg`，
p95 约 `1.35kg`，p99 约 `3.21kg`，最大约 `10.10kg`；同时超过 `5kg` 和 payload
`10%` 的样本只有 5 条，应作为首批人工审计 outlier。

## Dump Ownership

`dump` 表示已经进入 dump area 的 committed release 和沉积完成。

建议边界：

- 先找 `release_onset`: bucket mass 从局部峰值持续下降，且 dump/target deposit 持续增加。
- `release_onset` 需要发生在 dump virtual box 内或附近，并满足 clearance/height 安全条件。
- `dump_start`: 从 `release_onset` 向前取有限 committed aiming window。默认
  `dump_pre_release_lead_max_steps = 120`，即 `dump_start >= release_onset - 120`。
  早于该上限的长距离 transport/alignment 归入 carry；不能因为最终 good dump 把几百上千
  steps 划入 dump。当前 refined 实现还要求 `dump_start` 进入 committed aiming band：
  bucket footprint 距 dump box 不远或已 over-target，height above rim 不明显异常，
  signed dump-area `relative_x/z` 在宽 corridor 内，并且短窗口内 `relative_x/z`
  变化量已经下降到微调级别。区域内 release 前的 swing/boom/stick/bucket 姿态微调归
  dump；仍在大幅向 dump area 移动的横向/纵向过程归 carry。找不到 committed aiming
  band 时，只 fallback 到 release 前短窗口，不再单靠无符号 outside-distance 提前切入。
- `dump_end`: bucket mass 达到 release 后低位并稳定，deposit plateau，再加有限 post-hold。
  这里的 `dump_end` 是物理意义上的“倒料完成/桶内残余低位稳定”，不是旧 cycle 的
  `work_end`。`work_end` 只作为旧标注给出的搜索上界，避免算法向后吞掉 return。

必要证据：

- dump-area geometry 可用。
- dump box fraction 高。
- `mass_in_bucket_kg` 下降与 `deposited_mass_in_dump_area_kg` 或
  `deposited_mass_in_target_box_kg` 增加同时出现。
- hard collision delta 为 0。

建议 QC：

- dump length max/p95。
- release lead steps，即 `release_onset - dump_start`。
- release lead 超过 120 steps 时，builder 应优先把 `dump_start` 后移到
  `release_onset - 120`；如果后移后仍出现超长 dump，说明不是单纯 lead 问题，而要继续
  检查 multi-pulse 或 dump_end 识别。
- dump window 内 mass drop、deposit delta、dump-box fraction、clearance-ok fraction。
- official `dump_start_mask/dump_end_mask` 与 material release/dump end 的偏移。
- 如果一个旧 dump window 内出现多个 release pulse，必须拆分或 reject。

当前数据分布支持 120 steps 作为第一版上限：当前 dump window 的
`dump_start -> release_onset` 中位数约 70 steps，p90 约 99 steps，p95 约 141
steps；637 条可识别 release 的 dump 中有 35 条超过 120 steps。把 lead cap 到 120
只能修掉“起点过早”，不能修掉旧 cycle 粘连，因此 cap 与 multi-pulse 拆分必须同时做。

2026-05-22 的真实数据重建进一步确认：只修 `dump_start` 不够，必须同时修
`dump_end`。V2.4.5 `physical_dump_qc` run 使用 release 后残余质量低位 + deposit
plateau 作为完成点后，dump length 从旧异常长窗口收敛到 max `315`、p95 `228.7`，
pre-release lead 被严格压到 max `120`，transition contamination 为 `0`。

同日的人工关键帧反馈又暴露出另一类风险：`carry_end` 容易太早、`dump_start` 容易太早。
`process_boundary_qc4` 因此把 `dump_start` 从 lead cap 进一步后移到稳定 dump-area
接近段，并把“仍在大幅向 dump area 移动”的片段归 carry。该版 Gate 1 通过，`dig/carry/dump`
各 `644` 条、`return=589`；dump length max/p95/p50 从 physical QC 的
`315/228.7/171` 收敛到 `293/204.85/154`，release lead mean/p50 从 `63.9/58.5`
降到 `45.0/32`。carry deposit contamination 仍为 `0`，`carry_mass_loss` audit flag
从 `54` 降到 `26`，但新增 `carry_dump_transition_tight=106` 需要在 Gate 2 人工确认。

`process_boundary_qc5` 将 qc4 的“稳定接近段”细化为 committed aiming band：outside
distance 只判断接近，真正决定 dump ownership 的是 signed `relative_x/z` 是否进入宽
corridor，且短窗口内 `relative_x/z` 变化是否降到微调级别；区域内 release 前 swing
和姿态微调归 dump，仍在大幅赶往 dump area 的横向/纵向运动归 carry。该版 Gate 1
同样通过，`dig/carry/dump=644`、`return=589`，没有进入 materialize/train。相对
qc4，395/644 个 carry end / dump start 被后移，后移量 p50/mean/p90/p95 为
`16.5/28.0/78/86` steps；dump pre-release lead 从 `45.0/32/105.7/117.85`
降到 `17.0/12/39.4/64.85`，dump length p50/mean/p95 从 `154/156.4/204.85`
降到 `131/128.4/196`。对应地，carry length p50/mean/p95 从 `106/110.7/169`
增到 `135.5/138.6/218`，说明被 dump 吞掉的大段 transport 已回到 carry。carry
deposit delta 仍全为 `0`，mass-loss p95 保持 `3.361kg`。Gate 2 的 contact sheet
位于 qc5 primitive root 的 `boundary_audit/contact_sheets/` 和
`boundary_audit/contact_sheets_clean_gold/`；`dump_start_outside_footprint` 需要结合
signed `relative_x/z` 曲线、over/clearance mask 和视频人工判断，不能按 outside flag
单项否决。

qc5 人工复核后进一步确认：carry/dump 边界仍偏早，dump 前半段混入了 dump area 外的
大幅移动；问题不是 dump start 太晚。`process_boundary_qc6` 因此把小场景的 outside
阈值收紧到 stable `0.30m`、fallback max `0.35m`，并把 no-candidate fallback 改成
`release_onset_no_aiming_candidate`，避免严格阈值反而回退到早期 lead cap。该版 Gate 1
通过且仍停在 Gate 2：相对 qc5，622/644 个 carry/dump 边界继续后移，后移量
p50/mean/p90/p95 为 `3/6.8/10.7/36` steps；dump pre-release lead 从
`17.0/12/39.4/64.85` 降到 `10.2/9/15/26.85`，dump length p50/mean/p95 从
`131/128.4/196` 降到 `125.5/121.6/191`。`dump_start_source` 分布为 committed band
`539`、release-onset fallback `81`、late pre-release fallback `24`；outside
`>0.30m` 从 `143` 降到 `105`，`>0.35m` 从 `128` 降到 `81`。剩余 high-outside
样本大多是 release 本身也在该几何距离上发生，需要按视频和 mass/deposit 曲线人工确认。

后续 planner/eval 不再把 qc6 的自然语义边界重新拆成 planner 内部阈值。`BoundaryDetector`
新增 `boundary_profile=legacy|v2_4_5_spatial_mass`：legacy 保持旧的
`qualified_dig_start/dump_start/dump_end`，V2.4.5 profile 则在线输出
`dig_start`、`dig_complete`、`dump_committed_start`、`release_onset`、
`dump_complete`、`next_dig_entry_ready`。其中 `dump_committed_start` 表示带料 bucket
进入 dump-area committed aiming band 且空间变化已经是微调级别，不需要等 deposit；
`release_onset` 才是 mass drop 或 dump/target deposit gain；`dump_complete`
在 release 后用 residual bucket mass 与 deposit plateau 判定。planner 只消费这些
事件、skill 顺序、coverage 状态和 pending target entry-close gate，不再知道
committed band 的具体几何阈值。

qc6 训练/eval 的 coverage prior 也同步收敛到 3x2 cell：`yulong_removed_depth_dig_cut_prior_v3.json`
新增 `coverage_cells`，每个 cell 写入 `source_count/source_fraction`、entry/exit、
cut depth、payload 和 effective deposit。`PrimitivePlannerACTPolicy` 的
`coverage.candidate_layout=cell_weighted_3x2` 使用这 6 条候选直接对应
removed-depth grid，旧 prior 缺少 `coverage_cells` 时仍回到 3x3 percentile grid。
cell 4 的 source fraction 低于 `0.05`，默认 `max_attempts=1`，且不会作为 first-dig
候选，除非其它 cell 已耗尽。

## Return Ownership

`return` 表示倒料完成后，空斗从 dump 区回到下一轮 dig 可接管状态。

建议边界：

- `return_start = dump_end`
- `return_end`: 下一轮 material cycle 的 `dig_start`，或可靠 `qualified_dig_start`。

必要证据：

- bucket mass 处于 release 后低位。
- return window 内不应出现新的 payload acquisition 或 dump deposit。
- 不包含 realign step。

建议 QC：

- return length max/p95，当前训练 episode length 上限可继续使用 `512` 做 gate。
- return/dig 数量比例。
- `return_end` 到下一轮 entry/cut token 的几何误差。
- terminal cycle 无下一轮目标时不产出 return，只写 reject/summary。

## Realign Policy

`replay_pose_realign_steps` 是数据质量弃置信号，但不能吞掉相邻 clean cycle。

- 对 material cycle 使用半开窗口 `[cycle_start, next_cycle_start)`。
- realign 落在窗口内，则该 material cycle 的 `dig/carry/dump` 均 reject。
- realign 落在 return window 内，则该 return reject。
- realign 正好落在下一轮 start/qds 帧，只归属下一轮。
- reject summary 必须记录 realign step、窗口范围、source episode/cycle/material-cycle id。

## Token Contract Compatibility

V2.4.5 不要求推翻现有 `dig_cut_tokens`。相反，ownership 变干净后，dig token 更容易
被 ACT 学到。但最近 live 结果说明：把同一个 cut-intent token 直接用于 return 不够。

- `dig_cut_tokens` 仍描述本轮 dig 的 entry/exit/cut/depth/payload/outcome intent；
  其中 depth 必须使用 `v2_4_removed_depth_cut_v3` 的真实 removed-depth delta。
- 旧 10D `return_target_tokens` 只描述下一轮 cut intent：entry/exit/direction/length/depth/payload。
  这对 return 不够，因为 return 的任务不是“怎么切”，而是“把空斗带到下一个 dig
  可以稳定接管的 start envelope”。
- material cycle 重建后，token 应绑定到对应 material cycle，而不是旧 `/v2/cycle`。
- `carry/dump` 可以继续只用 `qpos + qvel` 作为第一版；它们的参数化问题主要来自 handoff
  和 ownership 污染，而不一定需要马上新增 token。
- 后续如需给 `carry/dump` 加 token，应先通过 QC/可视化确认它们的窗口语义稳定。

## Return Start Envelope Token

V2.4.5 应把 return conditioning 从“next cut intent”升级为“next dig-start state
envelope”。推荐新增一个独立 token contract，例如
`return_start_envelope_tokens_v1`。它可以与 `dig_cut_tokens` 同时存在，但语义不同：

- `dig_cut_tokens`: 下一铲要切什么。
- `return_start_envelope_tokens`: return 应把机器带到什么 dig-start 状态。

初始 contract 建议覆盖以下信息：

| 类别 | 信息 |
| --- | --- |
| bucket tip envelope | next dig-start bucket tip 在 DigArea local frame 的 `x/y/z` 或 long/short/depth 坐标，以及容差半径 |
| shallow contact/depth | 允许的浅接触深度范围，避免 return 提前插土或压深 |
| expert qpos envelope | next dig-start 的 swing/boom/stick/bucket qpos 中心与容差，尤其 bucket curl/pitch |
| velocity gate | next dig-start qvel norm 目标接近 0，或各轴速度容差 |
| distribution validity | 该 envelope 是否来自 gold expert distribution、是否在专家 qds pose 分布内 |
| safety hints | 是否要求 dig-area contact、是否禁止 dump-area contact、hard-collision guard |

这里的 envelope 首先是训练输入和 QC 目标，不是 planner 低层姿态控制器。planner 只选择
下一铲 cut intent / start envelope，并决定何时切 skill；return policy 自己学习如何把机器
带到这个 envelope。不要让 planner 通过 qpos 规则逐步规定 boom/stick/bucket 的动作轨迹。
如果 live return 出现提前下铲或卡住 DigArea 壁，第一排查对象应是
`return_start_envelope_tokens_v1` 中由 env_state/下一轮状态派生出的数值条件，或者
planner 在线生成 token 的方式；这不等价于否定物理直觉切出来的连续 return 窗口。
`tb-audit-return-ckpt` 可在 recorded return stream 上离线比较原始 token、depth mask、
spatial mask 和 qpos-only envelope：原始 token 下若贴近专家，优先查 live token/planner；
原始 token 下也偏离专家，再查 checkpoint 和训练分布。
2026-05-23 live 对比确认：旧 planner 在 return 刚开始时用当前 `qpos/env_state`
构造 envelope，和训练时“下一轮 dig-start 窗口”的 token contract 不一致。qc6 修复版把
`return_start_envelope_cells/global` 写入 dig-cut prior，live 按已选 coverage cell 使用
qc6 gold return 的 median envelope；这仍然只是任务级 target token，不是手写动作轨迹。
同一轮诊断也确认：第二次 dig 失败时注入的 `dig_cut_tokens` 数值并不离群，离群的是
handoff 状态和该 token 描述的 entry envelope 不一致。qc6 planner 因此把
`return_start_envelope_tokens_v1` 同时作为 return policy 输入和 `return -> dig`
readiness gate：只有 long/short、local depth/contact 和 qpos 落在对应 cell 的 qc6
p05-p95 envelope 附近时，才允许把 pending `dig_cut_tokens` 交给 dig primitive。
其中 local depth 使用 token 自身的 min/max 字段；qc6 prior depth p05 在部分 return
窗口中接近 0，只适合描述分布尾部，不适合作为 live handoff 下界。
第二铲复现还暴露了一个更底层的字段语义问题：`bucket_depth_below_local_surface`
在被挖过的局部表面附近会变浅，而 qc6 dig-start 的稳定边界是
`bucket_depth_below_dig_area_plane`。因此 qc6 prior 额外记录每个 coverage cell 的
gold dig-start plane-depth 分布，planner readiness 用它确认机器已进入 ACT dig
训练时的可切起点。live qc6 配置使用 `p50_floor` plane-depth mode：交接下界来自
对应 cell 的 dig-start p50，而不是 p05；这样 return 的任务是回到可重复起挖流形，
不是只达到最低可接受接触深度。由于 detector 的 `next_dig_entry_ready` 是边沿事件，
planner 会 latch 住该事件并等待 envelope gate 同步 ready；V2.4.5 下不再让旧
shallow guard 单独触发 `return -> dig`。

另一个闭环保护是 primitive ownership 不能被低载荷状态绕开：`dig_complete` 只说明
一次 dig 轨迹已结束，不代表 carry 有足够 payload 可执行。如果当前 bucket mass 低于
carry/dump 最低可用载荷，planner 会把该 cell 记为低质量尝试并重新规划；如果 carry
阶段已经实际发生 release，则 safety latch 直接转 return，避免 carry 长时间停留在
dump 后姿态。

离线生成方式：

1. 对每个 material cycle，读取下一轮 `dig_start` 附近的专家状态窗口；当前实现使用
   40-step window，而不是只信一个 exact frame。
2. 从该窗口提取 bucket tip DigArea local 坐标、bucket depth/contact、4D qpos、4D qvel。
3. 按 corridor/cell 或 token bucket 聚合专家分布，得到中心、p05/p95 或 robust radius。
4. return 训练时在整个 return window 注入对应 envelope token。
5. live 时 planner 先选择 next cut intent，再从专家分布/当前 DigArea 状态派生 next
   start envelope；return 追 envelope，dig 仍读 cut intent。

当前代码实现的第一版 token contract 固定为 18D，并在 return window 内逐步重复写入：

| index | 含义 |
| --- | --- |
| 0 | next dig-start 的 `bucket_dig_area_long_norm` |
| 1 | next dig-start 的 `bucket_dig_area_short_norm` |
| 2 | next dig-start depth center，优先 `bucket_depth_below_local_surface_m` |
| 3 | bucket tip tolerance radius，第一版固定 `0.20m` |
| 4-5 | shallow depth min/max |
| 6 | contact allowed flag |
| 7-10 | next dig-start 4D qpos center |
| 11-14 | next dig-start qpos robust half-width |
| 15 | next dig-start qvel abs max |
| 16 | expert/envelope core valid flag；当前表示 qpos/qvel 核心状态可用 |
| 17 | no dump contact required flag |

对应 HDF5 字段为：

- `/v2/step/return_start_envelope_tokens_v1`，shape `(T, 18)`，`float32`。
- `/v2/step/return_start_envelope_valid_mask`，shape `(T, 18)`，`uint8`。

dataset/runtime/ACT adapter/eval planner 均已识别该 low-dim key。训练配置使用
`qpos + qvel + return_start_envelope_tokens_v1`；旧 `return_target_tokens` 仍保留为
诊断和 pending dig-cut intent 的来源，但不再作为 V2.4.5 return 训练输入。

`return_start_envelope_valid_mask` 是 per-dim mask，不是 all-or-nothing episode flag。
空间、depth、contact 维度可因局部 geometry 缺失而单独置 0；只要 qpos/qvel 核心状态
可用，token 第 16 维仍可为 1，Gate 1 也以这个核心 valid 判定 return episode 是否有
可训练 envelope。这样做的目的，是避免一个空间传感维度临时缺失就把整条 return 训练窗
丢掉，同时仍让训练/诊断知道哪些 envelope 维度不能监督。

## 已接入的 Builder Profile

`tb-build-primitives-v2_2` 新增 `--boundary-profile v2_4_5_spatial_mass`：

- 从 raw/hindsight episode 直接切 `dig/carry/dump/return`，不走旧 workskill crop。
- `dig_start` 优先找 dig-box contact/depth；找不到时才回退到 material cycle start。
- `dig_end` 使用过程式条件：历史 mass 峰值已经出现、未来窗口无显著增量，并且
  bucket 无 contact/有效 depth、稳定离开 dig area box。
- `release_onset` 使用当前步的 bucket mass drop 或 dump/target deposit increase；不会因为
  “未来若干步会掉料”提前把 long aiming window 划进 dump。
- `dump_start` 先限制在 `release_onset - 120` 以内，再从这个上界向后找 dump-area
  稳定 aiming band；如果 distance-to-dump-area 仍在明显变化，更早的
  curl-out/alignment/approach 仍归 carry。
- `dump_end` 使用 release 后 bucket residual low、bucket mass plateau 和
  target/dump deposit plateau 的物理完成点；旧 `work_end` 只作为搜索上界和诊断字段。
- carry 若出现 `deposit_delta > 5kg AND deposit_delta / payload_loss > 10%`，作为
  `carry_deposit_contamination_before_dump` reject。
- return 只在存在下一轮 material dig-start 时生成；最后一轮写
  `return:terminal_return_reject`。
- realign policy 使用半开窗口：work realign 只 reject 当前 cycle 的
  `dig/carry/dump`，return realign 只 reject 对应 return window，下一轮 start 帧不被前一轮吞掉。

第一版实现仍以旧 `/v2/cycle` 限定 material-cycle 搜索窗口，但会在旧 cycle 内发现多个
`qualified_dig_start_mask` 时拆成多个 material 子窗口。仅靠质量/沉积曲线、但没有可靠
next dig-start 标签的 multi-pulse 仍进入人工审计范围。因此 Gate 1/2 必须重点检查旧
cycle 粘连、multi-pulse 和长 dump outlier，不能因为 profile 已接入就默认数据干净。

live `return -> dig` handoff gate 必须保持轻量：

- 第一版硬 gate 只检查 task-level readiness：entry/tip 误差、空斗或低质量、浅接触/深度
  不危险、速度不要明显过大、无 hard collision。
- qpos / bucket pitch / expert pose envelope 默认作为 QC、debug 和训练目标；只有在确认某类
  极端 out-of-distribution 姿态会稳定导致 dig 失败后，才作为很宽的 safety veto。
- gate 不应要求 policy 命中某个精确姿态，也不应在 return 后插入手写 qpos servo。否则会把
  planner 变成动作级控制器，和未来多模态 planner 的接口方向相冲突。

当前失败应归因于两件事叠加：

- ownership 污染让 return/carry/dump 边界本身不干净。
- return token 只描述 next cut intent，没有显式描述 next dig-start state。

因此修复不能只靠重切数据，也不能只靠加 token。推荐顺序是：先用 V2.4.5 ownership
重建干净 return window，再训练带 `return_start_envelope_tokens` 的 return；最后在 live
handoff gate 中用轻量 readiness 检查防止明显错误接管，同时把 qpos/depth/qvel envelope
误差作为 QC 和训练诊断。

## QC 输出

V2.4.5 builder 或 audit 工具至少应输出：

- 每个旧 `/v2/cycle` 的 material pulse count。
- 每个 material cycle 的 primitive 边界和 reject reason。
- 每个 material cycle 是否覆盖 realign；multi-pulse 旧 cycle 要列出 salvage/reject 子轮数。
- 每类 primitive 的数量、长度分布、tier 分布。
- dig: removed-depth/payload/dig-box fraction。
- carry: mass loss、deposit delta、deposit/payload ratio、release-like action fraction、
  dig/dump box fraction，并标出 `>5kg AND >10% payload` 的红线 outlier。
- dump: release onset、lead steps、mass drop、deposit delta、dump-box fraction、clearance
  fraction，并标出 `release_onset - dump_start > 120` 的 outlier。
- return: length、empty-bucket fraction、next-dig entry error、next-start qpos/qvel
  envelope error、shallow depth/contact error。
- realign overlap summary。

QC gate 不应只给 pass/fail，还应给出 top outliers 和可视化索引，方便人工复核。
`tb-audit-primitive-boundaries` 的 Gate 2 输出现在还会自动生成两类关键帧报告：
`boundary_audit/contact_sheets/index.html` 覆盖 selected risk/balanced 样本，
`boundary_audit/contact_sheets_clean_gold/index.html` 覆盖 clean gold 对照样本。每张
sheet 把边界前后关键帧、bucket mass/deposit、signed dump-area `relative_x/z`、
outside distance、`bucket_over_target_footprint_mask`、`dump_clearance_ok_mask`、height
above rim 和 target horizontal distance 放在同一页，避免把无符号 outside-distance
误当成 carry/dump 边界的唯一语义。审阅时还要看 `relative_x/z` 在边界后短窗口内是否
仍在大幅变化；如果仍在明显横向/纵向赶路，则应归 carry，而不是 dump。

2026-05-22 `runs/jobs/yulong_v2_4_5_physical_dump_qc_20260522` 的 Gate 1 数字 QC：

- `dig/carry/dump` 各 644 条，`return` 589 条；return/dig ratio `0.915`。
- dig gold 样本 595 条，depth source 全部为 `env_state_removed_depth_delta`，depth token
  无饱和，gold token p10/p50/p90 为 `0.105/0.189/0.374`。
- carry deposit contamination 为 `0`；target deposit delta p95 为 `0`，max `5.03kg`。
- dump length max `315`、p95 `228.7`；release lead max `120`；transition
  contamination 为 `0`。
- return length max `437`、p95 `302.6`；overlong return reject ratio `0.0469`；
  return envelope episode valid fraction `1.0`。

Gate 2 已按设计暂停：boundary audit 生成 5042 条边界记录和 24 个 selected videos，
主要风险标记为 `carry_mass_loss=54`、`low_dig_payload=2`、`low_effective_deposit=4`、
`non_gold=382`、`short_window=12`。因此当前结论是“数字 QC 符合继续人工审阅的预期”，
还不是“可以直接训练”。

## 可视化审阅

推荐先做 episode/cycle timeline，而不是只看表格。

单条 timeline 应至少包含：

- 彩色 primitive 窗口：`dig/carry/dump/return/reject`。
- `mass_in_bucket_kg` 曲线。
- `deposited_mass_in_dump_area_kg` 与 `deposited_mass_in_target_box_kg` 曲线。
- dig-box / dump-box mask 或 fraction。
- bucket action/qpos，尤其 bucket release-like 区间。
- `qualified_dig_start`, old `dump_start/dump_end`, new `release_onset/dump_end` marker。
- realign marker。
- hard collision / clearance flag。

每个 outlier 由 `tb-audit-primitive-boundaries` 自动生成关键帧 contact sheet，优先取：

- `dig_start`, `dig_end/carry_start`, `dump_start`, `release_onset`, `dump_end/return_start`,
  `return_end/next_dig_start`。
- 对 multi-pulse 旧 cycle，每个 detected pulse 至少取 `pulse_start` 和 `release_onset`。
- 对 realign reject，额外取 realign step 前后各一帧。
- carry/dump 边界审阅时，先看 signed dump-area `relative_x/z` corridor、
  `bucket_over_target_footprint_mask`、`dump_clearance_ok_mask`、height above rim、
  mass drop、deposit gain，再结合关键帧/视频直觉；`outside-distance` 只说明离 footprint
  多近，不能表达 bucket 在 dump area 的前/中/后位置。

批量 dashboard 应至少包含：

- primitive count 和 reject count。
- length histogram/p95/max。
- material pulse count histogram。
- old marker 与 new physical event 的偏移分布。
- carry contamination scatter: `mass_loss` vs `deposit_delta`。
- dump purity scatter: `dump_box_fraction` vs `deposit_delta/mass_drop`。
- token distribution 与 outcome distribution，确认 token 没有塌缩。
- return start-envelope token distribution，以及 live/validation 中 return end state 到 expert
  envelope 的误差分布。

人工审核第一版优先看 timeline + 关键帧：

1. 多 material pulse 旧 cycle 的拆分是否符合视频/曲线直觉。
2. carry 是否保留了自然的预姿态调整，但没有实际倒土。
3. dump 是否只包含进入 dump area 后的 committed release。
4. return 是否从空斗开始，并接到下一轮 dig start。
5. realign 是否只丢弃受影响 cycle，没有扩大污染。
6. return end 是否落在专家 dig-start pose/envelope 内，而不仅仅是 bucket tip 位置接近。
