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

Goal sector name/id mapping 只从 `testbed.planner.goal_sequence` 读取。primitive
planner config、fixed sequence planner、Stage-4 planner types 和 eval live-goal
sequence normalization 只能引用该 mapping，不能各自复制 `left/mid/right -> 0/1/2`
语义。

Cycle boundary profile 的 semantic-mainline predicate 只从
`testbed.contracts.primitive_profile.is_v2_4_5_cycle_boundary_profile()` 读取。
planner shell 可以从 boundary detector config 采样 profile name，但不能在
dig/dump/return facts assembly 中复制 `v2_4_5_spatial_mass` 字符串比较。

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

## 优先级与已知失败支线

5P 已被验证为失败支线，当前重构主线不以 5P 行为改进或 5P service 拆分为优先目标。
涉及 5P 的现有代码只作为兼容路径保留：如果迁移主线 service 时顺带触达 5P helper，
只能做 behavior-preserving facade / pass-through / deletion-after-migration，不新增
5P 调度语义、不围绕 5P 扩展测试矩阵，也不把 5P 作为后续切片的主要验收路径。后续
优先级仍放在 4P / semantic profile 主线的 dig、carry、dump、return lifecycle 和
planner shell 瘦身。

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

## Planner Observation Facts Slice

`testbed/planner/snapshots.py` 作为 planner observation facts 的 source-of-truth。
除 `PlannerSnapshot` / `PlannerObservationView` 外，该模块还负责从 `obs`、
`task_metrics` 和 `env_state` 解析 scheduler legacy helper 所需事实：
bucket mass、deposited mass、dig-area distance/depth/contact、bucket/tip pose、
dig cell id、dig-area geometry availability，以及 carry->dump target geometry。
同一边界还拥有 boundary detector update 的输入投影：
`boundary_detector_update_facts_from_obs()` 保留旧 `obs.get(...)` raw value/default
语义，只组装 detector 需要的 env_state、action、qpos、reward_phase、
task_step_successes 和 task_metrics；detector update 的调用时机、返回事件处理和
detector state mutation 仍由 planner shell 的 `predict()` 拥有。

planner 大文件只保留旧 private facade：

- `_env_state()`
- `_target_geometry()`
- `_mass_in_bucket()`
- `_deposited_mass()`
- `_min_distance_to_dig_area()`
- `_bucket_depth_below_dig_area_plane()`
- `_bucket_depth_below_local_surface()`
- `_bucket_dig_area_contact_mask()`
- `_bucket_dig_area_cell_in_bounds_mask()`
- `_dig_cell_id()`
- `_bucket_dig_area_pose()`
- `_bucket_tip_dig_area_pose()`
- `_boundary_detector_update_facts()`

本切片只移动 observation parsing，不改变 snapshot view 既有 missing-env fallback、
legacy planner helper 的 zero/NaN fallback、boundary detector raw qpos/default
行为、target geometry error message、branch order、threshold、switch reason、
policy dispatch、debug schema 或 rollout 行为。

## Primitive Planner Config Helper Slice

新增模块：

- `testbed/planner/primitive_config.py`

`primitive_config` 负责 primitive planner 初始化期间的纯配置解析/校验 helper：
return-start envelope plane-depth mode normalization、failed-dig replan next-skill
normalization、optional float/vector parsing、dig-cut prior JSON loading、dig-cut /
coverage / dig-depth-profile config validation，以及 legacy goal-sequence
normalization。

`PrimitiveConditioningConfig` 和 `build_conditioning_config()` 负责把
`dig_cut_planner` 与 `return_target_planner` 的 nested config 解析成 planner shell
需要应用的显式字段：dig-cut mode/prior/hold flag、return-start-envelope qpos/spatial
conditioning 参数、dig-depth-profile source/fallback flags、return-target token
conditioning 参数，以及 coverage scoring / multi-pass / state-exemplar /
first-dig / percentile 参数。该 helper 不接收 planner `self`，不创建 coverage
service，不执行 runtime reset，不组装 policy observation，不构造 token，不处理 pending
dig plan，也不迁 pre-dig-align config。coverage state-exemplar 的实际加载仍通过
coverage capability/facade 执行，避免 config helper 拥有 coverage I/O。

planner 大文件只保留旧 private facade：

- `_normalize_plane_depth_mode()`
- `_normalize_failed_dig_replan_skill()`
- `_align_vector()`
- `_optional_align_vector()`
- `_optional_float()`
- `_load_dig_cut_prior()`
- `_validate_dig_cut_planner_config()`
- `_normalize_goal_sequence()`
- `_apply_conditioning_config()`

本切片不改变默认 config、validation error text、prior token-order validation、
goal sector id mapping、threshold、branch order、switch reason、policy dispatch、
debug schema 或 rollout 行为。初始化仍由 `PrimitivePlannerACTPolicy.__init__`
负责调用 helper 并把解析后的配置写入 planner state；config helper 不接收 planner
`self`，不创建 service，不读取 runtime observation，也不参与状态机跳转。

## Pre-Dig Align Config Assembly Slice

`primitive_config` 新增 `PreDigAlignmentPlannerConfig` 和
`build_pre_dig_alignment_config()`，负责把 `pre_dig_align` 初始化配置解析成
planner shell 需要应用的显式字段：enable / first-dig / failed-dig-replan flags、
PD gain、action clip/sign、controlled dims、entry-intent dims 与 handoff 默认值、
surface guard 参数、start envelope 参数、qpos/pose bounds 和 token-to-qpos
coefficients。

本切片把配置解析留在 `primitive_config` capability，而不是放入
`DigStartAlignmentService`。原因是 `pre_dig_align` namespace 同时包含
alignment 数值配置和 scheduler lifecycle flags，例如 `first_dig_only` 与
`replan_after_failed_dig`；这些 flags 的运行时语义仍由 planner/dig lifecycle
边界拥有，alignment service 不应扩展为 scheduler state owner。

planner 大文件只保留薄应用入口：

- `_apply_pre_dig_align_config()`

本切片不改变 pre-dig-align 默认值、shape/dtype、`entry_intent_handoff_enabled`
依赖默认、threshold、branch order、switch reason、terminal reason、policy reset
timing、debug/summary schema、token contract 或 rollout 输出。pre-dig-align
runtime reset、active-for-next-dig 判断、surface/ready/timeout gate、outcome
classification、counter 写回和 debug-state 展开仍在既有 service/facade 边界内。

## Dig-Start Alignment Runtime Config Assembly Slice

`dig_start_alignment` 新增 `build_dig_start_alignment_runtime_config()`，负责把
planner shell 中的 pre-dig-align runtime 字段投影成 `DigStartAlignmentConfig`：
action dim、qpos bounds、token-to-qpos coefficients、controlled dims、entry-intent
dims、bucket target、PD gain、action clip/sign、enable flags、qpos/qvel tolerance、
entry/start-envelope/surface-guard handoff thresholds，以及 start qpos/pose bounds。

本切片把 `_dig_start_alignment_config()` 中的 `int` / `float` / `bool` coercion
迁入已有 `dig_start_alignment` domain capability；planner 旧 private facade 只负责
传递当前 planner 字段并返回 builder 结果。该 builder 不接收 planner `self`，不读取
observation，不拥有 active skill，不调用 `_set_skill()`，不 reset policy，不写 HDF5
或 checkpoint，也不组装 debug schema。

本切片不改变 pre-dig-align 初始化默认值、runtime 字段来源、array/list 原样透传
语义、threshold、branch order、switch reason、terminal reason、policy reset
timing、debug/summary schema、token contract 或 rollout 输出。pre-dig-align
readiness/outcome、surface guard、entry-intent handoff、timeout handoff、runtime
counter 写回和 debug-state 展开仍留在既有 service/facade 边界内。

## Dig-Start Alignment Runtime Config Mapping Slice

`dig_start_alignment` 继续作为 pre-dig-align target / action / readiness / runtime
state projection 的 source-of-truth。本切片新增
`DIG_START_ALIGNMENT_RUNTIME_CONFIG_FIELDS` 和
`build_dig_start_alignment_runtime_config_from_mapping()`，把
`_dig_start_alignment_config()` 的 runtime config 字段映射收回到 domain capability
内。planner 旧 private facade 只从自身当前字段构造 focused mapping 并转调 builder。

service 只从显式 mapping 中读取 runtime config 字段并复用
`build_dig_start_alignment_runtime_config()`；不接收 planner `self`，不读取
observation，不计算 target/action/ready/outcome，不更新 pre-dig-align counters，不
调用 `_set_skill()`，不 reset policy，也不写 debug schema。planner shell 仍负责
service 调用顺序、pre-dig-align runtime state 写回、surface guard / timeout /
entry-intent handoff 的 gate 调用顺序、branch order、switch reason、terminal reason、
policy reset timing 和 debug/summary schema。

本切片不改变 pre-dig-align runtime 字段来源、array/list object identity、`int()` /
`float()` / `bool()` coercion、entry/start-envelope/surface guard thresholds、
first-dig handoff flags、entry-intent dims、branch order、switch reason、terminal
reason、policy reset timing、debug/summary schema、token contract 或 rollout 输出。

## Return-To-Dig Config Assembly Slice

`return_handoff` 新增 `ReturnToDigPlannerConfig` 和
`build_return_to_dig_config()`，负责把 planner 初始化期间的 return-to-dig
handoff / return start-envelope gate 配置解析成 planner shell 需要应用的显式字段：
legacy shallow guard 参数、entry-error threshold、start-envelope gate/direct flags、
spatial/depth/qpos tolerance、plane-depth mode、contact requirement，以及
`return_max_steps`。`RETURN_TO_DIG_CONFIG_KEYS` 只作为 planner `__init__` filtered
init-argument mapping facade 的字段边界，避免 planner 大文件复制冗长参数转发表。

本切片把 return-to-dig 初始化配置放在 `return_handoff` domain capability，而不是
继续放入 `primitive_config`。原因是 return handoff 已经拥有 entry-error 几何、
handoff gate、transition classification、direct-handoff attempt、runtime status 和
runtime reset 的 service-object 边界；配置投影属于同一领域输入边界，同时避免
`primitive_config` 继续膨胀。`primitive_config` 只保留旧 import facade，保证现有
public helper import 不破坏。return start-envelope plane-depth mode normalization 的
source-of-truth 在 `return_start_envelope`，`primitive_config` 同样只转出同一对象。

planner 大文件只保留薄应用入口：

- `_apply_return_to_dig_config()`

本切片只迁初始化配置投影，不迁 return transition classification、same-frame direct
handoff attempt、return-to-dig handoff gate、return start-envelope token 构造、
return timeout counter、policy reset timing 或 debug/summary schema。config helper
不复制 threshold、token/schema/profile source-of-truth，也不接收 planner `self`。

本切片不改变 return-to-dig 默认值、plane-depth mode alias / error text、
`None` / `"null"` optional float 语义、return max step coercion、branch order、
switch reason、terminal reason、policy reset timing、debug/summary schema、token
contract 或 rollout 输出。

## Return-To-Dig Handoff Runtime Config Mapping Slice

`return_handoff` 继续作为 return-to-dig handoff gate 的
source-of-truth。本切片新增 `RETURN_TO_DIG_HANDOFF_CONFIG_FIELDS` 和
`build_return_to_dig_handoff_config_from_mapping()`，把
`_return_to_dig_handoff_config()` 中当前 planner runtime 字段到
`ReturnToDigHandoffConfig` 的投影收回 return handoff capability。planner 旧 private
facade 只从自身当前字段构造 focused mapping 并转调 builder。

该 builder 只复刻旧 runtime `_return_to_dig_handoff_config()` 的原样投影语义：
shallow guard 参数、entry-error threshold、start-envelope gate flag 和 direct-handoff
flag。它不复用初始化 `build_return_to_dig_config()` 的 `bool()` / `float()` /
optional-float normalization，也不读取 return start-envelope tolerance fields；这些
仍由 return-start-envelope runtime config facade 和 initialization config helper 各自
负责，避免混淆 runtime facade 与 init config 语义。

service 不接收 planner `self`，不读取 observation，不调用 `_set_skill()`，不 reset
policy，不写 HDF5/checkpoint/debug schema，也不决定 return branch outcome。return
transition classification 的 source-of-truth 在 `return_to_dig_transition`，planner
shell 仍负责 handoff gate 调用顺序、same-frame direct handoff attempt、return
transition classification、`_return_next_dig_event_seen` 写回、completed transition /
cycle counter 写回、switch reason、policy reset timing 和 public debug/summary schema。

本切片不改变 return-to-dig threshold 值、start-envelope tolerance/source-of-truth、
direct handoff branch、legacy shallow guard branch、next-dig event handling、
switch reason、terminal reason、policy reset timing、debug/summary schema、token
contract 或 rollout 输出。

## Dig Lifecycle Config Assembly Slice

`dig_lifecycle` 新增 `DigLifecyclePlannerConfig` 和
`build_dig_lifecycle_config()`，负责把 planner 初始化期间的 dig lifecycle 配置解析成
planner shell 需要应用的显式字段：dig-to-carry mass / distance / target payload、
mass-plateau gate 参数、bad-dig replan 参数、exit-guard 参数，以及
failed-dig replan next-skill normalization。`DIG_LIFECYCLE_CONFIG_KEYS` 只作为
planner `__init__` filtered init-argument mapping facade 的字段边界，避免 planner
大文件复制冗长参数转发表。

本切片把 dig lifecycle 初始化配置放在 `dig_lifecycle` domain capability，而不是
继续放入 `primitive_config`。原因是 dig lifecycle 已经拥有 gate、progress、
transition outcome、runtime status 和 runtime reset 的 service-object 边界；配置投影
属于同一领域输入边界，同时避免 `primitive_config` 继续接近大文件阈值。
`primitive_config` 只保留旧 import facade，保证现有 public helper import 不破坏。

planner 大文件只保留薄应用入口：

- `_apply_dig_lifecycle_config()`

本切片只迁初始化配置投影，不迁 dig progress update、dig-to-carry gate、
bad-replan / exit-guard gate、failed-dig recovery、coverage reject/complete、
pre-dig-align lifecycle flags、dump-ready threshold、policy reset timing 或
debug/summary schema。`dig_lifecycle` 拥有
`normalize_failed_dig_replan_skill()` 的 alias/source-of-truth；`primitive_config`
只转出同一对象，不复制 alias 规则。config helper 不接收 planner `self`，不调用
`_set_skill()`，不读取 observation。

本切片不改变 dig lifecycle 默认值、target-payload fallback 到
`dig_to_carry_min_bucket_mass_kg` 的旧语义、hold/min-step `max(1, int(...))`
coercion、failed-dig skill alias / error text、branch order、switch reason、
terminal reason、policy reset timing、debug/summary schema、token contract 或
rollout 输出。runtime gate config 汇总由单独的 runtime config slice 处理；初始化
config helper 不拥有 observation、gate 调用、runtime counters 或 pre-dig-align
runtime 决策。

## Dig Lifecycle Runtime Config Assembly Slice

`dig_lifecycle` 继续作为 dig lifecycle gate / progress / recovery 的
source-of-truth。本切片新增 `build_dig_lifecycle_runtime_config()`，负责把 planner
shell 已维护的 runtime config 字段投影成 `DigLifecycleConfig`：dig-to-carry mass /
distance / target payload、mass-plateau gate 参数、bad-dig replan 参数、exit-guard
参数、dump-ready mass threshold、failed-dig next-skill string，以及 pre-dig-align
lifecycle flags。

planner 大文件只保留旧 private facade：

- `_dig_lifecycle_config()`

planner shell 仍负责从当前 planner runtime state 读取字段，并保留 service 调用顺序、
dig progress counter 写回、coverage payload gain 写回、failed-dig recovery、
pre-dig-align lifecycle side effects、branch order、switch reason、terminal reason、
policy reset timing 和 debug/summary schema。builder 只做旧 runtime 语义中的
`float()` / `bool()` / `int()` / `str()` 投影；它不接收 planner `self`，不读取
observation，不调用 dig gates，不更新 counters，不完成/reject coverage，不调用
`_set_skill()`，也不写 debug schema。

本切片刻意不复用 `build_dig_lifecycle_config()` 的初始化 coercion，因为旧
`_dig_lifecycle_config()` 对 hold/min/max step 字段使用直接 `int()`，而初始化 helper
会做 `max(1, int(...))` normalization。该差异必须保持 behavior-preserving。本切片不
改变 dig-to-carry / bad-replan / exit-guard threshold、mass-plateau counters、
failed-dig next-skill runtime string、pre-dig-align lifecycle flags、branch order、
switch reason、terminal reason、policy reset timing、debug/summary schema 或 rollout
输出。

## Dig Lifecycle Runtime Config Mapping Slice

`dig_lifecycle` 继续作为 dig lifecycle runtime gate config 的 source-of-truth。本切片
新增 `DIG_LIFECYCLE_RUNTIME_CONFIG_KEYS` 和
`build_dig_lifecycle_runtime_config_from_mapping()`，把 `_dig_lifecycle_config()` 的
runtime key 清单收回到 domain capability 内。planner 旧 private facade 只从自身当前
字段构造 focused mapping 并转调 builder。

service 只从显式 mapping 中读取 runtime config 字段并复用
`build_dig_lifecycle_runtime_config()`；不接收 planner `self`，不读取 observation，
不调用 dig-to-carry / bad-replan / exit-guard gate，不更新 progress counters，不
reject / complete coverage，不调用 `_set_skill()`，也不写 debug schema。planner shell
仍负责 service 调用顺序、dig progress counter 写回、coverage payload gain 写回、
failed-dig recovery、pre-dig-align lifecycle side effects、branch order、switch
reason、terminal reason、policy reset timing 和 debug/summary schema。

本切片不改变 dig-to-carry / bad-replan / exit-guard threshold、mass-plateau counters、
failed-dig next-skill runtime string、pre-dig-align lifecycle flags、`int()` 直接投影
而非初始化 `max(1, int(...))` normalization 的旧 runtime 语义、branch order、switch
reason、terminal reason、policy reset timing、debug/summary schema 或 rollout 输出。

## Dump Lifecycle Config Assembly Slice

`dump_lifecycle` 新增 `DumpLifecyclePlannerConfig` 和
`build_dump_lifecycle_config()`，负责把 planner 初始化期间的 4P dump lifecycle
配置解析成 planner shell 需要应用的显式字段：dump-ready mass / height / footprint /
clearance / horizontal-distance 参数、dump-area-relative window、near-window 参数、
dump-ready hold steps、dump-done mass / deposit / hold 参数，以及
`dump_done_use_boundary_event`。`DUMP_LIFECYCLE_CONFIG_KEYS` 只作为 planner
`__init__` filtered init-argument mapping facade 的字段边界，避免 planner 大文件复制
冗长参数转发表。

本切片把 dump 初始化配置放在 `dump_lifecycle` domain capability，而不是继续放入
`primitive_config`。原因是 `primitive_config` 已接近大文件阈值，且 dump lifecycle
已有稳定 service module 承接 gate、outcome 与 runtime reset；把初始化投影放回该领域
module 可以减少 planner shell 和 central config helper 的双重膨胀，同时不新建单
helper 贫血模块。

planner 大文件只保留薄应用入口：

- `_apply_dump_lifecycle_config()`

本切片只迁 4P dump 初始化配置投影，不迁 `_dump_lifecycle_config()` 的 runtime 汇总、
`_dump_ready()` / `_dump_done()` gate、carry/dump transition outcome、hold counter
写回、dump-start deposit snapshot、coverage completion、return direct handoff、
policy reset timing、debug/summary schema 或 5P approach / dump-release 兼容语义。
`dump_lifecycle` 不接收 planner `self`，不调用 `_set_skill()`，不读取 observation，
不复制 token/schema/profile source-of-truth。

本切片不改变 dump lifecycle 默认值、optional float 仅对 `None` 保持 `None` 的旧
语义、hold-step `max(1, int(...))` coercion、branch order、switch reason、
terminal reason、policy reset timing、debug/summary schema、token contract 或 rollout
输出。5P 仍通过既有 super-call 参数映射复用 4P dump fields，本切片不提升或扩展 5P
调度语义。

## Dump Lifecycle Runtime Config Assembly Slice

`dump_lifecycle` 继续作为 dump lifecycle gate / outcome / runtime state 的
source-of-truth。本切片新增 `build_dump_lifecycle_runtime_config()`，负责把 planner
shell 已维护的 runtime config 字段投影成 `DumpLifecycleConfig`：4P dump-ready mass /
height / footprint / clearance / horizontal-distance、dump-area-relative window、
near-window、dump-done mass/deposit，以及 5P `approach_ready` 兼容 gate 字段。

planner 大文件只保留旧 private facade：

- `_dump_lifecycle_config()`

planner shell 仍负责从当前 planner runtime state 读取字段，并保留 5P super-call
兼容路径中 `approach_ready_*` 缺失时的 legacy `getattr(..., default)` fallback。builder
只做旧语义中的 `float()` / `bool()` / `str()` coercion，以及 optional float
`None -> None else float(value)` 投影；不接收 planner `self`，不读取 observation，
不调用 dump-ready / dump-done gate，不写 hold counter，不完成 coverage，不调用
`_set_skill()`，也不写 debug schema。

本切片不改变 dump-ready / dump-done / approach-ready threshold 值、optional float
fallback、position mode error string、carry/dump branch order、hold-count 写回、
dump-start deposit snapshot、coverage completion、return direct handoff、switch
reason、terminal reason、policy reset timing、debug/summary schema 或 rollout 输出。

## Dump Lifecycle Runtime Config Mapping Slice

`dump_lifecycle` 继续作为 dump lifecycle runtime gate config 的 source-of-truth。本切片
新增 `DUMP_LIFECYCLE_RUNTIME_CONFIG_KEYS` 和
`build_dump_lifecycle_runtime_config_from_mapping()`，把 `_dump_lifecycle_config()` 的
runtime key 清单、4P required fields 与 5P `approach_ready_*` 兼容 fallback defaults
收回到 domain capability 内。planner 旧 private facade 只从自身当前字段构造 focused
mapping 并转调 builder。

service 只从显式 mapping 中读取 runtime config 字段并复用
`build_dump_lifecycle_runtime_config()`；不接收 planner `self`，不读取 observation，
不调用 dump-ready / dump-done / approach-ready gate，不写 hold counter，不完成
coverage，不调用 `_set_skill()`，也不写 debug schema。planner shell 仍负责 service
调用顺序、5P/4P branch order、counter 写回、coverage completion、return direct
handoff、policy reset timing 和 debug/summary schema。

本切片不改变 dump-ready / dump-done / approach-ready threshold 值、optional float
fallback、缺失 approach config 时的 legacy defaults、position mode error string、
branch order、hold-count 写回、dump-start deposit snapshot、coverage completion、
switch reason、terminal reason、policy reset timing、debug/summary schema 或 rollout
输出。

## Goal Sequence Source-Of-Truth Slice

新增模块：

- `testbed/planner/goal_sequence.py`

`goal_sequence` 负责 goal sector name/id mapping 的唯一 source-of-truth，以及
primitive goal sequence 的纯 normalization、current/next sector lookup 和 goal
token assembly。`GoalSequenceService` 只接收显式 `GoalSequenceFacts`、
`GoalSequenceConfig` 和 normalized sequence，不接收 planner `self`，不调用
`_set_skill()`，不 reset policy，不写 debug schema，不改变
`testbed.data.v2_1.build_goal_tokens` 的 token contract。

现有 public/facade 入口继续保留并转调该 source-of-truth：

- `primitive_config.PRIMITIVE_GOAL_SECTOR_IDS`
- `primitive_config.normalize_goal_sequence()`
- `types.SECTOR_NAME_TO_ID` / `types.SECTOR_ID_TO_NAME`
- `fixed_sequence_planner.SECTOR_NAME_TO_ID` / `SECTOR_ID_TO_NAME`
- `EvalSuite._normalize_live_goal_sequence()`
- planner private facade `_goal_tokens()` / `_goal_sector_id()` /
  `_next_goal_sector_id()`

本切片不改变 `left/mid/right -> 0/1/2`、primitive/live goal sequence validation
error text、goal token values、debug `primitive_goal_*_sector_id` 字段、policy
observation injection order、branch order、switch reason、policy reset timing 或
rollout 行为。

## Goal Sequence Config Assembly Slice

`goal_sequence` 新增 `GoalSequencePlannerConfig` 和
`build_goal_sequence_planner_config()`，负责把 planner 初始化期间的 primitive goal
sequence 配置解析成 planner shell 需要应用的显式字段：normalized
`goal_sequence`、`goal_scenario_id`、`goal_depth_norm` 和
`goal_dump_target_norm`。`GOAL_SEQUENCE_CONFIG_KEYS` 只作为 planner `__init__`
filtered init-argument mapping facade 的字段边界，避免 planner 大文件继续直接复制
goal-sequence 初始化 coercion。

本切片把初始化配置投影放入现有 `goal_sequence` capability，而不是新建单 helper
模块。原因是 `goal_sequence` 已经是 sector mapping、normalization、current/next
sector lookup 和 primitive goal token assembly 的 source-of-truth；config assembly
只补齐同一领域的初始化输入边界，不引入新的 service 状态或 token/schema/profile
定义。

planner 大文件只保留薄应用入口：

- `_apply_goal_sequence_config()`

planner shell 仍负责 service 调用顺序、policy observation injection、active skill、
reset timing、branch order、switch reason、debug/summary schema 和旧 private facade
`_goal_tokens()` / `_goal_sector_id()` / `_next_goal_sector_id()` /
`_normalize_goal_sequence()`。`goal_sequence` config helper 不接收 planner `self`，
不调用 `_set_skill()`，不 reset policy，不写 HDF5/checkpoint，不写 debug schema，
也不改变 `testbed.data.v2_1.build_goal_tokens` 的 token contract。

本切片不改变 goal sequence 默认值、goal sector validation error text、goal token
values、debug `primitive_goal_*_sector_id` 字段、policy observation injection order、
branch order、switch reason、policy reset timing、debug/summary schema、token contract
或 rollout 输出。

## Dump Lifecycle Gate Slice

新增模块：

- `testbed/planner/dump_lifecycle.py`

`DumpLifecycleGateService` 负责纯 gate 判断：4P `dump_ready`、
dump-area relative position / near-window helper、`dump_done`、
`carry_release_safety_done`，以及 5P `approach_ready`。service 还负责 carry/dump
分支的纯 outcome classification，基于 caller-provided boundary/gate/hold-ready
布尔值返回旧 switch reason 和 coverage completion reason。service 只接收显式
`DumpLifecycleFacts`、`DumpLifecycleConfig` 和 caller-provided booleans，不接收
planner `self`，不调用 `_set_skill()`，不写回 hold counter，不 reset policy，
不完成 coverage，不决定 return direct handoff。后续 runtime slice 允许 service
纯计算 next hold-count 建议值，但最终状态写回仍由 planner shell 执行。

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
counter 写回、dump start deposit 写回、coverage completion 执行、skill transition、
return direct handoff、policy reset timing 和 debug schema。semantic profile 下
legacy `_dump_ready()` / `_dump_done()` fallback 仍由 planner shell 的原有分支控制，
service 不提升实验语义为默认行为。5P `_approach_ready()` 在本切片中只是兼容 facade，
不代表 5P 被提升为当前重构优先级。

## Dump Lifecycle Facts Assembly Slice

`dump_lifecycle` 新增 `build_dump_lifecycle_facts()`，负责把 planner shell 显式采样的
dump lifecycle 输入投影成 `DumpLifecycleFacts`：当前 bucket mass、deposited mass、
target geometry、semantic boundary profile flag，以及 coverage cycle start deposit
snapshot。该 helper 不接收 planner `self`，不读取 observation，不调用 target
geometry facade，不写 planner state，不完成 coverage，也不决定 return direct
handoff。

planner `_dump_lifecycle_facts()` 作为旧 private facade 保留在 shell 内，只负责按旧
来源采样 obs、target geometry、boundary detector profile 和 coverage deposit snapshot，
然后转调 `build_dump_lifecycle_facts()`。carry/dump branch order、hold counter 写回、
dump start deposit snapshot 写回、coverage completion、`_set_return_or_direct_handoff()`、
`_set_skill()`、policy reset timing 和 debug/summary schema 仍由 planner shell 拥有。

同一 Facts Assembly 边界后续新增 `DUMP_LIFECYCLE_FACT_FIELDS` 和
`build_dump_lifecycle_facts_from_mapping()`，把 `_dump_lifecycle_facts()` 中的显式
facts mapping 字段表与 `build_dump_lifecycle_facts()` 调用收回 `dump_lifecycle`
capability。planner 旧 private facade 仍按旧来源采样 mass/deposit、target geometry、
semantic profile flag 和 coverage cycle-start deposit snapshot，再按字段表转调
builder。

同一 boundary 现在继续收口 source projection：`dump_lifecycle` 新增
`build_dump_lifecycle_facts_from_observation_view()` 与
`DumpLifecycleGateService.facts_from_observation_view()`，从
`PlannerObservationView` 的原始 observation 复用 `snapshots` 中的 legacy
mass/deposit/target-geometry helper，保持旧 fallback 与 target geometry error text。
planner `_dump_lifecycle_facts()` 只创建 snapshot 并传递 semantic profile flag 与
coverage cycle-start deposit snapshot；不再在 planner 大文件内手写 facts mapping。
该 service method 不接收 planner `self`，不调用 `_set_skill()`，不 reset policy，
不写 debug/summary schema，也不执行 coverage side effect。

本切片不改变 target geometry key/value、mass/deposit fallback、semantic boundary
profile 判断、`carry_to_return_release_safety`、`carry_to_return_dump_complete_boundary`、
`carry_to_dump_*`、`dump_to_return_dump_complete_boundary`、
`dump_to_return_dump_end`、`dump_to_return_mass_low` reason 字符串，不改变
threshold、branch order、coverage side effect、policy reset timing、debug/summary
schema 或 rollout 输出。

## Dump Lifecycle Transition Runtime Slice

`DumpLifecycleGateService` 继续负责 dump lifecycle 的纯 gate/outcome 能力。本切片
新增 `CarryTransitionRuntimeFacts` / `CarryTransitionRuntimeState` 和
`DumpTransitionRuntimeFacts` / `DumpTransitionRuntimeState`，把 carry/dump 分支中
hold-count 的下一状态和既有 `DumpLifecycleOutcome` 组合迁入 service。service 只接收
planner 已经按旧短路顺序采集好的布尔事实、当前 hold count 和 hold-step 配置，返回
建议的 hold count 与 outcome；不读取 obs，不调用 `_dump_ready()` /
`_dump_done()`，不写 planner state，不完成 coverage，不调用 `_set_skill()`。

后续 slice 在同一 `dump_lifecycle` capability 中新增
`CarryTransitionRuntimeRequest` / `DumpTransitionRuntimeRequest` 以及
`build_carry_transition_runtime_request()` /
`build_dump_transition_runtime_request()`，负责解析 boundary-event flags、legacy
`dump_start` / `dump_end` 只在非 semantic boundary profile 下生效的兼容 gate，以及
是否应按旧短路顺序调用 `_dump_ready()` / `_dump_done()`。request 只返回显式 facts
和 gate-request bool；不读取 observation，不调用 dump-ready/dump-done gate，不写
hold counter，不完成 coverage，也不决定 skill transition。

planner 大文件仍负责：

- carry/dump branch order
- 按 request 的 gate-request bool 和旧短路时机调用 `_carry_release_safety_done()`、
  `_dump_ready()` 和 `_dump_done()`
- `_dump_ready_hold_count` / `_dump_done_hold_count` 的最终写回
- `_dump_start_deposited_mass_kg` snapshot
- `_complete_coverage_dump()`、`_set_return_or_direct_handoff()`、`_set_skill()`
- policy reset timing、debug/summary schema 和 rollout trace

本切片不改变 `carry_to_return_release_safety`、
`carry_to_return_dump_complete_boundary`、`carry_to_dump_*`、
`dump_to_return_dump_complete_boundary`、`dump_to_return_dump_end`、
`dump_to_return_mass_low` reason 字符串，不改变 hold-count threshold 行为、boundary
event 优先级、semantic profile 下 legacy dump-ready / dump-done gate 禁用逻辑、
coverage completion reason、dump-start deposit snapshot、return direct handoff、
branch order、policy reset timing 或 debug/summary schema。

## Dump Lifecycle Transition Application Facade Slice

`DumpLifecycleGateService` 已经负责 carry/dump transition request、hold-count runtime
state 和 `DumpLifecycleOutcome` 的纯 projection。本切片把 planner carry/dump branch 中
runtime 之后的 shell-owned application 集中到旧 private facades：

- `_apply_carry_transition_runtime()`
- `_apply_dump_transition_runtime()`

这些 facade 只应用 service 已返回的 runtime state：写回 `_dump_ready_hold_count` 或
`_dump_done_hold_count`，并在同一 shell 边界内执行既有 side effects。carry return
路径仍执行 `_complete_coverage_dump()` 后 `_set_return_or_direct_handoff()`；carry dump
路径仍采样 `_deposited_mass(obs)` 写入 `_dump_start_deposited_mass_kg` 后
`_set_skill("dump", ...)`；dump return 路径仍执行 `_complete_coverage_dump()` 后
`_set_return_or_direct_handoff()`。facade 不重新分类 outcome，不调用 dump-ready /
dump-done gate，不 reset policy，不写 debug schema，也不把 side effect 放入 service。

planner carry/dump 分支仍负责旧有调用顺序：按 request 决定是否调用
`_dump_ready()` / `_dump_done()`，调用 transition runtime service，然后调用该 shell
application facade。本切片只把 runtime 到 shell lifecycle side effects 的应用细节从主
branch 移入 planner shell 的私有 facade，让主 state-machine branch 更接近
“生成 runtime -> 应用 runtime -> return”的薄结构。

本切片不改变 branch order、hold-count threshold、boundary event priority、semantic
profile legacy gate 禁用逻辑、coverage completion reason、dump-start deposit snapshot
采样时机、return direct-handoff 时机、switch reason、policy reset timing、
debug/summary schema、token contract 或 rollout 输出。

## Dump Lifecycle Transition Module Boundary Slice

`dump_lifecycle_transition` 作为 dump lifecycle carry/dump transition request、
outcome classification 和 hold-count runtime projection 的稳定 source-of-truth。
`dump_lifecycle` 只保留这些 transition runtime symbols 的 compatibility re-export，
并继续拥有 dump lifecycle config、facts、gate geometry、runtime reset/status
projection 和 5P approach-ready compatibility gate。

