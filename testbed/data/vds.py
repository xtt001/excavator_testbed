"""HDF5 VDS helpers for V2.2 dataset builders.

The VDS path keeps large per-step tensors in their immutable source episodes
and writes only lightweight wrapper files for enriched raw and primitive
windows.  Small audit fields stay materialized in the wrapper so metadata,
lineage, and primitive ownership remain readable without scanning the source.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from testbed.data.schema import (
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
    GRP_ACTION_SOURCE,
    GRP_ENCODED_IMAGES,
    GRP_METADATA,
    GRP_OBS,
    GRP_TIMESTAMPS,
    GRP_V2,
    GRP_V2_CYCLE,
    GRP_V2_STEP,
    SCHEMA_VERSION,
)

STORAGE_MODE_COPY = "copy"
STORAGE_MODE_VDS = "vds"
STORAGE_MODE_MANIFEST = "manifest"
EPISODE_STORAGE_MODES = (STORAGE_MODE_COPY, STORAGE_MODE_VDS)
PRIMITIVE_STORAGE_MODES = (
    STORAGE_MODE_COPY,
    STORAGE_MODE_VDS,
    STORAGE_MODE_MANIFEST,
)


def write_vds_episode(
    path: str | Path,
    *,
    source_path: str | Path,
    crop: slice,
    metadata: dict[str, Any] | None = None,
    v2_step_overlay: dict[str, np.ndarray] | None = None,
    v2_cycle_payload: dict[str, np.ndarray] | None = None,
    action_src_types: list[str] | None = None,
    action_src_ids: list[str] | None = None,
    relative_paths: bool = True,
) -> None:
    """Write one HDF5 wrapper episode backed by virtual source datasets."""
    path = Path(path)
    source_path = Path(source_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with h5py.File(source_path, "r") as src, h5py.File(path, "w") as dst:
        start, end = _normalise_crop(crop=crop, source_len=int(src[DS_ACTION].shape[0]))
        source_ref = _source_ref_for_target(
            source_path=source_path,
            target_path=path,
            relative_paths=relative_paths,
        )

        meta = dst.create_group(GRP_METADATA)
        meta.attrs[ATTR_SCHEMA_VERSION] = SCHEMA_VERSION
        meta.attrs[ATTR_SIM] = True
        if metadata:
            for key, value in metadata.items():
                meta.attrs[str(key)] = _canonicalize_hdf5_attr(value)
        meta.attrs["storage_mode"] = STORAGE_MODE_VDS
        meta.attrs["vds_source_path"] = str(source_ref)
        meta.attrs["vds_source_abs_path"] = str(source_path.resolve())
        meta.attrs["vds_source_start_step"] = int(start)
        meta.attrs["vds_source_end_step_exclusive"] = int(end)
        meta.attrs["vds_path_mode"] = "relative" if relative_paths else "absolute"
        dst.attrs[ATTR_SIM] = True

        obs_grp = dst.create_group(GRP_OBS)
        _create_vds(dst, src=src, target_path=DS_QPOS, source_path=DS_QPOS, source_ref=source_ref, start=start, end=end)
        _create_vds(dst, src=src, target_path=DS_QVEL, source_path=DS_QVEL, source_ref=source_ref, start=start, end=end)
        if DS_ENV_STATE in src:
            _create_vds(dst, src=src, target_path=DS_ENV_STATE, source_path=DS_ENV_STATE, source_ref=source_ref, start=start, end=end)

        if "observations/images" in src:
            obs_grp.require_group("images")
            for camera_name in src["observations/images"]:
                dataset_path = f"observations/images/{camera_name}"
                _create_vds(
                    dst,
                    src=src,
                    target_path=dataset_path,
                    source_path=dataset_path,
                    source_ref=source_ref,
                    start=start,
                    end=end,
                )

        if GRP_ENCODED_IMAGES in src:
            obs_grp.require_group("encoded_images")
            for camera_name in src[GRP_ENCODED_IMAGES]:
                dataset_path = f"{GRP_ENCODED_IMAGES}/{camera_name}"
                _create_vds(
                    dst,
                    src=src,
                    target_path=dataset_path,
                    source_path=dataset_path,
                    source_ref=source_ref,
                    start=start,
                    end=end,
                )
                _copy_attrs(src[dataset_path].attrs, dst[dataset_path].attrs)

        _create_vds(dst, src=src, target_path=DS_ACTION, source_path=DS_ACTION, source_ref=source_ref, start=start, end=end)
        if DS_REWARDS in src:
            _create_vds(dst, src=src, target_path=DS_REWARDS, source_path=DS_REWARDS, source_ref=source_ref, start=start, end=end)

        if DS_STEP_ID in src or DS_STEP_NS in src:
            dst.require_group(GRP_TIMESTAMPS)
            if DS_STEP_ID in src:
                _create_vds(dst, src=src, target_path=DS_STEP_ID, source_path=DS_STEP_ID, source_ref=source_ref, start=start, end=end)
            if DS_STEP_NS in src:
                _create_vds(dst, src=src, target_path=DS_STEP_NS, source_path=DS_STEP_NS, source_ref=source_ref, start=start, end=end)

        if DS_ACTION_SRC_TYPE in src or action_src_types is not None or action_src_ids is not None:
            src_grp = dst.require_group(GRP_ACTION_SOURCE)
            if action_src_types is None and DS_ACTION_SRC_TYPE in src:
                action_src_types = _read_string_slice(src[DS_ACTION_SRC_TYPE], start=start, end=end)
            if action_src_ids is None and DS_ACTION_SRC_ID in src:
                action_src_ids = _read_string_slice(src[DS_ACTION_SRC_ID], start=start, end=end)
            if action_src_types is not None:
                _write_string_dataset(src_grp, "type", action_src_types)
            if action_src_ids is not None:
                _write_string_dataset(src_grp, "id", action_src_ids)

        _write_v2_mixed(
            dst=dst,
            src=src,
            source_ref=source_ref,
            start=start,
            end=end,
            step_overlay=dict(v2_step_overlay or {}),
            cycle_payload=dict(v2_cycle_payload or {}),
        )


def write_lineage_json(
    output_root: str | Path,
    *,
    builder: str,
    storage_mode: str,
    source_roots: Iterable[str | Path],
    input_dataset_ids: Iterable[str] | None = None,
    schema_versions: dict[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write standard lineage metadata for an immutable builder output root."""
    output_root = Path(output_root)
    payload: dict[str, Any] = {
        "builder": str(builder),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "command": " ".join(sys.argv),
        "git_commit": _git(["rev-parse", "HEAD"]),
        "git_status_short": _git(["status", "--short"]),
        "schema_versions": dict(schema_versions or {"hdf5": SCHEMA_VERSION}),
        "storage_mode": str(storage_mode),
        "vds_path_mode": "relative" if storage_mode == STORAGE_MODE_VDS else "",
        "source_roots": [str(Path(path)) for path in source_roots],
        "output_root": str(output_root),
        "input_dataset_ids": list(input_dataset_ids or []),
    }
    if extra:
        payload.update(extra)
    output_root.mkdir(parents=True, exist_ok=True)
    with open(output_root / "lineage.json", "w") as f:
        json.dump(_jsonable(payload), f, indent=2, sort_keys=True)
    return payload


