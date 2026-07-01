"""Offline discrete terrain cut-candidate generation for eval diagnostics."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any


SCHEMA = "terrain_discrete_cut_candidates_v1"
SOURCE = "explicit_target_residual_discrete_candidate_generation"
DEFAULT_PROFILE = "explicit_target_residual_discrete_candidates"


def build_discrete_cut_candidates(
    *,
    residual_depth_grid_m: Sequence[Any],
    target_region_mask: Sequence[Any],
    valid_mask: Sequence[Any],
    grid_shape: Sequence[Any],
    direction_options: Sequence[Any],
    depth_fraction_options: Sequence[Any],
    min_candidate_count: Any,
    max_candidate_count: Any,
    profile: str = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Generate deterministic offline cut candidates from positive residual cells."""

    lengths = {
        len(residual_depth_grid_m),
        len(target_region_mask),
        len(valid_mask),
    }
    if len(lengths) != 1 or not lengths or next(iter(lengths)) == 0:
        return _candidate_result(
            status="invalid_grid_lengths",
            profile=profile,
            grid_shape=None,
            positive_residual_cell_indices=[],
            candidates=[],
            untruncated_candidate_count=0,
            validation_errors=[
                "residual_depth_grid_m, target_region_mask, and valid_mask must have matching non-empty lengths",
            ],
        )

    cell_count = next(iter(lengths))
    parsed_grid_shape = _parse_grid_shape(grid_shape, cell_count)
    if parsed_grid_shape is None:
        return _candidate_result(
            status="invalid_grid_shape",
            profile=profile,
            grid_shape=None,
            positive_residual_cell_indices=[],
            candidates=[],
            untruncated_candidate_count=0,
            validation_errors=[
                "grid_shape must contain two positive integers whose product matches the grid length",
            ],
        )

    residual_depth = _parse_residual_depths(residual_depth_grid_m)
    if residual_depth is None:
        return _candidate_result(
            status="invalid_residual_values",
            profile=profile,
            grid_shape=[parsed_grid_shape[0], parsed_grid_shape[1]],
            positive_residual_cell_indices=[],
            candidates=[],
            untruncated_candidate_count=0,
            validation_errors=[
                "residual_depth_grid_m values must be finite numbers",
            ],
        )

    target_mask = _parse_mask(target_region_mask)
    valid_cells = _parse_mask(valid_mask)
    if target_mask is None or valid_cells is None:
        return _candidate_result(
            status="invalid_mask_values",
            profile=profile,
            grid_shape=[parsed_grid_shape[0], parsed_grid_shape[1]],
            positive_residual_cell_indices=[],
            candidates=[],
            untruncated_candidate_count=0,
            validation_errors=[
                "target_region_mask and valid_mask values must be finite numbers",
            ],
        )

    parsed_options, option_errors = _parse_candidate_options(
        direction_options=direction_options,
        depth_fraction_options=depth_fraction_options,
        min_candidate_count=min_candidate_count,
        max_candidate_count=max_candidate_count,
    )
    if option_errors:
        return _candidate_result(
            status="invalid_candidate_options",
            profile=profile,
            grid_shape=[parsed_grid_shape[0], parsed_grid_shape[1]],
            positive_residual_cell_indices=[],
            candidates=[],
            untruncated_candidate_count=0,
            validation_errors=option_errors,
        )

    positive_residual_cell_indices = [
        index
        for index, (residual, is_target, is_valid) in enumerate(
            zip(residual_depth, target_mask, valid_cells, strict=True)
        )
        if is_valid and is_target and residual > 0.0
    ]
    if not positive_residual_cell_indices:
        return _candidate_result(
            status="no_positive_residual_cells",
            profile=profile,
            grid_shape=[parsed_grid_shape[0], parsed_grid_shape[1]],
            positive_residual_cell_indices=[],
            candidates=[],
            untruncated_candidate_count=0,
            validation_errors=[],
        )

    all_candidates = _build_candidates(
        positive_residual_cell_indices=positive_residual_cell_indices,
        residual_depth=residual_depth,
        grid_shape=parsed_grid_shape,
        direction_options=parsed_options["direction_options"],
        depth_fraction_options=parsed_options["depth_fraction_options"],
    )
    untruncated_candidate_count = len(all_candidates)
    max_candidate_count_value = parsed_options["max_candidate_count"]
    candidates = all_candidates[:max_candidate_count_value]
    if untruncated_candidate_count > max_candidate_count_value:
        status = "candidate_count_above_max"
    elif len(candidates) < parsed_options["min_candidate_count"]:
        status = "candidate_count_below_min"
    else:
        status = "present"

    return _candidate_result(
        status=status,
        profile=profile,
        grid_shape=[parsed_grid_shape[0], parsed_grid_shape[1]],
        positive_residual_cell_indices=positive_residual_cell_indices,
        candidates=candidates,
        untruncated_candidate_count=untruncated_candidate_count,
        validation_errors=[],
    )


