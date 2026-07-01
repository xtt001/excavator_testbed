# 训练与评测 Runbook

状态日期：2026-06-30
适用范围：Repo A 仿真库当前 V2.4 / V2.4.5 训练、评测、离线审核流程。V1、V2.1 和早期 V2.2 内容只作为历史对照，不再作为默认训练依据。

## 1. 当前信源

训练前先以这些文件为准：

- 数据、VDS、primitive、QC 和 Gate 合同：`docs/data_processing_hdf5_qc_contract.md`
- planner / ACT 行为边界：`docs/planner_to_act_conceptual_contract.md`
- config 入口和历史/当前状态：`testbed/configs/README.md`
- LLM planner 前地形闭环方向：`docs/llm_planner_closed_loop_terrain_conclusion.md`
- 代码事实：`testbed/data/*`、`testbed/train/*`、`testbed/evaluation/*`、`testbed/pipeline/*`

如果本文和上述信源冲突，以上述信源和当前代码为准，并更新本文。

## 2. 当前训练心智模型

现在的训练闭环不再是“拿 HDF5 直接训练 ACT”。默认链路是：

```text
raw full-cycle / replay refreshed root
  -> tb-dataset-qc
  -> tb-label-v2_1
  -> tb-build-operator-first-v2_2
  -> tb-build-hindsight-goal-v2_4
  -> tb-build-primitives-v2_2 --boundary-profile v2_4_5_spatial_mass
  -> Gate 1: pre-materialize QC
  -> Gate 2: tb-audit-primitive-boundaries + contact sheet / manual review
  -> tb-materialize-vds
  -> Gate 1b: materialized-copy QC
  -> tb-train
  -> policy audit / policy audit manifest
  -> tb-eval
  -> rollout review / root-cause audit
```

定位问题时按四层拆开：

1. 数据 QC：raw、VDS、materialized copy、字段、mask、primitive boundary、reject 统计。
2. Policy audit：训练后、eval 前，对 checkpoint 做离线行为审核。
3. Policy audit manifest：eval 前汇总已有离线 audit JSON，生成证据清单。
4. Rollout review：eval 后看 planned vs actual、handoff、coverage trace、terminal reason。
5. Root-cause audit：只有前面证据指出明确症状后，再追 live observation/action scaling、temporal aggregation、控制切换等。

### 2.1 检查类型命名

长期文档中统一使用这些名称，不再依赖临时计划文件：

| 名称 | 阶段 | 作用 |
| --- | --- | --- |
| `data QC` | 训练前 | 检查数据质量，包括 raw / VDS / materialized copy、字段、mask、primitive 边界和 reject 统计。 |
| `policy audit` | 训练后、eval 前 | 检查 checkpoint 在 recorded stream 上是否已经不跟 token 或不跟专家。 |
| `policy audit manifest` | eval 前 | 汇总已有离线 audit JSON；缺失项只能标为 `missing`，不能伪造通过。 |
| `rollout review` | eval 后 | 检查真实闭环表现，包括 planned vs actual、handoff、coverage trace 和 terminal reason。 |
| `root-cause audit` | rollout review 发现明确症状后 | 定位问题来自 policy、token 语义、handoff、live scaling、planner belief 还是数据/QC 回流。 |

## 3. 当前数据合同

### 3.1 HDF5 / VDS 基本字段

当前 YuLong / V2.4.5 体系里，低维状态不再按旧 9D 假设理解。常用字段包括：

- `/observations/qpos`
- `/observations/qvel`
- `/observations/env_state`：当前合同为 64D，具体语义以 schema / QC 合同为准。
- `/action`
- `/observations/images/<camera_name>`
- `/v2/*`：阶段、事件、token、outcome target、valid mask 等训练/审核字段。

训练配置只应显式消费当前 primitive 需要的字段，不应把全量 env_state 当作默认 policy 输入。

### 3.2 当前 primitive 输入与监督

| Primitive / family | 默认低维输入 | 监督 / head | 状态 |
| --- | --- | --- | --- |
| dig V2.4 hindsight-goal | `qpos + qvel + dig_cut_tokens` | `dig_outcome_targets` | 当前可用 |
| dig V2.4.5 spatial-mass | `qpos + qvel + dig_cut_tokens` | `dig_outcome_targets` | 当前主线 |
| dig depth-profile 诊断 | `qpos + qvel + dig_cut_tokens + dig_depth_profile_tokens_v1` | `dig_outcome_targets` | 深度语义/浅挖诊断用 |
| return envelope | `qpos + qvel + return_start_envelope_tokens_v1` | `return_outcome_targets` | 当前可用 |
| return relocate / 后续变体 | `qpos + qvel + return_*_tokens` | `return_outcome_targets` | 以 config 为准 |
| carry / dump V2.4.5 | `qpos + qvel` | 当前 first-version 监督 | 可训练但需审核 |

关键判断：

