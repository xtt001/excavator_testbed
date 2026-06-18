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
    ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
    ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
)
from testbed.planner.primitive_capabilities import (
    BootstrapStatus,
    CarryTransitionStatus,
    DigTransitionStatus,
    PrimitiveObservationFacts,
)


class _BoundaryEvent:
    def __init__(
        self,
        *,
        qualified_dig_start: bool = False,
        dig_complete: bool = False,
        dump_committed_start: bool = False,
        release_onset: bool = False,
        dump_complete: bool = False,
        dump_start: bool = False,
        metrics: dict[str, float] | None = None,
    ) -> None:
        self.qualified_dig_start = qualified_dig_start
        self.dig_complete = dig_complete
        self.dump_committed_start = dump_committed_start
        self.release_onset = release_onset
        self.dump_complete = dump_complete
        self.dump_start = dump_start
        self.metrics = metrics


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


def test_bootstrap_status_records_first_qualified_dig_start_gate() -> None:
    facts = PrimitiveObservationFacts.from_obs({}, action_dim=4)

    ready = BootstrapStatus.from_inputs(
        observation=facts,
        boundary_event=_BoundaryEvent(qualified_dig_start=True),
        bootstrap_policy_present=True,
        bootstrap_end_mode="first_qualified_dig_start",
    )
    no_policy = BootstrapStatus.from_inputs(
        observation=facts,
        boundary_event=_BoundaryEvent(qualified_dig_start=True),
        bootstrap_policy_present=False,
        bootstrap_end_mode="first_qualified_dig_start",
    )

    assert ready.qualified_dig_start is True
    assert ready.should_end is True
    assert no_policy.should_end is False


def test_bootstrap_status_records_loaded_and_clear_gate_from_observation_facts() -> None:
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_MASS_IN_BUCKET_IDX] = 120.0
    env_state[ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX] = 0.75
    facts = PrimitiveObservationFacts.from_obs({"env_state": env_state}, action_dim=4)

    status = BootstrapStatus.from_inputs(
        observation=facts,
        boundary_event=None,
        bootstrap_policy_present=True,
        bootstrap_end_mode="loaded_and_clear",
        bootstrap_end_min_bucket_mass_kg=100.0,
        bootstrap_end_min_distance_to_dig_area_m=0.5,
    )

    assert status.mass_in_bucket_kg == 120.0
    assert status.min_distance_to_dig_area_m == 0.75
    assert status.loaded_and_clear_ready is True
    assert status.should_end is True


def test_bootstrap_status_records_scripted_qpos_gate_without_mutating_inputs() -> None:
    qpos = np.asarray([1.0, 2.0, 3.0, 4.0], dtype=np.float32)
    qvel = np.asarray([0.01, -0.02, 0.03, -0.04], dtype=np.float32)
    facts = PrimitiveObservationFacts.from_obs(
        {"qpos": qpos, "qvel": qvel},
        action_dim=4,
    )

    status = BootstrapStatus.from_inputs(
        observation=facts,
        boundary_event=None,
        bootstrap_policy_present=True,
        bootstrap_end_mode="scripted_qpos",
        scripted_bootstrap_target_qpos=np.asarray([1.0, 2.0, 3.0, 4.0]),
        scripted_bootstrap_qpos_tolerance=0.02,
        scripted_bootstrap_qvel_abs_max=0.08,
        scripted_bootstrap_hold_count=4,
        scripted_bootstrap_hold_steps=5,
        scripted_bootstrap_step_count=10,
        scripted_bootstrap_max_steps=240,
    )

    assert status.scripted_bootstrap_enabled is True
    assert status.scripted_qpos_close is True
    assert status.scripted_qvel_small is True
    assert status.scripted_target_reached is True
    assert status.scripted_timeout_reached is False
    assert status.should_end is True
    assert np.array_equal(qpos, np.asarray([1.0, 2.0, 3.0, 4.0], dtype=np.float32))
    assert np.array_equal(qvel, np.asarray([0.01, -0.02, 0.03, -0.04], dtype=np.float32))


def test_bootstrap_status_records_scripted_timeout_gate() -> None:
    facts = PrimitiveObservationFacts.from_obs({}, action_dim=4)

    status = BootstrapStatus.from_inputs(
        observation=facts,
        boundary_event=None,
        bootstrap_policy_present=True,
        bootstrap_end_mode="scripted_qpos",
        scripted_bootstrap_target_qpos=np.ones(4, dtype=np.float32),
        scripted_bootstrap_step_count=240,
        scripted_bootstrap_max_steps=240,
    )

    assert status.scripted_target_reached is False
    assert status.scripted_timeout_reached is True
    assert status.should_end is True


def test_dig_transition_status_records_boundary_completion_reason() -> None:
    facts = PrimitiveObservationFacts.from_obs({}, action_dim=4)

    status = DigTransitionStatus.from_inputs(
        observation=facts,
        boundary_event=_BoundaryEvent(dig_complete=True),
        dig_step_count=8,
    )

    assert status.dig_complete_boundary is True
    assert status.dig_to_carry_ready is True
    assert status.dig_to_carry_reason == "dig_complete_boundary"


