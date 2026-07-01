from __future__ import annotations

from testbed.eval.terrain_candidate_generation import (
    build_discrete_cut_candidates,
)


def test_discrete_cut_candidates_cover_positive_target_residual_cells_deterministically() -> None:
    result = build_discrete_cut_candidates(
        residual_depth_grid_m=[0.20, 0.0, 0.10, -0.05, 0.0, 0.0],
        target_region_mask=[1.0, 0.0, 1.0, 1.0, 0.0, 0.0],
        valid_mask=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        grid_shape=[3, 2],
        direction_options=[
            "row_forward",
            "row_reverse",
            "col_forward",
            "col_reverse",
        ],
        depth_fraction_options=[0.5, 0.75, 1.0],
        min_candidate_count=20,
        max_candidate_count=100,
    )

    assert result["status"] == "present"
    assert result["schema"] == "terrain_discrete_cut_candidates_v1"
    assert result["source"] == "explicit_target_residual_discrete_candidate_generation"
    assert result["offline_only"] is True
    assert result["profile"] == "explicit_target_residual_discrete_candidates"
    assert result["grid_shape"] == [3, 2]
    assert result["positive_residual_cell_count"] == 2
    assert result["candidate_count"] == 24
    assert result["untruncated_candidate_count"] == 24
    assert result["positive_residual_coverage"] == {
        "status": "present",
        "positive_residual_cell_indices": [0, 2],
        "covered_cell_indices": [0, 2],
        "uncovered_cell_indices": [],
        "covered_cell_count": 2,
        "uncovered_cell_count": 0,
    }
    assert result["validation_errors"] == []
    assert result["cell_size_status"] == "missing"
    assert result["origin_status"] == "missing"
    assert result["timestamp_status"] == "missing"
    assert result["frame_transform_status"] == "missing"
    assert result["height_grid_status"] == "missing"
    assert result["elevation_grid_status"] == "missing"
    assert result["confidence_grid_status"] == "missing"

    assert result["candidates"][:4] == [
        {
            "candidate_id": "cut_candidate_000001",
            "anchor_cell_index": 0,
            "anchor_row": 0,
            "anchor_col": 0,
            "direction": "row_forward",
            "depth_fraction": 0.5,
            "anchor_positive_residual_depth_m": 0.2,
            "candidate_depth_m": 0.1,
            "offline_only": True,
        },
        {
            "candidate_id": "cut_candidate_000002",
            "anchor_cell_index": 0,
            "anchor_row": 0,
            "anchor_col": 0,
            "direction": "row_forward",
            "depth_fraction": 0.75,
            "anchor_positive_residual_depth_m": 0.2,
            "candidate_depth_m": 0.15,
            "offline_only": True,
        },
        {
            "candidate_id": "cut_candidate_000003",
            "anchor_cell_index": 0,
            "anchor_row": 0,
            "anchor_col": 0,
            "direction": "row_forward",
            "depth_fraction": 1.0,
            "anchor_positive_residual_depth_m": 0.2,
            "candidate_depth_m": 0.2,
            "offline_only": True,
        },
        {
            "candidate_id": "cut_candidate_000004",
            "anchor_cell_index": 0,
            "anchor_row": 0,
            "anchor_col": 0,
            "direction": "row_reverse",
            "depth_fraction": 0.5,
            "anchor_positive_residual_depth_m": 0.2,
            "candidate_depth_m": 0.1,
            "offline_only": True,
        },
    ]
    assert result["candidates"][12]["candidate_id"] == "cut_candidate_000013"
    assert result["candidates"][12]["anchor_cell_index"] == 2
    assert result["candidates"][12]["anchor_row"] == 1
    assert result["candidates"][12]["anchor_col"] == 0