本切片是责任边界修正，不新增调度语义：原
`CarryTransitionRuntimeFacts` / `DumpTransitionRuntimeFacts`、
`build_carry_transition_runtime_request()` / `build_dump_transition_runtime_request()`、
`carry_outcome()` / `dump_outcome()` 以及 carry/dump transition runtime projection 原样迁入
`dump_lifecycle_transition`。`DumpLifecycleGateService` 通过继承
`DumpLifecycleTransitionService` 保留旧 method API，旧 `dump_lifecycle` import 继续可用以
保护现有调用方。新模块只依赖标准库 dataclass/typing，不 import planner shell、
`dump_lifecycle`、observation/parser、token/schema 或 profile source-of-truth，因此不形成
循环 import，也不复制 threshold 或 contract 语义。

后续 service API 收口在同一责任边界内新增
`CarryTransitionRuntimeRequestFacts` / `DumpTransitionRuntimeRequestFacts` 和
`DumpLifecycleTransitionService.carry_transition_runtime_request()` /
`dump_transition_runtime_request()`。旧
`build_carry_transition_runtime_request()` / `build_dump_transition_runtime_request()`
继续作为 compatibility facade 保留，并作为 planner shell 的 request 构造入口；
planner 不再内联构造 `CarryTransitionRuntimeRequestFacts` /
`DumpTransitionRuntimeRequestFacts`。request facts、boundary-event priority、legacy
gate 兼容语义和 hold-count request projection 仍由同一个 dump lifecycle transition
service API 暴露；这不新增模块、不复制 threshold，也不把 planner state 或副作用交给
service。

planner shell 仍负责 carry/dump branch order、按 request 的 gate-request bool 和旧短路
时机调用 `_carry_release_safety_done()` / `_dump_ready()` / `_dump_done()`、
`_dump_ready_hold_count` / `_dump_done_hold_count` 实际写回、
`_dump_start_deposited_mass_kg` snapshot、coverage completion、
`_set_return_or_direct_handoff()`、`_set_skill()`、policy reset timing、debug/summary
schema 和 rollout trace。本切片不改变 switch reason、coverage reason、hold-count
threshold、boundary event priority、semantic profile legacy gate 禁用逻辑、branch
order、policy reset timing、debug/summary schema、token contract 或 rollout 输出。

## Dump Lifecycle Transition Request Builder Facade Slice

planner carry/dump 分支现在通过
`build_carry_transition_runtime_request()` /
`build_dump_transition_runtime_request()` 构造 transition request，而不是在
`primitive_planner.py` 内联实例化 request facts dataclass。该 slice 只移动显式 facts
映射边界：`release_safety_done`、`dump_done_use_boundary_event`、boundary event、
semantic boundary profile active flag 和当前 hold count 仍由 planner 按旧顺序采集，
再交给 dump lifecycle transition capability 解析 request。

planner shell 继续负责按 request bool 短路调用 `_dump_ready()` / `_dump_done()`，
继续调用 transition runtime service 并应用 `_apply_carry_transition_runtime()` /
`_apply_dump_transition_runtime()`。本切片不改变 branch order、boundary-event priority、
legacy `dump_start` / `dump_end` profile gate、hold-count threshold、switch reason、
coverage reason、dump-start deposit snapshot、policy reset timing、debug/summary schema、
token contract 或 rollout 输出。

## Dump Lifecycle Runtime Reset Slice

`DumpLifecycleGateService` 新增 `DumpLifecycleRuntimeState` 和
`initial_runtime_state()`，负责投影 dump lifecycle runtime 的 legacy reset 默认值：
dump-ready hold count、dump-done hold count 和 dump-start deposited-mass snapshot。
service 只返回显式 runtime state；不接收 planner `self`，不调用 `_set_skill()`，不
reset policy，不写 HDF5/checkpoint，不写 debug schema，不读取 observation，不完成
coverage，也不决定 return direct handoff。

planner `_reset_dump_lifecycle_runtime()` 和
`_apply_dump_lifecycle_runtime_state()` 作为旧 private facade 保留在 shell 内，只负责
调用 service 并把返回 state 应用到既有 `_dump_*` runtime 字段。carry/dump 分支内
hold-count 的运行时更新、dump-start deposited-mass snapshot 更新、
`_complete_coverage_dump()`、`_set_return_or_direct_handoff()` 和 `_set_skill()` 仍由
planner shell 按旧 branch order 执行。

本切片不改变 reset timing、初始 active skill、switch reason `reset`、
`carry_to_dump_*` / `dump_to_return_*` reason 字符串、hold-count threshold 行为、
dump-start deposit snapshot 写回时机、coverage completion reason、return direct
handoff、branch order、policy reset timing、debug/summary schema 或 rollout 输出。

## Dump Lifecycle Runtime Status Projection Slice

`DumpLifecycleGateService` 新增 `DumpLifecycleRuntimeStatusState` 和
`DumpLifecycleRuntimeStatusSnapshot`，负责把 planner shell 已维护的 dump lifecycle
hold counters 投影成 debug-state 需要的 runtime facts：dump-ready hold count 和
dump-done hold count。service 只接收显式 runtime state；不接收 planner `self`，
不调用 `_set_skill()`，不 reset policy，不写 debug schema，不读取 observation，不
完成 coverage，也不决定 return direct handoff。

planner `_dump_lifecycle_runtime_status_snapshot()` 作为旧 private facade 保留在
shell 内，只负责采样 `_dump_ready_hold_count` / `_dump_done_hold_count` 并调用
service snapshot。`_make_debug_state()` 从该 snapshot 写入既有
`dump_ready_hold_count` / `dump_done_hold_count` 字段；public debug-state key、
key order 和 coercion 仍由 `primitive_debug` 拥有。

同一 Runtime Status Projection 边界后续新增
`DUMP_LIFECYCLE_RUNTIME_STATUS_FIELDS` 和
`build_dump_lifecycle_runtime_status_state_from_mapping()`，把 planner 当前 dump hold
counters 到 `DumpLifecycleRuntimeStatusState` 的投影收回 `dump_lifecycle`
capability。planner 旧 private facade 只按字段表采样当前 shell state 后调用 builder；
public debug-state key、key order 和 schema 仍不进入 service。

本切片不改变 carry/dump branch order、`carry_to_return_release_safety`、
`carry_to_return_dump_complete_boundary`、`carry_to_dump_*`、
`dump_to_return_dump_complete_boundary`、`dump_to_return_dump_end`、
`dump_to_return_mass_low` reason 字符串，不改变 hold-count threshold 行为、
coverage completion reason、dump-start deposit snapshot 写回时机、return direct
handoff、policy reset timing、debug/summary schema 或 rollout 输出。

## Dig Lifecycle Gate Slice

新增模块：

- `testbed/planner/dig_lifecycle.py`

`DigLifecycleGateService` 负责纯 gate/progress 判断：dig progress 的
step/best-mass/plateau/payload-gain 更新、`dig_bad_replan` readiness、
`dig_exit_guard` overshoot readiness、`dig_complete` low-payload guard，以及
legacy / semantic `dig -> carry` readiness reason。service 也负责 failed-dig
recovery 的纯 decision：基于 `FailedDigRecoveryFacts` / `DigLifecycleConfig`
选择 `pre_dig_align`、`stop` 或 `dig` retry，并返回旧 switch/terminal reason
字符串。service 只接收显式 `DigLifecycleFacts`、`FailedDigRecoveryFacts` 和
`DigLifecycleConfig`，不接收 planner `self`，不调用 `_set_skill()`，不
reject/complete coverage，不请求 terminal stop，不 reset policy，也不写 planner
trace。

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
- `_restart_after_failed_dig()`
- `_should_pre_dig_align_before_dig()`
- `_should_pre_dig_align_after_failed_dig()`

同一边界内的后续 consolidation 新增 `_apply_dig_progress_state()`，把
`DigProgressState` 中的 step/best-mass/plateau/payload-gain 写回收口为 planner shell
内的应用 facade。`_update_dig_progress()` 仍按旧时机调用
`DigLifecycleGateService.update_progress()`，只把 service 返回的 progress state 交给该
facade；service 仍不写 planner state、不拥有 coverage side effect，也不参与 branch
transition。

本切片保留 dig 分支顺序：
`exit_guard -> bad_replan -> complete_low_payload -> carry`。coverage reject、
cell-entry/coverage dig completion、failed-dig stop/retry/pre-dig-align 执行、
policy reset timing 和 debug schema 仍由 planner shell 控制；failed-dig recovery
decision 不改变旧 switch reason、terminal reason 或 planner trace schema。

## Dig Lifecycle Facts Assembly Slice

`dig_lifecycle` 新增 `build_dig_lifecycle_facts()`，负责把 planner shell 显式采样的
dig lifecycle 输入投影成 `DigLifecycleFacts`：当前 bucket mass / dig distance、
boundary-event metrics 对 carry mass / distance 的旧 fallback、semantic boundary
profile flag、boundary dig-complete flag、coverage terminal-stop flag、dig runtime
counters、coverage payload-gain state、active coverage corridor entry/exit xz，以及
bucket-tip xz。该 helper 不接收 planner `self`，不读取 observation，不调用 coverage
facade，不写 planner state，也不触发 failed-dig recovery 或 coverage side effect。

planner `_dig_lifecycle_facts()` 作为旧 private facade 保留在 shell 内，只负责按旧
来源采样 obs、boundary event、boundary detector profile、coverage active corridor 和
runtime counters，然后转调 `build_dig_lifecycle_facts()`。dig branch order、
`_dig_to_carry_reason` 写回、`_dig_bad_replan_count` /
`_dig_exit_guard_replan_count` 写回、coverage reject/complete、
`_restart_after_failed_dig()`、`_set_skill()`、policy reset timing 和 debug/summary
schema 仍由 planner shell 拥有。

同一 Facts Assembly 边界后续新增 `DIG_LIFECYCLE_FACT_FIELDS` 和
`build_dig_lifecycle_facts_from_mapping()`，把 `_dig_lifecycle_facts()` 中的显式
facts mapping 字段表与 `build_dig_lifecycle_facts()` 调用收回 `dig_lifecycle`
capability。planner 旧 private facade 仍按旧来源采样 mass/distance、boundary
metrics/flag、semantic profile flag、coverage terminal flag、dig runtime counters、
coverage payload-gain state、active corridor 和 bucket-tip pose，再按字段表转调
builder。

同一 Facts Assembly 边界本轮继续新增
`build_dig_lifecycle_facts_from_observation_view()` 与
`DigLifecycleGateService.facts_from_observation_view()`，把 observation-view source
projection 收回 `dig_lifecycle` capability。planner `_dig_lifecycle_facts()` 旧
private facade 不再在大文件内逐项拼 `DIG_LIFECYCLE_FACT_FIELDS` values dict；它只构造
`PlannerSnapshot.view`，显式传入 boundary event、semantic profile flag、coverage
terminal flag、dig runtime counters、coverage payload-gain state 和 active corridor，
再调用 service projection。该 service entry point 不接收 planner `self`，不调用
coverage facade，不读取 raw observation，不执行 transition decision，不写 planner
state，也不触发 coverage reject/complete 或 failed-dig recovery。

本切片不改变 boundary metrics fallback key、active corridor geometry、bucket-tip xz
projection、`exit_overshoot_low_payload` / `bad_dig_low_payload` /
`complete_low_payload` / `dig_to_carry_*` reason 字符串、threshold、branch order、
counter 写回时机、coverage side effect、failed-dig recovery、debug/summary schema
或 rollout 输出。

## Dig Lifecycle Transition Runtime Slice

`DigLifecycleGateService` 继续负责 dig lifecycle 的纯 gate/outcome 能力。本切片
新增 `DigTransitionRuntimeFacts` / `DigTransitionRuntimeOutcome`，把 dig 分支中
caller-provided gate 布尔值到旧 outcome、counter 名称、coverage reject reason、
failed-dig reason 和 carry switch reason 的纯分类迁入 service。service 只接收
planner 已经按旧短路顺序采集好的布尔事实和 `_dig_to_carry_ready()` 写出的 reason，
不读取 obs，不接收 boundary event，不调用任何 `_dig_*` facade，不写 planner state，
不 reject/complete coverage，不调用 `_restart_after_failed_dig()` 或 `_set_skill()`。

后续 slice 在同一 `dig_lifecycle` capability 中新增
`DigTransitionRuntimeRequest` 和 `dig_transition_runtime_request()`，负责把
exit-guard gate result 投影成 dig runtime facts 与是否应按旧短路顺序继续调用
bad-replan gate 的 request bool。request 还提供
`should_check_complete_boundary_low_payload(bad_replan_ready)`、
`should_check_dig_to_carry(...)` 和 `facts_with_gate_results()`，用于保留
`exit_guard -> bad_replan -> complete_low_payload -> carry` 的旧求值顺序。service
不读取 observation，不调用 `_dig_bad_replan_ready()`、
`_dig_complete_boundary_low_payload()` 或 `_dig_to_carry_ready()`，不写 dig counters，
不 reject/complete coverage，不执行 failed-dig recovery，也不调用 `_set_skill()`。

planner 大文件仍负责：

- dig branch order 和 gate 短路求值：
  `exit_guard -> bad_replan -> complete_low_payload -> carry`
- `_dig_exit_guard_replan_count` / `_dig_bad_replan_count` 的最终写回
- `_reject_active_coverage_corridor()`、`_restart_after_failed_dig()`、
  `_complete_cell_entry_dig()`、`_complete_coverage_dig()`、`_set_skill()`
- `_dig_to_carry_ready()` 对 `_dig_to_carry_reason` 的 legacy 写回时机
- failed-dig stop/retry/pre-dig-align 执行、policy reset timing、debug/summary schema
  和 rollout trace

本切片不改变 `exit_overshoot_low_payload`、`bad_dig_low_payload`、
`complete_low_payload`、`dig_complete_low_current_payload`、
`dig_to_carry_*` reason 字符串，不改变 complete-low payload 复用
`_dig_bad_replan_count` 的既有行为，不改变 branch order、threshold、coverage
side effect、failed-dig recovery、policy reset timing 或 debug/summary schema。

## Dig Transition Counter Projection Slice

`DigLifecycleGateService` 继续作为 dig lifecycle 纯 outcome/projection 边界。本切片
新增 `DigTransitionRuntimeProjection` 和 `dig_transition_runtime_projection()`，把
`DigTransitionRuntimeOutcome.counter` 到 `_dig_exit_guard_replan_count` /
`_dig_bad_replan_count` increment，以及 failed-dig restart / carry handoff action
判断的纯投影迁入 service。service 只接收已经分类好的
`DigTransitionRuntimeOutcome`，不读取 obs，不接收 planner `self`，不调用
`_reject_active_coverage_corridor()`、`_restart_after_failed_dig()`、
`_complete_cell_entry_dig()`、`_complete_coverage_dig()` 或 `_set_skill()`，不写
planner state，不 reset policy，也不写 debug/summary schema。

planner dig branch 仍负责按旧顺序执行全部 side effect：

- 应用 `_dig_exit_guard_replan_count` / `_dig_bad_replan_count` increment
- `_reject_active_coverage_corridor()` 和 `_restart_after_failed_dig()`
- `_complete_cell_entry_dig()`、`_complete_coverage_dig()` 与 `_set_skill("carry")`
- `_dig_to_carry_ready()` 对 `_dig_to_carry_reason` 的 legacy 写回时机
- failed-dig recovery、policy reset timing、debug/summary schema 和 rollout trace

本切片不改变 branch order、threshold、switch reason、terminal reason、coverage
reject/complete side effect、complete-low payload 复用 bad-replan counter 的既有行为、
policy reset timing、debug/summary schema 或 rollout 输出。

## Dig Transition Application Facade Slice

`DigLifecycleGateService` 已经负责 `DigTransitionRuntimeProjection` 的纯建议。本切片把
planner dig branch 中 projection 之后的 shell-owned application 集中到旧 private
facade：

- `_apply_dig_transition_runtime_projection()`

该 facade 只应用 service 已返回的 projection：先按旧时机写回
`_dig_exit_guard_replan_count` / `_dig_bad_replan_count` counter 增量，然后在同一 shell
边界内执行既有 failed-dig side effect
`_reject_active_coverage_corridor()` + `_restart_after_failed_dig()`，或 carry handoff side
effect `_complete_cell_entry_dig()` + `_complete_coverage_dig()` + `_set_skill("carry",
...)`。它不重新分类 outcome，不调用任何 gate，不读取 observation 以外的新 facts，不
reset policy，也不写 debug schema。

planner dig 分支仍负责旧有调用顺序：按 request 决定 gate 短路求值，调用
`dig_transition_runtime()` / `dig_transition_runtime_projection()`，然后调用该 shell
application facade。service 仍不接收 planner `self`，不拥有 coverage side effect、不
执行 failed-dig recovery、不调用 `_set_skill()`。本切片只是把 projection 到 shell
lifecycle side effects 的应用细节从主 branch 移入同一 planner shell 的私有 facade，
让主 state-machine branch 更接近“生成 projection -> 应用 projection -> return”的薄
结构。

本切片不改变 dig branch order、counter 增量、counter 写回早于 reject/restart 的旧时机、
coverage reject/complete side effect、failed-dig recovery、carry switch reason、
terminal reason、policy reset timing、debug/summary schema、token contract 或 rollout
输出。

## Failed-Dig Recovery Decision Apply Facade Slice

同一 dig lifecycle 边界内的后续 consolidation 新增
`_apply_failed_dig_recovery_decision()`，把
`DigLifecycleGateService.failed_dig_recovery()` 返回的
`FailedDigRecoveryDecision` 应用收口到 planner shell。`_restart_after_failed_dig()` 仍按
旧时机调用 service，并传入原始 failed-dig reason、`FailedDigRecoveryFacts` 和当前
runtime config；service 继续只负责纯 decision：`pre_dig_align`、`stop` 或 `dig` retry
及对应旧 switch/terminal reason。

该 facade 只执行 shell-owned side effect：`pre_dig_align` decision 调用
`_restart_pre_dig_align()`，`stop` decision 调用 `_stop_after_failed_dig()` 并保留 service
给出的 switch/terminal reason，默认 retry 调用 `_restart_dig_with_new_cut()`。coverage
reject 仍由 `_apply_dig_transition_runtime_projection()` 在调用
`_restart_after_failed_dig()` 之前执行；stop path 的 coverage event 与 terminal-stop
request 仍由 `_apply_failed_dig_stop_state()` 承接。

本切片不改变 failed-dig recovery branch order、`dig_to_pre_dig_align_*` /
`dig_failed_stop_*` / `dig_retry_*` switch reason、`dig_failed_*` terminal reason、
coverage reject/stop side effect、policy reset timing、debug/summary schema、token
contract 或 rollout 输出。

## Failed-Dig Stop Projection Slice

`DigLifecycleGateService` 继续负责 dig lifecycle 的纯 recovery/outcome payload
projection。本切片新增 `FailedDigStopFacts` 和 `FailedDigStopState`，把
`_stop_after_failed_dig()` 中的 stop switch reason、terminal reason、
`failed_dig_stop` coverage event name，以及 coverage event extra payload
`reason` / `payload_gain_kg` / `current_bucket_mass_kg` / `dig_best_mass_kg` /
`dig_step_count` 的纯组装迁入 service。

planner `_stop_after_failed_dig()` 作为旧 private facade 保留在 shell 内，仍负责：

- 采样 active coverage corridor 和当前 bucket mass
- 调用 `failed_dig_stop_state()`
- 写回 `_switch_reason`
- 调用 `_record_coverage_decision_event()`
- 调用 `_request_coverage_terminal_stop()`

service 不接收 planner `self`，不读取 observation，不查 coverage corridor，不记录
coverage trace，不 request terminal stop，不调用 `_set_skill()`，不 reset policy，
不写 debug schema。

同一切片后续新增 `FAILED_DIG_STOP_FACT_FIELDS` 和
`build_failed_dig_stop_facts_from_mapping()`，把 planner shell 中已有 failed-dig stop
runtime fields 到 `FailedDigStopFacts` 的投影收回 `dig_lifecycle_transition`
capability。字段表只覆盖 shell-owned runtime fields：
`_coverage_current_payload_gain_kg`、`_dig_best_mass_kg` 和 `_dig_step_count`；
caller 仍显式传入 failure reason、当前 obs 采样出的 bucket mass，以及 recovery
decision 已给出的 optional switch/terminal reason。这样 service 统一负责 `float()` /
`int()` / optional reason coercion 和 facts contract，planner 仍负责 observation 采样与
全部 side effect。

同一边界的后续 runtime-builder 收口新增
`build_failed_dig_stop_facts_from_runtime()`，让 planner `_stop_after_failed_dig()` 不再
遍历 `FAILED_DIG_STOP_FACT_FIELDS` 或内联构造 facts mapping。planner 只把显式 runtime
输入交给 builder：failure reason、`_coverage_current_payload_gain_kg`、
`_dig_best_mass_kg`、当前 obs 采样出的 bucket mass、`_dig_step_count`，以及 optional
switch/terminal reason。旧 `build_failed_dig_stop_facts_from_mapping()` 保留为
compatibility facade，并转调同一 runtime builder；这不新增模块，不复制 threshold，也不
让 service 拥有 observation、coverage trace 或 terminal-stop side effect。

后续同一边界继续收口 state 应用：`_apply_failed_dig_stop_state()` 作为 planner shell
内的应用 facade，统一执行 `FailedDigStopState` 的 `_switch_reason` 写回、
coverage decision event 记录和 terminal-stop request。`_stop_after_failed_dig()` 仍按旧
时机在调用 service 前采样 active corridor，并把该 corridor 显式传给 apply facade；
service 仍不拥有 coverage trace、terminal-stop request 或 planner mutable state。

本切片不改变 `dig_failed_stop_*` switch reason fallback、
`dig_failed_*` terminal reason fallback、explicit recovery reason 优先级、
payload-gain `max(coverage_current_payload_gain_kg, dig_best_mass_kg,
current_bucket_mass_kg, 0.0)` 语义、`failed_dig_stop` event name、terminal stop
`replace=True`、failed-dig recovery branch order、coverage side effect、policy reset
timing、debug/summary schema 或 rollout trace。

## Dig Lifecycle Transition Module Boundary Slice

`dig_lifecycle_transition` 作为 dig lifecycle branch transition request、outcome
classification、counter projection 和 failed-dig stop payload projection 的稳定
source-of-truth。`dig_lifecycle` 只保留这些 transition runtime symbols 的
compatibility re-export，并继续拥有 dig lifecycle config、facts、progress、
readiness gate、failed-dig recovery decision、runtime reset/status projection 和
entry-runtime projection。

本切片是责任边界修正，不新增调度语义：原
`DigTransitionRuntimeFacts` / `DigTransitionRuntimeRequest` /
`DigTransitionRuntimeOutcome` / `DigTransitionRuntimeProjection`、
`dig_transition_runtime_request()` / `dig_transition_runtime()` /
`dig_transition_runtime_projection()` 以及 `FailedDigStopFacts` /
`FailedDigStopState` / `failed_dig_stop_state()` 原样迁入
`dig_lifecycle_transition`。`DigLifecycleGateService` 通过继承
`DigLifecycleTransitionService` 保留旧 method API，旧 `dig_lifecycle` import 继续可用以
保护现有调用方。新模块只依赖标准库 dataclass，不 import planner shell、
`dig_lifecycle`、observation/parser、token/schema 或 profile source-of-truth，因此不形成
循环 import，也不复制 threshold、reason 字符串或 contract 语义。

planner shell 仍负责 dig branch order、按 request 的 gate-request bool 和旧短路时机
调用 `_dig_exit_guard_ready()` / `_dig_bad_replan_ready()` /
`_dig_complete_boundary_low_payload()` / `_dig_to_carry_ready()`、
`_dig_exit_guard_replan_count` / `_dig_bad_replan_count` 实际写回、coverage
reject/complete side effect、failed-dig recovery execution、`_set_skill()`、policy
reset timing、debug/summary schema 和 rollout trace。本切片不改变 switch reason、
terminal reason、coverage reject reason、counter increment、payload-gain projection、
branch order、threshold、policy reset timing、debug/summary schema、token contract 或
rollout 输出。

## Dig Lifecycle Entry Runtime Projection Slice

`DigLifecycleGateService` 继续负责 dig lifecycle runtime 的纯状态投影。本切片新增
`DigLifecycleEntryRuntimeFacts` 和 `DigLifecycleEntryRuntimeState`，把进入或重启
dig attempt 时重复出现的 runtime reset payload 迁入 service：`dig_step_count`、
`dig_best_mass_kg`、`dig_mass_plateau_count`、`dig_to_carry_reason` 和
`coverage_current_payload_gain_kg` 清回 legacy 默认值，同时保留 caller 已维护的
`dig_bad_replan_count` 与 `dig_exit_guard_replan_count`。

planner `_reset_dig_entry_runtime()` 作为旧 shell 内的薄应用入口，仍负责读取当前
replan counters、调用 `entry_runtime_state()`，并把返回值写回既有 planner fields。
`_set_skill("dig")`、`_restart_pre_dig_align()` 和 `_restart_dig_with_new_cut()` 只在
旧时机调用该入口；active skill 写回、switch reason、policy reset、
coverage active corridor invalidation、pending dig-cut invalidation 和 dig-cut plan
clear side effect 仍由 planner shell 拥有。

同一边界内的后续 consolidation 新增
`DIG_LIFECYCLE_ENTRY_RUNTIME_FACT_FIELDS` 和
`build_dig_lifecycle_entry_runtime_facts_from_mapping()`，把
`_reset_dig_entry_runtime()` 中的 bad-replan / exit-guard replan counter facts
投影收回 `dig_lifecycle` capability。planner 旧 private facade 只按字段表采样当前
counter 后调用 builder 和 `entry_runtime_state()`；counter 的 `int()` coercion 和
facts contract 由 `dig_lifecycle` 统一负责。

后续同一边界继续收口 runtime state 写回：
`_apply_dig_lifecycle_entry_runtime_state()` 作为 planner shell 内的应用 facade，
统一落地 `DigLifecycleEntryRuntimeState` 中的 step/best-mass/plateau/reason、
coverage payload gain 和保留后的 replan counters。`_reset_dig_entry_runtime()` 只负责
按旧时机采样 facts、调用 service，并把 state 交给 apply facade；service 仍不拥有
planner mutable state 或 scheduler side effect。

service 不接收 planner `self`，不调用 `_set_skill()`，不 reset policy，不读取
observation，不修改 active corridor，不 invalidate pending plan，不写 debug schema。

本切片不改变 dig entry / retry reset timing、`dig_bad_replan_count` 与
`dig_exit_guard_replan_count` 的保留语义、failed-dig recovery branch order、
switch reason、terminal reason、policy reset timing、debug/summary schema、token
contract 或 rollout 输出。

## Dig Lifecycle Runtime Status Projection Slice

`DigLifecycleGateService` 继续作为 dig lifecycle gate/progress/outcome 的
service-object 边界。本切片新增 `DigLifecycleRuntimeStatusState` 和
`DigLifecycleRuntimeStatusSnapshot`，负责把 planner shell 已维护的 dig lifecycle
runtime state 投影成 debug-state 与 rollout-summary 共同需要的 facts：
failed-dig replan next skill、dig step/best-mass/plateau counters、dig-to-carry
reason、bad-dig replan count 和 exit-guard replan count。

后续同一切片新增 `DIG_LIFECYCLE_RUNTIME_STATUS_FIELDS` 和
`build_dig_lifecycle_runtime_status_state_from_mapping()`，把 planner 当前
`_dig_*` runtime counters/reason 到 `DigLifecycleRuntimeStatusState` 的投影收回
dig lifecycle capability。planner 旧 private facade 只按字段表采样当前 state 后
调用 builder；`int` / `float` / `str` coercion 和 status-state contract 由
`dig_lifecycle` 统一负责。

planner 大文件只保留薄 facade：

- `_dig_lifecycle_runtime_status_snapshot()`

planner shell 仍负责 dig progress counter 写回、dig branch order、exit guard /
bad-dig / complete-low-payload / carry gate 调用顺序、failed-dig recovery 执行、
coverage reject/complete、`_set_skill()`、policy reset timing、trace 写入，以及
public debug/summary schema 展开。service 不接收 planner `self`，不调用
`_set_skill()`，不 reset policy，不写 debug schema，不读取 observation，也不改变
任何 lifecycle counter。

本切片不改变 debug-state 或 rollout-summary key/key order、failed-dig next-skill
字符串、dig-to-carry reason、replan counter 数值、branch order、threshold、
coverage side effect、switch/terminal reason、policy reset timing 或 rollout 输出。

## Dig Lifecycle Runtime Reset Slice

`DigLifecycleGateService` 新增 `initial_runtime_state()`，继续复用
`DigLifecycleRuntimeStatusState`，负责投影 dig lifecycle runtime 的 legacy reset
默认值：dig step count、best mass、mass plateau count、dig-to-carry reason、
bad-dig replan count 和 exit-guard replan count。service 只返回显式 runtime state；
不接收 planner `self`，不调用 `_set_skill()`，不 reset policy，不写 HDF5/checkpoint，
不写 debug schema，不读取 observation，不执行 failed-dig recovery，也不更新 coverage
state。

planner `_reset_dig_lifecycle_runtime()` 和 `_apply_dig_lifecycle_runtime_state()`
作为旧 private facade 保留在 shell 内，只负责调用 service 并把返回 state 应用到
既有 `_dig_*` lifecycle 字段。`reset()` 的 policy reset、boundary detector reset、
active skill 选择、switch reason、pre-dig-align reset、cell-entry reset、dig-cut /
depth-profile reset、return conditioning/handoff reset 和 coverage reset 顺序仍由
planner shell 拥有。

本切片不改变 reset timing、初始 active skill、switch reason `reset`、dig branch
order、dig progress update、failed-dig recovery、coverage reject/complete side
effect、dig-to-carry reason 写回时机、debug/summary schema、policy reset timing 或
rollout 输出。dig 分支内 `return -> dig` / failed-dig / clear-plan 等路径中的旧
counter 清理仍属于 scheduler transition side effects，本轮不混合迁移。

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

## Dig-Start Alignment Facts Assembly Slice

`dig_start_alignment` 新增 `build_dig_start_alignment_facts()`，负责把 planner
shell 显式采样的 pre-dig alignment 输入投影成 `DigStartAlignmentFacts`：
qpos/qvel/target qpos 的 legacy float32 reshape、entry error、bucket dig-area pose、
surface-depth/contact facts，以及 cycle/hold runtime counters。该 helper 不接收
planner `self`，不读取 observation，不访问 coverage corridor，不调用 `_set_skill()`，
不 reset policy，不写 planner state，也不组装 debug schema。

planner `_dig_start_alignment_facts()` 作为旧 private facade 保留在 shell 内；早期
过渡阶段只负责按旧来源采样 obs/default qpos/qvel、entry-error facade、bucket pose、
surface/contact facts 和 runtime counters，然后转调
`build_dig_start_alignment_facts()`。后续 observation-view source projection 阶段把
bucket pose / surface-depth / contact 采样收回 alignment capability，planner facade
只保留 snapshot 创建、entry-error 采样时机和 override/counter 传递。

同一 Facts Assembly 边界后续新增 `DIG_START_ALIGNMENT_FACT_FIELDS` 和
`build_dig_start_alignment_facts_from_mapping()`，把显式 facts mapping 的字段表和
`build_dig_start_alignment_facts()` 调用收回 `dig_start_alignment` capability。
该 mapping builder 不读取 observation，不调用 coverage service，不写 planner
state，也不改变 qpos/qvel/target qpos 的 float32 reshape source-of-truth。

同一 Facts Assembly 边界后续新增
`build_dig_start_alignment_facts_from_observation_view()` 和
`DigStartAlignmentService.facts_from_observation_view()`，把
`PlannerObservationView` 到 `DigStartAlignmentFacts` 的 source projection 收回
alignment capability。该 projection 保留旧输入来源：qpos/qvel 仍从 raw
`view.obs.get("qpos" / "qvel", zeros)` 进入既有 float32 reshape，bucket pose /
surface-depth / contact 仍复用 `snapshots` legacy helper；planner facade 只负责按旧
时机创建 snapshot、在需要时调用 `_pre_dig_align_entry_error(obs)` 并显式传入
entry-error、target/qpos/qvel override、cycle index 和 hold count。service 不读取
coverage corridor，不计算 entry-error，不写 planner state，也不改变 readiness /
outcome gate 顺序。

本切片不改变 pre-dig-align readiness/outcome branch order、surface guard、
start-envelope gate、entry-close handoff、entry-intent handoff、timeout handoff、
hold counter 写回、coverage reject/replan、switch reason、policy reset timing、
debug/summary schema 或 rollout 输出。

## Dig-Start Alignment Context Module Boundary Slice

新增模块：

- `testbed/planner/dig_start_alignment_context.py`

该 module 是 pre-dig-align `DigStartAlignmentConfig`、`DigStartAlignmentFacts`、
`DIG_START_ALIGNMENT_RUNTIME_CONFIG_FIELDS`、`DIG_START_ALIGNMENT_FACT_FIELDS` 以及
对应 runtime config / facts mapping builders 的 source-of-truth。它只负责把 planner
shell 显式传入的 config mapping 和 facts mapping 投影成 typed dataclass，保留既有
legacy dtype、shape、default qpos/qvel、target qpos optional、entry error、
surface/contact、cycle index 和 hold count 语义。

`testbed.planner.dig_start_alignment` 继续 re-export 这些 symbols 作为旧兼容入口；
planner shell 和新增测试直接引用 `dig_start_alignment_context`，避免后续把 numeric
target/action、readiness gate、timeout handoff、outcome 和 runtime projection 拆成不同
capability module 时出现互相 import 的循环依赖。

本切片不新增 gate、threshold、branch order、switch reason、debug/summary schema、
token contract、policy reset timing 或 rollout 语义；也不让 context module 读取
observation、持有 planner mutable state、调用 `_set_skill()`、reset policy、写
HDF5/checkpoint 或写 debug schema。后续如果继续拆分 readiness/action 能力，应复用该
context module 的 Config/Facts，而不是复制字段表或 builder。

## Pre-Dig Alignment Entry-Error Evaluation Composition Slice

`dig_start_alignment_context` 新增
`build_dig_start_alignment_entry_error_facts_from_observation_view()`，把
`PlannerObservationView` 中的 bucket-tip dig-area pose 投影为
`DigStartAlignmentEntryErrorFacts`。该 projection 继续复用 `snapshots`
里的 `bucket_tip_dig_area_pose_from_obs()`，不复制 env-state schema index 或
legacy fallback。

