"""Eval-only predicted residual rollout evidence for heuristic terrain cuts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from testbed.eval.terrain_candidate_effect_model import (
    build_geometric_swept_footprint_effect,
)
from testbed.eval.terrain_candidate_effect_summary import (
    build_candidate_effect_summary,
)
from testbed.eval.terrain_candidate_evidence import (
    build_candidate_constraint_evidence,
)
from testbed.eval.terrain_candidate_generation import build_discrete_cut_candidates
from testbed.eval.terrain_candidate_scoring import build_candidate_heuristic_scores
from testbed.eval.terrain_residual_cut_intent import (
    build_heuristic_residual_cut_intent,
)
from testbed.eval.terrain_residual_cut_update import build_predicted_residual_update
from testbed.eval.terrain_residual_predicted_rollout_contract import (
    DEFAULT_PROFILE,
    SELECTION_POLICY,
    _aggregate_delta_summary,
    _empty_delta_summary,
    _empty_metrics,
    _invalid_option_result,
    _metric_subset,
    _option_provenance,
    _parse_branch_run_plan,
    _parse_candidate_constraint_options,
    _parse_candidate_generation_options,
    _parse_cycle_budget,
    _parse_effect_geometry,
    _parse_grid_inputs,
    _parse_positive_float,
    _parse_scoring_weights,
    _record_for_candidate,
    _rollout_result,
    _target_metrics,
    _target_positive_residual,
    _target_spec_errors,
)



def build_predicted_residual_rollout(
    *,
    branch_run_plan: Mapping[str, Any],
    initial_removed_depth_grid_m: Sequence[Any],
    target_depth_grid_m: Sequence[Any],
    target_region_mask: Sequence[Any],
    valid_mask: Sequence[Any],
    grid_shape: Sequence[Any],
    target_spec: Mapping[str, Any],
    cycle_budget: Mapping[str, Any],
    candidate_generation_options: Mapping[str, Any],
    candidate_constraint_options: Mapping[str, Any],
    scoring_weights: Mapping[str, Any],
    effect_geometry: Mapping[str, Any],
    payload_capacity_m3: Any,
    selection_policy: Any,
    profile: str = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Run an in-memory predicted B-branch residual rollout for a small budget."""

    parsed_branch, branch_errors = _parse_branch_run_plan(branch_run_plan)
    if branch_errors:
        return _rollout_result(
            status="invalid_branch_run_plan",
            profile=profile,
            step_count=0,
            stop_reason="invalid_branch_run_plan",
            initial_metrics=_empty_metrics(),
            final_metrics=_empty_metrics(),
            per_step_records=[],
            final_grid=[],
            aggregate_delta_summary=_empty_delta_summary(),
            validation_errors=branch_errors,
            option_provenance={},
        )

    parsed_cycle_budget, cycle_errors = _parse_cycle_budget(cycle_budget)
    if cycle_errors:
        return _invalid_option_result(
            status="invalid_cycle_budget",
            profile=profile,
            validation_errors=cycle_errors,
            parsed_branch=parsed_branch,
        )

    parsed_generation, generation_errors = _parse_candidate_generation_options(
        candidate_generation_options
    )
    if generation_errors:
        return _invalid_option_result(
            status="invalid_candidate_generation_options",
            profile=profile,
            validation_errors=generation_errors,
            parsed_branch=parsed_branch,
        )

    parsed_constraints, constraint_errors = _parse_candidate_constraint_options(
        candidate_constraint_options
    )
    if constraint_errors:
        return _invalid_option_result(
            status="invalid_candidate_constraint_options",
            profile=profile,
            validation_errors=constraint_errors,
            parsed_branch=parsed_branch,
        )

    parsed_weights, weight_errors = _parse_scoring_weights(scoring_weights)
    if weight_errors:
        return _invalid_option_result(
            status="invalid_scoring_weights",
            profile=profile,
            validation_errors=weight_errors,
            parsed_branch=parsed_branch,
        )

    parsed_geometry, geometry_errors = _parse_effect_geometry(effect_geometry)
    if geometry_errors:
        return _invalid_option_result(
            status="invalid_effect_geometry",
            profile=profile,
            validation_errors=geometry_errors,
            parsed_branch=parsed_branch,
        )

    parsed_payload_capacity = _parse_positive_float(payload_capacity_m3)
    if parsed_payload_capacity is None:
        return _invalid_option_result(
            status="invalid_payload_capacity",
            profile=profile,
            validation_errors=[
                "payload_capacity_m3 must be a finite positive number",
            ],
            parsed_branch=parsed_branch,
        )

    target_errors = _target_spec_errors(target_spec)
    if target_errors:
        return _invalid_option_result(
            status="invalid_target_spec",
            profile=profile,
            validation_errors=target_errors,
            parsed_branch=parsed_branch,
        )

    if selection_policy != SELECTION_POLICY:
        return _invalid_option_result(
            status="invalid_selection_policy",
            profile=profile,
            validation_errors=["selection_policy must be explicit score_ranking_first"],
            parsed_branch=parsed_branch,
        )

    parsed_grid = _parse_grid_inputs(
        initial_removed_depth_grid_m=initial_removed_depth_grid_m,
        target_depth_grid_m=target_depth_grid_m,
        target_region_mask=target_region_mask,
        valid_mask=valid_mask,
        grid_shape=grid_shape,
    )
    if parsed_grid["status"] != "present":
        return _rollout_result(
            status=parsed_grid["status"],
            profile=profile,
            step_count=0,
            stop_reason=parsed_grid["status"],
            initial_metrics=_empty_metrics(),
            final_metrics=_empty_metrics(),
            per_step_records=[],
            final_grid=[],
            aggregate_delta_summary=_empty_delta_summary(),
            validation_errors=parsed_grid["validation_errors"],
            option_provenance=_option_provenance(
                parsed_branch=parsed_branch,
                parsed_cycle_budget=parsed_cycle_budget,
                parsed_generation=parsed_generation,
                parsed_constraints=parsed_constraints,
                parsed_geometry=parsed_geometry,
                payload_capacity_m3=parsed_payload_capacity,
                selection_policy=selection_policy,
            ),
        )

    current_grid = list(parsed_grid["initial_removed_depth_grid_m"])
    target_depth = list(parsed_grid["target_depth_grid_m"])
    target_mask = list(parsed_grid["target_region_mask"])
    valid_cells = list(parsed_grid["valid_mask"])
    parsed_grid_shape = list(parsed_grid["grid_shape"])

    initial_metrics = _target_metrics(
        removed_depth_grid_m=current_grid,
        target_depth_grid_m=target_depth,
        target_region_mask=target_mask,
        valid_mask=valid_cells,
        grid_shape=parsed_grid_shape,
        cell_size_m=parsed_geometry["cell_size_m"],
    )
    if initial_metrics["status"] != "present":
        return _rollout_result(
            status=str(initial_metrics["status"]),
            profile=profile,
            step_count=0,
            stop_reason=str(initial_metrics["status"]),
            initial_metrics=initial_metrics,
            final_metrics=initial_metrics,
            per_step_records=[],
            final_grid=current_grid,
            aggregate_delta_summary=_empty_delta_summary(),
            validation_errors=list(initial_metrics.get("validation_errors", [])),
            option_provenance=_option_provenance(
                parsed_branch=parsed_branch,
                parsed_cycle_budget=parsed_cycle_budget,
                parsed_generation=parsed_generation,
                parsed_constraints=parsed_constraints,
                parsed_geometry=parsed_geometry,
                payload_capacity_m3=parsed_payload_capacity,
                selection_policy=selection_policy,
            ),
        )
    if _target_positive_residual(initial_metrics) <= 0.0:
        return _rollout_result(
            status="no_positive_residual_cells",
            profile=profile,
            step_count=0,
            stop_reason="no_positive_residual_cells",
            initial_metrics=initial_metrics,
            final_metrics=initial_metrics,
            per_step_records=[],
            final_grid=current_grid,
            aggregate_delta_summary=_aggregate_delta_summary(
                initial_metrics=initial_metrics,
                final_metrics=initial_metrics,
                per_step_records=[],
            ),
            validation_errors=[],
            option_provenance=_option_provenance(
                parsed_branch=parsed_branch,
                parsed_cycle_budget=parsed_cycle_budget,
                parsed_generation=parsed_generation,
                parsed_constraints=parsed_constraints,
                parsed_geometry=parsed_geometry,
                payload_capacity_m3=parsed_payload_capacity,
                selection_policy=selection_policy,
            ),
        )

    per_step_records: list[dict[str, Any]] = []
    final_metrics = initial_metrics
    stop_reason = "max_cycles_reached"
    validation_errors: list[str] = []

    for step_index in range(parsed_cycle_budget["max_cycles"]):
        before_metrics = _target_metrics(
            removed_depth_grid_m=current_grid,
            target_depth_grid_m=target_depth,
            target_region_mask=target_mask,
            valid_mask=valid_cells,
            grid_shape=parsed_grid_shape,
            cell_size_m=parsed_geometry["cell_size_m"],
        )
        if before_metrics["status"] != "present":
            stop_reason = "invalid_metric_inputs"
            validation_errors.extend(before_metrics.get("validation_errors", []))
            break
        if _target_positive_residual(before_metrics) <= 0.0:
            stop_reason = "zero_target_positive_residual"
            final_metrics = before_metrics
            break

        step_result = _build_prediction_step(
            step_index=step_index,
            branch_run_plan=branch_run_plan,
            before_metrics=before_metrics,
            current_grid=current_grid,
            target_depth_grid_m=target_depth,
            target_region_mask=target_mask,
            valid_mask=valid_cells,
            grid_shape=parsed_grid_shape,
            target_spec=target_spec,
            parsed_generation=parsed_generation,
            parsed_constraints=parsed_constraints,
            parsed_weights=parsed_weights,
            parsed_geometry=parsed_geometry,
            payload_capacity_m3=parsed_payload_capacity,
            selection_policy=selection_policy,
        )
        if step_result["status"] != "present":
            stop_reason = "no_valid_candidate_path"
            validation_errors.extend(step_result["validation_errors"])
            break

        step_record = step_result["step_record"]
        per_step_records.append(step_record)
        current_grid = list(step_result["predicted_removed_depth_grid_m"])
        final_metrics = step_record["after_metrics"]
        if _target_positive_residual(final_metrics) <= 0.0:
            stop_reason = "zero_target_positive_residual"
            break

    status = "present" if per_step_records else stop_reason
    return _rollout_result(
        status=status,
        profile=profile,
        step_count=len(per_step_records),
        stop_reason=stop_reason,
        initial_metrics=initial_metrics,
        final_metrics=final_metrics,
        per_step_records=per_step_records,
        final_grid=current_grid,
        aggregate_delta_summary=_aggregate_delta_summary(
            initial_metrics=initial_metrics,
            final_metrics=final_metrics,
            per_step_records=per_step_records,
        ),
        validation_errors=validation_errors,
        option_provenance=_option_provenance(
            parsed_branch=parsed_branch,
            parsed_cycle_budget=parsed_cycle_budget,
            parsed_generation=parsed_generation,
            parsed_constraints=parsed_constraints,
            parsed_geometry=parsed_geometry,
            payload_capacity_m3=parsed_payload_capacity,
            selection_policy=selection_policy,
        ),
    )


