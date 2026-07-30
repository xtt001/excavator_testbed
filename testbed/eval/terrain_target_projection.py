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
CONVERGENCE_SOURCE = "rollout_jsonl_dig_segments_explicit_target_residual_convergence"
CONVERGENCE_CURVE_WINDOW = (
    "final usable compact-grid snapshot per contiguous rows where skill_name == 'dig'"
)
CONVERGENCE_SUMMARY_SOURCE = "target_residual_convergence_curve"


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
        grid_shape=grid_shape,
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


def build_target_residual_convergence_projection(
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
    """Project target-shape residuals over final snapshots of dig segments."""

    target_spec = _target_spec(
        grid_shape=grid_shape,
        row_start=row_start,
        row_end=row_end,
        col_start=col_start,
        col_end=col_end,
        target_depth_m=target_depth_m,
        profile=profile,
    )
    target_grid = build_rectangular_target_grid(
        grid_shape=grid_shape,
        valid_mask=_target_spec_valid_mask(grid_shape),
        row_start=row_start,
        row_end=row_end,
        col_start=col_start,
        col_end=col_end,
        target_depth_m=target_depth_m,
        profile=profile,
    )
    if target_grid["status"] != "present":
        return _convergence_projection_result(
            status=str(target_grid["status"]),
            target_spec=target_spec,
            target_grid=target_grid,
            curve=[],
            summary=_target_residual_convergence_summary([]),
        )

    curve = []
    failed_metric: dict[str, Any] | None = None
    for dig_segment_index, snapshot in _dig_segment_final_snapshots(rollout_records):
        metrics = build_target_residual_metrics(
            removed_depth_grid_m=snapshot["removed_depth_grid_m"],
            target_depth_grid_m=target_grid["target_depth_grid_m"],
            target_region_mask=target_grid["target_region_mask"],
            valid_mask=snapshot["valid_mask"],
            grid_shape=grid_shape,
        )
        if metrics["status"] != "present":
            failed_metric = metrics
            break
        curve.append(_convergence_curve_point(dig_segment_index, snapshot, metrics))

    if failed_metric is not None:
        return _convergence_projection_result(
            status=str(failed_metric["status"]),
            target_spec=target_spec,
            target_grid=target_grid,
            curve=[],
            summary=_target_residual_convergence_summary([]),
        )

    return _convergence_projection_result(
        status="present" if curve else "missing_curve",
        target_spec=target_spec,
        target_grid=target_grid,
        curve=curve,
        summary=_target_residual_convergence_summary(curve),
    )


def _latest_grid_snapshot(
    rollout_records: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for row_index in range(len(rollout_records) - 1, -1, -1):
        snapshot = _grid_snapshot_from_row(row_index, rollout_records[row_index])
        if snapshot is not None:
            return snapshot
    return None


def _dig_segment_final_snapshots(
    rollout_records: list[dict[str, Any]],
) -> list[tuple[int, dict[str, Any]]]:
    snapshots: list[tuple[int, dict[str, Any]]] = []
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

        if in_dig_segment and latest_segment_snapshot is not None:
            snapshots.append((dig_segment_index, latest_segment_snapshot))
        in_dig_segment = False
        latest_segment_snapshot = None

    if in_dig_segment and latest_segment_snapshot is not None:
        snapshots.append((dig_segment_index, latest_segment_snapshot))
    return snapshots


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


def _convergence_curve_point(
    dig_segment_index: int,
    snapshot: dict[str, Any],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "dig_segment_index": int(dig_segment_index),
        "snapshot_row_index": int(snapshot["row_index"]),
        "target_positive_residual_depth_sum_m": metrics[
            "target_positive_residual_depth_sum_m"
        ],
        "target_overdig_depth_sum_m": metrics["target_overdig_depth_sum_m"],
        "target_removed_completion_ratio": metrics[
            "target_removed_completion_ratio"
        ],
        "outside_target_removed_depth_sum_m": metrics[
            "outside_target_removed_depth_sum_m"
        ],
        "target_residual_metrics": metrics,
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


def _convergence_projection_result(
    *,
    status: str,
    target_spec: dict[str, Any],
    target_grid: dict[str, Any],
    curve: list[dict[str, Any]],
    summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": status,
        "source": CONVERGENCE_SOURCE,
        "curve_window": CONVERGENCE_CURVE_WINDOW,
        "target_spec": target_spec,
        "target_grid": target_grid,
        "curve": curve,
        "summary": summary,
        **_missing_provenance_fields(),
    }


def _target_residual_convergence_summary(
    curve: list[dict[str, Any]],
) -> dict[str, Any]:
    point_count = len(curve)
    if point_count == 0:
        return _empty_target_residual_convergence_summary("missing", point_count)

    start = curve[0]
    end = curve[-1]
    status = "present" if point_count >= 2 else "insufficient_points"
    positive_delta = _summary_delta(
        end,
        start,
        "target_positive_residual_depth_sum_m",
        enabled=point_count >= 2,
    )
    overdig_delta = _summary_delta(
        end,
        start,
        "target_overdig_depth_sum_m",
        enabled=point_count >= 2,
    )
    completion_delta = _summary_delta(
        end,
        start,
        "target_removed_completion_ratio",
        enabled=point_count >= 2,
    )
    outside_delta = _summary_delta(
        end,
        start,
        "outside_target_removed_depth_sum_m",
        enabled=point_count >= 2,
    )

    return {
        "status": status,
        "source": CONVERGENCE_SUMMARY_SOURCE,
        "point_count": int(point_count),
        "start_dig_segment_index": _summary_int(start, "dig_segment_index"),
        "end_dig_segment_index": _summary_int(end, "dig_segment_index"),
        "target_positive_residual_depth_sum_start_m": _summary_float(
            start,
            "target_positive_residual_depth_sum_m",
        ),
        "target_positive_residual_depth_sum_end_m": _summary_float(
            end,
            "target_positive_residual_depth_sum_m",
        ),
        "target_positive_residual_depth_sum_delta_m": positive_delta,
        "target_overdig_depth_sum_start_m": _summary_float(
            start,
            "target_overdig_depth_sum_m",
        ),
        "target_overdig_depth_sum_end_m": _summary_float(
            end,
            "target_overdig_depth_sum_m",
        ),
        "target_overdig_depth_sum_delta_m": overdig_delta,
        "target_removed_completion_ratio_start": _summary_float(
            start,
            "target_removed_completion_ratio",
        ),
        "target_removed_completion_ratio_end": _summary_float(
            end,
            "target_removed_completion_ratio",
        ),
        "target_removed_completion_ratio_delta": completion_delta,
        "outside_target_removed_depth_sum_start_m": _summary_float(
            start,
            "outside_target_removed_depth_sum_m",
        ),
        "outside_target_removed_depth_sum_end_m": _summary_float(
            end,
            "outside_target_removed_depth_sum_m",
        ),
        "outside_target_removed_depth_sum_delta_m": outside_delta,
        "diagnostic_trend": _target_convergence_trend(
            status,
            positive_delta,
            outside_delta,
        ),
    }


def _empty_target_residual_convergence_summary(
    status: str,
    point_count: int,
) -> dict[str, Any]:
    return {
        "status": status,
        "source": CONVERGENCE_SUMMARY_SOURCE,
        "point_count": int(point_count),
        "start_dig_segment_index": None,
        "end_dig_segment_index": None,
        "target_positive_residual_depth_sum_start_m": None,
        "target_positive_residual_depth_sum_end_m": None,
        "target_positive_residual_depth_sum_delta_m": None,
        "target_overdig_depth_sum_start_m": None,
        "target_overdig_depth_sum_end_m": None,
        "target_overdig_depth_sum_delta_m": None,
        "target_removed_completion_ratio_start": None,
        "target_removed_completion_ratio_end": None,
        "target_removed_completion_ratio_delta": None,
        "outside_target_removed_depth_sum_start_m": None,
        "outside_target_removed_depth_sum_end_m": None,
        "outside_target_removed_depth_sum_delta_m": None,
        "diagnostic_trend": status,
    }


def _summary_delta(
    end: dict[str, Any],
    start: dict[str, Any],
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


def _summary_float(point: dict[str, Any], field: str) -> float | None:
    value = point.get(field)
    if value is None:
        return None
    return float(value)


def _summary_int(point: dict[str, Any], field: str) -> int | None:
    value = point.get(field)
    if value is None:
        return None
    return int(value)


def _target_convergence_trend(
    status: str,
    positive_delta: float | None,
    outside_delta: float | None,
) -> str:
    if status != "present":
        return status
    if positive_delta is None or positive_delta >= 0.0:
        return "target_positive_residual_not_reduced"
    if outside_delta is not None and outside_delta > 0.0:
        return "target_positive_residual_reduced_outside_removed_increased"
    return "target_positive_residual_reduced_outside_removed_not_increased"


def _grid_shape(long_count: float | None, short_count: float | None) -> list[int] | None:
    long_cells = _integer_count(long_count)
    short_cells = _integer_count(short_count)
    if long_cells is None or short_cells is None:
        return None
    if long_cells * short_cells != GRID_CELL_COUNT:
        return None
    return [long_cells, short_cells]


def _target_spec(
    *,
    grid_shape: Sequence[Any],
    row_start: int,
    row_end: int,
    col_start: int,
    col_end: int,
    target_depth_m: float,
    profile: str,
) -> dict[str, Any]:
    return {
        "grid_shape": _grid_shape_from_sequence(grid_shape),
        "row_start": int(row_start),
        "row_end": int(row_end),
        "col_start": int(col_start),
        "col_end": int(col_end),
        "target_depth_m": _metric_float(float(target_depth_m)),
        "profile": str(profile),
    }


def _target_spec_valid_mask(grid_shape: Sequence[Any]) -> list[float]:
    parsed_shape = _grid_shape_from_sequence(grid_shape)
    if parsed_shape is None:
        return []
    return [1.0] * int(parsed_shape[0] * parsed_shape[1])


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


__all__ = [
    "build_latest_target_residual_projection",
    "build_target_residual_convergence_projection",
]
