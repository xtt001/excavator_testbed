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

3. Training And Eval Preflight

Before starting any `tb-train` or `tb-eval` command, the agent must read
`docs/training_setup.md` and use `docs/checklist_train.md` as the preflight
checklist, or perform an equivalent explicit preflight summary.

The preflight must at least confirm:

- the selected train/eval config and whether it is current or legacy
- dataset root, primitive root, or materialized copy root
- required Gate / QC status, including manual review when the data contract
  requires it
- low-dimensional inputs, supervision keys, and training tier assumptions
- checkpoint/output directories and whether existing artifacts may be
  overwritten

If the user asks to run training or eval urgently, the agent may keep the
preflight concise, but it must not silently skip these checks.

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
