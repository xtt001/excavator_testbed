# AGENTS.md

This file defines repository-wide working rules for coding agents in this
workspace.

## Scope

These rules apply to the entire repository unless a deeper `AGENTS.md` overrides
them for a subdirectory.

## Global Rules

1. Language

All user-facing responses should be in Chinese by default, unless the user
explicitly asks for another language.

2. User-Facing Clarity

Lead with the practical result in plain language: whether the task completed,
what directly stopped it, why that matters, and what should happen next. Do not
make the user decode internal experiment names, schema names, status enums,
gate labels, abbreviations, or untranslated English terminology.

When an internal identifier is needed for traceability, explain its real-world
meaning first and place the identifier afterward in parentheses or in a
separate technical-reference note. Define unavoidable technical terms on first
use. For rollout and planner reports, state task completion and the direct
failure chain before discussing internal evidence categories.

This presentation rule must not weaken technical rigor. Preserve exact
measurements, safety boundaries, evidence provenance, uncertainty, and the
distinction between observed facts and inference; only translate how they are
communicated to the user.

For every non-trivial implementation, diagnosis, evaluation, rollout, or
planner final response, use two audience layers:

1. User conclusion

   The opening must stand on its own for a reader who has not read the code,
   configs, logs, or prior experiment labels. State, in this order:

   - exactly what is complete and what remains incomplete;
   - the direct operational or physical cause in ordinary language;
   - what changed, what the observed result was, and whether safety checks
     passed;
   - whether production/default behavior changed and what should happen next.

   Never use a bare phrase such as "completed" when only a diagnosis, bounded
   experiment, replay, shadow run, or diagnostic-only implementation completed.
   Say that boundary explicitly, for example: "The diagnosis and bounded
   experiment completed; the production fix has not been promoted."

2. Technical evidence

   Put exact field names, schema dimensions, source-owner identifiers, gate
   names, step numbers, experiment codes, raw thresholds, artifact paths, and
   superseded attempts after the user conclusion. This layer may preserve all
   engineering precision, but the reader must not need it to understand the
   outcome.

In the user conclusion:

- Describe what a component or condition does before naming it. For example,
  explain "which data source has the final say" before using `owner`, "the
  conditions required to begin the next action" before using `handoff gate`,
  and "the measured joint position" before using `qpos`.
- Do not lead with raw identifiers or untranslated phrases such as field
  numbers, `p05`/`p50`, `ready`, `bounded`, `request-local`, `superseded`, or
  `diagnostic_only`. Use them only afterward in parentheses or in technical
  evidence when traceability requires them.
- Interpret every important number. State what is being compared, which side of
  the limit it falls on, and why that changes the result. Prefer human-readable
  units in the user conclusion while retaining exact raw values in technical
  evidence.
- Separate causal evidence from correlation and separate replay/verifier
  evidence from real closed-loop execution.
- State safety preservation in practical terms, such as "no safety threshold
  was relaxed," before listing unchanged config identifiers.

Before sending the final response, silently check that a non-expert reader can
answer all four questions from the opening alone:

1. What was actually completed?
2. Why did it succeed or fail?
3. Is the result safe and what evidence type supports it?
4. Did the production/default system change, and what is next?

If any answer requires decoding a project identifier or reading the technical
evidence, rewrite the opening before sending.

3. Documentation Sync

Any task that changes code must also update the relevant documentation in the
same task. Update the closest source of truth for the change, such as:

- `README.md`
- files under `docs/`
- protocol or integration specs
- config examples
- docstrings or other developer-facing documentation when appropriate

If a code change is purely internal and no documentation update is needed, the
agent must explicitly justify that decision in the final response instead of
silently skipping documentation updates.

## Codebase Governance

These rules keep the repository maintainable as training, rollout, replay, and
planner semantics grow more coupled.

1. Large File Policy

A Python file with 1000 or more lines is considered a large file. Large files
must not receive new feature implementations, new algorithm logic, or new
semantic branches.

Allowed changes in large files are limited to thin interface work: imports,
parameter pass-through, facade or adapter calls into focused modules, deleting
old implementation after migration, small bug fixes, and parallel replacement
that moves behavior into a smaller module. New functionality, new semantics, and
new reusable helpers must live in a focused module or an existing small module
with the right responsibility.

2. Semantic Source Of Truth

