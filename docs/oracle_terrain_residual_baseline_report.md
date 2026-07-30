# Oracle Terrain Residual Baseline Report

## Purpose

This report records the current-run explicit-target residual baseline for
Oracle Terrain Residual Planner v0. It is a durable, human-readable packet
built from the pure eval report builder, not a rollout-review schema change and
not an eval pass/fail judgment.

## Current Official Phase 6 v0 Contract

The historical baseline sections below still describe the explicit
non-official smoke target used when they were produced. Current Phase 6 v0 eval
semantics are now centralized in
`testbed.eval.terrain_residual_contract`:

- `terrain_residual_target_v1` defines official T1
  `t1_large_shallow_rectangular_pit_default`: compact `grid[3,2]`, rows
  `[0,2)`, cols `[0,2)`, depth `0.25m`.
- `terrain_residual_target_v1` defines official T2
  `t2_long_shallow_trench_default`: compact `grid[3,2]`, rows `[0,3)`, cols
  `[0,1)`, depth `0.25m`.
- The official conservative pass/fail profile is
  `not_worse_than_current_A_gate2_baseline`. A same-run branch must reach the
  target-cycle gate, complete at least two dumps, have zero transition
  timeouts, and be no worse than the A gate-2 baseline on target positive
  residual, target overdig, outside-target removal, deposited fraction, and
  depth absolute error.

Request-local official evidence is written at:

```text
runs/eval/oracle_terrain_residual_phase6_official_v0_pass_fail_20260703/official_t1_t2_a_baseline_pass_fail_comparison.json
```

That artifact records A passing both official targets against its own gate-2
baseline. The target-specific B reruns reached gate 2 with zero transition
timeouts for both T1 and T2, but failed official v0 on
`target_positive_residual_worse_than_baseline`,
`deposited_fraction_below_baseline`, and `depth_abs_error_above_baseline`.
The evidence points to execution-quality / ACT depth response or dump-exit
state rather than return reachability: B request-local cut intents ask for
shallow depth around `0.015m - 0.019m`, while real B depth peaks are around
`0.21m - 0.29m` and deposit / payload are lower than A. No planner behavior
change, checked-in default config change, prior promotion, or production
readiness claim is made from this evidence.

The current depth-execution diagnostic root is:

```text
runs/eval/oracle_terrain_residual_phase6_depth_execution_diagnostic_20260703
```

Its index artifact
`t1_t2_b_depth_execution_diagnostic_index.json` records that both completed T1
cycles and both completed T2 cycles overshot the residual intent depth. T1 mean
depth peak minus intent is `0.223569767456m`; T2 mean depth peak minus intent is
`0.245077269058m`. Both target-specific B runs still reached gate 2 with zero
transition timeouts, and dump-exit rows show return envelope readiness. This
keeps the next root-cause focus on ACT depth response / dump-exit state, not on
return reachability.

`testbed.eval.terrain_residual_execution_diagnostic` also owns the
request-local official-v0 failure packet builder/writer. The packet is only a
summary of existing official pass/fail, depth diagnostic, cycle-quality, and
B-runtime-source artifacts. Its required conservative statuses are
`planner_behavior_change_status=not_made`,
`production_readiness_status=not_claimed`, and
`calibrated_branch_status=blocked_pending_gold_replay_samples`. The current
generated packet is
`runs/eval/oracle_terrain_residual_phase6_official_v0_failure_packet_20260707/official_v0_failure_packet.json`.

The calibrated C branch remains
`blocked_pending_gold_replay_samples`. The new
`testbed.eval.terrain_gold_cycle_samples` owner defines one
`terrain_gold_cycle_sample_v1` JSONL record per completed cycle with required
`payload_mass_kg`. Complete cycle-quality-derived records include start/end
removed-depth grids, target grid/masks, residual metrics, payload peak,
effective deposited mass, deposited fraction, depth target/peak/error,
planned/actual entry and exit fields, success, transition, and gate fields.
Volume labels remain `requires_unity_volume_fields` until future Unity /
env-state direct volume measurements exist; they are not inferred from
`removed_depth_delta * cell_area`.

## Repository State

- cwd: `/home/pingfan/PACT/excavator_testbed`
- branch/status: `tx/oracle-terrain-residual-planner-v0`, tracking
  `origin/tx/v2_6-llm-planner`, ahead `34`
- HEAD observed during this report slice:
  `7b65e95244dc2730bf55ee70917f03ce0c4fd6f7`

## Input Run

- results directory:
  `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results`
- rollout jsonl:
  `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results/rollouts/rollout_000.jsonl`
- file count under the results directory before/after the read-only smoke:
  `10 -> 10`

## Explicit Target Spec

This target is an explicit non-official smoke spec. It is not an official T1
default.

