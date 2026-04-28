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
│   ├── protocol_version     str   optional    ← v1.1
│   ├── episode_id           str   optional
│   ├── operator_id          str   optional
│   ├── session_id           str   optional
│   ├── notes                str   optional
│   ├── record_config_path   str   optional
│   ├── record_config_yaml   str   optional
│   ├── camera_width         int   optional
│   ├── camera_height        int   optional
│   ├── camera_fps           float optional
│   ├── camera_row_order     str   optional
│   ├── action_order         str   optional comma-sep
│   ├── qpos_order           str   optional comma-sep
│   ├── qvel_order           str   optional comma-sep
│   ├── env_state_order      str   optional comma-sep
│   ├── teleop_input         str   optional
│   ├── deadzone             float[4] optional
│   ├── scale                float[4] optional
│   ├── limit                float[4] optional
│   ├── axis_map             int[4] optional
│   ├── joystick_ids         int[4] optional
│   ├── invert               bool[4] optional
│   └── key_speed            float optional
│   ├── response_profile_enabled      int/bool optional
│   ├── response_profile_attack_rate  float[4] optional
│   ├── response_profile_release_rate float[4] optional
│   ├── response_profile_recenter_rate float[4] optional
│   ├── response_profile_exponent     float[4] optional
│   ├── scenario_id         str   optional
│   ├── goal_token_dim      int   optional
│   ├── goal_token_version  str   optional
│   ├── phase_version       str   optional
│   ├── scenario_manifest_version str optional
│   ├── recording_mode      str   optional
│   ├── target_dump_count   int   optional
│   ├── stop_reason         str   optional
│   ├── transition_source   str   optional
│   ├── replay_source_episode str optional
│   ├── replay_source_dataset str optional
│   ├── replay_config_path  str   optional
│   ├── replay_post_tail_steps int optional
│   └── v2_enabled          int/bool optional
│
├── observations/
│   ├── qpos                 (T, 4)  float32  [swing, boom, stick, bucket] position_norm
│   ├── qvel                 (T, 4)  float32  [swing, boom, stick, bucket] speed
│   ├── env_state            (T, M)  float32  current AGX order:
│   │                                     [mass_in_bucket, excavated_mass,
│   │                                      mass_in_target_box, deposited_mass_in_target_box,
│   │                                      min_distance_to_target,
│   │                                      target_hard_collision_count,
│   │                                      target_contact_max_normal_force_n,
│   │                                      min_distance_to_dig_area_m,
│   │                                      bucket_depth_below_dig_area_plane_m,
│   │                                      target_horizontal_distance_m,
│   │                                      bucket_height_above_target_rim_m,
│   │                                      bucket_over_target_footprint_mask,
│   │                                      dump_clearance_ok_mask,
│   │                                      bucket_bed_relative_x_m,
│   │                                      bucket_bed_relative_z_m,
│   │                                      bucket_bed_footprint_outside_distance_m]
│   │                                      ← v1.1 add-only
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

Optional Repo A `/v2` extension group (still schema_version="1.1")
────────────────────────────────────────────────────────────────
/v2
├── step/
│   ├── cycle_id             (T,)    int32
│   ├── mode_id              (T,)    uint8
│   ├── phase_id             (T,)    uint8
│   ├── phase_progress       (T,)    float32
│   ├── work_stage_id        (T,)    uint8
│   ├── goal_tokens          (T, 10) float32
│   ├── action_loss_mask     (T,)    uint8 optional, 1=train action, 0=ignore
│   ├── planner_replan_mask  (T,)    uint8
│   ├── qualified_dig_start_mask (T,) uint8
│   ├── dump_start_mask      (T,)    uint8
│   ├── dump_end_mask        (T,)    uint8
│   ├── pause_mask           (T,)    uint8
│   └── boundary_mask        (T,)    uint8
└── cycle/
    ├── cycle_id             (K,)    int32
    ├── start_step           (K,)    int32
    ├── dump_end_step        (K,)    int32
    ├── end_step             (K,)    int32
    ├── curr_src_sector_id   (K,)    int32
    ├── curr_cut_depth_class (K,)    int32
    ├── next_src_sector_id   (K,)    int32
    ├── next_cut_depth_class (K,)    int32
    ├── dst_target_id        (K,)    int32
    ├── fill_peak_kg         (K,)    float32
    ├── deposit_delta_kg     (K,)    float32
    ├── peak_bucket_depth_m  (K,)    float32
    ├── collision_count_delta (K,)   int32
    ├── transition_source    (K,)    string
    ├── plan_source          (K,)    string
    └── cycle_success        (K,)    int8
