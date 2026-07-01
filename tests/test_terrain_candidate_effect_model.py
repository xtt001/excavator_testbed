from testbed.eval.terrain_candidate_effect_model import (
    build_entry_exit_swept_footprint_effect,
    build_geometric_swept_footprint_effect,
)
from testbed.eval.terrain_candidate_evidence import (
    build_candidate_constraint_evidence,
)
from testbed.eval.terrain_candidate_generation import build_discrete_cut_candidates
from testbed.eval.terrain_candidate_scoring import build_candidate_heuristic_scores


def _candidate(**overrides):
    candidate = {
        "candidate_id": "cut_candidate_000001",
        "anchor_cell_index": 5,
        "anchor_row": 1,
        "anchor_col": 1,
        "direction": "row_forward",
        "candidate_depth_m": 0.1,
        "offline_only": True,
    }
    candidate.update(overrides)
    return candidate


def _present_inputs(**overrides):
    grid_shape = [3, 4]
    removed_depth_grid_m = [0.0] * 12
    removed_depth_grid_m[5] = 0.2
    removed_depth_grid_m[6] = 0.1

    target_depth_grid_m = [0.0] * 12
    target_depth_grid_m[5] = 0.25
    target_depth_grid_m[6] = 0.25

    target_region_mask = [False] * 12
    target_region_mask[5] = True
    target_region_mask[6] = True

    inputs = {
        "candidate": _candidate(),
        "removed_depth_grid_m": removed_depth_grid_m,
        "target_depth_grid_m": target_depth_grid_m,
        "target_region_mask": target_region_mask,
        "valid_mask": [True] * 12,
        "grid_shape": grid_shape,
        "cell_size_m": 0.5,
        "bucket_width_m": 0.5,
        "bucket_length_m": 1.0,
    }
    inputs.update(overrides)
    return inputs


def _entry_exit_inputs(**overrides):
    inputs = _present_inputs()
    inputs.pop("bucket_length_m")
    inputs.update(
        {
            "entry_cell_index": 5,
            "exit_cell_index": 7,
            "target_penetration_depth_m": 0.1,
        }
    )
    inputs.update(overrides)
    return inputs


def test_build_geometric_swept_footprint_effect_reports_expected_patch_and_volumes():
    result = build_geometric_swept_footprint_effect(**_present_inputs())

    assert result["status"] == "present"
    assert result["offline_only"] is True
    assert result["source"] == "explicit_geometric_swept_footprint_effect"
    assert result["footprint"]["model"] == (
        "centerline_rectangular_swept_footprint_approximation"
    )
    assert result["geometry_inputs"] == {
        "cell_size_m": 0.5,
        "bucket_width_m": 0.5,
        "bucket_length_m": 1.0,
        "penetration_depth_m": 0.1,
        "penetration_depth_source": "candidate_depth_m",
    }
    assert result["footprint"]["footprint_cell_indices"] == [5, 6, 7]
    assert result["footprint"]["footprint_clipped_by_grid_boundary"] is False
    assert result["expected_delta_depth_grid_m"] == [
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.1,
        0.1,
        0.1,
        0.0,
        0.0,
        0.0,
        0.0,
    ]
    assert result["summary_metrics"] == {
        "expected_removed_depth_sum_m": 0.3,
        "expected_removed_volume_m3": 0.075,
        "target_removed_delta_sum_m": 0.2,
        "target_removed_volume_m3": 0.05,
        "outside_target_removed_delta_sum_m": 0.1,
        "outside_target_removed_volume_m3": 0.025,
        "overdig_depth_delta_sum_m": 0.15,
        "overdig_volume_delta_m3": 0.0375,
    }


def test_build_geometric_swept_footprint_effect_uses_explicit_penetration_override():
    result = build_geometric_swept_footprint_effect(
        **_present_inputs(penetration_depth_m=0.2)
    )

    assert result["status"] == "present"
    assert result["geometry_inputs"]["penetration_depth_m"] == 0.2
    assert (
        result["geometry_inputs"]["penetration_depth_source"]
        == "explicit_penetration_depth_m"
    )
    assert result["summary_metrics"]["expected_removed_depth_sum_m"] == 0.6
    assert result["summary_metrics"]["expected_removed_volume_m3"] == 0.15


