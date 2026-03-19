# AGXUnity ↔ Python Testbed Integration Spec (Step-Ack, Teleop Demos, First-Person Vision)
**Audience:** Unity/AGX team + Python testbed team  
**Purpose:** A single document both sides can implement against (no “interpretation gaps”).  
**Scope (V0):** Expert teleop demos → HDF5 → train (ACT) → eval (success_rate) → auto videos  
**Control rate (V0):** 50 Hz (dt = 0.02s)

---

## 0) Decisions We Already Made (Lock These)
1) **AGXUnity** is the simulation runtime (Unity/C# side).  
2) **Custom C# socket** is the communication bridge (not ROS-TCP).  
3) **First-person camera is required** (driver view).  
4) **V0 transport:** raw image payload is acceptable; **future** may switch to H.264 to reduce latency.  
5) **Stepping model:** implement **strict step-ack** with **manual stepping** (`DoStep()`), because we need replayable, reproducible training data.  
   - AGXUnity supports manual stepping and warns if `DoStep()` is called while auto-stepping is enabled (so we must disable auto-stepping).  [oai_citation:0‡extgit.vtt.fi](https://extgit.vtt.fi/petri.tikka/TREDIH/-/blob/main/Assets/AGXUnity/AGXUnity/Simulation.cs?utm_source=chatgpt.com)  
   - AGXUnity also provides step callbacks (`PreStepForward`, `SimulationPost`, etc.) to reliably set actions and read state at consistent points in the step.  [oai_citation:1‡Algoryx](https://us.download.algoryx.se/AGXUnity/documentation/current/scripting.html?utm_source=chatgpt.com)  
6) **Action semantics (current business chain):** joystick → `OperatorCommand` → actuator/constraint speed (NOT joint position targets).  
7) **Available actuator signals (current):**
   - `*_position_norm` in [0,1]: **boom/stick/bucket only** (no swing_position_norm)
   - `*_speed`: **boom/stick/bucket/swing**
   - `boom_position_norm` / `boom_speed` currently read from `BoomPrismatics[0]` only (not expanded to multiple prismatics)

---

## 1) Why Step-Ack (One Action → One Step → One Observation)
**We choose step-ack** because:
- dataset correctness requires action/obs alignment (no drift due to timing/jitter)
- replay must reproduce the same trajectory
- fixed-seed evaluation requires deterministic stepping