`DigStartAlignmentService` 新增 `entry_error_from_observation_view()`，把上述 facts
projection 与既有 `entry_error()` / `dig_start_alignment_entry_error()` 组合起来。
service 只消费 caller 显式传入的 active corridor entry x/z；不读取 coverage service
state，不选择 corridor，不读取 planner `self`，不写 runtime state，不调用
`_set_skill()`，不 reset policy，也不写 debug schema。

planner `_pre_dig_align_entry_error()` 作为旧 private facade 保留，继续负责在旧时机
读取 `_coverage_active_corridor()` 并把 active corridor entry x/z 投影为显式 tuple；
bucket-tip observation facts 与 entry-error 公式的 source-of-truth 已迁入 alignment
capability。planner 仍拥有所有调用方的采样时机、runtime 写回、branch order、
coverage reject/replan、policy reset timing 和 debug schema。

本切片不改变 bucket-tip x/z source、无 active corridor 返回 NaN 的旧语义、
非有限坐标结果、entry-error 采样时机、branch order、threshold、switch reason、
terminal reason、policy reset timing、debug/summary schema、token contract 或 rollout
输出。

## Dig-Start Alignment Target Facts Projection Slice

planner 的 `_pre_dig_align_target_from_token()` 通过 `_dig_start_alignment_facts()`
复用 `build_dig_start_alignment_facts()` 的 legacy qpos fallback / float32 reshape，
再把 `facts.qpos` 传给 `DigStartAlignmentService.target_from_token()`。该 slice 不新建
module，不改变 `target_from_token()` 作为 target qpos 数值计算 source-of-truth 的职责。

planner 仍负责 `_ensure_dig_cut_plan_for_cycle()`、dig-cut token 读取、是否更新
`_pre_dig_align_target_qpos`、target state 写回时机、action dispatch、branch order、
switch reason、policy reset timing 和 debug schema。后续 runtime consolidation 新增
`target_runtime_state()`，把已计算出的 target qpos 投影成新的
`DigStartAlignmentRuntimeState`；planner shell 仍决定是否调用该投影并通过
`_apply_pre_dig_align_runtime_state()` 执行实际写回。target projection 不采样 entry-error；
facade 显式传入 `NaN` entry error 只用于避免 facts builder 的默认 entry-error 采样路径。

本切片不改变 qpos fallback/shape/dtype、short-token fallback、controlled dims、
entry-intent hold dims、bucket target qpos、target qpos state update timing、token
contract、debug/summary schema 或 rollout 输出。

## Pre-Dig Alignment Target Evaluation Composition Slice

`DigStartAlignmentActionService` 新增
`target_from_token_from_observation_view()`，把 pre-dig-align target 路径中的
observation-view facts projection 与既有 `target_from_token()` 组合收回 action
service。该入口继续复用
`build_dig_start_alignment_facts_from_observation_view()` 的 legacy qpos fallback /
float32 reshape，只消费 caller 显式传入的 dig-cut token、`PlannerObservationView`、
config、cycle index 和 hold count；不读取 planner `self`，不 ensure dig-cut plan，
不采样 entry-error，不写 target runtime state，不调用 `_set_skill()`，不 reset policy，
也不写 debug schema。

planner `_pre_dig_align_target_from_token()` 作为旧 private facade 保留，继续负责
dig-cut token caller 传入、`update_state` 分支、target runtime apply、action dispatch
顺序、policy reset timing 和 debug schema。`_pre_dig_align_target()` 仍负责
`_ensure_dig_cut_plan_for_cycle()` 和读取 `_dig_cut_tokens`。

本切片不改变 qpos fallback/shape/dtype、short-token fallback、controlled dims、
entry-intent hold dims、bucket target qpos、target qpos state update timing、
entry-error 不采样语义、token contract、branch order、switch reason、terminal reason、
debug/summary schema 或 rollout 输出。

## Dig-Start Alignment Action Projection Slice

`DigStartAlignmentService` 新增 `AlignmentActionDecision` 和 `action_decision()`，
负责从 `DigStartAlignmentFacts` 与 `DigStartAlignmentConfig` 纯计算 pre-dig-align
servo action、target-vs-current qpos error，以及已采样的 entry error projection。
该 service 方法不接收 planner `self`，不递增 step counter，不读取 observation，不
ensure dig-cut plan，不调用 `_set_skill()`，不 reset policy，也不写 planner state。

同一 action/runtime 边界后续新增 `action_runtime_state()`，把
`AlignmentActionDecision` 中的 alignment error 与已采样 entry error 投影成新的
`DigStartAlignmentRuntimeState`。planner shell 仍负责 action enabled guard、step
counter 递增、surface-guard zero-action 短路、target qpos 获取和实际
`_apply_pre_dig_align_runtime_state()` 写回；service 不拥有 action dispatch 或 planner
side effect。

planner `_pre_dig_align_action()` 作为旧 private facade 保留在 shell 内，仍负责
enabled guard、step counter 递增、surface-guard zero-action 短路、target plan/target
qpos 获取、entry-error 采样、`_pre_dig_align_error` 与
`_pre_dig_align_entry_error_m` 写回时机，以及最终 action 返回。

本切片不改变 action clip/sign、controlled dims、surface-guard zero-action 行为、
target qpos 更新时机、entry-error 采样来源、branch order、switch reason、policy
reset timing、debug/summary schema 或 rollout 输出。

## Pre-Dig Alignment Action Decision Evaluation Composition Slice

`DigStartAlignmentActionService` 新增 `action_decision_from_observation_view()`，把
pre-dig-align action 路径中的 observation-view facts projection 与既有
`action_decision()` 组合收回 action service。该入口继续复用
`build_dig_start_alignment_facts_from_observation_view()`，只消费 caller 显式传入的
`target_qpos`、entry-error、`PlannerObservationView`、config、cycle index 和 hold
count；不读取 planner `self`，不选择 target，不采样 entry-error，不递增 step
counter，不写 runtime state，不调用 `_set_skill()`，不 reset policy，也不写 debug
schema。

planner `_pre_dig_align_action()` 作为旧 private facade 保留，继续负责 enabled guard、
step counter 递增、surface-guard zero-action 短路、`_pre_dig_align_target()` 的旧调用
时机和 target runtime 写回、`_pre_dig_align_entry_error()` 的采样时机、snapshot 构造、
action decision runtime apply、policy action 返回、policy reset timing 和 debug
schema。

本切片不改变 qpos/qvel source、target qpos source、entry-error source、action
clip/sign、controlled dims、surface-guard zero-action 行为、step counter 更新时机、
target qpos 更新时机、branch order、switch reason、terminal reason、policy reset
timing、debug/summary schema、token contract 或 rollout 输出。

## Dig-Start Alignment Action Module Boundary Slice

新增模块：

- `testbed/planner/dig_start_alignment_action.py`

该 module 承载 pre-dig-align target/action 数值能力的稳定责任边界：
`AlignmentActionDecision`、`DigStartAlignmentActionService` 和 `pd_servo_action()`。
它复用 `dig_start_alignment_context` 的 `DigStartAlignmentConfig` /
`DigStartAlignmentFacts`，负责从 dig-cut token 投影 target qpos、应用 qpos min/max、
bucket target、controlled-dim / entry-intent mask，以及基于 PD servo 计算 action、
target-vs-current qpos error 和已采样 entry-error projection。

`DigStartAlignmentService` 继承 `DigStartAlignmentActionService` 并继续 re-export 旧
action symbols，保留旧 private facade 和测试调用面。planner shell 直接引用
`dig_start_alignment_action.pd_servo_action()`，但仍负责 `_pre_dig_align_action()` 的
enabled guard、step counter 递增、surface-guard zero-action 短路、target plan/target
qpos 获取、entry-error 采样、`_pre_dig_align_error` /
`_pre_dig_align_entry_error_m` 写回，以及 action dispatch。`bootstrap` 复用同一个
`pd_servo_action()` source-of-truth，不通过兼容 shell 间接导入。

本切片不迁 entry-error 几何、readiness gates、outcome classification、runtime
projection 或 debug snapshot；不改变 token contract、short-token fallback、action
clip/sign、controlled dims、entry-intent hold dims、bucket target qpos、target qpos
更新时机、surface-guard zero-action 行为、branch order、switch reason、policy reset
timing、debug/summary schema 或 rollout 输出。action module 不接收 planner `self`，
不读取 observation，不调用 `_set_skill()`，不 reset policy，不写 HDF5/checkpoint，也
不写 debug schema。

## Dig-Start Alignment Readiness Facts Projection Slice

planner 的 pre-dig-align readiness/handoff facades 统一通过
`build_dig_start_alignment_facts()` / `_dig_start_alignment_facts()` 装配
`DigStartAlignmentFacts`，不再在 planner 大文件内手写 qpos/qvel reshape 或临时
facts dataclass 构造。该 slice 覆盖 `_pre_dig_align_ready()`、
`_pre_dig_align_entry_close_handoff_ready_for_state()` 和
`_pre_dig_align_timeout_can_handoff()` 中的 facts projection。

同一边界内的后续 consolidation 把 entry-close handoff、start-envelope state
readiness，以及 timeout sampled-entry-error 路径的 facts projection 收回既有
`DigStartAlignmentService` / `PreDigAlignTimeoutHandoffRequest`。planner 旧 private
facade 只负责在旧时机采样 obs/qpos/qvel/bucket pose/entry error、调用 service
projection 和 gate，并把 runtime 字段写回；不在 planner 大文件内直接构造
handoff/readiness facts。

start-envelope state readiness 的后续 consolidation 新增
`DigStartAlignmentService.start_envelope_facts_from_observation_view()`，把
`PlannerObservationView` 到 start-envelope gate facts 的 source projection 收回
readiness capability。该 projection 刻意只读取 start-envelope gate 需要的 action
dim、caller-provided qpos、entry error 和 bucket dig-area pose；qvel 仍走旧
`start_envelope_facts()` 的 zero default，不读取 observation qvel，也不采样
surface/contact facts。planner `_pre_dig_align_start_envelope_ready_for_state()` 只负责
按旧时机创建 snapshot、传入 qpos/entry-error，然后调用同一个
`start_envelope_ready()` gate。

timeout sampled-entry-error 路径的后续 consolidation 新增
`PreDigAlignTimeoutHandoffRequest.facts_with_entry_sampling_from_observation_view()`，
把 sampled path 中 qpos/qvel fallback、bucket dig-area pose 和 entry-error 到
timeout handoff facts 的 projection 收回 readiness request。该 projection 仍使用
observation 中的原始 qpos/qvel 值或旧的 zero fallback，再交给既有
`build_dig_start_alignment_facts()` 做 float32 reshape；no-entry-gate 路径继续通过
`facts_without_entry_sampling()` 复用既有 entry-error state，不读取 observation。

planner 仍负责 pre-dig-align enabled guard、target qpos 获取、entry-error 采样时机、
timeout no-entry-gate 路径复用既有 `_pre_dig_align_entry_error_m` 的旧语义、
ready/start-envelope/entry-intent/timeout runtime 字段写回、hold counter 写回、
coverage reject/replan、`_set_skill()`、policy reset timing 和 debug schema。

本切片不改变 qpos/qvel fallback、entry-error 采样来源、timeout reason、
start-envelope readiness 写回时机、entry-intent handoff sticky 写回、hold counter、
branch order、switch reason、threshold、debug/summary schema 或 rollout 输出。

## Dig-Start Alignment Timeout Handoff Request Slice

`DigStartAlignmentService` 继续负责 pre-dig alignment timeout handoff 的纯 request
与 decision projection。本切片新增 `PreDigAlignTimeoutHandoffRequest`，把
`_pre_dig_align_timeout_can_handoff()` 中的 timeout-entry threshold 解析和
no-entry-gate / sampled-entry-error 路径选择迁入 service。request 只返回是否需要
planner 采样 fresh entry error，以及 no-entry-gate 路径应复用的当前
`_pre_dig_align_entry_error_m` facts；不读取 observation，不调用
`_pre_dig_align_entry_error()`，不写 planner state。

planner `_pre_dig_align_timeout_can_handoff()` 作为旧 private facade 保留在 shell 内，
仍负责清空 timeout reason、按 request 在旧时机采样 entry error、调用
`timeout_can_handoff()`、写回 `_pre_dig_align_entry_error_m`、
`_pre_dig_align_start_envelope_ready`、sticky
`_pre_dig_align_entry_intent_handoff_ready` 和
`_pre_dig_align_timeout_handoff_reason`。

本切片不改变 timeout no-entry-gate 复用既有 entry-error state 的旧语义、
threshold fallback 顺序、entry-error 采样来源、timeout reason、start-envelope
readiness 写回时机、entry-intent handoff sticky 写回、branch order、switch reason、
policy reset timing、debug/summary schema 或 rollout 输出。

## Pre-Dig Alignment Timeout Handoff Evaluation Slice

`DigStartAlignmentReadinessService` 新增 `timeout_handoff_decision()`，把
`PreDigAlignTimeoutHandoffRequest` 的 sample/no-sample facts projection 与既有
`timeout_can_handoff()` gate 组合收回 readiness service。该方法只接收显式
request、config、action_dim、可选 `PlannerObservationView` 和已由 caller 采样的
entry-error；sample 路径继续复用
`facts_with_entry_sampling_from_observation_view()`，no-entry-gate 路径继续复用
`facts_without_entry_sampling()` 和旧 `_pre_dig_align_entry_error_m` state。

planner `_pre_dig_align_timeout_can_handoff()` 仍作为 shell facade 保留，继续负责
timeout reason 清空、按 request 在旧时机调用 `_pre_dig_align_entry_error()`、
创建 snapshot/view、以及通过 `_apply_pre_dig_align_timeout_handoff_decision()` 写回
`_pre_dig_align_entry_error_m`、`_pre_dig_align_start_envelope_ready`、sticky
`_pre_dig_align_entry_intent_handoff_ready` 和 timeout reason。service 不读取 raw
observation，不调用 entry-error sampler，不写 planner state，不调用 `_set_skill()`，
不 reset policy，也不写 debug schema。

本切片不改变 timeout threshold fallback、no-entry-gate 复用旧 entry-error state、
threshold path fresh sampling 时机、qpos/qvel fallback、bucket-pose source、timeout
reason string、start-envelope readiness 写回时机、entry-intent sticky 写回、branch
order、switch reason、policy reset timing、debug/summary schema、token contract 或
rollout 输出。

## Pre-Dig Alignment Readiness Gate Evaluation Composition Slice

`DigStartAlignmentReadinessService` 新增两个组合入口：

- `entry_close_handoff_ready_from_runtime_values()`
- `start_envelope_ready_from_observation_view()`

这两个入口只把既有 facts projection 与既有 gate 方法组合起来：
`entry_close_handoff_ready_from_runtime_values()` 继续复用
`entry_close_handoff_facts()` 和 `entry_close_handoff_ready()`；
`start_envelope_ready_from_observation_view()` 继续复用
`start_envelope_facts_from_observation_view()` 和 `start_envelope_ready()`。它们不新增
threshold、reason 或 schema 语义，也不读取 planner `self`。

planner 旧 private facade 仍保留：

- `_pre_dig_align_entry_close_handoff_ready_for_state()`
- `_pre_dig_align_start_envelope_ready_for_state()`

这些 facade 只负责传入旧时机下已经采样出的 qvel / entry-error / qpos 和
`PlannerObservationView`。planner 仍拥有 snapshot 创建、`qvel` zero override、
entry-error 采样时机、ready/outcome gate 调用顺序、runtime 写回、coverage
reject/replan、`_set_skill()`、policy reset timing 和 debug schema。

本切片不改变 first-dig entry-close handoff gate、start-envelope gate、
start-envelope facts 的 qvel zero default、bucket-pose source、qpos bounds、pose
bounds、entry-error threshold、branch order、switch reason、policy reset timing、
debug/summary schema、token contract 或 rollout 输出。

## Pre-Dig Alignment Ready Gate Evaluation Composition Slice

`DigStartAlignmentReadinessService` 新增 `ready_from_observation_view()`，把
pre-dig-align ready 路径中的 observation-view facts projection 与既有 `ready()`
gate 组合收回 readiness service。该入口继续复用
`build_dig_start_alignment_facts_from_observation_view()`，只消费 caller 显式传入的
`target_qpos`、entry-error、`PlannerObservationView`、config、cycle index 和 hold
count；不读取 planner `self`，不选择 target，不采样 entry-error，不写 runtime state，
不调用 `_set_skill()`，不 reset policy，也不写 debug schema。

planner `_pre_dig_align_ready()` 作为旧 private facade 保留，继续负责 disabled guard、
`_pre_dig_align_target()` 的旧调用时机和 target runtime 写回、
`_pre_dig_align_entry_error()` 的采样时机、snapshot 构造、ready decision runtime
apply、outcome gate 调用顺序、coverage reject/replan、`_set_skill()`、policy reset
timing 和 debug schema。

本切片不改变 qpos/qvel source、target qpos source、entry-error source、hold counter
更新、start-envelope ready 写回、entry-close handoff 写回、entry-intent handoff 写回、
ready threshold、branch order、switch reason、terminal reason、policy reset timing、
debug/summary schema、token contract 或 rollout 输出。

## Pre-Dig Alignment Surface Guard Gate Evaluation Composition Slice

`DigStartAlignmentReadinessService` 新增两个 surface guard 组合入口：

- `surface_guard_triggered_from_observation_view()`
- `surface_guard_can_handoff_from_observation_view()`

这两个入口只把既有 observation-view facts projection 与既有 surface guard gate
组合起来：trigger 路径继续复用 `build_dig_start_alignment_facts_from_observation_view()`
和 `surface_guard_triggered()`；handoff 路径继续复用同一 facts projection 和
`surface_guard_can_handoff()`。service 不读取 planner `self`，不采样 entry-error，
不写 planner runtime state，不调用 `_set_skill()`，不 reset policy，也不写 debug
schema。

planner 旧 private facade 仍保留：

- `_pre_dig_align_surface_guard_triggered_for_state()`
- `_pre_dig_align_surface_guard_can_handoff()`

这些 facade 继续负责旧时机下的 snapshot 构造、entry-error 采样、handoff gate 前的
`_pre_dig_align_entry_error_m` runtime 写回、surface guard decision apply、outcome
gate 调用顺序、coverage reject/replan、`_set_skill()`、policy reset timing 和 debug
schema。

本切片不改变 surface penetration threshold、contact fallback、surface handoff
threshold fallback、entry-error source、entry-error runtime 写回时机、branch order、
switch reason、terminal reason、policy reset timing、debug/summary schema、token
contract 或 rollout 输出。

## Dig-Start Alignment Restart Runtime Projection Slice

`DigStartAlignmentService` 继续负责 pre-dig alignment runtime 的纯 state projection。
本切片新增 `restart_runtime_state()`，把 `_restart_pre_dig_align()` 中的
pre-dig-align runtime payload 投影迁入 service：step/hold count 清零、
`replan_count` 加一、entry-intent handoff ready 清回 `False`、timeout handoff reason
清空、surface-guard triggered 清回 `False`，同时保留 timeout/completed count、
target qpos、alignment error、entry-error、start-envelope ready、entry-close handoff
ready、surface depth 和 surface-guard count。

planner `_restart_pre_dig_align()` 作为旧 shell side-effect 入口保留，仍负责 active
skill 写回、switch reason、调用 `restart_runtime_state()` 并应用返回 state、重置 dig
entry runtime、清空 active coverage corridor、重置 return next-dig event、invalidate
pending dig-cut plan 和 clear dig-cut plan。service 不接收 planner `self`，不调用
`_set_skill()`，不 reset policy，不读取 observation，不修改 coverage/pending plan，
不写 debug schema。

本切片不改变 pre-dig-align restart timing、`pre_dig_align_replan_count` 加一语义、
保留/清零字段集合、failed-dig recovery branch order、switch reason、policy reset
timing、debug/summary schema、token contract 或 rollout 输出。

## Dig-Start Alignment Enter Runtime Projection Slice

`DigStartAlignmentService` 继续作为 pre-dig alignment runtime state projection 的
source-of-truth。本切片新增 `enter_runtime_state()`，把
`_set_skill(PRE_DIG_ALIGN_SKILL_NAME)` 中的 pre-dig-align entry payload 投影迁入
service：step/hold count 清零、entry-close handoff ready 和 entry-intent handoff
ready 清回 `False`、timeout handoff reason 清空、surface-guard triggered 清回
`False`，同时保留 timeout/completed/replan count、target qpos、alignment error、
entry-error、start-envelope ready、surface depth 和 surface-guard count。

planner `_set_skill()` 仍作为 scheduler shell 的唯一 active-skill 切换入口，继续
负责 active skill 写回、switch reason、policy reset timing、其它 skill 的 lifecycle
字段重置、dig-cut plan 清理条件和 `_apply_pre_dig_align_runtime_state()` side effect。
service 不接收 planner `self`，不调用 `_set_skill()`，不 reset policy，不读取
observation，不修改 dig-cut plan，不写 debug schema。

本切片不改变 PRE_DIG_ALIGN 进入时跳过 active policy reset 的旧时序、不改变
`pre_dig_align_replan_count` 不递增语义、不改变保留/清零字段集合、不改变
`return_next_dig_event_seen` 或 dig-cut token 保留行为、不改变 branch order、switch
reason、policy reset timing、debug/summary schema、token contract 或 rollout 输出。

## Dig-Start Alignment Replan Handoff Runtime Projection Slice

`DigStartAlignmentService` 继续作为 pre-dig alignment runtime state projection 的
source-of-truth。本切片新增 `replan_handoff_runtime_state()`，把
`_try_replan_pre_dig_align_handoff()` 成功路径中的 pre-dig-align runtime payload
投影迁入 service：step/hold count 清零、completed count 和 replan count 各加一，
同时保留 timeout count、target qpos、alignment error、entry-error、start-envelope
ready、entry-close / entry-intent handoff readiness、timeout handoff reason、surface
depth、surface-guard triggered 和 surface-guard count。

planner `_try_replan_pre_dig_align_handoff()` 仍作为旧 shell side-effect 入口保留，
继续负责 planner-mode guard、coverage active corridor invalidation、pending dig-cut
plan invalidation、dig-cut plan clear、operator-prior coverage token 构建、dig-cut
state 写回、entry-error 采样、timeout handoff gate 调用、`_set_skill("dig",
"pre_dig_align_replan_to_dig_entry_close")` 和 policy reset timing。service 不接收
planner `self`，不调用 `_set_skill()`，不 reset policy，不读取 observation，不构建
dig-cut token，不修改 coverage/pending plan，不写 debug schema。

本切片不改变 replan handoff 成功路径的 planner-mode guard、operator-prior token
构建时机、entry-error 采样来源、timeout handoff reason、completed/replan counter
增量、dig runtime reset timing、`pre_dig_align_replan_to_dig_entry_close` switch
reason、branch order、policy reset timing、debug/summary schema、token contract 或
rollout 输出。

## Dig-Start Alignment Readiness Slice

`DigStartAlignmentService` 继续负责 pre-dig alignment 的纯 readiness checks：
surface-guard trigger/can-handoff、entry-close threshold、start-envelope qpos/pose
gate、first-dig entry-close handoff、entry-intent mode/handoff、timeout handoff
reason，以及 ready sample 对 hold count 的建议更新。service 还负责
pre-dig-align 的纯 outcome classification：根据已计算的 surface/ready/timeout
gate 结果返回 `PreDigAlignOutcome` 的 action、旧 switch reason 和 reject reason。
service 只接收显式 `DigStartAlignmentFacts`、`DigStartAlignmentConfig` 和
caller-provided gate booleans，不调用 `_ensure_dig_cut_plan_for_cycle()`，不写
planner debug 字段，不更新 counter，不 reject/complete coverage，不 dispatch policy。

后续 slice 在同一 service 中新增 `PreDigAlignOutcomeRequest` 和
`outcome_request()`，负责把 surface-guard trigger、当前 step count 与 max-step
timeout 阈值投影成 outcome request，并显式暴露是否应按旧顺序继续调用
surface-guard handoff、ready、timeout handoff gate。request 的
`outcome_with_gate_results()` 只把 caller-provided gate 结果投影回既有
`PreDigAlignOutcome`；不读取 observation，不调用 `_pre_dig_align_ready()` 或
`_pre_dig_align_timeout_can_handoff()`，不写 hold/timeout/surface counters，不
reject coverage，不重建 token，也不调用 `_set_skill()`。

planner 大文件只保留薄 facade 和状态写回：

- `_pre_dig_align_surface_guard_triggered_for_state()`
- `_pre_dig_align_surface_guard_can_handoff()`
- `_pre_dig_align_ready()`
- `_pre_dig_align_entry_close()`
- `_pre_dig_align_entry_close_handoff_ready_for_state()`
- `_pre_dig_align_entry_intent_mode_enabled()`
- `_pre_dig_align_entry_intent_handoff_ready_for_state()`
- `_pre_dig_align_timeout_can_handoff()`
- `_pre_dig_align_start_envelope_ready_for_state()`
- `_pre_dig_align_outcome()`

本切片仍保留 `_maybe_switch_skill()` 的 pre-dig-align 分支顺序、surface/timeout/
completed/replan counters、hold counter 写回、coverage reject/replan、token rebuild、
skill transition、policy reset timing 和 debug schema 在 planner shell；outcome
classification 不改变旧 switch reason、reject reason 或 debug schema。

## Dig-Start Alignment Readiness Gate Module Boundary Slice

新增模块：

- `testbed/planner/dig_start_alignment_readiness.py`

该 module 承载 pre-dig-align readiness / handoff gate 的稳定责任边界：
`SurfaceGuardDecision`、`AlignmentReadyDecision`、`TimeoutHandoffDecision`、
`PreDigAlignTimeoutHandoffRequest` 和 `DigStartAlignmentReadinessService`。
它复用 `dig_start_alignment_context` 的 `DigStartAlignmentConfig` /
`DigStartAlignmentFacts`，负责纯计算 surface guard trigger/can-handoff、
entry-close threshold、start-envelope qpos/pose gate、first-dig entry-close handoff、
entry-intent mode/handoff、timeout handoff request/decision，以及 ready sample 的
建议 hold count 和 readiness diagnostic fields。

`DigStartAlignmentService` 继承 `DigStartAlignmentReadinessService` 并继续 re-export 旧
readiness symbols，保留旧 private facade 和测试调用面。planner shell 仍负责
observation 采样、entry-error 采样时机、surface/ready/timeout gate 调用顺序、
runtime state 写回、hold/timeout/surface counters 写回、coverage reject/replan、
`_set_skill()`、policy reset timing 和 debug/summary schema。

本切片不迁 action target/servo 计算、entry-error 几何、outcome classification、
runtime projection 或 debug snapshot；不改变任何 threshold fallback、timeout reason、
start-envelope readiness 写回时机、entry-intent handoff sticky 写回、branch order、
switch reason、policy reset timing、debug/summary schema、token contract 或 rollout
输出。readiness module 不接收 planner `self`，不读取 observation，不调用
`_set_skill()`，不 reset policy，不写 HDF5/checkpoint，也不写 debug schema。

## Pre-Dig Align Outcome Runtime Projection Slice

`DigStartAlignmentService` 继续负责 pre-dig-align lifecycle 的纯 outcome/runtime
projection。由于 `dig_start_alignment.py` 已接近 large-file 阈值，本切片新增稳定
capability module `testbed.planner.dig_start_alignment_runtime`，由该 module 承载
`DigStartAlignmentRuntimeState`、`PreDigAlignOutcomeRuntimeProjection` 和纯 runtime
projection function；`DigStartAlignmentService.outcome_runtime_projection()` 保留为
domain service facade。本切片还新增 `PreDigAlignOutcomeRuntimeFacts`，把
`_maybe_switch_skill()` 中 pre-dig-align outcome action 之后的 runtime counter 投影迁出
planner shell：surface-guard handoff/replan 的 surface counter 与 hold reset、ready
handoff 的 completed counter、timeout handoff/replan 的 timeout counter，以及对应的
建议 transition action、switch reason 和 reject reason。

planner shell 仍负责：

- 调用 `_pre_dig_align_outcome()`，保持 surface-guard -> ready -> timeout 的旧 gate 顺序
- `_apply_pre_dig_align_runtime_state()` 的实际写回时机
- `_set_skill("dig", ...)`、coverage reject、`_restart_dig_with_new_cut()`、
  `_try_replan_pre_dig_align_handoff()` 和 `_restart_pre_dig_align()` 的副作用
- token rebuild、policy reset timing、debug/summary schema 和 rollout trace

service 不接收 planner `self`，不读取 observation，不调用 `_set_skill()`，不 reject
coverage，不构建 dig-cut token，不 reset policy，也不写 debug schema。本切片不改变
pre-dig-align branch order、surface/ready/timeout switch reason、reject reason、
counter 增量、replan handoff 尝试时机、policy reset timing、debug/summary schema 或
rollout 输出。

## Pre-Dig Align Outcome Application Facade Slice

planner shell 保留 `_apply_pre_dig_align_outcome_runtime_projection()` 作为旧 private
application facade，专门应用 `DigStartAlignmentService.outcome_runtime_projection()`
返回的 projection。该 facade 只负责按旧顺序执行 side effects：先在
`transition_action != "none"` 时写回 `_apply_pre_dig_align_runtime_state()`，再执行
`_set_skill("dig", ...)`、coverage reject + `_restart_dig_with_new_cut()`，或
coverage reject + `_try_replan_pre_dig_align_handoff()` / `_restart_pre_dig_align()`。

`DigStartAlignmentService` 和 `testbed.planner.dig_start_alignment_runtime` 仍只拥有纯
outcome/runtime projection；coverage reject、replan handoff、restart、active skill
切换和 policy reset timing 均不迁入 service。本切片不新增 application module，也不
把 side effects 包进 capability module，避免形成过细或带 planner state 的 service
边界。

本切片不改变 `_pre_dig_align_outcome()` 的 surface-guard -> ready -> timeout gate
顺序，不改变 runtime counter projection、switch/reject reason、coverage reject /
replan 尝试时机、policy reset timing、debug/summary schema、token contract 或 rollout
输出。

## Pre-Dig Align Outcome Runtime Application Facade Slice

`DigStartAlignmentOutcomeService` 新增
`outcome_runtime_projection_from_state()`，把 `PreDigAlignOutcome` 与
`DigStartAlignmentRuntimeState` 到 `PreDigAlignOutcomeRuntimeFacts` 的输入投影保留在
outcome service 边界内，并继续复用既有 `outcome_runtime_projection()` 和
`dig_start_alignment_runtime.project_pre_dig_align_outcome_runtime()` source-of-truth。

planner shell 新增 `_apply_pre_dig_align_outcome()` 作为旧 private application facade。
该 facade 只负责读取当前 `_pre_dig_align_runtime_state()`、调用 service 的纯 runtime
projection，并把 projection 交给既有
`_apply_pre_dig_align_outcome_runtime_projection()` 执行实际 side effects。
`_maybe_switch_skill()` 的 pre-dig-align 分支因此只保留 outcome gate facade 调用和
application facade 调用；`PreDigAlignOutcomeRuntimeFacts` 不再由 planner 大文件直接构造。

planner 仍拥有 active skill transition、`_set_skill()`、coverage reject/replan、
`_restart_dig_with_new_cut()`、`_try_replan_pre_dig_align_handoff()`、
`_restart_pre_dig_align()`、policy reset timing 和实际 runtime state 写回。service 不
接收 planner `self`，不读取 observation，不调用 `_set_skill()`，不 reject coverage，
不 reset policy，也不写 debug schema。

本切片不改变 `_pre_dig_align_outcome()` 的 surface-guard -> ready -> timeout gate
顺序，不改变 outcome action、runtime counter projection、switch/reject reason、
coverage reject / replan 尝试时机、policy reset timing、debug/summary schema、token
contract 或 rollout 输出。

## Dig-Start Alignment Outcome Module Boundary Slice

新增模块：

- `testbed/planner/dig_start_alignment_outcome.py`

该 module 承载 pre-dig-align final outcome 的稳定责任边界：
`PreDigAlignOutcome`、`PreDigAlignOutcomeRequest`、
`PreDigAlignOutcomeRuntimeFacts` 和 `DigStartAlignmentOutcomeService`。
它只负责把 caller 已按旧顺序计算出的 surface-guard / ready / timeout gate 结果
投影成 action、switch reason、reject reason，并把 outcome 与 runtime state 投影成
`PreDigAlignOutcomeRuntimeProjection`。该 module 不接收 planner `self`，不采样
observation，不调用 `_set_skill()`，不 reset policy，不 reject coverage，不构建
dig-cut token，不写 HDF5/checkpoint，也不写 debug schema。

`DigStartAlignmentService` 继承 `DigStartAlignmentOutcomeService` 并继续 re-export 旧
outcome symbols，保留旧 private facade 和测试调用面。planner shell 直接从新 module
引用 outcome facts/types，但仍负责 `_pre_dig_align_outcome()` 的实际 gate 调用顺序、
runtime state 写回、coverage reject/replan、skill transition、policy reset timing 和
debug/summary schema。

本切片不迁 surface guard、readiness、timeout handoff、start envelope 或 entry-intent
gate 的阈值/decision 逻辑；这些仍留在 `DigStartAlignmentService`，后续如果继续拆分，
必须按稳定 gate capability 选择单独 slice。本切片不改变 pre-dig-align branch order、
surface/ready/timeout switch reason、reject reason、counter 增量、replan handoff
尝试时机、policy reset timing、debug/summary schema、token contract 或 rollout 输出。

## Dig-Start Alignment Entry Error Geometry Slice

`DigStartAlignmentService` 继续负责 pre-dig alignment 的 entry-error 几何 helper。
本切片新增 `DigStartAlignmentEntryErrorFacts`，并让 planner 旧 private facade
`_pre_dig_align_entry_error()` 只负责装配 bucket-tip pose 与 active coverage corridor
entry target 后转调 service。

planner 大文件仍负责从 coverage service 读取 active corridor、从 observation 解析
bucket-tip pose、写回 `_pre_dig_align_entry_error_m` debug state、hold/timeout/
surface-guard counters、coverage reject/replan、branch order、switch reason、
policy reset timing 和 debug schema。

本切片不改变 entry error 数值：pose 或 active corridor 缺失时返回 `NaN`，否则
使用 bucket-tip x/z 与 active corridor entry x/z 计算 `np.hypot`。不改变
entry-close threshold、start-envelope gate、surface guard、entry-intent handoff、
timeout handoff、pre-dig-align outcome classification、reject reason 或 rollout 行为。

