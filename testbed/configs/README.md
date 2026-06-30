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
- `tb-materialize-vds --input <vds-dir> --output <copy-dir>` 可把已有 VDS wrapper
  解析成实体 HDF5，保留 metadata/lineage，并把图像写成完整 frame chunk。它适合在
  SSD 空间充裕时给训练做 I/O 对照：牺牲空间，换取更少的 VDS 追源和更好的随机单帧读取。
- `tb-virtualize-images --input <copy-dir> --output <archive-dir>` 可做反向归档：
  低维数组、动作、标签和 metadata 留在输出 HDF5 中，`/observations/images/*`
  改成指向 canonical source episode 的 VDS。它适合历史数据瘦身，不建议作为训练热入口；
  需要重新训练时再用 `tb-materialize-vds` 落到 SSD copy root。早期 full-episode
  relabeled 数据如果没有 provenance，可显式加
  `--fallback-source-dir <raw-dir>` 按 episode id 追到 raw。
- 两个 builder 都会写 `lineage.json`，默认拒绝覆盖已有 episode；只有显式
  `--overwrite` 才会替换 builder output。需要在 `data/` 下保留当前候选入口时，
  使用 `--current-symlink <path>` 更新 symlink；如果该路径是真实目录，builder 会拒绝替换。
- conditioned dig 已接入两条语义：legacy `cell_entry_tokens` 与 operator-first
  `dig_cut_tokens` 都是固定 10D low-dim key。当前 YuLong pro 主线使用
  `act_yulong_v2_2_operator_first_4p_dig_cut_qvel.yaml` 训练
  `qpos + qvel + dig_cut_tokens` 的 dig；`carry/dump/return` 继续保持
  `qpos + qvel`。live 时 `primitive_planner_act` 只在调用 `dig` policy 时注入
  `dig_cut_tokens`，不会把 dig token 喂给 carry/dump/return。
- 2026-05-22 起，YuLong V2.4 token contract 版本为
  `v2_4_removed_depth_cut_v3`。10D 维度不变，但第 8 维改为本铲
  `cut_depth_semantic_m`，优先来自修复后的 `bucket_depth_below_local_surface_m`
  peak，depth scale 为 `0.80m`；旧 checkpoint 视为不兼容。没有可靠
  `env_state_surface_penetration` 的 cycle 不进入 gold tier。
- 全部 planner 配置遵循同一条边界：planner 只提出任务级 goal/token、维护 coverage
  belief、决定 skill 切换和少量 readiness/safety gate；不手写 joystick/qpos 轨迹，
  不要求 ACT 命中精确姿态，不用姿态补丁替代低层 skill 学习。未来多模态 planner 也应只
  产出同类 high-level intent，而不是直接指挥挖机摇杆。
- V2.4 removed-depth 数据链统一用 `tb-build-v2_4-hindsight-pipeline`：
  前段生成 label/operator-first/hindsight/primitive VDS，随后先跑
  `04_pre_materialize_qc.json` 对 token/source、return 长度、dump 长度和 dump
  transition 污染做训练前 QC，通过后再用 `tb-materialize-vds --recursive
  --workers <N>` 并行落含 image 的 primitive copy。
  每个阶段写入 `runs/jobs/<job>/logs/*.log`，适合全量重建时用 `tail -f` 看进度。
  对 replay 刷新出来的 removed-depth raw root，使用
  `--v2-label-source-dir data/yulong_v2_2_current_relabeled` 转移原始 QC 过的
  `/v2` cycle boundary；不要重新 detector relabel，否则容易漏掉下一次
  `qualified_dig_start`，把多个 cycle 粘成超长 return 并丢掉大部分 return 训练窗。
  raw-direct primitive split 写 `dig/carry/dump` 时只裁到 `dump_end_step`，避免
  `dump` 吞入 return；但 realign 判废按完整逻辑 cycle 执行，即从本轮 dig start
  到 return 完成/下一次 qualified dig start 之前的半开窗口，任一 step 覆盖
  `replay_pose_realign_steps` 都会丢弃该轮 work primitive；如果 realign 正好落在
  下一轮 qualified dig start 帧，只归属下一轮。
- V2.4.5 四 primitive 重切使用同一个 pipeline，但必须显式传
  `--boundary-profile v2_4_5_spatial_mass`。该 profile 以 material cycle 的空间/质量事件
  为 ownership 真相：`dig` 看 dig-box contact/depth、removed-depth/payload gain；
  refined 版 `dig_end` 还要求历史 bucket-mass 峰值已出现、后续无显著新增 mass、
  无 dig contact/有效深度，并稳定离开 dig area box；`carry` 允许带料运输、向
  dump area 移动和 dump 前预姿态调整，但明显实际倒土会 reject；`dump` 从 committed
  release/deposit 附近开始，`dump_start` 最多提前到 `release_onset - 120`，并会继续
  后移到 dump-area 稳定 aiming band。如果 dump-area outside distance 仍在大幅变化，
  该过程仍归 carry。surface-depth 主线把 committed band 收紧为 stable outside
  `0.25m`、fallback outside `0.30m`，并要求 outside/relative-x/relative-z 在窗口内
  只剩 `0.06/0.16/0.10m` 级别微调；live `BoundaryDetector` 使用同一语义的 causal
  rolling stability，不再用旧 `0.45m` 单帧宽门切换。`release_onset` 单独保留
  `0.45m` release-area 近邻门，只在 dump 接管后用于识别真实掉料。`dump_end` 用 release 后 bucket 残余低位 + mass/deposit plateau
  的物理完成点，旧 `work_end` 只是搜索上界。
  `return` 从物理 dump end 接到下一轮 dig-start envelope，terminal return 只写 reject。
  V2.4.5 下 pipeline 默认停在 Gate 2 boundary audit，除非传 `--ack-feedback-gates`
  表示已人工审阅。
