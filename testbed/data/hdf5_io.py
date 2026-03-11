"""
Low-level HDF5 read/write for demo episodes.

Preserves full backward compatibility with legacy episode_N.hdf5 files
(same qpos/qvel/images/action layout) while adding a /metadata group
and schema versioning for new files.
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
    DS_ACTION,
    DS_QPOS,
    DS_QVEL,
    DS_REWARDS,
    GRP_METADATA,
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
) -> None:
    """
    Write one demonstration episode to an HDF5 file.

    Parameters
    ----------
    path     Destination file (parent dirs created automatically).
    qpos     (T, Nq) joint positions.
    qvel     (T, Nq) joint velocities.
    actions  (T, Na) action sequence.
    images   {cam_name: (T, H, W, 3) uint8} — optional.
    rewards  (T,) per-step rewards — optional.
    metadata Scalar metadata written as /metadata attributes.
    compress Use lzf compression for image datasets (default True).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    kwargs = {"compression": "lzf"} if compress else {}

    with h5py.File(path, "w") as f:
        # ── metadata ─────────────────────────────────────────────────────────
        meta = f.create_group(GRP_METADATA)
        meta.attrs[ATTR_SCHEMA_VERSION] = SCHEMA_VERSION
        meta.attrs[ATTR_SIM] = True  # always True for sim data
        if metadata:
            for k, v in metadata.items():
                meta.attrs[k] = v

        # ── legacy root-level attrs (for backward compat) ────────────────────
        f.attrs[ATTR_SIM] = True

        # ── observations ─────────────────────────────────────────────────────
        obs_grp = f.create_group("observations")
        obs_grp.create_dataset("qpos",  data=qpos.astype(np.float32))
        obs_grp.create_dataset("qvel",  data=qvel.astype(np.float32))

        if images:
            img_grp = obs_grp.create_group("images")
            for cam, arr in images.items():
                img_grp.create_dataset(
                    cam, data=arr.astype(np.uint8), **kwargs
                )

        # ── action ───────────────────────────────────────────────────────────
        f.create_dataset("action", data=actions.astype(np.float32))

        # ── rewards (optional) ────────────────────────────────────────────────
        if rewards is not None:
            f.create_dataset("rewards", data=rewards.astype(np.float32))


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

        # metadata
        meta: dict[str, Any] = {}
        if GRP_METADATA in f:
            meta.update(dict(f[GRP_METADATA].attrs))
        # fallback: read legacy root attrs
        meta.update(dict(f.attrs))
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