## Dig-Start Alignment Entry Error Context Consolidation Slice

后续复盘发现 entry-error 只剩一个 facts dataclass 和一段纯 derived-fact projection，
如果继续为它新增独立长期 geometry module，会把同一个 pre-dig alignment context
能力拆成过细的小文件。本切片因此回收该边界：`DigStartAlignmentEntryErrorFacts`
和 `dig_start_alignment_entry_error()` 归入
`testbed.planner.dig_start_alignment_context`，与 alignment config/facts projection
共享同一稳定 source-of-truth。

`DigStartAlignmentService.entry_error()` 保留为旧兼容 facade，直接转调 context
函数；`testbed.planner.dig_start_alignment` 继续 re-export entry-error symbols，避免
破坏旧 private/test 调用面。planner shell 仍负责从 coverage corridor 读取 active
entry、从 observation 解析 bucket-tip pose、写回 `_pre_dig_align_entry_error_m`、
执行 branch order、coverage reject/replan、policy reset timing 和 debug/summary
schema。

本切片不改变 entry error 数值、`NaN`/non-finite 传播、entry-close threshold、
start-envelope gate、surface guard、entry-intent handoff、timeout handoff、
pre-dig-align outcome classification、switch/reject reason、token contract 或 rollout
输出。

## Pre-Dig Align Debug Snapshot Slice

`testbed.planner.dig_start_alignment_runtime` 新增
`DigStartAlignmentDebugState`、`DigStartAlignmentDebugSnapshot` 和
`debug_snapshot()`，负责从 alignment config/runtime state 中快照 pre-dig-align
debug facts：enabled、entry-intent mask、surface-guard config/state、step/hold/
timeout/completed/replan counters、target qpos、alignment error、entry error、
start-envelope readiness、entry-close / entry-intent handoff readiness、first-dig
entry-close handoff config、controlled dims 和 bucket target qpos。
`DigStartAlignmentService.debug_snapshot()` 只保留为兼容 facade，负责把
`DigStartAlignmentConfig` 展开给 runtime projection；runtime module 和 service facade
都不接收 planner `self`，不调用 `_set_skill()`，不 reset policy，不写
HDF5/checkpoint，也不写 public debug schema。

planner `_pre_dig_align_debug_snapshot()` 只负责把当前 planner state 装配成
`DigStartAlignmentDebugState` 并调用 snapshot；`_debug_state_facts()` 和
`_rollout_summary_facts()` 都从该 snapshot 展开既有 facts 字段。`primitive_debug`
仍拥有 public debug-state / rollout-summary key/order/coercion。
`pre_dig_align_first_dig_only`、`pre_dig_align_replan_after_failed_dig` 和
`pre_dig_align_active_for_next_dig` 仍留在 planner/dig lifecycle 边界，因为它们描述
scheduler lifecycle 和 failed-dig recovery，不是纯 alignment runtime projection。

同一 Pre-Dig Align Debug Snapshot 边界后续新增
`DIG_START_ALIGNMENT_DEBUG_STATE_FIELDS` 和 `debug_state_from_mapping()`，把
planner `_pre_dig_align_debug_snapshot()` 中对 `_pre_dig_align_*` debug/runtime 字段
的采样与 int/float/bool coercion 收回 `dig_start_alignment_runtime.py`。planner 旧
private facade 只按字段表采样当前 planner state，并继续把
`DigStartAlignmentConfig` 交给 `DigStartAlignmentService.debug_snapshot()`；target qpos
和 alignment error 数组仍按旧语义原样进入 debug state，public snapshot 的 dtype /
shape / copy 仍由 `debug_snapshot()` 负责。

本切片不改变 debug-state key、key order、167 字段数量、array-to-list coercion、
`None -> NaN` debug fallback、pre-dig-align branch order、surface/ready/timeout
gate、hold/replan counter更新时机、rollout-summary key/type、switch reason、
policy reset timing 或 rollout 输出。

## Dig-Start Alignment Runtime Service Boundary Slice

`testbed.planner.dig_start_alignment_runtime` 新增
`DigStartAlignmentRuntimeService`，作为 pre-dig-align runtime/debug projection 的
service-object 边界。该 service 复用 runtime module 内已有 pure functions：
`initial_runtime_state()`、`enter_runtime_state()`、`restart_runtime_state()`、
`replan_handoff_runtime_state()` 和 `debug_snapshot()`，只负责把
`DigStartAlignmentConfig` 展开成 `action_dim` / debug config 参数，并返回显式 runtime
state 或 debug snapshot。

`DigStartAlignmentService` 继承 `DigStartAlignmentRuntimeService` 并继续 re-export 旧
runtime/debug symbols，保留旧 private facade 和测试调用面。`dig_start_alignment.py`
不再实现 runtime/debug wrapper 方法，只作为兼容入口组合 action、readiness、outcome
和 runtime service 边界。

本切片不改变 initial/enter/restart/replan runtime projection、debug snapshot 字段、
field list、array dtype/shape/copy、reset timing、branch order、switch reason、
policy reset timing、debug/summary schema 或 rollout 输出。runtime service 不接收
planner `self`，不读取 observation，不调用 `_set_skill()`，不 reset policy，不写
HDF5/checkpoint，也不写 public debug schema。

## Pre-Dig Align Runtime Reset Slice

`DigStartAlignmentService` 新增 `DigStartAlignmentRuntimeState` 和
`initial_runtime_state()`，负责投影 pre-dig-align runtime 的 legacy reset 默认值：
step/hold/timeout/completed/replan counters、target qpos、alignment error、
entry error、start-envelope readiness、entry-close / entry-intent handoff readiness、
timeout handoff reason、surface-depth / surface-guard state。service 只接收显式
`DigStartAlignmentConfig`，返回不可变 state dataclass；不接收 planner `self`，
不调用 `_set_skill()`，不 reset policy，不写 HDF5/checkpoint，不写 public debug
schema，也不更新 scheduler lifecycle counter。

planner `_reset_pre_dig_align_runtime()` 作为旧 private facade 保留在 shell 内，
只负责调用 service；`_apply_pre_dig_align_runtime_state()` 作为 shell 内的旧
private facade，集中把返回 state 应用到既有 `_pre_dig_align_*` 字段。`reset()`
的 policy reset、boundary detector reset、coverage reset、active skill 选择、
switch reason、cell-entry reset、debug-state 初始化顺序仍由 planner shell 拥有。

本切片不改变 reset timing、初始 active skill、switch reason `reset`、任何
pre-dig-align threshold、branch order、surface/ready/timeout gate、debug-state
key/key order、rollout-summary key/type、array dtype/shape 或 rollout 输出。

## Dig-Start Alignment Runtime Projection Consolidation Slice

由于 `dig_start_alignment.py` 已接近 large-file 阈值，且
`DigStartAlignmentRuntimeState` 与 outcome runtime projection 已经位于
`testbed.planner.dig_start_alignment_runtime`，本切片把 pre-dig-align runtime state
projection 的 source-of-truth 统一收回该 runtime capability module：
initial reset、enter-pre-dig-align、restart-pre-dig-align 和 replan-handoff success
runtime state projection 都由 `dig_start_alignment_runtime.py` 中的纯函数负责。

同一 runtime projection 边界后续新增
`DIG_START_ALIGNMENT_RUNTIME_STATE_FIELDS` 和 `runtime_state_from_mapping()`，把
planner `_pre_dig_align_runtime_state()` 中对 `_pre_dig_align_*` runtime 字段的
采样与 int/float/bool/string coercion 收回 `dig_start_alignment_runtime.py`。planner
旧 private facade 只按字段表采样当前 runtime state 并转调 builder；target qpos 和
alignment error 数组仍按旧语义原样进入 state，后续 dtype/shape/copy 仍由
`_apply_pre_dig_align_runtime_state()` 负责。

`DigStartAlignmentService.initial_runtime_state()`、
`enter_runtime_state()`、`restart_runtime_state()` 和
`replan_handoff_runtime_state()` 继续作为 domain service 的兼容 facade 保留，planner
调用面不变。planner shell 仍负责 `_set_skill()`、active skill 写回、policy reset
timing、coverage reject/replan、dig-cut token/pending state side effect，以及把返回的
runtime state 应用到 `_pre_dig_align_*` 字段。

同一 runtime projection 边界后续新增 readiness decision 的 runtime state projection：
`surface_guard_runtime_state()`、`ready_runtime_state()` 和
`timeout_handoff_runtime_state()`。这些方法只把已计算出的
`SurfaceGuardDecision`、`AlignmentReadyDecision` 或 `TimeoutHandoffDecision` 投影为
新的 `DigStartAlignmentRuntimeState`：surface depth / triggered 字段、ready sample
的 error / entry-error / start-envelope / entry-close / entry-intent / hold count 字段，
以及 timeout handoff 的 reason、sampled-entry-error、start-envelope 覆盖和
entry-intent sticky 语义。同一边界还承接 target qpos 以及 action decision 的 error /
entry-error runtime projection。后续同一边界补齐 fresh entry-error runtime projection，
用于 surface-guard handoff gate 和 replan-handoff timeout gate 前的旧 entry-error
写回时机；service 只返回带有新 entry-error 的 runtime state，planner shell 仍按旧顺序调用
surface/ready/timeout gate、决定 entry-error 采样时机，并通过
`_apply_pre_dig_align_runtime_state()` 执行实际字段写回。

本切片只修正 runtime projection 的责任边界，不改变保留/清零字段集合、counter 增量、
array dtype/shape/copy 语义、surface/ready/timeout gate 调用顺序、entry-error 采样来源、
timeout no-entry-gate 复用旧 entry-error state、entry-intent sticky 写回、target qpos
state update timing、fresh entry-error 写回时机、action dispatch、branch order、switch
reason、policy reset timing、debug/summary schema、token contract 或 rollout 输出。

## Pre-Dig Alignment Readiness Gate Decision Apply Facade Slice

planner shell 新增三个旧 private apply facade：

- `_apply_pre_dig_align_surface_guard_decision()`
- `_apply_pre_dig_align_ready_decision()`
- `_apply_pre_dig_align_timeout_handoff_decision()`

这些 facade 只负责把已经由 `DigStartAlignmentService` 计算出的
`SurfaceGuardDecision`、`AlignmentReadyDecision` 和 `TimeoutHandoffDecision`
投影成 `DigStartAlignmentRuntimeState`，再通过
`_apply_pre_dig_align_runtime_state()` 写回既有 `_pre_dig_align_*` 字段，并返回旧
gate boolean。runtime projection 的 source-of-truth 仍位于
`dig_start_alignment_runtime.py`；planner 仍拥有 surface/ready/timeout gate 的调用顺序、
timeout reason 清空时机、entry-error 采样时机、outcome assembly、switch reason、
policy reset timing 和所有实际 side effect。

本切片不新增 service/module，不改变 threshold、branch order、timeout reason string、
surface guard/ready/timeout gate 结果、entry-error 采样来源、entry-intent sticky 写回、
counter 语义、debug/summary schema、token contract 或 rollout 输出。

## Pre-Dig Alignment Fresh Entry-Error Runtime Apply Facade Slice

planner shell 新增旧 private facade：

- `_apply_pre_dig_align_entry_error_runtime_state()`

该 facade 只负责把已采样的 fresh entry-error 通过
`DigStartAlignmentService.entry_error_runtime_state()` 投影成
`DigStartAlignmentRuntimeState`，再通过 `_apply_pre_dig_align_runtime_state()` 写回既有
`_pre_dig_align_entry_error_m` 字段。runtime projection 的 source-of-truth 仍位于
`dig_start_alignment_runtime.py`。

planner 仍拥有 fresh entry-error 的采样时机和调用顺序：surface-guard handoff gate
前由 `_pre_dig_align_surface_guard_can_handoff()` 采样并写回，replan-handoff timeout
gate 前由 `_try_replan_pre_dig_align_handoff()` 采样并写回。service 不读取 observation，
不调用 `_pre_dig_align_entry_error()`，不决定 surface/timeout gate 是否执行，也不拥有
coverage reject/replan、switch reason、policy reset timing 或 debug schema。

本切片不改变 entry-error 采样来源、fresh entry-error 写回时机、
surface-guard handoff gate、replan-handoff timeout gate、timeout no-entry-gate 复用旧
entry-error state、branch order、threshold、switch reason、policy reset timing、
debug/summary schema、token contract 或 rollout 输出。

## Pre-Dig Alignment Action Decision Apply Facade Slice

planner shell 新增旧 private facade：

- `_apply_pre_dig_align_action_decision()`

该 facade 只负责把已经由 `DigStartAlignmentService.action_decision()` 计算出的
`AlignmentActionDecision` 通过 `DigStartAlignmentService.action_runtime_state()` 投影成
`DigStartAlignmentRuntimeState`，再通过 `_apply_pre_dig_align_runtime_state()` 写回
`_pre_dig_align_error` 和 `_pre_dig_align_entry_error_m`，并返回旧 action。

planner 仍拥有 `_pre_dig_align_action()` 的 enabled guard、step counter 递增、
surface-guard zero-action 短路、target qpos 获取、entry-error 采样、action dispatch
顺序和最终 action 返回路径。service 不读取 observation，不递增 counter，不调用
`_set_skill()`，不 reset policy，也不拥有 debug schema。

本切片不改变 action clip/sign、controlled dims、surface-guard zero-action 行为、
target qpos 更新时机、entry-error 采样来源、action dtype、branch order、switch reason、
policy reset timing、debug/summary schema、token contract 或 rollout 输出。

## Pre-Dig Alignment Target Runtime Apply Facade Slice

planner shell 新增旧 private facade：

- `_apply_pre_dig_align_target_runtime_state()`

该 facade 只负责把已经由 `DigStartAlignmentService.target_from_token()` 计算出的 target
qpos 通过 `DigStartAlignmentService.target_runtime_state()` 投影成
`DigStartAlignmentRuntimeState`，再通过 `_apply_pre_dig_align_runtime_state()` 写回
`_pre_dig_align_target_qpos`。target qpos 数值计算仍由
`dig_start_alignment_action.py` / `DigStartAlignmentService.target_from_token()` 拥有；
runtime projection 的 source-of-truth 仍位于 `dig_start_alignment_runtime.py`。

planner 仍拥有 `_pre_dig_align_target_from_token()` 的 `update_state` 分支、dig-cut token
读取、`NaN` entry-error facts facade、target state 写回时机、最终 `target.copy()` 返回、
action dispatch、branch order、switch reason 和 policy reset timing。service 不读取
observation，不调用 `_set_skill()`，不 reset policy，也不拥有 debug schema。

本切片不改变 target qpos 数值、qpos fallback/shape/dtype、short-token fallback、
controlled dims、entry-intent hold dims、bucket target qpos、target qpos state update
timing、returned target copy 语义、token contract、debug/summary schema 或 rollout 输出。

## Pre-Dig Alignment Lifecycle Runtime Apply Facades Slice

planner shell 新增旧 private apply facade：

- `_apply_pre_dig_align_initial_runtime_state()`
- `_apply_pre_dig_align_enter_runtime_state()`
- `_apply_pre_dig_align_restart_runtime_state()`
- `_apply_pre_dig_align_replan_handoff_runtime_state()`

这些 facade 只负责把 `DigStartAlignmentService.initial_runtime_state()`、
`enter_runtime_state()`、`restart_runtime_state()` 和
`replan_handoff_runtime_state()` 返回的 `DigStartAlignmentRuntimeState` 通过
`_apply_pre_dig_align_runtime_state()` 写回既有 `_pre_dig_align_*` 字段。runtime
projection 的 source-of-truth 仍位于 `dig_start_alignment_runtime.py`。

planner 仍拥有 lifecycle side effects：`reset()` 的 active skill 和 reset timing、
`_set_skill(PRE_DIG_ALIGN_SKILL_NAME)` 的 active skill/switch reason 写回与 policy reset
规则、`_restart_pre_dig_align()` 的 dig-entry reset / coverage corridor clear /
pending plan invalidation / dig-cut clear，以及 `_try_replan_pre_dig_align_handoff()`
的 token rebuild、entry-error sampling、timeout handoff gate、最终
`_set_skill("dig", ...)` 和 policy reset timing。service 不接收 planner `self`，不调用
`_set_skill()`，不 reset policy，不读取 observation，也不写 debug schema。

本切片不改变 pre-dig-align reset defaults、enter/restart/replan counter projection、
state field copy/dtype、active skill 写回时机、switch reason、coverage/pending/dig-cut
side effect、timeout handoff gate 调用顺序、policy reset timing、debug/summary schema、
token contract 或 rollout 输出。

## Coverage Service Package Status

`testbed/planner/dig_coverage/` 已作为 dig coverage / corridor planning 的
service package。`CoverageService` 组合 candidate 构造、raw-field 组装、selection
scoring 和 progress/depletion 更新；`DigCoverageMixin` 作为
`PrimitivePlannerACTPolicy` 的 compatibility facade，保留旧 `_coverage_*`
private entry points 和旧 state/debug property names。

该 package 已符合本计划第 5 步的主要方向：service owns coverage candidate、
scoring、target selection、progress/depletion state updates；planner shell 仍负责
何时 reject/complete coverage、何时执行 terminal stop 请求、何时 `_set_skill()`、
何时 reset policy，以及 rollout/debug/trace 的最终编排。coverage service 不直接
触发 terminal stop；它返回 deferred `CoverageActionResult`，由
`DigCoverageMixin` facade 在 planner shell 调用链中执行旧 terminal-stop side effect
并保留旧 trace event。后续 coverage 迁移应继续保持 behavior-preserving，不改
candidate layout、score weight、attempt/depletion、multi-pass、state exemplar、
terminal-stop reason 或 trace schema。

## Coverage Runtime Reset Slice

`CoverageService` 新增 `initial_runtime_state()`，继续复用
`CoverageServiceState`，负责投影 coverage / corridor planning runtime 的 legacy reset
默认值：corridors、active/last-selected corridor、payload/deposit counters、
low-productivity streak、completed dump count、pass index、terminal-stop state、
candidate scores、decision trace、state-exemplar ids/distance/profile token。

planner `_reset_coverage_service()` 仍作为旧 private facade 保留在 shell 内，只负责
按当前 coverage config 创建新的 service，并把 `initial_runtime_state()` 返回的 state
交给 service 拥有。`reset()` 中不再逐字段复制 `_coverage_*` 默认值；coverage mutable
state 的 source of truth 回到 `CoverageServiceState`。planner shell 仍负责 reset 调用
顺序、active skill 选择、switch reason、policy reset timing、coverage terminal-stop
side effect 执行、`_set_skill()` 和 public debug/summary schema 组装。

本切片不改变 reset timing、candidate layout、score weight、attempt/depletion、
multi-pass、state exemplar、terminal-stop reason、coverage decision trace payload、
debug/summary schema、branch order、switch reason、policy reset timing 或 rollout
输出。

## Coverage Service Config Mapping Slice

`dig_coverage.models` 新增 `COVERAGE_SERVICE_CONFIG_FIELDS` 和
`build_coverage_service_config_from_mapping()`，把
`DigCoverageMixin._coverage_service_config()` 中对 planner coverage runtime fields 的
字段表、类型 coercion 和 copy/reshape 语义收回 coverage package。该 builder 负责
构造 `CoverageServiceConfig`，包括 coverage scoring / multi-pass / state-exemplar /
first-dig selection 参数，以及 first-dig alignment 的 enable flag、controlled dims 和
optional qpos delta bounds。

planner 旧 private facade `_coverage_service_config()` 仍保留在
`DigCoverageMixin`，只从当前 planner shell 字段构造 focused mapping 并转调 builder。
`coverage_state_exemplars_by_cell` 继续保持旧的 missing-attr fallback；其它字段仍要求
planner 初始化路径已显式设置。coverage service config builder 不接收 planner `self`，
不加载 state-exemplar 文件，不创建 `CoverageService`，不执行 reset，不读取
observation，不选择 corridor，不写 terminal-stop/debug/trace state。

本切片不改变 coverage 默认值、candidate layout、score weight、attempt/depletion、
multi-pass、state exemplar、first-dig alignment target callback、terminal-stop reason、
coverage decision trace payload、debug/summary schema、branch order、switch reason、
policy reset timing 或 rollout 输出。

## Coverage Observation Facts Projection Slice

`dig_coverage.models` 新增 `COVERAGE_OBSERVATION_FACT_FIELDS`、
`build_coverage_observation_facts_from_mapping()` 和
`build_coverage_context_facts_from_mapping()`，把
`DigCoverageMixin._coverage_observation_facts()` 与
`_coverage_context_facts()` 中对 `CoverageObservationFacts` 的 runtime 字段投影、
`qpos` missing fallback、dtype/shape coercion 和 terminal-stop context 默认值收回
coverage package。该切片延续 `CoverageObservationFacts` 已有 dataclass 边界，只负责
把已解析 facts 构造成 coverage service 输入。

planner 旧 private facade 仍保留在 `DigCoverageMixin`。facade 继续调用
`_env_state()`、`_bucket_tip_dig_area_pose()`、`_mass_in_bucket()` 和
`_deposited_mass()` 解析 raw observation，并只把已解析值、当前 `action_dim` 和
focused runtime mapping 传给 builder。builder 不接收 planner `self`，不接收 raw
`obs`，不复制 `testbed.planner.snapshots` 的 observation schema fallback，不选择
corridor，不更新 coverage state，不发 terminal-stop side effect，也不写 debug/trace
schema。

本切片不改变 coverage observation parsing source-of-truth、`qpos` 缺失与显式非法
shape 的旧错误行为、cycle/skill/dig-best coercion、terminal-stop context facts、
candidate layout、score weight、attempt/depletion、multi-pass、state exemplar、
terminal-stop reason、coverage decision trace payload、debug/summary schema、branch
order、switch reason、policy reset timing 或 rollout 输出。

## Bootstrap Config Assembly Slice

`bootstrap` 新增 `BootstrapPlannerConfig` 和
`build_bootstrap_planner_config()`，负责把 planner 初始化期间的 legacy / diagnostic
bootstrap 配置解析成 planner shell 需要应用的显式字段：`bootstrap_end_*` learned
handoff 参数，以及 `scripted_bootstrap_*` target qpos、PD gains、action clip/signs、
qpos/qvel tolerance、hold steps 和 timeout steps。`BOOTSTRAP_CONFIG_KEYS` 只作为
planner `__init__` filtered init-argument mapping facade 的字段边界，避免 planner
大文件复制 bootstrap 参数转发表。

本切片把 bootstrap 初始化配置放在 `bootstrap` compatibility capability，而不是放入
`primitive_config`。原因是 bootstrap 已有稳定 service module 承接 legacy/diagnostic
gate、scripted action、runtime reset 和 runtime status projection；配置投影属于该
capability 的输入边界，同时避免继续扩张接近大文件阈值的 central config helper。

planner 大文件只保留薄应用入口：

- `_apply_bootstrap_config()`

本切片只迁初始化配置投影，不迁 `_bootstrap_config()` runtime 汇总、
`_should_end_bootstrap()`、`_scripted_bootstrap_enabled()`、
`_scripted_bootstrap_target_reached()`、`_scripted_bootstrap_action()`、scripted
step/hold/timeout counter 写回、bootstrap branch order、active policy dispatch、
policy reset timing、debug/summary schema 或 5P compatibility pass-through。
`bootstrap` 不接收 planner `self`，不调用 `_set_skill()`，不读取 observation，不
reset policy，不写 HDF5/checkpoint/debug schema。

本切片不改变 bootstrap 默认值、target qpos / action signs `float32` reshape 语义、
missing action signs fallback to ones、hold/max step `max(1, int(...))` coercion、
`bootstrap_to_*` switch reason、terminal reason、policy reset timing、debug/summary
schema、token contract 或 rollout 输出。bootstrap 仍保持 legacy smoke /
diagnostic / learned first-handoff compatibility layer，不提升为 mainline 调度语义。

## Bootstrap Facts Assembly Slice

`bootstrap` 新增 `build_bootstrap_facts()`，负责把 planner shell 显式采样的 legacy
bootstrap 输入投影成 `BootstrapFacts`：qpos/qvel 的 legacy float32 reshape、bucket
mass、dig-area distance、qualified dig-start boundary flag、scripted step/hold
counters，以及 bootstrap policy presence。该 helper 不接收 planner `self`，不读取
observation，不调用 boundary detector，不调用 `_set_skill()`，不 reset policy，也不
写 planner state 或 debug schema。

planner `_bootstrap_facts()` 作为旧 private facade 保留在 shell 内，只负责按旧来源
采样 obs/default qpos/qvel、mass/distance helper、boundary event flag、scripted
runtime counters 和 bootstrap policy presence，然后转调 `build_bootstrap_facts()`。

同一 Facts Assembly 边界后续新增 `BOOTSTRAP_FACT_FIELDS` 和
`build_bootstrap_facts_from_mapping()`，把 `_bootstrap_facts()` 中的显式 facts
mapping 字段表与 `build_bootstrap_facts()` 调用收回 `bootstrap` capability。
planner 旧 private facade 仍按旧来源采样 obs/default qpos/qvel、mass/distance、
boundary event flag、scripted counters 和 bootstrap policy presence，再按字段表转调
builder。

同一 Facts Assembly 边界现在继续收口 source projection：`bootstrap` 新增
`build_bootstrap_facts_from_observation_view()` 与
`BootstrapService.facts_from_observation_view()`，从 `PlannerObservationView` 的原始
observation 复用 `snapshots` legacy mass/distance helpers，并保持 qpos/qvel 由原始
obs 或 zero default 进入 `build_bootstrap_facts()` 的旧 reshape/dtype 语义。planner
`_bootstrap_facts()` 只创建 snapshot 并显式传入 boundary event、scripted counters 和
bootstrap policy presence；不再在 planner 大文件内手写 bootstrap facts mapping。

本切片不改变 qpos/qvel fallback/shape/dtype、boundary event 优先级、mass/distance
来源、scripted hold/timeout counter 写回、bootstrap branch order、`bootstrap_to_*`
switch reason、policy reset timing、debug/summary schema 或 rollout 输出。

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

## Bootstrap Gate Decision Apply Facade Slice

同一 bootstrap compatibility 边界内的后续 consolidation 新增
`_apply_bootstrap_end_decision()` 和 `_apply_bootstrap_target_decision()`，把
`BootstrapEndDecision` 与 `BootstrapTargetDecision` 中的 scripted bootstrap counter
写回收口到 planner shell。`_should_end_bootstrap()` 和
`_scripted_bootstrap_target_reached()` 仍按旧时机调用 `BootstrapService` 的
`should_end()` / `scripted_target_reached()`；service 继续只负责纯 gate decision，不写
planner state。

这些 facade 只执行 shell-owned side effect：写回
`_scripted_bootstrap_hold_count`，并在 end decision 的 `timeout_increment=True` 时按旧
语义递增 `_scripted_bootstrap_timeout_count`。它们不分类 bootstrap 下一 skill，不调用
`_set_skill()`，不 reset policy，不读取 observation，也不写 debug schema。

本切片不改变 scripted target hold gate、scripted timeout gate、learned bootstrap end
gate、bootstrap branch order、`bootstrap_to_*` switch reason、counter increment
时机、policy reset timing、debug/summary schema、token contract 或 rollout 输出。

## Bootstrap Runtime Config Mapping Slice

`bootstrap` 继续作为 legacy/diagnostic bootstrap compatibility capability。本切片
新增 `BOOTSTRAP_RUNTIME_CONFIG_FIELDS` 和
`build_bootstrap_config_from_mapping()`，把 `_bootstrap_config()` 中当前 planner
runtime 字段到 `BootstrapConfig` 的投影收回 bootstrap capability。planner 旧 private
facade 只从自身当前字段构造 focused mapping 并转调 builder。

该 builder 只复刻旧 runtime `_bootstrap_config()` 的投影语义：`action_dim`、
`end_mode`、bucket-mass / distance threshold、scripted qpos/action 参数、
qpos/qvel tolerance，以及 hold/max steps 的直接 `int()` coercion。它不复用初始化
`build_bootstrap_planner_config()` 的 `max(1, int(...))` normalization，避免改变旧
runtime facade 在字段被测试或诊断代码直接设置时的行为。

service 不接收 planner `self`，不读取 observation，不调用 `_set_skill()`，不 reset
policy，不写 HDF5/checkpoint/debug schema，也不决定 bootstrap 的下一 skill。
planner shell 仍负责 bootstrap branch order、`bootstrap_to_*` switch reason、scripted
step/hold/timeout counters 写回、active policy dispatch、policy reset timing 和 public
debug/summary schema 展开。

本切片不改变 bootstrap 初始化默认值、scripted target/action 数值、scripted
hold/timeout gate、learned bootstrap end gate、`bootstrap_to_*` switch reason、
terminal reason、policy reset timing、debug/summary schema、token contract 或 rollout
输出。

## Bootstrap End Transition Classification Slice

`BootstrapService` 新增显式 `BootstrapEndTransitionFacts`、
`BootstrapTransitionConfig` 和 `BootstrapTransitionDecision`，负责在 planner shell
已经判定 bootstrap should-end 之后，纯分类下一 skill 与旧 switch reason：
`first_qualified_dig_start` / `scripted_qpos` 进入 dig path，且在 planner 显式传入
`pre_dig_align_before_dig=True` 时进入 pre-dig-align；其它 bootstrap end mode 进入
carry。decision 只返回 `next_skill` 和 `bootstrap_to_{next_skill}` reason。

planner shell 仍负责 `_should_end_bootstrap()` 的 gate 调用和 scripted hold/timeout
counter 写回，只在 should-end 为 true 后采样 `_should_pre_dig_align_before_dig()`，
再调用 service decision 并通过 `_set_skill()` 执行状态切换。service 不接收 planner
`self`，不读取 observation，不调用 `_set_skill()`，不 reset policy，不写
HDF5/checkpoint/debug schema，也不决定 bootstrap should-end。

同一边界后续新增 `BootstrapEndTransitionRequest` 和
`BootstrapService.end_transition_request()`，把 `_maybe_switch_skill()` 中
`BootstrapEndTransitionFacts` 与 `BootstrapTransitionConfig` 的构造收回 bootstrap
capability。planner shell 仍只在 should-end 成功后按旧时机采样
`_should_pre_dig_align_before_dig()`，并显式传入 `PRE_DIG_ALIGN_SKILL_NAME`；service
只做 facts/config 投影，不读取 observation、不写 counters、不调用 `_set_skill()`。

本切片不改变 bootstrap should-end branch order、scripted step/hold/timeout counter
写回、pre-dig-align eligibility 采样时机、`bootstrap_to_dig` /
`bootstrap_to_pre_dig_align` / `bootstrap_to_carry` reason 字符串、policy reset timing、
debug/summary schema、token contract 或 rollout 输出。

## Bootstrap End Transition Apply Facade Slice

同一 bootstrap compatibility 边界内的后续 consolidation 新增
`_apply_bootstrap_transition_decision()`，把 `BootstrapTransitionDecision` 中的
`next_skill` 和 `switch_reason` 应用收口到 planner shell 的统一 facade。bootstrap
branch 仍按旧顺序先调用 `_should_end_bootstrap()`，再在 should-end 成功分支中采样
`_should_pre_dig_align_before_dig()` 并调用 `BootstrapService.end_transition()`；最终
skill switch 通过该 facade 调用 `_set_skill()`。

该 facade 不调用 bootstrap should-end gate，不读取 observation，不分类 next skill，不
修改 scripted bootstrap counters，不 reset policy，也不写 debug schema。它只保留 planner
shell 对 `_set_skill()` 和 policy reset timing 的所有权，避免最终 bootstrap transition
side effect 散落在 `_maybe_switch_skill()` 分支内。

本切片不改变 bootstrap should-end branch order、scripted step/hold/timeout counter
写回、pre-dig-align eligibility 采样时机、`bootstrap_to_dig` /
`bootstrap_to_pre_dig_align` / `bootstrap_to_carry` reason 字符串、policy reset timing、
debug/summary schema、token contract 或 rollout 输出。

## Bootstrap Runtime Status Projection Slice

`BootstrapService` 继续作为 legacy/diagnostic bootstrap compatibility 的 capability
边界。本切片新增 `BootstrapRuntimeStatusState` 和
`BootstrapRuntimeStatusSnapshot`，负责把 planner shell 已维护的 scripted bootstrap
runtime counters 投影成 debug-state 与 rollout-summary 共同需要的 facts：
scripted step count、hold count 和 timeout count。

后续同一切片新增 `BOOTSTRAP_RUNTIME_STATUS_FIELDS` 和
`build_bootstrap_runtime_status_state_from_mapping()`，把 planner 当前 scripted
bootstrap runtime counters 到 `BootstrapRuntimeStatusState` 的投影收回 bootstrap
capability。planner 旧 private facade 只按字段表采样当前 state 后调用 builder；
counter `int` coercion 和 status-state contract 由 `bootstrap` 统一负责。

planner 大文件只保留薄 facade：

- `_bootstrap_runtime_status_snapshot()`

planner shell 仍负责 scripted bootstrap step/hold/timeout counters 的写回时机、
bootstrap branch order、`bootstrap_to_*` switch reason、active policy dispatch、
policy reset timing 和 public debug/summary schema 展开。service 不接收 planner
`self`，不调用 `_set_skill()`，不 reset policy，不写 debug schema，不读取
observation，也不改变任何 bootstrap counter。

本切片不改变 debug-state 或 rollout-summary key/key order、step/hold/timeout
counter 数值、scripted target/timeout gate、bootstrap end branch、switch reason、
policy reset timing 或 rollout 输出。rollout summary 继续只暴露 timeout count，不新增
step/hold summary 字段。

## Bootstrap Runtime Reset Slice

`BootstrapService` 新增 `initial_runtime_state()`，继续复用
`BootstrapRuntimeStatusState`，负责投影 scripted bootstrap runtime 的 legacy reset
默认值：scripted step count、hold count 和 timeout count。service 只返回显式 runtime
state；不接收 planner `self`，不调用 `_set_skill()`，不 reset policy，不写
HDF5/checkpoint，不写 debug schema，不读取 observation，也不决定 bootstrap 是否启用
或结束。

