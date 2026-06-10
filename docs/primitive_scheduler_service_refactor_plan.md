# Primitive Scheduler Refactor Plan

本文档是 primitive planner 重构的执行手册。它替代旧的长篇 service extraction
日志，目标是帮助人类和 agent 用同一套规则推进后续切片。

当前方向：**沉淀行为树可复用的决策语义层**，而不是单纯把
`PrimitivePlannerACTPolicy` 拆成更多文件。现有状态机仍是兼容入口；长期目标是让
状态机、行为树、decision tree 或 option scheduler 都复用同一批 capability。

## Current Map

当前 public facade：

- `testbed.policies.hybrid.primitive_planner.PrimitivePlannerACTPolicy`
- `PrimitivePlannerACT5PPolicy` 只作为 5P compatibility / diagnostic path。

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

Reject or postpone a slice when:

- It only wraps one helper call with a new long-term module.
- It reduces a few lines but leaves the same private state protocol in place.
- It requires semantic changes to thresholds, branch order, token contracts, debug fields,
  rollout output, primitive boundaries or checkpoint compatibility without user confirmation.
- It promotes 5P, legacy or diagnostic behavior into mainline semantics without confirmation.
- It creates an orchestrator before blackboard/result/effect contracts are stable.

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
- Keep docs and tests synchronized with every code migration.

Don't:

- Do not add new gate logic to `primitive_planner.py`.
- Do not create a new module for a single helper or one experiment.
- Do not copy token path, token order, profile string, primitive name tuple or env-state index.
- Do not let behavior-tree nodes read or write `policy._xxx`.
- Do not change thresholds, branch order, switch reasons, token contracts, debug fields,
  rollout records, primitive boundaries or checkpoint compatibility without confirmation.
- Do not keep adding tests that make private shell fields the semantic source-of-truth.

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
- Whether 5P is permanently legacy or should be redesigned later.
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
