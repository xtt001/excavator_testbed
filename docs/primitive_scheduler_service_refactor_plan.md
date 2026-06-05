# Primitive Scheduler Service Refactor Plan

本文档记录 primitive scheduler 拆分为 thin state machine shell 与 focused services 的总体方案。当前阶段只做 behavior-preserving extraction，不引入新的调度语义。

## 目标边界

`PrimitivePlannerACTPolicy` 保留为 public facade。它负责 active skill、transition reason、scheduler lifecycle、service 调用顺序、`_set_skill()`、policy dispatch 和 reset timing。

领域 service 负责稳定能力边界内的事实提取和 gate 判断，例如 return-to-dig handoff、dump lifecycle、dig lifecycle、coverage targeting、dig-start alignment。service 不接收 planner `self`，不调用 `_set_skill()`，不 reset policy，不写 HDF5，不加载 checkpoint，也不复制 token 或 schema source of truth。

## Source Of Truth

schema index 只从 `testbed.data.schema` 读取。primitive token dimension、token
order、contract version 和 contract string 只从 `testbed.contracts.primitive_tokens`
读取。low-dim observation key 名称从 `testbed.contracts.low_dim` 和
`testbed.contracts.primitive_tokens` 读取。boundary profile name 由 boundary
detector 配置或后续 canonical registry 提供。

新增模块只能引用这些 source of truth，不能在 service 内复制 index、token order、profile 字符串或默认 contract 语义。

## 迁移顺序

1. 建立最小 `PlannerSnapshot`、primitive decision contract 和 golden trace 行为锁。
2. 抽出 `ReturnToDigHandoffGateService`，保留旧 return 分支顺序和旧 reason 字符串。
3. 抽出 dump lifecycle，保留 carry/dump/dump_release/return threshold 与事件顺序。
4. 抽出 dig lifecycle 和 failed dig recovery，先迁 facts，再迁 decision。
5. 逐步拆 `DigCoverageMixin` 为 coverage candidate、scoring、target selection、progress。
6. 抽出 dig-start alignment，先锁 scripted action 数值，再迁 decision。
7. 抽出 debug/trace builder，保持 debug schema 不变。
8. 抽出 policy observation assembly，保持 token 生成和 policy dispatch 不变。
9. ACT commitment 先 shadow 记录，不默认拦截 switch。
10. option scheduler 只作为 experimental mode，在同一 public facade 下接入。

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

## Dig-Start Alignment Readiness Slice

`DigStartAlignmentService` 继续负责 pre-dig alignment 的纯 readiness checks：
surface-guard trigger/can-handoff、entry-close threshold、start-envelope qpos/pose
gate、first-dig entry-close handoff、entry-intent mode/handoff、timeout handoff
reason，以及 ready sample 对 hold count 的建议更新。service 只接收显式
`DigStartAlignmentFacts` 和 `DigStartAlignmentConfig`，不调用
`_ensure_dig_cut_plan_for_cycle()`，不写 planner debug 字段，不更新 counter，不
reject/complete coverage，不选择下一 skill。

planner 大文件只保留薄 facade 和状态写回：

- `_dig_start_alignment_facts()`
- `_pre_dig_align_surface_guard_triggered_for_state()`
- `_pre_dig_align_surface_guard_can_handoff()`
- `_pre_dig_align_ready()`
- `_pre_dig_align_entry_close()`
- `_pre_dig_align_entry_close_handoff_ready_for_state()`
- `_pre_dig_align_entry_intent_mode_enabled()`
- `_pre_dig_align_entry_intent_handoff_ready_for_state()`
- `_pre_dig_align_timeout_can_handoff()`
- `_pre_dig_align_start_envelope_ready_for_state()`

本切片仍保留 `_maybe_switch_skill()` 的 pre-dig-align 分支顺序、surface/timeout/
completed/replan counters、hold counter 写回、coverage reject/replan、token rebuild、
switch reason、policy reset timing 和 debug schema 在 planner shell。