- `dig_cut_tokens` 目前仍是深度控制的主要间接入口。
- `dig_depth_profile_tokens_v1` 是深度轨迹监督/语义诊断方向，不等价于已经完成 depth closed-loop。
- return 的起点/包络 token 是为减少从 dig 到 return 的分布断裂，不应和旧 9D env_state 混为一谈。

## 4. 当前 config 家族

以 `testbed/configs/README.md` 为索引，常用入口如下。

| 场景 | 代表 config | 用途 |
| --- | --- | --- |
| V2.4.5 spatial-mass dig | `act_yulong_v2_4_5_spatial_mass_dig_qvel.yaml` | 当前 dig 主线训练 |
| V2.4.5 spatial-mass return | `act_yulong_v2_4_5_spatial_mass_return_envelope_qvel.yaml` | 当前 return 主线训练 |
| V2.4.5 spatial-mass carry | `act_yulong_v2_4_5_spatial_mass_carry_qvel.yaml` | carry first-version |
| V2.4.5 spatial-mass dump | `act_yulong_v2_4_5_spatial_mass_dump_qvel.yaml` | dump first-version |
| QC6 process-boundary dig | `act_yulong_v2_4_5_process_boundary_qc6_dig_qvel.yaml` | qc6 accepted split 正式训练入口 |
| QC6 process-boundary return | `act_yulong_v2_4_5_process_boundary_qc6_return_envelope_qvel.yaml` | qc6 accepted split 正式训练入口 |
| Depth-profile 诊断 | `act_yulong_v2_4_5_process_boundary_qc6_dig_depth_profile_qvel.yaml` | 深度 token / trajectory 诊断 |
| V2.4 hindsight-goal | `act_yulong_v2_4_hindsight_goal_*_qvel.yaml` | V2.4 对照/过渡 |
| V2.2 pro teleop | `teleop_yulong_v2_2_pro_pilot.yaml`、`teleop_yulong_v2_2_pro_full_task.yaml` | 新环境手动采集 |

历史入口：

- `act_agx_v1*`、`eval_agx_v1*`、早期 `v2_1*` 只用于复现实验或对照，不再作为新训练默认选择。
- 早期 `episode_len=1000`、`qpos only`、`9D env_state`、`dump_complete_final_hold` 等写法，不能直接迁移到 V2.4.5。

## 5. 训练前 Gate

训练前必须完成三类检查。

### 5.1 Gate 1：pre-materialize QC

确认 primitive root 上的字段、mask、episode、phase、boundary、reject 统计没有 blocking issue。典型产物包括：

- `04_pre_materialize_qc.json`
- primitive summary / reject stats
- source lineage / metadata

### 5.2 Gate 2：人工视觉审阅

V2.4.5 的 Gate 2 不是形式动作。训练前需要看 boundary audit 的视频和 contact sheet，尤其是：

- phase boundary 是否切在正确动作段。
- dig / return / carry / dump 的起止帧是否符合 planner/ACT 合同。
- clean-gold 集合是否真的干净。
- 是否存在系统性浅挖、空斗、提前 return、错误 dump 等模式。

典型产物：

- `summary.json`
- `boundary_audit.csv`
- `videos/`
- `contact_sheets/index.html`
- `contact_sheets_clean_gold/index.html`

只有完成审阅后，才应在后续命令中使用 `--ack-feedback-gates`。

### 5.3 Gate 1b：materialized-copy QC

VDS materialize 后，要对 materialized copy 再做一次字段和样本检查。训练默认使用 materialized primitive copy，而不是隐式依赖原始 VDS。

默认训练 tier 是 `training_tier=gold`。如果要引入 silver，必须在 config 和实验记录里显式说明。

## 6. 训练运行记录

每次训练至少记录这些信息：

- 原始数据 root、primitive root、materialized copy root。
- 使用的 config、resolved config、`low_dim_keys`、`supervision_keys`。
- checkpoint 输出目录、best checkpoint 路径、训练日志路径。
- Git commit / dirty status。
- Gate 1、Gate 2、Gate 1b 产物路径。
- 是否使用 `--ack-feedback-gates`，以及人工审阅结论。
- 是否只用 gold tier，或显式混入 silver。
- 训练后 policy audit、eval rollout、rollout review 的输出目录。

建议 run id 包含：

```text
<primitive>_<dataset-tag>_<contract-tag>_<date-or-short-hash>
```

示例：

```text
dig_qc6_depth_profile_20260622
return_qc6_envelope_20260622
```

## 7. 训练与审核命令

命令以当前 config 为准，下面只记录意图。

