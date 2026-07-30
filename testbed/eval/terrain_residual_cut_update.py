"""Eval-only predicted residual update evidence for terrain cut intents."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from testbed.eval.terrain_target_metrics import build_target_residual_metrics

SCHEMA = "terrain_residual_predicted_cut_update_v1"
SOURCE = "explicit_predicted_residual_cut_update"
DEFAULT_PROFILE = "phase6e_predicted_residual_cut_update"
METRIC_SOURCE = "testbed.eval.terrain_target_metrics.build_target_residual_metrics"
TARGET_METRIC_KEYS = (
    "target_positive_residual_depth_sum_m",
    "target_overdig_depth_sum_m",
    "outside_target_removed_depth_sum_m",
    "target_removed_completion_ratio",
)


def build_predicted_residual_update(
    *,
    cut_intent: Mapping[str, Any],
    effect_record: Mapping[str, Any],
    removed_depth_grid_m: Sequence[Any],
    target_depth_grid_m: Sequence[Any],
    target_region_mask: Sequence[Any],
    valid_mask: Sequence[Any],
    grid_shape: Sequence[Any],
    cell_size_m: Any = None,
    profile: str = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Apply one explicit effect delta and recompute target residual metrics."""

    parsed_cut_intent, cut_errors = _parse_cut_intent(cut_intent)
    if cut_errors:
        return _update_result(
            status="invalid_cut_intent",
            profile=profile,
            cut_intent_candidate_id=None,
            before_metrics=_empty_metrics(),
            after_metrics=_empty_metrics(),
            delta_summary={},
            predicted_removed_depth_grid_m=[],
            effect_provenance={},
            validation_errors=cut_errors,
            cell_size_status=_cell_size_status(cell_size_m),
        )

    parsed_effect, effect_errors = _parse_effect_record(effect_record)
    if effect_errors:
        return _update_result(
            status="invalid_effect_record",
            profile=profile,
            cut_intent_candidate_id=parsed_cut_intent["candidate_id"],
            before_metrics=_empty_metrics(),
            after_metrics=_empty_metrics(),
            delta_summary={},
            predicted_removed_depth_grid_m=[],
            effect_provenance={},
            validation_errors=effect_errors,
            cell_size_status=_cell_size_status(cell_size_m),
        )

    if parsed_effect["candidate_id"] != parsed_cut_intent["candidate_id"]:
        return _update_result(
            status="candidate_effect_mismatch",
            profile=profile,
            cut_intent_candidate_id=parsed_cut_intent["candidate_id"],
            before_metrics=_empty_metrics(),
            after_metrics=_empty_metrics(),
            delta_summary={},
            predicted_removed_depth_grid_m=[],
            effect_provenance=_effect_provenance(parsed_effect),
            validation_errors=[
                "cut_intent candidate id must match effect_record candidate id",
            ],
            cell_size_status=_cell_size_status(cell_size_m),
        )

    length_status, cell_count = _grid_length_status(
        removed_depth_grid_m,
        target_depth_grid_m,
        target_region_mask,
        valid_mask,
        parsed_effect["expected_delta_depth_grid_m"],
    )
    if length_status != "present":
        return _update_result(
            status="invalid_grid_lengths",
            profile=profile,
            cut_intent_candidate_id=parsed_cut_intent["candidate_id"],
            before_metrics=_empty_metrics(),
            after_metrics=_empty_metrics(),
            delta_summary={},
            predicted_removed_depth_grid_m=[],
            effect_provenance=_effect_provenance(parsed_effect),
            validation_errors=[
                "removed_depth_grid_m, target_depth_grid_m, target_region_mask, valid_mask, and expected_delta_depth_grid_m must have matching non-empty lengths",
            ],
            cell_size_status=_cell_size_status(cell_size_m),
        )

    parsed_grid_shape = _parse_grid_shape(grid_shape, cell_count)
    if parsed_grid_shape is None:
        return _update_result(
            status="invalid_grid_shape",
            profile=profile,
            cut_intent_candidate_id=parsed_cut_intent["candidate_id"],
            before_metrics=_empty_metrics(),
            after_metrics=_empty_metrics(),
            delta_summary={},
            predicted_removed_depth_grid_m=[],
            effect_provenance=_effect_provenance(parsed_effect),
            validation_errors=[
                "grid_shape must contain two positive integers whose product matches grid length",
            ],
            cell_size_status=_cell_size_status(cell_size_m),
        )

    removed_depth = _parse_nonnegative_depths(removed_depth_grid_m)
    target_depth = _parse_nonnegative_depths(target_depth_grid_m)
    expected_delta = _parse_nonnegative_depths(
        parsed_effect["expected_delta_depth_grid_m"]
    )
    if removed_depth is None or target_depth is None or expected_delta is None:
        return _update_result(
            status="invalid_depth_values",
            profile=profile,
            cut_intent_candidate_id=parsed_cut_intent["candidate_id"],
            before_metrics=_empty_metrics(),
            after_metrics=_empty_metrics(),
            delta_summary={},
            predicted_removed_depth_grid_m=[],
            effect_provenance=_effect_provenance(parsed_effect),
            validation_errors=[
                "removed, target, and expected delta depth values must be finite and nonnegative",
            ],
            cell_size_status=_cell_size_status(cell_size_m),
        )

    if _parse_mask(target_region_mask) is None or _parse_mask(valid_mask) is None:
        return _update_result(
            status="invalid_mask_values",
            profile=profile,
            cut_intent_candidate_id=parsed_cut_intent["candidate_id"],
            before_metrics=_empty_metrics(),
            after_metrics=_empty_metrics(),
            delta_summary={},
            predicted_removed_depth_grid_m=[],
            effect_provenance=_effect_provenance(parsed_effect),
            validation_errors=[
                "target_region_mask and valid_mask values must be finite booleans or numbers",
            ],
            cell_size_status=_cell_size_status(cell_size_m),
        )

    parsed_cell_size, cell_size_errors = _parse_optional_cell_size(cell_size_m)
    if cell_size_errors:
        return _update_result(
            status="invalid_cell_size",
            profile=profile,
            cut_intent_candidate_id=parsed_cut_intent["candidate_id"],
            before_metrics=_empty_metrics(),
            after_metrics=_empty_metrics(),
            delta_summary={},
            predicted_removed_depth_grid_m=[],
            effect_provenance=_effect_provenance(parsed_effect),
            validation_errors=cell_size_errors,
            cell_size_status="invalid",
        )

    predicted_removed_depth = [
        _metric_float(removed + delta)
        for removed, delta in zip(removed_depth, expected_delta, strict=True)
    ]
    before_metrics = build_target_residual_metrics(
        removed_depth_grid_m=removed_depth,
        target_depth_grid_m=target_depth,
        target_region_mask=target_region_mask,
        valid_mask=valid_mask,
        grid_shape=[parsed_grid_shape[0], parsed_grid_shape[1]],
        cell_size_m=parsed_cell_size,
    )
    after_metrics = build_target_residual_metrics(
        removed_depth_grid_m=predicted_removed_depth,
        target_depth_grid_m=target_depth,
        target_region_mask=target_region_mask,
        valid_mask=valid_mask,
        grid_shape=[parsed_grid_shape[0], parsed_grid_shape[1]],
        cell_size_m=parsed_cell_size,
    )
    if before_metrics["status"] != "present" or after_metrics["status"] != "present":
        return _update_result(
            status="invalid_metric_inputs",
            profile=profile,
            cut_intent_candidate_id=parsed_cut_intent["candidate_id"],
            before_metrics=before_metrics,
            after_metrics=after_metrics,
            delta_summary={},
            predicted_removed_depth_grid_m=predicted_removed_depth,
            effect_provenance=_effect_provenance(parsed_effect),
            validation_errors=[
                "before and after target residual metrics must both be present",
            ],
            cell_size_status=_cell_size_status(cell_size_m),
        )

    return _update_result(
        status="present",
        profile=profile,
        cut_intent_candidate_id=parsed_cut_intent["candidate_id"],
        before_metrics=before_metrics,
        after_metrics=after_metrics,
        delta_summary=_delta_summary(
            before_metrics=before_metrics,
            after_metrics=after_metrics,
            expected_delta_depth_grid_m=expected_delta,
            cell_size_m=parsed_cell_size,
        ),
        predicted_removed_depth_grid_m=predicted_removed_depth,
        effect_provenance=_effect_provenance(parsed_effect),
        validation_errors=[],
        cell_size_status=_cell_size_status(cell_size_m),
    )


