# Clean Testbed Build Plan v2 (Teleop-first) — Copy/Paste for Coding AI
**Updated based on latest decisions: Teleop expert demos + 50Hz control + success-rate-first.**

---

## Background / Goal (read first)

We are building an **engineering machinery intelligent excavation** system.  
Near-term goal is NOT perfect physics, but to build a **clean, independent testbed** that supports:

- **Teleoperation (expert demos) → record dataset → replay verification → train policy → evaluate → auto video**
- **Hot-swappable policies** (ACT first, but not locked-in)
- **Backend-swappable simulation** (MuJoCo now; Isaac/AGX/Chrono later)

### What we want to know (decision questions)
Using the same dataset + same eval suite, determine:
1) Is ACT worth deep investment for our scenario?
2) Which learning approach performs best under fixed evaluation?
3) What are the bottlenecks: model vs action/obs interface vs evaluation vs safety?
4) Can we scale to long-horizon, multi-stage cycles later?

---

## V0 Decisions (locked for Step0)

1) **Control frequency:** `50 Hz` (dt=0.02s)  
2) **Data collection mode:** **expert teleop demos** (no takeover/DAgger in Step0)  
3) **Primary metric:** **success_rate**  
4) **Action semantics (V0):** **joint_velocity** (recommended for keyboard teleop)
   - Store in metadata: `action_semantics="joint_velocity"`
   - If later changed to position targets, keep schema compatible and switch by metadata.

5) **Backend for Step0:** **MuJoCo** (fast pipeline). Backend swap later via `SimBackend`.

---

## MVP Acceptance Criteria (Step0)
- Can record teleop demos at 50Hz into HDF5 with metadata
- Can replay HDF5 actions and reproduce the episode
- Can train an ACT policy (plugin) from the dataset
- Can evaluate on a fixed eval suite and output:
  - `metrics.json` (must include success_rate)
  - `summary.csv`
  - `videos/episode_XX.mp4`
- Can hot-swap policies by config (`act` vs `dummy`) without changing env/recorder/eval code

---

## Architecture: 5 Stable Modules (model-independent)

1) **Sim Backend (Env Layer)**  
2) **State Interface (Structured State S_t)**  
3) **Data Recorder / Dataset (HDF5 + metadata/versioning + teleop fields)**  
4) **Trainer + Policy Plugin API (hot-swap)**  
5) **Evaluator Harness (fixed tasks/seeds + success_rate + auto video)**  

> IMPORTANT: testbed core must NOT import ACT. ACT must live under `policies/act/` as a plugin.

---

## Repo Structure (recommended)

repo/
  testbed/
    backends/
      base.py
      mujoco_backend.py
    state/
      state_interface.py
      kinematics.py
    data/
      recorder.py
      hdf5_io.py
      schema.py
      events.py            # optional placeholder
    actions/
      base.py              # ActionSource interface
      teleop/
        keyboard.py        # V0
        mapping.py
    policies/
      base.py
      act/
        adapter.py
        trainer.py
      dummy/
        adapter.py
      diffusion/           # skeleton only
        adapter.py
        trainer.py
    eval/
      suite.py
      metrics.py
      video.py
      tasks.py
    runtime/
      runner.py
      guard.py             # placeholder for Step1+
    configs/
      task_v0.yaml
      eval_v0.yaml
      teleop_v0.yaml
      act_v0.yaml
    cli/
      record_teleop.py
      replay.py
      train.py
      eval.py

---

## Step0 Tasks (do in order)

### Task 0.1 — Define stable interfaces (stubs first)

**SimBackend**
- reset(config)->raw_obs
- step(action)->raw_obs,reward,done,info
- render(camera,h,w)->image
- dt property (expect 0.02s for 50Hz)
- deterministic reset using `seed`

**StructuredState + StateInterface**
- raw_obs -> StructuredState S_t for policy/eval
- V0 required fields:
  - joint_pos (if available), joint_vel
  - images passthrough
  - ee_pos/ee_quat (optional but recommended)
  - step_index and/or timestamp_ns

**ActionSource (Teleop)**
- reset()
- next_action(S_t)->(action, action_info)
- action_info includes:
  - source_type="teleop"
  - source_id="keyboard"
  - (optional) latency_ms

**EpisodeRecorder**
- start(meta)
- add(S_t, action, reward, done, info, action_info)
- finish(success, fail_code)->path

**Policy + Trainer**
- Policy.reset(); Policy.act(S_t)->action
- Trainer.fit(dataset,cfg)->ckpt; load(ckpt)->Policy

**EvalSuite**
- run(policy, env, fixed_tasks, cfg)->metrics + artifacts (videos)

---

