from __future__ import annotations

from testbed.data.schema import (
    ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
    ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX,
    ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
)
from testbed.eval.terrain_target_projection import (
    build_latest_target_residual_projection,
    build_target_residual_convergence_projection,
)


def _env_state_with_compact_grid(
    *,
    removed_depth: list[float],
    valid_mask: list[float],
    long_count: float = 3.0,
    short_count: float = 2.0,
) -> list[float]:
    values = [0.0] * 64
    values[ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX] = long_count
    values[ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX] = short_count
    values[
        ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX : ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX
        + 6
    ] = removed_depth
    values[
        ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX : ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX
        + 6
    ] = valid_mask
    return values


def test_latest_target_projection_uses_latest_usable_snapshot_and_explicit_target() -> None:
    projection = build_latest_target_residual_projection(
        [
            {"env_state": [0.0] * 20},
            {
                "env_state": _env_state_with_compact_grid(
                    removed_depth=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                    valid_mask=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
                )
            },
            {
                "env_state": _env_state_with_compact_grid(
                    removed_depth=[0.10, 0.05, 0.30, 0.40, 0.20, 0.50],
                    valid_mask=[1.0, 1.0, 1.0, 1.0, 0.0, 1.0],
                )
            },
        ],
        grid_shape=[3, 2],
        row_start=0,
        row_end=2,
        col_start=0,
        col_end=1,
        target_depth_m=0.25,
    )

    assert projection["status"] == "present"
    assert (
        projection["source"]
        == "rollout_jsonl_latest_compact_grid_explicit_target_projection"
    )
    assert projection["snapshot_row_index"] == 2
    assert projection["observed_grid_shape"] == [3, 2]
    assert projection["target_spec_grid_shape"] == [3, 2]
    assert projection["removed_depth_grid_m"] == [
        0.10,
        0.05,
        0.30,
        0.40,
        0.20,
        0.50,
    ]
    assert projection["valid_mask"] == [1.0, 1.0, 1.0, 1.0, 0.0, 1.0]
    assert projection["target_grid"]["status"] == "present"
    assert projection["target_grid"]["target_depth_grid_m"] == [
        0.25,
        0.0,
        0.25,
        0.0,
        0.0,
        0.0,
    ]
    assert projection["target_grid"]["target_region_mask"] == [1, 0, 1, 0, 0, 0]
    assert projection["target_residual_metrics"]["status"] == "present"
    assert (
        projection["target_residual_metrics"][
            "target_positive_residual_depth_sum_m"
        ]
        == 0.15
    )
    assert projection["target_residual_metrics"]["target_overdig_depth_sum_m"] == 0.05
    assert projection["target_residual_metrics"]["target_depth_sum_m"] == 0.5
    assert projection["target_residual_metrics"]["target_removed_depth_sum_m"] == 0.4
    assert (
        projection["target_residual_metrics"]["target_removed_completion_ratio"]
        == 0.7
    )
    assert (
        projection["target_residual_metrics"]["outside_target_removed_depth_sum_m"]
        == 0.95
    )
    assert projection["cell_size_status"] == "missing"
    assert projection["origin_status"] == "missing"
    assert projection["timestamp_status"] == "missing"
    assert projection["frame_transform_status"] == "missing"
    assert projection["height_grid_status"] == "missing"
    assert projection["elevation_grid_status"] == "missing"
    assert projection["confidence_grid_status"] == "missing"


def test_latest_target_projection_returns_missing_without_usable_snapshot() -> None:
    projection = build_latest_target_residual_projection(
        [
            {"env_state": [0.0] * 20},
            {"env_state": "not-a-sequence"},
            {"skill_name": "dig"},
        ],
        grid_shape=[3, 2],
        row_start=0,
        row_end=1,
        col_start=0,
        col_end=1,
        target_depth_m=0.25,
    )

    assert projection["status"] == "missing_snapshot"
    assert projection["snapshot_row_index"] is None
    assert projection["observed_grid_shape"] is None
    assert projection["target_spec_grid_shape"] == [3, 2]
    assert projection["removed_depth_grid_m"] == []
    assert projection["valid_mask"] == []
    assert projection["target_grid"] is None
    assert projection["target_residual_metrics"] is None


def test_latest_target_projection_surfaces_target_grid_validation_status() -> None:
    projection = build_latest_target_residual_projection(
        [
            {
                "env_state": _env_state_with_compact_grid(
                    removed_depth=[0.10, 0.05, 0.30, 0.40, 0.20, 0.50],
                    valid_mask=[1.0, 0.0, 1.0, 1.0, 1.0, 1.0],
                )
            }
        ],
        grid_shape=[3, 2],
        row_start=0,
        row_end=1,
        col_start=1,
        col_end=2,
        target_depth_m=0.25,
    )

    assert projection["status"] == "invalid_target_region_mask"
    assert projection["snapshot_row_index"] == 0
    assert projection["target_grid"]["status"] == "invalid_target_region_mask"
    assert projection["target_grid"]["invalid_target_cell_count"] == 1
    assert projection["target_residual_metrics"] is None


