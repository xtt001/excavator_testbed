from __future__ import annotations

import numpy as np
import pytest

from testbed.contracts.primitive_profile import (
    CYCLE_BOUNDARY_PROFILE_LEGACY,
    CYCLE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS,
    CYCLE_BOUNDARY_PROFILES,
    normalize_cycle_boundary_profile,
)
from testbed.data.schema import (
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_DUMP_AREA_IDX,
    ENV_STATE_DUMP_CLEARANCE_OK_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
)
from testbed.planner.boundary_detector import (
    BOUNDARY_PROFILE_LEGACY,
    BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS,
    BOUNDARY_PROFILES,
    QUALIFIED_DIG_START_MODE_CONTACT_DEPTH,
    BoundaryDetector,
    BoundaryDetectorConfig,
)


def test_cycle_boundary_profile_contract_is_shared_by_detector() -> None:
    assert BOUNDARY_PROFILE_LEGACY == CYCLE_BOUNDARY_PROFILE_LEGACY
    assert BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS == (
        CYCLE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS
    )
    assert BOUNDARY_PROFILES == set(CYCLE_BOUNDARY_PROFILES)
    assert (
        normalize_cycle_boundary_profile(BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS)
        == BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS
    )

    with pytest.raises(ValueError, match="Unsupported cycle boundary_profile"):
        normalize_cycle_boundary_profile("unknown_profile")
    with pytest.raises(ValueError, match="Unsupported boundary_profile"):
        BoundaryDetector(
            BoundaryDetectorConfig(boundary_profile="unknown_profile")
        )


def test_spatial_mass_profile_event_table_for_one_cycle() -> None:
    detector = _spatial_mass_detector()
    rows = [
        (
            _env(mass=0.0, dig_distance=0.04, depth=0.03),
            {"dig_start": True},
        ),
        (
            _env(mass=30.0, dig_distance=0.12, depth=0.0),
            {},
        ),
        (
            _env(mass=30.0, dig_distance=0.12, depth=0.0),
            {"dig_complete": True},
        ),
        (
            _env(
                mass=30.0,
                dig_distance=0.30,
                depth=0.0,
                outside=0.10,
                relative_x=0.75,
                relative_z=1.20,
                height=0.70,
            ),
            {"dump_committed_start": True, "dump_start": True},
        ),
        (
            _env(
                mass=28.5,
                dig_distance=0.30,
                depth=0.0,
                deposited_dump_area=0.6,
                outside=0.40,
                relative_x=0.75,
                relative_z=1.20,
                height=0.70,
            ),
            {"release_onset": True},
        ),
        (
            _env(
                mass=0.0,
                dig_distance=0.30,
                depth=0.0,
                deposited_dump_area=0.6,
                outside=0.10,
                relative_x=0.75,
                relative_z=1.20,
                height=0.70,
            ),
            {"dump_complete": True, "dump_end": True},
        ),
    ]

    for env_state, expected in rows:
        event = detector.update(env_state=env_state, action=_ACTION, qpos=_QPOS)
        for field in (
            "dig_start",
            "dig_complete",
            "dump_committed_start",
            "dump_start",
            "release_onset",
            "dump_complete",
            "dump_end",
        ):
            assert getattr(event, field) is bool(expected.get(field, False))


def test_spatial_mass_profile_marks_next_dig_entry_as_boundary() -> None:
    detector = _spatial_mass_detector()
    for env_state in _complete_one_cycle_states():
        detector.update(env_state=env_state, action=_ACTION, qpos=_QPOS)

    event = detector.update(
        env_state=_env(mass=0.0, dig_distance=0.04, depth=0.03),
        action=_ACTION,
        qpos=_QPOS,
    )

    assert event.cycle_id == 1
    assert event.dig_start is True
    assert event.next_dig_entry_ready is True
    assert event.boundary is True


def _spatial_mass_detector() -> BoundaryDetector:
    return BoundaryDetector(
        BoundaryDetectorConfig(
            boundary_profile=BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS,
            qualified_dig_start_mode=QUALIFIED_DIG_START_MODE_CONTACT_DEPTH,
            residual_bucket_mass_thresh=15.0,
            deposit_plateau_steps=1,
            dig_complete_min_bucket_mass_kg=15.0,
            dig_complete_mass_plateau_hold_steps=1,
            dig_complete_departed_hold_steps=1,
            dump_committed_hold_steps=1,
            dump_committed_stable_window_steps=1,
        )
    )


def _complete_one_cycle_states() -> list[np.ndarray]:
    return [
        _env(mass=0.0, dig_distance=0.04, depth=0.03),
        _env(mass=30.0, dig_distance=0.12, depth=0.0),
        _env(mass=30.0, dig_distance=0.12, depth=0.0),
        _env(
            mass=30.0,
            dig_distance=0.30,
            depth=0.0,
            outside=0.10,
            relative_x=0.75,
            relative_z=1.20,
            height=0.70,
        ),
        _env(
            mass=28.5,
            dig_distance=0.30,
            depth=0.0,
            deposited_dump_area=0.6,
            outside=0.40,
            relative_x=0.75,
            relative_z=1.20,
            height=0.70,
        ),
        _env(
            mass=0.0,
            dig_distance=0.30,
            depth=0.0,
            deposited_dump_area=0.6,
            outside=0.10,
            relative_x=0.75,
            relative_z=1.20,
            height=0.70,
        ),
    ]


def _env(
    *,
    mass: float,
    dig_distance: float,
    depth: float,
    deposited_dump_area: float = 0.0,
    outside: float = 9.0,
    relative_x: float = 9.0,
    relative_z: float = 9.0,
    height: float = 0.0,
) -> np.ndarray:
    state = np.zeros(64, dtype=np.float32)
    state[ENV_STATE_MASS_IN_BUCKET_IDX] = float(mass)
    state[ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX] = float(dig_distance)
    state[ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX] = float(depth)
    state[ENV_STATE_DEPOSITED_MASS_IN_DUMP_AREA_IDX] = float(deposited_dump_area)
    state[ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = float(outside)
    state[ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX] = float(relative_x)
    state[ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX] = float(relative_z)
    state[ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX] = float(height)
    state[ENV_STATE_DUMP_CLEARANCE_OK_IDX] = 1.0
    return state


_ACTION = np.zeros(4, dtype=np.float32)
_QPOS = np.asarray([0.5, 0.6, 0.5, 0.6], dtype=np.float32)