def test_build_geometric_swept_footprint_effect_reports_grid_boundary_clipping():
    result = build_geometric_swept_footprint_effect(
        candidate=_candidate(
            anchor_cell_index=1,
            anchor_row=0,
            anchor_col=1,
            direction="row_forward",
        ),
        removed_depth_grid_m=[0.0, 0.0, 0.0, 0.0],
        target_depth_grid_m=[0.0, 0.0, 0.0, 0.0],
        target_region_mask=[False, True, False, False],
        valid_mask=[True, True, True, True],
        grid_shape=[2, 2],
        cell_size_m=0.5,
        bucket_width_m=0.5,
        bucket_length_m=0.5,
    )

    assert result["status"] == "present"
    assert result["footprint"]["footprint_cell_indices"] == [1]
    assert result["footprint"]["footprint_clipped_by_grid_boundary"] is True


def test_build_geometric_swept_footprint_effect_returns_explicit_invalid_statuses():
    assert (
        build_geometric_swept_footprint_effect(
            **_present_inputs(candidate={"candidate_id": "missing_fields"})
        )["status"]
        == "invalid_candidate"
    )
    assert (
        build_geometric_swept_footprint_effect(**_present_inputs(grid_shape=[3, 5]))[
            "status"
        ]
        == "invalid_grid_shape"
    )
    assert (
        build_geometric_swept_footprint_effect(
            **_present_inputs(target_depth_grid_m=[0.0])
        )["status"]
        == "invalid_grid_lengths"
    )
    assert (
        build_geometric_swept_footprint_effect(
            **_present_inputs(target_region_mask=["bad"] * 12)
        )["status"]
        == "invalid_mask_values"
    )
    assert (
        build_geometric_swept_footprint_effect(
            **_present_inputs(removed_depth_grid_m=[-1.0] + [0.0] * 11)
        )["status"]
        == "invalid_depth_values"
    )
    assert (
        build_geometric_swept_footprint_effect(**_present_inputs(cell_size_m=0.0))[
            "status"
        ]
        == "invalid_geometry"
    )


