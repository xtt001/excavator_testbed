# Primitive Scheduler Refactor Plan

Status: **historical / closed for the current backend-runtime migration**.

This document records the earlier primitive scheduler service-refactor context,
constraints, and lessons. Do not use the `Phase Plan` section below as the
active route for the 2026-06-17 planner backend/runtime migration. The active
backend/runtime phase authority is:

- `docs/superpowers/specs/2026-06-17-planner-backend-interface-design.md`

Agents may still read this file for historical guardrails such as large-file
policy, semantic-drift risks, and prior capability ownership, but backend phase
selection and Definition of Done must come from the backend interface design
spec unless a human explicitly reopens this plan.

本文档保留早期 primitive planner 重构背景；它不再作为当前 backend/runtime
migration 的活跃执行手册。

历史方向：**沉淀行为树可复用的决策语义层**，而不是单纯把
`PrimitivePlannerACTPolicy` 拆成更多文件。现有状态机仍是兼容入口；长期目标是让
状态机、行为树、decision tree 或 option scheduler 都复用同一批 capability。

## Current Map

当前 public facade：

- `testbed.policies.hybrid.primitive_planner.PrimitivePlannerACTPolicy`
- `testbed.policies.hybrid.primitive_planner_5p.PrimitivePlannerACT5PPolicy`
  只作为 5P compatibility / diagnostic path。旧
  `testbed.policies.hybrid.primitive_planner` import path 保留 lazy compatibility
  facade 和 policy registry 副作用。

当前大文件限制：

- `testbed/policies/hybrid/primitive_planner.py` 只能新增薄 adapter、import、
  effect application、facade deletion-after-migration、小 bug fix。
- `testbed/data/primitives_v2_2.py` 只能做 HDF5/data facade 或迁移后的删除，不新增
  planner 语义。

当前较成熟的 capability：

- `testbed.planner.snapshots`
- `testbed.planner.return_handoff`
- `testbed.planner.return_to_dig_transition`
- `testbed.planner.dig_lifecycle`
- `testbed.planner.dump_lifecycle`
- `testbed.planner.dig_start_alignment_*`
- `testbed.planner.dig_cut_plan`
- `testbed.planner.dig_depth_profile`
- `testbed.planner.return_target_plan`
- `testbed.planner.policy_observation`
- `testbed.planner.primitive_debug*`

当前最大阻塞：

- `DigCoverageMixin` 仍通过 `_coverage_*` 私有属性代理连接 shell 和
  `CoverageService`。
- return-target / dig-depth-profile build 仍依赖 shell callback。
- 测试仍大量绑定 `policy._xxx` 私有方法和私有状态。
- audit/QC/pipeline/eval 边缘路径仍可能复制 token path、primitive name、
  profile string 或 env-state magic index。

Recent checkpoint:

- 2026-06-17: 5P compatibility shell 已物理移到
  `testbed/policies/hybrid/primitive_planner_5p.py`。本迁移只改变代码组织，不改变
  5P branch order、switch reason、policy dispatch、policy reset timing、
  debug-state key/key order、hold-count 投影、token contract 或 rollout 输出。
- 2026-06-17: planner shell 删除了确认零调用的 private config helper
  pass-through：`_normalize_plane_depth_mode()`、
  `_normalize_failed_dig_replan_skill()` 和 `_load_dig_cut_prior()`。相关语义的
  source of truth 保留在 `testbed.planner.primitive_config` 及其领域 helper alias；
  原 private facade code 已归档到
  `deprecated/primitive_scheduler/primitive_planner_deprecated_facades.py.txt`。
- 2026-06-17: deprecated artifact policy 已建立。负结果实验和待移除 private
  facade 必须先记录到 `deprecated/primitive_scheduler/`，说明原设计动机、实验或迁移结果、
  替代 source-of-truth，以及为什么不应继续作为 live planner 语义。
- 2026-06-17: 在完整备份
  `deprecated/primitive_scheduler/primitive_planner_pre_facade_cleanup_2026_06_17.py.txt`
  后，live planner shell 删除了 295 行确认零调用 private facade，覆盖 dump readiness、
  pre-dig-align entry、dig lifecycle、dig-depth-profile prior/live、return-start-envelope
  prior/conditioning、snapshot projection 和 config parsing pass-through。保留
  `_pre_dig_align_entry_close_handoff_ready_for_state()`、policy dispatch、reset timing、
  `_set_skill()`、debug/trace/summary assembly，以及仍被 runtime 使用的 pose/env/mass
  observation helpers。
