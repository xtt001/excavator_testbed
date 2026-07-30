from __future__ import annotations

import numpy as np
import pytest

from testbed.data.schema import (
    ENV_STATE_ORDER_V2_3,
    ENV_STATE_ORDER_V2_4,
    ENV_STATE_V2_4_DIM,
)
from testbed.planner.box_emptying.contracts import (
    TerrainBoxResidual,
    TerrainBoxResidualContractError,
)


def _env_state_v2_4() -> np.ndarray:
    state = np.zeros(ENV_STATE_V2_4_DIM, dtype=np.float32)
    state[89] = 0.60
    state[90] = 1600.0
    state[91:97] = [0.50, 0.40, 0.30, 0.20, 0.10, 0.05]
    state[97] = 2480.0
    state[98] = 3000.0
    state[99] = 2480.0 / 3000.0
    state[100] = 1.0
    return state


def test_env_state_v2_4_is_append_only_107d_contract() -> None:
    assert ENV_STATE_V2_4_DIM == 107
    assert len(ENV_STATE_ORDER_V2_4) == ENV_STATE_V2_4_DIM
    assert ENV_STATE_ORDER_V2_4[: len(ENV_STATE_ORDER_V2_3)] == ENV_STATE_ORDER_V2_3
    assert ENV_STATE_ORDER_V2_4[89:] == (
        "dig_area_hard_bottom_depth_m",
        "dig_area_source_bulk_density_kg_m3",
        "dig_area_remaining_soil_volume_m3_r0_c0",
        "dig_area_remaining_soil_volume_m3_r0_c1",
        "dig_area_remaining_soil_volume_m3_r1_c0",
        "dig_area_remaining_soil_volume_m3_r1_c1",
        "dig_area_remaining_soil_volume_m3_r2_c0",
        "dig_area_remaining_soil_volume_m3_r2_c1",
        "dig_area_current_remaining_mass_kg",
        "dig_area_initial_remaining_mass_kg",
        "dig_area_remaining_mass_fraction",
        "dig_area_remaining_mass_valid_mask",
        "excavator_wall_contact_typed_mask",
        "excavator_wall_contact_step_max_force_n",
        "excavator_wall_contact_session_count",
        "bucket_factory_floor_contact_typed_mask",
        "bucket_factory_floor_contact_step_max_force_n",
        "bucket_factory_floor_contact_session_count",
    )


def test_terrain_box_residual_reads_the_107d_suffix() -> None:
    residual = TerrainBoxResidual.from_env_state(_env_state_v2_4())

    assert residual.remaining_volume_m3 == pytest.approx(
        (0.50, 0.40, 0.30, 0.20, 0.10, 0.05)
    )
    assert residual.hard_bottom_depth_m == pytest.approx(0.60)
    assert residual.soil_density_kg_m3 == pytest.approx(1600.0)
    assert residual.current_remaining_mass_kg == pytest.approx(2480.0)
    assert residual.initial_remaining_mass_kg == pytest.approx(3000.0)
    assert residual.remaining_fraction == pytest.approx(2480.0 / 3000.0)
    assert residual.valid is True


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda row: row[:89], "env_state_v2_4_width"),
        (lambda row: np.concatenate([row[:91], [-0.01], row[92:]]), "negative_remaining_volume"),
        (lambda row: np.concatenate([row[:99], [1.01], row[100:]]), "remaining_fraction_out_of_range"),
        (lambda row: np.concatenate([row[:100], [0.0], row[101:]]), "remaining_mass_invalid"),
    ],
)
def test_terrain_box_residual_rejects_invalid_live_contract(mutation, reason: str) -> None:
    with pytest.raises(TerrainBoxResidualContractError, match=reason):
        TerrainBoxResidual.from_env_state(mutation(_env_state_v2_4()))