Unity’s `FixedUpdate` timing is not guaranteed to run exactly once per rendered frame; it can “catch up” by running multiple fixed steps when the frame rate drops. The default fixed timestep is 0.02s (50Hz).  [oai_citation:2‡Unity 文档](https://docs.unity3d.com/6000.3/Documentation/Manual/fixed-updates.html?utm_source=chatgpt.com)  
Therefore, we should not rely on “frame rate” to define our dataset step. We rely on our own `step_id` and manual stepping.

---

## 2) High-Level Responsibilities (Two Machines)
### Unity/AGX machine (C#)
- Owns simulation instance, manual stepping, teleop input, cameras, actuator states
- Exposes a socket service that supports:
  - `RESET`
  - `STEP` (step-ack)
  - optional: `GET_INFO` (capabilities)

### Python/testbed machine
- Implements `AGXSimBackend` (remote backend) using the socket protocol
- Records episodes to HDF5 (schema v1.1)
- Trains policies (ACT plugin)
- Evaluates policies on fixed tasks/seeds and produces metrics + videos

> Keep Unity project and Python testbed in separate repos.  
> Keep **protocol + schema** in a shared folder/repo to prevent drift.

---

## 3) Socket Protocol (V0)
### 3.1 Transport assumptions
- TCP socket, binary framing
- All messages include a fixed header:
  - `magic` (uint32)
  - `version` (uint16) = 1
  - `msg_type` (uint16)
  - `payload_len` (uint32)
  - `crc32` (uint32) optional but recommended

### 3.2 Message Types
- `GET_INFO_REQ` / `GET_INFO_RESP`
- `RESET_REQ` / `RESET_RESP`
- `STEP_REQ` / `STEP_RESP`

### 3.3 Step-Ack Contract
**Python → Unity**
- send `STEP_REQ(step_id=k, action=...)`
**Unity**
- applies action
- advances simulation by exactly 1 logical step (dt=0.02)
- returns `STEP_RESP(step_id=k, obs=...)`

**Hard rule:** `STEP_RESP.step_id` must equal the request `step_id`.

---

## 4) Action Contract (V0)
### 4.1 Action semantics
- **Action is actuator speed command vector** (matches current joystick semantics)
- `action_semantics = "actuator_speed"`

### 4.2 Action vector layout (V0)
We standardize action ordering to avoid training confusion:

`action = [swing_speed_cmd, boom_speed_cmd, stick_speed_cmd, bucket_speed_cmd]`

Units:
- cmd values are normalized in [-1, 1] OR physical units — decide ONE and document in metadata.
- If you already have scaling/deadzone, output should be the **post-deadzone, post-scale** command (so replay matches exactly what AGX received).

**Required metadata (stored per episode):**
- `control_hz = 50`
- `dt = 0.02`
- `action_semantics = "actuator_speed"`
- per-joint `deadzone`, `scale`, `limit` (either embedded in YAML saved with run, or stored in HDF5 metadata)

---

## 5) Observation Contract (V0)
Python testbed expects `obs` dict with keys:
- `qpos` (float32 array)
- `qvel` (float32 array)
- `images` (dict of cameras)
- `env_state` (float32 array; can include mass_in_bucket, etc.)
- `tip_pos` optional (float32[3]) if available

### 5.1 Standardized qpos/qvel layout (IMPORTANT)
Because AGX doesn’t expose classic joint vectors yet, we define qpos/qvel based on available actuators:

**qpos (V0) = normalized positions** (range [0,1])  
Ordering (length 3):
- `boom_position_norm`  (from BoomPrismatics[0])  
- `stick_position_norm`
- `bucket_position_norm`

**qvel (V0) = actuator speeds**  
Ordering (length 4):
- `swing_speed`
- `boom_speed`   (from BoomPrismatics[0])  
- `stick_speed`
- `bucket_speed`

Notes:
- There is currently **no** `swing_position_norm`. In V0, swing position is omitted from qpos.
- The “boom prismatic list” issue: V0 uses `BoomPrismatics[0]`. Future versions may expand to multiple boom prismatics; if so we must bump schema + version.

### 5.2 First-person camera (required)
`images["fpv"]` must be deliverable to Python.
- V0 format (raw): `(H, W, 3) uint8`
- If using RenderTexture, V0 implementation can use `ReadPixels` to pull into Texture2D, then `GetRawTextureData()` to bytes.
  - `ReadPixels` requires setting the RenderTexture active; otherwise it reads the wrong buffer.  [oai_citation:3‡Stack Overflow](https://stackoverflow.com/questions/77725975/unity-texture2d-readpixels-not-reading-correctly-from-rendertexture?utm_source=chatgpt.com)
  - Unity community references standard pattern: create Texture2D, ReadPixels from RenderTexture.  [oai_citation:4‡Unity Discussions](https://discussions.unity.com/t/convert-a-rendertexture-to-a-texture2d/946?utm_source=chatgpt.com)
- Future (V1): H.264 encoded bytes + decode in Python (lower latency/bandwidth).

Camera metadata to report in `GET_INFO_RESP` and store in HDF5:
- name: `"fpv"`
- width, height
- fps (actual or target)
- color format (RGB)

### 5.3 env_state (optional but recommended)
Include any extra signals useful for success definition / debugging:
- `mass_in_bucket` (recommended)
- terrain reset counters, etc.

---

## 6) Manual Stepping & Callback Placement (Unity/AGX)
### 6.1 Manual stepping requirement
- Disable auto-stepping
- Use manual stepping `DoStep()` per `STEP_REQ`  
AGXUnity provides step callbacks; recommended usage:
- Apply action in `PreStepForward` (or just before stepping)
- Read back actuator states + env_state in `SimulationPost`/`SimulationLast`
 [oai_citation:5‡Algoryx](https://us.download.algoryx.se/AGXUnity/documentation/current/scripting.html?utm_source=chatgpt.com)

### 6.2 Fixed timestep
- Set Unity fixed timestep to 0.02s (50Hz) (`Edit/Project Settings/Time/Fixed Timestep`)
Unity docs show 0.02s default fixed timestep.  [oai_citation:6‡Unity 文档](https://docs.unity3d.com/6000.3/Documentation/Manual/fixed-updates.html?utm_source=chatgpt.com)

> Even with fixed timestep, Unity may execute multiple fixed steps per rendered frame to catch up. Step-ack avoids ambiguity.

---

## 7) Reset Contract (V0)
We currently have partial reset support (terrain reset + counters). For V0 evaluation we need at least:
- return excavator to a known pose
- reset bucket load state / relevant counters
- reset camera transform if needed

### 7.1 RESET_REQ fields (V0)
- `seed` (int32) — optional
- `scenario_id` (string) — optional, for future eval suites
- `reset_terrain` (bool)
- `reset_pose` (bool)

### 7.2 Determinism (V0)
- V0 does **not** require perfect seed determinism across all terrain randomness,
  but does require **repeatable baseline reset** (same initial pose and empty bucket state).
- Record in metadata whether reset was deterministic:
  - `metadata/reset_mode = "baseline_fixed"` (V0)
  - later: `metadata/reset_mode = "seeded_deterministic"`

---

## 8) Success Definition (V0, success_rate-first)
We will define success in Python evaluator (backend-agnostic) using signals in obs/env_state.

### Recommended V0 success (mass-based)
Success if:
- `mass_in_bucket >= M_thresh` for at least `hold_steps` consecutive steps  
Example defaults:
- `M_thresh = team_defined` (units from AGX)
- `hold_steps = 25` (0.5s @ 50Hz)

Fallback if mass_in_bucket unavailable:
- Success = bucket position_norm indicates “scooped posture” + stick/boom within bounds for hold_steps

### Required outputs from Unity to support success
- env_state contains `mass_in_bucket` (preferred)
- plus qpos/qvel as defined above

---

## 9) HDF5 Schema v1.1 (Add-only from current v1.0)
Existing v1.0:
- observations/qpos, observations/qvel, observations/images/top, action, rewards, metadata

**v1.1 additions:**
/metadata/control_hz           int32       = 50
/metadata/dt                  float32     = 0.02
/metadata/action_semantics     str         = “actuator_speed”
/metadata/camera_names         [str]       = [“fpv”]
/metadata/camera_fps           int32       (or float32)
/action_source/type            (T,) str    = “teleop” | “policy” | …
/action_source/id              (T,) str    = “joystick” | “operator_x”
/timestamps/step_id            (T,) int64
/timestamps/step_ns            (T,) int64  (optional)
/observations/images/fpv       (T, H, W, 3) uint8   # V0 raw
/observations/env_state        (T, M) float32       # includes mass_in_bucket if available

**Add-only rule:** never remove old fields. Bump `schema_version` from "1.0" → "1.1".

---

## 10) Implementation Plan (Two Teams)
### Unity/AGX Team (C#)
1) Implement socket server with `GET_INFO/RESET/STEP`
2) Implement manual stepping:
   - disable auto-stepping
   - `STEP_REQ` → apply action → `DoStep()` → sample obs → `STEP_RESP`
3) Implement fpv frame export (V0 raw):
   - RenderTexture → Texture2D.ReadPixels → RGB bytes
4) Export actuator signals as standardized vectors:
   - qpos(3) = boom/stick/bucket position_norm ([0,1]) with boom from BoomPrismatics[0]
   - qvel(4) = swing/boom/stick/bucket speeds (boom from BoomPrismatics[0])
5) Export env_state with at least mass_in_bucket (if available)

