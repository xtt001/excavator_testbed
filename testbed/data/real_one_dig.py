"""Real-machine one-dig dataset conversion utilities.

This module owns the HDF5 data contract for the v1 real one-dig windows:
source episodes are cropped, JPEG FPV frames are decoded to raw RGB, and the
resulting files are written in the training-compatible episode layout.
"""

from __future__ import annotations

import csv
import datetime as _dt
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from testbed.data.schema import (
    ATTR_ACTION_ORDER,
    ATTR_CAMERA_NAMES,
    ATTR_CONTROL_HZ,
    ATTR_IMAGE_FORMAT,
    ATTR_QPOS_ORDER,
    ATTR_QVEL_ORDER,
    ATTR_SCHEMA_VERSION,
    ATTR_SIM,
    DEFAULT_IMAGE_FORMAT,
    DS_ACTION,
    DS_ENV_STATE,
    DS_QPOS,
    DS_QVEL,
    DS_REWARDS,
    GRP_ACTION_SOURCE,
    GRP_METADATA,
    GRP_TIMESTAMPS,
    SCHEMA_VERSION,
)

REAL_ONE_DIG_SOURCE_EPISODE_IDS = tuple(range(13, 22))
EXCAVATOR_JOINT_ORDER = ("swing", "boom", "stick", "bucket")
REAL_ONE_DIG_DATASET_KIND = "real_one_dig_window_v1"
DEFAULT_CAMERA_NAME = "fpv"
DEFAULT_PRE_ACTION_CONTEXT_STEPS = 25
DEFAULT_GO_HOME_MARGIN_STEPS = 25
DEFAULT_ACTIVE_EPS = 1e-6


@dataclass(frozen=True)
class RealOneDigWindow:
    """Crop indices for one source recording."""

    start_index: int
    end_index_exclusive: int
    raw_first_active_index: int | None
    go_home_first_active_index: int | None

    @property
    def length(self) -> int:
        return self.end_index_exclusive - self.start_index


@dataclass(frozen=True)
class RealOneDigBuildResult:
    """Conversion summary for one output episode."""

    source_episode_id: int
    output_episode_id: int
    source_path: str
    output_path: str
    input_steps: int
    output_steps: int
    start_index: int
    end_index_exclusive: int
    raw_first_active_index: int | None
    go_home_first_active_index: int | None
    control_hz: float
    duration_s: float
    action_min: list[float]
    action_max: list[float]
    qpos_min: list[float]
    qpos_max: list[float]
    qvel_min: list[float]
    qvel_max: list[float]
    wrote_file: bool


def find_one_dig_window(
    *,
    raw_action: np.ndarray,
    go_home_commanded_action: np.ndarray | None,
    pre_action_context_steps: int = DEFAULT_PRE_ACTION_CONTEXT_STEPS,
    go_home_margin_steps: int = DEFAULT_GO_HOME_MARGIN_STEPS,
    active_eps: float = DEFAULT_ACTIVE_EPS,
) -> RealOneDigWindow:
    """Return the crop window for a real one-dig recording."""

    raw = np.asarray(raw_action, dtype=np.float32)
    if raw.ndim != 2:
        raise ValueError(f"raw_action must be 2-D, got shape {raw.shape}")
    source_len = int(raw.shape[0])
    active_rows = np.flatnonzero(np.any(np.abs(raw) > active_eps, axis=1))
    raw_first = int(active_rows[0]) if active_rows.size else None
    start = 0 if raw_first is None else max(0, raw_first - int(pre_action_context_steps))

    go_first = None
    if go_home_commanded_action is not None:
        go_home = np.asarray(go_home_commanded_action, dtype=np.float32)
        if go_home.ndim != 2 or go_home.shape[0] != source_len:
            raise ValueError(
                "go_home_commanded_action must be 2-D and time-aligned with raw_action; "
                f"got {go_home.shape}, expected first dim {source_len}"
            )
        go_rows = np.flatnonzero(np.any(np.abs(go_home) > active_eps, axis=1))
        if go_rows.size:
            go_first = int(go_rows[0])

    end = source_len if go_first is None else max(0, go_first - int(go_home_margin_steps))
    end = min(source_len, end)
    if end <= start:
        raise ValueError(
            "Computed an empty one-dig crop window: "
            f"start={start}, end={end}, raw_first={raw_first}, go_home_first={go_first}"
        )
    return RealOneDigWindow(
        start_index=int(start),
        end_index_exclusive=int(end),
        raw_first_active_index=raw_first,
        go_home_first_active_index=go_first,
    )


