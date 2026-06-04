# Primitive Scheduler Service Refactor Plan

本文档记录 primitive scheduler 拆分为 thin state machine shell 与 focused services 的总体方案。当前阶段只做 behavior-preserving extraction，不引入新的调度语义。

## 目标边界

`PrimitivePlannerACTPolicy` 保留为 public facade。它负责 active skill、transition reason、scheduler lifecycle、service 调用顺序、`_set_skill()`、policy dispatch 和 reset timing。

领域 service 负责稳定能力边界内的事实提取和 gate 判断，例如 return-to-dig handoff、dump lifecycle、dig lifecycle、coverage targeting、dig-start alignment。service 不接收 planner `self`，不调用 `_set_skill()`，不 reset policy，不写 HDF5，不加载 checkpoint，也不复制 token 或 schema source of truth。

## Source Of Truth

schema index 只从 `testbed.data.schema` 读取。primitive token dimension、token order 和 contract string 只从 `testbed.contracts.primitive_tokens` 读取。boundary profile name 由 boundary detector 配置或后续 canonical registry 提供。

新增模块只能引用这些 source of truth，不能在 service 内复制 index、token order、profile 字符串或默认 contract 语义。

## 迁移顺序

1. 建立最小 `PlannerSnapshot`、primitive decision contract 和 golden trace 行为锁。
2. 抽出 `ReturnToDigHandoffGateService`，保留旧 return 分支顺序和旧 reason 字符串。
3. 抽出 dump lifecycle，保留 carry/dump/dump_release/return threshold 与事件顺序。
4. 抽出 dig lifecycle 和 failed dig recovery，先迁 facts，再迁 decision。
5. 逐步拆 `DigCoverageMixin` 为 coverage candidate、scoring、target selection、progress。
6. 抽出 dig-start alignment，先锁 scripted action 数值，再迁 decision。
7. 抽出 debug/trace builder，保持 debug schema 不变。
8. ACT commitment 先 shadow 记录，不默认拦截 switch。
9. option scheduler 只作为 experimental mode，在同一 public facade 下接入。

## Phase 1 范围

新增模块：

- `testbed/planner/snapshots.py`
- `testbed/planner/primitive_decisions.py`
- `testbed/planner/return_handoff.py`

planner 大文件只增加薄 facade：

- `_make_snapshot()`
- `_return_to_dig_handoff_context()`
- `_evaluate_return_to_dig_handoff()`

旧 private method 名称继续保留，并转调 service：

- `_return_to_dig_entry_close()`
- `_return_to_dig_handoff_ready()`
- `_return_to_dig_direct_handoff_ready()`
- `_return_to_dig_start_envelope_ready()`
- `_return_to_dig_shallow_guard_ready()`

本阶段不改 threshold、不改 branch order、不改默认 config、不改 switch reason、不改 policy reset 语义、不改 debug/summary schema。

## 测试锁定规则

Phase 1 必须覆盖：

- return handoff service unit tests：entry-close、non-finite fallback、start-envelope ready/fail/missing-token fallback、direct handoff、shallow guard。
- golden trace：active skill trace、switch reason trace、completed transition count、policy reset count。
- legacy planner tests：return-to-dig、direct handoff、same-frame dump/carry -> dig、return -> pre_dig_align 的旧 reason 字符串。
- debug schema：keys、types、ordering 保持不变。

验证命令：

```bash
pytest tests/test_return_handoff_service.py tests/test_return_start_envelope.py tests/test_planner_golden_traces.py tests/test_primitive_planner_debug_schema.py
pytest tests/test_agx_primitives_v2_2.py -k "return_to_dig or direct_handoff or shallow_guard or pre_dig_align or spatial_mass_boundary"
```

## 回滚策略

Phase 1 的旧 private method 均保留为 facade。如果 service extraction 发现行为漂移，可以让 facade 临时回到旧实现，同时保留新增 service unit tests 和 golden trace 作为后续迁移的行为锁。
