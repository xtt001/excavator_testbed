from testbed.eval.terrain_candidate_evidence import (
    build_candidate_constraint_evidence,
)
from testbed.eval.terrain_candidate_generation import build_discrete_cut_candidates
from testbed.eval.terrain_candidate_scoring import build_candidate_heuristic_scores


WEIGHTS = {
    "candidate_depth_reward": 10.0,
    "target_footprint_cell_reward": 1.0,
    "outside_target_footprint_cell_penalty": 2.0,
    "outside_protected_boundary_cell_penalty": 4.0,
    "depth_budget_exceeded_penalty": 5.0,
    "grid_boundary_clipped_penalty": 0.5,
    "return_alignment_distance_penalty": 0.25,
}


def test_candidate_heuristic_scores_compute_components_and_ranking():
    result = build_candidate_heuristic_scores(
        evidence_records=[
            {
                "candidate_id": "candidate_a",
                "candidate_depth_m": 0.1,
                "offline_only": True,
                "target_footprint_cell_indices": [0],
                "outside_target_footprint_cell_indices": [],
                "outside_protected_boundary_cell_indices": [],
                "depth_budget_status": "within_budget",
                "clipped_by_grid_boundary": False,
                "return_alignment_cost_proxy": {
                    "status": "present",
                    "manhattan_distance_cells": 2,
                },
            },
            {
                "candidate_id": "candidate_b",
                "candidate_depth_m": 0.2,
                "offline_only": True,
                "target_footprint_cell_indices": [0],
                "outside_target_footprint_cell_indices": [1],
                "outside_protected_boundary_cell_indices": [1],
                "depth_budget_status": "exceeds_budget",
                "clipped_by_grid_boundary": True,
                "return_alignment_cost_proxy": {
                    "status": "present",
                    "manhattan_distance_cells": 1,
                },
            },
        ],
        weights=WEIGHTS,
    )

    assert result["status"] == "present"
    assert result["schema"] == "terrain_candidate_heuristic_scores_v1"
    assert result["source"] == "explicit_candidate_heuristic_score_evidence"
    assert result["offline_only"] is True
    assert result["candidate_count"] == 2
    assert result["validation_errors"] == []
    assert result["missing_provenance"] == {
        "calibrated_effect_model_status": "missing",
        "payload_model_status": "missing",
        "physical_bucket_footprint_status": "missing",
        "cell_size_status": "missing",
        "official_weight_status": "missing",
    }

    first, second = result["score_records"]
    assert first["candidate_id"] == "candidate_a"
    assert first["input_index"] == 0
    assert first["total_score"] == 1.5
    assert first["score_components"] == {
        "candidate_depth_reward": {
            "status": "present",
            "value": 1.0,
            "weight": 10.0,
            "candidate_depth_m": 0.1,
        },
        "target_footprint_cell_reward": {
            "status": "present",
            "value": 1.0,
            "weight": 1.0,
            "cell_count": 1,
        },
        "outside_target_footprint_cell_penalty": {
            "status": "present",
            "value": -0.0,
            "weight": 2.0,
            "cell_count": 0,
        },
        "outside_protected_boundary_cell_penalty": {
            "status": "present",
            "value": -0.0,
            "weight": 4.0,
            "cell_count": 0,
        },
        "depth_budget_exceeded_penalty": {
            "status": "not_applied",
            "value": 0.0,
            "weight": 5.0,
            "depth_budget_status": "within_budget",
        },
        "grid_boundary_clipped_penalty": {
            "status": "not_applied",
            "value": 0.0,
            "weight": 0.5,
            "clipped_by_grid_boundary": False,
        },
        "return_alignment_distance_penalty": {
            "status": "present",
            "value": -0.5,
            "weight": 0.25,
            "manhattan_distance_cells": 2,
        },
    }

    assert second["candidate_id"] == "candidate_b"
    assert second["total_score"] == -8.75
    assert result["ranking"] == {
        "semantics": "diagnostic_offline_ranking_only",
        "no_production_action": True,
        "ranked_candidate_ids": ["candidate_a", "candidate_b"],
        "ranked_candidates": [
            {
                "rank": 1,
                "candidate_id": "candidate_a",
                "total_score": 1.5,
                "input_index": 0,
            },
            {
                "rank": 2,
                "candidate_id": "candidate_b",
                "total_score": -8.75,
                "input_index": 1,
            },
        ],
    }
    assert result["score_summary"] == {
        "candidate_count": 2,
        "min_score": -8.75,
        "max_score": 1.5,
        "mean_score": -3.625,
        "best_candidate_id": "candidate_a",
        "best_score": 1.5,
        "worst_candidate_id": "candidate_b",
        "worst_score": -8.75,
    }


