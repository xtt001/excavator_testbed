from __future__ import annotations

from testbed.data.schema import (
    ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
    ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX,
    ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
)
from testbed.eval.terrain_target_report import (
    build_explicit_target_residual_baseline_report,
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


def _baseline_report(records: list[dict[str, object]]) -> dict[str, object]:
    return build_explicit_target_residual_baseline_report(
        records,
        grid_shape=[3, 2],
        row_start=0,
        row_end=2,
        col_start=0,
        col_end=1,
        target_depth_m=0.25,
    )


def test_explicit_target_report_composes_latest_and_convergence_outputs() -> None:
    report = _baseline_report(
        [
            {
                "skill_name": "dig",
                "env_state": _env_state_with_compact_grid(
                    removed_depth=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                    valid_mask=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
                ),
            },
            {
                "skill_name": "dig",
                "env_state": _env_state_with_compact_grid(
                    removed_depth=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
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
        ]
    )

    assert report["status"] == "present"
    assert report["source"] == "explicit_target_residual_baseline_report"
    assert report["schema"] == "explicit_target_residual_baseline_report_v1"
    assert report["target_spec"] == {
        "grid_shape": [3, 2],
        "row_start": 0,
        "row_end": 2,
        "col_start": 0,
        "col_end": 1,
        "target_depth_m": 0.25,
        "profile": "explicit_t1_like_rectangular_shallow_pit",
    }
    assert report["latest_projection"]["status"] == "present"
    assert report["latest_projection"]["snapshot_row_index"] == 4
    assert report["convergence_projection"]["status"] == "present"
    assert len(report["convergence_projection"]["curve"]) == 2

    latest_metrics = report["latest_projection"]["target_residual_metrics"]
    convergence_summary = report["convergence_projection"]["summary"]
    summary = report["diagnostic_summary"]
    assert summary == {
        "latest_projection_status": "present",
        "convergence_projection_status": "present",
        "latest_snapshot_row_index": 4,
        "latest_target_positive_residual_depth_sum_m": 0.15,
        "latest_target_overdig_depth_sum_m": 0.05,
        "latest_target_removed_completion_ratio": 0.7,
        "latest_outside_target_removed_depth_sum_m": 0.2,
        "convergence_summary_status": "present",
        "convergence_point_count": 2,
        "convergence_diagnostic_trend": (
            "target_positive_residual_reduced_outside_removed_increased"
        ),
        "convergence_start_dig_segment_index": 1,
        "convergence_end_dig_segment_index": 2,
        "convergence_target_positive_residual_depth_sum_start_m": 0.5,
        "convergence_target_positive_residual_depth_sum_end_m": 0.15,
        "convergence_target_positive_residual_depth_sum_delta_m": -0.35,
        "convergence_target_overdig_depth_sum_start_m": 0.0,
        "convergence_target_overdig_depth_sum_end_m": 0.05,
        "convergence_target_overdig_depth_sum_delta_m": 0.05,
        "convergence_target_removed_completion_ratio_start": 0.0,
        "convergence_target_removed_completion_ratio_end": 0.7,
        "convergence_target_removed_completion_ratio_delta": 0.7,
        "convergence_outside_target_removed_depth_sum_start_m": 0.0,
        "convergence_outside_target_removed_depth_sum_end_m": 0.2,
        "convergence_outside_target_removed_depth_sum_delta_m": 0.2,
    }
    assert (
        summary["latest_target_positive_residual_depth_sum_m"]
        == latest_metrics["target_positive_residual_depth_sum_m"]
    )
    assert latest_metrics["target_residual_depth_rmse_m"] == 0.111803398875
    assert (
        report["convergence_projection"]["curve"][-1]["target_residual_metrics"][
            "target_residual_depth_mae_m"
        ]
        == 0.1
    )
    assert (
        summary["latest_target_overdig_depth_sum_m"]
        == latest_metrics["target_overdig_depth_sum_m"]
    )
    assert (
        summary["convergence_target_positive_residual_depth_sum_delta_m"]
        == convergence_summary["target_positive_residual_depth_sum_delta_m"]
    )
    assert (
        summary["convergence_diagnostic_trend"]
        == convergence_summary["diagnostic_trend"]
    )
    assert report["cell_size_status"] == "missing"
    assert report["origin_status"] == "missing"
    assert report["timestamp_status"] == "missing"
    assert report["frame_transform_status"] == "missing"
    assert report["height_grid_status"] == "missing"
    assert report["elevation_grid_status"] == "missing"
    assert report["confidence_grid_status"] == "missing"


def test_explicit_target_report_marks_partial_when_curve_is_missing() -> None:
    report = _baseline_report(
        [
            {
                "skill_name": "carry",
                "env_state": _env_state_with_compact_grid(
                    removed_depth=[0.10, 0.00, 0.30, 0.00, 0.20, 0.00],
                    valid_mask=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
                ),
            }
        ]
    )

    assert report["status"] == "partial"
    assert report["latest_projection"]["status"] == "present"
    assert report["convergence_projection"]["status"] == "missing_curve"
    assert report["diagnostic_summary"]["latest_projection_status"] == "present"
    assert (
        report["diagnostic_summary"]["convergence_projection_status"]
        == "missing_curve"
    )
    assert report["diagnostic_summary"]["convergence_point_count"] == 0
    assert report["diagnostic_summary"]["convergence_diagnostic_trend"] == "missing"


def test_explicit_target_report_surfaces_shared_target_validation_status() -> None:
    report = build_explicit_target_residual_baseline_report(
        [
            {
                "skill_name": "dig",
                "env_state": _env_state_with_compact_grid(
                    removed_depth=[0.10, 0.00, 0.30, 0.00, 0.20, 0.00],
                    valid_mask=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
                ),
            }
        ],
        grid_shape=[3, 2],
        row_start=2,
        row_end=2,
        col_start=0,
        col_end=1,
        target_depth_m=0.25,
    )

    assert report["status"] == "invalid_rectangle_bounds"
    assert report["latest_projection"]["status"] == "invalid_rectangle_bounds"
    assert report["convergence_projection"]["status"] == "invalid_rectangle_bounds"
    assert report["latest_projection"]["target_grid"]["status"] == (
        "invalid_rectangle_bounds"
    )
    assert report["convergence_projection"]["target_grid"]["status"] == (
        "invalid_rectangle_bounds"
    )
    assert report["diagnostic_summary"]["latest_projection_status"] == (
        "invalid_rectangle_bounds"
    )
    assert report["diagnostic_summary"]["convergence_projection_status"] == (
        "invalid_rectangle_bounds"
    )
