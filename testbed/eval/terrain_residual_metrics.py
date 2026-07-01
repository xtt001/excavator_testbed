"""Diagnostic terrain residual metrics for offline rollout review."""

from __future__ import annotations

import math
from typing import Any

from testbed.data.schema import (
    ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
    ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX,
    ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
    ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX,
)


GRID_CELL_COUNT = 6
SOURCE = "rollout_jsonl_env_state_compact_dig_area_grid"


def build_terrain_residual_summary(
    rollout_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize the latest compact dig-area residual snapshot in rollout jsonl."""

    snapshot = _latest_grid_snapshot(rollout_records)
    if snapshot is None:
        return _missing_summary()

    removed_depth = snapshot["removed_depth_grid_m"]
    target_depth = snapshot["target_depth_grid_m"]
    valid_mask = snapshot["valid_mask"]
    valid_indices = [
        index for index, value in enumerate(valid_mask) if _valid_mask_value(value)
    ]
    residual_depth = [
        _metric_float(target - removed)
        for target, removed in zip(target_depth, removed_depth, strict=True)
    ]
    positive_residual_sum = _metric_sum(
        max(residual_depth[index], 0.0) for index in valid_indices
    )
    overdig_sum = _metric_sum(
        max(-residual_depth[index], 0.0) for index in valid_indices
    )
    target_sum = _metric_sum(target_depth[index] for index in valid_indices)
    removed_sum = _metric_sum(removed_depth[index] for index in valid_indices)
    completion_sum = _metric_sum(
        min(removed_depth[index], target_depth[index]) for index in valid_indices
    )
    completion_ratio = float(completion_sum / target_sum) if target_sum > 0.0 else None

    return {
        "status": "present",
        "source": SOURCE,
        "snapshot_row_index": int(snapshot["row_index"]),
        "grid_shape": _grid_shape(
            snapshot["long_count"],
            snapshot["short_count"],
        ),
        "cell_count": GRID_CELL_COUNT,
        "valid_cell_count": int(len(valid_indices)),
        "removed_depth_grid_m": removed_depth,
        "target_depth_grid_m": target_depth,
        "residual_depth_grid_m": residual_depth,
        "positive_residual_depth_sum_m": positive_residual_sum,
        "overdig_depth_sum_m": overdig_sum,
        "target_depth_sum_m": target_sum,
        "removed_depth_sum_m": removed_sum,
        "target_removed_completion_ratio": completion_ratio,
        **_missing_provenance_fields(),
        "env_state_indices": _env_state_index_provenance(),
    }


def _latest_grid_snapshot(
    rollout_records: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for row_index in range(len(rollout_records) - 1, -1, -1):
        row = rollout_records[row_index]
        env_state = row.get("env_state")
        if not isinstance(env_state, (list, tuple)):
            continue
        removed_depth = _float_slice(
            env_state,
            ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
            GRID_CELL_COUNT,
        )
        target_depth = _float_slice(
            env_state,
            ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX,
            GRID_CELL_COUNT,
        )
        valid_mask = _float_slice(
            env_state,
            ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
            GRID_CELL_COUNT,
        )
        if removed_depth is None or target_depth is None or valid_mask is None:
            continue
        return {
            "row_index": int(row_index),
            "long_count": _sequence_float(
                env_state,
                ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX,
            ),
            "short_count": _sequence_float(
                env_state,
                ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX,
            ),
            "removed_depth_grid_m": removed_depth,
            "target_depth_grid_m": target_depth,
            "valid_mask": valid_mask,
        }
    return None


def _missing_summary() -> dict[str, Any]:
    return {
        "status": "missing",
        "source": SOURCE,
        "snapshot_row_index": None,
        "grid_shape": None,
        "cell_count": 0,
        "valid_cell_count": 0,
        "removed_depth_grid_m": [],
        "target_depth_grid_m": [],
        "residual_depth_grid_m": [],
        "positive_residual_depth_sum_m": None,
        "overdig_depth_sum_m": None,
        "target_depth_sum_m": None,
        "removed_depth_sum_m": None,
        "target_removed_completion_ratio": None,
        **_missing_provenance_fields(),
        "env_state_indices": _env_state_index_provenance(),
    }


def _missing_provenance_fields() -> dict[str, str]:
    return {
        "confidence_grid_status": "missing",
        "height_grid_status": "missing",
        "elevation_grid_status": "missing",
        "cell_size_status": "missing",
        "origin_status": "missing",
        "timestamp_status": "missing",
        "frame_transform_status": "missing",
    }


def _env_state_index_provenance() -> dict[str, int | list[int]]:
    return {
        "long_count": int(ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX),
        "short_count": int(ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX),
        "removed_depth_grid": [
            int(ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX),
            int(ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX + GRID_CELL_COUNT),
        ],
        "target_depth_grid": [
            int(ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX),
            int(ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX + GRID_CELL_COUNT),
        ],
        "valid_mask": [
            int(ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX),
            int(ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX + GRID_CELL_COUNT),
        ],
    }


def _grid_shape(long_count: float | None, short_count: float | None) -> list[int] | None:
    long_cells = _integer_count(long_count)
    short_cells = _integer_count(short_count)
    if long_cells is None or short_cells is None:
        return None
    if long_cells * short_cells != GRID_CELL_COUNT:
        return None
    return [long_cells, short_cells]


def _integer_count(value: float | None) -> int | None:
    if value is None:
        return None
    rounded = round(value)
    if rounded <= 0 or not math.isclose(value, float(rounded), rel_tol=0.0, abs_tol=1e-6):
        return None
    return int(rounded)


def _float_slice(
    values: list[Any] | tuple[Any, ...],
    start: int,
    count: int,
) -> list[float] | None:
    end = start + count
    if len(values) < end:
        return None
    parsed = [_sequence_float(values, index) for index in range(start, end)]
    if any(value is None for value in parsed):
        return None
    return [_metric_float(float(value)) for value in parsed if value is not None]


def _sequence_float(values: list[Any] | tuple[Any, ...], index: int) -> float | None:
    if len(values) <= index:
        return None
    value = values[index]
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _valid_mask_value(value: float) -> bool:
    return value > 0.5


def _metric_sum(values: Any) -> float:
    return _metric_float(math.fsum(values))


def _metric_float(value: float) -> float:
    rounded = round(float(value), 12)
    return 0.0 if rounded == -0.0 else rounded


__all__ = [
    "build_terrain_residual_summary",
]