- 2026-06-17: private-test dependency audit 显示下一步高风险绑定集中在三类：
  coverage `_coverage_*` runtime state/proxy、pre-dig-align `_pre_dig_align_*`
  runtime fields、return-target/dig-cut/depth-profile pending state。coverage 第一刀已把
  dig-cut activation 的 corridor selection、payload/deposit cycle metric 初始化和
  raw_fields(update_state=True) 收进 `CoverageService.activate_dig_cut_corridor()`；
  planner shell 只保留 obs->facts adapter、coverage action effect application 和
  dig-cut token construction。coverage row 仍未完成：`DigCoverageMixin.__getattr__`
  和大量 `_coverage_*` compatibility properties 还需要后续测试迁移后再收窄。
- 2026-06-17: backend runtime contract Phase 2 的第一小刀已添加
  `testbed.planner.runtime.coverage.project_coverage_action_result()`，将
  `CoverageActionResult` 的 deferred terminal-stop request 投影为
  backend-neutral `PlannerRuntimeEffect`。这只是 effect projection contract；尚未把
  `DigCoverageMixin` 或 `PrimitivePlannerACTPolicy` 改为通过 runtime effect applier
  执行，也未改变 terminal-stop reason、debug/trace/rollout schema 或默认 planner 行为。
- 2026-06-17: backend runtime contract Phase 2 的第二小刀已让
  `DigCoverageMixin._apply_coverage_action_result()` 通过
  `project_coverage_action_result()` 和 `apply_coverage_runtime_effects()` 执行
  terminal-stop adapter callback。该切片只迁移 adapter 内部应用路径；没有改变
  `CoverageService` 决策、terminal-stop reason、trace/debug/rollout schema、
  `_maybe_switch_skill()` 或默认 planner 行为。
- 2026-06-17: backend runtime contract Phase 2 已补齐 completion gate：
  `tests/test_coverage_service_runtime_domain.py` 直接构造 `CoverageService`、
  `CoverageServiceConfig`、`CoverageServiceState` 和 `CoverageObservationFacts`，
  在不构造 `PrimitivePlannerACTPolicy` 的情况下覆盖 coverage selection 与
  dig-cut activation。Phase 2 只完成 coverage runtime effect contract 与
  service-level testability 证据；未迁移 `_maybe_switch_skill()`，也未改变默认 planner
  语义。
- 2026-06-17: backend runtime contract Phase 3 的第一小刀已添加
  `testbed.planner.runtime.legacy_fsm.LegacyStateMachineBackend` 和
  `run_legacy_fsm_transition` runtime effect。`PrimitivePlannerACTPolicy`
  的 `_maybe_switch_skill()` 现在只负责构造 `PlannerTickContext`、调用 legacy
  backend、应用返回 effect；原有 branch/order/reset/reason 逻辑保存在
  `_run_legacy_fsm_transition()` 作为兼容实现。该切片只建立 backend entry/effect
  path，尚未逐个迁移 active-skill branch。验证覆盖新增 backend tests、golden trace、
  primitive action tree、primitive scheduler facades 和 AGX primitive legacy tests。
- 2026-06-17: backend runtime contract Phase 3 的第二小刀已把默认 FSM 的
  `bootstrap` active-skill end-transition orchestration 接到
  `LegacyStateMachineBackend.tick()`。backend 通过当时的 untyped tick-context
  registry 调用现有 bootstrap service/callback，并返回
  `apply_bootstrap_transition_decision` effect；`PrimitivePlannerACTPolicy` 仍通过
  现有 `_apply_bootstrap_transition_decision()` 和 `_set_skill()` 应用实际副作用。
  该切片没有迁移 `pre_dig_align`、`dig`、`carry`、`dump` 或 `return` 分支，没有改变
  bootstrap end condition、reason string、pre-dig-align selection、reset timing、
  debug/trace/rollout schema 或默认行为。