planner `_reset_bootstrap_runtime()` 和 `_apply_bootstrap_runtime_state()` 作为旧
private facade 保留在 shell 内，只负责调用 service 并把返回 state 应用到既有
`_scripted_bootstrap_*` counter 字段。`reset()` 的 policy reset、boundary detector
reset、coverage reset、active skill 选择、switch reason、bootstrap enablement 判断、
pre-dig-align / dig lifecycle reset 顺序和 public debug/summary schema 仍由 planner
shell 拥有。

本切片不改变 reset timing、初始 active skill、switch reason `reset`、
`bootstrap_to_*` reason 字符串、scripted target/timeout gate、bootstrap branch
order、policy reset timing、debug/summary schema 或 rollout 输出。

## Debug / Trace Builder Slice

`testbed.planner.primitive_debug` 负责 primitive planner 的 debug-state、
rollout-summary 和 planner-trace payload builder。`PrimitivePlannerDebugState`
及其 side-effect-free snapshot builder 也由该模块定义；`PrimitivePlannerACTPolicy`
中的 `_make_debug_state()`、`debug_state()`、`rollout_summary()` 和
`planner_trace()` 只保留为 facade，转调对应 builder。

本切片只移动 schema/payload 构造位置，不改变 key、key order、字段类型、默认值、
token contract string、coverage decision trace payload、rollout JSONL 消费语义、
planner 分支顺序、switch reason、counter、policy reset timing 或 active policy
dispatch。

### Debug State Snapshot Runtime Assembly Slice

`primitive_debug` 继续作为 debug-state snapshot 的 schema builder source-of-truth。
本切片新增 `PrimitiveDebugStateSnapshotConfig`、
`PrimitiveDebugStateSnapshotFacts` 和
`build_primitive_debug_state_snapshot_from_runtime()`，把
`PrimitivePlannerACTPolicy._make_debug_state()` 与 5P compatibility override 中重复的
snapshot config / runtime facts 投影收回 debug capability。planner shell 仍负责采样
当前 active skill、switch reason、transition timeout/completed flags、cycle/counter
state、dump lifecycle runtime status snapshot、first-dig policy active flag 和 5P
兼容 hold-count 字段，然后调用 builder。

service builder 只消费显式 config/facts 并复用既有
`build_primitive_debug_state_snapshot()`；不读取 planner `self`，不调用 `_set_skill()`，
不 reset policy，不写 HDF5/checkpoint，也不写 public debug schema 之外的状态。4P 与
5P 的 skill id mapping、transition skill names、checkpoint mapping 和 hold-count
兼容值仍由 caller 显式传入，避免把 5P legacy scheduler 语义提升为主线。

本切片不改变 debug-state key/key order、checkpoint lookup key、hybrid-mode
classification、5P `approach_ready_hold_count` /
`dump_release_ready_hold_count` 输出、switch reason、transition timeout/completed
flags、counter 值、branch order、policy reset timing 或 rollout 输出。

### Planner Trace Facts Input Slice

`primitive_debug` 新增 `PrimitivePlannerTraceFacts` 和
`build_primitive_planner_trace_from_facts()`，让 planner trace payload builder 从显式
facts 构造 schema，而不是在主路径中直接读取 planner `self`。`planner_trace()` 只在
planner shell 中装配 cell-entry trace、dig-cut metadata 和 return-target 开关；
coverage config、corridor debug payload、coverage decision trace 和 terminal-stop
状态由 coverage trace snapshot 供给后再转调 builder。

旧 `build_primitive_planner_trace(policy)` 作为兼容 wrapper 保留，供现有直接调用方和
测试逐步迁移；它通过 `policy._planner_trace_facts()` 复用同一 facts path，不改变
trace schema，也不拥有 planner state。debug-state 与
rollout-summary 的 facts 输入迁移不在本切片内，后续应单独锁定 schema 后再迁。

后续 Planner Trace Facts Assembly 切片复用
`testbed.planner.primitive_debug_facts`，新增
`PrimitivePlannerTraceAssemblyInputs` 和 `build_primitive_planner_trace_facts()`，
把 planner 已采集的 coverage trace snapshot 与 shell-owned trace scalar facts 投影成
`PrimitivePlannerTraceFacts`。planner `_planner_trace_facts()` 只保留旧 private
facade：采集 cell-entry trace、dig-cut metadata、return-target enabled flag 和
coverage trace snapshot，然后调用 debug facts capability。`primitive_debug_facts`
不读取 planner `self`，不调用 `_set_skill()`，不 reset policy，不写
HDF5/checkpoint，也不改变 public planner-trace schema；`primitive_debug` 继续只负责
public trace builder 和 legacy wrapper。

后续同一 assembly 切片新增 `PRIMITIVE_PLANNER_TRACE_ASSEMBLY_FIELDS` 和
`build_primitive_planner_trace_assembly_inputs_from_mapping()`，把 planner shell 当前
cell-entry trace、dig-cut metadata 和 return-target enabled flag 到
`PrimitivePlannerTraceAssemblyInputs` 的投影收回 `primitive_debug_facts`。planner 旧
private facade 只按字段表采样当前 shell state，并继续显式传入 coverage trace
snapshot；`tuple` / `str` / `bool` coercion 由 debug facts capability 统一负责。
builder 不读取 planner `self`，不调用 coverage service，不拥有 decision trace，也不
改变 public planner-trace schema。

本切片不改变 planner trace key、key order、token contract string、coverage corridor
debug payload、coverage decision trace count、terminal-stop fields、debug/summary
schema、branch order、switch reason、policy reset timing 或 rollout 输出。

### Coverage Planner Trace Snapshot Slice

`CoverageService` 新增 coverage planner-trace snapshot 能力，负责从 coverage-owned
config/state 中快照 planner trace 所需的 coverage facts：removed-depth usage、
candidate layout、first-dig strategy、pass/multi-pass config、first-dig preferred
corridor、corridor debug payload、coverage decision trace、terminal-stop requested
和 terminal-stop reason。`DigCoverageMixin` 保留 `_coverage_trace_snapshot()`
compatibility facade；planner `_planner_trace_facts()` 只调用该 snapshot 并展开为
既有 `PrimitivePlannerTraceFacts` 扁平字段。

本切片修正 planner trace facts 输入迁移后的过渡性边界：coverage trace facts 的
source of truth 回到 coverage package，`primitive_debug` 仍只负责 public planner-trace
key/order、token contract string、decision trace count 和 coercion。service 不接收
planner `self`，不调用 `_set_skill()`，不 reset policy，不写 HDF5/checkpoint，也
不改变 coverage decision trace 记录或 terminal-stop side effect。

本切片不改变 planner trace key、key order、coverage corridor debug payload、
coverage decision trace payload/count、terminal-stop fields、debug/summary schema、
branch order、threshold、switch reason、policy reset timing 或 rollout 输出。

### Rollout Summary Facts Input Slice

`primitive_debug` 新增 `PrimitiveRolloutSummaryFacts` 和
`build_primitive_rollout_summary_from_facts()`，让 rollout summary payload builder 从
显式 facts 构造 schema，而不是在主路径中直接读取 planner `self`。`rollout_summary()`
只在 planner shell 中装配 transition counters、return handoff debug state、dig-cut
metadata、bootstrap counters、pre-dig-align counters 和 dig failed-replan counters；
coverage counters/config/terminal-stop state 由 coverage rollout-summary snapshot
供给后再转调 builder。

旧 `build_primitive_rollout_summary(policy)` 作为兼容 wrapper 保留，供现有直接调用方
和测试逐步迁移；它通过 `policy._rollout_summary_facts()` 复用同一 facts path，
不改变 summary schema，也不拥有 planner state。debug-state 的 facts 输入迁移不在
本切片内，后续应单独锁定 schema 后再迁。

后续 Rollout Summary Facts Assembly 切片复用
`testbed.planner.primitive_debug_facts`，新增
`PrimitiveRolloutSummaryAssemblyInputs` 和
`build_primitive_rollout_summary_facts()`，把 planner 已采集的 service snapshots 与
shell-owned scalar facts 投影成 `PrimitiveRolloutSummaryFacts`。planner
`_rollout_summary_facts()` 只保留旧 private facade：采集 coverage / return /
dig-cut / return-target / lifecycle / bootstrap / pre-dig-align snapshots、计算
transition counters、final skill、cycle index 和 cell-entry trace count，然后调用
debug facts capability。`primitive_debug_facts` 不读取 planner `self`，不调用
`_set_skill()`，不 reset policy，不写 HDF5/checkpoint，也不改变 public rollout
summary schema；`primitive_debug` 继续只负责 public summary builder 和 legacy wrapper。

后续同一 assembly 切片新增 `PRIMITIVE_ROLLOUT_SUMMARY_ASSEMBLY_FIELDS` 和
`build_primitive_rollout_summary_assembly_inputs_from_mapping()`，把 planner shell 当前
transition counters、final skill、cycle index、cell-entry trace 和 pre-dig-align flags
到 `PrimitiveRolloutSummaryAssemblyInputs` 的投影收回 `primitive_debug_facts`。
planner 旧 private facade 只按字段表采样当前 shell state，并继续显式传入 coverage /
return / dig-cut / return-target / lifecycle / bootstrap / pre-dig-align snapshots；
`int` / `bool` / `str` coercion 与 cell-entry trace count 计算由 debug facts capability
统一负责。builder 不读取 planner `self`，不调用 coverage 或 lifecycle service，不拥有
summary schema，也不改变 public rollout-summary payload。

本切片不改变 rollout summary key、key order、字段类型、bool-like 字段输出为
`int` 的兼容行为、`None -> NaN/-1` fallback、token dim 常量、transition
source/mode/fallback 常量、coverage depleted count 计算位置、debug/trace schema、
branch order、switch reason、policy reset timing 或 rollout 输出。

### Coverage Rollout Summary Snapshot Slice

`CoverageService` 新增 coverage rollout-summary snapshot 能力，负责从 coverage-owned
config/state 中快照 rollout summary 所需的 coverage facts：selected corridor id、
depleted count、completed dump count、pass index、multi-pass config、removed-depth
usage、candidate layout、first-dig strategy、first-dig preferred corridor、first-dig
entry distance gate、first-dig qpos delta weight、terminal-stop requested 和
terminal-stop reason。`DigCoverageMixin` 保留
`_coverage_rollout_summary_snapshot()` compatibility facade；planner
`_rollout_summary_facts()` 只调用该 snapshot 并展开为既有
`PrimitiveRolloutSummaryFacts` 扁平字段。

本切片修正 rollout summary facts 输入迁移后的过渡性边界：coverage summary facts 的
source of truth 回到 coverage package，`primitive_debug` 仍只负责 public
rollout-summary key/order、bool-like `int` coercion、`None -> -1/NaN` fallback 和 token
dim 常量。service 不接收 planner `self`，不调用 `_set_skill()`，不 reset policy，
不写 HDF5/checkpoint，也不改变 coverage depleted count、completed dump count 或
terminal-stop side effect。

本切片不改变 rollout summary key、key order、字段类型、coverage selected/depleted /
completed counters、`None -> -1/NaN` fallback、terminal-stop fields、branch order、
threshold、switch reason、policy reset timing 或 rollout 输出。

### Debug State Facts Input Slice

`primitive_debug` 新增 `PrimitiveDebugStateFacts` 和
`build_primitive_debug_state_from_facts()`，让 public debug-state payload builder
从显式 facts 构造 schema，而不是在主路径中直接读取 planner `self`。
`debug_state()` 只在 planner shell 中快照 debug-state、goal ids、token injection
状态、coverage/cell-entry/pre-dig-align debug facts、terminal-stop 状态和 bootstrap /
dig counters 后转调 builder。

后续 Debug State Facts Assembly 切片新增
`testbed.planner.primitive_debug_facts`，其中
`PrimitiveDebugStateAssemblyInputs` 和 `build_primitive_debug_state_facts()` 负责把
planner 已采集的 service snapshots 与 shell-owned scalar facts 投影成
`PrimitiveDebugStateFacts`。planner `_debug_state_facts()` 只保留旧 private facade：
采集各 service snapshot、计算 goal ids / pre-dig-align active-for-next-dig 等
shell 事实并调用 debug facts capability。`primitive_debug_facts` 不读取 planner
`self`，不调用 `_set_skill()`，不 reset policy，不写 HDF5/checkpoint，也不改变
public debug schema。`primitive_debug` 继续只负责 public schema builder 和 legacy
wrapper，避免 schema builder 文件继续增长为新的大文件。

同一 Debug State Facts Assembly 边界后续新增
`PRIMITIVE_DEBUG_STATE_ASSEMBLY_FIELDS` 和
`build_primitive_debug_state_assembly_inputs_from_mapping()`，把 planner facade 中
`debug_state`、cell-entry flags 和 pre-dig-align config flags 的字段采样与
bool/int coercion 收敛到 `primitive_debug_facts`。planner 仍显式传入 goal ids、
pre-dig-align active-for-next-dig fact，以及 coverage、handoff、dig-cut、
dig-depth-profile、return-target、dig-lifecycle、bootstrap、cell-entry 和
pre-dig-align snapshots；builder 不调用 goal sequence/pre-dig-align services，也不
拥有 planner mutable state。这样 debug-state assembly 与 trace/rollout-summary
assembly 使用同一字段表模式，同时避免复制 public debug schema 或
token/source-of-truth。

旧 `build_primitive_debug_state(policy)` 作为兼容 wrapper 保留，供现有直接调用方和
测试逐步迁移；它不改变 debug schema，也不拥有 planner state。coverage corridor
debug payload 与 cell-entry fallback snapshot 已回收到各自 capability facade；
pre-dig-align active-for-next-dig 判断仍由 planner shell 通过既有 facade 在调用时快照，
不在 debug builder 中复制领域计算。

本切片不改变 debug-state key、key order、167 字段数量、字段类型、`None -> NaN/-1`
fallback、token dim 常量、transition source/mode/fallback 常量、coverage corridor
debug payload、planner terminal-stop mirror 字段、branch order、switch reason、
policy reset timing 或 rollout 输出。

### Primitive Debug Facts Mapping Entry Point Slice

`primitive_debug_facts` 继续作为 debug-state、planner-trace 和 rollout-summary
facts assembly 的 source-of-truth。本切片新增
`build_primitive_debug_state_facts_from_mapping()`、
`build_primitive_planner_trace_facts_from_mapping()` 和
`build_primitive_rollout_summary_facts_from_mapping()`，把 planner 旧 private facade 中
“字段表采样 mapping -> assembly inputs -> facts”的组合入口收回同一个 facts
capability。

planner `_debug_state_facts()`、`_planner_trace_facts()` 和
`_rollout_summary_facts()` 仍只负责按旧时机采样 shell-owned scalar fields、goal /
pre-dig-align lifecycle facts，以及 coverage、return handoff、dig-cut、
dig-depth-profile、return-target、dig-lifecycle、bootstrap、cell-entry 和
pre-dig-align snapshots；随后直接调用 `primitive_debug_facts` 的 mapping entry
point。`primitive_debug` 继续只负责 public debug-state / planner-trace /
rollout-summary schema builder、key order、coercion 和 legacy wrapper。

本切片不新建 debug service，不接收 planner `self`，不调用 `_set_skill()`，不 reset
policy，不写 HDF5/checkpoint/debug schema，也不改变 debug-state、planner-trace 或
rollout-summary key/key order、字段类型、token contract string、coverage decision
trace payload、branch order、switch reason、policy reset timing 或 rollout 输出。

### Primitive Debug Facts Contract Module Boundary Slice

`primitive_debug_facts` 继续作为 debug-state、planner-trace 和 rollout-summary 的
explicit facts contract 与 facts assembly source-of-truth。本切片把
`PrimitiveDebugStateFacts`、`PrimitivePlannerTraceFacts` 和
`PrimitiveRolloutSummaryFacts` 的定义迁入 `primitive_debug_facts`，让 facts dataclass
与 mapping / assembly entry point 位于同一 capability 边界内。

`primitive_debug` 继续 re-export 这些 facts dataclass，保护旧 import path，并继续只
负责 public debug-state / planner-trace / rollout-summary schema builder、key order、
coercion、`PrimitivePlannerDebugState` snapshot dataclass 和 legacy wrapper。这样避免
facts assembly capability 反向依赖 public schema builder 模块，也不把 schema source of
truth 复制进新的 service。

本切片不改变 debug-state、planner-trace 或 rollout-summary key/key order、字段类型、
token dim/contract source-of-truth、coverage decision trace payload、transition source /
policy mode 常量、branch order、switch reason、terminal reason、policy reset timing、
rollout 输出或默认 config。`primitive_debug_facts` 不接收 planner `self`，不调用
`_set_skill()`，不 reset policy，不写 HDF5/checkpoint/debug schema。

### 5P Debug Dump Lifecycle Status Facade Slice

5P planner 仍是 legacy / compatibility path，不作为当前重构主线新增调度语义。本切片只
对齐 debug-state dump lifecycle status 采样边界：`PrimitivePlannerACT5PPolicy` 新增
5P 专用 `_dump_lifecycle_runtime_status_snapshot()` facade，继续调用既有
`DumpLifecycleGateService.runtime_status_snapshot()`，但显式把 legacy
`_dump_release_ready_hold_count` 投影为 debug schema 中兼容的 `dump_ready_hold_count`
/ `dump_release_ready_hold_count`。

5P `_make_debug_state()` 继续保留为 legacy override，负责 5P skill id、transition skill
集合和 approach/dump-release 兼容 fields；dump ready/done hold count 则从同一 dump
lifecycle status snapshot 读取。service 不接收 planner `self`，不调用 `_set_skill()`，
不 reset policy，不写 debug schema，也不改变 5P branch order 或 policy dispatch。

本切片不改变 debug-state key/key order、5P hold-count 输出值、switch reason、terminal
reason、policy reset timing、默认 config、token contract 或 rollout 输出。

### Coverage Debug Snapshot Slice

`CoverageService` 新增 coverage debug snapshot 能力，负责从 coverage-owned config /
state 中快照 active corridor、last-selected corridor、active corridor scalar fields、
state-exemplar ids、multi-pass config、productivity counters、terminal-stop state、
candidate scores 和 corridor debug payload。`DigCoverageMixin` 保留
`_coverage_debug_snapshot()` compatibility facade；planner `_debug_state_facts()` 从
该 snapshot 展开既有 coverage debug facts，不再逐字段读取 coverage service state。

本切片修正 debug facts 输入迁移后的过渡性边界：coverage debug facts 的 source of
truth 回到 coverage package，`PrimitiveDebugStateFacts` 保持平坦 facts contract，
`primitive_debug` 仍只负责 public debug-state key/order 和 coercion。service 不接收
planner `self`，不调用 `_set_skill()`，不 reset policy，不写 HDF5/checkpoint，也
不改变 coverage completion、terminal-stop 请求或 decision trace side effect。

本切片不改变 debug-state key、key order、coverage corridor debug payload、
state-exemplar id 类型、terminal-stop mirror 字段、candidate score payload、branch
order、threshold、switch reason、policy reset timing 或 rollout 输出。

### Cell Entry Debug Snapshot Slice

`CellEntryRuntimeService` 新增 `CellEntryDebugSnapshot` 投影能力，负责从
`CellEntryRuntimeState` 中快照 cell-entry goal/audit/seen-cell debug facts：
selected cell/indices、planned entry xyz、planner audit ok/reason/risk/entry-envelope
状态、distance fallback 和 first-seen cell latch。planner
`_cell_entry_debug_snapshot()` 只构造显式 runtime state 并调用 snapshot；
`_debug_state_facts()` 把 snapshot 展开为既有 `PrimitiveDebugStateFacts` 扁平字段。
`primitive_debug` 仍只负责 public debug-state key/order 和 coercion。

本切片修正 debug facts 输入迁移后的过渡性边界：cell-entry goal/audit fallback 的
source of truth 回到 cell-entry runtime capability，当前实现为
`testbed.planner.cell_entry_runtime`，而不是继续散在 `PrimitivePlannerACTPolicy`
大文件中。service 不接收 planner `self`，不调用
`_set_skill()`，不 reset policy，不写 HDF5/checkpoint，不写 debug schema，也不读取
observation 或生成 token。

本切片不改变 debug-state key、key order、167 字段数量、`goal None -> -1/NaN`、
`audit None -> False/-1/""/0/NaN`、seen-cell latch 输出、cell-entry token contract、
trace key names、branch order、threshold、switch reason、policy reset timing 或
rollout 输出。

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

## Return Start-Envelope Build Request Assembly Slice

`return_start_envelope` 新增 `build_return_start_envelope_request()`，负责把 planner
shell 显式采样的 return start-envelope 输入投影成
`ReturnStartEnvelopeBuildRequest`：env state、qpos/qvel legacy fallback、raw fields、
action dim、dig-cut prior、return start-envelope config 和 corridor/cell id。该 helper
不接收 planner `self`，不读取 observation，不构造 token，不写 planner state，不调用
`_set_skill()`，不 reset policy，也不写 debug schema。

同一边界后续新增
`build_return_start_envelope_request_from_observation_view()`，把
`PlannerObservationView` 到 build request 的 source projection 收回
return-start-envelope capability。projection 保留旧输入来源：env state 仍复用
`snapshots.env_state_from_obs()` 的 zero/default 语义，qpos/qvel 仍从 raw
`view.obs.get("qpos" / "qvel", np.zeros(action_dim))` 传入 request builder；raw fields、
dig-cut prior、runtime config 和 cell id 仍由 planner shell 按旧时机显式传入。

planner `_return_start_envelope_build_request()` 和
`_build_return_start_envelope_tokens_for_obs()` 作为旧 private facade 保留在 shell 内；
前者只负责创建 snapshot、采样 raw fields、dig-cut prior、config 和 cell id 后调用
source projection helper，后者只调用 request builder 与
`build_return_start_envelope_for_plan()`，然后写回 token source 与 prior-bounds flags。

本切片不改变 qpos/qvel fallback、prior lookup 优先级、source 字符串、qpos/spatial
conditioning、token 字段、fallback token、return target plan 生命周期、branch order、
policy reset timing、debug/summary schema 或 rollout 输出。

## Return Start-Envelope Token Result Projection Slice

`return_start_envelope` 新增 `ReturnStartEnvelopeTokenResult` 和
`require_return_start_envelope_token_result()`，负责把
`ReturnStartEnvelopeState` 投影成 planner 可写回的 token/source/prior-bounds result。
该 helper 保留 legacy missing-token error string，并只做 `float32` token projection、
source string 和 prior-bounds flags 的 bool 投影；不构造 token，不读取 observation，
不接收 planner `self`，不写 planner state，不调用 `_set_skill()`，不 reset policy，
也不写 debug schema。

planner `_apply_return_start_envelope_token_result()` 作为旧 private facade 保留在 shell
内，只负责调用 result helper，并把 source 与 prior-bounds flags 写回既有
`_return_start_envelope_*` runtime 字段。`_build_return_start_envelope_tokens_for_obs()`
和 `_maybe_condition_return_start_envelope_qpos_from_relocate()` 共用这个 apply facade，
避免 planner 大文件继续重复 token result writeback。

本切片不改变 return-start-envelope builder/relocate-conditioning 数值、source 字符串、
missing-token error text、qpos/spatial prior-bounds flags、return target plan 生命周期、
branch order、policy reset timing、debug/summary schema 或 rollout 输出。

## Return Start-Envelope Gate Prior Context Slice

`testbed.planner.return_start_envelope` 继续负责 return start-envelope gate 使用的
prior context 纯解析。本切片新增 gate prior context helper，集中处理 token 是否
带可用 qpos/spatial bounds、cell/global prior mapping 选择、prior p05/p95 bounds
解析，以及 corridor id 到 prior cell id 的 legacy fallback。

planner 大文件只保留旧 private facade：

- `_return_start_envelope_cell_id()`
- `_return_start_envelope_prior_mapping()`
- `_return_start_envelope_prior_bounds()`

`_return_to_dig_handoff_context()` 仍由 planner shell 负责按旧条件确保 return target
plan、从 coverage service 查 corridor/cell id、调用 handoff context builder，以及保留
branch order、switch reason、policy reset timing 和 debug/summary schema。

本切片不改变 gate-disabled / missing-token / invalid-token 的 permissive 行为，不
改变 cell prior、global-low-support fallback、global prior source string、prior
bounds shape fallback、`_pending_dig_cut_corridor_id < 0` 返回 `None` 或 coverage
corridor `cell_id` 优先于 corridor id 的 legacy 语义。

## Return Start-Envelope Prior Context Module Boundary Slice

`testbed.planner.return_start_envelope_prior` 作为 return start-envelope prior lookup
和 gate-prior context 的 focused capability module。它负责
`ReturnStartEnvelopeGatePriorContext`、token 是否携带 gate bounds、cell/global prior
mapping 选择、prior token source string、p05/p95 bounds 投影，以及 prior token shape
validation。`testbed.planner.return_start_envelope` 继续 re-export 这些 symbols，保护旧
public imports 和 planner facade 调用面。

本切片只修正 `return_start_envelope.py` 继续膨胀的责任边界，不改变
`ReturnStartEnvelopeConfig`、token build、relocate conditioning、ready gate 或 planner
handoff context assembly。prior module 不 import planner shell，不读取 observation，
不调用 `_set_skill()`，不 reset policy，不写 debug schema，也不复制 token constants；
它只从 `testbed.contracts.primitive_tokens` 引用既有 token dim/key/index source of
truth。

本切片不改变 gate-disabled / missing-token / invalid-token 的 permissive 行为，不改变
cell prior、global-low-support fallback、global prior source string、prior bounds
shape fallback、prior token error text、old import path、return handoff branch order、
switch reason、policy reset timing、debug/summary schema 或 rollout 输出。

## Return Handoff Context Assembly Slice

`testbed.planner.return_handoff` 继续作为 return-to-dig handoff context 与 gate 的
source-of-truth。本切片新增 `build_return_to_dig_handoff_context()`，负责把 planner
shell 已取出的 entry target、return start-envelope token/config、dig-cut prior、
resolved cell id 和 prior-bounds flags 投影成 `ReturnToDigHandoffContext`。builder
复用 `return_start_envelope_gate_prior_context()` 作为 prior mapping/bounds 的唯一
解析来源，只做 token `float32` projection、prior lower/upper/mapping projection 和
bool flag projection；不读取 observation，不接收 planner `self`，不查询 coverage，
不写 planner state，不调用 `_set_skill()`，不 reset policy，也不写 debug schema。

同一边界后续新增 `build_return_to_dig_handoff_context_from_runtime()`，把
planner runtime token、pending corridor id、prior-bound flags 和 lazy corridor-cell
resolver 投影成同一 `ReturnToDigHandoffContext`。该 helper 仍不接收 planner `self`；
它只在 token 具备 return start-envelope gate bounds 时调用显式
`corridor_cell_id_resolver`，再复用
`resolve_return_start_envelope_cell_id()` 保持 coverage corridor `cell_id` 优先于
corridor id 的旧 fallback 语义。

planner 大文件只保留旧 private facade：

- `_return_to_dig_handoff_context()`

planner shell 仍负责：

- 按旧条件调用 `_ensure_return_target_plan_for_cycle(obs)`
- 提供只读 `corridor_cell_id_resolver` facade，保持 coverage corridor lookup 的旧
  exception fallback
- 从 planner runtime state 读取当前 token、flags、pending corridor id、config 和
  dig-cut prior
- handoff gate evaluation、debug state 写回、branch order、switch reason、policy
  reset timing 和 rollout trace

本切片不改变 return start-envelope gate-disabled / missing-token / invalid-token
permissive 行为，不改变 prior mapping/bounds 选择、cell-id fallback、entry target
fallback、direct handoff、legacy shallow guard、return transition classification、
debug/summary schema、token contract、policy reset timing 或 rollout 输出。

## Return Start-Envelope Cell-ID Resolver Consolidation Slice

`return_start_envelope` 已经通过 `resolve_return_start_envelope_cell_id()` 拥有
return start-envelope prior lookup 的 corridor id / corridor cell id fallback 语义。
本轮不新增 service 或 helper，只回收 planner shell 中 return handoff context 对
cell-id fallback 的重复入口：`_return_to_dig_handoff_context()` 复用
`_return_start_envelope_cell_id()` 作为 runtime context builder 的 resolver。旧
`_return_start_envelope_corridor_cell_id()` 保留为 private compatibility helper，但不再
作为 handoff context 的主 resolver，避免 return start-envelope build path 与 handoff
gate-prior path 各自维护 cell-id fallback。

该旧 compatibility helper 的窄语义必须保留：它只执行 coverage corridor lookup，
找到 corridor 时返回真实 `cell_id`，corridor 缺失、lookup exception 或负 corridor
id 时返回 `None`。non-negative corridor id fallback 只属于
`_return_start_envelope_cell_id()` / `resolve_return_start_envelope_cell_id()` 的主
resolver 语义，不能为了进一步 consolidation 把旧 private helper 静默改成主 resolver
行为。

planner shell 仍负责 coverage corridor lookup 的调用时机和 exception fallback；
`return_start_envelope` capability 仍负责最终 `corridor_id < 0 -> None`、
coverage corridor `cell_id` 优先于 corridor id，以及 corridor 缺失时 fallback 到
non-negative corridor id 的旧语义。handoff context builder 仍只在 token 具备 gate
bounds 时调用 resolver，不读取 planner `self`，不写 planner state，不调用
`_set_skill()`，不 reset policy，也不写 debug schema。

本切片不改变 return start-envelope prior mapping/bounds 选择、cell-id fallback、
gate-disabled / missing-token / invalid-token permissive 行为、return handoff branch
order、switch reason、policy reset timing、debug/summary schema、token contract 或
rollout 输出。

## Return Transition Classification Slice

`testbed.planner.return_to_dig_transition` 作为 return-to-dig transition
classification 的 source-of-truth。本切片新增 `ReturnToDigTransitionService`，
负责在 planner shell 已按旧顺序计算好的 gate/fact 基础上，纯分类 return 分支的
transition outcome：next-dig event latch、direct start-envelope handoff、legacy
shallow guard handoff，或继续等待。service 返回 `ReturnToDigTransitionOutcome`
的 action、reason suffix 和建议的 `return_next_dig_event_seen` latch 值；完整
switch reason 仍通过 outcome 的 `switch_reason(next_skill_name)` 生成旧字符串。

后续 slice 在同一 service 中新增 `ReturnToDigTransitionRequest` 和
`transition_request()`，负责把 return 分支的 current boundary event、
previous next-dig-event latch、handoff-ready fact 和 semantic boundary profile fact
投影成 transition facts、transition config，以及是否应按旧短路顺序调用 direct
handoff gate 的 request bool。request 还提供
`should_check_shallow_guard(direct_handoff_ready)` 和 `facts_with_gate_results()`，
用于保留 direct handoff 优先于 legacy shallow guard 的旧顺序。service 不读取
observation，不调用 `_return_to_dig_direct_handoff_ready()` 或
`_return_to_dig_shallow_guard_ready()`，不写 `_return_next_dig_event_seen`，不更新
cycle/completed counters，也不调用 `_set_skill()`。

planner 大文件仍负责：

- `_return_to_dig_handoff_ready()`、`_return_to_dig_direct_handoff_ready()` 和
  `_return_to_dig_shallow_guard_ready()` 的实际 gate 调用
- `_completed_transition_count`、`_cycle_index` 和 `_return_next_dig_event_seen`
  写回
- next skill 选择、`_set_skill()`、policy reset timing、return direct handoff after
  dump/carry、debug schema 和 rollout trace

本切片不改变 return 分支顺序：
`next_dig_event latch + handoff_ready -> direct_handoff -> legacy shallow_guard`。
也不改变 `return_to_{next_skill}_next_dig_entry_ready`、
`return_to_{next_skill}_start_envelope_ready`、
`return_to_{next_skill}_shallow_entry_guard` reason 字符串、completed transition
计数、cycle index 更新、policy reset timing、debug/summary schema 或 rollout 行为。

## Return Direct-Handoff Attempt Slice

`testbed.planner.return_to_dig_transition` 继续作为 return-to-dig transition 的
source-of-truth。本切片扩展既有 `ReturnToDigTransitionService`，新增显式
`ReturnDirectHandoffAttemptFacts`、`ReturnDirectHandoffAttemptConfig` 和
`ReturnDirectHandoffAttemptOutcome`，负责纯分类 same-frame
dump/carry -> return -> dig/pre_dig_align direct handoff attempt：先按旧 guard
判断是否需要准备 return target 和计算 handoff gate，再在 planner 已计算
handoff/direct gate 后返回 direct-handoff outcome 与 reason suffix。

后续 slice 在同一 service 中新增 `ReturnDirectHandoffAttemptRequest` 和
`direct_handoff_attempt_request()`，负责把 active skill、return-target planner flag
和 direct-handoff flag 投影成初始 attempt facts/config/outcome，并提供
`facts_with_gate_results(handoff_ready, direct_handoff_ready)`。request 只表达
same-frame direct handoff 的 guard/facts 边界；不准备 return target，不调用
`_return_to_dig_handoff_ready()` 或 `_return_to_dig_direct_handoff_ready()`，不更新
cycle/completed counters，也不调用 `_set_skill()`。

planner 大文件仍负责：

- `_set_return_or_direct_handoff()` 先执行 `_set_skill("return", reason)`
- `_ensure_return_target_plan_for_cycle(obs)` 的调用时机
- `_return_to_dig_handoff_ready()` 与 `_return_to_dig_direct_handoff_ready()` 的实际
  gate 计算和 debug state 写回
- `_completed_transition_count`、`_cycle_index`、next skill 选择和 `_set_skill()`

本切片不改变 `_try_return_direct_handoff_at_current_obs()` 的 guard 顺序：
active skill must be return -> return-target planner enabled -> direct-handoff flag
enabled -> ensure return target plan -> handoff ready -> direct handoff ready；
也不改变 `return_to_{next_skill}_start_envelope_ready` reason 字符串、same-frame
dump/carry -> dig/pre_dig_align 行为、policy reset timing、debug/summary schema 或
rollout 输出。

## Return Transition Completion Projection Slice

`ReturnToDigTransitionService` 继续作为 return-to-dig transition 能力边界。本切片在
既有 transition/direct-handoff outcome 之后新增两阶段 completion projection：
service 先根据 outcome 纯返回 `_completed_transition_count` / `_cycle_index` 的建议增量，
planner shell 按旧语义先应用这些增量；随后 planner 按旧时机采样
`pre_dig_align_before_dig` fact，并通过 `completion_request()` 把该 fact 与显式
`ReturnToDigTransitionCompletionConfig` 投影为 completion request，再交给 service 纯返回
`ReturnToDigTransitionCompletion`，包含是否应 transition、next skill 和完整 switch
reason。