```json
{
  "grid_shape": [3, 2],
  "row_start": 0,
  "row_end": 2,
  "col_start": 0,
  "col_end": 1,
  "target_depth_m": 0.25,
  "profile": "explicit_t1_like_rectangular_shallow_pit",
  "official_t1_default": false
}
```

## Report Identity

- report source: `explicit_target_residual_baseline_report`
- report schema: `explicit_target_residual_baseline_report_v1`
- report status: `present`
- latest projection status: `present`
- convergence projection status: `present`

## Latest Projection Summary

| Field | Value |
| --- | ---: |
| latest snapshot row | `6147` |
| target positive residual depth sum | `0.374313589186` |
| target overdig depth sum | `0.0` |
| target removed completion ratio | `0.251372821628` |
| outside-target removed depth sum | `0.488698139786` |
| target residual depth RMSE | `0.187219063753` |
| target residual depth MAE | `0.187156794593` |
| target residual depth abs max | `0.191985052079` |

## Convergence Summary

| Field | Value |
| --- | ---: |
| point count | `10` |
| diagnostic trend | `target_positive_residual_reduced_outside_removed_increased` |
| target positive residual start | `0.498092905036` |
| target positive residual end | `0.383547134697` |
| target positive residual delta | `-0.114545770339` |
| target overdig start | `0.0` |
| target overdig end | `0.0` |
| target overdig delta | `0.0` |
| target removed completion ratio start | `0.003814189928` |
| target removed completion ratio end | `0.232905730606` |
| target removed completion ratio delta | `0.229091540678` |
| outside-target removed depth start | `0.050789695233` |
| outside-target removed depth end | `0.479643445462` |
| outside-target removed depth delta | `0.428853750229` |

## Target Interior Depth-Error Summary

These values are computed over valid target cells only, using
`target_depth_grid_m - removed_depth_grid_m`. They are threshold-free
diagnostics, not pass/fail criteria.

| Point | Snapshot row | RMSE | MAE | Abs max |
| --- | ---: | ---: | ---: | ---: |
| first convergence point | `416` | `0.24904827798` | `0.249046452518` | `0.25` |
| last convergence point | `5821` | `0.191779018803` | `0.191773567348` | `0.19321956858` |
| latest projection | `6147` | `0.187219063753` | `0.187156794593` | `0.191985052079` |

## Target Shape Overlap / Tolerance Summary

These values compare valid removed-active cells (`removed_depth_grid_m > 0.0`)
against the explicit target cells. They are diagnostic shape-overlap evidence,
not target-shape pass/fail criteria.

| Point | Snapshot row | Raw IoU | Raw outside removed-depth sum | One-cell dilated IoU | Dilated saturation | Outside dilated removed-depth sum |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| first convergence point | `416` | `0.333333333333` | `0.050789695233` | `0.333333333333` | `1.0` | `0.0` |
| last convergence point | `5821` | `0.333333333333` | `0.479643445462` | `1.0` | `1.0` | `0.0` |
| latest projection | `6147` | `0.333333333333` | `0.488698139786` | `1.0` | `1.0` | `0.0` |

The one-cell dilated mask uses row-major Chebyshev / 8-neighbor dilation. For
this explicit `3 x 2` grid, that one-cell dilation saturates all valid cells
(`saturation_ratio = 1.0`). Therefore a dilated IoU of `1.0` at the last and
latest points only means all removed-active valid cells fall inside the
saturated dilated mask; it must not be interpreted as target-shape success.

Meter tolerance profiles are present as diagnostics but not evaluated for this
run because the records do not include cell size:

| Profile | Tolerance | Status |
| --- | ---: | --- |
| `narrow_0_30m` | `0.30m` | `cell_size_missing` |
| `bucket_0_50m` | `0.50m` | `cell_size_missing` |

No meter-derived IoU is inferred.

## Shape Guard Shadow Audit

This section records a shadow-only diagnostic audit for the same explicit
non-official target spec. It does not make a production decision, stop the
planner, define eval pass/fail, or define official threshold/default semantics.

Audit identity:

- source: `explicit_target_shape_guard_shadow_audit`
- schema: `terrain_shape_guard_shadow_audit_v1`
- status: `present`
- `shadow_only`: `true`
- `no_production_decision`: `true`
- validation errors: `[]`

Explicit example thresholds used for this report only:

| Input | Value |
| --- | ---: |
| `max_target_overdig_depth_sum_m` | `0.0` |
| `max_target_positive_residual_depth_sum_m` | `0.4` |
| `max_outside_target_removed_depth_delta_m` | `0.0` |
| `latest_payload_fraction` | `null` |
| `min_payload_fraction` | `null` |

