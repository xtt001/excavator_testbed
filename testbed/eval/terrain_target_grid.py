"""Explicit diagnostic terrain target-grid generation for eval tooling."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

SOURCE = "explicit_rectangular_target_grid_spec"
DEFAULT_PROFILE = "explicit_t1_like_rectangular_shallow_pit"


def build_rectangular_target_grid(
    *,
    grid_shape: Sequence[Any],
    valid_mask: Sequence[Any],
    row_start: int,
    row_end: int,
    col_start: int,
    col_end: int,
    target_depth_m: float,
    profile: str = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Build a row-major target-depth grid from an explicit rectangle spec."""

    parsed_shape = _parse_grid_shape(grid_shape)
    if parsed_shape is None:
        return _target_grid_result(
            status="invalid_grid_shape",
            profile=profile,
            grid_shape=None,
            target_depth_grid_m=[],
            target_region_mask=[],
            valid_cell_count=0,
            target_cell_count=0,
            target_depth_sum_m=0.0,
            invalid_target_cell_count=0,
            rectangle_bounds=_rectangle_bounds(row_start, row_end, col_start, col_end),
            validation_errors=[
                "grid_shape must contain two positive integer counts",
            ],
        )

    row_count, col_count = parsed_shape
    cell_count = row_count * col_count
    parsed_valid_mask, valid_mask_error = _parse_valid_mask(valid_mask, cell_count)
    if parsed_valid_mask is None:
        return _target_grid_result(
            status="invalid_valid_mask",
            profile=profile,
            grid_shape=[row_count, col_count],
            target_depth_grid_m=[],
            target_region_mask=[],
            valid_cell_count=0,
            target_cell_count=0,
            target_depth_sum_m=0.0,
            invalid_target_cell_count=0,
            rectangle_bounds=_rectangle_bounds(row_start, row_end, col_start, col_end),
            validation_errors=[valid_mask_error],
        )

    valid_cell_count = sum(1 for is_valid in parsed_valid_mask if is_valid)
    empty_depth_grid = [0.0] * cell_count
    empty_region_mask = [0] * cell_count

    target_depth = _parse_positive_float(target_depth_m)
    if target_depth is None:
        return _target_grid_result(
            status="invalid_target_depth",
            profile=profile,
            grid_shape=[row_count, col_count],
            target_depth_grid_m=empty_depth_grid,
            target_region_mask=empty_region_mask,
            valid_cell_count=valid_cell_count,
            target_cell_count=0,
            target_depth_sum_m=0.0,
            invalid_target_cell_count=0,
            rectangle_bounds=_rectangle_bounds(row_start, row_end, col_start, col_end),
            validation_errors=[
                "target_depth_m must be finite and greater than 0",
            ],
        )

    rectangle_indices = _rectangle_indices(
        row_count=row_count,
        col_count=col_count,
        row_start=row_start,
        row_end=row_end,
        col_start=col_start,
        col_end=col_end,
    )
    if rectangle_indices is None:
        return _target_grid_result(
            status="invalid_rectangle_bounds",
            profile=profile,
            grid_shape=[row_count, col_count],
            target_depth_grid_m=empty_depth_grid,
            target_region_mask=empty_region_mask,
            valid_cell_count=valid_cell_count,
            target_cell_count=0,
            target_depth_sum_m=0.0,
            invalid_target_cell_count=0,
            rectangle_bounds=_rectangle_bounds(row_start, row_end, col_start, col_end),
            validation_errors=[
                "rectangle bounds must be non-empty and within grid_shape",
            ],
        )

    invalid_target_cell_count = sum(
        1 for index in rectangle_indices if not parsed_valid_mask[index]
    )
    if invalid_target_cell_count:
        return _target_grid_result(
            status="invalid_target_region_mask",
            profile=profile,
            grid_shape=[row_count, col_count],
            target_depth_grid_m=empty_depth_grid,
            target_region_mask=empty_region_mask,
            valid_cell_count=valid_cell_count,
            target_cell_count=0,
            target_depth_sum_m=0.0,
            invalid_target_cell_count=invalid_target_cell_count,
            rectangle_bounds=_rectangle_bounds(row_start, row_end, col_start, col_end),
            validation_errors=[
                "rectangle selects invalid cells; target cells are rejected",
            ],
        )

    target_depth_grid = [0.0] * cell_count
    target_region_mask = [0] * cell_count
    for index in rectangle_indices:
        target_depth_grid[index] = target_depth
        target_region_mask[index] = 1

    target_cell_count = len(rectangle_indices)
    return _target_grid_result(
        status="present",
        profile=profile,
        grid_shape=[row_count, col_count],
        target_depth_grid_m=target_depth_grid,
        target_region_mask=target_region_mask,
        valid_cell_count=valid_cell_count,
        target_cell_count=target_cell_count,
        target_depth_sum_m=_metric_float(target_depth * target_cell_count),
        invalid_target_cell_count=0,
        rectangle_bounds=_rectangle_bounds(row_start, row_end, col_start, col_end),
        validation_errors=[],
    )


