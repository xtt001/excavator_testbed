# YuLong V2.4 Outcome-Grounded Hindsight Goal-Conditioned Learning 计划

## Summary
- 目标是让低层 ACT 真正“听 goal token”，而不是继续复现专业师傅的平均动作习惯。
- 当前工程状态：四 primitive 闭环已经能跑通 10-cycle smooth milestone；最新主线重点已从
  “能连续跑完”转到“planner 点位是否合理、ACT 是否严格跟随 token、coverage/depleted
  是否反映真实 remaining depth”的诊断和收口。
- 不要求专业师傅按 planner 录制；从自然操作数据中离线反推 actual cut / payload / deposit / return target，作为 hindsight goal 和 outcome supervision。
- V2.4.5 本轮改为重切 `dig/carry/dump/return` 全部 primitive；如果 Gate 1/2 显示
  `carry/dump` 窗口语义干净，则按 `dig -> return -> carry -> dump` 一并训练。
- Planner 短期保持 rule/belief goal proposer，不上 learned planner；等离线 token-swap 证明 `dig/return` 会响应 goal 后，再放大 planner 自由度。
- 全部 planner 设计都遵循同一条边界：planner 只提出任务级 goal/token、维护 coverage
  belief、决定 skill 切换和少量 readiness/safety gate；不手写 joystick/qpos 轨迹，不用
  姿态补丁替代低层 ACT 学习。最终验收仍要求 ACT 对 planner token 呈现足够精准的
  entry/exit/depth 跟随，而不是在参考位置附近自行找地方干活。

## V2.4.5 闭环执行状态

- `tb-build-primitives-v2_2 --boundary-profile v2_4_5_spatial_mass` 已接入
  spatial/mass ownership profile：在 raw/hindsight episode 上按 material cycle 直接切
  四个 primitive。`dig_end` 现在要求已达到历史 bucket-mass 峰值附近、后续无显著新增
  mass、无 dig contact/有效深度，并稳定离开 dig area box；在此之前即使已经过了旧
  return/dig handoff，也仍归 dig。`dump_start` 先受 `release_onset - 120` lead cap
  约束，再后移到 dump-area 稳定接近/瞄准段；如果 dump-area outside distance 仍在大幅
  变化，该过程归 carry。`dump_end` 使用 release 后 bucket 质量低位 + deposit plateau
  的物理完成点，旧 `work_end` 只作为搜索上界和诊断参考。terminal return 只写 reject，
  不进入训练窗。
- return 数据新增 `/v2/step/return_start_envelope_tokens_v1` 和
  `/v2/step/return_start_envelope_valid_mask`。当前 token 为 18D：
  `long_norm, short_norm, depth_center, tip_radius, depth_min, depth_max,
  contact_flag, qpos_center[4], qpos_half_width[4], qvel_abs_max, qpos_valid,
  spatial_depth_valid`。V2.4.5 builder 从下一轮 dig-start 附近 40-step 窗口抽取
  envelope；valid mask 是 per-dim mask，Gate 1 的 episode-level envelope valid 使用
  token 第 16 维 `qpos_valid`，即 qpos/qvel 核心状态可用，而不是要求所有空间维度逐项全有效。
  dim/order/path 的代码 source-of-truth 是 `testbed.contracts.primitive_tokens`。
- `EpisodicDataset`、train/eval runtime、ACT adapter 和 `primitive_planner_act` 已识别
  `return_start_envelope_tokens_v1`。live/eval 中 return planner 仍维护 pending
  `dig_cut_tokens`，同时给 return policy 注入 envelope token；planner 不因此写动作轨迹。
- 新增四个训练配置：
  - `act_yulong_v2_4_5_spatial_mass_dig_qvel.yaml`
  - `act_yulong_v2_4_5_spatial_mass_return_envelope_qvel.yaml`
  - `act_yulong_v2_4_5_spatial_mass_carry_qvel.yaml`
  - `act_yulong_v2_4_5_spatial_mass_dump_qvel.yaml`
- `tb-build-v2_4-hindsight-pipeline` 已支持反馈 gate：
  - Gate 1 写 `04_pre_materialize_qc.json`，失败直接停止，不 materialize。
    Gate 1 primitive-VDS numeric QC 的实现 source-of-truth 是
    `testbed.pipeline.v2_4_qc_gates`；CLI 只保留参数解析、stage 编排和 thin facade。
  - Gate 2 自动跑 `tb-audit-primitive-boundaries`，写
    `04b_boundary_audit_gate_summary.json`。当 boundary profile 是
    `v2_4_5_spatial_mass` 且未传 `--ack-feedback-gates` 时，默认停在 Gate 2 等人工审阅。
  - Gate 3 每个训练 stage 完成后写 `<stage>_gate_summary.json`；V2.4.5 下 `--train`
    默认训练顺序为 `dig -> return -> carry -> dump`。

2026-05-22 的 data-only 闭环 run
`runs/jobs/yulong_v2_4_5_physical_dump_qc_20260522` 已从最新 removed-depth replay
root 重建到 Gate 2：使用 `--v2-label-source-dir data/yulong_v2_2_current_relabeled`
转移原始 `/v2` 标注，没有重新跑 Unity replay，也没有进入 materialize/train。

- relabel/operator/hindsight：26 条 replay episode；operator-first 649 cycles
  (`gold=600`, `silver=49`)；hindsight 675 cycles，其中 649 个 cycle 使用
  `env_state_removed_depth_delta`，26 个 terminal/legacy-zero cycle 不进入 gold depth。
- Gate 1 数字 QC 已通过，`04_pre_materialize_qc.json` 没有 failed checks：
  `dig/carry/dump` 各 644 条，`return` 589 条；dig gold depth source fraction `1.0`，
  gold depth token p10/p50/p90 为 `0.105/0.189/0.374`，饱和率 `0.0`。
- dump 切分符合这轮设计意图的主要数字信号：length max `315`、p95 `228.7`，
  pre-release lead max `120`、p50 `58.5`，transition contamination `0`。这比旧切法的
  超长 dump 明显收敛，说明“物理 dump end + 有限 aiming window”修到了关键问题。
- carry 数字 QC 干净：deposit contaminated episode `0`，deposit delta p95 `0`，
  max `5.03kg` 且 deposit/payload ratio 为 `0`。
- return 数字 QC 可用但仍要看视频：return/dig ratio `0.915`，max length `437`，
  p95 `302.6`，overlong reject ratio `0.0469`；return envelope episode valid fraction
  `1.0`。
- Gate 2 已按闭环规则暂停等待人工可视化审阅：
  `04b_boundary_audit_gate_summary.json` 为 `decision=pause`，原因是
  `manual_visual_review_required`。boundary audit 输出 5042 条边界记录和 24 个视频，
  主要风险标记为 `carry_mass_loss=54`、`low_dig_payload=2`、
  `low_effective_deposit=4`、`non_gold=382`、`short_window=12`。训练前下一步必须先看
  `boundary_audit/videos` 的 selected videos，确认这些 outlier 是合理风格/低质样本，
  还是仍有边界污染。