### Python/Testbed Team
1) Add `testbed/backends/agx/backend.py` implementing `SimBackend` via socket
2) Implement strict step-ack wait:
   - send STEP_REQ(step_id)
   - block until STEP_RESP(step_id matches)
3) Extend recorder schema to v1.1 (add-only)
4) Add teleop recorder:
   - for now, action_source/type="teleop"
5) Implement replay:
   - replay HDF5 actions back through AGX backend
6) Add V0 evaluator success rule (mass_in_bucket-based)

---

## 11) Known Hard Points / Risks
1) **RenderTexture → uint8 export performance**
   - V0 should prioritize correctness over speed (ReadPixels), optimize later.
   - Ensure correct buffer activation before ReadPixels.  [oai_citation:7‡Stack Overflow](https://stackoverflow.com/questions/77725975/unity-texture2d-readpixels-not-reading-correctly-from-rendertexture?utm_source=chatgpt.com)
2) **State standardization**
   - Missing swing_position_norm is OK in V0, but must be documented.
   - BoomPrismatics multi-element not expanded in V0; if expanded later, bump schema.
3) **Reset determinism**
   - V0 baseline fixed reset is OK, but eval suite comparability depends on stable initial state.
4) **Image bandwidth**
   - Raw RGB is acceptable for V0; plan H.264 for V1.