Token dimensions, token order, contract versions, dataset paths, low-dimensional
keys, and boundary profile names must have one source of truth. Do not duplicate
these semantics separately across training, evaluation, rollout, replay, data
builders, and policy adapters.

New semantics must be defined centrally first, then referenced by the train,
eval, rollout, and data-building paths that consume them. Do not copy semantic
definitions into multiple places just to make a run work.

3. Responsibility Boundaries

`data` modules own HDF5 I/O, schema constants, dataset reading, and derived data
fields; they must not make online planner decisions.

`planner` and scheduler code owns target selection, handoff, gates, and replan
decisions; it must not own training loops, checkpoint formats, or HDF5 writing.

`policy` and adapter code owns model inputs/outputs, normalization stats, and
checkpoint loading; it must not accumulate task-level business semantics.

`cli` modules own argument parsing and orchestration; complex algorithms should
live in focused library modules and be called from the CLI.

4. Legacy And Experimental Semantics

Legacy, diagnostic, and ablation paths must be explicitly labeled as such. New
code must not extend legacy paths unless the task explicitly asks for
compatibility or a bug fix.

Experimental semantics must not silently become the default mainline. Promote an
experimental path only after the intended semantics and compatibility policy have
been confirmed.

5. Semantic Change Confirmation

Before changing semantics that affect training, rollout, replay, planner logic,
primitive boundaries, token contracts, or checkpoint compatibility, confirm what
should be kept, discarded, and kept only for compatibility.

Agents must not decide official semantics from assumptions. Unconfirmed
semantics must not be written into central contracts or default configs.

6. Tests And Documentation

New semantics require consistency tests that cover the affected train, eval,
rollout, data, or policy interfaces.

Code changes must update the closest source-of-truth documentation. If a change
is only an internal rearrangement and needs no documentation update, the final
response must explain why.

Test strategy should be proportional to semantic risk. Use strict
test-first/TDD for new behavior, bug fixes, risky refactors, public contracts,
planner gates, token schemas, training/eval data semantics, and other changes
where a failing test is needed to prove the intended behavior. Do not perform a
ceremonial red-green cycle for simple documentation edits, mechanical renames,
comment/help-text updates, one-line mapping changes, or other obvious
low-risk changes where the existing contract is already clear.

For low-risk changes that skip test-first development, explicitly choose the
smallest useful verification instead: for example `git diff --check` for docs,
compile/lint for touched Python modules, or focused existing tests for a small
code path. Do not use "simple change" as a reason to skip verification
entirely.

7. Refactoring Direction

Extract central facts and pure functions first, then migrate callers. Preserve
existing public imports, CLI commands, and config entry points as facades unless
the user explicitly approves a breaking change.

Each refactor should move one clear responsibility at a time and must not mix
structural movement with algorithmic semantic changes.

8. Naming And File Creation

Files, classes, and functions must be named by stable responsibility, domain
capability, or interface role. Long-term library code must not be named after a
single experiment, one bug, one run, a date, a temporary observation, or the
specific feature request that happened to introduce it.

New method and class names should describe the role, input/output, or strategy
they implement. Avoid one-off requirement names that cannot still make sense
after the immediate experiment is over.

Before creating a new file, check whether an existing small module already owns
the responsibility. If a new file is still needed, its stable responsibility,
domain or capability, expected reuse boundary, and reason for not using an
existing module must be clear.

A new file may be small, but it must own one stable responsibility. Do not create
long-term library files for a single function, single bug, single experiment, or
single run.

New directories and packages should be created only for stable domains or
capabilities. Do not create library directories for one feature, experiment,
date, checkpoint, rollout, or one-off pipeline. Avoid turning a large-file
problem into a large-directory problem.

Version suffixes in library file names are allowed only for true compatibility
boundaries such as schemas, protocols, token contracts, and data contracts.
Experiment tags, dates, and stage-specific run names belong in `runs/jobs` or
`scripts`, not in long-term `testbed` library module names.

CLI file names may reflect concrete commands or workflows, but CLI modules
should only parse arguments and orchestrate. Complex logic must live in
responsibility-named library modules. Temporary probes, one-off migrations, and
single-run experiment orchestration should stay in `runs/jobs` or `scripts`
unless they are promoted into a stable library capability.

9. Planner State Machine Architecture

Planner state-machine classes should converge toward thin state machine shells.
The shell owns the active state, transition reason, state lifecycle, policy
dispatch, and the order in which focused services are called.