planner shell 仍负责：

- 只在旧成功分支内、且在 `_completed_transition_count` / `_cycle_index` 写回之后调用
  `_should_pre_dig_align_before_dig()`
- `_completed_transition_count` 与 `_cycle_index` 的实际写入和写入顺序
- `_set_skill()`、policy reset timing、return 分支/direct-handoff 的 gate 调用顺序
- `_return_next_dig_event_seen` latch 写回、debug/summary schema 和 rollout trace

本切片不改变 branch order、`return_to_{next_skill}_next_dig_entry_ready`、
`return_to_{next_skill}_start_envelope_ready`、
`return_to_{next_skill}_shallow_entry_guard` 字符串、计数增量、cycle index 先更新再采样
pre-dig-align 的旧时机、policy reset timing、debug/summary schema 或 rollout 输出。

## Return Transition Completion Request Builder Slice

`ReturnToDigTransitionService` 继续作为 return-to-dig transition completion 的
source-of-truth。本切片新增 `ReturnToDigTransitionCompletionRequest` 和
`completion_request()`，把普通 return 分支与 same-frame direct-handoff 分支中重复的
`ReturnToDigTransitionCompletionFacts` / `ReturnToDigTransitionCompletionConfig`
构造收回同一 return transition capability。planner shell 不再内联实例化 completion
facts/config dataclass；它只在旧 counter/cycle 写回之后采样
`_should_pre_dig_align_before_dig()`，把该 bool 和 `PRE_DIG_ALIGN_SKILL_NAME` 作为显式
输入交给 request builder。

planner shell 仍负责 return handoff/direct-handoff/shallow-guard gate 调用顺序、
runtime projection 写回、counter/cycle 写回之后再采样 pre-dig-align、调用
`transition_completion()` / `direct_handoff_completion()`、以及最终通过
`_apply_return_to_dig_transition_completion()` 调用 `_set_skill()`。request builder 不读取
observation，不接收 planner `self`，不更新 counters，不调用 `_set_skill()`，不 reset
policy，也不写 debug/summary schema。

本切片不改变 branch order、direct handoff / legacy shallow guard 优先级、
next-dig event latch、counter 增量、cycle index 先更新再采样 pre-dig-align 的旧时机、
`return_to_{next_skill}_*` reason 字符串、policy reset timing、debug/summary schema、
token contract 或 rollout 输出。

## Return Transition Runtime Projection Slice

`ReturnToDigTransitionService` 新增 `ReturnToDigTransitionRuntimeProjection` 和
`transition_runtime_projection()`，把 return 分支 outcome 之后的 runtime side-effect
建议收回 return transition capability：`_return_next_dig_event_seen` latch 值、
是否应进入 transition，以及 `_completed_transition_count` / `_cycle_index` 的建议增量。
该 projection 复用既有 `transition_counter_update()`，只返回显式建议，不写 planner
state。

planner return 分支仍负责实际 gate 调用顺序、`_return_next_dig_event_seen` 写回、
counter 写回、counter 写回之后再采样 `_should_pre_dig_align_before_dig()`、调用
`transition_completion()`，以及最终 `_set_skill()` / policy reset timing。service 不
接收 planner `self`，不读取 observation，不调用 `_set_skill()`，不 reset policy，不写
HDF5/checkpoint，也不写 debug schema。

本切片不改变 return branch order、next-dig event latch、direct handoff /
legacy shallow guard 优先级、计数增量、cycle index 先更新再采样 pre-dig-align 的旧
时机、`return_to_{next_skill}_*` reason 字符串、policy reset timing、debug/summary
schema 或 rollout 输出。

## Return Direct-Handoff Runtime Projection Slice

`ReturnToDigTransitionService` 继续作为 return-to-dig transition 能力边界。本切片在
same-frame dump/carry -> return -> dig/pre_dig_align direct-handoff attempt outcome
之后新增 `ReturnDirectHandoffRuntimeProjection` 和
`direct_handoff_runtime_projection()`，把 direct-handoff 成功后的
`_completed_transition_count` / `_cycle_index` 建议增量投影收回同一 return
transition service。该 projection 复用既有 `direct_handoff_counter_update()`，只返回
显式建议，不写 planner state。

planner direct-handoff 分支仍负责 `_set_return_or_direct_handoff()` 先切到
`return`、按旧顺序准备 return target、调用 handoff/direct handoff gates、实际 counter
写回、counter 写回之后再采样 `_should_pre_dig_align_before_dig()`、调用
`direct_handoff_completion()`，以及最终 `_set_skill()` / policy reset timing。service
不接收 planner `self`，不读取 observation，不调用 `_set_skill()`，不 reset policy，
不写 HDF5/checkpoint，也不写 debug schema。

本切片不改变 same-frame direct-handoff guard 顺序、计数增量、cycle index 先更新再采样
pre-dig-align 的旧时机、`return_to_{next_skill}_start_envelope_ready` reason 字符串、
policy reset timing、debug/summary schema 或 rollout 输出。

## Return Transition Runtime Projection Apply Facade Slice

`ReturnToDigTransitionService` 已经负责 return 分支与 same-frame direct-handoff
分支的 runtime projection；planner shell 现在保留一个统一的旧 private facade：

- `_apply_return_to_dig_transition_runtime_projection()`

该 facade 只应用 service 已返回的 lifecycle 建议：return 分支 projection 的
`_return_next_dig_event_seen` latch，以及 transition 成功时
`_completed_transition_count` / `_cycle_index` 的建议增量。它不调用 gate，不重新分类
outcome，不调用 `_set_skill()`，不 reset policy，不读取 observation，不写 debug
schema，也不持有新的领域语义。

planner return 分支和 same-frame direct-handoff 分支仍负责旧有调用顺序：
return-target 准备、handoff/direct-handoff/shallow guard gate 调用、counter 写回之后再
采样 `_should_pre_dig_align_before_dig()`、调用 completion projection，以及最终
`_set_skill()` / policy reset timing。本切片只消除两个分支中重复的 latch/counter
写回代码，避免让 transition side-effect projection 半散在 planner 大文件里。

本切片不改变 branch order、next-dig event latch 语义、direct handoff / legacy
shallow guard 优先级、counter 增量、cycle index 更新时机、`return_to_{next_skill}_*`
reason 字符串、policy reset timing、debug/summary schema、token contract 或 rollout
输出。

## Return Transition Completion Apply Facade Slice

同一 return transition 边界内的后续 consolidation 新增
`_apply_return_to_dig_transition_completion()`，把
`ReturnToDigTransitionCompletion` 中的最终 skill switch 应用收口到 planner shell 的
统一 facade。普通 return 分支和 same-frame direct-handoff 分支仍按旧顺序先应用 runtime
projection 写回 latch/counter/cycle，再采样 `_should_pre_dig_align_before_dig()` 并调用
service completion projection；完成后的 `should_transition` 判断、`next_skill` 和
`switch_reason` 应用都经由该 facade 调用 `_set_skill()`。

该 facade 不调用 return handoff/direct handoff/shallow guard gate，不重新分类 outcome，
不修改 counter 或 next-dig latch，不 reset policy，也不写 debug schema。它只保留 planner
shell 对 `_set_skill()` 和 reset timing 的所有权，避免最终 completion side effect 在普通
return 和 direct-handoff 两条路径中重复散落。

本切片不改变 branch order、direct handoff / legacy shallow guard 优先级、cycle index
先更新再采样 pre-dig-align 的旧时机、`return_to_{next_skill}_*` reason 字符串、
policy reset timing、debug/summary schema、token contract 或 rollout 输出。

## Return Transition Module Boundary Slice

`return_to_dig_transition` 作为 return-to-dig transition classification、same-frame
direct-handoff attempt、completion projection 和 runtime projection 的稳定
source-of-truth。`return_handoff` 只保留这些 transition/direct-handoff symbols 的
compatibility re-export，继续拥有 handoff gate、entry-target resolution、runtime
handoff config/status 和 return start-envelope context assembly。

本切片是责任边界修正，不新增调度语义：原 `ReturnToDigTransitionService` 及其
Facts/Config/Outcome/Projection dataclass 原样迁入 `return_to_dig_transition`；
planner 和 transition tests 改为直接引用新模块，旧 `return_handoff` import 继续可用以
保护现有调用方。新模块只依赖标准库 dataclass/typing，不 import `return_handoff`、
planner shell、snapshot、primitive decision、return start-envelope、token/schema 或
profile source-of-truth，因此不形成循环 import，也不复制 threshold 或 contract 语义。

planner shell 仍负责 return handoff/direct-handoff gate 调用顺序、
`_return_next_dig_event_seen` / `_completed_transition_count` / `_cycle_index` 实际写回、
counter 写回之后再采样 `_should_pre_dig_align_before_dig()`、`_set_skill()`、policy
reset timing、debug/summary schema 和 rollout trace。本切片不改变 branch order、
switch reason、terminal reason、counter 增量、policy reset timing、debug/summary
schema、token contract 或 rollout 输出。

## Return Next-Dig Entry Target Resolution Slice

`testbed.planner.return_handoff` 继续作为 return-to-dig handoff context 与 gate
能力的 source-of-truth。本切片新增 `ReturnNextDigEntryTargetResolver`，负责纯解析
return handoff context 需要的下一次 dig entry target：先使用当前 cycle 对应的
pending return-target raw fields，再 fallback 到 caller-provided active coverage
corridor entry target，最后返回 `None`。

planner 大文件只保留旧 private facade：

- `_return_to_dig_entry_target()`

planner shell 仍负责：

- 在 `_return_to_dig_handoff_context()` 中按旧条件调用
  `_ensure_return_target_plan_for_cycle(obs)`
- 从 coverage service 读取 active corridor，并把当前 pending state 与 active corridor
  作为参数传给 `build_return_next_dig_entry_target_facts_from_runtime()`
- `_return_to_dig_entry_error_for_obs()` legacy debug/helper 计算
- pending return-target plan 写回、coverage active corridor 写回、branch order、
  switch reason、policy reset timing 和 debug/summary schema

`return_handoff` 同时拥有 `build_return_next_dig_entry_target_facts()` 与
`build_return_next_dig_entry_target_facts_from_runtime()`，作为
`ReturnNextDigEntryTargetResolver` 的 facts assembly source-of-truth。builder 只做
旧语义中的 `cycle_index` / `pending_dig_cut_cycle_id` 整型投影，以及 active corridor
entry target 的 `(x, z)` float 投影；它不接收 planner `self`、不写回 pending plan 或
coverage corridor，也不改变 resolver 的 pending-first fallback 语义。

本切片不改变 target 优先级：`_pending_dig_cut_cycle_id == _cycle_index + 1` 且
`operator_entry_x_m` / `operator_entry_z_m` 都 finite 时使用 pending raw fields；
否则 fallback 到 active coverage corridor；无 active corridor 时返回 `None`。也不
改变 non-finite pending fallback、entry error `NaN` permissive 语义、return direct
handoff、legacy shallow guard、return target planner zero-fallback、coverage corridor
selection 或 rollout 行为。

## Return Start-Envelope Runtime Config Assembly Slice

`testbed.planner.return_start_envelope_config` 作为 return start-envelope runtime
config/coercion 的 source-of-truth。本切片新增
`build_return_start_envelope_config()`，负责把 planner shell 已维护的 runtime config
字段投影成 `ReturnStartEnvelopeConfig`：cell/global prior 选择、source support 阈值、
relocate-conditioned qpos/spatial coefficients 与 bounds、prior-bound reuse flags、
handoff gate tolerance、plane-depth mode、qpos tolerance 和 contact requirement。
`testbed.planner.return_start_envelope` 继续 re-export config symbols，保护旧 import
path；token build、relocate conditioning 和 handoff gate 仍留在
`return_start_envelope` capability。

planner 大文件只保留旧 private facade：

- `_current_return_start_envelope_config()`

planner shell 仍负责从当前 planner runtime state 读取字段、保持 return-target /
return-start-envelope token build 时机、return-to-dig handoff gate 调用顺序、debug
state 写回、branch order、switch reason、policy reset timing 和 rollout trace。
builder 只构造 `ReturnStartEnvelopeConfig` 并复用该 dataclass 的既有
`__post_init__` coercion；不接收 planner `self`，不读取 observation，不构造 token，
不查询 prior/corridor，不调用 handoff gate，不写 debug schema，也不调用
`_set_skill()`。

本切片不改变 `ReturnStartEnvelopeConfig` 默认值、min-source coercion、vector/matrix
shape/dtype coercion、plane-depth mode string、gate tolerance、prior-bound flags、
return start-envelope token source/fallback、return-to-dig handoff behavior、
debug/summary schema、policy reset timing 或 rollout 输出。

## Return Start-Envelope Runtime Config Mapping Slice

`testbed.planner.return_start_envelope_config` 继续作为 return start-envelope runtime
config/coercion 的 source-of-truth。本切片新增
`RETURN_START_ENVELOPE_RUNTIME_CONFIG_FIELDS` 和
`build_return_start_envelope_config_from_mapping()`，把
`_current_return_start_envelope_config()` 的 runtime config 字段映射收回到 domain
capability 内。planner 旧 private facade 只从自身当前字段构造 focused mapping 并
转调 builder。

service 只从显式 mapping 中读取 runtime config 字段并复用
`build_return_start_envelope_config()`；不接收 planner `self`，不读取 observation，
不构造 return start-envelope token，不查询 prior/corridor，不调用 return-to-dig
handoff gate，不写 debug schema，也不调用 `_set_skill()`。planner shell 仍负责
service 调用顺序、return-target / return-start-envelope token build 时机、handoff gate
调用顺序、debug state 写回、branch order、switch reason、policy reset timing 和
rollout trace。

本切片不改变 `ReturnStartEnvelopeConfig` 默认值、min-source coercion、vector/matrix
shape/dtype coercion、plane-depth mode string、gate tolerance、prior-bound flags、
return start-envelope token source/fallback、return-to-dig handoff behavior、
debug/summary schema、policy reset timing 或 rollout 输出。

## Return Start-Envelope Config Module Boundary Slice

`return_start_envelope_config` 作为 return start-envelope runtime config dataclass、
field table、mapping builder、direct builder、plane-depth mode normalization 和 config
coercion helper 的稳定 source-of-truth。`return_start_envelope` 只保留这些 config
symbols 的 compatibility re-export，并继续拥有 return start-envelope state/result、
build request、live token builder、relocate conditioning、cell-id resolution、
ready gate 和 prior module re-exports。

本切片是责任边界修正，不新增调度语义：原 `ReturnStartEnvelopeConfig`、
`RETURN_START_ENVELOPE_RUNTIME_CONFIG_FIELDS`、
`build_return_start_envelope_config()`、
`build_return_start_envelope_config_from_mapping()`、
`normalize_plane_depth_mode()` 以及 config-only `_optional_matrix()` / `_vector()` 原样迁入
`return_start_envelope_config`。新 config module 只依赖标准库和 numpy，不 import
planner shell、`return_start_envelope`、`return_handoff`、observation/parser、
token/schema 或 profile source-of-truth，因此不形成循环 import，也不复制 token
contract 或 gate semantics。

planner shell 仍负责 `_current_return_start_envelope_config()` 的字段采样、
return-target / return-start-envelope token build 时机、handoff gate 调用顺序、debug
state 写回、branch order、switch reason、policy reset timing 和 rollout trace。本切片
不改变 `ReturnStartEnvelopeConfig` 默认值、min-source coercion、vector/matrix
shape/dtype coercion、plane-depth mode alias/error text、gate tolerance、prior-bound
flags、return start-envelope token source/fallback、return-to-dig handoff behavior、
debug/summary schema、policy reset timing 或 rollout 输出。

## Return Entry Error Geometry Slice

`ReturnToDigHandoffGateService` 继续负责 return-to-dig handoff gate 使用的 entry
error 几何计算。本切片新增 `ReturnToDigEntryErrorFacts`，并让
`_return_to_dig_entry_error_for_obs()` 旧 private facade 与 handoff gate evaluation
共享同一个 service 方法。

planner 大文件只保留旧 private facade：

- `_return_to_dig_entry_error_for_obs()`

planner shell 仍负责从当前 observation 解析 bucket pose、调用
`_return_to_dig_entry_target()`、写回 `_return_to_dig_entry_error_m` /
`_return_to_dig_entry_close_state` debug state，以及 branch order、switch reason、
policy reset timing 和 rollout trace。service 只计算 `np.hypot(bucket_x-entry_x,
bucket_z-entry_z)`，并在 target、pose 或任一参与值缺失 / non-finite 时返回 `NaN`。

本切片不改变 `max_entry_error_m is None` 或 entry error 非 finite 时 entry-close
permissive 的旧语义，不改变 start-envelope gate、direct handoff、legacy shallow
guard、return transition classification、debug/summary key 或 rollout 行为。

## Return Handoff Status Projection Slice

`ReturnToDigHandoffGateService` 继续作为 return-to-dig handoff gate 状态的
source-of-truth。本切片新增 `ReturnToDigHandoffStatusState` 和
`ReturnToDigHandoffStatusSnapshot`，负责把 handoff config、return start-envelope
config 与 planner shell 已维护的 runtime state 投影成 debug-state 和 rollout-summary
共同需要的 handoff status facts：max entry error、entry error、entry close、
next-dig event latch、start-envelope gate/direct flags、ready state、plane-depth mode、
local-depth tolerance、error 和 checks。

后续同一切片新增 `RETURN_TO_DIG_HANDOFF_STATUS_FIELDS` 和
`build_return_to_dig_handoff_status_state_from_mapping()`，把 planner 当前
`_return_to_dig_*` runtime fields 到 `ReturnToDigHandoffStatusState` 的投影收回
return handoff capability。planner 旧 private facade 只按字段表采样当前 state 后调用
builder；checks payload 复制、bool/float coercion 和 status-state contract 由
`return_handoff` 统一负责。

planner 大文件只保留薄 facade：

- `_return_to_dig_handoff_status_snapshot()`

planner shell 仍负责 `_return_to_dig_entry_error_m`、
`_return_to_dig_entry_close_state`、`_return_next_dig_event_seen`、
`_return_to_dig_start_envelope_ready_state`、error/checks 的写回时机，以及
return target token、return relocate token、return start-envelope token 的组装和
public debug/summary schema 展开。service 不接收 planner `self`，不调用
`_set_skill()`，不 reset policy，不写 debug schema，不读取 observation，也不生成
token。

本切片不改变 debug-state 或 rollout-summary key/key order、bool/int coercion、
`None -> NaN` summary fallback、entry-close permissive 语义、start-envelope gate、
return 分支顺序、switch reason、threshold、policy reset timing、token contract 或
rollout 输出。

## Return Handoff Evaluation Status Projection Slice

`ReturnToDigHandoffGateService` 继续作为 return-to-dig handoff gate evaluation 与
status projection 的 source-of-truth。本切片新增
`runtime_state_from_decision()`，负责把 `ReturnToDigHandoffDecision` 纯投影成
`ReturnToDigHandoffStatusState`：entry error、entry-close、start-envelope ready /
error / checks，以及 caller-provided next-dig-event latch。projection 只复制 decision
中已有的 status facts，不重新计算 gate，不读取 observation，不接收 planner `self`，
不写 planner state，不调用 `_set_skill()`，不 reset policy，也不写 debug schema。

planner `_evaluate_return_to_dig_handoff()` 仍保留旧 private facade 和 shell 副作用：
按旧顺序构造 snapshot、boundary facts、handoff context 和 config，调用
`ReturnToDigHandoffGateService.evaluate()`，再把 service 返回的 status state 写回既有
`_return_to_dig_*` runtime fields。planner 仍负责 `_return_next_dig_event_seen` 的
transition latch 写回时机；本 projection 只保持当前 latch 值，不决定 return
transition outcome。

本切片不改变 handoff gate 计算、start-envelope checks payload、direct handoff、
legacy shallow guard、return transition classification、branch order、switch reason、
counter 增量、policy reset timing、debug/summary schema、token contract 或 rollout
输出。

## Return Handoff Evaluation Runtime Apply Facade Slice

planner shell 保留 `_apply_return_to_dig_handoff_runtime_state()` 作为 return-to-dig
handoff runtime/status 的唯一写回 facade。`_evaluate_return_to_dig_handoff()` 在
`ReturnToDigHandoffGateService.evaluate()` 和
`runtime_state_from_decision()` 之后只调用该 apply facade，不再在 evaluation 方法内逐项
写回 `_return_to_dig_entry_error_m`、entry-close、next-dig-event latch、
start-envelope ready/error/checks。

本切片不改变 handoff evaluation 的 snapshot/context/config 构造顺序，不改变
`runtime_state_from_decision()` 的 next-dig-event latch 输入，也不把写回副作用迁入
`ReturnToDigHandoffGateService`。service 仍只返回显式 decision/status state；planner
shell 仍负责实际 mutable state 写回、return transition latch 更新时机、branch order、
switch reason、policy reset timing、debug/summary schema、token contract 和 rollout
输出。

## Return Handoff Runtime Reset Slice

`ReturnToDigHandoffGateService` 新增 `initial_runtime_state()`，继续复用
`ReturnToDigHandoffStatusState`，负责投影 return-to-dig handoff runtime 的 legacy
reset 默认值：entry error、entry-close latch、next-dig event latch、return
start-envelope ready state、start-envelope error 和 checks。service 只返回显式
runtime/status state；不接收 planner `self`，不调用 `_set_skill()`，不 reset policy，
不写 HDF5/checkpoint，不写 debug schema，不读取 observation，不生成 return target /
return start-envelope token，也不执行 handoff gate。

planner `_reset_return_to_dig_handoff_runtime()` 和
`_apply_return_to_dig_handoff_runtime_state()` 作为旧 private facade 保留在 shell 内，
只负责调用 service 并把返回 state 应用到既有 `_return_to_dig_*` 与
`_return_next_dig_event_seen` 字段。`reset()` 的 policy reset、boundary detector
reset、active skill 选择、switch reason、pre-dig-align/cell-entry/dig-cut/depth-profile
reset、return-target conditioning reset 和 coverage reset 顺序仍由 planner shell
拥有。

本切片不改变 reset timing、初始 active skill、switch reason `reset`、entry-close
permissive 默认值、next-dig event latch 默认值、start-envelope ready/error/checks
默认值、handoff gate/transition classification、debug/summary schema、policy reset
timing、token contract 或 rollout 输出。

## Dig-Cut Plan Assembly Slice

新增模块：

- `testbed/planner/dig_cut_plan.py`

`dig_cut_plan` 负责 dig-cut raw fields、token、source string 和 fallback reason
的纯组装：conservative live-pose raw fields/token、operator-prior pose clamp、
missing-pose median fallback，以及 prior percentile/clamp helper。该模块不选择
coverage corridor，不更新 coverage/current-cycle state，不写 pending return-target
plan，不决定 planner mode fallback，也不 dispatch policy。

后续同一边界新增 `build_raw_fields_dig_cut_plan()`，负责把 planner 或 coverage
capability 已经选好的 raw fields 投影成 `DigCutPlan`。planner 的 coverage dig-cut
paths 不再直接调用数据层私有 `_build_dig_cut_token()`；planner 仍负责 coverage
corridor selection、`_coverage_raw_fields(..., update_state=True)`、
`_coverage_active_corridor_id` 写回、return-target source prefix 和 branch order。
该 helper 不复制 raw fields，以保持 return-target build projection 的既有对象身份
语义。

planner 大文件只保留旧 private facade：

- `_raw_fields_from_live_pose()`
- `_build_operator_prior_dig_cut_tokens()`
- `_prior_percentile()`
- `_clamp_to_prior()`

`_build_dig_cut_tokens_for_obs()` 和 `_build_next_dig_cut_plan_for_return()` 仍保留为
planner shell facade：它们调用 dig-cut service 做纯 dispatch classification，并继续
负责 pending return-target plan 复用、fallback-mode 执行、coverage active corridor
写回、prior-range debug flag 写回和 return target source prefix。coverage mode 的
corridor selection / raw-fields 仍由 `testbed/planner/dig_coverage/` 负责；不把通用
operator-prior dig-cut 组装塞进 coverage package。

本切片不改变 dig-cut token dim/order、operator-prior source string、
`missing_bucket_dig_area_pose` fallback reason、fallback conservative token、pending
return-target source、coverage corridor selection、prior-range debug flag、policy
dispatch、branch order 或 rollout/debug schema。

## Dig-Cut Plan Attempt Resolution Slice

`testbed.planner.dig_cut_plan` 继续作为 dig-cut plan/token assembly 的
source-of-truth。本切片新增 `DigCutPlanService`、`DigCutPlanAttempt`、
`DigCutPlanSuccessAttemptFacts`、`DigCutPlanFailureAttemptFacts` 和
`DigCutPlanState`，负责在 planner shell 已按原 mode branch 调用 builder、计算好
prior-range flag，或已捕获异常并构造好 fallback conservative plan 后，纯组装
attempt 并解析成返回给 planner 的 token/source/fallback reason/prior-range state。
service 不接收 planner `self`，不调用 coverage service，不读取 observation，不选择
mode，不捕获异常，不决定 fallback policy，也不写 planner debug state。

planner 大文件仍负责：

- pending return-target branch 与所有 dig-cut planner mode branch order
- `operator_prior` / `operator_prior_coverage` / `operator_prior_sweep_belief`
  builder 调用
- coverage corridor selection、coverage raw fields `update_state=True` 和 active
  corridor 写回
- `_raw_fields_in_prior_range()` 的 source-of-truth 调用
- `dig_cut_planner_fallback_mode != "conservative_pose"` 时的原地 re-raise
- fallback conservative plan 的 observation pose 采样与 source/fallback reason
  填充
- `_dig_cut_token_source`、`_dig_cut_fallback_reason`、
  `_dig_cut_token_in_prior_p10_p90` 的最终写回

本切片不改变 conservative pose、operator-prior、coverage 或 sweep-belief 的 mode
顺序，不改变 fallback conservative source/fallback reason、no-fallback exception
行为、prior-range flag、coverage state side effects、pending return-target reuse、
policy dispatch、debug/summary schema 或 rollout 行为。

同一 attempt-resolution 边界后续新增
`DigCutPlanService.state_from_success_plan()`，把 planner 已经构造好的
`DigCutPlan` 直接投影为 `DigCutPlanState`。该入口复用既有
`DigCutPlanAttempt.success(...) -> state_from_attempt(...)` 路径，只让
`_build_dig_cut_tokens_for_obs()` 的 conservative-pose 分支不再手写
`DigCutPlanSuccessAttemptFacts`。planner 仍负责 conservative pose 的 observation 采样、
pending return-target branch priority、mode dispatch、coverage side effects 和最终
`_apply_dig_cut_plan_state()` 写回。

## Dig-Cut Token Result Projection Slice

`DigCutPlanService` 新增 `DigCutPlanTokenResult` 和 `token_result()`，负责把
`DigCutPlanState` 纯投影成 planner shell 需要写回和返回的 token/source/fallback
reason/prior-range result。该 projection 保留旧 `np.asarray(..., dtype=np.float32)`
token 语义：float32 token 不额外 copy，非 float32 token 只按旧路径 cast。

planner `_apply_dig_cut_plan_state()` 作为旧 private facade 保留在 shell 内，只负责
调用 service projection、写回 `_dig_cut_token_source`、
`_dig_cut_fallback_reason`、`_dig_cut_token_in_prior_p10_p90`，并返回投影后的
dig-cut token。`_build_dig_cut_tokens_for_obs()` 的 pending return-target branch、
conservative pose、operator-prior、coverage 和 sweep-belief branch order 仍由 planner
shell 拥有。

本切片不改变 dig-cut token dim/order、source/fallback string、prior-range flag、
fallback conservative 行为、no-fallback exception 行为、coverage side effects、
pending return-target reuse、policy dispatch、debug/summary schema 或 rollout 输出。

## Dig-Cut Plan Cycle Gate Decision Slice

`DigCutPlanService` 继续负责 dig-cut plan/token 的纯 assembly 与 gate decision。本切片
新增 `DigCutPlanCycleConfig`、`DigCutPlanCycleFacts` 和
`DigCutPlanCycleDecision`，把 `_ensure_dig_cut_plan_for_cycle()` 开头的 enabled /
hold-existing / build 判定迁入 service。service 只接收显式 config/facts，返回
action 与 `should_build`；不选择 mode，不调用 builder，不读取 observation，不生成
dig-cut token，不构造 depth-profile token，不写 planner state，也不写 debug schema。

planner 大文件仍负责：

- 提供当前 enabled / hold / planned-cycle / cycle-index runtime scalar，并按
  `should_build` 早退
- pending return-target branch 与所有 dig-cut planner mode branch order
- `_build_dig_cut_tokens_for_obs()` 和 `_build_dig_depth_profile_tokens_for_obs()`
  的调用顺序
- `_dig_cut_tokens`、`_dig_depth_profile_tokens` 和 `_dig_cut_planned_cycle_id`
  的最终写回
- coverage state side effects、fallback behavior、policy dispatch、debug/summary
  schema 和 rollout trace

同一 cycle gate 边界后续新增
`DigCutPlanService.cycle_decision_from_runtime()`，把 planner runtime scalar 到
`DigCutPlanCycleConfig` / `DigCutPlanCycleFacts` 的投影收回 dig-cut service。planner
`_ensure_dig_cut_plan_for_cycle()` 仍只负责传当前字段、按 `should_build` 早退，并按旧
顺序先构造 dig-cut token、写入 `_dig_cut_tokens` 中间态、再构造 depth-profile token。
service 不读取 observation、不选择 planner mode、不调用 builder、不生成 token、不写
planner state，也不写 debug schema。

本切片不改变 dig-cut disabled 早退效果、hold-existing 行为、dig-cut token 先于
depth-profile token 的 build order、planned cycle id 写回时机、pending return-target
reuse、mode branch order、fallback conservative source/fallback reason、coverage side
effect、switch reason、policy reset timing、debug/summary schema 或 rollout 输出。

## Dig-Cut Plan Cycle Apply Projection Slice

`DigCutPlanService` 继续承载 dig-cut cycle 的纯 decision/result projection。本切片
新增 `DigCutPlanCycleApplyState` 和 `cycle_apply_state()`，把
`_ensure_dig_cut_plan_for_cycle()` 在完成 cycle build 后需要写回的
`_dig_cut_tokens`、`_dig_depth_profile_tokens` 和 `_dig_cut_planned_cycle_id`
收口成显式 service result。service 只接收已经由 planner shell 构建出的 dig-cut
token、depth-profile token 和当前 cycle index，并返回 planned cycle id 的 `int`
投影；不读取 observation，不调用 builder，不 copy/cast token，不写 planner state，
也不写 debug schema。

planner shell 仍负责 enabled/hold-existing gate 的调用顺序、dig-cut token 先于
depth-profile token 的 build order、build depth-profile 前的 legacy `_dig_cut_tokens`
中间写回、最终字段赋值、pending return-target reuse、coverage side effects、
fallback behavior、policy dispatch、debug/summary schema 和 rollout trace。

本切片不改变 dig-cut disabled 早退效果、hold-existing 行为、dig-cut token 先于
depth-profile token 的 build order、build depth-profile 前的 `_dig_cut_tokens` 可见性、
planned cycle id 的最终写回语义、pending return-target reuse、mode branch order、
fallback conservative source/fallback reason、coverage side effect、switch reason、
policy reset timing、debug/summary schema 或 rollout 输出。

## Dig-Cut Plan Cycle Apply Facade Slice

planner shell 保留 `_apply_dig_cut_plan_cycle_state()` 作为 dig-cut cycle build 完成后
的唯一 cycle-state 写回 facade。`_ensure_dig_cut_plan_for_cycle()` 仍按旧顺序先调用
`_build_dig_cut_tokens_for_obs(obs)`，把返回 token 暂写入 `_dig_cut_tokens`，再调用
`_build_dig_depth_profile_tokens_for_obs(obs)`，最后把
`DigCutPlanService.cycle_apply_state()` 返回的 `DigCutPlanCycleApplyState` 交给该
apply facade。

该 facade 只写回 service 已返回的 `_dig_cut_tokens`、
`_dig_depth_profile_tokens` 和 `_dig_cut_planned_cycle_id`；不调用 builders，不选择
planner mode，不处理 pending return-target，不执行 coverage side effect，不 dispatch
policy，不 reset policy，也不写 debug schema。service 仍只做纯 cycle-state projection，
planner shell 仍拥有 build order、fallback behavior、coverage side effects 和 policy
observation injection timing。

本切片不改变 dig-cut disabled 早退效果、hold-existing 行为、dig-cut token 先于
depth-profile token 的 build order、build depth-profile 前的 `_dig_cut_tokens` 可见性、
planned cycle id 写回语义、pending return-target reuse、mode branch order、
fallback conservative source/fallback reason、coverage side effect、switch reason、
policy reset timing、debug/summary schema、token contract 或 rollout 输出。

## Dig-Cut Plan Dispatch Decision Slice

`DigCutPlanService` 新增 `DigCutPlanDispatchFacts` 和
`DigCutPlanDispatchDecision`，负责把 `_build_dig_cut_tokens_for_obs()` 开头的纯
dispatch classification 迁入 dig-cut capability：current-cycle pending
return-target token 优先，否则按 `dig_cut_planner_mode` 解析为
`conservative_pose`、`operator_prior` 或 coverage-style builder；其中
`operator_prior_sweep_belief` 继续复用 coverage builder kind。service 只返回 action
与 builder kind；不读取 observation，不调用 builder，不选择 coverage corridor，不做
fallback conservative plan，不写 planner state，也不写 debug schema。

planner `_build_dig_cut_tokens_for_obs()` 作为旧 private facade 保留在 shell 内，仍
负责 pending return-target activation、conservative live-pose plan 构造、
operator-prior / coverage builder 调用、fallback-mode exception handling、
coverage active corridor side effects、prior-range 判断和 `_apply_dig_cut_plan_state()`
写回。unsupported mode 的 `ValueError` 文本保持原样；pending current-cycle token
仍优先于 mode validation。

本切片不改变 pending return-target branch priority、conservative pose、
operator-prior、coverage 或 sweep-belief 的 mode 顺序，不改变 fallback conservative
source/fallback reason、no-fallback exception 行为、prior-range flag、coverage state
side effects、policy dispatch、debug/summary schema 或 rollout 输出。

## Dig-Cut Builder Attempt Resolution Slice