## Coverage Service Package Status

`testbed/planner/dig_coverage/` 已作为 dig coverage / corridor planning 的
service package。`CoverageService` 组合 candidate 构造、raw-field 组装、selection
scoring 和 progress/depletion 更新；`DigCoverageMixin` 作为
`PrimitivePlannerACTPolicy` 的 compatibility facade，保留旧 `_coverage_*`
private entry points 和旧 state/debug property names。

该 package 已符合本计划第 5 步的主要方向：service owns coverage candidate、
scoring、target selection、progress；planner shell 仍负责何时 reject/complete
coverage、何时 `_set_skill()`、何时 reset policy，以及 rollout/debug/trace 的最终
编排。后续 coverage 迁移应继续保持 behavior-preserving，不改 candidate layout、
score weight、attempt/depletion、multi-pass、state exemplar 或 trace schema。

## Scripted Bootstrap Compatibility Slice

新增模块：

- `testbed/planner/bootstrap.py`

`BootstrapService` 只负责 legacy/diagnostic bootstrap compatibility 的纯判断和
动作数值：`scripted_qpos` 是否启用、scripted target/qvel hold gate、scripted
timeout end gate、learned bootstrap 的 `first_qualified_dig_start` /
`loaded_and_clear` end gate，以及 scripted qpos PD action。service 只接收显式
`BootstrapFacts` 和 `BootstrapConfig`，不接收 planner `self`，不调用
`_set_skill()`，不 reset policy，不写 debug schema，不决定下一 skill。

planner 大文件只保留薄 facade 和状态写回：

- `_bootstrap_config()`
- `_bootstrap_facts()`
- `_should_end_bootstrap()`
- `_scripted_bootstrap_enabled()`
- `_scripted_bootstrap_target_reached()`
- `_scripted_bootstrap_action()`

本切片不提升 bootstrap 为 mainline 语义。bootstrap 仍按既有文档作为 legacy smoke /
diagnostic / learned first-handoff compatibility layer；planner shell 继续负责
bootstrap branch order、`bootstrap_to_*` switch reason、scripted step/hold/timeout
counters、active policy dispatch、policy reset timing 和 debug schema。

## Debug / Trace Builder Slice

`testbed.planner.primitive_debug` 负责 primitive planner 的 debug-state、
rollout-summary 和 planner-trace payload builder。`PrimitivePlannerACTPolicy`
中的 `debug_state()`、`rollout_summary()` 和 `planner_trace()` 只保留为 public
facade，转调对应 builder。

本切片只移动 schema/payload 构造位置，不改变 key、key order、字段类型、默认值、
token contract string、coverage decision trace payload、rollout JSONL 消费语义、
planner 分支顺序、switch reason、counter、policy reset timing 或 active policy
dispatch。

## Return Start-Envelope Builder Slice

`testbed.planner.return_start_envelope` 继续作为 return start-envelope token 和
handoff gate 的 source-of-truth。本切片新增
`ReturnStartEnvelopeBuildRequest` 和 `build_return_start_envelope_for_plan()`，
负责把 cell/global prior fallback、live-current-observation fallback、relocate
qpos/spatial conditioning、source string 和 prior-bounds usage flags 组合成一个
`ReturnStartEnvelopeState`。

planner 大文件只保留旧 private facade：

- `_build_return_start_envelope_tokens_for_obs()`
- `_maybe_condition_return_start_envelope_qpos_from_relocate()`
- `_return_start_envelope_prior_token()`
- `_return_start_envelope_prior_mapping()`
- `_return_start_envelope_prior_bounds()`
- `_return_start_envelope_token_from_prior_mapping()`

其中 `_build_return_start_envelope_tokens_for_obs()` 只负责从 planner state 装配
request、调用 service，并写回 `_return_start_envelope_token_source`、
`_return_start_envelope_use_prior_spatial_bounds` 和
`_return_start_envelope_use_prior_qpos_bounds`。planner shell 仍负责 return target
plan 生成、pending dig cut state 写回、handoff context 装配、branch order、switch
reason、policy dispatch、debug schema 和 rollout trace。