def test_candidate_heuristic_scores_keep_missing_return_proxy_as_zero_component():
    result = build_candidate_heuristic_scores(
        evidence_records=[
            {
                "candidate_id": "candidate_a",
                "candidate_depth_m": 0.1,
                "offline_only": True,
                "target_footprint_cell_indices": [],
                "outside_target_footprint_cell_indices": [],
                "outside_protected_boundary_cell_indices": [],
                "depth_budget_status": "within_budget",
                "clipped_by_grid_boundary": False,
                "return_alignment_cost_proxy": {
                    "status": "not_evaluated",
                    "reason": "return_origin_cell_index_missing",
                },
            }
        ],
        weights=WEIGHTS,
    )

    record = result["score_records"][0]
    assert record["total_score"] == 1.0
    assert record["score_components"]["return_alignment_distance_penalty"] == {
        "status": "not_evaluated",
        "value": 0.0,
        "weight": 0.25,
        "reason": "return_origin_cell_index_missing",
    }


def test_candidate_heuristic_scores_return_invalid_statuses():
    missing_weight_result = build_candidate_heuristic_scores(
        evidence_records=[],
        weights={
            key: value
            for key, value in WEIGHTS.items()
            if key != "candidate_depth_reward"
        },
    )
    assert missing_weight_result["status"] == "invalid_weights"
    assert missing_weight_result["score_records"] == []

    invalid_evidence_result = build_candidate_heuristic_scores(
        evidence_records=[
            {
                "candidate_id": "candidate_a",
                "candidate_depth_m": 0.1,
                "offline_only": True,
            }
        ],
        weights=WEIGHTS,
    )
    assert invalid_evidence_result["status"] == "invalid_evidence_records"
    assert invalid_evidence_result["score_records"] == []

    no_evidence_result = build_candidate_heuristic_scores(
        evidence_records=[],
        weights=WEIGHTS,
    )
    assert no_evidence_result["status"] == "no_evidence_records"
    assert no_evidence_result["ranking"]["ranked_candidate_ids"] == []


def test_candidate_heuristic_scores_compose_with_generation_and_evidence():
    generated = build_discrete_cut_candidates(
        residual_depth_grid_m=[0.2, 0.0, 0.1, 0.0],
        target_region_mask=[True, False, True, False],
        valid_mask=[True, True, True, True],
        grid_shape=[2, 2],
        direction_options=["row_forward", "col_forward"],
        depth_fraction_options=[0.5, 1.0],
        min_candidate_count=1,
        max_candidate_count=100,
    )
    evidence = build_candidate_constraint_evidence(
        candidates=generated["candidates"],
        target_region_mask=[True, False, True, False],
        valid_mask=[True, True, True, True],
        grid_shape=[2, 2],
        max_candidate_depth_m=0.2,
        protected_boundary_cell_radius=0,
        return_origin_cell_index=0,
    )

    result = build_candidate_heuristic_scores(
        evidence_records=evidence["evidence_records"],
        weights=WEIGHTS,
    )

    assert result["status"] == "present"
    assert result["candidate_count"] == evidence["candidate_count"]
    assert [record["candidate_id"] for record in result["score_records"]] == [
        record["candidate_id"] for record in evidence["evidence_records"]
    ]
    assert sorted(result["ranking"]["ranked_candidate_ids"]) == sorted(
        record["candidate_id"] for record in evidence["evidence_records"]
    )
