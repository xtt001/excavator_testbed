"""Explicit target-shape residual metrics for eval diagnostics."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any


SOURCE = "explicit_target_grid_removed_depth_comparison"
DEFAULT_PROFILE = "explicit_target_shape_residual_metrics"


def build_target_residual_metrics(
    *,
    removed_depth_grid_m: Sequence[Any],
    target_depth_grid_m: Sequence[Any],
    target_region_mask: Sequence[Any],
    valid_mask: Sequence[Any],
    profile: str = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Compare observed removed depth against an explicit target-depth grid."""

    lengths = {
        len(removed_depth_grid_m),
        len(target_depth_grid_m),
        len(target_region_mask),
        len(valid_mask),
    }
    if len(lengths) != 1 or not lengths or next(iter(lengths)) == 0:
        return _target_metrics_result(
            status="invalid_grid_lengths",
            profile=profile,
            cell_count=0,
            valid_cell_count=0,
            target_cell_count=0,
            outside_target_cell_count=0,
            target_positive_residual_depth_sum_m=None,
            target_overdig_depth_sum_m=None,
            target_depth_sum_m=None,
            target_removed_depth_sum_m=None,
            target_removed_completion_ratio=None,
            outside_target_removed_depth_sum_m=None,
            target_residual_depth_rmse_m=None,
            target_residual_depth_mae_m=None,
            target_residual_depth_abs_max_m=None,
            residual_depth_grid_m=[],
            invalid_target_cell_count=0,
            validation_errors=[
                "removed_depth_grid_m, target_depth_grid_m, target_region_mask, and valid_mask must have matching non-empty lengths",
            ],
        )

    cell_count = next(iter(lengths))
    removed_depth = _parse_nonnegative_depths(removed_depth_grid_m)
    target_depth = _parse_nonnegative_depths(target_depth_grid_m)
    if removed_depth is None or target_depth is None:
        return _target_metrics_result(
            status="invalid_depth_values",
            profile=profile,
            cell_count=cell_count,
            valid_cell_count=0,
            target_cell_count=0,
            outside_target_cell_count=0,
            target_positive_residual_depth_sum_m=None,
            target_overdig_depth_sum_m=None,
            target_depth_sum_m=None,
            target_removed_depth_sum_m=None,
            target_removed_completion_ratio=None,
            outside_target_removed_depth_sum_m=None,
            target_residual_depth_rmse_m=None,
            target_residual_depth_mae_m=None,
            target_residual_depth_abs_max_m=None,
            residual_depth_grid_m=[],
            invalid_target_cell_count=0,
            validation_errors=[
                "removed_depth_grid_m and target_depth_grid_m values must be finite and nonnegative",
            ],
        )

    target_mask = _parse_mask(target_region_mask)
    valid_cells = _parse_mask(valid_mask)
    if target_mask is None or valid_cells is None:
        return _target_metrics_result(
            status="invalid_mask_values",
            profile=profile,
            cell_count=cell_count,
            valid_cell_count=0,
            target_cell_count=0,
            outside_target_cell_count=0,
            target_positive_residual_depth_sum_m=None,
            target_overdig_depth_sum_m=None,
            target_depth_sum_m=None,
            target_removed_depth_sum_m=None,
            target_removed_completion_ratio=None,
            outside_target_removed_depth_sum_m=None,
            target_residual_depth_rmse_m=None,
            target_residual_depth_mae_m=None,
            target_residual_depth_abs_max_m=None,
            residual_depth_grid_m=[],
            invalid_target_cell_count=0,
            validation_errors=[
                "target_region_mask and valid_mask values must be finite numbers",
            ],
        )

    valid_cell_count = sum(1 for is_valid in valid_cells if is_valid)
    invalid_target_cell_count = sum(
        1
        for is_target, is_valid in zip(target_mask, valid_cells, strict=True)
        if is_target and not is_valid
    )
    if invalid_target_cell_count:
        return _target_metrics_result(
            status="invalid_target_region_mask",
            profile=profile,
            cell_count=cell_count,
            valid_cell_count=valid_cell_count,
            target_cell_count=0,
            outside_target_cell_count=0,
            target_positive_residual_depth_sum_m=None,
            target_overdig_depth_sum_m=None,
            target_depth_sum_m=None,
            target_removed_depth_sum_m=None,
            target_removed_completion_ratio=None,
            outside_target_removed_depth_sum_m=None,
            target_residual_depth_rmse_m=None,
            target_residual_depth_mae_m=None,
            target_residual_depth_abs_max_m=None,
            residual_depth_grid_m=[],
            invalid_target_cell_count=invalid_target_cell_count,
            validation_errors=[
                "target_region_mask selects cells that are not valid",
            ],
        )

    residual_depth = [
        _metric_float(target - removed)
        for target, removed in zip(target_depth, removed_depth, strict=True)
    ]
    target_indices = [
        index
        for index, (is_target, is_valid) in enumerate(
            zip(target_mask, valid_cells, strict=True)
        )
        if is_target and is_valid
    ]
    outside_target_indices = [
        index
        for index, (is_target, is_valid) in enumerate(
            zip(target_mask, valid_cells, strict=True)
        )
        if not is_target and is_valid
    ]
    target_error_metrics = _target_depth_error_metrics(
        residual_depth,
        target_indices,
    )
    target_depth_sum = _metric_sum(target_depth[index] for index in target_indices)
    target_removed_sum = _metric_sum(
        removed_depth[index] for index in target_indices
    )
    target_completion_sum = _metric_sum(
        min(removed_depth[index], target_depth[index]) for index in target_indices
    )

    return _target_metrics_result(
        status="present",
        profile=profile,
        cell_count=cell_count,
        valid_cell_count=valid_cell_count,
        target_cell_count=len(target_indices),
        outside_target_cell_count=len(outside_target_indices),
        target_positive_residual_depth_sum_m=_metric_sum(
            max(residual_depth[index], 0.0) for index in target_indices
        ),
        target_overdig_depth_sum_m=_metric_sum(
            max(-residual_depth[index], 0.0) for index in target_indices
        ),
        target_depth_sum_m=target_depth_sum,
        target_removed_depth_sum_m=target_removed_sum,
        target_removed_completion_ratio=(
            float(target_completion_sum / target_depth_sum)
            if target_depth_sum > 0.0
            else None
        ),
        outside_target_removed_depth_sum_m=_metric_sum(
            removed_depth[index] for index in outside_target_indices
        ),
        target_residual_depth_rmse_m=target_error_metrics["rmse"],
        target_residual_depth_mae_m=target_error_metrics["mae"],
        target_residual_depth_abs_max_m=target_error_metrics["abs_max"],
        residual_depth_grid_m=residual_depth,
        invalid_target_cell_count=0,
        validation_errors=[],
    )


