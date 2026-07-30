"""Explicit target-shape residual baseline report composition for eval diagnostics."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from testbed.eval.terrain_target_projection import (
    build_latest_target_residual_projection,
    build_target_residual_convergence_projection,
)

SOURCE = "explicit_target_residual_baseline_report"
SCHEMA = "explicit_target_residual_baseline_report_v1"
DEFAULT_PROFILE = "explicit_t1_like_rectangular_shallow_pit"
_PROVENANCE_STATUS_FIELDS = (
    "cell_size_status",
    "origin_status",
    "timestamp_status",
    "frame_transform_status",
    "height_grid_status",
    "elevation_grid_status",
    "confidence_grid_status",
)


def build_explicit_target_residual_baseline_report(
    rollout_records: list[dict[str, Any]],
    *,
    grid_shape: Sequence[Any],
    row_start: int,
    row_end: int,
    col_start: int,
    col_end: int,
    target_depth_m: float,
    profile: str = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Compose latest and convergence target-shape diagnostics for one target spec."""

    latest_projection = build_latest_target_residual_projection(
        rollout_records,
        grid_shape=grid_shape,
        row_start=row_start,
        row_end=row_end,
        col_start=col_start,
        col_end=col_end,
        target_depth_m=target_depth_m,
        profile=profile,
    )
    convergence_projection = build_target_residual_convergence_projection(
        rollout_records,
        grid_shape=grid_shape,
        row_start=row_start,
        row_end=row_end,
        col_start=col_start,
        col_end=col_end,
        target_depth_m=target_depth_m,
        profile=profile,
    )
    return {
        "status": _report_status(latest_projection, convergence_projection),
        "source": SOURCE,
        "schema": SCHEMA,
        "target_spec": _target_spec(
            grid_shape=grid_shape,
            row_start=row_start,
            row_end=row_end,
            col_start=col_start,
            col_end=col_end,
            target_depth_m=target_depth_m,
            profile=profile,
        ),
        "latest_projection": latest_projection,
        "convergence_projection": convergence_projection,
        "diagnostic_summary": _diagnostic_summary(
            latest_projection,
            convergence_projection,
        ),
        **_provenance_statuses(latest_projection, convergence_projection),
    }


def _report_status(
    latest_projection: dict[str, Any],
    convergence_projection: dict[str, Any],
) -> str:
    latest_status = str(latest_projection.get("status"))
    convergence_status = str(convergence_projection.get("status"))
    if latest_status == "present" and convergence_status == "present":
        return "present"
    if latest_status == convergence_status:
        return latest_status
    return "partial"


def _diagnostic_summary(
    latest_projection: dict[str, Any],
    convergence_projection: dict[str, Any],
) -> dict[str, Any]:
    latest_metrics = latest_projection.get("target_residual_metrics") or {}
    convergence_summary = convergence_projection.get("summary") or {}
    return {
        "latest_projection_status": latest_projection.get("status"),
        "convergence_projection_status": convergence_projection.get("status"),
        "latest_snapshot_row_index": latest_projection.get("snapshot_row_index"),
        "latest_target_positive_residual_depth_sum_m": latest_metrics.get(
            "target_positive_residual_depth_sum_m"
        ),
        "latest_target_overdig_depth_sum_m": latest_metrics.get(
            "target_overdig_depth_sum_m"
        ),
        "latest_target_removed_completion_ratio": latest_metrics.get(
            "target_removed_completion_ratio"
        ),
        "latest_outside_target_removed_depth_sum_m": latest_metrics.get(
            "outside_target_removed_depth_sum_m"
        ),
        "convergence_summary_status": convergence_summary.get("status"),
        "convergence_point_count": convergence_summary.get("point_count"),
        "convergence_diagnostic_trend": convergence_summary.get(
            "diagnostic_trend"
        ),
        "convergence_start_dig_segment_index": convergence_summary.get(
            "start_dig_segment_index"
        ),
        "convergence_end_dig_segment_index": convergence_summary.get(
            "end_dig_segment_index"
        ),
        "convergence_target_positive_residual_depth_sum_start_m": convergence_summary.get(
            "target_positive_residual_depth_sum_start_m"
        ),
        "convergence_target_positive_residual_depth_sum_end_m": convergence_summary.get(
            "target_positive_residual_depth_sum_end_m"
        ),
        "convergence_target_positive_residual_depth_sum_delta_m": convergence_summary.get(
            "target_positive_residual_depth_sum_delta_m"
        ),
        "convergence_target_overdig_depth_sum_start_m": convergence_summary.get(
            "target_overdig_depth_sum_start_m"
        ),
        "convergence_target_overdig_depth_sum_end_m": convergence_summary.get(
            "target_overdig_depth_sum_end_m"
        ),
        "convergence_target_overdig_depth_sum_delta_m": convergence_summary.get(
            "target_overdig_depth_sum_delta_m"
        ),
        "convergence_target_removed_completion_ratio_start": convergence_summary.get(
            "target_removed_completion_ratio_start"
        ),
        "convergence_target_removed_completion_ratio_end": convergence_summary.get(
            "target_removed_completion_ratio_end"
        ),
        "convergence_target_removed_completion_ratio_delta": convergence_summary.get(
            "target_removed_completion_ratio_delta"
        ),
        "convergence_outside_target_removed_depth_sum_start_m": convergence_summary.get(
            "outside_target_removed_depth_sum_start_m"
        ),
        "convergence_outside_target_removed_depth_sum_end_m": convergence_summary.get(
            "outside_target_removed_depth_sum_end_m"
        ),
        "convergence_outside_target_removed_depth_sum_delta_m": convergence_summary.get(
            "outside_target_removed_depth_sum_delta_m"
        ),
    }


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


def _grid_shape_from_sequence(grid_shape: Sequence[Any]) -> list[int] | None:
    if len(grid_shape) != 2:
        return None
    row_count = _integer_count(_coerce_float(grid_shape[0]))
    col_count = _integer_count(_coerce_float(grid_shape[1]))
    if row_count is None or col_count is None:
        return None
    return [row_count, col_count]


def _integer_count(value: float | None) -> int | None:
    if value is None:
        return None
    rounded = round(value)
    if rounded <= 0 or not math.isclose(value, float(rounded), rel_tol=0.0, abs_tol=1e-6):
        return None
    return int(rounded)


def _coerce_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _provenance_statuses(
    latest_projection: dict[str, Any],
    convergence_projection: dict[str, Any],
) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for field in _PROVENANCE_STATUS_FIELDS:
        statuses[field] = str(
            latest_projection.get(field)
            or convergence_projection.get(field)
            or "missing"
        )
    return statuses


def _metric_float(value: float) -> float:
    rounded = round(float(value), 12)
    return 0.0 if rounded == -0.0 else rounded


__all__ = ["build_explicit_target_residual_baseline_report"]
