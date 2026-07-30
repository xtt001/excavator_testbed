from __future__ import annotations

import numpy as np
import pytest

from testbed.data.schema import (
    ENV_STATE_DIG_AREA_CELL_LONG_SIZE_IDX,
    ENV_STATE_DIG_AREA_CELL_SHORT_SIZE_IDX,
    ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX,
    ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX,
    ENV_STATE_DIG_AREA_LONG_AXIS_IDX,
    ENV_STATE_V2_3_DIM,
    ENV_STATE_V2_4_DIM,
)
from testbed.planner.primitive.coverage.wall_safety import (
    CONSERVATIVE_2D_WORKTOOL_SWEPT_FOOTPRINT_PROFILE,
    CoverageWallSafetyConfig,
    CoverageWallSafetyService,
)


def _env_state(
    *,
    dim: int = ENV_STATE_V2_4_DIM,
    long_axis: int = 2,
    grid_long_count: int = 3,
    grid_short_count: int = 2,
    cell_long_size_m: float = 1.0,
    cell_short_size_m: float = 1.25,
) -> np.ndarray:
    env_state = np.zeros(dim, dtype=np.float32)
    env_state[ENV_STATE_DIG_AREA_LONG_AXIS_IDX] = float(long_axis)
    env_state[ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX] = float(grid_long_count)
    env_state[ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX] = float(grid_short_count)
    env_state[ENV_STATE_DIG_AREA_CELL_LONG_SIZE_IDX] = float(cell_long_size_m)
    env_state[ENV_STATE_DIG_AREA_CELL_SHORT_SIZE_IDX] = float(cell_short_size_m)
    return env_state


def _service() -> CoverageWallSafetyService:
    return CoverageWallSafetyService(
        CoverageWallSafetyConfig(
            enabled=True,
            profile=CONSERVATIVE_2D_WORKTOOL_SWEPT_FOOTPRINT_PROFILE,
            worktool_width_m=0.70,
            hard_clearance_m=0.30,
            soft_clearance_m=0.45,
            max_score_penalty=1.0,
            missing_geometry="fail_closed",
        )
    )


def test_axis_aligned_segment_uses_full_segment_and_lateral_half_width() -> None:
    result = _service().evaluate_segment(
        env_state=_env_state(),
        entry_x_m=-0.40,
        entry_z_m=0.00,
        exit_x_m=0.40,
        exit_z_m=0.00,
    )

    assert result.box_half_x_m == pytest.approx(1.25)
    assert result.box_half_z_m == pytest.approx(1.50)
    assert result.footprint_outer_x_m == pytest.approx(0.40)
    assert result.footprint_outer_z_m == pytest.approx(0.35)
    assert result.clearance_x_m == pytest.approx(0.85)
    assert result.clearance_z_m == pytest.approx(1.15)
    assert result.minimum_clearance_m == pytest.approx(0.85)
    assert result.safety_class == "clear"
    assert result.eligible is True
    assert result.score_penalty == pytest.approx(0.0)


def test_diagonal_segment_inflates_both_local_axes() -> None:
    result = _service().evaluate_segment(
        env_state=_env_state(),
        entry_x_m=-0.50,
        entry_z_m=-0.50,
        exit_x_m=0.50,
        exit_z_m=0.50,
    )

    lateral = 0.35 / np.sqrt(2.0)
    assert result.footprint_outer_x_m == pytest.approx(0.50 + lateral)
    assert result.footprint_outer_z_m == pytest.approx(0.50 + lateral)
    assert result.minimum_clearance_m == pytest.approx(
        1.25 - 0.50 - lateral
    )
    assert result.safety_class == "clear"


@pytest.mark.parametrize(
    ("long_axis", "expected_half_x", "expected_half_z"),
    [
        (0, 1.50, 1.25),
        (2, 1.25, 1.50),
    ],
)
def test_long_axis_maps_3x2_geometry_to_local_xz(
    long_axis: int,
    expected_half_x: float,
    expected_half_z: float,
) -> None:
    result = _service().evaluate_segment(
        env_state=_env_state(long_axis=long_axis),
        entry_x_m=-0.10,
        entry_z_m=0.00,
        exit_x_m=0.10,
        exit_z_m=0.00,
    )

    assert result.box_half_x_m == pytest.approx(expected_half_x)
    assert result.box_half_z_m == pytest.approx(expected_half_z)


@pytest.mark.parametrize(
    ("entry_x_m", "expected_class", "expected_penalty"),
    [
        (0.65, "hard_reject", 1.0),
        (0.60, "near_wall", 1.0),
        (0.525, "near_wall", 0.5),
        (0.45, "clear", 0.0),
    ],
)
def test_hard_clearance_and_linear_soft_penalty_boundaries(
    entry_x_m: float,
    expected_class: str,
    expected_penalty: float,
) -> None:
    result = _service().evaluate_segment(
        env_state=_env_state(),
        entry_x_m=entry_x_m,
        entry_z_m=-0.10,
        exit_x_m=entry_x_m,
        exit_z_m=0.10,
    )

    assert result.safety_class == expected_class
    assert result.eligible is (expected_class != "hard_reject")
    assert result.score_penalty == pytest.approx(expected_penalty)


@pytest.mark.parametrize("dim", [ENV_STATE_V2_3_DIM, ENV_STATE_V2_4_DIM])
@pytest.mark.parametrize(
    "invalid_override",
    [
        {"long_axis": -1},
        {"long_axis": 1},
        {"grid_long_count": 0},
        {"grid_short_count": 3},
        {"cell_long_size_m": 0.0},
        {"cell_short_size_m": float("nan")},
    ],
)
def test_invalid_89d_or_107d_geometry_fails_closed(
    dim: int,
    invalid_override: dict[str, float | int],
) -> None:
    result = _service().evaluate_segment(
        env_state=_env_state(dim=dim, **invalid_override),
        entry_x_m=-0.10,
        entry_z_m=0.00,
        exit_x_m=0.10,
        exit_z_m=0.00,
    )

    assert result.eligible is False
    assert result.safety_class == "invalid_geometry"
    assert result.rejection_reason.startswith("wall_geometry_")


@pytest.mark.parametrize(
    ("name", "entry", "exit", "depth", "expected_class"),
    [
        ("F0", (0.552648, -1.029915), (0.308558, -1.014107), 0.419068, "hard_reject"),
        ("D1", (0.552648, -1.029915), (0.308558, -1.014107), 0.243690, "hard_reject"),
        ("C1", (0.615094, -0.439306), (0.516926, -0.276453), 0.419068, "near_wall"),
        ("DC1", (0.615094, -0.439306), (0.516926, -0.276453), 0.243690, "near_wall"),
    ],
)
def test_live_matrix_corridor_classification_is_independent_of_depth(
    name: str,
    entry: tuple[float, float],
    exit: tuple[float, float],
    depth: float,
    expected_class: str,
) -> None:
    raw_fields = {
        "operator_entry_x_m": entry[0],
        "operator_entry_z_m": entry[1],
        "operator_exit_x_m": exit[0],
        "operator_exit_z_m": exit[1],
        "operator_cut_depth_peak_m": depth,
    }

    result = _service().evaluate_raw_fields(
        env_state=_env_state(),
        raw_fields=raw_fields,
    )

    assert result.safety_class == expected_class, name
    assert result.eligible is (expected_class == "near_wall")