---

## 12) Minimal “Info We Still Need” (to finalize constants, not architecture)
Please fill these in once known (can be updated without breaking API):
- fpv resolution (W×H) and target fps
- action command range after scaling (e.g., [-1,1]) and per-actuator limits
- mass_in_bucket units + reasonable M_thresh for V0
- whether Unity step uses 1 DoStep or multiple substeps per command (but must appear as 1 step externally)

---

## Appendix A: Message Field Definitions (Suggested)
### STEP_REQ
- `step_id` (int64)
- `action` (float32[4])  # swing, boom, stick, bucket speed commands
- `timestamp_ns` (int64) optional

### STEP_RESP
- `step_id` (int64)
- `qpos` (float32[3])   # boom/stick/bucket position_norm
- `qvel` (float32[4])   # swing/boom/stick/bucket speeds
- `env_state` (float32[M]) including mass_in_bucket at a known index
- `image_fpv` (bytes) raw RGB or encoded (flag in header)
- `image_w`, `image_h` (int32)
- `reward` (float32) optional; V0 can be 0 and computed in Python

### GET_INFO_RESP
- supported cameras, fps, image format
- actuator vector sizes and ordering
- dt/control_hz
- backend version strings

---

## Appendix B: Why Unity FixedUpdate Alone Is Not Enough
Unity fixed timestep is 0.02s by default (50Hz), but FixedUpdate calls may bunch up depending on frame time.  [oai_citation:8‡Unity 文档](https://docs.unity3d.com/6000.3/Documentation/Manual/fixed-updates.html?utm_source=chatgpt.com)  
Therefore, **dataset step** should be driven by explicit step_id + manual DoStep, not by frame count.

---


# protocol.md — AGXUnity ↔ Python Testbed Integration Spec (V0)
Audience: Unity/AGX team + Python testbed team  
Last updated: 2026-03-18  
Scope (V0): Expert teleop demos → HDF5 → train (ACT) → eval (success_rate) → auto videos  
Control rate (V0): 50 Hz (dt = 0.02s)

---

## 0) Locked Decisions (Do NOT change without joint review)
1) Simulator = **AGXUnity (Unity/C#)**  
2) Communication = **custom C# TCP socket** (NOT ROS-TCP)  
3) Stepping = **strict step-ack** using **manual DoStep()**  
4) Vision = **first-person camera required** (“driver view”)  
5) Image transport: **V0 raw RGB**; **V1 optional H.264**  
6) Action semantics (current business chain): joystick → OperatorCommand → **actuator/constraint speed**  
7) Available actuator signals (current):
   - `boom/stick/bucket_position_norm` in **[0,1]** (no `swing_position_norm`)
   - `swing/boom/stick/bucket_speed`
   - `boom_position_norm`/`boom_speed` currently uses **BoomPrismatics[0] only** (not expanded)