def build_real_one_dig_dataset(
    source_dir: str | Path,
    output_dir: str | Path,
    *,
    episode_ids: Iterable[int] = REAL_ONE_DIG_SOURCE_EPISODE_IDS,
    camera_name: str = DEFAULT_CAMERA_NAME,
    overwrite: bool = False,
    dry_run: bool = False,
    reindex: bool = True,
    compression: str | None = "lzf",
    pre_action_context_steps: int = DEFAULT_PRE_ACTION_CONTEXT_STEPS,
    go_home_margin_steps: int = DEFAULT_GO_HOME_MARGIN_STEPS,
    active_eps: float = DEFAULT_ACTIVE_EPS,
) -> list[RealOneDigBuildResult]:
    """Convert selected real recordings into training-compatible windows."""

    source_dir = Path(source_dir)
    output_dir = Path(output_dir)
    selected_episode_ids = [int(ep_id) for ep_id in episode_ids]
    if not selected_episode_ids:
        raise ValueError("episode_ids must not be empty")
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Source dataset directory does not exist: {source_dir}")

    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    results: list[RealOneDigBuildResult] = []
    for ordinal, source_episode_id in enumerate(selected_episode_ids):
        source_path = source_dir / f"episode_{source_episode_id}.hdf5"
        if not source_path.exists():
            raise FileNotFoundError(f"Missing source episode: {source_path}")

        output_episode_id = ordinal if reindex else source_episode_id
        output_path = output_dir / f"episode_{output_episode_id}.hdf5"
        if output_path.exists() and not overwrite and not dry_run:
            raise FileExistsError(
                f"Output episode already exists: {output_path}. Use --overwrite to replace it."
            )

        result = _convert_one_episode(
            source_path=source_path,
            output_path=output_path,
            source_episode_id=source_episode_id,
            output_episode_id=output_episode_id,
            camera_name=camera_name,
            overwrite=overwrite,
            dry_run=dry_run,
            compression=_normalize_compression(compression),
            pre_action_context_steps=pre_action_context_steps,
            go_home_margin_steps=go_home_margin_steps,
            active_eps=active_eps,
        )
        results.append(result)

    if not dry_run:
        _write_conversion_summary(output_dir, results)
    return results


def _convert_one_episode(
    *,
    source_path: Path,
    output_path: Path,
    source_episode_id: int,
    output_episode_id: int,
    camera_name: str,
    overwrite: bool,
    dry_run: bool,
    compression: str | None,
    pre_action_context_steps: int,
    go_home_margin_steps: int,
    active_eps: float,
) -> RealOneDigBuildResult:
    with h5py.File(source_path, "r") as src:
        _validate_source_episode(src, camera_name=camera_name)
        source_len = int(src[DS_ACTION].shape[0])
        raw_action = src["diagnostics/raw_action"][()]
        go_home = (
            src["diagnostics/go_home_commanded_action"][()]
            if "diagnostics/go_home_commanded_action" in src
            else None
        )
        window = find_one_dig_window(
            raw_action=raw_action,
            go_home_commanded_action=go_home,
            pre_action_context_steps=pre_action_context_steps,
            go_home_margin_steps=go_home_margin_steps,
            active_eps=active_eps,
        )

        start = window.start_index
        end = window.end_index_exclusive
        actions = src[DS_ACTION][start:end].astype(np.float32)
        qpos = src[DS_QPOS][start:end].astype(np.float32)
        qvel = src[DS_QVEL][start:end].astype(np.float32)
        control_hz = float(_read_metadata_attrs(src).get(ATTR_CONTROL_HZ, 50.0))

        result = RealOneDigBuildResult(
            source_episode_id=int(source_episode_id),
            output_episode_id=int(output_episode_id),
            source_path=str(source_path),
            output_path=str(output_path),
            input_steps=int(source_len),
            output_steps=int(end - start),
            start_index=int(start),
            end_index_exclusive=int(end),
            raw_first_active_index=window.raw_first_active_index,
            go_home_first_active_index=window.go_home_first_active_index,
            control_hz=control_hz,
            duration_s=float((end - start) / control_hz) if control_hz > 0 else 0.0,
            action_min=_float_list(actions.min(axis=0)),
            action_max=_float_list(actions.max(axis=0)),
            qpos_min=_float_list(qpos.min(axis=0)),
            qpos_max=_float_list(qpos.max(axis=0)),
            qvel_min=_float_list(qvel.min(axis=0)),
            qvel_max=_float_list(qvel.max(axis=0)),
            wrote_file=not dry_run,
        )
        if dry_run:
            return result

        _write_converted_episode(
            src=src,
            source_path=source_path,
            output_path=output_path,
            output_episode_id=output_episode_id,
            window=window,
            camera_name=camera_name,
            compression=compression,
            overwrite=overwrite,
            pre_action_context_steps=pre_action_context_steps,
            go_home_margin_steps=go_home_margin_steps,
            active_eps=active_eps,
        )
        return result