def _build_prediction_step(
    *,
    step_index: int,
    branch_run_plan: Mapping[str, Any],
    before_metrics: Mapping[str, Any],
    current_grid: list[float],
    target_depth_grid_m: list[float],
    target_region_mask: list[bool],
    valid_mask: list[bool],
    grid_shape: list[int],
    target_spec: Mapping[str, Any],
    parsed_generation: Mapping[str, Any],
    parsed_constraints: Mapping[str, Any],
    parsed_weights: Mapping[str, float],
    parsed_geometry: Mapping[str, Any],
    payload_capacity_m3: float,
    selection_policy: str,
) -> dict[str, Any]:
    candidate_generation = build_discrete_cut_candidates(
        residual_depth_grid_m=before_metrics["residual_depth_grid_m"],
        target_region_mask=target_region_mask,
        valid_mask=valid_mask,
        grid_shape=grid_shape,
        direction_options=parsed_generation["direction_options"],
        depth_fraction_options=parsed_generation["depth_fraction_options"],
        min_candidate_count=parsed_generation["min_candidate_count"],
        max_candidate_count=parsed_generation["max_candidate_count"],
    )
    candidates = candidate_generation.get("candidates", [])
    if candidate_generation["status"] == "no_positive_residual_cells":
        return _step_failure("no_positive_residual_cells", candidate_generation)
    if not candidates:
        return _step_failure("candidate_generation_no_candidates", candidate_generation)

    candidate_evidence = build_candidate_constraint_evidence(
        candidates=candidates,
        target_region_mask=target_region_mask,
        valid_mask=valid_mask,
        grid_shape=grid_shape,
        max_candidate_depth_m=parsed_constraints["max_candidate_depth_m"],
        protected_boundary_cell_radius=parsed_constraints[
            "protected_boundary_cell_radius"
        ],
        return_origin_cell_index=parsed_constraints["return_origin_cell_index"],
    )
    if candidate_evidence["status"] != "present":
        return _step_failure("candidate_evidence_not_present", candidate_evidence)

    candidate_scoring = build_candidate_heuristic_scores(
        evidence_records=candidate_evidence["evidence_records"],
        weights=parsed_weights,
    )
    if candidate_scoring["status"] != "present":
        return _step_failure("candidate_scoring_not_present", candidate_scoring)

    effect_records = [
        build_geometric_swept_footprint_effect(
            candidate=candidate,
            removed_depth_grid_m=current_grid,
            target_depth_grid_m=target_depth_grid_m,
            target_region_mask=target_region_mask,
            valid_mask=valid_mask,
            grid_shape=grid_shape,
            cell_size_m=parsed_geometry["cell_size_m"],
            bucket_width_m=parsed_geometry["bucket_width_m"],
            bucket_length_m=parsed_geometry["bucket_length_m"],
            penetration_depth_m=parsed_geometry["penetration_depth_m"],
        )
        for candidate in candidates
    ]
    effect_summary = build_candidate_effect_summary(
        effect_records,
        payload_capacity_m3=payload_capacity_m3,
    )
    if effect_summary["status"] != "present":
        return _step_failure("effect_summary_not_present", effect_summary)

    cut_intent = build_heuristic_residual_cut_intent(
        branch_run_plan=branch_run_plan,
        candidate_generation=candidate_generation,
        candidate_evidence=candidate_evidence,
        candidate_scoring=candidate_scoring,
        candidate_effect_summary=effect_summary,
        target_spec=target_spec,
        selection_policy=selection_policy,
    )
    if cut_intent["status"] != "present":
        return _step_failure("cut_intent_not_present", cut_intent)

    candidate_id = cut_intent["cut_intent"]["candidate_id"]
    effect_record = _record_for_candidate(effect_records, candidate_id)
    if effect_record is None:
        return _step_failure(
            "matching_effect_record_missing",
            {"validation_errors": ["matching effect record missing"]},
        )

    predicted_update = build_predicted_residual_update(
        cut_intent=cut_intent,
        effect_record=effect_record,
        removed_depth_grid_m=current_grid,
        target_depth_grid_m=target_depth_grid_m,
        target_region_mask=target_region_mask,
        valid_mask=valid_mask,
        grid_shape=grid_shape,
        cell_size_m=parsed_geometry["cell_size_m"],
    )
    if predicted_update["status"] != "present":
        return _step_failure("predicted_update_not_present", predicted_update)

    step_record = _step_record(
        step_index=step_index,
        candidate_generation=candidate_generation,
        candidate_evidence=candidate_evidence,
        candidate_scoring=candidate_scoring,
        effect_summary=effect_summary,
        effect_record=effect_record,
        cut_intent=cut_intent,
        predicted_update=predicted_update,
    )
    return {
        "status": "present",
        "step_record": step_record,
        "predicted_removed_depth_grid_m": predicted_update[
            "predicted_removed_depth_grid_m"
        ],
        "validation_errors": [],
    }