```bash
RUN_ID=<run_id>
AUDIT_DIR=runs/audit/${RUN_ID}

# 训练
tb-train --config testbed/configs/<act_config>.yaml

# dig checkpoint 离线审核
tb-audit-dig-ckpt \
  --config testbed/configs/<dig_act_config>.yaml \
  --ckpt <dig_checkpoint> \
  --output "${AUDIT_DIR}/dig_ckpt_audit.json"

# dig 深度语义审核
tb-audit-dig-depth-semantics \
  --dataset-dir <dig_dataset_dir> \
  --output "${AUDIT_DIR}/dig_depth_semantics_audit.json"

# return checkpoint 离线审核
tb-audit-return-ckpt \
  --config testbed/configs/<return_act_config>.yaml \
  --ckpt <return_checkpoint> \
  --output "${AUDIT_DIR}/return_ckpt_audit.json"

# eval 前证据清单
tb-policy-audit-manifest \
  --output "${AUDIT_DIR}/policy_audit_manifest.json" \
  --dig-ckpt-audit "${AUDIT_DIR}/dig_ckpt_audit.json" \
  --dig-depth-audit "${AUDIT_DIR}/dig_depth_semantics_audit.json" \
  --return-ckpt-audit "${AUDIT_DIR}/return_ckpt_audit.json"

# 评测 / rollout
tb-eval --config testbed/configs/<eval_config>.yaml

# eval 后 rollout review，默认写入 <eval_results_dir>/rollout_review.json
tb-rollout-review --results-dir <eval_results_dir>
```

`policy_audit_manifest.json` 只汇总已有 audit JSON，不替代 `tb-audit-dig-ckpt`、`tb-audit-dig-depth-semantics`、`tb-audit-return-ckpt`。缺少某类 audit 或 schema 不匹配时必须保留为 evidence gap。

如果 return config 同时使用 `return_start_envelope_tokens_v1` 和 `return_relocate_tokens_v1`，`tb-audit-return-ckpt` 会读取 recorded stream 中的 return-relocate token；受控 token 变体仍主要用于检查 return-start envelope 对动作的影响。

浅挖类问题优先看：

- dig token / depth-profile 分桶是否被 policy 区分。
- 目标 depth、实际 depth、payload、mass outcome 是否一致。
- checkpoint 离线正常但 live rollout 异常时，再查 observation scaling、action scaling、handoff 和 temporal aggregation。

return 类问题优先看：

- return 起点 envelope token 是否有效。
- dig->return handoff 时的姿态、bucket height、payload 是否落在训练分布内。
- return policy 是否能按 envelope 做起步，而不是复用旧固定轨迹。

## 8. Eval 与 rollout review

当前 eval 不只看“有没有完成若干 cycle”。每次 rollout review 至少检查：

- dig planned vs actual：entry、exit、dig depth、payload。
- carry / dump transport quality：deposited fraction、low deposit、残留或漏料等质量指标。
- `return -> dig` handoff readiness：是否回到下一铲 entry 附近，能否交接给 dig。
- `coverage_decision_trace`：选点、跳点、重复点、fallback 是否合理。
- terminal reason：成功、timeout、safety stop、empty bucket、wrong phase 等。
- 视频 / contact sheet：是否存在肉眼可见但指标没捕获的问题。

标准产物路径：

```text
<eval_results_dir>/rollout_review.json
```

`rollout_review.json` 的顶层字段包括 `schema_version`、`source_results_dir`、`overall_status`、`evidence_gaps`、`rollout_reviews`、`root_cause_hints`、`llm_candidate_ranking_ready`。该报告只做诊断，不改变 eval success 语义。

每个 rollout review 还会输出 `terrain_residual` 诊断块。该块只读取 per-rollout jsonl
中最新可用的 compact dig-area `env_state` 快照，使用 `testbed.data.schema` 中的
grid count、removed-depth、target-depth 和 valid-mask 下标计算：

- `removed_depth_grid_m`、`target_depth_grid_m`、`residual_depth_grid_m = target - removed`。
- valid cell 上的 positive residual、overdig、target/removed depth sum 和
  `target_removed_completion_ratio = sum(min(removed, target)) / target_depth_sum_m`。
- `snapshot_row_index`、`grid_shape`、`cell_count`、`valid_cell_count` 和明确的 source
  provenance。
- `residual_convergence_curve`：按 per-rollout jsonl 中连续 `dig` 段取该段最后一个可用
  compact grid 快照，记录 `dig_segment_index`、`snapshot_row_index`、positive residual、
  overdig、target/removed depth sum、completion ratio 和 valid cell count。该曲线是
  dig-segment 诊断证据，不声明官方 cycle id 语义。
- `residual_convergence_summary`：只从 `residual_convergence_curve` 派生，报告起止
  dig-segment 点数、positive residual / overdig / completion ratio 的起点、终点和
  delta，并给出诊断性 `diagnostic_trend`。该 trend 只概括已观察 dig-segment 证据，
  不作为 eval pass/fail、planner success 或官方收敛语义。

当前记录没有 cell size、origin、timestamp、frame transform、height/elevation grid 或
confidence grid，报告必须把这些字段标为 `missing`，不能从现有 jsonl 推断。该 residual
块、convergence curve 和 convergence summary 都是离线诊断和 baseline 投影，不改变
planner、gate、checkpoint、token 或 eval success 语义。由于 cell size 仍缺失，
positive residual、overdig、target/removed 仍是 depth sum，不是物理体积。