---

## 1) Why Step-Ack (One Action → One Step → One Observation)
We require step-ack because we need:
- correct action/obs alignment (training data validity)
- replayable episodes (dataset correctness)
- reproducible eval suite (fair model comparison)

**Hard rule**: Python sends `STEP_REQ(step_id=k, action=...)`. Unity must return `STEP_RESP(step_id=k, obs=...)` for the same k.

---

## 2) Two-Machine Responsibilities
### Unity/AGX machine (C#)
- Owns simulation instance, manual stepping, cameras, actuator states
- Runs socket server supporting: GET_INFO / RESET / STEP

### Python/testbed machine
- Implements AGXSimBackend (remote SimBackend) via this socket protocol
- Records HDF5 episodes (schema v1.1)
- Trains policies (ACT plugin)
- Evaluates policies on fixed tasks/seeds → metrics + videos

---

## 3) Socket Protocol (V0)
### 3.1 Transport
- TCP
- Framed messages (binary header + payload)

### 3.2 Header (recommended)
- magic: uint32 (e.g., 0xA6A6A6A6)
- version: uint16 (1)
- msg_type: uint16
- payload_len: uint32
- (optional) crc32: uint32

### 3.3 Message types
- GET_INFO_REQ / GET_INFO_RESP
- RESET_REQ / RESET_RESP
- STEP_REQ / STEP_RESP

---

## 4) Action Contract (V0)
### 4.1 Semantics
`action_semantics = "actuator_speed_cmd"`

### 4.2 Action vector layout (length 4, fixed order)
`action = [ swing_speed_cmd, boom_speed_cmd, stick_speed_cmd, bucket_speed_cmd ]`

### 4.3 Command value convention (choose one and lock in metadata)
Option A (recommended): normalized command in `[-1, 1]`  
Option B: physical units (must document units)

**Important**: Commands sent via STEP_REQ should be **post-deadzone, post-scale**, i.e., exactly what AGX receives, so replay is identical.

### 4.4 Required metadata per episode
- control_hz = 50
- dt = 0.02
- action_semantics = "actuator_speed_cmd"
- deadzone[4], scale[4], limit[4] (store in HDF5 metadata or sidecar YAML copied into run folder)

---

## 5) Observation Contract (V0)
Unity must return a timestep-like object:
- observation: dict with keys `qpos`, `qvel`, `images`, `env_state`
- reward: float (optional; V0 can be 0 and computed in Python)

### 5.1 Standardized qpos/qvel layout (V0)
Because we currently do not have full joint vectors, we standardize based on available actuators.

**qpos (len=3, normalized [0,1])**
1) boom_position_norm  (from BoomPrismatics[0])  
2) stick_position_norm  
3) bucket_position_norm  

**qvel (len=4, actuator speeds)**
1) swing_speed  
2) boom_speed  (from BoomPrismatics[0])  
3) stick_speed  
4) bucket_speed  

Notes:
- No swing_position_norm in V0.
- Boom uses BoomPrismatics[0] only in V0. Expanding this later is a versioned change.

### 5.2 First-person camera (required)
- Camera key name: `"fpv"`
- V0 image format: raw RGB `(H, W, 3) uint8`
- If Unity runs the camera as a RenderTexture, convert to bytes in STEP_RESP.

V1 image format: H.264 bytes (optional)
- Include `image_format` in GET_INFO_RESP and STEP_RESP.

### 5.3 env_state (recommended)
env_state should include at least:
- mass_in_bucket (float) at a known index
- any other debug signals useful for evaluation

---