### Task 0.2 — Implement MuJoCoBackend wrapper (no behavior changes)
- Encapsulate all dm_control calls in `mujoco_backend.py`
- raw_obs keys: qpos, qvel, images (contacts optional)
- Enforce dt=0.02s if possible (or resample in runner)

---

### Task 0.3 — Implement StateInterface V0 + FK (working minimal)
- Convert raw_obs -> S_t
- Add bucket tip / EE pose if possible using MuJoCo site pose
- If site missing: return None and warn (do not crash)

---

### Task 0.4 — Implement Teleop (Keyboard) at 50Hz
- Keyboard mapping to joint velocities:
  - e.g., WASD controls swing/boom; arrows for stick/bucket (adjust mapping later)
- Output action vector shape=(action_dim,)
- Clip to vel_limits in teleop module (soft safety)

---

### Task 0.5 — Recorder schema (HDF5) with teleop + metadata (add-only)
Required fields:

/observations/qpos                 (T, D) float64  # if available
/observations/qvel                 (T, D) float64
/observations/images/{cam}         (T, H, W, 3) uint8
/action                            (T, A) float64
/timestamps/step_index             (T,) int64
# optional if available:
/timestamps/step_ns                (T,) int64

/action_source/type                (T,) string  # "teleop" | "policy" | ...
/action_source/id                  (T,) string  # "keyboard" | device name
# optional:
/action_source/latency_ms          (T,) float32

/metadata/schema_version           string
/metadata/sim_backend              string  # "mujoco"
/metadata/task_name                string
/metadata/seed                     int
/metadata/param_version            string
/metadata/control_hz               int      # 50
/metadata/action_semantics         string   # "joint_velocity"
/metadata/camera_names             string[] # e.g. ["top"]

Rule: schema is add-only. Never delete old keys.

---

### Task 0.6 — CLI: record teleop demos + replay verification (must-have)
Deliverables:
- `cli/record_teleop.py`:
  - create env with fixed config
  - run teleop at 50Hz
  - record HDF5 episodes
  - auto-save a quick video

- `cli/replay.py`:
  - load HDF5 episode
  - replay recorded actions in env
  - verify the motion is reproducible
  - output replay video

This is critical to ensure dataset correctness.

---

### Task 0.7 — Policies: ACT plugin + Dummy policy
- `policies/act/` adapter + trainer (wrap existing ACT pipeline)
- `policies/dummy/` returns zeros or hold-last (fully working)
- `policies/diffusion/` skeleton only (adapter/trainer TODO)

Hot-swap proof:
- config changes `policy.name=act` → `policy.name=dummy`
- no other code changes required

---

### Task 0.8 — EvalSuite V0 (success-rate-first + auto videos)
Define `eval_suite_v0`:
- fixed list of tasks + fixed seeds
- horizon/timeouts fixed
- camera fixed

Metrics V0:
- **success_rate** (primary)
- episode_duration (secondary)
- action_delta/jerk_proxy (secondary)

Auto artifacts:
- metrics.json
- summary.csv
- videos/

---

## V0 Task definition (for success-rate evaluation)
We need a V0 success definition that is easy and stable.

### Proposed V0 task: "Lift-and-place cube" (proxy task)
- Objective: move cube into a target tray/region and keep it stable for N steps
- Success = cube center within tray bounds for >= N consecutive steps (e.g. N=25 at 50Hz = 0.5s)

This matches existing proxy setup (cube → tray) and is compatible with teleop demos.

Configuration parameters (task_v0.yaml):
- tray center + size (x_range, y_range, z_range)
- required_hold_steps: 25
- max_steps: 500 (10 seconds)

---

## Engineering Standards (short, mandatory)

- Installable package via `pyproject.toml` and `pip install -e .` (no sys.path hacks)
- Formatting: black (88), lint: ruff, imports: isort, pre-commit enabled
- Config: pydantic + PyYAML (typed validation)
- No artifacts committed (datasets/videos/checkpoints in gitignore)
- Every run saves config + git commit hash + metrics to run folder

---

## Notes / pitfalls (teleop edition)
- Keep action semantics consistent across teleop → record → replay → train → eval.
- Store `control_hz=50` and action_semantics in metadata.
- Replay is mandatory; otherwise teleop dataset may silently be wrong.
- Keep eval suite fixed; otherwise success_rate comparisons are meaningless.

---

## Next milestone (1–2 weeks)
- Teleop record → replay → train(act) → eval(act) runs end-to-end
- Eval suite fixed; outputs success_rate + videos
- Hot-swap demo works (act vs dummy)

After Step0:
- Add Guard V1 + PhaseRouter V1
- Add takeover events + slicing (DAgger-ready)
- Add second real baseline (diffusion/RDP) using same testbed