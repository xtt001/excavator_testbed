"""Offline geometric effect evidence for terrain cut candidates."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


SCHEMA = "terrain_candidate_geometric_effect_v1"
SOURCE = "explicit_geometric_swept_footprint_effect"
DEFAULT_PROFILE = "explicit_geometric_swept_footprint_effect"
FOOTPRINT_MODEL = "centerline_rectangular_swept_footprint_approximation"
DIRECTION_DELTAS = {
    "row_forward": (0, 1),
    "row_reverse": (0, -1),
    "col_forward": (1, 0),
    "col_reverse": (-1, 0),
}


def build_geometric_swept_footprint_effect(
    *,
    candidate: Mapping[str, Any],
    removed_depth_grid_m: Sequence[Any],
    target_depth_grid_m: Sequence[Any],
    target_region_mask: Sequence[Any],
    valid_mask: Sequence[Any],
    grid_shape: Sequence[Any],
    cell_size_m: Any,
    bucket_width_m: Any,
    bucket_length_m: Any,
    penetration_depth_m: Any = None,
    profile: str = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Estimate an offline rectangular swept-footprint delta patch."""

    lengths = {
        len(removed_depth_grid_m),
        len(target_depth_grid_m),
        len(target_region_mask),
        len(valid_mask),
    }
    if len(lengths) != 1 or not lengths or next(iter(lengths)) == 0:
        return _effect_result(
            status="invalid_grid_lengths",
            profile=profile,
            candidate_id=None,
            grid_shape=None,
            geometry_inputs=_empty_geometry_inputs(),
            footprint=_empty_footprint(),
            expected_delta_depth_grid_m=[],
            summary_metrics=_empty_summary_metrics(),
            validation_errors=[
                "removed_depth_grid_m, target_depth_grid_m, target_region_mask, and valid_mask must have matching non-empty lengths",
            ],
        )

    cell_count = next(iter(lengths))
    parsed_grid_shape = _parse_grid_shape(grid_shape, cell_count)
    if parsed_grid_shape is None:
        return _effect_result(
            status="invalid_grid_shape",
            profile=profile,
            candidate_id=None,
            grid_shape=None,
            geometry_inputs=_empty_geometry_inputs(),
            footprint=_empty_footprint(),
            expected_delta_depth_grid_m=[],
            summary_metrics=_empty_summary_metrics(),
            validation_errors=[
                "grid_shape must contain two positive integers whose product matches grid length",
            ],
        )

    removed_depth = _parse_depth_grid(removed_depth_grid_m)
    target_depth = _parse_depth_grid(target_depth_grid_m)
    if removed_depth is None or target_depth is None:
        return _effect_result(
            status="invalid_depth_values",
            profile=profile,
            candidate_id=None,
            grid_shape=[parsed_grid_shape[0], parsed_grid_shape[1]],
            geometry_inputs=_empty_geometry_inputs(),
            footprint=_empty_footprint(),
            expected_delta_depth_grid_m=[],
            summary_metrics=_empty_summary_metrics(),
            validation_errors=[
                "removed_depth_grid_m and target_depth_grid_m values must be finite nonnegative numbers",
            ],
        )

    target_mask = _parse_mask(target_region_mask)
    valid_cells = _parse_mask(valid_mask)
    if target_mask is None or valid_cells is None:
        return _effect_result(
            status="invalid_mask_values",
            profile=profile,
            candidate_id=None,
            grid_shape=[parsed_grid_shape[0], parsed_grid_shape[1]],
            geometry_inputs=_empty_geometry_inputs(),
            footprint=_empty_footprint(),
            expected_delta_depth_grid_m=[],
            summary_metrics=_empty_summary_metrics(),
            validation_errors=[
                "target_region_mask and valid_mask values must be finite booleans or numbers",
            ],
        )

    parsed_candidate, candidate_errors = _parse_candidate(
        candidate,
        grid_shape=parsed_grid_shape,
        cell_count=cell_count,
    )
    if candidate_errors:
        return _effect_result(
            status="invalid_candidate",
            profile=profile,
            candidate_id=None,
            grid_shape=[parsed_grid_shape[0], parsed_grid_shape[1]],
            geometry_inputs=_empty_geometry_inputs(),
            footprint=_empty_footprint(),
            expected_delta_depth_grid_m=[],
            summary_metrics=_empty_summary_metrics(),
            validation_errors=candidate_errors,
        )

    geometry, geometry_errors = _parse_geometry(
        cell_size_m=cell_size_m,
        bucket_width_m=bucket_width_m,
        bucket_length_m=bucket_length_m,
        penetration_depth_m=penetration_depth_m,
        candidate_depth_m=parsed_candidate["candidate_depth_m"],
    )
    geometry_inputs = _geometry_inputs(geometry)
    if geometry_errors:
        return _effect_result(
            status="invalid_geometry",
            profile=profile,
            candidate_id=parsed_candidate["candidate_id"],
            grid_shape=[parsed_grid_shape[0], parsed_grid_shape[1]],
            geometry_inputs=geometry_inputs,
            footprint=_empty_footprint(),
            expected_delta_depth_grid_m=[],
            summary_metrics=_empty_summary_metrics(),
            validation_errors=geometry_errors,
        )

    footprint_indices = _footprint_cell_indices(
        candidate=parsed_candidate,
        valid_cells=valid_cells,
        grid_shape=parsed_grid_shape,
        cell_size_m=geometry["cell_size_m"],
        bucket_width_m=geometry["bucket_width_m"],
        bucket_length_m=geometry["bucket_length_m"],
    )
    footprint_clipped = _footprint_clipped_by_grid_boundary(
        candidate=parsed_candidate,
        grid_shape=parsed_grid_shape,
        cell_size_m=geometry["cell_size_m"],
        bucket_width_m=geometry["bucket_width_m"],
        bucket_length_m=geometry["bucket_length_m"],
    )
    if not footprint_indices:
        return _effect_result(
            status="no_valid_footprint_cells",
            profile=profile,
            candidate_id=parsed_candidate["candidate_id"],
            grid_shape=[parsed_grid_shape[0], parsed_grid_shape[1]],
            geometry_inputs=geometry_inputs,
            footprint=_footprint_result(
                candidate=parsed_candidate,
                footprint_indices=[],
                footprint_clipped_by_grid_boundary=footprint_clipped,
                cell_area_m2=geometry["cell_size_m"] ** 2,
            ),
            expected_delta_depth_grid_m=[0.0 for _ in range(cell_count)],
            summary_metrics=_empty_summary_metrics(),
            validation_errors=[],
        )

    expected_delta_depth_grid_m = [
        geometry["penetration_depth_m"] if index in set(footprint_indices) else 0.0
        for index in range(cell_count)
    ]
    expected_delta_depth_grid_m = [
        _metric_float(value) for value in expected_delta_depth_grid_m
    ]
    summary_metrics = _summary_metrics(
        expected_delta_depth_grid_m=expected_delta_depth_grid_m,
        removed_depth=removed_depth,
        target_depth=target_depth,
        target_mask=target_mask,
        valid_cells=valid_cells,
        cell_area_m2=geometry["cell_size_m"] ** 2,
    )

    return _effect_result(
        status="present",
        profile=profile,
        candidate_id=parsed_candidate["candidate_id"],
        grid_shape=[parsed_grid_shape[0], parsed_grid_shape[1]],
        geometry_inputs=geometry_inputs,
        footprint=_footprint_result(
            candidate=parsed_candidate,
            footprint_indices=footprint_indices,
            footprint_clipped_by_grid_boundary=footprint_clipped,
            cell_area_m2=geometry["cell_size_m"] ** 2,
        ),
        expected_delta_depth_grid_m=expected_delta_depth_grid_m,
        summary_metrics=summary_metrics,
        validation_errors=[],
    )


