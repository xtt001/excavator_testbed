"""
HDF5 schema constants and versioned field names.

All data access must go through hdf5_io.py; never hardcode these strings
elsewhere — use the constants defined here.

Add-only policy: never remove or rename fields.  Bump SCHEMA_VERSION when
any new *required* field is introduced.

Schema v1.1 layout (add-only on top of v1.0)
─────────────────────────────────────────────
/                            (root)
├── metadata/                group — all stored as attrs
│   ├── schema_version       str   "1.1"
│   ├── task_name            str
│   ├── sim_backend          str   "agxunity" | "mujoco" | …
│   ├── seed                 int
│   ├── param_version        str
│   ├── timestamp            str   ISO 8601
│   ├── control_hz           int   50          ← v1.1
│   ├── dt                   float 0.02        ← v1.1
│   ├── action_semantics     str   "actuator_speed_cmd"  ← v1.1
│   ├── camera_names         str   comma-sep   ← v1.1
│   ├── image_format         str   "raw_rgb"   ← v1.1
│   └── protocol_version     str   optional    ← v1.1
│
├── observations/
│   ├── qpos                 (T, 3)  float32  [boom, stick, bucket] position_norm
│   ├── qvel                 (T, 4)  float32  [swing, boom, stick, bucket] speed
│   ├── env_state            (T, M)  float32  includes mass_in_bucket  ← v1.1
│   └── images/
│       └── fpv              (T, H, W, 3) uint8                        ← v1.1
│
├── action                   (T, 4)  float32  [swing, boom, stick, bucket]
├── rewards                  (T,)    float32  optional
│
├── timestamps/                                                         ← v1.1
│   ├── step_id              (T,) int64
│   └── step_ns              (T,) int64  optional (0 if unused)
│
└── action_source/                                                      ← v1.1
    ├── type                 (T,) bytes  "teleop"|"policy"|"scripted"
    └── id                   (T,) bytes  "joystick"|"keyboard"|…
"""

# ── Schema version ────────────────────────────────────────────────────────────
SCHEMA_VERSION = "1.1"

# ── Group paths ───────────────────────────────────────────────────────────────
GRP_METADATA      = "metadata"
GRP_OBS           = "observations"
GRP_IMAGES        = "observations/images"
GRP_TIMESTAMPS    = "timestamps"        # v1.1
GRP_ACTION_SOURCE = "action_source"     # v1.1

# ── Dataset paths — v1.0 ─────────────────────────────────────────────────────
DS_QPOS    = "observations/qpos"
DS_QVEL    = "observations/qvel"
DS_ACTION  = "action"
DS_REWARDS = "rewards"

# ── Dataset paths — v1.1 additions ───────────────────────────────────────────
DS_ENV_STATE       = "observations/env_state"       # (T, M) float32
DS_STEP_ID         = "timestamps/step_id"            # (T,) int64
DS_STEP_NS         = "timestamps/step_ns"            # (T,) int64
DS_ACTION_SRC_TYPE = "action_source/type"            # (T,) variable-length str
DS_ACTION_SRC_ID   = "action_source/id"              # (T,) variable-length str

# ── Metadata attribute names — v1.0 ──────────────────────────────────────────
ATTR_SCHEMA_VERSION = "schema_version"
ATTR_SIM            = "sim"            # legacy bool flag — keep for compat
ATTR_TASK_NAME      = "task_name"
ATTR_SIM_BACKEND    = "sim_backend"
ATTR_SEED           = "seed"
ATTR_PARAM_VERSION  = "param_version"
ATTR_TIMESTAMP      = "timestamp"

# ── Metadata attribute names — v1.1 additions ────────────────────────────────
ATTR_CONTROL_HZ       = "control_hz"
ATTR_DT               = "dt"
ATTR_ACTION_SEMANTICS = "action_semantics"
ATTR_CAMERA_NAMES     = "camera_names"       # comma-separated string
ATTR_IMAGE_FORMAT     = "image_format"       # "raw_rgb" | "h264"
ATTR_PROTOCOL_VERSION = "protocol_version"   # optional

# ── V0 locked constants ───────────────────────────────────────────────────────
DEFAULT_CONTROL_HZ       = 50
DEFAULT_DT               = 0.02
DEFAULT_ACTION_SEMANTICS = "actuator_speed_cmd"
DEFAULT_IMAGE_FORMAT     = "raw_rgb"

# env_state index for mass_in_bucket (Unity side must match this)
ENV_STATE_MASS_IN_BUCKET_IDX = 0

# ── Image dataset name template ───────────────────────────────────────────────
def image_ds(cam_name: str) -> str:
    return f"observations/images/{cam_name}"