- 2026-06-17: backend runtime contract Phase 3 的第三小刀已把默认 FSM 的
  `pre_dig_align` active-skill outcome orchestration 接到
  `LegacyStateMachineBackend.tick()`。backend 通过当时的 untyped tick-context
  registry 调用现有 facade 计算
  `PreDigAlignOutcome`，并返回 `apply_pre_dig_align_outcome` effect；
  `PrimitivePlannerACTPolicy` 仍通过现有 `_apply_pre_dig_align_outcome()` 应用
  projection 和实际副作用。该切片没有迁移 `dig`、`carry`、`dump` 或 `return`
  分支，没有改变 pre-dig-align readiness、surface guard、timeout、replan、restart、
  switch reason、branch order、reset timing、debug/trace/rollout schema 或默认行为。
- 2026-06-17: backend runtime contract Phase 3 的第四小刀已把默认 FSM 的
  `dig` active-skill gate orchestration 接到 `LegacyStateMachineBackend.tick()`。
  backend 通过当时的 untyped tick-context registry 调用现有 adapter gate callbacks，并返回
  `apply_dig_transition_runtime_projection` effect；`PrimitivePlannerACTPolicy`
  仍通过现有 `_apply_dig_transition_runtime_projection()` 应用 counter、coverage
  reject、failed-dig restart、cell-entry/coverage completion 和 `_set_skill("carry", ...)`
  等实际副作用。该切片特意保留 `_dig_to_carry_ready()` 的 adapter callback 路径，
  以保持 `_dig_to_carry_reason` 写入时机；没有迁移 `carry`、`dump` 或 `return`
  分支，没有改变 dig exit guard、bad replan、complete-low-payload、dig-to-carry、
  switch reason、branch order、reset timing、debug/trace/rollout schema 或默认行为。
- 2026-06-17: backend runtime contract Phase 3 的第五小刀已把默认 FSM 的
  `carry` active-skill request/gate orchestration 接到
  `LegacyStateMachineBackend.tick()`。backend 通过当时的 untyped tick-context
  registry 调用现有 adapter callbacks 和
  `DumpLifecycleGateService.carry_transition_runtime()`，并返回
  `apply_carry_transition_runtime` effect；`PrimitivePlannerACTPolicy` 仍通过现有
  `_apply_carry_transition_runtime()` 应用 hold count、coverage dump completion、
  return/direct handoff、dump-start mass capture 和 `_set_skill("dump", ...)`
  等实际副作用。该切片没有迁移 `dump` 或 `return` 分支，没有改变 release-safety、
  dump-ready、boundary-event short-circuit、hold count、switch reason、branch order、
  reset timing、debug/trace/rollout schema 或默认行为；验证覆盖新增 carry backend
  contract tests、carry facade locks、golden/action-tree、primitive scheduler facades
  和 AGX primitive legacy tests。
- 2026-06-17: backend runtime contract Phase 3 的第六小刀已把默认 FSM 的
  `dump` active-skill request/gate orchestration 接到
  `LegacyStateMachineBackend.tick()`。backend 通过当时的 untyped tick-context
  registry 调用现有 adapter callbacks 和
  `DumpLifecycleGateService.dump_transition_runtime()`，并返回
  `apply_dump_transition_runtime` effect；`PrimitivePlannerACTPolicy` 仍通过现有
  `_apply_dump_transition_runtime()` 应用 hold count、coverage dump completion、
  return/direct handoff 和 `_set_skill("return", ...)` 等实际副作用。该切片没有迁移
  `return` 分支，没有改变 dump-done threshold、boundary-event short-circuit、
  hold count、switch reason、branch order、reset timing、debug/trace/rollout schema
  或默认行为；验证覆盖新增 dump backend contract tests、dump facade locks、
  golden/action-tree、primitive scheduler facades 和 AGX primitive legacy tests。
- 2026-06-17: backend runtime contract Phase 3 的第七小刀已把默认 FSM 的
  `return` active-skill gate orchestration 接到
  `LegacyStateMachineBackend.tick()`。backend 通过当时的 untyped tick-context registry
  以原顺序调用现有 adapter callbacks，并用 `ReturnToDigTransitionService` 生成
  `ReturnToDigTransitionOutcome` 与 runtime projection；`PrimitivePlannerACTPolicy`
  仍通过新增的薄 adapter applier 先应用 projection，再构造/apply completion，确保
  `_should_pre_dig_align_before_dig()` 仍在 cycle/completed-transition counters 更新后
  执行。该切片没有迁移 `_try_return_direct_handoff_at_current_obs()`，没有改变
  return handoff/direct/shallow gate、next-dig latch、switch reason、branch order、
  reset timing、debug/trace/rollout schema 或默认行为；验证覆盖新增 return backend
  contract tests、return service/facade locks、golden/action-tree、primitive scheduler
  facades 和 AGX primitive legacy tests。
