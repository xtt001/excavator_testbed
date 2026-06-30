# 引入 LLM Goal Planner 前证据门禁

状态：2026-06-30 已落地首版诊断工具

目标：先确认当前问题是否真的来自 goal / candidate ranking，再决定 LLM 是否接管 planner 决策。本阶段不接入 LLM、VLM、BehaviorTree 或新 planner backend，也不改变 `PrimitivePlannerACTPolicy`、checkpoint contract 或 eval success 计算。

## 1. 检查类型命名

- `data QC`：训练前检查数据质量，包括 raw/VDS/materialized copy、字段、mask、primitive 边界和 reject 统计。
- `policy audit`：训练后、eval 前检查 checkpoint 离线行为，确认 policy 在 recorded stream 上是否已经不跟 token/不跟专家。
- `policy audit manifest`：把已有离线 audit JSON 汇总为 eval 前证据清单，缺失项只能标为 `missing`，不能伪造通过。
- `rollout review`：eval 后检查真实闭环表现，包括 planned vs actual、handoff、coverage trace 和 terminal reason。
- `root-cause audit`：rollout review 发现明确症状后触发，用于定位问题来自 policy、token 语义、handoff、live scaling 还是 planner belief。

## 2. Eval 前 policy audit manifest

先跑已有 audit 工具，保存 JSON：

```bash
AUDIT_DIR=runs/audit/<run_id>

tb-audit-dig-ckpt \
  --config testbed/configs/<dig_act_config>.yaml \
  --ckpt <dig_checkpoint> \
  --output "${AUDIT_DIR}/dig_ckpt_audit.json"

tb-audit-dig-depth-semantics \
  --dataset-dir <dig_dataset_dir> \
  --output "${AUDIT_DIR}/dig_depth_semantics_audit.json"

tb-audit-return-ckpt \
  --config testbed/configs/<return_act_config>.yaml \
  --ckpt <return_checkpoint> \
  --output "${AUDIT_DIR}/return_ckpt_audit.json"
```

`tb-audit-return-ckpt` 支持包含 `return_start_envelope_tokens_v1` 的 return checkpoint；如果当前 return policy 还包含 `return_relocate_tokens_v1`，audit 会按数据加载合同从 `return_target_tokens` 派生该 token。当前变体分析仍聚焦 return-start envelope，return-relocate token 作为 recorded-stream 输入参与离线推理。

再生成 eval 前清单：

```bash
tb-policy-audit-manifest \
  --output "${AUDIT_DIR}/policy_audit_manifest.json" \
  --dig-ckpt-audit "${AUDIT_DIR}/dig_ckpt_audit.json" \
  --dig-depth-audit "${AUDIT_DIR}/dig_depth_semantics_audit.json" \
  --return-ckpt-audit "${AUDIT_DIR}/return_ckpt_audit.json"
```

输出字段包括 `schema_version`、`overall_status`、`eval_ready`、`evidence_gaps`、`audits`、`next_steps`。缺少某类 audit 或 schema 不匹配时，`overall_status=missing_or_invalid_policy_audit`，应先补证据或解释豁免，再进入正式 rollout eval。

## 3. Eval 后 rollout review

`rollout review` 是诊断报告，不改变 eval success 语义。默认读取 eval `results_dir` 下的 `rollout_manifest.json`、per-rollout summary、planner trace，并输出：

```bash
tb-rollout-review --results-dir <eval_results_dir>
```

默认产物为：

```text
<eval_results_dir>/rollout_review.json
```

也可以显式指定输出路径：

```bash
tb-rollout-review \
  --results-dir <eval_results_dir> \
  --output <eval_results_dir>/rollout_review.json
```

输出字段包括 `schema_version`、`source_results_dir`、`overall_status`、`evidence_gaps`、`rollout_reviews`、`root_cause_hints`、`llm_candidate_ranking_ready`。

每个 rollout 至少复查：

- planned vs actual：entry、exit、dig depth、payload/deposit。
- `return -> dig` handoff readiness：entry-close、entry error、允许最大 entry error。
- coverage evidence：`coverage_decision_trace` 是否存在，terminal stop / depleted / reject 是否可解释。
- terminal reason：是否只是 target-cycle gate 触发，而不是证明每铲都跟手。
- quality flags：low deposited fraction、quality issue、浅挖、dig area escape 等。

## 4. Root-cause 触发规则

- `policy_audit_manifest.json` 不 ready：先补已有 audit JSON，不进入 rollout 结论。
- `rollout_review.json` 出现 `needs_root_cause_audit`：不要直接归因 LLM，先按症状查 policy、token、handoff、live scaling 或 planner belief。
- `rollout_review.json` 出现 `insufficient_evidence`：先补 summary、handoff 字段或 coverage trace，再讨论 candidate ranking。
- 只有在 policy audit 干净、rollout quality 干净，并且 coverage trace 指向 candidate ranking / depleted / terminal-stop 问题时，`llm_candidate_ranking_ready` 才可能为 true。

## 5. 既有 10-cycle 回查

用首版工具回查既有 10-cycle artifact：

```bash
tb-rollout-review \
  --results-dir runs/eval/yulong_v2_4_hindsight_goal_10cycle_20260520/results
```

该产物虽然 `success_rate=1.0`，但回查必须能暴露质量证据不足或不干净，例如 `quality_issue_count`、low deposited fraction、空缺的 `coverage_decision_trace`。结论应写成：

```text
10-cycle smooth / success=1.0 不能单独证明 entry、exit、depth、payload 跟手。
```

## 6. Planner 结构边界

- 给 `PrimitivePlannerACTPolicy` 做职责 map：scheduler、coverage、return handoff、token builder、debug summary。
- 新 planner 语义必须进小模块；大文件只保留 facade / adapter / pass-through。
- 本阶段新增的是证据门禁和报告产物，不改变 planner backend、不调整 threshold、不改 success 计算。