These are report/smoke example thresholds only. They are not official defaults,
not runtime gate thresholds, and not target-shape success criteria.

Event summary:

| Event | Status | Reason | Evidence |
| --- | --- | --- | --- |
| `low_payload_shape_guard_stop` | `not_evaluated` | `missing_explicit_payload_inputs` | `latest_payload_fraction=null`, `min_payload_fraction=null` |
| `overdig_guard_stop` | `not_triggered` | `latest_target_overdig_within_explicit_max` | latest target overdig `0.0`, explicit max `0.0` |
| `depth_budget_exhausted` | `triggered` | `latest_target_positive_residual_at_or_below_explicit_max` | latest target positive residual `0.374313589186`, explicit max `0.4` |
| `outside_protected_removed_increased` | `triggered` | `outside_target_removed_delta_exceeds_explicit_max` | outside-target removed-depth delta `0.428853750229`, explicit max `0.0` |

Triggered event names:

- `depth_budget_exhausted`
- `outside_protected_removed_increased`

Not-evaluated event names:

- `low_payload_shape_guard_stop`

The payload event is not evaluated because this report does not infer payload
fraction from the baseline report. The two triggered events mean only that the
explicit example thresholds would flag those shadow conditions in the current
run evidence.

## Shadow Audit Impact Evidence

This section reviews what the current shadow-event evidence can and cannot say
about reducing overdig risk without materially reducing payload or cycle
efficiency. The review recomputed the baseline report and shadow audit
read-only, then inspected the existing rollout review and summary artifacts. The
results directory file count stayed `10 -> 10`.

Overdig-risk signal supported by the current shadow events:

- `outside_protected_removed_increased` is triggered because outside-target
  removed-depth delta is `0.428853750229` against the explicit example max
  `0.0`.
- `depth_budget_exhausted` is triggered because latest target positive residual
  is `0.374313589186`, at or below the explicit example max `0.4`.
- `overdig_guard_stop` is not triggered because latest target overdig inside
  the two selected target cells is `0.0` against explicit max `0.0`.
- `low_payload_shape_guard_stop` is not evaluated because explicit payload
  inputs are absent.

Existing payload / cycle-efficiency evidence available from the current
artifacts:

| Field | Value |
| --- | ---: |
| rollout review overall status | `needs_root_cause_audit` |
| rollout success flag | `true` |
| target cycle gate success | `false` |
| rollout stop reason | `dig_area_depleted` |
| completed dump cycles | `10` |
| target cycle gate | `15` |
| planned/actual cycle records | `10` |
| bucket mass out mean / min / max | `61.33190612793` / `28.913818359375` / `79.430519104004` |
| bucket mass out population stdev | `15.127678986711` |
| deposited fraction mean / min / max | `0.802401915908` / `0.572773417672` / `0.968514219634` |
| deposited fraction population stdev | `0.114068889876` |
| target deposit delta mean / min / max kg | `49.890930366516` / `22.668653488159` / `73.156555175781` |
| quality issue count | `183` |
| low-cycle deposited-fraction count | `9` |
| post-dump target mass drop mean / max kg | `0.0` / `0.0` |

Evidence gaps that prevent a stronger impact claim:

- The audit is retrospective; it does not simulate stopping, replanning, or
  choosing alternative cuts at the triggered shadow events.
- The payload event is not evaluated because the audit did not receive explicit
  `latest_payload_fraction` / `min_payload_fraction` inputs.
- The bucket mass and deposited-fraction fields describe the actual current run,
  not a counterfactual shape-guarded run.
- The current summary exposes completed dump count and target-cycle-gate status,
  but it does not prove cycle time, guarded cycle count, or payload efficiency
  after hypothetical shadow stops.
- The example thresholds are report-only values, not official defaults or
  production gate thresholds.

Conservative conclusion: the current evidence supports an overdig-risk concern
for outside-target removal growth under the explicit example thresholds. It
does not prove that a shape guard would reduce overdig in production, nor that
such a guard would preserve payload or cycle efficiency without material loss.

## Offline Residual Baseline Comparison

This section records the Phase 6A offline baseline-comparison scaffold output
for the same current run and explicit non-official target spec. It is
report/evidence infrastructure only. It does not run a new simulation rollout,
define target-shape success, define eval/planner success, compare closed-loop
performance, or promote any diagnostic ranking into runtime action selection.

Comparison identity:

- source: `explicit_offline_residual_planner_baseline_comparison`
- schema: `terrain_residual_planner_baseline_comparison_v1`
- status: `present`
- `offline_only`: `true`
- validation errors: `[]`

Input scope:

- target rollout:
  `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results/rollouts/rollout_000.jsonl`
- explicit non-official target spec: `grid_shape=[3, 2]`, rows `[0:2]`,
  cols `[0:1]`, `target_depth_m=0.25`