def test_dig_transition_status_records_legacy_loaded_reason() -> None:
    facts = PrimitiveObservationFacts.from_obs(
        {"task_metrics": {"mass_in_bucket_kg": 120.0, "min_distance_to_dig_area_m": 0.75}},
        action_dim=4,
    )

    status = DigTransitionStatus.from_inputs(
        observation=facts,
        boundary_event=None,
        dig_step_count=10,
        dig_to_carry_min_bucket_mass_kg=100.0,
        dig_to_carry_target_bucket_mass_kg=100.0,
        dig_to_carry_min_distance_to_dig_area_m=0.5,
    )

    assert status.distance_ready is True
    assert status.dig_to_carry_ready is True
    assert status.dig_to_carry_reason == "loaded"


def test_dig_transition_status_records_semantic_loaded_reason_from_boundary_metrics() -> None:
    facts = PrimitiveObservationFacts.from_obs(
        {"task_metrics": {"mass_in_bucket_kg": 10.0, "min_distance_to_dig_area_m": 0.1}},
        action_dim=4,
    )

    status = DigTransitionStatus.from_inputs(
        observation=facts,
        boundary_event=_BoundaryEvent(
            metrics={"mass_in_bucket_kg": 130.0, "min_distance_to_dig_area_m": 0.8}
        ),
        semantic_boundary_profile_active=True,
        dig_step_count=10,
        dig_to_carry_target_bucket_mass_kg=100.0,
        dig_to_carry_min_distance_to_dig_area_m=0.5,
    )

    assert status.transition_mass_in_bucket_kg == 130.0
    assert status.transition_min_distance_to_dig_area_m == 0.8
    assert status.dig_to_carry_ready is True
    assert status.dig_to_carry_reason == "semantic_material_loaded"


def test_dig_transition_status_records_replan_and_exit_guard_without_mutation() -> None:
    facts = PrimitiveObservationFacts.from_obs(
        {"task_metrics": {"mass_in_bucket_kg": 5.0, "min_distance_to_dig_area_m": 0.75}},
        action_dim=4,
    )

    status = DigTransitionStatus.from_inputs(
        observation=facts,
        boundary_event=None,
        coverage_terminal_stop_requested=False,
        dig_step_count=20,
        dig_bad_replan_enabled=True,
        dig_bad_replan_max_steps=10,
        dig_bad_replan_min_bucket_mass_kg=15.0,
        dig_exit_guard_enabled=True,
        dig_exit_guard_min_steps=10,
        dig_exit_guard_min_bucket_mass_kg=20.0,
        dig_exit_guard_overshoot_m=0.3,
        dig_exit_overshoot_m=0.4,
    )

    assert status.dig_bad_replan_ready is True
    assert status.dig_exit_guard_ready is True


def test_carry_transition_status_records_committed_boundary_as_dump_ready() -> None:
    facts = PrimitiveObservationFacts.from_obs({}, action_dim=4)

    status = CarryTransitionStatus.from_inputs(
        observation=facts,
        boundary_event=_BoundaryEvent(dump_committed_start=True),
        dump_ready_hold_count=0,
        dump_ready_hold_steps=3,
    )

    assert status.dump_committed_event is True
    assert status.next_dump_ready_hold_count == 3
    assert status.ready_to_dump is True
    assert status.carry_to_dump_reason == "dump_committed_boundary"


def test_carry_transition_status_records_semantic_release_safety() -> None:
    facts = PrimitiveObservationFacts.from_obs(
        {"task_metrics": {"mass_in_bucket_kg": 10.0, "deposited_mass_in_target_box_kg": 40.0}},
        action_dim=4,
    )

    status = CarryTransitionStatus.from_inputs(
        observation=facts,
        boundary_event=None,
        semantic_boundary_profile_active=True,
        coverage_cycle_start_deposit_kg=15.0,
        dump_done_max_bucket_mass_kg=20.0,
        dump_done_min_deposit_delta_kg=10.0,
    )

    assert status.deposit_delta_since_cycle_start_kg == 25.0
    assert status.carry_release_safety_done is True
    assert status.carry_to_return_reason == "carry_to_return_release_safety"


def test_carry_transition_status_records_legacy_target_ready_hold() -> None:
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_MASS_IN_BUCKET_IDX] = 150.0
    env_state[ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX] = 0.30
    env_state[ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX] = 0.50
    env_state[ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX] = 1.0
    env_state[ENV_STATE_DUMP_CLEARANCE_OK_IDX] = 1.0
    facts = PrimitiveObservationFacts.from_obs({"env_state": env_state}, action_dim=4)

    status = CarryTransitionStatus.from_inputs(
        observation=facts,
        boundary_event=None,
        semantic_boundary_profile_active=False,
        dump_ready_hold_count=1,
        dump_ready_hold_steps=2,
        dump_ready_min_bucket_mass_kg=100.0,
        dump_ready_min_height_above_rim_m=0.45,
        dump_ready_require_over_footprint=True,
        dump_ready_require_clearance=True,
        dump_ready_max_horizontal_distance_m=0.60,
        dump_ready_position_mode="footprint",
    )

    assert status.dump_ready is True
    assert status.next_dump_ready_hold_count == 2
    assert status.ready_to_dump is True
    assert status.carry_to_dump_reason == "target_ready"


def test_carry_transition_status_keeps_legacy_dump_start_out_of_semantic_profile() -> None:
    facts = PrimitiveObservationFacts.from_obs({}, action_dim=4)

    status = CarryTransitionStatus.from_inputs(
        observation=facts,
        boundary_event=_BoundaryEvent(dump_start=True),
        semantic_boundary_profile_active=True,
        dump_ready_hold_count=1,
        dump_ready_hold_steps=2,
    )

    assert status.legacy_dump_start_event is False
    assert status.next_dump_ready_hold_count == 0
    assert status.ready_to_dump is False