根据 2026-05-22 人工关键帧反馈，`process_boundary_qc4` 已把边界从单点 detector
阈值改成“过程式 ownership”判断：dig end 同时看 mass 是否停止增长和是否离开 dig
area；carry/dump 边界要求 dump-area distance 已经进入稳定接近段，仍在明显移动去
dump area 的片段保留给 carry。该 run 仍只到 Gate 2，没有 materialize/train：

- job: `runs/jobs/yulong_v2_4_5_process_boundary_qc4_20260522`
- primitive VDS:
  `/fastdata/pingfan/excavator_testbed_data_hot/yulong_v2_4_removed_depth_hindsight_goal_primitives_vds_v2_4_5_process_boundary_qc4_20260522`
- Gate 1 通过：`dig/carry/dump=644`，`return=589`；carry 数量恢复到上一版
  physical QC 水平。
- dump 窗口更贴近 committed release：length max `293`、p95 `204.85`、p50 `154`，
  比 physical QC 的 max `315`、p95 `228.7`、p50 `171` 继续收敛；pre-release lead
  mean/p50 从 `63.9/58.5` 降到 `45.0/32`，max 仍受 `120` cap 约束。
- carry 泄漏风险下降：`carry_mass_loss` audit flag 从 `54` 降到 `26`，
  `short_window` 从 `12` 降到 `4`，carry deposit contamination 仍为 `0`。
- 新的主要待审项是 `carry_dump_transition_tight=106`：这是 dump_start 后移到稳定
  dump-area 接近段后的自然副作用，表示 carry/dump 边界变紧，需要人工确认没有把
  真正 release 前的必要动作切得过晚。
- `tb-audit-primitive-boundaries` 现在会随 Gate 2 自动生成关键帧 contact sheet：
  - risk selected:
    `/fastdata/pingfan/excavator_testbed_data_hot/yulong_v2_4_removed_depth_hindsight_goal_primitives_vds_v2_4_5_process_boundary_qc4_20260522/boundary_audit/contact_sheets/index.html`
  - clean gold contrast:
    `/fastdata/pingfan/excavator_testbed_data_hot/yulong_v2_4_removed_depth_hindsight_goal_primitives_vds_v2_4_5_process_boundary_qc4_20260522/boundary_audit/contact_sheets_clean_gold/index.html`
  每张 sheet 同时显示边界前后关键帧、bucket mass/deposit、signed dump-area
  `relative_x/z`、outside distance、`bucket_over_target_footprint_mask`、
  `dump_clearance_ok_mask`、height above rim 和 target horizontal distance；黄色十字/竖线是
  offset 0。`*_end_*` 的 offset 0 是 `source_end_step_exclusive`，即 primitive
  结束后的第一帧。

2026-05-22 后续修正把 carry/dump 边界从“outside-distance 稳定”进一步改成
“committed aiming band”：

- `bucket_dump_area_footprint_outside_distance_m` 仍只是接近度，不足以表达 bucket 在
  dump area 的前/中/后位置。
- `dump_start` 仍受 `release_onset - 120` 上界约束，但必须同时满足 dump-area 接近、
  height above rim 不明显异常、signed `relative_x/z` 在宽 corridor 内，并且短窗口内
  `relative_x/z` 变化量已经下降到 aiming 微调级别。
- 区域内 release 前的 swing/姿态微调属于 dump；仍在大幅赶往 dump area 的横向/纵向
  运动属于 carry。找不到 committed aiming band 时只 fallback 到 release 前短窗口，
  不再让无符号 outside-distance 把半段 carry 吞进 dump。
- `process_boundary_qc5` 已按这套规则从 qc4 operator relabel root 重切到 Gate 2，
  仍没有 materialize/train：
  - job: `runs/jobs/yulong_v2_4_5_process_boundary_qc5_20260522`
  - primitive VDS:
    `/fastdata/pingfan/excavator_testbed_data_hot/yulong_v2_4_removed_depth_hindsight_goal_primitives_vds_v2_4_5_process_boundary_qc5_20260522`
  - Gate 1 通过：`dig/carry/dump=644`，`return=589`，carry deposit contamination
    仍为 `0`。
  - 相比 qc4，395/644 个 carry end / dump start 被后移；后移量 p50/mean/p90/p95
    为 `16.5/28.0/78/86` steps，60 条后移超过 `80` steps，249 条保持不变。
  - dump pre-release lead 从 qc4 的 mean/p50/p90/p95 `45.0/32/105.7/117.85`
    降到 `17.0/12/39.4/64.85`；dump length p50/mean/p95 从
    `154/156.4/204.85` 降到 `131/128.4/196`。
  - carry length p50/mean/p95 从 `106/110.7/169` 增到 `135.5/138.6/218`，
    表明之前被 dump 吞掉的大段 transport 已回到 carry。carry mass loss 风险没有放大：
    mean/p95 从 `0.643/3.361kg` 到 `0.617/3.361kg`，deposit delta 仍全为 `0`。
  - Gate 2 正常暂停等待人工审阅。contact sheet:
    `/fastdata/pingfan/excavator_testbed_data_hot/yulong_v2_4_removed_depth_hindsight_goal_primitives_vds_v2_4_5_process_boundary_qc5_20260522/boundary_audit/contact_sheets/index.html`
    和
    `/fastdata/pingfan/excavator_testbed_data_hot/yulong_v2_4_removed_depth_hindsight_goal_primitives_vds_v2_4_5_process_boundary_qc5_20260522/boundary_audit/contact_sheets_clean_gold/index.html`。
    当前 audit flag 里 `dump_start_outside_footprint=384` 多数是 signed `relative_x/z`
    已稳定但 over-target/clearance mask 仍未翻转的 pre-release 微调，需要用视频和
    geometry 曲线一起人工判断；旧的 `carry_dump_transition_tight=106` 不能单独作为失败信号。

2026-05-22 人工复核 qc5 后确认：carry/dump 主问题仍是 `dump_start` 太早，dump 前半段
混入 dump area 外的大幅移动，而不是 dump start 太晚。`process_boundary_qc6` 因此把
小场景下的 outside 阈值继续收紧，并把 no-candidate fallback 改为贴近 `release_onset`
而不是回退到 `release_onset - 120`：

- 阈值：stable outside `0.30m`、fallback max outside `0.35m`、outside range
  `0.08m`、total approach `0.12m`、`relative_x/z` 短窗口变化 `0.20/0.12m`；
  signed corridor 收到 `x=[-0.40, 2.10]`、`z=[0.30, 2.30]`，height above rim
  下限 `0.45m`，fallback pre-release window `15` steps。
- job: `runs/jobs/yulong_v2_4_5_process_boundary_qc6_20260522`
- primitive VDS:
  `/fastdata/pingfan/excavator_testbed_data_hot/yulong_v2_4_removed_depth_hindsight_goal_primitives_vds_v2_4_5_process_boundary_qc6_20260522`
