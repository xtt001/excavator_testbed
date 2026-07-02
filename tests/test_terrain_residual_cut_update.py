from __future__ import annotations

import json

from testbed.eval.terrain_residual_cut_update import (
    build_predicted_residual_update,
)


def _cut_intent_record(**overrides):
    record = {
        "cut_intent_candidate_id": "cut_candidate_000009",
        "candidate_id": "cut_candidate_000009",
        "offline_only": True,
        "anchor_cell_index": 2,
        "anchor_row": 1,
        "anchor_col": 0,
        "direction": "col_forward",
        "candidate_depth_m": 0.1,
        "score_rank_provenance": {
            "source": "explicit_candidate_heuristic_score_evidence",
            "rank": 1,
            "total_score": 4.25,
        },
        "effect_evidence_provenance": {
            "source": "explicit_candidate_effect_summary",
            "effect_status": "present",
        },
        "target_spec_provenance": {
            "source": "explicit_input_target_spec",
            "grid_shape": [2, 2],
            "target_depth_m": 0.25,
        },
        "safety_stop_condition_provenance_status": "from_branch_run_plan_contract",
        "runner_input_status": "ready_for_eval_harness",
        "production_runtime_action": False,
    }
    record.update(overrides)
    return record


def _cut_intent_output(**overrides):
    output = {
        "status": "present",
        "schema": "terrain_residual_heuristic_cut_intent_v1",
        "source": "explicit_heuristic_residual_cut_intent",
        "offline_only": True,
        "cut_intent": _cut_intent_record(),
    }
    output.update(overrides)
    return output


def _effect_record(**overrides):
    record = {
        "status": "present",
        "schema": "terrain_candidate_geometric_effect_v1",
        "source": "explicit_geometric_swept_footprint_effect",
        "offline_only": True,
        "candidate_id": "cut_candidate_000009",
        "expected_delta_depth_grid_m": [0.1, 0.0, 0.1, 0.0],
        "summary_metrics": {
            "expected_removed_depth_sum_m": 0.2,
            "target_removed_delta_sum_m": 0.2,
            "outside_target_removed_delta_sum_m": 0.0,
            "overdig_depth_delta_sum_m": 0.05,
        },
    }
    record.update(overrides)
    return record


def _build_update(**overrides):
    kwargs = {
        "cut_intent": _cut_intent_output(),
        "effect_record": _effect_record(),
        "removed_depth_grid_m": [0.1, 0.0, 0.2, 0.0],
        "target_depth_grid_m": [0.25, 0.0, 0.25, 0.0],
        "target_region_mask": [True, False, True, False],
        "valid_mask": [True, True, True, True],
        "grid_shape": [2, 2],
        "cell_size_m": 0.5,
    }
    kwargs.update(overrides)
    return build_predicted_residual_update(**kwargs)


