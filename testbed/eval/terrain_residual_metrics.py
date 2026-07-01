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
CONVERGENCE_CURVE_SOURCE = (
    "rollout_jsonl_contiguous_dig_segments_final_usable_env_state_compact_dig_area_grid"
)
CONVERGENCE_CURVE_WINDOW = (
    "final usable compact-grid snapshot per contiguous rows where skill_name == 'dig'"
)
CONVERGENCE_SUMMARY_SOURCE = "residual_convergence_curve"


def build_terrain_residual_summary(
    rollout_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize the latest compact dig-area residual snapshot in rollout jsonl."""

    snapshot = _latest_grid_snapshot(rollout_records)
    if snapshot is None:
        return _missing_summary()

    metrics = _snapshot_metrics(snapshot)
    convergence_curve = _dig_segment_residual_convergence_curve(rollout_records)

    return {
        "status": "present",
        "source": SOURCE,
        "snapshot_row_index": int(snapshot["row_index"]),
        "grid_shape": _grid_shape(
            snapshot["long_count"],
            snapshot["short_count"],
        ),
        "cell_count": GRID_CELL_COUNT,
        "valid_cell_count": metrics["valid_cell_count"],
        "removed_depth_grid_m": metrics["removed_depth_grid_m"],
        "target_depth_grid_m": metrics["target_depth_grid_m"],
        "residual_depth_grid_m": metrics["residual_depth_grid_m"],
        "positive_residual_depth_sum_m": metrics["positive_residual_depth_sum_m"],
        "overdig_depth_sum_m": metrics["overdig_depth_sum_m"],
        "target_depth_sum_m": metrics["target_depth_sum_m"],
        "removed_depth_sum_m": metrics["removed_depth_sum_m"],
        "target_removed_completion_ratio": metrics["target_removed_completion_ratio"],
        "residual_convergence_curve_status": (
            "present" if convergence_curve else "missing"
        ),
        "residual_convergence_curve_source": CONVERGENCE_CURVE_SOURCE,
        "residual_convergence_curve_window": CONVERGENCE_CURVE_WINDOW,
        "residual_convergence_curve": convergence_curve,
        "residual_convergence_summary": _residual_convergence_summary(
            convergence_curve
        ),
        **_missing_provenance_fields(),
        "env_state_indices": _env_state_index_provenance(),
    }


def _latest_grid_snapshot(
    rollout_records: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for row_index in range(len(rollout_records) - 1, -1, -1):
        snapshot = _grid_snapshot_from_row(row_index, rollout_records[row_index])
        if snapshot is not None:
            return snapshot
    return None


def _dig_segment_residual_convergence_curve(
    rollout_records: list[dict[str, Any]],
) -> list[dict[str, int | float | None]]:
    points: list[dict[str, int | float | None]] = []
    in_dig_segment = False
    dig_segment_index = 0
    latest_segment_snapshot: dict[str, Any] | None = None

    for row_index, row in enumerate(rollout_records):
        if str(row.get("skill_name", "")) == "dig":
            if not in_dig_segment:
                in_dig_segment = True
                dig_segment_index += 1
                latest_segment_snapshot = None
            snapshot = _grid_snapshot_from_row(row_index, row)
            if snapshot is not None:
                latest_segment_snapshot = snapshot
            continue

        if in_dig_segment:
            point = _curve_point(dig_segment_index, latest_segment_snapshot)
            if point is not None:
                points.append(point)
        in_dig_segment = False
        latest_segment_snapshot = None

    if in_dig_segment:
        point = _curve_point(dig_segment_index, latest_segment_snapshot)
        if point is not None:
            points.append(point)
    return points


def _grid_snapshot_from_row(row_index: int, row: dict[str, Any]) -> dict[str, Any] | None:
    env_state = row.get("env_state")
    if not isinstance(env_state, (list, tuple)):
        return None
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
        "target_depth_grid_m": target_depth,
        "valid_mask": valid_mask,
    }


def _curve_point(
    dig_segment_index: int,
    snapshot: dict[str, Any] | None,
) -> dict[str, int | float | None] | None:
    if snapshot is None:
        return None
    metrics = _snapshot_metrics(snapshot)
    return {
        "dig_segment_index": int(dig_segment_index),
        "snapshot_row_index": int(snapshot["row_index"]),
        "positive_residual_depth_sum_m": metrics["positive_residual_depth_sum_m"],
        "overdig_depth_sum_m": metrics["overdig_depth_sum_m"],
        "target_depth_sum_m": metrics["target_depth_sum_m"],
        "removed_depth_sum_m": metrics["removed_depth_sum_m"],
        "target_removed_completion_ratio": metrics["target_removed_completion_ratio"],
        "valid_cell_count": metrics["valid_cell_count"],
    }


def _residual_convergence_summary(
    convergence_curve: list[dict[str, int | float | None]],
) -> dict[str, int | float | str | None]:
    point_count = len(convergence_curve)
    if point_count == 0:
        return _empty_residual_convergence_summary("missing", point_count)

    start = convergence_curve[0]
    end = convergence_curve[-1]
    status = "present" if point_count >= 2 else "insufficient_points"
    positive_delta = _summary_delta(
        end,
        start,
        "positive_residual_depth_sum_m",
        enabled=point_count >= 2,
    )
    overdig_delta = _summary_delta(
        end,
        start,
        "overdig_depth_sum_m",
        enabled=point_count >= 2,
    )
    completion_delta = _summary_delta(
        end,
        start,
        "target_removed_completion_ratio",
        enabled=point_count >= 2,
    )

    return {
        "status": status,
        "source": CONVERGENCE_SUMMARY_SOURCE,
        "point_count": int(point_count),
        "start_dig_segment_index": _summary_int(start, "dig_segment_index"),
        "end_dig_segment_index": _summary_int(end, "dig_segment_index"),
        "positive_residual_depth_sum_start_m": _summary_float(
            start,
            "positive_residual_depth_sum_m",
        ),
        "positive_residual_depth_sum_end_m": _summary_float(
            end,
            "positive_residual_depth_sum_m",
        ),
        "positive_residual_depth_sum_delta_m": positive_delta,
        "overdig_depth_sum_start_m": _summary_float(start, "overdig_depth_sum_m"),
        "overdig_depth_sum_end_m": _summary_float(end, "overdig_depth_sum_m"),
        "overdig_depth_sum_delta_m": overdig_delta,
        "target_removed_completion_ratio_start": _summary_float(
            start,
            "target_removed_completion_ratio",
        ),
        "target_removed_completion_ratio_end": _summary_float(
            end,
            "target_removed_completion_ratio",
        ),
        "target_removed_completion_ratio_delta": completion_delta,
        "diagnostic_trend": _diagnostic_convergence_trend(
            status,
            positive_delta,
            overdig_delta,
        ),
    }


def _empty_residual_convergence_summary(
    status: str,
    point_count: int,
) -> dict[str, int | str | None]:
    return {
        "status": status,
        "source": CONVERGENCE_SUMMARY_SOURCE,
        "point_count": int(point_count),
        "start_dig_segment_index": None,
        "end_dig_segment_index": None,
        "positive_residual_depth_sum_start_m": None,
        "positive_residual_depth_sum_end_m": None,
        "positive_residual_depth_sum_delta_m": None,
        "overdig_depth_sum_start_m": None,
        "overdig_depth_sum_end_m": None,
        "overdig_depth_sum_delta_m": None,
        "target_removed_completion_ratio_start": None,
        "target_removed_completion_ratio_end": None,
        "target_removed_completion_ratio_delta": None,
        "diagnostic_trend": status,
    }


def _summary_delta(
    end: dict[str, int | float | None],
    start: dict[str, int | float | None],
    field: str,
    *,
    enabled: bool,
) -> float | None:
    if not enabled:
        return None
    start_value = _summary_float(start, field)
    end_value = _summary_float(end, field)
    if start_value is None or end_value is None:
        return None
    return _metric_float(end_value - start_value)


def _summary_float(
    point: dict[str, int | float | None],
    field: str,
) -> float | None:
    value = point.get(field)
    if value is None:
        return None
    return float(value)


def _summary_int(point: dict[str, int | float | None], field: str) -> int | None:
    value = point.get(field)
    if value is None:
        return None
    return int(value)


def _diagnostic_convergence_trend(
    status: str,
    positive_delta: float | None,
    overdig_delta: float | None,
) -> str:
    if status != "present":
        return status
    if positive_delta is None or positive_delta >= 0.0:
        return "positive_residual_not_reduced"
    if overdig_delta is not None and overdig_delta > 0.0:
        return "positive_residual_reduced_overdig_increased"
    return "positive_residual_reduced_overdig_not_increased"


def _snapshot_metrics(snapshot: dict[str, Any]) -> dict[str, Any]:
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
        "valid_cell_count": int(len(valid_indices)),
        "removed_depth_grid_m": removed_depth,
        "target_depth_grid_m": target_depth,
        "residual_depth_grid_m": residual_depth,
        "positive_residual_depth_sum_m": positive_residual_sum,
        "overdig_depth_sum_m": overdig_sum,
        "target_depth_sum_m": target_sum,
        "removed_depth_sum_m": removed_sum,
        "target_removed_completion_ratio": completion_ratio,
    }


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
        "residual_convergence_curve_status": "missing",
        "residual_convergence_curve_source": CONVERGENCE_CURVE_SOURCE,
        "residual_convergence_curve_window": CONVERGENCE_CURVE_WINDOW,
        "residual_convergence_curve": [],
        "residual_convergence_summary": _residual_convergence_summary([]),
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