T1-like rectangular shallow-pit 目标网格当前只提供显式参数生成器
`testbed.eval.terrain_target_grid.build_rectangular_target_grid()`，用于后续离线 target-shape
诊断。调用方必须显式传入 grid shape、valid mask、半开 row/col 矩形边界和 target depth；
该工具按 row-major 顺序生成 `target_depth_grid_m` 与 `target_region_mask`，并报告
`valid_cell_count`、`target_cell_count`、`target_depth_sum_m`、`validation_errors` 以及
缺失的 cell size / origin / timestamp / frame transform / height/elevation / confidence
provenance。矩形若选中 invalid cell 会被拒绝为 `invalid_target_region_mask`，不会静默把
invalid cell 当作 target cell。该工具不声明官方 T1 默认尺寸、默认深度、cell size、物理面积、
world-frame 或 eval success 语义，也不接入 production planner/gate。

显式目标坑形 residual metric 当前由
`testbed.eval.terrain_target_metrics.build_target_residual_metrics()` 单独计算。调用方必须显式传入
observed `removed_depth_grid_m`、`target_depth_grid_m`、`target_region_mask` 和 `valid_mask`；
该工具只比较 row-major depth grid，报告 target 内 positive residual、overdig、target/removed
depth sum、target completion ratio、target 外 valid cells 的 removed-depth sum，以及
`residual_depth_grid_m = target_depth_grid_m - removed_depth_grid_m`。输入长度不一致、depth
非有限或为负、mask 非有限、target mask 选中 invalid cell 时会返回具体 validation status 和
`validation_errors`，不会抛出常规规格错误，也不会静默把 invalid cell 当作 target cell。该 metric
还会在 valid target cells 内报告 threshold-free depth-error 诊断：
`target_residual_depth_rmse_m`、`target_residual_depth_mae_m` 和
`target_residual_depth_abs_max_m`。如果没有 target cell，这些字段保留为 `null`，不能解释成
零误差或成功。该 metric 还会输出 `target_shape_overlap_diagnostics`，作为 threshold-free
shape-overlap 诊断：

- `raw_target_overlap` 严格比较 valid target cells 与 valid removed-active cells
  (`removed_depth_grid_m > 0.0`) 的交并比，并报告 target 外 valid cells 的 removed-depth
  sum，作为不加容差的对照口径。
- `one_cell_dilated_target_overlap` 在调用方显式传入有效 `grid_shape` 时，用 row-major
  Chebyshev / 8-neighbor 一格膨胀 target mask，再报告 dilated target cell count、valid-cell
  count、saturation ratio、intersection / union / IoU 和 dilated target 外 removed-depth
  sum。saturation ratio 用来暴露小 grid 上膨胀 mask 是否已经覆盖大部分或全部 valid cells。
- `meter_tolerance_profiles` 固定包含 `narrow_0_30m` (`0.30m`) 和 `bucket_0_50m`
  (`0.50m`) 两个诊断 profile。当前 rollout records 没有 cell size，因此 profile 会明确标记
  `cell_size_missing`，不会推断 meter-derived IoU；只有调用方显式提供 `cell_size_m` 时才按
  `ceil(tolerance_m / cell_size_m)` 的保守规则换算 cell radius 并计算同类 overlap 字段。

这些 overlap / tolerance 字段仍是离线诊断，不提供 pass/fail、planner success、eval success、
官方 T1 默认值、protected-area band、物理体积、官方 cycle id 或 runtime gate 语义。

latest-snapshot rollout projection 当前由
`testbed.eval.terrain_target_projection.build_latest_target_residual_projection()` 组合上述两个
owner：它从显式传入的 rollout records 中读取最新可用 compact-grid `env_state` removed-depth
和 valid-mask 快照，再用显式矩形 target spec 生成 target grid，并调用
`build_target_residual_metrics()` 计算 target-shape residual。输出包含 `snapshot_row_index`、
observed / target spec grid shape、observed removed-depth grid、valid mask、`target_grid` 和
`target_residual_metrics`。没有可用 snapshot 时返回 `missing_snapshot`；target spec 或 metric
验证失败时透传对应 validation status。该 helper 只用于离线投影，不写 review artifact、不改变
`rollout_review.json` schema、不声明官方 T1 默认值，也不改变 eval success 或 production planner/gate
语义。

target-shape residual convergence 当前由
`testbed.eval.terrain_target_projection.build_target_residual_convergence_projection()` 生成。它使用同一类显式
矩形 target spec，并按 per-rollout records 中连续 `dig` 段取该段最后一个可用 compact-grid
snapshot，逐点调用 `build_target_residual_metrics()`，输出 dig-segment curve 和 summary。summary
只报告点数、起止值与 delta：target positive residual、target overdig、target removed completion
ratio、outside-target removed-depth sum，以及诊断性 trend。该 curve 是 dig-segment evidence，
不声明官方 cycle id；trend 不作为 planner success、eval pass/fail、bucket-aware tolerance 或
boundary-protected shape success 语义。