def test_discrete_cut_candidates_report_count_below_min_without_inventing_options() -> None:
    result = build_discrete_cut_candidates(
        residual_depth_grid_m=[0.2, 0.0, 0.0, 0.0],
        target_region_mask=[1.0, 0.0, 0.0, 0.0],
        valid_mask=[1.0, 1.0, 1.0, 1.0],
        grid_shape=[2, 2],
        direction_options=["row_forward"],
        depth_fraction_options=[1.0],
        min_candidate_count=2,
        max_candidate_count=10,
    )

    assert result["status"] == "candidate_count_below_min"
    assert result["candidate_count"] == 1
    assert result["untruncated_candidate_count"] == 1
    assert result["positive_residual_coverage"]["covered_cell_indices"] == [0]
    assert result["validation_errors"] == []


def test_discrete_cut_candidates_truncate_when_candidate_count_exceeds_explicit_max() -> None:
    result = build_discrete_cut_candidates(
        residual_depth_grid_m=[0.2, 0.1],
        target_region_mask=[1.0, 1.0],
        valid_mask=[1.0, 1.0],
        grid_shape=[1, 2],
        direction_options=["row_forward", "row_reverse"],
        depth_fraction_options=[0.5, 1.0],
        min_candidate_count=1,
        max_candidate_count=3,
    )

    assert result["status"] == "candidate_count_above_max"
    assert result["candidate_count"] == 3
    assert result["untruncated_candidate_count"] == 8
    assert [candidate["candidate_id"] for candidate in result["candidates"]] == [
        "cut_candidate_000001",
        "cut_candidate_000002",
        "cut_candidate_000003",
    ]
    assert result["positive_residual_coverage"] == {
        "status": "truncated",
        "positive_residual_cell_indices": [0, 1],
        "covered_cell_indices": [0],
        "uncovered_cell_indices": [1],
        "covered_cell_count": 1,
        "uncovered_cell_count": 1,
    }


def test_discrete_cut_candidates_report_no_positive_residual_cells() -> None:
    result = build_discrete_cut_candidates(
        residual_depth_grid_m=[0.0, -0.1, 0.0, 0.0],
        target_region_mask=[1.0, 1.0, 0.0, 0.0],
        valid_mask=[1.0, 1.0, 1.0, 1.0],
        grid_shape=[2, 2],
        direction_options=["row_forward"],
        depth_fraction_options=[1.0],
        min_candidate_count=1,
        max_candidate_count=10,
    )

    assert result["status"] == "no_positive_residual_cells"
    assert result["positive_residual_cell_count"] == 0
    assert result["candidate_count"] == 0
    assert result["candidates"] == []
    assert result["positive_residual_coverage"] == {
        "status": "no_positive_residual_cells",
        "positive_residual_cell_indices": [],
        "covered_cell_indices": [],
        "uncovered_cell_indices": [],
        "covered_cell_count": 0,
        "uncovered_cell_count": 0,
    }


def test_discrete_cut_candidates_validate_grid_lengths_and_options() -> None:
    length_result = build_discrete_cut_candidates(
        residual_depth_grid_m=[0.2, 0.1],
        target_region_mask=[1.0],
        valid_mask=[1.0, 1.0],
        grid_shape=[1, 2],
        direction_options=["row_forward"],
        depth_fraction_options=[1.0],
        min_candidate_count=1,
        max_candidate_count=10,
    )

    assert length_result["status"] == "invalid_grid_lengths"
    assert length_result["candidate_count"] == 0
    assert length_result["validation_errors"] == [
        "residual_depth_grid_m, target_region_mask, and valid_mask must have matching non-empty lengths",
    ]

    options_result = build_discrete_cut_candidates(
        residual_depth_grid_m=[0.2, 0.1],
        target_region_mask=[1.0, 1.0],
        valid_mask=[1.0, 1.0],
        grid_shape=[1, 2],
        direction_options=[],
        depth_fraction_options=[0.0, 1.1],
        min_candidate_count=10,
        max_candidate_count=1,
    )

    assert options_result["status"] == "invalid_candidate_options"
    assert options_result["validation_errors"] == [
        "direction_options must contain at least one non-empty string",
        "depth_fraction_options values must be finite and greater than 0.0 and at most 1.0",
        "min_candidate_count and max_candidate_count must be nonnegative integers with min <= max",
    ]
