"""
Low-level HDF5 read/write for demo episodes.

Preserves full backward compatibility with legacy episode_N.hdf5 files
(same qpos/qvel/images/action layout) while adding a /metadata group,
schema versioning, and an optional Repo A `/v2` extension group.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from testbed.data.schema import (
    ATTR_CAMERA_NAMES,
    ATTR_IMAGE_FORMAT,
    ATTR_SCHEMA_VERSION,
    ATTR_SIM,
    DS_ACTION,
    DS_ACTION_SRC_ID,
    DS_ACTION_SRC_TYPE,
    DS_ENV_STATE,
    DS_QPOS,
    DS_QVEL,
    DS_REWARDS,
    DS_STEP_ID,
    DS_STEP_NS,
    GRP_METADATA,
    GRP_ACTION_SOURCE,
    GRP_ENCODED_IMAGES,
    GRP_TIMESTAMPS,
    GRP_V2,
    GRP_V2_CYCLE,
    GRP_V2_STEP,
    SCHEMA_VERSION,
)
from testbed.data.camera_images import (
    JPEG_ENCODING,
    decode_jpeg_rgb,
    encoded_frame_to_uint8,
    ordered_camera_names,
    validate_exclusive_camera_layout,
)


# ─── Write ────────────────────────────────────────────────────────────────────

def write_episode(
    path: str | Path,
    *,
    qpos: np.ndarray,
    qvel: np.ndarray,
    actions: np.ndarray,
    images: dict[str, np.ndarray] | None = None,
    encoded_images: dict[str, Any] | None = None,
    rewards: np.ndarray | None = None,
    metadata: dict[str, Any] | None = None,
    compress: bool = True,
    # ── v1.1 additions (all optional; written only if provided) ──────────────
    env_state: np.ndarray | None = None,          # (T, M) float32
    step_ids: np.ndarray | None = None,           # (T,) int64
    step_ns: np.ndarray | None = None,            # (T,) int64
    action_src_types: list[str] | None = None,    # (T,) str
    action_src_ids: list[str] | None = None,      # (T,) str
    v2: dict[str, dict[str, np.ndarray]] | None = None,
) -> None:
    """
    Write one demonstration episode to an HDF5 file (schema v1.1).

    All v1.1 fields (env_state, step_ids, action_src_*) are optional so
    the function remains backward-compatible.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    str_dtype = h5py.special_dtype(vlen=str)

    metadata = dict(metadata or {})
    stored_camera_names = validate_exclusive_camera_layout(
        (images or {}).keys(), (encoded_images or {}).keys()
    )
    ordered_names = (
        ordered_camera_names(stored_camera_names, metadata)
        if stored_camera_names
        else []
    )
    if ordered_names:
        metadata[ATTR_CAMERA_NAMES] = ",".join(ordered_names)
        metadata[ATTR_IMAGE_FORMAT] = JPEG_ENCODING if encoded_images else "raw_rgb"

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
            for cam in ordered_names:
                arr = images[cam]
                image_arr = arr.astype(np.uint8)
                img_grp.create_dataset(
                    cam,
                    data=image_arr,
                    **_image_dataset_kwargs(image_arr, compress=compress),
                )

        if encoded_images:
            encoded_grp = obs_grp.create_group("encoded_images")
            for cam in ordered_names:
                _write_encoded_image_dataset(encoded_grp, cam, encoded_images[cam])

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

        if v2:
            _write_v2_group(f, v2)