显式目标坑形 baseline report 当前由
`testbed.eval.terrain_target_report.build_explicit_target_residual_baseline_report()` 生成。它只组合
`build_latest_target_residual_projection()` 与
`build_target_residual_convergence_projection()` 的已有输出，不重新实现 target-grid 或 target
residual 公式。调用方必须显式传入 rollout records、grid shape、半开 row/col 矩形边界和 target
depth；输出包含 `target_spec`、`latest_projection`、`convergence_projection` 和从嵌套 projection
字段复制出的 `diagnostic_summary`。report `status` 仅表示诊断证据完整性：latest 与 convergence
都为 `present` 时为 `present`；两者共享同一 validation / missing status 时透传该 status；否则为
`partial` 并在 summary 中保留各 projection status。该 helper 默认不写 report artifact、不接入
`rollout_review.json` schema、不定义官方 T1 默认值，也不改变 planner、gate、eval success 或物理体积
语义。当前 run 的显式非官方 baseline packet 记录在
`docs/oracle_terrain_residual_baseline_report.md`。

shape guard shadow audit 当前由
`testbed.eval.terrain_shape_guard_shadow.build_shape_guard_shadow_audit()` 生成。它只读取
baseline report 中已有的 `latest_projection.target_residual_metrics` 和
`convergence_projection.summary` 字段，不重新实现 target-grid、residual metric、projection 或
report 公式。输出是 shadow-only review surface，包含 `low_payload_shape_guard_stop`、
`overdig_guard_stop`、`depth_budget_exhausted` 和
`outside_protected_removed_increased` 四个事件记录。每个事件只报告
`triggered`、`not_triggered`、`not_evaluated` 或 `invalid_input`，并带有证据字段和稳定
reason；top-level summary 只列出 triggered / not-evaluated event names 和 validation
errors。所有阈值和 payload/cycle-efficiency 约束都必须由调用方显式传入：target overdig max、
target positive residual max、outside-target removed-depth delta max，以及 latest/min payload
fraction。缺少显式阈值、payload 输入或 report 嵌套证据时，该事件必须是
`not_evaluated`；非法数值输入返回 `invalid_input`，不抛出常规诊断规格错误。该 helper 不推断
payload、不提供默认阈值、不写 run artifact、不接入 `rollout_review.json` schema，也不改变
production planner/gate/policy/runtime、eval pass/fail、planner success、official T1 default 或
物理体积语义。

offline discrete candidate generation 当前由
`testbed.eval.terrain_candidate_generation.build_discrete_cut_candidates()` 生成。它只读取显式
row-major `residual_depth_grid_m`、`target_region_mask`、`valid_mask` 和 `grid_shape`，从
valid target cells 中 `residual_depth_grid_m > 0.0` 的 anchor 生成离线候选。调用方必须显式传入
`direction_options`、`depth_fraction_options`、`min_candidate_count` 和 `max_candidate_count`；
候选排序固定为 row-major positive residual anchor、direction option 顺序、depth fraction option
顺序。每个候选包含 `candidate_id`、anchor cell / row / col、direction、depth fraction、
anchor positive residual depth、candidate depth 和 `offline_only=true`。`candidate_depth_m` 只等于
anchor positive residual depth 乘以 depth fraction，不推断 bucket 物理 footprint 或官方 depth cap。

该 helper 输出 `positive_residual_coverage`、candidate count、untruncated candidate count、
validation errors 和 cell size / origin / timestamp / frame transform / height/elevation /
confidence provenance status。`present` 只表示按显式选项生成了候选且数量落在显式 min/max 内；
`candidate_count_below_min`、`candidate_count_above_max`、`no_positive_residual_cells` 和
`invalid_*` 状态只用于离线诊断。该候选集不是 heuristic effect model scoring，不接
production planner，不写 run artifact，不定义官方候选数量、官方方向集、官方 depth fraction、
eval pass/fail 或 planner success 语义。缺少 cell size 时不做物理 footprint、meter-derived
tolerance、boundary 或体积推断。

offline candidate constraint evidence 当前由
`testbed.eval.terrain_candidate_evidence.build_candidate_constraint_evidence()` 标注。它读取
`build_discrete_cut_candidates()` 的候选列表，以及显式 `target_region_mask`、`valid_mask`、
`grid_shape`、`max_candidate_depth_m`、`protected_boundary_cell_radius` 和可选
`return_origin_cell_index`。该 helper 不生成新候选、不排序、不打分，只按候选输入顺序输出
`evidence_records` 和 `constraint_summary`。

每条 evidence 记录使用 row-major grid-cell proxy footprint，而不是物理 bucket footprint：
`row_forward` / `row_reverse` / `col_forward` / `col_reverse` 分别表示 anchor cell 加相邻同
row/col cell；相邻 cell 出网格时记录 `clipped_by_grid_boundary=true` 和 off-grid neighbor，
不会虚构 footprint。每条记录同时给出 target / outside-target footprint cells、valid / invalid
footprint cells、显式 Chebyshev cell-radius 保护区内外 cells、`candidate_depth_m <=
max_candidate_depth_m` 的 depth-budget evidence，以及可选的 Manhattan row-major
`return_alignment_cost_proxy`。如果没有显式 return origin，该 proxy 为 `not_evaluated`。

