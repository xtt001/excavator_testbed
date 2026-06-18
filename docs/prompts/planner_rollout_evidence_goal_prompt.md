# Planner Rollout Evidence Goal Prompt

Use this prompt to start a Codex Long-running Goal for the active planner
refactor route.

```text
请创建并执行 Long-running Goal：

objective:
在 /home/pingfan/PACT/excavator_testbed 中按 rollout-evidence-driven 方法继续 planner backend/runtime migration。不要继续在巨大 primitive planner 文件里牵线式重构；先从真实 rollout log 证明 live path，再起新 focused module，把旧代码里真实用上的逻辑搬出来，parity 通过后删除旧 inline path。

必须使用：
- $excavator-planner-safe-refactor
- superpowers:test-driven-development
- superpowers:verification-before-completion

目标锁：
- host: 本机
- cwd: /home/pingfan/PACT/excavator_testbed
- branch: fs/v2_4-refactor-tests
- remote policy: 不 fetch / pull / push，完成后只做本地 commit

先读：
- AGENTS.md
- docs/planner_rollout_evidence_refactor_plan.md
- docs/planner_rollout_evidence_refactor_log.md
- docs/superpowers/specs/2026-06-17-planner-backend-interface-design.md
- /home/pingfan/.codex/skills/excavator-planner-safe-refactor/SKILL.md

第一性原理反思门：
每轮代码前先回答：
1. 哪个真实 rollout log 证明这条路径 live？
2. log 里明确出现了哪些 skill / switch reason / token source / debug key / runtime effect？
3. 这轮是否在减少耦合，还是只是给旧大文件再加一层 adapter？
4. 新文件的稳定责任是什么？
5. parity 通过后要删除哪段旧代码？
6. 当前动作是否偏离 docs/planner_rollout_evidence_refactor_plan.md？
7. 这轮是否把“保护旧代码”放到了“重构和理顺逻辑”之上？如果是，停止并重选切片。

执行规则：
- 主目标是重构、抽象层封装、保留真实 rollout 用到的有用代码；保护行为只是约束，不是主目标。
- 没有 rollout log 证据时，只做 audit，不做迁移。
- 新实现先进 focused module，不在 primitive_planner.py 里新增算法逻辑。
- primitive_planner.py 只允许 import、显式输入构造、调用新模块、应用 effect、删除旧实现。
- tests 先行，至少覆盖新 module contract、old path deletion/compatibility guard、必要 parity。
- 计划和修改记录分离：计划不写 landing record；结果追加到 docs/planner_rollout_evidence_refactor_log.md。
- 保持默认 backend、branch order、threshold、reason string、policy reset timing、debug/rollout/token schema 不变；如不确定，停止询问。

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
old code deleted or reclassified:
commands run:
verification result:
decisions made:
first-principles reflection:
risks or unknowns:
next action:
do-not-repeat:
```
