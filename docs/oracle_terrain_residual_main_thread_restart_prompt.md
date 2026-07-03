# Oracle Terrain Residual Planner Main-Thread Restart Prompt

This document is the startup prompt and handoff packet for the next ordinary
Codex development thread. It replaces the previous planner/executor thread
workflow for this effort.

## Operating Mode

Do not continue the previous planner/executor callback loop.

The new thread is the single main development thread. It should inspect,
implement, run, analyze, document, and commit local work directly in the repo
when the work is accepted. Do not create executor threads, do not wait for
callbacks, and do not use subagents unless the user explicitly re-approves that
workflow later.

User-facing replies should be in Chinese by default. Repository documentation
may follow the surrounding language and can use English where the nearby docs
already do.

## Target Lock At Handoff

Repository:

```text
/home/pingfan/PACT/excavator_testbed
```

Branch:

```text
tx/oracle-terrain-residual-planner-v0
```

State before this restart document was added:

```text
## tx/oracle-terrain-residual-planner-v0...origin/tx/v2_6-llm-planner [ahead 65]
211d492a3112400d60dfcf681b0370435d646519
211d492 docs: record residual envelope compatibility blocker
```

The restart document itself may be committed after that SHA. If the latest
commit is a docs-only restart handoff commit, treat it as part of the accepted
handoff baseline and verify the current `git status --short --branch` and
`git rev-parse HEAD` before doing any work.

Keep all work local unless the user explicitly asks to push or publish.

## Repository Rules To Preserve

Follow `AGENTS.md` in the repo root:

- Code changes require the closest source-of-truth documentation update.
- New behavior and bug fixes require TDD or an explicit existing failing
  evidence path before implementation.
- Python files with 1000 or more lines may receive only thin facade,
  pass-through, adapter, deletion, or small bug-fix edits. New semantic logic
  belongs in a focused owner.
- Do not decide official planner, training, rollout, token, checkpoint, or
  config semantics from assumptions.
- Do not change checked-in eval YAML/default config, production defaults, gate
  thresholds, target-cycle semantics, coverage-count semantics, fallback
  behavior, or prior promotion unless the evidence and user intent are explicit.
- Do not run destructive git operations. Do not fetch, pull, push, reset,
  checkout, rebase, stage, or commit unless it is part of local accepted work in
  this repo. If committing, first inspect `git status` and diff scope.

## Source-Of-Truth Documents

Read these before changing behavior:

- `docs/llm_planner_closed_loop_terrain_conclusion.md`
- `docs/oracle_terrain_residual_planner_v0_plan.md`
- `docs/oracle_terrain_residual_planner_closed_loop_log.md`
- `docs/oracle_terrain_residual_planner_closed_loop_profile.md`
- `docs/training_setup.md`
- `docs/planner_to_act_conceptual_contract.md`
- `docs/oracle_terrain_residual_baseline_report.md` only when durable
  comparison facts change.

The most recent accepted workflow facts are in the Phase 6G-Q and Phase 6G-R
sections of `docs/oracle_terrain_residual_planner_closed_loop_log.md`.

## Original Development Objective

The objective is still real closed-loop A/B/C comparison evidence for the
oracle terrain residual planner:

- A: current planner baseline.
- B: heuristic residual pipeline using explicit residual cut-intent runtime
  source.
- C: calibrated/gold-sample branch when the required gold sample calibration
  evidence exists.

The desired outcome is not just infrastructure or scaffolding. The work should
produce real closed-loop evidence that shows whether residual planning improves
over A, and whether calibrated C improves over B. If B or C does not improve,
the result should narrow the reason with artifact-backed evidence.

## Progress Summary

Overall status estimate at handoff:

- Planning/docs/manifest/eval artifact framework: mostly complete.
- B-branch residual runtime plumbing: mostly complete.
- B-branch real gate-2 smoke: reaches return but has not completed return
  handoff.
- Full A/B/C comparison evidence: incomplete.
- Overall objective: roughly halfway complete; the main open blocker is the B
  branch return handoff under real smoke conditions.

