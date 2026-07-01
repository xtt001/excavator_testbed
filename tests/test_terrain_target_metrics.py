from __future__ import annotations

from testbed.eval.terrain_target_grid import build_rectangular_target_grid
from testbed.eval.terrain_target_metrics import build_target_residual_metrics


def _missing_meter_profile(tolerance_m: float) -> dict[str, object]:
    return {
        "status": "cell_size_missing",
        "tolerance_m": tolerance_m,
        "cell_size_m": None,
        "cell_radius": None,
        "cell_radius_rule": "ceil(tolerance_m / cell_size_m)",
        "dilation_type": "chebyshev_8_neighbor_row_major",
        "dilated_target_cell_count": None,
        "valid_cell_count": None,
        "saturation_ratio": None,
        "intersection_cell_count": None,
        "union_cell_count": None,
        "iou": None,
        "outside_dilated_target_removed_depth_sum_m": None,
    }


def _unavailable_overlap(status: str, *, valid_cell_count: int) -> dict[str, object]:
    return {
        "status": status,
        "dilation_type": "chebyshev_8_neighbor_row_major",
        "cell_radius": None,
        "dilated_target_cell_count": None,
        "valid_cell_count": valid_cell_count,
        "saturation_ratio": None,
        "intersection_cell_count": None,
        "union_cell_count": None,
        "iou": None,
        "outside_dilated_target_removed_depth_sum_m": None,
    }


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
        "target_shape_overlap_diagnostics": {
            "status": "present",
            "source": "explicit_target_shape_overlap_diagnostics",
            "semantics": "diagnostic_only",
            "removed_active_depth_threshold_m": 0.0,
            "grid_shape": None,
            "cell_size_m": None,
            "raw_target_overlap": {
                "status": "present",
                "target_cell_count": 3,
                "removed_active_cell_count": 5,
                "intersection_cell_count": 3,
                "union_cell_count": 5,
                "iou": 0.6,
                "outside_raw_target_removed_depth_sum_m": 0.45,
            },
            "one_cell_dilated_target_overlap": _unavailable_overlap(
                "grid_shape_missing",
                valid_cell_count=5,
            ),
            "meter_tolerance_profiles": {
                "narrow_0_30m": _missing_meter_profile(0.3),
                "bucket_0_50m": _missing_meter_profile(0.5),
            },
        },
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


def test_target_residual_metrics_reports_raw_shape_overlap_without_grid_context() -> None:
    metrics = build_target_residual_metrics(
        removed_depth_grid_m=[0.10, 0.00, 0.35, 0.00, 0.20, 0.00],
        target_depth_grid_m=[0.25, 0.0, 0.25, 0.0, 0.0, 0.0],
        target_region_mask=[1, 0, 1, 0, 0, 0],
        valid_mask=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
    )

    diagnostics = metrics["target_shape_overlap_diagnostics"]
    assert diagnostics["status"] == "present"
    assert diagnostics["semantics"] == "diagnostic_only"
    assert diagnostics["removed_active_depth_threshold_m"] == 0.0
    assert diagnostics["raw_target_overlap"] == {
        "status": "present",
        "target_cell_count": 2,
        "removed_active_cell_count": 3,
        "intersection_cell_count": 2,
        "union_cell_count": 3,
        "iou": 0.666666666667,
        "outside_raw_target_removed_depth_sum_m": 0.2,
    }
    assert diagnostics["one_cell_dilated_target_overlap"] == _unavailable_overlap(
        "grid_shape_missing",
        valid_cell_count=6,
    )
    assert diagnostics["meter_tolerance_profiles"] == {
        "narrow_0_30m": _missing_meter_profile(0.3),
        "bucket_0_50m": _missing_meter_profile(0.5),
    }


def test_target_residual_metrics_reports_one_cell_dilated_overlap_and_saturation() -> None:
    metrics = build_target_residual_metrics(
        removed_depth_grid_m=[0.10, 0.00, 0.35, 0.00, 0.20, 0.00],
        target_depth_grid_m=[0.25, 0.0, 0.25, 0.0, 0.0, 0.0],
        target_region_mask=[1, 0, 1, 0, 0, 0],
        valid_mask=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        grid_shape=[3, 2],
    )

    diagnostics = metrics["target_shape_overlap_diagnostics"]
    assert diagnostics["grid_shape"] == [3, 2]
    assert diagnostics["one_cell_dilated_target_overlap"] == {
        "status": "present",
        "dilation_type": "chebyshev_8_neighbor_row_major",
        "cell_radius": 1,
        "dilated_target_cell_count": 6,
        "valid_cell_count": 6,
        "saturation_ratio": 1.0,
        "intersection_cell_count": 3,
        "union_cell_count": 6,
        "iou": 0.5,
        "outside_dilated_target_removed_depth_sum_m": 0.0,
    }
    assert diagnostics["meter_tolerance_profiles"]["narrow_0_30m"]["status"] == (
        "cell_size_missing"
    )