def _parse_candidate(
    candidate: Mapping[str, Any],
    *,
    grid_shape: tuple[int, int],
    cell_count: int,
) -> tuple[dict[str, Any], list[str]]:
    required_fields = {
        "candidate_id",
        "anchor_cell_index",
        "anchor_row",
        "anchor_col",
        "direction",
        "candidate_depth_m",
        "offline_only",
    }
    if not isinstance(candidate, Mapping):
        return {}, ["candidate must be a mapping"]
    missing_fields = sorted(required_fields - set(candidate.keys()))
    if missing_fields:
        return {}, [
            "candidate missing required fields: " + ", ".join(missing_fields)
        ]

    row_count, col_count = grid_shape
    candidate_id = str(candidate["candidate_id"])
    anchor_cell_index = _parse_integer(candidate["anchor_cell_index"])
    anchor_row = _parse_integer(candidate["anchor_row"])
    anchor_col = _parse_integer(candidate["anchor_col"])
    direction = str(candidate["direction"])
    candidate_depth = _parse_nonnegative_float(candidate["candidate_depth_m"])
    offline_only = candidate["offline_only"] is True
    if (
        not candidate_id
        or anchor_cell_index is None
        or anchor_cell_index < 0
        or anchor_cell_index >= cell_count
        or anchor_row is None
        or anchor_col is None
        or anchor_row < 0
        or anchor_row >= row_count
        or anchor_col < 0
        or anchor_col >= col_count
        or anchor_cell_index != anchor_row * col_count + anchor_col
        or direction not in DIRECTION_DELTAS
        or candidate_depth is None
        or not offline_only
    ):
        return {}, ["candidate has invalid geometric effect fields"]

    return (
        {
            "candidate_id": candidate_id,
            "anchor_cell_index": anchor_cell_index,
            "anchor_row": anchor_row,
            "anchor_col": anchor_col,
            "direction": direction,
            "candidate_depth_m": candidate_depth,
            "offline_only": True,
        },
        [],
    )