- Gate 1 通过：`dig/carry/dump=644`，`return=589`，carry deposit contamination
  仍为 `0`。
- 相比 qc5，622/644 个 carry end / dump start 继续后移；后移量 p50/mean/p90/p95
  为 `3/6.8/10.7/36` steps，29 条后移超过 `40` steps。
- dump pre-release lead 从 qc5 的 `17.0/12/39.4/64.85` 降到
  `10.2/9/15/26.85`，dump length p50/mean/p95 从 `131/128.4/196` 降到
  `125.5/121.6/191`。这更符合“dump 只承担 committed release/deposit 和区域内微调”
  的 ownership。
- `dump_start_source` 分布为 committed aiming band `539`、release-onset fallback
  `81`、late pre-release fallback `24`；outside `>0.30m` 从 qc5 的 `143` 降到
  `105`，`>0.35m` 从 `128` 降到 `81`。剩余高 outside 基本是 release 本身的几何量也高，
  需要人工看视频和 mass/drop，而不是用 outside 单项回退到早边界。
- surface-depth 重放后的 carry/dump 复核显示 live planner 的旧 committed detector
  仍会比离线 `dump_start` 早触发：`0.45m + hold3` 在这套 dig/dump 最短距离不到
  `1m` 的场景中过宽。因此 V2.4.5 后续 split/eval 同步收紧 committed band：
  stable outside `0.25m`、fallback outside `0.30m`、relative corridor
  `x=[-0.2,1.9]`、`z=[0.45,2.1]`，并要求 outside/relative 窗口变化量进入
  `0.06/0.16/0.10m` 微调级别。live `BoundaryDetector` 也增加 causal rolling
  stability，避免 planner 使用旧 raw dump-ready 阈值提前切换。`release_onset`
  单独保留 `0.45m` 近邻门，防止 dump 接管后 release 动作轻微越出 tightened band
  导致 completion 事件丢失。
- Gate 2 contact sheet:
  `/fastdata/pingfan/excavator_testbed_data_hot/yulong_v2_4_removed_depth_hindsight_goal_primitives_vds_v2_4_5_process_boundary_qc6_20260522/boundary_audit/contact_sheets/index.html`
  和
  `/fastdata/pingfan/excavator_testbed_data_hot/yulong_v2_4_removed_depth_hindsight_goal_primitives_vds_v2_4_5_process_boundary_qc6_20260522/boundary_audit/contact_sheets_clean_gold/index.html`。

2026-05-22 后续主线接受 qc6 作为 copy/train/eval 的唯一数据源，不再从 qc5 或
scale022 派生训练 copy：

- primitive VDS root:
  `/fastdata/pingfan/excavator_testbed_data_hot/yulong_v2_4_removed_depth_hindsight_goal_primitives_vds_v2_4_5_process_boundary_qc6_20260522`
- materialized copy root:
  `/fastdata/pingfan/excavator_testbed_data_hot/yulong_v2_4_removed_depth_hindsight_goal_primitives_copy_v2_4_5_process_boundary_qc6_20260522`
- checkpoint root:
  `runs/ckpts/yulong_v2_4_5_process_boundary_qc6_20260522/{dig,return,carry,dump}`
- qc6 训练只用 `training_tier=gold`：`dig/carry/dump=595`，`return=545`。
  全量 primitive 仍保留 silver 诊断样本：`dig/carry/dump=644`，`return=589`。
- 人工复核记录的 3x2 dominant removed-depth 分布为
  `0:64, 1:163, 2:142, 3:180, 4:18, 5:82`，cell 4 明显稀缺。实际 qc6 gold
  prior 使用训练样本中可见 cell 统计写入
  `testbed/configs/planner_priors/yulong_removed_depth_dig_cut_prior_v3.json` 的
  `coverage_cells`，其中 cell 4 `source_fraction < 0.05`，默认只尝试一次且不作为
  first-dig 候选，除非其它 cell 已耗尽。
- `PrimitivePlannerACTPolicy` 新增
  `coverage.candidate_layout: cell_weighted_3x2`。当 prior 提供 `coverage_cells`
  时 planner 只生成 6 条 corridor，直接对应 3x2 removed-depth cell；旧 prior
  没有 `coverage_cells` 时仍按 3x3 percentile grid 生成 9 条候选，保证旧 eval
  和测试兼容。
- 2026-05-23 return live token 修复：qc6 prior 追加
  `return_start_envelope_cells` 与 `return_start_envelope_global`，均来自 qc6 gold
  return primitive 的 `return_start_envelope_tokens_v1` 分布。live return 不再用
  return 刚开始那一帧的当前 `qpos/env_state` 拼目标 envelope；planner 默认取
  global median envelope，再缺失才使用旧 live-current fallback。coverage cell
  只属于下一次 dig 的 pending `dig_cut_tokens` 和 entry gate，不再默认参与
  return-start envelope 条件化；旧实验如需复现 cell prior，必须显式打开
  `dig_cut_planner.return_start_envelope.use_cell_prior: true`。rollout JSONL 同步写出实际注入的
  `return_start_envelope_tokens` 和 source，便于检查 live token 是否仍在训练分布内。
- 2026-05-23 第二轮 dig 卡住诊断：第二轮 live `dig_cut_tokens` 本身落在 qc6 cell 1
  gold 分布中位附近，问题是 handoff 当前状态尚未进入该 cell 的 dig-start
  envelope。qc6 eval 因此打开 `return_to_dig_start_envelope_gate_enabled`：
  `return -> dig` 既要满足 pending target entry-close，也要满足
  `return_start_envelope_tokens_v1` 对应的 long/short、local depth/contact 和 qpos
  分布 gate。这个 gate 是 skill 边界语义检查，不是 planner 手写 qpos 轨迹。
  depth gate 使用 token 内的显式 min/max，而不是 prior p05/p95；qc6 的少量 return
  envelope depth p05 接近 0，会把尚未进入可切深度的状态误放给 dig。
  进一步 rollout 对照显示，第二铲 0 mass 的关键差异是 plane depth：live handoff
  约 `0.30m`，而 qc6 cell1 gold dig-start 的 p05/p50 约 `0.57/0.59m`。因此 prior
  记录 `dig_start_plane_depth_m`，readiness gate 使用该物理语义而不是只看
  local-surface depth。2026-05-23 follow-up 将 qc6 eval 的 plane-depth gate 从
  p05-p95 range 改为 `p50_floor`：下界锚定 cell-wise p50，p95 只作为过深保护，
  避免 return 刚达到分布尾部就把控制权交给 dig。`next_dig_entry_ready` 作为
  one-shot detector event 会被 return 阶段 latch，直到 envelope gate 也 ready；
  legacy shallow guard 不再参与 V2.4.5 语义交接。
