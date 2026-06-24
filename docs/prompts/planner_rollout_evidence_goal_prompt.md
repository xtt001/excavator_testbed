# Planner Rollout Evidence Goal Prompt

Use this prompt to start a Codex Long-running Goal for the active planner
refactor route.

```text
请创建并执行 Long-running Goal：

objective:
在 /home/pingfan/PACT/excavator_testbed 中按 baseline-architecture + rollout-evidence-driven 方法继续 planner backend/runtime migration。不要继续在巨大 primitive planner 文件里牵线式重构，也不要把当前半迁移 HEAD 当作目标架构。先回到 branch baseline 重建 planner 架构图，再用真实 rollout log 证明 live path，起新 focused module，把旧代码里真实用上的逻辑搬出来；parity 通过后只做 thin facade / legacy parking / compatibility owner，不把删除旧函数当作当前目标。

必须使用：
- $excavator-planner-safe-refactor
- superpowers:test-driven-development
- superpowers:verification-before-completion

目标锁：
- host: 本机
- cwd: /home/pingfan/PACT/excavator_testbed
- branch: fs/v2_4-refactor-tests
- remote policy: 不 fetch / pull / push，完成后只做本地 commit

先读 source-of-truth：
- AGENTS.md
- docs/planner_rollout_evidence_refactor_plan.md
- docs/planner_rollout_evidence_refactor_log.md
- docs/planner_baseline_architecture_map.md
- docs/planner_current_architecture.md
- docs/planner_scheduling_backend_design.md
- docs/planner_current_code_architecture_plan.md
- docs/planner_evidence_trace_tool.md
- /home/pingfan/.codex/skills/excavator-planner-safe-refactor/SKILL.md

可选历史参考，不作为实施 source-of-truth：
- docs/refactor_history/planner/

开始前必须先做 branch baseline 架构重建：
- 不 fetch / pull。
- 用本地 reflog 确认 `fs/v2_4-refactor-tests` 创建时的 baseline。
- 当前已知 branch-created baseline 是 `152350e3ed9a8816ca8d685195fc8f297ab3fcec`。
- 不要用 `origin/fs/v2_4-refactor-tests` 或
  `git merge-base HEAD origin/fs/v2_4-refactor-tests` 替代创建 baseline。
- 从 branch baseline 的代码重建 planner 入口、状态切换、token、effect、debug/reporting 数据流。
- 更新 `docs/planner_baseline_architecture_map.md`。
- 以 `docs/planner_current_architecture.md` 和
  `docs/planner_current_code_architecture_plan.md` 的结构为目标：
  public policy adapter -> execution kernel -> capability port -> decision
  backend -> effect application。
- 第一段代码迁移应优先抽出 public tick execution template，不要直接跳到
  behavior tree、VLM 或 legacy FSM backend。
- 当前 HEAD 只能作为 patch queue / implementation history，不能作为目标架构 source of truth。
- 架构图未补齐前，只允许 audit，不允许迁移 planner 代码。
- 用 `tb-planner-evidence classify` 先从 rollout JSONL / planner trace /
  rollout summary / evidence JSONL 生成 retention decision；成功主线没有体现作用、
  或失败时没有突出为缺失原因的非兼容路径，应进入 `dead-candidate`，并先作为
  legacy parking 处理，不迁入主干架构。

第一性原理反思门：
每轮代码前先回答：
1. 我们是否从 branch baseline 架构出发，而不是从当前乱序代码出发？
2. docs/planner_baseline_architecture_map.md 是否已经描述这条路径的数据流？
3. 哪个真实 rollout log 证明这条路径 live？
4. log 里明确出现了哪些 skill / switch reason / token source / debug key / runtime effect？
5. 这轮是否在减少耦合，还是只是给旧大文件再加一层 adapter？
6. 新文件的稳定责任是什么？
7. parity 通过后哪些旧代码要变成 thin facade、legacy parking 或
   compatibility owner？
8. 当前动作是否偏离 docs/planner_rollout_evidence_refactor_plan.md？
9. 这轮是否把“保护旧代码”放到了“重构和理顺逻辑”之上？如果是，停止并重选切片。

执行规则：
- 主目标是重构、抽象层封装、保留真实 rollout 用到的有用代码；保护行为只是约束，不是主目标。
- 目标架构来自 branch baseline + rollout 证据 + docs/planner_baseline_architecture_map.md，不来自当前 HEAD 的堆叠形状。
- 没有 rollout log 证据时，只做 audit，不做迁移。
- 新实现先进 focused module，不在 primitive_planner.py 里新增算法逻辑。
- primitive_planner.py 只允许 import、显式输入构造、调用新模块、应用 effect、thin facade / legacy parking owner。
- tests 先行，至少覆盖新 module contract、old path parking/reclassification/compatibility guard、必要 parity。
- 计划和修改记录分离：计划不写 landing record；结果追加到 docs/planner_rollout_evidence_refactor_log.md。
- 保持默认 backend、branch order、threshold、reason string、policy reset timing、debug/rollout/token schema 不变；如不确定，停止询问。
- 如果你作为 refactor/audit 线程创建 executor thread，executor prompt 必须要求：
  在 bounded task 完成后、executor 本地 final reply 前，使用 Codex thread tool
  `send_message_to_thread` 回调 source/refactor thread，字段必须包含 target lock、
  TDD red、changed files、core factual change、verification、behavior impact、
  docs status、git status after、HEAD after；并在后续 executor prompt 中递归保留
  这个闭环回调要求。
- refactor/audit 线程自身必须始终显式使用 `thinking: xhigh`。每次生成
  executor prompt 时，prompt 文本必须显式指定 executor thinking effort 为
  `thinking: high` 或 `thinking: xhigh`；如果 Codex thread tool 暴露
  thinking 参数，也要在 tool 调用里传相同强度。这个 thinking-effort 要求必须
  写进要求 executor 回调的递归规则里，避免后续 prompt 漂移到未指定或错误的
  思考强度。
- 每 3 轮 bounded executor implementation 后，refactor/audit 线程必须先在
  docs/planner_rollout_evidence_refactor_log.md 记录 three-iteration
  reflection，再生成下一轮 executor prompt。反思必须显式列出并核对 reference
  set，不能凭记忆、随机旧文档或当前代码形状自由发挥。reference set 至少包括：
  docs/planner_current_architecture.md；
  docs/planner_scheduling_backend_design.md；
  docs/planner_primitive_interface_standard.md；
  docs/planner_current_code_architecture_plan.md；
  docs/planner_baseline_architecture_map.md（历史/基线对照，不替代当前标准）；
  docs/planner_rollout_evidence_refactor_plan.md；
  docs/planner_rollout_evidence_refactor_log.md；
  docs/prompts/planner_rollout_evidence_goal_prompt.md；
  AGENTS.md；以及当前代码/ focused tests。反思必须判断：是否更接近该 reference
  set 中的当前架构图、backend guide 和 interface standard，最大剩余差距，下一步核心 bounded slice，
  是否过度保护旧代码或产生贫血 pass-through facade，以及是否需要方向修正。
  executor 不写反思。
- 这条 three-iteration reflection gate 必须显式写进双方 prompt surface：
  refactor/audit prompt 要记录当前 accepted-slice 计数和下一次 callback 是否触发
  gate；executor prompt 要要求 executor 回传足够事实证据，但不得替 planner 写
  deep reflection、不得选择下一片。未记录三轮反思前，不允许派发第四个 executor
  implementation slice。
- 每一轮 refactor/audit prompt 和 executor delegation prompt 都必须显式复制
  skill compliance block：target lock first；planner dispatch 后 yield，不轮询；
  executor green 不等于 closure，planner 必须复核 target lock/scope/diff/docs/
  behavior/verification；每次 callback 做轻量反思，三次 accepted implementation
  callback 或失败/偏航后做 deep reflection；executor 只回事实，不选下一片；
  不虚构 thinking/model/tool/CLI/env/path/branch/schema/port/config 值；不改
  runtime config 除非明确允许并已验证；保护是约束不是目标；不保留可直接连到
  focused owner/service 的旧 private glue；不传 planner self，不新增 broad
  pass-through object、generic blackboard、broad config bag、anemic service 或
  one-method-per-private-method callback bag；保持 public schema、token order/
  dimensions、branch order、reason string、reset timing、default legacy FSM 和
  BT/VLM/LLM fail-fast，除非用户明确批准语义改变。

每轮验证至少考虑：
- focused pytest for new module
- affected backend/runtime/facade/golden/debug/token tests
- python -m compileall for changed modules
- git diff --check
- python scripts/planner_refactor_guard.py --check-plan-contract
- python scripts/planner_refactor_guard.py --check-skill-contract

最终输出 handoff manifest：
purpose:
host/repo/branch:
dirty status before/after:
HEAD before/after:
rollout evidence used:
confirmed-live path:
new files:
old code parked or reclassified:
executor callback status:
commands run:
verification result:
decisions made:
first-principles reflection:
three-iteration reflection status:
risks or unknowns:
next action:
do-not-repeat:
```