def _all_keys(value):
    if isinstance(value, dict):
        for key, nested_value in value.items():
            yield key
            yield from _all_keys(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            yield from _all_keys(nested_value)


def test_predicted_residual_update_applies_effect_delta_and_recomputes_metrics():
    result = _build_update()

    assert result["status"] == "present"
    assert result["schema"] == "terrain_residual_predicted_cut_update_v1"
    assert result["source"] == "explicit_predicted_residual_cut_update"
    assert result["offline_only"] is True
    assert result["cut_intent_candidate_id"] == "cut_candidate_000009"
    assert result["predicted_removed_depth_grid_m"] == [0.2, 0.0, 0.3, 0.0]
    assert result["before_metrics"]["status"] == "present"
    assert result["after_metrics"]["status"] == "present"
    assert result["before_metrics"]["target_positive_residual_depth_sum_m"] == 0.2
    assert result["after_metrics"]["target_positive_residual_depth_sum_m"] == 0.05
    assert result["before_metrics"]["target_overdig_depth_sum_m"] == 0.0
    assert result["after_metrics"]["target_overdig_depth_sum_m"] == 0.05
    assert result["before_metrics"]["outside_target_removed_depth_sum_m"] == 0.0
    assert result["after_metrics"]["outside_target_removed_depth_sum_m"] == 0.0
    assert result["before_metrics"]["target_removed_completion_ratio"] == 0.6
    assert result["after_metrics"]["target_removed_completion_ratio"] == 0.9
    assert result["delta_summary"] == {
        "target_positive_residual_depth_delta_m": -0.15,
        "target_overdig_depth_delta_m": 0.05,
        "outside_target_removed_depth_delta_m": 0.0,
        "target_removed_completion_ratio_delta": 0.3,
        "expected_delta_depth_sum_m": 0.2,
        "expected_delta_volume_m3": 0.05,
        "target_positive_residual_volume_delta_m3": -0.0375,
        "target_overdig_volume_delta_m3": 0.0125,
        "outside_target_removed_volume_delta_m3": 0.0,
    }
    assert result["effect_provenance"] == {
        "source": "explicit_geometric_swept_footprint_effect",
        "candidate_id": "cut_candidate_000009",
        "expected_delta_depth_grid_status": "present",
        "summary_metrics_status": "present",
        "expected_removed_depth_sum_m": 0.2,
        "target_removed_delta_sum_m": 0.2,
        "outside_target_removed_delta_sum_m": 0.0,
        "overdig_depth_delta_sum_m": 0.05,
    }
    assert result["validation_errors"] == []
    assert result["provenance_statuses"] == {
        "cut_intent_source": "explicit_input",
        "effect_record_source": "explicit_input",
        "grid_source": "explicit_input",
        "metric_source": "testbed.eval.terrain_target_metrics.build_target_residual_metrics",
        "artifact_write_status": "not_written",
        "runner_execution_status": "not_run",
    }

    all_keys = set(_all_keys(result))
    assert "runtime_action" not in all_keys
    assert "pass_fail" not in all_keys
    assert "eval_success" not in all_keys
    assert "planner_success" not in all_keys
    serialized = json.dumps(result, sort_keys=True)
    assert "cut_candidate_000009" in serialized
    assert "target_positive_residual_depth_delta_m" in serialized


def test_predicted_residual_update_accepts_direct_cut_intent_record_without_volume():
    result = _build_update(cut_intent=_cut_intent_record(), cell_size_m=None)

    assert result["status"] == "present"
    assert result["cut_intent_candidate_id"] == "cut_candidate_000009"
    assert result["delta_summary"]["expected_delta_depth_sum_m"] == 0.2
    assert "expected_delta_volume_m3" not in result["delta_summary"]
    assert result["provenance_statuses"]["cell_size_status"] == "missing"


def test_predicted_residual_update_validates_cut_intent_and_effect_record():
    invalid_cut = _cut_intent_output(status="invalid_candidate_scoring")
    assert _build_update(cut_intent=invalid_cut)["status"] == "invalid_cut_intent"

    production_action_cut = _cut_intent_record(production_runtime_action=True)
    assert (
        _build_update(cut_intent=production_action_cut)["status"]
        == "invalid_cut_intent"
    )

    mismatched_effect = _effect_record(candidate_id="cut_candidate_other")
    assert (
        _build_update(effect_record=mismatched_effect)["status"]
        == "candidate_effect_mismatch"
    )

    invalid_effect = _effect_record(status="invalid_geometry")
    assert (
        _build_update(effect_record=invalid_effect)["status"]
        == "invalid_effect_record"
    )


def test_predicted_residual_update_validates_grid_lengths_and_metric_inputs():
    assert (
        _build_update(removed_depth_grid_m=[0.1])["status"]
        == "invalid_grid_lengths"
    )
    assert (
        _build_update(removed_depth_grid_m=[-0.1, 0.0, 0.2, 0.0])["status"]
        == "invalid_depth_values"
    )
    assert (
        _build_update(target_region_mask=["bad", False, True, False])["status"]
        == "invalid_mask_values"
    )
    assert _build_update(grid_shape=[3, 2])["status"] == "invalid_grid_shape"