def _parse_geometry(
    *,
    cell_size_m: Any,
    bucket_width_m: Any,
    bucket_length_m: Any,
    penetration_depth_m: Any,
    candidate_depth_m: float,
) -> tuple[dict[str, Any], list[str]]:
    parsed_cell_size = _parse_positive_float(cell_size_m)
    parsed_bucket_width = _parse_positive_float(bucket_width_m)
    parsed_bucket_length = _parse_positive_float(bucket_length_m)
    validation_errors: list[str] = []
    if parsed_cell_size is None:
        validation_errors.append("cell_size_m must be a finite positive number")
    if parsed_bucket_width is None:
        validation_errors.append("bucket_width_m must be a finite positive number")
    if parsed_bucket_length is None:
        validation_errors.append("bucket_length_m must be a finite positive number")

    if penetration_depth_m is None:
        parsed_penetration = candidate_depth_m
        penetration_source = "candidate_depth_m"
    else:
        parsed_penetration = _parse_nonnegative_float(penetration_depth_m)
        penetration_source = "explicit_penetration_depth_m"
        if parsed_penetration is None:
            validation_errors.append(
                "penetration_depth_m must be a finite nonnegative number when provided"
            )
            parsed_penetration = 0.0

    return (
        {
            "cell_size_m": parsed_cell_size,
            "bucket_width_m": parsed_bucket_width,
            "bucket_length_m": parsed_bucket_length,
            "penetration_depth_m": parsed_penetration,
            "penetration_depth_source": penetration_source,
        },
        validation_errors,
    )


def _footprint_cell_indices(
    *,
    candidate: dict[str, Any],
    valid_cells: list[bool],
    grid_shape: tuple[int, int],
    cell_size_m: float,
    bucket_width_m: float,
    bucket_length_m: float,
) -> list[int]:
    _, col_count = grid_shape
    half_width_m = bucket_width_m / 2.0
    footprint_indices: list[int] = []
    for index, is_valid in enumerate(valid_cells):
        if not is_valid:
            continue
        row = index // col_count
        col = index % col_count
        row_delta_m = (row - candidate["anchor_row"]) * cell_size_m
        col_delta_m = (col - candidate["anchor_col"]) * cell_size_m
        along_m, lateral_m = _directional_distances(
            direction=candidate["direction"],
            row_delta_m=row_delta_m,
            col_delta_m=col_delta_m,
        )
        if (
            -1e-12 <= along_m <= bucket_length_m + 1e-12
            and abs(lateral_m) <= half_width_m + 1e-12
        ):
            footprint_indices.append(index)
    return footprint_indices


def _directional_distances(
    *,
    direction: str,
    row_delta_m: float,
    col_delta_m: float,
) -> tuple[float, float]:
    if direction == "row_forward":
        return col_delta_m, row_delta_m
    if direction == "row_reverse":
        return -col_delta_m, row_delta_m
    if direction == "col_forward":
        return row_delta_m, col_delta_m
    return -row_delta_m, col_delta_m