def update_current_symlink(
    *,
    symlink_path: str | Path,
    target_path: str | Path,
) -> None:
    """Point a current-candidate symlink at a builder output root."""
    symlink_path = Path(symlink_path)
    target_path = Path(target_path)
    if symlink_path.exists() and not symlink_path.is_symlink():
        raise FileExistsError(
            f"{symlink_path} exists and is not a symlink; refusing to replace it."
        )
    symlink_path.parent.mkdir(parents=True, exist_ok=True)
    if symlink_path.is_symlink():
        symlink_path.unlink()
    relative_target = os.path.relpath(
        target_path.resolve(),
        start=symlink_path.parent.resolve(),
    )
    symlink_path.symlink_to(relative_target, target_is_directory=True)


def _normalise_crop(*, crop: slice, source_len: int) -> tuple[int, int]:
    start = 0 if crop.start is None else int(crop.start)
    stop = source_len if crop.stop is None else int(crop.stop)
    step = 1 if crop.step is None else int(crop.step)
    if step != 1:
        raise ValueError("VDS episode crops must use step=1.")
    start = max(0, min(start, source_len))
    stop = max(start, min(stop, source_len))
    if stop <= start:
        raise ValueError("VDS episode crop must contain at least one timestep.")
    return start, stop


def _source_ref_for_target(
    *,
    source_path: Path,
    target_path: Path,
    relative_paths: bool,
) -> str:
    if not relative_paths:
        return str(source_path.resolve())
    return os.path.relpath(source_path.resolve(), start=target_path.parent.resolve())


def _create_vds(
    h5_file: h5py.File,
    *,
    src: h5py.File,
    target_path: str,
    source_path: str,
    source_ref: str,
    start: int,
    end: int,
) -> None:
    source_dataset = src[source_path]
    source_shape = tuple(int(value) for value in source_dataset.shape)
    target_shape = (int(end - start),) + source_shape[1:]
    layout = h5py.VirtualLayout(shape=target_shape, dtype=source_dataset.dtype)
    vsource = h5py.VirtualSource(source_ref, source_path, shape=source_shape)
    layout[...] = vsource[start:end]
    parent = Path(target_path).parent.as_posix()
    if parent and parent != ".":
        h5_file.require_group(parent)
    h5_file.create_virtual_dataset(target_path, layout)
    _copy_attrs(source_dataset.attrs, h5_file[target_path].attrs)


