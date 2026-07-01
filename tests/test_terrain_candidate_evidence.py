from testbed.eval.terrain_candidate_evidence import (
    build_candidate_constraint_evidence,
)
from testbed.eval.terrain_candidate_generation import build_discrete_cut_candidates


def test_candidate_constraint_evidence_annotates_grid_proxy_footprints_and_constraints():
    result = build_candidate_constraint_evidence(
        candidates=[
            {
                "candidate_id": "candidate_0000",
                "anchor_cell_index": 0,
                "anchor_row": 0,
                "anchor_col": 0,
                "direction": "row_forward",
                "candidate_depth_m": 0.15,
                "offline_only": True,
            },
            {
                "candidate_id": "candidate_0001",
                "anchor_cell_index": 0,
                "anchor_row": 0,
                "anchor_col": 0,
                "direction": "row_reverse",
                "candidate_depth_m": 0.25,
                "offline_only": True,
            },
        ],
        target_region_mask=[True, False, False, False, False, False, False, False, False],
        valid_mask=[True, True, True, True, True, True, True, True, True],
        grid_shape=[3, 3],
        max_candidate_depth_m=0.2,
        protected_boundary_cell_radius=0,
        return_origin_cell_index=8,
    )

    assert result["status"] == "present"
    assert result["schema"] == "terrain_candidate_constraint_evidence_v1"
    assert result["source"] == "explicit_target_candidate_constraint_evidence"
    assert result["offline_only"] is True
    assert result["candidate_count"] == 2
    assert result["validation_errors"] == []
    assert result["missing_provenance"] == {
        "cell_size_status": "missing",
        "origin_status": "missing",
        "timestamp_status": "missing",
        "frame_transform_status": "missing",
        "height_grid_status": "missing",
        "elevation_grid_status": "missing",
        "confidence_grid_status": "missing",
    }

    assert result["constraint_summary"] == {
        "candidate_count": 2,
        "grid_footprint_proxy": "directional_adjacent_cell_row_major",
        "protected_boundary_cell_radius": 0,
        "protected_boundary_cell_count": 1,
        "valid_cell_count": 9,
        "protected_boundary_saturation_ratio": 0.111111111111,
        "depth_budget_exceeded_count": 1,
        "clipped_by_grid_boundary_count": 1,
        "outside_target_footprint_candidate_count": 1,
        "outside_protected_boundary_candidate_count": 1,
        "return_alignment_cost_proxy_status": "present",
        "return_alignment_cost_proxy_min_cells": 4,
        "return_alignment_cost_proxy_max_cells": 4,
    }

    first, second = result["evidence_records"]
    assert first == {
        "candidate_id": "candidate_0000",
        "anchor_cell_index": 0,
        "anchor_row": 0,
        "anchor_col": 0,
        "direction": "row_forward",
        "candidate_depth_m": 0.15,
        "offline_only": True,
        "grid_footprint_cell_indices": [0, 1],
        "clipped_by_grid_boundary": False,
        "off_grid_neighbor": None,
        "target_footprint_cell_indices": [0],
        "outside_target_footprint_cell_indices": [1],
        "valid_footprint_cell_indices": [0, 1],
        "invalid_footprint_cell_indices": [],
        "protected_boundary_cell_indices": [0],
        "outside_protected_boundary_cell_indices": [1],
        "depth_budget_status": "within_budget",
        "max_candidate_depth_m": 0.2,
        "return_alignment_cost_proxy": {
            "status": "present",
            "source": "row_major_anchor_manhattan_distance",
            "return_origin_cell_index": 8,
            "anchor_cell_index": 0,
            "manhattan_distance_cells": 4,
        },
    }
    assert second["grid_footprint_cell_indices"] == [0]
    assert second["clipped_by_grid_boundary"] is True
    assert second["off_grid_neighbor"] == {"row": 0, "col": -1}
    assert second["depth_budget_status"] == "exceeds_budget"
    assert second["outside_target_footprint_cell_indices"] == []
    assert second["outside_protected_boundary_cell_indices"] == []