## Completed Work

### Baseline framing

- The original conclusion document established that the next step is terrain
  residual closed-loop planning, not directly integrating an LLM planner.
- The v0 plan defines payload-vs-shape framing and the Phase 6 A/B/C evidence
  target.
- Phase 0 through Phase 6E created the offline evidence chain, predicted
  residual artifacts, manifest shape, A/B/C branch plan scaffolding, and request
  contracts.

### Real bounded A/B smoke infrastructure

- Phase 6G-F/G created request-local B branch eval config generation and fixed
  bounded smoke stop timing by setting terminal hold to `0` in request-local
  configs.
- Phase 6G-H produced bounded one-cycle A/B smoke comparison evidence. C
  remained `not_evaluated` / `blocked_by_missing_gold_samples`.
- Phase 6G-I produced a gate-2 A/B smoke: A completed the bounded gate; B ran
  but failed the gate and exposed real residual branch blockers.

### Residual runtime source and return target path

- Phase 6G-K implemented residual return-target planning for
  `dig_cut_planner.mode=residual_cut_intent`.
- Return target planning now consumes only an explicit
  `residual_cut_intent_return_target_plan_provider`.
- Active dig still uses exact current-cycle lookup.
- Return target uses `cycle_index + 1` lookup from the same explicit
  request-local residual source.
- Missing provider/source remains diagnostic and does not become hidden success.
- This removed the post-dump `return_target_token_source=fallback_zero` blocker.

### Return-start envelope and residual return target mapping

- Phase 6G-L maps residual return-target raw entry fields to the nearest
  available coverage corridor before selecting a cell-conditioned
  `return_start_envelope_tokens_v1` prior.
- Missing coverage prior/corridors still degrades to the existing diagnostic
  live-current-observation path; it does not relax handoff gates.
- B reached return with explicit residual return target and QC6 envelope prior,
  but still timed out.

### Source-token hypotheses ruled out

- Phase 6G-M/N showed near-origin return target / relocate tokens came from
  request-local residual-grid source inputs, not from runtime fallback.
- Phase 6G-O showed globally replacing all source cycles with corridor-shaped
  geometry changes active dig and stops before return.
- Phase 6G-P created a mixed source: cycle `0` preserved original active dig,
  while cycles `1` / `2` supplied corridor-conditioned next-cycle return target
  / relocate tokens. B reached return and used nonzero corridor-conditioned
  return target / relocate tokens, but return handoff still timed out.

### Return trajectory and envelope compatibility diagnostics

- Phase 6G-Q compared 6G-P against the working 2026-06-16 return handoff.
- Source fallback, near-origin return target / relocate tokens, and handoff
  reporting were cleared as first blockers.
- 6G-P failed `local_depth_m`, `plane_depth_m`, `dig_contact`, and `qpos_3`
  through all return rows.
- Phase 6G-R confirmed the selected 6G-P envelope source
  `qc6_return_start_envelope_cell_0+relocate_spatial_linear+relocate_qpos_linear`
  is consistent with the current nearest-entry rule. There is no evidenced
  cell-selection or reporting bug.
- The first directly evidenced blocker is now artifact/config-level:
  `testbed/configs/planner_priors/yulong_removed_depth_dig_cut_prior_v3.json`
  cell `0` asks for local/plane depth and contact that residual B never reaches
  in the 6G-P return trajectory.

## Key Current Evidence

### Current B failure after source/token fixes

6G-P mixed-source smoke facts:

- Artifact root:
  `runs/eval/oracle_terrain_residual_phase6g_p_real_b_smoke_20260703_r1/heuristic_residual_pipeline/results`
- Mixed source:
  `runs/eval/oracle_terrain_residual_phase6g_p_mixed_source_probe_20260703_r1/results/residual_cut_intent_runtime_source.json`
- Request-local config:
  `runs/eval/oracle_terrain_residual_phase6g_p_b_branch_request_20260703_r1/heuristic_residual_pipeline_eval_config_with_qc6_prior.yaml`