def _parse_cut_intent(cut_intent: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(cut_intent, Mapping):
        return {}, ["cut_intent must be a mapping"]
    if "cut_intent" in cut_intent:
        if (
            cut_intent.get("status") != "present"
            or cut_intent.get("offline_only") is not True
            or not isinstance(cut_intent.get("cut_intent"), Mapping)
        ):
            return {}, ["cut_intent top-level output must be present and offline-only"]
        record = cut_intent["cut_intent"]
    else:
        record = cut_intent

    candidate_id = str(record.get("candidate_id", ""))
    cut_intent_candidate_id = str(record.get("cut_intent_candidate_id", ""))
    if (
        not candidate_id
        or cut_intent_candidate_id != candidate_id
        or record.get("runner_input_status") != "ready_for_eval_harness"
        or record.get("production_runtime_action") is not False
        or record.get("offline_only") is not True
    ):
        return {}, [
            "cut_intent must be eval-harness ready, offline-only, and not a production runtime action",
        ]
    return {
        "candidate_id": candidate_id,
        "cut_intent_candidate_id": cut_intent_candidate_id,
    }, []


def _parse_effect_record(
    effect_record: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    if (
        not isinstance(effect_record, Mapping)
        or effect_record.get("status") != "present"
        or effect_record.get("offline_only") is not True
    ):
        return {}, ["effect_record must be present and offline-only"]
    candidate_id = str(effect_record.get("candidate_id", ""))
    expected_delta = effect_record.get("expected_delta_depth_grid_m")
    if (
        not candidate_id
        or isinstance(expected_delta, (str, bytes))
        or not isinstance(expected_delta, Sequence)
        or not expected_delta
    ):
        return {}, [
            "effect_record must include candidate_id and expected_delta_depth_grid_m",
        ]
    return {
        "candidate_id": candidate_id,
        "source": str(effect_record.get("source", "")),
        "expected_delta_depth_grid_m": list(expected_delta),
        "summary_metrics": (
            dict(effect_record["summary_metrics"])
            if isinstance(effect_record.get("summary_metrics"), Mapping)
            else {}
        ),
    }, []


def _grid_length_status(*grids: Sequence[Any]) -> tuple[str, int]:
    lengths = {len(grid) for grid in grids}
    if len(lengths) != 1 or not lengths:
        return "invalid_grid_lengths", 0
    cell_count = next(iter(lengths))
    if cell_count <= 0:
        return "invalid_grid_lengths", 0
    return "present", cell_count


def _parse_grid_shape(
    grid_shape: Sequence[Any],
    cell_count: int,
) -> tuple[int, int] | None:
    if isinstance(grid_shape, (str, bytes)) or not isinstance(grid_shape, Sequence):
        return None
    if len(grid_shape) != 2:
        return None
    row_count = _parse_positive_integer(grid_shape[0])
    col_count = _parse_positive_integer(grid_shape[1])
    if row_count is None or col_count is None:
        return None
    if row_count * col_count != cell_count:
        return None
    return row_count, col_count


def _parse_nonnegative_depths(values: Sequence[Any]) -> list[float] | None:
    parsed_values: list[float] = []
    for value in values:
        parsed = _parse_finite_float(value)
        if parsed is None or parsed < 0.0:
            return None
        parsed_values.append(_metric_float(parsed))
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


def _parse_optional_cell_size(value: Any) -> tuple[float | None, list[str]]:
    if value is None:
        return None, []
    parsed = _parse_finite_float(value)
    if parsed is None or parsed <= 0.0:
        return None, ["cell_size_m must be a finite positive number when provided"]
    return _metric_float(parsed), []


def _delta_summary(
    *,
    before_metrics: Mapping[str, Any],
    after_metrics: Mapping[str, Any],
    expected_delta_depth_grid_m: Sequence[float],
    cell_size_m: float | None,
) -> dict[str, Any]:
    summary = {
        "target_positive_residual_depth_delta_m": _metric_delta(
            after_metrics,
            before_metrics,
            "target_positive_residual_depth_sum_m",
        ),
        "target_overdig_depth_delta_m": _metric_delta(
            after_metrics,
            before_metrics,
            "target_overdig_depth_sum_m",
        ),
        "outside_target_removed_depth_delta_m": _metric_delta(
            after_metrics,
            before_metrics,
            "outside_target_removed_depth_sum_m",
        ),
        "target_removed_completion_ratio_delta": _metric_delta(
            after_metrics,
            before_metrics,
            "target_removed_completion_ratio",
        ),
        "expected_delta_depth_sum_m": _metric_sum(expected_delta_depth_grid_m),
    }
    if cell_size_m is not None:
        cell_area = cell_size_m * cell_size_m
        summary.update(
            {
                "expected_delta_volume_m3": _metric_float(
                    summary["expected_delta_depth_sum_m"] * cell_area
                ),
                "target_positive_residual_volume_delta_m3": _metric_float(
                    summary["target_positive_residual_depth_delta_m"] * cell_area
                ),
                "target_overdig_volume_delta_m3": _metric_float(
                    summary["target_overdig_depth_delta_m"] * cell_area
                ),
                "outside_target_removed_volume_delta_m3": _metric_float(
                    summary["outside_target_removed_depth_delta_m"] * cell_area
                ),
            }
        )
    return summary


def _effect_provenance(effect_record: Mapping[str, Any]) -> dict[str, Any]:
    if not effect_record:
        return {}
    summary_metrics = effect_record.get("summary_metrics")
    return {
        "source": effect_record.get("source") or "explicit_effect_record",
        "candidate_id": effect_record.get("candidate_id"),
        "expected_delta_depth_grid_status": "present",
        "summary_metrics_status": (
            "present" if isinstance(summary_metrics, Mapping) else "missing"
        ),
        "expected_removed_depth_sum_m": (
            summary_metrics.get("expected_removed_depth_sum_m")
            if isinstance(summary_metrics, Mapping)
            else None
        ),
        "target_removed_delta_sum_m": (
            summary_metrics.get("target_removed_delta_sum_m")
            if isinstance(summary_metrics, Mapping)
            else None
        ),
        "outside_target_removed_delta_sum_m": (
            summary_metrics.get("outside_target_removed_delta_sum_m")
            if isinstance(summary_metrics, Mapping)
            else None
        ),
        "overdig_depth_delta_sum_m": (
            summary_metrics.get("overdig_depth_delta_sum_m")
            if isinstance(summary_metrics, Mapping)
            else None
        ),
    }


def _metric_delta(
    after_metrics: Mapping[str, Any],
    before_metrics: Mapping[str, Any],
    key: str,
) -> float:
    return _metric_float(float(after_metrics[key]) - float(before_metrics[key]))


def _empty_metrics() -> dict[str, Any]:
    return {
        "status": "not_evaluated",
        **{key: None for key in TARGET_METRIC_KEYS},
    }


def _update_result(
    *,
    status: str,
    profile: str,
    cut_intent_candidate_id: str | None,
    before_metrics: Mapping[str, Any],
    after_metrics: Mapping[str, Any],
    delta_summary: Mapping[str, Any],
    predicted_removed_depth_grid_m: Sequence[float],
    effect_provenance: Mapping[str, Any],
    validation_errors: list[str],
    cell_size_status: str,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "source": SOURCE,
        "status": status,
        "offline_only": True,
        "profile": str(profile),
        "cut_intent_candidate_id": cut_intent_candidate_id,
        "before_metrics": dict(before_metrics),
        "after_metrics": dict(after_metrics),
        "delta_summary": dict(delta_summary),
        "predicted_removed_depth_grid_m": list(predicted_removed_depth_grid_m),
        "effect_provenance": dict(effect_provenance),
        "validation_errors": validation_errors,
        "non_goal_statuses": _non_goal_statuses(),
        "provenance_statuses": _provenance_statuses(cell_size_status),
    }


def _cell_size_status(value: Any) -> str:
    if value is None:
        return "missing"
    parsed = _parse_finite_float(value)
    if parsed is None or parsed <= 0.0:
        return "invalid"
    return "present"


def _parse_positive_integer(value: Any) -> int | None:
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


def _metric_sum(values: Sequence[float]) -> float:
    return _metric_float(math.fsum(float(value) for value in values))


def _metric_float(value: float) -> float:
    rounded = round(float(value), 12)
    return 0.0 if rounded == -0.0 else rounded


def _non_goal_statuses() -> dict[str, str]:
    return {
        "simulation_status": "not_run",
        "run_artifact_status": "not_created",
        "branch_output_file_status": "not_created",
        "production_planner_integration_status": "not_integrated",
        "rollout_review_schema_integration_status": "not_integrated",
        "command_space_control_status": "not_emitted",
        "official_success_semantics_status": "not_defined",
        "official_default_status": "not_defined",
        "official_threshold_status": "not_defined",
        "calibrated_model_fallback_status": "not_invented",
    }


def _provenance_statuses(cell_size_status: str) -> dict[str, str]:
    statuses = {
        "cut_intent_source": "explicit_input",
        "effect_record_source": "explicit_input",
        "grid_source": "explicit_input",
        "metric_source": METRIC_SOURCE,
        "artifact_write_status": "not_written",
        "runner_execution_status": "not_run",
    }
    if cell_size_status != "present":
        statuses["cell_size_status"] = cell_size_status
    return statuses
