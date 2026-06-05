from __future__ import annotations

import numpy as np
import pytest

from testbed.data.schema import (
    ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
    ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX,
    ENV_STATE_DUMP_CLEARANCE_OK_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
    ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
)
from testbed.planner.snapshots import (
    bucket_depth_below_dig_area_plane_from_obs,
    bucket_depth_below_local_surface_from_obs,
    bucket_dig_area_cell_in_bounds_mask_from_obs,
    bucket_dig_area_contact_mask_from_obs,
    bucket_dig_area_pose_from_obs,
    bucket_tip_dig_area_pose_from_obs,
    build_planner_snapshot,
    deposited_mass_from_obs,
    dig_cell_id_from_obs,
    env_state_from_obs,
    mass_in_bucket_from_obs,
    min_distance_to_dig_area_from_obs,
    target_geometry_from_obs,
)


def test_snapshot_missing_env_keeps_nan_view_but_legacy_helpers_keep_defaults() -> None:
    snapshot = build_planner_snapshot(
        {},
        active_skill="dig",
        cycle_index=0,
        prev_action=None,
        boundary_event=None,
        action_dim=4,
    )

    assert np.isnan(snapshot.view.mass_in_bucket_kg)
    assert np.isnan(snapshot.view.deposited_mass_kg)
    assert mass_in_bucket_from_obs({}) == pytest.approx(0.0)
    assert deposited_mass_from_obs({}) == pytest.approx(0.0)
    assert min_distance_to_dig_area_from_obs({}) == pytest.approx(0.0)
    assert bucket_depth_below_dig_area_plane_from_obs({}) == pytest.approx(0.0)
    assert np.isnan(bucket_depth_below_local_surface_from_obs({}))
    assert env_state_from_obs({}).shape == (13,)


def test_legacy_helpers_prefer_task_metrics_then_env_state() -> None:
    env_state = _env_state()
    env_state[ENV_STATE_MASS_IN_BUCKET_IDX] = 12.0
    env_state[ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX] = 8.0
    env_state[ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX] = 0.42
    env_state[ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX] = 0.03
    env_state[ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX] = 0.02
    env_state[ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX] = 0.0

    obs = {
        "env_state": env_state,
        "task_metrics": {
            "mass_in_bucket_kg": 7.5,
            "bucket_contact_dig_area_mask": 1.0,
        },
    }

    assert mass_in_bucket_from_obs(obs) == pytest.approx(7.5)
    assert deposited_mass_from_obs(obs) == pytest.approx(8.0)
    assert min_distance_to_dig_area_from_obs(obs) == pytest.approx(0.42)
    assert bucket_depth_below_dig_area_plane_from_obs(obs) == pytest.approx(0.03)
    assert bucket_depth_below_local_surface_from_obs(obs) == pytest.approx(0.02)
    assert bucket_dig_area_contact_mask_from_obs(obs) is True


def test_pose_and_cell_helpers_match_legacy_env_state_parsing() -> None:
    env_state = _env_state()
    env_state[ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX] = 2.6
    env_state[ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX] = 1.0
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX] = 0.7
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX] = -0.1
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX] = -0.3
    env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX] = 0.8
    env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX] = -0.2
    env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX] = -0.4

    obs = {"env_state": env_state}

    assert dig_cell_id_from_obs(obs) == 3
    assert bucket_dig_area_cell_in_bounds_mask_from_obs(obs) is True
    assert bucket_dig_area_pose_from_obs(obs) == pytest.approx((0.7, -0.1, -0.3))
    assert bucket_tip_dig_area_pose_from_obs(obs) == pytest.approx((0.8, -0.2, -0.4))


def test_target_geometry_preserves_required_and_optional_fallbacks() -> None:
    env_state = _env_state()
    env_state[ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX] = 1.4
    env_state[ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX] = 0.6
    env_state[ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX] = 1.0
    env_state[ENV_STATE_DUMP_CLEARANCE_OK_IDX] = 1.0
    env_state[ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX] = 0.5
    env_state[ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX] = 1.2
    env_state[ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = 0.08

    geometry = target_geometry_from_obs(
        {
            "env_state": env_state,
            "task_metrics": {
                "target_geometry_available": 1.0,
                "target_horizontal_distance_m": float("nan"),
                "bucket_height_above_target_rim_m": 0.7,
                "bucket_dump_area_relative_x_m": float("nan"),
            },
        }
    )

    assert geometry["target_horizontal_distance_m"] == pytest.approx(1.4)
    assert geometry["bucket_height_above_target_rim_m"] == pytest.approx(0.7)
    assert geometry["bucket_over_target_footprint_mask"] == pytest.approx(1.0)
    assert geometry["dump_clearance_ok_mask"] == pytest.approx(1.0)
    assert np.isnan(geometry["bucket_dump_area_relative_x_m"])
    assert geometry["bucket_dump_area_relative_z_m"] == pytest.approx(1.2)
    assert geometry["bucket_dump_area_footprint_outside_distance_m"] == pytest.approx(
        0.08
    )


def test_target_geometry_keeps_legacy_errors() -> None:
    with pytest.raises(
        RuntimeError,
        match="requires Unity target geometry field 'target_horizontal_distance_m'",
    ):
        target_geometry_from_obs({"env_state": np.zeros(0, dtype=np.float32)})

    with pytest.raises(
        RuntimeError,
        match="requires target_geometry_available=1",
    ):
        target_geometry_from_obs(
            {
                "env_state": _env_state(),
                "task_metrics": {"target_geometry_available": 0.0},
            }
        )


def _env_state() -> np.ndarray:
    return np.zeros(64, dtype=np.float32)