def _write_converted_episode(
    *,
    src: h5py.File,
    source_path: Path,
    output_path: Path,
    output_episode_id: int,
    window: RealOneDigWindow,
    camera_name: str,
    compression: str | None,
    overwrite: bool,
    pre_action_context_steps: int,
    go_home_margin_steps: int,
    active_eps: float,
) -> None:
    start = window.start_index
    end = window.end_index_exclusive
    tmp_path = output_path.with_name(f".{output_path.name}.tmp")
    if tmp_path.exists():
        tmp_path.unlink()
    if output_path.exists() and overwrite:
        output_path.unlink()

    try:
        with h5py.File(tmp_path, "w") as dst:
            _write_real_metadata(
                src=src,
                dst=dst,
                source_path=source_path,
                output_episode_id=output_episode_id,
                window=window,
                camera_name=camera_name,
                pre_action_context_steps=pre_action_context_steps,
                go_home_margin_steps=go_home_margin_steps,
                active_eps=active_eps,
            )
            obs = dst.create_group("observations")
            obs.create_dataset("qpos", data=src[DS_QPOS][start:end].astype(np.float32))
            obs.create_dataset("qvel", data=src[DS_QVEL][start:end].astype(np.float32))
            if DS_ENV_STATE in src:
                obs.create_dataset(
                    "env_state",
                    data=src[DS_ENV_STATE][start:end].astype(np.float32),
                )

            dst.create_dataset(DS_ACTION, data=src[DS_ACTION][start:end].astype(np.float32))
            if DS_REWARDS in src:
                dst.create_dataset(
                    "rewards",
                    data=src[DS_REWARDS][start:end].astype(np.float32),
                )

            _write_decoded_images(
                src=src,
                dst=dst,
                camera_name=camera_name,
                start=start,
                end=end,
                compression=compression,
            )
            _copy_time_aligned_group(
                src=src,
                dst=dst,
                group_name=GRP_TIMESTAMPS,
                start=start,
                end=end,
                source_len=int(src[DS_ACTION].shape[0]),
            )
            _copy_time_aligned_group(
                src=src,
                dst=dst,
                group_name=GRP_ACTION_SOURCE,
                start=start,
                end=end,
                source_len=int(src[DS_ACTION].shape[0]),
            )
            _copy_time_aligned_group(
                src=src,
                dst=dst,
                group_name="diagnostics",
                start=start,
                end=end,
                source_len=int(src[DS_ACTION].shape[0]),
            )
        tmp_path.replace(output_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def _write_real_metadata(
    *,
    src: h5py.File,
    dst: h5py.File,
    source_path: Path,
    output_episode_id: int,
    window: RealOneDigWindow,
    camera_name: str,
    pre_action_context_steps: int,
    go_home_margin_steps: int,
    active_eps: float,
) -> None:
    source_meta = _read_metadata_attrs(src)
    meta = dst.create_group(GRP_METADATA)
    for key, value in source_meta.items():
        _set_attr(meta.attrs, key, value)

    source_image_format = source_meta.get(ATTR_IMAGE_FORMAT, "jpeg")
    action_order = _csv_tuple(source_meta.get(ATTR_ACTION_ORDER, ""))
    qpos_order = _csv_tuple(source_meta.get(ATTR_QPOS_ORDER, ""))
    qvel_order = _csv_tuple(source_meta.get(ATTR_QVEL_ORDER, ""))

    source_episode_id = source_meta.get("episode_id", source_path.stem)
    attrs = {
        ATTR_SCHEMA_VERSION: SCHEMA_VERSION,
        ATTR_SIM: False,
        "is_real": True,
        "dataset_kind": REAL_ONE_DIG_DATASET_KIND,
        "task_name": "real_one_dig_v1",
        "episode_id": f"episode_{int(output_episode_id)}",
        "source_episode_id": str(source_episode_id),
        "source_episode_index": int(source_path.stem.split("_", 1)[1]),
        "source_path": str(source_path),
        "source_dataset_dir": str(source_path.parent),
        "source_schema_version": str(source_meta.get(ATTR_SCHEMA_VERSION, "")),
        "source_image_format": str(source_image_format),
        ATTR_IMAGE_FORMAT: DEFAULT_IMAGE_FORMAT,
        ATTR_CAMERA_NAMES: camera_name,
        "n_steps": int(window.length),
        "source_n_steps": int(src[DS_ACTION].shape[0]),
        "window_start_index": int(window.start_index),
        "window_end_index_exclusive": int(window.end_index_exclusive),
        "raw_first_active_index": -1
        if window.raw_first_active_index is None
        else int(window.raw_first_active_index),
        "go_home_first_active_index": -1
        if window.go_home_first_active_index is None
        else int(window.go_home_first_active_index),
        "window_pre_action_context_steps": int(pre_action_context_steps),
        "window_go_home_margin_steps": int(go_home_margin_steps),
        "window_active_eps": float(active_eps),
        "converted_at": _utc_now_iso(),
        "learning_target": "operator_command_from_observation",
        "raw_action_role": "joystick_offset_analysis_only",
        "commanded_action_role": "machine_command_safety_reference",
    }
    for key, value in attrs.items():
        _set_attr(meta.attrs, key, value)

    if not action_order:
        meta.attrs[ATTR_ACTION_ORDER] = ",".join(EXCAVATOR_JOINT_ORDER)
    if not qpos_order:
        meta.attrs[ATTR_QPOS_ORDER] = ",".join(EXCAVATOR_JOINT_ORDER)
    if not qvel_order:
        meta.attrs[ATTR_QVEL_ORDER] = ",".join(EXCAVATOR_JOINT_ORDER)

    dst.attrs[ATTR_SIM] = False
    dst.attrs["is_real"] = True


def _write_decoded_images(
    *,
    src: h5py.File,
    dst: h5py.File,
    camera_name: str,
    start: int,
    end: int,
    compression: str | None,
) -> None:
    encoded_path = f"observations/encoded_images/{camera_name}"
    encoded = src[encoded_path]
    first = decode_jpeg_rgb(encoded[start])
    n_steps = int(end - start)
    h, w = first.shape[:2]
    img_group = dst.require_group("observations/images")
    kwargs: dict[str, Any] = {"chunks": (1, h, w, 3)}
    if compression is not None:
        kwargs["compression"] = compression
    images = img_group.create_dataset(
        camera_name,
        shape=(n_steps, h, w, 3),
        dtype=np.uint8,
        **kwargs,
    )
    images[0] = first
    for out_idx, src_idx in enumerate(range(start + 1, end), start=1):
        images[out_idx] = decode_jpeg_rgb(encoded[src_idx])


def decode_jpeg_rgb(payload: Any) -> np.ndarray:
    """Decode one HDF5 JPEG payload to an RGB uint8 image."""

    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("opencv-python is required to decode JPEG FPV frames") from exc

    if isinstance(payload, (bytes, bytearray)):
        encoded = np.frombuffer(payload, dtype=np.uint8)
    else:
        encoded = np.asarray(payload, dtype=np.uint8).reshape(-1)
    bgr = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError("Failed to decode JPEG FPV frame")
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def _copy_time_aligned_group(
    *,
    src: h5py.File,
    dst: h5py.File,
    group_name: str,
    start: int,
    end: int,
    source_len: int,
) -> None:
    if group_name not in src:
        return
    src_group = src[group_name]
    dst_group = dst.create_group(group_name)
    _copy_group_attrs(src_group, dst_group)
    for name, item in src_group.items():
        if isinstance(item, h5py.Group):
            child = dst_group.create_group(name)
            _copy_group_attrs(item, child)
            _copy_time_aligned_items(
                src_group=item,
                dst_group=child,
                start=start,
                end=end,
                source_len=source_len,
            )
        elif isinstance(item, h5py.Dataset):
            _copy_dataset_if_time_aligned(
                src_dataset=item,
                dst_group=dst_group,
                name=name,
                start=start,
                end=end,
                source_len=source_len,
            )


def _copy_time_aligned_items(
    *,
    src_group: h5py.Group,
    dst_group: h5py.Group,
    start: int,
    end: int,
    source_len: int,
) -> None:
    for name, item in src_group.items():
        if isinstance(item, h5py.Dataset):
            _copy_dataset_if_time_aligned(
                src_dataset=item,
                dst_group=dst_group,
                name=name,
                start=start,
                end=end,
                source_len=source_len,
            )


def _copy_dataset_if_time_aligned(
    *,
    src_dataset: h5py.Dataset,
    dst_group: h5py.Group,
    name: str,
    start: int,
    end: int,
    source_len: int,
) -> None:
    if not src_dataset.shape or int(src_dataset.shape[0]) != source_len:
        return
    data = src_dataset[start:end]
    try:
        dst = dst_group.create_dataset(name, data=data, dtype=src_dataset.dtype)
    except TypeError:
        dst = dst_group.create_dataset(name, data=data)
    _copy_group_attrs(src_dataset, dst)


def _copy_group_attrs(src_obj: h5py.Group | h5py.Dataset, dst_obj: h5py.Group | h5py.Dataset) -> None:
    for key, value in src_obj.attrs.items():
        _set_attr(dst_obj.attrs, key, value)


def _validate_source_episode(src: h5py.File, *, camera_name: str) -> None:
    required_paths = [
        DS_ACTION,
        DS_QPOS,
        DS_QVEL,
        "diagnostics/raw_action",
        f"observations/encoded_images/{camera_name}",
    ]
    missing = [path for path in required_paths if path not in src]
    if missing:
        raise KeyError(f"Source episode is missing required path(s): {missing}")

    source_len = int(src[DS_ACTION].shape[0])
    for path in (DS_QPOS, DS_QVEL, "diagnostics/raw_action"):
        if int(src[path].shape[0]) != source_len:
            raise ValueError(
                f"{path} is not time-aligned with action: {src[path].shape[0]} vs {source_len}"
            )

    metadata = _read_metadata_attrs(src)
    _validate_order(metadata, ATTR_ACTION_ORDER)
    _validate_order(metadata, ATTR_QPOS_ORDER)
    _validate_order(metadata, ATTR_QVEL_ORDER)
    qvel_units = str(metadata.get("qvel_units", ""))
    if qvel_units and qvel_units != "rad/s":
        raise ValueError(f"Expected qvel_units='rad/s', got {qvel_units!r}")


def _validate_order(metadata: dict[str, Any], attr_name: str) -> None:
    value = metadata.get(attr_name, "")
    if not value:
        return
    order = _csv_tuple(value)
    if order != EXCAVATOR_JOINT_ORDER:
        raise ValueError(
            f"Expected {attr_name}={EXCAVATOR_JOINT_ORDER}, got {order}"
        )


def _read_metadata_attrs(src: h5py.File) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if GRP_METADATA in src:
        metadata.update(dict(src[GRP_METADATA].attrs))
    metadata.update(dict(src.attrs))
    return metadata


def _write_conversion_summary(
    output_dir: Path,
    results: list[RealOneDigBuildResult],
) -> None:
    summary_json = output_dir / "conversion_summary.json"
    summary_csv = output_dir / "conversion_summary.csv"
    payload = {
        "generated_at": _utc_now_iso(),
        "dataset_kind": REAL_ONE_DIG_DATASET_KIND,
        "n_episodes": len(results),
        "source_episode_ids": [result.source_episode_id for result in results],
        "output_episode_ids": [result.output_episode_id for result in results],
        "results": [asdict(result) for result in results],
    }
    summary_json.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    if results:
        with summary_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(asdict(results[0]).keys()))
            writer.writeheader()
            for result in results:
                row = asdict(result)
                for key, value in list(row.items()):
                    if isinstance(value, list):
                        row[key] = json.dumps(value)
                writer.writerow(row)


def _normalize_compression(compression: str | None) -> str | None:
    if compression is None:
        return None
    normalized = str(compression).strip().lower()
    if normalized in ("", "none", "false", "0"):
        return None
    if normalized not in ("lzf", "gzip"):
        raise ValueError("compression must be one of: lzf, gzip, none")
    return normalized


def _utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _csv_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, np.ndarray):
        value = ",".join(str(item) for item in value.tolist())
    return tuple(part.strip() for part in str(value).split(",") if part.strip())


def _float_list(values: np.ndarray) -> list[float]:
    return [float(value) for value in np.asarray(values, dtype=np.float32).reshape(-1)]


def _set_attr(attrs: h5py.AttributeManager, key: str, value: Any) -> None:
    if value is None:
        return
    if isinstance(value, np.generic):
        value = value.item()
    attrs[key] = value
