---
name: closed-loop-planner-executor
description: >-
  Use when Codex needs a closed-loop planner/executor workflow for complex,
  long-running, high-risk, multi-stage, dirty-worktree, remote-repo, research,
  or refactor tasks prone to context drift. Use when one thread must own target
  lock, scope, recovery, closure, reflection, confirmed reference-base
  standards, and next-slice prompts while an executor performs bounded slices
  and returns factual callbacks. Require hard rules and the confirmed reference
  base in every recursive prompt.
---

# Closed Loop Planner Executor

## Core idea

Separate control from execution. The planner owns goals, boundaries, target lock, sequencing, reflection, and the next prompt. The executor owns one bounded slice and returns facts only.

The loop must optimize for solving the user's problem, not for preserving the
current code by default. The planner should actively question whether existing
code is necessary, whether the slice is large enough to remove real coupling,
and whether the current verification plan duplicates work without reducing
risk.

This is not ordinary delegation. It is a recursive loop:

1. Planner locks the target and writes a bounded executor prompt.
2. Executor performs exactly that slice and returns a factual callback.
3. Planner wakes on callback, audits the facts, syncs durable docs/prompts, reflects on drift, then dispatches the next slice or stops.

## Progress discipline

Closed loop does not mean conservative drift. The planner must keep pressure on
outcome, throughput, and necessary change.

- Treat current code as evidence, not as a protected artifact. Ask what must
  survive because of user value, public contract, or verified behavior.
- Prefer the smallest core slice that actually solves the current architectural
  or product problem over defensive micro-slices that mainly preserve old glue.
- The planner owns work allocation. It should bundle tightly coupled work that
  shares setup and verification, and split only when ownership, risk, or
  verification differs.
- Communication is overhead. Prompts, callbacks, and audits should be just
  detailed enough to prevent drift and unblock execution.
- Verification roles should differ: executor proves the assigned slice; planner
  audits scope, evidence quality, unexpected diff, and only reruns tests when
  checking a different risk or distrusting the callback facts.
- If two consecutive callbacks mainly add process, docs, or repeated checks
  without reducing risk or moving code/artifacts, run deep reflection and
  either change the slice shape or stop.

## Event-driven rule

Treat the workflow as a callback-driven state machine, not as an always-running goal loop.

- After dispatching an executor slice, the planner should stop, sleep, archive, or otherwise yield until the executor callback or handoff artifact exists.
- Do not keep the planner alive just to poll for executor completion, restate current state, or speculate about the next step without new facts.
- If thread callback, automation, or wakeup tools are available, use them to resume the planner only when the executor reports completion or a blocker.
- If no callback mechanism is available, leave the next executor prompt and explicit pending state, then stop; the next planner turn resumes from the callback or user-provided result.
- Use goal-like long-running state only for the controlling planner's durable objective and discipline checks, not for continuous empty execution.

## Hard-rule restatement

Do not rely on inherited chat context to preserve workflow discipline. Every planner/executor thread prompt or continuation must restate the hard rules near the top.

- For executor handoffs, put the `thinking: xhigh` or `thinking: high` line first, then the hard-rule block.
- For planner resumes, callback audits, recovery prompts, doc-sync prompts, or context-compaction restarts, put the hard-rule block before task details.
- Preserve the hard-rule block under token pressure. Compress history, examples, or explanation before dropping hard rules.
- Keep the block compact and stable. Project replay profiles may append project-specific hard rules, but must not remove the generic rules.
- If a prompt is missing or weakens the hard-rule block, hold dispatch and rewrite the prompt before any executor starts.

Canonical hard-rule block:

```markdown
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
```

## Configuration discipline

Prevent long-horizon configuration hallucinations. The planner must write explicit, verified configuration intent instead of inventing model, tool, or thinking-effort values.

- Every planner-to-executor prompt must start with one of these exact first lines:
  - `thinking: xhigh`
  - `thinking: high`