def _step_record(
    *,
    step_index: int,
    candidate_generation: Mapping[str, Any],
    candidate_evidence: Mapping[str, Any],
    candidate_scoring: Mapping[str, Any],
    effect_summary: Mapping[str, Any],
    effect_record: Mapping[str, Any],
    cut_intent: Mapping[str, Any],
    predicted_update: Mapping[str, Any],
) -> dict[str, Any]:
    delta_summary = predicted_update["delta_summary"]
    record = {
        "step_index": step_index,
        "status": "present",
        "cut_intent_candidate_id": cut_intent["cut_intent"][
            "cut_intent_candidate_id"
        ],
        "candidate_generation_status": candidate_generation["status"],
        "candidate_count": candidate_generation["candidate_count"],
        "candidate_evidence_status": candidate_evidence["status"],
        "candidate_scoring_status": candidate_scoring["status"],
        "effect_record_status": effect_record["status"],
        "effect_summary_status": effect_summary["status"],
        "cut_intent_status": cut_intent["status"],
        "cut_intent": dict(cut_intent["cut_intent"]),
        "predicted_update_status": predicted_update["status"],
        "before_metrics": _metric_subset(predicted_update["before_metrics"]),
        "after_metrics": _metric_subset(predicted_update["after_metrics"]),
        "expected_delta_depth_sum_m": delta_summary["expected_delta_depth_sum_m"],
        "validation_errors": [],
        "provenance_statuses": {
            "candidate_generation_source": candidate_generation["source"],
            "candidate_evidence_source": candidate_evidence["source"],
            "candidate_scoring_source": candidate_scoring["source"],
            "effect_summary_source": effect_summary["source"],
            "effect_record_source": effect_record["source"],
            "cut_intent_source": cut_intent["source"],
            "predicted_update_source": predicted_update["source"],
        },
    }
    if "expected_delta_volume_m3" in delta_summary:
        record["expected_delta_volume_m3"] = delta_summary[
            "expected_delta_volume_m3"
        ]
    return record


def _step_failure(reason: str, evidence: Mapping[str, Any]) -> dict[str, Any]:
    errors = evidence.get("validation_errors", [])
    if (
        isinstance(errors, Sequence)
        and not isinstance(errors, (str, bytes))
    ):
        validation_errors = [reason, *list(errors)]
    else:
        validation_errors = [reason]
    return {
        "status": reason,
        "step_record": {},
        "predicted_removed_depth_grid_m": [],
        "validation_errors": validation_errors,
    }
