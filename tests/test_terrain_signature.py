from __future__ import annotations

import numpy as np
import pytest

from testbed.data.schema import (
    ENV_STATE_ORDER_V2_3,
    ENV_STATE_ORDER_V2_4,
    ENV_STATE_V2_3_DIM,
)
from testbed.data.terrain_signature import (
    TERRAIN_SIGNATURE_FIELD_NAMES,
    build_terrain_signature_v1,
    build_terrain_signature_v1_from_env_state,
)


def test_terrain_signature_v1_projects_v23_by_name_from_v24_mapping() -> None:
    values = {
        name: float(index) + 0.25
        for index, name in reversed(tuple(enumerate(ENV_STATE_ORDER_V2_4)))
    }

    signature = build_terrain_signature_v1(values)

    assert signature.schema == "terrain_signature_v1"
    assert signature.field_names == tuple(ENV_STATE_ORDER_V2_3)
    assert signature.field_names == TERRAIN_SIGNATURE_FIELD_NAMES
    assert signature.dimension == ENV_STATE_V2_3_DIM == 89
    assert signature.values == pytest.approx(
        tuple(values[name] for name in ENV_STATE_ORDER_V2_3)
    )
    assert not (
        set(signature.field_names)
        & set(ENV_STATE_ORDER_V2_4[len(ENV_STATE_ORDER_V2_3) :])
    )


def test_terrain_signature_v1_vector_projection_uses_explicit_field_order() -> None:
    permuted_order = tuple(reversed(ENV_STATE_ORDER_V2_4))
    value_by_name = {
        name: float(index) / 10.0 for index, name in enumerate(ENV_STATE_ORDER_V2_4)
    }
    vector = np.asarray(
        [value_by_name[name] for name in permuted_order],
        dtype=np.float64,
    )

    signature = build_terrain_signature_v1_from_env_state(
        vector,
        env_state_order=permuted_order,
    )

    assert signature.values == pytest.approx(
        tuple(value_by_name[name] for name in ENV_STATE_ORDER_V2_3)
    )
    assert signature.as_array().shape == (89,)


def test_terrain_signature_v1_rejects_missing_duplicate_or_nonfinite_fields() -> None:
    complete = {name: float(index) for index, name in enumerate(ENV_STATE_ORDER_V2_3)}
    missing = dict(complete)
    missing.pop(ENV_STATE_ORDER_V2_3[-1])
    with pytest.raises(ValueError, match="missing"):
        build_terrain_signature_v1(missing)

    bad = dict(complete)
    bad[ENV_STATE_ORDER_V2_3[4]] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        build_terrain_signature_v1(bad)

    with pytest.raises(ValueError, match="duplicate"):
        build_terrain_signature_v1_from_env_state(
            np.zeros(89),
            env_state_order=(ENV_STATE_ORDER_V2_3[:-1] + (ENV_STATE_ORDER_V2_3[0],)),
        )
