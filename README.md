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
| AGX socket protocol (binary framing, step-ack) | ✅ implemented and strict smoke-tested |
| `AGXSimBackend` (`SimBackend` ABC) | ✅ implemented and live smoke-tested |
| HDF5 schema v1.1 (timestamps, action_source, env_state, fpv) | ✅ implemented |
| `EpisodeRecorder` v1.1 | ✅ implemented and live teleop recording tested |
| `JoystickActionSource` (pygame, dual-stick FarmStick, smoothing, button reset) | ✅ implemented |
| `KeyboardActionSource` (pygame, WASD+arrows fallback) | ✅ implemented |
| `tb-record-teleop` CLI | ✅ live HDF5 recording tested against Unity |
| `tb-replay` CLI + QA diff report | ✅ live replay path tested against Unity |
| Eval suite: AGX target-mass success rule + mission reward | ✅ implemented |
| ACT policy adapter + trainer | ✅ AGX 4D train path fixed and smoke-trained |
| ACT live eval path | ✅ checkpoint loading + live rollouts tested |
| Dummy policy | ✅ retained for smoke / baseline checks |
| MuJoCo backend | ✅ retained (legacy, not primary) |
| Current V0 task scope | ✅ stationary digging only, 4D arm action space |
| Current pilot policy quality | ⚠️ plumbing works, smoke checkpoint still fails digging eval |

**Current focus:** collect more demos, evaluate the main V0 checkpoint, and improve
training/data quality. The main plumbing loop is now working end to end.

---

## Quick start

### 1. Install

```bash
conda activate aloha
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
tb-record-teleop --config testbed/configs/teleop_v0.yaml --input keyboard --num-episodes 5

# dual-stick FarmStick / pygame joystick
tb-record-teleop --config testbed/configs/teleop_v0.yaml --input joystick --num-episodes 5
```

Episodes are saved to `data/agx_teleop/episode_N.hdf5` (schema v1.1).

Current V0 scope:
- fixed-position / stationary digging only
- action space is 4D arm control only: `[swing, boom, stick, bucket]`
- track / drive / steer are intentionally out of scope for V0 teleop data

### 4. Replay QA

```bash
tb-replay --episode data/agx_teleop/episode_0.hdf5 --config testbed/configs/teleop_v0.yaml
# QA — qpos diff: mean=X  max=X  (over N replayed steps)

tb-replay --episode data/agx_teleop/episode_0.hdf5 --config testbed/configs/teleop_v0.yaml --save-video
# writes runs/replay/episode_0_replay.mp4
```

### 5. Train ACT

```bash
# offline training: Unity does not need to be running
tb-train --config testbed/configs/act_agx_v0.yaml
```

### 6. Evaluate

```bash
# smoke eval on the small smoke checkpoint
tb-eval --config testbed/configs/eval_agx_smoke.yaml

# final V0 eval on the main checkpoint
tb-eval --config testbed/configs/eval_agx_v0.yaml
# outputs: runs/eval/agx_excavation/*.mp4 + runs/eval/agx_excavation/results/{metrics.json,results.csv}
```

`tb-eval` is a live rollout command. Unity must be running and listening on the
configured AGX host/port. `tb-train` is offline and only reads recorded HDF5
episodes.

### 7. Current V0 run sequence

