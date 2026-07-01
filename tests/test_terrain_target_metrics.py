from __future__ import annotations

from testbed.eval.terrain_target_grid import build_rectangular_target_grid
from testbed.eval.terrain_target_metrics import build_target_residual_metrics


def test_target_residual_metrics_compare_removed_depth_to_target_shape() -> None:
    metrics = build_target_residual_metrics(
        removed_depth_grid_m=[0.10, 0.05, 0.30, 0.40, 0.20, 0.50],
        target_depth_grid_m=[0.20, 0.00, 0.20, 0.00, 0.00, 0.20],
        target_region_mask=[1.0, 0.0, 1.0, 0.0, 0.0, 1.0],
        valid_mask=[1.0, 1.0, 1.0, 1.0, 0.0, 1.0],
    )

    assert metrics == {
        "status": "present",
        "source": "explicit_target_grid_removed_depth_comparison",
        "profile": "explicit_target_shape_residual_metrics",
        "cell_count": 6,
        "valid_cell_count": 5,
        "target_cell_count": 3,
        "outside_target_cell_count": 2,
        "target_positive_residual_depth_sum_m": 0.1,
        "target_overdig_depth_sum_m": 0.4,
        "target_depth_sum_m": 0.6,
        "target_removed_depth_sum_m": 0.9,
        "target_removed_completion_ratio": 0.8333333333333334,
        "outside_target_removed_depth_sum_m": 0.45,
        "target_residual_depth_rmse_m": 0.191485421551,
        "target_residual_depth_mae_m": 0.166666666667,
        "target_residual_depth_abs_max_m": 0.3,
        "residual_depth_grid_m": [0.1, -0.05, -0.1, -0.4, -0.2, -0.3],
        "invalid_target_cell_count": 0,
        "validation_errors": [],
        "cell_size_status": "missing",
        "origin_status": "missing",
        "timestamp_status": "missing",
        "frame_transform_status": "missing",
        "height_grid_status": "missing",
        "elevation_grid_status": "missing",
        "confidence_grid_status": "missing",
    }


def test_target_residual_metrics_accept_target_grid_generator_output() -> None:
    target_grid = build_rectangular_target_grid(
        grid_shape=[3, 2],
        valid_mask=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        row_start=0,
        row_end=2,
        col_start=0,
        col_end=1,
        target_depth_m=0.25,
    )

    metrics = build_target_residual_metrics(
        removed_depth_grid_m=[0.10, 0.00, 0.35, 0.00, 0.20, 0.00],
        target_depth_grid_m=target_grid["target_depth_grid_m"],
        target_region_mask=target_grid["target_region_mask"],
        valid_mask=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
    )

    assert metrics["status"] == "present"
    assert metrics["target_cell_count"] == 2
    assert metrics["target_positive_residual_depth_sum_m"] == 0.15
    assert metrics["target_overdig_depth_sum_m"] == 0.1
    assert metrics["target_depth_sum_m"] == 0.5
    assert metrics["target_removed_depth_sum_m"] == 0.45
    assert metrics["target_removed_completion_ratio"] == 0.7
    assert metrics["outside_target_removed_depth_sum_m"] == 0.2
    assert metrics["target_residual_depth_rmse_m"] == 0.12747548784
    assert metrics["target_residual_depth_mae_m"] == 0.125
    assert metrics["target_residual_depth_abs_max_m"] == 0.15


def test_target_residual_metrics_reports_invalid_grid_lengths() -> None:
    metrics = build_target_residual_metrics(
        removed_depth_grid_m=[0.10, 0.20],
        target_depth_grid_m=[0.20, 0.20, 0.20],
        target_region_mask=[1.0, 1.0],
        valid_mask=[1.0, 1.0],
    )

    assert metrics["status"] == "invalid_grid_lengths"
    assert metrics["cell_count"] == 0
    assert metrics["valid_cell_count"] == 0
    assert metrics["target_cell_count"] == 0
    assert metrics["target_removed_completion_ratio"] is None
    assert metrics["residual_depth_grid_m"] == []
    assert metrics["validation_errors"] == [
        "removed_depth_grid_m, target_depth_grid_m, target_region_mask, and valid_mask must have matching non-empty lengths"
    ]