top-level 状态包括 `present`、`no_candidates`、`invalid_candidates`、`invalid_grid_shape`、
`invalid_grid_lengths`、`invalid_mask_values`、`invalid_depth_budget`、
`invalid_boundary_radius` 和 `invalid_return_origin`。`constraint_summary` 汇总候选数、
grid footprint proxy 名称、保护半径、保护区 cell count / saturation ratio、depth-budget 超出数、
grid-boundary clipped 数、outside-target / outside-protected candidate 数，以及 return proxy
min/max。所有 budget、boundary radius 和 return origin 都是调用方显式输入；该 helper 不定义官方
depth budget、boundary tolerance、bucket footprint、physical volume、cell-size inference、top-k、
pass/fail、eval success 或 production planner 语义。

offline heuristic candidate scoring 当前由
`testbed.eval.terrain_candidate_scoring.build_candidate_heuristic_scores()` 生成。它只读取
`build_candidate_constraint_evidence()` 输出的 `evidence_records` 和调用方显式传入的 `weights`。
必需权重 key 为 `candidate_depth_reward`、`target_footprint_cell_reward`、
`outside_target_footprint_cell_penalty`、`outside_protected_boundary_cell_penalty`、
`depth_budget_exceeded_penalty`、`grid_boundary_clipped_penalty` 和
`return_alignment_distance_penalty`。这些权重只属于本次离线诊断调用；repo 不定义默认权重或官方权重。

score record 按 evidence 输入顺序保留。每条记录输出 candidate depth reward、target footprint
reward、outside-target penalty、outside-protected penalty、depth-budget exceeded penalty、
grid-boundary clipped penalty 和 return-alignment distance penalty 的组件值，并把组件求和成
`total_score`。return proxy 缺失时该组件为 `not_evaluated` 且贡献 `0.0`，不会推断 return cost。
`ranking` 只按 total score 降序、再按原输入顺序给出 deterministic diagnostic ranking；它不包含
selected/top-k/action 字段，也不接入 production planner。top-level 状态包括 `present`、
`no_evidence_records`、`invalid_evidence_records` 和 `invalid_weights`，并保留 calibrated effect
model、payload model、physical bucket footprint、cell size 和 official weight 的 missing provenance。
该 helper 是 heuristic score evidence，不是 calibrated effect/capability model，不写 run artifact，不改变
`rollout_review.json` schema，不定义 pass/fail、eval success、planner success、official candidate
defaults 或 production behavior。

offline geometric swept-footprint effect evidence 当前由
`testbed.eval.terrain_candidate_effect_model.build_geometric_swept_footprint_effect()` 生成。它读取单个
offline candidate、显式 `removed_depth_grid_m`、`target_depth_grid_m`、`target_region_mask`、
`valid_mask`、`grid_shape`、`cell_size_m`、`bucket_width_m`、`bucket_length_m`，以及可选
`penetration_depth_m`。所有几何量都必须由调用方显式传入；当前 run 记录缺少 cell size 和
bucket geometry 时不得推断。

该 helper 的 footprint model 明确命名为
`centerline_rectangular_swept_footprint_approximation`，不是 calibrated bucket physics。它把 anchor
cell center 作为起点，按 `row_forward` / `row_reverse` / `col_forward` / `col_reverse` 的 row-major
方向，用 `cell_size_m` 将 cell center 距离转换成米；valid cell center 在 `[0, bucket_length_m]`
的前向区间内且横向距离不超过 `bucket_width_m / 2` 时进入 footprint。若请求的中心线矩形范围越过
grid 边界，则记录 `footprint_clipped_by_grid_boundary=true`，但不虚构 grid 外 cell。

expected delta patch 是 row-major `expected_delta_depth_grid_m`，footprint cell 上的 delta 等于
`penetration_depth_m`；缺少显式 penetration 时使用 candidate 的 `candidate_depth_m`，并把来源记录为
`candidate_depth_m`。输出使用 `cell_size_m ** 2` 计算
`expected_removed_volume_m3`、`target_removed_volume_m3`、`outside_target_removed_volume_m3` 和
`overdig_volume_delta_m3`，同时保留 depth-sum 口径。overdig delta 只比较 expected removal 前后相对
`target_depth_grid_m` 的 overdig 变化。top-level 状态包括 `present`、`invalid_candidate`、
`invalid_grid_shape`、`invalid_grid_lengths`、`invalid_mask_values`、`invalid_depth_values`、
`invalid_geometry` 和 `no_valid_footprint_cells`。该 helper 是 offline effect evidence，不接
production planner，不写 run artifact，不定义官方 cell size、bucket geometry、penetration depth、
payload proxy、calibrated effect/capability model、top-k、pass/fail、eval success 或 planner success
语义。