def test_candidate_constraint_evidence_keeps_return_proxy_optional():
    result = build_candidate_constraint_evidence(
        candidates=[
            {
                "candidate_id": "candidate_0000",
                "anchor_cell_index": 0,
                "anchor_row": 0,
                "anchor_col": 0,
                "direction": "row_forward",
                "candidate_depth_m": 0.1,
                "offline_only": True,
            }
        ],
        target_region_mask=[True, False, False, False],
        valid_mask=[True, True, True, True],
        grid_shape=[2, 2],
        max_candidate_depth_m=0.2,
        protected_boundary_cell_radius=1,
        return_origin_cell_index=None,
    )

    assert result["status"] == "present"
    assert result["constraint_summary"]["return_alignment_cost_proxy_status"] == "not_evaluated"
    assert result["constraint_summary"]["return_alignment_cost_proxy_min_cells"] is None
    assert result["constraint_summary"]["return_alignment_cost_proxy_max_cells"] is None
    assert result["evidence_records"][0]["return_alignment_cost_proxy"] == {
        "status": "not_evaluated",
        "reason": "return_origin_cell_index_missing",
    }


def test_candidate_constraint_evidence_returns_explicit_invalid_statuses():
    assert (
        build_candidate_constraint_evidence(
            candidates=[
                {
                    "candidate_id": "candidate_0000",
                    "anchor_cell_index": 0,
                    "direction": "row_forward",
                    "candidate_depth_m": 0.1,
                }
            ],
            target_region_mask=[True],
            valid_mask=[True],
            grid_shape=[1, 1],
            max_candidate_depth_m=0.2,
            protected_boundary_cell_radius=0,
        )["status"]
        == "invalid_candidates"
    )
    assert (
        build_candidate_constraint_evidence(
            candidates=[],
            target_region_mask=[True, False],
            valid_mask=[True, True],
            grid_shape=[1, 2],
            max_candidate_depth_m=-0.1,
            protected_boundary_cell_radius=0,
        )["status"]
        == "invalid_depth_budget"
    )
    assert (
        build_candidate_constraint_evidence(
            candidates=[],
            target_region_mask=[True, False],
            valid_mask=[True, True],
            grid_shape=[1, 2],
            max_candidate_depth_m=0.1,
            protected_boundary_cell_radius=-1,
        )["status"]
        == "invalid_boundary_radius"
    )
    assert (
        build_candidate_constraint_evidence(
            candidates=[],
            target_region_mask=[True, False, True],
            valid_mask=[True, True, True],
            grid_shape=[1, 2],
            max_candidate_depth_m=0.1,
            protected_boundary_cell_radius=0,
        )["status"]
        == "invalid_grid_shape"
    )
    assert (
        build_candidate_constraint_evidence(
            candidates=[],
            target_region_mask=[True, "yes"],
            valid_mask=[True, True],
            grid_shape=[1, 2],
            max_candidate_depth_m=0.1,
            protected_boundary_cell_radius=0,
        )["status"]
        == "invalid_mask_values"
    )
    assert (
        build_candidate_constraint_evidence(
            candidates=[],
            target_region_mask=[True, False],
            valid_mask=[True, True],
            grid_shape=[1, 2],
            max_candidate_depth_m=0.1,
            protected_boundary_cell_radius=0,
            return_origin_cell_index=3,
        )["status"]
        == "invalid_return_origin"
    )


def test_candidate_constraint_evidence_preserves_generation_order_and_count():
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

    result = build_candidate_constraint_evidence(
        candidates=generated["candidates"],
        target_region_mask=[True, False, True, False],
        valid_mask=[True, True, True, True],
        grid_shape=[2, 2],
        max_candidate_depth_m=0.2,
        protected_boundary_cell_radius=0,
        return_origin_cell_index=0,
    )

    assert result["status"] == "present"
    assert result["candidate_count"] == generated["candidate_count"]
    assert [record["candidate_id"] for record in result["evidence_records"]] == [
        candidate["candidate_id"] for candidate in generated["candidates"]
    ]
    assert result["constraint_summary"]["outside_target_footprint_candidate_count"] == 4