`DigCutPlanService` 继续作为 dig-cut plan attempt / state projection 的 source of
truth。本切片新增 `state_from_builder_attempt()`，把
`_dig_cut_plan_state_from_builder()` 中的 builder success/failure attempt resolution
收回 dig-cut capability：service 接收 planner shell 显式提供的 `build_plan`
callback、prior-range checker、fallback mode 和 fallback-plan factory，负责把成功
builder result 包装成 `DigCutPlanSuccessAttemptFacts`，或在 builder failure 且 fallback
mode 为 `conservative_pose` 时包装成 `DigCutPlanFailureAttemptFacts`，最后复用
`state_from_attempt()` 生成 `DigCutPlanState`。fallback mode 不是
`conservative_pose` 时仍 re-raise 原异常。

planner shell 仍负责 `_build_dig_cut_tokens_for_obs()` 的 branch order 和具体 builder
选择：pending return-target activation、conservative pose、operator-prior、
operator-prior coverage/sweep-belief，以及 unsupported-mode error。planner shell 也仍
拥有 coverage corridor selection、coverage raw-field state update、fallback conservative
pose 采样、dig-depth-profile build timing、`_apply_dig_cut_plan_state()` 写回、
policy dispatch、debug/summary schema 和 rollout trace。service 不接收 planner
`self`，不读取 observation，不调用 `_set_skill()`，不 reset policy，不写 HDF5 /
checkpoint，也不写 debug schema。

本切片不改变 builder 调用时机、fallback conservative source/fallback reason、
no-fallback exception 行为、raw-fields prior-range flag、coverage side effects、
pending return-target priority、mode branch order、switch reason、policy reset timing、
debug/summary schema 或 rollout 输出。

## Return-Target Dig-Cut Dispatch Reuse Slice

`_build_next_dig_cut_plan_for_return()` 复用既有
`DigCutPlanService.dispatch_decision()` 与 `DigCutPlanDispatchFacts`，避免在
return-target facade 中复制另一份 `dig_cut_planner_mode` mapping。该 call 显式传入
`pending_tokens_present=False`，因此 pending return-target activation 仍只属于
`_build_dig_cut_tokens_for_obs()` 的 current-cycle pending branch；return-target build
path 不会消费 pending dig-cut state。

planner shell 仍负责实际 builder 调用与 side effects：conservative pose plan 构造、
operator-prior builder 调用、coverage corridor selection、`_coverage_raw_fields(...,
update_state=True)`、`_coverage_active_corridor_id` 写回，以及 return-target source
prefix。coverage 与 sweep-belief 继续共用 coverage builder kind，但 source string
仍使用原始 `dig_cut_planner_mode`，因此
`return_target_operator_prior_sweep_belief` 保持不变。unsupported mode 的
`ValueError` 文本仍由同一个 dig-cut dispatch service 产生。

本切片不新增 return-target dispatch service，不新增 token/schema/profile source-of-truth，
不改变 return-target conservative/operator-prior/coverage/sweep-belief branch 行为、
pending activation timing、coverage side effects、source/fallback string、debug/summary
schema、policy reset timing 或 rollout 输出。

## Return-Target Dig-Cut Build Result Projection Slice

`ReturnTargetPlanService` 新增
`ReturnTargetDigCutBuildResultConfig`、`ReturnTargetDigCutBuildFacts` 和
`dig_cut_build_result()`，负责把 return-target dig-cut builder 输出投影成 planner
旧 facade 需要返回的 token、raw fields、source、fallback reason 和 corridor id。
source prefix 由显式 config 提供，builder source suffix、fallback reason 与 corridor
id 由 facts 提供；projection 不复制 raw fields、不 cast token，只保留旧 branch 已经
执行过的 dtype / object identity 语义。

后续同一边界新增 `ReturnTargetDigCutBuildContext`、
`dig_cut_build_context()`、`dig_cut_build_result_from_parts()` 和
`ReturnTargetDigCutBuildResult.legacy_tuple()`，把
`_build_next_dig_cut_plan_for_return()` 中重复的 source-prefix context、facts 构造和
legacy tuple projection 收回 return-target state assembly capability。context 只保存
caller 已通过 `DigCutPlanService.dispatch_decision()` 得到的 builder kind、原始
planner mode 和 source prefix；它不重新分类 mode，不读取 pending plan，也不选择
coverage corridor。

planner `_build_next_dig_cut_plan_for_return()` 仍负责 dig-cut dispatch decision 的
调用顺序、conservative pose / operator-prior / coverage builder 调用、coverage
corridor selection、`_coverage_active_corridor_id` 写回、
`_coverage_raw_fields(..., update_state=True)` side effect，以及 unsupported mode 的
`ValueError`。coverage 与 sweep-belief 仍共用 coverage builder kind，但 source suffix
继续使用原始 `dig_cut_planner_mode`，因此
`return_target_operator_prior_sweep_belief` 保持不变。

本切片不新增 module，不复制 token/schema/profile source-of-truth，不改变
conservative/operator-prior/coverage branch order、pending return-target activation
timing、coverage side effects、source/fallback string、corridor id、unsupported-mode
error text、debug/summary schema、policy reset timing 或 rollout 输出。

## Dig-Cut Runtime Status Projection Slice

`DigCutPlanService` 继续作为 dig-cut plan/token runtime state 的 capability
边界。本切片新增 `DigCutRuntimeStatusConfig`、`DigCutRuntimeStatusState` 和
`DigCutRuntimeStatusSnapshot`，负责把 planner shell 已维护的 dig-cut runtime state
投影成 debug-state 与 rollout-summary 共同需要的 facts：pending cycle/corridor id、
token injected flag、planner mode、prior id、token source、dig-cut tokens、
prior-range flag 和 fallback reason。

后续同一切片新增 `DIG_CUT_RUNTIME_STATUS_CONFIG_FIELDS`、
`DIG_CUT_RUNTIME_STATUS_STATE_FIELDS`、
`build_dig_cut_runtime_status_config_from_mapping()` 和
`build_dig_cut_runtime_status_state_from_mapping()`，把 planner 当前 dig-cut runtime
config/state 字段到 status config/state dataclass 的投影收回 dig-cut capability。
planner 旧 private facade 只按字段表采样当前 state 后调用 builder；`str` / `int` /
`bool` coercion 和 status-state contract 由 `dig_cut_plan` 统一负责。token array
仍由 `runtime_status_snapshot()` 做旧 `float32` copy，mapping builder 不复制 token
contract 或 token dim source-of-truth。

后续同一切片继续新增 `DigCutPlanService.runtime_status_snapshot_from_mappings()`，
把 config/state mapping builders 到 snapshot projection 的组合收回
`DigCutPlanService`。planner 旧 private facade 仍只负责按字段表采样当前 planner
runtime state，并把 config/state mapping 交给 service；typed dataclass 构造、
coercion 和 snapshot float32 token copy 继续由 dig-cut capability 统一负责。

planner 大文件只保留薄 facade：

- `_dig_cut_runtime_status_snapshot()`

planner shell 仍负责 pending return-target activation、dig-cut mode branch order、
coverage corridor selection、raw-fields prior-range 计算、dig-depth-profile token
生成、`_dig_cut_tokens` / source / fallback / prior-range flag 的写回时机，以及
public debug/summary schema 展开。service 不接收 planner `self`，不调用
`_set_skill()`，不 reset policy，不写 debug schema，不读取 observation，不选择
planner mode，也不生成 token。

本切片不改变 debug-state 或 rollout-summary key/key order、token dim/order、
token injected bool/int coercion、pending id fallback、source/fallback string、
prior-range flag、pending return-target branch、coverage side effect、switch reason、
policy reset timing 或 rollout 输出。

## Dig-Cut Runtime Reset Slice

`DigCutPlanService` 新增 `DigCutRuntimeState` 和 `initial_runtime_state()`，负责
投影 dig-cut runtime 的 legacy reset 默认值：dig-cut token zeros、token injected
flag、planned cycle id、token source、fallback reason 和 prior-range flag。service
只返回显式 runtime state；不接收 planner `self`，不调用 `_set_skill()`，不 reset
policy，不写 HDF5/checkpoint，不写 debug schema，不读取 observation，不选择 planner
mode，也不生成新的 dig-cut plan。

planner `_reset_dig_cut_runtime()` 和 `_apply_dig_cut_runtime_state()` 作为旧
private facade 保留在 shell 内，只负责调用 service 并把返回 state 应用到既有
`_dig_cut_*` 字段。`reset()` 的 policy reset、boundary detector reset、
active skill 选择、switch reason、cell-entry reset、dig-depth-profile reset、
return-target conditioning reset、return-to-dig handoff state 和 coverage reset 顺序
仍由 planner shell 拥有。

本切片不改变 reset timing、初始 active skill、switch reason `reset`、dig-cut token
dim/order、source/fallback string、prior-range flag 默认值、debug/summary schema、
policy observation injection、policy reset timing 或 rollout 输出。dig-depth-profile
runtime 默认值仍属于 `DigDepthProfileService` 的后续独立 slice，本轮不混合迁移。

## Dig Depth-Profile Builder Slice

新增模块：

- `testbed/planner/dig_depth_profile.py`

`DigDepthProfileService` 负责 dig depth-profile token 的 source selection 和
token 构造：`live_plan`、`prior_profile`、state-conditioned exemplar 优先级、
cell/global prior fallback、prior token shape/finite validation、required prior
缺失错误、live plan token build，以及从 caller-provided facts 解析 raw-fields /
cell id 的 fallback 级联。service 只接收显式 `DigDepthProfileInputFacts`、
`DigDepthProfileBuildRequest`、`DigDepthProfileConfig`、prior/raw-fields/env-state
和可选 exemplar token，不接收 planner `self`，不读取 coverage state，不写 pending
dig state，不 dispatch policy，不 reset policy，也不写 debug schema。

planner 大文件只保留旧 private facade：

- `_build_dig_depth_profile_tokens_for_obs()`
- `_build_live_dig_depth_profile_tokens_for_obs()`
- `_dig_depth_profile_prior_token()`
- `_dig_depth_profile_prior_mapping()`
- `_dig_depth_profile_token_from_prior_mapping()`
- `_dig_depth_profile_raw_fields()`
- `_dig_depth_profile_cell_id()`

其中 `_build_dig_depth_profile_tokens_for_obs()` 只负责解析当前 cell id、装配
raw fields/env state/config/exemplar request、调用 service，并写回
`_dig_depth_profile_token_source` 与 `_dig_depth_profile_fallback_reason`。planner
shell 的 `_dig_depth_profile_raw_fields()` 与 `_dig_depth_profile_cell_id()` 只收集
pending dig、active coverage corridor、live pose/current dig token 和 env-state facts
并转调 service resolver；planner 仍负责 coverage/pending dig state、return target
plan、branch order、switch reason、debug schema 和 rollout trace。

`DigDepthProfileInputSourceFacts` 和
`build_dig_depth_profile_input_facts()` 是 dig depth-profile input facts assembly 的
source-of-truth。planner shell 仍按旧短路顺序读取 pending dig state、coverage
corridor、live pose 和 env-state；service 只接收显式 source facts，并负责投影成
`DigDepthProfileInputFacts`：current-cycle pending raw/cell 优先，stale pending
忽略，active raw/cell 只填补 pending 缺口，live raw 只在 pending/active raw 都缺失
时使用，env-state 只在 caller 显式要求或 pending/active cell 都缺失时透传。该
builder 保留 planner facade 传入的 raw-fields、token 和 env-state 引用语义，不复制
token/schema/profile/source-of-truth。

`DigDepthProfileService.build_token_from_input_facts()` 是
`DigDepthProfileInputFacts -> DigDepthProfileState` 的 domain entry point。它先按
既有 priority 调用 `resolve_cell_id()` 与 `resolve_raw_fields()`，再构造
`DigDepthProfileBuildRequest` 并复用 `build_token()`。planner shell 只采样 pending
return-target facts、active coverage facts、live pose fallback 和 env-state，然后调用
该入口；service 不读取 planner state、不选择 coverage corridor、不写回 token source /
fallback reason。

本切片不改变 token dim/order、source string、prior fallback 策略、required prior
失败信息、live token 数值、pending dig plan、coverage state exemplar 选择、
debug_state 字段或 rollout 行为。

## Dig Depth-Profile Input Source Sampling Slice

`DigDepthProfileService` 继续作为 dig depth-profile input source selection 的
capability 边界。本切片新增 `DigDepthProfileInputSourcePlan` 和
`input_source_plan()`，把 `_dig_depth_profile_input_facts()` 中 pending / active /
live / env 的采样 gate 收回 service：current-cycle pending raw/cell 优先，stale
pending 不采样，pending raw 当前存在时只允许 active corridor 补 missing cell，
active raw 缺失后才允许 live raw fallback，env-state 只在 caller 显式要求或
pending/active cell 都缺失时采样。

planner `_dig_depth_profile_input_facts()` 作为旧 private facade 保留在 shell 内，
仍负责按 service 返回的分阶段 plan 调用 `_coverage_corridor_by_id()`、
`_coverage_active_corridor()`、`_coverage_raw_fields()`、
`_raw_fields_from_live_pose()` 和 `_env_state()`，并把已采样 source 交回
`DigDepthProfileService.input_facts()`。该 facade 保留旧调用顺序：pending corridor
lookup、active corridor lookup、active raw/cell、live raw、env-state；service 不读取
coverage state、不接收 planner `self`、不复制 token/schema source-of-truth、不写回
token source/fallback reason，也不 reset policy 或写 debug schema。

本切片不改变 pending raw / active raw / live raw / env-state 对象引用语义、
`include_env_state=True` 的强制 env 采样、stale pending 忽略规则、cell id fallback、
token dim/order、source/fallback string、policy observation injection、debug/summary
schema、branch order、switch reason、policy reset timing 或 rollout 输出。

## Dig Depth-Profile Input Source Callback Assembly Slice

`DigDepthProfileService` 继续作为 dig depth-profile input source sampling 与
`DigDepthProfileInputFacts` assembly 的 capability 边界。本切片新增
`DigDepthProfileInputSourceCallbacks` 和
`input_facts_from_source_callbacks()`，把 `_dig_depth_profile_input_facts()` 中
pending corridor lookup、active corridor lookup、active raw/cell、live raw 和 env-state
的分阶段采样顺序收回 service。service 只通过显式 callbacks 请求 caller-owned facts；
不接收 planner `self`，不读取 coverage service state，不写 planner state，也不写 debug
schema。

planner `_dig_depth_profile_input_facts()` 作为旧 private facade 保留在 shell 内，只负责
传入当前 cycle/pending ids、pending raw fields、current dig-cut token、
`include_env_state` flag，以及读取 pending corridor cell、active corridor、active raw
fields、live raw fields 和 env-state 的 callbacks。coverage state、live pose 读取和
env-state 读取仍由 planner/coverage 既有 facade 提供；service 只拥有采样 gate、调用顺序
和 `DigDepthProfileInputSourceFacts -> DigDepthProfileInputFacts` 投影。

本切片不改变 pending raw / active raw / live raw / env-state 对象引用语义、
`include_env_state=True` 的强制 env 采样、stale pending 忽略规则、cell id fallback、
coverage state exemplar side effects、token dim/order、source/fallback string、policy
observation injection、debug/summary schema、branch order、switch reason、policy reset
timing 或 rollout 输出。

## Dig Depth-Profile Token Result Projection Slice

`DigDepthProfileService` 新增 `DigDepthProfileTokenResult` 和 `token_result()`，
负责把 `DigDepthProfileState` 纯投影成 planner shell 需要写回和返回的
token/source/fallback reason result。该 projection 保留旧
`np.asarray(..., dtype=np.float32)` token 语义：float32 token 不额外 copy，非
float32 token 只按旧路径 cast。

planner `_apply_dig_depth_profile_token_result()` 作为旧 private facade 保留在 shell
内，只负责调用 service projection、写回 `_dig_depth_profile_token_source` 与
`_dig_depth_profile_fallback_reason`，并返回投影后的 dig-depth-profile token。
`_build_dig_depth_profile_tokens_for_obs()` 的 input-facts 采样、service build 调用、
`DigDepthProfileMissingPriorError` source/fallback 写回和 re-raise 行为仍由 planner
shell 拥有。

本切片不改变 dig-depth-profile token dim/order、source/fallback string、
prior/global/live fallback、missing-required-prior error behavior、pending
return-target profile token 复用、policy observation injection、debug/summary schema
或 rollout 输出。

## Dig Depth-Profile Runtime Status Projection Slice

`DigDepthProfileService` 继续作为 dig depth-profile token source selection 与 token
runtime state 的 capability 边界。本切片新增
`DigDepthProfileRuntimeStatusState` 和 `DigDepthProfileRuntimeStatusSnapshot`，
负责把 dig depth-profile config 与 planner shell 已维护的 runtime state 投影成
debug-state 需要的 facts：profile source、required flag、token injected flag、token
source、fallback reason 和 profile tokens。

后续同一切片新增 `DIG_DEPTH_PROFILE_CONFIG_FIELDS`、
`DIG_DEPTH_PROFILE_RUNTIME_STATUS_STATE_FIELDS`、
`build_dig_depth_profile_config_from_mapping()` 和
`build_dig_depth_profile_runtime_status_state_from_mapping()`，把 planner 当前
dig-depth-profile config/status fields 到 `DigDepthProfileConfig` 与
`DigDepthProfileRuntimeStatusState` 的投影收回 dig-depth-profile capability。
planner 旧 private facade 只按字段表采样当前 state 后调用 builder；`bool` / `str`
coercion 和 status-state contract 由 `dig_depth_profile` 统一负责。profile token array
仍由 `runtime_status_snapshot()` 做旧 `float32` copy，mapping builder 不复制 token
contract 或 token dim source-of-truth。

后续同一切片继续新增
`DigDepthProfileService.runtime_status_snapshot_from_mappings()`，把 config/state
mapping builders 到 snapshot projection 的组合收回 `DigDepthProfileService`。
planner 旧 private facade 仍只负责按字段表采样当前 planner config/runtime state，
并把 config/state mapping 交给 service；typed dataclass 构造、`bool` / `str`
coercion 和 snapshot float32 token copy 继续由 dig-depth-profile capability 统一负责。

planner 大文件只保留薄 facade：

- `_dig_depth_profile_runtime_status_snapshot()`

planner shell 仍负责 `_build_dig_depth_profile_tokens_for_obs()` 的 build order、
prior/global/live fallback、missing-required-prior error handling、pending
return-target profile token 复用、policy observation injection flag 写回，以及 public
debug schema 展开。service 不接收 planner `self`，不调用 `_set_skill()`，不 reset
policy，不写 debug schema，不读取 observation，不选择 prior fallback，也不生成新
token。

本切片不改变 debug-state key/key order、token dim/order、profile source string、
required flag、token injected bool coercion、fallback reason、prior/profile fallback
语义、pending return-target behavior、policy observation injection、switch reason、
policy reset timing 或 rollout 输出。

## Dig Depth-Profile Runtime Reset Slice

`DigDepthProfileService` 新增 `DigDepthProfileRuntimeState` 和
`initial_runtime_state()`，负责投影 dig depth-profile runtime 的 legacy reset
默认值：profile token zeros、token injected flag、token source 和 fallback reason。
service 只返回显式 runtime state；不接收 planner `self`，不调用 `_set_skill()`，
不 reset policy，不写 HDF5/checkpoint，不写 debug schema，不读取 observation，
不选择 prior fallback，也不生成新的 profile token。

planner `_reset_dig_depth_profile_runtime()` 和
`_apply_dig_depth_profile_runtime_state()` 作为旧 private facade 保留在 shell 内，
只负责调用 service 并把返回 state 应用到既有 `_dig_depth_profile_*` 字段。
`reset()` 的 policy reset、boundary detector reset、active skill 选择、switch
reason、cell-entry reset、dig-cut reset、return-target conditioning reset、
return-to-dig handoff state 和 coverage reset 顺序仍由 planner shell 拥有。

本切片不改变 reset timing、初始 active skill、switch reason `reset`、
dig-depth-profile token dim/order、source/fallback string、debug/summary schema、
policy observation injection、policy reset timing 或 rollout 输出。

## Dig Conditioning Clear-Plan Projection Slice

`DigCutPlanService` 继续作为 active dig-cut conditioning plan lifecycle 的 capability
边界。本切片新增 `DigCutPlanClearState` 和 `cleared_plan_state()`，负责投影
`_clear_dig_cut_plan()` 的 legacy clear 默认值：planned cycle id、dig-cut token、
dig-depth-profile token、dig-cut source/fallback/prior-range flag。service 只返回
显式 state；不接收 planner `self`，不调用 `_set_skill()`，不 reset policy，不写
HDF5/checkpoint，不读取 observation，不选择 planner mode，不生成新 plan，也不写
debug schema。

Coverage active state-exemplar runtime state 不属于 dig-cut plan lifecycle。它由
coverage capability 拥有：`CoverageActiveStateExemplarState` 和
`CoverageService.cleared_active_state_exemplar_state()` 投影 legacy clear 默认值
ids=empty、distance=NaN、profile token=None。`DigCoverageMixin` 保留
`_clear_coverage_active_state_exemplar()` 和
`_apply_coverage_active_state_exemplar_state()` 作为旧 private facade，只负责把
coverage service 返回的 state 复制到既有 coverage fields。

planner `_clear_dig_cut_plan()` 作为旧 private facade 保留在 shell 内，只负责调用
`DigCutPlanService.cleared_plan_state()` 和 coverage exemplar clear facade，并通过
对应 `_apply_*` 方法把返回 state 复制到既有字段。`_set_skill()`、failed-dig
restart、pre-dig-align replan、pending return-target invalidation、其它 coverage
side effects、policy dispatch、debug/summary schema 展开和 reset timing 仍由原
边界负责。

本切片不改变 clear-plan 调用时机、dig-cut token dim/order、dig-depth-profile token
dim/order、dig-cut source/fallback/prior-range 默认值、active state-exemplar 清理
默认值、switch reason、branch order、policy reset timing 或 rollout 输出。旧行为中
`_clear_dig_cut_plan()` 不重置 `*_token_injected`、dig-depth-profile source/fallback
字段；这些字段仍不在 clear-plan state 中，由原 policy-observation/reset 路径维护。

## Dig-Cut Plan Dispatch Facts Mapping Slice

`DigCutPlanService` 继续作为 dig-cut conditioning plan dispatch 的 source-of-truth。
本切片新增 `DIG_CUT_PLAN_DISPATCH_FACT_FIELDS` 和
`build_dig_cut_plan_dispatch_facts_from_mapping()`，把 planner shell 中重复构造
`DigCutPlanDispatchFacts` 的字段投影收回 dig-cut plan capability。planner
`_dig_cut_plan_dispatch_facts()` 作为薄 facade 保留，只从自身当前字段采样
planner mode、pending dig-cut token presence、pending cycle id 和 cycle index，再调用
builder。

`_build_dig_cut_tokens_for_obs()` 继续使用 pending dig-cut token 是否为 `None` 的旧
presence 语义；`_build_next_dig_cut_plan_for_return()` 继续显式传入
`pending_tokens_present=False`，因此 return-target 下一次 dig-cut 构造不会因为当前
pending token 命中而走 pending-return-target activation branch。`dispatch_decision()`
仍保留原 branch order、builder kind mapping 和 unsupported-mode error string。

本切片不新增 service、不改变 dig-cut planner mode 语义、pending activation 优先级、
return-target build path 的 pending override、coverage corridor selection、fallback
conservative-pose 行为、branch order、switch reason、debug/summary schema、policy
reset timing、token contract 或 rollout 输出。

## Return Target Plan State Slice

新增模块：

- `testbed/planner/return_target_plan.py`

`ReturnTargetPlanService` 负责 return target planner 的状态结果组装，而不负责
target/corridor selection。它只接收 planner 已经构造好的 `ReturnTargetPlanBuild`
和 `ReturnTargetExemplarSnapshot`，返回成功或失败后的
`ReturnTargetPlanState`：`return_target_tokens`、`return_start_envelope_tokens`、
return target source/fallback reason、planned cycle id、pending dig cut token/raw
fields/corridor id、pending dig depth-profile token，以及 pending state exemplar
metadata。service 还提供 hold-token 判断，避免该判断继续散落在 planner shell。

planner 大文件仍负责：

- `_build_next_dig_cut_plan_for_return()` 的 target/corridor selection
- `_build_return_start_envelope_tokens_for_obs()` 的 envelope facade
- coverage selection、raw fields、state exemplar selection
- pending state 的最终字段写回
- branch order、switch reason、policy dispatch、debug schema 和 rollout trace

本切片不改变 return target token、return relocate token、pending dig plan、
coverage corridor selection、return start-envelope token/source、fallback_zero 语义、
debug_state 字段、policy dispatch 或 switch 行为。

## Return Target Plan Cycle Gate Decision Slice

`ReturnTargetPlanService` 继续负责 return target planner 的纯 state / gate assembly。
本切片新增 `ReturnTargetPlanCycleConfig`、`ReturnTargetPlanCycleFacts` 和
`ReturnTargetPlanCycleDecision`，把 `_ensure_return_target_plan_for_cycle()` 开头的
enabled / hold-existing / build 判定迁入 service。service 只接收显式 config/facts，
返回 action 与 `should_build`，不选择 target/corridor，不调用 return start-envelope
builder，不捕获 planner exception，不写 pending state，不 reset policy，也不写
debug schema。

planner 大文件仍负责：

- 提供当前 enabled / hold / planned-cycle / cycle-index runtime scalar，并按
  `should_build` 早退
- `_build_next_dig_cut_plan_for_return()` 的 target/corridor selection
- `_build_return_start_envelope_tokens_for_obs()` 的 envelope 构造与 source 写回
- `Exception` catch 后构造 failure attempt
- `_apply_return_target_plan_state()` 的最终字段写回

同一 cycle request 边界后续新增
`ReturnTargetPlanService.plan_request_from_runtime()`，把 planner runtime scalar 到
`ReturnTargetPlanCycleConfig` / `ReturnTargetPlanCycleFacts` / state-exemplar snapshot
的投影收回 return-target service。planner `_ensure_return_target_plan_for_cycle()`
仍只传当前字段与 coverage exemplar snapshot；service 不读取 observation、不选择
target/corridor、不调用 return start-envelope builder、不捕获 planner exception、
不写 pending state，也不 reset policy 或 debug schema。

本切片不改变 return-target disabled 早退效果、hold-existing 行为、success 路径顺序、
failure `fallback_zero` token/source、pending invalidation、state exemplar metadata、
return start-envelope source 保留行为、coverage active corridor 写回、branch order、
switch reason、policy reset timing、debug/summary schema 或 rollout 行为。

## Return Target Plan Attempt Assembly Slice

`ReturnTargetPlanService` 继续负责 return target planner 的纯 state assembly。本切片
新增显式 `ReturnTargetPlanAttempt`，把 planner shell 已完成的 success attempt
或已捕获的 failure attempt 转换成既有 `ReturnTargetPlanState`。service 不执行 hold
判断、不选择 target/corridor、不调用 return start-envelope builder、不捕获 planner
异常、不写 pending state。

后续 slice 在同一 service 中新增 `ReturnTargetPlanRequest`、`plan_request()` 和
`ReturnTargetPlanBuildFacts`，负责把 return-target cycle gate decision、
state-exemplar snapshot、planner 已构造好的 dig-cut/envelope build facts，以及
success/failure attempt construction 组合到一个 request 边界。request 只暴露
`should_build`、`success_attempt(plan)`、`success_attempt_from_facts(facts)`、
`failure_attempt(reason)` 与 exemplar；不选择 target/corridor，不调用 return
start-envelope builder，不捕获 planner exception，不写 pending state，也不 reset
policy。

planner 大文件仍负责：

- cycle gate decision 的 runtime scalar 提供与 early return
- `_build_next_dig_cut_plan_for_return()` 的 target/corridor selection
- `_build_return_start_envelope_tokens_for_obs()` 的 envelope 构造与 source 写回
- planner 已完成 return start-envelope build 后，只传显式 build facts 给 request
- `Exception` catch 后构造 failure attempt
- `_apply_return_target_plan_state()` 的最终字段写回

本切片不改变 success 路径顺序、`planned_cycle_id = cycle_index`、
`pending_dig_cut_cycle_id = cycle_index + 1`、pending token/raw-field copy 语义、
failure `fallback_zero` token/source、pending invalidation、state exemplar metadata、
return start-envelope source 保留行为、coverage active corridor 写回、branch order、
switch reason、policy reset timing、debug/summary schema 或 rollout 行为。

## Return Target Build-Attempt Finalization Slice

`ReturnTargetPlanService` 继续作为 return target planner state / attempt assembly 的
source of truth。本切片新增 `ReturnTargetPlanBuildAttemptFacts` 和
`state_from_build_attempt()`，把 `_ensure_return_target_plan_for_cycle()` 中 success /
failure attempt finalization 收回 service：planner shell 传入已经构造好的
`ReturnTargetPlanBuildFacts` 或已捕获的 failure reason，service 负责调用
`ReturnTargetPlanRequest.success_attempt_from_facts()` 或 `failure_attempt()`，再复用
`state_from_attempt()` 生成 `ReturnTargetPlanState`。

planner shell 仍负责 return-target cycle gate config/facts 装配、`should_build` 早退、
`_build_next_dig_cut_plan_for_return()` 的 target/corridor selection、
`_build_return_start_envelope_tokens_for_obs()` 的 envelope 构造与 source 写回、
`try/except` 的旧捕获范围、`_apply_return_target_plan_state()` 的最终字段写回、
pending dig-cut field copy、coverage side effects、branch order、switch reason、
policy reset timing、debug/summary schema 和 rollout trace。service 不接收 planner
`self`，不读取 observation，不调用 `_set_skill()`，不 reset policy，不写 HDF5 /
checkpoint，也不写 debug schema。

本切片不改变 success 路径中 build-next-plan 先于 return-start-envelope 的调用顺序、
failure `fallback_zero` token/source、failure reason string、pending invalidation、
state exemplar metadata、return start-envelope source 保留行为、coverage active
corridor 写回、branch order、switch reason、policy reset timing、debug/summary
schema 或 rollout 输出。

## Return Target Build-Attempt Callback Resolution Slice

`ReturnTargetPlanService` 新增 `state_from_build_facts_callback()`，把
`_ensure_return_target_plan_for_cycle()` 中旧 `try/except` 的 success/failure build
attempt resolution 收回 return-target state assembly 边界。planner shell 传入当前
cycle 的 `ReturnTargetPlanRequest` 和一个 caller-provided build-facts callback；
service 只调用该 callback 取得 `ReturnTargetPlanBuildFacts`，或在 callback 抛出
`Exception` 时构造 failure attempt，然后复用 `state_from_build_attempt()` 生成
`ReturnTargetPlanState`。

同一边界后续新增 `ReturnTargetPlanService.plan_build_facts_from_parts()`，把
`_ensure_return_target_plan_for_cycle()` callback 内 token、raw fields、return
start-envelope token、source、fallback reason 和 corridor id 到
`ReturnTargetPlanBuildFacts` 的投影收回 return-target state assembly capability。该
projection 只保留旧 object identity 和 `str()` / `int()` 标量投影语义；不复制 token、
raw fields 或 envelope token，不选择 target/corridor，也不读取 observation。

同一 return-target dig-cut build result 边界继续新增
`dig_cut_build_result_from_plan()`，把 planner 已经构造好的 `DigCutPlan`
投影成 `ReturnTargetDigCutBuildResult`：保留 plan token/raw-fields object identity，
复用 plan source/fallback reason，并只附加 return-target source prefix 与 corridor id。

本轮同一边界新增 `ReturnTargetDigCutBuildCallbacks` 和
`dig_cut_build_result_from_callbacks()`，把
`_build_next_dig_cut_plan_for_return()` 中给定 dispatch context 后的 builder-kind
callback selection 收回 return-target service。service 只按
`context.builder_kind` 选择一个 caller-provided callback，并复用既有
`dig_cut_build_result_from_plan()` / `dig_cut_build_result_from_parts()` 做 legacy result
projection；它不读取 observation，不选择 coverage corridor，不写 coverage 或 pending
state，不调用 `_set_skill()`，不 reset policy，也不写 debug schema。

planner shell 仍负责构造 dispatch decision/context 和三个显式 callback：
conservative callback 采样当前 bucket pose，operator-prior callback 调用旧
operator-prior builder，coverage callback 执行 coverage corridor selection、
`_coverage_active_corridor_id` 写回、`_coverage_raw_fields(..., update_state=True)`
side effect，并用原始 planner mode 构造 raw-fields dig-cut plan。unsupported-mode
error 仍由 `DigCutPlanService.dispatch_decision()` 产生。

planner shell 仍负责 callback 内的完整 build 顺序和 side effects：
`_build_next_dig_cut_plan_for_return(obs)` 先执行，随后
`_build_return_start_envelope_tokens_for_obs(...)` 执行；coverage corridor selection /
raw-field update、return start-envelope source 写回、pending dig-cut field copy、
`_apply_return_target_plan_state()` 最终写回、switch reason、policy reset timing 和
debug/summary schema 仍由原边界负责。service 不接收 planner `self`，不读取
observation，不调用 `_set_skill()`，不 reset policy，不写 HDF5/checkpoint，也不写
debug schema。

本切片不改变旧异常捕获范围、success build order、failure `fallback_zero`
token/source、failure reason string、pending invalidation、state exemplar metadata、
coverage active corridor 写回、return start-envelope source 保留行为、builder-kind
selection 行为、switch reason、policy reset timing、debug/summary schema 或 rollout
输出。

## Pending Return Target Activation Slice

`ReturnTargetPlanService` 继续作为 return target planner state/activation assembly
边界。本切片新增显式 `PendingReturnTargetActivationFacts`、
`build_pending_return_target_activation_facts()` 和
`PendingReturnTargetActivation`。`build_pending_return_target_activation_facts()`
是 pending activation facts 的组装边界：保留 planner facade 传入的
token/raw-fields/profile/exemplar 引用语义，只投影 corridor id、prior-range
标记、state-exemplar distance 和 cycle-start deposit 这些标量值。同一边界内的
`PENDING_RETURN_TARGET_ACTIVATION_FACT_FIELDS` 和
`build_pending_return_target_activation_facts_from_mapping()` 只把 planner 当前
pending dig-cut runtime 字段投影为 facts；`raw_fields_in_prior_range` 与
`cycle_start_deposit_kg` 仍由 planner shell 显式提供。service 在 planner 已判定当前
cycle 命中 pending return target plan 后，纯组装 dig-cut token copy、source/fallback、
prior-range 标记、coverage corridor 建议、payload counter reset、
cycle-start deposit snapshot 以及 state exemplar snapshot。service 不选择
target/corridor，不读取 obs，不调用 coverage service，不写 planner state，不 reset
policy，不写 debug schema。