Do not keep adding non-core computation to large planner classes. Geometry
calculations, alignment logic, coverage scoring, return envelope construction,
handoff gates, dump geometry gates, token assembly, diagnostic payloads, and
debug or summary schemas should live in responsibility-named service objects or
capability modules.

New migrations should prefer service objects as the long-term boundary. Mixins
are allowed as a low-risk transition when they preserve old private methods, and
pure functions are appropriate only for clearly stateless logic. Service names
must describe stable capabilities, such as `DigStartAlignmentService` or
`PrimitiveHandoffGateService`, not one experiment, bug, run, or temporary
feature.

Existing private methods may remain as facade entry points for tests and
diagnostics, but the implementation source of truth should move to the
service/capability module. Each migration should move one clear responsibility
chain and must not mix structural movement with state-machine semantic changes,
threshold changes, or algorithm changes.

10. Sub-Agent Dispatch

- At the start of each non-trivial task, judge whether the task is simple, medium, or complex, and decide whether sub-agents would materially help.
- Use sub-agents proactively when the task has independent parallel tracks, such as codebase exploration, research comparison, test investigation, review, source synthesis, or multi-file implementation with separated ownership.
- If the user explicitly asks to use multi-threading, parallel agents, or sub-agents at the beginning of a thread, treat that as a standing preference for the rest of the thread unless they later say not to.
- Keep the main thread as Lead: it owns task decomposition, dispatch, result collection, conflict resolution, and final synthesis.
- Prefer delegating sidecar tasks that can run in parallel while the Lead continues useful local work. Keep urgent, tightly coupled, or next-step-blocking work in the main thread.
- Give each sub-agent a bounded task contract: role, input scope, expected output, Definition of Done, file/path ownership when relevant, what not to change, and the exact context it must know.
- Assume sub-agents may not inherit the full parent conversation. Include necessary goals, file paths, constraints, prior decisions, and error messages directly in the task prompt.
- Use read-only/tool-limited agents for exploration and review when possible. Give write-capable workers disjoint ownership to avoid conflicts.
- For large outputs, ask sub-agents to return concise summaries plus artifact paths or evidence references. Only allow artifact writes when the Lead assigns an explicit writable path.
- Before dispatching, provide a short dispatch summary: which agents will do what, what the main thread will do locally, and what result is expected.
- After agents return, provide a short collection summary: what was accepted, what was ignored, what remains uncertain, and the next action.
- Do not use sub-agents for tiny tasks, simple one-answer explanations, simple terminal commands, or narrow single-file edits where coordination would add more cost than value.
- Avoid uncontrolled fan-out and recursive delegation. Start with 1-3 sub-agents unless there are clearly independent tracks that justify more.
- Escalate destructive, irreversible, privacy-sensitive, or high-stakes decisions to the user instead of letting a sub-agent decide.
- If the thread has an active multi-agent preference and two consecutive non-trivial turns forget dispatch or collection, the next turn must self-correct before continuing.

<!-- codex-deep-reasoning-budget:begin -->
## 深度推理预算守则

适用范围：在不违反更高优先级系统、开发者或用户指令的前提下，默认采用以下工作方式，以降低过早结束推理、误把边界情况当作模式题、或在低推理预算处提前 final 的概率。

### 规则 0
- 可以花费足够多的时间进行思考；不要为了显得响应很快而提前给出未经验证的答案。
- 不要发送可选的 commentary 消息。
- 不要用 commentary 汇报进度、叙述状态或解释中间过程。
- 只有在工具调用需要，或用户明确要求状态更新，或更高优先级指令要求状态更新时，才使用 commentary。
- 对于不需要工具的任务，先完成推理，然后只在 final 中回答。

### 推理
- 优先使用第一性原理推理，而不是模式匹配。
- 在解决问题前，先识别哪些信息是可观察的，哪些行动是可控制的，以及要求保证什么。
- 如果某个属性可以被观察、触摸感知、标记、排序或以其他方式控制，就用一个可以利用分阶段/自适应选择的策略来求解；不要把问题简化成盲目的一次性抽样。
- 对于定量、逻辑、边界或保证类问题，在最终回答前，证明策略在最坏情况下的充分性，并证明匹配的下界。
- 如果答案是数字，重新检查算术，并确保最终数值准确回答了问题。

### 通用性
- 这些是通用工作规则；不要针对某个特定评测、预期答案或固定输出模式进行定制。
<!-- codex-deep-reasoning-budget:end -->