- 2026-05-23 carry 卡住诊断：第二轮 dig 虽进入 plane-depth envelope，但
  `dig_complete` 时当前 bucket mass 只有约 `12kg`，低于 carry/dump 最低可用载荷，
  planner 却允许切到 carry，导致 carry policy 在 underloaded 状态下自己完成 release，
  而 planner 没有及时进入 dump/return。修复后 V2.4.5 planner 会拒绝这种
  low-current-payload `dig_complete` 并重新规划；carry 中若已经检测到 release 完成，
  则通过 release safety 转 return，避免继续卡在 carry。
- 2026-05-23 dig 深度语义收口：修复 Unity DigArea 几何后，主线不再把
  `dig_depth_profile_tokens_v1` 当最终接口。12D profile 只保留作 ablation/探针，
  用来验证几何信息是否有用。正式训练继续使用 10D `dig_cut_tokens`：
  第 8 维保留原接口位置，但内部语义从 removed-depth delta 改为
  `cut_depth_semantic_m`，优先来自修复后的
  `bucket_depth_below_local_surface_m` peak；`actual_removed_depth_delta_grid`
  继续作为 outcome/audit 字段，而不是默认 command-depth source。
- 2026-05-23 planner depth 修复不再用“平地就加深”的阈值规则。新增
  `yulong_removed_depth_dig_cut_state_exemplars_qc6.json`，从 qc6 gold dig 中保留
  每条样本的 6-cell removed-depth start grid、expert raw cut fields 和
  `dig_depth_profile_tokens_v1`。depth-profile eval 配置开启
  `coverage.state_conditioned_exemplars` 后，planner 会在当前 coverage cell 内用
  当前 6-cell removed-depth grid 做 KNN，选择/加权相似专家样本生成
  `dig_cut_tokens` 和 12D profile token；cell prior median 只在该 exemplar 层未开启
  或无可用样本时作为兼容路径。bad-dig / exit-guard / pre-dig-align replan 会同时
  invalidate return 阶段预置的 pending dig token，避免失败后继续复用旧浅挖计划。
  失败 replan 也不再默认把新 token 直接交给 `dig`：depth-profile eval 开启
  `pre_dig_align.replan_after_failed_dig=true`，即使 `first_dig_only=true`，只要 dig
  内部被 bad-dig/exit-guard 拒绝，planner 会先回到 entry-align skill，让 dig 只从
  可接管的 entry/envelope 开始工作。
- 2026-05-25 first-dig handoff 决议：V2.4.5 qc6 主线关闭手写
  `pre_dig_align`。第一铲没有上一轮 return 产生的 next-entry 约束，不应被 planner
  强制移动到某个预选 cell；planner 只负责选择近场/coverage token，dig ACT 从当前可行
  姿态开始挖。`pre_dig_align` 保留为诊断开关；如果手动启用 entry-intent 屏蔽模式，
  它也不能用 timeout 消耗 coverage corridor 或触发 dig-area depleted。
- 2026-05-25 return relocation 训练决议：不 replay、不重切 primitive，只在 loader/runtime
  增加派生 low-dim key `return_relocate_tokens_v1`。该 token 来自
  `return_target_tokens`，但 mask depth/payload，只保留下一铲 entry/exit/direction/length
  给 return 学习 relocation；若 step token 全 0 而 metadata 有 `next_operator_*`，
  loader 从 metadata 修复这个派生 view。本轮只重训 return，输入为
  `qpos + qvel + return_start_envelope_tokens_v1 + return_relocate_tokens_v1`，
  dig/carry/dump 继续使用上一轮 surface-depth checkpoint。
- 2026-05-25/26 live rollout 探索确认：`return_start_envelope_tokens_v1` 若只用
  qc6 global median，会把 return 拉回平均 dig-start 姿态，视觉上表现为多轮回到同一
  区域附近再挖。`return_relocate_tokens_v1` 的作用不是把 return 变成脚本对齐器，而是把
  下一铲 entry/exit/direction/length 作为 target-specific conditioning 暴露给 return；
  对应 live envelope 可以开启 `spatial_from_relocate` / `qpos_from_relocate`，用
  relocate token 派生 spatial long/short 与 qpos center。这个路径实现了 10-cycle
  smooth rollout：`runs/jobs/yulong_v2_4_5_return_relocate_train_eval_20260525/eval/10cycle_return_relocate`
  完成 10 次 dump，`rollout_stop_reason=target_cycle_gate_terminal_hold_reached`，
  无 spill/hard target collision，mean/min deposited fraction 为 `0.877/0.654`。但该
  rollout 是 milestone，不是“严格指哪挖哪”的最终证明：它使用旧的 1-step gate tail，
  且当时还没有 per-cycle intent/execution/prior 精度表。
- 2026-05-26 之后的诊断方向收敛为“失败就暴露根因”。dig 低载荷、exit guard、
  entry/envelope 不 ready 或 depleted 判断异常时，诊断/eval 配置应 fail fast 或记录
  terminal reason，不再用 pre-dig align、宽 handoff、return 内 replan 等补救逻辑把问题
  糊过去。当前报告会输出每铲 planner intent、actual bucket-tip/peak depth 和 expert
  prior p05/p50/p95/radial p95；这些误差相对的是 planner 本轮 token，不是相对 expert
  p50。expert prior 只用来说明“planner 点位本身是否在训练分布支持内”和“ACT 偏差是否
  超出该 cell 的专家容忍范围”。
- 2026-05-26 depleted/长 rollout 语义修正：`coverage.depleted` 是 planner 的
  pass-local 尝试状态，不等于物理土量已经清零。若 `coverage.use_env_removed_depth=true`
  且 env removed-depth/target-depth grid 显示某 cell 的 remaining depth 仍高于阈值，
  attempt limit 不应单独把该 cell 终止；`coverage.multi_pass_enabled` 会在所有候选都
  被 pass-local depleted 后检查 remaining depth，记录 `reopen_coverage_pass` 并重开仍有
  余量的 cell。只有没有可重开余量或 pass 用尽时才报告 `dig_area_depleted`。
- 当前 N-cycle qc6 eval 配置已把 `target_cycle_gate_terminal_hold_steps` 提到 `100`，
  让达到目标 cycle 后继续保留 100 step 尾段，避免最后一次 dump/coverage/summary 在停止
  当帧被截断。15/30-cycle 现在主要是 depletion/remaining-depth probe；若 10-cycle 就因
  `dig_area_depleted` 提前结束，优先分析阈值、remaining-depth grid 和 coverage pass
  语义，而不是直接拉长 rollout 预算。
- operator-first 的 cut-depth 窗口必须在进入 carry/approach/dump 前停止；当 cycle
  window 刚好延伸到 episode 末尾时也要扫描 work-stage，否则 depth peak 会把后续
  carry/dump 姿态误计入 dig token。