- V2.4.5 新增训练配置：
  - `act_yulong_v2_4_5_spatial_mass_dig_qvel.yaml`:
    `qpos + qvel + dig_cut_tokens`，带 `dig_outcome_targets` 和 token-swap/outcome head。
  - `act_yulong_v2_4_5_spatial_mass_return_envelope_qvel.yaml`:
    `qpos + qvel + return_start_envelope_tokens_v1`，带 `return_outcome_targets`。
  - `act_yulong_v2_4_5_spatial_mass_carry_qvel.yaml`:
    第一版 `qpos + qvel`，只在 carry QC/人工审阅通过后训练。
  - `act_yulong_v2_4_5_spatial_mass_dump_qvel.yaml`:
    第一版 `qpos + qvel`，只在 dump QC/人工审阅通过后训练。
  - `act_yulong_v2_4_5_process_boundary_qc6_*_qvel.yaml`:
    qc6 accepted split 的正式训练入口，路径指向 `/fastdata/..._copy_v2_4_5_process_boundary_qc6_20260522`，
    ckpt 写入 `runs/ckpts/yulong_v2_4_5_process_boundary_qc6_20260522`。
  `return_start_envelope_tokens_v1` 为 18D low-dim key，对应
  `/v2/step/return_start_envelope_tokens_v1` 与
  `/v2/step/return_start_envelope_valid_mask`；builder 从下一轮 dig-start 附近 40-step
  窗口抽取 envelope。valid mask 是 per-dim mask，token 第 16 维表示 qpos/qvel 核心
  状态可用，Gate 1 用它判定 episode-level envelope valid；dataset、train/eval runtime、
  ACT adapter 和 `primitive_planner_act` 都已接入。
- 2026-05-22 data-only run
  `runs/jobs/yulong_v2_4_5_physical_dump_qc_20260522` 已从最新 removed-depth replay root
  跑完 label transfer/operator-first/hindsight/primitive VDS 和 Gate 1/2，没有进入
  materialize/train。Gate 1 数字 QC 通过：`dig/carry/dump=644`，`return=589`；
  dump length max `315`、p95 `228.7`，release lead max `120`，transition contamination
  `0`；carry deposit contamination `0`；return/dig ratio `0.915`，return envelope valid
  `1.0`。Gate 2 正常暂停等待人工看 selected videos，风险标记集中在
  `carry_mass_loss`、少量 `low_dig_payload/low_effective_deposit` 和 non-gold/short
  window 样本。
- 根据人工关键帧反馈，`runs/jobs/yulong_v2_4_5_process_boundary_qc4_20260522` 把
  边界判断改成过程式 ownership，仍只跑到 Gate 2，没有
  materialize/train。Gate 1 通过：`dig/carry/dump=644`，`return=589`；dump length
  max/p95/p50 为 `293/204.85/154`，pre-release lead mean/p50 为 `45.0/32`；
  carry deposit contamination `0`，`carry_mass_loss` audit flag 从上一版 `54` 降到
  `26`，`short_window` 从 `12` 降到 `4`。新的主要待审项是
  `carry_dump_transition_tight=106`，需要人工确认 dump_start 没有后移过度。
  `tb-audit-primitive-boundaries` 默认在 primitive VDS 写
  `boundary_audit/contact_sheets/index.html` 和
  `boundary_audit/contact_sheets_clean_gold/index.html`；sheet 同时包含边界帧、
  bucket mass/deposit、signed dump-area `relative_x/z`、outside distance、
  `bucket_over_target_footprint_mask`、`dump_clearance_ok_mask`、height above rim 和
  target horizontal distance。carry/dump 边界审阅不能只看无符号 outside-distance。
  最新 refined builder 也采用这个语义：`dump_start` 仍不早于
  `release_onset - 120`，但必须进入 committed aiming band，要求 dump-area 接近、
  signed `relative_x/z` 在宽 corridor 内且短窗口变化量下降到微调级别；区域内 release
  前的 swing/姿态微调归 dump，仍在大幅赶往 dump area 的横向/纵向运动归 carry。
- `runs/jobs/yulong_v2_4_5_process_boundary_qc5_20260522` 是当前 refined
  committed-aiming data-only 候选，同样只跑到 Gate 2，没有 materialize/train。
  Gate 1 通过：`dig/carry/dump=644`、`return=589`，carry deposit contamination
  仍为 `0`。相比 qc4，395/644 个 carry/dump 边界被后移，后移量 p50/mean/p90/p95
  为 `16.5/28.0/78/86` steps；dump pre-release lead mean/p50/p90/p95 从
  `45.0/32/105.7/117.85` 降到 `17.0/12/39.4/64.85`，dump length p50/mean/p95
  从 `154/156.4/204.85` 降到 `131/128.4/196`。carry length p50/mean/p95 从
  `106/110.7/169` 增到 `135.5/138.6/218`，说明此前被 dump 吞掉的 transport 已回到
  carry；mass-loss p95 保持 `3.361kg`。Gate 2 contact sheet 位于 qc5 primitive root
  的 `boundary_audit/contact_sheets/index.html` 和
  `boundary_audit/contact_sheets_clean_gold/index.html`。
- `runs/jobs/yulong_v2_4_5_process_boundary_qc6_20260522` 是当前更严格 outside 的
  data-only 候选：stable outside `0.30m`、fallback max outside `0.35m`，no-candidate
  fallback 贴近 `release_onset`。Gate 1 通过：`dig/carry/dump=644`、`return=589`，
  carry deposit contamination 仍为 `0`。相比 qc5，622/644 个 carry/dump 边界继续
  后移，后移量 p50/mean/p90/p95 为 `3/6.8/10.7/36` steps；dump pre-release lead
  mean/p50/p90/p95 从 `17.0/12/39.4/64.85` 降到 `10.2/9/15/26.85`，dump length
  p50/mean/p95 从 `131/128.4/196` 降到 `125.5/121.6/191`。Gate 2 contact sheet
  位于 qc6 primitive root 的 `boundary_audit/contact_sheets/index.html` 和
  `boundary_audit/contact_sheets_clean_gold/index.html`。
- qc6 已被接受为后续 copy/train/eval 源。训练配置为
  `act_yulong_v2_4_5_process_boundary_qc6_{dig,return_envelope,carry,dump}_qvel.yaml`，
  dataset 指向
  `/fastdata/pingfan/excavator_testbed_data_hot/yulong_v2_4_removed_depth_hindsight_goal_primitives_copy_v2_4_5_process_boundary_qc6_20260522`，
  ckpt root 为 `runs/ckpts/yulong_v2_4_5_process_boundary_qc6_20260522`，且全部保留
  `metadata_filters.training_tier: gold`。训练顺序固定为
  `dig -> return -> carry -> dump`。
