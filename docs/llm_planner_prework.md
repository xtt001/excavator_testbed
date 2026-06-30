# 引入 LLM Goal Planner 前收尾清单

状态：草案

目标：确认当前问题是否真的来自 goal 决策，再决定 LLM 是否接管 candidate ranking。

## 1. 检查类型命名

- `data QC`：训练前检查数据质量，包括 raw/VDS/materialized copy、字段、mask、primitive 边界和 reject 统计。
- `policy audit`：训练后、eval 前检查 checkpoint 离线行为，确认 policy 在 recorded stream 上是否已经不跟 token/不跟专家。
- `rollout review`：eval 后检查真实闭环表现，包括 planned vs actual、handoff、coverage trace 和 terminal reason。
- `root-cause audit`：rollout review 发现明确症状后触发，用于定位问题来自 policy、token 语义、handoff、live scaling 还是 planner belief。

## 2. 需要补强的位置

- 保留现有训练前 `data QC`：`gate1` primitive VDS numeric QC、`gate2` boundary review、`gate1b` materialized-copy QC。
- 新增或规范 `policy audit`：训练完成后先跑离线 checkpoint 审计，再进入正式 eval。
- 新增或规范 `rollout review`：qc6 `3/10/15-cycle` eval 后统一检查每铲 planned entry/exit/depth/payload vs actual execution。
- `rollout review` 重点看：entry/exit 是否落在 expert prior 支持范围，depth 是否达到 intent，payload/deposit 是否与目标一致。
- `rollout review` 同时检查 `return -> dig` handoff：entry-close、envelope、contact、plane/local depth 是否同步 ready。
- `rollout review` 必须复查 `coverage_decision_trace`：select、reject、depleted、reopen、terminal stop 是否可解释。
- 触发式 `root-cause audit`：dig 浅挖跑 `tb-audit-dig-ckpt` / `tb-audit-dig-depth-semantics`；return 问题跑 `tb-audit-return-ckpt`。
- coverage 选择或 depleted 不合理：优先复查 `coverage_decision_trace`、remaining depth、attempt/low-productivity 记录。
- 若 `policy audit` 正常但 live 异常，再查 live observation/action scaling、handoff gate、temporal aggregation。

## 3. Planner 结构整理

- 给 `PrimitivePlannerACTPolicy` 做职责 map：scheduler、coverage、return handoff、token builder、debug summary。
- 新 planner 语义必须进小模块；大文件只保留 facade / adapter / pass-through。

## 4. 回查既有 10-cycle checkpoint

- 用新增 `rollout review` 回查既有 `10-cycle smooth` checkpoint：确认连续跑通是否真的等于 entry/exit/depth/payload 跟手。
