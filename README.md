# Excavator Testbed

A **clean, model-agnostic imitation learning testbed** for engineering machinery (excavator / loader) intelligent control, built on top of MuJoCo + dm_control.

## Status

**Pipeline validated end-to-end** on `sim_transfer_cube_scripted` (vx300s bimanual, 14-DOF):

| Stage | Status |
|---|---|
| Scripted data collection (HDF5) | ✅ working |
| ACT training on GPU | ✅ working — val_loss 74.6 → 0.087 over 500 epochs |
| Policy rollout + evaluation | ✅ working — 10% success @ 39 demos / 500 epochs |
| MP4 video output with reward overlay | ✅ working |

Excavator task and teleop data collection are **next** — the infrastructure is ready.

## Philosophy

- **Policies are hot-swappable plugins** — register with `@register_policy("name")`, swap in YAML, nothing else changes. ACT is fully wired; `diffusion` stub is ready to implement.
- **Fixed evaluation** — same tasks, same seeds, same camera views every run. Fair comparison by design.
- **Backend-agnostic** — MuJoCo (`SimBackend` ABC) now; other simulators slot in by implementing the same interface.
- **Data collection pipeline** — Phase 1: scripted policy runs in EE-space (`MuJoCoEESimBackend`) to drive the robot. Phase 2: extracted joint trajectory is replayed in joint-space sim (`MuJoCoSimBackend`) and saved as HDF5 with 14-DOF joint-space actions. The trained policy then operates in the same joint-space during evaluation.

## Quick start

```bash
conda activate aloha
pip install -e ".[dev]"   # only needed once

# 1. Collect scripted demos (two-phase EE→joint pipeline, saves 14-DOF joint-space actions)
python -m testbed.cli.record --config testbed/configs/task_v0.yaml --num-episodes 50

# 2. Train ACT (resumes from checkpoint if resume_ckpt is set in act_v0.yaml)
python -m testbed.cli.train --config testbed/configs/act_v0.yaml

# 3. Evaluate trained policy + save MP4 videos
python -m testbed.cli.eval --config testbed/configs/eval_v0.yaml

# 4. Quick demo (N rollouts, saves runs/demo/transfer_cube_act_v0/rollout_00x.mp4)
python scripts/demo_sim.py --rollouts 10

# 5. Live interactive viewer (no video saving)
python scripts/watch_sim.py
```

> **Note:** The CLI flag is `--num-episodes` (hyphen), not `--num_episodes`.
> To train from scratch, remove or comment out `resume_ckpt` / `start_epoch` in `testbed/configs/act_v0.yaml`.

## Repo layout

```
testbed/                    ← Python package (pip install -e .)
  backends/
    base.py                 ← SimBackend / EESimBackend ABCs
    mujoco/
      backend.py            ← MuJoCoSimBackend  (joint-space, policy eval)
      ee_backend.py         ← MuJoCoEESimBackend (EE-space, data collection)
      tasks/                ← dm_control task physics (bimanual, single-arm, excavator)
  policies/
    base.py                 ← Policy / Trainer ABCs + registry
    act/                    ← ACT — FULLY IMPLEMENTED (ResNet18 + Transformer, temporal agg)
    diffusion/              ← Diffusion — stub, NotImplementedError
    dummy/                  ← Zero / replay policy for smoke tests
  data/
    recorder.py             ← HDF5 episode recorder
    dataset.py              ← EpisodeDataset (PyTorch DataLoader compatible)
  eval/
    suite.py                ← EvalSuite (runs rollouts, computes metrics)
    tasks.py                ← EvalTaskDef per task (cameras, reward threshold, pose sampler)
    video.py                ← MP4 renderer with reward bar overlay
    metrics.py              ← Success rate, reward statistics
  configs/
    schema.py               ← Pydantic config schemas
    act_v0.yaml             ← ACT training + eval config (transfer cube)
    task_v0.yaml            ← Data collection config
    eval_v0.yaml            ← Standalone eval config
  cli/
    record.py               ← `python -m testbed.cli.record`
    train.py                ← `python -m testbed.cli.train`
    eval.py                 ← `python -m testbed.cli.eval`
  runtime/                  ← Runner loop + safety guard (future: real robot)
  state/                    ← StructuredState, FK helpers
  tasks/                    ← Backend-independent task specs

scripts/
  demo_sim.py               ← Run trained policy, save MP4s (no CLI overhead)
  watch_sim.py              ← Live MuJoCo viewer (interactive window)

legacy/                     ← Original PACT code, frozen — will be removed
runs/                       ← Experiment artifacts (gitignored)
data_sim_episodes/          ← Collected HDF5 episodes (gitignored)
```

## Adding a new policy

Implement `Policy` (+ optionally `Trainer`) from `testbed.policies.base`:

```python
# testbed/policies/my_model/adapter.py
from testbed.policies.base import Policy, register_policy
import numpy as np

@register_policy("my_model")
class MyPolicy(Policy):
    def predict(self, obs: dict) -> np.ndarray:
        # obs["qpos"]        → (14,) joint positions
        # obs["image_top"]   → (3, H, W) float32 [0,1]
        ...

    def reset(self) -> None: ...
```

Then set `policy.class: MyModel` in any YAML config — the CLI picks it up automatically.

## Tasks

| Task name | Robot | DOF | Description |
|---|---|---|---|
| `sim_transfer_cube_scripted` | vx300s bimanual | 14 | Right arm picks cube, hands off to left arm |
| `sim_lifting_cube_scripted` | vx300s single | 7 | Single arm lifts cube to target height |
| `sim_excavator_*` | Excavator | 4 | Dig + dump (scripted policy needs recalibration) |

## Legacy

The original PACT ACT-coupled code lives in `legacy/`. It is frozen and will be removed once the testbed fully covers all functionality.