- candidate/effect/calibration evidence: recomputed in memory from the Phase
  3/4/5 offline helpers using explicit smoke-only options and capacity values
  documented in the phase log

Branch status summary:

| Branch | Status | Reason / evidence |
| --- | --- | --- |
| `current_planner_baseline` | `present` | current rollout and target residual diagnostics are available |
| `heuristic_residual_pipeline` | `present` | offline candidate, constraint, scoring, effect, and payload-proxy evidence are available |
| `calibrated_residual_pipeline` | `not_evaluated` | `blocked_by_missing_gold_samples` |

Heuristic branch smoke facts:

| Field | Value |
| --- | ---: |
| candidate count | `24` |
| best score candidate | `cut_candidate_000009` |
| effect record count | `24` |
| payload proxy fraction max | `0.899929931625` |
| expected removed volume total | `0.368464939353` |
| target removed volume total | `0.263189242395` |
| outside-target removed volume total | `0.105275696958` |
| overdig volume delta total | `0.105879229144` |

Calibrated branch facts:

| Field | Value |
| --- | ---: |
| usable gold sample count | `0` |
| usable extracted record count | `0` |

Comparison limits:

- closed-loop resimulation: `not_run`
- counterfactual cycle count: `not_available`
- cycle time: `not_available`
- production integration: `not_integrated`
- official success semantics: `not_defined`
- calibrated-model fallback: `not_invented`

Conservative interpretation: the Phase 6A scaffold proves that current-run
diagnostics and the heuristic residual candidate/effect pipeline can be placed
side by side in a durable offline comparison packet, while the calibrated branch
is correctly blocked by missing usable gold samples. It does not prove the
heuristic residual pipeline outperforms the current planner, does not prove a
calibrated model is better than the heuristic branch, and does not establish any
runtime action, official target default, official threshold, target-shape
success, eval success, or planner success semantics.

## Predicted Residual A/B Comparison

This section records the Phase 6E-F predicted A/B comparison output for the
same current run and explicit non-official target spec. Branch A is current
rollout evidence. Branch B is a Phase 6E-E effect-model counterfactual, not a
real simulation rollout. Branch C remains blocked by missing usable gold
samples.

Comparison identity:

- source: `explicit_predicted_residual_ab_comparison`
- schema: `terrain_residual_predicted_ab_comparison_v1`
- status: `present`
- `offline_only`: `true`
- validation errors: `[]`

Input scope:

- target rollout:
  `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results/rollouts/rollout_000.jsonl`
- explicit non-official target spec: `grid_shape=[3, 2]`, rows `[0:2]`,
  cols `[0:1]`, `target_depth_m=0.25`
- protected current results file count in the read-only smoke: `10 -> 10`
- future Phase 6D/6E run root remained absent:
  `runs/eval/oracle_terrain_residual_phase6d_t1_ab_20260702/results`

Branch status summary:

| Branch | Status | Evidence type / reason |
| --- | --- | --- |
| `current_planner_baseline` | `present` | `current_rollout_evidence` |
| `heuristic_residual_pipeline` | `present` | `predicted_counterfactual` |
| `calibrated_residual_pipeline` | `not_evaluated` | `blocked_by_missing_gold_samples` |

A/B residual comparison facts:

| Field | A current rollout | B predicted counterfactual |
| --- | ---: | ---: |
| target positive residual depth sum | `0.374313589186` | `0.0` |
| target removed completion ratio | `0.251372821628` | `1.0` |
| target overdig depth sum | `0.0` | `0.009656514972` |
| outside-target removed depth sum | `0.488698139786` | `0.680683191865` |

B predicted rollout facts:

| Field | Value |
| --- | ---: |
| predicted rollout status | `present` |
| step count | `1` |
| stop reason | `zero_target_positive_residual` |
| selected eval-only cut-intent candidate | `cut_candidate_000009` |
| aggregate expected delta depth | `0.575955156237` |
| aggregate expected delta volume | `0.035997197265` |

Delta summary:

| Field | Value |
| --- | ---: |
| target positive residual delta | `-0.374313589186` |
| target positive residual improvement magnitude | `0.374313589186` |
| target removed completion ratio delta | `0.748627178372` |
| target overdig increase | `0.009656514972` |
| outside-target removed-depth increase | `0.191985052079` |

Comparison limits:

- A branch evidence type: `current_rollout_evidence`
- B branch evidence type: `predicted_counterfactual`
- B real simulation status: `not_run`
- production integration: `not_integrated`
- official success semantics: `not_defined`
- official thresholds: `not_defined`
- calibrated-model fallback: `not_invented`