def test_target_residual_metrics_reports_meter_profiles_with_cell_size() -> None:
    removed_depth_grid_m = [0.0] * 25
    target_depth_grid_m = [0.0] * 25
    target_region_mask = [0.0] * 25
    removed_depth_grid_m[0] = 0.10
    removed_depth_grid_m[12] = 0.10
    removed_depth_grid_m[24] = 0.10
    target_depth_grid_m[12] = 0.20
    target_region_mask[12] = 1.0

    metrics = build_target_residual_metrics(
        removed_depth_grid_m=removed_depth_grid_m,
        target_depth_grid_m=target_depth_grid_m,
        target_region_mask=target_region_mask,
        valid_mask=[1.0] * 25,
        grid_shape=[5, 5],
        cell_size_m=0.4,
    )

    profiles = metrics["target_shape_overlap_diagnostics"]["meter_tolerance_profiles"]
    assert profiles["narrow_0_30m"] == {
        "status": "present",
        "tolerance_m": 0.3,
        "cell_size_m": 0.4,
        "cell_radius": 1,
        "cell_radius_rule": "ceil(tolerance_m / cell_size_m)",
        "dilation_type": "chebyshev_8_neighbor_row_major",
        "dilated_target_cell_count": 9,
        "valid_cell_count": 25,
        "saturation_ratio": 0.36,
        "intersection_cell_count": 1,
        "union_cell_count": 11,
        "iou": 0.090909090909,
        "outside_dilated_target_removed_depth_sum_m": 0.2,
    }
    assert profiles["bucket_0_50m"] == {
        "status": "present",
        "tolerance_m": 0.5,
        "cell_size_m": 0.4,
        "cell_radius": 2,
        "cell_radius_rule": "ceil(tolerance_m / cell_size_m)",
        "dilation_type": "chebyshev_8_neighbor_row_major",
        "dilated_target_cell_count": 25,
        "valid_cell_count": 25,
        "saturation_ratio": 1.0,
        "intersection_cell_count": 3,
        "union_cell_count": 25,
        "iou": 0.12,
        "outside_dilated_target_removed_depth_sum_m": 0.0,
    }


def test_target_residual_metrics_reports_no_target_no_active_overlap_without_success() -> None:
    metrics = build_target_residual_metrics(
        removed_depth_grid_m=[0.0, 0.0, 0.0],
        target_depth_grid_m=[0.0, 0.0, 0.0],
        target_region_mask=[0.0, 0.0, 0.0],
        valid_mask=[1.0, 1.0, 1.0],
        grid_shape=[1, 3],
    )

    diagnostics = metrics["target_shape_overlap_diagnostics"]
    assert diagnostics["raw_target_overlap"] == {
        "status": "present",
        "target_cell_count": 0,
        "removed_active_cell_count": 0,
        "intersection_cell_count": 0,
        "union_cell_count": 0,
        "iou": None,
        "outside_raw_target_removed_depth_sum_m": 0.0,
    }
    assert diagnostics["one_cell_dilated_target_overlap"] == {
        "status": "present",
        "dilation_type": "chebyshev_8_neighbor_row_major",
        "cell_radius": 1,
        "dilated_target_cell_count": 0,
        "valid_cell_count": 3,
        "saturation_ratio": 0.0,
        "intersection_cell_count": 0,
        "union_cell_count": 0,
        "iou": None,
        "outside_dilated_target_removed_depth_sum_m": 0.0,
    }


def test_target_residual_metrics_reports_grid_dependent_status_for_invalid_shape() -> None:
    metrics = build_target_residual_metrics(
        removed_depth_grid_m=[0.10, 0.20, 0.30],
        target_depth_grid_m=[0.20, 0.20, 0.20],
        target_region_mask=[1.0, 0.0, 0.0],
        valid_mask=[1.0, 1.0, 1.0],
        grid_shape=[2, 2],
        cell_size_m=0.4,
    )

    diagnostics = metrics["target_shape_overlap_diagnostics"]
    assert diagnostics["status"] == "present"
    assert diagnostics["raw_target_overlap"]["status"] == "present"
    assert diagnostics["one_cell_dilated_target_overlap"] == _unavailable_overlap(
        "invalid_grid_shape",
        valid_cell_count=3,
    )
    assert diagnostics["meter_tolerance_profiles"]["narrow_0_30m"]["status"] == (
        "invalid_grid_shape"
    )
    assert diagnostics["meter_tolerance_profiles"]["narrow_0_30m"]["cell_radius"] is None


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
    assert metrics["target_shape_overlap_diagnostics"]["status"] == (
        "invalid_grid_lengths"
    )
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
