"""Offline candidate constraint evidence for terrain eval diagnostics."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


SCHEMA = "terrain_candidate_constraint_evidence_v1"
SOURCE = "explicit_target_candidate_constraint_evidence"
DEFAULT_PROFILE = "explicit_target_candidate_constraint_evidence"
GRID_FOOTPRINT_PROXY = "directional_adjacent_cell_row_major"
DIRECTION_DELTAS = {
    "row_forward": (0, 1),
    "row_reverse": (0, -1),
    "col_forward": (1, 0),
    "col_reverse": (-1, 0),
}


def build_candidate_constraint_evidence(
    *,
    candidates: Sequence[Any],
    target_region_mask: Sequence[Any],
    valid_mask: Sequence[Any],
    grid_shape: Sequence[Any],
    max_candidate_depth_m: Any,
    protected_boundary_cell_radius: Any,
    return_origin_cell_index: Any = None,
    profile: str = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Annotate offline cut candidates with explicit constraint evidence."""

    lengths = {len(target_region_mask), len(valid_mask)}
    if len(lengths) != 1 or not lengths or next(iter(lengths)) == 0:
        return _evidence_result(
            status="invalid_grid_lengths",
            profile=profile,
            grid_shape=None,
            candidate_count=0,
            evidence_records=[],
            constraint_summary=_empty_constraint_summary(),
            validation_errors=[
                "target_region_mask and valid_mask must have matching non-empty lengths",
            ],
        )

    cell_count = next(iter(lengths))
    parsed_grid_shape = _parse_grid_shape(grid_shape, cell_count)
    if parsed_grid_shape is None:
        return _evidence_result(
            status="invalid_grid_shape",
            profile=profile,
            grid_shape=None,
            candidate_count=0,
            evidence_records=[],
            constraint_summary=_empty_constraint_summary(),
            validation_errors=[
                "grid_shape must contain two positive integers whose product matches mask length",
            ],
        )

    target_mask = _parse_mask(target_region_mask)
    valid_cells = _parse_mask(valid_mask)
    if target_mask is None or valid_cells is None:
        return _evidence_result(
            status="invalid_mask_values",
            profile=profile,
            grid_shape=[parsed_grid_shape[0], parsed_grid_shape[1]],
            candidate_count=0,
            evidence_records=[],
            constraint_summary=_empty_constraint_summary(),
            validation_errors=[
                "target_region_mask and valid_mask values must be finite numbers",
            ],
        )

    parsed_depth_budget = _parse_nonnegative_float(max_candidate_depth_m)
    if parsed_depth_budget is None:
        return _evidence_result(
            status="invalid_depth_budget",
            profile=profile,
            grid_shape=[parsed_grid_shape[0], parsed_grid_shape[1]],
            candidate_count=0,
            evidence_records=[],
            constraint_summary=_empty_constraint_summary(),
            validation_errors=[
                "max_candidate_depth_m must be a finite nonnegative number",
            ],
        )

    parsed_boundary_radius = _parse_nonnegative_integer(
        protected_boundary_cell_radius
    )
    if parsed_boundary_radius is None:
        return _evidence_result(
            status="invalid_boundary_radius",
            profile=profile,
            grid_shape=[parsed_grid_shape[0], parsed_grid_shape[1]],
            candidate_count=0,
            evidence_records=[],
            constraint_summary=_empty_constraint_summary(),
            validation_errors=[
                "protected_boundary_cell_radius must be a nonnegative integer",
            ],
        )

    parsed_return_origin = _parse_optional_cell_index(
        return_origin_cell_index,
        cell_count=cell_count,
        valid_cells=valid_cells,
    )
    if parsed_return_origin == "invalid":
        return _evidence_result(
            status="invalid_return_origin",
            profile=profile,
            grid_shape=[parsed_grid_shape[0], parsed_grid_shape[1]],
            candidate_count=0,
            evidence_records=[],
            constraint_summary=_empty_constraint_summary(),
            validation_errors=[
                "return_origin_cell_index must be a valid in-grid cell when provided",
            ],
        )

    if not candidates:
        return _evidence_result(
            status="no_candidates",
            profile=profile,
            grid_shape=[parsed_grid_shape[0], parsed_grid_shape[1]],
            candidate_count=0,
            evidence_records=[],
            constraint_summary=_empty_constraint_summary(
                valid_cell_count=sum(1 for is_valid in valid_cells if is_valid),
            ),
            validation_errors=[],
        )

    parsed_candidates, candidate_errors = _parse_candidates(
        candidates,
        grid_shape=parsed_grid_shape,
        cell_count=cell_count,
    )
    if candidate_errors:
        return _evidence_result(
            status="invalid_candidates",
            profile=profile,
            grid_shape=[parsed_grid_shape[0], parsed_grid_shape[1]],
            candidate_count=0,
            evidence_records=[],
            constraint_summary=_empty_constraint_summary(),
            validation_errors=candidate_errors,
        )

    protected_boundary_indices = _protected_boundary_indices(
        target_mask=target_mask,
        valid_cells=valid_cells,
        grid_shape=parsed_grid_shape,
        cell_radius=parsed_boundary_radius,
    )
    evidence_records = [
        _candidate_evidence_record(
            candidate=candidate,
            target_mask=target_mask,
            valid_cells=valid_cells,
            protected_boundary_indices=protected_boundary_indices,
            grid_shape=parsed_grid_shape,
            max_candidate_depth_m=parsed_depth_budget,
            return_origin_cell_index=(
                parsed_return_origin
                if isinstance(parsed_return_origin, int)
                else None
            ),
        )
        for candidate in parsed_candidates
    ]

    return _evidence_result(
        status="present",
        profile=profile,
        grid_shape=[parsed_grid_shape[0], parsed_grid_shape[1]],
        candidate_count=len(evidence_records),
        evidence_records=evidence_records,
        constraint_summary=_constraint_summary(
            evidence_records=evidence_records,
            protected_boundary_indices=protected_boundary_indices,
            valid_cells=valid_cells,
            protected_boundary_cell_radius=parsed_boundary_radius,
            return_origin_cell_index=(
                parsed_return_origin
                if isinstance(parsed_return_origin, int)
                else None
            ),
        ),
        validation_errors=[],
    )