- 如果 qc6 return rollout 出现提前下铲或卡 DigArea 壁，先跑离线 ckpt 审计：
  `python -m testbed.cli.audit_return_ckpt --config testbed/configs/act_yulong_v2_4_5_process_boundary_qc6_return_envelope_qvel.yaml --ckpt runs/ckpts/yulong_v2_4_5_process_boundary_qc6_20260522/return/policy_best.ckpt --output runs/jobs/yulong_v2_4_5_process_boundary_qc6_20260522/return_ckpt_offline_audit.json`。
  该工具在 recorded return stream 上比较原始 `return_start_envelope_tokens_v1`、
  depth mask、spatial mask 和 qpos-only envelope，先区分 ckpt 分布问题与
  planner/live token 数值问题。
- 如果 qc6 dig rollout 偏浅，先跑离线 dig checkpoint 审计：
  `python -m testbed.cli.audit_dig_ckpt --config <dig-train-yaml> --ckpt <dig-ckpt>/policy_best.ckpt --episode-ids 198,229,304 --chunk-start-steps 0 --max-steps 160 --output <job>/dig_ckpt_offline_audit.json`。
  它同时比较 recorded stream 的 first-action 和从起点预测出的 ACT chunk；若离线
  chunk 已经偏离专家，优先查 dig checkpoint/训练分布/ACT chunk 机制，若离线贴近专家
  而 live 仍浅，再查 planner handoff 之后的 live observation/action scaling。
- V2.4.5 visual-policy eval 默认设置 `eval.send_planner_debug_to_backend: false`。
  rollout JSONL 仍保留 planner/debug 字段，但不会把 coverage marker/debug geometry
  发给 Unity 渲染进 ACT 的 `fpv` 图像；需要人工 HUD/marker 复查时可以临时打开该开关，
  但这类 rollout 不应用作 ACT 行为判断。
- `tb-eval --output-dir <dir>` 会把 `results_dir`、`video_dir`、`rollout_log_dir`
  和可选 HDF5 rollout 目录一起改到 `<dir>` 下，避免重复 smoke/probe 时 JSONL 仍写回
  原配置目录并覆盖旧 rollout。
- `tb-eval --target-cycle-gate <N>` 可在不复制 YAML 的情况下把同一套 eval 配置扩展到
  5-cycle、10-cycle 等长程 smoke/probe；建议配合 `--output-dir` 写入独立结果目录。
- 如果 qc6 dig rollout 继续偏浅，先跑深度语义审计：
  `python -m testbed.cli.audit_dig_depth_semantics --dataset-dir /fastdata/pingfan/excavator_testbed_data_hot/yulong_v2_4_removed_depth_hindsight_goal_primitives_copy_v2_4_5_process_boundary_qc6_20260522/dig --training-tier gold --output runs/jobs/yulong_v2_4_5_process_boundary_qc6_20260522/dig_depth_semantics_audit.json`。
  当前结论是：planner 继续消费 6-cell removed-depth grid 作为地形状态；ACT 的紧凑
  10D `dig_cut_tokens` 第 8 维改为 surface-relative `cut_depth_semantic_m`，
  来源是修复后的 `bucket_depth_below_local_surface_m` peak。12D
  `dig_depth_profile_tokens_v1` 只作为 ablation/探针，qc6 copy 可用
  `tb-build-dig-depth-profile-tokens-v1 --dataset-dir <qc6-copy>/dig --training-tier gold`
  追加该 token，但默认训练配置不再要求它。
- depth-profile planner/eval 不允许静默 fallback。使用
  `eval_yulong_v2_4_5_qc6_cell_weighted_depth_profile_{3cycle_smoke,15cycle_probe,30cycle_probe}.yaml`
  时，`dig_cut_planner.dig_depth_profile` 固定为 prior-driven strict mode：
  `source: prior_profile`、`required: true`、`allow_live_fallback: false`、
  `allow_global_fallback: false`。这些配置的 `dig_low_dim_keys` 显式包含
  `dig_depth_profile_tokens_v1`，并指向 `dig_depth_profile` checkpoint；如果 low-dim
  key 缺失或 prior cell 缺失，eval/planner 会 fail fast。
- qc6 live return envelope 已改为 prior-driven：`yulong_removed_depth_dig_cut_prior_v3.json`
  里新增 `return_start_envelope_cells/global`，planner 默认注入 qc6 gold return 的
  global median envelope；coverage cell 只通过 pending `dig_cut_tokens` 和 entry gate
  影响下一次 dig，不再默认进入 return-start envelope。旧 cell-conditioned return
  实验需要显式设置 `dig_cut_planner.return_start_envelope.use_cell_prior: true`；只有缺少
  prior 时才回退旧的 current-observation 拼接。eval JSONL 会写
  `return_start_envelope_token_source` 和 `return_start_envelope_tokens`，后续可直接对比
  live token 是否 OOD。
- surface-depth job-local prior 应使用 `tb-build-surface-depth-planner-prior` 或同等逻辑
  生成。`return_start_envelope_cells` 的 cell id 必须由下一铲
  `next_operator_entry_x/z` 最近匹配到 `coverage_cells.entry`，不能由 envelope token
  的 long/short 反推；否则 cell0/cell4 这类边缘姿态会被错分到中间 bucket。
- qc6 eval 同时打开 `return_to_dig_start_envelope_gate_enabled`。这会在
  `return -> dig` handoff 时复用上述 envelope 的 qc6 p05-p95 范围，检查
  long/short、local depth/contact 和 qpos 是否已进入下一轮 dig-start 分布；否则即使
  2D entry error 接近，也继续留在 return。若 prior cell 带
  `dig_start_local_depth_m`，local depth gate 使用真实 dig-start local-depth
  p05-p95 加 `return_to_dig_start_envelope_local_depth_tolerance_m`，并且
  `return_to_dig_start_envelope_require_contact: true` 会独立要求 dig contact，
  不再依赖 token[6]。`dig_start_plane_depth_m` 仍用于检查
  `bucket_depth_below_dig_area_plane`；在 `p50_floor` 下，若 local prior+contact
  gate 可用，plane depth 使用 p05-p95 作 terrain-offset 范围，否则才用 p50 floor
  防止零深度 handoff。旧 `range` mode 仍保留给 legacy/诊断配置。V2.4.5
  planner 会 latch `next_dig_entry_ready`，等 plane-depth/qpos/spatial envelope
  同步 ready 再交接，并会拒绝低于 carry/dump 最低载荷的 `dig_complete` 直接进入
  carry。