- 2026-06-17: backend runtime contract Phase 3 已做 closure pass：所有默认
  active-skill branch (`bootstrap`、`pre_dig_align`、`dig`、`carry`、`dump`、`return`)
  都有 explicit backend branch；`run_legacy_fsm_transition` effect 保留为
  unsupported non-explicit context 的兼容 fallback。显式默认 FSM skill 如果收到
  generic fallback 会被拒绝，避免 under-wired backend 递归重入 adapter。
  `PrimitivePlannerACTPolicy`
  里的重复 backend tick/apply 兼容分发被收敛为薄 helper，return-specific 和
  effect-application backend tests 从 `tests/test_legacy_fsm_backend.py` 拆到
  focused files，使主 backend test 文件回到大文件阈值以下。该 pass 没有改变 branch
  order、thresholds、reason strings、reset timing、debug/trace/rollout schema、默认
  backend 选择或 behavior-tree 默认状态。
- 2026-06-17: backend runtime contract Phase 3 post-closure review 修正了一个
  测试置信度问题：`_run_legacy_fsm_transition()` 在所有默认 skill 迁到 backend 后不再是
  独立 old-inline FSM source-of-truth，因此旧的 backend-versus-direct private method
  parity test 被替换为 fallback recursion guard test。该修正只改变 under-wired
  fallback 的错误边界，不改变默认 planner 行为。
- 2026-06-18: backend runtime contract 已把旧的 untyped tick-context registry
  收敛为 typed backend ports。当前 source of truth 是
  `testbed.planner.runtime.ports.PlannerBackendPorts` /
  `LegacyFsmBackendPorts` 和
  `docs/superpowers/specs/2026-06-17-planner-backend-interface-design.md` 的
  typed ports landing record。旧记录中提到的 untyped registry 只描述历史落地过程，
  不再是当前 backend dependency boundary。
- 2026-06-17: backend interface spec 的 Phase 4 pre-slice 已添加
  `testbed.planner.runtime.behavior_tree.BehaviorTreeBackend` 实验性 fail-closed
  contract skeleton 和 contract tests。该记录属于 backend-interface phase numbering，
  不是本计划下方 broader Phase 4 `Reporting Capability Cleanup`；没有把
  `PrimitiveActionTreeRunner` 提升为 backend，也没有改默认 planner 行为。

## Methodology Correction

后续重构不再以“抽出一个 service”作为成功标准。成功标准改为：

- capability 能否脱离 `PrimitivePlannerACTPolicy` 单测？
- 输入是否是显式 `snapshot + blackboard + config`，而不是 planner `self`？
- 输出是否是显式 decision/result/effect，而不是直接写 shell 私有字段？
- 是否减少行为树 leaf node 未来需要模拟的私有状态协议？
- 是否删除或弱化旧 facade，而不是永久增加 pass-through wrapper？

不满足这些条件的切片，即使能减少 LOC，也不应优先做。

## Core Terms

`PlannerSnapshot` / `PlannerObservationView`

: 当前 step 的只读 observation projection。它回答“现在看到了什么”，例如 bucket
mass、deposit、pose、target geometry、dig-area depth/contact。

`PlannerBlackboard`

: planner 的显式工作记忆。它替代分散在 shell 中的 `self._xxx` 状态，例如 current
skill、cycle index、held tokens、pending dig plan、coverage runtime state、
counters、last switch reason。

`PlannerNodeResult`

: condition/action node 的返回值。建议形态是 `SUCCESS | FAILURE | RUNNING` 加
reason、diagnostics 和 runtime effects。

`PlannerRuntimeEffect`

: capability 请求外壳执行的副作用，例如 `set_skill`、`reset_policy`、
`update_counter`、`hold_token`、`clear_pending_plan`、`record_trace`、
`request_terminal_stop`。

`Capability`

: 可复用决策能力。它不知道自己被状态机、行为树还是测试调用，只接收显式 context，
返回 result/effect。

`Adapter`

