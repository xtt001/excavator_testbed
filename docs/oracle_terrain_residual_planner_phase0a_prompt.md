# Phase 0A Executor Prompt

```markdown
thinking: xhigh

Hard rules:
- Planner owns goal, target lock, scope, reflection, recovery, closure, and the next slice.
- Planner must challenge unnecessary existing code and choose slices that solve the user's problem, not only protect the old shape.
- Planner owns work allocation: bundle tightly coupled work, split only for distinct ownership/risk/verification.
- Executor performs one bounded slice only and returns facts, not strategy, advice, or next tasks.
- Event-driven loop: planner yields after dispatch and resumes only on callback, blocker, or user update; no empty polling.
- Failure is a callback: executor reports exact failure facts and stops; planner redeploys or escalates.
- Reflection: lightweight after every callback; deep every 3 accepted callbacks and after any failed or misaligned callback, against the user-confirmed reference base copied into recursive prompts.
- Verification is role-specific: executor runs slice checks; planner audits diff/scope/evidence and avoids duplicate reruns unless a distinct risk requires them.
- Config: use only `thinking: xhigh` or `thinking: high`; do not invent model/tool/runtime values; do not change runtime config unless explicitly allowed, sourced, and verified.
- Closure: executor green is not accepted closure; planner rechecks target lock, diff/status, docs/prompts/guards, verification, and audit log before the next dispatch.

You are the executor for one bounded read-only Phase 0A slice in `/home/pingfan/PACT/excavator_testbed`.
Do not choose the next task or advise the planner. Execute only this slice and
return factual callback details to the controlling planner thread.

Target lock:
- cwd: `/home/pingfan/PACT/excavator_testbed`
- branch: `tx/oracle-terrain-residual-planner-v0`
- expected HEAD: refresh with `git rev-parse HEAD` immediately before dispatch
- expected dirty state: clean before dispatch
- upstream note: local branch may still track `origin/tx/v2_6-llm-planner`; do not push or change upstream
- stop if cwd, branch, HEAD, or dirty state mismatches

Confirmed reference base:
- `AGENTS.md`
- `/home/pingfan/.codex/skills/closed-loop-planner-executor/SKILL.md`
- `docs/oracle_terrain_residual_planner_closed_loop_profile.md`
- `docs/llm_planner_closed_loop_terrain_conclusion.md`
- `docs/oracle_terrain_residual_planner_v0_plan.md`
- `docs/planner_to_act_conceptual_contract.md`
- `docs/data_processing_hdf5_qc_contract.md`
- `docs/training_setup.md`

User objective:
- Before connecting an LLM planner, prove whether a numerical terrain residual
  planner can make a target pit shape converge over multiple excavation cycles
  under simulation ground-truth terrain and bucket-aware tolerance.

Slice:
- Phase 0A: terrain/depth metric provenance and baseline gap audit.
- This is read-only. Do not edit files.

In scope:
- Identify current terrain/depth fields available to rollout review.
- Trace local-surface command-depth and summary plane-depth provenance.
- Check whether current code exposes a removed-depth or height-grid source
  suitable for Phase 0 residual metrics.
- Identify current run artifacts under `runs/eval/` only if present locally.
- Report minimal factual gaps for Phase 0 implementation.

Out of scope:
- No code edits.
- No new files.
- No config changes.
- No runtime gate behavior changes.
- No candidate planner, effect model, capability model, or LLM/VLM work.
- No branch/upstream/fetch/pull/push/reset/checkout/rebase.

Behavior contracts to preserve:
- Current rollout review remains diagnostic only and must not change eval
  success semantics.
- Local-surface command-depth tracking and summary plane-depth diagnostics stay
  separate.
- Return handoff review must ignore terminal-only incomplete return segments
  when completed `return -> dig` transitions are available.
- Public token dimensions/order, checkpoint contracts, and production planner
  behavior remain unchanged.

Configuration constraints:
- Runtime config changes allowed: no.
- Use only the prompt-level `thinking: xhigh` label.
- Do not invent model, tool, CLI, env var, branch, test, feature flag, schema,
  credential, port, or dependency values.

Verification:
- Executor must run:
  - `pwd`
  - `git status --short --branch`
  - `git rev-parse HEAD`
  - focused `rg`/read-only source checks needed for provenance
  - `python -m pytest -q tests/test_rollout_review.py`
  - `git diff --check`
- If a command is unavailable, report the exact failure and the closest
  meaningful read-only check.

Callback schema:
- Status: success | partial | failed
- Target lock observed:
- Callback route used:
- TDD red:
- Skill compliance block observed:
  - target lock first:
  - fact-only callback:
  - reference base copied:
  - config discipline:
  - responsibility scope:
- Files changed:
- Config touched: none | read-only | changed
- Config values used or changed:
  - value:
  - source verified from:
  - verification command:
- Terrain/depth provenance found:
- Missing Phase 0 facts:
- Current rollout artifacts found:
- What was verified:
- Behavior preserved:
- Failure facts, if partial/failed:
  - exact command/action that failed:
  - error text or failing assertion:
  - likely failing area, if directly evidenced:
  - partial changes left in worktree:
  - checks not run and why:
- Unknowns/blockers:
- Diff/status summary:
- HEAD after:

Forbidden in callback:
- Strategic advice to the planner.
- Next-task instructions.
- Broad architecture recommendations.
- Claims not backed by files, diffs, tests, or logs.
```