def _footprint_clipped_by_grid_boundary(
    *,
    candidate: dict[str, Any],
    grid_shape: tuple[int, int],
    cell_size_m: float,
    bucket_width_m: float,
    bucket_length_m: float,
) -> bool:
    row_count, col_count = grid_shape
    anchor_row_m = candidate["anchor_row"] * cell_size_m
    anchor_col_m = candidate["anchor_col"] * cell_size_m
    half_width_m = bucket_width_m / 2.0
    max_row_m = (row_count - 1) * cell_size_m
    max_col_m = (col_count - 1) * cell_size_m

    if candidate["direction"] == "row_forward":
        row_min = anchor_row_m - half_width_m
        row_max = anchor_row_m + half_width_m
        col_min = anchor_col_m
        col_max = anchor_col_m + bucket_length_m
    elif candidate["direction"] == "row_reverse":
        row_min = anchor_row_m - half_width_m
        row_max = anchor_row_m + half_width_m
        col_min = anchor_col_m - bucket_length_m
        col_max = anchor_col_m
    elif candidate["direction"] == "col_forward":
        row_min = anchor_row_m
        row_max = anchor_row_m + bucket_length_m
        col_min = anchor_col_m - half_width_m
        col_max = anchor_col_m + half_width_m
    else:
        row_min = anchor_row_m - bucket_length_m
        row_max = anchor_row_m
        col_min = anchor_col_m - half_width_m
        col_max = anchor_col_m + half_width_m

    return row_min < 0.0 or col_min < 0.0 or row_max > max_row_m or col_max > max_col_m


def _summary_metrics(
    *,
    expected_delta_depth_grid_m: list[float],
    removed_depth: list[float],
    target_depth: list[float],
    target_mask: list[bool],
    valid_cells: list[bool],
    cell_area_m2: float,
) -> dict[str, float]:
    expected_removed_depth_sum = math.fsum(
        delta
        for delta, is_valid in zip(expected_delta_depth_grid_m, valid_cells, strict=True)
        if is_valid
    )
    target_removed_delta_sum = math.fsum(
        delta
        for delta, is_target, is_valid in zip(
            expected_delta_depth_grid_m,
            target_mask,
            valid_cells,
            strict=True,
        )
        if is_valid and is_target
    )
    outside_target_removed_delta_sum = math.fsum(
        delta
        for delta, is_target, is_valid in zip(
            expected_delta_depth_grid_m,
            target_mask,
            valid_cells,
            strict=True,
        )
        if is_valid and not is_target
    )
    overdig_depth_delta_sum = math.fsum(
        max(removed + delta - target, 0.0) - max(removed - target, 0.0)
        for removed, target, delta, is_valid in zip(
            removed_depth,
            target_depth,
            expected_delta_depth_grid_m,
            valid_cells,
            strict=True,
        )
        if is_valid
    )
    return {
        "expected_removed_depth_sum_m": _metric_float(expected_removed_depth_sum),
        "expected_removed_volume_m3": _metric_float(
            expected_removed_depth_sum * cell_area_m2
        ),
        "target_removed_delta_sum_m": _metric_float(target_removed_delta_sum),
        "target_removed_volume_m3": _metric_float(
            target_removed_delta_sum * cell_area_m2
        ),
        "outside_target_removed_delta_sum_m": _metric_float(
            outside_target_removed_delta_sum
        ),
        "outside_target_removed_volume_m3": _metric_float(
            outside_target_removed_delta_sum * cell_area_m2
        ),
        "overdig_depth_delta_sum_m": _metric_float(overdig_depth_delta_sum),
        "overdig_volume_delta_m3": _metric_float(
            overdig_depth_delta_sum * cell_area_m2
        ),
    }


def _effect_result(
    *,
    status: str,
    profile: str,
    candidate_id: str | None,
    grid_shape: list[int] | None,
    geometry_inputs: dict[str, Any],
    footprint: dict[str, Any],
    expected_delta_depth_grid_m: list[float],
    summary_metrics: dict[str, Any],
    validation_errors: list[str],
) -> dict[str, Any]:
    return {
        "status": status,
        "schema": SCHEMA,
        "source": SOURCE,
        "offline_only": True,
        "profile": str(profile),
        "candidate_id": candidate_id,
        "grid_shape": grid_shape,
        "geometry_inputs": geometry_inputs,
        "footprint": footprint,
        "expected_delta_depth_grid_m": expected_delta_depth_grid_m,
        "summary_metrics": summary_metrics,
        "validation_errors": validation_errors,
        "provenance": _provenance_fields(geometry_inputs),
    }


def _geometry_inputs(geometry: dict[str, Any]) -> dict[str, Any]:
    return {
        "cell_size_m": geometry["cell_size_m"],
        "bucket_width_m": geometry["bucket_width_m"],
        "bucket_length_m": geometry["bucket_length_m"],
        "penetration_depth_m": geometry["penetration_depth_m"],
        "penetration_depth_source": geometry["penetration_depth_source"],
    }


def _empty_geometry_inputs() -> dict[str, Any]:
    return {
        "cell_size_m": None,
        "bucket_width_m": None,
        "bucket_length_m": None,
        "penetration_depth_m": None,
        "penetration_depth_source": None,
    }


