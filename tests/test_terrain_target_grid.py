from __future__ import annotations

from testbed.eval.terrain_target_grid import build_rectangular_target_grid


def test_rectangular_target_grid_builds_row_major_depth_grid() -> None:
    target = build_rectangular_target_grid(
        grid_shape=[3, 2],
        valid_mask=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        row_start=0,
        row_end=2,
        col_start=0,
        col_end=1,
        target_depth_m=0.25,
    )

    assert target == {
        "status": "present",
        "source": "explicit_rectangular_target_grid_spec",
        "profile": "explicit_t1_like_rectangular_shallow_pit",
        "grid_shape": [3, 2],
        "target_depth_grid_m": [0.25, 0.0, 0.25, 0.0, 0.0, 0.0],
        "target_region_mask": [1, 0, 1, 0, 0, 0],
        "valid_cell_count": 6,
        "target_cell_count": 2,
        "target_depth_sum_m": 0.5,
        "invalid_target_cell_count": 0,
        "rectangle_bounds": {
            "row_start": 0,
            "row_end": 2,
            "col_start": 0,
            "col_end": 1,
        },
        "validation_errors": [],
        "cell_size_status": "missing",
        "origin_status": "missing",
        "timestamp_status": "missing",
        "frame_transform_status": "missing",
        "height_grid_status": "missing",
        "elevation_grid_status": "missing",
        "confidence_grid_status": "missing",
    }


def test_rectangular_target_grid_rejects_invalid_target_cells() -> None:
    target = build_rectangular_target_grid(
        grid_shape=[3, 2],
        valid_mask=[1.0, 0.0, 1.0, 1.0, 1.0, 1.0],
        row_start=0,
        row_end=1,
        col_start=1,
        col_end=2,
        target_depth_m=0.2,
    )

    assert target["status"] == "invalid_target_region_mask"
    assert target["grid_shape"] == [3, 2]
    assert target["target_depth_grid_m"] == [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    assert target["target_region_mask"] == [0, 0, 0, 0, 0, 0]
    assert target["valid_cell_count"] == 5
    assert target["target_cell_count"] == 0
    assert target["target_depth_sum_m"] == 0.0
    assert target["invalid_target_cell_count"] == 1
    assert target["validation_errors"] == [
        "rectangle selects invalid cells; target cells are rejected"
    ]


def test_rectangular_target_grid_reports_invalid_shape_and_mask() -> None:
    target = build_rectangular_target_grid(
        grid_shape=[3, 0],
        valid_mask=[1.0, 1.0, 1.0],
        row_start=0,
        row_end=1,
        col_start=0,
        col_end=1,
        target_depth_m=0.2,
    )

    assert target["status"] == "invalid_grid_shape"
    assert target["grid_shape"] is None
    assert target["target_depth_grid_m"] == []
    assert target["target_region_mask"] == []
    assert target["valid_cell_count"] == 0
    assert target["target_cell_count"] == 0
    assert target["target_depth_sum_m"] == 0.0
    assert target["validation_errors"] == [
        "grid_shape must contain two positive integer counts"
    ]


def test_rectangular_target_grid_reports_invalid_mask_length() -> None:
    target = build_rectangular_target_grid(
        grid_shape=[3, 2],
        valid_mask=[1.0, 1.0, 1.0],
        row_start=0,
        row_end=1,
        col_start=0,
        col_end=1,
        target_depth_m=0.2,
    )

    assert target["status"] == "invalid_valid_mask"
    assert target["grid_shape"] == [3, 2]
    assert target["target_depth_grid_m"] == []
    assert target["target_region_mask"] == []
    assert target["valid_cell_count"] == 0
    assert target["validation_errors"] == [
        "valid_mask length must match grid cell count"
    ]


def test_rectangular_target_grid_reports_invalid_mask_value() -> None:
    target = build_rectangular_target_grid(
        grid_shape=[3, 2],
        valid_mask=[1.0, 1.0, "bad", 1.0, 1.0, 1.0],
        row_start=0,
        row_end=1,
        col_start=0,
        col_end=1,
        target_depth_m=0.2,
    )

    assert target["status"] == "invalid_valid_mask"
    assert target["grid_shape"] == [3, 2]
    assert target["target_depth_grid_m"] == []
    assert target["target_region_mask"] == []
    assert target["valid_cell_count"] == 0
    assert target["validation_errors"] == [
        "valid_mask values must be finite numbers"
    ]


def test_rectangular_target_grid_reports_invalid_depth() -> None:
    target = build_rectangular_target_grid(
        grid_shape=[3, 2],
        valid_mask=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        row_start=0,
        row_end=1,
        col_start=0,
        col_end=1,
        target_depth_m=0.0,
    )

    assert target["status"] == "invalid_target_depth"
    assert target["grid_shape"] == [3, 2]
    assert target["target_depth_grid_m"] == [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    assert target["target_region_mask"] == [0, 0, 0, 0, 0, 0]
    assert target["valid_cell_count"] == 6
    assert target["validation_errors"] == [
        "target_depth_m must be finite and greater than 0"
    ]


def test_rectangular_target_grid_reports_invalid_rectangle_bounds() -> None:
    target = build_rectangular_target_grid(
        grid_shape=[3, 2],
        valid_mask=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        row_start=2,
        row_end=2,
        col_start=0,
        col_end=1,
        target_depth_m=0.2,
    )

    assert target["status"] == "invalid_rectangle_bounds"
    assert target["grid_shape"] == [3, 2]
    assert target["target_depth_grid_m"] == [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    assert target["target_region_mask"] == [0, 0, 0, 0, 0, 0]
    assert target["valid_cell_count"] == 6
    assert target["validation_errors"] == [
        "rectangle bounds must be non-empty and within grid_shape"
    ]
