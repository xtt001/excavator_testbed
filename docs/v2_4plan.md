# YuLong V2.4 Outcome-Grounded Hindsight Goal-Conditioned Learning 计划

## Summary
- 目标是让低层 ACT 真正“听 goal token”，而不是继续复现专业师傅的平均动作习惯。
- 不要求专业师傅按 planner 录制；从自然操作数据中离线反推 actual cut / payload / deposit / return target，作为 hindsight goal 和 outcome supervision。
- V2.4.5 本轮改为重切 `dig/carry/dump/return` 全部 primitive；如果 Gate 1/2 显示
  `carry/dump` 窗口语义干净，则按 `dig -> return -> carry -> dump` 一并训练。
- Planner 短期保持 rule/belief goal proposer，不上 learned planner；等离线 token-swap 证明 `dig/return` 会响应 goal 后，再放大 planner 自由度。
- 全部 planner 设计都遵循同一条边界：planner 只提出任务级 goal/token、维护 coverage
  belief、决定 skill 切换和少量 readiness/safety gate；不手写 joystick/qpos 轨迹，不要求
  skill 命中精确姿态，不用姿态补丁替代低层 ACT 学习。

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
  contact_allowed, qpos_center[4], qpos_half_width[4], qvel_abs_max, valid,
  no_dump_contact_required`。V2.4.5 builder 从下一轮 dig-start 附近 40-step 窗口抽取
  envelope；valid mask 是 per-dim mask，Gate 1 的 episode-level envelope valid 使用
  token 第 16 维，即 qpos/qvel 核心状态可用，而不是要求所有空间维度逐项全有效。
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
- `BoundaryDetectorConfig.boundary_profile=v2_4_5_spatial_mass` 会输出
  `dig_complete / dump_committed_start / release_onset / dump_complete /
  next_dig_entry_ready` 等语义事件。planner 在该 profile 下优先消费事件完成
  `dig -> carry -> dump -> return -> dig`，不再在 planner 内拼 committed aiming
  band 的几何阈值；`return -> dig` 仍保留 pending target 的 entry-close gate，
  因为这是目标协调而不是全局物理边界。
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
    `v2_4_removed_depth_cut_v3`：第 8 维从旧 bucket peak depth 改为本铲
    `max(actual_removed_depth_delta_grid)`，新 depth scale 为 `0.25m`；旧
    checkpoint 全部按不兼容处理。
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
  start envelope。例外是第一铲：因为没有上一轮 return，live eval 允许
  `pre_dig_align.first_dig_only=true` 在 `bootstrap -> dig` 前做一次友好的 entry
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
- depth 目前仍只能通过 `dig_cut_tokens` 间接控制；区别是第 8 维现在监督真实
  removed-depth delta，而不是旧 bucket peak depth。p90 depth/payload 是更强 intent，
  不是闭环深度控制。真正保证“挖到指定深度再离土”仍需要后续把 depth trajectory
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
- 2026-05-22 removed-depth replay QC 显示 `0.15m` scale 会让 depth token 饱和率约 `8%`，
  高于 `<2%` 验收线；`0.22m` 在 gold-only 训练集上仍约 `2.6%`。因此 contract bump
  到 `v2_4_removed_depth_cut_v3`，scale 改为 `0.25m`。gold dig replay 的真实 removed-depth p10/p50/p90 约为
  `0.046/0.085/0.157m`，live planner 使用
  `planner_priors/yulong_removed_depth_dig_cut_prior_v3.json`。
- 1cycle smoke eval 的 `dig_bad_replan_min_bucket_mass_kg` 暂设为 `25kg`：在尚未加入 false-recovery 数据前，优先快速 reject bad dig start，避免低 payload dig 长时间卡住。