- 对于 return relocation ACT，若 `return_start_envelope_tokens_v1` 已经给出目标相关的
  spatial/qpos 起挖包络，可在 eval 的 `policy.switch` 中显式打开
  `return_to_dig_start_envelope_direct_handoff_enabled: true`。这不是 predig scripted
  align；它只允许“空斗、entry-close、envelope-ready”的状态直接从 return 交给 dig，
  避免 semantic boundary 还在等待接触/深度事件时错过浅层起挖窗口。若 dump/carry
  完成当帧已经满足同一 gate，状态机也允许不执行 return ACT 而直接交接，防止 return
  policy 把已经合格的浅接触状态带离训练分布。
- planner trace 现在会输出 `coverage_decision_trace`。该事件流覆盖
  `select_corridor`、`complete_dump`、`reject_corridor` 和 `terminal_stop`，并保存每次
  选择时的 candidate score、remaining depth、attempt/depleted、bucket 几何位置以及
  payload/deposit 结果。调 10cycle 覆盖时优先看它，而不是只看最终
  `coverage_corridors` 快照。
- qc6 eval 配置为
  `eval_yulong_v2_4_5_qc6_cell_weighted_{3cycle_smoke,15cycle_probe,30cycle_probe}.yaml`。
  这些配置显式设置 `boundary.profile: v2_4_5_spatial_mass` 和
  `coverage.candidate_layout: cell_weighted_3x2`，从
  `yulong_removed_depth_dig_cut_prior_v3.json` 的 `coverage_cells` 生成 6 条 3x2
  corridor；`boundary.dump_committed_*` 使用 tightened stable aiming band
  (`outside<=0.25m`, `x=[-0.2,1.9]`, `z=[0.45,2.1]`, rolling range
  `0.06/0.16/0.10m`)，`release_onset_max_outside_distance_m=0.45` 只用于
  已进入 dump 后的 release/drop 识别；旧 prior 没有 `coverage_cells` 时 planner 仍兼容 3x3 percentile grid。
  `target_cycle_gate_terminal_hold_steps=100`，让达成 N-cycle gate 后继续 tail
  100 step，给 dump/coverage summary 和视频尾段留出稳定刷新窗口。
  qc6 人工复核分布为 `0:64, 1:163, 2:142, 3:180, 4:18, 5:82`，cell 4 默认按
  rare cell 限制 first-dig 和 attempt 次数。
- YuLong operator-first rollout 默认使用 `dig_cut_planner.mode=operator_prior`，
  prior 文件为
  `testbed/configs/planner_priors/yulong_removed_depth_dig_cut_prior_v3.json`。
  该 prior 当前来自 qc6 V2.4.5 spatial-mass gold dig 样本，记录 P10/P50/P90、
  3x2 `coverage_cells` 与 lineage；旧固定模板 planner 保留为
  `dig_cut_planner.mode=conservative_pose`，baseline tag 为
  `planner-baseline-conservative-pose-20260516`。
- YuLong V2.4 在同一 10D `dig_cut_tokens` contract 上新增
  `dig_cut_planner.mode=operator_prior_coverage`：planner 从现有 64D
  `env_state` 的 3x2 removed/target/valid grid 和质量/入箱结果维护候选
  cut corridor 的 attempts、低产 streak、depleted 标志与 score。旧 percentile
  grid 覆盖 `entry_x=p10/p50/p90` 与 `entry_z=p10/p50/p90`；带
  `coverage_cells` 的 qc6 prior 使用 3x2 cell-weighted 六候选。planner 用 max-attempt、attempt
  penalty、recent-selection penalty 以及 `recent_row_selection_penalty` 防止长
  rollout 后段继续挖空区或在同一个 3x2 coverage-cell row 上反复横移。它只改变 live dig token
  的选择，不改 checkpoint 和训练 schema。V2.4 hindsight eval 还可用
  `coverage.cut_depth_percentile` / `coverage.payload_percentile` 在专家 prior
  内请求更深、更高 payload 的 cut intent，避免用“继续推到边界”补偿装土不足。
  `coverage.depleted` 是 planner 的 pass-local 尝试状态，不等价于物理土量已经清零。
  当 `coverage.use_env_removed_depth=true` 且对应 cell 的 remaining depth 仍高于
  `coverage.min_remaining_depth_m` 时，planner 不会仅因为 `max_attempts_per_corridor`
  或 `rare_cell_max_attempts` 命中就把该 corridor 标为 depleted；attempt limit 只在缺少
  可挖深度证据或 remaining depth 已低于阈值时终止该 corridor。
  若配置 `coverage.multi_pass_enabled=true`、`coverage.multi_pass_max_passes>1`，
  当所有候选都因低产/attempt limit 被标记 depleted，但 env removed-depth grid 显示仍有
  `coverage.multi_pass_min_remaining_depth_m` 以上余量时，planner 会记录
  `reopen_coverage_pass` 并重开这些 cell；只有没有可重开的余量或 pass 用尽时才报告
  `dig_area_depleted`。
  每步可把压缩的 `planner_debug_json` 作为 `STEP_REQ` optional tail 发给 Unity，让 HUD 和
  DigArea 上方的细竖针/entry-to-exit 箭头实时显示 planner 入铲点与方向。V2.4
  eval 现在还会把当前 bucket tip 的 DigArea-local 位置放进同一个 debug JSON，
  Unity 以洋红十字显示实际铲尖位置，便于判断 dig 是否真的从绿色 entry marker
  附近接管。