def _parse_candidates(
    candidates: Sequence[Any],
    *,
    grid_shape: tuple[int, int],
    cell_count: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    parsed_candidates: list[dict[str, Any]] = []
    validation_errors: list[str] = []
    row_count, col_count = grid_shape
    required_fields = {
        "candidate_id",
        "anchor_cell_index",
        "anchor_row",
        "anchor_col",
        "direction",
        "candidate_depth_m",
        "offline_only",
    }

    for position, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            validation_errors.append(f"candidate[{position}] must be a mapping")
            continue
        missing_fields = sorted(required_fields - set(candidate.keys()))
        if missing_fields:
            validation_errors.append(
                f"candidate[{position}] missing required fields: {', '.join(missing_fields)}"
            )
            continue

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
            validation_errors.append(
                f"candidate[{position}] has invalid candidate evidence fields"
            )
            continue

        parsed_candidates.append(
            {
                "candidate_id": candidate_id,
                "anchor_cell_index": anchor_cell_index,
                "anchor_row": anchor_row,
                "anchor_col": anchor_col,
                "direction": direction,
                "candidate_depth_m": candidate_depth,
                "offline_only": True,
            }
        )
    return parsed_candidates, validation_errors


def _candidate_evidence_record(
    *,
    candidate: dict[str, Any],
    target_mask: list[bool],
    valid_cells: list[bool],
    protected_boundary_indices: set[int],
    grid_shape: tuple[int, int],
    max_candidate_depth_m: float,
    return_origin_cell_index: int | None,
) -> dict[str, Any]:
    footprint, clipped_by_grid_boundary, off_grid_neighbor = _grid_footprint(
        anchor_row=candidate["anchor_row"],
        anchor_col=candidate["anchor_col"],
        anchor_cell_index=candidate["anchor_cell_index"],
        direction=candidate["direction"],
        grid_shape=grid_shape,
    )
    target_footprint = [index for index in footprint if target_mask[index]]
    outside_target_footprint = [
        index for index in footprint if not target_mask[index]
    ]
    valid_footprint = [index for index in footprint if valid_cells[index]]
    invalid_footprint = [index for index in footprint if not valid_cells[index]]
    outside_protected = [
        index for index in footprint if index not in protected_boundary_indices
    ]
    candidate_depth = candidate["candidate_depth_m"]

    return {
        "candidate_id": candidate["candidate_id"],
        "anchor_cell_index": candidate["anchor_cell_index"],
        "anchor_row": candidate["anchor_row"],
        "anchor_col": candidate["anchor_col"],
        "direction": candidate["direction"],
        "candidate_depth_m": candidate_depth,
        "offline_only": True,
        "grid_footprint_cell_indices": footprint,
        "clipped_by_grid_boundary": clipped_by_grid_boundary,
        "off_grid_neighbor": off_grid_neighbor,
        "target_footprint_cell_indices": target_footprint,
        "outside_target_footprint_cell_indices": outside_target_footprint,
        "valid_footprint_cell_indices": valid_footprint,
        "invalid_footprint_cell_indices": invalid_footprint,
        "protected_boundary_cell_indices": sorted(protected_boundary_indices),
        "outside_protected_boundary_cell_indices": outside_protected,
        "depth_budget_status": (
            "within_budget"
            if candidate_depth <= max_candidate_depth_m
            else "exceeds_budget"
        ),
        "max_candidate_depth_m": max_candidate_depth_m,
        "return_alignment_cost_proxy": _return_alignment_cost_proxy(
            return_origin_cell_index=return_origin_cell_index,
            anchor_cell_index=candidate["anchor_cell_index"],
            grid_shape=grid_shape,
        ),
    }


def _grid_footprint(
    *,
    anchor_row: int,
    anchor_col: int,
    anchor_cell_index: int,
    direction: str,
    grid_shape: tuple[int, int],
) -> tuple[list[int], bool, dict[str, int] | None]:
    row_count, col_count = grid_shape
    row_delta, col_delta = DIRECTION_DELTAS[direction]
    neighbor_row = anchor_row + row_delta
    neighbor_col = anchor_col + col_delta
    footprint = [anchor_cell_index]
    if 0 <= neighbor_row < row_count and 0 <= neighbor_col < col_count:
        footprint.append(neighbor_row * col_count + neighbor_col)
        return footprint, False, None
    return footprint, True, {"row": neighbor_row, "col": neighbor_col}


def _protected_boundary_indices(
    *,
    target_mask: list[bool],
    valid_cells: list[bool],
    grid_shape: tuple[int, int],
    cell_radius: int,
) -> set[int]:
    row_count, col_count = grid_shape
    protected_indices: set[int] = set()
    for index, is_target in enumerate(target_mask):
        if not is_target:
            continue
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
                    protected_indices.add(neighbor_index)
    return protected_indices


def _return_alignment_cost_proxy(
    *,
    return_origin_cell_index: int | None,
    anchor_cell_index: int,
    grid_shape: tuple[int, int],
) -> dict[str, Any]:
    if return_origin_cell_index is None:
        return {
            "status": "not_evaluated",
            "reason": "return_origin_cell_index_missing",
        }
    _, col_count = grid_shape
    origin_row = return_origin_cell_index // col_count
    origin_col = return_origin_cell_index % col_count
    anchor_row = anchor_cell_index // col_count
    anchor_col = anchor_cell_index % col_count
    return {
        "status": "present",
        "source": "row_major_anchor_manhattan_distance",
        "return_origin_cell_index": return_origin_cell_index,
        "anchor_cell_index": anchor_cell_index,
        "manhattan_distance_cells": (
            abs(origin_row - anchor_row) + abs(origin_col - anchor_col)
        ),
    }


def _constraint_summary(
    *,
    evidence_records: list[dict[str, Any]],
    protected_boundary_indices: set[int],
    valid_cells: list[bool],
    protected_boundary_cell_radius: int,
    return_origin_cell_index: int | None,
) -> dict[str, Any]:
    valid_cell_count = sum(1 for is_valid in valid_cells if is_valid)
    return_distances = [
        record["return_alignment_cost_proxy"]["manhattan_distance_cells"]
        for record in evidence_records
        if record["return_alignment_cost_proxy"]["status"] == "present"
    ]
    return {
        "candidate_count": len(evidence_records),
        "grid_footprint_proxy": GRID_FOOTPRINT_PROXY,
        "protected_boundary_cell_radius": protected_boundary_cell_radius,
        "protected_boundary_cell_count": len(protected_boundary_indices),
        "valid_cell_count": valid_cell_count,
        "protected_boundary_saturation_ratio": (
            _metric_float(len(protected_boundary_indices) / valid_cell_count)
            if valid_cell_count > 0
            else None
        ),
        "depth_budget_exceeded_count": sum(
            1
            for record in evidence_records
            if record["depth_budget_status"] == "exceeds_budget"
        ),
        "clipped_by_grid_boundary_count": sum(
            1
            for record in evidence_records
            if record["clipped_by_grid_boundary"]
        ),
        "outside_target_footprint_candidate_count": sum(
            1
            for record in evidence_records
            if record["outside_target_footprint_cell_indices"]
        ),
        "outside_protected_boundary_candidate_count": sum(
            1
            for record in evidence_records
            if record["outside_protected_boundary_cell_indices"]
        ),
        "return_alignment_cost_proxy_status": (
            "present" if return_origin_cell_index is not None else "not_evaluated"
        ),
        "return_alignment_cost_proxy_min_cells": (
            min(return_distances) if return_distances else None
        ),
        "return_alignment_cost_proxy_max_cells": (
            max(return_distances) if return_distances else None
        ),
    }


def _empty_constraint_summary(
    *,
    valid_cell_count: int = 0,
) -> dict[str, Any]:
    return {
        "candidate_count": 0,
        "grid_footprint_proxy": GRID_FOOTPRINT_PROXY,
        "protected_boundary_cell_radius": None,
        "protected_boundary_cell_count": 0,
        "valid_cell_count": int(valid_cell_count),
        "protected_boundary_saturation_ratio": None,
        "depth_budget_exceeded_count": 0,
        "clipped_by_grid_boundary_count": 0,
        "outside_target_footprint_candidate_count": 0,
        "outside_protected_boundary_candidate_count": 0,
        "return_alignment_cost_proxy_status": "not_evaluated",
        "return_alignment_cost_proxy_min_cells": None,
        "return_alignment_cost_proxy_max_cells": None,
    }


def _evidence_result(
    *,
    status: str,
    profile: str,
    grid_shape: list[int] | None,
    candidate_count: int,
    evidence_records: list[dict[str, Any]],
    constraint_summary: dict[str, Any],
    validation_errors: list[str],
) -> dict[str, Any]:
    return {
        "status": status,
        "schema": SCHEMA,
        "source": SOURCE,
        "offline_only": True,
        "profile": str(profile),
        "grid_shape": grid_shape,
        "candidate_count": int(candidate_count),
        "evidence_records": evidence_records,
        "constraint_summary": constraint_summary,
        "validation_errors": validation_errors,
        "missing_provenance": _missing_provenance_fields(),
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


def _parse_mask(values: Sequence[Any]) -> list[bool] | None:
    parsed_values: list[bool] = []
    for value in values:
        parsed = _parse_finite_float(value)
        if parsed is None:
            return None
        parsed_values.append(parsed > 0.5)
    return parsed_values


def _parse_optional_cell_index(
    value: Any,
    *,
    cell_count: int,
    valid_cells: list[bool],
) -> int | str | None:
    if value is None:
        return None
    parsed = _parse_integer(value)
    if parsed is None or parsed < 0 or parsed >= cell_count or not valid_cells[parsed]:
        return "invalid"
    return parsed


def _parse_positive_integer(value: Any) -> int | None:
    parsed = _parse_integer(value)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def _parse_nonnegative_integer(value: Any) -> int | None:
    parsed = _parse_integer(value)
    if parsed is None or parsed < 0:
        return None
    return parsed


def _parse_integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    parsed = _parse_finite_float(value)
    if parsed is None or not parsed.is_integer():
        return None
    return int(parsed)


def _parse_nonnegative_float(value: Any) -> float | None:
    parsed = _parse_finite_float(value)
    if parsed is None or parsed < 0.0:
        return None
    return _metric_float(parsed)


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
    rounded = round(float(value), 12)
    return 0.0 if rounded == -0.0 else rounded


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


__all__ = ["build_candidate_constraint_evidence"]