本切片不改变 token dim/order、prior cell/global fallback 策略、source string、
relocate conditioning 数值、start-envelope handoff gate、pending dig plan、
return->dig branch order、debug_state 字段或 rollout 行为。

## Policy Observation Assembly Slice

新增模块：

- `testbed/planner/policy_observation.py`

`PolicyObservationAssembler` 负责把 planner 已经生成的 optional low-dim token
合并进 ACT policy observation，并返回 debug 注入标志。service 只接收显式
`PolicyObservationTokens` 和当前 observation，不接收 planner `self`，不调用
token builder，不改变 active skill，不 dispatch policy，不 reset policy，不写 debug
schema，也不决定哪些 token 应该存在。

planner 大文件只保留薄 facade：`_policy_obs()` 继续按原顺序调用
`_goal_tokens()`、`_cell_entry_tokens_for_obs()`、`_dig_cut_tokens_for_obs()`、
`_dig_depth_profile_tokens_for_obs()`、`_return_target_tokens_for_obs()`、
`_return_relocate_tokens_for_obs()` 和 `_return_start_envelope_tokens_for_obs()`；
随后调用 assembler，并把 `*_token_injected` 标志写回 planner state 供
debug/trace builder 使用。

本切片不改变 token 生成语义、low-dim key、policy dispatch 目标、active skill、
branch order、switch reason、debug schema 或 rollout record 行为。无 token 时仍返回
原 observation 对象；只有 `goal_tokens` 时仍不设置 planner debug injected flag。

## 测试锁定规则

Phase 1 必须覆盖：

- return handoff service unit tests：entry-close、non-finite fallback、start-envelope ready/fail/missing-token fallback、direct handoff、shallow guard。
- golden trace：active skill trace、switch reason trace、completed transition count、policy reset count。
- legacy planner tests：return-to-dig、direct handoff、same-frame dump/carry -> dig、return -> pre_dig_align 的旧 reason 字符串。
- debug/trace schema：keys、types、ordering 保持不变。

验证命令：

```bash
pytest tests/test_return_handoff_service.py tests/test_return_start_envelope.py tests/test_planner_golden_traces.py tests/test_primitive_planner_debug_schema.py
pytest tests/test_agx_primitives_v2_2.py -k "return_to_dig or direct_handoff or shallow_guard or pre_dig_align or spatial_mass_boundary"
pytest tests/test_dump_lifecycle_service.py tests/test_planner_golden_traces.py tests/test_primitive_planner_debug_schema.py tests/test_agx_primitives_v2_2.py -k "dump_ready or dump_done or dump_end or dump_release or approach_dump or release_safety or near_window or dump_area_relative or carry_to_dump or dump_to_return"
pytest tests/test_dig_lifecycle_service.py tests/test_agx_primitives_v2_2.py -k "dig_bad_replan or exit_guard or failed_dig or dig_complete or pre_dig_align or dig_to_carry"
pytest tests/test_dig_start_alignment_service.py tests/test_agx_primitives_v2_2.py -k "pre_dig_align"
pytest tests/test_bootstrap_service.py tests/test_agx_primitives_v2_2.py -k "bootstrap"
pytest tests/test_primitive_planner_debug_schema.py tests/test_planner_golden_traces.py
pytest tests/test_policy_observation.py tests/test_eval_rollout_records.py
```

## 回滚策略

Phase 1、dump lifecycle gate slice、dig lifecycle gate slice、dig-start
alignment numeric/readiness slice、scripted bootstrap compatibility slice 和
debug/trace builder slice 的旧 private/public method 均保留为 facade。如果 service
extraction 发现行为漂移，可以让 facade 临时回到旧实现，同时保留新增 service unit
tests 和 golden trace 作为后续迁移的行为锁。