- Skill counts: bootstrap `267`, dig `144`, carry `139`, dump `152`,
  return `420`.
- Return target source:
  `conditioned_return_explicit_residual_cut_intent_dig_cut_token`.
- Return start envelope source:
  `qc6_return_start_envelope_cell_0+relocate_spatial_linear+relocate_qpos_linear`.
- `completed_transition_count=0`.
- `transition_timeout_count=1`.
- `entry_close_count=0`.
- `envelope_ready_count=0`.
- Min-entry row around `t=1119`:
  `return_to_dig_entry_error_m ~= 0.572m`, failed checks include
  `dig_contact`, `local_depth_m`, `plane_depth_m`, `qpos_3`.

### 6G-R prior compatibility evidence

6G-R diagnostic artifact:

```text
runs/eval/oracle_terrain_residual_phase6g_r_envelope_compatibility_diagnostic_20260703/phase6g_r_envelope_compatibility_analysis.json
```

Important facts:

- 6G-P mixed cycle `1` raw entry `(0.8955, -0.952)` exactly maps to checked-in
  prior cell `0`.
- 6G-P checked-in prior:
  `testbed/configs/planner_priors/yulong_removed_depth_dig_cut_prior_v3.json`.
- Cell `0` has no `dig_start_local_depth_m` summary.
- Cell `0` generates local-depth lower bound about `0.239792m`.
- Cell `0` has `dig_start_plane_depth_m.p50=0.585981`.
- Contact is active through token index `6=1.0`; config also requires contact.
- 6G-P dump-end and all return rows keep local depth `0.0`, plane depth `0.0`,
  and contact `0.0`.

Working comparison:

- Working run:
  `runs/eval/planner_compare_20260616_x99/refactored_fsm/results`
- Working prior:
  `runs/jobs/yulong_v2_4_5_surface_depth_replay_train_eval_20260523/planner_prior_v2_4_5_surface_depth_tight_dump_qc6labels_scale080_20260524_next_entry_cells.json`
- Working transition row uses cell `1`, not cell `0`.
- Working prior cell `1` has shallow local-depth stats:
  `p05=0.00601`, `p50=0.011339`, `p95=0.021112`.
- Working prior cell `1` has plane-depth `p05=0.0`, `p50=0.056943`,
  `p95=0.253921`.
- Working transition passed with
  `return_to_dig_entry_error_m=0.09901039892653803`,
  `return_to_dig_start_envelope_error=0.0`, `dig_contact=1.0`, and no failed
  checks.

## Known Bad Workflow State To Ignore

Ignore old active/superseded planner/executor threads. The previous
planner/executor workflow caused thread confusion where executor threads began
doing planner work or failed to callback.

Do not continue or recover these as workflow authorities:

- old planner handoff chains from `019f1d55-*`
- 6G-Q/R/S executor thread chain
- any thread titled `EXECUTOR ACTIVE ...` from the previous workflow

If useful for archaeology, their final facts are already reflected in
`docs/oracle_terrain_residual_planner_closed_loop_log.md` and this restart
document. Treat repository docs and run artifacts as source of truth.

## Remaining Work

### Immediate next step: Phase 6G-S prior-path counterfactual

Run this in the new main thread, not in a delegated executor.

Goal:

- Preserve the 6G-P mixed source and all return/gate settings.
- Change only request-local `policy.dig_cut_planner.prior_path` to the existing
  working surface-depth prior:

```text
runs/jobs/yulong_v2_4_5_surface_depth_replay_train_eval_20260523/planner_prior_v2_4_5_surface_depth_tight_dump_qc6labels_scale080_20260524_next_entry_cells.json
```

Suggested fresh roots:

```text
runs/eval/oracle_terrain_residual_phase6g_s_surface_prior_counterfactual_20260703
runs/eval/oracle_terrain_residual_phase6g_s_real_b_smoke_20260703/heuristic_residual_pipeline
```

