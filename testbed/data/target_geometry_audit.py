"""Audit AGX datasets for the target-geometry contract."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from testbed.data.hdf5_io import list_episodes
from testbed.data.schema import (
    ATTR_ENV_STATE_ORDER,
    DS_ENV_STATE,
    GRP_METADATA,
    ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
    ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
    ENV_STATE_DUMP_CLEARANCE_OK_IDX,
    ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
)


TARGET_GEOMETRY_FIELDS = (
    "target_horizontal_distance_m",
    "bucket_height_above_target_rim_m",
    "bucket_over_target_footprint_mask",
    "dump_clearance_ok_mask",
)

TARGET_GEOMETRY_FIXED_INDICES = {
    "target_horizontal_distance_m": ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
    "bucket_height_above_target_rim_m": ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
    "bucket_over_target_footprint_mask": ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
    "dump_clearance_ok_mask": ENV_STATE_DUMP_CLEARANCE_OK_IDX,
}


def _metadata_env_state_order(metadata: dict[str, Any]) -> tuple[str, ...]:
    raw_value = metadata.get(ATTR_ENV_STATE_ORDER, "")
    if isinstance(raw_value, bytes):
        raw_value = raw_value.decode()
    if isinstance(raw_value, str):
        return tuple(item.strip() for item in raw_value.split(",") if item.strip())
    if isinstance(raw_value, np.ndarray):
        return tuple(
            item.decode() if isinstance(item, bytes) else str(item)
            for item in raw_value.reshape(-1)
        )
    if isinstance(raw_value, (list, tuple)):
        return tuple(
            item.decode() if isinstance(item, bytes) else str(item)
            for item in raw_value
        )
    return ()


def _read_env_state_and_metadata(path: Path) -> tuple[np.ndarray | None, dict[str, Any]]:
    with h5py.File(path, "r") as h5_file:
        env_state = (
            h5_file[DS_ENV_STATE][()].astype(np.float32)
            if DS_ENV_STATE in h5_file
            else None
        )
        metadata: dict[str, Any] = {}
        if GRP_METADATA in h5_file:
            metadata.update(dict(h5_file[GRP_METADATA].attrs))
        metadata.update(dict(h5_file.attrs))
    return env_state, metadata


def _target_geometry_indices(
    *,
    env_state_order: tuple[str, ...],
    env_state_width: int,
) -> tuple[dict[str, int] | None, str]:
    if env_state_order:
        if not all(field in env_state_order for field in TARGET_GEOMETRY_FIELDS):
            return None, "metadata_env_state_order"
        return {
            field: int(env_state_order.index(field))
            for field in TARGET_GEOMETRY_FIELDS
        }, "metadata_env_state_order"

    max_index = max(TARGET_GEOMETRY_FIXED_INDICES.values())
    if env_state_width > max_index:
        return dict(TARGET_GEOMETRY_FIXED_INDICES), "fixed_indices"
    return None, "missing_env_state_order"


def _source_group(path: Path) -> str:
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    return resolved.parent.name


def audit_target_geometry_dataset(
    dataset_dir: str | Path,
    *,
    min_step_coverage: float = 0.999,
) -> dict[str, Any]:
    """Return a JSON-serializable target-geometry audit for a dataset."""
    dataset_dir = Path(dataset_dir)
    episode_paths = list_episodes(dataset_dir)
    if not episode_paths:
        raise FileNotFoundError(f"No episode_*.hdf5 files found under {dataset_dir}")

    field_valid_step_counts = {field: 0 for field in TARGET_GEOMETRY_FIELDS}
    total_steps = 0
    episodes_with_env_state = 0
    episodes_with_all_fields = 0
    episodes_with_full_step_coverage = 0
    legacy_only_episode_count = 0
    missing_env_state_episode_count = 0
    target_geometry_valid_steps = 0
    source_groups: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "episode_count": 0,
            "step_count": 0,
            "episodes_with_all_fields": 0,
            "legacy_only_episode_count": 0,
            "missing_env_state_episode_count": 0,
        }
    )
    episode_reports: list[dict[str, Any]] = []

    for path in episode_paths:
        env_state, metadata = _read_env_state_and_metadata(path)
        env_state_order = _metadata_env_state_order(metadata)
        group_name = _source_group(path)
        group = source_groups[group_name]
        group["episode_count"] += 1

        if env_state is None:
            missing_env_state_episode_count += 1
            group["missing_env_state_episode_count"] += 1
            episode_reports.append(
                {
                    "path": str(path),
                    "source_group": group_name,
                    "step_count": 0,
                    "env_state_width": 0,
                    "target_geometry_status": "missing_env_state",
                    "valid_step_coverage": 0.0,
                }
            )
            continue

        arr = np.asarray(env_state, dtype=np.float32)
        if arr.ndim != 2:
            arr = arr.reshape(arr.shape[0], -1)
        step_count = int(arr.shape[0])
        env_state_width = int(arr.shape[1]) if arr.ndim == 2 else 0
        total_steps += step_count
        group["step_count"] += step_count
        episodes_with_env_state += 1

        indices, index_source = _target_geometry_indices(
            env_state_order=env_state_order,
            env_state_width=env_state_width,
        )
        if indices is None:
            legacy_only_episode_count += 1
            group["legacy_only_episode_count"] += 1
            episode_reports.append(
                {
                    "path": str(path),
                    "source_group": group_name,
                    "step_count": step_count,
                    "env_state_width": env_state_width,
                    "target_geometry_status": "legacy_only",
                    "index_source": index_source,
                    "valid_step_coverage": 0.0,
                }
            )
            continue

        episodes_with_all_fields += 1
        group["episodes_with_all_fields"] += 1
        field_masks = []
        for field, index in indices.items():
            values = arr[:, index]
            valid_mask = np.isfinite(values)
            if field == "target_horizontal_distance_m":
                valid_mask = np.logical_and(valid_mask, values >= 0.0)
            field_valid_step_counts[field] += int(np.sum(valid_mask))
            field_masks.append(valid_mask)
        all_fields_valid = np.logical_and.reduce(field_masks)
        valid_steps = int(np.sum(all_fields_valid))
        target_geometry_valid_steps += valid_steps
        valid_coverage = float(valid_steps) / float(max(step_count, 1))
        if valid_coverage >= min_step_coverage:
            episodes_with_full_step_coverage += 1
        episode_reports.append(
            {
                "path": str(path),
                "source_group": group_name,
                "step_count": step_count,
                "env_state_width": env_state_width,
                "target_geometry_status": "available",
                "index_source": index_source,
                "valid_step_coverage": valid_coverage,
            }
        )

    total_steps_safe = max(total_steps, 1)
    geometry_step_coverage_rate = float(target_geometry_valid_steps) / float(total_steps_safe)
    all_episodes_geometry_ready = (
        episodes_with_all_fields == len(episode_paths)
        and missing_env_state_episode_count == 0
        and legacy_only_episode_count == 0
        and geometry_step_coverage_rate >= min_step_coverage
    )
    recommendation = (
        "ok_for_target_geometry_training"
        if all_episodes_geometry_ready
        else "collect_new_data_with_target_geometry_contract"
    )

    return {
        "dataset_dir": str(dataset_dir),
        "episode_count": int(len(episode_paths)),
        "step_count": int(total_steps),
        "required_fields": list(TARGET_GEOMETRY_FIELDS),
        "episodes_with_env_state": int(episodes_with_env_state),
        "episodes_with_all_target_geometry_fields": int(episodes_with_all_fields),
        "episodes_with_full_target_geometry_step_coverage": int(
            episodes_with_full_step_coverage
        ),
        "legacy_only_episode_count": int(legacy_only_episode_count),
        "missing_env_state_episode_count": int(missing_env_state_episode_count),
        "target_geometry_valid_step_count": int(target_geometry_valid_steps),
        "target_geometry_valid_step_rate": float(geometry_step_coverage_rate),
        "field_valid_step_rates": {
            field: float(count) / float(total_steps_safe)
            for field, count in field_valid_step_counts.items()
        },
        "usable_for_target_safety_training": bool(all_episodes_geometry_ready),
        "recommendation": recommendation,
        "old_data_decision": (
            "keep_for_non_target-geometry_use_only"
            if not all_episodes_geometry_ready
            else "ok"
        ),
        "source_groups": dict(sorted(source_groups.items())),
        "episodes": episode_reports,
    }