- Use `thinking: xhigh` for planning-heavy, architecture-sensitive, recovery, debugging, reflection, cross-file, or high-risk slices.
- Use `thinking: high` for bounded implementation slices when the handoff is already compact and the executor only needs careful execution.
- Do not write unverified values such as `thinking: max`, `maximum`, `ultra`, `auto`, or made-up model/config names.
- Treat `thinking: xhigh/high` as an explicit workflow label unless the current tool or repo documentation verifies it as an actual runtime configuration value.
- Treat all runtime configuration surfaces as risky until verified: model ids, reasoning flags, CLI flags, API parameters, tool/plugin/connector names, automation/thread ids, environment variables, proxy hosts/ports, repo paths, branches, HEADs, package versions, package-manager commands, test or CI job names, feature flags, schema keys, ports, credentials, auth scopes, and deployment targets.
- Default to no runtime configuration changes. Executors may read and report config, but must not edit config files, agent definitions, skill manifests, CI files, package manifests, environment variables, remotes, credentials, or deployment settings unless the slice explicitly allows it.
- If a real runtime config must be used or changed, verify allowed values from current local docs, repo config, checked-in examples, CLI help, current status commands, or official docs before writing it into files or commands.
- Record the verification source and command for every runtime config value used in a command or changed in a file.
- If verification is unavailable, keep runtime config unchanged and express only the prompt-level `thinking:` label.
- If a needed config value is missing or unverifiable, return a partial or failed callback with the missing value and verification attempt; do not invent a placeholder unless the repo already documents that exact placeholder.
- Do not choose dependency versions, config defaults, feature flags, ports, model names, or auth scopes by plausibility. Use existing project values or verified documentation.

## Executor failure channel

Treat executor failure as a callback event, not as a workflow stop.

- The executor must not wait, loop indefinitely, silently broaden scope, or ask the planner to solve the problem inside the executor thread.
- If the slice cannot be completed within the assigned scope, the executor must emit a failure callback with exact facts, close the executor turn, and avoid waiting for planner intervention.
- A failure callback is a valid handoff artifact. It wakes the planner and gives the planner enough information to redeploy, narrow, split, change verification, or update the target lock without treating the workflow as stopped.
- The planner owns recovery decisions. The executor may report local observations, but must not prescribe the next strategy unless explicitly asked.
- The planner should treat failure as new evidence, run immediate deep reflection against the reference set, and then dispatch a revised bounded slice, a diagnostic slice, or a user-facing escalation.
- Only ask the user when the planner lacks an external decision, permission, credential, or product requirement. Do not ask merely because an executor hit a normal implementation error.

## Reflection reference base

Before the first executor dispatch, establish the objective standards that
reflection must use. Do this as a task-start reference-base dialogue with the
user: ask what baseline, design, docs, artifacts, behavior contracts, or
accepted examples should be treated as the reference base. If the user already
provided them, restate the set and proceed; if the set is vague or missing,
propose a concrete candidate set and ask the user to confirm or correct it
before dispatch.

The reference base is not always project files. It may be architecture
diagrams, design docs, code-analysis docs, specs, tickets, datasets, logs,
tests, metrics, examples, user-written standards, or current artifacts. Project
profiles may list concrete files as examples, but the generic skill must not
hard-code one project's files as universal references.

Write the confirmed reference base into every recursive planner prompt,
executor prompt, callback-audit prompt, recovery prompt, and context-compaction
handoff. Preserve it under token pressure; compress history before dropping the
reference base. Do not accept a reflection that does not name what it is
comparing against.

Use the most concrete available references:

- User objective: the user's actual requested outcome, not the executor's local subgoal.
- Ideal target state: what the repo, artifact, behavior, or research corpus should look like when the loop is done.
- Non-goals: changes that must not be absorbed into the current loop.
- Target lock: cwd, branch, HEAD expectation, dirty state, ownership boundary, and stop conditions.
- Behavior contracts: public API, schema, trace shape, ordering, compatibility, performance, or domain constraints that must remain stable.
- Verification standard: exact tests, guards, logs, metrics, source checks, or deliverables that prove the slice.
- Source-of-truth docs/prompts: current plan, architecture notes, effect/boundary docs, rollout logs, or handoff prompt.
- Efficiency discipline: token, latency, model/thinking effort, and callback/pause behavior when those are part of the task.
- Configuration discipline: allowed `thinking:` label, no-runtime-config-change default, verified config values, verification sources, and explicit "do not invent config" constraints.

If the confirmed reference base becomes stale, contradictory, or too generic to
judge the next slice, hold dispatch and run another reference-base dialogue
with the user before continuing.

## Use when

- The task is too large for one thread to hold target selection, archaeology, implementation, verification, and review cleanly.
- There is wrong-repo, wrong-branch, dirty-worktree, or stale-history risk.
- The user wants bounded executor prompts and callback review rather than fire-and-forget subagents.
- The planner would otherwise waste tokens in Goal mode by waiting or polling while an executor is still running.
- Progress needs to preserve architecture intent, docs, prompts, guard checks, or phase logs across rounds.
- A smaller/faster executor model may be useful only after the planner has made the handoff compact and explicit.

Do not use this protocol for tiny one-file changes, quick conceptual answers, or tasks where one normal agent can inspect, edit, verify, and summarize without state drift.

## Role contract

### Planner thread

- Maintain the live goal, non-goals, current target lock, and stop conditions.
- Establish and preserve the user-confirmed reference base for reflection.
- Read rules, docs, prior callbacks, and current repo state before dispatching.
- Challenge the necessity of existing code before preserving it. Keep public
  contracts and verified behavior; do not protect private glue, duplication, or
  obsolete paths merely because they exist.
- Choose slice size deliberately. Combine tightly coupled changes that share
  one owner and one verification path; split only for distinct ownership, risk, or
  user decisions.
- Produce one executor prompt at a time.
- Put `thinking: xhigh` or `thinking: high` as the first non-empty line of every executor prompt, followed by the hard-rule block.
- Yield after dispatch and resume only when a callback, blocker, or user update provides new facts.
- Audit executor output before accepting progress.
- Decide the next slice; do not let the executor set strategy.
- Sync durable docs, prompts, logs, and guard expectations when workflow state changes.
- Run a lightweight reflection after every callback and a deep reflection every
  three accepted callbacks, both against the reflection reference set. Include
  an efficiency verdict: whether the loop is doing necessary work or mainly
  communicating, protecting, or repeating checks.

### Executor thread

- Execute only the assigned slice.
- Preserve behavior outside the stated scope.
- Verify with the requested checks, or report the exact blocker.
- Return a factual success, partial, or failure callback in the requested schema.
- Do not recommend strategy, assign tasks to the planner, broaden scope, rewrite the plan, or choose the next slice unless the planner explicitly asks.
- Do not compensate for a timid prompt by inventing wider scope. If the slice is
  too small to solve the problem, return that as a factual blocker.

## Planner workflow

1. Lock the target.
   Record cwd, repo, branch, HEAD, dirty state, owned files/area, expected verification, and stop conditions.

2. Read enough context.
   Prefer focused reads: repo rules, current plan docs, relevant code, latest callback, and active guard/test expectations. Treat old memory as historical until re-verified. If the task-start reference base is not confirmed, ask the user to confirm it before dispatch.

3. Size the work.
   Decide whether one executor should handle the slice or whether it should be
   split. Use a single executor when the work has one owner and one verification
   path. Split only when tasks are independent or a user decision separates
   them.

4. Write one executor prompt.
   Start with `thinking: xhigh` or `thinking: high`, include the hard-rule block, then include the confirmed reference base, target lock, config constraints, exact slice, allowed files/areas, non-goals, behavior contracts, required checks, and callback schema.