def _target_metrics_result(
    *,
    status: str,
    profile: str,
    cell_count: int,
    valid_cell_count: int,
    target_cell_count: int,
    outside_target_cell_count: int,
    target_positive_residual_depth_sum_m: float | None,
    target_overdig_depth_sum_m: float | None,
    target_depth_sum_m: float | None,
    target_removed_depth_sum_m: float | None,
    target_removed_completion_ratio: float | None,
    outside_target_removed_depth_sum_m: float | None,
    target_residual_depth_rmse_m: float | None,
    target_residual_depth_mae_m: float | None,
    target_residual_depth_abs_max_m: float | None,
    residual_depth_grid_m: list[float],
    invalid_target_cell_count: int,
    validation_errors: list[str],
) -> dict[str, Any]:
    return {
        "status": status,
        "source": SOURCE,
        "profile": str(profile),
        "cell_count": int(cell_count),
        "valid_cell_count": int(valid_cell_count),
        "target_cell_count": int(target_cell_count),
        "outside_target_cell_count": int(outside_target_cell_count),
        "target_positive_residual_depth_sum_m": target_positive_residual_depth_sum_m,
        "target_overdig_depth_sum_m": target_overdig_depth_sum_m,
        "target_depth_sum_m": target_depth_sum_m,
        "target_removed_depth_sum_m": target_removed_depth_sum_m,
        "target_removed_completion_ratio": target_removed_completion_ratio,
        "outside_target_removed_depth_sum_m": outside_target_removed_depth_sum_m,
        "target_residual_depth_rmse_m": target_residual_depth_rmse_m,
        "target_residual_depth_mae_m": target_residual_depth_mae_m,
        "target_residual_depth_abs_max_m": target_residual_depth_abs_max_m,
        "residual_depth_grid_m": residual_depth_grid_m,
        "invalid_target_cell_count": int(invalid_target_cell_count),
        "validation_errors": validation_errors,
        **_missing_provenance_fields(),
    }


def _parse_nonnegative_depths(values: Sequence[Any]) -> list[float] | None:
    parsed_values: list[float] = []
    for value in values:
        parsed = _parse_finite_float(value)
        if parsed is None or parsed < 0.0:
            return None
        parsed_values.append(_metric_float(parsed))
    return parsed_values


def _target_depth_error_metrics(
    residual_depth_grid_m: list[float],
    target_indices: list[int],
) -> dict[str, float | None]:
    if not target_indices:
        return {
            "rmse": None,
            "mae": None,
            "abs_max": None,
        }

    residuals = [residual_depth_grid_m[index] for index in target_indices]
    squared_error_sum = math.fsum(residual * residual for residual in residuals)
    absolute_errors = [abs(residual) for residual in residuals]
    return {
        "rmse": _metric_float(math.sqrt(squared_error_sum / len(residuals))),
        "mae": _metric_float(math.fsum(absolute_errors) / len(absolute_errors)),
        "abs_max": _metric_float(max(absolute_errors)),
    }


def _parse_mask(values: Sequence[Any]) -> list[bool] | None:
    parsed_values: list[bool] = []
    for value in values:
        parsed = _parse_finite_float(value)
        if parsed is None:
            return None
        parsed_values.append(parsed > 0.5)
    return parsed_values


def _parse_finite_float(value: Any) -> float | None:
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


def _metric_sum(values: Any) -> float:
    return _metric_float(math.fsum(values))


def _metric_float(value: float) -> float:
    rounded = round(float(value), 12)
    return 0.0 if rounded == -0.0 else rounded


__all__ = ["build_target_residual_metrics"]