Conservative interpretation: the Phase 6E-F output places current A residual
evidence and predicted B counterfactual residual evidence in one durable report
packet. It still does not prove that B outperforms A in real closed-loop
simulation, does not define pass/fail or success semantics, and does not promote
the eval-only cut intent into runtime action selection.

## Materialized Predicted A/B Artifacts

This section records the Phase 6F-A artifact materialization output. The
artifacts are generated from explicit in-memory evidence: the Phase 6E-A
manifest, Phase 6E-B branch plan, Phase 6E-E predicted B rollout, and Phase
6E-F predicted A/B comparison. They are not real simulator rollouts.

Artifact writer identity:

- source: `explicit_predicted_residual_ab_artifact_writer`
- schema: `terrain_residual_predicted_ab_artifacts_v1`
- status: `present`
- validation errors: `[]`

Artifact root:

```text
runs/eval/oracle_terrain_residual_phase6f_predicted_ab_20260702/results
```

Written files:

- `eval_run_metadata.json`
- `experiment_manifest.json`
- `branch_run_plan.json`
- `predicted_b_rollout.json`
- `branch_comparison_report.json`
- `rollout_manifest.json`

Materialized comparison facts:

| Field | Value |
| --- | ---: |
| predicted B step count | `1` |
| predicted B stop reason | `zero_target_positive_residual` |
| selected eval-only cut-intent candidate | `cut_candidate_000009` |
| A target positive residual | `0.374313589186` |
| B predicted final positive residual | `0.0` |
| target completion delta | `0.748627178372` |
| target overdig increase | `0.009656514972` |
| outside-target removed-depth increase | `0.191985052079` |
| expected delta depth | `0.575955156237` |
| expected delta volume | `0.035997197265` |

No-overwrite facts:

- protected current results file count stayed `10 -> 10`
- writer rejected overwrite semantics in tests
- artifact writer status remains eval-only and diagnostic-only

Conservative interpretation: Phase 6F-A creates durable JSON artifacts for the
predicted A/B comparison so later runner or review work has a concrete file
surface. It still does not run a simulator, does not define pass/fail or success
semantics, does not integrate with production planner/runtime, and does not
turn the predicted B counterfactual into a real rollout.

## Predicted A/B Artifact Pipeline

This section records the Phase 6F-B end-to-end eval pipeline output. The
pipeline reads the explicit source rollout JSONL, rebuilds the target residual
report and predicted B branch evidence in memory, builds the predicted A/B
comparison, and then writes the same deterministic artifact surface as Phase
6F-A. It is still an effect-model counterfactual pipeline, not a simulator run.

Pipeline identity:

- source: `explicit_predicted_residual_ab_artifact_pipeline`
- schema: `terrain_residual_predicted_ab_artifact_pipeline_v1`
- status: `present`
- validation errors: `[]`

Source and target:

- source rollout:
  `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results/rollouts/rollout_000.jsonl`
- source record count: `6148`
- explicit non-official target spec: `grid_shape=[3, 2]`, rows `[0:2]`,
  cols `[0:1]`, `target_depth_m=0.25`

Artifact root:

```text
runs/eval/oracle_terrain_residual_phase6f_pipeline_ab_20260702/results
```

Nested status summary:

| Stage | Status |
| --- | --- |
| target residual report | `present` |
| experiment manifest | `present` |
| branch run plan | `present` |
| predicted B rollout | `present` |
| predicted A/B comparison | `present` |
| artifact writer | `present` |

Written files:

- `eval_run_metadata.json`
- `experiment_manifest.json`
- `branch_run_plan.json`
- `predicted_b_rollout.json`
- `branch_comparison_report.json`
- `rollout_manifest.json`

Pipeline comparison facts:

| Field | Value |
| --- | ---: |
| predicted B step count | `1` |
| predicted B stop reason | `zero_target_positive_residual` |
| selected eval-only cut-intent candidate | `cut_candidate_000009` |
| A target positive residual | `0.374313589186` |
| B predicted final positive residual | `0.0` |
| target positive residual improvement | `0.374313589186` |
| target completion delta | `0.748627178372` |
| target overdig increase | `0.009656514972` |
| outside-target removed-depth increase | `0.191985052079` |
| expected delta depth | `0.575955156237` |
| expected delta volume | `0.035997197265` |

No-overwrite facts:

- protected current results file count stayed `10 -> 10`
- pipeline root did not exist before the smoke and exists after the smoke
- protected-root overlap is rejected before artifact writing

Conservative interpretation: Phase 6F-B makes the predicted A/B artifact
generation reproducible from the source rollout and explicit options. It still
does not prove B outperforms A in real closed-loop simulation, does not define
pass/fail or success semantics, and does not promote eval-only cut intents into
runtime action selection.

## Predicted A/B Artifact CLI