: 兼容旧 public API 的外壳。当前主要是 `PrimitivePlannerACTPolicy`。adapter 可以把
effect 应用回旧字段，但不能成为新语义 source-of-truth。

## Source Of Truth

这些语义必须只从中心模块读取：

- schema path、env-state index/order：`testbed.data.schema`
- primitive token key/dim/order/path/version/index：`testbed.contracts.primitive_tokens`
- low-dim key/dim/order/stats/checkpoint contract：`testbed.contracts.low_dim`
- primitive profile/name/version：`testbed.contracts.primitive_profile`
- online observation projection：`testbed.planner.snapshots`
- goal sequence sector mapping：`testbed.planner.goal_sequence`
- cell-entry grid/token semantics：`testbed.planner.cell_entry`
- return start-envelope config/prior/gate：`testbed.planner.return_start_envelope*`

Edge CLI、audit、QC、pipeline 和 eval 代码不得继续手写 `v2/step/...` token path、
token order、primitive name tuple、boundary profile string 或 env-state magic index。
兼容旧入口时可以保留 facade，但 facade 必须转调中心 source-of-truth。

## Capability Matrix

| Capability | Current owner | Target role | Input contract | Output contract | State owner | Status |
| --- | --- | --- | --- | --- | --- | --- |
| Observation projection | `snapshots` | blackboard input | raw `obs`, action dim | `PlannerSnapshot` | none | mostly ready |
| Return handoff | `return_handoff` | condition node | snapshot, boundary facts, handoff context | handoff decision | blackboard effect | mostly ready |
| Return transition | `return_to_dig_transition` | transition node | handoff result, boundary event, config | outcome/projection | shell adapter now, blackboard later | mostly ready |
| Dig lifecycle | `dig_lifecycle*` | condition/action nodes | snapshot, boundary event, coverage state, counters | progress/transition decision | blackboard | mostly ready |
| Dump lifecycle | `dump_lifecycle*` | condition/action nodes | snapshot, boundary event, hold counters | readiness/completion outcome | blackboard | mostly ready |
| Pre-dig alignment | `dig_start_alignment_*` | action/condition nodes | snapshot, token/config, counters | target/action/readiness/effect | blackboard | mostly ready |
| Policy observation | `policy_observation` | action helper | active skill, token availability | policy obs + injected flags | adapter | ready |
| Dig-cut plan | `dig_cut_plan` + shell | action node | snapshot, prior, selected corridor | token/source/effect | pending plan | partial |
| Dig depth profile | `dig_depth_profile` + shell callbacks | action helper | pending/active/live facts | token/source/effect | pending plan | partial |
| Return target plan | `return_target_plan` + shell callbacks | action node | next dig target, envelope, exemplar | return token + pending dig effect | pending plan | partial |
| Coverage selection/progress | `dig_coverage/*` + `DigCoverageMixin` | action node | snapshot, coverage state, config | corridor/action/effect | coverage blackboard state | blocked |
| Debug/reporting | `primitive_debug*` + shell facts | reporting capability | explicit facts/snapshots | debug/trace/summary payload | adapter | partial |

Agent rule: before starting a refactor, identify the target row and update its `Status`
only when the Definition of Done is met.

## Slice Selection Rules

Accept a slice when it satisfies at least one high-value condition:

- It removes a direct dependency on planner `self` from a reusable capability.
- It replaces shell private state access with explicit blackboard/state/result objects.
- It centralizes duplicated token/profile/schema/env-state semantics.
- It allows a capability to be tested without constructing `PrimitivePlannerACTPolicy`.
- It deletes or narrows old private facade surface after migration.
- It archives deprecated code and rationale before removing a live private facade.

Reject or postpone a slice when:

- It only wraps one helper call with a new long-term module.
- It reduces a few lines but leaves the same private state protocol in place.
- It requires semantic changes to thresholds, branch order, token contracts, debug fields,
  rollout output, primitive boundaries or checkpoint compatibility without user confirmation.
- It promotes 5P, legacy or diagnostic behavior into mainline semantics without confirmation.
- It creates an orchestrator before blackboard/result/effect contracts are stable.
- It deletes legacy/private facade code without first adding a deprecated artifact
  record when the old code documents a real design attempt or migration seam.

## Migration Ticket Template

Every non-trivial refactor task should start with this ticket:

