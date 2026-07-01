"""Rollout-record projection for explicit target-shape residual diagnostics."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from testbed.data.schema import (
    ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
    ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX,
    ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
)
from testbed.eval.terrain_target_grid import build_rectangular_target_grid
from testbed.eval.terrain_target_metrics import build_target_residual_metrics


GRID_CELL_COUNT = 6
SOURCE = "rollout_jsonl_latest_compact_grid_explicit_target_projection"


def build_latest_target_residual_projection(
    rollout_records: list[dict[str, Any]],
    *,
    grid_shape: Sequence[Any],
    row_start: int,
    row_end: int,
    col_start: int,
    col_end: int,
    target_depth_m: float,
    profile: str = "explicit_t1_like_rectangular_shallow_pit",
) -> dict[str, Any]:
    """Project the latest rollout compact grid onto an explicit target spec."""

    target_spec_grid_shape = _grid_shape_from_sequence(grid_shape)
    snapshot = _latest_grid_snapshot(rollout_records)
    if snapshot is None:
        return _projection_result(
            status="missing_snapshot",
            snapshot_row_index=None,
            observed_grid_shape=None,
            target_spec_grid_shape=target_spec_grid_shape,
            removed_depth_grid_m=[],
            valid_mask=[],
            target_grid=None,
            target_residual_metrics=None,
        )

    target_grid = build_rectangular_target_grid(
        grid_shape=grid_shape,
        valid_mask=snapshot["valid_mask"],
        row_start=row_start,
        row_end=row_end,
        col_start=col_start,
        col_end=col_end,
        target_depth_m=target_depth_m,
        profile=profile,
    )
    if target_grid["status"] != "present":
        return _projection_result(
            status=str(target_grid["status"]),
            snapshot_row_index=int(snapshot["row_index"]),
            observed_grid_shape=_grid_shape(
                snapshot["long_count"],
                snapshot["short_count"],
            ),
            target_spec_grid_shape=target_spec_grid_shape,
            removed_depth_grid_m=snapshot["removed_depth_grid_m"],
            valid_mask=snapshot["valid_mask"],
            target_grid=target_grid,
            target_residual_metrics=None,
        )

    target_residual_metrics = build_target_residual_metrics(
        removed_depth_grid_m=snapshot["removed_depth_grid_m"],
        target_depth_grid_m=target_grid["target_depth_grid_m"],
        target_region_mask=target_grid["target_region_mask"],
        valid_mask=snapshot["valid_mask"],
    )
    return _projection_result(
        status=str(target_residual_metrics["status"]),
        snapshot_row_index=int(snapshot["row_index"]),
        observed_grid_shape=_grid_shape(
            snapshot["long_count"],
            snapshot["short_count"],
        ),
        target_spec_grid_shape=target_spec_grid_shape,
        removed_depth_grid_m=snapshot["removed_depth_grid_m"],
        valid_mask=snapshot["valid_mask"],
        target_grid=target_grid,
        target_residual_metrics=target_residual_metrics,
    )


def _latest_grid_snapshot(
    rollout_records: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for row_index in range(len(rollout_records) - 1, -1, -1):
        snapshot = _grid_snapshot_from_row(row_index, rollout_records[row_index])
        if snapshot is not None:
            return snapshot
    return None


def _grid_snapshot_from_row(row_index: int, row: dict[str, Any]) -> dict[str, Any] | None:
    env_state = row.get("env_state")
    if not isinstance(env_state, (list, tuple)):
        return None
    removed_depth = _float_slice(
        env_state,
        ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
        GRID_CELL_COUNT,
    )
    valid_mask = _float_slice(
        env_state,
        ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
        GRID_CELL_COUNT,
    )
    if removed_depth is None or valid_mask is None:
        return None
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
        "valid_mask": valid_mask,
    }


def _projection_result(
    *,
    status: str,
    snapshot_row_index: int | None,
    observed_grid_shape: list[int] | None,
    target_spec_grid_shape: list[int] | None,
    removed_depth_grid_m: list[float],
    valid_mask: list[float],
    target_grid: dict[str, Any] | None,
    target_residual_metrics: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "status": status,
        "source": SOURCE,
        "snapshot_row_index": snapshot_row_index,
        "observed_grid_shape": observed_grid_shape,
        "target_spec_grid_shape": target_spec_grid_shape,
        "removed_depth_grid_m": removed_depth_grid_m,
        "valid_mask": valid_mask,
        "target_grid": target_grid,
        "target_residual_metrics": target_residual_metrics,
        **_missing_provenance_fields(),
    }


def _grid_shape(long_count: float | None, short_count: float | None) -> list[int] | None:
    long_cells = _integer_count(long_count)
    short_cells = _integer_count(short_count)
    if long_cells is None or short_cells is None:
        return None
    if long_cells * short_cells != GRID_CELL_COUNT:
        return None
    return [long_cells, short_cells]


def _grid_shape_from_sequence(grid_shape: Sequence[Any]) -> list[int] | None:
    if len(grid_shape) != 2:
        return None
    long_cells = _integer_count(_coerce_float(grid_shape[0]))
    short_cells = _integer_count(_coerce_float(grid_shape[1]))
    if long_cells is None or short_cells is None:
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
    return _coerce_float(values[index])


def _coerce_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _missing_provenance_fields() -> dict[str, str]:
    return {
        "cell_size_status": "missing",
        "origin_status": "missing",
        "timestamp_status": "missing",
        "frame_transform_status": "missing",
        "height_grid_status": "missing",
        "elevation_grid_status": "missing",
        "confidence_grid_status": "missing",
    }


def _metric_float(value: float) -> float:
    rounded = round(float(value), 12)
    return 0.0 if rounded == -0.0 else rounded


__all__ = ["build_latest_target_residual_projection"]
