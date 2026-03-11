"""
HDF5 schema constants and versioned field names.

All data access must go through hdf5_io.py; never hardcode these strings
elsewhere — use the constants defined here.

Schema v1.0 layout
------------------
/                       (root)
├── metadata/           group
│   ├── schema_version  str attr   e.g. "1.0"
│   ├── task_name       str attr
│   ├── sim_backend     str attr
│   ├── seed            int attr
│   ├── param_version   str attr
│   └── timestamp       str attr   ISO 8601
├── observations/
│   ├── qpos            (T, Nq) float32
│   ├── qvel            (T, Nq) float32
│   └── images/
│       └── <cam_name>  (T, H, W, 3) uint8
├── action              (T, Na) float32
└── rewards             (T,)    float32   (optional)
"""

SCHEMA_VERSION = "1.0"

# ── Group paths ───────────────────────────────────────────────────────────────
GRP_METADATA    = "metadata"
GRP_OBS         = "observations"
GRP_IMAGES      = "observations/images"

# ── Dataset paths ─────────────────────────────────────────────────────────────
DS_QPOS         = "observations/qpos"
DS_QVEL         = "observations/qvel"
DS_ACTION       = "action"
DS_REWARDS      = "rewards"

# ── Metadata attribute names ─────────────────────────────────────────────────
ATTR_SCHEMA_VERSION = "schema_version"
ATTR_SIM            = "sim"          # legacy bool flag — keep for compat
ATTR_TASK_NAME      = "task_name"
ATTR_SIM_BACKEND    = "sim_backend"
ATTR_SEED           = "seed"
ATTR_PARAM_VERSION  = "param_version"
ATTR_TIMESTAMP      = "timestamp"

# ── Image dataset name template ───────────────────────────────────────────────
def image_ds(cam_name: str) -> str:
    return f"observations/images/{cam_name}"