```bash
conda activate aloha

# 1) live bridge check
python scripts/agx_smoke.py --host 127.0.0.1 --port 5057 --steps 500 --strict

# 2) collect pilot demos
tb-record-teleop --config testbed/configs/teleop_v0.yaml --input joystick --num-episodes 5

# 3) replay one episode back through Unity
tb-replay --episode data/agx_teleop/episode_0.hdf5 --config testbed/configs/teleop_v0.yaml --save-video

# 4) offline training
tb-train --config testbed/configs/act_agx_v0.yaml

# 5) live evaluation
tb-eval --config testbed/configs/eval_agx_v0.yaml
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
terrain initialization is only applied once per episode reset path, and that
`reset_terrain: true` rebuilds the deformable terrain state so soil particles
remaining in the bucket are returned to the initial terrain baseline.

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
    suite.py                  ← EvalSuite — AGX mission reward + target-mass success
    tasks.py                  ← EvalTaskDef per task (agx_excavation_teleop + legacy)
    metrics.py                ← EvalMetrics → metrics.json + summary.csv
    video.py                  ← MP4 with reward overlay
  configs/
    agx_v0.yaml               ← AGX host/port/dims
    teleop_v0.yaml            ← Teleop session config (joystick mapping, episode params)
    eval_agx_smoke.yaml       ← Small live eval smoke config
    eval_agx_v0.yaml          ← AGX eval suite (success rule, num_rollouts)
    act_agx_smoke.yaml        ← Small offline train smoke config
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

Useful artifact paths:
- `data/agx_teleop/episode_N.hdf5` — canonical recorded demos
- `runs/ckpts/agx_excavation_act_smoke/` — smoke checkpoints + plots
- `runs/ckpts/agx_excavation_act_v0/` — main V0 checkpoints + plots
- `runs/eval/agx_excavation_smoke_results/metrics.json` — smoke eval metrics
- `runs/eval/agx_excavation/results/metrics.json` — main V0 eval metrics

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
- `env_state (9,)` —
  `[mass_in_bucket_kg, excavated_mass_kg, mass_in_target_box_kg, deposited_mass_in_target_box_kg, min_distance_to_target_m, target_hard_collision_count, target_contact_max_normal_force_n, min_distance_to_dig_area_m, bucket_depth_below_dig_area_plane_m]`
- `images["fpv"]` — `(H, W, 3)` uint8

Collision-field semantics:
- `min_distance_to_target_m` is the approximate minimum distance between the bucket target-distance proxy volume and the active target distance geometry
- in the current Unity scene that bucket proxy volume is editor-configurable on `ExcavationMassTracker`
- on the target side Unity now prefers target hard box shapes and only falls back to a dedicated target-distance volume when those shapes are unavailable
- for `TruckBed`, helper `*FailureVolume` shapes such as the dump/top failure volumes are excluded from that target-side geometry set
- `target_hard_collision_count` is cumulative within the current episode
- a continuous excavator-vs-target contact session increments the count at most once
- the count can increase again only after the excavator leaves the target and later touches it again
- `target_contact_max_normal_force_n` is the current-step maximum monitored normal force
- when the active target is `TruckBed`, collision monitoring covers the whole `BedTruck` hard body, not only the bed/trunk measurement region
- `min_distance_to_dig_area_m` is the approximate minimum distance between the bucket measurement volume and the scene `DigArea`
- `bucket_depth_below_dig_area_plane_m` is `max(0, dig_plane_y - bucket_world_min_y)` and only becomes positive when the bucket volume goes below the DigArea plane

**Mission reward (Repo A / testbed):**
- `loading`: reward grows only after a qualified DigArea good start, meaning bucket load increases while the bucket measurement volume touches the DigArea region and goes below the DigArea plane
- `approaching_target`: reward grows when a loaded bucket moves closer to the active target
- `depositing`: reward grows when target retained mass starts increasing
- `retained_success`: reward reaches max when retained target mass stays above the success threshold long enough
- `hard_target_collision`: if cumulative `target_hard_collision_count` increases on this step, Repo A subtracts one fixed `0.75` penalty for that step

**Success rule (current V0 default):**
`deposited_mass_in_target_box_kg ≥ 100.0 kg` for `25` consecutive steps within
the `1000`-step episode.

Current reward/success ownership:
- Repo B now mirrors `deposited_mass_in_target_box_kg` into `STEP_RESP.reward`
  as a backup success proxy
- Repo A computes the excavation mission reward locally from exported `env_state`
- success is computed from retained target mass, not from Unity reward
- older 5D / 7D episodes remain readable; missing DigArea or collision fields fall back to legacy defaults

Here "post-hoc" means:
- first record the raw episode: observations, actions, images, env_state
- later run evaluator / analysis logic over the saved episode or rollout
- derive `success` from the retained target-mass series instead of trusting a live
  simulator reward or a manual operator flag

Live Repo A <-> Repo B interaction uses the binary TCP step-ack protocol above.
HDF5 is the offline dataset artifact written by Repo A. Unity-local
`metadata.json` / `steps.jsonl` / `.rgb24` exports are auxiliary sidecar
artifacts, not the shared live interaction contract.

Command ownership:
- `tb-record-teleop` — live Python teleop → Unity step-ack → HDF5
- `tb-replay` — live Unity replay of a recorded HDF5 episode
- `tb-train` — offline HDF5 training only
- `tb-eval` — live policy rollout against Unity

Current Unity-side runtime notes:
- terrain reset is handled by Unity `ResetTerrain` / `SceneResetService`; the
  excavation metrics component no longer mutates terrain heights during reset
- pending step-ack requests are consumed on Unity `FixedUpdate`, so external
  teleop stepping is aligned to `Time.fixedDeltaTime` rather than Editor render
  frame timing

---

## HDF5 schema v1.1

```
episode_N.hdf5
├── metadata/           schema_version="1.1", task_name, sim_backend, control_hz,
│                       dt, action_semantics, camera_names, image_format, seed, ...
├── observations/
│   ├── qpos            (T, 4)  float32  [swing, boom, stick, bucket] position_norm
│   ├── qvel            (T, 4)  float32  [swing, boom, stick, bucket] speed
│   ├── env_state       (T, 9)  float32  [mass_in_bucket, excavated_mass, mass_in_target_box, deposited_mass_in_target_box, min_distance_to_target, target_hard_collision_count, target_contact_max_normal_force_n, min_distance_to_dig_area, bucket_depth_below_dig_area_plane]
│   └── images/fpv      (T, H, W, 3) uint8
├── action              (T, 4)  float32  [swing, boom, stick, bucket] speed cmd
├── rewards             (T,)    float32  testbed-defined AGX mission reward
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
