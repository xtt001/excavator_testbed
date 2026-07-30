"""Dataset quality-control utilities for recorded HDF5 episodes."""

from __future__ import annotations

import csv
import datetime
import json
from pathlib import Path
from typing import Any

import h5py
import matplotlib
import numpy as np

from testbed.data.camera_images import (
    JPEG_ENCODING,
    camera_names_from_metadata,
    decode_jpeg_rgb,
)
from testbed.data.hdf5_io import list_episodes, read_episode
from testbed.data.schema import (
    ATTR_ENV_STATE_ORDER,
    ATTR_EPISODE_ID,
    GRP_ENCODED_IMAGES,
)

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def run_dataset_qc(
    dataset_dir: str | Path,
    output_dir: str | Path | None = None,
    *,
    short_episode_threshold: int = 50,
    expected_camera_names: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    dataset_dir = Path(dataset_dir)
    output_dir = Path(output_dir) if output_dir is not None else dataset_dir / "qc"
    output_dir.mkdir(parents=True, exist_ok=True)

    episode_paths = list_episodes(dataset_dir)
    if not episode_paths:
        raise FileNotFoundError(f"No episode_*.hdf5 files found under {dataset_dir}")

    rows: list[dict[str, Any]] = []
    actions_all: list[np.ndarray] = []
    qpos_all: list[np.ndarray] = []
    qvel_all: list[np.ndarray] = []
    env_state_all: list[np.ndarray] = []
    env_state_orders: set[str] = set()
    unreadable_episode_ids: list[str] = []
    unreadable_episode_errors: dict[str, str] = {}

    short_episode_ids: list[str] = []
    missing_image_ids: list[str] = []
    missing_env_state_ids: list[str] = []
    missing_step_ns_ids: list[str] = []
    non_monotonic_step_ids: list[str] = []
    nan_or_inf_ids: list[str] = []
    shape_mismatch_ids: list[str] = []
    camera_contract_error_ids: list[str] = []
    camera_contract_errors: dict[str, list[str]] = {}

    for path in episode_paths:
        episode_id = path.stem
        camera_audit = _audit_episode_cameras(
            path,
            expected_camera_names=expected_camera_names,
        )
        if camera_audit["errors"]:
            camera_contract_error_ids.append(episode_id)
            camera_contract_errors[episode_id] = list(camera_audit["errors"])
        try:
            episode = read_episode(path)
        except Exception as exc:
            unreadable_episode_ids.append(episode_id)
            unreadable_episode_errors[episode_id] = f"{type(exc).__name__}: {exc}"
            rows.append(
                {
                    "episode_id": episode_id,
                    "path": str(path),
                    "n_steps": -1,
                    "success": 0,
                    "has_images": 0,
                    "has_env_state": 0,
                    "env_state_dim": 0,
                    "step_ids_monotonic": 0,
                    "has_step_ns": 0,
                    "has_v2": 0,
                    "action_dim": -1,
                    "qpos_dim": -1,
                    "qvel_dim": -1,
                    "camera_count": int(camera_audit["camera_count"]),
                    "camera_names": ",".join(camera_audit["camera_names"]),
                    "camera_format": str(camera_audit["format"]),
                    "camera_shapes": json.dumps(camera_audit["shapes"], sort_keys=True),
                    "camera_errors": ";".join(camera_audit["errors"]),
                    "timestamp": "",
                    "operator_id": "",
                    "session_id": "",
                    "warnings": "unreadable_episode",
                    "error": unreadable_episode_errors[episode_id],
                }
            )
            continue

        metadata = dict(episode.get("metadata", {}))
        episode_id = str(metadata.get(ATTR_EPISODE_ID, path.stem))
        actions = np.asarray(episode["actions"], dtype=np.float32)
        qpos = np.asarray(episode["qpos"], dtype=np.float32)
        qvel = np.asarray(episode["qvel"], dtype=np.float32)
        env_state_raw = episode.get("env_state")
        env_state = None if env_state_raw is None else np.asarray(env_state_raw, dtype=np.float32)
        step_ids = episode.get("step_ids")
        step_ns = episode.get("step_ns")
        images = episode.get("images", {})
        v2_data = episode.get("v2")
        success = bool(int(metadata.get("success", 0)))
        n_steps = int(len(actions))

        warnings: list[str] = []
        if n_steps < short_episode_threshold:
            warnings.append("short_episode")
            short_episode_ids.append(episode_id)
        if not images:
            warnings.append("missing_images")
            missing_image_ids.append(episode_id)
        if camera_audit["errors"]:
            warnings.append("camera_contract")
        if env_state is None:
            warnings.append("missing_env_state")
            missing_env_state_ids.append(episode_id)
        if step_ns is None:
            warnings.append("missing_step_ns")
            missing_step_ns_ids.append(episode_id)
        if step_ids is not None and len(step_ids) > 1 and np.any(np.diff(step_ids) <= 0):
            warnings.append("non_monotonic_step_id")
            non_monotonic_step_ids.append(episode_id)

        expected_len = n_steps
        if qpos.shape[0] != expected_len or qvel.shape[0] != expected_len:
            warnings.append("shape_mismatch")
            shape_mismatch_ids.append(episode_id)
        if env_state is not None and env_state.shape[0] != expected_len:
            warnings.append("shape_mismatch")
            if episode_id not in shape_mismatch_ids:
                shape_mismatch_ids.append(episode_id)

        arrays_to_check = [actions, qpos, qvel]
        if env_state is not None:
            arrays_to_check.append(env_state)
        if any(np.isnan(arr).any() or np.isinf(arr).any() for arr in arrays_to_check):
            warnings.append("nan_or_inf")
            nan_or_inf_ids.append(episode_id)

        env_state_order = metadata.get(ATTR_ENV_STATE_ORDER, "")
        if env_state_order:
            env_state_orders.add(str(env_state_order))

        actions_all.append(actions)
        qpos_all.append(qpos)
        qvel_all.append(qvel)
        if env_state is not None:
            env_state_all.append(env_state)

        rows.append(
            {
                "episode_id": episode_id,
                "path": str(path),
                "n_steps": n_steps,
                "success": int(success),
                "has_images": int(bool(images)),
                "has_env_state": int(env_state is not None),
                "env_state_dim": 0 if env_state is None else int(env_state.shape[1]),
                "step_ids_monotonic": int("non_monotonic_step_id" not in warnings),
                "has_step_ns": int(step_ns is not None),
                "has_v2": int(v2_data is not None),
                "action_dim": int(actions.shape[1]) if actions.ndim == 2 else -1,
                "qpos_dim": int(qpos.shape[1]) if qpos.ndim == 2 else -1,
                "qvel_dim": int(qvel.shape[1]) if qvel.ndim == 2 else -1,
                "camera_count": int(camera_audit["camera_count"]),
                "camera_names": ",".join(camera_audit["camera_names"]),
                "camera_format": str(camera_audit["format"]),
                "camera_shapes": json.dumps(camera_audit["shapes"], sort_keys=True),
                "camera_errors": ";".join(camera_audit["errors"]),
                "timestamp": str(metadata.get("timestamp", "")),
                "operator_id": str(metadata.get("operator_id", "")),
                "session_id": str(metadata.get("session_id", "")),
                "warnings": ";".join(warnings),
                "error": "",
            }
        )

    if not actions_all:
        raise RuntimeError(
            "No readable episodes were found for dataset QC. "
            f"Unreadable episodes: {', '.join(unreadable_episode_ids) if unreadable_episode_ids else 'none'}"
        )

    actions_cat = np.concatenate(actions_all, axis=0)
    qpos_cat = np.concatenate(qpos_all, axis=0)
    qvel_cat = np.concatenate(qvel_all, axis=0)
    env_state_cat = np.concatenate(env_state_all, axis=0) if env_state_all else None
    lengths = np.array([int(row["n_steps"]) for row in rows], dtype=np.int32)
    success_values = np.array([int(row["success"]) for row in rows], dtype=np.int32)

    summary = {
        "generated_at": datetime.datetime.utcnow().isoformat(),
        "dataset_dir": str(dataset_dir),
        "output_dir": str(output_dir),
        "n_episodes": len(rows),
        "n_success": int(success_values.sum()),
        "success_rate": float(success_values.mean()) if len(success_values) > 0 else 0.0,
        "n_v2_episodes": int(sum(int(row.get("has_v2", 0)) for row in rows)),
        "episode_length": _series_stats(lengths.reshape(-1, 1)),
        "stats": {
            "action": _series_stats(actions_cat),
            "qpos": _series_stats(qpos_cat),
            "qvel": _series_stats(qvel_cat),
            "env_state": None if env_state_cat is None else _series_stats(env_state_cat),
        },
        "warnings": {
            "unreadable_episode_ids": unreadable_episode_ids,
            "unreadable_episode_errors": unreadable_episode_errors,
            "short_episode_ids": short_episode_ids,
            "missing_image_ids": missing_image_ids,
            "missing_env_state_ids": missing_env_state_ids,
            "missing_step_ns_ids": missing_step_ns_ids,
            "non_monotonic_step_ids": non_monotonic_step_ids,
            "nan_or_inf_ids": nan_or_inf_ids,
            "shape_mismatch_ids": shape_mismatch_ids,
            "camera_contract_error_ids": camera_contract_error_ids,
            "camera_contract_errors": camera_contract_errors,
        },
        "env_state_order_values": sorted(env_state_orders),
        "env_state_order_consistent": len(env_state_orders) <= 1,
    }

    summary_path = output_dir / "summary.json"
    episodes_csv_path = output_dir / "episodes.csv"
    _write_json(summary_path, summary)
    _write_csv(episodes_csv_path, rows)
    _plot_episode_length_hist(lengths, output_dir / "episode_length_hist.png")
    _plot_action_distribution(actions_cat, output_dir / "action_distribution.png")
    _plot_state_ranges(
        qpos=qpos_cat,
        qvel=qvel_cat,
        env_state=env_state_cat,
        path=output_dir / "state_ranges.png",
    )
    return {
        "summary_path": str(summary_path),
        "episodes_csv_path": str(episodes_csv_path),
        "output_dir": str(output_dir),
        "summary": summary,
    }


def _audit_episode_cameras(
    path: Path,
    *,
    expected_camera_names: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "camera_count": 0,
        "camera_names": [],
        "format": "none",
        "shapes": {},
        "errors": [],
    }
    try:
        with h5py.File(path, "r") as handle:
            metadata = dict(handle["metadata"].attrs) if "metadata" in handle else {}
            configured = camera_names_from_metadata(metadata)
            raw_group = handle.get("observations/images")
            encoded_group = handle.get(GRP_ENCODED_IMAGES)
            raw_names = list(raw_group.keys()) if raw_group is not None else []
            encoded_names = list(encoded_group.keys()) if encoded_group is not None else []
            stored_names = raw_names or encoded_names
            result["camera_count"] = len(stored_names)
            result["camera_names"] = configured or stored_names
            result["format"] = "mixed" if raw_names and encoded_names else (
                JPEG_ENCODING if encoded_names else ("raw_rgb" if raw_names else "none")
            )
            if raw_names and encoded_names:
                result["errors"].append(
                    f"mixed_camera_layout:raw={raw_names},encoded={encoded_names}"
                )
            if configured and set(configured) != set(stored_names):
                missing = [name for name in configured if name not in stored_names]
                unexpected = [name for name in stored_names if name not in configured]
                result["errors"].append(
                    f"camera_set_mismatch:missing={missing},unexpected={unexpected}"
                )
            expected_names = [str(name) for name in expected_camera_names or ()]
            if expected_names:
                actual_names = configured or stored_names
                if set(expected_names) != set(actual_names):
                    missing = [name for name in expected_names if name not in actual_names]
                    unexpected = [name for name in actual_names if name not in expected_names]
                    result["errors"].append(
                        f"expected_camera_set_mismatch:missing={missing},unexpected={unexpected}"
                    )
                elif actual_names != expected_names:
                    result["errors"].append(
                        f"camera_order_mismatch:expected={expected_names},actual={actual_names}"
                    )
            expected_len = int(handle["action"].shape[0]) if "action" in handle else -1
            for camera_name in raw_names:
                dataset = raw_group[camera_name]
                if dataset.ndim != 4 or dataset.dtype != np.dtype("uint8") or dataset.shape[-1] != 3:
                    result["errors"].append(
                        f"camera={camera_name}:raw_layout_invalid:shape={dataset.shape},dtype={dataset.dtype}"
                    )
                    continue
                result["shapes"][camera_name] = list(dataset.shape[1:])
                if int(dataset.shape[0]) != expected_len:
                    result["errors"].append(
                        f"camera={camera_name}:length_mismatch:expected={expected_len},actual={dataset.shape[0]}"
                    )
            for camera_name in encoded_names:
                dataset = encoded_group[camera_name]
                encoding = dataset.attrs.get("encoding", "")
                if isinstance(encoding, bytes):
                    encoding = encoding.decode("utf-8", errors="replace")
                vlen_base = h5py.check_vlen_dtype(dataset.dtype)
                if dataset.ndim != 1 or vlen_base != np.dtype("uint8"):
                    result["errors"].append(
                        f"camera={camera_name}:encoded_layout_invalid:shape={dataset.shape},dtype={dataset.dtype}"
                    )
                    continue
                if str(encoding).lower() != JPEG_ENCODING:
                    result["errors"].append(
                        f"camera={camera_name}:encoding_invalid:expected=jpeg,actual={encoding}"
                    )
                if int(dataset.shape[0]) != expected_len:
                    result["errors"].append(
                        f"camera={camera_name}:length_mismatch:expected={expected_len},actual={dataset.shape[0]}"
                    )
                decoded_shape = None
                for frame_index in range(int(dataset.shape[0])):
                    try:
                        decoded = decode_jpeg_rgb(dataset[frame_index])
                    except Exception as exc:
                        result["errors"].append(
                            f"camera={camera_name}:frame={frame_index}:jpeg_decode_failed:{exc}"
                        )
                        continue
                    if decoded.dtype != np.uint8 or decoded.ndim != 3 or decoded.shape[-1] != 3:
                        result["errors"].append(
                            f"camera={camera_name}:frame={frame_index}:decoded_layout_invalid:"
                            f"shape={decoded.shape},dtype={decoded.dtype}"
                        )
                        continue
                    shape = tuple(int(value) for value in decoded.shape)
                    if decoded_shape is None:
                        decoded_shape = shape
                    elif shape != decoded_shape:
                        result["errors"].append(
                            f"camera={camera_name}:frame={frame_index}:dimension_mismatch:"
                            f"expected={decoded_shape},actual={shape}"
                        )
                if decoded_shape is not None:
                    result["shapes"][camera_name] = list(decoded_shape)
            distinct_shapes = {
                tuple(int(value) for value in shape)
                for shape in result["shapes"].values()
            }
            if len(distinct_shapes) > 1:
                result["errors"].append(
                    f"camera_dimensions_inconsistent:shapes={result['shapes']}"
                )
    except Exception as exc:
        result["errors"].append(f"camera_audit_unreadable:{type(exc).__name__}:{exc}")
    return result

def _series_stats(array: np.ndarray) -> dict[str, Any]:
    array = np.asarray(array, dtype=np.float64)
    return {
        "shape": list(array.shape),
        "min": np.min(array, axis=0).tolist(),
        "max": np.max(array, axis=0).tolist(),
        "mean": np.mean(array, axis=0).tolist(),
        "std": np.std(array, axis=0).tolist(),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    with open(path, "w") as f:
        json.dump(_to_jsonable(payload), f, indent=2)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _plot_episode_length_hist(lengths: np.ndarray, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(6, 4))
    bins = min(20, max(5, len(lengths)))
    ax.hist(lengths, bins=bins, color="#4c78a8", edgecolor="white")
    ax.set_title("Episode Length Distribution")
    ax.set_xlabel("Steps")
    ax.set_ylabel("Count")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _plot_action_distribution(actions: np.ndarray, path: Path) -> None:
    num_dims = actions.shape[1]
    fig, axes = plt.subplots(num_dims, 1, figsize=(7, max(3, 2 * num_dims)), squeeze=False)
    for dim in range(num_dims):
        ax = axes[dim, 0]
        ax.hist(actions[:, dim], bins=40, color="#f58518", edgecolor="white")
        ax.set_title(f"Action dim {dim}")
        ax.set_xlabel("Value")
        ax.set_ylabel("Count")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _plot_state_ranges(
    *,
    qpos: np.ndarray,
    qvel: np.ndarray,
    env_state: np.ndarray | None,
    path: Path,
) -> None:
    fig, axes = plt.subplots(3, 1, figsize=(8, 9))
    _plot_range_panel(axes[0], qpos, "qpos")
    _plot_range_panel(axes[1], qvel, "qvel")
    if env_state is None:
        axes[2].set_title("env_state")
        axes[2].text(0.5, 0.5, "missing in dataset", ha="center", va="center")
        axes[2].set_axis_off()
    else:
        _plot_range_panel(axes[2], env_state, "env_state")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _plot_range_panel(ax, array: np.ndarray, title: str) -> None:
    mins = np.min(array, axis=0)
    maxs = np.max(array, axis=0)
    means = np.mean(array, axis=0)
    xs = np.arange(array.shape[1])
    ax.fill_between(xs, mins, maxs, color="#72b7b2", alpha=0.35, label="min/max")
    ax.plot(xs, means, color="#54a24b", linewidth=2, label="mean")
    ax.set_title(title)
    ax.set_xlabel("Dimension")
    ax.legend(loc="best")


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value
