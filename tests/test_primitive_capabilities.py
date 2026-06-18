from __future__ import annotations

from types import MappingProxyType

import numpy as np
import pytest

from testbed.data.schema import (
    ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
    ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_DUMP_CLEARANCE_OK_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
)
from testbed.planner.primitive_capabilities import PrimitiveObservationFacts


def test_observation_facts_extract_obs_values_without_mutating_inputs() -> None:
    qpos = np.asarray([1.0, 2.0, 3.0, 4.0], dtype=np.float32)
    qvel = np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_MASS_IN_BUCKET_IDX] = 7.0
    env_state[ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX] = 8.0
    task_metrics = {"mass_in_bucket_kg": 11.0}
    obs = {
        "qpos": qpos,
        "qvel": qvel,
        "env_state": env_state,
        "task_metrics": task_metrics,
        "reward_phase": "dump",
        "task_step_successes": {"dump": True},
    }

    facts = PrimitiveObservationFacts.from_obs(obs, action_dim=4)

    assert facts.qpos.tolist() == [1.0, 2.0, 3.0, 4.0]
    assert np.allclose(facts.qvel, [0.1, 0.2, 0.3, 0.4])
    assert facts.env_state[ENV_STATE_MASS_IN_BUCKET_IDX] == 7.0
    assert facts.task_metrics == MappingProxyType(task_metrics)
    assert facts.reward_phase == "dump"
    assert facts.task_step_successes == {"dump": True}
    assert facts.mass_in_bucket_kg == 11.0
    assert facts.deposited_mass_in_target_box_kg == 8.0
    assert np.array_equal(qpos, np.asarray([1.0, 2.0, 3.0, 4.0], dtype=np.float32))
    assert np.array_equal(qvel, np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32))
    assert env_state[ENV_STATE_MASS_IN_BUCKET_IDX] == 7.0
    assert facts.qpos.flags.writeable is False
    assert facts.qvel.flags.writeable is False
    assert facts.env_state.flags.writeable is False


def test_observation_facts_use_legacy_missing_defaults() -> None:
    facts = PrimitiveObservationFacts.from_obs({}, action_dim=4)

    assert facts.qpos.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert facts.qvel.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert facts.env_state.shape == (13,)
    assert facts.task_metrics == {}
    assert facts.reward_phase is None
    assert facts.task_step_successes is None
    assert facts.mass_in_bucket_kg == 0.0
    assert facts.deposited_mass_in_target_box_kg == 0.0


def test_observation_facts_target_geometry_matches_task_metric_precedence() -> None:
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX] = 99.0
    env_state[ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX] = 98.0
    env_state[ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX] = 97.0
    env_state[ENV_STATE_DUMP_CLEARANCE_OK_IDX] = 96.0
    env_state[ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX] = 95.0
    env_state[ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX] = 94.0
    env_state[ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = 93.0
    facts = PrimitiveObservationFacts.from_obs(
        {
            "env_state": env_state,
            "task_metrics": {
                "target_geometry_available": 1.0,
                "target_horizontal_distance_m": 1.0,
                "bucket_height_above_target_rim_m": 2.0,
                "bucket_over_target_footprint_mask": 3.0,
                "dump_clearance_ok_mask": 4.0,
                "bucket_dump_area_relative_x_m": 5.0,
                "bucket_dump_area_relative_z_m": 6.0,
                "bucket_dump_area_footprint_outside_distance_m": 7.0,
            },
        },
        action_dim=4,
    )

    assert facts.target_geometry() == {
        "target_horizontal_distance_m": 1.0,
        "bucket_height_above_target_rim_m": 2.0,
        "bucket_over_target_footprint_mask": 3.0,
        "dump_clearance_ok_mask": 4.0,
        "bucket_dump_area_relative_x_m": 5.0,
        "bucket_dump_area_relative_z_m": 6.0,
        "bucket_dump_area_footprint_outside_distance_m": 7.0,
    }


def test_observation_facts_target_geometry_preserves_legacy_unavailable_error() -> None:
    facts = PrimitiveObservationFacts.from_obs(
        {"task_metrics": {"target_geometry_available": 0.0}},
        action_dim=4,
    )

    with pytest.raises(RuntimeError, match="target_geometry_available=1"):
        facts.target_geometry()
