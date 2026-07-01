"""Offline effect-summary and payload-proxy evidence for terrain candidates."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


SCHEMA = "terrain_candidate_effect_summary_v1"
SOURCE = "explicit_candidate_effect_summary"
DEFAULT_PROFILE = "explicit_candidate_effect_summary"
EFFECT_SOURCE = "explicit_geometric_swept_footprint_effect"


def build_candidate_effect_summary(
    effect_records: Sequence[Any],
    *,
    payload_capacity_m3: Any,
    profile: str = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Summarize offline effect records with explicit payload-capacity evidence."""

    parsed_capacity = _parse_positive_float(payload_capacity_m3)
    if parsed_capacity is None:
        return _summary_result(
            status="invalid_payload_capacity",
            profile=profile,
            payload_capacity_m3=None,
            summary_records=[],
            aggregate_summary=_empty_aggregate_summary(),
            diagnostic_rankings=_empty_diagnostic_rankings(),
            validation_errors=[
                "payload_capacity_m3 must be a finite positive number",
            ],
        )

    if not _is_sequence(effect_records):
        return _summary_result(
            status="invalid_effect_records",
            profile=profile,
            payload_capacity_m3=parsed_capacity,
            summary_records=[],
            aggregate_summary=_empty_aggregate_summary(),
            diagnostic_rankings=_empty_diagnostic_rankings(),
            validation_errors=["effect_records must be a sequence of mappings"],
        )

    if not effect_records:
        return _summary_result(
            status="no_effect_records",
            profile=profile,
            payload_capacity_m3=parsed_capacity,
            summary_records=[],
            aggregate_summary=_empty_aggregate_summary(),
            diagnostic_rankings=_empty_diagnostic_rankings(),
            validation_errors=[],
        )

    parsed_records, validation_errors = _parse_effect_records(effect_records)
    if validation_errors:
        return _summary_result(
            status="invalid_effect_records",
            profile=profile,
            payload_capacity_m3=parsed_capacity,
            summary_records=[],
            aggregate_summary=_empty_aggregate_summary(),
            diagnostic_rankings=_empty_diagnostic_rankings(),
            validation_errors=validation_errors,
        )

    summary_records = [
        _summary_record(record=record, payload_capacity_m3=parsed_capacity)
        for record in parsed_records
    ]
    return _summary_result(
        status="present",
        profile=profile,
        payload_capacity_m3=parsed_capacity,
        summary_records=summary_records,
        aggregate_summary=_aggregate_summary(summary_records),
        diagnostic_rankings=_diagnostic_rankings(summary_records),
        validation_errors=[],
    )