- YuLong V2.4 coverage eval 保留 `policy.pre_dig_align` 作为诊断开关。长期
  `return -> dig` 主线仍由 conditioned return 学会回到 next-entry 状态；手写 align
  不替代后续铲的 learned transition。V2.4 conditioned-return / hindsight-goal eval
  只在第 0 铲启用 `pre_dig_align.first_dig_only=true`，用于补上第一铲没有上一轮
  return、固定 bootstrap 会落到 exit/orange 侧的盲点。第 0 铲的 coverage planner
  使用 `coverage.first_dig_strategy=nearest_entry`，按当前 bucket-tip 到候选
  entry 的距离选择更容易接上的 corridor；同时用
  `coverage.first_dig_max_entry_distance_m` 做第一铲 reachability gate：只要存在
  entry 距离在阈值内的专家 corridor，超出阈值的第一铲候选就会被排除。若 replan 后
  新 entry 已经足够近，会直接 handoff 给 dig，避免 open-loop qpos align 又把 bucket
  推离可挖位置。第一铲候选还可配置
  `coverage.first_dig_max_qpos_delta` 与 `coverage.first_dig_qpos_delta_weight`：
  前者排除需要大幅关节迁移的候选，后者在 nearest-entry 评分中惩罚会让
  pre-dig handoff 过度抬/收大小臂的 corridor，使第一铲 handoff 只承担接近正常
  dig-start 的小范围调整。2026-05-22 起第一铲 handoff 还启用
  `pre_dig_align.first_dig_entry_close_handoff=true`：当实际 bucket-tip 已进入
  `max_entry_error_m` 且受控轴速度低于
  `first_dig_entry_close_handoff_qvel_abs_max` 时，即使 qpos 代理目标还没完全 close，
  也允许交给 dig，避免静态 qpos servo 越过 entry 后继续追点。后续铲次不再插入手写
  align，继续使用 return policy 产生的 next-entry handoff。
  几何真值修复后，qc6 eval 还显式设置
  `pre_dig_align.entry_intent_controlled_dims: [1, 0, 0, 0]`：pre-align 只消费
  `dig_cut_tokens` 的水平 entry intent，不再把完整 dig-start token 隐含的深度/姿态语义
  反解成 qpos 目标。`pre_dig_align.surface_guard_enabled=true` 时，若
  `bucket_depth_below_local_surface_m` 已经超过
  `surface_guard_max_penetration_m`，planner 会立刻停止 pre-align servo 并把控制权交给
  dig。entry-intent 模式的成功条件是 intent 受控轴稳定且没有 surface penetration，
  不再把完整 entry-distance close 当作必须条件；bounded timeout 也会 handoff 给 dig，
  并且不会增加 corridor attempts / low-productivity streak。
  live eval 还应显式设置 `switch.dig_to_carry_min_distance_to_dig_area_m: 0.0`：
  第一铲达到 target payload 时要及时交给 carry，不能再要求 bucket 先离开 DigArea，
  否则容易在装满后继续挖/漏料或卡在 dig。
  该 handoff 的专家 dig-start envelope 只作为诊断和宽安全边界：当前 scale025 配置把
  `pre_dig_align.qpos_min/qpos_max` 与 `start_qpos_min/start_qpos_max` 收紧到
  replay 后 dig primitive 起点 qpos 的近似 p05/p95，并把 `bucket_target_qpos`
  设为 `null`，让 token->qpos prior 决定铲斗起始姿态，避免固定把 bucket 压到
  `0.0` 这种不属于正常 dig-start 的姿态；它不应演化成通用 qpos servo 或精确姿态规则。
- 诊断 learned first-handoff 时，可以把旧 dig checkpoint 挂到
  `policy.bootstrap_ckpt_path`，并设置 `bootstrap_low_dim_keys: [qpos, qvel,
  dig_cut_tokens]` 与 `bootstrap_end_mode: first_qualified_dig_start`。planner 会在
  bootstrap policy 存在时给 bootstrap 阶段注入同一个 `dig_cut_tokens`，这样
  10D-conditioned dig ckpt 可以作为第 0 铲之前的 learned bootstrap 做 A/B 测试；
  若同时启用 `pre_dig_align`，scripted handoff 仍会接在 bootstrap 后面，因此该实验
  通常需要先关闭 `pre_dig_align.enabled`。
- 若只想替换第 0 铲实际 dig，而保留现有 handoff，可设置
  `policy.first_dig_ckpt_path` 和可选 `policy.first_dig_low_dim_keys`。planner 只会在
  cycle 0 且尚未完成 dump 前用 `first_dig_policy`，从第二铲开始自动回到普通
  `dig_ckpt_path`。
- YuLong V2.4 return handoff 额外使用 `return_to_dig_max_entry_error_m` 约束：
  return 只有在 planned next-entry 附近才允许切回 dig。若 entry 已经 close，
  shallow guard 可覆盖很窄的 `return_to_dig_max_depth_m` 上限，防止 return 已到点后
  继续把 bucket 压进土里等待 `qualified_dig_start`。V2.4.5 的
  `return_start_envelope_tokens_v1` 是 return 训练条件和 QC 目标，不表示 planner 要用
  qpos 规则强行规定姿态；qc6 handoff 会用 envelope 分布做 readiness gate，确保
  pending `dig_cut_tokens` 只在当前状态已进入对应 dig-start envelope 后交给 dig。
- YuLong V2.4 conditioned return 当前使用固定 10D `return_target_tokens`，语义与
  `dig_cut_tokens` 对齐，但只表示“下一铲”的 cut intent。最近 live 结果说明这对
  return 不够：return 还需要 next dig-start state envelope，显式描述 bucket tip
  容差、浅接触/深度范围、bucket curl/pitch、boom/stick/bucket qpos、qvel 近零和专家
  dig-start pose 分布。训练入口使用
  `data/yulong_v2_4_return_conditioned_primitives_copy/return`，该 root 必须是
  materialized copy，关键数据集不能是 VDS。没有下一铲目标的 terminal return
  window 必须 reject，不进入 conditioned return 训练。live 时 planner 在 return
  阶段注入 return conditioning token；V2.4.5 应改为
  `return_start_envelope_tokens_v1`，下一次 dig 继续复用同一个 pending
  `dig_cut_tokens`，避免 return 追一个目标、dig 又重新规划另一个目标。
- V2.4.5 return relocation 训练新增 `return_relocate_tokens_v1`，它是
  `return_target_tokens` 的派生 low-dim key，只保留 entry/exit/direction/length/valid，
  depth 和 payload 固定为 0。当前 surface-depth return-only 重训使用
  `qpos + qvel + return_start_envelope_tokens_v1 + return_relocate_tokens_v1`，
  不重切数据、不重训 dig/carry/dump。该输入组合训练时的
  `token_swap_outcome_loss` 需要同步交换 envelope 与 relocate 两个 token slice；
  只交换 envelope 会把 relocation 监督变弱，live 更容易回到全局 median 姿态。
  return-relocate 重训应使用 `return_relocate_outcome_targets_v1`
  supervision：它从 `return_outcome_targets` 派生，但屏蔽 depth/payload 维度，
  保证 return 只学回到下一铲位置/方向附近，不承担下一段 dig 的挖深或装料目标。