offline entry/exit swept-footprint effect evidence 的公共入口为
`testbed.eval.terrain_candidate_effect_model.build_entry_exit_swept_footprint_effect()`；具体实现放在 focused
owner `testbed.eval.terrain_candidate_entry_exit_effect`，避免把 entry/exit 线段算法继续堆入几何
effect facade。它读取单个
offline candidate、显式 `removed_depth_grid_m`、`target_depth_grid_m`、`target_region_mask`、
`valid_mask`、`grid_shape`、`cell_size_m`、`bucket_width_m`、`entry_cell_index`、
`exit_cell_index` 和 `target_penetration_depth_m`。entry / exit cell 必须是 row-major grid 内的
valid cell，且两者不能相同；这些入口、出口、宽度和 penetration 都是调用方输入，不从 current run
或配置推断。

该 helper 的 path model 明确命名为 `entry_exit_centerline_segment_approximation`，不是 calibrated
bucket physics。candidate direction 会作为 evidence 保留，但 swept centerline 使用显式 entry cell
center 到 exit cell center 的线段；cell center 在线段投影范围内且到线段的垂直距离不超过
`bucket_width_m / 2` 时进入 footprint。输出包含 `entry_exit_path`、target / outside-target /
valid / invalid footprint cells、row-major `expected_delta_depth_grid_m`、以及与 Phase 4A 相同口径的
expected / target / outside-target / overdig depth-sum 和 volume summary。top-level 状态包括
`present`、`invalid_candidate`、`invalid_grid_shape`、`invalid_grid_lengths`、
`invalid_mask_values`、`invalid_depth_values`、`invalid_geometry`、`invalid_entry_exit` 和
`no_valid_footprint_cells`。该 helper 只提供 offline entry/exit expected-delta evidence；它不定义
entry/exit default、official geometry、ACT capability、action selection、top-k、pass/fail、eval
success、planner success 或 production planner/gate/policy/runtime 语义。

offline candidate effect summary / payload proxy evidence 当前由
`testbed.eval.terrain_candidate_effect_summary.build_candidate_effect_summary()` 生成。它只读取 Phase 4A
effect records 和调用方显式传入的 `payload_capacity_m3`；该 capacity 是本次离线诊断输入，不写入
config，不作为官方 bucket payload、bucket geometry、material density 或 fill model 默认值。

summary record 按 effect record 输入顺序保留，包含 candidate id、effect status、expected removed
volume、target removed volume、outside-target removed volume、overdig volume delta、footprint cell
count、grid-boundary clipped flag、`payload_proxy_volume_m3 = min(expected_removed_volume_m3,
payload_capacity_m3)` 和 `payload_proxy_fraction`。当 expected removed volume 大于 0 时，还报告
outside-target volume fraction 和 overdig volume fraction；分母为 0 时这些 fraction 为 `None`，不虚构
比值。aggregate summary 汇总 payload proxy volume/fraction 的 min/max/mean、expected / target /
outside-target / overdig volume totals，以及 max payload proxy、max outside-target volume 和 max
overdig volume 的诊断 candidate id。

`diagnostic_rankings` 只提供 evidence-only 排序：payload proxy volume 降序、outside-target volume
降序、overdig volume 降序，tie-break 使用原输入顺序。该 ranking 不包含 selected/top-k/action 字段，
不接 production planner。top-level 状态包括 `present`、`no_effect_records`、
`invalid_effect_records` 和 `invalid_payload_capacity`，并保留 calibrated payload model、material
density、cycle time、bucket fill model 和 production integration 的 missing / not-integrated provenance。
该 helper 不定义 payload/capacity default、material density、cycle-time semantics、pass/fail、eval
success、planner success、top-k action selection 或 calibrated effect/capability model。

gold-sample calibration inventory / schema evidence 当前由
`testbed.eval.terrain_calibration_inventory.build_gold_sample_calibration_inventory()` 生成。它是
offline-only inventory helper，不训练 calibrated effect model，也不训练 capability model。调用方必须显式传入
`source_paths`、`required_fields` 和 `episode_split_key_candidates`；repo 不定义官方 gold-sample schema、
官方 required fields、官方 split keys、label 语义、payload capacity 或 material-density 默认值。

该 helper 只检查调用方给出的显式文件或目录；目录会在该显式 root 下递归枚举文件，不扫描整个 repo 或整个
`runs`。当前支持 JSONL object records 和 JSON list-of-object records；JSON metadata dict 会作为
metadata document 报告，但不会被当作 calibration records；不支持的文件后缀会计入 unsupported source，
解析错误保留在 source-level `parser_errors`，不会让整个 inventory 失败。一个 usable calibration record
必须同时包含全部显式 `required_fields`，并至少包含一个显式 split-key candidate。

输出包含 source/support/record/usable record counts、per-source summaries、required-field presence /
missing counts、split-key detection / distinct group counts、validation errors 和 missing provenance。top-level
状态包括 `present`、`no_sources`、`invalid_source_paths`、`invalid_required_fields`、
`invalid_split_keys` 和 `no_supported_sources`。如果支持源能解析但没有 usable records，状态仍为
`present`，并用 `usable_record_count=0`、missing-field counts 和 split evidence 暴露 gap。该 helper
不拟合模型、不虚构 labels、不声明 pass/fail、eval success、planner success、episode split 官方语义或
production integration。

