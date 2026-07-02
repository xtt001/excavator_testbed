from __future__ import annotations

import json

from testbed.eval.terrain_residual_predicted_rollout import (
    build_predicted_residual_rollout,
)


def _branch_run_plan(**overrides):
    plan = {
        "status": "present",
        "schema": "terrain_residual_closed_loop_branch_run_plan_v1",
        "source": "explicit_closed_loop_branch_run_plan",
        "offline_only": True,
        "branch_order": [
            "current_planner_baseline",
            "heuristic_residual_pipeline",
            "calibrated_residual_pipeline",
        ],
        "branch_run_plans": {
            "current_planner_baseline": {
                "status": "present",
                "run_status": "not_run",
            },
            "heuristic_residual_pipeline": {
                "status": "present",
                "input_readiness_status": "present",
                "runtime_integration_status": "not_integrated",
                "cut_intent_boundary_status": "present",
                "run_status": "not_run",
            },
            "calibrated_residual_pipeline": {
                "status": "not_evaluated",
                "reason": "blocked_by_missing_gold_samples",
                "calibration_available": False,
                "run_status": "not_run",
            },
        },
        "executable_cut_intent_boundary": {
            "status": "present",
            "semantics": "future_runner_contract_only",
        },
    }
    plan.update(overrides)
    return plan


def _target_spec():
    return {
        "target_id": "unit_test_target",
        "grid_shape": [2, 2],
        "row_start": 0,
        "row_end": 2,
        "col_start": 0,
        "col_end": 1,
        "target_depth_m": 0.2,
        "official_semantics": "non_official_explicit_unit_test_spec",
    }


def _rollout_kwargs(**overrides):
    kwargs = {
        "branch_run_plan": _branch_run_plan(),
        "initial_removed_depth_grid_m": [0.0, 0.0, 0.0, 0.0],
        "target_depth_grid_m": [0.2, 0.0, 0.2, 0.0],
        "target_region_mask": [True, False, True, False],
        "valid_mask": [True, True, True, True],
        "grid_shape": [2, 2],
        "target_spec": _target_spec(),
        "cycle_budget": {"max_cycles": 3},
        "candidate_generation_options": {
            "direction_options": ["col_forward"],
            "depth_fraction_options": [1.0],
            "min_candidate_count": 1,
            "max_candidate_count": 10,
        },
        "candidate_constraint_options": {
            "max_candidate_depth_m": 0.2,
            "protected_boundary_cell_radius": 0,
            "return_origin_cell_index": 0,
        },
        "scoring_weights": {
            "candidate_depth_reward": 10.0,
            "target_footprint_cell_reward": 1.0,
            "outside_target_footprint_cell_penalty": 2.0,
            "outside_protected_boundary_cell_penalty": 4.0,
            "depth_budget_exceeded_penalty": 5.0,
            "grid_boundary_clipped_penalty": 0.5,
            "return_alignment_distance_penalty": 0.25,
        },
        "effect_geometry": {
            "cell_size_m": 0.5,
            "bucket_width_m": 0.5,
            "bucket_length_m": 0.5,
            "penetration_depth_m": None,
        },
        "payload_capacity_m3": 0.2,
        "selection_policy": "score_ranking_first",
    }
    kwargs.update(overrides)
    return kwargs


def _build_rollout(**overrides):
    return build_predicted_residual_rollout(**_rollout_kwargs(**overrides))