def test_build_geometric_swept_footprint_effect_composes_with_candidate_pipeline():
    generated = build_discrete_cut_candidates(
        residual_depth_grid_m=[0.2, 0.0, 0.1, 0.0],
        target_region_mask=[True, False, True, False],
        valid_mask=[True, True, True, True],
        grid_shape=[2, 2],
        direction_options=["row_forward", "col_forward"],
        depth_fraction_options=[1.0],
        min_candidate_count=1,
        max_candidate_count=10,
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
    scores = build_candidate_heuristic_scores(
        evidence_records=evidence["evidence_records"],
        weights={
            "candidate_depth_reward": 10.0,
            "target_footprint_cell_reward": 1.0,
            "outside_target_footprint_cell_penalty": 2.0,
            "outside_protected_boundary_cell_penalty": 4.0,
            "depth_budget_exceeded_penalty": 5.0,
            "grid_boundary_clipped_penalty": 0.5,
            "return_alignment_distance_penalty": 0.25,
        },
    )
    best_candidate_id = scores["score_summary"]["best_candidate_id"]
    candidate = next(
        candidate
        for candidate in generated["candidates"]
        if candidate["candidate_id"] == best_candidate_id
    )

    result = build_geometric_swept_footprint_effect(
        candidate=candidate,
        removed_depth_grid_m=[0.05, 0.0, 0.0, 0.0],
        target_depth_grid_m=[0.25, 0.0, 0.25, 0.0],
        target_region_mask=[True, False, True, False],
        valid_mask=[True, True, True, True],
        grid_shape=[2, 2],
        cell_size_m=0.5,
        bucket_width_m=0.5,
        bucket_length_m=0.5,
    )

    assert result["status"] == "present"
    assert result["candidate_id"] == best_candidate_id
    assert result["footprint"]["footprint_cell_count"] >= 1


def test_build_entry_exit_swept_footprint_effect_reports_segment_patch_and_volumes():
    result = build_entry_exit_swept_footprint_effect(**_entry_exit_inputs())

    assert result["status"] == "present"
    assert result["offline_only"] is True
    assert result["source"] == "explicit_entry_exit_swept_footprint_effect"
    assert result["entry_exit_path"] == {
        "model": "entry_exit_centerline_segment_approximation",
        "candidate_direction": "row_forward",
        "entry_cell_index": 5,
        "entry_row": 1,
        "entry_col": 1,
        "exit_cell_index": 7,
        "exit_row": 1,
        "exit_col": 3,
        "segment_length_m": 1.0,
    }
    assert result["geometry_inputs"] == {
        "cell_size_m": 0.5,
        "bucket_width_m": 0.5,
        "target_penetration_depth_m": 0.1,
        "target_penetration_depth_source": "explicit_target_penetration_depth_m",
    }
    assert result["footprint"]["model"] == (
        "entry_exit_centerline_segment_approximation"
    )
    assert result["footprint"]["footprint_cell_indices"] == [5, 6, 7]
    assert result["footprint"]["target_footprint_cell_indices"] == [5, 6]
    assert result["footprint"]["outside_target_footprint_cell_indices"] == [7]
    assert result["footprint"]["valid_footprint_cell_indices"] == [5, 6, 7]
    assert result["footprint"]["invalid_footprint_cell_indices"] == []
    assert result["footprint"]["entry_cell_valid"] is True
    assert result["footprint"]["exit_cell_valid"] is True
    assert result["footprint"]["footprint_clipped_by_grid_boundary"] is False
    assert result["expected_delta_depth_grid_m"] == [
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.1,
        0.1,
        0.1,
        0.0,
        0.0,
        0.0,
        0.0,
    ]
    assert result["summary_metrics"] == {
        "expected_removed_depth_sum_m": 0.3,
        "expected_removed_volume_m3": 0.075,
        "target_removed_delta_sum_m": 0.2,
        "target_removed_volume_m3": 0.05,
        "outside_target_removed_delta_sum_m": 0.1,
        "outside_target_removed_volume_m3": 0.025,
        "overdig_depth_delta_sum_m": 0.15,
        "overdig_volume_delta_m3": 0.0375,
    }


def test_build_entry_exit_swept_footprint_effect_uses_explicit_segment_not_candidate_direction():
    result = build_entry_exit_swept_footprint_effect(
        **_entry_exit_inputs(candidate=_candidate(direction="col_forward"))
    )

    assert result["status"] == "present"
    assert result["entry_exit_path"]["candidate_direction"] == "col_forward"
    assert result["footprint"]["footprint_cell_indices"] == [5, 6, 7]


def test_build_entry_exit_swept_footprint_effect_returns_explicit_invalid_statuses():
    assert (
        build_entry_exit_swept_footprint_effect(
            **_entry_exit_inputs(candidate={"candidate_id": "missing_fields"})
        )["status"]
        == "invalid_candidate"
    )
    assert (
        build_entry_exit_swept_footprint_effect(**_entry_exit_inputs(grid_shape=[3, 5]))[
            "status"
        ]
        == "invalid_grid_shape"
    )
    assert (
        build_entry_exit_swept_footprint_effect(
            **_entry_exit_inputs(target_depth_grid_m=[0.0])
        )["status"]
        == "invalid_grid_lengths"
    )
    assert (
        build_entry_exit_swept_footprint_effect(
            **_entry_exit_inputs(target_region_mask=["bad"] * 12)
        )["status"]
        == "invalid_mask_values"
    )
    assert (
        build_entry_exit_swept_footprint_effect(
            **_entry_exit_inputs(removed_depth_grid_m=[-1.0] + [0.0] * 11)
        )["status"]
        == "invalid_depth_values"
    )
    assert (
        build_entry_exit_swept_footprint_effect(
            **_entry_exit_inputs(bucket_width_m=0.0)
        )["status"]
        == "invalid_geometry"
    )
    assert (
        build_entry_exit_swept_footprint_effect(
            **_entry_exit_inputs(entry_cell_index=5, exit_cell_index=5)
        )["status"]
        == "invalid_entry_exit"
    )
    assert (
        build_entry_exit_swept_footprint_effect(
            **_entry_exit_inputs(valid_mask=[True] * 5 + [False] + [True] * 6)
        )["status"]
        == "invalid_entry_exit"
    )
