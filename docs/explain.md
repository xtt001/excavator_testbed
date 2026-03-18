# Excavator Testbed — Current State & AGX Migration Guide

> **Audience:** Team members onboarding to the testbed, or anyone planning the AGX Dynamics + joystick teleop integration.  
> **Last updated:** 2026-03-17

---

## 1. What Has Been Built

### 1.1 Goal

The testbed is a **clean, model-agnostic imitation learning platform** for engineering machinery (excavator / loader). The near-term goal is not perfect physics but a reproducible pipeline that answers:

- Is ACT a viable policy for our excavation scenario?
- Which learning approach wins under a fixed, fair evaluation?
- Where are the bottlenecks — model, action interface, or evaluation design?

### 1.2 Validated Pipeline

The full pipeline has been smoke-tested end-to-end on the proxy task `sim_transfer_cube_scripted` (dual-arm vx300s, 14-DOF):

| Stage | Status | Notes |
|---|---|---|
| Scripted data collection → HDF5 | ✅ | Two-phase EE→joint replay pipeline |
| ACT training on GPU | ✅ | val_loss 74.6 → 0.087 over 500 epochs |
| Policy rollout + evaluation | ✅ | 10% success @ 39 demos / 500 epochs |
| MP4 video output with reward overlay | ✅ | Per-rollout videos saved automatically |

The proxy task was chosen only to **validate that every component connects correctly**. The excavator task and expert teleop data collection are the real next milestone.

---

## 2. Architecture Overview

The testbed is structured around **5 stable, decoupled modules**. The core never imports any specific backend or policy — everything is swappable via config.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CLI / Runner                                  │
│  cli/record.py   cli/train.py   cli/eval.py   runtime/runner.py     │
└────────┬──────────────┬─────────────────┬────────────────┬──────────┘
         │              │                 │                │
         ▼              ▼                 ▼                ▼
   ┌──────────┐  ┌────────────┐  ┌─────────────┐  ┌──────────────┐
   │ Sim      │  │ Data       │  │ Policy      │  │ Eval         │
   │ Backend  │  │ Recorder / │  │ Plugin      │  │ Suite        │
   │ (ABC)    │  │ Dataset    │  │ (ABC)       │  │              │
   └──────────┘  └────────────┘  └─────────────┘  └──────────────┘
         │
   ┌─────┴──────┐
   │ MuJoCo     │  ← only current implementation
   │ Backend    │
   └────────────┘
```

### 2.1 Module 1 — Sim Backend (`testbed/backends/`)

The `SimBackend` ABC defines the only interface the testbed core ever calls:

```python
class SimBackend(ABC):
    def reset(self, seed: int | None = None) -> Any: ...
    def step(self, action: np.ndarray) -> Any: ...
    def render(self, camera_id: str, height: int, width: int) -> np.ndarray: ...
    def set_initial_object_pose(self, pose: np.ndarray) -> None: ...
    @property def dt(self) -> float: ...
    @property def max_reward(self) -> float: ...
```

**Contract for `step()` return value** — the returned timestep must have:
- `.observation` → dict with keys `qpos`, `qvel`, `images`, `env_state`
- `.reward` → float

The current `MuJoCoSimBackend` wraps dm_control and satisfies this contract. Any new backend (AGX, Isaac, etc.) only needs to implement the same 6 methods.

### 2.2 Module 2 — State Interface (`testbed/state/`)

`StateConverter` turns the raw `obs` dict into a typed `StructuredState`:

```
raw obs dict  →  StructuredState
  qpos             .qpos        (N,) float32
  qvel             .qvel        (N,) float32
  images           .images      dict[str, (H,W,3) uint8]
  env_state        .env_state   (M,) float32
                   .tip_pos     dict[site → (3,) xyz]   ← FK-populated
                   .tip_mat     dict[site → (3,3)]
```

`StructuredState.as_policy_input()` flattens this into the dict that every `Policy.predict()` receives. Policies never touch raw obs dicts.

### 2.3 Module 3 — Data Recorder / Dataset (`testbed/data/`)

**`EpisodeRecorder`** buffers one episode in memory and flushes to HDF5 on `save()`.

**HDF5 schema v1.0** (add-only, never remove fields):

```
episode_N.hdf5
├── metadata/
│   ├── schema_version   "1.0"
│   ├── task_name        str
│   ├── sim_backend      str        e.g. "mujoco_ee"
│   ├── seed             int
│   ├── param_version    str
│   └── timestamp        ISO 8601
├── observations/
│   ├── qpos             (T, Nq) float32
│   ├── qvel             (T, Nq) float32
│   └── images/
│       └── top          (T, H, W, 3) uint8
├── action               (T, Na) float32
└── rewards              (T,)    float32
```

**`EpisodeDataset`** is a PyTorch Dataset that loads these HDF5 files and serves `(obs_chunk, action_chunk)` pairs for training.

### 2.4 Module 4 — Policy Plugin API (`testbed/policies/`)

Policies are registered by name and hot-swapped via YAML config with zero code changes:

```python
@register_policy("my_policy")
class MyPolicy(Policy):
    def predict(self, obs: dict) -> np.ndarray: ...
    def reset(self) -> None: ...