同一 inventory 输出还包含 `observed_field_catalog` 和 `schema_gap_summary`。`observed_field_catalog`
只统计支持源中 JSON/JSONL object record 的原始 top-level field presence counts，并按 field 名稳定排序；
metadata document、unsupported source 和 parser error 不会被解释成 calibration schema。`schema_gap_summary`
只基于调用方显式传入的 `required_fields` 与 `episode_split_key_candidates` 汇总 gap：哪些 required
fields 在全部 records 中缺失、部分存在或全部存在，哪些 split-key candidates 出现或完全缺失，以及
这些事实对 `usable_record_count` 的影响。该 catalog/gap summary 不做 alias inference，不把 `label`、
`source_id`、`mass_in_bucket_kg` 或其他 telemetry field 自动映射成 success、payload 或 episode split 语义；
如需语义映射，必须在后续切片用显式 schema 决策单独定义。

explicit calibration record extraction / mapping feasibility evidence 当前由
`testbed.eval.terrain_calibration_extraction.build_explicit_calibration_record_extraction()` 生成。
它是 offline-only extraction helper，不训练 calibrated effect model，也不定义官方样本 schema。调用方必须显式传入
`source_paths`、`field_mapping`、`required_output_fields` 和
`episode_split_key_candidates`。`field_mapping` 是 caller-provided explicit raw-field mapping：
输出字段名指向原始 observed field 名；helper 只按这份 mapping 抽取字段，不做 alias inference，不把
`label`、`source_id`、`mass_in_bucket_kg`、`excavated_mass_kg` 或其他 telemetry fields 自动解释为
success、payload、split key、pass/fail、eval success 或 planner success。

该 helper 使用与 inventory 相同的显式 source-path 边界：只检查调用方给出的文件或目录，目录只在该显式 root
下递归枚举文件，不扫描整个 repo 或整个 `runs`。当前支持 JSONL object records 和 JSON list-of-object
records；JSON metadata dict 会作为 metadata document 报告，不作为 extracted records；unsupported source
和 parser error 都保留为 source-level facts。输出包含 mapping summary、extracted record count、
usable extracted record count、missing output-field summary、split summary、bounded sample record shape evidence、
validation errors 和 missing provenance。一个 usable extracted record 必须同时包含全部显式
`required_output_fields`，并至少包含一个显式 split-key candidate。top-level 状态包括 `present`、
`no_sources`、`invalid_source_paths`、`invalid_field_mapping`、`invalid_required_output_fields`、
`invalid_split_keys`、`no_supported_sources` 和 `no_records`。如果后续需要把 provisional telemetry mapping
提升为 calibration schema，必须单独确认字段语义、label 语义、split 语义和 compatibility policy。

depth 诊断必须区分三种口径：

- `depth_tracking.dig_local_surface`：正式 command-depth 跟手口径，来自 jsonl 连续
  `dig` 段的 `env_state[31] bucket_depth_below_local_surface_m` 峰值，目标来自
  `dig_cut_tokens[7] * 0.8`。
- `depth_tracking.summary_plane_depth` / `planned_actual_cycles.depth_peak_m`：历史
  summary plane-depth 诊断，来自 `env_state[8] bucket_depth_below_dig_area_plane_m`，
  且窗口可覆盖 `qds -> dump_end`，不能直接当作 command-depth 跟手结论。
- `depth_tracking.expert_p95_overshoot`：相对专家 p95 的超出量，用于判断是否离开专家
  支持范围，不等同于 target depth error。

handoff 诊断优先读取 per-rollout jsonl 中已完成的 `return -> dig`
transition。已经 terminal-stop 后停在 `return` 的不完整段会记录为 ignored，并保留
原始 summary snapshot，避免把终止后的残留 return 帧误判成真实 handoff 失败。

`3cycle_smoke` 用于快速冒烟；`15cycle_probe` / `30cycle_probe` 是 probe，不应直接写成已经完成稳定长程闭环。

## 9. 清理与保留

训练产物通常只长期保留：

- best checkpoint
- resolved config / metadata
- train log summary
- Gate / audit / rollout review 证据
- 必要视频或 contact sheet 索引

可用清理工具：

```bash
tb-cleanup-training-artifacts --ckpt-dir <ckpt_dir> --delete
```

如果正在排查训练过程，不要急着清理中间 checkpoint；必要时使用 `--no-cleanup-after-train`。

## 10. 历史基线说明

旧 V1 / V2.1 文档里关于 `act_agx_v1`、9D `env_state`、`episode_len=1000`、`qpos only`、`dump_complete_final_hold`、`success_rate=100%` 等内容，只能用于解释当时实验，不再代表当前系统状态。

如果需要复现旧结果，应把它标为 legacy experiment，并同时记录当前代码是否仍支持对应 config。不要把旧成功结论迁移到 V2.4.5 spatial-mass / qc6 / depth-profile 训练上。