## 6) Manual Stepping / Step Callbacks (Unity)
### 6.1 Manual stepping requirement
- Disable auto-stepping
- Per STEP_REQ:
  1) Apply action command
  2) DoStep() exactly once (or N substeps internally, but expose as 1 step externally)
  3) Sample states + camera frame
  4) Respond STEP_RESP(step_id=k)

### 6.2 Callback placement (recommended pattern)
- Apply action in a “pre-step” callback
- Read state and env_state in “post-step” callbacks
This avoids reading partially updated state.

---

## 7) Reset Contract (V0)
V0 requires a **baseline fixed reset** (not perfect seeded determinism):
- excavator pose reset to known pose
- bucket load counters reset
- terrain reset supported if available
- camera pose reset if needed

RESET_REQ fields:
- seed: int32 (optional; may be ignored in V0)
- scenario_id: string (optional)
- reset_terrain: bool
- reset_pose: bool

RESET_RESP should confirm:
- reset applied
- current dt/control_hz
- any warning flags

---

## 8) Success Definition (V0, evaluator-side)
Primary metric: success_rate.

Recommended V0 success rule:
- success if `mass_in_bucket >= M_thresh` for `hold_steps=25` consecutive steps (0.5s @ 50Hz)

Fallback if mass_in_bucket unavailable:
- posture-based thresholds on qpos + stability thresholds on qvel

---

## 9) Required GET_INFO Response (V0)
GET_INFO_RESP must include:
- protocol_version
- dt, control_hz
- action_semantics
- action_dim (=4), action_order
- qpos_dim (=3), qpos_order
- qvel_dim (=4), qvel_order
- available cameras: ["fpv"]
- camera width/height/fps and image_format(s)
- env_state layout and indices (e.g., mass_in_bucket index)

---

## 10) STEP Message Payloads (Recommended)
### STEP_REQ
- step_id: int64
- action: float32[4]
- (optional) client_time_ns: int64

### STEP_RESP
- step_id: int64
- qpos: float32[3]
- qvel: float32[4]
- env_state: float32[M]
- image_format: str ("raw_rgb" | "h264")
- image_w, image_h: int32
- image_payload: bytes (raw RGB or encoded)
- reward: float32 (optional)
- (optional) sim_time_ns: int64

---

## 11) Versioning Rules
- Any change to vector ordering, dims, or semantics requires:
  - protocol version bump and joint review
  - schema version bump if it impacts dataset


# schema.md — HDF5 Dataset Schema v1.1 (Add-only)
Audience: Python/testbed team + data consumers  
Last updated: 2026-03-18  
Rule: **Add-only**. Never remove fields. New fields must be optional/default-safe.

---

## 1) File layout
`episode_XXXX.hdf5`

### 1.1 /metadata (required)
- schema_version: "1.1"
- task_name: str
- sim_backend: str ("agxunity" | "mujoco" | ...)
- seed: int32 (use -1 if unused)
- param_version: str
- timestamp: ISO 8601 str
- control_hz: int32 (50)
- dt: float32 (0.02)
- action_semantics: str ("actuator_speed_cmd")
- camera_names: str[] (["fpv"])
- camera_width: int32
- camera_height: int32
- image_format: str ("raw_rgb" for V0; "h264" in future)

Optional recommended:
- operator_id: str
- session_id: str
- deadzone: float32[4]
- scale: float32[4]
- limit: float32[4]
- protocol_version: str/int

### 1.2 /timestamps (required)
- step_id: (T,) int64
Optional:
- step_ns: (T,) int64   # for remote teleop / profiling

### 1.3 /action_source (required)
- type: (T,) str  # "teleop" | "policy" | "scripted"
- id:   (T,) str  # "joystick" | "keyboard" | "policy:act@<ckpt>"
Optional:
- latency_ms: (T,) float32

### 1.4 /observations (required)
- qpos: (T, 3) float32
  Order: [boom_position_norm, stick_position_norm, bucket_position_norm]
- qvel: (T, 4) float32
  Order: [swing_speed, boom_speed, stick_speed, bucket_speed]
- env_state: (T, M) float32
  Must include mass_in_bucket at a known index documented in config