def write_v2_extension(
    path: str | Path,
    *,
    v2: dict[str, dict[str, np.ndarray]],
    metadata_updates: dict[str, Any] | None = None,
) -> None:
    """Attach or replace the optional Repo A `/v2` extension in-place."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    with h5py.File(path, "a") as f:
        meta = f.require_group(GRP_METADATA)
        meta.attrs[ATTR_SCHEMA_VERSION] = SCHEMA_VERSION
        meta.attrs[ATTR_SIM] = bool(meta.attrs.get(ATTR_SIM, True))
        if metadata_updates:
            for key, value in metadata_updates.items():
                meta.attrs[key] = value
        if GRP_V2 in f:
            del f[GRP_V2]
        _write_v2_group(f, v2)


def read_episode(
    path: str | Path,
    *,
    load_images: bool = True,
    load_encoded_images: bool = True,
) -> dict[str, Any]:
    """
    Read a full episode from HDF5 (v1.0 and v1.1 compatible).

    Returns
    -------
    {
      "qpos":             (T, Nq) float32,
      "qvel":             (T, Nq) float32,
      "actions":          (T, Na) float32,
      "images":           {cam: (T, H, W, 3) uint8}, or {} when load_images=False
      "rewards":          (T,) float32 | None,
      "env_state":        (T, M) float32 | None,    # v1.1
      "step_ids":         (T,) int64 | None,        # v1.1
      "step_ns":          (T,) int64 | None,        # v1.1
      "action_src_types": list[str] | None,         # v1.1
      "action_src_ids":   list[str] | None,         # v1.1
      "v2":               dict | None,              # optional Repo A extension
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

        # images: encoded episodes are decoded here so all consumers see RGB HWC.
        images = {}
        encoded_images: dict[str, list[np.ndarray]] = {}
        raw_group = f.get("observations/images")
        encoded_group = f.get(GRP_ENCODED_IMAGES)
        stored_names = validate_exclusive_camera_layout(
            raw_group.keys() if raw_group is not None else (),
            encoded_group.keys() if encoded_group is not None else (),
        )
        metadata_attrs = dict(f[GRP_METADATA].attrs) if GRP_METADATA in f else {}
        ordered_names = ordered_camera_names(stored_names, metadata_attrs)
        if encoded_group is not None and (load_images or load_encoded_images):
            for cam in ordered_names:
                dataset = encoded_group[cam]
                encoding = dataset.attrs.get("encoding", "")
                if isinstance(encoding, bytes):
                    encoding = encoding.decode()
                if str(encoding).lower() != JPEG_ENCODING:
                    raise ValueError(f"camera {cam!r} has unsupported encoding {encoding!r}")
                frames = [
                    np.asarray(dataset[i], dtype=np.uint8).reshape(-1).copy()
                    for i in range(dataset.shape[0])
                ]
                if load_encoded_images:
                    encoded_images[cam] = frames
                if load_images:
                    images[cam] = np.stack([decode_jpeg_rgb(frame) for frame in frames])
        elif load_images and raw_group is not None:
            for cam in ordered_names:
                images[cam] = raw_group[cam][()]
        result["images"] = images
        result["encoded_images"] = encoded_images

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

        result["v2"] = _read_v2_group(f)

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


def _write_v2_group(h5_file: h5py.File, v2: dict[str, dict[str, np.ndarray]]) -> None:
    v2_grp = h5_file.create_group(GRP_V2)
    step_data = dict(v2.get("step", {}))
    cycle_data = dict(v2.get("cycle", {}))
    if step_data:
        _write_dataset_group(v2_grp.create_group("step"), step_data)
    if cycle_data:
        _write_dataset_group(v2_grp.create_group("cycle"), cycle_data)


def _write_dataset_group(group: h5py.Group, payload: dict[str, np.ndarray]) -> None:
    for key, value in payload.items():
        arr = np.asarray(value)
        if arr.dtype.kind == "U":
            str_dtype = h5py.special_dtype(vlen=str)
            ds = group.create_dataset(str(key), (len(arr),), dtype=str_dtype)
            for index, item in enumerate(arr):
                ds[index] = str(item)
            continue
        group.create_dataset(str(key), data=arr)


def _image_dataset_kwargs(arr: np.ndarray, *, compress: bool) -> dict[str, Any]:
    """Return HDF5 options for training-friendly image frame reads."""
    if not compress:
        return {}
    kwargs: dict[str, Any] = {"compression": "lzf"}
    if arr.ndim >= 4 and int(arr.shape[0]) > 0:
        kwargs["chunks"] = (1,) + tuple(int(value) for value in arr.shape[1:])
    return kwargs


def _write_encoded_image_dataset(group: h5py.Group, name: str, frames: Any) -> None:
    frame_list = list(frames)
    dataset = group.create_dataset(
        name, (len(frame_list),), dtype=h5py.vlen_dtype(np.dtype("uint8"))
    )
    dataset.attrs["encoding"] = JPEG_ENCODING
    for index, frame in enumerate(frame_list):
        dataset[index] = encoded_frame_to_uint8(frame)


def _read_v2_group(h5_file: h5py.File) -> dict[str, dict[str, Any]] | None:
    if GRP_V2 not in h5_file:
        return None
    result: dict[str, dict[str, Any]] = {}
    for section_name, group_path in (("step", GRP_V2_STEP), ("cycle", GRP_V2_CYCLE)):
        if group_path not in h5_file:
            continue
        section_group = h5_file[group_path]
        section_payload: dict[str, Any] = {}
        for dataset_name in section_group:
            value = section_group[dataset_name][()]
            if isinstance(value, np.ndarray) and value.dtype.kind in {"S", "O"}:
                value = np.asarray(
                    [
                        item.decode() if isinstance(item, bytes) else item
                        for item in value
                    ],
                    dtype=object,
                )
            section_payload[dataset_name] = value
        result[section_name] = section_payload
    return result or None
