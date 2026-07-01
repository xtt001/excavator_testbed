"""Offline heuristic score evidence for terrain cut candidates."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


SCHEMA = "terrain_candidate_heuristic_scores_v1"
SOURCE = "explicit_candidate_heuristic_score_evidence"
DEFAULT_PROFILE = "explicit_candidate_heuristic_score_evidence"
REQUIRED_WEIGHT_KEYS = (
    "candidate_depth_reward",
    "target_footprint_cell_reward",
    "outside_target_footprint_cell_penalty",
    "outside_protected_boundary_cell_penalty",
    "depth_budget_exceeded_penalty",
    "grid_boundary_clipped_penalty",
    "return_alignment_distance_penalty",
)


def build_candidate_heuristic_scores(
    *,
    evidence_records: Sequence[Any],
    weights: Mapping[str, Any],
    profile: str = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Compute deterministic offline heuristic score evidence for candidates."""

    parsed_weights, weight_errors = _parse_weights(weights)
    if weight_errors:
        return _score_result(
            status="invalid_weights",
            profile=profile,
            score_records=[],
            ranking=_empty_ranking(),
            score_summary=_empty_score_summary(),
            validation_errors=weight_errors,
        )

    if not evidence_records:
        return _score_result(
            status="no_evidence_records",
            profile=profile,
            score_records=[],
            ranking=_empty_ranking(),
            score_summary=_empty_score_summary(),
            validation_errors=[],
        )

    parsed_records, evidence_errors = _parse_evidence_records(evidence_records)
    if evidence_errors:
        return _score_result(
            status="invalid_evidence_records",
            profile=profile,
            score_records=[],
            ranking=_empty_ranking(),
            score_summary=_empty_score_summary(),
            validation_errors=evidence_errors,
        )

    score_records = [
        _score_record(
            record=record,
            weights=parsed_weights,
        )
        for record in parsed_records
    ]
    ranking = _ranking(score_records)
    return _score_result(
        status="present",
        profile=profile,
        score_records=score_records,
        ranking=ranking,
        score_summary=_score_summary(score_records),
        validation_errors=[],
    )


def _score_record(
    *,
    record: dict[str, Any],
    weights: dict[str, float],
) -> dict[str, Any]:
    components = _score_components(record=record, weights=weights)
    total_score = _metric_float(
        math.fsum(component["value"] for component in components.values())
    )
    return {
        "candidate_id": record["candidate_id"],
        "input_index": record["input_index"],
        "offline_only": True,
        "total_score": total_score,
        "score_components": components,
    }


def _score_components(
    *,
    record: dict[str, Any],
    weights: dict[str, float],
) -> dict[str, dict[str, Any]]:
    target_cell_count = len(record["target_footprint_cell_indices"])
    outside_target_cell_count = len(record["outside_target_footprint_cell_indices"])
    outside_protected_cell_count = len(
        record["outside_protected_boundary_cell_indices"]
    )
    depth_budget_exceeded = record["depth_budget_status"] == "exceeds_budget"
    clipped_by_grid_boundary = record["clipped_by_grid_boundary"] is True
    return_alignment_component = _return_alignment_component(
        record["return_alignment_cost_proxy"],
        weight=weights["return_alignment_distance_penalty"],
    )
    return {
        "candidate_depth_reward": {
            "status": "present",
            "value": _metric_float(
                record["candidate_depth_m"] * weights["candidate_depth_reward"]
            ),
            "weight": weights["candidate_depth_reward"],
            "candidate_depth_m": record["candidate_depth_m"],
        },
        "target_footprint_cell_reward": {
            "status": "present",
            "value": _metric_float(
                target_cell_count * weights["target_footprint_cell_reward"]
            ),
            "weight": weights["target_footprint_cell_reward"],
            "cell_count": target_cell_count,
        },
        "outside_target_footprint_cell_penalty": {
            "status": "present",
            "value": _metric_float(
                -outside_target_cell_count
                * weights["outside_target_footprint_cell_penalty"]
            ),
            "weight": weights["outside_target_footprint_cell_penalty"],
            "cell_count": outside_target_cell_count,
        },
        "outside_protected_boundary_cell_penalty": {
            "status": "present",
            "value": _metric_float(
                -outside_protected_cell_count
                * weights["outside_protected_boundary_cell_penalty"]
            ),
            "weight": weights["outside_protected_boundary_cell_penalty"],
            "cell_count": outside_protected_cell_count,
        },
        "depth_budget_exceeded_penalty": {
            "status": "applied" if depth_budget_exceeded else "not_applied",
            "value": (
                _metric_float(-weights["depth_budget_exceeded_penalty"])
                if depth_budget_exceeded
                else 0.0
            ),
            "weight": weights["depth_budget_exceeded_penalty"],
            "depth_budget_status": record["depth_budget_status"],
        },
        "grid_boundary_clipped_penalty": {
            "status": "applied" if clipped_by_grid_boundary else "not_applied",
            "value": (
                _metric_float(-weights["grid_boundary_clipped_penalty"])
                if clipped_by_grid_boundary
                else 0.0
            ),
            "weight": weights["grid_boundary_clipped_penalty"],
            "clipped_by_grid_boundary": clipped_by_grid_boundary,
        },
        "return_alignment_distance_penalty": return_alignment_component,
    }


