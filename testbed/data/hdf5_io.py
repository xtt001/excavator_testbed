"""
Low-level HDF5 read/write for demo episodes.

Preserves full backward compatibility with legacy episode_N.hdf5 files
(same qpos/qvel/images/action layout) while adding a /metadata group
and schema versioning for new files.

write_episode() now accepts all v1.1 fields as optional kwargs.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from testbed.data.schema import (
    ATTR_SCHEMA_VERSION,
    ATTR_SIM,
    ATTR_TASK_NAME,
    ATTR_SIM_BACKEND,
    ATTR_SEED,
    ATTR_PARAM_VERSION,
    ATTR_TIMESTAMP,
    ATTR_CONTROL_HZ,
    ATTR_DT,
    ATTR_ACTION_SEMANTICS,
    ATTR_CAMERA_NAMES,
    ATTR_IMAGE_FORMAT,
    DS_ACTION,
    DS_QPOS,
    DS_QVEL,
    DS_REWARDS,
    DS_ENV_STATE,
    DS_STEP_ID,
    DS_STEP_NS,
    DS_ACTION_SRC_TYPE,
    DS_ACTION_SRC_ID,
    GRP_METADATA,
    GRP_TIMESTAMPS,
    GRP_ACTION_SOURCE,
    SCHEMA_VERSION,
    image_ds,
)


# ─── Write ────────────────────────────────────────────────────────────────────

def write_episode(
    path: str | Path,
    *,
    qpos: np.ndarray,
    qvel: np.ndarray,
    actions: np.ndarray,
    images: dict[str, np.ndarray] | None = None,
    rewards: np.ndarray | None = None,
    metadata: dict[str, Any] | None = None,
    compress: bool = True,
    # ── v1.1 additions (all optional; written only if provided) ──────────────
    env_state: np.ndarray | None = None,          # (T, M) float32
    step_ids: np.ndarray | None = None,           # (T,) int64
    step_ns: np.ndarray | None = None,            # (T,) int64
    action_src_types: list[str] | None = None,    # (T,) str
    action_src_ids: list[str] | None = None,      # (T,) str
) -> None:
    """
    Write one demonstration episode to an HDF5 file (schema v1.1).

    All v1.1 fields (env_state, step_ids, action_src_*) are optional so
    the function remains backward-compatible.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    kwargs = {"compression": "lzf"} if compress else {}
    str_dtype = h5py.special_dtype(vlen=str)

    with h5py.File(path, "w") as f:
        # ── metadata ─────────────────────────────────────────────────────────
        meta = f.create_group(GRP_METADATA)
        meta.attrs[ATTR_SCHEMA_VERSION] = SCHEMA_VERSION
        meta.attrs[ATTR_SIM] = True
        if metadata:
            for k, v in metadata.items():
                meta.attrs[k] = v

        # ── legacy root-level attrs (backward compat) ────────────────────────
        f.attrs[ATTR_SIM] = True

        # ── observations ─────────────────────────────────────────────────────
        obs_grp = f.create_group("observations")
        obs_grp.create_dataset("qpos", data=qpos.astype(np.float32))
        obs_grp.create_dataset("qvel", data=qvel.astype(np.float32))

        if env_state is not None:                                   # v1.1
            obs_grp.create_dataset(
                "env_state", data=env_state.astype(np.float32)
            )

        if images:
            img_grp = obs_grp.create_group("images")
            for cam, arr in images.items():
                img_grp.create_dataset(
                    cam, data=arr.astype(np.uint8), **kwargs
                )

        # ── action ───────────────────────────────────────────────────────────
        f.create_dataset("action", data=actions.astype(np.float32))

        # ── rewards ──────────────────────────────────────────────────────────
        if rewards is not None:
            f.create_dataset("rewards", data=rewards.astype(np.float32))

        # ── timestamps (v1.1) ────────────────────────────────────────────────
        if step_ids is not None or step_ns is not None:
            ts_grp = f.create_group(GRP_TIMESTAMPS)
            if step_ids is not None:
                ts_grp.create_dataset("step_id", data=np.asarray(step_ids, dtype=np.int64))
            if step_ns is not None:
                ts_grp.create_dataset("step_ns", data=np.asarray(step_ns, dtype=np.int64))

        # ── action_source (v1.1) ─────────────────────────────────────────────
        if action_src_types is not None or action_src_ids is not None:
            src_grp = f.create_group(GRP_ACTION_SOURCE)
            if action_src_types is not None:
                ds = src_grp.create_dataset("type", (len(action_src_types),), dtype=str_dtype)
                for i, s in enumerate(action_src_types):
                    ds[i] = s
            if action_src_ids is not None:
                ds = src_grp.create_dataset("id", (len(action_src_ids),), dtype=str_dtype)
                for i, s in enumerate(action_src_ids):
                    ds[i] = s


