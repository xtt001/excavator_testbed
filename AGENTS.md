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

2. Documentation Sync

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