def _parse_effect_records(
    effect_records: Sequence[Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    parsed_records: list[dict[str, Any]] = []
    validation_errors: list[str] = []
    required_fields = {
        "status",
        "source",
        "offline_only",
        "candidate_id",
        "footprint",
        "summary_metrics",
    }
    for index, record in enumerate(effect_records):
        if not isinstance(record, Mapping):
            validation_errors.append(f"effect_records[{index}] must be a mapping")
            continue
        missing_fields = sorted(required_fields - set(record.keys()))
        if missing_fields:
            validation_errors.append(
                f"effect_records[{index}] missing required fields: {', '.join(missing_fields)}"
            )
            continue

        candidate_id = str(record["candidate_id"])
        effect_status = str(record["status"])
        footprint = record["footprint"]
        summary_metrics = record["summary_metrics"]
        if (
            not candidate_id
            or effect_status != "present"
            or record["source"] != EFFECT_SOURCE
            or record["offline_only"] is not True
            or not isinstance(footprint, Mapping)
            or not isinstance(summary_metrics, Mapping)
        ):
            validation_errors.append(
                f"effect_records[{index}] has invalid effect summary fields"
            )
            continue

        footprint_cell_count = _parse_nonnegative_integer(
            footprint.get("footprint_cell_count")
        )
        clipped = footprint.get("footprint_clipped_by_grid_boundary")
        expected_volume = _parse_nonnegative_float(
            summary_metrics.get("expected_removed_volume_m3")
        )
        target_volume = _parse_nonnegative_float(
            summary_metrics.get("target_removed_volume_m3")
        )
        outside_target_volume = _parse_nonnegative_float(
            summary_metrics.get("outside_target_removed_volume_m3")
        )
        overdig_volume = _parse_nonnegative_float(
            summary_metrics.get("overdig_volume_delta_m3")
        )
        if (
            footprint_cell_count is None
            or not isinstance(clipped, bool)
            or expected_volume is None
            or target_volume is None
            or outside_target_volume is None
            or overdig_volume is None
        ):
            validation_errors.append(
                f"effect_records[{index}] has invalid volume or footprint fields"
            )
            continue

        parsed_records.append(
            {
                "candidate_id": candidate_id,
                "input_index": index,
                "effect_status": effect_status,
                "expected_removed_volume_m3": expected_volume,
                "target_removed_volume_m3": target_volume,
                "outside_target_removed_volume_m3": outside_target_volume,
                "overdig_volume_delta_m3": overdig_volume,
                "footprint_cell_count": footprint_cell_count,
                "footprint_clipped_by_grid_boundary": clipped,
            }
        )
    return parsed_records, validation_errors


def _summary_record(
    *,
    record: dict[str, Any],
    payload_capacity_m3: float,
) -> dict[str, Any]:
    expected_volume = record["expected_removed_volume_m3"]
    payload_proxy_volume = min(expected_volume, payload_capacity_m3)
    return {
        "candidate_id": record["candidate_id"],
        "input_index": record["input_index"],
        "effect_status": record["effect_status"],
        "offline_only": True,
        "expected_removed_volume_m3": expected_volume,
        "target_removed_volume_m3": record["target_removed_volume_m3"],
        "outside_target_removed_volume_m3": record[
            "outside_target_removed_volume_m3"
        ],
        "overdig_volume_delta_m3": record["overdig_volume_delta_m3"],
        "footprint_cell_count": record["footprint_cell_count"],
        "footprint_clipped_by_grid_boundary": record[
            "footprint_clipped_by_grid_boundary"
        ],
        "payload_proxy_volume_m3": _metric_float(payload_proxy_volume),
        "payload_proxy_fraction": _metric_float(
            payload_proxy_volume / payload_capacity_m3
        ),
        "outside_target_volume_fraction": _volume_fraction(
            record["outside_target_removed_volume_m3"],
            expected_volume,
        ),
        "overdig_volume_fraction": _volume_fraction(
            record["overdig_volume_delta_m3"],
            expected_volume,
        ),
    }


def _aggregate_summary(summary_records: list[dict[str, Any]]) -> dict[str, Any]:
    if not summary_records:
        return _empty_aggregate_summary()

    payload_volumes = [record["payload_proxy_volume_m3"] for record in summary_records]
    payload_fractions = [record["payload_proxy_fraction"] for record in summary_records]
    ranked_payload = _rank_records(
        summary_records,
        key="payload_proxy_volume_m3",
    )
    ranked_outside = _rank_records(
        summary_records,
        key="outside_target_removed_volume_m3",
    )
    ranked_overdig = _rank_records(
        summary_records,
        key="overdig_volume_delta_m3",
    )
    return {
        "effect_record_count": len(summary_records),
        "payload_proxy_volume_min_m3": min(payload_volumes),
        "payload_proxy_volume_max_m3": max(payload_volumes),
        "payload_proxy_volume_mean_m3": _metric_float(
            math.fsum(payload_volumes) / len(payload_volumes)
        ),
        "payload_proxy_fraction_min": min(payload_fractions),
        "payload_proxy_fraction_max": max(payload_fractions),
        "payload_proxy_fraction_mean": _metric_float(
            math.fsum(payload_fractions) / len(payload_fractions)
        ),
        "expected_removed_volume_total_m3": _metric_sum(
            record["expected_removed_volume_m3"] for record in summary_records
        ),
        "target_removed_volume_total_m3": _metric_sum(
            record["target_removed_volume_m3"] for record in summary_records
        ),
        "outside_target_removed_volume_total_m3": _metric_sum(
            record["outside_target_removed_volume_m3"] for record in summary_records
        ),
        "overdig_volume_delta_total_m3": _metric_sum(
            record["overdig_volume_delta_m3"] for record in summary_records
        ),
        "max_payload_proxy_candidate_id": ranked_payload[0]["candidate_id"],
        "max_outside_target_volume_candidate_id": ranked_outside[0]["candidate_id"],
        "max_overdig_volume_candidate_id": ranked_overdig[0]["candidate_id"],
    }


def _diagnostic_rankings(
    summary_records: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "semantics": "diagnostic_offline_ranking_only",
        "no_production_action": True,
        "payload_proxy_desc": _ranking_items(
            _rank_records(summary_records, key="payload_proxy_volume_m3"),
            value_key="payload_proxy_volume_m3",
        ),
        "outside_target_volume_desc": _ranking_items(
            _rank_records(summary_records, key="outside_target_removed_volume_m3"),
            value_key="outside_target_removed_volume_m3",
        ),
        "overdig_volume_desc": _ranking_items(
            _rank_records(summary_records, key="overdig_volume_delta_m3"),
            value_key="overdig_volume_delta_m3",
        ),
    }


def _rank_records(
    summary_records: list[dict[str, Any]],
    *,
    key: str,
) -> list[dict[str, Any]]:
    return sorted(
        summary_records,
        key=lambda record: (-record[key], record["input_index"]),
    )


def _ranking_items(
    ranked_records: list[dict[str, Any]],
    *,
    value_key: str,
) -> list[dict[str, Any]]:
    return [
        {
            "rank": index + 1,
            "candidate_id": record["candidate_id"],
            "input_index": record["input_index"],
            value_key: record[value_key],
        }
        for index, record in enumerate(ranked_records)
    ]


def _summary_result(
    *,
    status: str,
    profile: str,
    payload_capacity_m3: float | None,
    summary_records: list[dict[str, Any]],
    aggregate_summary: dict[str, Any],
    diagnostic_rankings: dict[str, Any],
    validation_errors: list[str],
) -> dict[str, Any]:
    return {
        "status": status,
        "schema": SCHEMA,
        "source": SOURCE,
        "offline_only": True,
        "profile": str(profile),
        "effect_record_count": len(summary_records),
        "payload_capacity_m3": payload_capacity_m3,
        "summary_records": summary_records,
        "aggregate_summary": aggregate_summary,
        "diagnostic_rankings": diagnostic_rankings,
        "validation_errors": validation_errors,
        "missing_provenance": _missing_provenance_fields(),
    }


def _empty_aggregate_summary() -> dict[str, Any]:
    return {
        "effect_record_count": 0,
        "payload_proxy_volume_min_m3": None,
        "payload_proxy_volume_max_m3": None,
        "payload_proxy_volume_mean_m3": None,
        "payload_proxy_fraction_min": None,
        "payload_proxy_fraction_max": None,
        "payload_proxy_fraction_mean": None,
        "expected_removed_volume_total_m3": 0.0,
        "target_removed_volume_total_m3": 0.0,
        "outside_target_removed_volume_total_m3": 0.0,
        "overdig_volume_delta_total_m3": 0.0,
        "max_payload_proxy_candidate_id": None,
        "max_outside_target_volume_candidate_id": None,
        "max_overdig_volume_candidate_id": None,
    }


def _empty_diagnostic_rankings() -> dict[str, Any]:
    return {
        "semantics": "diagnostic_offline_ranking_only",
        "no_production_action": True,
        "payload_proxy_desc": [],
        "outside_target_volume_desc": [],
        "overdig_volume_desc": [],
    }


def _volume_fraction(numerator: float, denominator: float) -> float | None:
    if denominator <= 0.0:
        return None
    return _metric_float(numerator / denominator)


def _metric_sum(values: Any) -> float:
    return _metric_float(math.fsum(values))


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


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


def _parse_nonnegative_integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    parsed = _parse_finite_float(value)
    if parsed is None or parsed < 0.0 or not parsed.is_integer():
        return None
    return int(parsed)


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
        "calibrated_payload_model_status": "missing",
        "material_density_status": "missing",
        "cycle_time_status": "missing",
        "bucket_fill_model_status": "missing",
        "production_integration_status": "not_integrated",
    }


__all__ = ["build_candidate_effect_summary"]