This section records the Phase 6F-C CLI entrypoint smoke. The CLI is a thin
runner-facing wrapper around the Phase 6F-B pipeline: it reads a caller-supplied
request JSON, runs the explicit eval-only pipeline, and writes the top-level
pipeline result JSON to stdout or an output path.

CLI identity:

- command: `tb-terrain-residual-ab-artifacts`
- module: `testbed.cli.terrain_residual_ab_artifact_pipeline`
- request input: explicit `--request-json`
- result output: `--output-json` or stdout
- return code in smoke: `0`

Artifact root:

```text
runs/eval/oracle_terrain_residual_phase6f_cli_ab_20260702/results
```

CLI smoke facts:

| Field | Value |
| --- | ---: |
| pipeline status | `present` |
| predicted B step count | `1` |
| predicted B stop reason | `zero_target_positive_residual` |
| selected eval-only cut-intent candidate | `cut_candidate_000009` |
| A target positive residual | `0.374313589186` |
| B predicted final positive residual | `0.0` |
| target positive residual improvement | `0.374313589186` |
| target completion delta | `0.748627178372` |
| target overdig increase | `0.009656514972` |
| outside-target removed-depth increase | `0.191985052079` |
| expected delta depth | `0.575955156237` |
| expected delta volume | `0.035997197265` |

No-overwrite facts:

- protected current results file count stayed `10 -> 10`
- CLI artifact root did not exist before the smoke and exists after the smoke
- request JSON was explicit and temporary; no official defaults were inferred

Conservative interpretation: Phase 6F-C makes the predicted A/B artifact
pipeline callable without a bespoke Python smoke script. The CLI return code
does not define eval pass/fail, planner success, production readiness, or
official thresholds.

## Residual Eval Run Plan

This section records the Phase 6G-A command-plan bridge from predicted A/B
artifacts toward a real eval runner invocation. It does not run `tb-eval` and
does not create a new run root.

Run-plan identity:

- schema: `terrain_residual_eval_run_plan_v1`
- source: `explicit_residual_eval_run_plan`
- owner: `testbed.eval.terrain_residual_eval_run_plan`
- future planned root: `runs/eval/oracle_terrain_residual_phase6g_real_ab_20260702`

Current-run smoke inputs:

- current baseline metadata:
  `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results/eval_run_metadata.json`
- predicted A/B artifacts:
  `runs/eval/oracle_terrain_residual_phase6f_cli_ab_20260702/results`
- protected current evidence root:
  `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results`

Smoke facts:

| Field | Value |
| --- | --- |
| run plan status | `present` |
| validation errors | `[]` |
| no-overwrite status | `present` |
| A branch status | `runnable` |
| A command status | `runnable` |
| A planned output dir | `runs/eval/oracle_terrain_residual_phase6g_real_ab_20260702/current_planner_baseline` |
| A source config | `runs/jobs/yulong_v2_4_5_return_relocate_token_swap_all_train_eval_20260526/eval_configs/eval_10cycle_next_entry_cell_prior_relocate_spatial_bounds_fail_fast.yaml` |
| B branch status | `not_runnable` |
| B command status | `not_runnable` |
| B runtime integration status | `missing` |
| C branch status | `not_evaluated` |
| C reason | `blocked_by_missing_gold_samples` |

B branch blockers:

- `missing_residual_runtime_planner_mode`
- `missing_cut_intent_to_dig_cut_token_adapter`
- `missing_simulated_branch_execution_artifacts`

No-write facts:

- future root existed before smoke: `False`
- future root existed after smoke: `False`
- protected current results file count stayed `10 -> 10`

Conservative interpretation: Phase 6G-A identifies the exact command-level gap
between the predicted A/B artifact pipeline and a real B-branch eval run. A can
be rerun under a new branch output directory. B still cannot be honestly run as
a simulator branch until the residual cut intent is wired into runtime planner
mode and dig-cut token generation.

## Phase 6G-T Real A/B Surface-Prior Residual Projection

This section records the first fresh gate-2 real A/B bounded smoke after the
Phase 6G-S surface-prior counterfactual unblocked B return handoff. It uses the
same explicit non-official target spec as this report. It remains bounded
one-rollout evidence and does not define official pass/fail.

Artifacts:

- A/B comparison:
  `runs/eval/oracle_terrain_residual_phase6g_t_gate2_real_ab_20260703/real_ab_gate2_surface_prior_bounded_smoke_comparison.json`
- residual metric comparison:
  `runs/eval/oracle_terrain_residual_phase6g_t_gate2_real_ab_20260703/real_ab_gate2_surface_prior_residual_metric_comparison.json`
- A explicit target residual report:
  `runs/eval/oracle_terrain_residual_phase6g_t_gate2_real_ab_20260703/current_planner_baseline_explicit_target_residual_report.json`