def _write_v2_mixed(
    *,
    dst: h5py.File,
    src: h5py.File,
    source_ref: str,
    start: int,
    end: int,
    step_overlay: dict[str, np.ndarray],
    cycle_payload: dict[str, np.ndarray],
) -> None:
    if GRP_V2_STEP not in src and not step_overlay and not cycle_payload:
        return
    v2_grp = dst.require_group(GRP_V2)
    if GRP_V2_STEP in src or step_overlay:
        step_grp = v2_grp.require_group("step")
        overlay_keys = set(step_overlay)
        if GRP_V2_STEP in src:
            source_step_group = src[GRP_V2_STEP]
            for key in source_step_group:
                if key in overlay_keys:
                    continue
                _create_vds(
                    dst,
                    src=src,
                    target_path=f"{GRP_V2_STEP}/{key}",
                    source_path=f"{GRP_V2_STEP}/{key}",
                    source_ref=source_ref,
                    start=start,
                    end=end,
                )
        _write_dataset_group(step_grp, step_overlay)
        if GRP_V2_STEP in src:
            for key in step_overlay:
                source_key = f"{GRP_V2_STEP}/{key}"
                target_key = f"{GRP_V2_STEP}/{key}"
                if source_key in src and target_key in dst:
                    _copy_attrs(src[source_key].attrs, dst[target_key].attrs)
    if cycle_payload:
        _write_dataset_group(v2_grp.require_group("cycle"), cycle_payload)
        if GRP_V2_CYCLE in src:
            for key in cycle_payload:
                source_key = f"{GRP_V2_CYCLE}/{key}"
                target_key = f"{GRP_V2_CYCLE}/{key}"
                if source_key in src and target_key in dst:
                    _copy_attrs(src[source_key].attrs, dst[target_key].attrs)


def _write_dataset_group(group: h5py.Group, payload: dict[str, np.ndarray]) -> None:
    for key, value in payload.items():
        arr = np.asarray(value)
        if arr.dtype.kind in {"U", "O"}:
            _write_string_dataset(group, str(key), arr.reshape(-1))
            continue
        group.create_dataset(str(key), data=arr)


def _write_string_dataset(group: h5py.Group, name: str, values: Iterable[Any]) -> None:
    values = [_canonical_hdf5_text(value) for value in values]
    str_dtype = h5py.special_dtype(vlen=str)
    ds = group.create_dataset(str(name), (len(values),), dtype=str_dtype)
    for index, value in enumerate(values):
        ds[index] = value


def _copy_attrs(src_attrs: h5py.AttributeManager, dst_attrs: h5py.AttributeManager) -> None:
    for key, value in src_attrs.items():
        dst_attrs[key] = _canonicalize_hdf5_attr(value)


def _read_string_slice(dataset: h5py.Dataset, *, start: int, end: int) -> list[str]:
    values = dataset[start:end]
    return [_canonical_hdf5_text(item) for item in values]


def _canonical_hdf5_text(value: Any) -> str:
    """Decode HDF5 text and unwrap accidental nested bytes-literal strings.

    Older wrapper builders converted raw ``bytes`` with ``str(value)``. Repeating
    that operation produced values such as ``b\"b'gold'\"``. Only exact Python
    bytes literals are unwrapped; ordinary strings containing similar text are
    left unchanged unless the entire value is a bytes literal.
    """

    if isinstance(value, (bytes, np.bytes_)):
        text = bytes(value).decode("utf-8")
    else:
        text = str(value)
    max_nested_bytes_literals = 4
    for _ in range(max_nested_bytes_literals):
        if not text.startswith(("b'", 'b"')):
            return text
        try:
            decoded = ast.literal_eval(text)
        except (SyntaxError, ValueError) as exc:
            raise ValueError(
                f"HDF5 text cannot be canonicalized as a bytes literal: {text!r}"
            ) from exc
        if not isinstance(decoded, bytes):
            raise ValueError(
                f"HDF5 text cannot be canonicalized as bytes: {text!r}"
            )
        next_text = decoded.decode("utf-8")
        if next_text == text:
            raise ValueError(f"HDF5 text canonicalization made no progress: {text!r}")
        text = next_text
    if text.startswith(("b'", 'b"')):
        raise ValueError(
            "HDF5 text contains more than 4 nested bytes literals: "
            f"{text!r}"
        )
    return text


def _canonicalize_hdf5_attr(value: Any) -> Any:
    if isinstance(value, (str, bytes, np.str_, np.bytes_)):
        return _canonical_hdf5_text(value)
    return value


def _git(args: list[str]) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return value