5. Dispatch one executor.
   Use one executor by default. Fan out only when slices are independent and target ownership cannot collide.

6. Yield until callback.
   Do not poll, re-summarize, or continue planning while waiting. The planner's next action requires new executor facts, a blocker, or a user update.

7. Audit the callback.
   Compare claimed changes against the target lock, scope, diff, tests, docs, and original goal. Reject or narrow the slice if facts are missing.

8. If the callback is failed or partial, convert it into a planner recovery action.
   Do not let the workflow block. Use the failure facts to redeploy with a narrower prompt, diagnostic slice, stronger model/thinking effort, updated verification, or a documented escalation.

9. Run per-callback reflection.
   Record a short verdict against the reflection reference set: still aligned, drifting, blocked, or reference update needed.

10. Sync durable state.
   Update the relevant docs, prompt files, plans, logs, or guard tests before the next round when the workflow state changed.

11. Run deep reflection when due.
   After every three accepted executor callbacks, or immediately after a failed/misaligned callback, compare the loop against the reference set and decide whether to change target, prompt, verification, model/thinking effort, or stop conditions.

12. Continue or stop.
   Dispatch the next bounded slice only after the audit, doc sync, and reflection gate are satisfied.

## Planner closure gate

Do not count an executor slice as accepted just because the executor reported green checks. The planner must close the loop in the controlling thread before dispatching another slice.

Run this closure gate after every callback:

- Recheck target lock: cwd, branch, HEAD or expected base, dirty state, owned files, and unexpected worktree changes.
- Inspect the executor diff/status enough to confirm the changed files and behavior claims.
- Confirm the callback is factual, scoped, and free of planner-directed strategy.
- Confirm the slice advanced the user objective with a necessary change, or
  explicitly record why preserving current behavior/code was the right result.
- Do not automatically rerun the executor's full verification bundle. Rerun or
  expand checks only when the planner is validating a different risk, sampling
  an untrusted callback, checking integration impact, or verifying docs/guards
  changed after executor completion.
- Sync source-of-truth docs, prompts, rollout logs, and guard expectations when the slice changed workflow or architecture state.
- Run planner-side verification after doc/prompt sync, not only executor-side tests.
- Record the accepted callback, local audit result, verification result, and next bounded target in the rollout/reflection log.
- Dispatch the next executor only after this closure gate is complete.

If the closure gate fails, turn the facts into a recovery prompt, diagnostic slice, doc-sync slice, or hold-and-replan state.

## Project replay profiles

Use a project replay profile when a long-running workflow needs repeatable local conventions. Keep the core protocol generic; put project-specific paths, docs, tests, and callback routes into a small profile. Treat every profile as historical until re-verified in the live workspace.

Profile fields:

- Target aliases: repo names, remote hosts, worktrees, or thread names that may be confused.
- Target lock: cwd, branch, expected base, dirty-state rule, ownership boundary, and stop conditions.
- Source-of-truth artifacts: plan docs, architecture docs, prompts, logs, manifests, dashboards, datasets, or tickets.
- Verification bundle: tests, guards, linters, compilers, source checks, metrics, or render checks that close the planner loop.
- Callback route: where executor success, partial, or failure facts must be returned.
- Closure rule: what the planner must recheck before dispatching another executor.
- Config constraints: allowed prompt labels, runtime config defaults, verified values, and forbidden invented values.
- Project-specific non-goals: tempting work that must not be silently absorbed into the current loop.

Generic replay rule:

- executor green is not closure;
- callback facts must return to the planner;
- planner rechecks target lock, diff/status, and callback scope;
- planner syncs source-of-truth artifacts when state changed;
- planner runs only the profile checks needed for closure risk, sampling or
  auditing executor evidence instead of duplicating the same full bundle by
  default;