If a root already exists, choose a suffixed fresh root and do not overwrite.

Required checks:

1. Verify current target lock.
2. Verify 6G-P request-local config values:
   - mixed source path
   - target gate `2`
   - terminal hold `0`
   - return target planner enabled
   - return-start envelope gate settings
   - current prior path
3. Copy the 6G-P request-local config into the fresh root and change only
   `policy.dig_cut_planner.prior_path`.
4. Write a small request-local provenance JSON.
5. Run:

```bash
python testbed/cli/eval.py \
  --config <surface-prior-overlay-config> \
  --num-rollouts 1 \
  --target-cycle-gate 2 \
  --output-dir <fresh smoke root> \
  --no-video
```

6. Analyze rollout rows and summary:
   - row count
   - skill counts
   - dump/carry/return presence
   - selected return-start envelope source/cell
   - return target / relocate sources and tokens
   - first return, min-entry, min-envelope, and last return rows
   - local-depth / plane-depth / contact / qpos failures
   - transition counts and gate success fields
   - recursive file count
7. Validate any generated JSON with `jq empty`.
8. Run `git diff --check`.

Expected interpretation:

- If B completes return handoff, the prior artifact is a leading blocker.
  Do not automatically promote the working prior to a checked-in default; first
  decide whether to regenerate/promote a residual-compatible surface-depth
  prior.
- If B still fails, inspect whether the selected cell changed and which checks
  remain failed. The next likely owner is return ACT reachability from residual
  dump-exit state, not source-token construction.

### After 6G-S

Depending on 6G-S:

- If the prior counterfactual succeeds:
  - Record the evidence in docs.
  - Decide whether to rebuild a residual-compatible prior or wire a
    request-scoped prior selection policy.
  - Keep checked-in default promotion separate and user-confirmed.
  - Rerun bounded B and then bounded A/B comparison.
- If it fails:
  - Compare selected source/cell/check failures against 6G-P and working run.
  - Decide whether return ACT cannot reach the target from residual B dump-exit
    state, or whether dump/return state itself must be changed.
  - Avoid further residual source variants unless directly proven necessary.

### A/B/C comparison still open

After B can complete the bounded gate:

1. Run a fresh bounded A/B comparison at the same target gate and stop
   semantics.
2. Confirm whether B improves over A on residual terrain metrics and not just
   stop reason.
3. C remains blocked unless gold-sample calibration/effect evidence is available.
4. Update `docs/oracle_terrain_residual_baseline_report.md` only when durable
   comparison facts change.

## Non-Goals

Do not do these without explicit user confirmation:

- Continue the planner/executor callback workflow.
- Open more executor threads.
- Promote any request-local config/prior to checked-in default.
- Replace or regenerate checked-in priors as an assumed official semantic.
- Relax return handoff thresholds or disable entry/contact/depth/qpos/envelope
  checks.
- Add hidden fallback, source repetition, last-plan reuse, fallback success, or
  calibrated fallback.
- Change target-cycle/count semantics or coverage-count semantics.
- Claim official pass/fail, eval success, planner success, production
  readiness, or full Phase 6 success from bounded smoke evidence alone.

## Verification Commands To Prefer

For doc-only work:

```bash
python scripts/planner_architecture_doc_guard.py --check-changed-docs <docs...>
python scripts/planner_architecture_doc_guard.py --check-doc-inventory
python scripts/planner_architecture_doc_guard.py --check-architecture-contract
git diff --check
```

For generated JSON:

```bash
jq empty <artifact.json>
```

For focused Python code changes:

- Use TDD when changing behavior.
- Run the focused pytest files named by the owner area.
- Run `python -m compileall -q <touched python files>`.
- Run doc guards and `git diff --check`.

## Startup Instruction For The New Thread

Start by reading this document and the source-of-truth docs named above. Then
verify the current branch/status/HEAD and run the 6G-S prior-path
counterfactual directly in the main thread. Do not create executor threads or
wait for callbacks.