def test_latest_target_projection_reports_unknown_observed_shape_when_counts_mismatch() -> None:
    projection = build_latest_target_residual_projection(
        [
            {
                "env_state": _env_state_with_compact_grid(
                    removed_depth=[0.10, 0.05, 0.30, 0.40, 0.20, 0.50],
                    valid_mask=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
                    long_count=4.0,
                    short_count=2.0,
                )
            }
        ],
        grid_shape=[3, 2],
        row_start=0,
        row_end=1,
        col_start=0,
        col_end=1,
        target_depth_m=0.25,
    )

    assert projection["status"] == "present"
    assert projection["observed_grid_shape"] is None
    assert projection["target_spec_grid_shape"] == [3, 2]
    assert projection["target_residual_metrics"]["status"] == "present"


def test_target_convergence_projection_reports_dig_segment_curve_and_summary() -> None:
    projection = build_target_residual_convergence_projection(
        [
            {
                "skill_name": "dig",
                "env_state": _env_state_with_compact_grid(
                    removed_depth=[0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
                    valid_mask=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
                ),
            },
            {
                "skill_name": "dig",
                "env_state": _env_state_with_compact_grid(
                    removed_depth=[0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
                    valid_mask=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
                ),
            },
            {"skill_name": "carry", "env_state": [0.0] * 64},
            {"skill_name": "dig", "env_state": [0.0] * 20},
            {
                "skill_name": "dig",
                "env_state": _env_state_with_compact_grid(
                    removed_depth=[0.10, 0.00, 0.30, 0.00, 0.20, 0.00],
                    valid_mask=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
                ),
            },
            {"skill_name": "return", "env_state": [0.0] * 20},
        ],
        grid_shape=[3, 2],
        row_start=0,
        row_end=2,
        col_start=0,
        col_end=1,
        target_depth_m=0.25,
    )

    assert projection["status"] == "present"
    assert (
        projection["source"]
        == "rollout_jsonl_dig_segments_explicit_target_residual_convergence"
    )
    assert projection["curve_window"] == (
        "final usable compact-grid snapshot per contiguous rows where skill_name == 'dig'"
    )
    assert projection["target_spec"] == {
        "grid_shape": [3, 2],
        "row_start": 0,
        "row_end": 2,
        "col_start": 0,
        "col_end": 1,
        "target_depth_m": 0.25,
        "profile": "explicit_t1_like_rectangular_shallow_pit",
    }
    assert projection["target_grid"]["status"] == "present"
    assert projection["curve"] == [
        {
            "dig_segment_index": 1,
            "snapshot_row_index": 1,
            "target_positive_residual_depth_sum_m": 0.5,
            "target_overdig_depth_sum_m": 0.0,
            "target_removed_completion_ratio": 0.0,
            "outside_target_removed_depth_sum_m": 0.0,
            "target_residual_metrics": {
                "status": "present",
                "source": "explicit_target_grid_removed_depth_comparison",
                "profile": "explicit_target_shape_residual_metrics",
                "cell_count": 6,
                "valid_cell_count": 6,
                "target_cell_count": 2,
                "outside_target_cell_count": 4,
                "target_positive_residual_depth_sum_m": 0.5,
                "target_overdig_depth_sum_m": 0.0,
                "target_depth_sum_m": 0.5,
                "target_removed_depth_sum_m": 0.0,
                "target_removed_completion_ratio": 0.0,
                "outside_target_removed_depth_sum_m": 0.0,
                "residual_depth_grid_m": [0.25, 0.0, 0.25, 0.0, 0.0, 0.0],
                "invalid_target_cell_count": 0,
                "validation_errors": [],
                "cell_size_status": "missing",
                "origin_status": "missing",
                "timestamp_status": "missing",
                "frame_transform_status": "missing",
                "height_grid_status": "missing",
                "elevation_grid_status": "missing",
                "confidence_grid_status": "missing",
            },
        },
        {
            "dig_segment_index": 2,
            "snapshot_row_index": 4,
            "target_positive_residual_depth_sum_m": 0.15,
            "target_overdig_depth_sum_m": 0.05,
            "target_removed_completion_ratio": 0.7,
            "outside_target_removed_depth_sum_m": 0.2,
            "target_residual_metrics": {
                "status": "present",
                "source": "explicit_target_grid_removed_depth_comparison",
                "profile": "explicit_target_shape_residual_metrics",
                "cell_count": 6,
                "valid_cell_count": 6,
                "target_cell_count": 2,
                "outside_target_cell_count": 4,
                "target_positive_residual_depth_sum_m": 0.15,
                "target_overdig_depth_sum_m": 0.05,
                "target_depth_sum_m": 0.5,
                "target_removed_depth_sum_m": 0.4,
                "target_removed_completion_ratio": 0.7,
                "outside_target_removed_depth_sum_m": 0.2,
                "residual_depth_grid_m": [0.15, 0.0, -0.05, 0.0, -0.2, 0.0],
                "invalid_target_cell_count": 0,
                "validation_errors": [],
                "cell_size_status": "missing",
                "origin_status": "missing",
                "timestamp_status": "missing",
                "frame_transform_status": "missing",
                "height_grid_status": "missing",
                "elevation_grid_status": "missing",
                "confidence_grid_status": "missing",
            },
        },
    ]
    assert projection["summary"] == {
        "status": "present",
        "source": "target_residual_convergence_curve",
        "point_count": 2,
        "start_dig_segment_index": 1,
        "end_dig_segment_index": 2,
        "target_positive_residual_depth_sum_start_m": 0.5,
        "target_positive_residual_depth_sum_end_m": 0.15,
        "target_positive_residual_depth_sum_delta_m": -0.35,
        "target_overdig_depth_sum_start_m": 0.0,
        "target_overdig_depth_sum_end_m": 0.05,
        "target_overdig_depth_sum_delta_m": 0.05,
        "target_removed_completion_ratio_start": 0.0,
        "target_removed_completion_ratio_end": 0.7,
        "target_removed_completion_ratio_delta": 0.7,
        "outside_target_removed_depth_sum_start_m": 0.0,
        "outside_target_removed_depth_sum_end_m": 0.2,
        "outside_target_removed_depth_sum_delta_m": 0.2,
        "diagnostic_trend": "target_positive_residual_reduced_outside_removed_increased",
    }


def test_target_convergence_projection_reports_missing_curve_without_usable_dig_snapshot() -> None:
    projection = build_target_residual_convergence_projection(
        [
            {"skill_name": "dig", "env_state": [0.0] * 20},
            {"skill_name": "carry", "env_state": [0.0] * 64},
            {"skill_name": "dig"},
        ],
        grid_shape=[3, 2],
        row_start=0,
        row_end=1,
        col_start=0,
        col_end=1,
        target_depth_m=0.25,
    )

    assert projection["status"] == "missing_curve"
    assert projection["curve"] == []
    assert projection["summary"] == {
        "status": "missing",
        "source": "target_residual_convergence_curve",
        "point_count": 0,
        "start_dig_segment_index": None,
        "end_dig_segment_index": None,
        "target_positive_residual_depth_sum_start_m": None,
        "target_positive_residual_depth_sum_end_m": None,
        "target_positive_residual_depth_sum_delta_m": None,
        "target_overdig_depth_sum_start_m": None,
        "target_overdig_depth_sum_end_m": None,
        "target_overdig_depth_sum_delta_m": None,
        "target_removed_completion_ratio_start": None,
        "target_removed_completion_ratio_end": None,
        "target_removed_completion_ratio_delta": None,
        "outside_target_removed_depth_sum_start_m": None,
        "outside_target_removed_depth_sum_end_m": None,
        "outside_target_removed_depth_sum_delta_m": None,
        "diagnostic_trend": "missing",
    }


def test_target_convergence_projection_reports_insufficient_points() -> None:
    projection = build_target_residual_convergence_projection(
        [
            {
                "skill_name": "dig",
                "env_state": _env_state_with_compact_grid(
                    removed_depth=[0.10, 0.00, 0.30, 0.00, 0.20, 0.00],
                    valid_mask=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
                ),
            },
        ],
        grid_shape=[3, 2],
        row_start=0,
        row_end=2,
        col_start=0,
        col_end=1,
        target_depth_m=0.25,
    )

    assert projection["status"] == "present"
    assert len(projection["curve"]) == 1
    assert projection["summary"]["status"] == "insufficient_points"
    assert projection["summary"]["point_count"] == 1
    assert projection["summary"]["diagnostic_trend"] == "insufficient_points"
    assert projection["summary"]["target_positive_residual_depth_sum_delta_m"] is None


def test_target_convergence_projection_surfaces_invalid_target_spec() -> None:
    projection = build_target_residual_convergence_projection(
        [
            {
                "skill_name": "dig",
                "env_state": _env_state_with_compact_grid(
                    removed_depth=[0.10, 0.00, 0.30, 0.00, 0.20, 0.00],
                    valid_mask=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
                ),
            },
        ],
        grid_shape=[3, 2],
        row_start=2,
        row_end=2,
        col_start=0,
        col_end=1,
        target_depth_m=0.25,
    )

    assert projection["status"] == "invalid_rectangle_bounds"
    assert projection["target_grid"]["status"] == "invalid_rectangle_bounds"
    assert projection["curve"] == []
    assert projection["summary"]["status"] == "missing"
