from __future__ import annotations

from testbed.data.schema import (
    ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
    ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX,
    ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
)
from testbed.eval.terrain_target_projection import (
    build_latest_target_residual_projection,
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
