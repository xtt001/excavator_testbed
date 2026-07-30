from __future__ import annotations

import numpy as np
import pytest

from testbed.data.schema import (
    ENV_STATE_DIG_AREA_CELL_LONG_SIZE_IDX,
    ENV_STATE_DIG_AREA_CELL_SHORT_SIZE_IDX,
    ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX,
    ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX,
    ENV_STATE_DIG_AREA_LONG_AXIS_IDX,
    ENV_STATE_V2_4_DIM,
)
from testbed.planner.primitive.coverage.selection import (
    CoverageCandidateSelectionFacts,
    CoverageCorridorState,
    CoverageSelectionConfig,
    CoverageSelectionService,
)
from testbed.planner.primitive.coverage.swept_cells import (
    CoverageSweptFootprint,
)
from testbed.planner.primitive.coverage.wall_safety import (
    CoverageWallGeometry,
    CoverageWallSafetyConfig,
    CoverageWallSafetyService,
)


def _env(long_axis: int = 2) -> np.ndarray:
    env = np.zeros(ENV_STATE_V2_4_DIM, dtype=np.float32)
    env[ENV_STATE_DIG_AREA_LONG_AXIS_IDX] = long_axis
    env[ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX] = 3
    env[ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX] = 2
    env[ENV_STATE_DIG_AREA_CELL_LONG_SIZE_IDX] = 1.0
    env[ENV_STATE_DIG_AREA_CELL_SHORT_SIZE_IDX] = 1.25
    return env


@pytest.mark.parametrize(
    ("long_axis", "entry", "exit", "expected_centerline"),
    [
        (2, (0.4, 0.55), (0.4, 0.75), (5,)),
        (0, (0.55, 0.4), (0.75, 0.4), (5,)),
    ],
)
def test_physical_cell_mapping_supports_both_long_axes(
    long_axis: int,
    entry: tuple[float, float],
    exit: tuple[float, float],
    expected_centerline: tuple[int, ...],
) -> None:
    geometry = CoverageWallGeometry.from_env_state(_env(long_axis))
    footprint = CoverageSweptFootprint.from_segment(
        geometry=geometry,
        entry_x_m=entry[0],
        entry_z_m=entry[1],
        exit_x_m=exit[0],
        exit_z_m=exit[1],
        worktool_width_m=0.70,
    )

    assert footprint.centerline_cell_ids == expected_centerline
    assert 5 in footprint.swept_cell_ids


def test_failed_cycle6_logical_cell_four_sweeps_physical_cell_five() -> None:
    result = CoverageWallSafetyService(
        CoverageWallSafetyConfig(enabled=True)
    ).evaluate_segment(
        env_state=_env(long_axis=2),
        entry_x_m=0.635571,
        entry_z_m=0.549191,
        exit_x_m=0.41758,
        exit_z_m=0.717073,
    )

    assert result.centerline_cell_ids == (5,)
    assert result.swept_cell_ids == (3, 5)
    assert 4 not in result.centerline_cell_ids


def _selection_config() -> CoverageSelectionConfig:
    return CoverageSelectionConfig(
        candidate_layout="cell_weighted_3x2",
        prior_fields={
            "cut_depth_peak_m": {"p50": 0.3},
            "effective_deposit_delta_kg": {"p50": 50.0},
        },
        cut_depth_percentile="p50",
        use_env_removed_depth=True,
        max_attempts_per_corridor=3,
        recent_selection_penalty=0.0,
        unattempted_bonus=0.0,
        attempt_penalty=0.0,
        cell_confidence_weight=0.0,
        rare_cell_source_fraction_threshold=0.0,
        rare_cell_max_attempts=1,
        recent_row_selection_penalty=0.0,
        last_selected_corridor_id=-1,
        cycle_index=1,
        completed_dump_count=1,
        first_dig_strategy="coverage_score",
        first_dig_preferred_corridor_id=None,
        first_dig_preferred_bonus=0.0,
        first_dig_proximity_weight=0.0,
        first_dig_max_entry_distance_m=None,
        first_dig_qpos_delta_weight=0.0,
        first_dig_max_qpos_delta=None,
        pre_dig_align_controlled_dims=np.zeros(4, dtype=bool),
        state_exemplars_enabled=False,
        state_exemplar_score_weight=0.0,
        wall_safety=CoverageWallSafetyConfig(enabled=True),
    )


def test_exhausted_physical_swept_cell_is_hard_filtered_not_low_scored() -> None:
    wall = CoverageWallSafetyService(
        CoverageWallSafetyConfig(enabled=True)
    ).evaluate_segment(
        env_state=_env(),
        entry_x_m=0.635571,
        entry_z_m=0.549191,
        exit_x_m=0.41758,
        exit_z_m=0.717073,
    )
    blocked = CoverageCorridorState(
        corridor_id=4,
        cell_id=4,
        entry_x_m=0.635571,
        entry_z_m=0.549191,
        exit_x_m=0.41758,
        exit_z_m=0.717073,
        source_fraction=1.0,
        cut_depth_peak_m=0.3,
    )
    safe = CoverageCorridorState(
        corridor_id=2,
        cell_id=2,
        entry_x_m=-0.4,
        entry_z_m=0.0,
        exit_x_m=-0.2,
        exit_z_m=0.0,
        source_fraction=0.1,
        cut_depth_peak_m=0.3,
    )
    safe_wall = CoverageWallSafetyService(
        CoverageWallSafetyConfig(enabled=True)
    ).evaluate_segment(
        env_state=_env(),
        entry_x_m=safe.entry_x_m,
        entry_z_m=safe.entry_z_m,
        exit_x_m=safe.exit_x_m,
        exit_z_m=safe.exit_z_m,
    )
    facts = {
        4: CoverageCandidateSelectionFacts(
            remaining_depth_m=1.0,
            first_dig_entry_distance_m=0.0,
            first_dig_qpos_delta=np.zeros(4, dtype=np.float32),
            wall_safety=wall.with_depth_exhausted_cells({5}),
        ),
        2: CoverageCandidateSelectionFacts(
            remaining_depth_m=0.1,
            first_dig_entry_distance_m=0.0,
            first_dig_qpos_delta=np.zeros(4, dtype=np.float32),
            wall_safety=safe_wall,
        ),
    }

    result = CoverageSelectionService(_selection_config()).select(
        [blocked, safe],
        facts_by_corridor_id=facts,
        recent_row_reference=None,
    )
    trace = {item["corridor_id"]: item for item in result.candidate_scores}

    assert result.selected.corridor_id == 2
    assert trace[4]["selectable"] == 0
    assert trace[4]["rejection_reason"] == (
        "swept_footprint_intersects_depth_exhausted_cell"
    )
    assert trace[4]["depth_exhausted_swept_cell_ids"] == [5]