- B explicit target residual report:
  `runs/eval/oracle_terrain_residual_phase6g_t_gate2_real_ab_20260703/heuristic_residual_pipeline_explicit_target_residual_report.json`

Gate facts:

| Branch | Gate success | Completed dumps | Stop reason | Lines |
| --- | ---: | ---: | --- | ---: |
| A current planner | `1.0` | `2` | `target_cycle_gate_reached` | `1454` |
| B heuristic residual + surface prior | `1.0` | `2` | `target_cycle_gate_reached` | `1432` |
| C calibrated | `not_evaluated` | | `blocked_by_missing_gold_samples` | |

Residual projection facts:

| Field | A current | B heuristic | B - A |
| --- | ---: | ---: | ---: |
| latest target positive residual depth sum | `0.497471058391` | `0.497159857768` | `-0.000311200623` |
| latest target removed completion ratio | `0.005057883218` | `0.005680284464` | `+0.000622401246` |
| latest outside-target removed depth sum | `0.102324411273` | `0.086281180382` | `-0.016043230891` |
| latest target overdig depth sum | `0.0` | `0.0` | `0.0` |
| convergence target positive residual delta | `-0.000310920703` | `-0.000933047268` | `-0.000622126565` |
| convergence completion ratio delta | `+0.000621841406` | `+0.001866094536` | `+0.00124425313` |
| convergence outside-target removed delta | `+0.052445076406` | `+0.039773162455` | `-0.012671913951` |

Execution-quality caveat:

| Field | A current | B heuristic |
| --- | ---: | ---: |
| deposited fraction mean | `0.8045243480617356` | `0.6729643155685991` |
| deposited fraction min | `0.7736410550070904` | `0.6371127565113851` |
| dig-depth absolute error mean | `0.03503912687301633m` | `0.24203957766294482m` |

Conservative interpretation: B shows a small explicit-target residual
projection improvement over A in this bounded smoke, and both branches reached
the same gate. However, B's deposited fraction and depth-command tracking are
worse in the same run. This is evidence that the residual path can now complete
the bounded gate with request-local surface-depth prior evidence; it is not a
full Phase 6 success claim, production-readiness claim, checked-in prior
promotion, or calibrated C comparison.

## Phase 6G-U Request-Local T1/T2 Cycle Quality Projection

The user authorized reasonable request-local default assumptions for the larger
Phase 6 experiment goals. This section records posthoc projections on the
existing Phase 6G-T gate-2 A/B rollouts; it does not rerun simulation and does
not define checked-in official target defaults.

New artifacts:

- assumptions:
  `runs/eval/oracle_terrain_residual_phase6g_t_gate2_real_ab_20260703/phase6_request_local_default_target_assumptions.json`
- T1/T2 comparison:
  `runs/eval/oracle_terrain_residual_phase6g_t_gate2_real_ab_20260703/phase6_request_local_default_t1_t2_ab_comparison.json`
- original-target per-cycle A report:
  `runs/eval/oracle_terrain_residual_phase6g_t_gate2_real_ab_20260703/current_planner_baseline_cycle_quality_report.json`
- original-target per-cycle B report:
  `runs/eval/oracle_terrain_residual_phase6g_t_gate2_real_ab_20260703/heuristic_residual_pipeline_cycle_quality_report.json`
- target-specific T1/T2 B rerun comparison:
  `runs/eval/oracle_terrain_residual_phase6g_u_target_specific_t1_t2_ab_20260703/phase6g_u_target_specific_t1_t2_ab_comparison.json`

Request-local target assumptions:

| Target | Compact-grid rectangle | Depth | Reason |
| --- | --- | ---: | --- |
| T1 large shallow rectangle | rows `[0, 2)`, cols `[0, 2)` | `0.25m` | covers `4 / 6` cells, about `67%` |
| T2 long shallow trench | rows `[0, 3)`, cols `[0, 1)` | `0.25m` | one-cell-wide trench across the long axis |

Default T1/T2 posthoc B-minus-A facts:

| Field | T1 default B - A | T2 default B - A |
| --- | ---: | ---: |
| latest target positive residual depth sum | `+0.015732030268` | `-0.000311200623` |
| latest target removed completion ratio | `-0.015732030268` | `+0.000414934164` |
| latest outside-target removed depth sum | `0.0` | `-0.016043230891` |
| latest target overdig depth sum | `0.0` | `0.0` |
| deposited fraction mean | `-0.131560032493` | `-0.131560032493` |
| effective deposit delta mean | `-11.33339881897kg` | `-11.33339881897kg` |
| payload peak mean | `-9.625952243805kg` | `-9.625952243805kg` |