```

Currently implemented:
- `act` — fully wired (ResNet18 + Transformer, temporal aggregation)
- `dummy` — returns zeros, used for pipeline smoke tests
- `diffusion` — stub, `NotImplementedError`

### 2.5 Module 5 — Eval Suite (`testbed/eval/`)

`EvalSuite` runs **fixed-seed rollouts** and produces:
- `metrics.json` — success rate, reward statistics
- `summary.csv` — per-rollout breakdown
- `videos/rollout_XXX.mp4` — MP4 with reward bar overlay

Fixed seeds and task parameters live in `testbed/eval/tasks.py`, not in the suite logic. This ensures evaluations are reproducible and comparable across policy versions.

---

## 3. Data Collection Pipeline (Current)

The current scripted data pipeline is a two-phase process for vx300s bimanual:

```
Phase 1: EE-space rollout
  MuJoCoEESimBackend  +  ScriptedPolicy (waypoints in Cartesian space)
       ↓
  joint_traj = [qpos_0, qpos_1, ..., qpos_T]   (14-DOF, with gripper ctrl)

Phase 2: Joint-space replay
  MuJoCoSimBackend  ←  replay joint_traj step-by-step
       ↓
  episode_replay = [timestep_0, ..., timestep_T]
       ↓
  EpisodeRecorder.save()  →  episode_N.hdf5
```

**Why two phases?** The EE-space env uses MuJoCo's mocap body to specify Cartesian targets (easy to write scripted policies for), but the saved actions must be in joint space so the trained policy operates in the same space during evaluation.

**Current success rate:** ~27% per attempt. `only_save_success=true` filters failures; the system retries up to `num_episodes × 5` attempts. This scripted data is temporary — teleop demos will replace it.

---

## 4. What Needs to Change for AGX Dynamics

### 4.1 What Does NOT Need to Change

Because of the `SimBackend` ABC, **none of the following need modification**:

| Component | Why it's safe |
|---|---|
| `EpisodeRecorder` / HDF5 schema | Only receives `obs` dict, not a backend |
| `EpisodeDataset` | Reads HDF5, never touches the simulator |
| All policies (ACT, dummy, diffusion) | Only call `Policy.predict(obs_dict)` |
| `EvalSuite` | Calls `backend.reset()` / `backend.step()` via ABC |
| `Runner` / CLI | Calls `Runner.record()` / `.train()` / `.eval()` |
| `StructuredState` / `StateConverter` | Converts `obs` dict, backend-agnostic |

### 4.2 What Needs to Be Written

You need to create one new file: **`testbed/backends/agx/backend.py`**, implementing `SimBackend`:

```python
# testbed/backends/agx/backend.py

from testbed.backends.base import SimBackend

class AGXSimBackend(SimBackend):

    def reset(self, seed=None) -> Any:
        # 1. Connect to or restart the AGX simulation
        # 2. Return a timestep-like object with .observation and .reward
        ...

    def step(self, action: np.ndarray) -> Any:
        # 1. Send joint velocity commands to AGX
        # 2. Advance simulation by dt (0.02s)
        # 3. Read back qpos, qvel, camera images, env_state
        # 4. Return timestep with .observation dict and .reward
        ...

    def render(self, camera_id, height, width) -> np.ndarray:
        # Return (H, W, 3) uint8 from AGX camera
        ...

    def set_initial_object_pose(self, pose: np.ndarray) -> None:
        # Place the object (soil/rock/cube) at the given pose in AGX
        ...

    @property
    def dt(self) -> float:
        return 0.02  # 50 Hz

    @property
    def max_reward(self) -> float:
        return ...  # define your success threshold
```

Then register it in the config schema and backend factory so it can be selected via `backend.name: agx` in YAML.

### 4.3 Key Integration Questions for AGX

The following need to be resolved before implementing `AGXSimBackend`:

1. **Communication interface** — Does AGX expose a Python API, a socket/RPC interface, or a shared-memory bridge? This determines how `step()` sends actions and reads observations.

2. **`obs` dict contract** — AGX must return at minimum: `qpos` (joint positions), `qvel` (joint velocities), `images` (camera frames), `env_state` (object state for reward computation). If AGX provides different names, a thin adapter layer maps them.

3. **Timing / synchronization** — MuJoCo steps are synchronous and instant. AGX may run in real-time or faster-than-real-time. The backend must handle this so the rest of the pipeline sees a consistent 50 Hz interface.

4. **Reward function** — The excavator reward (e.g. soil volume dumped into target zone) must be computed either inside AGX or from AGX-provided state in the backend. Define it clearly before connecting the eval suite.

5. **Camera output** — AGX should provide camera images in `(H, W, 3) uint8` format per camera name. Confirm camera names match what the YAML configs expect.

---

## 5. Adding Joystick Teleop

### 5.1 Where It Fits in the Architecture

The plan ([`plan(3).md`](plan(3).md)) defines an `ActionSource` interface that sits alongside `SimBackend`. Teleop is just one `ActionSource` — the recorder doesn't care whether actions come from a joystick, keyboard, or scripted policy.

```
ActionSource (teleop/joystick)
    └── next_action(state) → (action, action_info)
                                    ↓
                            EpisodeRecorder.record(obs, action, ...)
                                    ↓
                              episode_N.hdf5