"""

# ── Schema version ────────────────────────────────────────────────────────────
SCHEMA_VERSION = "1.1"

# ── Group paths ───────────────────────────────────────────────────────────────
GRP_METADATA      = "metadata"
GRP_OBS           = "observations"
GRP_IMAGES        = "observations/images"
GRP_TIMESTAMPS    = "timestamps"        # v1.1
GRP_ACTION_SOURCE = "action_source"     # v1.1
GRP_V2            = "v2"                # optional Repo A add-only extension
GRP_V2_STEP       = "v2/step"
GRP_V2_CYCLE      = "v2/cycle"

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

# ── Dataset paths — optional Repo A /v2 extension ───────────────────────────
DS_V2_STEP_CYCLE_ID       = "v2/step/cycle_id"
DS_V2_STEP_MODE_ID        = "v2/step/mode_id"
DS_V2_STEP_PHASE_ID       = "v2/step/phase_id"
DS_V2_STEP_PHASE_PROGRESS = "v2/step/phase_progress"
DS_V2_STEP_WORK_STAGE_ID  = "v2/step/work_stage_id"
DS_V2_STEP_GOAL_TOKENS    = "v2/step/goal_tokens"
DS_V2_STEP_ACTION_LOSS_MASK = "v2/step/action_loss_mask"
DS_V2_STEP_PLANNER_REPLAN_MASK = "v2/step/planner_replan_mask"
DS_V2_STEP_QUALIFIED_DIG_START_MASK = "v2/step/qualified_dig_start_mask"
DS_V2_STEP_DUMP_START_MASK = "v2/step/dump_start_mask"
DS_V2_STEP_DUMP_END_MASK = "v2/step/dump_end_mask"
DS_V2_STEP_PAUSE_MASK     = "v2/step/pause_mask"
DS_V2_STEP_BOUNDARY_MASK  = "v2/step/boundary_mask"

DS_V2_CYCLE_CYCLE_ID        = "v2/cycle/cycle_id"
DS_V2_CYCLE_START_STEP      = "v2/cycle/start_step"
DS_V2_CYCLE_DUMP_END_STEP   = "v2/cycle/dump_end_step"
DS_V2_CYCLE_END_STEP        = "v2/cycle/end_step"
DS_V2_CYCLE_DST_TARGET_ID   = "v2/cycle/dst_target_id"
DS_V2_CYCLE_CURR_SRC_SECTOR_ID = "v2/cycle/curr_src_sector_id"
DS_V2_CYCLE_CURR_CUT_DEPTH_CLASS = "v2/cycle/curr_cut_depth_class"
DS_V2_CYCLE_NEXT_SRC_SECTOR_ID = "v2/cycle/next_src_sector_id"
DS_V2_CYCLE_NEXT_CUT_DEPTH_CLASS = "v2/cycle/next_cut_depth_class"
DS_V2_CYCLE_FILL_PEAK_KG    = "v2/cycle/fill_peak_kg"
DS_V2_CYCLE_DEPOSIT_DELTA_KG = "v2/cycle/deposit_delta_kg"
DS_V2_CYCLE_PEAK_BUCKET_DEPTH_M = "v2/cycle/peak_bucket_depth_m"
DS_V2_CYCLE_COLLISION_COUNT_DELTA = "v2/cycle/collision_count_delta"
DS_V2_CYCLE_TRANSITION_SOURCE = "v2/cycle/transition_source"
DS_V2_CYCLE_PLAN_SOURCE = "v2/cycle/plan_source"
DS_V2_CYCLE_SUCCESS         = "v2/cycle/cycle_success"

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
ATTR_EPISODE_ID       = "episode_id"
ATTR_OPERATOR_ID      = "operator_id"
ATTR_SESSION_ID       = "session_id"
ATTR_NOTES            = "notes"
ATTR_RECORD_CONFIG_PATH = "record_config_path"
ATTR_RECORD_CONFIG_YAML = "record_config_yaml"
ATTR_CAMERA_WIDTH     = "camera_width"
ATTR_CAMERA_HEIGHT    = "camera_height"
ATTR_CAMERA_FPS       = "camera_fps"
ATTR_CAMERA_ROW_ORDER = "camera_row_order"
ATTR_ACTION_ORDER     = "action_order"
ATTR_QPOS_ORDER       = "qpos_order"
ATTR_QVEL_ORDER       = "qvel_order"
ATTR_ENV_STATE_ORDER  = "env_state_order"
ATTR_TELEOP_INPUT     = "teleop_input"
ATTR_DEADZONE         = "deadzone"
ATTR_SCALE            = "scale"
ATTR_LIMIT            = "limit"
ATTR_AXIS_MAP         = "axis_map"
ATTR_JOYSTICK_IDS     = "joystick_ids"
ATTR_INVERT           = "invert"
ATTR_KEY_SPEED        = "key_speed"
ATTR_RESPONSE_PROFILE_ENABLED = "response_profile_enabled"
ATTR_RESPONSE_PROFILE_ATTACK_RATE = "response_profile_attack_rate"
ATTR_RESPONSE_PROFILE_RELEASE_RATE = "response_profile_release_rate"
ATTR_RESPONSE_PROFILE_RECENTER_RATE = "response_profile_recenter_rate"
ATTR_RESPONSE_PROFILE_EXPONENT = "response_profile_exponent"
ATTR_SCENARIO_ID = "scenario_id"
ATTR_GOAL_TOKEN_DIM = "goal_token_dim"
ATTR_GOAL_TOKEN_VERSION = "goal_token_version"
ATTR_PHASE_VERSION = "phase_version"
ATTR_WORK_STAGE_VERSION = "work_stage_version"
ATTR_SCENARIO_MANIFEST_VERSION = "scenario_manifest_version"
ATTR_RECORDING_MODE = "recording_mode"
ATTR_TARGET_DUMP_COUNT = "target_dump_count"
ATTR_STOP_REASON = "stop_reason"
ATTR_TRANSITION_SOURCE = "transition_source"
ATTR_REPLAY_SOURCE_EPISODE = "replay_source_episode"
ATTR_REPLAY_SOURCE_DATASET = "replay_source_dataset"
ATTR_REPLAY_CONFIG_PATH = "replay_config_path"
ATTR_REPLAY_POST_TAIL_STEPS = "replay_post_tail_steps"
ATTR_V2_ENABLED = "v2_enabled"

# ── V0 locked constants ───────────────────────────────────────────────────────
DEFAULT_CONTROL_HZ       = 50
DEFAULT_DT               = 0.02
DEFAULT_ACTION_SEMANTICS = "actuator_speed_cmd"
DEFAULT_IMAGE_FORMAT     = "raw_rgb"

# env_state indices for the current AGX Unity contract
ENV_STATE_MASS_IN_BUCKET_IDX = 0
ENV_STATE_EXCAVATED_MASS_IDX = 1
ENV_STATE_MASS_IN_TARGET_BOX_IDX = 2
ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX = 3
ENV_STATE_MIN_DISTANCE_TO_TARGET_IDX = 4
ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX = 5
ENV_STATE_TARGET_CONTACT_MAX_NORMAL_FORCE_N_IDX = 6
ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX = 7
ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX = 8
ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX = 9
ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX = 10
ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX = 11
ENV_STATE_DUMP_CLEARANCE_OK_IDX = 12
ENV_STATE_BUCKET_BED_RELATIVE_X_IDX = 13
ENV_STATE_BUCKET_BED_RELATIVE_Z_IDX = 14
ENV_STATE_BUCKET_BED_FOOTPRINT_OUTSIDE_DISTANCE_IDX = 15

# ── Image dataset name template ───────────────────────────────────────────────
def image_ds(cam_name: str) -> str:
    return f"observations/images/{cam_name}"
