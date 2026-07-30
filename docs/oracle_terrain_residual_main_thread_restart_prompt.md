# Oracle Terrain Residual Planner Main-Thread Restart Prompt

This document is the startup prompt and handoff packet for the next ordinary
Codex development thread. It replaces the previous planner/executor thread
workflow for this effort.

> **2026-07-31 superseding handoff:** the active mainline is
> `exact diagnostic → contact audit/A-B → Unity wall+FactoryFloor diagnostic
> → return-handoff/action diagnostic → return-handoff owner isolation
> → contact-budget freeze
> → continuous predictor → E0/G1/W1 → bounded live
> → conditional 1×10`.
> The contact audit/A-B stage has finished and is now paused for human review.
> Geometry covered 433 paths; all 18 recorded-action source replays completed,
> but all `379 train + 61 holdout` dig windows were fairness-invalid and none
> may drive production inference. The six immutable paired attempts produced
> B carry+dump on seeds 0/1 and a repeat-session hard stop on seed 2, so the
> source-locked append-only `reanalysis_v4` classification is `inconclusive`.
> It is a zero-execution postprocess of the original attempts. Production
> bucket region and force/duration/impulse budgets are not frozen. Do not
> implement the qpos predictor, modify the continuous contact contract, or run
> E0/G1/W1, bounded live, or 1×10 until the user explicitly reviews and freezes
> those contact semantics.
>
> One separately authorized B2 diagnostic then reran **seed 2 exactly once**.
> Its only semantic delta was `session_end_clear_ticks=2`: one 20ms clear
> observation remains inside the same logical bucket-wall session. The source
> reset, target, checkpoint set, ACT settings, timeout, and hard thresholds
> remained locked. Physical contact at step 625 and steps 627..689 was
> bucket-only on the same `Dig_ZMin_Board`, with step 626 as the sole clear
> observation. B2 merged those physical sessions, entered carry, completed
> dump, and had no hard-stop violation. The outcome is
> `single_clear_tick_split_supported`.
>
> A later, separately authorized current-code diagnostic ran **one fresh
> seed-1000 rollout and no retry**, with a maximum of ten shovels. It used the
> historical seven-dump Strict-18 resolved config/reset/checkpoint lineage but
> did not resume cycle 8. Its only ordinary wall-contact semantic change made
> finite, strictly sub-100kN bucket contact record-only across arbitrary
> sessions, durations, bucket regions, and wall identities. Such contact could
> not request neutral, reset ACT, replan, or block a corridor; boom/stick/other,
> data anomalies, high force, hard-bottom, stuck, and timeout remained hard
> stops.
>
> That sole rollout completed six dumps and stopped safely during shovel 7 on
> `hard_bottom_depth_budget_guard_clearance_depth_increase`. Zero-based report
> shovel index 1 (the second shovel) contained 12 physical bucket ×
> `Dig_ZMin_Board` sessions over 21 contact ticks and 0.42s, with normal
> peak/RMS `73924.76/43681.23N`, normal impulse
> `15555.178944N·s`, and observed motion progress. All 21 allowed ticks had zero
> neutral, ACT-reset, replan, and corridor-block side effects. Report status was
> `passed`, outcome `hard_safety_stop_before_10`; no HDF5 was written.
>
> The later Unity-only wall+FactoryFloor investigation invalidated its first
> apparent high-force result: v2/v4 were launched with `-nographics`, so ACT
> consumed Null-renderer frozen gray camera frames. Unity now rejects a
> supports-images GET_INFO/capture with
> `recording_camera_graphics_device_unavailable` when the graphics device is
> Null. v5 used a real GPU but had an extra preflight RESET; v6 ended in an
> FMOD native crash. The final valid v7 used RTX 5070 Ti, exactly one RESET,
> and matched the frozen A0 reset on every fairness metric. It completed seven
> dumps and ended on the unchanged timeout chain. Shovel 6 had one 68.353kN
> bucket-wall tick; shovel 7 had 3.98s bucket-wall contact peaking at 31.971kN
> and 3.20s bucket-FactoryFloor contact peaking at 61.433kN, with motion
> progress during both long contacts. No boom/stick/other, >=100kN, stuck, or
> data anomaly occurred.
>
> The original v7 failed report remains immutable. Append-only
> `run/report_reanalysis_v2.json` corrects only the JSONL ownership of a
> post-step contact immediately followed by an independent timeout
> zero→neutral→terminal chain; it reports `passed/timeout`, seven dumps, and
> valid reset fairness.
>
> The subsequent return-handoff audit found that extending timeout or widening
> qpos_1 was not supported: v7 ACT commanded boom farther down before contact
> and crossed the locked cell-0 upper bound. A diagnostic-only boom-axis
> limiter was therefore added without changing the envelope. v3 completed
> seven dumps but never exercised it because the config was incorrectly scoped
> to cell 0 while the fresh goal was cell 4. v4 exposed a wiring bug that used
> the bucket's current spatial cell instead of the locked return-goal cell and
> correctly failed closed. Both roots remain immutable evidence.
>
> The corrected no-overwrite v5 used the locked coverage return-goal identity.
> All 358 train handoffs across cells 0..5 support the in-envelope target. The
> live goal was cell 2; the controller intervened for 19 ticks, kept qpos_1
> below the unchanged `0.622343` upper bound, entered the eighth dig, and
> completed the eighth dump. Reset fairness passed, the eighth shovel had no
> wall/floor contact or hard violation, and no HDF5 was written. The generic
> report label `normal_completed_10` is historical; the manifest and stop
> reason prove this was an eight-dump gate, not a 1×10.
>
> A final two-part causal diagnostic then compared the immutable v7 step-3550
> failure against all 416 strict-18 return→dig boundaries and independently
> pulsed the Unity boom without ACT or terrain physics. No same-cell expert row
> jointly matched the cut intent, full 18D return envelope, qpos/qvel,
> local-depth gate, and required contact; ignoring contact still produced zero
> envelope+state matches. The locked envelope contact token is `0`, while
> runtime config forces `require_contact=true`. All five
> near-upper-band cell-0 expert examples continued negative boom action rather
> than braking. In Unity, full failure-posture-matched tests at boom qpos
> `0.42/0.52/0.62` produced the expected inverse command/qpos direction,
> max/min gain ratio `1.119953`, and zero external/wall/FactoryFloor contacts.
> The source-locked conclusion is therefore
> `return_handoff_contract_outside_expert_support`: Unity mapping is normal,
> and the evidence does not support an expert-brakes/ACT-does-not temporal
> failure. It does not yet choose a replacement production return contract.
>
> A target-scoped owner diagnostic has now answered that narrower question.
> Production-service replay of the immutable v7 segment showed that simply
> setting global `require_contact=false` also moved the plane-depth floor from
> prior p05 to p50, so the handoff still missed the pre-qpos window. Keeping
> depth on its original prior p05-p95 bounds and letting 18D token field 6 own
> contact made the offline gate ready at step 3554, before qpos_1 failed at
> step 3555.
>
> The first live attempt applied that change globally and is superseded because
> it perturbed earlier handoffs, took a cycle-3 carry release-safety path, and
> timed out after four dumps. The accepted v2 kept v7 semantics until seven
> completed dumps, then activated the diagnostic owner control. Reset fairness
> was exact. It entered the eighth dig at step 3475 with qpos_1
> `0.598779 < 0.648137`, completed the eighth `dump_end`, and stopped on the
> target-cycle gate with no safety violation. Use
> `return_handoff_owner_target_scoped_diagnostic_v2/run/report_reanalysis_v1.json`;
> the raw terminal generic dump counter is one tick stale at 7, while both
> `target_cycle_completed_dump_count` and `dump_end_count` are 8.
>
> Two later no-overwrite diagnostic roots extended that same request-local
> setup to a ten-dump target. Both resets were fair, but both stopped after
> exactly two dump events, before the owner control activated. In each run the
> second shovel released while still owned by `carry`, took
> `carry_to_return_release_safety`, and never entered the explicit dump skill.
> Bucket-only FactoryFloor contact lasted about four seconds and remained
> below 100kN. Return then re-entered terrain with `61.660kg` and `68.385kg`
> residual bucket mass, exceeded both local-depth and qpos_1 envelope checks,
> and ended on the unchanged timeout chain. Use
> `return_handoff_owner_target_scoped_10cycle_diagnostic_v1/run/report_reanalysis_v1.json`
> and
> `return_handoff_owner_target_scoped_10cycle_diagnostic_v2/run/report.json`.
> Neither attempt exercised the seventh-dump owner change, so they do not
> overturn the gate-8 proof. They identify an earlier lifecycle blocker:
> `carry -> dump` committed-boundary/release ordering.
>
> All of B2, the wall-only diagnostic, v7, and the return-action v5 remain
> diagnostic/non-promotable; the owner-isolation v2 has the same boundary.
> They do not replace the original six-attempt
> `inconclusive` contact classification, define a production contact budget,
> promote the axis limiter, or count as a ten-dump pass. The next semantic
> decision is to review whether token-owned contact plus prior-owned depth is
> the desired production return contract, or whether to keep it diagnostic and
> instead address return ACT/data. Before another multi-shovel repeat, isolate
> why release can complete under carry ownership without a committed dump
> transition. Contact-budget review is still unresolved and all
> predictor/live rollout gates remain false.