- images/
  - fpv: (T, H, W, 3) uint8   # V0 raw RGB

Future option (V1+):
- images/fpv_h264: variable-length bytes + index table
  (only if we switch transport/storage to H.264)

### 1.5 /action (required)
- action: (T, 4) float32
  Order: [swing_speed_cmd, boom_speed_cmd, stick_speed_cmd, bucket_speed_cmd]

### 1.6 /rewards (optional but recommended)
- reward: (T,) float32
V0 can set to 0; success is computed in evaluator.

### 1.7 /labels (optional, future)
- success: bool
- fail_code: str
- phase: str

---

## 2) Replay validity requirement (must-have QA)
A dataset is valid iff:
- Replaying action[t] step-by-step produces a visually consistent rollout
- qpos/qvel time series remain within tolerance (to be defined) between record and replay

---

## 3) Add-only policy and version bump
- Add fields by adding new datasets/groups
- Never rename/remove existing datasets
- Increment schema_version when any new required field is introduced
  


  # implementation_checklist.md — 2-Week Execution Plan (Step-Ack + Teleop + Train/Eval)
Audience: Project leads + Unity/AGX engineers + Python/testbed engineers  
Last updated: 2026-03-18

---

## Milestone M0 (Day 0–1): Agreement & Skeleton
**Goal:** No ambiguity. Everyone codes the same contract.

Deliverables:
- [ ] `protocol.md` finalized and committed (shared repo or mirrored)
- [ ] `schema.md` v1.1 finalized and committed
- [ ] `eval_suite_v0.yaml` skeleton created (even if only 1 scenario)
- [ ] Owners assigned:
  - Unity/AGX bridge owner
  - Python backend owner
  - Dataset/schema owner
  - Eval owner

Exit criteria:
- Everyone agrees on action order, qpos/qvel order, dt/control_hz, step_id rules

---

## Milestone M1 (Day 1–3): Step-Ack PoC (No images)
### Unity/AGX team
- [ ] Disable auto-stepping
- [ ] Implement socket server: GET_INFO/RESET/STEP
- [ ] STEP: apply speed cmd → DoStep once → return qpos/qvel/env_state + step_id
- [ ] Run 10s @ 50Hz: step_id monotonic, no duplicates, no reorder

### Python/testbed team
- [ ] Implement `AGXSimBackend` socket client
- [ ] `step()` blocks until matching step_id response
- [ ] Minimal runner: reset → 500 steps → assert monotonic step_id

Exit criteria:
- Step-ack loop stable for 10 seconds

---

## Milestone M2 (Day 3–6): FPV Image Export V0 (raw RGB)
### Unity/AGX team
- [ ] Export fpv camera frame as raw RGB bytes
- [ ] Include image_w/image_h/image_format in STEP_RESP
- [ ] Maintain 50Hz stepping even if image FPS is lower:
  - allowed: repeat last image on some steps

### Python/testbed team
- [ ] Decode raw RGB bytes → numpy uint8 (H,W,3)
- [ ] Plumb to obs["images"]["fpv"]

Exit criteria:
- Python receives correctly shaped fpv frames during stepping

---

## Milestone M3 (Day 6–9): Teleop Recording + Replay QA
### Unity/AGX team
- [ ] Confirm teleop command path maps to STEP action path (same semantics)
- [ ] Provide deadzone/scale/limit values (or config export)

### Python/testbed team
- [ ] Implement `record_teleop.py`:
  - action_source/type="teleop", id="joystick"
  - write HDF5 schema v1.1
- [ ] Implement `replay.py`:
  - load HDF5 actions
  - replay into AGX backend
  - record replay video + metrics

Exit criteria:
- Record 5 episodes, replay all 5 successfully with consistent motion

---

## Milestone M4 (Day 9–12): Success Definition + EvalSuite V0
### Joint decision (fast)
- [ ] Define env_state index for mass_in_bucket
- [ ] Pick initial M_thresh and hold_steps=25