def test_target_residual_metrics_reports_invalid_depth_values() -> None:
    metrics = build_target_residual_metrics(
        removed_depth_grid_m=[0.10, -0.20, 0.30],
        target_depth_grid_m=[0.20, 0.20, 0.20],
        target_region_mask=[1.0, 1.0, 1.0],
        valid_mask=[1.0, 1.0, 1.0],
    )

    assert metrics["status"] == "invalid_depth_values"
    assert metrics["cell_count"] == 3
    assert metrics["valid_cell_count"] == 0
    assert metrics["target_cell_count"] == 0
    assert metrics["residual_depth_grid_m"] == []
    assert metrics["validation_errors"] == [
        "removed_depth_grid_m and target_depth_grid_m values must be finite and nonnegative"
    ]


def test_target_residual_metrics_reports_invalid_mask_values() -> None:
    metrics = build_target_residual_metrics(
        removed_depth_grid_m=[0.10, 0.20, 0.30],
        target_depth_grid_m=[0.20, 0.20, 0.20],
        target_region_mask=[1.0, "bad", 1.0],
        valid_mask=[1.0, 1.0, 1.0],
    )

    assert metrics["status"] == "invalid_mask_values"
    assert metrics["cell_count"] == 3
    assert metrics["valid_cell_count"] == 0
    assert metrics["target_cell_count"] == 0
    assert metrics["validation_errors"] == [
        "target_region_mask and valid_mask values must be finite numbers"
    ]


def test_target_residual_metrics_rejects_target_cells_outside_valid_mask() -> None:
    metrics = build_target_residual_metrics(
        removed_depth_grid_m=[0.10, 0.20, 0.30],
        target_depth_grid_m=[0.20, 0.20, 0.20],
        target_region_mask=[1.0, 1.0, 0.0],
        valid_mask=[1.0, 0.0, 1.0],
    )

    assert metrics["status"] == "invalid_target_region_mask"
    assert metrics["cell_count"] == 3
    assert metrics["valid_cell_count"] == 2
    assert metrics["target_cell_count"] == 0
    assert metrics["invalid_target_cell_count"] == 1
    assert metrics["target_positive_residual_depth_sum_m"] is None
    assert metrics["target_overdig_depth_sum_m"] is None
    assert metrics["outside_target_removed_depth_sum_m"] is None
    assert metrics["validation_errors"] == [
        "target_region_mask selects cells that are not valid"
    ]


def test_target_residual_metrics_reports_null_completion_ratio_without_target_depth() -> None:
    metrics = build_target_residual_metrics(
        removed_depth_grid_m=[0.10, 0.20, 0.30],
        target_depth_grid_m=[0.00, 0.00, 0.00],
        target_region_mask=[1.0, 1.0, 0.0],
        valid_mask=[1.0, 1.0, 1.0],
    )

    assert metrics["status"] == "present"
    assert metrics["target_cell_count"] == 2
    assert metrics["target_depth_sum_m"] == 0.0
    assert metrics["target_removed_completion_ratio"] is None
    assert metrics["target_overdig_depth_sum_m"] == 0.3
    assert metrics["target_residual_depth_rmse_m"] == 0.158113883008
    assert metrics["target_residual_depth_mae_m"] == 0.15
    assert metrics["target_residual_depth_abs_max_m"] == 0.2


def test_target_residual_metrics_reports_null_depth_error_without_target_cells() -> None:
    metrics = build_target_residual_metrics(
        removed_depth_grid_m=[0.10, 0.20, 0.30],
        target_depth_grid_m=[0.00, 0.00, 0.00],
        target_region_mask=[0.0, 0.0, 0.0],
        valid_mask=[1.0, 1.0, 1.0],
    )

    assert metrics["status"] == "present"
    assert metrics["target_cell_count"] == 0
    assert metrics["target_residual_depth_rmse_m"] is None
    assert metrics["target_residual_depth_mae_m"] is None
    assert metrics["target_residual_depth_abs_max_m"] is None
