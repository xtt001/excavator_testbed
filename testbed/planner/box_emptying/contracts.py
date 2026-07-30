"""Central live residual contract for the hard-bottom soil box."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.data.schema import (
    ENV_STATE_DIG_AREA_CURRENT_REMAINING_MASS_IDX,
    ENV_STATE_DIG_AREA_HARD_BOTTOM_DEPTH_IDX,
    ENV_STATE_DIG_AREA_INITIAL_REMAINING_MASS_IDX,
    ENV_STATE_DIG_AREA_REMAINING_MASS_FRACTION_IDX,
    ENV_STATE_DIG_AREA_REMAINING_MASS_VALID_MASK_IDX,
    ENV_STATE_DIG_AREA_REMAINING_SOIL_VOLUME_START_IDX,
    ENV_STATE_DIG_AREA_SOURCE_BULK_DENSITY_IDX,
    ENV_STATE_V2_4_DIM,
)

TERRAIN_BOX_RESIDUAL_SCHEMA = "terrain_box_residual_v1"
TERRAIN_BOX_CELL_COUNT = 6


class TerrainBoxResidualContractError(ValueError):
    """Raised when a live observation cannot satisfy the 107D contract."""


@dataclass(frozen=True)
class TerrainBoxResidual:
    """One validated 3x2 remaining-soil observation.

    The mass values already include static height-integrated source mass and
    dynamic soil/handled-as-particle mass still assigned to the box.  This
    class never attempts to reconstruct that Unity-owned measurement.
    """

    remaining_volume_m3: tuple[float, float, float, float, float, float]
    hard_bottom_depth_m: float
    soil_density_kg_m3: float
    current_remaining_mass_kg: float
    initial_remaining_mass_kg: float
    remaining_fraction: float
    valid: bool
    schema: str = TERRAIN_BOX_RESIDUAL_SCHEMA

    @classmethod
    def from_env_state(cls, env_state: Any) -> TerrainBoxResidual:
        row = np.asarray(env_state, dtype=np.float64).reshape(-1)
        if row.size < ENV_STATE_V2_4_DIM:
            raise TerrainBoxResidualContractError(
                f"env_state_v2_4_width: expected at least {ENV_STATE_V2_4_DIM}, "
                f"got {row.size}"
            )
        suffix = row[:ENV_STATE_V2_4_DIM]
        if not np.isfinite(suffix[ENV_STATE_DIG_AREA_HARD_BOTTOM_DEPTH_IDX:]).all():
            raise TerrainBoxResidualContractError("nonfinite_v2_4_residual_suffix")

        valid = bool(
            suffix[ENV_STATE_DIG_AREA_REMAINING_MASS_VALID_MASK_IDX] >= 0.5
        )
        if not valid:
            raise TerrainBoxResidualContractError("remaining_mass_invalid")

        volumes = suffix[
            ENV_STATE_DIG_AREA_REMAINING_SOIL_VOLUME_START_IDX :
            ENV_STATE_DIG_AREA_REMAINING_SOIL_VOLUME_START_IDX
            + TERRAIN_BOX_CELL_COUNT
        ]
        if np.any(volumes < 0.0):
            raise TerrainBoxResidualContractError("negative_remaining_volume")

        hard_bottom_depth = float(
            suffix[ENV_STATE_DIG_AREA_HARD_BOTTOM_DEPTH_IDX]
        )
        density = float(suffix[ENV_STATE_DIG_AREA_SOURCE_BULK_DENSITY_IDX])
        current_mass = float(
            suffix[ENV_STATE_DIG_AREA_CURRENT_REMAINING_MASS_IDX]
        )
        initial_mass = float(
            suffix[ENV_STATE_DIG_AREA_INITIAL_REMAINING_MASS_IDX]
        )
        fraction = float(
            suffix[ENV_STATE_DIG_AREA_REMAINING_MASS_FRACTION_IDX]
        )
        if hard_bottom_depth <= 0.0:
            raise TerrainBoxResidualContractError("hard_bottom_depth_nonpositive")
        if density <= 0.0:
            raise TerrainBoxResidualContractError("soil_density_nonpositive")
        if current_mass < 0.0 or initial_mass <= 0.0:
            raise TerrainBoxResidualContractError("remaining_mass_invalid_range")
        if fraction < 0.0 or fraction > 1.0:
            raise TerrainBoxResidualContractError(
                "remaining_fraction_out_of_range"
            )

        return cls(
            remaining_volume_m3=tuple(float(value) for value in volumes),  # type: ignore[arg-type]
            hard_bottom_depth_m=hard_bottom_depth,
            soil_density_kg_m3=density,
            current_remaining_mass_kg=current_mass,
            initial_remaining_mass_kg=initial_mass,
            remaining_fraction=fraction,
            valid=True,
        )


__all__ = [
    "TERRAIN_BOX_CELL_COUNT",
    "TERRAIN_BOX_RESIDUAL_SCHEMA",
    "TerrainBoxResidual",
    "TerrainBoxResidualContractError",
]