- `BoundaryDetectorConfig.boundary_profile=v2_4_5_spatial_mass` 会输出
  `dig_complete / dump_committed_start / release_onset / dump_complete /
  next_dig_entry_ready` 等语义事件。planner 在该 profile 下优先消费事件完成
  `dig -> carry -> dump -> return -> dig`，不再在 planner 内拼 committed aiming
  band 的几何阈值；detector 内部用小场景尺度的 rolling stable aiming band 判断
  `dump_committed_start`，而不是旧的 `0.45m` 单帧接近门；`return -> dig` 仍保留 pending target 的 entry-close gate，
  因为这是目标协调而不是全局物理边界。live ACT 还保留一个 material liveness escape：
  如果 detector 尚未发出 `dig_complete`，但 bucket 已经达到目标载荷或稳定质量 plateau，
  planner 可用 `semantic_material_loaded/plateau` 切到 carry，打破“必须先离开 dig box
  才能切 carry、但离开动作又由 carry skill 负责”的循环等待。
- 本轮配置：
  - `act_yulong_v2_4_5_process_boundary_qc6_dig_qvel.yaml`
  - `act_yulong_v2_4_5_process_boundary_qc6_return_envelope_qvel.yaml`
  - `act_yulong_v2_4_5_process_boundary_qc6_carry_qvel.yaml`
  - `act_yulong_v2_4_5_process_boundary_qc6_dump_qvel.yaml`
  - `eval_yulong_v2_4_5_qc6_cell_weighted_3cycle_smoke.yaml`
  - `eval_yulong_v2_4_5_qc6_cell_weighted_15cycle_probe.yaml`
  - `eval_yulong_v2_4_5_qc6_cell_weighted_30cycle_probe.yaml`
- 本地全量推进脚本：

```bash
chmod +x runs/jobs/yulong_v2_4_5_process_boundary_qc6_20260522/run_qc6_materialize_train_eval.sh
TRAIN_AFTER_QC=1 RUN_EVAL_AFTER_TRAIN=0 \
  runs/jobs/yulong_v2_4_5_process_boundary_qc6_20260522/run_qc6_materialize_train_eval.sh
```

脚本顺序固定为 materialize -> pre-train QC -> `dig -> return -> carry -> dump`
训练 -> dig token sensitivity。`RUN_EVAL_AFTER_TRAIN=1` 会继续跑 3/15/30-cycle
live eval，需要 Unity/AGX endpoint 已就绪。

推荐闭环命令第一步只跑到可视化 gate：

```bash
python -m testbed.cli.build_v2_4_hindsight_pipeline \
  --raw-dir /fastdata/pingfan/excavator_testbed_data_hot/yulong_v2_4_removed_depth_replay_realign_all_20260521_164859 \
  --v2-label-source-dir data/yulong_v2_2_current_relabeled \
  --boundary-profile v2_4_5_spatial_mass \
  --tag v2_4_5_spatial_mass_gate12 \
  --update-current-symlinks \
  --detach
```

人工确认 Gate 1/2 没有偏离后，再显式承认继续：

```bash
python -m testbed.cli.build_v2_4_hindsight_pipeline \
  --raw-dir /fastdata/pingfan/excavator_testbed_data_hot/yulong_v2_4_removed_depth_replay_realign_all_20260521_164859 \
  --v2-label-source-dir data/yulong_v2_2_current_relabeled \
  --boundary-profile v2_4_5_spatial_mass \
  --tag v2_4_5_spatial_mass_train \
  --update-current-symlinks \
  --ack-feedback-gates \
  --train \
  --detach
```

## Key Changes
- 新增 V2.4 hindsight relabel builder：
  - 输入当前 operator-first relabel/copy 数据，输出 image-VDS 中间 relabel root：`data/yulong_v2_4_hindsight_goal_relabel_vds`。
  - Add-only 写入 `/v2/step/dig_outcome_targets`、`/v2/step/return_outcome_targets`、对应 valid mask，以及 `/v2/cycle/actual_removed_depth_delta_grid`、dominant removed-depth cell、payload/deposit/handoff outcome fields。
  - 10D token 维度保持不变，但 contract bump 到
    `v2_4_removed_depth_cut_v3`：第 8 维仍是 depth slot，内部值改为
    `cut_depth_semantic_m`，优先使用修复后 surface-relative penetration peak，
    depth scale 为 `0.80m`；旧 checkpoint 全部按不兼容处理。
  - 如果旧 raw 没有可靠 `removed_depth`，depth outcome 写
    `depth_outcome_source=unavailable_or_legacy_zero`，并把该 cycle 的 goal valid
    置 0，不能进入 gold training tier；新录/新 replay 数据有修复后 depth 时才启用
    depth-delta supervision。

- 重建 primitive copy 数据：
  - 先输出 primitive image-VDS：`data/yulong_v2_4_hindsight_goal_primitives_vds`。
  - 再从 primitive VDS 并行 materialize 训练 copy：`data/yulong_v2_4_hindsight_goal_primitives_copy`。
  - `dig` episode 保留 `dig_cut_tokens + dig_outcome_targets + dig_goal_valid_mask`。
  - `return` episode 当前兼容保留旧 `return_target_tokens` 用于回溯诊断，但 V2.4.5
    训练入口必须新增并优先读取 `return_start_envelope_tokens_v1 +
    return_start_envelope_valid_mask`。2026-05-22 live 结果表明，旧 10D
    `return_target_tokens` 只表达 next cut intent，对 return 不足；新的 envelope token
    必须显式描述 bucket tip/depth/contact、4D qpos、qvel 与专家 qds pose 分布。
  - V2.4.5 下 `carry/dump` 不再只做一致 QC；若 Gate 1/2 通过，会用
    `qpos + qvel` 第一版配置进入本轮训练。所有新训练输入必须 `is_virtual=False`。
  - materialize 使用 episode/window 级并行，默认 `16` workers、`image_batch_size=16`；因为 primitive window 远小于完整 raw episode，内存风险低于 full relabel copy。
  - 只用 `training_tier=gold` 训练 dig/return；terminal return 无 next target 的样本排除。

- 训练改造：
  - `EpisodicDataset` 支持可选 `supervision_keys`，训练时返回 dict，旧 4-tuple loader 保持兼容。
  - ACT 增加可选 action-conditioned outcome head：从 predicted action chunk 预测 10D outcome target。
  - Loss 组成：
    - 原 ACT action BC + KL；
    - `outcome_loss = SmoothL1(predicted_outcome, hindsight_outcome_target)`；
    - `token_swap_outcome_loss`：同一 obs/image 换另一个 goal token，不算 action BC，只要求 predicted action chunk 经 outcome head 后对应 swapped goal。
  - 这样 outcome loss 会通过 predicted action 反传，迫使 action 随 token 改变，而不是只让单独 head 背答案。