def _return_alignment_component(
    return_alignment_cost_proxy: dict[str, Any],
    *,
    weight: float,
) -> dict[str, Any]:
    status = return_alignment_cost_proxy["status"]
    if status != "present":
        return {
            "status": "not_evaluated",
            "value": 0.0,
            "weight": weight,
            "reason": str(
                return_alignment_cost_proxy.get(
                    "reason",
                    "return_alignment_proxy_not_present",
                )
            ),
        }
    distance = return_alignment_cost_proxy["manhattan_distance_cells"]
    return {
        "status": "present",
        "value": _metric_float(-distance * weight),
        "weight": weight,
        "manhattan_distance_cells": distance,
    }


def _ranking(score_records: list[dict[str, Any]]) -> dict[str, Any]:
    ranked_records = sorted(
        score_records,
        key=lambda record: (-record["total_score"], record["input_index"]),
    )
    ranked_candidates = [
        {
            "rank": index + 1,
            "candidate_id": record["candidate_id"],
            "total_score": record["total_score"],
            "input_index": record["input_index"],
        }
        for index, record in enumerate(ranked_records)
    ]
    return {
        "semantics": "diagnostic_offline_ranking_only",
        "no_production_action": True,
        "ranked_candidate_ids": [
            str(record["candidate_id"]) for record in ranked_records
        ],
        "ranked_candidates": ranked_candidates,
    }


def _score_summary(score_records: list[dict[str, Any]]) -> dict[str, Any]:
    if not score_records:
        return _empty_score_summary()
    scores = [record["total_score"] for record in score_records]
    ranked_records = sorted(
        score_records,
        key=lambda record: (-record["total_score"], record["input_index"]),
    )
    worst_records = sorted(
        score_records,
        key=lambda record: (record["total_score"], record["input_index"]),
    )
    return {
        "candidate_count": len(score_records),
        "min_score": min(scores),
        "max_score": max(scores),
        "mean_score": _metric_float(math.fsum(scores) / len(scores)),
        "best_candidate_id": ranked_records[0]["candidate_id"],
        "best_score": ranked_records[0]["total_score"],
        "worst_candidate_id": worst_records[0]["candidate_id"],
        "worst_score": worst_records[0]["total_score"],
    }


def _parse_weights(
    weights: Mapping[str, Any],
) -> tuple[dict[str, float], list[str]]:
    if not isinstance(weights, Mapping):
        return {}, ["weights must be a mapping"]
    parsed_weights: dict[str, float] = {}
    validation_errors: list[str] = []
    for key in REQUIRED_WEIGHT_KEYS:
        if key not in weights:
            validation_errors.append(f"weights missing required key: {key}")
            continue
        parsed = _parse_finite_float(weights[key])
        if parsed is None:
            validation_errors.append(f"weights.{key} must be a finite number")
            continue
        parsed_weights[key] = _metric_float(parsed)
    return parsed_weights, validation_errors