planner 大文件仍负责：

- pending return target 的 branch order 和命中条件
- `_pending_return_target_activation_facts()` 中
  `_raw_fields_in_prior_range()` 与 `_deposited_mass(obs)` 的 planner fact 采集，
  然后调用 `build_pending_return_target_activation_facts_from_mapping()`
- `_apply_pending_return_target_activation()` 中 dig-cut / coverage / exemplar
  activation state 的实际写回
- coverage active/last-selected corridor、payload counter、cycle-start deposit 的实际写回
- state exemplar fields 的实际写回
- conservative/operator-prior/fallback dig-cut branches
- debug/summary schema、switch reason、policy dispatch 和 rollout trace

本切片不改变 `dig_cut_token_source = "pending_return_target"`、fallback reason 清空、
raw-fields 缺失时 prior-range 标记为 false、pending token/profile token 的
float32 copy 语义、coverage corridor id 写回、payload gain reset、cycle-start deposit
取值、state exemplar metadata 恢复、后续 dig-cut planner 分支顺序、policy reset
timing、debug/summary schema 或 rollout 行为。

当前行为锁包括 service unit tests 和 planner facade spy/parity test：命中当前 cycle
pending return target 时，planner 只负责采集 `_raw_fields_in_prior_range()` 与
`_deposited_mass(obs)` facts、调用 `ReturnTargetPlanService.pending_activation()`，
再通过 `_apply_pending_return_target_activation()` 写回 dig-cut / coverage / exemplar
side effects；stale pending plan 不应调用 activation service。

review 结论：不要继续把 pending return-target activation、pending dig-cut plan
invalidation、pending state projection 和 runtime update projection 拆成更多独立小
slice。后续只有在能合并边界或移除 planner 中实质领域判断时才继续，否则保留 shell
side effects 和当前 facade。

后续下沉 return-target / dig-cut conditioning lifecycle 前，新增
`tests/test_primitive_scheduler_conditioning_facades.py` 作为 focused facade 行为锁：
return-target planner disabled 时必须早退且不调用 build path；return-start
envelope 构造失败必须进入既有 `fallback_zero` return-target state 并 invalidate
pending dig plan；pending return target 缺失 raw fields 时不能调用
`_raw_fields_in_prior_range()`，并必须保留 `pending_return_target` source、prior-range
false、coverage corridor 写回、payload counter reset 与 cycle-start deposit snapshot；
`_build_next_dig_cut_plan_for_return()` 的 operator-prior source prefix、coverage
`update_state=True` side effect、corridor id 返回值必须保持不变；dig-cut plan for
cycle 必须先写 dig-cut token，再构造 depth-profile token，最后更新 planned cycle id；
`_apply_return_target_plan_state()` 必须保持 token dtype、pending dict/list/array copy
隔离和 return-start envelope source 写回行为。这些测试只锁旧行为，不提升新的
conditioning 语义，也不改变 service/planner 责任边界。

## Pending Dig-Cut Plan Invalidation Slice

`ReturnTargetPlanService` 继续作为 return target planner state / pending dig-cut
conditioning lifecycle 的 source-of-truth。本切片新增 `PendingDigCutPlanState`
和 `invalidated_pending_dig_cut_plan()`，负责投影 legacy pending dig-cut plan
invalidation 默认值：pending cycle/corridor id、raw fields、pending dig-cut token、
pending depth-profile token、pending state-exemplar ids 和 distance。service 只返回
显式 state；不接收 planner `self`，不调用 `_set_skill()`，不 reset policy，不写
HDF5/checkpoint，不写 debug schema，不选择 target/corridor，也不构造新 token。

planner `_invalidate_pending_dig_cut_plan()` 作为旧 private facade 保留在 shell 内，
只负责调用 service 并通过 `_apply_pending_dig_cut_plan_state()` 把返回 state 复制到
既有 `_pending_dig_*` 字段。`_apply_return_target_plan_state()`、return-target
cycle gate、fallback-zero path、pending activation、coverage side effects、branch
order、switch reason、policy reset timing 和 public debug/summary schema 仍由原边界
负责。

本切片不改变 pending invalidation 默认值、dict/array copy 隔离、return-target
token/source/fallback 状态、pending activation source `pending_return_target`、
prior-range flag、debug/summary schema、branch order、switch reason、policy reset
timing 或 rollout 输出。

## Pending Dig-Cut Plan State Projection Slice

`ReturnTargetPlanService` 继续作为 return target planner state / pending dig-cut
conditioning lifecycle 的 source-of-truth。本切片新增
`pending_plan_state_from_return_target_state()` 和
`pending_plan_state_from_conditioning_state()`，负责把 `ReturnTargetPlanState` 与
`ReturnTargetConditioningRuntimeState` 中已存在的 pending dig-cut 字段纯投影成
`PendingDigCutPlanState`。这两个方法只做旧语义中的 `int()` / `float()` / `tuple()`
投影，并保持 raw-fields / token / depth-profile payload 引用交给 planner 旧 facade
统一 copy。

planner `_apply_return_target_plan_state()` 与
`_apply_return_target_conditioning_runtime_state()` 只保留 return-target /
return-relocate / return start-envelope 字段写回，然后把 service 返回的
`PendingDigCutPlanState` 交给 `_apply_pending_dig_cut_plan_state()` 执行既有 side
effects。service 不接收 planner `self`，不调用 `_set_skill()`，不 reset policy，不
读取 observation，不选择 target/corridor，不构造 token，不写 HDF5/checkpoint，也不写
debug schema。

本切片不改变 pending dig-cut dict/array copy 隔离、pending invalidation 默认值、
return-target success/failure 状态、conditioning runtime reset timing、pending
activation source `pending_return_target`、prior-range flag、debug/summary schema、
branch order、switch reason、policy reset timing 或 rollout 输出。

## Return Target Plan Runtime Update Projection Slice

`ReturnTargetPlanService` 继续作为 return target planner state / pending dig-cut
conditioning lifecycle 的 source-of-truth。本切片新增 `ReturnTargetPlanRuntimeUpdate`
和 `runtime_update_from_plan_state()`，把 `ReturnTargetPlanState` 中已经完成的
return-target plan state 纯投影成 planner shell 需要应用的 runtime update：
return-target token、return start-envelope token、return-target source/fallback、
可选 return start-envelope source、planned cycle id，以及同一 service 生成的
`PendingDigCutPlanState`。

planner `_apply_return_target_plan_state()` 仍作为旧 private facade 保留，只负责把
service 返回的 runtime update 写回既有 planner fields，并继续通过
`_apply_pending_dig_cut_plan_state()` 执行 pending dig-cut fields 的旧 copy/side-effect
语义。service 不接收 planner `self`，不读取 observation，不选择 target/corridor，
不构造 token，不调用 `_set_skill()`，不 reset policy，不写 HDF5/checkpoint，也不写
debug schema。

本切片不改变 return-target token 与 return start-envelope token 的 `float32`
projection 语义、不改变 `return_start_envelope_token_source is None` 时保留旧 source
的兼容行为、不改变 pending dig-cut dict/list/array copy 隔离、success/failure
fallback-zero 状态、pending activation source、branch order、switch reason、policy
reset timing、debug/summary schema 或 rollout 输出。

## Return Target Conditioning Runtime Status Projection Slice

`ReturnTargetPlanService` 继续作为 return target planner state/conditioning payload
的 capability 边界。本切片新增 `ReturnTargetConditioningStatusState` 和
`ReturnTargetConditioningStatusSnapshot`，负责把 planner shell 已维护的 return
conditioning runtime state 投影成 debug-state 与 rollout-summary 共同需要的 facts：
return-target token injected/source/tokens/fallback reason、return-relocate token
injected/tokens、return start-envelope token injected/source/tokens。

后续同一切片新增 `RETURN_TARGET_CONDITIONING_STATUS_FIELDS` 和
`build_return_target_conditioning_status_state_from_mapping()`，把 planner 当前 return
conditioning runtime fields 到 `ReturnTargetConditioningStatusState` 的投影收回
return-target capability。planner 旧 private facade 只按字段表采样当前 state 后调用
builder；`bool` / `str` coercion 和 status-state contract 由
`return_target_plan` 统一负责。target / relocate / start-envelope token arrays 仍由
`conditioning_status_snapshot()` 做旧 `float32` copy，mapping builder 不复制 token
contract 或 token dim source-of-truth。

后续同一切片继续新增
`ReturnTargetPlanService.conditioning_status_snapshot_from_mapping()`，把 status-state
mapping builder 到 snapshot projection 的组合收回 `ReturnTargetPlanService`。
planner 旧 private facade 仍只负责按字段表采样当前 planner return conditioning
runtime state，并把 mapping 交给 service；typed dataclass 构造、`bool` / `str`
coercion 和三组 token array 的 snapshot float32 copy 继续由 return-target
capability 统一负责。

planner 大文件只保留薄 facade：

- `_return_target_conditioning_status_snapshot()`

planner shell 仍负责 `_ensure_return_target_plan_for_cycle()` 的 cycle-gate
config/facts 装配、early return 与 fallback attempt 构造，
`_return_target_tokens_for_obs()`、`_return_relocate_tokens_for_obs()`、
`_return_start_envelope_tokens_for_obs()` 的 policy-observation token 生成和 injection
flag 写回、return start-envelope builder 调用、pending activation、return branch
order、switch reason 和 public debug/summary schema 展开。service 不接收 planner
`self`，不调用 `_set_skill()`，不 reset policy，不写 debug schema，不构造 return
start-envelope token，也不选择新 return target。

本切片不改变 debug-state 或 rollout-summary key/key order、token dim/order、
return-target source/fallback string、return-relocate source 仍由 debug builder 复用
return-target source 的兼容行为、token injected bool/int coercion、pending return
target behavior、return start-envelope source、policy observation injection、switch
reason、policy reset timing 或 rollout 输出。

## Return Conditioning Policy-Observation Token Projection Slice

`ReturnTargetPlanService` 新增 `ReturnTargetObservationTokenResult`、
`ReturnRelocateObservationTokenResult`、
`ReturnStartEnvelopeObservationTokenResult`，以及对应的
`return_target_token_result()`、`return_relocate_token_result()`、
`return_start_envelope_token_result()`。这些 result 明确表示 policy-observation
token projection，不复用 `return_start_envelope` builder 的
`ReturnStartEnvelopeTokenResult` 语义。这些方法只把 planner shell 已维护的 return
conditioning tokens 投影成 policy-observation helper 需要返回的 payload：
return-target 与 return start-envelope token 保留旧 `.copy()` 语义，不额外 cast；
return-relocate token 只调用
`testbed.contracts.primitive_tokens.derive_return_relocate_token()`，不复制 token index、
token order 或 relocation 规则。

planner `_return_target_tokens_for_obs()`、`_return_relocate_tokens_for_obs()` 和
`_return_start_envelope_tokens_for_obs()` 作为旧 private facade 保留在 shell 内，只
负责 policy-observation token-request gate、按旧顺序调用
`_ensure_return_target_plan_for_cycle(obs)`，再调用 service projection。只有
return-relocate facade 继续通过 `_apply_return_relocate_token_result()` 写回
`_return_relocate_tokens`；target/start-envelope helper 仍只返回 copy。所有
`*_token_injected` flag 仍由 policy observation assembly 按旧路径写回。

本切片不改变 return-target/start-envelope copy dtype 语义、return-relocate token
dim/order、depth/payload mask 规则、return-target plan build timing、policy
observation injection、return-target source 复用为 return-relocate debug source 的兼容
行为、switch reason、policy reset timing、debug/summary schema 或 rollout 输出。

## Return Target Conditioning Runtime Reset Slice

`ReturnTargetPlanService` 新增 `ReturnTargetConditioningRuntimeState` 和
`initial_conditioning_state()`，负责投影 return-target conditioning 的 legacy reset
默认值：return-target tokens/source/fallback/injection、return-relocate tokens/injection、
return start-envelope tokens/source/injection/prior-bound flags、planned cycle id，
以及 pending dig-cut raw fields/tokens/corridor id/depth-profile token/state exemplar
metadata。service 只返回显式 runtime state；不接收 planner `self`，不调用
`_set_skill()`，不 reset policy，不写 HDF5/checkpoint，不写 public debug schema，也不
选择 target/corridor 或构造 token。

planner `_reset_return_target_conditioning_runtime()` 和
`_apply_return_target_conditioning_runtime_state()` 作为旧 private facade 保留在 shell
内，只负责调用 service 并把返回 state 应用到既有 `_return_*` 与 `_pending_dig_*`
字段；其中 pending dig-cut 字段通过同一个 `_apply_pending_dig_cut_plan_state()`
facade 写回，避免 reset path、return-target state apply path 和 explicit invalidation
path 维护多套 copy 语义。`reset()` 的 policy reset、boundary detector reset、active
skill 选择、switch reason、return-to-dig handoff state、cell-entry reset、dig-cut
reset 和 coverage reset 顺序仍由 planner shell 拥有。

本切片不改变 reset timing、初始 active skill、switch reason `reset`、
return-target/relocate/start-envelope token dim/order、source/fallback string、
pending invalidation 默认值、prior-bound flags 默认值、debug/summary schema、
policy observation injection、switch reason、policy reset timing 或 rollout 输出。

## Cell Entry Config Assembly Slice

`cell_entry` 新增 `CellEntryPlannerConfig` 和
`build_cell_entry_planner_config()`，负责把 planner 初始化期间的 cell-entry online
配置解析成 planner shell 需要应用的显式字段：`cell_entry_enabled`、validated
`CellGridSpec`，以及 `cell_entry_low_productivity_payload_gain_kg`。`CELL_ENTRY_CONFIG_KEYS`
只作为 planner `__init__` filtered init-argument mapping facade 的字段边界，避免
planner 大文件复制 cell-entry 配置解析。

本切片把 cell-entry 初始化配置放在 `cell_entry` capability，而不是放入
`primitive_config`。原因是 `cell_entry` 已经是 grid、online planner、auditor、
runtime service 和 token builder 的 source-of-truth；初始化配置投影属于该领域输入
边界，同时避免继续扩张接近大文件阈值的 central config helper。

planner 大文件只保留薄应用入口：

- `_apply_cell_entry_config()`

planner shell 仍负责按旧顺序创建 `CellEntryPlanner`、
`PlannerDecisionAuditor` 和 `CellEntryRuntimeService`，以及 reset 时机、online
token/audit/trace facade、policy observation injection、branch order、switch reason、
policy reset timing 和 debug/summary schema。`cell_entry` config helper 不接收 planner
`self`，不调用 `_set_skill()`，不 reset policy，不写 HDF5/checkpoint，不写 debug
schema，也不选择 cell goal 或构造 online token。

本切片不改变 `CellGridSpec` 默认值和 validation error、low-productivity threshold
coercion、cell-entry planner/auditor semantics、`CELL_ENTRY_TOKEN_DIM`、token dtype/order、
trace key names、debug/summary schema、policy observation injection、switch reason、
policy reset timing 或 rollout 输出。

## Cell Entry Online Runtime Slice

`testbed.planner.cell_entry` 继续作为 cell-entry planning、audit 和 token
construction 的 source-of-truth；当前 `CellEntryRuntimeService` 的 implementation
source-of-truth 已迁到 `testbed.planner.cell_entry_runtime`，旧 `cell_entry` import
path 只作为 compatibility re-export。本切片新增 `CellEntryRuntimeService`，负责在线
planner path 中的纯 runtime 组装：按 cycle 选择/复用 `CellEntryGoal`、更新
first-seen cell latch、构造旧 `PrimitiveCycleOutcome`、运行
`PlannerDecisionAuditor`、生成 `cell_entry_tokens`，以及 dig completion 时构造旧
`cell_entry_trace` event。service 只接收显式 `CellEntryRuntimeFacts`、
`CellEntryRuntimeConfig`、`CellEntryRuntimeState` 和现有 `CellEntryPlanner` /
`PlannerDecisionAuditor` 域对象，不接收 planner `self`，不调用 `_set_skill()`，
不 reset policy，不写 HDF5，不加载 checkpoint，也不写 debug schema。

planner 大文件只保留旧 private facade 和状态写回：

- `_cell_entry_tokens_for_obs()`
- `_complete_cell_entry_dig()`

planner shell 仍负责是否在当前 skill 调用 cell-entry facade、何时完成 cell-entry
dig、`_cell_entry_goal` / `_cell_entry_audit` / `_cell_entry_tokens` /
`_cell_entry_seen_cell_id` / `_cell_entry_trace` 的最终写回、policy observation
injection flag、branch order、switch reason、policy reset timing、debug schema 和
rollout trace。`CellEntryRuntimeService` 不改变 `CELL_ENTRY_TOKEN_DIM`、
`cell_entry_tokens` low-dim key、grid/audit thresholds、trace key names、debug key
order、`actual_*_step=-1` 在线近似、`deposit_delta_kg=0.0`、
`collision_count_delta=0` 或只对 `dig` policy 注入 token 的行为。

同一 runtime 边界内的后续 consolidation 增加
`_apply_cell_entry_runtime_token_result()` 和
`_apply_cell_entry_runtime_completion_result()`，把
`CellEntryRuntimeTokenResult` / `CellEntryRuntimeCompletionResult` 的旧 side effect
应用收口在 planner shell 内。token-result apply 只写回 goal/audit/seen-cell/tokens，
不写 `token_injected`，也不复制 result state 中的 trace events；completion-result
apply 只按旧行为 append `trace_event`，不应用完整 runtime state。reset 语义继续由
`_apply_cell_entry_runtime_state()` 独立拥有，避免 token path 和 completion path 改变
legacy side effect 边界。

## Cell Entry Runtime Input Projection Slice

`cell_entry_runtime` 继续作为 cell-entry online runtime input projection 的
source-of-truth；`cell_entry` 只保留 compatibility re-export。本切片新增
`CELL_ENTRY_RUNTIME_FACT_FIELDS` / `build_cell_entry_runtime_facts_from_mapping()`
以及 `CELL_ENTRY_RUNTIME_STATE_FIELDS` /
`build_cell_entry_runtime_state_from_mapping()`，把 `_cell_entry_tokens_for_obs()`、
`_complete_cell_entry_dig()` 和 `_cell_entry_debug_snapshot()` 共享的 runtime facts /
state 输入投影收回 cell-entry capability。planner 旧 private facades 只负责在旧时机
采样 obs-derived facts、调用 service、写回 `_cell_entry_*` runtime 字段，以及 append
trace event。

同一 Input Projection 边界现在继续收口 source projection：
`cell_entry_runtime` 新增 `build_cell_entry_runtime_facts_from_observation_view()` 与
`CellEntryRuntimeService.facts_from_observation_view()`，从 `PlannerObservationView`
的原始 observation 复用 `snapshots` legacy helpers 构建 cycle、active skill、cell id、
bucket pose、geometry availability 和 bucket mass facts。planner
`_cell_entry_runtime_facts()` 只创建 snapshot 并传递 cycle/active skill；不再在 planner
大文件内手写 cell-entry runtime facts mapping。

该 projection 不选择 cell goal，不运行 auditor，不生成 token，不完成 dig，不写
debug schema，也不保留/reset `token_injected` 或 trace events 到 service-call input
state；这些仍由 reset/apply facade、policy observation assembly 和 planner shell 的
旧写回路径拥有。

本切片不改变 cell-entry token request 条件、planner/auditor semantics、
`CELL_ENTRY_TOKEN_DIM`、token dtype/order、trace key names、debug/summary schema、
policy observation injection、switch reason、policy reset timing 或 rollout 输出。

## Cell Entry Runtime Reset Slice

`CellEntryRuntimeService` 新增 `initial_runtime_state()`，继续复用
`CellEntryRuntimeState`，负责投影 cell-entry online runtime 的 legacy reset 默认值：
goal/audit empty state、goal cycle id、cell-entry token zeros、token injected flag、
first-seen cell id 和 trace events。service 只返回显式 runtime state；不接收 planner
`self`，不调用 `_set_skill()`，不 reset policy，不写 HDF5/checkpoint，不写 debug
schema，不选择 cell goal，不运行 auditor，也不构造新的 trace event。

planner `_reset_cell_entry_runtime()` 和 `_apply_cell_entry_runtime_state()` 作为旧
private facade 保留在 shell 内。`_reset_cell_entry_runtime()` 仍由 planner shell 在
旧 `cell_entry_planner.reset()` 的位置调用，并由 shell 执行
`cell_entry_planner.reset()`；随后只把 service 返回 state 应用到既有
`_cell_entry_*` 字段。`reset()` 的 policy reset、boundary detector reset、
active skill 选择、switch reason、pre-dig-align reset、dig-cut/depth-profile reset、
return-target conditioning reset、return-to-dig handoff state 和 coverage reset 顺序
仍由 planner shell 拥有。

本切片不改变 reset timing、初始 active skill、switch reason `reset`、
`CELL_ENTRY_TOKEN_DIM`、cell-entry token dtype/order、token injection flag 默认值、
seen-cell/trace 默认值、cell-entry planner/auditor semantics、debug/summary schema、
policy observation injection、policy reset timing 或 rollout 输出。

## Cell Entry Runtime Module Boundary Slice

`cell_entry_runtime` 作为 cell-entry online runtime facts/state projection、runtime
token/audit service、completion trace projection 和 debug snapshot projection 的稳定
source-of-truth。`cell_entry` 只保留这些 runtime symbols 的 compatibility re-export，
并继续拥有 grid spec、cell-entry planner、decision auditor、audit geometry helper、
token builder、env-state geometry availability helper 和 initialization config
projection。

本切片是责任边界修正，不新增调度语义：原
`CellEntryRuntimeConfig` / `CellEntryRuntimeFacts` / `CellEntryRuntimeState`、
`CELL_ENTRY_RUNTIME_FACT_FIELDS` / `CELL_ENTRY_RUNTIME_STATE_FIELDS`、
`build_cell_entry_runtime_facts_from_mapping()` /
`build_cell_entry_runtime_state_from_mapping()`、`CellEntryDebugSnapshot`、
`CellEntryRuntimeTokenResult` / `CellEntryRuntimeCompletionResult`、
`CellEntryRuntimeService` 和 runtime `PrimitiveCycleOutcome` projection 原样迁入
`cell_entry_runtime`。旧 `cell_entry` import path 继续可用以保护现有 planner、
tests 和外部调用方。

`cell_entry_runtime` 不接收 planner `self`，不调用 `_set_skill()`，不 reset policy，
不写 HDF5/checkpoint/debug schema，也不复制 token/schema/profile source-of-truth。
它只在 runtime method 中调用 `cell_entry` 的既有 domain objects 和
`build_cell_entry_tokens()`；`CELL_ENTRY_TOKEN_DIM` 和 token dtype/order 仍由
`cell_entry` token builder capability 保持为 source-of-truth。

planner shell 仍负责 cell-entry runtime reset 时机、是否在当前 skill 请求
cell-entry token、policy-observation injection flag 写回、`_cell_entry_*` runtime
字段写回、cell-entry trace append、dig branch order、switch reason、policy reset
timing、debug/summary schema 和 rollout trace。本切片不改变 cell-entry token request
条件、planner/auditor semantics、trace key names、debug key/order、token contract、
policy observation injection、switch reason、policy reset timing 或 rollout 输出。

## Policy Observation Assembly Slice

新增模块：

- `testbed/planner/policy_observation.py`

`PolicyObservationAssembler` 负责两类纯 policy-observation capability：根据显式
`PolicyObservationRequestFacts` / `PolicyObservationRequestConfig` 计算当前 active
skill 下哪些 optional token helper 应该被请求；以及把 planner 已经生成的 optional
low-dim token 合并进 ACT policy observation，并返回 debug 注入标志。request gate
只决定 helper 调用条件，不生成 token，不决定实际 token 是否存在；`*_token_injected`
仍由实际 token 是否非 `None` 决定。service 不接收 planner `self`，不调用 token
builder，不改变 active skill，不 dispatch policy，不 reset policy，不写 debug
schema，也不写 planner state。

planner 大文件只保留薄 facade：`_policy_obs()` 先构造 request facts 并调用
`_policy_observation_token_request()`，再按原顺序调用被 request 启用的
`_goal_tokens()`、`_cell_entry_tokens_for_obs()`、`_dig_cut_tokens_for_obs()`、
`_dig_depth_profile_tokens_for_obs()`、`_return_target_tokens_for_obs()`、
`_return_relocate_tokens_for_obs()` 和 `_return_start_envelope_tokens_for_obs()`；
随后调用 assembler，并把实际 token 注入得到的 `*_token_injected` 标志写回 planner
state 供 debug/trace builder 使用。各旧 private token helper 继续作为 facade 保留，
直接调用时会自行计算同一 request gate。

同一边界内的后续 consolidation 新增
`_apply_policy_observation_assembly()`，把 `PolicyObservationAssembly` 的返回 obs 与
六个 `*_token_injected` 标志写回收口为 planner shell 内的应用 facade。`_policy_obs()`
仍保持旧 token helper 调用顺序和 assembler 调用时机，只把 assembly result 交给该
facade；`PolicyObservationAssembler` 仍不写 planner state、不 dispatch policy，也不
拥有 reset/debug schema。

本切片不改变 token 生成语义、low-dim key、policy dispatch 目标、active skill、
branch order、switch reason、debug schema 或 rollout record 行为。无 token 时仍返回
原 observation 对象；只有 `goal_tokens` 时仍不设置 planner debug injected flag。

## Policy Observation Request Facts Mapping Slice

`testbed.planner.policy_observation` 继续作为 policy-observation request gate 和 token
merge 的 source-of-truth。本切片新增
`POLICY_OBSERVATION_REQUEST_FACT_FIELDS` 和
`build_policy_observation_request_facts_from_mapping()`，把
`_policy_observation_token_request()` 的 request facts 字段映射收回到 capability 内。
planner 旧 private facade 只从自身当前字段构造 focused mapping，并继续显式传入
`PolicyObservationRequestConfig` 以保留 bootstrap skill name。

service 只把显式 mapping 投影为 `PolicyObservationRequestFacts`，包括旧
`bootstrap_policy is not None` 的 bool 语义；不接收 planner `self`，不调用 token
helper，不生成 token，不 merge observation，不写 `*_token_injected` flag，不 dispatch
policy，不 reset policy，也不写 debug schema。planner shell 仍负责 `_policy_obs()`
中的 token helper 调用顺序、token 生成时机、实际 injection flag 写回、policy dispatch
和 debug/summary schema。

后续同一切片继续新增
`PolicyObservationAssembler.token_request_from_mapping()`，把 request facts mapping
builder 到 token request gate 的组合收回 `policy_observation` capability。planner
旧 private facade 仍只负责按字段表采样当前 planner request state，并显式传入
`PolicyObservationRequestConfig`；active-skill gate、bootstrap-policy presence 判断和
optional token helper request decision 继续由 capability 统一负责。

本切片不改变 token request gate 语义、bootstrap policy presence 判断、active skill
字符串、optional token helper 调用顺序、low-dim key、policy dispatch 目标、debug
schema、switch reason、policy reset timing 或 rollout record 行为。

## Dig Conditioning Policy-Observation Terminal Gate Slice

`PolicyObservationAssembler` 新增 `DigConditioningObservationTokenGateFacts` 和
`DigConditioningObservationTokenGateDecision`，负责在 request gate 之后纯判断
dig-cut / dig-depth-profile observation token helper 是否应该返回 token，以及是否
需要触发 dig-cut plan build。该 gate 只消费显式 active skill、terminal-stop flag
和 token-request bool；不调用 `_ensure_dig_cut_plan_for_cycle()`，不读取 observation，
不生成 token，不写 planner state，也不 dispatch policy。

`DigCutPlanService` 与 `DigDepthProfileService` 分别新增 observation-token projection
result，负责把 planner shell 已维护的 dig conditioning token 按旧 `.copy()` 语义投影
成 policy-observation helper 的返回值。该 projection 不复用 build-result
`token_result()` 的 `float32` cast 语义，避免混淆 build-time state projection 与
policy-observation copy projection。

同一 Dig Conditioning Policy-Observation Terminal Gate 边界后续新增
`DIG_CONDITIONING_TOKEN_GATE_FACT_FIELDS` 和
`build_dig_conditioning_token_gate_facts_from_mapping()`，把
`_dig_cut_tokens_for_obs()` / `_dig_depth_profile_tokens_for_obs()` 中共享的
active-skill 与 coverage terminal-stop facts 投影收回 `policy_observation`
capability。planner 旧 private facades 仍显式传入各自 token-request bool，并继续按
旧顺序决定是否调用 `_ensure_dig_cut_plan_for_cycle(obs)`；builder 不调用 token
helper，不读取 observation，不 build dig-cut plan，不生成 token，也不写
`*_token_injected` flag。

同一 gate 边界后续新增
`PolicyObservationAssembler.dig_conditioning_token_gate_from_mapping()`，把 planner
两个 token helper 中重复的 facts mapping + gate decision 组合收回
`policy_observation` capability。planner 旧 private facades 仍只负责选择各自
`token_requested` bool、按 decision 调用 `_ensure_dig_cut_plan_for_cycle(obs)`，以及
调用 dig-cut / dig-depth-profile service 的 observation-token projection。

后续 consolidation 不新增 service，只在 planner shell 内增加
`_dig_conditioning_token_gate()` 薄 facade，把
`DIG_CONDITIONING_TOKEN_GATE_FACT_FIELDS` 的字段采样、
`PolicyObservationRequestConfig(dig_skill_name="dig")` 和
`dig_conditioning_token_gate_from_mapping()` 转调集中到一个入口。
`_dig_cut_tokens_for_obs()` 与 `_dig_depth_profile_tokens_for_obs()` 仍分别选择自己的
`token_requested` bool、按旧时机调用 `_ensure_dig_cut_plan_for_cycle(obs)`，并调用各自
token projection service；该 facade 不读取 observation、不 build plan、不生成 token、
不写 injection flag，也不 dispatch policy。

planner `_dig_cut_tokens_for_obs()` 和 `_dig_depth_profile_tokens_for_obs()` 作为旧
private facade 保留在 shell 内，只负责获取同一 `PolicyObservationTokenRequest`、
调用 terminal/build gate、在 gate 要求时按旧时机调用
`_ensure_dig_cut_plan_for_cycle(obs)`，再调用对应 service projection。coverage
terminal-stop 下仍只在 active skill 为 `dig` 时返回当前 token copy；其它 active skill
即使 direct helper 传入 enabled request 也返回 `None` 且不 build。

本切片不改变 dig-cut/depth-profile request 条件、terminal-stop reuse 行为、
`_ensure_dig_cut_plan_for_cycle()` 的 build order、dig-cut token 先于 depth-profile
token 的生成顺序、planned cycle id 写回时机、copy dtype 语义、policy observation
injection flag 写回、debug/summary schema、policy reset timing 或 rollout 输出。

## Reflection Check 2026-06-06

本轮判断：继续当前 service-object 路线，但暂不在已服务化链条上新增代码 slice。
当前 planner 仍是大文件，但 `PrimitivePlannerACTPolicy` 剩余的核心大块主要是
state-machine branch order、service 调用顺序、runtime side-effect 写回、
`_set_skill()`、policy dispatch、reset timing 和 legacy facade。pre-dig-align、
policy observation、cell-entry、dig-cut / return-target pending activation、
dump/dig runtime status、coverage、debug/trace facts 等领域能力已经有对应
service/capability 作为 source-of-truth；继续在这些链条上拆单个 mapping 或单个
snapshot helper，会倾向制造 pass-through wrapper，而不是减少 planner 中的真实语义。

本轮过细风险检查结论：不要继续拆 pending return-target activation / invalidation /
runtime projection；不要为 `_dump_lifecycle_runtime_status_snapshot()` 这类单次
mapping + service call 增加组合 wrapper；不要把 `_dig_conditioning_token_gate()` 再拆
成更小 facade；不要把 pre-dig-align 已分离的 context/action/readiness/outcome/runtime
继续拆成只包一两个 helper 的长期模块。上述区域的 planner 代码若仍需调整，应优先
合并边界、删除重复 facade，或迁移仍留在 planner 内的真实领域判断。

本轮过粗风险检查结论：`PrimitivePlannerACTPolicy._maybe_switch_skill()` 仍然较长，但
当前内容主要是旧分支顺序、gate 调用顺序、projection 应用和 side-effect 顺序；这些
属于 thin shell 保留责任。`PrimitivePlannerACT5PPolicy` 仍有独立状态机逻辑，但 5P
在本文档中已定义为兼容路径和失败支线，不应在没有用户确认的情况下成为后续主线
service 拆分目标。

后续 slice selection 规则：只有当候选迁移能移除 planner 中仍存在的完整领域能力
时才新增 service/capability 代码；若候选只减少几行字段映射、只组合已有 builder 与
service call，或需要改变 5P / token / debug / rollout 语义，必须停止并重新审视边界。

## 测试锁定规则

Phase 1 必须覆盖：

- return handoff service unit tests：entry-close、non-finite fallback、start-envelope ready/fail/missing-token fallback、direct handoff、direct-handoff attempt guard/reason、shallow guard。
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
pytest tests/test_dig_depth_profile_service.py tests/test_agx_primitives_v2_2.py -k "dig_depth_profile or state_conditioned_exemplar"
pytest tests/test_return_target_plan_service.py tests/test_agx_primitives_v2_2.py -k "return_target or pending_return_target"
pytest tests/test_dig_cut_plan_service.py tests/test_agx_primitives_v2_2.py -k "dig_cut or operator_prior or pending_return_target"
pytest tests/test_primitive_planner_config.py tests/test_agx_primitives_v2_2.py -k "goal_sequence or failed_dig_replan or dig_depth_profile or return_envelope"
pytest tests/test_cell_entry_v2_2.py tests/test_agx_primitives_v2_2.py -k "cell_entry"
pytest tests/test_goal_sequence.py tests/test_primitive_planner_config.py tests/test_agx_primitives_v2_2.py -k "goal_tokens_for_sequence"
```

## 回滚策略

Phase 1、dump lifecycle gate slice、dig lifecycle gate slice、dig-start
alignment numeric/readiness slice、scripted bootstrap compatibility slice 和
debug/trace builder slice 的旧 private/public method 均保留为 facade。如果 service
extraction 发现行为漂移，可以让 facade 临时回到旧实现，同时保留新增 service unit
tests 和 golden trace 作为后续迁移的行为锁。