- live return 默认 global `return_start_envelope_tokens_v1` 会把 qpos center 固定在
  qc6 gold return 的全局 median dig-start 姿态附近；如果希望 return ACT 自己回到
  下一铲 entry 附近，而不是靠 `pre_dig_align` 脚本补偿，应启用
  `dig_cut_planner.return_start_envelope.{spatial,qpos}_from_relocate`，用
  `return_relocate_tokens_v1` 派生 target-specific envelope spatial long/short 和
  qpos center。
- surface-depth planner prior 的 `return_start_envelope_cells` 会随 cell 写入
  `dig_start_plane_depth_m` / `dig_start_local_depth_m`，来源是对应 gold dig primitive
  的真实起始状态。handoff gate 优先用 local-depth stats 加 contact 判断是否真正进入
  surface-relative dig-start 分布，再用 plane-depth stats 做 terrain-offset 检查，
  避免 return 只满足 qpos/spatial envelope、但 bucket 仍未接触有效起挖 surface 时
  过早 handoff 给 dig。
- YuLong V2.4 reconstructed-belief sweep planner 使用
  `dig_cut_planner.mode=operator_prior_sweep_belief`。它不依赖当前全零的
  Unity `removed_depth`，而是根据历史 cut corridor、payload、effective deposit
  与低产 streak 更新 coverage belief。低产 dig 不应无限卡在 dig：当前 sweep
  eval 在 45kg target payload 之外允许 `15kg` 以上的 plateau payload 超时进入
  carry，并在当前 bucket mass 低于 15kg 的长 dig 后 reject 当前 corridor、重选下一条
  cut intent。bad-dig 判据使用当前保留质量，不使用 transient best mass，避免 bucket
  曾短暂碰到土但最后空斗时继续卡在 dig。V2.4 hindsight eval 还启用
  `dig_exit_guard_*`：当 bucket tip 已沿 planned entry→exit 方向越过 yellow exit
  一定距离但 payload 仍过低时，将当前 cut 判为 `exit_overshoot_low_payload`。
  默认 replan 仍兼容旧行为，在 dig skill 内重选 cut；诊断/eval 应配置
  `policy.switch.dig_failed_replan_next_skill: stop`，失败时直接结束 rollout，
  并在 rollout summary / planner trace 中留下 `dig_failed_*` 退出原因，避免补救动作掩盖
  planner/ACT 的真实根因。
- 当前 depth 控制仍是 open-loop token conditioning：`cut_depth_percentile=p90` 会把
  depth token 推到专家 prior 的深挖端，但并不等价于 closed-loop depth controller。
  若 Unity depth/soil response 不支持或 ACT 未学会对应姿态，planner 只能通过 bad-dig /
  exit guard 早停重选，不能手写每一步 bucket 轨迹。
  与 low-productivity streak 维护覆盖 belief；30cycle 是 depletion/probe，不是
  固定成功门槛。
- YuLong V2.4 coverage smoke 的 `dig -> carry` 不再以 `15kg` 作为正式离开条件。
  `15kg` 只作为最低有效质量和 bad-dig 判据；正式 target payload 为 `45kg`，
  或者 `>=35kg` 后质量 plateau 才允许切 carry。`220` step 仍低于 `35kg` 的 dig
  会标记 `bad_dig_low_payload` 并回到 planner/replan，避免 carry 被污染成继续挖土。