Interpretation: with these request-local defaults, B is not uniformly better.
The T2 trench projection preserves a small residual advantage for B, while the
larger T1 rectangle makes B worse than A on positive residual and completion.
Both target projections keep the same execution-quality caveat: B has worse
payload/deposit quality. C remains `not_evaluated` /
`blocked_by_missing_gold_samples`.

Target-specific B rerun:

The posthoc result was followed by request-local target-specific B source
generation and real bounded B reruns. For each target, the source generation
preserved the 6G-P isolation design: cycle `0` used the near-origin active-dig
plan and cycles `1` / `2` used corridor-conditioned return-target plans. The B
config preserved the surface-depth prior and gate settings from 6G-T.

| Target | B gate success | B completed dumps | B stop reason | B rollout lines |
| --- | ---: | ---: | --- | ---: |
| T1 target-specific B | `1` | `2` | `target_cycle_gate_reached` | `1476` |
| T2 target-specific B | `1` | `2` | `target_cycle_gate_reached` | `1439` |

Target-specific B-minus-A facts, with A using the Phase 6G-T current baseline
rollout projected onto the same target:

| Field | T1 target-specific B - A | T2 target-specific B - A |
| --- | ---: | ---: |
| latest target positive residual depth sum | `+0.013392139722` | `+0.000310925942` |
| latest target removed completion ratio | `-0.013392139722` | `-0.000414567923` |
| latest outside-target removed depth sum | `0.0` | `-0.018496505917` |
| latest target overdig depth sum | `0.0` | `0.0` |
| deposited fraction mean | `-0.082576753762` | `-0.094762842451` |
| effective deposit delta mean | `-8.226134777069kg` | `-10.882712960243kg` |
| payload peak mean | `-7.206075668335kg` | `-10.695754528046kg` |
| depth absolute error mean | `+0.188530640304m` | `+0.210038141906m` |

Interpretation update: target-specific B reruns reached gate 2 for both default
targets, but neither T1 nor T2 beats A on positive residual or completion.
The earlier T2 B advantage was only a posthoc projection on the 6G-T B rollout;
after regenerating and rerunning the B residual source for T2, B is slightly
worse than A on target residual while still carrying the same deposit / payload
and depth-tracking caveats.

## Interpretation

For this explicit non-official example spec, target positive residual decreases
over the observed dig-segment evidence, while outside-target removed depth
increases substantially. Target overdig inside the two selected target cells
stays at `0.0`, and the latest target removed completion ratio remains low at
`0.251372821628`. Target-interior depth-error diagnostics also decrease across
the example convergence evidence: RMSE moves from `0.24904827798` at the first
point to `0.191779018803` at the last point, and MAE moves from
`0.249046452518` to `0.191773567348`. Raw target-cell IoU stays at
`0.333333333333`, while raw outside-target removed-depth sum grows from
`0.050789695233` to `0.479643445462` across the convergence points.

These facts are diagnostic evidence only. They do not prove target-shape
success or failure, and they do not define planner success, eval success,
bucket-aware tolerance, boundary tolerance pass/fail, shape-guard pass/fail,
production stopping behavior, or official T1 semantics.

## Missing Provenance

The current records do not provide these fields for this target-shape report:

- cell size
- origin
- timestamp
- frame transform
- height grid
- elevation grid
- confidence grid
- physical volume conversion
- official cycle IDs
- official target defaults

All residual, overdig, removed, and target values above are depth sums, not
physical volumes.

## Non-Goals

This report does not:

- integrate with `rollout_review.json`;
- change rollout review schema;
- make the original baseline projection builder write generated artifacts under
  `runs/eval` as part of report generation;
- define official T1 dimensions, depth, cell size, origin, or world-frame
  semantics;
- introduce target-shape pass/fail, eval pass/fail, planner success, bucket
  IoU pass/fail, official boundary tolerance, protected-area band, RMSE
  threshold/pass-fail, shape-guard pass/fail, production stopping behavior,
  default shadow thresholds, candidate/effect/capability semantics, or official
  cycle IDs;
- change production planner, gate, policy, runtime config, token order,
  checkpoint contracts, branch, upstream, or dependencies.

## Reproducibility

The report values were produced in memory with
`testbed.eval.terrain_target_report.build_explicit_target_residual_baseline_report()`
using the rollout jsonl path and explicit target spec listed above. The smoke
projection confirmed that no files were written under the eval results
directory.

The Phase 6G-T values were produced by first running fresh request-local
bounded A/B smoke artifacts under
`runs/eval/oracle_terrain_residual_phase6g_t_gate2_real_ab_20260703/`, then
applying the same report builder to each branch's `rollout_000.jsonl` and
writing explicit comparison artifacts in that same request-local root.
