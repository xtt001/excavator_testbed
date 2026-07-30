"""Field-named terrain-signature contracts for goal-following models.

The v1 learning input intentionally remains the 89-field v2.3 environment
state.  Newer append-only live telemetry may be supplied to the builders, but
contact and hard-bottom suffixes are excluded by selecting the v2.3 fields by
name rather than by positional slicing.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.data.schema import ENV_STATE_ORDER_V2_3, ENV_STATE_V2_3_DIM

TERRAIN_SIGNATURE_SCHEMA_V1 = "terrain_signature_v1"
TERRAIN_SIGNATURE_FIELD_NAMES = tuple(ENV_STATE_ORDER_V2_3)
TERRAIN_SIGNATURE_DIM = ENV_STATE_V2_3_DIM


@dataclass(frozen=True)
class TerrainSignatureV1:
    """Immutable 89D terrain signature with its semantic field order."""

    values: tuple[float, ...]
    field_names: tuple[str, ...] = TERRAIN_SIGNATURE_FIELD_NAMES
    schema: str = TERRAIN_SIGNATURE_SCHEMA_V1

    def __post_init__(self) -> None:
        names = tuple(str(name) for name in self.field_names)
        values = tuple(float(value) for value in self.values)
        if self.schema != TERRAIN_SIGNATURE_SCHEMA_V1:
            raise ValueError(
                f"terrain signature schema must be {TERRAIN_SIGNATURE_SCHEMA_V1!r}"
            )
        if names != TERRAIN_SIGNATURE_FIELD_NAMES:
            raise ValueError(
                "terrain signature field_names must exactly match ENV_STATE_ORDER_V2_3"
            )
        if len(values) != TERRAIN_SIGNATURE_DIM:
            raise ValueError(
                f"terrain signature must contain {TERRAIN_SIGNATURE_DIM} values"
            )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("terrain signature values must be finite")
        object.__setattr__(self, "field_names", names)
        object.__setattr__(self, "values", values)

    @property
    def dimension(self) -> int:
        return len(self.values)

    def as_array(
        self,
        *,
        dtype: np.dtype[Any] | type[np.floating[Any]] = np.float64,
    ) -> np.ndarray:
        """Return a fresh dense vector in the declared semantic order."""

        return np.asarray(self.values, dtype=dtype).copy()

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation with explicit semantics."""

        return {
            "schema": self.schema,
            "dimension": self.dimension,
            "field_names": list(self.field_names),
            "values": list(self.values),
        }


def build_terrain_signature_v1(
    env_state_by_field: Mapping[str, Any],
) -> TerrainSignatureV1:
    """Build v1 from named environment-state values.

    Extra keys are allowed so a v2.4 live observation can be supplied without
    teaching the model about its append-only hard-bottom/contact suffix.
    """

    missing = [
        name for name in TERRAIN_SIGNATURE_FIELD_NAMES if name not in env_state_by_field
    ]
    if missing:
        preview = ", ".join(missing[:5])
        raise ValueError(
            f"terrain signature is missing required v2.3 fields: {preview}"
        )
    values: list[float] = []
    for name in TERRAIN_SIGNATURE_FIELD_NAMES:
        try:
            value = float(env_state_by_field[name])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"terrain signature field {name!r} must be numeric"
            ) from exc
        if not math.isfinite(value):
            raise ValueError(f"terrain signature field {name!r} must be finite")
        values.append(value)
    return TerrainSignatureV1(values=tuple(values))


def build_terrain_signature_v1_from_env_state(
    env_state: Sequence[float] | np.ndarray,
    *,
    env_state_order: Sequence[str],
) -> TerrainSignatureV1:
    """Project an ordered environment-state vector into v1 by field name."""

    names = tuple(str(name) for name in env_state_order)
    if len(names) != len(set(names)):
        raise ValueError("env_state_order contains duplicate field names")
    values = np.asarray(env_state, dtype=np.float64)
    if values.ndim != 1 or values.shape[0] != len(names):
        raise ValueError(
            "env_state must be a 1D vector matching env_state_order length"
        )
    return build_terrain_signature_v1(
        {name: values[index] for index, name in enumerate(names)}
    )


__all__ = [
    "TERRAIN_SIGNATURE_DIM",
    "TERRAIN_SIGNATURE_FIELD_NAMES",
    "TERRAIN_SIGNATURE_SCHEMA_V1",
    "TerrainSignatureV1",
    "build_terrain_signature_v1",
    "build_terrain_signature_v1_from_env_state",
]