- YuLong V2.4 hindsight-goal 1cycle smoke 先把 `dig_bad_replan_min_bucket_mass_kg`
  提高到 `25kg`。当前没有 false-recovery 数据，eval 更偏向早重选坏起点，而不是让
  dig policy 在低 payload 起点里长时间空转。

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
| YuLong V2.4 primitive copy build | `tb-build-primitives-v2_2 --raw-dir <operator-first-copy-root> --output-root <primitive-copy-root> --storage-mode copy --boundary-profile v2_2_effect_release_fallback` | 从 operator-first enriched raw 直接切实体 HDF5 primitive；用于 conditioned return 训练热入口 |
| YuLong V2.2 primitive materialized copy | `tb-materialize-vds --input <primitive-vds-dir> --output <primitive-copy-dir>` | 从 VDS wrapper 落成实体 HDF5；用于新 SSD 上的训练吞吐 A/B |
| YuLong V2.2 primitive image-VDS archive | `tb-virtualize-images --input <primitive-copy-dir> --output <primitive-image-vds-dir> --recursive` | 历史归档入口：只把图像反向 VDS 化，低维状态和标签仍在 wrapper 内 |
| YuLong V2.2 conditioned dig 训练 | `testbed/configs/act_yulong_v2_2_pro_conditioned_dig_cell_entry_qvel.yaml` | dig 使用 `qpos + qvel + cell_entry_tokens`，读取 VDS primitive dig root |
| YuLong V2.2 operator-first 4P 500 epoch 训练 | `testbed/configs/act_yulong_v2_2_operator_first_4p_{dig_cut,carry,dump,return}_qvel.yaml` | dig 使用 `qpos + qvel + dig_cut_tokens`；carry/dump/return 使用 `qpos + qvel` |
| YuLong V2.2 operator-first primitive planner smoke | `testbed/configs/eval_yulong_v2_2_operator_first_primitive_planner_4p_500e_smoke.yaml` | 加载 4 个 operator-first checkpoint；live 只给 dig 注入 operator-prior `dig_cut_tokens` |
| YuLong V2.2 conservative planner baseline smoke | `testbed/configs/eval_yulong_v2_2_operator_first_primitive_planner_4p_500e_conservative_pose_smoke.yaml` | 回放旧 `conservative_pose` dig token 模板，用于 A/B 和 git baseline 对照 |
| YuLong V2.2 5-cycle clean-dump smoke | `testbed/configs/eval_yulong_v2_2_operator_first_primitive_planner_4p_500e_5cycle_clean_dump_smoke.yaml` | 5 dig 压力测试；bucket 残余阈值 `15kg`，dump/terminal hold 约 `2s`，默认不写 HDF5 |
| YuLong V2.2 10-cycle clean-dump smoke | `testbed/configs/eval_yulong_v2_2_operator_first_primitive_planner_4p_500e_10cycle_clean_dump_smoke.yaml` | 10 dig 压力测试；bucket 残余阈值 `15kg`，no post-dump hold，smooth dump 用累计入箱质量识别，return 浅接触 entry 后切 dig，默认不写 HDF5 |
| YuLong V2.4 coverage planner 15-cycle smoke | `testbed/configs/eval_yulong_v2_4_operator_prior_coverage_15cycle_smoke.yaml` | 保住 15cycle milestone 的 A/B 入口；仍用 V2.2 4P checkpoint，只把 live dig planner 换成 coverage corridor，并把 planner decision 发到 Unity HUD/入铲点竖针 |
| YuLong V2.4 coverage planner 30-cycle probe | `testbed/configs/eval_yulong_v2_4_operator_prior_coverage_30cycle_probe.yaml` | 30cycle 是 depletion/probe，不是固定 success 标准；期望覆盖更多 corridor，并在低产/耗尽/疑似穿模时用 planner terminal reason 停止 |
| YuLong V2.4 conditioned-return sweep 15-cycle | `testbed/configs/eval_yulong_v2_4_conditioned_return_sweep_15cycle.yaml` | dig/carry/dump 复用 V2.2 checkpoint，return 使用 conditioned checkpoint；planner 用 reconstructed belief，不读全零 removed-depth |
| YuLong V2.4 conditioned-return sweep 30-cycle | `testbed/configs/eval_yulong_v2_4_conditioned_return_sweep_30cycle.yaml` | 30cycle probe 入口；看 coverage belief、return target gap、payload/deposit 和 terminal reason |
| YuLong V2.4 copy-root conditioned dig retrain | `testbed/configs/act_yulong_v2_4_dig_conditioned_copy_qvel.yaml` | 用 materialized copy `dig` primitive 重训 `qpos + qvel + dig_cut_tokens`，用于比较新旧 dig ACT 是否真正对 token 敏感 |
| YuLong V2.4 hindsight-goal relabel | `tb-build-hindsight-goal-v2_4 --dataset-dir <operator-first-copy-root> --output-dir data/yulong_v2_4_hindsight_goal_relabel_copy` | 从自然 pro 数据反推 `dig_outcome_targets` / `return_outcome_targets`，materialized copy，不改 raw |
| YuLong V2.4 hindsight-goal dig/return 训练 | `testbed/configs/act_yulong_v2_4_hindsight_goal_{dig,return}_qvel.yaml` | 只训练 dig/return；action BC + KL + outcome loss + token-swap outcome loss，默认 `training_tier=gold` |
| YuLong V2.4 hindsight-goal rollout | `testbed/configs/eval_yulong_v2_4_hindsight_goal_{1,3,5}cycle_smoke.yaml`、`..._10cycle.yaml`、`..._15cycle.yaml`、`..._30cycle_probe.yaml` | planner 仍是 rule/belief proposer，只替换 dig/return hindsight-goal checkpoint；30cycle 仍为 depletion probe |
| YuLong V2.2 conditioned dig primitive planner smoke | `testbed/configs/eval_yulong_v2_2_pro_primitive_planner_conditioned_dig_smoke.yaml` | `primitive_planner_act` 只给 dig 注入 Cell Entry token；carry/dump/return 仍为 `qpos + qvel` |
| YuLong FarmStick replayx20 rollout smoke | `testbed/configs/eval_yulong_farmstick_3cycle_replay20_workskill_qvel_smoke.yaml` | 单 rollout 接回 Unity；无 YuLong bootstrap，直接 smoke work policy |
| YuLong V2.2 四 primitive contact-depth 训练 | `testbed/configs/act_yulong_farmstick_3cycle_replay20_contact_depth_v2_2_4p_{dig,carry,dump,return}_qvel.yaml` | 小斗 YuLong 主训练入口；`qualified_dig_start=contact_depth` 后重切，四类各 40 条且无 reject |