## Post-Restart Status

This document originally launched the Phase 6G-S work from handoff commit
`ec6e47253968864aea26aca0571aff7c7f12cbe4`. The main thread has since
completed Phase 6G-S and Phase 6G-T; consult
`docs/oracle_terrain_residual_planner_closed_loop_log.md` for the current
source-of-truth facts before treating the older "Immediate next step" section
below as active work.

Current post-restart facts:

- Phase 6G-S request-local prior counterfactual succeeded: with the 6G-P mixed
  source and gate settings preserved, changing only
  `policy.dig_cut_planner.prior_path` to the existing surface-depth prior let
  B complete return handoff and gate 2.
- Phase 6G-T fresh gate-2 A/B bounded smoke succeeded for both A and B. The
  explicit target residual projection showed a small B improvement over A, with
  worse B deposited fraction / depth-command tracking as an execution-quality
  caveat.
- C remains `not_evaluated` / `blocked_by_missing_gold_samples`.
- The working surface-depth prior remains request-local evidence only; it is
  not a checked-in default promotion.
- A main-thread open-testing audit verified the existing 6G-S / 6G-T artifacts
  and focused residual tests. The remaining unchecked Phase 6 items are broader
  experiment objectives that require explicit target / run-scope / calibration
  decisions, not a safe default continuation of the old immediate-next-step
  smoke.
- The user later authorized request-local reasonable defaults for those broader
  Phase 6 experiment objectives. Phase 6G-U added per-cycle quality reports and
  posthoc T1/T2 default projections on the existing 6G-T A/B rollouts, then
  generated target-specific T1/T2 B runtime sources and reran bounded B smokes.
  Both target-specific B reruns reached gate 2, but both are worse than A on
  target residual/completion; the earlier posthoc T2 B advantage does not
  survive target-specific source regeneration. B also remains worse on deposit
  / payload / depth tracking in both targets.

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