- 新训练配置：
  - `act_yulong_v2_4_hindsight_goal_dig_qvel.yaml`
    - dataset: `data/yulong_v2_4_hindsight_goal_primitives_copy/dig`
    - low dim: `qpos + qvel + dig_cut_tokens`
    - supervision: `dig_outcome_targets`
    - train batch: `24`；trainer 的 best-checkpoint snapshot 已移到 CPU，先保留和既有 YuLong conditioned runs 一致的 batch 口径
    - epochs: 500
    - ckpt: `runs/ckpts/yulong_v2_4_hindsight_goal_20260520/dig/policy_best.ckpt`
  - `act_yulong_v2_4_hindsight_goal_return_qvel.yaml`
    - dataset: `data/yulong_v2_4_hindsight_goal_primitives_copy/return`
    - current low dim: `qpos + qvel + return_target_tokens`
    - V2.4.5 low dim: `qpos + qvel + return_start_envelope_tokens_v1`
    - return relocation ablation low dim:
      `qpos + qvel + return_start_envelope_tokens_v1 + return_relocate_tokens_v1`
    - supervision: `return_outcome_targets` + return endpoint/start-envelope error metrics
    - train batch: `24`；若实际再次 OOM，再降到 `16`
    - epochs: 500
    - ckpt: `runs/ckpts/yulong_v2_4_hindsight_goal_20260520/return/policy_best.ckpt`

- Planner / eval：
  - 新 eval config 使用 current rule/belief planner，只替换 dig/return checkpoint。
  - Planner 继续只提出训练分布内 goal：entry/exit/length/depth/payload clamp 到 prior P10-P90。
  - `dig` 注入 `dig_cut_tokens`；当前 `return` 注入 `return_target_tokens`，但该 token
    只表示 next cut intent。V2.4.5 应改为给 return 注入
    `return_start_envelope_tokens_v1`；`carry/dump` 不注入 goal token。
  - 输出 1/3/5cycle smoke，再跑 10/15cycle milestone；30cycle 仍只作为 depletion probe。

## Test Plan
- Builder tests：
  - hindsight relabel 写入 10D outcome target、valid mask、cycle outcome fields，且不覆盖旧 operator-first 字段。
  - materialized primitive root 关键 dataset 全部 `is_virtual=False`。
  - terminal return 不进入 conditioned return 训练。
  - depth grid delta 仅在 `removed_depth` 非零且可信时启用，否则标注 unavailable。

- Training tests：
  - dataloader 旧 tuple 模式和新 dict supervision 模式都可用。
  - ACT outcome head disabled 时旧 checkpoint/eval 不受影响。
  - outcome head enabled 时 forward loss 包含 `l1/kl/outcome/token_swap/loss`。
  - 500 epoch dig/return 均生成 `policy_best.ckpt` 和 metadata，记录 dataset、low_dim_keys、supervision_keys、git commit。

- Diagnostics：
  - `dig_token_sensitivity` 升级为同时输出 action delta 与 predicted outcome delta。
  - 同一 obs 下换 left/middle/right token，要求 predicted outcome 明显变化，action 的 swing/boom/stick/bucket 至少有可测变化。
  - 若 token-swap 仍几乎不改变 action，不进入 live rollout，先调高 token-swap/outcome loss 或重新检查 token/data 分布。
  - dig rollout 偏浅时，先跑 `tb-audit-dig-ckpt`：
    `python -m testbed.cli.audit_dig_ckpt --config runs/jobs/yulong_v2_4_5_surface_depth_replay_train_eval_20260523/train_configs/act_dig_surface_depth_qvel.yaml --ckpt runs/ckpts/v2_4_5_surface_depth_tight_dump_qc6labels_scale080_20260524/dig/policy_best.ckpt --episode-ids 198,229,304 --chunk-start-steps 0 --max-steps 160 --output runs/jobs/yulong_v2_4_5_surface_depth_replay_train_eval_20260523/dig_ckpt_offline_audit.json`。
    它在 recorded dig stream 上比较 first-action，并从 primitive 起点导出完整 ACT
    chunk 对齐专家后续动作。离线也浅时查 ckpt/训练分布/chunk 机制；离线正常但 live
    浅时查 deployment observation/action scaling、camera、temporal aggregation 或
    planner handoff 后的真实起点。
  - V2.4.5 visual-policy eval 关闭 `eval.send_planner_debug_to_backend`。planner
    debug 仍写入 JSONL，但 coverage marker/debug geometry 不再发送给 Unity 渲染到
    ACT 的 FPV observation；打开该开关的 rollout 只用于人工可视化，不用于判断 ACT
    dig policy。
  - return 出现提前下铲、卡 DigArea 壁或疑似混合动作时，先跑
    `tb-audit-return-ckpt`：
    `python -m testbed.cli.audit_return_ckpt --config testbed/configs/act_yulong_v2_4_5_process_boundary_qc6_return_envelope_qvel.yaml --ckpt runs/ckpts/yulong_v2_4_5_process_boundary_qc6_20260522/return/policy_best.ckpt --output runs/jobs/yulong_v2_4_5_process_boundary_qc6_20260522/return_ckpt_offline_audit.json`。
    它在 recorded return stream 上比较原始 envelope token、depth mask、spatial mask
    和 qpos-only envelope。若原始 token 下预测贴近专家，优先查 planner/live token
    数值；若原始 token 下也偏离，才回头查 ckpt 或训练分布。这个诊断不否定
    V2.4.5 的物理直觉边界，只把问题定位到 ckpt、token 数值或在线 planner。

- Live acceptance：
  - 1cycle：能正常 dig/carry/dump/return，无明显 handoff regression。
  - 3/5cycle：相比当前安全 planner，不应更差；重点看 dig point 跟随、return-to-next-entry gap、payload/deposit。
  - 10/15cycle：保持 milestone 能力，检查是否减少重复挖空区。
  - 30cycle：停止原因应来自 low productivity/depleted/artifact suspicion，而不是靠穿模继续算成功。

## Assumptions
- V2.4.5 本轮会重切 `carry/dump`；若 Gate 1 数字 QC 和 Gate 2 人工可视化审阅都显示
  窗口语义稳定，则本轮直接训练 `carry/dump`。如果任一 primitive 偏离预期，只暂停该
  primitive 分支，把原因写入 gate summary 和复盘，不阻塞已经通过的分支。
- 本轮不引入 learned planner；planner 仍是 rule/belief goal proposer + safety/coverage manager。
  所有 planner/handoff 都只做轻量 readiness gate，不做动作级姿态控制：位置接近、质量状态、
  浅接触/深度不危险、速度不过大、无 hard collision 可以作为硬条件；qpos / bucket pitch /
  expert pose envelope 默认是训练 token、QC 指标和 debug 信号，只有极端
  out-of-distribution 姿态被证明确认会稳定导致失败时，才考虑很宽的 safety veto。