- planner records audit/reflection and only then issues the next `thinking: xhigh/high` executor prompt with the hard-rule block restated.

Example profile: pingfan `excavator_testbed`

Use only when the target is the observed `/home/pingfan/PACT/excavator_testbed` planner-refactor workflow.

- cwd: `/home/pingfan/PACT/excavator_testbed`
- branch: verify live; `fs/v2_4-refactor-tests` appeared in the recorded workflow
- source-of-truth examples: `docs/planner_current_code_architecture_plan.md`, `docs/planner_effect_boundary_design.md`, `docs/planner_primitive_interface_standard.md`, `docs/planner_rollout_evidence_refactor_plan.md`, `docs/planner_rollout_evidence_refactor_log.md`, `docs/prompts/planner_rollout_evidence_goal_prompt.md`
- verification examples: focused pytest targets, selected AGX/integration tests when relevant, `python -m compileall ...`, `python scripts/planner_refactor_guard.py --check-plan-contract`, `python scripts/planner_refactor_guard.py --check-skill-contract`, `git diff --check`
- replay caution: paths, branch names, phase numbers, HEADs, and ahead counts from memory are stale until rechecked live

## Reflection cadence

Use two different reflection strengths.

Per-callback reflection is lightweight and required after every executor callback. Keep it short:

- Reference used: name the user objective, target lock, behavior contract, verification standard, or source-of-truth doc being checked.
- Alignment verdict: say whether this slice advanced the ideal target, stayed neutral, drifted, or exposed a blocker.
- Next-slice implication: continue as planned, narrow scope, update docs/prompts, rerun verification, or stop.

Three-callback deep reflection is heavier and required after every three accepted executor callbacks, and after any failed or misaligned callback. Check:

- Whether the loop still serves the user's original objective and ideal target state.
- Whether the non-goals, behavior contracts, and ownership boundary still hold.
- Whether verification is proving the right thing or merely proving local green checks.
- Whether docs/prompts/guards are stale compared with actual code or artifacts.
- Whether executor slices are too broad, too small, too doc-heavy, or too implementation-heavy.
- Whether the event-driven pause/callback discipline is still saving context rather than adding ritual.
- Whether model choice or thinking effort should change for the next slice.

If the reference set is missing, stale, or vague, update it before dispatching another executor.

## Executor prompt template

Use this shape when creating an executor handoff:

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

You are the executor for one bounded slice. Do not choose the next task or advise the planner.

Target lock:
- cwd:
- repo/branch/HEAD:
- dirty state:
- owned files/areas:
- stop if:

Slice:
- Goal:
- Why this slice size is right:
- In scope:
- Out of scope:
- Behavior contracts to preserve:

Reflection references:
- Confirmed reference base:
- User confirmation source or correction:
- User objective:
- Ideal target state:
- Verification standard:
- Source-of-truth docs/prompts:

Configuration constraints:
- Runtime config changes allowed: no, unless explicitly listed here
- Verified config sources:
- Values that must not be invented:

Required context:
- Read:
- Treat as source of truth:

Implementation rules:
- Make the smallest coherent change that satisfies the slice.
- Do not refactor unrelated code.
- Do not edit docs unless explicitly listed in scope.
- Do not change public schema, trace shape, ordering, or external behavior unless explicitly requested.
- Do not invent model, tool, CLI, API, env var, proxy, version, path, branch, CI/test, feature flag, schema, credential, port, or thinking-effort config values.
- Use only verified runtime values, report their source, and keep this prompt-level `thinking:` line unchanged.
- Do not edit runtime config unless the slice explicitly lists the config file/value and verification source.

Verification:
- Executor must run:
- Planner will later audit/check:
- Do not duplicate:
- If unavailable, report why and run the closest meaningful check.

Callback schema:
- Status: success | partial | failed
- Target lock observed:
- Files changed:
- Config touched: none | read-only | changed
- Config values used or changed:
  - value:
  - source verified from:
  - verification command:
- What changed:
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

Forbidden in callback:
- Strategic advice to the planner
- Next-task instructions
- Broad architecture recommendations
- Claims not backed by files, diffs, tests, or logs
- Waiting for the planner instead of returning failure facts
```

## Planner audit checklist

Before accepting an executor callback, verify:

- Target lock still matches cwd, branch, HEAD expectation, dirty state, and owned area.
- Executor prompt began with exactly `thinking: xhigh` or `thinking: high`.
- The prompt included the hard-rule block without deleting role boundary, event-driven, failure-channel, reflection, config, or closure rules.
- Runtime config was not changed unless the slice explicitly allowed it.
- Any runtime config value used in commands or files has a verification source and command.
- Changed files are allowed by the prompt.
- The executor did not broaden scope or modify unrelated docs/code.
- Required tests or guards passed, or the failure facts are concrete enough for planner redeployment.
- The callback states facts rather than advice.
- The callback did not merely protect current code without evidence that the old
  code is necessary.
- Planner-side verification is differentiated from executor verification, or the
  reason for rerunning the same checks is explicit.
- Failed or partial callbacks are converted into a revised bounded slice, diagnostic slice, or explicit escalation.
- Per-callback reflection names at least one objective reference and gives an alignment verdict.
- Per-callback reflection includes an efficiency verdict: useful progress,
  necessary audit, duplicated verification, over-communication, or timid slice.
- Planner closure gate was run in the controlling thread before the next dispatch.
- Durable docs/prompts are synced if the slice changed workflow state or source-of-truth architecture notes.
- The next slice can be expressed in one bounded prompt.
- The planner did not spend a waiting round polling or guessing without new callback facts.

## Handoff artifacts

Keep handoff artifacts compact and stable. Prefer a small set of live files over long chat history:

- Current goal prompt: what the loop is trying to accomplish, non-goals, and thinking-effort rule.
- Hard-rule block: compact canonical rules copied into every planner/executor prompt, continuation, recovery prompt, and callback-audit prompt.
- Confirmed reference base: task-start user-confirmed baseline, design/docs/artifacts, behavior contracts, verification standard, and source-of-truth prompts to preserve in every recursive prompt.
- Configuration rule: allowed `thinking:` prompt labels, no-runtime-config-change default, verified values, verification commands, and forbidden invented values.
- Current architecture/plan doc: source-of-truth state and next bounded order.
- Effect/boundary doc: what behavior/schema/trace contracts cannot change.
- Rollout/reflection log: accepted callbacks, audit conclusions, stale assumptions, and next slice.
- Failure log: failed/partial callback facts, planner diagnosis, and redeployment decision.
- Pending-state note: executor slice dispatched, callback expected, planner paused until facts arrive.
- Guard/test file: checks that fail if required workflow rules disappear.

## Hold-and-replan conditions

Hold dispatch and re-plan before sending another executor when:

- Target lock does not match.
- The worktree contains unexpected changes in the executor's owned area.
- The executor changed out-of-scope files or returned advice instead of facts.
- Required verification is missing and no concrete failure facts are given.
- The next prompt omits the hard-rule block or drops any generic hard rule under context/token pressure.
- The planner has not confirmed the task-start reference base with the user, or cannot name the objective reference or ideal target that reflection should use.
- The planner cannot choose a valid prompt-level `thinking:` label or is about to invent an unverified config value.
- A runtime config change is needed but not explicitly allowed, sourced, and verifiable.
- The only available planner action would be polling for an executor that has not reported back.
- The planner cannot explain the next slice in one bounded prompt.
- Reflection shows the loop is optimizing local cleanup while drifting from the user's goal.

## Output shape

When reporting this workflow to the user, keep it short:

1. Target lock
2. Current accepted callback or finding
3. Audit result
4. Reflection result, if due
5. Next bounded executor prompt, recovery action, or stop reason
