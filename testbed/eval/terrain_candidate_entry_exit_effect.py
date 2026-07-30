"""Offline entry/exit swept-footprint effect evidence for terrain candidates."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

SCHEMA = "terrain_candidate_entry_exit_effect_v1"
SOURCE = "explicit_entry_exit_swept_footprint_effect"
DEFAULT_PROFILE = "explicit_entry_exit_swept_footprint_effect"
PATH_MODEL = "entry_exit_centerline_segment_approximation"
DIRECTION_DELTAS = {
    "row_forward": (0, 1),
    "row_reverse": (0, -1),
    "col_forward": (1, 0),
    "col_reverse": (-1, 0),
}


def build_entry_exit_swept_footprint_effect(
    candidate: Mapping[str, Any],
    *,
    removed_depth_grid_m: Sequence[Any],
    target_depth_grid_m: Sequence[Any],
    target_region_mask: Sequence[Any],
    valid_mask: Sequence[Any],
    grid_shape: Sequence[Any],
    cell_size_m: Any,
    bucket_width_m: Any,
    entry_cell_index: Any,
    exit_cell_index: Any,
    target_penetration_depth_m: Any,
    profile: str = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Estimate an offline entry/exit centerline swept-footprint delta patch."""

    lengths = {
        len(removed_depth_grid_m),
        len(target_depth_grid_m),
        len(target_region_mask),
        len(valid_mask),
    }
    if len(lengths) != 1 or not lengths or next(iter(lengths)) == 0:
        return _result(
            status="invalid_grid_lengths",
            profile=profile,
            candidate_id=None,
            grid_shape=None,
            entry_exit_path=_empty_path(),
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
        return _result(
            status="invalid_grid_shape",
            profile=profile,
            candidate_id=None,
            grid_shape=None,
            entry_exit_path=_empty_path(),
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
        return _result(
            status="invalid_depth_values",
            profile=profile,
            candidate_id=None,
            grid_shape=[parsed_grid_shape[0], parsed_grid_shape[1]],
            entry_exit_path=_empty_path(),
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
        return _result(
            status="invalid_mask_values",
            profile=profile,
            candidate_id=None,
            grid_shape=[parsed_grid_shape[0], parsed_grid_shape[1]],
            entry_exit_path=_empty_path(),
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
        return _result(
            status="invalid_candidate",
            profile=profile,
            candidate_id=None,
            grid_shape=[parsed_grid_shape[0], parsed_grid_shape[1]],
            entry_exit_path=_empty_path(),
            geometry_inputs=_empty_geometry_inputs(),
            footprint=_empty_footprint(),
            expected_delta_depth_grid_m=[],
            summary_metrics=_empty_summary_metrics(),
            validation_errors=candidate_errors,
        )

    geometry, geometry_errors = _parse_geometry(
        cell_size_m=cell_size_m,
        bucket_width_m=bucket_width_m,
        target_penetration_depth_m=target_penetration_depth_m,
    )
    geometry_inputs = _geometry_inputs(geometry)
    if geometry_errors:
        return _result(
            status="invalid_geometry",
            profile=profile,
            candidate_id=parsed_candidate["candidate_id"],
            grid_shape=[parsed_grid_shape[0], parsed_grid_shape[1]],
            entry_exit_path=_empty_path(parsed_candidate["direction"]),
            geometry_inputs=geometry_inputs,
            footprint=_empty_footprint(parsed_candidate),
            expected_delta_depth_grid_m=[],
            summary_metrics=_empty_summary_metrics(),
            validation_errors=geometry_errors,
        )

    entry_exit_path, entry_exit_errors = _parse_entry_exit_path(
        entry_cell_index=entry_cell_index,
        exit_cell_index=exit_cell_index,
        valid_cells=valid_cells,
        grid_shape=parsed_grid_shape,
        cell_count=cell_count,
        cell_size_m=geometry["cell_size_m"],
        candidate_direction=parsed_candidate["direction"],
    )
    if entry_exit_errors:
        return _result(
            status="invalid_entry_exit",
            profile=profile,
            candidate_id=parsed_candidate["candidate_id"],
            grid_shape=[parsed_grid_shape[0], parsed_grid_shape[1]],
            entry_exit_path=entry_exit_path,
            geometry_inputs=geometry_inputs,
            footprint=_empty_footprint(parsed_candidate),
            expected_delta_depth_grid_m=[],
            summary_metrics=_empty_summary_metrics(),
            validation_errors=entry_exit_errors,
        )

    footprint_all_indices = _segment_cell_indices(
        grid_shape=parsed_grid_shape,
        cell_size_m=geometry["cell_size_m"],
        bucket_width_m=geometry["bucket_width_m"],
        entry_exit_path=entry_exit_path,
    )
    footprint_indices = [index for index in footprint_all_indices if valid_cells[index]]
    invalid_footprint_indices = [
        index for index in footprint_all_indices if not valid_cells[index]
    ]
    if not footprint_indices:
        return _result(
            status="no_valid_footprint_cells",
            profile=profile,
            candidate_id=parsed_candidate["candidate_id"],
            grid_shape=[parsed_grid_shape[0], parsed_grid_shape[1]],
            entry_exit_path=entry_exit_path,
            geometry_inputs=geometry_inputs,
            footprint=_footprint_result(
                candidate=parsed_candidate,
                footprint_indices=[],
                invalid_footprint_indices=invalid_footprint_indices,
                target_mask=target_mask,
                valid_cells=valid_cells,
                cell_area_m2=geometry["cell_size_m"] ** 2,
            ),
            expected_delta_depth_grid_m=[0.0 for _ in range(cell_count)],
            summary_metrics=_empty_summary_metrics(),
            validation_errors=[],
        )

    footprint_set = set(footprint_indices)
    expected_delta_depth_grid_m = [
        _metric_float(
            geometry["target_penetration_depth_m"] if index in footprint_set else 0.0
        )
        for index in range(cell_count)
    ]
    summary_metrics = _summary_metrics(
        expected_delta_depth_grid_m=expected_delta_depth_grid_m,
        removed_depth=removed_depth,
        target_depth=target_depth,
        target_mask=target_mask,
        valid_cells=valid_cells,
        cell_area_m2=geometry["cell_size_m"] ** 2,
    )

    return _result(
        status="present",
        profile=profile,
        candidate_id=parsed_candidate["candidate_id"],
        grid_shape=[parsed_grid_shape[0], parsed_grid_shape[1]],
        entry_exit_path=entry_exit_path,
        geometry_inputs=geometry_inputs,
        footprint=_footprint_result(
            candidate=parsed_candidate,
            footprint_indices=footprint_indices,
            invalid_footprint_indices=invalid_footprint_indices,
            target_mask=target_mask,
            valid_cells=valid_cells,
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
    target_penetration_depth_m: Any,
) -> tuple[dict[str, Any], list[str]]:
    parsed_cell_size = _parse_positive_float(cell_size_m)
    parsed_bucket_width = _parse_positive_float(bucket_width_m)
    parsed_penetration = _parse_nonnegative_float(target_penetration_depth_m)
    validation_errors: list[str] = []
    if parsed_cell_size is None:
        validation_errors.append("cell_size_m must be a finite positive number")
    if parsed_bucket_width is None:
        validation_errors.append("bucket_width_m must be a finite positive number")
    if parsed_penetration is None:
        validation_errors.append(
            "target_penetration_depth_m must be a finite nonnegative number"
        )

    return (
        {
            "cell_size_m": parsed_cell_size,
            "bucket_width_m": parsed_bucket_width,
            "target_penetration_depth_m": parsed_penetration,
            "target_penetration_depth_source": (
                "explicit_target_penetration_depth_m"
            ),
        },
        validation_errors,
    )


def _parse_entry_exit_path(
    *,
    entry_cell_index: Any,
    exit_cell_index: Any,
    valid_cells: list[bool],
    grid_shape: tuple[int, int],
    cell_count: int,
    cell_size_m: float,
    candidate_direction: str,
) -> tuple[dict[str, Any], list[str]]:
    row_count, col_count = grid_shape
    entry = _parse_integer(entry_cell_index)
    exit_ = _parse_integer(exit_cell_index)
    errors: list[str] = []
    if entry is None or entry < 0 or entry >= cell_count:
        errors.append("entry_cell_index must be an in-range row-major cell index")
    if exit_ is None or exit_ < 0 or exit_ >= cell_count:
        errors.append("exit_cell_index must be an in-range row-major cell index")
    if not errors and entry == exit_:
        errors.append("entry_cell_index and exit_cell_index must differ")
    if not errors and (not valid_cells[entry] or not valid_cells[exit_]):
        errors.append("entry_cell_index and exit_cell_index must refer to valid cells")
    if errors:
        return _empty_path(candidate_direction), errors

    entry_row = entry // col_count
    entry_col = entry % col_count
    exit_row = exit_ // col_count
    exit_col = exit_ % col_count
    if entry_row >= row_count or exit_row >= row_count:
        return _empty_path(candidate_direction), [
            "entry_cell_index and exit_cell_index must map inside grid_shape"
        ]

    segment_length_m = math.hypot(
        (exit_row - entry_row) * cell_size_m,
        (exit_col - entry_col) * cell_size_m,
    )
    if segment_length_m <= 0.0:
        return _empty_path(candidate_direction), [
            "entry/exit segment length must be positive"
        ]

    return (
        {
            "model": PATH_MODEL,
            "candidate_direction": candidate_direction,
            "entry_cell_index": entry,
            "entry_row": entry_row,
            "entry_col": entry_col,
            "exit_cell_index": exit_,
            "exit_row": exit_row,
            "exit_col": exit_col,
            "segment_length_m": _metric_float(segment_length_m),
        },
        [],
    )


def _segment_cell_indices(
    *,
    grid_shape: tuple[int, int],
    cell_size_m: float,
    bucket_width_m: float,
    entry_exit_path: dict[str, Any],
) -> list[int]:
    _, col_count = grid_shape
    entry_row_m = entry_exit_path["entry_row"] * cell_size_m
    entry_col_m = entry_exit_path["entry_col"] * cell_size_m
    exit_row_m = entry_exit_path["exit_row"] * cell_size_m
    exit_col_m = entry_exit_path["exit_col"] * cell_size_m
    vector_row_m = exit_row_m - entry_row_m
    vector_col_m = exit_col_m - entry_col_m
    length_sq = vector_row_m * vector_row_m + vector_col_m * vector_col_m
    if length_sq <= 0.0:
        return []

    half_width_m = bucket_width_m / 2.0
    footprint_indices: list[int] = []
    for row in range(grid_shape[0]):
        for col in range(grid_shape[1]):
            point_row_m = row * cell_size_m
            point_col_m = col * cell_size_m
            delta_row_m = point_row_m - entry_row_m
            delta_col_m = point_col_m - entry_col_m
            projection = (
                delta_row_m * vector_row_m + delta_col_m * vector_col_m
            ) / length_sq
            if projection < -1e-12 or projection > 1.0 + 1e-12:
                continue
            closest_row_m = entry_row_m + projection * vector_row_m
            closest_col_m = entry_col_m + projection * vector_col_m
            distance_m = math.hypot(
                point_row_m - closest_row_m,
                point_col_m - closest_col_m,
            )
            if distance_m <= half_width_m + 1e-12:
                footprint_indices.append(row * col_count + col)
    return footprint_indices


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


def _result(
    *,
    status: str,
    profile: str,
    candidate_id: str | None,
    grid_shape: list[int] | None,
    entry_exit_path: dict[str, Any],
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
        "entry_exit_path": entry_exit_path,
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
        "target_penetration_depth_m": geometry["target_penetration_depth_m"],
        "target_penetration_depth_source": geometry[
            "target_penetration_depth_source"
        ],
    }


def _empty_geometry_inputs() -> dict[str, Any]:
    return {
        "cell_size_m": None,
        "bucket_width_m": None,
        "target_penetration_depth_m": None,
        "target_penetration_depth_source": None,
    }


def _footprint_result(
    *,
    candidate: dict[str, Any],
    footprint_indices: list[int],
    invalid_footprint_indices: list[int],
    target_mask: list[bool],
    valid_cells: list[bool],
    cell_area_m2: float,
) -> dict[str, Any]:
    return {
        "model": PATH_MODEL,
        "model_scope": (
            "offline_entry_exit_segment_approximation_not_calibrated_bucket_physics"
        ),
        "direction": candidate["direction"],
        "anchor_cell_index": candidate["anchor_cell_index"],
        "anchor_row": candidate["anchor_row"],
        "anchor_col": candidate["anchor_col"],
        "footprint_cell_indices": footprint_indices,
        "footprint_cell_count": len(footprint_indices),
        "target_footprint_cell_indices": [
            index for index in footprint_indices if target_mask[index]
        ],
        "outside_target_footprint_cell_indices": [
            index for index in footprint_indices if not target_mask[index]
        ],
        "valid_footprint_cell_indices": [
            index for index in footprint_indices if valid_cells[index]
        ],
        "invalid_footprint_cell_indices": invalid_footprint_indices,
        "entry_cell_valid": True,
        "exit_cell_valid": True,
        "footprint_clipped_by_grid_boundary": False,
        "clipping_basis": "explicit_entry_exit_segment_only",
        "cell_area_m2": _metric_float(cell_area_m2),
        "nonzero_delta_cell_indices": footprint_indices,
    }


def _empty_footprint(candidate: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "model": PATH_MODEL,
        "model_scope": (
            "offline_entry_exit_segment_approximation_not_calibrated_bucket_physics"
        ),
        "direction": candidate["direction"] if candidate else None,
        "anchor_cell_index": candidate["anchor_cell_index"] if candidate else None,
        "anchor_row": candidate["anchor_row"] if candidate else None,
        "anchor_col": candidate["anchor_col"] if candidate else None,
        "footprint_cell_indices": [],
        "footprint_cell_count": 0,
        "target_footprint_cell_indices": [],
        "outside_target_footprint_cell_indices": [],
        "valid_footprint_cell_indices": [],
        "invalid_footprint_cell_indices": [],
        "entry_cell_valid": None,
        "exit_cell_valid": None,
        "footprint_clipped_by_grid_boundary": None,
        "clipping_basis": "explicit_entry_exit_segment_only",
        "cell_area_m2": None,
        "nonzero_delta_cell_indices": [],
    }


def _empty_path(candidate_direction: str | None = None) -> dict[str, Any]:
    return {
        "model": PATH_MODEL,
        "candidate_direction": candidate_direction,
        "entry_cell_index": None,
        "entry_row": None,
        "entry_col": None,
        "exit_cell_index": None,
        "exit_row": None,
        "exit_col": None,
        "segment_length_m": None,
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
        "bucket_width_status": (
            "explicit"
            if geometry_inputs.get("bucket_width_m") is not None
            else "missing"
        ),
        "target_penetration_depth_status": str(
            geometry_inputs.get("target_penetration_depth_source") or "missing"
        ),
        "entry_exit_geometry_status": "explicit_input_required",
        "calibrated_bucket_physics_status": "missing",
        "capability_model_status": "missing",
        "payload_model_status": "missing",
        "official_geometry_default_status": "not_used",
    }


__all__ = ["build_entry_exit_swept_footprint_effect"]