- 当前 26 条 pro 数据可以先训练 entry/exit/payload/deposit hindsight goal；修复后的 depth grid 主要服务未来新录数据或 replay-derived root。
- 不恢复通用 pre-dig align；return 仍应通过 conditioned return 学会回到 next dig
  start envelope。第一铲主线也不再使用 scripted bootstrap 做动作级姿态控制：
  Unity reset pose 负责给出可挖的起始姿态，planner 从 reset 后直接进入 `dig`，
  并由 `dig_cut_tokens` / depth token 指定第一铲目标。旧
  `bootstrap_end_mode=scripted_qpos` 只保留作 legacy smoke 或诊断配置，不应作为
  return-relocate 主线 eval 的默认第一铲路径。若需要做第一铲 A/B，可用
  `pre_dig_align.first_dig_only=true` 做一次友好的 entry
  handoff，并用 `coverage.first_dig_strategy=nearest_entry` 按当前 bucket-tip 到
  entry 的距离选择更容易接上的 corridor；`coverage.first_dig_max_entry_distance_m`
  是第一铲 reachability gate，只要存在阈值内的专家 corridor，就排除距离更远的
  第一铲候选。若 replan 后新 entry 已经 close，planner 直接 handoff 给 dig，
  不再继续用 qpos proxy 追点。2026-05-22 进一步修正第一铲候选选择：通过
  `coverage.first_dig_max_qpos_delta` / `coverage.first_dig_qpos_delta_weight`
  让 nearest-entry 同时考虑该 corridor 的 pre-dig qpos target 离当前 qpos 的距离，
  排除或降权需要大幅抬/收大小臂的 handoff。第一铲 handoff 也支持：若实际
  bucket-tip 已进入 `max_entry_error_m`，且受控轴速度低于
  `first_dig_entry_close_handoff_qvel_abs_max`，则允许交给 dig，不再等待静态 qpos
  target 完全 close，避免 align 越过 entry；专家 dig-start qpos envelope 用作
  第一铲 handoff 的诊断和宽安全边界，不应变成精确姿态目标。scale025 eval 配置把
  first-dig align 的 qpos clamp 收紧到
  dig primitive 起点 qpos 近似 p05/p95，并取消固定 `bucket_target_qpos=0.0`，
  避免把大小臂/铲斗带到不属于正常 dig-start 的姿态。后续铲次不插入手写 align。
  `dig_to_carry_min_distance_to_dig_area_m` 在本轮 live eval 中显式设为 `0.0`：
  第一铲达到 target payload 后应立即允许切 carry，不能要求 bucket 先离开 DigArea，
  否则会在已经装满后继续挖、漏料，甚至卡在 dig。
  若 scripted handoff 仍把第 0 铲带入不自然姿态，可用旧 dig checkpoint 做
  learned first-handoff 诊断：设置 `bootstrap_ckpt_path`、`bootstrap_low_dim_keys:
  [qpos, qvel, dig_cut_tokens]`、`bootstrap_end_mode: first_qualified_dig_start`，
  并关闭 `pre_dig_align`，让 bootstrap 在 qualified dig start 后直接交给新的 V2.4
  conditioned dig。另一个 A/B 是保留 handoff 但替换第 0 铲实际 dig：设置
  `first_dig_ckpt_path` 后，planner 只在 cycle 0 且尚未完成 dump 前使用该 policy，
  后续自动回到主线 V2.4 dig。
  2026-05-29 检查确认最新 return-relocate eval 的 scripted bootstrap target 已等于
  surface-depth gold dig-start qpos p50
  `[0.5057, 0.7376, 0.1194, 0.1740]`。因此第一铲观感 A/B 先不改 target 语义，
  而是新增 `eval_1cycle_bootstrap_p50_fast_handoff.yaml`：保持 p50 target，只放宽
  qpos/qvel hold 并提高 scripted bootstrap clip，以验证较早交给 dig 是否改善第一铲
  表现。
- return handoff 不是单纯等 `qualified_dig_start`：live eval 配置
  `return_to_dig_max_entry_error_m`，确保 bucket 回到 planned next-entry 附近才切回
  dig；entry 已经 close 时允许 bypass 很窄的 shallow max-depth 上限，避免 return
  到位后继续把 bucket 插进土里。
- 最近一次 return-conditioned live 失败说明：same cut token 对 return 信息量不够。
  return 需要的不是下一铲“怎么切”，而是下一铲“从什么 start state 接管”：bucket tip
  envelope、浅接触/深度范围、bucket curl/pitch、boom/stick/bucket qpos、qvel 近零、
  是否在专家 dig-start pose distribution 内，以及是否避免提前插土。这应成为
  V2.4.5 return start-envelope token 的核心。
- 5cycle live probe 暴露的第 4 铲卡住模式不是 return entry gate，而是 coverage
  planner 在一次低产后继续选同一 entry-z row 的相邻 corridor，加上 bad-dig replan
  只看 transient best mass。当前修正为：`recent_row_selection_penalty` 降低刚挖过
  row 的相邻候选分数；bad-dig replan 用当前 bucket mass 判断，若最后已经空斗则 reject
  当前 corridor 并重选。
- 2026-05-21 后续观察：yellow exit marker 是 ACT 的 goal token 和可视化标记，
  不是手写轨迹终止点。planner 不应规定专家动作怎么走，但应在专家 prior 内选择更适配
  当前状态的 goal；V2.4 hindsight eval 因此把 coverage cut 的 depth/payload percentile
  暴露成配置，并默认请求 p90 depth/payload。同时增加 `dig_exit_guard_*`，当 bucket tip
  已明显越过 planned exit 而 payload 仍过低时 reject/replan，避免用继续推到 DigArea
  边界来弥补装土不足。
- depth 目前仍通过 `dig_cut_tokens` 间接控制；区别是第 8 维现在监督修复后
  surface-relative 的 `cut_depth_semantic_m`，而不是旧 bucket peak depth 或
  removed-depth outcome。真正保证“挖到指定深度再离土”仍需要后续把 depth trajectory
  supervision 或 depth guard 纳入训练/状态机。

## Storage Notes
- 本轮训练输入 `data/yulong_v2_4_hindsight_goal_primitives_copy/{dig,return}` 必须保持 materialized copy，不用 VDS 直接训练。
- 中间 relabel/build 第一段使用 image-VDS：大图像不复制，只把新增 hindsight `/v2` 字段和小型 metadata 写到 wrapper 里。
- 标注流水线按两段式并行推进：先并行切 primitive VDS，再从 primitive VDS 并行
  materialize 含 image 的训练 copy，提高 CPU 利用率并避免 relabel/build/image copy
  串行等待。
- 统一入口为 `tb-build-v2_4-hindsight-pipeline`：可从 `--raw-dir`、
  `--relabeled-dir` 或 `--operator-dir` 接入，按顺序写 label/operator-first/hindsight
  VDS、primitive VDS，再调用 `tb-materialize-vds --recursive --workers N`。每个阶段
  都写 `runs/jobs/<job>/logs/*.log`，长任务可用 `--detach` 后 `tail -f` 观察。
- 如果 `--raw-dir` 是为了刷新 removed-depth/env_state 的 replay root，不应重新用
  `progress` detector 推断 cycle boundary；必须加
  `--v2-label-source-dir <已QC的v2_2 relabeled root>`，让 replay 只提供状态/图像，
  `/v2` 的 `qualified_dig_start`、`dump_end` 和 cycle ownership 沿用原始专业操作
  标签。否则漏检下一次 dig-start 会把多个周期粘成超长 return，导致大量本来可用的
  return 被 `overlong_transition_len` 丢弃。
