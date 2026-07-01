"""Explicit target-shape residual metrics for eval diagnostics."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any


SOURCE = "explicit_target_grid_removed_depth_comparison"
DEFAULT_PROFILE = "explicit_target_shape_residual_metrics"
SHAPE_OVERLAP_SOURCE = "explicit_target_shape_overlap_diagnostics"
DILATION_TYPE = "chebyshev_8_neighbor_row_major"
CELL_RADIUS_RULE = "ceil(tolerance_m / cell_size_m)"
REMOVED_ACTIVE_DEPTH_THRESHOLD_M = 0.0
METER_TOLERANCE_PROFILES = (
    ("narrow_0_30m", 0.30),
    ("bucket_0_50m", 0.50),
)


def build_target_residual_metrics(
    *,
    removed_depth_grid_m: Sequence[Any],
    target_depth_grid_m: Sequence[Any],
    target_region_mask: Sequence[Any],
    valid_mask: Sequence[Any],
    profile: str = DEFAULT_PROFILE,
    grid_shape: Sequence[Any] | None = None,
    cell_size_m: float | None = None,
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
            target_shape_overlap_diagnostics=_unavailable_shape_overlap_diagnostics(
                "invalid_grid_lengths",
            ),
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
            target_shape_overlap_diagnostics=_unavailable_shape_overlap_diagnostics(
                "invalid_depth_values",
            ),
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
            target_shape_overlap_diagnostics=_unavailable_shape_overlap_diagnostics(
                "invalid_mask_values",
            ),
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
            target_shape_overlap_diagnostics=_unavailable_shape_overlap_diagnostics(
                "invalid_target_region_mask",
                valid_cell_count=valid_cell_count,
            ),
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
        target_shape_overlap_diagnostics=_target_shape_overlap_diagnostics(
            removed_depth_grid_m=removed_depth,
            target_indices=target_indices,
            outside_target_indices=outside_target_indices,
            valid_cells=valid_cells,
            grid_shape=grid_shape,
            cell_size_m=cell_size_m,
        ),
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
    target_shape_overlap_diagnostics: dict[str, Any],
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
        "target_shape_overlap_diagnostics": target_shape_overlap_diagnostics,
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


def _target_shape_overlap_diagnostics(
    *,
    removed_depth_grid_m: list[float],
    target_indices: list[int],
    outside_target_indices: list[int],
    valid_cells: list[bool],
    grid_shape: Sequence[Any] | None,
    cell_size_m: float | None,
) -> dict[str, Any]:
    cell_count = len(valid_cells)
    valid_cell_count = sum(1 for is_valid in valid_cells if is_valid)
    removed_active_indices = [
        index
        for index, (removed_depth, is_valid) in enumerate(
            zip(removed_depth_grid_m, valid_cells, strict=True)
        )
        if is_valid and removed_depth > REMOVED_ACTIVE_DEPTH_THRESHOLD_M
    ]
    parsed_grid_shape, grid_shape_status = _parse_grid_shape_for_overlap(
        grid_shape,
        cell_count,
    )
    parsed_cell_size, cell_size_status = _parse_cell_size(cell_size_m)
    dilated_overlap = (
        _dilated_overlap(
            target_indices=target_indices,
            removed_active_indices=removed_active_indices,
            removed_depth_grid_m=removed_depth_grid_m,
            valid_cells=valid_cells,
            grid_shape=parsed_grid_shape,
            cell_radius=1,
        )
        if parsed_grid_shape is not None
        else _unavailable_dilated_overlap(
            grid_shape_status,
            valid_cell_count=valid_cell_count,
        )
    )

    return {
        "status": "present",
        "source": SHAPE_OVERLAP_SOURCE,
        "semantics": "diagnostic_only",
        "removed_active_depth_threshold_m": REMOVED_ACTIVE_DEPTH_THRESHOLD_M,
        "grid_shape": (
            [parsed_grid_shape[0], parsed_grid_shape[1]]
            if parsed_grid_shape is not None
            else None
        ),
        "cell_size_m": parsed_cell_size,
        "raw_target_overlap": _raw_target_overlap(
            target_indices=target_indices,
            removed_active_indices=removed_active_indices,
            removed_depth_grid_m=removed_depth_grid_m,
            outside_target_indices=outside_target_indices,
        ),
        "one_cell_dilated_target_overlap": dilated_overlap,
        "meter_tolerance_profiles": _meter_tolerance_profiles(
            target_indices=target_indices,
            removed_active_indices=removed_active_indices,
            removed_depth_grid_m=removed_depth_grid_m,
            valid_cells=valid_cells,
            parsed_grid_shape=parsed_grid_shape,
            grid_shape_status=grid_shape_status,
            cell_size_m=parsed_cell_size,
            cell_size_status=cell_size_status,
        ),
    }


def _raw_target_overlap(
    *,
    target_indices: list[int],
    removed_active_indices: list[int],
    removed_depth_grid_m: list[float],
    outside_target_indices: list[int],
) -> dict[str, Any]:
    target_set = set(target_indices)
    removed_active_set = set(removed_active_indices)
    intersection_cell_count = len(target_set & removed_active_set)
    union_cell_count = len(target_set | removed_active_set)
    return {
        "status": "present",
        "target_cell_count": len(target_indices),
        "removed_active_cell_count": len(removed_active_indices),
        "intersection_cell_count": intersection_cell_count,
        "union_cell_count": union_cell_count,
        "iou": _overlap_iou(intersection_cell_count, union_cell_count),
        "outside_raw_target_removed_depth_sum_m": _metric_sum(
            removed_depth_grid_m[index] for index in outside_target_indices
        ),
    }


def _meter_tolerance_profiles(
    *,
    target_indices: list[int],
    removed_active_indices: list[int],
    removed_depth_grid_m: list[float],
    valid_cells: list[bool],
    parsed_grid_shape: tuple[int, int] | None,
    grid_shape_status: str,
    cell_size_m: float | None,
    cell_size_status: str,
) -> dict[str, dict[str, Any]]:
    profiles = {}
    for profile_name, tolerance_m in METER_TOLERANCE_PROFILES:
        if cell_size_status != "present":
            profiles[profile_name] = _unavailable_meter_tolerance_profile(
                status=cell_size_status,
                tolerance_m=tolerance_m,
                cell_size_m=cell_size_m,
            )
            continue
        if parsed_grid_shape is None:
            profiles[profile_name] = _unavailable_meter_tolerance_profile(
                status=grid_shape_status,
                tolerance_m=tolerance_m,
                cell_size_m=cell_size_m,
            )
            continue

        cell_radius = int(math.ceil(tolerance_m / float(cell_size_m)))
        profiles[profile_name] = {
            "tolerance_m": _metric_float(tolerance_m),
            "cell_size_m": cell_size_m,
            **_dilated_overlap(
                target_indices=target_indices,
                removed_active_indices=removed_active_indices,
                removed_depth_grid_m=removed_depth_grid_m,
                valid_cells=valid_cells,
                grid_shape=parsed_grid_shape,
                cell_radius=cell_radius,
            ),
            "cell_radius_rule": CELL_RADIUS_RULE,
        }
    return profiles


def _dilated_overlap(
    *,
    target_indices: list[int],
    removed_active_indices: list[int],
    removed_depth_grid_m: list[float],
    valid_cells: list[bool],
    grid_shape: tuple[int, int],
    cell_radius: int,
) -> dict[str, Any]:
    valid_cell_count = sum(1 for is_valid in valid_cells if is_valid)
    dilated_target_indices = _dilate_target_indices(
        target_indices,
        valid_cells=valid_cells,
        grid_shape=grid_shape,
        cell_radius=cell_radius,
    )
    removed_active_set = set(removed_active_indices)
    intersection_cell_count = len(dilated_target_indices & removed_active_set)
    union_cell_count = len(dilated_target_indices | removed_active_set)
    return {
        "status": "present",
        "dilation_type": DILATION_TYPE,
        "cell_radius": int(cell_radius),
        "dilated_target_cell_count": len(dilated_target_indices),
        "valid_cell_count": valid_cell_count,
        "saturation_ratio": (
            _metric_float(len(dilated_target_indices) / valid_cell_count)
            if valid_cell_count > 0
            else None
        ),
        "intersection_cell_count": intersection_cell_count,
        "union_cell_count": union_cell_count,
        "iou": _overlap_iou(intersection_cell_count, union_cell_count),
        "outside_dilated_target_removed_depth_sum_m": _metric_sum(
            removed_depth
            for index, removed_depth in enumerate(removed_depth_grid_m)
            if valid_cells[index] and index not in dilated_target_indices
        ),
    }


def _dilate_target_indices(
    target_indices: list[int],
    *,
    valid_cells: list[bool],
    grid_shape: tuple[int, int],
    cell_radius: int,
) -> set[int]:
    row_count, col_count = grid_shape
    dilated_indices: set[int] = set()
    for index in target_indices:
        row = index // col_count
        col = index % col_count
        for neighbor_row in range(
            max(0, row - cell_radius),
            min(row_count, row + cell_radius + 1),
        ):
            for neighbor_col in range(
                max(0, col - cell_radius),
                min(col_count, col + cell_radius + 1),
            ):
                neighbor_index = neighbor_row * col_count + neighbor_col
                if valid_cells[neighbor_index]:
                    dilated_indices.add(neighbor_index)
    return dilated_indices


def _parse_grid_shape_for_overlap(
    grid_shape: Sequence[Any] | None,
    cell_count: int,
) -> tuple[tuple[int, int] | None, str]:
    if grid_shape is None:
        return None, "grid_shape_missing"
    if len(grid_shape) != 2:
        return None, "invalid_grid_shape"
    row_count = _parse_positive_int(grid_shape[0])
    col_count = _parse_positive_int(grid_shape[1])
    if row_count is None or col_count is None or row_count * col_count != cell_count:
        return None, "invalid_grid_shape"
    return (row_count, col_count), "present"


def _parse_cell_size(cell_size_m: float | None) -> tuple[float | None, str]:
    if cell_size_m is None:
        return None, "cell_size_missing"
    parsed = _parse_finite_float(cell_size_m)
    if parsed is None or parsed <= 0.0:
        return None, "invalid_cell_size"
    return _metric_float(parsed), "present"


def _parse_positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    parsed = _parse_finite_float(value)
    if parsed is None:
        return None
    rounded = round(parsed)
    if rounded <= 0 or not math.isclose(
        parsed,
        float(rounded),
        rel_tol=0.0,
        abs_tol=1e-6,
    ):
        return None
    return int(rounded)


def _overlap_iou(
    intersection_cell_count: int,
    union_cell_count: int,
) -> float | None:
    if union_cell_count == 0:
        return None
    return _metric_float(intersection_cell_count / union_cell_count)


def _unavailable_shape_overlap_diagnostics(
    status: str,
    *,
    valid_cell_count: int = 0,
) -> dict[str, Any]:
    return {
        "status": status,
        "source": SHAPE_OVERLAP_SOURCE,
        "semantics": "diagnostic_only",
        "removed_active_depth_threshold_m": REMOVED_ACTIVE_DEPTH_THRESHOLD_M,
        "grid_shape": None,
        "cell_size_m": None,
        "raw_target_overlap": {
            "status": status,
            "target_cell_count": None,
            "removed_active_cell_count": None,
            "intersection_cell_count": None,
            "union_cell_count": None,
            "iou": None,
            "outside_raw_target_removed_depth_sum_m": None,
        },
        "one_cell_dilated_target_overlap": _unavailable_dilated_overlap(
            status,
            valid_cell_count=valid_cell_count,
        ),
        "meter_tolerance_profiles": {
            profile_name: _unavailable_meter_tolerance_profile(
                status=status,
                tolerance_m=tolerance_m,
                cell_size_m=None,
            )
            for profile_name, tolerance_m in METER_TOLERANCE_PROFILES
        },
    }


def _unavailable_dilated_overlap(
    status: str,
    *,
    valid_cell_count: int,
) -> dict[str, Any]:
    return {
        "status": status,
        "dilation_type": DILATION_TYPE,
        "cell_radius": None,
        "dilated_target_cell_count": None,
        "valid_cell_count": int(valid_cell_count),
        "saturation_ratio": None,
        "intersection_cell_count": None,
        "union_cell_count": None,
        "iou": None,
        "outside_dilated_target_removed_depth_sum_m": None,
    }


def _unavailable_meter_tolerance_profile(
    *,
    status: str,
    tolerance_m: float,
    cell_size_m: float | None,
) -> dict[str, Any]:
    return {
        "status": status,
        "tolerance_m": _metric_float(tolerance_m),
        "cell_size_m": cell_size_m,
        "cell_radius": None,
        "cell_radius_rule": CELL_RADIUS_RULE,
        "dilation_type": DILATION_TYPE,
        "dilated_target_cell_count": None,
        "valid_cell_count": None,
        "saturation_ratio": None,
        "intersection_cell_count": None,
        "union_cell_count": None,
        "iou": None,
        "outside_dilated_target_removed_depth_sum_m": None,
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
