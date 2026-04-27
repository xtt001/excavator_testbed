# V2.2 5-Primitives Summary

Date: 2026-04-27

## Design

- Branch: `fs/v2_2-dev-5primitives`
- Baseline preserved on `fs/v2_1-dev-4primitives`.
- Last 4p baseline rollout:
  `runs/eval/agx_v2_2_4primitives_carrytrim120_leftboost_postdump_hold30_260427_smoke/videos/rollout_000.mp4`
- Docs copy:
  `docs/v2_2_4primitives/rollout_000_carrytrim120_leftboost_postdump_hold30_260427_success.mp4`

The 5p split is:

```text
dig -> carry -> approach_dump -> dump_release -> return
```

`carry` transports loaded soil toward the truck. `approach_dump` enters
dump-ready relative geometry and may include light fluent human pre-release
motion where swing and curl-out overlap. This is not treated as label pollution
by itself, because human teleop often curls while visually confirming that soil
will not spill.

The ownership boundary is stable release intent, not the delayed material-mass
counter. The old material-release boundary let `approach_dump` learn
`dump_release` actions, so at rollout it took the future skill's job, emptied
the bucket early, and pushed the system into a state the next skill had not
seen.

## Upper Model Boundary

Do not run the VLM / upper model at primitive switch frequency. The long-term
structure is two-layer:

- VLM / upper model outputs low-frequency task intent: dig sector, dig depth,
  dump target, continue/stop, or exception replanning.
- Skill planner / boundary head handles high-frequency primitive switching from
  relative geometry, bucket mass, clearance, and later visual geometry heads.

`dig` and `carry` are intended to become goal-conditioned primitives: the motion
pattern is mostly shared, while position, depth, start pose, end pose, and safety
constraints parameterize the skill.

## Implementation Entry Points

- Builder CLI: `tb-build-primitives-v2_2_5p`
- Builder function: `build_primitive_datasets_5p`
- Planner policy: `primitive_planner_act_5p`
- Train configs:
  - `testbed/configs/act_agx_v2_2_5primitives_carry_qvel_e500.yaml`
  - `testbed/configs/act_agx_v2_2_5primitives_approach_dump_qvel_e500.yaml`
  - `testbed/configs/act_agx_v2_2_5primitives_dump_release_qvel_e500.yaml`
- Eval config:
  - `testbed/configs/eval_agx_v2_2_5primitives_qvel_3cycle_smoke.yaml`

The first version keeps ACT inputs non-privileged: `qpos + qvel`. Unity target
geometry is used for offline labels, QC, scripted switch diagnostics, and logs,
not as low-dimensional ACT policy input.

## First Dataset And Training

- Dataset root:
  `/data/pingfan/excavator_testbed_data_archive/agx_v2_2_5primitives_approach_dump_260427`
- Repo symlink: `data/agx_v2_2_5primitives_approach_dump_260427`
- Episode counts: `dig=64`, `carry=34`, `approach_dump=19`,
  `dump_release=63`, `return=0`.
- `return` was intentionally skipped in this first build to avoid redundant
  slow copying; the smoke rollout reuses the 4p return checkpoint.
- Carry QC: accepted `34`; bucket mass loss median/max `0kg`; tail strong
  curl-out exists in `22/34` windows but is accepted because it did not release
  material.
- Approach QC: accepted `19`; length median `36` steps; bucket mass loss median
  `97.7kg`, max `137.5kg`, below the reject threshold for pre-release spill.
- Dump-release QC: accepted `63`; hard collision windows `0`; first 20 steps
  never dropped below rim or lost clearance.
- Trained e500 checkpoints:
  - `/data/pingfan/excavator_testbed_runs/ckpts/v2_2_5primitives/carry_qvel_e500_260427/policy_best.ckpt`
  - `/data/pingfan/excavator_testbed_runs/ckpts/v2_2_5primitives/approach_dump_qvel_e500_260427/policy_best.ckpt`
  - `/data/pingfan/excavator_testbed_runs/ckpts/v2_2_5primitives/dump_release_qvel_e500_260427/policy_best.ckpt`

## Diagnostic Rollout

- Partial rollout log:
  `runs/eval/agx_v2_2_5primitives_approach_dump_260427_smoke/results/rollouts/rollout_000.partial.jsonl`
- Cycle1 switched `carry -> approach_dump -> dump_release -> return` and
  deposited into the target.
- Cycle2 switched `carry -> approach_dump` at `t=1230`, then
  `approach_dump` emptied the bucket while target horizontal distance was still
  about `2.4m`; the planner never switched to `dump_release`.
- No completed video was produced because the diagnostic rollout was stopped
  after the failure mode was clear.

Conclusion: the material-release split does not solve the cycle2 issue. The
failure matches the ownership problem: the previous skill performed the future
skill's release action and drove itself outside the distribution expected by
the planner and next primitive.

## Ownership Rebuild

The builder now uses the first safe, stable release intent as the
`dump_release` start. This keeps mild mixed swing/curl in `approach_dump`, but
moves stable release supervision into `dump_release`.

- Dataset root:
  `/data/pingfan/excavator_testbed_data_archive/agx_v2_2_5primitives_ownership_260427`
- Repo symlink: `data/agx_v2_2_5primitives_ownership_260427`
- Episode counts: `dig=64`, `carry=34`, `approach_dump=4`,
  `dump_release=27`, `return=0`.
- QC: `dump_release` starts `6-94` steps before official mass-based
  `dump_start`; hard collision windows `0`; near collision windows `3`.

This confirms that the current history dataset has too little clean
`approach_dump` ownership data. Training a robust 5p approach policy from only
four windows is not recommended; the next data collection should deliberately
separate "position over truck" from "stable release", or the planner should add
an explicit boundary/axis-ownership head.

## Acceptance Target

- One 3-cycle live smoke succeeds: `cycle1/2/3_success_rate = 1.0`
- `completed_transition_count = 2`
- `transition_timeout_count = 0`
- `hard_target_collision_count = 0`
- cycle2 final deposited fraction `>= 0.90`
- cycle2 post-dump target mass drop `< 50kg`
- Visual check: no obvious cycle2 early release or post-dump pullback spill.
