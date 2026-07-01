from __future__ import annotations

from testbed.data.schema import (
    ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
    ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX,
    ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
    ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX,
)
from testbed.eval.terrain_residual_metrics import build_terrain_residual_summary


def _env_state_with_grid(
    *,
    removed_depth: list[float],
    target_depth: list[float],
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
        ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX : ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX
        + 6
    ] = target_depth
    values[
        ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX : ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX
        + 6
    ] = valid_mask
    return values


def test_terrain_residual_summary_uses_latest_usable_grid_snapshot() -> None:
    records = [
        {
            "skill_name": "dig",
            "env_state": _env_state_with_grid(
                removed_depth=[0.00, 0.10, 0.20, 0.30, 0.40, 0.50],
                target_depth=[0.20, 0.20, 0.20, 0.20, 0.20, 0.20],
                valid_mask=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
            ),
        },
        {"skill_name": "carry", "env_state": [0.0] * 20},
        {
            "skill_name": "dig",
            "env_state": _env_state_with_grid(
                removed_depth=[0.05, 0.20, 0.35, 0.10, 0.00, 0.50],
                target_depth=[0.20, 0.20, 0.30, 0.00, 0.00, 0.40],
                valid_mask=[1.0, 1.0, 1.0, 0.0, 1.0, 1.0],
            ),
        },
    ]

    summary = build_terrain_residual_summary(records)

    assert summary["status"] == "present"
    assert summary["source"] == "rollout_jsonl_env_state_compact_dig_area_grid"
    assert summary["snapshot_row_index"] == 2
    assert summary["grid_shape"] == [3, 2]
    assert summary["cell_count"] == 6
    assert summary["valid_cell_count"] == 5
    assert summary["removed_depth_grid_m"] == [0.05, 0.20, 0.35, 0.10, 0.00, 0.50]
    assert summary["target_depth_grid_m"] == [0.20, 0.20, 0.30, 0.00, 0.00, 0.40]
    assert summary["residual_depth_grid_m"] == [0.15, 0.0, -0.05, -0.10, 0.0, -0.10]
    assert summary["positive_residual_depth_sum_m"] == 0.15
    assert summary["overdig_depth_sum_m"] == 0.15
    assert summary["target_depth_sum_m"] == 1.10
    assert summary["removed_depth_sum_m"] == 1.10
    assert summary["target_removed_completion_ratio"] == 0.8636363636363635
    assert summary["confidence_grid_status"] == "missing"
    assert summary["height_grid_status"] == "missing"
    assert summary["elevation_grid_status"] == "missing"
    assert summary["cell_size_status"] == "missing"
    assert summary["origin_status"] == "missing"
    assert summary["timestamp_status"] == "missing"
    assert summary["frame_transform_status"] == "missing"


def test_terrain_residual_summary_reports_dig_segment_convergence_curve() -> None:
    records = [
        {
            "skill_name": "dig",
            "env_state": _env_state_with_grid(
                removed_depth=[0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
                target_depth=[0.20, 0.20, 0.20, 0.20, 0.20, 0.20],
                valid_mask=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
            ),
        },
        {
            "skill_name": "dig",
            "env_state": _env_state_with_grid(
                removed_depth=[0.10, 0.20, 0.30, 0.40, 0.50, 0.60],
                target_depth=[0.30, 0.30, 0.30, 0.30, 0.30, 0.30],
                valid_mask=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
            ),
        },
        {"skill_name": "carry", "env_state": [0.0] * 64},
        {"skill_name": "dig", "env_state": [0.0] * 20},
        {
            "skill_name": "dig",
            "env_state": _env_state_with_grid(
                removed_depth=[0.25, 0.25, 0.35, 0.35, 0.30, 0.00],
                target_depth=[0.30, 0.30, 0.30, 0.30, 0.30, 0.30],
                valid_mask=[1.0, 0.0, 1.0, 1.0, 1.0, 1.0],
            ),
        },
        {"skill_name": "return", "env_state": [0.0] * 20},
    ]

    summary = build_terrain_residual_summary(records)

    assert summary["snapshot_row_index"] == 4
    assert summary["positive_residual_depth_sum_m"] == 0.35
    assert summary["overdig_depth_sum_m"] == 0.1
    assert summary["residual_convergence_curve_status"] == "present"
    assert summary["residual_convergence_curve_source"] == (
        "rollout_jsonl_contiguous_dig_segments_final_usable_env_state_compact_dig_area_grid"
    )
    assert summary["residual_convergence_curve_window"] == (
        "final usable compact-grid snapshot per contiguous rows where skill_name == 'dig'"
    )
    assert summary["residual_convergence_curve"] == [
        {
            "dig_segment_index": 1,
            "snapshot_row_index": 1,
            "positive_residual_depth_sum_m": 0.3,
            "overdig_depth_sum_m": 0.6,
            "target_depth_sum_m": 1.8,
            "removed_depth_sum_m": 2.1,
            "target_removed_completion_ratio": 0.8333333333333333,
            "valid_cell_count": 6,
        },
        {
            "dig_segment_index": 2,
            "snapshot_row_index": 4,
            "positive_residual_depth_sum_m": 0.35,
            "overdig_depth_sum_m": 0.1,
            "target_depth_sum_m": 1.5,
            "removed_depth_sum_m": 1.25,
            "target_removed_completion_ratio": 0.7666666666666666,
            "valid_cell_count": 5,
        },
    ]


def test_terrain_residual_summary_marks_shape_unknown_when_counts_do_not_match() -> None:
    summary = build_terrain_residual_summary(
        [
            {
                "env_state": _env_state_with_grid(
                    removed_depth=[0.00, 0.10, 0.20, 0.30, 0.40, 0.50],
                    target_depth=[0.20, 0.20, 0.20, 0.20, 0.20, 0.20],
                    valid_mask=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
                    long_count=4.0,
                    short_count=2.0,
                )
            }
        ]
    )

    assert summary["status"] == "present"
    assert summary["grid_shape"] is None
    assert summary["cell_count"] == 6
    assert summary["valid_cell_count"] == 6


def test_terrain_residual_summary_returns_missing_without_usable_snapshot() -> None:
    summary = build_terrain_residual_summary(
        [
            {"env_state": [0.0] * 20},
            {"env_state": "not-a-sequence"},
            {"skill_name": "dig"},
        ]
    )

    assert summary["status"] == "missing"
    assert summary["source"] == "rollout_jsonl_env_state_compact_dig_area_grid"
    assert summary["snapshot_row_index"] is None
    assert summary["grid_shape"] is None
    assert summary["cell_count"] == 0
    assert summary["valid_cell_count"] == 0
    assert summary["removed_depth_grid_m"] == []
    assert summary["target_depth_grid_m"] == []
    assert summary["residual_depth_grid_m"] == []
    assert summary["target_removed_completion_ratio"] is None
    assert summary["residual_convergence_curve_status"] == "missing"
    assert summary["residual_convergence_curve"] == []