def _all_keys(value):
    if isinstance(value, dict):
        for key, nested_value in value.items():
            yield key
            yield from _all_keys(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            yield from _all_keys(nested_value)


def test_predicted_rollout_iterates_until_target_residual_is_zero():
    result = _build_rollout()

    assert result["status"] == "present"
    assert result["schema"] == "terrain_residual_predicted_rollout_v1"
    assert result["source"] == "explicit_predicted_residual_rollout"
    assert result["offline_only"] is True
    assert result["step_count"] == 1
    assert result["stop_reason"] == "zero_target_positive_residual"
    assert result["initial_metrics"]["target_positive_residual_depth_sum_m"] == 0.4
    assert result["final_metrics"]["target_positive_residual_depth_sum_m"] == 0.0
    assert result["final_predicted_removed_depth_grid_m"] == [0.2, 0.0, 0.2, 0.0]
    assert result["aggregate_delta_summary"] == {
        "target_positive_residual_depth_delta_m": -0.4,
        "target_overdig_depth_delta_m": 0.0,
        "outside_target_removed_depth_delta_m": 0.0,
        "target_removed_completion_ratio_delta": 1.0,
        "expected_delta_depth_sum_m": 0.4,
        "expected_delta_volume_m3": 0.1,
    }

    step = result["per_step_records"][0]
    assert step["step_index"] == 0
    assert step["status"] == "present"
    assert step["cut_intent_candidate_id"] == "cut_candidate_000001"
    assert step["before_metrics"]["target_positive_residual_depth_sum_m"] == 0.4
    assert step["after_metrics"]["target_positive_residual_depth_sum_m"] == 0.0
    assert step["expected_delta_depth_sum_m"] == 0.4
    assert step["expected_delta_volume_m3"] == 0.1
    assert step["candidate_generation_status"] == "present"
    assert step["candidate_scoring_status"] == "present"
    assert step["cut_intent_status"] == "present"
    assert step["predicted_update_status"] == "present"
    assert result["validation_errors"] == []

    all_keys = set(_all_keys(result))
    assert "runtime_action" not in all_keys
    assert "pass_fail" not in all_keys
    assert "eval_success" not in all_keys
    assert "planner_success" not in all_keys
    assert "calibrated_fallback" not in all_keys
    serialized = json.dumps(result, sort_keys=True)
    assert "cut_candidate_000001" in serialized
    assert "zero_target_positive_residual" in serialized


def test_predicted_rollout_can_run_multiple_prediction_steps():
    result = _build_rollout(
        target_depth_grid_m=[0.2, 0.0, 0.0, 0.2],
        target_region_mask=[True, False, False, True],
        candidate_generation_options={
            "direction_options": ["row_forward"],
            "depth_fraction_options": [1.0],
            "min_candidate_count": 1,
            "max_candidate_count": 10,
        },
    )

    assert result["status"] == "present"
    assert result["step_count"] == 2
    assert result["stop_reason"] == "zero_target_positive_residual"
    assert [
        record["cut_intent_candidate_id"] for record in result["per_step_records"]
    ] == ["cut_candidate_000002", "cut_candidate_000001"]
    assert result["initial_metrics"]["target_positive_residual_depth_sum_m"] == 0.4
    assert result["final_metrics"]["target_positive_residual_depth_sum_m"] == 0.0
    assert result["final_predicted_removed_depth_grid_m"] == [0.2, 0.2, 0.0, 0.2]
    assert result["aggregate_delta_summary"]["expected_delta_depth_sum_m"] == 0.6
    assert result["aggregate_delta_summary"]["expected_delta_volume_m3"] == 0.15


def test_predicted_rollout_reports_no_positive_residual_without_steps():
    result = _build_rollout(
        initial_removed_depth_grid_m=[0.2, 0.0, 0.2, 0.0],
    )

    assert result["status"] == "no_positive_residual_cells"
    assert result["step_count"] == 0
    assert result["stop_reason"] == "no_positive_residual_cells"
    assert result["per_step_records"] == []
    assert result["initial_metrics"]["target_positive_residual_depth_sum_m"] == 0.0
    assert result["final_metrics"]["target_positive_residual_depth_sum_m"] == 0.0


def test_predicted_rollout_validates_branch_plan_budget_and_options():
    invalid_branch = _branch_run_plan(status="invalid")
    assert _build_rollout(branch_run_plan=invalid_branch)["status"] == "invalid_branch_run_plan"

    assert _build_rollout(cycle_budget={"max_cycles": 0})["status"] == "invalid_cycle_budget"

    invalid_generation_options = {
        "direction_options": [],
        "depth_fraction_options": [1.0],
        "min_candidate_count": 1,
        "max_candidate_count": 10,
    }
    assert (
        _build_rollout(candidate_generation_options=invalid_generation_options)[
            "status"
        ]
        == "invalid_candidate_generation_options"
    )

    invalid_geometry = {
        "cell_size_m": 0.5,
        "bucket_width_m": -0.5,
        "bucket_length_m": 0.5,
    }
    assert _build_rollout(effect_geometry=invalid_geometry)["status"] == "invalid_effect_geometry"