```

### 5.2 What Needs to Be Written

**`testbed/actions/teleop/joystick.py`** — the joystick action source:

```python
class JoystickTeleop:
    """
    Reads joystick axes at 50Hz and maps them to joint velocity commands.
    """
    def reset(self) -> None: ...

    def next_action(self, state: StructuredState) -> tuple[np.ndarray, dict]:
        # 1. Read joystick axes (e.g. via pygame or inputs library)
        # 2. Map axes → joint velocity vector shape=(action_dim,)
        # 3. Clip to velocity limits
        # 4. Return (action, {"source_type": "teleop", "source_id": "joystick"})
        ...
```

**`testbed/actions/teleop/mapping.py`** — axis-to-joint mapping table (separate from the logic so it can be tuned without touching code).

**`testbed/cli/record_teleop.py`** — the teleop record loop:

```python
# Pseudocode
backend = AGXSimBackend(...)         # or MuJoCoSimBackend for testing
teleop  = JoystickTeleop(mapping)
recorder = EpisodeRecorder(...)

ts = backend.reset()
while not done:
    state = StateConverter().convert(ts.observation)
    action, action_info = teleop.next_action(state)
    ts = backend.step(action)
    recorder.record(ts.observation, action, reward=ts.reward)
recorder.save(success=operator_confirmed_success)
```

**`testbed/cli/replay.py`** — replay verification (mandatory before training):

```python
# Load HDF5, replay actions, confirm the trajectory is reproducible
```

### 5.3 HDF5 Schema Extension for Teleop

The current schema (v1.0) needs these fields added (schema stays add-only):

```
/action_source/type        (T,) string    "teleop"
/action_source/id          (T,) string    "joystick"
/action_source/latency_ms  (T,) float32   optional

/metadata/control_hz       int            50
/metadata/action_semantics string         "joint_velocity"
```

Bump `SCHEMA_VERSION` to `"1.1"` in `testbed/data/schema.py` when these are added.

### 5.4 Key Integration Questions for Joystick Teleop

1. **Joystick library** — `pygame.joystick` is the simplest cross-platform option. `inputs` is another. Confirm which is available / preferred.

2. **Axis mapping** — Which joystick axis controls which excavator joint (swing, boom, stick, bucket)? Start with a YAML mapping file so operators can reconfigure without code changes.

3. **Velocity limits** — Define safe `vel_max` per joint. The teleop module must clip, not the backend.

4. **Success / failure annotation** — With scripted data, success is determined by reward. With teleop, the operator must signal success at episode end. Decide: key press, joystick button, or automatic reward threshold?

5. **Replay verification** — Teleop actions must be replayable in the same sim to confirm dataset correctness. This is critical — silent dataset bugs are the most common failure mode.

---

## 6. Suggested Integration Order

Given the current state, the recommended order of work is:

```
Step 1  AGXSimBackend stub
        └── Implement reset()/step()/render() returning placeholder obs
        └── Confirm the full eval pipeline runs without error (even with random reward)

Step 2  AGX obs contract
        └── Map real AGX state → {qpos, qvel, images, env_state}
        └── Confirm StructuredState populates correctly

Step 3  AGX reward function
        └── Define success condition (soil in dump zone? bucket angle? volume?)
        └── Wire it into backend.max_reward and step().reward

Step 4  Joystick ActionSource + mapping
        └── Test against MuJoCoSimBackend first (no AGX needed)
        └── Confirm 50Hz loop, axis deadzone, velocity clipping

Step 5  CLI: record_teleop.py + replay.py
        └── Record 5 episodes, replay all 5, confirm trajectories match

Step 6  HDF5 schema v1.1
        └── Add action_source and teleop metadata fields
        └── Confirm EpisodeDataset still loads correctly

Step 7  End-to-end: AGX teleop → train ACT → eval on AGX
```

---

## 7. Open Questions to Resolve with the Team

| # | Question | Impact |
|---|---|---|
| 1 | What is the AGX Python/RPC interface? | Determines entire backend implementation |
| 2 | Does AGX run faster-than-realtime or realtime only? | Determines if eval can be batched quickly |
| 3 | Can AGX be reset programmatically? | Required for `reset(seed)` |
| 4 | What constitutes "success" for the excavator task? | Required for reward function + eval suite |
| 5 | Are AGX camera images available per-frame? | Required for ACT (image-based policy) |
| 6 | Joystick model / axis layout? | Required for mapping.py |
| 7 | Should teleop and eval use the same AGX instance? | Affects deployment architecture |