```text
Task type:
  capability migration / source-of-truth cleanup / adapter deletion / test migration

Capability matrix row:

Goal:

Non-goals:
  threshold changes:
  branch order changes:
  token/debug/rollout schema changes:

Source-of-truth modules:

Files allowed to edit:

Files allowed only as adapter/facade:

Old shell dependency to remove:

New input contract:

New output/effect contract:

Tests to add or migrate:

Definition of Done:

Open semantic decisions:
```

If the ticket cannot be filled without guessing semantics, pause and ask for confirmation.

## Agent Execution Protocol

For future Codex work:

1. Classify the task.
   - structural refactor
   - semantic change
   - compatibility fix
   - documentation/test-only change

2. Locate the capability row.
   - If no row exists, decide whether this is a stable capability or a one-off request.
   - Do not create a long-term module for a one-off experiment.

3. State invariants before editing.
   - no threshold change
   - no branch order change
   - no switch reason change
   - no token/debug/rollout schema change
   - no checkpoint compatibility change

4. Prefer capability tests first.
   - A capability that cannot be tested without `PrimitivePlannerACTPolicy` is not yet
     behavior-tree ready.

5. Keep shell edits thin.
   - shell samples old fields
   - calls capability
   - applies returned effect
   - preserves public/debug behavior

6. After migration, remove or demote private facade tests when safe.
   - Do not let old private tests define long-term semantics.
   - Before deleting a live private facade, archive the old code and rationale under
     `deprecated/primitive_scheduler/` unless the change is only formatting or an
     unreachable typo fix.

## Phase Plan

### Phase 0: Contract And Execution Layer

Goal: make future agent work mechanical and verifiable.

Work:

- Finalize `PlannerBlackboard`, `PlannerNodeResult`, `PlannerRuntimeEffect` field boundaries.
- Add context source precedence tests for `PlannerObservationView`.
- Add a small synthetic planner semantic trace:
  boundary event -> snapshot/context -> service decision -> runtime effect ->
  debug/rollout/eval visible field.
- Mark legacy/diagnostic/experimental tests or isolate them by naming convention.
- Keep this plan and the capability matrix updated as source-of-truth.

Definition of Done:

- A new agent can choose the next refactor by reading this file and one target module.
- At least one capability can be tested with `snapshot + blackboard + config` and no
  `PrimitivePlannerACTPolicy`.

### Phase 1: Source-Of-Truth Cleanup

Goal: remove semantic drift before deeper behavior-tree work.

Work:

- Replace audit/QC/pipeline/eval token path literals with `schema` /
  `primitive_tokens` constants.
- Replace repeated primitive name tuples with `primitive_profile`.
- Add env-state helper for grid/cell index math.
- Consolidate spatial-mass / surface-depth profile thresholds into a profile config object
  before using them across builder, detector and eval.
- Add rg/contract tests for naked token paths, profile strings and magic env-state indexes.

Definition of Done:

- Core and edge paths cite the same source-of-truth.
- Contract tests fail if a new naked token path/profile/index appears in long-term code.

### Phase 2: Coverage Capability Boundary

Goal: make coverage usable as a behavior-tree action node.

Work:

- Define explicit `CoverageRuntimeState`.
- Define `CoverageDecisionResult` and `CoverageRuntimeEffect`.
- Move `_coverage_*` private state proxy semantics out of `DigCoverageMixin` and into
  explicit state/effect application.
- Keep `DigCoverageMixin` as compatibility adapter only.
- Test direct coverage capability and old facade equivalence.

Definition of Done:

- Coverage selection, raw fields, complete/reject can run without constructing
  `PrimitivePlannerACTPolicy`.
- Shell adapter does not expose broad `_coverage_*` private field ownership as the
  long-term API.

### Phase 3: Token And Pending-Plan Action Capabilities

Goal: remove shell callback chains from dig-cut, dig-depth-profile and return-target build.

Work:

- Replace return-target coverage corridor callback with explicit provider/result.
- Replace dig-depth-profile pending/active/live/env callbacks with explicit facts.
- Return token/source/fallback/pending-state effects from action capability.
- Shell only applies effects and preserves debug/rollout compatibility.

Definition of Done:

- Token build can be tested from `snapshot + blackboard + config`.
- Pending return-target activation does not require shell private helper calls.