YuLong operator-first 训练优化不改变图像分辨率或推理输入语义。当前配置仍读取原始
`fpv` 图像，只通过 `batch_size`、`num_workers`、`prefetch_factor`、
`hdf5_cache_size`、TF32/cudnn benchmark 和较低频率的 validation/plot 来提高吞吐；
如果出现 CUDA OOM，优先把对应 primitive 的 `batch_size` 下调。
同一轮的 conditioned dig 与 5/10/15-dig GC-ACT VDS diagnostic 配置也默认打开
4 个 DataLoader worker、`persistent_workers` 和 HDF5 handle cache；迁到新 SSD
时要把 VDS wrapper 及其 sibling source roots 一起放在同一个新 archive root 下，
否则 wrapper 仍可能通过旧 `/data` 上的源 HDF5 读图像。
新写出的 HDF5 图像默认按完整 frame chunk：`(1, H, W, C)` + `lzf`，避免 h5py
自动 chunk 成跨很多 timestep 的小空间 tile。训练时每个 sample 只随机读一个
`fpv` frame，这个布局比旧 `(625, 15, 45, 1)` 一类 chunk 更贴合 DataLoader 的访问模式。
ACT live temporal aggregation 使用 rolling query window：当前动作只会被最近
`chunk_size` 个预测 chunk 影响，因此 eval 端只保留 `(chunk_size, chunk_size, action_dim)`
buffer，而不是按 `episode_len^2` 分配显存。这保持 temporal aggregation 语义，同时允许
10/15/30-cycle 这类长 rollout 使用较大的 `task.episode_len`。
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
截断。可用 `--post-tail-steps <N>` 临时覆盖。刷新 replay 只读 source
episode 的 actions/qpos/metadata，不读旧 image dataset；输出图像来自当前
Unity 后端。

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
| `act_yulong_v2_4_dig_conditioned_copy_qvel.yaml` | YuLong V2.4 conditioned dig 诊断重训 | `qpos + qvel + dig_cut_tokens`，读取 materialized copy dig root；训练前后用 `python -m testbed.cli.dig_token_sensitivity` 比较 token sensitivity |
| `act_yulong_v2_4_return_conditioned_qvel.yaml` | YuLong V2.4 conditioned return 主线 | 当前为 `qpos + qvel + return_target_tokens`，读取 materialized copy return root；V2.4.5 计划改为 `qpos + qvel + return_start_envelope_tokens_v1` |
| `runs/jobs/yulong_v2_4_5_return_relocate_train_eval_20260525/train_configs/act_return_relocate_surface_depth_qvel.yaml` | YuLong V2.4.5 surface-depth return relocation 重训 | `qpos + qvel + return_start_envelope_tokens_v1 + return_relocate_tokens_v1`，读取 surface-depth qc6labels scale080 return copy；只重训 return，dig/carry/dump 复用上一轮 ckpt |
| `act_yulong_v2_4_hindsight_goal_dig_qvel.yaml` | YuLong V2.4 outcome-grounded dig 主线 | `qpos + qvel + dig_cut_tokens`，读取 hindsight-goal copy dig root；supervision 为 `dig_outcome_targets`，只用 gold tier |
| `act_yulong_v2_4_5_process_boundary_qc6_dig_depth_profile_qvel.yaml` | YuLong V2.4.5 qc6 depth-profile dig 诊断重训 | `qpos + qvel + dig_cut_tokens + dig_depth_profile_tokens_v1`，读取 qc6 materialized dig copy；用于验证 ACT 是否能把 removed-depth target 与姿态深度 profile 分开学习 |
| `eval_yulong_v2_4_5_qc6_cell_weighted_depth_profile_{3cycle_smoke,15cycle_probe,30cycle_probe}.yaml` | YuLong V2.4.5 qc6 depth-profile eval | dig 指向 `runs/ckpts/.../dig_depth_profile`，planner 使用 qc6 per-cell `dig_depth_profile_cells` strict prior，不允许 live/global fallback |
| `act_yulong_v2_4_hindsight_goal_return_qvel.yaml` | YuLong V2.4 outcome-grounded return 主线 | 当前为 `qpos + qvel + return_target_tokens`，读取 hindsight-goal copy return root；supervision 为 `return_outcome_targets`，只用 gold tier；V2.4.5 需要 `return_start_envelope_tokens_v1` 与 endpoint envelope QC |
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
`docs/primitive_phase_boundaries.md`。

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
  `docs/primitive_phase_boundaries.md` as the manipulation contract.

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
YuLong 10-cycle clean-dump config 是当前例外：不再使用 post-dump hold，而是让
BoundaryDetector 用 `deposit_started_threshold_kg` 对累计有效入箱质量识别 smooth
professional dump；同时启用 `return_to_dig_shallow_guard_enabled`，当 return 空斗到达
dig-area 浅接触 entry 时直接切回 dig，防止 return primitive 继续下压到箱底。
长周期 YuLong smoke 使用 outcome-first `carry -> dump` handoff：bucket 已在 dump
footprint 上方、离 rim 足够高、bucket mass 仍高于 `15kg` 时即可 handoff 到 dump；
signed x/z window 保留为旧规则兼容。这个规则避免长 rollout 后段因土量下降到
`20kg` 以下、或 target-relative 坐标漂到窗口另一侧而一直停留在 carry。
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
- `dig_precision_cycle_count`
- `dig_entry_error_mean_m` / `dig_entry_error_max_m`
- `dig_exit_error_mean_m` / `dig_exit_error_max_m`
- `dig_exit_signed_error_mean_m`
- `dig_exit_abs_overshoot_mean_m` / `dig_exit_abs_overshoot_max_m`
- `dig_entry_expert_box_hit_rate` / `dig_entry_expert_radial_p95_hit_rate`
- `dig_exit_expert_box_hit_rate` / `dig_exit_expert_radial_p95_hit_rate`
- `dig_entry_error_over_expert_p95_mean` / `dig_exit_error_over_expert_p95_mean`
- `dig_depth_target_mean_m` / `dig_depth_peak_mean_m`
- `dig_depth_error_mean_m`
- `dig_depth_abs_error_mean_m` / `dig_depth_abs_error_max_m`
- `dig_depth_expert_range_hit_rate`
- `dig_depth_expert_p95_overshoot_mean_m` / `dig_depth_expert_p95_overshoot_max_m`
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

单条 rollout summary / manifest 还会输出 `cycleN_entry_error_m`、
`cycleN_exit_error_m`、`cycleN_exit_signed_error_m`、`cycleN_depth_target_m`、
`cycleN_depth_peak_m` 和 `cycleN_depth_error_m`，用于直接观察每一铲相对 planner
entry / exit / depth token 的执行误差。聚合后的 `metrics.json` 会输出对应
`avg_cycleN_*` 字段，默认覆盖 `1..30` cycle。

如果 planner prior 的 `coverage_cells` 带专家分布，单条 rollout summary / manifest
还会输出每铲的 intent-vs-execution-vs-prior 字段，例如
`cycleN_entry_planned_x_m`、`cycleN_entry_actual_x_m`、
`cycleN_entry_expert_x_p05_m` / `p50_m` / `p95_m`、
`cycleN_entry_expert_radial_p95_m`、`cycleN_entry_expert_radial_p95_hit`，
以及对应的 `exit` 和 `depth_expert_*` 字段。它们用于判断 ACT 是没有严格命中
planner p50 点，还是已经偏离当前 cell 的专家分布。

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
当配置 `eval.target_cycle_gate` 时，报告会额外输出 `target_cycle_gate_success`、
`target_cycle_completed_dump_count`、`target_cycle_gate_success_rate` 和
`target_cycle_completed_dump_mean`。这些字段才表示 N-cycle gate 是否真正达成；
qc6 N-cycle 配置会在 gate 后 tail 100 step，避免停止当帧截断末尾
dump/coverage 刷新。
AGX 的 `success_rate` 仍按 `success.mode` 表示物料/倒土成功，不能单独当作 10cycle 成功。

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
- 旧低频 sector `goal_tokens` 只作为 diagnostic/legacy 对照。历史 YuLong V2.2
  数据和 checkpoint 仍可保留 `cell_entry_tokens` 低维 schema，但 primitive planner
  里的 cell-entry runtime 已删除；新 runtime 配置不能再启用 `policy.cell_entry`。
  若需要保留旧 block 作为报告/schema 兼容占位，必须显式禁用：

```yaml
policy:
  class: "primitive_planner_act"
  cell_entry:
    enabled: false
  dig_low_dim_keys: ["qpos", "qvel"]
  return_low_dim_keys: ["qpos", "qvel"]
  carry_low_dim_keys: ["qpos", "qvel"]
  dump_low_dim_keys: ["qpos", "qvel"]
```

设置 `policy.cell_entry.enabled: true` 会在 primitive-planner config
normalization 阶段 fail-fast。历史 HDF5 / training / eval 代码仍可读取已有
`cell_entry_tokens` 数据，但当前 primitive planner 不再注入 token、不再运行
cell-entry planner/auditor trace，也不会把 cell-entry completion 作为 backend effect。
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