def _footprint_result(
    *,
    candidate: dict[str, Any],
    footprint_indices: list[int],
    footprint_clipped_by_grid_boundary: bool,
    cell_area_m2: float,
) -> dict[str, Any]:
    return {
        "model": FOOTPRINT_MODEL,
        "model_scope": "offline_geometric_approximation_not_calibrated_bucket_physics",
        "direction": candidate["direction"],
        "anchor_cell_index": candidate["anchor_cell_index"],
        "anchor_row": candidate["anchor_row"],
        "anchor_col": candidate["anchor_col"],
        "footprint_cell_indices": footprint_indices,
        "footprint_cell_count": len(footprint_indices),
        "footprint_clipped_by_grid_boundary": footprint_clipped_by_grid_boundary,
        "cell_area_m2": _metric_float(cell_area_m2),
        "nonzero_delta_cell_indices": footprint_indices,
    }


def _empty_footprint() -> dict[str, Any]:
    return {
        "model": FOOTPRINT_MODEL,
        "model_scope": "offline_geometric_approximation_not_calibrated_bucket_physics",
        "direction": None,
        "anchor_cell_index": None,
        "anchor_row": None,
        "anchor_col": None,
        "footprint_cell_indices": [],
        "footprint_cell_count": 0,
        "footprint_clipped_by_grid_boundary": None,
        "cell_area_m2": None,
        "nonzero_delta_cell_indices": [],
    }


def _empty_summary_metrics() -> dict[str, Any]:
    return {
        "expected_removed_depth_sum_m": None,
        "expected_removed_volume_m3": None,
        "target_removed_delta_sum_m": None,
        "target_removed_volume_m3": None,
        "outside_target_removed_delta_sum_m": None,
        "outside_target_removed_volume_m3": None,
        "overdig_depth_delta_sum_m": None,
        "overdig_volume_delta_m3": None,
    }


def _parse_grid_shape(
    grid_shape: Sequence[Any],
    cell_count: int,
) -> tuple[int, int] | None:
    if len(grid_shape) != 2:
        return None
    row_count = _parse_positive_integer(grid_shape[0])
    col_count = _parse_positive_integer(grid_shape[1])
    if row_count is None or col_count is None or row_count * col_count != cell_count:
        return None
    return row_count, col_count


def _parse_depth_grid(values: Sequence[Any]) -> list[float] | None:
    parsed_values: list[float] = []
    for value in values:
        parsed = _parse_nonnegative_float(value)
        if parsed is None:
            return None
        parsed_values.append(parsed)
    return parsed_values


def _parse_mask(values: Sequence[Any]) -> list[bool] | None:
    parsed_values: list[bool] = []
    for value in values:
        if isinstance(value, bool):
            parsed_values.append(value)
            continue
        parsed = _parse_finite_float(value)
        if parsed is None:
            return None
        parsed_values.append(parsed > 0.5)
    return parsed_values


def _parse_positive_integer(value: Any) -> int | None:
    parsed = _parse_integer(value)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def _parse_integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    parsed = _parse_finite_float(value)
    if parsed is None or not parsed.is_integer():
        return None
    return int(parsed)


def _parse_positive_float(value: Any) -> float | None:
    parsed = _parse_finite_float(value)
    if parsed is None or parsed <= 0.0:
        return None
    return _metric_float(parsed)


def _parse_nonnegative_float(value: Any) -> float | None:
    parsed = _parse_finite_float(value)
    if parsed is None or parsed < 0.0:
        return None
    return _metric_float(parsed)


def _parse_finite_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _metric_float(value: float) -> float:
    rounded = round(float(value), 12)
    return 0.0 if rounded == -0.0 else rounded


def _provenance_fields(geometry_inputs: dict[str, Any]) -> dict[str, str]:
    return {
        "cell_size_status": (
            "explicit" if geometry_inputs.get("cell_size_m") is not None else "missing"
        ),
        "bucket_geometry_status": (
            "explicit"
            if geometry_inputs.get("bucket_width_m") is not None
            and geometry_inputs.get("bucket_length_m") is not None
            else "missing"
        ),
        "penetration_depth_status": str(
            geometry_inputs.get("penetration_depth_source") or "missing"
        ),
        "calibrated_bucket_physics_status": "missing",
        "capability_model_status": "missing",
        "payload_model_status": "missing",
        "official_geometry_default_status": "not_used",
    }


__all__ = ["build_geometric_swept_footprint_effect"]
