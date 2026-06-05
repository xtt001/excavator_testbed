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

## Dump Lifecycle Gate Slice

新增模块：

- `testbed/planner/dump_lifecycle.py`

`DumpLifecycleGateService` 负责纯 gate 判断：4P `dump_ready`、
dump-area relative position / near-window helper、`dump_done`、
`carry_release_safety_done`，以及 5P `approach_ready`。service 只接收显式
`DumpLifecycleFacts` 和 `DumpLifecycleConfig`，不接收 planner `self`，不调用
`_set_skill()`，不更新 hold counter，不 reset policy，不完成 coverage，不决定
return direct handoff。

planner 大文件只保留薄 facade 和 facts/config 装配：

- `_dump_lifecycle_config()`
- `_dump_lifecycle_facts()`
- `_dump_ready()`
- `_dump_area_relative_dump_position_ok()`
- `_dump_area_relative_near_window_ok()`
- `_optional_range_ok()`
- `_optional_range_near_ok()`
- `_dump_ready_position_ok()`
- `_dump_done()`
- `_carry_release_safety_done()`
- 5P `_approach_ready()`

本切片保留 carry/dump/dump_release/return 的 branch order、threshold、hold
counter、switch reason、coverage completion reason、policy reset timing 和 debug
schema。semantic profile 下 legacy `_dump_ready()` / `_dump_done()` fallback 仍由
planner shell 的原有分支控制，service 不提升实验语义为默认行为。

## Dig Lifecycle Gate Slice

新增模块：

- `testbed/planner/dig_lifecycle.py`

`DigLifecycleGateService` 负责纯 gate/progress 判断：dig progress 的
step/best-mass/plateau/payload-gain 更新、`dig_bad_replan` readiness、
`dig_exit_guard` overshoot readiness、`dig_complete` low-payload guard，以及
legacy / semantic `dig -> carry` readiness reason。service 只接收显式
`DigLifecycleFacts` 和 `DigLifecycleConfig`，不接收 planner `self`，不调用
`_set_skill()`，不 reject/complete coverage，不选择 pre-dig-align，不请求 terminal
stop，不 reset policy，也不写 planner trace。

planner 大文件只保留薄 facade 和 facts/config 装配：

- `_dig_lifecycle_config()`
- `_dig_lifecycle_facts()`
- `_update_dig_progress()`
- `_dig_bad_replan_ready()`
- `_dig_exit_guard_ready()`
- `_dig_exit_overshoot_m()`
- `_dig_to_carry_ready()`
- `_semantic_dig_to_carry_liveness_ready()`
- `_dig_complete_boundary_low_payload()`

本切片保留 dig 分支顺序：
`exit_guard -> bad_replan -> complete_low_payload -> carry`。coverage reject、
cell-entry/coverage dig completion、failed-dig stop/retry/pre-dig-align 选择、
switch reason 拼接、policy reset timing 和 debug schema 仍由 planner shell 控制。

## Dig-Start Alignment Numeric Slice

新增模块：

- `testbed/planner/dig_start_alignment.py`

`DigStartAlignmentService` 负责 pre-dig alignment 的纯数值 helper：从
`dig_cut_tokens` 计算 target qpos、应用 qpos min/max、bucket target、
controlled-dim / entry-intent mask，并生成 PD servo action。`pd_servo_action`
是该数值计算的 source of truth；planner 中的 `_pd_servo_action()` 只保留为旧
private facade。

planner 大文件只保留薄 facade 和状态写回：

- `_dig_start_alignment_config()`
- `_pre_dig_align_target_from_token()`
- `_pre_dig_align_action()`
- `_pd_servo_action()`

本切片不迁 pre-dig-align readiness decision，不改 surface guard、start envelope、
entry-close handoff、entry-intent handoff、timeout handoff、hold counter、coverage
reject/replan、switch reason、policy reset timing 或 debug schema。

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
pytest tests/test_dump_lifecycle_service.py tests/test_planner_golden_traces.py tests/test_primitive_planner_debug_schema.py tests/test_agx_primitives_v2_2.py -k "dump_ready or dump_done or dump_end or dump_release or approach_dump or release_safety or near_window or dump_area_relative or carry_to_dump or dump_to_return"
pytest tests/test_dig_lifecycle_service.py tests/test_agx_primitives_v2_2.py -k "dig_bad_replan or exit_guard or failed_dig or dig_complete or pre_dig_align or dig_to_carry"
pytest tests/test_dig_start_alignment_service.py tests/test_agx_primitives_v2_2.py -k "pre_dig_align"
```

## 回滚策略

Phase 1、dump lifecycle gate slice、dig lifecycle gate slice 和 dig-start
alignment numeric slice 的旧 private method 均保留为 facade。如果 service extraction
发现行为漂移，可以让 facade 临时回到旧实现，同时保留新增 service unit tests 和
golden trace 作为后续迁移的行为锁。