### Phase 4: Reporting Capability Cleanup

Goal: keep debug/trace/summary stable while removing shell hand assembly.

Work:

- Define explicit reporting facts sourced from capability snapshots/results.
- Keep public debug keys and order stable.
- Migrate private debug tests toward reporting capability tests.

Definition of Done:

- Debug/summary/trace payload can be built from explicit facts, not arbitrary shell reads.
- Shell tests only verify public compatibility.

### Phase 5: Node/Effect Shadow Runner

Goal: prove behavior-tree compatibility without changing live behavior.

Work:

- Express main dig/carry/dump/return paths as condition/action node composition.
- Return `PlannerNodeResult`; do not call `_set_skill()` inside nodes.
- Apply effects through shell adapter in shadow mode only.
- Compare behavior-tree shadow trace with current state-machine golden trace.

Definition of Done:

- Shadow trace records node path, reason, result, effects and blackboard diff.
- Divergence is explainable before any live default changes.

### Phase 6: Experimental Behavior-Tree Backend

Goal: expose a behavior-tree backend only as an explicit experimental mode.

Work:

- Add explicit config such as `planner_backend: behavior_tree_shadow` or
  `behavior_tree_experimental`.
- Reuse existing capability modules; do not copy gate/token/profile semantics into nodes.
- Promotion to mainline requires user-confirmed compatibility policy.

Definition of Done:

- Behavior-tree mode can run with full diagnostics.
- Default planner behavior remains unchanged until explicitly promoted.

## Do / Don't

Do:

- Treat `PrimitivePlannerACTPolicy` as adapter, not long-term semantic home.
- Use `snapshot + blackboard + config` as target input shape.
- Use `result/effect` as target output shape.
- Add capability tests before or with adapter changes.
- Delete or narrow private facade surface when compatibility no longer needs it.
- Archive deprecated design/code before deleting it from live modules.
- Keep docs and tests synchronized with every code migration.

Don't:

- Do not add new gate logic to `primitive_planner.py`.
- Do not create a new module for a single helper or one experiment.
- Do not copy token path, token order, profile string, primitive name tuple or env-state index.
- Do not let behavior-tree nodes read or write `policy._xxx`.
- Do not change thresholds, branch order, switch reasons, token contracts, debug fields,
  rollout records, primitive boundaries or checkpoint compatibility without confirmation.
- Do not keep adding tests that make private shell fields the semantic source-of-truth.
- Do not delete historically meaningful failed branches or migration seams without a
  deprecated artifact that explains why the live path should not use them.

## Test Strategy

Use this order of preference:

1. Contract tests: token, low-dim, schema path, profile name, env-state index.
2. Capability tests: snapshot/context, gate decision, token build, coverage decision.
3. Effect tests: capability result to runtime effect projection.
4. Adapter tests: old facade applies effect and preserves public behavior.
5. Golden trace tests: active skill, switch reason, completed transition count, token source,
   debug and rollout visible fields.
6. Legacy tests: explicitly marked compatibility/diagnostic coverage.

## Open Decisions

These must not be guessed by agent work:

- Whether behavior tree will become default planner backend or remain diagnostic.
- Which private facades can be deleted versus kept for compatibility.
- Whether coverage runtime state belongs entirely in `PlannerBlackboard` or remains owned by
  a coverage-specific state object referenced by blackboard.
- Whether 5P should ever be redesigned later. Current rule: keep it
  compatibility-only and do not expand 5P semantics or acceptance criteria unless the
  user explicitly reopens it.
- Which debug fields are compatibility-contract fields versus diagnostic-only fields.
- When behavior-tree shadow divergence becomes acceptable for live gating experiments.

## Completion Definition

The refactor reaches the intended target when:

- Behavior-tree leaf nodes can reuse planner capability modules without reading planner shell
  private fields.
- Coverage, dig-cut, return-target, return-envelope and dig/dump/return gates all have
  explicit input/output/effect contracts.
- `PrimitivePlannerACTPolicy` is only a compatibility adapter applying effects and dispatching
  policies.
- Source-of-truth contracts cover train/eval/data/policy/rollout/audit/QC edge paths.
- Golden traces compare current state-machine behavior with behavior-tree shadow behavior.
- Future agent tasks can be scoped by capability matrix row and migration ticket, without
  rereading the full historical refactor thread.