def _target_grid_result(
    *,
    status: str,
    profile: str,
    grid_shape: list[int] | None,
    target_depth_grid_m: list[float],
    target_region_mask: list[int],
    valid_cell_count: int,
    target_cell_count: int,
    target_depth_sum_m: float,
    invalid_target_cell_count: int,
    rectangle_bounds: dict[str, int],
    validation_errors: list[str],
) -> dict[str, Any]:
    return {
        "status": status,
        "source": SOURCE,
        "profile": str(profile),
        "grid_shape": grid_shape,
        "target_depth_grid_m": target_depth_grid_m,
        "target_region_mask": target_region_mask,
        "valid_cell_count": int(valid_cell_count),
        "target_cell_count": int(target_cell_count),
        "target_depth_sum_m": _metric_float(target_depth_sum_m),
        "invalid_target_cell_count": int(invalid_target_cell_count),
        "rectangle_bounds": rectangle_bounds,
        "validation_errors": validation_errors,
        **_missing_provenance_fields(),
    }


def _parse_grid_shape(grid_shape: Sequence[Any]) -> tuple[int, int] | None:
    if len(grid_shape) != 2:
        return None
    row_count = _parse_positive_int(grid_shape[0])
    col_count = _parse_positive_int(grid_shape[1])
    if row_count is None or col_count is None:
        return None
    return row_count, col_count


def _parse_valid_mask(
    valid_mask: Sequence[Any],
    cell_count: int,
) -> tuple[list[bool] | None, str]:
    if len(valid_mask) != cell_count:
        return None, "valid_mask length must match grid cell count"
    parsed: list[bool] = []
    for value in valid_mask:
        parsed_value = _parse_finite_float(value)
        if parsed_value is None:
            return None, "valid_mask values must be finite numbers"
        parsed.append(parsed_value > 0.5)
    return parsed, ""


def _rectangle_indices(
    *,
    row_count: int,
    col_count: int,
    row_start: int,
    row_end: int,
    col_start: int,
    col_end: int,
) -> list[int] | None:
    if (
        row_start < 0
        or col_start < 0
        or row_end > row_count
        or col_end > col_count
        or row_start >= row_end
        or col_start >= col_end
    ):
        return None
    return [
        row_index * col_count + col_index
        for row_index in range(row_start, row_end)
        for col_index in range(col_start, col_end)
    ]


def _rectangle_bounds(
    row_start: int,
    row_end: int,
    col_start: int,
    col_end: int,
) -> dict[str, int]:
    return {
        "row_start": int(row_start),
        "row_end": int(row_end),
        "col_start": int(col_start),
        "col_end": int(col_end),
    }


def _parse_positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0 or not math.isclose(float(value), float(parsed), abs_tol=1e-6):
        return None
    return parsed


def _parse_positive_float(value: Any) -> float | None:
    parsed = _parse_finite_float(value)
    if parsed is None or parsed <= 0.0:
        return None
    return _metric_float(parsed)


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


def _metric_float(value: float) -> float:
    rounded = round(float(value), 12)
    return 0.0 if rounded == -0.0 else rounded


__all__ = ["build_rectangular_target_grid"]