def _build_candidates(
    *,
    positive_residual_cell_indices: list[int],
    residual_depth: list[float],
    grid_shape: tuple[int, int],
    direction_options: list[str],
    depth_fraction_options: list[float],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    _, col_count = grid_shape
    for anchor_index in positive_residual_cell_indices:
        anchor_residual = residual_depth[anchor_index]
        for direction in direction_options:
            for depth_fraction in depth_fraction_options:
                candidate_depth = _metric_float(anchor_residual * depth_fraction)
                candidates.append(
                    {
                        "candidate_id": f"cut_candidate_{len(candidates) + 1:06d}",
                        "anchor_cell_index": int(anchor_index),
                        "anchor_row": int(anchor_index // col_count),
                        "anchor_col": int(anchor_index % col_count),
                        "direction": direction,
                        "depth_fraction": depth_fraction,
                        "anchor_positive_residual_depth_m": anchor_residual,
                        "candidate_depth_m": candidate_depth,
                        "offline_only": True,
                    }
                )
    return candidates


def _candidate_result(
    *,
    status: str,
    profile: str,
    grid_shape: list[int] | None,
    positive_residual_cell_indices: list[int],
    candidates: list[dict[str, Any]],
    untruncated_candidate_count: int,
    validation_errors: list[str],
) -> dict[str, Any]:
    covered_cell_indices = sorted(
        {int(candidate["anchor_cell_index"]) for candidate in candidates}
    )
    uncovered_cell_indices = [
        index
        for index in positive_residual_cell_indices
        if index not in set(covered_cell_indices)
    ]
    return {
        "status": status,
        "schema": SCHEMA,
        "source": SOURCE,
        "offline_only": True,
        "profile": str(profile),
        "grid_shape": grid_shape,
        "positive_residual_cell_count": int(len(positive_residual_cell_indices)),
        "candidate_count": int(len(candidates)),
        "untruncated_candidate_count": int(untruncated_candidate_count),
        "candidates": candidates,
        "positive_residual_coverage": {
            "status": _coverage_status(
                status,
                positive_residual_cell_indices,
                uncovered_cell_indices,
            ),
            "positive_residual_cell_indices": positive_residual_cell_indices,
            "covered_cell_indices": covered_cell_indices,
            "uncovered_cell_indices": uncovered_cell_indices,
            "covered_cell_count": int(len(covered_cell_indices)),
            "uncovered_cell_count": int(len(uncovered_cell_indices)),
        },
        "validation_errors": validation_errors,
        **_missing_provenance_fields(),
    }


def _coverage_status(
    status: str,
    positive_residual_cell_indices: list[int],
    uncovered_cell_indices: list[int],
) -> str:
    if not positive_residual_cell_indices:
        return "no_positive_residual_cells"
    if status == "candidate_count_above_max" and uncovered_cell_indices:
        return "truncated"
    return "present"


def _parse_grid_shape(
    grid_shape: Sequence[Any],
    cell_count: int,
) -> tuple[int, int] | None:
    if len(grid_shape) != 2:
        return None
    parsed_shape: list[int] = []
    for value in grid_shape:
        parsed_value = _parse_integer(value)
        if parsed_value is None or parsed_value <= 0:
            return None
        parsed_shape.append(parsed_value)
    if parsed_shape[0] * parsed_shape[1] != cell_count:
        return None
    return parsed_shape[0], parsed_shape[1]


def _parse_residual_depths(values: Sequence[Any]) -> list[float] | None:
    parsed_values: list[float] = []
    for value in values:
        parsed = _parse_finite_float(value)
        if parsed is None:
            return None
        parsed_values.append(_metric_float(parsed))
    return parsed_values


def _parse_mask(values: Sequence[Any]) -> list[bool] | None:
    parsed_values: list[bool] = []
    for value in values:
        parsed = _parse_finite_float(value)
        if parsed is None:
            return None
        parsed_values.append(bool(parsed))
    return parsed_values


def _parse_candidate_options(
    *,
    direction_options: Sequence[Any],
    depth_fraction_options: Sequence[Any],
    min_candidate_count: Any,
    max_candidate_count: Any,
) -> tuple[dict[str, Any], list[str]]:
    validation_errors: list[str] = []
    parsed_directions = [
        str(direction)
        for direction in direction_options
        if str(direction).strip()
    ]
    if not parsed_directions:
        validation_errors.append(
            "direction_options must contain at least one non-empty string"
        )

    parsed_depth_fractions: list[float] = []
    for value in depth_fraction_options:
        parsed = _parse_finite_float(value)
        if parsed is None or parsed <= 0.0 or parsed > 1.0:
            parsed_depth_fractions = []
            validation_errors.append(
                "depth_fraction_options values must be finite and greater than 0.0 and at most 1.0"
            )
            break
        parsed_depth_fractions.append(_metric_float(parsed))
    if not depth_fraction_options:
        validation_errors.append(
            "depth_fraction_options values must be finite and greater than 0.0 and at most 1.0"
        )

    parsed_min = _parse_integer(min_candidate_count)
    parsed_max = _parse_integer(max_candidate_count)
    if (
        parsed_min is None
        or parsed_max is None
        or parsed_min < 0
        or parsed_max < 0
        or parsed_min > parsed_max
    ):
        validation_errors.append(
            "min_candidate_count and max_candidate_count must be nonnegative integers with min <= max"
        )
        parsed_min = 0
        parsed_max = 0

    return (
        {
            "direction_options": parsed_directions,
            "depth_fraction_options": parsed_depth_fractions,
            "min_candidate_count": parsed_min,
            "max_candidate_count": parsed_max,
        },
        validation_errors,
    )


def _parse_integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or not parsed.is_integer():
        return None
    return int(parsed)


def _parse_finite_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _metric_float(value: float) -> float:
    return round(float(value), 12)


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


__all__ = ["build_discrete_cut_candidates"]