# ─── Read ─────────────────────────────────────────────────────────────────────

def read_episode(path: str | Path) -> dict[str, Any]:
    """
    Read a full episode from HDF5.

    Returns
    -------
    {
      "qpos":    (T, Nq) float32,
      "qvel":    (T, Nq) float32,
      "actions": (T, Na) float32,
      "images":  {cam: (T, H, W, 3) uint8},
      "rewards": (T,) float32 | None,
      "metadata": dict,
      "is_sim":  bool,
    }
    """
    path = Path(path)
    result: dict[str, Any] = {}

def read_episode(path: str | Path) -> dict[str, Any]:
    """
    Read a full episode from HDF5 (v1.0 and v1.1 compatible).

    Returns
    -------
    {
      "qpos":             (T, Nq) float32,
      "qvel":             (T, Nq) float32,
      "actions":          (T, Na) float32,
      "images":           {cam: (T, H, W, 3) uint8},
      "rewards":          (T,) float32 | None,
      "env_state":        (T, M) float32 | None,    # v1.1
      "step_ids":         (T,) int64 | None,        # v1.1
      "step_ns":          (T,) int64 | None,        # v1.1
      "action_src_types": list[str] | None,         # v1.1
      "action_src_ids":   list[str] | None,         # v1.1
      "metadata":         dict,
      "is_sim":           bool,
    }
    """
    path = Path(path)
    result: dict[str, Any] = {}

    with h5py.File(path, "r") as f:
        result["qpos"]    = f[DS_QPOS][()].astype(np.float32)
        result["qvel"]    = f[DS_QVEL][()].astype(np.float32)
        result["actions"] = f[DS_ACTION][()].astype(np.float32)

        # images
        images = {}
        if "observations/images" in f:
            for cam in f["observations/images"]:
                images[cam] = f[f"observations/images/{cam}"][()]
        result["images"] = images

        # rewards (optional)
        result["rewards"] = f[DS_REWARDS][()] if DS_REWARDS in f else None

        # v1.1 — env_state
        result["env_state"] = (
            f[DS_ENV_STATE][()].astype(np.float32)
            if DS_ENV_STATE in f else None
        )

        # v1.1 — timestamps
        result["step_ids"] = f[DS_STEP_ID][()] if DS_STEP_ID in f else None
        result["step_ns"]  = f[DS_STEP_NS][()] if DS_STEP_NS in f else None

        # v1.1 — action_source
        if DS_ACTION_SRC_TYPE in f:
            result["action_src_types"] = [
                s.decode() if isinstance(s, bytes) else s
                for s in f[DS_ACTION_SRC_TYPE][()]
            ]
        else:
            result["action_src_types"] = None

        if DS_ACTION_SRC_ID in f:
            result["action_src_ids"] = [
                s.decode() if isinstance(s, bytes) else s
                for s in f[DS_ACTION_SRC_ID][()]
            ]
        else:
            result["action_src_ids"] = None

        # metadata
        meta: dict[str, Any] = {}
        if GRP_METADATA in f:
            meta.update(dict(f[GRP_METADATA].attrs))
        meta.update(dict(f.attrs))  # fallback: legacy root attrs
        result["metadata"] = meta
        result["is_sim"] = bool(meta.get(ATTR_SIM, True))

    return result


# ─── Discovery ────────────────────────────────────────────────────────────────

def list_episodes(dataset_dir: str | Path) -> list[Path]:
    """
    Return sorted list of episode_N.hdf5 paths in a dataset directory.
    Only files matching the pattern episode_<int>.hdf5 are returned.
    """
    dataset_dir = Path(dataset_dir)
    eps = []
    for p in dataset_dir.glob("episode_*.hdf5"):
        try:
            int(p.stem.split("_", 1)[1])
            eps.append(p)
        except (IndexError, ValueError):
            continue
    return sorted(eps, key=lambda p: int(p.stem.split("_", 1)[1]))


def episode_id_from_path(path: Path) -> int:
    return int(path.stem.split("_", 1)[1])
