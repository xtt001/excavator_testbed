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

当前记录没有 cell size、origin、timestamp、frame transform、height/elevation grid 或
confidence grid，报告必须把这些字段标为 `missing`，不能从现有 jsonl 推断。该 residual
块和 convergence curve 都是离线诊断和 baseline 投影，不改变 planner、gate、checkpoint、
token 或 eval success 语义。由于 cell size 仍缺失，positive residual、overdig、
target/removed 仍是 depth sum，不是物理体积。

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
