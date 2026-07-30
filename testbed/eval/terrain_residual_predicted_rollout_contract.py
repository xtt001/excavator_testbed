"""Input and output contract helpers for predicted residual rollouts."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from testbed.eval.terrain_target_metrics import build_target_residual_metrics

SCHEMA = "terrain_residual_predicted_rollout_v1"
SOURCE = "explicit_predicted_residual_rollout"
DEFAULT_PROFILE = "phase6e_predicted_residual_rollout"
SELECTION_POLICY = "score_ranking_first"
HEURISTIC_BRANCH_NAME = "heuristic_residual_pipeline"
TARGET_METRIC_KEYS = (
    "target_positive_residual_depth_sum_m",
    "target_overdig_depth_sum_m",
    "outside_target_removed_depth_sum_m",
    "target_removed_completion_ratio",
)
TARGET_REQUIRED_FIELDS = (
    "grid_shape",
    "row_start",
    "row_end",
    "col_start",
    "col_end",
    "target_depth_m",
    "official_semantics",
)
WEIGHT_KEYS = (
    "candidate_depth_reward",
    "target_footprint_cell_reward",
    "outside_target_footprint_cell_penalty",
    "outside_protected_boundary_cell_penalty",
    "depth_budget_exceeded_penalty",
    "grid_boundary_clipped_penalty",
    "return_alignment_distance_penalty",
)


def _parse_branch_run_plan(
    branch_run_plan: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    if (
        not isinstance(branch_run_plan, Mapping)
        or branch_run_plan.get("status") != "present"
        or branch_run_plan.get("offline_only") is not True
    ):
        return {}, ["branch_run_plan must be present and offline-only"]
    branch_run_plans = branch_run_plan.get("branch_run_plans")
    if not isinstance(branch_run_plans, Mapping):
        return {}, ["branch_run_plan must include branch_run_plans"]
    heuristic = branch_run_plans.get(HEURISTIC_BRANCH_NAME)
    if not isinstance(heuristic, Mapping):
        return {}, ["branch_run_plan must include heuristic_residual_pipeline"]
    if (
        heuristic.get("status") != "present"
        or heuristic.get("input_readiness_status") != "present"
        or heuristic.get("runtime_integration_status") != "not_integrated"
        or heuristic.get("cut_intent_boundary_status") != "present"
    ):
        return {}, ["heuristic branch must be present but not runtime integrated"]
    return {
        "heuristic_branch_status": "present",
        "runtime_integration_status": "not_integrated",
        "source": str(branch_run_plan.get("source", "explicit_input")),
    }, []


def _parse_cycle_budget(cycle_budget: Mapping[str, Any]) -> tuple[dict[str, int], list[str]]:
    if not isinstance(cycle_budget, Mapping):
        return {}, ["cycle_budget must be a mapping"]
    max_cycles = _parse_positive_integer(cycle_budget.get("max_cycles"))
    if max_cycles is None:
        return {}, ["cycle_budget.max_cycles must be a finite positive integer"]
    return {"max_cycles": max_cycles}, []


def _parse_candidate_generation_options(
    options: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(options, Mapping):
        return {}, ["candidate_generation_options must be a mapping"]
    directions = _string_list(options.get("direction_options"))
    depth_fractions = _positive_fraction_list(options.get("depth_fraction_options"))
    min_count = _parse_nonnegative_integer(options.get("min_candidate_count"))
    max_count = _parse_nonnegative_integer(options.get("max_candidate_count"))
    errors: list[str] = []
    if not directions:
        errors.append("direction_options must contain at least one direction")
    if not depth_fractions:
        errors.append("depth_fraction_options must contain positive values <= 1.0")
    if min_count is None or max_count is None or min_count > max_count:
        errors.append("min/max candidate counts must be nonnegative with min <= max")
    if errors:
        return {}, errors
    return {
        "direction_options": directions,
        "depth_fraction_options": depth_fractions,
        "min_candidate_count": min_count,
        "max_candidate_count": max_count,
    }, []


def _parse_candidate_constraint_options(
    options: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(options, Mapping):
        return {}, ["candidate_constraint_options must be a mapping"]
    max_depth = _parse_nonnegative_float(options.get("max_candidate_depth_m"))
    boundary_radius = _parse_nonnegative_integer(
        options.get("protected_boundary_cell_radius")
    )
    errors: list[str] = []
    if max_depth is None:
        errors.append("max_candidate_depth_m must be finite and nonnegative")
    if boundary_radius is None:
        errors.append("protected_boundary_cell_radius must be a nonnegative integer")
    if errors:
        return {}, errors
    return {
        "max_candidate_depth_m": max_depth,
        "protected_boundary_cell_radius": boundary_radius,
        "return_origin_cell_index": options.get("return_origin_cell_index"),
    }, []


def _parse_scoring_weights(weights: Mapping[str, Any]) -> tuple[dict[str, float], list[str]]:
    if not isinstance(weights, Mapping):
        return {}, ["scoring_weights must be a mapping"]
    parsed: dict[str, float] = {}
    errors: list[str] = []
    for key in WEIGHT_KEYS:
        value = _parse_finite_float(weights.get(key))
        if value is None:
            errors.append(f"scoring_weights.{key} must be a finite number")
        else:
            parsed[key] = _metric_float(value)
    return parsed, errors


def _parse_effect_geometry(
    geometry: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(geometry, Mapping):
        return {}, ["effect_geometry must be a mapping"]
    cell_size = _parse_positive_float(geometry.get("cell_size_m"))
    bucket_width = _parse_positive_float(geometry.get("bucket_width_m"))
    bucket_length = _parse_positive_float(geometry.get("bucket_length_m"))
    penetration_depth = geometry.get("penetration_depth_m")
    if penetration_depth is not None:
        parsed_penetration = _parse_nonnegative_float(penetration_depth)
    else:
        parsed_penetration = None
    errors: list[str] = []
    if cell_size is None:
        errors.append("cell_size_m must be a finite positive number")
    if bucket_width is None:
        errors.append("bucket_width_m must be a finite positive number")
    if bucket_length is None:
        errors.append("bucket_length_m must be a finite positive number")
    if penetration_depth is not None and parsed_penetration is None:
        errors.append("penetration_depth_m must be finite and nonnegative")
    if errors:
        return {}, errors
    return {
        "cell_size_m": cell_size,
        "bucket_width_m": bucket_width,
        "bucket_length_m": bucket_length,
        "penetration_depth_m": parsed_penetration,
    }, []


def _target_spec_errors(target_spec: Mapping[str, Any]) -> list[str]:
    if not isinstance(target_spec, Mapping):
        return ["target_spec must be a mapping"]
    missing = [field for field in TARGET_REQUIRED_FIELDS if field not in target_spec]
    if missing:
        return ["target_spec missing required fields: " + ", ".join(missing)]
    return []


def _parse_grid_inputs(
    *,
    initial_removed_depth_grid_m: Sequence[Any],
    target_depth_grid_m: Sequence[Any],
    target_region_mask: Sequence[Any],
    valid_mask: Sequence[Any],
    grid_shape: Sequence[Any],
) -> dict[str, Any]:
    if not all(
        _is_sequence(value)
        for value in (
            initial_removed_depth_grid_m,
            target_depth_grid_m,
            target_region_mask,
            valid_mask,
        )
    ):
        return _parsed_grid_error(
            "invalid_grid_lengths",
            "grid inputs must be sequences",
        )
    lengths = {
        len(initial_removed_depth_grid_m),
        len(target_depth_grid_m),
        len(target_region_mask),
        len(valid_mask),
    }
    if len(lengths) != 1 or not lengths or next(iter(lengths)) <= 0:
        return _parsed_grid_error(
            "invalid_grid_lengths",
            "grid inputs must have matching non-empty lengths",
        )
    cell_count = next(iter(lengths))
    parsed_grid_shape = _parse_grid_shape(grid_shape, cell_count)
    if parsed_grid_shape is None:
        return _parsed_grid_error(
            "invalid_grid_shape",
            "grid_shape must contain two positive integers matching grid length",
        )
    initial_removed = _parse_nonnegative_depths(initial_removed_depth_grid_m)
    target_depth = _parse_nonnegative_depths(target_depth_grid_m)
    if initial_removed is None or target_depth is None:
        return _parsed_grid_error(
            "invalid_depth_values",
            "removed and target depth values must be finite and nonnegative",
        )
    target_mask = _parse_mask(target_region_mask)
    valid_cells = _parse_mask(valid_mask)
    if target_mask is None or valid_cells is None:
        return _parsed_grid_error(
            "invalid_mask_values",
            "target_region_mask and valid_mask values must be boolean-like",
        )
    return {
        "status": "present",
        "grid_shape": [parsed_grid_shape[0], parsed_grid_shape[1]],
        "initial_removed_depth_grid_m": initial_removed,
        "target_depth_grid_m": target_depth,
        "target_region_mask": target_mask,
        "valid_mask": valid_cells,
        "validation_errors": [],
    }


def _parsed_grid_error(status: str, message: str) -> dict[str, Any]:
    return {"status": status, "validation_errors": [message]}


def _target_metrics(
    *,
    removed_depth_grid_m: Sequence[float],
    target_depth_grid_m: Sequence[float],
    target_region_mask: Sequence[bool],
    valid_mask: Sequence[bool],
    grid_shape: Sequence[int],
    cell_size_m: float,
) -> dict[str, Any]:
    return build_target_residual_metrics(
        removed_depth_grid_m=removed_depth_grid_m,
        target_depth_grid_m=target_depth_grid_m,
        target_region_mask=target_region_mask,
        valid_mask=valid_mask,
        grid_shape=grid_shape,
        cell_size_m=cell_size_m,
    )


def _metric_subset(metrics: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": metrics.get("status"),
        **{key: metrics.get(key) for key in TARGET_METRIC_KEYS},
    }


def _aggregate_delta_summary(
    *,
    initial_metrics: Mapping[str, Any],
    final_metrics: Mapping[str, Any],
    per_step_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    summary = {
        "target_positive_residual_depth_delta_m": _metric_delta(
            final_metrics,
            initial_metrics,
            "target_positive_residual_depth_sum_m",
        ),
        "target_overdig_depth_delta_m": _metric_delta(
            final_metrics,
            initial_metrics,
            "target_overdig_depth_sum_m",
        ),
        "outside_target_removed_depth_delta_m": _metric_delta(
            final_metrics,
            initial_metrics,
            "outside_target_removed_depth_sum_m",
        ),
        "target_removed_completion_ratio_delta": _metric_delta(
            final_metrics,
            initial_metrics,
            "target_removed_completion_ratio",
        ),
        "expected_delta_depth_sum_m": _metric_sum(
            record.get("expected_delta_depth_sum_m", 0.0)
            for record in per_step_records
        ),
    }
    if any("expected_delta_volume_m3" in record for record in per_step_records):
        summary["expected_delta_volume_m3"] = _metric_sum(
            record.get("expected_delta_volume_m3", 0.0)
            for record in per_step_records
        )
    return summary


def _rollout_result(
    *,
    status: str,
    profile: str,
    step_count: int,
    stop_reason: str,
    initial_metrics: Mapping[str, Any],
    final_metrics: Mapping[str, Any],
    per_step_records: Sequence[Mapping[str, Any]],
    final_grid: Sequence[float],
    aggregate_delta_summary: Mapping[str, Any],
    validation_errors: Sequence[str],
    option_provenance: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "source": SOURCE,
        "status": status,
        "offline_only": True,
        "profile": str(profile),
        "step_count": int(step_count),
        "stop_reason": str(stop_reason),
        "initial_metrics": _metric_subset(initial_metrics),
        "final_metrics": _metric_subset(final_metrics),
        "per_step_records": [dict(record) for record in per_step_records],
        "final_predicted_removed_depth_grid_m": list(final_grid),
        "aggregate_delta_summary": dict(aggregate_delta_summary),
        "validation_errors": list(validation_errors),
        "option_provenance": dict(option_provenance),
        "non_goal_statuses": _non_goal_statuses(),
        "provenance_statuses": _provenance_statuses(),
    }


def _invalid_option_result(
    *,
    status: str,
    profile: str,
    validation_errors: Sequence[str],
    parsed_branch: Mapping[str, Any],
) -> dict[str, Any]:
    return _rollout_result(
        status=status,
        profile=profile,
        step_count=0,
        stop_reason=status,
        initial_metrics=_empty_metrics(),
        final_metrics=_empty_metrics(),
        per_step_records=[],
        final_grid=[],
        aggregate_delta_summary=_empty_delta_summary(),
        validation_errors=list(validation_errors),
        option_provenance={"branch_run_plan_status": parsed_branch},
    )


def _option_provenance(
    *,
    parsed_branch: Mapping[str, Any],
    parsed_cycle_budget: Mapping[str, Any],
    parsed_generation: Mapping[str, Any],
    parsed_constraints: Mapping[str, Any],
    parsed_geometry: Mapping[str, Any],
    payload_capacity_m3: float,
    selection_policy: Any,
) -> dict[str, Any]:
    return {
        "branch_run_plan_status": dict(parsed_branch),
        "cycle_budget": dict(parsed_cycle_budget),
        "candidate_generation_options_status": "explicit_input",
        "candidate_generation_options": dict(parsed_generation),
        "candidate_constraint_options_status": "explicit_input",
        "candidate_constraint_options": dict(parsed_constraints),
        "scoring_weights_status": "explicit_input",
        "effect_geometry_status": "explicit_input",
        "effect_geometry": dict(parsed_geometry),
        "payload_capacity_m3": payload_capacity_m3,
        "selection_policy": selection_policy,
    }


def _record_for_candidate(
    records: Sequence[Mapping[str, Any]],
    candidate_id: str,
) -> Mapping[str, Any] | None:
    for record in records:
        if record.get("candidate_id") == candidate_id:
            return record
    return None


def _target_positive_residual(metrics: Mapping[str, Any]) -> float:
    value = metrics.get("target_positive_residual_depth_sum_m")
    parsed = _parse_finite_float(value)
    return parsed if parsed is not None else 0.0


def _metric_delta(
    after_metrics: Mapping[str, Any],
    before_metrics: Mapping[str, Any],
    key: str,
) -> float:
    after = _parse_finite_float(after_metrics.get(key))
    before = _parse_finite_float(before_metrics.get(key))
    if after is None or before is None:
        return 0.0
    return _metric_float(after - before)


def _empty_metrics() -> dict[str, Any]:
    return {
        "status": "not_evaluated",
        **{key: None for key in TARGET_METRIC_KEYS},
    }


def _empty_delta_summary() -> dict[str, Any]:
    return {
        "target_positive_residual_depth_delta_m": 0.0,
        "target_overdig_depth_delta_m": 0.0,
        "outside_target_removed_depth_delta_m": 0.0,
        "target_removed_completion_ratio_delta": 0.0,
        "expected_delta_depth_sum_m": 0.0,
    }


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


def _provenance_statuses() -> dict[str, str]:
    return {
        "branch_run_plan_source": "explicit_input",
        "grid_source": "explicit_input",
        "target_spec_source": "explicit_input",
        "candidate_generation_source": (
            "testbed.eval.terrain_candidate_generation.build_discrete_cut_candidates"
        ),
        "candidate_evidence_source": (
            "testbed.eval.terrain_candidate_evidence."
            "build_candidate_constraint_evidence"
        ),
        "candidate_scoring_source": (
            "testbed.eval.terrain_candidate_scoring."
            "build_candidate_heuristic_scores"
        ),
        "effect_model_source": (
            "testbed.eval.terrain_candidate_effect_model."
            "build_geometric_swept_footprint_effect"
        ),
        "effect_summary_source": (
            "testbed.eval.terrain_candidate_effect_summary."
            "build_candidate_effect_summary"
        ),
        "cut_intent_source": (
            "testbed.eval.terrain_residual_cut_intent."
            "build_heuristic_residual_cut_intent"
        ),
        "predicted_update_source": (
            "testbed.eval.terrain_residual_cut_update."
            "build_predicted_residual_update"
        ),
        "artifact_write_status": "not_written",
        "runner_execution_status": "not_run",
    }


def _parse_grid_shape(
    grid_shape: Sequence[Any],
    cell_count: int,
) -> tuple[int, int] | None:
    if not _is_sequence(grid_shape) or len(grid_shape) != 2:
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


def _string_list(value: Any) -> list[str]:
    if not _is_sequence(value):
        return []
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            return []
        normalized.append(item)
    return normalized


def _positive_fraction_list(value: Any) -> list[float]:
    if not _is_sequence(value):
        return []
    parsed_values: list[float] = []
    for item in value:
        parsed = _parse_finite_float(item)
        if parsed is None or parsed <= 0.0 or parsed > 1.0:
            return []
        parsed_values.append(_metric_float(parsed))
    return parsed_values


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


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


def _metric_sum(values: Any) -> float:
    return _metric_float(math.fsum(float(value) for value in values))


def _metric_float(value: float) -> float:
    rounded = round(float(value), 12)
    return 0.0 if rounded == -0.0 else rounded