### Python/testbed team
- [ ] Implement evaluator rule:
  - success if mass_in_bucket >= M_thresh for 25 consecutive steps
- [ ] Fixed eval suite:
  - fixed reset mode
  - fixed scenario list (even 3 seeds is enough for V0)
- [ ] Output artifacts:
  - metrics.json (must include success_rate)
  - summary.csv
  - videos/rollout_XXX.mp4

Exit criteria:
- Eval produces deterministic artifacts on the fixed suite

---

## Milestone M5 (Day 12–14): Train ACT + Evaluate (First closed-loop result)
### Python/testbed team
- [ ] Train ACT on teleop dataset (HDF5 v1.1)
- [ ] Evaluate ACT on fixed eval suite
- [ ] Produce “weekly demo pack”:
  - highlight video
  - metrics diff vs previous baseline
  - failure clips (3×5s)

Exit criteria:
- End-to-end pipeline: teleop→HDF5→train→eval→videos works

---

## Ongoing QA Rules (Do not skip)
- [ ] Every recorded dataset must pass replay QA
- [ ] Any change to ordering/units requires protocol+schema review
- [ ] Fixed eval suite must not change silently


# repo_checklists.md — Three-Repo Checklist (What goes where)
Audience: team leads + repo owners  
Last updated: 2026-03-18

---

## Repo A — engmach-testbed (Python)
Purpose: training/eval/data pipeline + AGX remote backend  
Owner: Python/testbed team

### Must-have code
- [ ] `testbed/backends/agx/backend.py` (socket client + step-ack)
- [ ] Recorder supports schema v1.1 (metadata + timestamps + action_source + fpv + env_state)
- [ ] `cli/record_teleop.py`, `cli/replay.py`, `cli/train.py`, `cli/eval.py`
- [ ] Evaluator: success rule + fixed eval suite loader
- [ ] Policy plugins: act + dummy (diffusion skeleton optional)

### Engineering standards
- [ ] installable package (`pyproject.toml`) + `pip install -e .`
- [ ] pre-commit: black/ruff/isort
- [ ] artifacts gitignored: datasets/videos/checkpoints/runs
- [ ] run folder saves: config snapshot + commit hash + metrics

### Acceptance tests
- [ ] step-ack integration test (500 steps)
- [ ] replay test (replay a recorded episode)
- [ ] eval test produces metrics.json + summary.csv + videos/

---

## Repo B — agxunity-sim (Unity/AGXUnity)
Purpose: scene + bridge + camera export + actuator state export + reset  
Owner: Unity/AGX team

### Must-have components
- [ ] Socket server: GET_INFO/RESET/STEP
- [ ] Manual stepping: disable auto-step; DoStep once per STEP_REQ
- [ ] Export qpos/qvel vectors in standardized order
- [ ] Export fpv image as raw RGB bytes (V0)
- [ ] Export env_state with mass_in_bucket (index documented)
- [ ] Reset baseline fixed initial state

### Acceptance tests
- [ ] 10 seconds @ 50Hz, step_id monotonic and continuous
- [ ] fpv frame correctness (dims + RGB order)
- [ ] qpos/qvel stable and documented

---

## Repo C — sim-protocol (Shared)
Purpose: prevent drift: protocol + schema + constants + eval suite definitions  
Owner: joint (CODEOWNERS: Unity+Python)

### Must include
- [ ] protocol.md (socket + step-ack + vectors)
- [ ] schema.md (HDF5 v1.1)
- [ ] constants.yaml:
  - action order + limits/deadzones/scales
  - qpos/qvel order + units
  - env_state indices (mass_in_bucket index)
- [ ] eval_suite_v0.yaml:
  - scenario list / seeds
  - reset flags
  - success parameters (M_thresh, hold_steps)

### Process rules
- [ ] Any change to ordering/dims requires PR review from both sides
- [ ] Version bumps required for breaking changes
- [ ] “Single source of truth”: do not duplicate conflicting definitions in other repos