- V2.4 return 训练的 `episode_len=512`，pipeline 默认把
  `--return-max-transition-len` 设为 `512`；超过该长度的 dump-end 到下一次
  qualified-dig-start gap 视为长等待/恢复片段，只进 reject summary，不进入 return
  primitive 训练。
- pipeline 必须先跑 primitive-VDS 级 pre-materialize QC，再写 image copy 和训练。
  `04_pre_materialize_qc.json` 至少检查 gold depth token 饱和率 `<2%`、depth
  token p90-p10 分离、可靠 depth source 占比、return max length、return/dig
  保留比例、overlong return reject 比例、dump max/p95 length，以及 dump 内是否混入
  transition mode/phase；QC 不通过时直接 fail，不进入 materialize/train。
  该 Gate 1 检查的阈值、HDF5 读取和 feedback payload 生成集中在
  `testbed.pipeline.v2_4_qc_gates`，本次职责迁移不改变 JSON 字段、failed-check 文案
  或 pipeline stage 行为。
- V2.4.5 ownership 改为以 64D `env_state` 的空间位置和质量变化定义边界，详见
  `docs/v2_4_5_spatial_mass_ownership.md`。旧 `/v2` cycle/phase 只作为候选和诊断，
  不能再作为唯一 ownership 真相；一个旧 cycle 内出现多个 material pulse 时需要拆分
  或 reject。该标准同时要求 replay 后的 `dig_area_removed_depth_m_*` 作为 gold dig
  token/outcome 的事实源。2026-05-22 后的 refined 版本进一步要求边界看变化过程：
  dig 结束必须同时满足“质量不再增长”和“稳定离开 dig area”；dump 开始必须已经处于
  dump-area 稳定接近/瞄准段，仍在大幅向 dump area 移动的窗口归 carry。
- V2.4.5 第一版默认拆分旧 cycle 内的多个 material pulse；拆分后的子 material cycle
  独立检查 realign，只丢弃覆盖 `replay_pose_realign_steps` 的子轮。`dump_start`
  最多提前到 `release_onset - 120`，更早的预姿态调整归入 carry；carry 掉料红线为
  `deposit_delta > 5kg AND deposit_delta / payload > 10%`。`dump_end` 不能再等同于旧
  `work_end`；V2.4.5 使用 release 后残余 bucket 质量低位、质量 plateau 和 deposit
  plateau 来判定物理倒料完成，`work_end` 只是防止搜索越界的上界。
- 人工 QC 先产出 timeline + 自动关键帧 contact sheet：曲线看 mass/deposit/box/release
  marker 是否解释得通，关键帧看
  `dig_start/dig_end/dump_start/release_onset/dump_end/return_end` 是否符合直觉；
  V2.4.5 contact sheet 由 `tb-audit-primitive-boundaries` 默认生成，carry/dump
  边界必须同时看 signed `relative_x/z` corridor 和短窗口变化量、
  `bucket_over_target_footprint_mask`、`dump_clearance_ok_mask`、height above rim、
  mass drop、deposit gain 和视频直觉。`bucket_dump_area_footprint_outside_distance_m`
  只是无符号接近度，不能单独决定 carry/dump 归属；短视频留作二阶段 outlier 复核。
- replay 为修复旧随机 pose 跳变启用 realign 时，metadata 中的
  `replay_pose_realign_steps` 是高敏感弃置信号；primitive builder 会丢弃覆盖该
  step 的完整逻辑 cycle：判废窗口从本轮 dig start 到 return 完成/下一次
  qualified dig start 之前的半开窗口；realign 正好落在下一轮 qualified dig
  start 帧时只归属下一轮。写 `dig/carry/dump` 训练片段时仍只裁到
  `dump_end_step`，防止 `dump` 吞入 return。覆盖该 step 的 return transition
  window 也会单独 reject，但不包含下一轮 qualified dig start 帧，保护没有
  realign 的好 cycle 不被暴力对齐片段污染。
- 正式重建时 pipeline 必须用 `--detach` 后台跑，避免 Cursor 和数据保存/materialize
  同时占用内存。
- 训练完成并确认 `policy_best.ckpt` 后，materialized primitive copy 可以删除；保留 primitive VDS 作为可重建训练 copy 的轻量来源。
- 历史 relabel/workskill/primitive 根目录如果只作归档或 lineage source，可以替换为 image-VDS：低维字段本地保留，`/observations/images/*` 回指 canonical raw/source episode。
- 历史 primitive 压缩时优先使用完整 replay/raw source，而不是中间 single-cycle VDS wrapper；旧数据里部分 `source_episode_id` 是 legacy 局部编号，不能盲目用于删除源数据。
- raw 录制根目录、当前正在构建的 V2.4 materialized copy、以及 checkpoint 目录不属于 image-VDS 压缩对象。
- V2.4 hindsight dig/return 训练启用 `keep_only_best_ckpt: true`：训练中仍允许 periodic/latest checkpoint 用于进度恢复，但训练成功写出 `policy_best.ckpt` 后会自动删除非 best 中间产物，避免再次占满系统盘。
- V2.4 hindsight dig/return 的 outcome head 训练包含原 batch forward 和 token-swap forward；当前先使用 `batch_size=24`、`prefetch_factor=4`，和既有 YuLong conditioned dig/return 训练保持一致。如果在 CPU best-checkpoint snapshot 修正后仍然 OOM，再把 batch 降到 `16`。
- ACT trainer 会把 validation best checkpoint snapshot 克隆到 CPU 保存，避免在 GPU 上额外常驻一份模型权重；这不改变训练结果，只降低 outcome/token-swap 训练的 OOM 风险。
- 2026-05-23 DigArea 几何修复后，第 8 维 depth slot 改为
  surface-relative `cut_depth_semantic_m`；2026-05-24 根据 realign replay 的
  gold surface-depth 分布把 scale 调整为 `0.80m`，避免 `0.25m` 下 58%+
  gold token 饱和。旧 removed-depth 分布仍作为 outcome/audit 参考；新 replay 后
  需要重新核对 `env_state_surface_penetration` 的 p10/p50/p90 和 token 饱和率。
- 同一轮 return reject 审计显示：overlong return 在前 200-400 step 已到达下一轮
  dig entry/contact/depth，但 delayed material start 把后续 dig/payload 变化吞进
  return。primitive builder 因此把 V2.4.5 return 终点改成
  `first_next_dig_entry_ready`，realign reject 只检查 `dump_end -> handoff`。
- 1cycle smoke eval 的 `dig_bad_replan_min_bucket_mass_kg` 暂设为 `25kg`：在尚未加入 false-recovery 数据前，优先快速 reject bad dig start，避免低 payload dig 长时间卡住。
