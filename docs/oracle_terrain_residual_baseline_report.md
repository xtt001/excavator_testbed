# Oracle Terrain Residual Baseline Report

## Purpose

This report records the current-run explicit-target residual baseline for
Oracle Terrain Residual Planner v0. It is a durable, human-readable packet
built from the pure eval report builder, not a rollout-review schema change and
not an eval pass/fail judgment.

## Repository State

- cwd: `/home/pingfan/PACT/excavator_testbed`
- branch/status: `tx/oracle-terrain-residual-planner-v0`, tracking
  `origin/tx/v2_6-llm-planner`, ahead `14`
- HEAD observed during this report slice:
  `441eb1a28f06e2fd1d17e64ea6f3e0ccada4a69f`

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

## Interpretation

For this explicit non-official example spec, target positive residual decreases
over the observed dig-segment evidence, while outside-target removed depth
increases substantially. Target overdig inside the two selected target cells
stays at `0.0`, and the latest target removed completion ratio remains low at
`0.251372821628`.

These facts are diagnostic evidence only. They do not prove target-shape
success or failure, and they do not define planner success, eval success,
bucket-aware tolerance, or official T1 semantics.

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
- write generated artifacts under `runs/eval`;
- define official T1 dimensions, depth, cell size, origin, or world-frame
  semantics;
- introduce target-shape pass/fail, eval pass/fail, planner success, bucket
  IoU, boundary tolerance, protected-area band, RMSE, candidate/effect/
  capability semantics, or official cycle IDs;
- change production planner, gate, policy, runtime config, token order,
  checkpoint contracts, branch, upstream, or dependencies.

## Reproducibility

The report values were produced in memory with
`testbed.eval.terrain_target_report.build_explicit_target_residual_baseline_report()`
using the rollout jsonl path and explicit target spec listed above. The smoke
projection confirmed that no files were written under the eval results
directory.