def _parse_evidence_records(
    evidence_records: Sequence[Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    parsed_records: list[dict[str, Any]] = []
    validation_errors: list[str] = []
    required_fields = {
        "candidate_id",
        "candidate_depth_m",
        "offline_only",
        "target_footprint_cell_indices",
        "outside_target_footprint_cell_indices",
        "outside_protected_boundary_cell_indices",
        "depth_budget_status",
        "clipped_by_grid_boundary",
        "return_alignment_cost_proxy",
    }
    for index, record in enumerate(evidence_records):
        if not isinstance(record, Mapping):
            validation_errors.append(f"evidence_records[{index}] must be a mapping")
            continue
        missing_fields = sorted(required_fields - set(record.keys()))
        if missing_fields:
            validation_errors.append(
                f"evidence_records[{index}] missing required fields: {', '.join(missing_fields)}"
            )
            continue

        candidate_id = str(record["candidate_id"])
        candidate_depth = _parse_nonnegative_float(record["candidate_depth_m"])
        target_cells = _parse_cell_indices(record["target_footprint_cell_indices"])
        outside_target_cells = _parse_cell_indices(
            record["outside_target_footprint_cell_indices"]
        )
        outside_protected_cells = _parse_cell_indices(
            record["outside_protected_boundary_cell_indices"]
        )
        depth_budget_status = str(record["depth_budget_status"])
        clipped_by_grid_boundary = record["clipped_by_grid_boundary"]
        return_alignment = _parse_return_alignment_proxy(
            record["return_alignment_cost_proxy"]
        )
        if (
            not candidate_id
            or candidate_depth is None
            or record["offline_only"] is not True
            or target_cells is None
            or outside_target_cells is None
            or outside_protected_cells is None
            or depth_budget_status not in {"within_budget", "exceeds_budget"}
            or not isinstance(clipped_by_grid_boundary, bool)
            or return_alignment is None
        ):
            validation_errors.append(
                f"evidence_records[{index}] has invalid score evidence fields"
            )
            continue

        parsed_records.append(
            {
                "candidate_id": candidate_id,
                "input_index": index,
                "candidate_depth_m": candidate_depth,
                "target_footprint_cell_indices": target_cells,
                "outside_target_footprint_cell_indices": outside_target_cells,
                "outside_protected_boundary_cell_indices": outside_protected_cells,
                "depth_budget_status": depth_budget_status,
                "clipped_by_grid_boundary": clipped_by_grid_boundary,
                "return_alignment_cost_proxy": return_alignment,
            }
        )
    return parsed_records, validation_errors


def _parse_return_alignment_proxy(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    status = str(value.get("status"))
    if status == "present":
        distance = _parse_nonnegative_integer(value.get("manhattan_distance_cells"))
        if distance is None:
            return None
        return {
            "status": "present",
            "manhattan_distance_cells": distance,
        }
    if status == "not_evaluated":
        return {
            "status": "not_evaluated",
            "reason": str(value.get("reason", "return_alignment_proxy_not_present")),
        }
    return None


def _parse_cell_indices(value: Any) -> list[int] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    parsed_indices: list[int] = []
    for item in value:
        parsed = _parse_nonnegative_integer(item)
        if parsed is None:
            return None
        parsed_indices.append(parsed)
    return parsed_indices


def _score_result(
    *,
    status: str,
    profile: str,
    score_records: list[dict[str, Any]],
    ranking: dict[str, Any],
    score_summary: dict[str, Any],
    validation_errors: list[str],
) -> dict[str, Any]:
    return {
        "status": status,
        "schema": SCHEMA,
        "source": SOURCE,
        "offline_only": True,
        "profile": str(profile),
        "candidate_count": len(score_records),
        "score_records": score_records,
        "ranking": ranking,
        "score_summary": score_summary,
        "validation_errors": validation_errors,
        "missing_provenance": _missing_provenance_fields(),
    }


def _empty_ranking() -> dict[str, Any]:
    return {
        "semantics": "diagnostic_offline_ranking_only",
        "no_production_action": True,
        "ranked_candidate_ids": [],
        "ranked_candidates": [],
    }


def _empty_score_summary() -> dict[str, Any]:
    return {
        "candidate_count": 0,
        "min_score": None,
        "max_score": None,
        "mean_score": None,
        "best_candidate_id": None,
        "best_score": None,
        "worst_candidate_id": None,
        "worst_score": None,
    }


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


def _missing_provenance_fields() -> dict[str, str]:
    return {
        "calibrated_effect_model_status": "missing",
        "payload_model_status": "missing",
        "physical_bucket_footprint_status": "missing",
        "cell_size_status": "missing",
        "official_weight_status": "missing",
    }


__all__ = ["build_candidate_heuristic_scores"]
