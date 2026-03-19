# Excavator Testbed (Repo A — Python)

A **clean, backend-agnostic imitation learning testbed** for engineering machinery intelligent excavation.

Three-repo architecture:
- **Repo A — this repo** (Python): training / eval / data pipeline + AGX remote backend
- **Repo B — agxunity-sim** (Unity/C#): scene, bridge, camera export, actuator state export
- **Repo C — sim-protocol** (Shared): protocol.md, schema.md, constants, eval suite YAML

---

## Status (branch: `tx/dev_agxunity`)

| Component | Status |
|---|---|
| AGX socket protocol (binary framing, step-ack) | ✅ implemented |
| `AGXSimBackend` (`SimBackend` ABC) | ✅ implemented |
| HDF5 schema v1.1 (timestamps, action_source, env_state, fpv) | ✅ implemented |
| `EpisodeRecorder` v1.1 | ✅ implemented |
| `JoystickActionSource` (pygame, dual-stick FarmStick, smoothing, button reset) | ✅ implemented |
| `KeyboardActionSource` (pygame, WASD+arrows fallback) | ✅ implemented |
| `tb-record-teleop` CLI | ✅ implemented |
| `tb-replay` CLI + QA diff report | ✅ implemented |
| Eval suite: AGX mass-based success rule (spec §8) | ✅ implemented |
| ACT policy adapter + trainer | ✅ carried from v0 |
| Dummy policy | ✅ carried from v0 |
| MuJoCo backend | ✅ retained (legacy, not primary) |

**Next:** collect a small pilot teleop dataset → replay QA → train ACT → eval.

---

## Quick start

### 1. Install

```bash
pip install -e ".[dev]"
```

### 2. Run the protocol smoke test against Unity

```bash
python scripts/agx_smoke.py --host 127.0.0.1 --port 5057 --steps 500

# stricter validation: reset baseline consistency + reset-separated swing pulse sign checks
python scripts/agx_smoke.py --host 127.0.0.1 --port 5057 --steps 500 --strict
```

This verifies the live Unity bridge with `GET_INFO / RESET / STEP`, step-id
continuity, and raw RGB frame decoding.

`--strict` adds stronger live checks on top of the basic smoke:
- GET_INFO metadata consistency
- reset baseline repeatability
- reset-separated positive/negative swing pulse sign checks
- stable FPV image dimensions across the run

### 3. Record teleop episodes

```bash
# keyboard (WASD = swing/boom, arrows = stick/bucket, D = discard, Q = quit)
tb-record-teleop --config testbed/configs/teleop_v0.yaml --input keyboard

# dual-stick FarmStick / pygame joystick
tb-record-teleop --config testbed/configs/teleop_v0.yaml --input joystick
```

Episodes are saved to `data/agx_teleop/episode_N.hdf5` (schema v1.1).

Current V0 scope:
- fixed-position / stationary digging only
- action space is 4D arm control only: `[swing, boom, stick, bucket]`
- track / drive / steer are intentionally out of scope for V0 teleop data

### 4. Replay QA

```bash
tb-replay --episode data/agx_teleop/episode_0.hdf5
# QA — qpos diff: mean=X  max=X  (over 500 steps)

tb-replay --episode data/agx_teleop/episode_0.hdf5 --save-video
# writes runs/replay/episode_0_replay.mp4
```

### 5. Train ACT

```bash
tb-train --config testbed/configs/act_agx_v0.yaml
```

### 6. Evaluate

```bash
tb-eval --config testbed/configs/eval_agx_v0.yaml
# outputs: runs/eval/agx_excavation/metrics.json + summary.csv + videos/
```

---

## Connecting real AGXUnity machine

Edit `testbed/configs/teleop_v0.yaml`:

```yaml
agx:
  host: "192.168.x.x"   # Unity machine IP
  port: 5057
  reset_terrain: true   # teleop default
  reset_pose: true
```

Then run without the mock server. The Unity side must implement the V0 protocol
defined in Repo C `protocol.md` and match the current Repo B bridge.

For the current teleop pipeline, the default reset policy is full episode reset:
- `reset_pose: true`
- `reset_terrain: true`

Terrain reset is expected every episode. The Unity side should ensure that
terrain initialization is only applied once per episode reset path.

---

## Repo layout

```
testbed/
  backends/
    base.py                   ← SimBackend ABC (swap any backend by implementing this)
    agx/
      protocol.py             ← Binary framing, message enums, pack/unpack (V0)
      backend.py              ← AGXSimBackend(SimBackend) — primary backend
    mujoco/                   ← MuJoCo backend (retained, not primary)
  actions/
    base.py                   ← ActionSource ABC + ActionInfo dataclass
    gamepad.py                ← JoystickActionSource (pygame, per-axis deadzone/scale)
    keyboard.py               ← KeyboardActionSource (WASD+arrows fallback)
  data/
    schema.py                 ← HDF5 schema v1.1 constants (add-only)
    hdf5_io.py                ← write_episode / read_episode (v1.0 + v1.1 fields)
    recorder.py               ← EpisodeRecorder (buffers + flushes to HDF5)
    dataset.py                ← EpisodicDataset (PyTorch DataLoader)
  policies/
    base.py                   ← Policy / Trainer ABCs + @register_policy registry
    act/                      ← ACT — fully implemented (ResNet18 + Transformer)
    dummy/                    ← Zero policy for smoke tests
    diffusion/                ← Stub (NotImplementedError)
  eval/
    suite.py                  ← EvalSuite — AGX mass-based + MuJoCo reward-based success
    tasks.py                  ← EvalTaskDef per task (agx_excavation_teleop + legacy)
    metrics.py                ← EvalMetrics → metrics.json + summary.csv
    video.py                  ← MP4 with reward overlay
  configs/
    agx_v0.yaml               ← AGX host/port/dims
    teleop_v0.yaml            ← Teleop session config (joystick mapping, episode params)
    eval_agx_v0.yaml          ← AGX eval suite (success rule, num_rollouts)
    act_v0.yaml               ← Legacy ACT training config
    act_agx_v0.yaml           ← ACT training config for AGX teleop data
    task_v0.yaml              ← Legacy MuJoCo task config
  cli/
    record_teleop.py          ← tb-record-teleop
    replay.py                 ← tb-replay
    train.py                  ← tb-train
    eval.py                   ← tb-eval
    record.py                 ← tb-record (legacy MuJoCo scripted)

docs/
  add_teleop.md               ← Full integration spec (protocol + schema + milestones)

legacy/                       ← Original PACT code — frozen
data/                         ← HDF5 episodes (gitignored)
runs/                         ← Experiment artifacts (gitignored)
```

---

## AGX V0 protocol summary

All messages share a 16-byte little-endian header:
`magic(4) version(2) msg_type(2) payload_len(4) crc32(4)`

| Message | Direction | Key fields |
|---|---|---|
| `GET_INFO_REQ/RESP` | Python → Unity / Unity → Python | protocol version, dt/control_hz, action/qpos order, camera descriptors |
| `RESET_REQ/RESP` | Python → Unity / Unity → Python | seed, reset_terrain, reset_pose / success, dt |
| `STEP_REQ` | Python → Unity | step_id (int64), action float32[4] |
| `STEP_RESP` | Unity → Python | step_id, qpos[4], qvel[4], env_state[M], reward, fpv image |

**Action vector:** `[swing_speed_cmd, boom_speed_cmd, stick_speed_cmd, bucket_speed_cmd]` — normalized `[-1, 1]`

**Observation:**
- `qpos (4,)` — `[swing, boom, stick, bucket]` position_norm `[0, 1]`
- `qvel (4,)` — `[swing, boom, stick, bucket]` speed
- `env_state (M,)` — index 0 = `mass_in_bucket`
- `images["fpv"]` — `(H, W, 3)` uint8

**Success rule (spec §8):** `mass_in_bucket ≥ 2.0 kg` for `hold_steps=25` consecutive steps.

Current reward/success ownership:
- Repo B currently emits `reward = 0.0` in `STEP_RESP`
- Repo A records that value but does not use it as the primary task signal
- success is computed post-hoc from the recorded `env_state` time series
  (`mass_in_bucket_kg`), not decided by the simulator at teleop record time

Here "post-hoc" means:
- first record the raw episode: observations, actions, images, env_state
- later run evaluator / analysis logic over the saved episode or rollout
- derive `success` from the `env_state` series instead of trusting a live
  simulator reward or a manual operator flag

Live Repo A <-> Repo B interaction uses the binary TCP step-ack protocol above.
HDF5 is the offline dataset artifact written by Repo A. Unity-local
`metadata.json` / `steps.jsonl` / `.rgb24` exports are auxiliary sidecar
artifacts, not the shared live interaction contract.

---

## HDF5 schema v1.1

```
episode_N.hdf5
├── metadata/           schema_version="1.1", task_name, sim_backend, control_hz,
│                       dt, action_semantics, camera_names, image_format, seed, ...
├── observations/
│   ├── qpos            (T, 4)  float32  [swing, boom, stick, bucket] position_norm
│   ├── qvel            (T, 4)  float32  [swing, boom, stick, bucket] speed
│   ├── env_state       (T, M)  float32  env_state[0] = mass_in_bucket
│   └── images/fpv      (T, H, W, 3) uint8
├── action              (T, 4)  float32  [swing, boom, stick, bucket] speed cmd
├── rewards             (T,)    float32  currently usually 0.0 for AGX V0
├── timestamps/
│   ├── step_id         (T,)    int64
│   └── step_ns         (T,)    int64
└── action_source/
    ├── type            (T,)    str   "teleop" | "policy"
    └── id              (T,)    str   "joystick" | "keyboard" | ...
```

Schema is **add-only** — fields are never removed or renamed. Version bump required for any new required field.

---

## Adding a new policy

```python
# testbed/policies/my_model/adapter.py
from testbed.policies.base import Policy, register_policy
import numpy as np

@register_policy("my_model")
class MyPolicy(Policy):
    def predict(self, obs: dict) -> np.ndarray:
        # obs["qpos"]       → (4,)  float32  AGX V0
        # obs["image_fpv"]  → (3, H, W) float32 [0,1]
        ...
    def reset(self) -> None: ...
```

Set `policy.name: my_model` in any eval YAML — the CLI picks it up automatically.

## Adding a new backend

Implement `SimBackend` from `testbed.backends.base`:

```python
class MySimBackend(SimBackend):
    def reset(self, seed=None): ...   # returns timestep-like object
    def step(self, action): ...       # returns timestep-like object
    def render(self, camera_id, h, w): ...
    @property
    def dt(self) -> float: ...
```

Add a `backend_type` entry in `eval/tasks.py` and a factory branch in `EvalSuite._make_env()`.

## Legacy

The original PACT ACT-coupled code lives in `legacy/`. It is frozen.
